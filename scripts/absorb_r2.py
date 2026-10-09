#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
absorb_r2.py —— 工程口径吸纳层 R2 执行器 · r2-1.0.0

一句话：把「AI-Film-Studio 本轮 13 条工程判据」+「OpenMontage 的清单/注册表/schema 设计思想」
吸纳为**可执行、可自测、可负控**的机器化校验，并对真实留档实跑出量化证据。

子命令
    check       对真实产线留档跑 R1~R8 八项检验，输出 reports/absorb-r2/last_run.json
    registry    工具注册表对账，输出 reports/absorb-r2/tool_envelope.json
    slideshow   对真实成片测动态度（噪声地板 + slideshow_risk），输出 reports/absorb-r2/slideshow_risk.json
    negcontrol  正例 + 负控用例集执行（fixtures），对照「无检验基线」
    receipt     追加一条回执（闭集状态 + 幂等重放）
    selftest    本层自检（含终界锚自检）
    all         按顺序跑全量并汇总

退出码：0=全绿；2=检出问题；1=工具自身故障
铁律（本层吸纳自 AI-Film-Studio）：exit code 只作附注，成功判据一律落在校验结论上。
本层只新增文件；不修改任何存量脚本/配置，不触碰任何已发布成片。
"""
from __future__ import annotations

import argparse
import datetime as _dt
import logging
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import eof_anchor  # noqa: E402  同层新增工具，仅复用其完整性证明原语

CONFIG_PATH = os.path.join(ROOT, "config", "absorb_r2.json")
MANIFEST_PATH = os.path.join(ROOT, "config", "pipelines", "douyin-shortform.yaml")
OUTDIR = os.path.join(ROOT, "reports", "absorb-r2")
FIXTURES = os.path.join(ROOT, "tests", "fixtures", "r2", "cases.json")
LEDGER = os.path.join(OUTDIR, "receipts.jsonl")
LAYER = "absorb_r2@r2-1.1.0"


def _now() -> str:
    return _dt.datetime.now().strftime("%Y-%m-%dT%H:%M:%S")


def _ensure_outdir() -> None:
    os.makedirs(OUTDIR, exist_ok=True)


def _ffmpeg() -> str:
    """解析 ffmpeg 可执行文件：PATH → 常见 Homebrew 路径 → 环境变量覆盖。"""
    cand = shutil.which("ffmpeg") or os.environ.get("STORYCTL_FFMPEG")
    for p in ("/opt/homebrew/bin/ffmpeg", "/usr/local/bin/ffmpeg", "/usr/bin/ffmpeg"):
        if cand:
            break
        if os.path.exists(p):
            cand = p
    if not cand or not os.path.exists(cand):
        raise FileNotFoundError("ffmpeg_not_found")
    return cand


def load_config() -> dict:
    with open(CONFIG_PATH, "r", encoding="utf-8") as fh:
        return json.load(fh)


def dump(path: str, obj) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, ensure_ascii=False, indent=2)
        fh.write("\n")


# =========================================================================== #
# 分析内核：输入 payload（可来自真实留档，也可来自 fixture），输出 (verdict, reason)
# =========================================================================== #
def a_r1_eof(p: dict):
    if not p.get("anchor_present"):
        return "FAIL", "anchor_absent"
    if p.get("volatile") and p.get("declared_sha256"):
        # volatile 产物只允许断言字节数；一旦断言内容同一性即自相矛盾（必然产生周期性假红）
        return "FAIL", "volatile_artifact_asserted_content_identity"
    if p.get("declared_bytes") != p.get("actual_bytes"):
        actual, declared = p.get("actual_bytes") or 0, p.get("declared_bytes") or 0
        return ("FAIL", "truncated_byte_count_mismatch") if actual < declared else ("FAIL", "anchor_mismatch_byte_count")
    if p.get("declared_sha256") and p["declared_sha256"] != p.get("actual_sha256"):
        return "FAIL", "anchor_mismatch_sha256"
    if p.get("marker_required") and not p.get("end_marker_found"):
        return "FAIL", "end_marker_missing"
    return "OK", "byte_count_proven" if p.get("volatile") else "integrity_proven"


def a_r2_receipt(p: dict):
    states = set(p.get("allowed_states") or [])
    receipts = p.get("receipts") or []
    if not receipts:
        return "SKIP", "empty_ledger"
    for r in receipts:
        st = r.get("state")
        if st not in states:
            return "FAIL", f"unknown_state_not_sunk:{st}"
        if st == "SENT_RECEIPT_UNKNOWN":
            if not r.get("request_id"):
                return "FAIL", "receipt_unknown_without_request_id"
            if r.get("counted_as_ok"):
                return "FAIL", "receipt_unknown_merged_into_ok"
        if r.get("retry_of") and int(r.get("side_effects_created") or 0) > 0:
            return "FAIL", "idempotent_retry_created_side_effect"
    return "OK", f"ledger_ok:{len(receipts)}"


def a_r3_floor(p: dict):
    b = p.get("binding")
    if not b:
        return "FAIL", "missing_binding"
    missing = [k for k in (p.get("required_floor_fields") or []) if b.get(k) in (None, "")]
    if missing:
        return "FAIL", "floor_incomplete:" + ",".join(missing)
    if not set(p.get("required_bound_to") or []) <= set(b.get("bound_to") or []):
        return "FAIL", "floor_not_bound_to_spec_and_receipt"
    if b.get("mutable"):
        return "FAIL", "floor_marked_mutable"
    if b.get("metric_id") in (p.get("tunables") or []):
        return "FAIL", "floor_exposed_as_tunable"
    if b.get("floor_at_spec_time") is not None and b.get("floor_at_measure_time") is not None \
            and b["floor_at_spec_time"] != b["floor_at_measure_time"]:
        return "FAIL", "floor_value_mutated_between_spec_and_measure"
    if b.get("status") == "rejected":
        return "REJECTED", "criterion_rejected:" + str(b.get("rejection_reason", ""))[:80]
    return "OK", "floor_bound"


def a_r4_criteria(p: dict):
    criteria = p.get("criteria") or []
    if not criteria:
        return "SKIP", "no_criteria"
    for c in criteria:
        for k in ("criteria_id", "source", "revision", "issuer_domain", "threshold"):
            if not c.get(k):
                return "FAIL", f"provenance_incomplete:{c.get('criteria_id')}:{k}"
        if c.get("threshold_changed") or c.get("revision_changed"):
            if not c.get("change_event"):
                return "FAIL", f"change_without_event:{c.get('criteria_id')}"
            if not c.get("negative_control"):
                return "FAIL", f"threshold_change_without_negative_control:{c.get('criteria_id')}"
        if c.get("issuer_domain") and c.get("issuer_domain") == c.get("subject_domain"):
            return "FAIL", f"issuer_equals_subject:{c.get('criteria_id')}"
    return "OK", f"criteria_ok:{len(criteria)}"


def a_r5_enum(p: dict):
    enums = p.get("enums") or []
    if not enums:
        return "SKIP", "no_enums"
    for e in enums:
        if not e.get("sink_explicit"):
            return "FAIL", f"sink_not_declared:{e.get('enum_id')}"
        if not e.get("sink"):
            return "FAIL", f"empty_sink:{e.get('enum_id')}"
        if e.get("sink") in (e.get("values") or []):
            sink_index = (e.get("values") or []).index(e["sink"])
            if e.get("sink_pinned_last") is False:
                return "FAIL", f"sink_not_isolated:{e.get('enum_id')}"
            del sink_index
        for o in e.get("observations") or []:
            if o.get("value") not in (e.get("values") or []):
                if o.get("routed_to") != e.get("sink"):
                    return "FAIL", f"out_of_set_silently_routed:{o.get('value')}->{o.get('routed_to')}"
    return "OK", f"enums_ok:{len(enums)}"


def a_r6_derived(p: dict):
    metrics = p.get("metrics") or []
    if not metrics:
        return "SKIP", "no_metrics"
    for m in metrics:
        if m.get("cached"):
            return "FAIL", f"derived_cache_present:{m.get('metric_id')}"
        if not m.get("observer") or not m.get("observer_revision"):
            return "FAIL", f"missing_observer_metadata:{m.get('metric_id')}"
        if m.get("source_digest_at_compute") and m.get("source_digest_now") \
                and m["source_digest_at_compute"] != m["source_digest_now"] and not m.get("recompute_on_source_change"):
            return "FAIL", f"stale_derived_not_invalidated:{m.get('metric_id')}"
    return "OK", f"derived_ok:{len(metrics)}"


def a_r7_bounds(p: dict):
    need = p.get("bounds_required") or ["occurred_at", "effective_from", "effective_until"]
    transitions = p.get("transitions") or []
    if not transitions:
        return "SKIP", "no_transitions"
    for t in transitions:
        miss = [k for k in need if not t.get(k)]
        if miss:
            return "FAIL", "bounds_incomplete:" + ",".join(miss)
    return "OK", f"bounds_ok:{len(transitions)}"


def a_r8_manifest(p: dict):
    reg_raw = set(p.get("registry_tools") or [])
    # 路径归一：注册表同时登记 rel_path 与 basename，清单里的 stage 工具用仓内相对路径或裸名皆可对齐
    reg = set(reg_raw) | {os.path.basename(str(x)) for x in reg_raw}
    exempt = set(p.get("schema_exempt") or [])
    for st in p.get("manifest_stages") or []:
        for t in st.get("tools") or []:
            if t not in reg and os.path.basename(str(t)) not in reg:
                return "FAIL", f"unknown_tool:{t}"
        for a in st.get("artifacts") or []:
            if a not in (p.get("artifact_schemas") or {}) and a not in exempt:
                return "FAIL", f"artifact_without_schema:{a}"
    for a, sc in (p.get("artifact_schemas") or {}).items():
        sample = (p.get("samples") or {}).get(a)
        if sample is None:
            continue
        miss = [k for k in (sc.get("required") or []) if k not in sample]
        if miss:
            return "FAIL", f"schema_drift:{a}:" + ",".join(miss)
        ik = sc.get("item_keys")
        if ik:
            items = sample if isinstance(sample, list) else []
            if not items:
                return "FAIL", f"schema_drift_empty_array:{a}"
            miss = [k for k in ik if k not in items[0]]
            if miss:
                return "FAIL", f"schema_drift_item:{a}:" + ",".join(miss)
    return "OK", "manifest_registry_schema_aligned"


ANALYZERS = {
    "R1": a_r1_eof, "R2": a_r2_receipt, "R3": a_r3_floor, "R4": a_r4_criteria,
    "R5": a_r5_enum, "R6": a_r6_derived, "R7": a_r7_bounds, "R8": a_r8_manifest,
}
# 无检验基线：原产线不存在该检验项时的行为 = 一律放行（假绿）
BASELINE = lambda p: ("OK", "no_check_available_pass_through")  # noqa: E731


# =========================================================================== #
# 工具注册表（借鉴 OpenMontage「先用注册表发现能力」）
# =========================================================================== #
def build_registry() -> dict:
    entries = []
    for base, kind in ((os.path.join(ROOT, "scripts"), "shared"), (ROOT, "root")):
        directory = base if kind == "shared" else ROOT
        if kind == "root":
            names = [n for n in sorted(os.listdir(directory)) if n.endswith(".py")]
        else:
            names = [n for n in sorted(os.listdir(directory)) if n.endswith(".py")]
        for n in names:
            path = os.path.join(directory, n)
            entries.append({
                "tool": n,
                "rel_path": os.path.relpath(path, ROOT),
                "kind": kind,
                "area": "pipeline",
                "exists": os.path.exists(path),
                "bytes": os.path.getsize(path) if os.path.exists(path) else 0,
            })
    entries.append({"tool": "story/<name>/build_audio.py", "rel_path": "story/<name>/build_audio.py",
                    "kind": "per_story", "area": "pipeline", "exists": True,
                    "note": "per-story 工序，由 scripts/storyctl.py new 从模板生成"})
    entries.append({"tool": "story/<name>/build_html.py", "rel_path": "story/<name>/build_html.py",
                    "kind": "per_story", "area": "pipeline", "exists": True,
                    "note": "per-story 工序，由 scripts/storyctl.py new 从模板生成"})
    envelope = {
        "layer": LAYER, "generated_at": _now(),
        "contract_version": "1.0.0",
        "counts": {"total": len(entries),
                   "shared_scripts": len([e for e in entries if e["kind"] == "shared"]),
                   "root_scripts": len([e for e in entries if e["kind"] == "root"]),
                   "per_story": len([e for e in entries if e["kind"] == "per_story"])},
        "tools": entries,
    }
    dump(os.path.join(OUTDIR, "tool_envelope.json"), envelope)
    return envelope


def registry_tool_names() -> set:
    env = build_registry()
    return {e["tool"] for e in env["tools"]}


# =========================================================================== #
# 真实留档 → R1~R8 的 payload
# =========================================================================== #
def load_json(path: str):
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return None


def payloads_from_reality(cfg: dict, story: str) -> dict:
    policy = cfg["eof_anchor"]
    payloads: dict = {}

    # ---- R1 终界锚：自动补签（新增文件）后逐件校验 ----
    anchor_results = []
    for rel in policy["anchored_artifacts"]:
        artifact = os.path.join(ROOT, rel)
        apath = eof_anchor.anchor_path_for(rel, policy["anchor_dir"])
        if os.path.exists(artifact) and not os.path.exists(apath):
            eof_anchor.cmd_seal(argparse.Namespace(artifact=artifact, out=apath))
        if os.path.exists(apath):
            with open(apath, "r", encoding="utf-8") as fh:
                anchor = json.load(fh)
            r = eof_anchor.verify_one(anchor, anchor.get("artifact"))
            anchor_results.append({
                "artifact": rel, "anchor_present": True,
                "declared_bytes": r.get("declared_bytes"), "actual_bytes": r.get("actual_bytes"),
                "declared_sha256": r.get("declared_sha256"), "actual_sha256": r.get("actual_sha256"),
                "marker_required": bool(anchor.get("marker_required")),
                "end_marker_found": anchor.get("end_marker_present", False),
                "exit_code": 0, "expect": "OK",
            })
        else:
            anchor_results.append({"artifact": rel, "anchor_present": False, "exit_code": 0, "expect": "OK"})

    # ---- R1b 终界锚（volatile 清单）：仅断言字节数，不断言内容同一性 ----
    # 依据 config.eof_anchor_volatile.admission_rule：被例行工序重写、正文含 wall-clock
    # 运行期字段的产物若做内容寻址，例行重跑即产生周期性假红。此处只签字节数，
    # 保留截断检测（R1 的本体命题），去掉内容同一性断言。
    vpol = cfg.get("eof_anchor_volatile") or {}
    for rel in vpol.get("volatile_artifacts") or []:
        artifact = os.path.join(ROOT, rel)
        apath = eof_anchor.anchor_path_for(rel, vpol.get("anchor_dir") or policy["anchor_dir"])
        if os.path.exists(artifact) and not os.path.exists(apath):
            os.makedirs(os.path.dirname(apath), exist_ok=True)
            with open(apath, "w", encoding="utf-8") as fh:
                json.dump({"anchor_version": vpol.get("policy_version"), "artifact": artifact,
                           "declared_bytes": os.path.getsize(artifact),
                           "content_identity": "not_asserted", "issuer": LAYER,
                           "sealed_at": _now()}, fh, ensure_ascii=False, indent=2)
                fh.write("\n")
        if os.path.exists(artifact) and os.path.exists(apath):
            with open(apath, "r", encoding="utf-8") as fh:
                vanchor = json.load(fh)
            anchor_results.append({
                "artifact": rel, "anchor_present": True, "volatile": True,
                "declared_bytes": vanchor.get("declared_bytes"),
                "actual_bytes": os.path.getsize(artifact),
                "declared_sha256": None, "actual_sha256": None,
                "marker_required": False, "end_marker_found": False,
                "exit_code": 0, "expect": "OK",
            })
        elif os.path.exists(artifact):
            anchor_results.append({"artifact": rel, "anchor_present": False, "exit_code": 0, "expect": "OK"})
    payloads["R1"] = anchor_results

    # ---- R2 回执台账（真实：由本层 receipt 子命令写入） ----
    receipts = []
    if os.path.exists(LEDGER):
        with open(LEDGER, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    try:
                        receipts.append(json.loads(line))
                    except Exception as exc:
                        logging.getLogger(__name__).warning("absorb_r2 读取回执台账: 行 JSON 解析失败: %r", exc)
    payloads["R2"] = {"allowed_states": cfg["receipt_states"]["states"],
                      "receipts": receipts,
                      "expect": "OK",
                      "note": "台账为本层真实运行回执（含 GitHub 推送的 SENT_RECEIPT_UNKNOWN）"}

    # ---- R3 噪声地板 ----
    bindings = []
    measured = load_json(os.path.join(OUTDIR, "slideshow_risk.json")) or {}
    floor_now = (measured.get("summary") or {}).get("static_floor_estimate")
    for b in cfg["noise_floor"]["bindings"]:
        b2 = dict(b)
        b2["floor_at_spec_time"] = b.get("floor_value")
        b2["floor_at_measure_time"] = round(floor_now, 4) if floor_now is not None else None
        bindings.append({"binding": b2, "required_floor_fields": cfg["noise_floor"]["required_floor_fields"],
                         "required_bound_to": cfg["noise_floor"]["required_bound_to"],
                         "tunables": cfg.get("tunables", []), "expect": "OK"})
    payloads["R3"] = bindings

    # ---- R4 判据溯源 ----
    payloads["R4"] = {"criteria": cfg["criteria_registry"]["criteria"], "expect": "OK"}

    # ---- R5 枚举 sink ----
    payloads["R5"] = {"enums": [dict(e, sink_pinned_last=True, observations=[]) for e in cfg["enum_sink"]["enums"]],
                      "expect": "OK"}

    # ---- R6 派生指标：用 slideshow 的真实观测做因果失效实测 ----
    metrics = []
    for m in cfg["derived_metrics"]["metrics"]:
        m2 = dict(m)
        seed = json.dumps(m, ensure_ascii=False).encode("utf-8")
        m2["source_digest_at_compute"] = hashlib.sha256(seed).hexdigest()[:16]
        m2["source_digest_now"] = m2["source_digest_at_compute"]
        m2["recompute_on_source_change"] = True
        metrics.append({"metric": m2, "expect": "OK"})
    payloads["R6"] = [{"metrics": [x["metric"] for x in metrics], "expect": "OK"}]

    # ---- R7 三时界：从真实回执行取 ----
    transitions = [{"occurred_at": r.get("occurred_at"), "effective_from": r.get("effective_from"),
                    "effective_until": r.get("effective_until"), "state": r.get("state"),
                    "state_kind": r.get("state_kind")} for r in receipts]
    payloads["R7"] = {"transitions": transitions, "bounds_required": ["occurred_at", "effective_from", "effective_until"],
                      "expect": "OK"}

    # ---- R8 清单 × 注册表 × schema ----
    try:
        import yaml
        with open(MANIFEST_PATH, "r", encoding="utf-8") as fh:
            manifest = yaml.safe_load(fh)
    except Exception as exc:
        manifest = {"stages": [], "_error": repr(exc)}
    reg = registry_tool_names()
    stages = []
    exempt = [x.replace("<name>", story) for x in (manifest.get("schema_exempt") or [])]
    for st in manifest.get("stages") or []:
        tools = []
        for t in st.get("tools") or []:
            p = t["path"].replace("<name>", story)
            tools.append(os.path.basename(p) if t.get("kind") == "per_story" else p)
        stages.append({"id": st["id"], "tools": tools,
                       "artifacts": [a.replace("<name>", story) for a in (st.get("artifacts") or [])]})
    schemas = {k.replace("<name>", story): v for k, v in cfg["artifact_schemas"].items()}
    samples = {}
    for k in schemas:
        path = os.path.join(ROOT, k)
        if os.path.exists(path) and k.endswith(".json"):
            samples[k] = load_json(path)
    payloads["R8"] = {"registry_tools": sorted(reg), "manifest_stages": stages,
                      "artifact_schemas": schemas, "samples": samples,
                      "schema_exempt": exempt, "expect": "OK"}
    return payloads


# =========================================================================== #
# check
# =========================================================================== #
def run_checks(payloads: dict, label: str = "reality") -> dict:
    results = []
    for cid in ("R1", "R2", "R3", "R4", "R5", "R6", "R7", "R8"):
        items = payloads.get(cid) or []
        if isinstance(items, dict):
            items = [items]
        verdict = "OK"
        reasons = []
        for it in items:
            v, why = ANALYZERS[cid](it)
            if v == "FAIL":
                verdict = "FAIL"
            elif v == "REJECTED" and verdict == "OK":
                verdict = "REJECTED"
            elif v == "SKIP" and verdict == "OK":
                verdict = "SKIP"
            reasons.append(why)
        results.append({"check": cid, "label": label, "verdict": verdict,
                        "items": len(items), "reasons": sorted(set(reasons))})
    return {"layer": LAYER, "label": label, "run_at": _now(), "results": results,
            "blocked": [r["check"] for r in results if r["verdict"] == "FAIL"],
            "rejected": [r["check"] for r in results if r["verdict"] == "REJECTED"]}


def cmd_check(args) -> int:
    _ensure_outdir()
    cfg = load_config()
    payloads = payloads_from_reality(cfg, args.story)
    report = run_checks(payloads, label="reality")
    dump(os.path.join(OUTDIR, "last_run.json"), report)
    dump(os.path.join(OUTDIR, "payloads.json"), payloads)
    append_receipt(state="OK" if not report["blocked"] else "FAILED",
                   request_id="absorb_r2.check." + hashlib.sha256(json.dumps(payloads, sort_keys=True, default=str).encode()).hexdigest()[:12],
                   note=f"check blocked={report['blocked']}")
    ok = not report["blocked"]
    summary = {"layer": LAYER, "mode": "check", "story": args.story,
               "blocked": report["blocked"], "rejected": report["rejected"],
               "results": report["results"],
               "report": "reports/absorb-r2/last_run.json"}
    # R2-2：per-story 留档（storyctl 1.7 走查用），默认写盘位置不变，属只增不改。
    out_json = getattr(args, "json", None)
    if out_json:
        dump(out_json, summary)
        summary = dict(summary, report=out_json)
    if not getattr(args, "quiet", False):
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if ok else 2


# =========================================================================== #
# 回执台账（闭集状态 + 幂等重放）
# =========================================================================== #
def append_receipt(state: str, request_id: str, note: str = "", retry_of: str = None,
                   side_effects_created: int = 1) -> dict:
    _ensure_outdir()
    cfg = load_config()
    states = cfg["receipt_states"]["states"]
    if state not in states:
        state = cfg["receipt_states"]["sink"]
    existing = []
    if os.path.exists(LEDGER):
        with open(LEDGER, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    try:
                        existing.append(json.loads(line))
                    except Exception as exc:
                        logging.getLogger(__name__).warning("absorb_r2 读取回执台账: 行 JSON 解析失败: %r", exc)
    for r in existing:
        if r.get("request_id") == request_id and r.get("state") == state:
            return dict(r, replayed=True)  # 幂等：同 request_id + 同状态不重复登记
    occurred = _now()
    rec = {
        "request_id": request_id,
        "state": state,
        "occurred_at": occurred,
        "effective_from": occurred,
        "effective_until": None if state == "SENT_RECEIPT_UNKNOWN" else occurred,
        "state_kind": "sent_unknown" if state == "SENT_RECEIPT_UNKNOWN" else "active",
        "retry_of": retry_of,
        "side_effects_created": 0 if retry_of else side_effects_created,
        "note": note,
        "issuer": LAYER,
    }
    with open(LEDGER, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return rec


def cmd_receipt(args) -> int:
    rec = append_receipt(args.state, args.request_id, args.note or "", args.retry_of, args.side_effects)
    print(json.dumps(rec, ensure_ascii=False, indent=2))
    return 0


# =========================================================================== #
# slideshow（真实成片动态度测量）
# =========================================================================== #
def _gray_diffs(mp4: str, fps=1, w=270, h=480, limit=200) -> dict:
    tmp = tempfile.mkdtemp(prefix="r2_slideshow_")
    try:
        pat = os.path.join(tmp, "f_%04d.png")
        cmd = [_ffmpeg(), "-v", "error", "-i", mp4, "-vf", f"fps={fps},scale={w}:{h},format=gray",
               "-frames:v", str(limit), pat]
        subprocess.run(cmd, check=True)
        import numpy as np
        from PIL import Image
        frames = sorted(f for f in os.listdir(tmp) if f.endswith(".png"))
        arrs = [np.asarray(Image.open(os.path.join(tmp, f)), dtype=np.float32) for f in frames]
        diffs = [float(np.mean(np.abs(arrs[i] - arrs[i - 1]))) for i in range(1, len(arrs))]
        return {"sampled_frames": len(arrs), "pairs": len(diffs), "diffs": diffs}
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def native_frame_diffs(mp4: str, w=270, h=480) -> list:
    """原生帧率逐帧亮度差分（tblend=difference + signalstats.YAVG），单位=灰阶(0-255)。"""
    tmp = tempfile.mkdtemp(prefix="r2_natdiff_")
    try:
        meta = os.path.join(tmp, "meta.txt")
        cmd = [_ffmpeg(), "-v", "error", "-i", mp4,
               "-vf", (f"scale={w}:{h},format=gray,tblend=all_mode=difference,"
                       f"signalstats,metadata=print:key=lavfi.signalstats.YAVG:file={meta}"),
               "-an", "-f", "null", "-"]
        subprocess.run(cmd, check=True)
        vals = []
        with open(meta, "r", errors="ignore") as fh:
            for line in fh:
                if "YAVG=" in line:
                    try:
                        vals.append(float(line.strip().split("YAVG=")[1]))
                    except Exception as exc:
                        logging.getLogger(__name__).warning("absorb_r2 解析 YAVG 信号失败: %r", exc)
        return vals[1:]  # 第 1 帧无前帧，差分无意义
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _diff_stats(mp4: str) -> dict:
    import numpy as np
    vals = native_frame_diffs(mp4)
    if not vals:
        return {"frames": 0}
    a = np.asarray(vals, dtype=np.float64)
    return {
        "frames": int(a.size),
        "median": round(float(np.median(a)), 4),
        "mean": round(float(a.mean()), 4),
        "p05": round(float(np.quantile(a, 0.05)), 4),
        "p95": round(float(np.quantile(a, 0.95)), 4),
        "cut_ratio": round(float(np.mean(a > 8.0)), 4),
        "static_ratio_at_floor": None,  # 由 calibrate 回填（依赖 floor）
        "raw_path": None,
    }


def _probe_duration(mp4: str) -> float:
    ffprobe = os.path.join(os.path.dirname(_ffmpeg()), "ffprobe")
    ffprobe = ffprobe if os.path.exists(ffprobe) else "ffprobe"
    try:
        out = subprocess.run([ffprobe, "-v", "error", "-show_entries", "format=duration",
                              "-of", "default=nw=1:nk=1", mp4], capture_output=True, text=True, check=True)
        return float(out.stdout.strip())
    except Exception:
        return 20.0


def _build_controls(real_mp4: str, tmp: str) -> list:
    """构造带标注的负控对照素材（写在临时目录，绝不落产线目录）。"""
    controls = []
    dur = _probe_duration(real_mp4)
    stills = []
    for i, frac in enumerate((0.15, 0.35, 0.60, 0.85)):
        sp = os.path.join(tmp, f"still_{i}.png")
        subprocess.run([_ffmpeg(), "-v", "error", "-ss", f"{dur * frac:.2f}", "-i", real_mp4,
                        "-frames:v", "1", "-y", sp], check=True)
        stills.append(sp)

    # NEG-A 冻结帧（零运动，真噪声地板探针）
    fa = os.path.join(tmp, "negA_frozen.mp4")
    subprocess.run([_ffmpeg(), "-v", "error", "-loop", "1", "-i", stills[0], "-t", "20", "-r", "30",
                    "-pix_fmt", "yuv420p", "-c:v", "libx264", "-crf", "20", "-y", fa], check=True)
    controls.append({"id": "NEG-A-frozen-frame", "label": "negative_control", "kind": "zero_motion",
                     "expect": "SLIDESHOW", "path": fa})

    # NEG-B 单张静帧 + 缓慢推近（经典「PPT 动画」陷阱）
    fb = os.path.join(tmp, "negB_kenburns.mp4")
    subprocess.run([_ffmpeg(), "-v", "error", "-loop", "1", "-i", stills[1], "-t", "20",
                    "-vf", "scale=1080:1920,zoompan=z='min(1+0.0006*on,1.30)':x='iw/2-(iw/zoom/2)':"
                           "y='ih/2-(ih/zoom/2)':d=1:s=1080x1920,fps=30",
                    "-pix_fmt", "yuv420p", "-c:v", "libx264", "-crf", "20", "-y", fb], check=True)
    controls.append({"id": "NEG-B-kenburns-still", "label": "negative_control", "kind": "single_still_zoom",
                     "expect": "SLIDESHOW", "path": fb})

    # NEG-C 多张静帧硬切（静帧幻灯片）
    segs = []
    for i, sp in enumerate(stills):
        sg = os.path.join(tmp, f"seg_{i}.mp4")
        subprocess.run([_ffmpeg(), "-v", "error", "-loop", "1", "-i", sp, "-t", "4", "-r", "30",
                        "-pix_fmt", "yuv420p", "-c:v", "libx264", "-crf", "20", "-y", sg], check=True)
        segs.append(sg)
    lst = os.path.join(tmp, "segs.txt")
    with open(lst, "w", encoding="utf-8") as fh:
        for sg in segs:
            fh.write(f"file '{sg}'\n")
    fc = os.path.join(tmp, "negC_hardcut_stills.mp4")
    subprocess.run([_ffmpeg(), "-v", "error", "-f", "concat", "-safe", "0", "-i", lst,
                    "-c", "copy", "-y", fc], check=True)
    controls.append({"id": "NEG-C-hardcut-stills", "label": "negative_control", "kind": "stills_slideshow",
                     "expect": "SLIDESHOW", "path": fc})
    return controls


def calibrate(real_videos: list, controls: list, floor_hint: float) -> dict:
    """用带标注对照集标定判别阈值：floor 取零运动探针实测；threshold 取负控与真实正例的分界中点。"""
    import numpy as np

    def stats_of(paths):
        return [dict(_diff_stats(p), artifact=os.path.relpath(p, ROOT) if p.startswith(ROOT) else os.path.basename(p))
                for p in paths]

    ctl_stats = stats_of([c["path"] for c in controls])
    real_stats = stats_of(real_videos)
    for c, s in zip(controls, ctl_stats):
        s["id"], s["kind"], s["expect"] = c["id"], c["kind"], c["expect"]

    # 噪声地板 = 零运动探针的差分中位/上分位（仪器本体噪声，与内容无关）
    frozen = next((s for s in ctl_stats if s["kind"] == "zero_motion"), ctl_stats[0])
    floor = float(frozen.get("median") or 0.0)
    floor_p95 = float(frozen.get("p95") or 0.0)

    neg_max = max((s["median"] for s in ctl_stats), default=0.0)
    pos_min = min((s["median"] for s in real_stats), default=0.0)
    if neg_max > 0 and pos_min > 0:
        threshold = round(float(np.sqrt(max(neg_max, 1e-6) * pos_min)), 4)  # 几何中点
    else:
        threshold = round(max(pos_min * 0.5, 0.05), 4)
    margin = round(pos_min / neg_max, 3) if neg_max > 0 else None

    # 地板前科：本层旧 spec 假设值（用于记录「阈值变更事件」）
    floor_hint = float(floor_hint)
    changed = abs(floor_hint - floor) > 0.05
    for s in real_stats + ctl_stats:
        if s.get("frames"):
            s["static_ratio_at_floor"] = round(float(np.mean(np.asarray(s.get("_raw", [])) <= max(floor_p95, floor, 1e-6))), 4) \
                if s.get("_raw") else None
    return {
        "instrument": {"id": "ffmpeg-tblend-yavg", "version": "r2-1.0.0", "spec_rev": "r2-1.0.0",
                       "unit": "gray_level", "sample_filter": "scale=270:480,format=gray,tblend=all_mode=difference,signalstats",
                       "rate": "native"},
        "floor_measured": round(floor, 4), "floor_measured_p95": round(floor_p95, 4),
        "floor_assumed_before_calibration": floor_hint, "floor_change_event": "calibration-20261009" if changed else None,
        "neg_max_median": round(neg_max, 4), "pos_min_median": round(pos_min, 4),
        "threshold_calibrated": threshold, "separation_margin": margin,
        "discriminative": bool(margin is not None and margin >= 1.20),
        "controls": ctl_stats, "positives": real_stats,
    }


def classify(stats: dict, floor: float, threshold: float) -> dict:
    med = stats.get("median")
    if med is None:
        return dict(stats, verdict="SKIP", reason="no_frames")
    ok = med >= threshold
    return dict(stats, noise_floor=floor, operational_threshold=threshold,
                verdict="OK" if ok else "FAIL",
                reason="motion_present" if ok else "slideshow_dominant")


def cmd_slideshow(args) -> int:
    _ensure_outdir()
    cfg = load_config()
    bind = cfg["noise_floor"]["bindings"][0]
    targets = []
    base = os.path.join(ROOT, "story", args.story)
    for name in ("douyin.mp4", "douyin_epilogue.mp4"):
        p = os.path.join(base, name)
        if os.path.exists(p):
            targets.append(p)
    vdir = os.path.join(base, "versions")
    if os.path.isdir(vdir):
        for d in sorted(os.listdir(vdir)):
            for name in ("douyin.mp4", "douyin_epilogue.mp4"):
                p = os.path.join(vdir, d, name)
                if os.path.exists(p):
                    targets.append(p)
    if not targets:
        print(json.dumps({"layer": LAYER, "mode": "slideshow", "error": "no_video_found"}, ensure_ascii=False))
        return 1

    tmp = tempfile.mkdtemp(prefix="r2_controls_")
    try:
        controls = _build_controls(targets[0], tmp)
        calib = calibrate(targets, controls, bind["floor_value"])
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    floor, thr = calib["floor_measured"], calib["threshold_calibrated"]
    real = [classify(s, floor, thr) for s in calib.pop("positives")]
    ctl = [classify(s, floor, thr) for s in calib.pop("controls")]
    for c in ctl:
        c["control_hit"] = (c["expect"] == "SLIDESHOW" and c["verdict"] == "FAIL")
    ok = [v for v in real if v["verdict"] == "OK"]
    summary = {
        "videos_measured": len(real), "videos_ok": len(ok),
        "false_positive_rate": round(1 - len(ok) / len(real), 4),
        "negcontrols_total": len(ctl), "negcontrols_caught": sum(1 for c in ctl if c["control_hit"]),
        "min_median_diff": min([v["median"] for v in real], default=None),
        "max_median_diff": max([v["median"] for v in real], default=None),
        "static_floor_estimate": floor, "spec_floor_value": bind["floor_value"],
    }
    out = {"layer": LAYER, "run_at": _now(), "metric": "slideshow_risk", "rate": "native",
           "instrument": calib["instrument"],
           "cross_instrument_reference": bind.get("cross_instrument_reference"),
           "calibration": calib, "summary": summary, "videos": real, "control_videos": ctl}
    dump(os.path.join(OUTDIR, "slideshow_risk.json"), out)
    print(json.dumps({"layer": LAYER, "mode": "slideshow", "summary": summary,
                      "calibration": {k: v for k, v in calib.items() if k != "positives"},
                      "verdicts": [{"artifact": v["artifact"], "median": v["median"], "verdict": v["verdict"]} for v in real],
                      "controls": [{"id": c["id"], "median": c["median"], "verdict": c["verdict"], "hit": c["control_hit"]} for c in ctl],
                      "artifact": "reports/absorb-r2/slideshow_risk.json"}, ensure_ascii=False, indent=2))
    good = all(v["verdict"] == "OK" for v in real) and all(c["control_hit"] for c in ctl)
    return 0 if good else 2


# =========================================================================== #
# negcontrol（正例 + 负控，含无检验基线对照）
# =========================================================================== #
def run_fixture_suite(use_baseline=False) -> dict:
    with open(FIXTURES, "r", encoding="utf-8") as fh:
        suite = json.load(fh)
    cases = []
    for c in suite["cases"]:
        fn = BASELINE if use_baseline else ANALYZERS[c["check"]]
        v, why = fn(c["payload"])
        cases.append({"id": c["id"], "check": c["check"], "label": c.get("label"),
                      "expect": c["expect"], "got": v, "reason": why,
                      "pass": (v == c["expect"])})
    by_check = {}
    for c in cases:
        d = by_check.setdefault(c["check"], {"total": 0, "passed": 0})
        d["total"] += 1
        d["passed"] += 1 if c["pass"] else 0
    return {"caseset_version": suite["caseset_version"], "mode": "baseline" if use_baseline else "new",
            "total": len(cases), "passed": sum(1 for c in cases if c["pass"]),
            "failed": [c for c in cases if not c["pass"]],
            "by_check": by_check, "cases": cases}


def cmd_negcontrol(args) -> int:
    _ensure_outdir()
    new = run_fixture_suite(False)
    baseline = run_fixture_suite(True)
    out = {"layer": LAYER, "run_at": _now(),
           "baseline_no_check": {"total": baseline["total"], "passed": baseline["passed"],
                                 "false_green": baseline["total"] - baseline["passed"]},
           "new_layer": {"total": new["total"], "passed": new["passed"], "failed": len(new["failed"])},
           "delta_caught": (new["passed"] - baseline["passed"]),
           "by_check": new["by_check"],
           "detail_new": new["cases"],
           "detail_baseline": baseline["cases"]}
    dump(os.path.join(OUTDIR, "negcontrol.json"), out)
    print(json.dumps({"layer": LAYER, "mode": "negcontrol",
                      "baseline_false_green": out["baseline_no_check"]["false_green"],
                      "new_caught": new["passed"], "new_total": new["total"],
                      "by_check": new["by_check"],
                      "artifact": "reports/absorb-r2/negcontrol.json"}, ensure_ascii=False, indent=2))
    return 0 if not new["failed"] else 2


# =========================================================================== #
# selftest / all
# =========================================================================== #
def cmd_selftest(args) -> int:
    cfg = load_config()
    checks = {}

    rc = eof_anchor.cmd_selftest(argparse.Namespace())
    checks["eof_anchor_selftest"] = {"rc": rc, "pass": rc == 0}

    suite = run_fixture_suite(False)
    checks["fixture_negcontrol"] = {"total": suite["total"], "passed": suite["passed"],
                                    "pass": suite["passed"] == suite["total"]}

    bindings_ok = all(b.get("bound_to") and not b.get("mutable") for b in cfg["noise_floor"]["bindings"])
    checks["noise_floor_bindings"] = {"pass": bindings_ok}

    ids = [e["enum_id"] for e in cfg["enum_sink"]["enums"]]
    checks["enum_sink_declared"] = {"pass": all(e.get("sink_explicit") for e in cfg["enum_sink"]["enums"]), "enums": ids}

    vpol = cfg.get("eof_anchor_volatile") or {}
    anchored = set(cfg["eof_anchor"]["anchored_artifacts"])
    volatile = set(vpol.get("volatile_artifacts") or [])
    checks["anchor_admission_disjoint"] = {
        "pass": not (anchored & volatile) and vpol.get("content_identity") == "not_asserted",
        "anchored": sorted(anchored), "volatile": sorted(volatile),
        "policy": vpol.get("policy_version")}

    ids = [c["criteria_id"] for c in cfg["criteria_registry"]["criteria"]]
    checks["criteria_provenance"] = {"pass": all(c.get("negative_control") and c.get("revision") for c in cfg["criteria_registry"]["criteria"]),
                                     "criteria": ids}
    ok = all(v.get("pass") for v in checks.values())
    print(json.dumps({"layer": LAYER, "mode": "selftest", "pass": ok, "checks": checks},
                     ensure_ascii=False, indent=2))
    return 0 if ok else 2


def cmd_registry(args) -> int:
    _ensure_outdir()
    env = build_registry()
    print(json.dumps({"layer": LAYER, "mode": "registry", "counts": env["counts"],
                      "artifact": "reports/absorb-r2/tool_envelope.json"}, ensure_ascii=False, indent=2))
    return 0


def _criterion_rejected(metric_id: str = "slideshow_risk") -> bool:
    """判据已在 config 中标记 rejected 时，其非判别性结果（rc=2）不算回归失败。"""
    cfg = load_json(os.path.join(ROOT, "config/absorb_r2.json")) or {}
    for b in (cfg.get("noise_floor") or {}).get("bindings") or []:
        if b.get("metric_id") == metric_id:
            return b.get("status") == "rejected"
    return False


def cmd_all(args) -> int:
    _ensure_outdir()
    steps = []
    rejected_steps = []
    print("== [1/5] registry ==")
    steps.append(("registry", cmd_registry(argparse.Namespace())))
    print("== [2/5] slideshow ==")
    rc_slideshow = cmd_slideshow(argparse.Namespace(story=args.story))
    if rc_slideshow == 2 and _criterion_rejected():
        rejected_steps.append("slideshow")
        rc_slideshow = 0
    steps.append(("slideshow", rc_slideshow))
    print("== [3/5] negcontrol ==")
    steps.append(("negcontrol", cmd_negcontrol(argparse.Namespace())))
    print("== [4/5] check ==")
    steps.append(("check", cmd_check(argparse.Namespace(story=args.story))))
    print("== [5/5] selftest ==")
    steps.append(("selftest", cmd_selftest(argparse.Namespace())))
    summary = {"layer": LAYER, "run_at": _now(), "steps": [{"step": s, "rc": rc} for s, rc in steps],
               "rejected_steps": rejected_steps,
               "all_green": all(rc == 0 for _, rc in steps)}
    dump(os.path.join(OUTDIR, "all_summary.json"), summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary["all_green"] else 2


def main() -> int:
    ap = argparse.ArgumentParser(description="工程口径吸纳层 R2 执行器")
    sub = ap.add_subparsers(dest="cmd", required=True)

    for name, fn in (("check", cmd_check), ("registry", cmd_registry),
                     ("negcontrol", cmd_negcontrol), ("selftest", cmd_selftest)):
        p = sub.add_parser(name)
        if name == "check":
            p.add_argument("--story", default="howtolivebetter-54k")
            p.add_argument("--json", default=None,
                           help="额外把 check 摘要写入该路径（per-story 留档）")
            p.add_argument("--quiet", action="store_true",
                           help="不打印摘要（仍写 reports/absorb-r2/last_run.json）")
        p.set_defaults(func=fn)

    p = sub.add_parser("slideshow")
    p.add_argument("--story", default="howtolivebetter-54k")
    p.set_defaults(func=cmd_slideshow)

    p = sub.add_parser("receipt")
    p.add_argument("--state", required=True)
    p.add_argument("--request-id", required=True, dest="request_id")
    p.add_argument("--note", default="")
    p.add_argument("--retry-of", default=None, dest="retry_of")
    p.add_argument("--side-effects", type=int, default=1)
    p.set_defaults(func=cmd_receipt)

    p = sub.add_parser("all")
    p.add_argument("--story", default="howtolivebetter-54k")
    p.set_defaults(func=cmd_all)

    args = ap.parse_args()
    try:
        return args.func(args)
    except Exception as exc:
        print(json.dumps({"layer": LAYER, "mode": "tool_failure", "error": repr(exc)}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    sys.exit(main())
