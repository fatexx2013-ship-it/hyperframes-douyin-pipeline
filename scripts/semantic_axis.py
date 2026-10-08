#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""semantic_axis.py —— KB-A4 三轴质控之「语义轴」（v1.13.0）

背景：既有两段门禁覆盖
  * 段1 渲染前门禁（design_ai_gate）：设计/规格轴
  * 段2 渲染后门禁（frame_audit）：解码轴 + 感知轴（画面能不能解出、观感是否达标）
缺一条**语义轴**：成片实际说的是不是稿子上的话（漏读/串词/离稿/额外内容）。
本脚本用本机离线 ASR（whisper.cpp ggml-small）对成片音轨做回读，与 script.json
逐句时间轴对齐后算文本相似度，落盘 qc/semantic_axis.json。

口径：
  * 相似度 = difflib.SequenceMatcher 在归一化（仅保留中日韩文字 + 字母数字）后的
    比率；阈值默认 0.55（低于即判该句"离稿"）。
  * 额外内容：ASR 段落在时间上不落入任何 script 句 → 记为 extra_segments（可能
    是占位符泄漏、意外画外音、或 ASR 把停顿补成语气词）。
  * 只读：不修改音轨/字幕/script.json；默认 advisory，--strict 时问题项 = rc=2。

退出码：0 通过（或 advisory 有告警）/ 1 编排器侧故障 / 2 --strict 检出问题。

用法：
  python3 scripts/semantic_axis.py story/<name> [--model models/ggml-small.bin]
          [--threshold 0.55] [--json OUT] [--strict] [--quiet]
"""
import argparse
import difflib
import json
import os
import re
import subprocess
import sys
import tempfile
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 跨平台适配层（真源 scripts/platform_env.py）：工具按 PATH/which + 平台常见位解析，
# 支持环境变量覆盖（PIPELINE_<TOOL> / <TOOL>）。
_SDIR = os.path.dirname(os.path.abspath(__file__))
if _SDIR not in sys.path:
    sys.path.insert(0, _SDIR)
import platform_env  # noqa: E402


def _which(name: str) -> str:
    """解析可执行文件：环境变量 → PATH → 平台常见安装位（跨平台，见 platform_env）。"""
    return platform_env.find_tool(name) or name


# whisper.cpp 可执行：PATH/平台常见位解析（环境变量 PIPELINE_WHISPER_CLI / WHISPER_CLI 可覆盖）
WHISPER = platform_env.find_tool("whisper-cli") or ""
KEEP = re.compile(r"[\u3400-\u9fff\uf900-\ufaffA-Za-z0-9]+")


def _ts() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def norm(s: str) -> str:
    return "".join(KEEP.findall(str(s or "")))


def sim(a: str, b: str) -> float:
    x, y = norm(a), norm(b)
    if not x and not y:
        return 1.0
    if not x or not y:
        return 0.0
    return round(difflib.SequenceMatcher(None, x, y).ratio(), 4)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("story")
    ap.add_argument("--model", default=os.path.join(ROOT, "models", "ggml-small.bin"))
    ap.add_argument("--threshold", type=float, default=0.55)
    ap.add_argument("--json", default=None)
    ap.add_argument("--strict", action="store_true")
    ap.add_argument("--quiet", action="store_true")
    ap.add_argument("--keep-wav", action="store_true",
                    help="保留 16k 单声道中间音轨（默认清理）")
    a = ap.parse_args()

    sd = a.story if os.path.isabs(a.story) else (
        os.path.join(ROOT, "story", a.story)
        if os.path.isdir(os.path.join(ROOT, "story", a.story))
        else os.path.join(ROOT, a.story))
    name = os.path.basename(sd.rstrip("/"))
    sp = os.path.join(sd, "script.json")
    out_path = a.json or os.path.join(sd, "qc", "semantic_axis.json")
    audio = os.path.join(sd, "audio_combined.wav")
    if not os.path.isfile(sp) or not os.path.isfile(audio):
        print(f"[semantic] 编排器侧故障：缺 {sp} 或 {audio}", file=sys.stderr)
        return 1
    if not WHISPER or not os.path.isfile(WHISPER):
        print(f"[semantic] 编排器侧故障：找不到 ASR 可执行 whisper-cli（当前解析值 {WHISPER or '未找到'}）。\n"
              f"  修复：安装 whisper.cpp 并确保 whisper-cli 在 PATH，或 export "
              f"PIPELINE_WHISPER_CLI=/绝对/路径/whisper-cli（Windows 为 whisper-cli.exe）；\n"
              f"  自检：python3 scripts/doctor.py", file=sys.stderr)
        return 1
    if not os.path.isfile(a.model):
        print(f"[semantic] 编排器侧故障：缺 ASR 模型 {a.model}", file=sys.stderr)
        return 1
    script = json.loads(open(sp, encoding="utf-8").read())

    tmp = tempfile.mkdtemp(prefix="semantic_axis_", dir=os.path.join(sd, "qc"))
    wav16 = os.path.join(tmp, "a16k.wav")
    if subprocess.run([_which("ffmpeg"), "-hide_banner", "-loglevel", "error", "-y", "-i",
                       audio, "-ac", "1", "-ar", "16000", wav16]).returncode != 0:
        print("[semantic] 编排器侧故障：ffmpeg 转 16k 单声道失败", file=sys.stderr)
        return 1

    pref = os.path.join(tmp, "asr")
    cmd = [WHISPER, "-m", a.model, "-f", wav16, "-l", "zh", "-oj", "-of", pref,
           "-np", "-t", "6"]
    r = subprocess.run(cmd, capture_output=True, text=True)
    jf = pref + ".json"
    if r.returncode != 0 or not os.path.isfile(jf):
        print(f"[semantic] 编排器侧故障：ASR 失败 rc={r.returncode} —— "
              f"{r.stderr.strip()[-300:]}", file=sys.stderr)
        return 1
    raw = json.loads(open(jf, encoding="utf-8").read())
    segs = []
    for s in raw.get("transcription") or []:
        off = s.get("offsets") or {}
        segs.append({"start": round(float(off.get("from", 0)) / 1000.0, 3),
                     "end": round(float(off.get("to", 0)) / 1000.0, 3),
                     "text": str(s.get("text", "")).strip()})

    # 时间轴真源（2026-10-08 校准）：build_audio.py 回填的是**扁平** lines[]
    # [{scene_index, text, start, end}]；未 build 的骨架才退回 scenes[].lines[]。
    lines = []
    flat = script.get("lines") or []
    if flat:
        for i, ln in enumerate(flat):
            lines.append({"scene": int(ln.get("scene_index", 0)),
                          "text": str(ln.get("text", "")),
                          "start": float(ln.get("start") or 0.0),
                          "end": float(ln.get("end") or 0.0)})
    else:
        for si, sc in enumerate(script.get("scenes") or []):
            for ln in sc.get("lines") or []:
                lines.append({"scene": si, "text": str(ln.get("text", "")),
                              "start": float(ln.get("start") or 0.0),
                              "end": float(ln.get("end") or 0.0)})
    if not lines or all(l["end"] <= 0 for l in lines):
        print(f"[semantic] 编排器侧故障：script.json 无可用时间轴（先跑 build_audio.py）",
              file=sys.stderr)
        return 1

    # 归属口径（避免串行污染）：ASR 段 → 按"与各句时间窗的重叠时长最大者"唯一归属，
    # 不再用 ±0.30s 双向命中（那会让段尾/段首被相邻两句同时吸收，制造假"离稿"）。
    used, results = set(), []
    bucket = {i: [] for i in range(len(lines))}
    for k, s in enumerate(segs):
        best, best_ov = None, 0.0
        for i, ln in enumerate(lines):
            ov = min(s["end"], ln["end"]) - max(s["start"], ln["start"])
            if ov > best_ov:
                best, best_ov = i, ov
        if best is None and lines:
            continue
        if best is not None:
            bucket[best].append(k)
            used.add(k)
    for i, ln in enumerate(lines):
        ks = sorted(bucket.get(i, []))
        heard = "".join(segs[k]["text"] for k in ks)
        results.append({"line": i, "scene": ln["scene"], "start": ln["start"],
                        "end": ln["end"], "script": ln["text"], "asr": heard,
                        "similarity": sim(ln["text"], heard)})

    extra = [segs[k] for k in range(len(segs)) if k not in used and norm(segs[k]["text"])]
    worst = sorted([r for r in results if r["similarity"] < a.threshold],
                   key=lambda r: r["similarity"])
    avg = round(sum(r["similarity"] for r in results) / len(results), 4) if results else 0.0
    payload = {
        "check": "semantic_axis(KB-A4)",
        "story": name,
        "checked_at": _ts(),
        "asr": {"engine": "whisper.cpp", "binary": WHISPER, "model": a.model,
                "language": "zh", "segments": len(segs)},
        "threshold": a.threshold,
        "line_count": len(results),
        "avg_similarity": avg,
        "mismatch_count": len(worst),
        "extra_segment_count": len(extra),
        "passed": (not worst) and (not extra),
        "lines": results,
        "mismatches": worst,
        "extra_segments": extra,
    }
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    open(out_path, "w", encoding="utf-8").write(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    if not a.keep_wav:
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)

    if not a.quiet:
        tag = "✔ 语义轴通过" if payload["passed"] else \
              f"⚠ 离稿 {len(worst)} 句 / 额外段 {len(extra)}"
        print(f"[semantic/KB-A4] {name}: {tag}（{len(results)} 句，平均相似度 {avg}，"
              f"ASR {len(segs)} 段）")
        for w in worst[:8]:
            print(f"    [off-script] 句{w['line']} sim={w['similarity']} "
                  f"稿={w['script'][:22]!r} 回读={w['asr'][:22]!r}")
        for e in extra[:5]:
            print(f"    [extra] {e['start']}-{e['end']}s {e['text'][:30]!r}")
        print(f"    报告：{out_path}")
    if not payload["passed"] and a.strict:
        print("[semantic] --strict：语义轴问题 = 退出码 2", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
