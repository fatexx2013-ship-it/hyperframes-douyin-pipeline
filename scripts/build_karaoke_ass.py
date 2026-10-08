#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_karaoke_ass.py —— 逐字卡拉OK ASS 生成器（产线落地版 v1.0.0）

输入：captions.srt（整句字幕，产线既有产物）+ captions.dtw.json（whisper_dtw.py 产出）
输出：captions.kara.ass（\\kf 逐字上色；已唱=primary_colour，未唱=secondary_colour）

设计红线：
1. **不回写、不覆盖** captions.srt / captions.ass；本脚本只新增 captions.kara.ass。
2. **文本对不上就退出码 2**（不做静默重排），由 render.sh 回退到整句 SRT 链路。
3. 时间轴一律取自 DTW token 级时间；SRT 只提供句子边界与呈现文本，句子边界不被篡改。
4. 时长下限 1cs，逐字时长按 token 内部等分（t_dtw 单位 1/100s）。

用法：
    python3 scripts/build_karaoke_ass.py \
        --srt story/xxx/captions.srt \
        --dtw story/xxx/captions.dtw.json \
        --out story/xxx/captions.kara.ass \
        [--config config/karaoke.json]

退出码：0 成功 / 1 输入或依赖错误 / 2 文本栅栏未过（应回退整句 SRT）
"""

import argparse
import difflib
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CS_RE = re.compile(r"(\d+):(\d{2}):(\d{2})[,.](\d{1,3})")


def resolve(p):
    if not p:
        return p
    return p if os.path.isabs(p) else os.path.join(ROOT, p)


def load_cfg(path):
    p = resolve(path)
    if os.path.isfile(p):
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    return {}


def to_cs(ms):
    return max(1, int(round(ms / 10.0)))


def fmt_ts(ms):
    """输入毫秒，输出 ASS 时间戳 h:mm:ss.cc（ASS 时间基为厘秒）。"""
    cs = int(round(float(ms) / 10.0))
    h, rem = divmod(cs, 360000)
    m, rem = divmod(rem, 6000)
    s, c = divmod(rem, 100)
    return f"{h:d}:{m:02d}:{s:02d}.{c:02d}"


def parse_srt(path):
    with open(path, encoding="utf-8-sig") as f:
        raw = f.read()
    cues = []
    for blk in re.split(r"\r?\n\s*\r?\n", raw.strip()):
        lines = [l for l in blk.splitlines() if l.strip() != ""]
        if not lines:
            continue
        idx_line = lines[0].strip()
        if idx_line.isdigit():
            lines = lines[1:]
        if not lines:
            continue
        m = lines[0].strip()
        mm = re.match(r"([\d:.,]+)\s*-->\s*([\d:.,]+)", m)
        if not mm:
            continue
        a, b = mm.group(1), mm.group(2)
        ma, mb = CS_RE.search(a), CS_RE.search(b)
        if not ma or not mb:
            continue
        s = int(ma.group(1)) * 3600000 + int(ma.group(2)) * 60000 + int(ma.group(3)) * 1000 + int(ma.group(4).ljust(3, "0"))
        e = int(mb.group(1)) * 3600000 + int(mb.group(2)) * 60000 + int(mb.group(3)) * 1000 + int(mb.group(4).ljust(3, "0"))
        text = " ".join(l.strip() for l in lines[1:]).strip()
        if text:
            cues.append({"start": s, "end": e, "text": text})
    return cues


def parse_dtw(path):
    """返回 [(start_ms, end_ms, ch), ...]，按时间排序；t_dtw 单位 1/100s。"""
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    chars = []
    for seg in data.get("transcription", []):
        for t in seg.get("tokens", []):
            txt = str(t.get("text", ""))
            if txt.startswith("[_"):
                continue
            td = t.get("t_dtw", -1)
            if td is None or td < 0:
                td = t.get("t0", -1)
            if td is None or td < 0:
                continue
            td = int(td)
            t1 = t.get("t1", td + 1)
            t1 = int(t1) if t1 is not None and int(t1) > td else td + 1
            vis = [c for c in txt if not c.isspace()]
            if not vis:
                continue
            span = (t1 - td) * 10.0
            step = span / len(vis)
            for i, c in enumerate(vis):
                chars.append((td * 10.0 + i * step, td * 10.0 + (i + 1) * step, c))
    chars.sort(key=lambda x: x[0])
    return chars


def assemble(cues, dchars, cfg, strict=True, min_ratio=0.85):
    """把 DTW 逐字时间轴贴到 SRT 句界上，返回 (ass_lines, stats)。文本栅栏未过返回 (None, stats)。"""
    style = cfg.get("style") or {}
    gate = cfg.get("gate") or {}
    body = []
    cursor = 0
    stats = {"cues": len(cues), "rendered": 0, "dtw_chars": len(dchars), "mismatch": [], "max_char_cs": 0,
             "long_chars": 0, "kf_sum_drift_cs": 0}
    tol = 150.0  # ms：句子边界容差

    for ci, cue in enumerate(cues, 1):
        win = []
        j = cursor
        while j < len(dchars) and dchars[j][0] < cue["end"] + tol:
            if dchars[j][1] > cue["start"] - tol:
                win.append(dchars[j])
            j += 1
        cursor = max(cursor, j)

        text_chars = [c for c in cue["text"] if not c.isspace()]
        if not text_chars:
            continue

        dtext = "".join(c for _, _, c in win)
        ttext = "".join(text_chars)
        starts = [None] * len(text_chars)

        if ttext == dtext and win:
            for i, (s, _, _) in enumerate(win):
                starts[i] = s
            ratio = 1.0
        else:
            sm = difflib.SequenceMatcher(None, dtext, ttext, autojunk=False)
            ratio = sm.ratio()
            if ratio < 1.0:
                stats["mismatch"].append({"cue": ci, "ratio": round(ratio, 3),
                                          "srt": ttext, "dtw": dtext})
                # 硬栅栏：低于地板值（或 strict 模式下任何不一致）→ 整文件回退整句 SRT
                if strict or ratio < min_ratio:
                    return None, stats
            # 线性分布式回填：匹配块用 DTW 真值，其余按句窗等比均分
            span = float(max(cue["end"] - cue["start"], 10))
            step = span / len(text_chars)
            for i in range(len(text_chars)):
                starts[i] = cue["start"] + i * step
            for blk in sm.get_matching_blocks():
                if blk.size == 0:
                    continue
                for k in range(blk.size):
                    di = blk.a + k
                    ti = blk.b + k
                    if di < len(win):
                        starts[ti] = win[di][0]

        starts = [min(max(s if s is not None else cue["start"], cue["start"]), cue["end"]) for s in starts]
        starts = sorted(starts)
        # 句首对齐句边界：保证 \kf 时长之和 == 整句时长（卡拉OK不提前跑完）
        starts[0] = float(cue["start"])
        # DTW 同一起拍抖动合并：run 内等分，避免出现 \kf1 闪烁
        i = 0
        n = len(starts)
        while i < n:
            j = i
            while j + 1 < n and abs(starts[j + 1] - starts[i]) < 1.0:
                j += 1
            if j > i:
                nxt = starts[j + 1] if j + 1 < n else float(cue["end"])
                span = max(10.0, float(nxt) - float(starts[i]))
                step = span / (j - i + 1)
                for k in range(i, j + 1):
                    starts[k] = float(starts[i]) + (k - i) * step
            i = j + 1
        # 逐字时长：下一字起拍 - 本字起拍；末字用句尾。不做上限截断，否则总时长漂移
        pairs = []
        max_char_ms = gate.get("max_char_ms") or 800
        for i, ch in enumerate(text_chars):
            nxt = starts[i + 1] if i + 1 < len(text_chars) else float(cue["end"])
            dur_ms = float(nxt) - float(starts[i])
            if dur_ms > float(max_char_ms):
                stats["long_chars"] = stats.get("long_chars", 0) + 1
            pairs.append([to_cs(max(dur_ms, 1.0)), ch])
        # 最小可见时长平滑：1cs 闪烁字向后方借 3cs（\kf 总和不变，时间轴不漂移）
        for i in range(len(pairs) - 1):
            if pairs[i][0] <= 1:
                j = i + 1
                while j < len(pairs) and pairs[j][0] - 3 < 2:
                    j += 1
                if j < len(pairs):
                    pairs[i][0] += 3
                    pairs[j][0] -= 3
        stats["min_char_cs"] = min([p[0] for p in pairs] or [0])
        parts = ["{\\kf%d}%s" % (cs, ch) for cs, ch in pairs]
        for cs, _ in pairs:
            stats["max_char_cs"] = max(stats["max_char_cs"], cs)
        total_cs = sum(cs for cs, _ in pairs)
        stats["kf_sum_drift_cs"] = max(stats["kf_sum_drift_cs"], abs(total_cs - to_cs(cue["end"] - cue["start"])))
        body.append("Dialogue: 0,%s,%s,Default,,0,0,0,,%s" % (fmt_ts(cue["start"]), fmt_ts(cue["end"]), "".join(parts)))
        stats["rendered"] += 1

    header = [
        "[Script Info]",
        "ScriptType: v4.00+",
        "WrapStyle: 2",
        "ScaledBorderAndShadow: yes",
        f"PlayResX: {style.get('play_res_x', 1080)}",
        f"PlayResY: {style.get('play_res_y', 1920)}",
        "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, "
        "Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
        "Alignment, MarginL, MarginR, MarginV, Encoding",
        "Style: Default,{font},{size},{primary},{secondary},{outline},{back},0,0,0,0,100,100,0,0,"
        "{bs},{ol},{sh},{al},{ml},{mr},{mv},1".format(
            font=style.get("font_name", "PingFang SC"),
            size=style.get("font_size", 36),
            primary=style.get("primary_colour", "&H0000D7FF"),
            secondary=style.get("secondary_colour", "&H00FFFFFF"),
            outline=style.get("outline_colour", "&H00000000"),
            back=style.get("back_colour", "&H00000000"),
            bs=style.get("border_style", 3),
            ol=style.get("outline", 2),
            sh=style.get("shadow", 1),
            al=style.get("alignment", 2),
            ml=style.get("margin_l", 30),
            mr=style.get("margin_r", 30),
            mv=style.get("margin_v", 150),
        ),
        "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]
    return header + body, stats


def main():
    ap = argparse.ArgumentParser(description="整句 SRT + DTW 时间轴 -> 逐字卡拉OK ASS")
    ap.add_argument("--srt", required=True)
    ap.add_argument("--dtw", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--config", default="config/karaoke.json")
    args = ap.parse_args()

    global ROOT
    cfg = load_cfg(args.config)
    if cfg:
        ROOT = os.path.dirname(os.path.dirname(os.path.abspath(args.config))) or ROOT
    srt = resolve(args.srt)
    dtw = resolve(args.dtw)
    out = resolve(args.out)

    if not os.path.isfile(srt):
        print(f"错误：找不到 SRT：{srt}", file=sys.stderr)
        return 1
    if not os.path.isfile(dtw):
        print(f"错误：找不到 DTW JSON：{dtw}", file=sys.stderr)
        return 1

    cues = parse_srt(srt)
    if not cues:
        print(f"错误：SRT 无可解析句：{srt}", file=sys.stderr)
        return 1
    dchars = parse_dtw(dtw)
    if not dchars:
        print(f"错误：DTW JSON 无逐字时间轴：{dtw}", file=sys.stderr)
        return 1

    gate = cfg.get("gate") or {}
    strict = bool(gate.get("strict_text_match", True))
    floor = float(gate.get("min_cue_ratio", 0.6) or 0.6)
    lines, stats = assemble(cues, dchars, cfg, strict=strict, min_ratio=floor)
    if lines is None:
        print("FAIL 文本栅栏未过（SRT 与 DTW 差异超阈），按回退策略处理：", file=sys.stderr)
        for mm in stats["mismatch"][:5]:
            print(f"  cue{mm['cue']} ratio={mm['ratio']} srt={mm['srt'][:40]} dtw={mm['dtw'][:40]}", file=sys.stderr)
        return 2

    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    rep = os.path.splitext(out)[0] + ".report.json"
    with open(rep, "w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)
    print(f"逐字卡拉OK ASS 已写出：{out}")
    n_soft = len(stats["mismatch"])
    gate_txt = "全等" if n_soft == 0 else f"{n_soft} 句让步（已按 DTW 匹配块+句内均分回填）"
    print(f"  句数 {stats['rendered']}/{stats['cues']}，DTW 逐字 {stats['dtw_chars']}，最长单字 {stats['max_char_cs'] / 100:.2f}s，文本栅栏 {gate_txt}")
    print(f"  报告：{rep}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
