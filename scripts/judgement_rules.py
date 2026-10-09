#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
judgement_rules.py —— 判定口径校验器（次级判定三条件 + 三组正交对）

所属产线：/Volumes/PSSD/抖音视频
资料来源：AI-Film-Studio 第二条私信 2026-09-26

覆盖两条口径
------------
1. 「次级」判定三条件（须同时成立，缺一即不降级为次级、按主判据处理）：
   ① 取值可由主判据派生（derivable）
   ② 缺失时不改变终态（missing_no_effect）
   ③ 必须与主判据同批次、同签发方（same_batch && same_issuer）
2. 三组正交对与计数分流：
   - role × source_tag              ：条目角色与来源标签正交
   - judge_source × frozen_state     ：判据来源与冻结状态正交；
                                      人工判据在冻结窗内**不得进自动通过率分母**
   - issuer × actionability          ：签发方与可动作性正交；
                                      执行侧签的 false 只进「跳过计数」，
                                      判定侧签的 false 进「不适配计数」

用法
----
  python3 scripts/judgement_rules.py secondary --file <case.json>
  python3 scripts/judgement_rules.py orthogonality --file <records.json>
  python3 scripts/judgement_rules.py self-test

退出码：0 = 通过；2 = 校验不通过（用例未达期望）；1 = 用法/输入错误
"""

from __future__ import annotations

import argparse
import json
import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DEFAULT = os.path.dirname(SCRIPT_DIR)

SECONDARY_CONDITIONS = [
    ("derivable", "① 取值可由主判据派生"),
    ("missing_no_effect", "② 缺失时不改变终态"),
    ("same_batch_issuer", "③ 与主判据同批次、同签发方"),
]
ORTHO_PAIRS = [
    ("role", "source_tag"),
    ("judge_source", "frozen_state"),
    ("issuer", "actionability"),
]


# ─────────────────────────────────────────────────────────────
# 次级判定三条件
# ─────────────────────────────────────────────────────────────

def check_secondary(case: dict) -> dict:
    """输入一条判定关系，输出该判据能否降级为次级。缺任一条件 → 按主判据。"""
    reasons, failed = [], []
    if not case.get("derivable"):
        failed.append("derivable")
        reasons.append("取值不能由主判据派生 → 缺条件①，按主判据处理")
    if not case.get("missing_no_effect"):
        failed.append("missing_no_effect")
        reasons.append("缺失会改变终态 → 缺条件②，按主判据处理")
    same_batch = case.get("batch") is not None and case.get("batch") == case.get("canonical_batch", case.get("batch"))
    same_issuer = bool(case.get("secondary_issuer")) and case.get("secondary_issuer") == case.get("canonical_issuer")
    if not (same_batch and same_issuer):
        failed.append("same_batch_issuer")
        reasons.append(
            f"批次/签发方不一致（batch={case.get('batch')!r}/{case.get('canonical_batch')!r}，"
            f"issuer={case.get('secondary_issuer')!r}/{case.get('canonical_issuer')!r}）→ 缺条件③，按主判据处理"
        )
    verdict = "secondary" if not failed else "canonical"
    if verdict == "secondary":
        reasons.append("三条件同时成立 → 可降级为次级判据")
    return {
        "secondary_field": case.get("secondary_field"),
        "canonical_field": case.get("canonical_field"),
        "verdict": verdict,
        "failed_conditions": failed,
        "reasons": reasons,
    }


# ─────────────────────────────────────────────────────────────
# 正交对与计数分流
# ─────────────────────────────────────────────────────────────

def orthogonality(records: list) -> dict:
    valid, invalid = [], []
    for r in records:
        missing = [f"{a}/{b}" for a, b in ORTHO_PAIRS if r.get(a) is None or r.get(b) is None]
        (invalid if missing else valid).append({**r, "missing_pairs": missing})

    skipped = [r for r in valid if r.get("issuer") == "executor" and r.get("actionability") is False]
    not_applicable = [r for r in valid if r.get("issuer") == "judge" and r.get("actionability") is False]
    manual = [r for r in valid if r.get("judge_source") == "manual"]
    frozen_in_window = [r for r in manual if r.get("frozen_state") == "in_window"]
    excluded = frozen_in_window  # 人工判据在冻结窗内 → 不得进自动通过率分母
    denominator = [r for r in valid if r not in skipped and r not in excluded]

    def ids(rs):
        return [r.get("id") for r in rs]

    return {
        "total": len(records),
        "valid": len(valid),
        "invalid": len(invalid),
        "invalid_ids": ids(invalid),
        "orthogonality_ok": not invalid,
        "auto_pass_denominator": len(denominator),
        "auto_pass_denominator_ids": ids(denominator),
        "excluded_manual_frozen_in_window": len(excluded),
        "excluded_ids": ids(excluded),
        "skipped_count": len(skipped),
        "skipped_ids": ids(skipped),
        "not_applicable_count": len(not_applicable),
        "not_applicable_ids": ids(not_applicable),
        "pair_check": {
            f"{a}×{b}": sum(1 for r in valid if r.get(a) is not None and r.get(b) is not None)
            for a, b in ORTHO_PAIRS
        },
    }


# ─────────────────────────────────────────────────────────────
# 命令
# ─────────────────────────────────────────────────────────────

def _load(path, root):
    full = path if os.path.isabs(path) else os.path.join(root, path)
    if not os.path.isfile(full):
        raise RuntimeError(f"输入文件不存在：{full}")
    with open(full, "r", encoding="utf-8") as fh:
        return json.load(fh)


def cmd_secondary(args):
    doc = _load(args.file, args.root)
    cases = doc.get("cases") if isinstance(doc, dict) else doc
    results = [check_secondary(c) for c in cases]
    for r in results:
        print(f"[{r['verdict']}] {r['secondary_field']} <- {r['canonical_field']}")
        for reason in r["reasons"]:
            print(f"    - {reason}")
    return 0


def cmd_orthogonality(args):
    doc = _load(args.file, args.root)
    records = doc.get("records") if isinstance(doc, dict) else doc
    res = orthogonality(records)
    print(json.dumps(res, ensure_ascii=False, indent=2))
    return 0 if res["orthogonality_ok"] else 2


def cmd_self_test(args):
    ok = True
    print("=" * 88)
    print("次级判定三条件 — 内置用例自测")
    print("=" * 88)
    base = {"secondary_field": "segment_duration_rounding", "canonical_field": "segment_duration",
            "batch": "b1", "canonical_batch": "b1", "canonical_issuer": "judge-A", "secondary_issuer": "judge-A"}
    sec_cases = [
        ("三条件全成立 → 次级", {**base, "derivable": True, "missing_no_effect": True}, "secondary"),
        ("缺①不可派生 → 主判据", {**base, "derivable": False, "missing_no_effect": True}, "canonical"),
        ("缺②缺失改终态 → 主判据", {**base, "derivable": True, "missing_no_effect": False}, "canonical"),
        ("缺③签发方不同 → 主判据", {**base, "derivable": True, "missing_no_effect": True,
                                "secondary_issuer": "judge-B"}, "canonical"),
        ("缺③批次不同 → 主判据", {**base, "derivable": True, "missing_no_effect": True,
                               "batch": "b2"}, "canonical"),
    ]
    for title, case, want in sec_cases:
        got = check_secondary(case)["verdict"]
        ok = ok and got == want
        print(f"  [{'PASS' if got == want else 'FAIL'}] {title}  期望 {want} 实得 {got}")

    print("-" * 88)
    print("三组正交对 — 内置用例自测")
    print("-" * 88)
    records = [
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
        {"id": "F", "role": "main", "judge_source": "auto",
         "frozen_state": "outside", "issuer": "judge", "actionability": True},
    ]
    res = orthogonality(records)
    wants = [
        ("正交性校验：缺 source_tag 的 F 判为不合法", res["invalid_ids"] == ["F"] and res["invalid"] == 1),
        ("跳过计数=2（执行侧 false：A、B）", res["skipped_count"] == 2 and res["skipped_ids"] == ["A", "B"]),
        ("不适配计数=2（判定侧 false：C、E）", res["not_applicable_count"] == 2 and res["not_applicable_ids"] == ["C", "E"]),
        ("自动通过率分母=2（排除执行侧 false 与人工冻结窗 C；D、E 入分母）",
         res["auto_pass_denominator"] == 2 and res["auto_pass_denominator_ids"] == ["D", "E"]),
        ("人工冻结窗排除数=1（C）", res["excluded_manual_frozen_in_window"] == 1 and res["excluded_ids"] == ["C"]),
    ]
    for title, passed in wants:
        ok = ok and passed
        print(f"  [{'PASS' if passed else 'FAIL'}] {title}")
    print("-" * 88)
    print(f"结论：{'全部通过' if ok else '存在未通过项'}")
    print("=" * 88)
    return 0 if ok else 2


def main(argv=None):
    p = argparse.ArgumentParser(description="判定口径校验器（次级三条件 + 三组正交对）")
    p.add_argument("--root", default=ROOT_DEFAULT)
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("secondary", help="次级判定三条件校验")
    sp.add_argument("--file", required=True)
    sp.set_defaults(func=cmd_secondary)

    op = sub.add_parser("orthogonality", help="三组正交对与计数分流")
    op.add_argument("--file", required=True)
    op.set_defaults(func=cmd_orthogonality)

    tp = sub.add_parser("self-test", help="内置用例自检")
    tp.set_defaults(func=cmd_self_test)

    args = p.parse_args(argv)
    try:
        return args.func(args)
    except RuntimeError as e:
        print(f"[error] {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
