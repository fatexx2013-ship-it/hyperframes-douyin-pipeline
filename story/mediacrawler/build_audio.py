#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""mediacrawler 视频构建：Qwen3 慵懒御姐配音（G 版·短篇压缩）+ 时间轴回填

G 版口径（短篇压缩版）：
  静音修剪  -52dB / 0.30s（句内上限不变，硬指标口径不动）
  句首留白  0.12s
  段落停顿  1.20s → 0.85s（短台词场景间不需要那么长的气口）
  输出      24000Hz / mono
"""
import os
import sys
import json
import subprocess
import wave

import numpy as np

ROOT = "/Volumes/PSSD/抖音视频"
STORY = os.path.join(ROOT, "story/mediacrawler")
sys.path.insert(0, ROOT)

import generate_qa_video as qa
from append_epilogue import reshape_g

FFMPEG = "/opt/homebrew/bin/ffmpeg"
FFPROBE = "/opt/homebrew/bin/ffprobe"

# G 版停顿表（短篇压缩）
PAUSE_COMMA = 0.25
PAUSE_PERIOD = 0.75
PAUSE_PARAGRAPH = 0.85

# ── 音色单一来源（防逐句漂移）──────────────────────────────
# 历史坑：本链路此前把「每句 emotion」交给 qa.match_emotion() 按关键词自选，
# 而 emotion 直接决定参考音频（EMOTION_REFS 里 6 个 yujie_*.wav 属 6 段不同录音），
# 于是同一支片子会出现多套音色（如 scene 3 命中「必须」→ yujie_serious）。
# 现收敛为单一来源：全片只有 1 个 voice_role + 1 个 emotion，且只由
# script.json 顶层 tts_emotion 指定（缺省 thoughtful = 慵懒御姐音）。
REF_ROLE = "answer"
REF_EMOTION_DEFAULT = "thoughtful"


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

    # ── 音色单一来源解析 + 一致性守卫（防复发）──
    role = script.get("voice_role") or REF_ROLE
    tts_emotion = script.get("tts_emotion") or REF_EMOTION_DEFAULT
    if role != REF_ROLE:
        raise SystemExit(f"voice_role={role!r} 非本链路御姐音角色（应为 {REF_ROLE!r}）——拒绝出片")
    if tts_emotion not in qa.EMOTION_REFS:
        raise SystemExit(f"tts_emotion={tts_emotion!r} 不在可用音色表 {sorted(qa.EMOTION_REFS)} 内")
    epi = script.get("epilogue") or {}
    if epi.get("enabled", True) and (epi.get("emotion") or tts_emotion) != tts_emotion:
        raise SystemExit(
            f"片尾 emotion={epi.get('emotion')!r} 与全片 tts_emotion={tts_emotion!r} 不一致："
            "参考音频不同会导致片尾音色跳变，请统一")
    drift = [(i, sc["lines"][0].get("emotion")) for i, sc in enumerate(scenes)
             if sc["lines"][0].get("emotion") and sc["lines"][0]["emotion"] != tts_emotion]
    if drift:
        raise SystemExit(f"逐句 emotion 与全片音色冲突（会导致漂移）：{drift}")
    ref_audio = os.path.join(qa.QWEN3_DIR, "voices", qa.EMOTION_REFS[tts_emotion]["audio"])
    if not os.path.exists(ref_audio):
        raise SystemExit(f"参考音频缺失：{ref_audio}")
    print(f"[音色] 全片统一 {role} / {tts_emotion} → {os.path.basename(ref_audio)}"
          f"（单一来源 script.json.tts_emotion，逐句 emotion 已禁用）", flush=True)
    print(f"[音色-核验] 9 句将全部使用同一参考音频：{ref_audio}", flush=True)

    line_metas = []
    for i, sc in enumerate(scenes):
        text = sc["lines"][0]["text"]
        raw = os.path.join(STORY, f"line_{i:02d}.raw.wav")
        m24 = os.path.join(STORY, f"line_{i:02d}.24k.wav")
        out = os.path.join(STORY, f"line_{i:02d}.wav")
        print(f"[scene {i}] {text[:34]}...", flush=True)
        print(f"  [emotion: {tts_emotion}] ref={os.path.basename(ref_audio)}", flush=True)
        ok = qa.generate_qwen3_tts(text, raw, role, force_emotion=tts_emotion)
        if not ok:
            raise SystemExit(f"Qwen3-TTS 合成失败（scene {i}）：按规范不得切云端，需先修链路")

        to_24k_mono(raw, m24)
        info = g_reshape(m24, out)
        n_long = trailing_check(out)
        dur = info["dur"]
        line_metas.append({"text": text, "path": out, "duration": round(dur, 3),
                           "voice_start": round(info["voice_start"], 3),
                           "voice_end": round(info["voice_end"], 3),
                           "silence_ge_040s": n_long})
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
    script["tts_emotion"] = tts_emotion
    script["total_duration"] = round(total_voice, 2)
    script["tts_params"] = {
        "version": "G-short", "engine": "Qwen3-TTS-12Hz-1.7B-Base-8bit (local MLX)",
        "ref_voice": f"{os.path.basename(ref_audio)}（慵懒御姐音）",
        "emotion": tts_emotion,
        "voice_role": role,
        "voice_source": "script.json.tts_emotion（全片单一来源，逐句 emotion 已禁用）",
        "voice_guard": "build_audio.py 启动即校验 voice_role / tts_emotion / 片尾 emotion 三者一致，冲突直接拒绝出片",
        "silence_trim": "-52dB / 0.30s（句内上限）",
        "lead_silence": 0.12, "tail_silence": 0.08,
        "pause_comma": PAUSE_COMMA, "pause_period": PAUSE_PERIOD,
        "pause_paragraph": PAUSE_PARAGRAPH,
        "note": "短篇压缩版：段落停顿 1.20s→0.85s，尾静音 0.4s→0.35s",
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
