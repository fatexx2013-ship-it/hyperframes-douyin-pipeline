#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
whisper_dtw.py —— 逐字（token 级）时间轴生成器（产线落地版 v1.0.0）

职责：把配音音频转成 whisper.cpp DTW 的 token 级时间轴 JSON，供 build_karaoke_ass.py
生成 \\kf 逐字卡拉OK ASS 使用。

与产线既有 whisper（openai-whisper -> transcript.json -> json_to_srt.py）的关系：
- 既有链路：句级/词级时间轴 -> 整句 SRT（captions.srt），默认链路，不被本脚本改动。
- 本脚本：额外产出 captions.dtw.json（token 级 t_dtw），只服务逐字卡拉OK。
  未开启卡拉OK（config/karaoke.json enabled=false）时不需要执行本脚本。

用法：
    python3 scripts/whisper_dtw.py \
        --audio story/xxx/narration.mp3 \
        --out   story/xxx/captions.dtw.json \
        [--model models/ggml-small.bin] [--language zh] \
        [--cross-check-model models/ggml-large-v3-turbo-q5_0.bin]

退出码：
    0  成功
    1  依赖缺失 / 音频缺失 / whisper-cli 失败 / 产物不可解析
    2  token 级时间轴全缺失（t_dtw 全为 -1：模型无对齐头，或未以 -nfa/-ojf 调用）

实现要点（实测口径）：
    -dtw 需要「预设名」而非模型路径（如 -dtw small -> models/ggml-small.bin）；
    -nfa 必须开启（关 flash-attn），否则 t_dtw 全为 -1；
    -ojf（完整 JSON）才会输出 tokens[].t_dtw；-oj 不带 tokens。t_dtw 单位 1/100s。
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def resolve(p):
    if not p:
        return p
    return p if os.path.isabs(p) else os.path.join(ROOT, p)


def load_cfg(path):
    p = resolve(path)
    if os.path.isfile(p):
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    return {}


def preset_of(model, override=""):
    """ggml-small.bin -> small；-dtw 走 whisper.cpp 预设名（非模型路径）。"""
    if override:
        return override
    base = os.path.basename(model or "")
    if base.startswith("ggml-") and base.endswith(".bin"):
        return base[len("ggml-"):-len(".bin")]
    return "small"


def run_dtw(bin_path, model, audio, language, out_json, extra_args=None, tag="", preset=""):
    if not os.path.isfile(bin_path):
        print(f"错误：找不到 whisper-cli：{bin_path}", file=sys.stderr)
        return 1, None
    if not os.path.isfile(model):
        print(f"错误：找不到 DTW 模型：{model}（可放 models/ggml-small.bin）", file=sys.stderr)
        return 1, None
    if not os.path.isfile(audio):
        print(f"错误：找不到音频：{audio}", file=sys.stderr)
        return 1, None

    preset = preset_of(model, preset)
    preset_file = os.path.join(ROOT, "models", f"ggml-{preset}.bin")
    if not os.path.isfile(preset_file):
        print(f"错误：-dtw 按预设名加载 models/ggml-{preset}.bin，该文件不存在"
              f"（模型名: {os.path.basename(model)}）", file=sys.stderr)
        return 1, None

    tmpdir = tempfile.mkdtemp(prefix="dtw_")
    prefix = os.path.join(tmpdir, "out")
    # -dtw <preset>：token 级时间戳；-nfa：必须关 flash-attn，否则 t_dtw 全 -1；
    # -ojf：完整 JSON（只有 -ojf 才带 tokens[].t_dtw）
    cmd = [bin_path, "-m", model, "-f", audio, "-l", language,
           "-dtw", preset, "-nfa", "-ojf", "-np", "-of", prefix]
    cmd += list(extra_args or [])
    print(f"--- whisper.cpp DTW{tag}（preset={preset}，-nfa，-ojf） ---")
    r = subprocess.run(cmd, capture_output=True, text=True, cwd=ROOT)
    src = prefix + ".json"
    if r.returncode != 0 or not os.path.isfile(src):
        print(f"错误：whisper-cli 失败（exit {r.returncode}）", file=sys.stderr)
        print((r.stderr or "")[-2000:], file=sys.stderr)
        shutil.rmtree(tmpdir, ignore_errors=True)
        return 1, None

    with open(src, encoding="utf-8") as f:
        data = json.load(f)
    shutil.rmtree(tmpdir, ignore_errors=True)

    n_tok, n_dtw = 0, 0
    for seg in data.get("transcription", []):
        for t in seg.get("tokens", []):
            if str(t.get("text", "")).startswith("[_"):
                continue
            n_tok += 1
            if (t.get("t_dtw") or -1) >= 0:
                n_dtw += 1
    if n_tok == 0:
        print("错误：转写结果为空", file=sys.stderr)
        return 1, None
    if n_dtw == 0:
        print("错误：t_dtw 全缺失（模型无对齐头，不支持 -dtw）", file=sys.stderr)
        return 2, None

    if out_json:
        os.makedirs(os.path.dirname(os.path.abspath(out_json)), exist_ok=True)
        with open(out_json, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
    print(f"  token 总数 {n_tok}，其中带 DTW 时间轴 {n_dtw}（{n_dtw * 100 // n_tok}%）")
    return 0, data


def compare(a, b, label_a, label_b):
    def chars(d):
        out = []
        for seg in d.get("transcription", []):
            for t in seg.get("tokens", []):
                txt = str(t.get("text", ""))
                if txt.startswith("[_"):
                    continue
                td = t.get("t_dtw", -1)
                if td is None or td < 0:
                    continue
                for c in txt:
                    if not c.isspace():
                        out.append((td * 10, c))
        return out

    ca, cb = chars(a), chars(b)
    n = min(len(ca), len(cb))
    if n == 0:
        print("  交叉校验：可比字符不足，跳过")
        return
    diffs = [abs(ca[i][0] - cb[i][0]) for i in range(n)]
    avg = sum(diffs) / len(diffs)
    print(f"  交叉校验 {label_a} vs {label_b}：{n} 字，起拍差平均 {avg:.0f}ms，最大 {max(diffs)}ms")


def main():
    cfg = load_cfg("config/karaoke.json")
    dtw_cfg = cfg.get("dtw") or {}

    ap = argparse.ArgumentParser(description="配音音频 -> whisper.cpp DTW token 级时间轴 JSON")
    ap.add_argument("--audio", required=True, help="配音音频（mp3/wav）")
    ap.add_argument("--out", default="", help="输出 DTW JSON（默认 story 目录下 captions.dtw.json）")
    ap.add_argument("--model", default=dtw_cfg.get("model") or "models/ggml-small.bin")
    ap.add_argument("--bin", dest="bin_path", default=dtw_cfg.get("bin") or "/opt/homebrew/bin/whisper-cli")
    ap.add_argument("--language", default=dtw_cfg.get("language") or "zh")
    ap.add_argument("--dtw-preset", default=dtw_cfg.get("dtw_preset") or "",
                    help="whisper.cpp -dtw 预设名（默认由模型名推导，如 small）")
    ap.add_argument("--cross-check-model", default=dtw_cfg.get("cross_check_model") or "")
    ap.add_argument("--config", default="config/karaoke.json")
    args = ap.parse_args()

    global ROOT
    cfg2 = load_cfg(args.config)
    if cfg2:
        ROOT = os.path.dirname(os.path.dirname(os.path.abspath(args.config))) or ROOT

    audio = os.path.abspath(args.audio)
    model = resolve(args.model)
    bin_path = resolve(args.bin_path) if args.bin_path.startswith(".") else args.bin_path
    out_json = os.path.abspath(args.out) if args.out else os.path.splitext(audio)[0] + ".dtw.json"

    extra = dtw_cfg.get("extra_args") or []
    code, data = run_dtw(bin_path, model, audio, args.language, out_json, extra, preset=args.dtw_preset)
    if code != 0:
        return code
    print(f"DTW 时间轴已写出：{out_json}")

    if args.cross_check_model:
        cm = resolve(args.cross_check_model)
        if not os.path.isfile(cm):
            print(f"  交叉校验跳过：模型不存在 {cm}")
        else:
            code2, data2 = run_dtw(bin_path, cm, audio, args.language, None, extra,
                                   tag="[cross-check]", preset=preset_of(cm))
            if code2 == 0 and data2:
                compare(data, data2, "主模型", "交叉模型")
    return 0


if __name__ == "__main__":
    sys.exit(main())
