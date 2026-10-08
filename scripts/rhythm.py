#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""rhythm.py — 情感节奏工程化参数（A1，落地自知识库候选 A1）

依据：docs/产线规范.md 「节奏层（v1.13.0，A1 情感节奏参数化）」
定位：story 层**节奏参数的唯一解析入口**。把「停顿/节奏」从脚本硬编码常量
      升级为 script.json 可覆盖的参数，供 build_audio.py（停顿定位）与
      build_html.py（入场速度）共享同一份解析结果，避免两处各写一套。

字段（全部可选；缺省即回到 G 版原常量，默认链路逐字节等价）
------------------------------------------------------------------
  scenes[i].beat            1–5   情绪强度（默认 3）
                                  1=冷静陈述 2=平缓 3=常态 4=推进 5=爆发
  scenes[i].lines[j].beat   同上（行级优先于场景级）
  scenes[i].pause_before    float 秒，本场景（行）前额外停顿（默认 0）
  scenes[i].pause_after     float 秒，本场景（行）后额外停顿（默认 0）
  scenes[i].gap_after       float 秒，直接指定与下一场景的基础间隔
                                  （默认 = 段落停顿 1.20s；给了就用它替基础值）
  scenes[i].lines[j].pause_before / pause_after  行级同上

解析口径（可追溯；改动须同步 docs/产线规范.md 版本号）
------------------------------------------------------
  · 句间基础停顿按**前一句末标点**取值：逗号 0.25s / 句末 0.75s / 省略号·破折号 1.00s；
  · 场景（段落）之间基础停顿 = 1.20s（G 版 PAUSE_PARAGRAPH），除非给了 gap_after；
  · 最终停顿 = 基础值 + 前项 pause_after + 后项 pause_before；
  · 结果统一夹到 [0.10, 3.00]s，越界只夹不报错但会在 validate 里记为 WARN；
  · 入场时长倍率 = 1.25/1.12/1.00/0.90/0.80（beat 1→5，越高越快），只作用于
    build_html.py 的入场动画时长，不改变 lines 时间轴（时间轴只由音频决定）。

退出码
------
  0 解析成功（validate 无 FAIL） / 1 用法或输入错误 / 2 validate 检出 FAIL

用法
----
  python3 scripts/rhythm.py story/<name>                 # 打印节奏表
  python3 scripts/rhythm.py story/<name> --json out.json # 落盘解析结果
  python3 scripts/rhythm.py story/<name> --validate      # 只做参数体检
"""
from __future__ import annotations

import argparse
import json
import os
import sys

EXIT_OK = 0
EXIT_USAGE = 1
EXIT_DETECT = 2

DEFAULT_BEAT = 3
BEAT_RANGE = (1, 5)
# 入场速度倍率：beat 越高 → 入场越快（时长 ×倍率）
BEAT_ENTER_SCALE = {1: 1.25, 2: 1.12, 3: 1.00, 4: 0.90, 5: 0.80}

# 与原 G 版停顿表一致的常量（build_audio.py 直接引用本模块，避免双份真源）
PAUSE_COMMA = 0.25
PAUSE_PERIOD = 0.75
PAUSE_ELLIPSIS = 1.00
PAUSE_PARAGRAPH = 1.20
PAUSE_CLAMP = (0.10, 3.00)

PERIOD_CHARS = "。！？!?"
ELLIPSIS_CHARS = "…—"
COMMA_CHARS = "，,、；;"


def load(path: str) -> dict:
    if os.path.isdir(path):
        path = os.path.join(path, "script.json")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _num(v):
    if isinstance(v, bool) or v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        try:
            return float(v.strip())
        except ValueError:
            return None
    return None


def beat_of(scene: dict, line: dict | None = None) -> int:
    for src in (line or {}, scene or {}):
        b = _num(src.get("beat"))
        if b is not None:
            return int(b)
    return DEFAULT_BEAT


def enter_scale(scene: dict, line: dict | None = None) -> float:
    return BEAT_ENTER_SCALE.get(beat_of(scene, line), 1.00)


def pause_for_punct(text: str) -> float:
    """按句末标点取基础停顿（与 G 版表一致）。"""
    t = (text or "").rstrip()
    while t and t[-1] in "”\"'）)】]":
        t = t[:-1]
    if not t:
        return PAUSE_PERIOD
    c = t[-1]
    if c in PERIOD_CHARS:
        return PAUSE_PERIOD
    if c in ELLIPSIS_CHARS:
        return PAUSE_ELLIPSIS
    if c in COMMA_CHARS:
        return PAUSE_COMMA
    return PAUSE_PERIOD


def _ov(scene: dict, line: dict | None, key: str):
    for src in (line or {}, scene or {}):
        v = _num(src.get(key))
        if v is not None:
            return v
    return 0.0


def _clamp(gap: float):
    lo, hi = PAUSE_CLAMP
    if gap < lo:
        return lo, f"停顿 {gap:.2f}s < 下限 {lo}s，已夹到下界"
    if gap > hi:
        return hi, f"停顿 {gap:.2f}s > 上限 {hi}s，已夹到上界"
    return gap, None


def _pairs(script: dict):
    """展开为 (scene_i, line_j, scene, line) 序列；scene.lines 为空时也占一个占位节点。"""
    out = []
    for i, sc in enumerate(script.get("scenes", []) or []):
        lns = sc.get("lines") or [None]
        for j, ln in enumerate(lns):
            out.append((i, j, sc, ln))
    return out


def resolve(script: dict) -> dict:
    """解析全篇节奏：返回 segments（每行）+ gaps（相邻行之间的有效停顿）。"""
    seq = _pairs(script)
    segments, notes = [], []
    for i, j, sc, ln in seq:
        text = (ln or {}).get("text", "") if isinstance(ln, dict) else ""
        if not text:
            text = ((sc.get("lines") or [{}])[0] or {}).get("text", "") if sc else ""
        segments.append({
            "scene_index": i,
            "line_index": j,
            "text": text,
            "beat": beat_of(sc, ln),
            "enter_scale": enter_scale(sc, ln),
            "pause_before_extra": _ov(sc, ln, "pause_before"),
            "pause_after_extra": _ov(sc, ln, "pause_after"),
            "punct_base": pause_for_punct(text),
        })

    gaps = []
    for k in range(len(seq) - 1):
        i, j, sc, ln = seq[k]
        ni, nj, nsc, nln = seq[k + 1]
        same_scene = (i == ni)
        if same_scene:
            base = segments[k]["punct_base"]
            base_src = f"句末标点（{base:.2f}s）"
            gap_after = _num(sc.get("gap_after"))
        else:
            gap_after = _num(sc.get("gap_after"))
            base = gap_after if gap_after is not None else PAUSE_PARAGRAPH
            base_src = ("gap_after 指定" if gap_after is not None else "段落停顿 1.20s")
        gap = base + segments[k]["pause_after_extra"] + segments[k + 1]["pause_before_extra"]
        gap, clamp_note = _clamp(gap)
        if clamp_note:
            notes.append(f"segment#{k}→#{k + 1}: {clamp_note}")
        gaps.append({
            "from": k, "to": k + 1,
            "from_scene": i, "to_scene": ni,
            "within_scene": same_scene,
            "base": round(base, 3), "base_source": base_src,
            "pause_after_extra": segments[k]["pause_after_extra"],
            "pause_before_extra": segments[k + 1]["pause_before_extra"],
            "gap": round(gap, 3),
        })

    return {
        "schema": "rhythm/v1",
        "defaults": {"beat": DEFAULT_BEAT, "enter_scale": 1.0,
                     "pause_comma": PAUSE_COMMA, "pause_period": PAUSE_PERIOD,
                     "pause_ellipsis": PAUSE_ELLIPSIS, "pause_paragraph": PAUSE_PARAGRAPH,
                     "pause_clamp": list(PAUSE_CLAMP)},
        "beat_enter_scale": {str(k): v for k, v in BEAT_ENTER_SCALE.items()},
        "segments": segments,
        "gaps": gaps,
        "notes": notes,
        "has_overrides": any(
            s["beat"] != DEFAULT_BEAT or s["pause_before_extra"] or s["pause_after_extra"]
            for s in segments
        ) or any(_num((sc or {}).get("gap_after")) is not None
                 for _, _, sc, _ in seq),
    }


def gap_for(script_or_resolved: dict, index: int, default=PAUSE_PARAGRAPH) -> float:
    """给 build_audio.py 的便捷口：第 index 个 segment 与其后一个 segment 的有效停顿。
    无 overrides 时返回值 == default（保证默认链路等价）。"""
    r = script_or_resolved if script_or_resolved.get("schema") == "rhythm/v1" \
        else resolve(script_or_resolved)
    for g in r["gaps"]:
        if g["from"] == index:
            return g["gap"]
    return default


def scene_enter_scales(script: dict) -> dict:
    """场景序号 → 入场时长倍率（一个场景多行时取首行 beat）。无字段时全为 1.0。"""
    out = {}
    for s in resolve(script)["segments"]:
        out.setdefault(s["scene_index"], s["enter_scale"])
    return out


def validate(script: dict) -> list:
    issues = []

    def add(level, iid, detail):
        issues.append({"level": level, "id": iid, "detail": detail})

    scenes = script.get("scenes", []) or []
    if not scenes:
        add("SKIP", "R0", "script.json 无 scenes：节奏层不适用")
        return issues
    checked_beat = checked_pause = 0
    for i, sc in enumerate(scenes):
        for j, ln in enumerate((sc.get("lines") or [None])):
            for src_name, src in (("scene", sc), ("line", ln or {})):
                if not isinstance(src, dict):
                    continue
                if "beat" in src:
                    b = _num(src["beat"])
                    checked_beat += 1
                    if b is None:
                        add("FAIL", "R1", f"scenes[{i}] {src_name}.beat 非数值：{src['beat']!r}")
                    elif not (BEAT_RANGE[0] <= b <= BEAT_RANGE[1]):
                        add("FAIL", "R1",
                            f"scenes[{i}] {src_name}.beat={b} 越界（须 {BEAT_RANGE[0]}–{BEAT_RANGE[1]}）")
                    elif float(b) != int(b):
                        add("WARN", "R1", f"scenes[{i}] {src_name}.beat={b} 非整数，已按 {int(b)} 处理")
                for key in ("pause_before", "pause_after", "gap_after"):
                    if key in src:
                        v = _num(src[key])
                        checked_pause += 1
                        if v is None:
                            add("FAIL", "R2", f"scenes[{i}] {src_name}.{key} 非数值：{src[key]!r}")
                        elif v < 0:
                            add("FAIL", "R2", f"scenes[{i}] {src_name}.{key}={v} 为负")
                        elif v > PAUSE_CLAMP[1]:
                            add("WARN", "R2",
                                f"scenes[{i}] {src_name}.{key}={v} > 上限 {PAUSE_CLAMP[1]}s，将夹到上界")
            if isinstance(ln, dict) and not (ln.get("text") or "").strip():
                add("WARN", "R3", f"scenes[{i}].lines[{j}] 文本为空：停顿只能按默认段末口径取值")
    r = resolve(script)
    for n in r["notes"]:
        add("WARN", "R4", n)
    beats = [s["beat"] for s in r["segments"]]
    if len(beats) >= 4 and len(set(beats)) == 1 and checked_beat:
        add("WARN", "R5", f"全篇 beat 恒为 {beats[0]}：节奏无起伏（显式声明了 beat 却全程一致）")
    for k in range(len(beats) - 1):
        if abs(beats[k] - beats[k + 1]) >= 3:
            add("WARN", "R6",
                f"segment#{k}→#{k + 1} beat 跳变 {beats[k]}→{beats[k + 1]}（跨度 ≥3，观感易断裂）")
    return issues


def print_table(script: dict, r: dict, issues: list) -> None:
    segs = r["segments"]
    print(f"[rhythm] segments={len(segs)} overrides={'yes' if r['has_overrides'] else 'no'}")
    print("  #  场景  beat  入场倍率  前置+  后置+  句末基础  与下一段停顿  文案")
    for k, s in enumerate(segs):
        g = next((x for x in r["gaps"] if x["from"] == k), None)
        gtxt = f"{g['gap']:.2f}s({g['base_source']})" if g else "—"
        print(f"  {k:<3}{s['scene_index']:<5}{s['beat']:<6}{s['enter_scale']:<10}"
              f"{s['pause_before_extra']:<7.2f}{s['pause_after_extra']:<7.2f}"
              f"{s['punct_base']:<10.2f}{gtxt:<24}{s['text'][:22]}")
    if issues:
        print("  参数体检：")
        for it in issues:
            print(f"    [{it['level']}] {it['id']} {it['detail']}")
    else:
        print("  参数体检：无问题")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        prog="rhythm",
        description="情感节奏参数解析（A1）。退出码 0=成功，1=用法错误，2=参数体检 FAIL")
    ap.add_argument("target", help="story 目录或 script.json")
    ap.add_argument("--json", dest="json_out", default=None, help="落盘解析结果 JSON")
    ap.add_argument("--validate", action="store_true", help="只做参数体检（仍打印节奏表）")
    args = ap.parse_args(argv)

    path = args.target
    if os.path.isdir(path):
        path = os.path.join(path, "script.json")
    if not os.path.isfile(path):
        print(f"[rhythm] 用法/输入错误：找不到 {path}", file=sys.stderr)
        return EXIT_USAGE
    try:
        script = load(path)
    except (OSError, ValueError) as exc:
        print(f"[rhythm] 用法/输入错误：script.json 解析失败 {exc}", file=sys.stderr)
        return EXIT_USAGE

    r = resolve(script)
    issues = validate(script)
    print_table(script, r, issues)
    if args.json_out:
        payload = dict(r)
        payload["issues"] = issues
        payload["script_path"] = os.path.abspath(path)
        with open(args.json_out, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        print(f"  解析结果落盘：{args.json_out}")
    return EXIT_DETECT if any(i["level"] == "FAIL" for i in issues) else EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
