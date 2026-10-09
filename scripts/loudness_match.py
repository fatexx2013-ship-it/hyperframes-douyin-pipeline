#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""loudness_match.py —— 逐段响度归一化（EBU R128，纯线性增益）

职责
----
把一组独立合成的配音素材拉平到同一响度目标，消除「某段更轻 / 某段更响」造成的
听感不一致（人耳对 1 LU 级差异即可察觉，易被误判为「音色变了」）。

与产线既有音频工具的关系
- build_audio.py：合成后、拼接前调用本工具（A11 / v1.16.0）；
- append_epilogue.py：负责 BGM 混音，本工具不碰 BGM。

实现要点
- 两遍法 loudnorm：pass1 测量（print_format=json）→ pass2 以 measured_* + linear=true 施加。
- linear=true 只做**线性增益**：不引入压缩/限幅，不改动态、不改时长、不改采样率。
- 若某段施加增益后峰值越过 TP，loudnorm 会退化为动态模式；调用方应保证目标 LUFS
  贴近素材自然响度（实测口径：目标 -19.0 LUFS / TP -1.5 dBTP 时全段线性）。
- 原地替换前自动备份到 <story>/versions/<ts>-pre-loudnorm/（可用 --no-backup 关闭）。

用法
    python3 scripts/loudness_match.py --wavs a.wav b.wav -I -19.0 -TP -1.5
    python3 scripts/loudness_match.py --wavs-dir story/xxx --pattern "line_*.wav"

退出码：0 成功；1 参数/依赖问题；2 loudnorm 失败或无法解析测量值。
"""
import argparse
import glob
import json
import os
import re
import shutil
import subprocess
import sys
import time
import wave

FFMPEG = "/opt/homebrew/bin/ffmpeg"
FFPROBE = "/opt/homebrew/bin/ffprobe"


def measure(path, I, TP, LRA):
    r = subprocess.run(
        [FFMPEG, "-hide_banner", "-nostats", "-i", path, "-af",
         f"loudnorm=I={I}:TP={TP}:LRA={LRA}:print_format=json",
         "-f", "null", "-"], capture_output=True, text=True)
    m = re.search(r"\{[^{}]*\}", r.stderr, re.S)
    if not m:
        raise RuntimeError(f"loudnorm 测量输出不可解析：{path}")
    return json.loads(m.group(0))


def apply_linear(path, I, TP, LRA, mj):
    """以线性增益施加 loudnorm，并写回**标准 RIFF 头**的 wav。

    注意：ffmpeg 直接 `-c:a pcm_s16le` 输出会写 WAVE_FORMAT_EXTENSIBLE(65534) 头，
    下游 Python `wave` 模块（build_audio.py 的拼接步骤）无法解析。故此处让 ffmpeg
    只输出裸 PCM，由 Python 按原参数重写标准 wav 头。
    """
    with wave.open(path, "rb") as w:
        sr, ch, sw = w.getframerate(), w.getnchannels(), w.getsampwidth()
    af = (f"loudnorm=I={I}:TP={TP}:LRA={LRA}:linear=true:"
          f"measured_I={mj['input_i']}:measured_TP={mj['input_tp']}:"
          f"measured_LRA={mj['input_lra']}:measured_thresh={mj['input_thresh']}:"
          f"offset={mj['target_offset']}")
    r = subprocess.run([FFMPEG, "-v", "error", "-i", path, "-af", af,
                        "-f", "s16le", "-ar", str(sr), "-ac", str(ch), "-"],
                       capture_output=True)
    if r.returncode != 0 or not r.stdout:
        raise RuntimeError(f"loudnorm 应用失败：{path}\n{r.stderr.decode()[:300]}")
    tmp = path + ".ln-tmp.wav"
    with wave.open(tmp, "wb") as w:
        w.setnchannels(ch)
        w.setsampwidth(sw)
        w.setframerate(sr)
        w.writeframes(r.stdout)
    os.replace(tmp, path)


def lufs_of(path):
    r = subprocess.run([FFMPEG, "-hide_banner", "-nostats", "-i", path, "-af", "ebur128",
                        "-f", "null", "-"], capture_output=True, text=True)
    v = re.findall(r"I:\s*(-?[\d.]+)\s*LUFS", r.stderr)
    return float(v[-1]) if v else float("nan")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--wavs", nargs="*", default=[])
    ap.add_argument("--wavs-dir", default="")
    ap.add_argument("--pattern", default="line_*.wav")
    ap.add_argument("-I", default="-19.0")
    ap.add_argument("-TP", default="-1.5")
    ap.add_argument("-LRA", default="11.0")
    ap.add_argument("--backup-dir", default="")
    ap.add_argument("--no-backup", action="store_true")
    args = ap.parse_args()

    files = list(args.wavs)
    if args.wavs_dir:
        files += sorted(glob.glob(os.path.join(args.wavs_dir, args.pattern)))
    files = [f for f in files if os.path.exists(f) and ".24k." not in f]
    if not files:
        print("无待处理音频")
        return 1

    bak = args.backup_dir
    if not args.no_backup and bak:
        os.makedirs(bak, exist_ok=True)
        for f in files:
            d = os.path.join(bak, os.path.basename(f))
            if not os.path.exists(d):
                shutil.copy2(f, d)
        print(f"已备份 {len(files)} 个文件 -> {bak}")

    print(f"目标：I={args.I} LUFS / TP={args.TP} dBTP / LRA={args.LRA}（linear=true 纯增益）")
    before, after, fails = {}, {}, []
    for f in files:
        try:
            before[f] = lufs_of(f)
            mj = measure(f, args.I, args.TP, args.LRA)
            apply_linear(f, args.I, args.TP, args.LRA, mj)
            after[f] = lufs_of(f)
            print(f"  {os.path.basename(f):26s} {before[f]:7.2f} -> {after[f]:7.2f} LUFS "
                  f"(增益 {after[f] - before[f]:+.2f} dB)")
        except Exception as e:  # noqa: BLE001
            fails.append((f, str(e)))
            print(f"  !! {os.path.basename(f)} 失败：{e}")

    if fails:
        return 2
    xs = [v for v in after.values() if v == v]
    if xs:
        print(f"归一化后段间极差 {max(xs) - min(xs):.2f} LU（目标 ≤0.3）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
