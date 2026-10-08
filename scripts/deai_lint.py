#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""deai_lint.py — 文案去 AI 味量化闸门（A9，落地自知识库候选 A9）

依据：docs/产线规范.md 「文案层（v1.13.0，A9 去 AI 味量化闸门）」
定位：story 层**只读**校验器。读 script.json（可含 build_audio.py 回填后的
      时间轴字段），对**文案全集**做 7 类可量化体检，输出 0–100 分与命中明细。
      不改任何文件、不动 config/ 共享真源、不参与渲染。

职责边界
--------
  · 拦的是「文案读起来像 AI 写的」这类**可量化**特征，不评判选题好坏；
  · 与段1 design_ai_gate（视觉 AI 痕迹）/ 段2 frame_audit（成片帧级）并列，
    属**文案层**第三类前置闸门，可独立跑、可被 storyctl build 前置调用；
  · 门禁判据（本文件内的阈值表）是可追溯常量，改动需同步规范版本号。

7 类体检项
----------
  D1 句长机械均匀   —— 句长标准差过小（AI 典型"每句一样长"）
  D2 连接词密度     —— 首先/其次/综上所述… 等书面连接词密度
  D3 口播套话       —— 众所周知/不难发现/在…的今天 等空话词
  D4 排比模板       —— "不是…而是…"/"越…越…"/三连同起首
  D5 标点单调       —— 逗号过密 / 感叹号滥用 / 全无问号
  D6 短语复读       —— 4+ 字短语重复出现
  D7 句长极差过小   —— 长短句节奏塌陷

退出码（钉死，与两段门禁同构）
------------------------------
  0 通过（含仅有 WARN）
  1 用法/输入错误（路径不存在、JSON 坏、无文案）
  2 检出问题（存在 FAIL 项）—— 属设计问题，不是 bug

用法
----
  python3 scripts/deai_lint.py story/<name>            # 目录（自动找 script.json）
  python3 scripts/deai_lint.py story/<name>/script.json
  python3 scripts/deai_lint.py story/<name> --json out.json --quiet
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import Counter

EXIT_OK = 0
EXIT_USAGE = 1
EXIT_DETECT = 2

# ── 阈值表（可追溯常量；改动须同步 docs/产线规范.md 版本号） ──────────────
TH = {
    "std_fail": 6.0,          # 句长标准差 < 6 字 → FAIL
    "std_warn": 9.0,          # < 9 字 → WARN
    "range_warn": 6,          # 最长句 - 最短句 < 6 字 → WARN
    "conn_ratio_fail": 0.25,  # 连接词命中数 / 句数
    "conn_ratio_warn": 0.12,
    "cliche_warn": 3,         # 套话命中次数
    "cliche_fail": 6,
    "parallel_warn": 2,       # 排比模板命中次数
    "comma_per_sentence_warn": 3.0,
    "exclaim_ratio_warn": 0.30,
    "phrase_min_len": 4,      # 复读短语最小字数
    "phrase_repeat_warn": 3,  # 同一短语出现次数
    "min_sentences": 6,       # 少于该句数不做 D1/D7 判定（样本不足）
}

CONNECTIVES = [
    "首先", "其次", "再次", "最后", "总的来说", "总而言之", "综上所述",
    "值得注意", "此外", "因此", "然而", "不仅仅是", "不仅如此", "换言之",
    "简而言之", "一方面", "另一方面", "与此同时", "由此可见",
    "除此之外", "在此基础上",
]

CLICHES = [
    "众所周知", "显而易见", "不难发现", "不言而喻", "毋庸置疑",
    "在当今", "在这个", "随着时代", "在这个时代", "在信息爆炸",
    "赋能", "闭环", "抓手", "底层逻辑", "深度赋能", "全面提升", "完美解决",
    "让我们", "相信大家", "不得不说", "值得一提的是",
]
CLICHE_PATTERNS = [
    re.compile(r"在.{0,6}的今天"),
    re.compile(r"随着.{0,8}的发展"),
    re.compile(r"作为一[个名]"),
    re.compile(r"不[得容]不"),
]

PARALLEL_PATTERNS = [
    re.compile(r"不是.{0,12}而是"),
    re.compile(r"越.{0,10}越.{0,10}"),
    re.compile(r"既.{0,12}又.{0,12}"),
    re.compile(r"只有.{0,12}才"),
]

PUNCT_SPLIT = re.compile(r"[。！？!?；;\n]+")
NON_CONTENT = re.compile(r"[\s，。！？!?.,;:：、—\-…“”\"'（）()《》【】\[\]]+")
# 强调整饰标记（story 层既有约定：<accent>…</accent> / <b>…</b>），
# 统计前必须剥离，否则 D6 短语复读会把标签名当成复读文本（误报源）。
TAG_RE = re.compile(r"<[^>]{0,64}>")
CJK_RUN = re.compile(r"[\u4e00-\u9fff]+")


def plain(s: str) -> str:
    """剥离强调整饰标记后的纯文案。"""
    return TAG_RE.sub("", s)


def _die(msg: str, code: int = EXIT_USAGE) -> int:
    print(f"[deai_lint] 用法/输入错误：{msg}", file=sys.stderr)
    return code


def resolve_script(path: str) -> str:
    if os.path.isdir(path):
        return os.path.join(path, "script.json")
    return path


def collect_texts(script: dict) -> list:
    """文案全集：台词 + 卡片文案 + 片尾 + 标题。保持出现顺序，便于报告定位。"""
    out = []

    def add(src, val):
        if isinstance(val, str) and val.strip():
            out.append({"src": src, "text": val.strip()})

    if isinstance(script.get("title"), str):
        add("title", script["title"])
    for i, sc in enumerate(script.get("scenes", [])):
        card = sc.get("card") or {}
        for k in ("eyebrow", "title", "subtitle", "cta", "sub", "big", "big_label"):
            if isinstance(card, dict) and k in card:
                add(f"scenes[{i}].card.{k}", card[k])
        for j, ln in enumerate(sc.get("lines", []) or []):
            if isinstance(ln, dict) and "text" in ln:
                add(f"scenes[{i}].lines[{j}].text", ln["text"])
    ep = script.get("epilogue")
    if isinstance(ep, dict):
        for k, v in ep.items():
            add(f"epilogue.{k}", v)
    return out


def split_sentences(text: str) -> list:
    return [s.strip() for s in PUNCT_SPLIT.split(plain(text)) if s.strip()]


def content_len(s: str) -> int:
    return len(NON_CONTENT.sub("", plain(s)))


def lint(script: dict) -> dict:
    items = collect_texts(script)
    # 非 per-story 双脚本路线（无 scenes/lines）不适用本闸门：给出 SKIP 结论而非误判
    if not script.get("scenes") and not script.get("lines"):
        return {
            "schema": "deai_lint/v1",
            "verdict": "SKIP",
            "score": None,
            "metrics": {"sentence_count": 0, "char_count": 0,
                        "note": "script.json 无 scenes/lines —— 非 per-story 双脚本路线，本闸门不适用"},
            "findings": [{"id": "D0", "level": "SKIP",
                          "detail": "无 scenes/lines：跳过文案层体检（不判 FAIL）", "evidence": []}],
            "sentences": [],
            "thresholds": TH,
        }
    lines = [it["text"] for it in items]
    sents = []
    for it in items:
        for s in split_sentences(it["text"]):
            sents.append({"text": s, "src": it["src"], "len": content_len(s)})

    findings = []
    metrics = {}

    lengths = [s["len"] for s in sents if s["len"] > 0]
    n = len(lengths)
    metrics["sentence_count"] = n
    metrics["char_count"] = sum(len(NON_CONTENT.sub("", t)) for t in lines)

    def add(fid, level, detail, evidence=None):
        findings.append({"id": fid, "level": level, "detail": detail,
                         "evidence": (evidence or [])[:8]})

    # D1 句长机械均匀
    if n >= TH["min_sentences"]:
        mean = sum(lengths) / n
        var = sum((x - mean) ** 2 for x in lengths) / n
        std = var ** 0.5
        metrics["sentence_len_mean"] = round(mean, 2)
        metrics["sentence_len_std"] = round(std, 2)
        metrics["sentence_len_min"] = min(lengths)
        metrics["sentence_len_max"] = max(lengths)
        if std < TH["std_fail"]:
            add("D1", "FAIL", f"句长标准差 {std:.2f} < {TH['std_fail']}（每句一样长 = 典型 AI 节奏）",
                [f"{s['len']}字 · {s['text'][:24]}" for s in sents])
        elif std < TH["std_warn"]:
            add("D1", "WARN", f"句长标准差 {std:.2f} < {TH['std_warn']}（节奏偏平）", [])
        # D7 句长极差
        if max(lengths) - min(lengths) < TH["range_warn"]:
            add("D7", "WARN",
                f"最长/最短句仅差 {max(lengths) - min(lengths)} 字（< {TH['range_warn']}）：缺长短句对照", [])
    else:
        add("D1", "SKIP", f"句数 {n} < {TH['min_sentences']}，样本不足不做句长分布判定", [])

    # D2 连接词密度
    conn_hits = []
    for s in sents:
        for w in CONNECTIVES:
            if w in s["text"]:
                conn_hits.append(f"{w} · {s['text'][:24]}")
    ratio = len(conn_hits) / n if n else 0.0
    metrics["connective_hits"] = len(conn_hits)
    metrics["connective_ratio"] = round(ratio, 3)
    if ratio > TH["conn_ratio_fail"]:
        add("D2", "FAIL", f"书面连接词密度 {ratio:.2f} > {TH['conn_ratio_fail']}", conn_hits)
    elif ratio > TH["conn_ratio_warn"]:
        add("D2", "WARN", f"书面连接词密度 {ratio:.2f} > {TH['conn_ratio_warn']}", conn_hits)

    # D3 口播套话
    cliche_hits = []
    for s in sents:
        for w in CLICHES:
            if w in s["text"]:
                cliche_hits.append(f"{w} · {s['text'][:24]}")
        for p in CLICHE_PATTERNS:
            m = p.search(s["text"])
            if m:
                cliche_hits.append(f"{m.group(0)} · {s['text'][:24]}")
    metrics["cliche_hits"] = len(cliche_hits)
    if len(cliche_hits) >= TH["cliche_fail"]:
        add("D3", "FAIL", f"套话/空话命中 {len(cliche_hits)} 次 ≥ {TH['cliche_fail']}", cliche_hits)
    elif len(cliche_hits) >= TH["cliche_warn"]:
        add("D3", "WARN", f"套话/空话命中 {len(cliche_hits)} 次", cliche_hits)

    # D4 排比模板
    para_hits = []
    for s in sents:
        for p in PARALLEL_PATTERNS:
            m = p.search(s["text"])
            if m:
                para_hits.append(f"{m.group(0)} · {s['text'][:24]}")
    # 三连同起首（连续 3 句前 2 字相同）
    for i in range(len(sents) - 2):
        a, b, c = (content_prefix(sents[i]["text"]), content_prefix(sents[i + 1]["text"]),
                   content_prefix(sents[i + 2]["text"]))
        if a and a == b == c:
            para_hits.append(f"三连同起首「{a}」 · {sents[i]['text'][:24]} …")
            break
    metrics["parallel_hits"] = len(para_hits)
    if len(para_hits) >= TH["parallel_warn"]:
        add("D4", "WARN", f"排比模板命中 {len(para_hits)} 次 ≥ {TH['parallel_warn']}", para_hits)

    # D5 标点单调
    raw = "".join(lines)
    commas = raw.count("，") + raw.count(",")
    exclaims = raw.count("！") + raw.count("!")
    qmarks = (raw.count("？") + raw.count("?") + raw.count("：") + raw.count(":"))
    per_sent = commas / n if n else 0.0
    ex_ratio = exclaims / n if n else 0.0
    metrics["comma_per_sentence"] = round(per_sent, 2)
    metrics["exclaim_ratio"] = round(ex_ratio, 3)
    metrics["question_or_colon"] = qmarks
    if per_sent > TH["comma_per_sentence_warn"]:
        add("D5", "WARN", f"逗号/句 = {per_sent:.2f} > {TH['comma_per_sentence_warn']}", [])
    if ex_ratio > TH["exclaim_ratio_warn"]:
        add("D5", "WARN", f"感叹号/句 = {ex_ratio:.2f} > {TH['exclaim_ratio_warn']}", [])
    if n >= TH["min_sentences"] and qmarks == 0 and exclaims == 0:
        add("D5", "WARN", "全篇无问号/冒号/感叹号：口播语气单一（陈述句一条道）", [])

    # D6 短语复读（仅在中文连续串内取 n-gram：避免英文单词/标记造成的误报）
    grams = Counter()
    for s in sents:
        for run in CJK_RUN.findall(plain(s["text"])):
            for size in (TH["phrase_min_len"], TH["phrase_min_len"] + 2):
                for i in range(len(run) - size + 1):
                    grams[run[i:i + size]] += 1
    cand = [g for g, c in grams.items()
            if c >= TH["phrase_repeat_warn"] and len(g) >= TH["phrase_min_len"]]
    # 去重叠：若某短语被更长的命中短语包含，则只报最长者（避免"自己写了/己写了一/写了一个"刷屏）
    cand.sort(key=len, reverse=True)
    kept = []
    for g in cand:
        if not any(g in k for k in kept):
            kept.append(g)
    repeats = [f"{g} ×{grams[g]}" for g in kept[:8]]
    metrics["phrase_repeats"] = repeats
    if repeats:
        add("D6", "WARN", f"{len(repeats)} 个短语重复 ≥{TH['phrase_repeat_warn']} 次", repeats)

    # 评分
    penalty = {"FAIL": 12, "WARN": 4, "SKIP": 0}
    score = 100 - sum(penalty.get(f["level"], 0) for f in findings)
    score = max(0, min(100, score))
    metrics["ai_flavor_score"] = score
    fails = [f for f in findings if f["level"] == "FAIL"]
    warns = [f for f in findings if f["level"] == "WARN"]
    verdict = "FAIL" if fails else ("WARN" if warns else "PASS")

    return {
        "schema": "deai_lint/v1",
        "verdict": verdict,
        "score": score,
        "metrics": metrics,
        "findings": findings,
        "sentences": sents,
        "thresholds": TH,
    }


def content_prefix(s: str) -> str:
    t = NON_CONTENT.sub("", plain(s))
    return t[:2] if len(t) >= 2 else ""


def print_report(rep: dict, script_path: str, quiet: bool = False) -> None:
    m = rep["metrics"]
    print(f"[deai_lint] {script_path}")
    score = "n/a" if rep["score"] is None else f"{rep['score']}/100"
    print(f"  verdict={rep['verdict']}  score={score}  "
          f"句子 {m['sentence_count']} 字 {m['char_count']}")
    if "sentence_len_std" in m:
        print(f"  句长 均值 {m['sentence_len_mean']} / 标准差 {m['sentence_len_std']} / "
              f"范围 {m['sentence_len_min']}–{m['sentence_len_max']}")
    print(f"  连接词 {m['connective_hits']}（密度 {m['connective_ratio']}） · "
          f"套话 {m['cliche_hits']} · 排比 {m['parallel_hits']} · "
          f"逗号/句 {m['comma_per_sentence']}")
    if rep["findings"]:
        print("  命中项：")
        for f in rep["findings"]:
            print(f"    [{f['level']}] {f['id']} {f['detail']}")
            for e in f["evidence"][:4]:
                print(f"        - {e}")
    else:
        print("  命中项：无")
    if not quiet:
        print("  句长序列：", " ".join(str(s["len"]) for s in rep["sentences"]))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        prog="deai_lint",
        description="文案去 AI 味量化闸门（A9）。退出码 0=通过/仅 WARN，1=用法错误，2=检出 FAIL")
    ap.add_argument("target", help="story 目录或 script.json 路径")
    ap.add_argument("--json", dest="json_out", default=None, help="把完整报告写入该 JSON 路径")
    ap.add_argument("--quiet", action="store_true", help="不打印句长序列")
    args = ap.parse_args(argv)

    sp = resolve_script(args.target)
    if not os.path.isfile(sp):
        return _die(f"找不到 script.json：{sp}")
    try:
        script = json.load(open(sp, encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return _die(f"script.json 解析失败：{exc}")

    rep = lint(script)
    rep["script_path"] = os.path.abspath(sp)
    print_report(rep, sp, quiet=args.quiet)

    if args.json_out:
        with open(args.json_out, "w", encoding="utf-8") as f:
            json.dump(rep, f, ensure_ascii=False, indent=2)
        print(f"  报告落盘：{args.json_out}")

    return EXIT_DETECT if rep["verdict"] == "FAIL" else EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
