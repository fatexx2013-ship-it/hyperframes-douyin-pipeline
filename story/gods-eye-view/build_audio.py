#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""gods-eye-view 视频构建：Qwen3 御姐配音 + 时间轴回填
复用 generate_qa_video.py 的 Qwen3-TTS 管线（慵懒玉女御姐音，情绪自动匹配）
"""
import os, sys, json, subprocess

ROOT = os.environ.get("PIPELINE_ROOT") or os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
STORY = os.path.dirname(os.path.abspath(__file__))
MAT = os.path.join(STORY, "materials")
sys.path.insert(0, ROOT)
import generate_qa_video as qa

sys.path.insert(0, os.path.join(ROOT, "scripts"))   # 跨平台适配层真源
import platform_env
FFMPEG = platform_env.require_tool("ffmpeg", purpose="配音转码 / 静音检测")

def trim_silence(src, dst):
    r = subprocess.run([FFMPEG, "-y", "-i", src, "-af",
        "silenceremove=start_periods=1:start_threshold=-45dB:start_silence=0.05,"
        "areverse,silenceremove=start_periods=1:start_threshold=-45dB:start_silence=0.08,areverse",
        dst], capture_output=True)
    return r.returncode == 0

def main():
    script = json.load(open(os.path.join(STORY, "script.json"), encoding="utf-8"))
    scenes = script["scenes"]

    # 1) 逐行 Qwen3 御姐配音
    line_metas = []
    for i, sc in enumerate(scenes):
        text = sc["lines"][0]["text"]
        out = os.path.join(STORY, f"line_{i:02d}.wav")
        print(f"[scene {i}] {text[:30]}...")
        ok = qa.generate_qwen3_tts(text, out, "answer")
        if not ok:
            print(f"  !! Qwen3 失败，Edge 兜底")
            import asyncio
            asyncio.run(qa.generate_edge_tts(text, out, "zh-CN-XiaoxiaoNeural"))
        t = out.replace(".wav", ".t.wav")
        trim_silence(out, t)
        os.replace(t, out)
        dur = qa.get_audio_duration(out)
        line_metas.append({"text": text, "path": out, "duration": round(dur, 2)})
        print(f"  -> {dur:.2f}s")

    # 2) 拼接成完整旁白（句间 0.35s 停顿）
    inputs, filters = [], []
    delay, idx = 0.0, 0
    PAUSE = 0.35
    for lm in line_metas:
        inputs += ["-i", lm["path"]]
        filters.append(f"[{idx}:a]adelay={int(delay*1000)}|{int(delay*1000)}[a{idx}]")
        delay += lm["duration"] + PAUSE
        idx += 1
    total = delay - PAUSE
    mix = "".join(f"[a{i}]" for i in range(idx)) + f"amix=inputs={idx}:duration=longest:normalize=0,"
    filters.append(mix + f"apad=whole_dur={total:.3f},atrim=0:{total:.3f}[out]")
    combined = os.path.join(STORY, "audio_combined.wav")
    subprocess.run([FFMPEG, "-y", *inputs, "-filter_complex", ";".join(filters),
                    "-map", "[out]", combined], capture_output=True)
    print(f"旁白总时长 {total:.2f}s -> {combined}")

    # 3) 回填 script.json 时间轴
    t = 0.0
    flat_lines = []
    for i, (sc, lm) in enumerate(zip(scenes, line_metas)):
        sc["_start"] = round(t, 2)
        sc["_end"] = round(t + lm["duration"], 2)
        flat_lines.append({
            "scene_index": i, "text": lm["text"],
            "start": round(t, 2), "end": round(t + lm["duration"], 2),
        })
        t += lm["duration"] + PAUSE
    script["scenes"] = scenes
    script["lines"] = flat_lines
    script["total_duration"] = round(total, 2)
    json.dump(script, open(os.path.join(STORY, "script.json"), "w"),
              ensure_ascii=False, indent=2)
    json.dump(line_metas, open(os.path.join(STORY, "timing.json"), "w"),
              ensure_ascii=False, indent=2)
    print("时间轴已回填 script.json")

if __name__ == "__main__":
    main()
