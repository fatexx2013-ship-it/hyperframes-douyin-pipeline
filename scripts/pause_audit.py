#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""pause_audit.py —— KB-A6 无意义停顿检测（v1.13.0）

口径（本机 /Volumes/PSSD/抖音视频 竖屏产线）：
  "无意义停顿" = 相邻两句之间出现 ≥ 阈值（默认 1.20s）的空档，且该空档**未**在
  script.json 的节奏声明里被显式声明为有意停顿。

两层证据：
  ① 时间轴层（主判据）：读 script.json 的 scenes[].lines[]（build_audio.py 回填后的
     start/end，单位秒），计算相邻句 gap = next.start - cur.end；凡 gap ≥ 阈值即候选。
  ② 音频层（交叉验证，尽力而为）：ffmpeg silencedetect 扫 audio_combined.wav，
     取实际静音区间；把候选 gap 与静音区间对齐（±0.15s），确认"真静音"还是
     "仅是字幕空档"。音频缺失 / ffmpeg 不可用时降级，只在报告中标记 layer2=skipped。

有意停顿的声明方式（任一即视为"有意义"，不计入问题项）：
  * 该句 line 含 "beat"（A1 节奏字段，int ≥ 1）；或
  * script.json 顶层/场景级 "pause_allow"（bool）为真；或
  * 该 gap 出现在场景分界（场景切换处的结构停顿）；或
  * --allow-gap 显式指定的句序号（可重复）。

只读检查，不改任何源；默认 advisory，--strict 时检出问题 = rc=2。

用法：
  python3 scripts/pause_audit.py story/<name> [--threshold 1.20] [--json OUT]
          [--allow-gap 3] [--strict] [--quiet]
"""
import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _ts() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _which(name: str) -> str:
    """解析可执行文件：先 PATH，再 macOS 常见安装位（Homebrew arm64/x86、MacPorts）。"""
    import shutil as _sh
    hit = _sh.which(name)
    if hit:
        return hit
    for d in ("/opt/homebrew/bin", "/usr/local/bin", "/opt/local/bin", "/usr/bin"):
        cand = os.path.join(d, name)
        if os.path.isfile(cand) and os.access(cand, os.X_OK):
            return cand
    return name


def _silences(wav: str, noise="-35dB", dur=0.5):
    if not os.path.isfile(wav):
        return None, "audio_combined.wav 缺失"
    try:
        p = subprocess.run([_which("ffmpeg"), "-hide_banner", "-nostats", "-i", wav,
                            "-af", f"silencedetect=noise={noise}:d={dur}",
                            "-f", "null", "-"],
                           capture_output=True, text=True, timeout=600)
    except (OSError, subprocess.SubprocessError) as exc:
        return None, f"ffmpeg 调用失败: {exc}"
    segs, cur = [], {}
    for m in re.finditer(r"silence_start: ([\d.]+)", p.stderr):
        cur = {"start": float(m.group(1))}
    for m in re.finditer(r"silence_end: ([\d.]+) \| silence_duration: ([\d.]+)",
                         p.stderr):
        s = cur.get("start")
        if s is not None:
            segs.append({"start": round(s, 3), "end": round(float(m.group(1)), 3),
                         "duration": round(float(m.group(2)), 3)})
    return segs, None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("story")
    ap.add_argument("--threshold", type=float, default=1.20,
                    help="空档判定阈值（秒），默认 1.20（与 A1 rhythm 默认 gap 一致）")
    ap.add_argument("--json", default=None)
    ap.add_argument("--allow-gap", type=int, action="append", default=[],
                    help="显式豁免的句序号（0-based，可重复）")
    ap.add_argument("--strict", action="store_true")
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args()

    sd = a.story if os.path.isabs(a.story) else (
        os.path.join(ROOT, "story", a.story)
        if os.path.isdir(os.path.join(ROOT, "story", a.story))
        else os.path.join(ROOT, a.story))
    name = os.path.basename(sd.rstrip("/"))
    sp = os.path.join(sd, "script.json")
    out_path = a.json or os.path.join(sd, "qc", "pause_audit.json")
    if not os.path.isfile(sp):
        print(f"[pause] 编排器侧故障：缺 {sp}", file=sys.stderr)
        return 1
    try:
        script = json.loads(open(sp, encoding="utf-8").read())
    except (OSError, ValueError) as exc:
        print(f"[pause] 编排器侧故障：script.json 不可解析 —— {exc}", file=sys.stderr)
        return 1

    # 展开逐句时间轴。真源口径（2026-10-08 校准）：
    #   * build_audio.py 回填的是**扁平** script["lines"] = [{scene_index, text,
    #     start, end, beat, enter_scale}]（timing.json 同款），场景侧只写
    #     scenes[i]._start/_end —— 因此扁平 lines[] 是首选；
    #   * 未 build 的骨架（scenes[].lines[]）没有 start/end，按"未回填"如实报错，
    #     绝不猜测时间。
    idx, lines = 0, []
    allow_scene_pause = bool(script.get("pause_allow"))
    for sc in script.get("scenes") or []:
        if bool(sc.get("pause_allow")) or bool((sc.get("card") or {}).get("pause_allow")):
            allow_scene_pause = True
    flat = script.get("lines") or []
    if flat:
        for i, ln in enumerate(flat):
            lines.append({"i": i, "scene": int(ln.get("scene_index", 0)),
                          "text": str(ln.get("text", "")),
                          "start": ln.get("start"), "end": ln.get("end"),
                          "beat": ln.get("beat")})
    else:
        for si, sc in enumerate(script.get("scenes") or []):
            for ln in sc.get("lines") or []:
                lines.append({"i": idx, "scene": si, "text": str(ln.get("text", "")),
                              "start": ln.get("start"), "end": ln.get("end"),
                              "beat": ln.get("beat")})
                idx += 1

    # A1 声明的句间停顿档位（build_audio 落 tts_params.rhythm.gaps）：
    # 实际 gap 命中声明档位（±0.05s）即视为"有意停顿"。
    declared_gaps = []
    ttp = script.get("tts_params") or {}
    raw_gaps = list(((ttp.get("rhythm") or {}).get("gaps") or []))
    for k in ("pause_comma", "pause_period", "pause_paragraph"):
        if ttp.get(k) is not None:
            raw_gaps.append(ttp[k])
    for sc in script.get("scenes") or []:
        for ln in sc.get("lines") or []:
            for k in ("pause_before", "pause_after"):
                if ln.get(k) is not None:
                    raw_gaps.append(ln[k])
    for x in raw_gaps:
        try:
            declared_gaps.append(float(x))
        except (TypeError, ValueError):
            continue
    missing = [l["i"] for l in lines if l["start"] is None or l["end"] is None]
    if missing:
        print(f"[pause] 编排器侧故障：{len(missing)} 句缺回填时间轴（句 {missing[:5]}…）"
              f" —— 先跑 build_audio.py", file=sys.stderr)
        return 1

    # 场景数 ≠ 句数时才存在"真结构分界"；1:1（一行一场景）时场景编号只是
    # 句子的载体，不能拿它当"有意停顿"的挡箭牌。
    multi_scene = len(script.get("scenes") or []) != len(lines)

    findings = []
    for k in range(len(lines) - 1):
        cur, nxt = lines[k], lines[k + 1]
        gap = round(float(nxt["start"]) - float(cur["end"]), 3)
        if gap < a.threshold:
            continue
        reasons = []
        if cur.get("beat"):
            reasons.append(f"前句含 beat={cur['beat']}（A1 节奏声明）")
        if allow_scene_pause:
            reasons.append("script 声明 pause_allow")
        if multi_scene and nxt["scene"] != cur["scene"]:
            reasons.append("场景分界（结构停顿）")
        if k in a.allow_gap or k + 1 in a.allow_gap:
            reasons.append("--allow-gap 显式豁免")
        hit = next((g for g in declared_gaps if abs(g - gap) <= 0.05), None)
        if hit is not None:
            reasons.append(f"命中 A1 声明停顿档位 {hit:.2f}s（rhythm.gaps）")
        findings.append({"after_line": cur["i"], "before_line": nxt["i"],
                         "scene": cur["scene"], "gap": gap,
                         "text_before": cur["text"][-18:], "text_after": nxt["text"][:18],
                         "declared": bool(reasons), "reasons": reasons})

    problems = [f for f in findings if not f["declared"]]
    segs, layer2_err = _silences(os.path.join(sd, "audio_combined.wav"))
    for f in findings:
        f["audio_silence_matched"] = None
        if segs is not None:
            st = float(lines[f["after_line"]]["end"])
            f["audio_silence_matched"] = any(
                abs(s["start"] - st) <= 0.15 and s["duration"] >= a.threshold * 0.8
                for s in segs)

    payload = {
        "check": "pause_audit(KB-A6)",
        "story": name,
        "checked_at": _ts(),
        "threshold_s": a.threshold,
        "line_count": len(lines),
        "candidate_gaps": len(findings),
        "declared_gaps": len(findings) - len(problems),
        "unintended_gaps": len(problems),
        "layer2_audio": {"status": "ok" if segs is not None else "skipped",
                         "error": layer2_err,
                         "silence_segments": len(segs or [])},
        "findings": findings,
        "passed": not problems,
    }
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    open(out_path, "w", encoding="utf-8").write(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n")

    if not a.quiet:
        tag = "✔ 无无意义停顿" if not problems else f"⚠ {len(problems)} 处无意义停顿"
        print(f"[pause/KB-A6] {name}: {tag}（{len(lines)} 句，≥{a.threshold}s 空档 "
              f"{len(findings)} 处，其中已声明 {len(findings) - len(problems)} 处；"
              f"音频层 {'OK' if segs is not None else 'skipped'}）")
        for f in problems:
            print(f"    [gap] 句{f['after_line']}→{f['before_line']} "
                  f"{f['gap']}s（scene {f['scene']}）音频静音匹配="
                  f"{f['audio_silence_matched']}")
        print(f"    报告：{out_path}")
    if problems and a.strict:
        print("[pause] --strict：无意义停顿 = 退出码 2", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
