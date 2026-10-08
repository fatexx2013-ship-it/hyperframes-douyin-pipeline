#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
negcontrol.py —— 两级负控执行器（不变量级 / 探索级）

所属产线：hyperframes 竖屏短视频产线（部署根由 PIPELINE_HOME / 仓库位置决定）
用例集  ：config/negcontrol_cases.json（caseset 1.0.0）
合同    ：config/param_contract.json

执行节奏（来自 AI-Film-Studio 的两级绑定做法）
--------------------------------------------
  不变量级（时基与取整、画幅方向、音频采样率、模型与权重版本）
      → 任何一次流水线变更（参数表版本升级）都全量跑，变更即验证
  探索级（采样器/步数/CFG/精度/分块尺寸/色彩空间/片段时长）
      → 按发布节奏抽跑，每周一次全量回归

负控的意义在于「能被证伪」：输入故意偏离合同口径，如果判定不变红，
就说明检测器失效。所以每条用例都写明 触发条件 → 输入 → 期望判定 → 必填字段，
并把素材 sha256 绑定进用例；素材被替换后必须重新标定。

用法
----
  python3 scripts/negcontrol.py run --level all
  python3 scripts/negcontrol.py run --level invariant          # 参数表版本变更时全量跑
  python3 scripts/negcontrol.py run --level exploratory        # 每周抽跑
  python3 scripts/negcontrol.py verify-materials               # 校验素材留档指纹
  python3 scripts/negcontrol.py status                         # 上次结果 + 两级节奏

退出码：0 = 全部用例达到期望；2 = 存在未达期望的用例（检测缺口）；1 = 用法/环境错误
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import sys
from datetime import datetime

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DEFAULT = os.path.dirname(SCRIPT_DIR)
sys.path.insert(0, SCRIPT_DIR)

import param_contract as pc  # noqa: E402

CASES_DEFAULT = os.path.join(ROOT_DEFAULT, "config", "negcontrol_cases.json")
CONTRACT_DEFAULT = os.path.join(ROOT_DEFAULT, "config", "param_contract.json")
OUT_DEFAULT = os.path.join(ROOT_DEFAULT, "reports", "negcontrol", "last_run.json")
CACHE_DIR = os.path.join(ROOT_DEFAULT, "reports", "negcontrol", "cache")


def now_iso():
    return datetime.now().strftime("%Y-%m-%dT%H:%M:%S")


def rel(root, p):
    try:
        return os.path.relpath(p, root)
    except Exception:
        return p


def material_fingerprint(path):
    if not os.path.isfile(path):
        return None
    return pc.file_fingerprint(path)


# ─────────────────────────────────────────────────────────────
# manifest 供给（带缓存，避免重复 ffprobe + 哈希）
# ─────────────────────────────────────────────────────────────

def manifest_for(root, video, story_dir=None, use_cache=True):
    path = video if os.path.isabs(video) else os.path.join(root, video)
    if not os.path.isfile(path):
        raise RuntimeError(f"素材不存在：{path}")
    fp = material_fingerprint(path)
    key = hashlib.sha256(f"{path}|{fp['sha256']}|{story_dir or ''}|m{pc.MANIFEST_VERSION}".encode("utf-8")).hexdigest()[:16]
    cache_file = os.path.join(CACHE_DIR, f"manifest_{key}.json")
    if use_cache and os.path.isfile(cache_file):
        cached = pc.read_json(cache_file)
        if cached and cached.get("derived"):
            return cached
    sd = story_dir
    if sd and not os.path.isabs(sd):
        sd = os.path.join(root, sd)
    m = pc.build_manifest(path, story_dir=sd, root=root)
    os.makedirs(CACHE_DIR, exist_ok=True)
    with open(cache_file, "w", encoding="utf-8") as f:
        json.dump(m, f, ensure_ascii=False, indent=2)
    return m


def _apply_mutation(obj, path, value):
    keys = path.split(".")
    node = obj
    for k in keys[:-1]:
        if k not in node or not isinstance(node[k], (dict, list)):
            raise RuntimeError(f"注入路径不存在：{path}")
        node = node[k]
    node[keys[-1]] = value


# ─────────────────────────────────────────────────────────────
# 单条用例执行
# ─────────────────────────────────────────────────────────────

def run_case(case, contract, root, use_cache=True):
    inp = case["input"]
    typ = inp["type"]
    base = cur = None
    materials = []

    if typ == "real_fixture":
        cur = manifest_for(root, inp["video"], inp.get("story_dir"), use_cache)
        materials.append(inp["video"])
        mode = "check"
    elif typ == "real_fixture_pair":
        base = manifest_for(root, inp["baseline_video"], inp.get("baseline_story_dir"), use_cache)
        cur = manifest_for(root, inp["video"], inp.get("story_dir"), use_cache)
        materials += [inp["baseline_video"], inp["video"]]
        mode = "diff"
    elif typ == "injected_manifest":
        base_path = os.path.join(root, inp["base_manifest"])
        base_raw = pc.read_json(base_path)
        if not base_raw:
            raise RuntimeError(f"底稿 manifest 不存在或不可解析：{base_path}")
        if inp.get("baseline_manifest"):
            base_path2 = os.path.join(root, inp["baseline_manifest"])
            base = pc.read_json(base_path2)
            if not base:
                raise RuntimeError(f"基线 manifest 不存在或不可解析：{base_path2}")
            materials.append(inp["baseline_manifest"])
        cur = copy.deepcopy(base_raw)
        for mu in inp.get("mutation", []):
            _apply_mutation(cur, mu["path"], mu["value"])
        cur["label"] = f"{base_raw.get('label')}#injected:{case['id']}"
        materials.append(inp["base_manifest"])
        mode = "check+injected"
    else:
        raise RuntimeError(f"未知的输入类型：{typ}")

    rep = pc.evaluate(contract, base=base, cur=cur)
    rows = {r["field"]: r for r in (rep["rows"] + rep.get("extended_rows", []))}

    checks = []
    for e in case.get("expect", []):
        r = rows.get(e["field"]) or {}
        got = r.get("verdict", "MISSING")
        reason = r.get("reason", "")
        ok = (got == e["verdict"]) and (not e.get("reason_contains") or e["reason_contains"] in reason)
        checks.append({
            "field": e["field"],
            "expected_verdict": e["verdict"],
            "actual_verdict": got,
            "expected_reason_contains": e.get("reason_contains"),
            "actual_reason": reason,
            "pass": ok,
        })

    passed = all(c["pass"] for c in checks) and bool(checks)

    # 把该用例关心的字段连同全表统计一起留档
    return {
        "id": case["id"],
        "title": case.get("title"),
        "level": case.get("level"),
        "case_type": case.get("case_type"),
        "trigger": (case.get("trigger") or {}).get("condition"),
        "mode": mode,
        "materials": [
            {"path": m,
             "fingerprint": (material_fingerprint(m if os.path.isabs(m) else os.path.join(root, m)) or {}).get("sha256")}
            for m in materials
        ],
        "checks": checks,
        "pass": passed,
        "report_summary": {
            "counts": rep["counts"],
            "overall": rep["overall"],
            "exit_code": rep["exit_code"],
            "all_rows": [{"field": r["field"], "verdict": r["verdict"], "reason": r["reason"],
                          "stability": r["stability"]} for r in rep["rows"]],
            "all_extended_rows": [{"field": r["field"], "verdict": r["verdict"], "reason": r["reason"],
                                   "stability": r["stability"]} for r in rep.get("extended_rows", [])],
        },
    }


# ─────────────────────────────────────────────────────────────
# 命令
# ─────────────────────────────────────────────────────────────

def cmd_run(args):
    cases_doc = pc.read_json(args.cases)
    contract = pc.read_json(args.contract)
    if not cases_doc or not contract:
        print("[error] 用例集或参数合同读不到", file=sys.stderr)
        return 1

    level_filter = args.level
    selected = [c for c in cases_doc["cases"]
                if level_filter == "all" or c.get("level") == level_filter]
    if not selected:
        print(f"[warn] 没有 level={level_filter} 的用例", file=sys.stderr)
        return 0

    policy = (cases_doc.get("execution_policy") or {}).get(level_filter) or {}
    print("=" * 96)
    print("两级负控执行（negcontrol）")
    print("=" * 96)
    print(f"用例集   : {cases_doc.get('caseset_version')}  共 {len(selected)} 条（level={level_filter}）")
    print(f"参数合同 : {contract.get('contract_version')}   {args.contract}")
    if policy:
        print(f"执行节奏 : {policy.get('label')} / 触发={policy.get('trigger')} / 模式={policy.get('run_mode')}")
    print("-" * 96)

    results = []
    for case in selected:
        try:
            r = run_case(case, contract, args.root, use_cache=not args.no_cache)
        except RuntimeError as e:
            print(f"[{case['id']}] ERROR：{e}")
            results.append({"id": case["id"], "title": case.get("title"), "level": case.get("level"),
                            "case_type": case.get("case_type"), "pass": False, "error": str(e),
                            "checks": [], "report_summary": {}})
            continue
        results.append(r)
        tag = "PASS" if r["pass"] else "FAIL(检测缺口)"
        print(f"[{r['id']}] {tag}  {r['level']}/{r['case_type']}  {r['title']}")
        for c in r["checks"]:
            mark = "ok" if c["pass"] else "xx"
            print(f"    {mark} {c['field']}: 期望 {c['expected_verdict']}"
                  f"{'（理由含「' + c['expected_reason_contains'] + '」）' if c['expected_reason_contains'] else ''}"
                  f" → 实测 {c['actual_verdict']} ｜ {c['actual_reason'][:76]}")
        print(f"    本次全表：{r['report_summary'].get('counts')} → {r['report_summary'].get('overall')}")

    n_pass = sum(1 for r in results if r["pass"])
    n_fail = len(results) - n_pass
    print("-" * 96)
    print(f"结果：PASS {n_pass} / 未达期望 {n_fail}")
    if n_fail:
        print("未达期望的用例（说明检测器对相应字段没有生效，必须修检测器或改用例）：")
        for r in results:
            if not r["pass"]:
                print(f"  - {r['id']}：{r.get('error') or [c['field'] for c in r['checks'] if not c['pass']]}")
    else:
        print("结论：全部负控/正控用例均达到期望 —— 故意喂错的输入都被判红，合规输入被判绿。")
    print("=" * 96)

    out = args.out or OUT_DEFAULT
    payload = {
        "run_at": now_iso(),
        "level_filter": level_filter,
        "caseset_version": cases_doc.get("caseset_version"),
        "contract_version": contract.get("contract_version"),
        "policy": policy,
        "results": results,
        "summary": {
            "total": len(results), "pass": n_pass, "not_as_expected": n_fail,
            "by_level": {lv: {"total": sum(1 for r in results if r.get("level") == lv),
                              "pass": sum(1 for r in results if r.get("level") == lv and r["pass"])}
                         for lv in sorted({r.get("level") for r in results if r.get("level")})},
            "verdict": "ALL_CASES_AS_EXPECTED" if n_fail == 0 else "DETECTION_GAP_FOUND",
        },
    }
    if n_fail:
        payload["summary"]["note"] = "存在未达期望用例；注意：这等价于「负控没判红」，是检测器缺陷信号，不是产线合格证明。"
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print(f"[archive] 运行留档（含素材指纹与合同版本）：{out}")
    return 2 if n_fail else 0


def cmd_verify_materials(args):
    cases_doc = pc.read_json(args.cases)
    if not cases_doc:
        print("[error] 用例集读不到", file=sys.stderr)
        return 1
    print("=" * 96)
    print("负控素材留档校验（素材被替换 → 旧对照基线失效）")
    print("=" * 96)
    bad = 0
    for case in cases_doc["cases"]:
        inp = case["input"]
        refs = []
        if inp.get("material_ref"):
            refs.append((inp["video"], inp["material_ref"]))
        if inp.get("baseline_material_ref"):
            refs.append((inp["baseline_video"], inp["baseline_material_ref"]))
        if inp.get("current_material_ref"):
            refs.append((inp["video"], inp["current_material_ref"]))
        for path, ref in refs:
            full = path if os.path.isabs(path) else os.path.join(args.root, path)
            fp = material_fingerprint(full)
            if not fp:
                print(f"  [MISS] {case['id']} 素材缺失：{path}")
                bad += 1
                continue
            ok_hash = (not ref.get("sha256")) or fp["sha256"] == ref["sha256"]
            ok_size = (not ref.get("size_bytes")) or fp["size_bytes"] == ref["size_bytes"]
            status = "OK  " if (ok_hash and ok_size) else "DRIFT"
            if not (ok_hash and ok_size):
                bad += 1
            print(f"  [{status}] {case['id']} {path}")
            print(f"          绑定 sha256 {str(ref.get('sha256'))[:20]}… / 实测 {fp['sha256'][:20]}…"
                  f" ｜ size {ref.get('size_bytes')} / {fp['size_bytes']}")
    print("-" * 96)
    print(f"结论：{'全部素材指纹与用例绑定一致' if bad == 0 else f'{bad} 处素材与绑定不一致，需重新标定用例'}")
    print("=" * 96)
    return 2 if bad else 0


def cmd_status(args):
    last = pc.read_json(args.out or OUT_DEFAULT)
    cases_doc = pc.read_json(args.cases) or {}
    print("=" * 96)
    print("负控状态")
    print("=" * 96)
    pol = cases_doc.get("execution_policy") or {}
    for lv in ("invariant", "exploratory"):
        p = pol.get(lv) or {}
        print(f"  {lv:<12} 触发：{p.get('trigger')}  模式：{p.get('run_mode')}  命令：{p.get('command')}")
    print("-" * 96)
    if not last:
        print("尚无运行留档；先执行：python3 scripts/negcontrol.py run --level all")
    else:
        s = last.get("summary", {})
        print(f"  上次运行：{last.get('run_at')}  level={last.get('level_filter')}  "
              f"caseset={last.get('caseset_version')}  contract={last.get('contract_version')}")
        print(f"  结果    ：PASS {s.get('pass')} / 未达期望 {s.get('not_as_expected')}  → {s.get('verdict')}")
        for r in last.get("results", []):
            print(f"    {'PASS' if r.get('pass') else 'FAIL'} {r.get('id'):<34}{r.get('level'):<12}{r.get('title')}")
    print("=" * 96)
    return 0


def main(argv=None):
    p = argparse.ArgumentParser(description="两级负控执行器")
    p.add_argument("--root", default=ROOT_DEFAULT)
    p.add_argument("--cases", default=CASES_DEFAULT)
    p.add_argument("--contract", default=CONTRACT_DEFAULT)
    sub = p.add_subparsers(dest="cmd", required=True)

    rp = sub.add_parser("run", help="执行负控用例")
    rp.add_argument("--level", default="all", choices=["all", "invariant", "exploratory"])
    rp.add_argument("--out", default=None)
    rp.add_argument("--no-cache", action="store_true", help="忽略 manifest 缓存，重新 snapshot")
    rp.set_defaults(func=cmd_run)

    vp = sub.add_parser("verify-materials", help="校验素材留档指纹与用例绑定是否一致")
    vp.set_defaults(func=cmd_verify_materials)

    sp = sub.add_parser("status", help="查看两级节奏与上次结果")
    sp.add_argument("--out", default=None)
    sp.set_defaults(func=cmd_status)

    args = p.parse_args(argv)
    try:
        return args.func(args)
    except RuntimeError as e:
        print(f"[error] {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
