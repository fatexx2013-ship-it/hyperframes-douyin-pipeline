#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
normalize_point.py —— 规范化器（normalize_point 六步枚举 + 签名域）

所属产线：/Volumes/PSSD/抖音视频
配置真源：config/canonicalization.json
资料来源：AI-Film-Studio 第二条私信 2026-09-26（normalize_point 完整枚举）

设计要点
--------
1. 规范化按固定顺序执行，**顺序本身进签名域**：改变枚举顺序 = 规范化器换实现，
   canonicalizer_version 必须同步变更（由 param_contract.py 判定为硬停）。
2. 显式不做 UNICODE_NORMALIZATION：避免引入 locale 依赖，规范化结果不得随运行环境
   语言/地区设置变化。
3. STRIP_INLINE_COMMENT 为最后一步：按枚举顺序执行后**不回溯**清理因剥离注释而新产生的
   行尾空白——这正是「顺序进签名域」的直接体现，顺序调换会改变输出。

用法
----
  python3 scripts/normalize_point.py sign                 # 打印枚举顺序与签名
  python3 scripts/normalize_point.py sign --write         # 把签名回填 config/canonicalization.json
  python3 scripts/normalize_point.py normalize <file>     # 规范化并输出（--out 落盘）
  python3 scripts/normalize_point.py verify <file>        # 幂等性与触发项自检
  python3 scripts/normalize_point.py self-test            # 内置用例自检

退出码：0 = 通过；2 = 自检/校验不通过；1 = 用法或环境错误
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DEFAULT = os.path.dirname(SCRIPT_DIR)
CANON_DEFAULT = os.path.join(ROOT_DEFAULT, "config", "canonicalization.json")

# 枚举顺序：一份实现只允许按此顺序执行；顺序进签名域
NORMALIZE_ORDER = [
    "STRIP_BOM",
    "UNIFY_LINE_ENDING",
    "STRIP_TRAILING_WHITESPACE",
    "STRIP_LEADING_WHITESPACE",
    "COLLAPSE_INTERNAL_WHITESPACE",
    "STRIP_INLINE_COMMENT",
]
EXCLUDED_POINTS = ["UNICODE_NORMALIZATION"]
SIGNATURE_RULE = "sha256('|'.join(normalize_point_order))[:16]"


# ─────────────────────────────────────────────────────────────
# 六步实现
# ─────────────────────────────────────────────────────────────

def _strip_bom(text: str) -> str:
    return text.lstrip("\ufeff")


def _unify_line_ending(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _strip_trailing_whitespace(text: str) -> str:
    return "\n".join(line.rstrip(" \t\f\v") for line in text.split("\n"))


def _strip_leading_whitespace(text: str) -> str:
    return "\n".join(line.lstrip(" \t\f\v") for line in text.split("\n"))


def _collapse_internal_whitespace(text: str) -> str:
    return "\n".join(re.sub(r"[ \t\f\v]+", " ", line) for line in text.split("\n"))


def _strip_inline_comment(text: str) -> str:
    """仅剥离「行首 #」或「前置空白 + #」起始的注释段；# 紧邻非空白字符时保留（非注释）。

    按枚举顺序，本步是最后一步，剥离后不再做尾随空白清理（不回溯）。
    """
    out = []
    for line in text.split("\n"):
        idx = line.find("#")
        if idx == 0:
            out.append("")
        elif idx > 0 and line[idx - 1] in " \t":
            out.append(line[:idx].rstrip(" \t"))
        else:
            out.append(line)
    return "\n".join(out)


STEPS = {
    "STRIP_BOM": _strip_bom,
    "UNIFY_LINE_ENDING": _unify_line_ending,
    "STRIP_TRAILING_WHITESPACE": _strip_trailing_whitespace,
    "STRIP_LEADING_WHITESPACE": _strip_leading_whitespace,
    "COLLAPSE_INTERNAL_WHITESPACE": _collapse_internal_whitespace,
    "STRIP_INLINE_COMMENT": _strip_inline_comment,
}


def normalize_text(text: str, order=None) -> str:
    if text is None:
        return ""
    for step in (order or NORMALIZE_ORDER):
        fn = STEPS.get(step)
        if fn is None:
            raise RuntimeError(f"未知的 normalize_point：{step}")
        text = fn(text)
    return text


def normalize_signature(order=None) -> str:
    """枚举顺序的签名（前 16 位 hex）；顺序变更即签名变更。"""
    return hashlib.sha256("|".join(order or NORMALIZE_ORDER).encode("utf-8")).hexdigest()[:16]


def detect_features(text: str) -> dict:
    # 行尾/行首空白检测须在统一行尾后进行：未统一的 CR 会遮蔽其前的空白
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    return {
        "has_bom": text.startswith("\ufeff"),
        "has_crlf": "\r\n" in text,
        "has_lone_cr": bool(re.search(r"\r(?!\n)", text)),
        "has_trailing_ws": any(line != line.rstrip(" \t\f\v") for line in lines),
        "has_leading_ws": any(line != line.lstrip(" \t\f\v") for line in lines),
        "has_internal_multi_ws": bool(re.search(r"[ \t\f\v]{2,}", text)),
        "has_inline_comment": any(
            line.find("#") == 0 or (line.find("#") > 0 and line[line.find("#") - 1] in " \t")
            for line in lines
        ),
    }


def load_config(path=CANON_DEFAULT) -> dict:
    if not os.path.isfile(path):
        return {}
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def verify_order_from_config(cfg: dict) -> list:
    """配置里声明的顺序与脚本实现顺序必须一致，否则视为规范化器换实现。"""
    declared = (cfg or {}).get("normalize_point_order")
    problems = []
    if declared and list(declared) != NORMALIZE_ORDER:
        problems.append(f"配置顺序 {declared} ≠ 实现顺序 {NORMALIZE_ORDER}")
    if problems:
        raise RuntimeError("；".join(problems))
    return NORMALIZE_ORDER


# ─────────────────────────────────────────────────────────────
# 命令
# ─────────────────────────────────────────────────────────────

def cmd_sign(args):
    cfg = load_config(args.canon)
    verify_order_from_config(cfg)
    sig = normalize_signature()
    print("=" * 88)
    print("normalize_point 枚举顺序（按执行顺序，顺序进签名域）")
    print("=" * 88)
    for i, step in enumerate(NORMALIZE_ORDER, 1):
        print(f"  {i}. {step}")
    for ex in EXCLUDED_POINTS:
        print(f"  -- 显式不做：{ex}（避免引入 locale 依赖）")
    print("-" * 88)
    print(f"签名规则        : {SIGNATURE_RULE}")
    print(f"actual 签名     : {sig}")
    print(f"配置声明签名    : {(cfg or {}).get('signature') or '-'}")
    drifted = bool(cfg) and cfg.get("signature") and cfg["signature"] != sig
    print(f"一致性          : {'漂移（配置需更新）' if drifted else '一致'}")
    if args.write:
        if not cfg:
            print("[error] 配置文件不存在，无法回填", file=sys.stderr)
            return 1
        cfg["signature"] = sig
        with open(args.canon, "w", encoding="utf-8") as fh:
            json.dump(cfg, fh, ensure_ascii=False, indent=2)
            fh.write("\n")
        print(f"已回填签名 → {args.canon}")
    print("=" * 88)
    return 0


def cmd_normalize(args):
    cfg = load_config(args.canon)
    verify_order_from_config(cfg)
    path = args.file if os.path.isabs(args.file) else os.path.join(args.root, args.file)
    if not os.path.isfile(path):
        print(f"[error] 文件不存在：{path}", file=sys.stderr)
        return 1
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        raw = fh.read()
    norm = normalize_text(raw)
    summary = {
        "input": os.path.abspath(path),
        "canonicalizer_version": normalize_signature(),
        "bytes_in": len(raw.encode("utf-8")),
        "bytes_out": len(norm.encode("utf-8")),
        "lines_out": norm.count("\n") + 1,
        "features": detect_features(raw),
    }
    if args.out:
        out = args.out if os.path.isabs(args.out) else os.path.join(args.root, args.out)
        os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
        with open(out, "w", encoding="utf-8") as fh:
            fh.write(norm)
        summary["output"] = os.path.abspath(out)
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        print("-" * 88)
        print(norm)
    return 0


def cmd_verify(args):
    cfg = load_config(args.canon)
    verify_order_from_config(cfg)
    path = args.file if os.path.isabs(args.file) else os.path.join(args.root, args.file)
    if not os.path.isfile(path):
        print(f"[error] 文件不存在：{path}", file=sys.stderr)
        return 1
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        raw = fh.read()
    once = normalize_text(raw)
    twice = normalize_text(once)
    res = {
        "input": os.path.abspath(path),
        "canonicalizer_version": normalize_signature(),
        "idempotent": once == twice,
        "features": detect_features(raw),
        "checks": [
            {"check": "幂等性（normalize(x) == normalize(normalize(x))）", "pass": once == twice},
            {"check": "无 BOM 残留", "pass": not once.startswith("\ufeff")},
            {"check": "无 CR 残留", "pass": "\r" not in once},
            {"check": "无行尾/行首空白残留（注释剥离行除外）",
             "pass": all(l == l.strip(" \t\f\v") for l in once.split("\n") if not l.startswith("#"))},
        ],
    }
    for c in res["checks"]:
        print(f"  [{'PASS' if c['pass'] else 'FAIL'}] {c['check']}")
    print(f"  规范化器版本：{res['canonicalizer_version']}  幂等：{res['idempotent']}")
    return 0 if all(c["pass"] for c in res["checks"]) else 2


def cmd_self_test(args):
    cases = [
        {
            "name": "BOM+CRLF+首尾空白+内部多空白+行内注释（六步全触发）",
            "raw": "\ufeffhello   world  \r\n   second line # note\r\nthird#not_comment\r\n",
            "want": "hello world\nsecond line\nthird#not_comment\n",
            "features": ["has_bom", "has_crlf", "has_trailing_ws", "has_leading_ws",
                         "has_internal_multi_ws", "has_inline_comment"],
        },
        {
            "name": "行首注释整行清空（注释剥离为最后一步，不回溯补空行清理）",
            "raw": "# pure comment\nvalue   x\n",
            "want": "\nvalue x\n",
            "features": ["has_inline_comment"],
        },
        {
            "name": "# 紧邻非空白字符不算注释，原样保留",
            "raw": "color#ff0000\n",
            "want": "color#ff0000\n",
            "features": [],
        },
        {
            "name": "无触发项文本保持不变",
            "raw": "type: video\nfps: 30\n",
            "want": "type: video\nfps: 30\n",
            "features": [],
        },
    ]
    ok = True
    print("=" * 88)
    print("normalize_point 内置用例自检")
    print("=" * 88)
    for c in cases:
        got = normalize_text(c["raw"])
        pass1 = got == c["want"]
        pass2 = normalize_text(got) == got  # 幂等
        feats = detect_features(c["raw"])
        pass3 = all(feats[k] for k in c["features"]) if c["features"] else not any(feats.values())
        ok = ok and pass1 and pass2 and pass3
        print(f"  [{'PASS' if (pass1 and pass2 and pass3) else 'FAIL'}] {c['name']}")
        if not (pass1 and pass2 and pass3):
            print(f"         got  : {got!r}")
            print(f"         want : {c['want']!r}")
            print(f"         幂等={pass2} 特征={pass3} {feats}")
    # 顺序敏感性：调换 UNIFY_LINE_ENDING 与 STRIP_TRAILING_WHITESPACE → 签名与输出都必须变化
    # （探针 "a \r\n"：TRS 先于 UNIFY 时 CR 会遮蔽其前空白，尾空白残留，输出可区分）
    swapped = list(NORMALIZE_ORDER)
    swapped[1], swapped[2] = swapped[2], swapped[1]
    sig_now, sig_swapped = normalize_signature(), normalize_signature(swapped)
    probe = "a \r\n"
    out_now, out_swapped = normalize_text(probe), normalize_text(probe, swapped)
    order_sensitive = sig_now != sig_swapped and out_now != out_swapped
    ok = ok and order_sensitive
    print(f"  [{'PASS' if order_sensitive else 'FAIL'}] 顺序进签名域（调换 UNIFY_LINE_ENDING/STRIP_TRAILING_WHITESPACE 后签名与输出均变化）")
    print(f"         原顺序签名 {sig_now} / 调换后 {sig_swapped}；探针 {probe!r} 输出 {out_now!r} vs {out_swapped!r}")
    print("-" * 88)
    print(f"结论：{'全部通过' if ok else '存在未通过项'}  规范化器版本={normalize_signature()}")
    print("=" * 88)
    return 0 if ok else 2


def main(argv=None):
    p = argparse.ArgumentParser(description="normalize_point 规范化器（六步枚举 + 签名域）")
    p.add_argument("--root", default=ROOT_DEFAULT)
    p.add_argument("--canon", default=CANON_DEFAULT)
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("sign", help="打印枚举顺序与签名，可回填配置")
    sp.add_argument("--write", action="store_true")
    sp.set_defaults(func=cmd_sign)

    np_ = sub.add_parser("normalize", help="规范化文件内容")
    np_.add_argument("file")
    np_.add_argument("--out", default=None)
    np_.set_defaults(func=cmd_normalize)

    vp = sub.add_parser("verify", help="幂等性与触发项自检")
    vp.add_argument("file")
    vp.set_defaults(func=cmd_verify)

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
