#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""KB-A10+ 整篇单次推理 TTS（音色一致性终极手段）

原理
----
Qwen3-TTS 为零样本语音克隆：即便锁定同一参考音、同一采样参数，**逐句分别推理**
时每句仍是独立解码轨迹，说话人音色会有 text-dependent 的细微漂移 —— 这正是
v2（锁参考音）/ v3（再锁采样）都无法根治、听感上"还有音色不一样的地方"的根因。

本方案改为：把全片文案拼接为**一个连续文本**，一次 generate 调用完成整段解码，
使全片共享同一条自回归轨迹与参考音 prompt → 音色在整段内部天然连续。
产出的整段语音再按静音边界切分为逐句素材。

用法：python tts_oneshot.py --text-file X.txt --out Y.wav [--seed .. --temperature ..]
"""
import argparse
import json
import os
import shutil
import sys
import time


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--text-file", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--ref-audio", required=True)
    ap.add_argument("--ref-text", default="")
    ap.add_argument("--seed", type=int, default=20261009)
    ap.add_argument("--temperature", type=float, default=0.60)
    ap.add_argument("--top-p", type=float, default=0.80)
    ap.add_argument("--top-k", type=int, default=-1)
    ap.add_argument("--max-tokens", type=int, default=20000,
                    help="整篇一次解码需要远超单句的 token 上限（12Hz 模型约 137.5 token/s）")
    ap.add_argument("--model",
                    default="/Users/mac/Projects/qwen3-tts-apple-silicon/"
                            "models/Qwen3-TTS-12Hz-1.7B-Base-8bit")
    args = ap.parse_args()

    text = open(args.text_file, encoding="utf-8").read().strip()
    import mlx.core as mx
    from mlx_audio.tts.utils import load_model
    from mlx_audio.tts.generate import generate_audio

    mx.random.seed(args.seed)
    print(f"[oneshot] chars={len(text)} seed={args.seed} temp={args.temperature} "
          f"top_p={args.top_p}", flush=True)

    t0 = time.time()
    model = load_model(args.model)
    print(f"model loaded in {time.time() - t0:.1f}s", flush=True)

    td = os.path.join(os.path.dirname(os.path.abspath(args.out)), "_oneshot_tmp")
    shutil.rmtree(td, ignore_errors=True)
    t1 = time.time()
    # 文本不含换行 -> split_pattern 不生效 => 整段一次解码
    generate_audio(model=model, text=text, ref_audio=args.ref_audio,
                   ref_text=args.ref_text, output_path=td,
                   temperature=args.temperature, top_p=args.top_p,
                   top_k=args.top_k, max_tokens=args.max_tokens, verbose=False)
    print(f"generated in {time.time() - t1:.1f}s", flush=True)

    src = os.path.join(td, "audio_000.wav")
    if not os.path.exists(src):
        print("FAIL: no audio_000.wav", flush=True)
        return 3
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    shutil.move(src, args.out)
    shutil.rmtree(td, ignore_errors=True)
    print("OK ->", args.out, flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
