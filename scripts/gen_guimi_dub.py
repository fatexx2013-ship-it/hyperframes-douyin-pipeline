#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""《闺蜜反目》情绪测试配音 — 复用 generate_qa_video 的 Qwen3-TTS 管线
林悦 = 御姐音(yujie, 带情绪)；苏苏 = 少女音(shaonv, 单一参考)
输出: <部署根>/output/guimi_dub_test/闺蜜反目-配音测试.mp3
      （部署根默认取仓库根，可用 PIPELINE_ROOT 覆盖）
"""
import os, sys, subprocess, asyncio

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.environ.get("PIPELINE_ROOT") or os.path.dirname(SCRIPT_DIR)   # 跨平台部署根
sys.path.insert(0, ROOT)
sys.path.insert(0, SCRIPT_DIR)
import platform_env
try:
    import generate_qa_video as qa
except ModuleNotFoundError as exc:      # 该模块为历史 Qwen3-TTS 管线，未必随仓库分发
    raise SystemExit(
        f"缺少 generate_qa_video 模块（{exc}）：本脚本为其薄封装，需先把该模块放到 "
        f"PIPELINE_ROOT={ROOT} 或 scripts/ 下；仅 mlx 档（Apple Silicon）适用。"
    )

OUT = os.path.join(ROOT, "output", "guimi_dub_test")
os.makedirs(OUT, exist_ok=True)
FFMPEG = platform_env.require_tool("ffmpeg", purpose="配音静音修剪")

# (文件名, 角色, 强制情绪, 台词, 台词后停顿秒)
LINES = [
    ("01_ly", "answer", "calm",      "苏苏，那笔钱……是你转的吧？", 0.7),
    ("02_ss", "question", None,       "你什么意思？！你怀疑我？！", 0.9),
    ("03_ly", "answer", "thoughtful", "我没怀疑你。我只是……有点失望。", 1.0),
    ("04_ss", "question", None,       "失望？林悦，我跟你五年！五年！你连我都不信？！", 1.2),
    ("05_ly", "answer", "serious",    "那你告诉我，为什么转账记录上的账户名，是你妈的名字？！", 1.4),
    ("06_ss", "question", None,       "……呵。行。既然你都查清楚了，那我也没什么好说的了。", 1.0),
    ("07_ly", "answer", "calm",       "苏苏，我给你最后一次机会。把钱还回来，咱们还能做朋友。", 0.9),
    ("08_ss", "question", None,       "朋友？林悦，从你怀疑我的那一刻起……咱们就不是朋友了。", 0.8),
]

def trim_silence(src, dst):
    """句首句尾静音修剪（同流水线逻辑的轻量版）"""
    r = subprocess.run([FFMPEG, "-y", "-i", src, "-af",
        "silenceremove=start_periods=1:start_threshold=-45dB:start_silence=0.05,"
        "areverse,silenceremove=start_periods=1:start_threshold=-45dB:start_silence=0.08,areverse",
        dst], capture_output=True)
    return r.returncode == 0

def main():
    wavs = []
    for name, role, emo, text, _ in LINES:
        out = os.path.join(OUT, f"{name}.wav")
        print(f"[{name}] role={role} emo={emo} :: {text[:18]}...")
        ok = qa.generate_qwen3_tts(text, out, role, force_emotion=emo)
        if not ok:
            print(f"  !! Qwen3 失败，Edge 兜底")
            asyncio.run(qa.generate_edge_tts(
                text, out, "zh-CN-XiaoyiNeural" if role == "question" else "zh-CN-XiaoxiaoNeural"))
        # 修剪
        t = out.replace(".wav", ".t.wav")
        trim_silence(out, t)
        os.replace(t, out)
        wavs.append(out)
        print(f"  -> {out} ({qa.get_audio_duration(out):.2f}s)")

    # 拼接：每句后按剧本停顿（含 05 后 2 秒沉默）
    inputs, filters = [], []
    delay = 0.0
    idx = 0
    for (name, role, emo, text, pause), w in zip(LINES, wavs):
        d = qa.get_audio_duration(w)
        inputs += ["-i", w]
        filters.append(f"[{idx}:a]adelay={int(delay*1000)}|{int(delay*1000)}[a{idx}]")
        delay += d + pause
        idx += 1
    total = delay
    mix = "".join(f"[a{i}]" for i in range(idx)) + f"amix=inputs={idx}:duration=longest:normalize=0,"
    filters.append(mix + f"apad=whole_dur={total},atrim=0:{total:.3f}[out]")
    combined = os.path.join(OUT, "combined.wav")
    subprocess.run([FFMPEG, "-y", *inputs, "-filter_complex", ";".join(filters),
                    "-map", "[out]", combined], capture_output=True)
    # 转 mp3 便于 IM 传输
    mp3 = os.path.join(OUT, "闺蜜反目-配音测试.mp3")
    subprocess.run([FFMPEG, "-y", "-i", combined, "-codec:a", "libmp3lame", "-b:a", "192k", mp3],
                   capture_output=True)
    print(f"TOTAL {total:.1f}s -> {mp3}")

if __name__ == "__main__":
    main()
