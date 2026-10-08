#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
observability_anchors.py —— 观测锚与口径校验器（四条外部方法落地）

所属产线：hyperframes 竖屏短视频产线（部署根由 PIPELINE_HOME / 仓库位置决定）
配置真源：config/observability_rules.json
资料来源（均为 2026-09-26 交换资料，来源可回溯）
--------------------------------------------------
1. kumiko      —— 无人值守任务三锚：字节数验投递完整 / 条数验载荷完整 / 版本号验数据新鲜
2. OCFANE      —— 「未更新 ≠ 执行失败」；零退出码 + 空消息不得判为健康
3. ruqiwg      —— UNSET ≠ EMPTY；绑定 universe 版本；INCOMPLETE 只入尝试分母且须用枚举原因码
4. AI-Film-Studio —— 读级 / 内容级两列新鲜度，区分「无事件上报」与「无事件发生」

设计要点
--------
1. 纯逻辑 + 声明式配置：判定表全部落在 config/observability_rules.json，脚本只做执行与校验；
   规则签名（rules_signature）随规则变更而变，供版本锚与留档引用。
2. 退出码语义与产线一致：0 = 通过（可能带 SKIP 但已如实列出）；2 = 校验不通过；1 = 用法/输入错误。
3. **SKIP ≠ 通过**：三锚缺证据一律记 SKIP 并如实列出，绝不读作 OK。
4. 锚断链（源文件不存在）判 FAIL，不得静默降级。

用法
----
  python3 scripts/observability_anchors.py signature
  python3 scripts/observability_anchors.py anchors   --file <留档.json>
  python3 scripts/observability_anchors.py health    --file <留档.json>
  python3 scripts/observability_anchors.py ledger    --file <留档.json>
  python3 scripts/observability_anchors.py freshness --file <留档.json>
  python3 scripts/observability_anchors.py check     --file <留档.json> [--json-out p]
  python3 scripts/observability_anchors.py self-test

留档 JSON 结构（各段可选，未提供的段在报告中显式列出，不读作通过）
----------------------------------------------------------------
  {
    "label": "20260927-paperclip",
    "universe_version": "1.1.0",
    "anchors":   {"byte_anchor": {...}, "item_anchor": {...}, "version_anchor": {...}},
    "health":    {"exit_code": 0, "message": "", "status": "NO_UPDATE",
                  "evidence": {"read_proof": true, "baseline_compared": true}},
    "ledger":    {"records": [{"id": "r1", "status": "COMPLETE", "universe_version": "1.1.0"}]},
    "freshness": {"read_level_freshness": "FRESH", "content_level_freshness": "ABSENT"}
  }
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DEFAULT = os.path.dirname(SCRIPT_DIR)
RULES_DEFAULT = os.path.join(ROOT_DEFAULT, "config", "observability_rules.json")

CORE_KEYS = ["anchors", "health", "ledger", "freshness"]

HEALTH_STATES = ["OK", "NO_UPDATE", "FAILED", "UNKNOWN"]
HEALTHY_STATES = ["OK", "NO_UPDATE"]

try:  # 与既有规范化链路保持一致（缺失时退化为原样序列化）
    import normalize_point as _npt
except Exception:  # pragma: no cover
    _npt = None


# ─────────────────────────────────────────────────────────────
# 配置与签名
# ─────────────────────────────────────────────────────────────

def load_rules(path=RULES_DEFAULT) -> dict:
    if not os.path.isfile(path):
        raise RuntimeError(f"配置真源不存在：{path}")
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def _normalize(text: str) -> str:
    return _npt.normalize_text(text) if _npt else text


def rules_core(rules: dict) -> dict:
    return {k: rules.get(k) for k in CORE_KEYS}


def rules_signature(rules: dict) -> str:
    """规则签名：核心判定表经规范化后取 sha256 前 16 位；规则变更即签名变更。"""
    text = json.dumps(rules_core(rules), sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(_normalize(text).encode("utf-8")).hexdigest()[:16]


def _resolve(path: str, root: str) -> str:
    return path if os.path.isabs(path) else os.path.join(root, path)


def _row(name, verdict, reason, **detail):
    return {"anchor": name, "verdict": verdict, "reason": reason, **detail}


def _navigate(doc, path: str):
    if not path:
        return doc
    cur = doc
    for seg in path.split("."):
        if isinstance(cur, dict):
            cur = cur.get(seg)
        elif isinstance(cur, list) and seg.isdigit():
            cur = cur[int(seg)] if int(seg) < len(cur) else None
        else:
            return None
    return cur


# ─────────────────────────────────────────────────────────────
# ① 三锚校验
# ─────────────────────────────────────────────────────────────

def check_anchors(anchors: dict, root: str = ROOT_DEFAULT) -> list:
    rows = []

    # —— 字节锚：投递完整 ——
    a = (anchors or {}).get("byte_anchor")
    if a is None:
        rows.append(_row("byte_anchor", "SKIP", "未提供字节锚，不得读作通过"))
    else:
        declared = a.get("declared_bytes")
        actual, src_used = a.get("actual_bytes"), None
        if actual is None and a.get("source"):
            p = _resolve(a["source"], root)
            if os.path.isfile(p):
                actual, src_used = os.path.getsize(p), os.path.abspath(p)
            else:
                rows.append(_row("byte_anchor", "FAIL", f"锚断链：源文件不存在 {p}", declared_bytes=declared))
                actual = None
        if actual is None and declared is not None and not any(r["anchor"] == "byte_anchor" for r in rows):
            rows.append(_row("byte_anchor", "SKIP", "仅声明字节数、无实测来源，不得读作通过", declared_bytes=declared))
        elif actual is not None and declared is None:
            rows.append(_row("byte_anchor", "SKIP", "有实测字节数但未声明期望值，无法验投递完整",
                             actual_bytes=actual, source=src_used))
        elif actual is not None and declared is not None and not any(r["anchor"] == "byte_anchor" for r in rows):
            if int(declared) != int(actual):
                rows.append(_row("byte_anchor", "FAIL",
                                 f"投递不完整：声明 {declared} 字节 ≠ 实收 {actual} 字节",
                                 declared_bytes=declared, actual_bytes=actual, source=src_used))
            else:
                rows.append(_row("byte_anchor", "OK", f"投递完整（{actual} 字节）",
                                 declared_bytes=declared, actual_bytes=actual, source=src_used))

    # —— 条数锚：载荷完整 ——
    b = (anchors or {}).get("item_anchor")
    if b is None:
        rows.append(_row("item_anchor", "SKIP", "未提供条数锚，不得读作通过"))
    else:
        declared = b.get("items_declared")
        actual, src_used = b.get("items_actual"), None
        if actual is None and b.get("source"):
            p = _resolve(b["source"], root)
            if os.path.isfile(p):
                src_used = os.path.abspath(p)
                try:
                    with open(p, "r", encoding="utf-8", errors="replace") as fh:
                        payload = json.load(fh)
                    paths = [s.strip() for s in (b.get("items_path") or "").split("+") if s.strip()] or [""]
                    total = 0
                    for seg in paths:  # 支持 "rows+extended_rows" 多段求和（载荷由多段清单拼成时）
                        node = _navigate(payload, seg)
                        if isinstance(node, (list, dict, str)):
                            total += len(node)
                        else:
                            total = None
                            break
                    actual = total
                except Exception as e:  # noqa: BLE001
                    rows.append(_row("item_anchor", "FAIL", f"锚断链：源文件不可解析（{e}）", source=src_used))
                    actual = None
                    src_used = None
            else:
                rows.append(_row("item_anchor", "FAIL", f"锚断链：源文件不存在 {p}", items_declared=declared))
        if not any(r["anchor"] == "item_anchor" for r in rows):
            if actual is None:
                rows.append(_row("item_anchor", "SKIP", "无实测条目数，不得读作通过", items_declared=declared))
            elif declared is None:
                rows.append(_row("item_anchor", "SKIP", "有实测条目数但未声明期望值，无法验载荷完整",
                                 items_actual=actual, source=src_used))
            elif int(declared) != int(actual):
                rows.append(_row("item_anchor", "FAIL",
                                 f"载荷不完整：声明 {declared} 条 ≠ 实际 {actual} 条",
                                 items_declared=declared, items_actual=actual, source=src_used,
                                 items_path=b.get("items_path") or "(顶层)"))
            else:
                rows.append(_row("item_anchor", "OK", f"载荷完整（{actual} 条）",
                                 items_declared=declared, items_actual=actual, source=src_used,
                                 items_path=b.get("items_path") or "(顶层)"))

    # —— 版本锚：数据新鲜 ——
    c = (anchors or {}).get("version_anchor")
    if c is None:
        rows.append(_row("version_anchor", "SKIP", "未提供版本锚，不得读作通过"))
    else:
        data_v = c.get("data_version")
        req_v = c.get("required_version", (anchors or {}).get("required_version"))
        if data_v is None or req_v is None:
            rows.append(_row("version_anchor", "SKIP", "版本证据不全（data_version / required_version 缺一）",
                             data_version=data_v, required_version=req_v))
        elif str(data_v) != str(req_v):
            rows.append(_row("version_anchor", "FAIL",
                             f"数据不新鲜：data_version={data_v} ≠ required_version={req_v}",
                             data_version=data_v, required_version=req_v))
        else:
            rows.append(_row("version_anchor", "OK", f"数据新鲜（版本 {data_v}）",
                             data_version=data_v, required_version=req_v))
    return rows


def anchors_verdict(rows: list) -> str:
    if any(r["verdict"] == "FAIL" for r in rows):
        return "FAIL"
    if all(r["verdict"] == "SKIP" for r in rows):
        return "SKIP_ONLY"
    return "OK"


# ─────────────────────────────────────────────────────────────
# ② 健康判定：未更新 ≠ 执行失败
# ─────────────────────────────────────────────────────────────

def judge_health(health: dict, rules: dict) -> dict:
    h = health or {}
    exit_code = h.get("exit_code")
    message = h.get("message")
    status = (h.get("status") or "").strip().upper() or None
    evidence = h.get("evidence") or {}
    need = (rules.get("health") or {}).get("no_update_evidence_fields") or ["read_proof", "baseline_compared"]
    verified = all(bool(evidence.get(k)) for k in need)
    msg_empty = message is None or str(message).strip() == ""

    if exit_code is None:
        state, reason = "UNKNOWN", "缺 exit_code：无执行证据，不得判为健康"
    elif int(exit_code) != 0:
        state, reason = "FAILED", f"退出码 {exit_code} ≠ 0 → 执行失败（消息有无不改变结论）"
    elif not msg_empty:
        state, reason = "OK", "退出码 0 且有非空消息 → 执行成功"
    elif status == "NO_UPDATE" and verified:
        state, reason = "NO_UPDATE", ("退出码 0 + 空消息，但有已核对证据（" + " && ".join(need) +
                                      "）→ 确为「无更新」，健康且 ≠ 执行失败")
    else:
        state, reason = "UNKNOWN", ("零退出码 + 空消息且无已核对证据 → 不得判为健康"
                                    "（无法区分「无更新」与「执行失败」）")
    return {
        "state": state,
        "healthy": state in HEALTHY_STATES,
        "is_failure": state == "FAILED",
        "reason": reason,
        "evidence_complete": verified,
        "inputs": {"exit_code": exit_code, "message_empty": msg_empty, "status": status},
    }


# ─────────────────────────────────────────────────────────────
# ③ 计量口径：UNSET ≠ EMPTY / 绑定 universe / INCOMPLETE
# ─────────────────────────────────────────────────────────────

def ledger_report(ledger: dict, rules: dict, default_universe=None) -> dict:
    spec = (rules.get("ledger") or {})
    statuses = spec.get("statuses") or {}
    reason_codes = set(spec.get("reason_codes") or [])
    current = (ledger or {}).get("current_universe_version", default_universe)
    records = (ledger or {}).get("records") or []

    buckets, problems = {k: [] for k in ["OK", "UNSET", "EMPTY", "INCOMPLETE", "COMPLETE"]}, []
    attempt_ids, success_ids, unset_ids = [], [], []
    incomparable, reason_tally = [], {}

    for r in records:
        rid = r.get("id")
        uv = r.get("universe_version")
        if uv is None:
            incomparable.append({"id": rid, "reason": "缺 universe_version → 不可比，不得混算"})
            continue
        if current is not None and str(uv) != str(current):
            incomparable.append({"id": rid, "reason": f"universe_version {uv} ≠ 当前 {current} → 不可比（防静默漂移）"})
            continue
        st = r.get("status")
        st_key = (st or "").strip().upper() or "UNSET"
        if st_key == "UNSET":
            unset_ids.append(rid)
            buckets["UNSET"].append(rid)
            continue
        if st_key == "EMPTY":
            buckets["EMPTY"].append(rid)
        elif st_key == "INCOMPLETE":
            buckets["INCOMPLETE"].append(rid)
            rc = r.get("reason_code")
            if not rc:
                problems.append(f"{rid}: INCOMPLETE 缺 reason_code（须用枚举原因码）")
            elif rc not in reason_codes:
                problems.append(f"{rid}: reason_code {rc!r} 不在枚举集内")
            else:
                reason_tally[rc] = reason_tally.get(rc, 0) + 1
        elif st_key == "COMPLETE":
            buckets["COMPLETE"].append(rid)
        else:
            problems.append(f"{rid}: 未知状态 {st!r}（状态机未定义，不得自行归类）")
            continue
        attempt_ids.append(rid)
        if statuses.get(st_key, {}).get("enters_success_numerator"):
            success_ids.append(rid)

    attempt, success = len(attempt_ids), len(success_ids)
    return {
        "current_universe_version": current,
        "universe_version_required": bool(spec.get("universe_version_required", True)),
        "records_total": len(records),
        "buckets": buckets,
        "unset_count": len(unset_ids),
        "unset_ids": unset_ids,
        "unset_note": "UNSET = 未上报，不进任何分母，也不得读作 EMPTY / 0",
        "incomparable_count": len(incomparable),
        "incomparable": incomparable,
        "attempt_denominator": attempt,
        "attempt_ids": attempt_ids,
        "success_numerator": success,
        "success_ids": success_ids,
        "success_ratio": (round(success / attempt, 4) if attempt else None),
        "incomplete_count": len(buckets["INCOMPLETE"]),
        "incomplete_reason_tally": reason_tally,
        "problems": problems,
        "ok": not problems,
    }


# ─────────────────────────────────────────────────────────────
# ④ 双新鲜度：无上报 vs 无发生
# ─────────────────────────────────────────────────────────────

def freshness_verdict(read_level, content_level, rules: dict) -> dict:
    table = {}
    for q in ((rules.get("freshness") or {}).get("quadrants") or []):
        table[(q["read_level_freshness"].upper(), q["content_level_freshness"].upper())] = q
    key = ((read_level or "").strip().upper(), (content_level or "").strip().upper())
    q = table.get(key)
    if q is None:
        return {"read_level_freshness": key[0] or None, "content_level_freshness": key[1] or None,
                "verdict": "ERROR", "meaning": "读级/内容级取值不在枚举内，无法判定（不得读作无事件发生）",
                "is_observed": False, "is_confirmed_absent": False}
    return {
        "read_level_freshness": key[0],
        "content_level_freshness": key[1],
        "verdict": q["verdict"],
        "meaning": q["meaning"],
        "is_observed": q["verdict"] in ("EVENT_OBSERVED", "NO_EVENT_OCCURRED"),
        "is_confirmed_absent": q["verdict"] == "NO_EVENT_OCCURRED",
    }


# ─────────────────────────────────────────────────────────────
# 综合校验
# ─────────────────────────────────────────────────────────────

def evaluate(doc: dict, root: str = ROOT_DEFAULT, rules: dict = None) -> dict:
    rules = rules or load_rules()
    report = {"label": doc.get("label"), "observability_version": rules.get("observability_version"),
              "rules_signature": rules_signature(rules), "checks_run": [], "checks_not_run": []}

    provided = [k for k in CORE_KEYS if doc.get(k) is not None]
    report["checks_run"] = provided
    report["checks_not_run"] = [k for k in CORE_KEYS if k not in provided]
    fails = []

    if doc.get("anchors") is not None:
        rows = check_anchors(doc["anchors"], root)
        verdict = anchors_verdict(rows)
        report["anchors"] = {"rows": rows, "verdict": verdict,
                             "counts": {v: sum(1 for r in rows if r["verdict"] == v) for v in ("OK", "FAIL", "SKIP")}}
        if verdict == "FAIL":
            fails.append("anchors")

    if doc.get("health") is not None:
        h = judge_health(doc["health"], rules)
        report["health"] = h
        if not h["healthy"]:
            fails.append("health")

    if doc.get("ledger") is not None:
        lg = ledger_report(doc["ledger"], rules, default_universe=doc.get("universe_version"))
        report["ledger"] = lg
        if not lg["ok"] or lg["incomparable_count"]:
            fails.append("ledger")

    if doc.get("freshness") is not None:
        f = doc["freshness"] or {}
        fr = freshness_verdict(f.get("read_level_freshness"), f.get("content_level_freshness"), rules)
        report["freshness"] = fr
        if fr["verdict"] in ("ERROR", "UNOBSERVED", "SYNC_SKIP_SUSPECT"):
            fails.append("freshness")

    report["overall"] = "OK" if not fails else "OBSERVABILITY_FAIL"
    report["failed_sections"] = fails
    report["exit_code"] = 0 if not fails else 2
    return report


# ─────────────────────────────────────────────────────────────
# 命令
# ─────────────────────────────────────────────────────────────

def _load_doc(path, root):
    full = _resolve(path, root)
    if not os.path.isfile(full):
        raise RuntimeError(f"输入文件不存在：{full}")
    with open(full, "r", encoding="utf-8") as fh:
        return json.load(fh)


def cmd_signature(args):
    rules = load_rules(args.rules)
    print("=" * 88)
    print("observability 观测层配置真源")
    print("=" * 88)
    print(f"  observability_version : {rules.get('observability_version')}")
    print(f"  rules_signature       : {rules_signature(rules)}")
    print(f"  规则核心段            : {', '.join(CORE_KEYS)}")
    print(f"  零退出码+空消息=健康  : {rules.get('health', {}).get('zero_exit_empty_message_is_healthy')}")
    print("=" * 88)
    return 0


def cmd_anchors(args):
    rules = load_rules(args.rules)
    doc = _load_doc(args.file, args.root)
    rows = check_anchors(doc.get("anchors", doc if "byte_anchor" in doc else {}), args.root)
    for r in rows:
        print(f"  [{r['verdict']:4}] {r['anchor']} — {r['reason']}")
    verdict = anchors_verdict(rows)
    print(f"  三锚结论：{verdict}")
    return 0 if verdict != "FAIL" else 2


def cmd_health(args):
    rules = load_rules(args.rules)
    doc = _load_doc(args.file, args.root)
    res = judge_health(doc.get("health", doc), rules)
    print(json.dumps(res, ensure_ascii=False, indent=2))
    return 0 if res["healthy"] else 2


def cmd_ledger(args):
    rules = load_rules(args.rules)
    doc = _load_doc(args.file, args.root)
    res = ledger_report(doc.get("ledger", doc), rules, default_universe=doc.get("universe_version"))
    print(json.dumps(res, ensure_ascii=False, indent=2))
    return 0 if res["ok"] and not res["incomparable_count"] else 2


def cmd_freshness(args):
    rules = load_rules(args.rules)
    doc = _load_doc(args.file, args.root)
    f = doc.get("freshness", doc)
    res = freshness_verdict(f.get("read_level_freshness"), f.get("content_level_freshness"), rules)
    print(json.dumps(res, ensure_ascii=False, indent=2))
    return 0 if res["is_observed"] else 2


def cmd_check(args):
    rules = load_rules(args.rules)
    doc = _load_doc(args.file, args.root)
    rep = evaluate(doc, args.root, rules)
    print(json.dumps(rep, ensure_ascii=False, indent=2))
    if args.json_out:
        out = _resolve(args.json_out, args.root)
        os.makedirs(os.path.dirname(out), exist_ok=True)
        with open(out, "w", encoding="utf-8") as fh:
            json.dump(rep, fh, ensure_ascii=False, indent=2)
            fh.write("\n")
        print(f"[written] {out}")
    return rep["exit_code"]


def cmd_self_test(args):
    rules = load_rules(args.rules)
    ok = True

    def ck(title, passed, detail=""):
        nonlocal ok
        ok = ok and bool(passed)
        print(f"  [{'PASS' if passed else 'FAIL'}] {title}" + (f"  ｜ {detail}" if detail else ""))

    def v(rows, name):
        return next((x["verdict"] for x in rows if x["anchor"] == name), None)

    def why(rows, name):
        return next((x["reason"] for x in rows if x["anchor"] == name), "")

    print("=" * 96)
    print("A. 三锚校验（kumiko）")
    print("=" * 96)
    ck("字节锚一致 → OK",
       v(check_anchors({"byte_anchor": {"declared_bytes": 100, "actual_bytes": 100}}), "byte_anchor") == "OK")
    rows = check_anchors({"byte_anchor": {"declared_bytes": 100, "actual_bytes": 88}})
    ck("字节锚不一致 → FAIL（投递不完整）", v(rows, "byte_anchor") == "FAIL" and "投递不完整" in why(rows, "byte_anchor"))
    ck("条数锚一致 → OK",
       v(check_anchors({"item_anchor": {"items_declared": 17, "items_actual": 17}}), "item_anchor") == "OK")
    rows = check_anchors({"item_anchor": {"items_declared": 17, "items_actual": 14}})
    ck("条数锚不一致 → FAIL（载荷不完整）", v(rows, "item_anchor") == "FAIL" and "载荷不完整" in why(rows, "item_anchor"))
    ck("版本锚一致 → OK",
       v(check_anchors({"version_anchor": {"data_version": "1.1.0", "required_version": "1.1.0"}}), "version_anchor") == "OK")
    rows = check_anchors({"version_anchor": {"data_version": "1.0.1", "required_version": "1.1.0"}})
    ck("版本锚不一致 → FAIL（数据不新鲜）", v(rows, "version_anchor") == "FAIL" and "数据不新鲜" in why(rows, "version_anchor"))
    rows = check_anchors({"byte_anchor": {"source": "__no_such_file__.json", "declared_bytes": 1}}, args.root)
    ck("锚断链（源文件不存在）→ FAIL，不得降级 SKIP", v(rows, "byte_anchor") == "FAIL" and "锚断链" in why(rows, "byte_anchor"))
    rows = check_anchors({})
    ck("三锚全缺证据 → SKIP_ONLY（SKIP ≠ 通过）",
       anchors_verdict(rows) == "SKIP_ONLY" and all(x["verdict"] == "SKIP" for x in rows))

    print("=" * 96)
    print("B. 健康判定（OCFANE）：未更新 ≠ 执行失败")
    print("=" * 96)
    ck("退出码非 0 → FAILED，且不是 NO_UPDATE",
       judge_health({"exit_code": 2, "message": "boom"}, rules)["state"] == "FAILED")
    h = judge_health({"exit_code": 0, "message": ""}, rules)
    ck("零退出码 + 空消息 + 无证据 → UNKNOWN（不得判健康）",
       h["state"] == "UNKNOWN" and h["healthy"] is False, h["reason"])
    ck("配置断言：零退出码+空消息不得读作健康",
       rules.get("health", {}).get("zero_exit_empty_message_is_healthy") is False)
    h = judge_health({"exit_code": 0, "message": "", "status": "OK"}, rules)
    ck("零退出码 + 空消息 + 自称 OK 但无证据 → UNKNOWN", h["state"] == "UNKNOWN")
    h = judge_health({"exit_code": 0, "message": "", "status": "NO_UPDATE",
                      "evidence": {"read_proof": True, "baseline_compared": True}}, rules)
    ck("零退出码 + 空消息 + 已核对无变化 → NO_UPDATE（健康，且 ≠ FAILED）",
       h["state"] == "NO_UPDATE" and h["healthy"] is True and h["is_failure"] is False, h["reason"])
    h = judge_health({"exit_code": 0, "message": "", "status": "NO_UPDATE",
                      "evidence": {"read_proof": True, "baseline_compared": False}}, rules)
    ck("自称无更新但证据不全 → 仍判 UNKNOWN", h["state"] == "UNKNOWN")
    ck("退出码 0 + 非空消息 → OK",
       judge_health({"exit_code": 0, "message": "job done"}, rules)["state"] == "OK")

    print("=" * 96)
    print("C. 计量口径（ruqiwg）")
    print("=" * 96)
    base = {"current_universe_version": "1.1.0"}
    lg = ledger_report({**base, "records": [
        {"id": "a", "status": "COMPLETE", "universe_version": "1.1.0"},
        {"id": "b", "status": "EMPTY", "universe_version": "1.1.0"},
        {"id": "c", "status": "INCOMPLETE", "universe_version": "1.1.0", "reason_code": "TIMEOUT"},
        {"id": "d", "status": "UNSET", "universe_version": "1.1.0"},
    ]}, rules)
    ck("UNSET 不进任何分母（且独立计数）",
       lg["unset_count"] == 1 and "d" not in lg["attempt_ids"] and lg["attempt_denominator"] == 3)
    ck("EMPTY 与 UNSET 严格区分（EMPTY 入分母）",
       lg["buckets"]["EMPTY"] == ["b"] and lg["buckets"]["UNSET"] == ["d"])
    ck("INCOMPLETE 只入尝试分母、不进成功分子",
       "c" in lg["attempt_ids"] and "c" not in lg["success_ids"] and lg["attempt_denominator"] == 3)
    ck("尝试分母=3 成功分子=2（a、b）", lg["attempt_denominator"] == 3 and lg["success_numerator"] == 2)
    ck("INCOMPLETE 原因码计入枚举统计", lg["incomplete_reason_tally"] == {"TIMEOUT": 1})
    lg2 = ledger_report({**base, "records": [
        {"id": "e", "status": "INCOMPLETE", "universe_version": "1.1.0"}]}, rules)
    ck("INCOMPLETE 缺 reason_code → 不可通过", lg2["ok"] is False and "缺 reason_code" in lg2["problems"][0])
    lg3 = ledger_report({**base, "records": [
        {"id": "f", "status": "INCOMPLETE", "universe_version": "1.1.0", "reason_code": "TOO_SLOW"}]}, rules)
    ck("原因码不在枚举集内 → 不可通过", lg3["ok"] is False and "不在枚举集内" in lg3["problems"][0])
    lg4 = ledger_report({**base, "records": [
        {"id": "g", "status": "COMPLETE", "universe_version": "1.0.1"}]}, rules)
    ck("universe 版本不匹配 → 不可比，拒绝混算",
       lg4["incomparable_count"] == 1 and lg4["attempt_denominator"] == 0)
    lg5 = ledger_report({**base, "records": [{"id": "h", "status": "COMPLETE"}]}, rules)
    ck("缺 universe_version → 不可比", lg5["incomparable_count"] == 1 and lg5["attempt_denominator"] == 0)

    print("=" * 96)
    print("D. 双新鲜度（AI-Film-Studio）：无上报 vs 无发生")
    print("=" * 96)
    ck("读级 STALE + 内容 ABSENT → UNOBSERVED（无事件上报）",
       freshness_verdict("STALE", "ABSENT", rules)["verdict"] == "UNOBSERVED")
    ck("读级 FRESH + 内容 ABSENT → NO_EVENT_OCCURRED（确认无事件发生）",
       freshness_verdict("FRESH", "ABSENT", rules)["verdict"] == "NO_EVENT_OCCURRED")
    ck("读级 FRESH + 内容 FRESH → EVENT_OBSERVED",
       freshness_verdict("FRESH", "FRESH", rules)["verdict"] == "EVENT_OBSERVED")
    ck("读级 STALE + 内容 FRESH → SYNC_SKIP_SUSPECT",
       freshness_verdict("STALE", "FRESH", rules)["verdict"] == "SYNC_SKIP_SUSPECT")
    ck("核心断言：无上报 ≠ 无发生（两象限语义必须不同）",
       freshness_verdict("STALE", "ABSENT", rules)["verdict"] !=
       freshness_verdict("FRESH", "ABSENT", rules)["verdict"])
    ck("取值非法 → ERROR，不得读作无事件发生",
       freshness_verdict("FRESH", "MISSING", rules)["verdict"] == "ERROR")

    print("=" * 96)
    print("E. 综合与签名")
    print("=" * 96)
    good = evaluate({
        "label": "selftest-ok", "universe_version": "1.1.0",
        "anchors": {"byte_anchor": {"declared_bytes": 10, "actual_bytes": 10},
                    "item_anchor": {"items_declared": 3, "items_actual": 3},
                    "version_anchor": {"data_version": "1.1.0", "required_version": "1.1.0"}},
        "health": {"exit_code": 0, "message": "", "status": "NO_UPDATE",
                   "evidence": {"read_proof": True, "baseline_compared": True}},
        "ledger": {"records": [{"id": "a", "status": "COMPLETE", "universe_version": "1.1.0"}]},
        "freshness": {"read_level_freshness": "FRESH", "content_level_freshness": "ABSENT"},
    }, args.root, rules)
    ck("全绿留档 → overall OK / exit 0", good["overall"] == "OK" and good["exit_code"] == 0)
    bad = evaluate({
        "label": "selftest-bad",
        "anchors": {"byte_anchor": {"declared_bytes": 10, "actual_bytes": 9}},
        "health": {"exit_code": 0, "message": ""},
        "freshness": {"read_level_freshness": "STALE", "content_level_freshness": "ABSENT"},
    }, args.root, rules)
    ck("三处异常 → overall FAIL / exit 2",
       bad["overall"] == "OBSERVABILITY_FAIL" and bad["exit_code"] == 2 and
       set(bad["failed_sections"]) == {"anchors", "health", "freshness"})
    ck("未提供段如实列出（checks_not_run），不读作通过", bad["checks_not_run"] == ["ledger"])
    sig = rules_signature(rules)
    mutated = json.loads(json.dumps(rules))
    mutated["freshness"]["quadrants"][0]["verdict"] = "NO_EVENT_OCCURRED"
    ck("规则变更 → 签名变更（观测层可自证新鲜）", rules_signature(mutated) != sig, f"{sig} → {rules_signature(mutated)}")
    ck("签名可复算（同输入同输出）", rules_signature(rules) == sig)

    print("-" * 96)
    print(f"结论：{'全部通过' if ok else '存在未通过项'}  规则签名={sig}")
    print("=" * 96)
    return 0 if ok else 2


def main(argv=None):
    p = argparse.ArgumentParser(description="观测锚与口径校验器（三锚 / 健康 / 计量 / 双新鲜度）")
    p.add_argument("--root", default=ROOT_DEFAULT)
    p.add_argument("--rules", default=RULES_DEFAULT)
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("signature", help="打印观测层配置版本与规则签名")
    sp.set_defaults(func=cmd_signature)

    ap = sub.add_parser("anchors", help="三锚校验")
    ap.add_argument("--file", required=True)
    ap.set_defaults(func=cmd_anchors)

    hp = sub.add_parser("health", help="执行结果健康判定")
    hp.add_argument("--file", required=True)
    hp.set_defaults(func=cmd_health)

    lp = sub.add_parser("ledger", help="回执计量口径校验")
    lp.add_argument("--file", required=True)
    lp.set_defaults(func=cmd_ledger)

    fp = sub.add_parser("freshness", help="读级/内容级双新鲜度判定")
    fp.add_argument("--file", required=True)
    fp.set_defaults(func=cmd_freshness)

    cp = sub.add_parser("check", help="综合校验一份观测留档")
    cp.add_argument("--file", required=True)
    cp.add_argument("--json-out", default=None)
    cp.set_defaults(func=cmd_check)

    tp = sub.add_parser("self-test", help="内置正负控自检")
    tp.set_defaults(func=cmd_self_test)

    args = p.parse_args(argv)
    try:
        return args.func(args)
    except RuntimeError as e:
        print(f"[error] {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
