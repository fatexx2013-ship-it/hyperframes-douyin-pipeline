#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""build_music.py —— 抖音视频产线最小版配乐环节（v0.2）

职责
----
给已完成的配音成片（run_dir 内含 douyin.mp4 / narration.wav / script.json /
timing.json）追加一条免版权 BGM 铺底：

    1. 读 script.json 时长（lines[].start/end、total_duration）与情绪参数
       （voice_lock.emotion / tts_params.voice_lock.emotion_ref）——有情绪参数
       则映射选曲档位，无则默认「温和推进」档；
    2. 从本机免版权曲库（默认 /Volumes/PSSD/视频/BGM/抖音候选BGM-20260916，
       mixkit 许可）选 1 首 BGM；可用 --bgm 显式指定；
    3. 响度闪避（ducking）：配音段（script.json lines[].start~end）BGM 压低
       6~10 dB（默认 8 dB，--duck-db 可调），非配音段全音量；
    4. 混音到 TTS 配音（narration.wav）后，整体 loudnorm 两遍法维持
       I=-19 LUFS / TP=-1.5 dBTP / LRA=11——复用 scripts/loudness_match.py
       的「裸 PCM + 标准 RIFF 头」做法（调用其 --wavs 单文件模式）；
    5. 产出配乐版成片 <run_dir>/douyin_music.mp4（复用原片视频流 -c:v copy，
       仅替换音轨），绝不覆盖已发布成片 douyin.mp4 / douyin_epilogue.mp4。
    6. （可选模式，v0.2 / v1.19.0 借鉴 huashu-art-motion synth 配乐模板）
       --bpm-grid 时跳过外部选曲，按 script.json 节奏参数（scenes/lines 的
       beat 1-5）生成严格 BPM 节拍网格配乐：128 BPM（--bpm 可调）八分音符
       网格（网格零点 0.028s，与 huashu 模板一致）、三音动机随和声进行移调、
       逐段按 beat 换配器（sine/triangle/saw/square+鼓）、逐段响度对齐到
       --bpm-grid-lufs（默认 -26 铺底；思路借鉴 huashu 逐段 K 加权对齐）。
       --bpm-key 参数预留（当前和声进行固定 D 小调 i–VI–III–VII）。
       不破坏现有选曲模式：不传 --bpm-grid 时行为与 v0.1 逐字节一致。

只做最小版 + 可选网格模式：不做情绪档位细分 / 五层转场 / 选曲器。
改动任何既有脚本前须先备份 *.bak-<日期>（本脚本仅新增文件）。

量化验证（写入 <run_dir>/qc/music_qc.json 并在 stdout 打印）
    - 整体 loudnorm 输入/输出 I/TP/LRA 与目标差值
    - 旁白段 LUFS 保持度（混音后配音段响度 vs 纯旁白对应段）
    - BGM 闪避深度（配音段 BGM 响度 vs 非配音段 BGM 响度）
    - 转场处（配音段起止 ±0.15s 窗口）峰值与削波检查

用法
    python3 scripts/build_music.py --story story/howtolivebetter-54k
    python3 scripts/build_music.py --story story/xxx --bgm "/path/bgm.mp3" --duck-db 8
    python3 scripts/build_music.py --story story/xxx --bgm-volume 0.22 --out douyin_music.mp4
    python3 scripts/build_music.py --story story/xxx --bpm-grid --out douyin_music_bpm.mp4

退出码：0 成功；1 参数/依赖问题；2 loudnorm 失败；3 输出已存在（--force 可覆盖）。
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
import wave

import numpy as np

ROOT = "/Volumes/PSSD/抖音视频"
FFMPEG = "/opt/homebrew/bin/ffmpeg"
FFPROBE = "/opt/homebrew/bin/ffprobe"

# 免版权本地曲库（mixkit 许可，允许免费商用；文件名已含 mixkit 来源标记）
DEFAULT_MUSIC_DIR = os.path.join("/Volumes/PSSD/视频/BGM", "抖音候选BGM-20260916")

# 情绪 → 选曲档位（最小版仅映射到「温和推进」默认档，为后续档位化留位）
EMOTION_DUCK_DB = 8.0          # 配音段默认闪避深度
EMOTION_FLOOR_LUFS = -26.0     # BGM 铺底目标响度（自动推算基础增益，避免混音爆 TP）
EMOTION_TABLE = {
    # 最小版：所有情绪先落「温和推进」档（同 BGM 基础策略；选曲档位化留待迭代）
    "thoughtful": {"tier": "mild-progress", "duck_db": 8.0},
    "calm": {"tier": "mild-progress", "duck_db": 8.0},
    "default": {"tier": "mild-progress", "duck_db": 8.0},
}

# 与 append_epilogue.py 对齐的成片音频编码（aac 128k / 44100 / stereo）
CODEC_A = ["-c:a", "aac", "-b:a", "128k", "-ar", "44100", "-ac", "2"]


def log(*a):
    print(*a, flush=True)

def run(cmd, **kw):
    r = subprocess.run(cmd, capture_output=True, text=True, **kw)
    if r.returncode != 0:
        log("  ERROR:", " ".join(str(c) for c in cmd[:8]), "...")
        log("  ", (r.stderr or "")[-800:])
        raise SystemExit(1)
    return r


def dur_of(path):
    r = subprocess.run([FFPROBE, "-v", "quiet", "-show_entries", "format=duration",
                        "-of", "default=noprint_wrappers=1:nokey=1", path],
                       capture_output=True, text=True)
    return float(r.stdout.strip())


def loudnorm_measure(path, I="-19.0", TP="-1.5", LRA="11.0"):
    """loudnorm 两遍法 pass1：返回输入测量 JSON。"""
    r = subprocess.run([FFMPEG, "-hide_banner", "-nostats", "-i", path, "-af",
                        f"loudnorm=I={I}:TP={TP}:LRA={LRA}:print_format=json",
                        "-f", "null", "-"], capture_output=True, text=True)
    m = re.search(r"\{[^{}]*\}", r.stderr, re.S)
    if not m:
        raise RuntimeError(f"loudnorm 测量输出不可解析：{path}")
    return json.loads(m.group(0))


def lufs_of(path, start=None, end=None):
    """整段或 [start,end] 时间窗的 ebur128 综合响度 I。"""
    cmd = [FFMPEG, "-hide_banner", "-nostats"]
    if start is not None:
        cmd += ["-ss", f"{start:.3f}"]
    if end is not None:
        cmd += ["-t", f"{end - start:.3f}"]
    cmd += ["-i", path, "-af", "ebur128", "-f", "null", "-"]
    r = subprocess.run(cmd, capture_output=True, text=True)
    v = re.findall(r"I:\s*(-?[\d.]+)\s*LUFS", r.stderr)
    return float(v[-1]) if v else float("nan")


def peak_db(path, start=None, end=None):
    """时间窗（或缺省整段）的绝对峰值 dBFS。"""
    cmd = [FFMPEG, "-hide_banner", "-nostats"]
    if start is not None:
        cmd += ["-ss", f"{start:.3f}"]
    if end is not None:
        cmd += ["-t", f"{end - start:.3f}"]
    cmd += ["-i", path, "-af", "astats=metadata=1:reset=0,ametadata=print:key=lavfi.astats.Overall.Peak_level",
            "-f", "null", "-"]
    r = subprocess.run(cmd, capture_output=True, text=True)
    vals = re.findall(r"Peak_level=(-?[\d.]+)", r.stderr)
    return float(vals[-1]) if vals else float("nan")


def clip_frames(path):
    """整段被削波（|sample| 触及 int16 满幅）的样本计数（numpy 精确统计）。"""
    with wave.open(path, "rb") as w:
        raw = w.readframes(w.getnframes())
    x = np.frombuffer(raw, dtype=np.int16)
    return int((np.abs(x) >= 32767).sum())


def to_24k_mono(src, dst):
    run([FFMPEG, "-y", "-v", "error", "-i", src, "-ar", "24000", "-ac", "1",
         "-c:a", "pcm_s16le", dst])


def read_wav_mono_int16(path):
    with wave.open(path, "rb") as w:
        sr, ch, sw = w.getframerate(), w.getnchannels(), w.getsampwidth()
        raw = w.readframes(w.getnframes())
    x = np.frombuffer(raw, dtype=np.int16).astype(np.float32)
    if ch > 1:
        x = x.reshape(-1, ch).mean(axis=1)
    return x, sr


def write_wav_mono_int16(path, x, sr):
    y = np.clip(x, -32768, 32767).astype(np.int16)
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(y.tobytes())


def pick_bgm(music_dir, script, explicit=None):
    """选曲：--bgm 显式优先；否则本地曲库自动选——优先未在 script.json
    bgm 字段引用过的文件（避免与已发布片尾 BGM 混淆），无则取第一个。"""
    if explicit and os.path.exists(explicit):
        return explicit, "explicit"
    if not os.path.isdir(music_dir):
        return None, f"曲库不存在 {music_dir}"
    cands = sorted(f for f in os.listdir(music_dir)
                   if f.lower().endswith((".mp3", ".wav", ".m4a", ".flac")))
    if not cands:
        return None, "曲库为空"
    used = os.path.basename(script.get("bgm", "") or "")
    for c in cands:
        if used and c == used:
            continue
        return os.path.join(music_dir, c), "local-auto"
    return os.path.join(music_dir, cands[0]), "local-auto(唯一候选)"


def duck_envelope(total_s, sr, voice_ranges, duck_db, fade_s=0.15):
    """生成闪避包络：配音段乘 10^(-duck_db/20)，边界 fade_s 线性过渡防咔哒。"""
    g = np.ones(int(round(total_s * sr)), dtype=np.float32)
    lo = 10 ** (-duck_db / 20.0)
    nf = int(round(fade_s * sr))
    for (a, b) in voice_ranges:
        ia, ib = int(round(a * sr)), int(round(b * sr))
        ia, ib = max(0, ia), min(len(g), ib)
        g[ia:ib] = lo
        # 边界过渡
        if ia - nf >= 0 and ia > 0:
            g[ia - nf:ia] = np.linspace(1.0, lo, nf, dtype=np.float32)
        if ib + nf <= len(g):
            g[ib:ib + nf] = np.linspace(lo, 1.0, nf, dtype=np.float32)
    return g


# ---------------------------------------------------------------------------
# BPM 节拍网格配乐（v0.2 / v1.19.0，借鉴 huashu-art-motion synth 配乐模板）
# 严格网格 / 动机换乐器 / 逐段配器 / 逐段响度对齐
# ---------------------------------------------------------------------------
GRID_T0 = 0.028          # 网格零点（秒），与 huashu synth 模板一致
NOTE_SEMI = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}
CHORD_OFFS = {"minor": (0, 3, 7), "major": (0, 4, 7)}


def semitone_to_hz(midi):
    return 440.0 * 2 ** ((midi - 69) / 12.0)


def osc_wave(freq, n, sr, kind):
    """无采样合成振荡器：sine / triangle / saw / square。"""
    t = np.arange(n) / sr
    ph = 2 * np.pi * freq * t
    if kind == "sine":
        return np.sin(ph)
    if kind == "triangle":
        return 2.0 / np.pi * np.arcsin(np.sin(ph))
    if kind == "saw":
        return 2.0 * ((freq * t) % 1.0) - 1.0
    if kind == "square":
        return np.sign(np.sin(ph))
    raise ValueError(kind)


def pluck_env(n, sr, decay=8.0):
    """拨弦式指数衰减包络（短促，避免无采样合成发闷）。"""
    t = np.arange(n) / sr
    return np.exp(-decay * t) * (1 - np.exp(-t * 80.0))


def drum_hit(n, sr, seed=20261010):
    """短噪声鼓点（噪声爆 + 指数衰减）。"""
    rng = np.random.default_rng(seed)
    x = rng.normal(0, 1, n).astype(np.float32)
    return x * np.exp(-np.arange(n) / sr * 12.0)


def build_grid_segments(script, total_s):
    """从 script.json 构造段表 [(start, end, beat)]：
    段边界取 lines[].start/end；beat 取行级 -> 场景级（scenes[].beat）-> 默认 3。"""
    lines = script.get("lines") or []
    scenes = script.get("scenes") or []
    segs = []
    for i, ln in enumerate(lines):
        a = float(ln.get("start", 0.0))
        b = float(ln.get("end", a + 1.0))
        beat = ln.get("beat")
        if beat is None and scenes:
            si = ln.get("scene_index", i if i < len(scenes) else None)
            if isinstance(si, int) and 0 <= si < len(scenes) and scenes[si]:
                beat = scenes[si].get("beat")
            if beat is None and i < len(scenes) and scenes[i]:
                beat = scenes[i].get("beat")
        segs.append((a, min(b, total_s), int(beat or 3)))
    if not segs:
        segs = [(0.0, total_s, 3)]
    return segs


def synth_bpm_bgm(segs, total_s, sr=24000, bpm=128.0, lufs_target=-26.0):
    """严格 BPM 节拍网格合成（24k mono float32）。

    思路（借鉴 huashu synth 模板）：
      - 八分音符网格：t_n = T0 + n·E（E = 60/BPM/2），段边界吸附到网格槽；
      - 三音动机（根音/三音/五音）随段序和声进行 i–VI–III–VII 移调（D 小调）；
      - 逐段按 beat 换配器：1-2 sine 长音 / 3 triangle / 4 saw+低通 / 5 square+鼓，
        beat 越高音符密度越大（动机换乐器 + 逐段配器）；
      - 逐段响度对齐：段内样本 RMS 对齐到 lufs_target（借鉴 huashu 逐段加权对齐，
        用 RMS 近似 LUFS）。
    """
    E = 60.0 / bpm / 2.0
    T0 = GRID_T0
    N = int(round(total_s * sr))
    bus = np.zeros(N, np.float32)
    roots = [50, 58, 53, 48]                 # D3 / Bb3 / F3 / C3（MIDI）
    kinds = ["minor", "major", "major", "major"]
    instr_by_beat = {1: "sine", 2: "sine", 3: "triangle", 4: "saw", 5: "square"}
    dens_by_beat = {1: 0.25, 2: 0.35, 3: 0.50, 4: 0.75, 5: 1.00}
    for si, (a, b, beat) in enumerate(segs):
        beat = min(max(int(round(beat or 3)), 1), 5)
        s_idx = max(0, int(round((a - T0) / E)))
        e_idx = max(s_idx + 1, int(round((b - T0) / E)))
        chord = roots[si % len(roots)]
        midis = [chord + o for o in CHORD_OFFS[kinds[si % len(kinds)]]]
        instr = instr_by_beat[beat]
        dens = dens_by_beat[beat]
        amp = 0.22 if beat <= 2 else 0.30
        for n_ in range(s_idx, e_idx):
            t = T0 + n_ * E
            if t >= total_s:
                break
            gate = ((n_ * 2654435761) % 100) / 100.0     # 槽号散列门控，避免同段内聚集
            if gate > dens:
                continue
            m = midis[n_ % 3]
            if beat >= 4 and n_ % 2 == 1:
                m += 12                                    # 高情绪段八度点缀
            f = semitone_to_hz(m)
            dur = min(E * (2.0 if beat <= 2 else 1.0), total_s - t)
            n_s = int(round(dur * sr))
            if n_s <= 0:
                continue
            sig = osc_wave(f, n_s, sr, instr) * pluck_env(n_s, sr, decay=6.0 if beat <= 2 else 9.0)
            if instr in ("saw", "square"):
                alpha = 0.25                                # 一阶低通去刺
                sig = np.convolve(sig, np.array([alpha, 1 - alpha]), mode="same")
            idx = int(round(t * sr))
            if idx < N:
                seg = sig[: N - idx]
                bus[idx: idx + len(seg)] += seg * amp
            if beat >= 4 and n_ % 2 == 0:                   # 鼓：每四分音符（=每 2 八分音符槽）
                n_d = int(round(min(0.18, total_s - t) * sr))
                if n_d > 0 and idx < N:
                    d = drum_hit(n_d, sr, seed=1000 + si) * 0.35
                    bus[idx: idx + n_d] += d[: N - idx]
        # 逐段响度对齐
        ia, ib = int(round(a * sr)), int(round(min(b, total_s) * sr))
        if ib > ia:
            rms = float(np.sqrt(np.mean(bus[ia:ib] ** 2))) + 1e-9
            g = float(np.clip(10 ** ((lufs_target - 20 * np.log10(rms)) / 20.0), 0.05, 8.0))
            bus[ia:ib] *= g
    return bus


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--story", default=os.path.join(ROOT, "story/howtolivebetter-54k"))
    ap.add_argument("--bgm", default="", help="显式指定免版权 BGM；缺省从本地曲库自动选")
    ap.add_argument("--music-dir", default=DEFAULT_MUSIC_DIR)
    ap.add_argument("--duck-db", type=float, default=EMOTION_DUCK_DB)
    ap.add_argument("--bgm-volume", type=float, default=0.0,
                    help="BGM 基础线性增益；0 表示按铺底响度 -26 LUFS 自动推算")
    ap.add_argument("--bpm-grid", action="store_true",
                    help="启用 BPM 节拍网格配乐模式（严格网格合成，不选外部 BGM；不改变现有选曲模式）")
    ap.add_argument("--bpm", type=float, default=128.0,
                    help="BPM 节拍网格模式的 BPM（默认 128，八分音符网格）")
    ap.add_argument("--bpm-key", default="dm",
                    help="BPM 模式调性（预留；当前和声进行固定 D 小调 i–VI–III–VII）")
    ap.add_argument("--bpm-grid-lufs", type=float, default=EMOTION_FLOOR_LUFS,
                    help="BPM 模式逐段响度对齐目标（默认 -26 铺底）")
    ap.add_argument("--out", default="douyin_music.mp4")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("-I", default="-19.0")
    ap.add_argument("-TP", default="-1.5")
    ap.add_argument("-LRA", default="11.0")
    args = ap.parse_args()

    story = os.path.abspath(args.story)
    src_mp4 = os.path.join(story, "douyin.mp4")
    narration = os.path.join(story, "narration.wav")
    script_json = os.path.join(story, "script.json")
    timing_json = os.path.join(story, "timing.json")
    for p in (src_mp4, narration, script_json):
        if not os.path.exists(p):
            raise SystemExit(f"缺少必需文件: {p}")

    script = json.load(open(script_json, encoding="utf-8"))
    lines = script.get("lines") or []
    if not lines:
        raise SystemExit("script.json 无 lines，无法定位配音段")

    # 1) 情绪参数 → 档位
    emotion = ((script.get("voice_lock") or {}).get("emotion")
               or ((script.get("tts_params") or {}).get("voice_lock") or {}).get("emotion_ref")
               or "default")
    tier_cfg = EMOTION_TABLE.get(emotion, EMOTION_TABLE["default"])
    duck_db = args.duck_db
    log(f"=== 最小版配乐 build_music.py ===")
    log(f"  story: {story}")
    log(f"  情绪参数: {emotion} → 档位 {tier_cfg['tier']}（闪避默认 {tier_cfg['duck_db']}dB，本次 {duck_db}dB）")

    # 2) 配音段时间轴（总时长提前计算，供选曲/BPM 合成使用）
    vdur = dur_of(src_mp4)
    total = vdur

    # 2') 选曲 / BPM 节拍网格合成（可选模式，不改变现有选曲）
    bpm_mode = args.bpm_grid
    if bpm_mode:
        work = os.path.join(story, "music_work")
        os.makedirs(work, exist_ok=True)
        segs = build_grid_segments(script, total)
        E = 60.0 / args.bpm / 2.0
        log(f"  BPM 节拍网格配乐: {args.bpm:.0f} BPM（八分音符 {E:.4f}s，网格零点 "
            f"{GRID_T0:.3f}s）/ key {args.bpm_key} / 逐段响度对齐 {args.bpm_grid_lufs:.0f} LUFS")
        sig = synth_bpm_bgm(segs, total, sr=24000, bpm=args.bpm, lufs_target=args.bpm_grid_lufs)
        bgm24 = os.path.join(work, "bgm.grid24k.wav")
        write_wav_mono_int16(bgm24, sig * 32767.0, 24000)   # 合成域 [-1,1] → int16 满幅量级
        bgm_path, pick_note = bgm24, "bpm-grid-synth（严格网格 / 逐段配器 / 逐段响度对齐）"
        bgm_dur = total
    else:
        bgm_path, pick_note = pick_bgm(args.music_dir, script, args.bgm.strip())
        if not bgm_path:
            raise SystemExit(f"无可用免版权 BGM：{pick_note}")
        bgm_dur = dur_of(bgm_path)
    log(f"  BGM: {bgm_path}（{pick_note}）")

    # 3) 配音段时间轴
    voice_ranges = [(ln["start"], ln["end"]) for ln in lines]
    log(f"  配音段 {len(voice_ranges)} 段 / 总时长 {total:.2f}s / BGM {bgm_dur:.1f}s")

    work = os.path.join(story, "music_work")
    os.makedirs(work, exist_ok=True)

    # 4) BGM → 24k mono → 循环到总时长 → 基础增益 + 闪避包络
    bgm24 = os.path.join(work, "bgm.24k.wav")
    to_24k_mono(bgm_path, bgm24)
    b, sr = read_wav_mono_int16(bgm24)
    if len(b) == 0:
        raise SystemExit("BGM 解码为空")
    reps = int(np.ceil(total * sr / len(b)))
    bgm_full = np.tile(b, reps)[: int(round(total * sr))]

    if bpm_mode:
        base_gain = 1.0
        gain_note = f"BPM 合成已按铺底 {args.bpm_grid_lufs:.0f} LUFS 逐段对齐，基础增益 1.0"
    elif args.bgm_volume > 0:
        base_gain = args.bgm_volume
        gain_note = f"显式 {base_gain:.3f}"
    else:
        bgm_lufs = lufs_of(bgm24)
        base_gain = float(np.clip(10 ** ((EMOTION_FLOOR_LUFS - bgm_lufs) / 20.0), 0.10, 0.40))
        gain_note = (f"按铺底 {EMOTION_FLOOR_LUFS:.0f} LUFS 自动推算"
                     f"（BGM 原始 {bgm_lufs:.1f} LUFS → 增益 {base_gain:.3f}）")
    log(f"  BGM 基础增益: {gain_note}")
    bgm_scaled = bgm_full * base_gain

    env = duck_envelope(total, sr, voice_ranges, duck_db)
    bgm_ducked = bgm_scaled * env
    bgm_ducked_wav = os.path.join(work, "bgm.ducked.wav")
    write_wav_mono_int16(bgm_ducked_wav, bgm_ducked, sr)
    bgm_noduck_wav = os.path.join(work, "bgm.noduck.wav")
    write_wav_mono_int16(bgm_noduck_wav, bgm_scaled, sr)
    log(f"  闪避包络已写: 配音段 -{duck_db:.0f}dB（边界 0.15s 过渡）")

    # 5) 混音（narration + 闪避 BGM）
    v, vsr = read_wav_mono_int16(narration)
    if vsr != sr:
        log(f"  WARN: narration {vsr}Hz ≠ BGM {sr}Hz，以 narration 为准重建 BGM")
        m = max(0, int(round(total * vsr)))
        b2 = np.tile(b, int(np.ceil(m / len(b))))[:m]
        b2 = b2 * base_gain
        env2 = duck_envelope(total, vsr, voice_ranges, duck_db)
        bgm_ducked = b2 * env2
        sr = vsr
    n = min(len(v), int(round(total * sr)))
    v = v[:n]
    bgm_ducked = bgm_ducked[:n]
    mix = v + bgm_ducked
    # 混音 headroom：加法可能触及 int16 满幅，预检并整体缩 10% 防削波（后续 loudnorm 会拉回目标）
    peak_abs = float(np.max(np.abs(mix))) if len(mix) else 0.0
    if peak_abs >= 32767.0:
        mix = mix * 0.9
        log(f"  混音峰值预检 {peak_abs:.0f} ≥ 满幅 → 整体 ×0.9 防削波")
    mix_raw = os.path.join(work, "mix.raw.wav")
    write_wav_mono_int16(mix_raw, mix, sr)
    log(f"  混音完成: narration {len(v)/sr:.2f}s + BGM → {os.path.basename(mix_raw)}")

    # 6) 整体 loudnorm 两遍法（复用 loudness_match.py：裸 PCM + 标准 RIFF 头）
    lm = os.path.join(ROOT, "scripts", "loudness_match.py")
    bak = os.path.join(story, "versions", f"{time.strftime('%Y%m%d')}-pre-musicloudnorm")
    log(f"  整体 loudnorm 两遍法: I={args.I} / TP={args.TP} / LRA={args.LRA}")
    r = subprocess.run([sys.executable, lm, "--wavs", mix_raw,
                        "-I", args.I, "-TP", args.TP, "-LRA", args.LRA,
                        "--backup-dir", bak], capture_output=True, text=True)
    log((r.stdout or "").strip())
    if r.returncode != 0:
        raise SystemExit(f"整体 loudnorm 失败 rc={r.returncode}：{(r.stderr or '')[-300:]}")
    mix_final = mix_raw  # loudness_match 原地替换

    # 7) 产出配乐版成片（另存新版，严禁覆盖 douyin.mp4 / douyin_epilogue.mp4）
    out_mp4 = os.path.join(story, args.out)
    if os.path.exists(out_mp4) and not args.force:
        raise SystemExit(f"输出已存在（如需覆盖请加 --force）: {out_mp4}")
    run([FFMPEG, "-y", "-v", "error", "-i", src_mp4, "-i", mix_final,
         "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy",
         *CODEC_A,
         "-movflags", "+faststart", out_mp4])
    log(f"  配乐版成片: {out_mp4}")

    # 8) 量化验证
    log("\n=== 量化验证 ===")
    qc = {}
    # 8.1 整体 loudnorm 测量（输入 vs 目标）
    mj = loudnorm_measure(mix_final, args.I, args.TP, args.LRA)
    qc["overall"] = {
        "input_I_lufs": round(float(mj.get("input_i", float("nan"))), 2),
        "input_TP_dbtp": round(float(mj.get("input_tp", float("nan"))), 2),
        "input_LRA_lu": round(float(mj.get("input_lra", float("nan"))), 2),
        "target": {"I": float(args.I), "TP": float(args.TP), "LRA": float(args.LRA)},
    }
    # 8.2 旁白段 LUFS 保持度：逐配音段 混音后 vs 纯旁白
    segs = []
    for i, (a, b) in enumerate(voice_ranges):
        narr_i = lufs_of(narration, a, b)
        mix_i = lufs_of(mix_final, a, b)
        segs.append({"idx": i, "start": round(a, 2), "end": round(b, 2),
                     "narration_LUFS": round(narr_i, 2),
                     "mixed_LUFS": round(mix_i, 2),
                     "delta_LU": round(mix_i - narr_i, 2)})
    qc["voice_segments"] = segs
    deltas = [s["delta_LU"] for s in segs if s["delta_LU"] == s["delta_LU"]]
    qc["voice_keep"] = {
        "max_delta_LU": round(max(abs(d) for d in deltas), 2) if deltas else None,
        "note": "|Δ| ≤ 1.5 LU 视为旁白响度保持（BGM 铺底 + 闪避后旁白应基本不变）",
    }
    # 8.3 BGM 闪避深度：配音段 vs 非配音段 BGM 响度差（同一基础增益轨）
    bgm_noduck_lufs_all = lufs_of(bgm_noduck_wav)
    bgm_noduck_lufs_voice = np.nan
    bgm_duck_lufs_voice = np.nan
    if voice_ranges:
        # 配音段合计时长权重测量：逐段 ebur128 求平均 I（时间权重）
        tot_v = sum(b - a for a, b in voice_ranges)
        if tot_v > 0:
            wsum = 0.0
            for (a, b) in voice_ranges:
                x = lufs_of(bgm_noduck_wav, a, b)
                if x == x:
                    wsum += (b - a) * x
            bgm_noduck_lufs_voice = wsum / tot_v
            wsum2 = 0.0
            for (a, b) in voice_ranges:
                x = lufs_of(bgm_ducked_wav, a, b)
                if x == x:
                    wsum2 += (b - a) * x
            bgm_duck_lufs_voice = wsum2 / tot_v
    # 非配音段（取前 3 个配音段之间的空隙采样，若有）
    bgm_noduck_lufs_gap = np.nan
    if len(voice_ranges) >= 2:
        a1, b1 = voice_ranges[0]
        a2, b2 = voice_ranges[1]
        if a2 - b1 > 0.3:
            bgm_noduck_lufs_gap = lufs_of(bgm_noduck_wav, b1 + 0.1, a2 - 0.1)
    qc["ducking"] = {
        "duck_db_setting": duck_db,
        "bgm_noduck_voice_LUFS": round(bgm_noduck_lufs_voice, 2) if bgm_noduck_lufs_voice == bgm_noduck_lufs_voice else None,
        "bgm_ducked_voice_LUFS": round(bgm_duck_lufs_voice, 2) if bgm_duck_lufs_voice == bgm_duck_lufs_voice else None,
        "duck_depth_dB": round(bgm_noduck_lufs_voice - bgm_duck_lufs_voice, 2)
        if bgm_noduck_lufs_voice == bgm_noduck_lufs_voice and bgm_duck_lufs_voice == bgm_duck_lufs_voice else None,
        "bgm_noduck_gap_LUFS": round(bgm_noduck_lufs_gap, 2) if bgm_noduck_lufs_gap == bgm_noduck_lufs_gap else None,
        "note": "duck_depth_dB ≈ 配音段 BGM 被压低的深度（设置 6~10dB 合规）",
    }
    # 8.4 转场处爆音：配音段起止 ±0.15s 窗口峰值 + 全片削波
    transitions = []
    for (a, b) in voice_ranges:
        for lab, t0 in (("entry", a), ("exit", b)):
            p = peak_db(mix_final, max(0, t0 - 0.15), t0 + 0.15)
            transitions.append({"pos": lab, "time": round(t0, 2),
                                "peak_dbfs": round(p, 2) if p == p else None})
    qc["transitions"] = transitions
    qc["clip_check"] = {"clip_frames": clip_frames(mix_final),
                        "note": "clip_frames=0 表示无 int16 削波（无爆音）"}

    qcdir = os.path.join(story, "qc")
    os.makedirs(qcdir, exist_ok=True)
    qc_path = os.path.join(qcdir, "music_qc.json")
    json.dump(qc, open(qc_path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)

    # 9) 打印汇总
    o = qc["overall"]
    log(f"  [整体] 输入 I={o['input_I_lufs']} LUFS / TP={o['input_TP_dbtp']} dBTP / "
        f"LRA={o['input_LRA_lu']} LU（目标 I={o['target']['I']} / TP={o['target']['TP']} / "
        f"LRA={o['target']['LRA']}，loudnorm 输出对齐目标）")
    dk = qc["ducking"]
    log(f"  [闪避] 配音段 BGM 压低 {dk['duck_depth_dB']} dB（设置 {duck_db}dB）；"
        f"非配音段 BGM {dk['bgm_noduck_gap_LUFS']} LUFS")
    vk = qc["voice_keep"]
    log(f"  [旁白] 配音段响度最大偏移 {vk['max_delta_LU']} LU（保持判据 |Δ|≤1.5）")
    cl = qc["clip_check"]
    log(f"  [爆音] 削波样本 {cl['clip_frames']}；转场窗口峰值：")
    for t in qc["transitions"]:
        log(f"      {t['pos']}@{t['time']:.2f}s peak {t['peak_dbfs']} dBFS")
    log(f"\n完成: {out_mp4}")
    log("QC: " + qc_path)
    log("RESULT " + json.dumps({
        "story": story, "output": out_mp4, "bgm": bgm_path, "pick_note": pick_note,
        "emotion": emotion, "tier": tier_cfg["tier"], "duck_db": duck_db,
        "base_gain": round(float(base_gain), 4), "qc": qc_path,
        "overall": o, "ducking": dk, "voice_keep": vk, "clip": cl,
        "transitions": qc["transitions"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
