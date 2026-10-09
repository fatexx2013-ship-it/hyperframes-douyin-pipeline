#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""KB-A10 采样锁定批量 TTS（单线单音色 v3）

引入背景（2026-10-09 二次反馈）
------------------------------
v2（KB-A9）只锁定了「参考音唯一」，但 Qwen3-TTS 每段推理仍走默认随机采样
（qwen3.generate 默认 temperature=0.6 / top_p=0.8，且无 seed 固定），
正片 6 句与片尾各为一次独立随机推理 → 每段音色在共振峰/发声质量维度仍有
细微随机偏移，听感上仍能察觉「音色不完全一致」。

本脚本 = 采样层锁定真源（v3）：
  1) 一次 load 模型，正片 + 片尾**同批**生成（消除分批差异与重复加载）
  2) mx.random.seed 固定（采样可复现）
  3) 收紧采样分布（默认 temperature=0.30 / top_p=0.70 / top_k=40），
     压低随机性 → 各段更贴近同一参考音音色

用法（由 build_audio.py 以 qwen3 venv python 直接调用）：
  python tts_seed_locked.py --jobs jobs.json --ref-audio A.wav --ref-text "..." \
      --seed 20261009 --temperature 0.30 --top-p 0.70 --top-k 40
退出码：0 全部成功 / 3 有段落失败（调用方据此判失败）
"""
import argparse
import json
import os
import shutil
import sys
import time


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--jobs", required=True, help="JSON 文件：[{text,out}]")
    ap.add_argument("--ref-audio", required=True)
    ap.add_argument("--ref-text", default="")
    ap.add_argument("--seed", type=int, default=20261009)
    ap.add_argument("--temperature", type=float, default=0.30)
    ap.add_argument("--top-p", type=float, default=0.70)
    ap.add_argument("--top-k", type=int, default=40)
    ap.add_argument("--repetition-penalty", type=float, default=1.3)
    ap.add_argument("--model",
                    default="/Users/mac/Projects/qwen3-tts-apple-silicon/"
                            "models/Qwen3-TTS-12Hz-1.7B-Base-8bit")
    args = ap.parse_args()

    jobs = json.load(open(args.jobs, encoding="utf-8"))
    if not os.path.exists(args.ref_audio):
        print("REF-MISSING", args.ref_audio, flush=True)
        return 3

    import mlx.core as mx
    from mlx_audio.tts.utils import load_model
    from mlx_audio.tts.generate import generate_audio

    mx.random.seed(args.seed)
    print(f"[seed-lock] seed={args.seed} temp={args.temperature} "
          f"top_p={args.top_p} top_k={args.top_k} jobs={len(jobs)}", flush=True)

    t0 = time.time()
    model = load_model(args.model)
    print(f"model loaded in {time.time() - t0:.1f}s", flush=True)

    ok = 0
    for i, j in enumerate(jobs):
        # 每段回到同一随机起点，保证「同批同源」且可复现
        mx.random.seed(args.seed)
        td = os.path.join(os.path.dirname(j["out"]) or ".", f"_tts_tmp_{i:02d}")
        shutil.rmtree(td, ignore_errors=True)
        print(f"GEN {i + 1}/{len(jobs)} {j['text'][:28]}", flush=True)
        try:
            generate_audio(model=model, text=j["text"], ref_audio=args.ref_audio,
                           ref_text=args.ref_text, output_path=td,
                           temperature=args.temperature, top_p=args.top_p,
                           top_k=args.top_k,
                           repetition_penalty=args.repetition_penalty,
                           verbose=False)
        except Exception as e:  # noqa: BLE001
            print("ERR", i, repr(e)[:200], flush=True)
        src = os.path.join(td, "audio_000.wav")
        if os.path.exists(src):
            os.makedirs(os.path.dirname(j["out"]), exist_ok=True)
            shutil.move(src, j["out"])
            ok += 1
            print("OK", i, flush=True)
        else:
            print("FAIL", i, flush=True)
        shutil.rmtree(td, ignore_errors=True)

    print(f"DONE ok={ok}/{len(jobs)}", flush=True)
    return 0 if ok == len(jobs) else 3


if __name__ == "__main__":
    sys.exit(main())
