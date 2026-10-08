#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""lunatranslator 视频构建：Qwen3 配音（G 版·短篇压缩·单音色锁死）

音色一致性（本次重点）：
  全篇所有场景强制 emotion=thoughtful → 固定参考音频 yujie_thoughtful.wav
  不再使用 match_emotion 自动匹配，避免不同 emotion 的参考音色混用。
  片尾 emotion 亦在 script.json 中设为 thoughtful，与正片同一参考音频。
"""
import os
import sys
import json
import subprocess
import wave

import numpy as np

ROOT = os.environ.get("PIPELINE_ROOT") or os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
STORY = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

import generate_qa_video as qa
from append_epilogue import reshape_g

sys.path.insert(0, os.path.join(ROOT, "scripts"))   # 跨平台适配层真源
import platform_env
FFMPEG = platform_env.require_tool("ffmpeg", purpose="配音转码 / 静音检测")
FFPROBE = platform_env.require_tool("ffprobe", purpose="配音时长探测")

# 单音色锁死：全篇只用慵懒御姐 thoughtful
LOCK_EMOTION = "thoughtful"

PAUSE_PARAGRAPH = 0.85


def to_24k_mono(src, dst):
    subprocess.run([FFMPEG, "-y", "-v", "error", "-i", src, "-ar", "24000", "-ac", "1",
                    "-c:a", "pcm_s16le", dst], check=True)
    return dst


def g_reshape(src, dst, lead_s=0.12, cap_s=0.30, thr_db=-52.0):
    info = reshape_g(src, dst, lead_s=lead_s, cap_s=cap_s, thr_db=thr_db)
    return info


def trailing_check(path):
    r = subprocess.run([FFMPEG, "-v", "error", "-i", path, "-af",
                        "silencedetect=noise=-52dB:d=0.40", "-f", "null", "-"],
                       capture_output=True, text=True)
    n = r.stderr.count("silence_duration")
    return n


def main():
    script = json.load(open(os.path.join(STORY, "script.json"), encoding="utf-8"))
    scenes = script["scenes"]

    # 断言：script.json 里所有 emotion（含片尾）必须与锁死值一致
    for i, sc in enumerate(scenes):
        e = sc["lines"][0].get("emotion")
        assert e in (None, LOCK_EMOTION), f"scene {i} emotion={e} 与单音色锁 {LOCK_EMOTION} 冲突"
    ep = script.get("epilogue", {})
    assert ep.get("emotion") == LOCK_EMOTION, f"片尾 emotion={ep.get('emotion')} 必须为 {LOCK_EMOTION}"
    print(f"单音色锁死：全篇 {LOCK_EMOTION} -> {qa.EMOTION_REFS[LOCK_EMOTION]['audio']}")

    line_metas = []
    for i, sc in enumerate(scenes):
        text = sc["lines"][0]["text"]
        raw = os.path.join(STORY, f"line_{i:02d}.raw.wav")
        m24 = os.path.join(STORY, f"line_{i:02d}.24k.wav")
        out = os.path.join(STORY, f"line_{i:02d}.wav")
        print(f"[scene {i}] {text[:34]}...", flush=True)
        ok = qa.generate_qwen3_tts(text, raw, "answer", force_emotion=LOCK_EMOTION)
        if not ok:
            raise SystemExit(f"Qwen3-TTS 合成失败（scene {i}）：按规范不得切云端，需先修链路")

        to_24k_mono(raw, m24)
        info = g_reshape(m24, out)
        n_long = trailing_check(out)
        dur = info["dur"]
        line_metas.append({"text": text, "path": out, "duration": round(dur, 3),
                           "voice_start": round(info["voice_start"], 3),
                           "voice_end": round(info["voice_end"], 3),
                           "silence_ge_040s": n_long,
                           "ref_audio": qa.EMOTION_REFS[LOCK_EMOTION]["audio"]})
        print(f"  -> {dur:.3f}s  句内静音≥0.40s: {n_long}", flush=True)

    ws = [wave.open(lm["path"], "rb") for lm in line_metas]
    sr = ws[0].getframerate()
    for w in ws:
        assert w.getframerate() == sr and w.getnchannels() == 1, "G 版要求统一的 24k mono 素材"
    frames = [np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32)
              for w in ws]
    for w in ws:
        w.close()

    chunks, starts, t = [], [], 0.0
    for k, fr in enumerate(frames):
        starts.append(t)
        chunks.append(fr)
        t += len(fr) / sr
        if k != len(frames) - 1:
            chunks.append(np.zeros(int(PAUSE_PARAGRAPH * sr), dtype=np.float32))
            t += PAUSE_PARAGRAPH
    total_voice = t

    chunks.append(np.zeros(int(0.35 * sr), dtype=np.float32))
    y = np.clip(np.concatenate(chunks), -32768, 32767).astype(np.int16)

    combined = os.path.join(STORY, "audio_combined.wav")
    with wave.open(combined, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr)
        w.writeframes(y.tobytes())
    with wave.open(os.path.join(STORY, "narration.wav"), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr)
        w.writeframes(y.tobytes())

    print(f"旁白总时长 {total_voice:.2f}s -> {combined}")

    flat_lines = []
    for i, (sc, lm, st) in enumerate(zip(scenes, line_metas, starts)):
        sc["_start"] = round(st, 2)
        sc["_end"] = round(st + lm["duration"], 2)
        flat_lines.append({"scene_index": i, "text": lm["text"],
                           "start": round(st, 2), "end": round(st + lm["duration"], 2)})
    script["scenes"] = scenes
    script["lines"] = flat_lines
    script["total_duration"] = round(total_voice, 2)
    script["tts_params"] = {
        "version": "G-short-monovoice", "engine": "Qwen3-TTS-12Hz-1.7B-Base-8bit (local MLX)",
        "ref_voice": "yujie_thoughtful.wav（慵懒御姐音 · 全篇单音色锁死）",
        "voice_lock": LOCK_EMOTION,
        "silence_trim": "-52dB / 0.30s（句内上限）",
        "lead_silence": 0.12, "tail_silence": 0.08,
        "pause_paragraph": PAUSE_PARAGRAPH,
        "note": "短篇压缩 + 单音色锁死：全篇强制 thoughtful，含片尾，杜绝音色混杂",
        "sample_rate": sr, "channels": 1,
        "silence_ge_040s_total": sum(lm["silence_ge_040s"] for lm in line_metas),
    }
    json.dump(script, open(os.path.join(STORY, "script.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    json.dump(line_metas, open(os.path.join(STORY, "timing.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    print("时间轴已回填 script.json")

    bad = [lm for lm in line_metas if lm["silence_ge_040s"] > 0]
    if bad:
        print(f"!! 硬指标不达标：{len(bad)} 条素材存在句内静音 ≥0.40s")
        for lm in bad:
            print("   ", os.path.basename(lm["path"]), lm["silence_ge_040s"])
    else:
        print("硬指标通过：句内静音 ≥0.40s 档位 = 0")


if __name__ == "__main__":
    main()
