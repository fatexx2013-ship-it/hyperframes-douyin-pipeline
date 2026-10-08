#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
extended_selftest.py —— 扩展判定层回归单测（AI-Film-Studio 第二条私信口径）

所属产线：hyperframes 竖屏短视频产线（部署根由 PIPELINE_HOME / 仓库位置决定）
资料来源：AI-Film-Studio 第二条私信 2026-09-26

覆盖范围（分支级，正/负控成对）
----------------------------
A. 8 字段漂移判定的每个分支（含硬停通道与放行通道）
B. normalize_point 六步枚举：顺序固定、顺序进签名域、显式不做 UNICODE_NORMALIZATION
C. 「次级」判定三条件：三条全满足才降级，缺一按主判据
D. 两组正交对：judge_source×frozen_state（人工判据不占自动通过率分母）、
   issuer×actionability（执行侧 false → 跳过计数；判定侧 false → 不适配计数）
E. 端到端：对真实产线产物（check/diff JSON 报告）做断言

用法：python3 scripts/extended_selftest.py
退出码：0 = 全部通过；2 = 存在未通过项
"""

from __future__ import annotations

import json
import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(SCRIPT_DIR)
sys.path.insert(0, SCRIPT_DIR)

import param_contract as pc          # noqa: E402
import normalize_point as npt        # noqa: E402
import judgement_rules as jr         # noqa: E402

CONTRACT = pc.read_json(pc.CONTRACT_DEFAULT) or {}
EXT_FIELDS = {f["field"]: f for f in (CONTRACT.get("extended_contract") or {}).get("fields", [])}
CORE_N = len(CONTRACT.get("fields", []))
FROZEN = pc.load_frozen_baseline()
RESULT = []


def check(group, title, passed, detail=""):
    RESULT.append((group, title, bool(passed), detail))
    print(f"  [{'PASS' if passed else 'FAIL'}] {title}" + (f"\n          {detail}" if detail else ""))


def judge(field, b, c, ctx):
    return pc._EXT_JUDGES[field](EXT_FIELDS[field], b, c, ctx)


def ctx_of(change_events=None, recomputed=None, **over):
    ctx = {
        "tolerance_policy": CONTRACT.get("tolerance_policy") or {},
        "expected_n_policy": CONTRACT.get("expected_n_policy") or {},
        "canonicalizer": pc.load_canonicalizer(),
        "frozen_baseline": FROZEN,
        "contract_canonicalizer_signature": (CONTRACT.get("canonicalization_ref") or {}).get("signature"),
        "actual_entry_count": CORE_N + len(EXT_FIELDS),
        "change_events": change_events or [],
        "recomputed_digest": recomputed if recomputed is not None else FROZEN.get("digest"),
    }
    ctx.update(over)
    return ctx


def expect(group, field, b, c, ctx, want, note=""):
    got, reason = judge(field, b, c, ctx)
    check(group, f"{field}｜{note}", got == want, f"期望 {want} 实得 {got} ｜ {reason}")
    return got, reason


# ─────────────────────────────────────────────────────────────
# A. 8 字段分支
# ─────────────────────────────────────────────────────────────

def test_fields():
    G = "A.8字段判定分支"
    print("=" * 96)
    print(G)
    print("=" * 96)
    ev = ctx_of([{"field": "render_window_frames", "reason": "重排版导致时长变化", "issued_by": "human"}])

    expect(G, "render_window_frames", None, {"value": 2507, "fps": 30.0}, ctx_of(), "SKIP", "无基线→首见登记")
    expect(G, "render_window_frames", {"value": 2507}, {"value": 2507}, ctx_of(), "OK", "与基线一致")
    expect(G, "render_window_frames", {"value": 2496}, {"value": 2507}, ctx_of(), "FAIL", "不同且无变更事件→硬停")
    expect(G, "render_window_frames", {"value": 2496}, {"value": 2507}, ev, "OK", "变更事件覆盖→放行")
    expect(G, "render_window_frames", {"value": 2496}, {"value": 2507}, ctx_of([{"all": True}]), "OK", "全局变更事件→放行")
    expect(G, "render_window_frames", None, {"value": None}, ctx_of(), "SKIP", "无时长/帧率证据")

    expect(G, "resolution_short_edge", None, {"value": 1080}, ctx_of(), "OK", "在允许集内")
    expect(G, "resolution_short_edge", None, {"value": 720}, ctx_of(), "WARN", "不在允许集→降级+人工")
    expect(G, "resolution_short_edge", {"value": 1080}, {"value": 960}, ctx_of(), "WARN", "相对基线偏移超容差带")

    expect(G, "peak_vram", None, {"value_gib": None}, ctx_of(), "SKIP", "未采集（≠无占用）")
    expect(G, "peak_vram", None, {"value_gib": 1.784, "source": "reports/peaks/render_paperclip.json"}, ctx_of(), "OK", "首见登记")
    expect(G, "peak_vram", {"value_gib": 1.784}, {"value_gib": 1.9, "source": "x"}, ctx_of(), "OK", "同容差带")
    expect(G, "peak_vram", {"value_gib": 1.0}, {"value_gib": 1.9, "source": "x"}, ctx_of(), "WARN", "超容差带→仅记录")

    expect(G, "seed", None, {"value": None, "explicit": False}, ctx_of(), "SKIP", "未显式声明→不可复算")
    expect(G, "seed", None, {"value": 42, "explicit": True}, ctx_of(), "SKIP", "首见登记")
    expect(G, "seed", {"value": 42, "explicit": True}, {"value": 42, "explicit": True}, ctx_of(), "OK", "与基线一致")
    expect(G, "seed", {"value": 42, "explicit": True}, {"value": 7, "explicit": True}, ctx_of(), "FAIL", "seed 不同→不可复算硬停")

    expect(G, "tolerance_value", None, {}, ctx_of(tolerance_policy={"unit": None, "tolerance_value": 0.1}), "FAIL", "单位缺失→不可比硬停")
    expect(G, "tolerance_value", None, {}, ctx_of(tolerance_policy={"unit": "秒", "tolerance_value": None}), "SKIP", "未声明容差")
    expect(G, "tolerance_value", {"value": 0.1}, {}, ctx_of(tolerance_policy={"unit": "秒", "tolerance_value": 0.1}), "OK", "容差稳定")
    expect(G, "tolerance_value", {"value": 0.05}, {}, ctx_of(tolerance_policy={"unit": "秒", "tolerance_value": 0.1}), "WARN", "容差取值变化→登记")

    sig = (CONTRACT.get("canonicalization_ref") or {}).get("signature")
    expect(G, "canonicalizer_version", None, {"value": sig}, ctx_of(), "OK", "首见登记")
    expect(G, "canonicalizer_version", None, {"value": sig}, ctx_of(canonicalizer={"signature": "deadbeefdeadbeef"}), "FAIL", "配置≠合同→换实现硬停")
    expect(G, "canonicalizer_version", None, {"value": None}, ctx_of(), "FAIL", "空→未版本化硬停")
    expect(G, "canonicalizer_version", None, {"value": "0000000000000000"}, ctx_of(), "FAIL", "快照签名≠合同硬停")
    expect(G, "canonicalizer_version", {"value": "0000000000000000"}, {"value": sig}, ctx_of(), "FAIL", "基线签名≠合同硬停")

    expect(G, "expected_n", None, {}, ctx_of(expected_n_policy={"declared": None}), "SKIP", "未显式签发→不可判")
    expect(G, "expected_n", None, {}, ctx_of(), "OK", f"声明={CORE_N + len(EXT_FIELDS)} 与实际一致")
    expect(G, "expected_n", None, {}, ctx_of(actual_entry_count=17), "FAIL", "字段静默丢失→硬停")

    expect(G, "frozen_baseline_digest", None, {}, ctx_of(frozen_baseline={"digest": None}), "SKIP", "未冻结")
    expect(G, "frozen_baseline_digest", None, {"value": FROZEN.get("digest")}, ctx_of(), "OK", "重判一致")
    expect(G, "frozen_baseline_digest", None, {}, ctx_of(recomputed="sha256:deadbeef"), "FAIL", "重判不一致→基线被改写")
    expect(G, "frozen_baseline_digest", None, {"value": "sha256:beefdead"}, ctx_of(), "FAIL", "快照摘要≠冻结摘要")
    expect(G, "frozen_baseline_digest", {"value": "sha256:beefdead"}, {"value": FROZEN.get("digest")}, ctx_of(), "FAIL", "基线条目摘要≠冻结摘要")
    no_recompute = ctx_of()
    no_recompute["recomputed_digest"] = None
    expect(G, "frozen_baseline_digest", None, {}, no_recompute, "SKIP", "缺 ref_manifest 无法重判")


# ─────────────────────────────────────────────────────────────
# B. 规范化器
# ─────────────────────────────────────────────────────────────

def test_canonicalizer():
    G = "B.规范化器"
    print("=" * 96)
    print(G)
    print("=" * 96)
    check(G, "六步枚举顺序与私信一致",
          npt.NORMALIZE_ORDER == ["STRIP_BOM", "UNIFY_LINE_ENDING", "STRIP_TRAILING_WHITESPACE",
                                  "STRIP_LEADING_WHITESPACE", "COLLAPSE_INTERNAL_WHITESPACE",
                                  "STRIP_INLINE_COMMENT"],
          f"{npt.NORMALIZE_ORDER}")
    check(G, "显式不做 UNICODE_NORMALIZATION", npt.EXCLUDED_POINTS == ["UNICODE_NORMALIZATION"])
    cfg = npt.load_config()
    sig = npt.normalize_signature()
    check(G, "配置声明的签名 = 实现签名", cfg.get("signature") == sig, f"配置 {cfg.get('signature')} / 实现 {sig}")
    swapped = list(npt.NORMALIZE_ORDER)
    swapped[1], swapped[2] = swapped[2], swapped[1]
    probe = "a \r\n"
    check(G, "顺序进签名域：调换顺序后签名与输出均变化",
          npt.normalize_signature(swapped) != sig and npt.normalize_text(probe, swapped) != npt.normalize_text(probe),
          f"{sig} → {npt.normalize_signature(swapped)}；{probe!r} → {npt.normalize_text(probe)!r} vs {npt.normalize_text(probe, swapped)!r}")
    nfc, nfd = "\u00e9", "e\u0301"
    check(G, "不做 Unicode 归一：NFC 与 NFD 规范化后仍不同（无 locale 依赖）",
          npt.normalize_text(nfc) != npt.normalize_text(nfd))
    check(G, "幂等性", npt.normalize_text(npt.normalize_text("x  \r\n")) == npt.normalize_text("x  \r\n"))


# ─────────────────────────────────────────────────────────────
# C/D. 次级三条件 + 两组正交对
# ─────────────────────────────────────────────────────────────

def test_rules():
    G = "C/D.次级三条件与正交对"
    print("=" * 96)
    print(G)
    print("=" * 96)
    base = {"secondary_field": "segment_duration_rounding", "canonical_field": "segment_duration",
            "batch": "b1", "canonical_batch": "b1", "canonical_issuer": "judge-A", "secondary_issuer": "judge-A"}
    check(G, "次级：三条件全满足→降级为次级",
          jr.check_secondary({**base, "derivable": True, "missing_no_effect": True})["verdict"] == "secondary")
    for title, over in [("缺①不可派生→按主判据", {"derivable": False, "missing_no_effect": True}),
                        ("缺②缺失改终态→按主判据", {"derivable": True, "missing_no_effect": False}),
                        ("缺③签发方不同→按主判据", {"derivable": True, "missing_no_effect": True,
                                              "secondary_issuer": "judge-B"}),
                        ("缺③批次不同→按主判据", {"derivable": True, "missing_no_effect": True, "batch": "b2"})]:
        check(G, f"次级：{title}", jr.check_secondary({**base, **over})["verdict"] == "canonical")

    recs = [
        {"id": "A", "role": "main", "source_tag": "primary", "judge_source": "auto",
         "frozen_state": "outside", "issuer": "executor", "actionability": False},
        {"id": "B", "role": "aux", "source_tag": "derived", "judge_source": "auto",
         "frozen_state": "outside", "issuer": "executor", "actionability": False},
        {"id": "C", "role": "main", "source_tag": "primary", "judge_source": "manual",
         "frozen_state": "in_window", "issuer": "judge", "actionability": False},
        {"id": "D", "role": "aux", "source_tag": "primary", "judge_source": "manual",
         "frozen_state": "outside", "issuer": "judge", "actionability": True},
        {"id": "E", "role": "main", "source_tag": "derived", "judge_source": "auto",
         "frozen_state": "in_window", "issuer": "judge", "actionability": False},
    ]
    r = jr.orthogonality(recs)
    check(G, "正交对：执行侧 false（A/B）→ 跳过计数",
          r["skipped_count"] == 2 and r["skipped_ids"] == ["A", "B"])
    check(G, "正交对：判定侧 false（C/E）→ 不适配计数",
          r["not_applicable_count"] == 2 and r["not_applicable_ids"] == ["C", "E"])
    check(G, "正交对：人工判据冻结窗内（C）不进自动通过率分母",
          r["excluded_ids"] == ["C"] and "C" not in r["auto_pass_denominator_ids"])
    check(G, "正交对：D/E 进自动通过率分母", r["auto_pass_denominator_ids"] == ["D", "E"])
    check(G, "正交对：三组正交对字段齐全（缺一即不合法）",
          set(jr.ORTHO_PAIRS) == {("role", "source_tag"), ("judge_source", "frozen_state"),
                                  ("issuer", "actionability")})


# ─────────────────────────────────────────────────────────────
# E. 端到端（真实产线产物）
# ─────────────────────────────────────────────────────────────

def test_end_to_end():
    G = "E.端到端（真实产物）"
    print("=" * 96)
    print(G)
    print("=" * 96)
    chk = pc.read_json(os.path.join(ROOT, "reports/artifacts/check_paperclip_v110.json"))
    dif = pc.read_json(os.path.join(ROOT, "reports/artifacts/diff_compositor_paperclip_v110.json"))
    fb = FROZEN
    if chk:
        rows = {r["field"]: r for r in (chk.get("rows") or []) + (chk.get("extended_rows") or [])}
        check(G, "check：判定条目数 = 合同声明 expected_n",
              chk["expected_n"]["actual"] == chk["expected_n"]["declared"] == len(rows),
              f"{chk['expected_n']} / 实际行 {len(rows)}")
        check(G, "check：frozen_baseline_digest 重判一致",
              rows["frozen_baseline_digest"]["verdict"] == "OK",
              rows["frozen_baseline_digest"]["reason"])
        check(G, "check：canonicalizer_version 与合同签名一致",
              rows["canonicalizer_version"]["verdict"] == "OK" and
              chk["canonicalizer_signature"] == (CONTRACT.get("canonicalization_ref") or {}).get("signature"))
        check(G, "check：overall 无阻断（exit_code=0）",
              chk["overall"] in ("OK", "WARN_ONLY") and chk["exit_code"] == 0, chk["overall"])
    else:
        check(G, "check 报告存在", False, "缺 reports/artifacts/check_paperclip_v110.json")

    if dif:
        rows = {r["field"]: r for r in (dif.get("rows") or []) + (dif.get("extended_rows") or [])}
        check(G, "diff：跨片帧数漂移被硬停命中（2496→2507 无变更事件）",
              rows["render_window_frames"]["verdict"] == "FAIL" and dif["exit_code"] == 2,
              rows["render_window_frames"]["reason"])
        check(G, "diff：扩展层 FAIL 计入 overall 阻断",
              dif["overall"] == "INVARIANT_FAIL" and dif["extended_counts"]["FAIL"] == 1)
        check(G, "diff：resolution_short_edge / peak_vram 无漂移",
              rows["resolution_short_edge"]["verdict"] == "OK" and rows["peak_vram"]["verdict"] == "OK")
        check(G, "diff：正交计数已随报告输出",
              isinstance(dif.get("orthogonality_counts"), dict) and
              dif["orthogonality_counts"]["auto_pass_denominator"] == len(rows),
              json.dumps(dif.get("orthogonality_counts"), ensure_ascii=False))
    else:
        check(G, "diff 报告存在", False, "缺 reports/artifacts/diff_compositor_paperclip_v110.json")

    if fb.get("digest"):
        digest, ok = pc.canonical_digest(pc.read_json(os.path.join(ROOT, fb["ref_manifest"])))
        check(G, "冻结摘要可复算：重算值 = 冻结值", digest == fb["digest"], f"{digest}")
        check(G, "规范化器已接入摘要链路", ok is True)


def main():
    test_fields()
    test_canonicalizer()
    test_rules()
    test_end_to_end()
    total = len(RESULT)
    failed = [r for r in RESULT if not r[2]]
    print("=" * 96)
    print(f"结论：共 {total} 项，PASS {total - len(failed)} / FAIL {len(failed)}")
    if failed:
        for g, t, _p, d in failed:
            print(f"  [FAIL] {g} ｜ {t}")
    print("=" * 96)
    return 0 if not failed else 2


if __name__ == "__main__":
    sys.exit(main())
