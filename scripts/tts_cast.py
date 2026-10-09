#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
多角色 TTS 合成脚本（增量4）——显式 --cast 开关，默认单人线行为一字不变。

角色表与音色池复用有声书线（audiobook-markup v2.0）：
  - config/roles.json  ：角色编号 → 音色 / 语速 / 音量 / emotion_scale
  - config/voices.json  ：音色池（engine=clone 参考音频克隆 / engine=custom 内置说话人）
视频产线多角色项目直接引同一份角色表，两个产线共享角色宇宙。

用法（必须用 qwen3 venv python 运行）：
  ~/Projects/qwen3-tts-apple-silicon/.venv/bin/python scripts/tts_cast.py \
      --lines "男主:你好|女主:你也好|男二:都别吵了" --out-dir story/<n>/cast/
  # 或从 script.json 的 cast_lines 读台词（显式 --cast 模式）

输出：
  story/<n>/cast/role_<id>_<idx>.wav  每角色每句独立文件
  story/<n>/cast/cast_full.wav        拼接后完整对话
  story/<n>/cast/cast_meta.json       台账（角色/音色/引擎/时长/F0 摘要）

单人线不触发本脚本；storyctl build 不调用本入口。
"""
import argparse
import json
import os
import sys
from pathlib import Path

VENV_HINT = "~/Projects/qwen3-tts-apple-silicon/.venv/bin/python"

def die(msg: str, code: int = 2):
    print(f"[tts-cast] {msg}", file=sys.stderr)
    sys.exit(code)

def expand(p: str, base: Path | None = None) -> Path:
    p = os.path.expanduser(p)
    if base and not os.path.isabs(p):
        p = str(base / p)
    return Path(p)

def load_json(path: Path, kind: str) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        die(f"读取{kind}失败：{path}（{e}）")

def main() -> int:
    ap = argparse.ArgumentParser(description="多角色 TTS 合成（--cast 显式模式）")
    ap.add_argument("--lines", default="", help="台词：'角色名:台词|角色名:台词'（角色名对应 roles.json 的 name）")
    ap.add_argument("--script", default="", help="story/<n>/script.json（读 cast_lines 字段：[{role,text}]）")
    ap.add_argument("--out-dir", default="", help="输出目录（默认 cwd/cast）")
    ap.add_argument("--roles-json", default="~/Documents/小说演播稿标注/config/roles.json")
    ap.add_argument("--voices-json", default="~/Documents/小说演播稿标注/config/voices.json")
    ap.add_argument("--dry-run", action="store_true", help="只打印计划不合成")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    roles_cfg = load_json(expand(args.roles_json), "角色表")
    voices_cfg = load_json(expand(args.voices_json), "音色池")
    eng_cfg = voices_cfg.get("engine", {})
    providers = eng_cfg.get("providers", {})
    if not providers.get("qwen3-tts", {}).get("enabled"):
        die("voices.json engine.providers.qwen3-tts 未启用")

    # 台词解析：显式 --lines 优先，否则读 script.json 的 cast_lines
    lines: list[dict] = []
    if args.lines:
        for seg in args.lines.split("|"):
            seg = seg.strip()
            if not seg:
                continue
            if ":" not in seg:
                die(f"台词缺少角色分隔符（角色名:台词）：{seg}")
            role_name, text = seg.split(":", 1)
            lines.append({"role": role_name.strip(), "text": text.strip()})
    elif args.script:
        sd = load_json(expand(args.script), "剧本")
        lines = sd.get("cast_lines") or sd.get("cast") or []
        if not lines:
            die("script.json 无 cast_lines/cast 字段（多角色模式需显式声明角色台词）")
    if not lines:
        die("未提供台词：--lines '角色:台词|...' 或 --script 含 cast_lines")
    if len({l["role"] for l in lines}) < 3:
        print("[tts-cast] 提示：多角色验收以 3 个及以上不同角色为准", file=sys.stderr)

    # 角色名 → roles.json 编号 → voice id
    role_by_name = {str(r.get("name")): (n, r) for n, r in roles_cfg.get("roles", {}).items()}
    voices = voices_cfg.get("voices", {})
    cast_plan: list[dict] = []
    for ln in lines:
        rn = str(ln["role"])
        if rn not in role_by_name:
            die(f"角色「{rn}」不在 roles.json（现有：{sorted(role_by_name)}）")
        num, role = role_by_name[rn]
        vid = role.get("voice")
        if vid not in voices:
            die(f"角色「{rn}」引用音色「{vid}」不在 voices.json")
        vc = voices[vid]
        cast_plan.append({
            "role_num": num, "role_name": rn, "voice_id": vid,
            "engine": vc.get("engine", "custom"),
            "speaker": vc.get("speaker"), "ref_audio": vc.get("ref_audio"),
            "ref_text": vc.get("ref_text", ""), "text": ln["text"],
            "speed": float(role.get("speed", 1.0)) * float(vc.get("speed", 1.0)),
            "volume": float(role.get("volume", 1.0)) * float(vc.get("volume", 1.0)),
            "emotion_scale": float(role.get("emotion_scale", 1.0)),
        })

    out_dir = Path(args.out_dir) if args.out_dir else Path("cast")
    out_dir.mkdir(parents=True, exist_ok=True)

    if args.dry_run:
        for i, c in enumerate(cast_plan, 1):
            print(f"  {i}. [{c['role_name']}]({c['voice_id']}, engine={c['engine']}, "
                  f"speaker={c.get('speaker') or c.get('ref_audio')}) {c['text'][:40]}")
        print(f"[tts-cast] dry-run：{len(cast_plan)} 句，输出 {out_dir}")
        return 0

    # 逐角色合成（MLX 串行）
    try:
        import numpy as np
        from mlx_audio.tts.utils import load_model
    except ImportError:
        die(f"缺少 mlx_audio。请用 qwen3 venv 运行：{VENV_HINT} {Path(sys.argv[0]).name} ...")

    assets = expand(eng_cfg.get("assets_dir", "~/Projects/qwen3-tts-apple-silicon"))
    models = eng_cfg.get("models", {})
    sample_rate = int(eng_cfg.get("sample_rate", 24000))
    lang = eng_cfg.get("default_lang", "chinese")
    cache: dict = {}
    meta = []
    stream = []
    for i, c in enumerate(cast_plan, 1):
        engine = c["engine"]
        if engine not in cache:
            mp = expand(models.get(engine, ""), assets)
            if not mp.is_dir():
                die(f"模型目录不存在：{mp}（voices.json engine.models.{engine}）")
            if not args.quiet:
                print(f"[tts-cast] 加载模型（{engine}）：{mp.name} …")
            cache[engine] = load_model(str(mp))
        model = cache[engine]
        kwargs = dict(text=c["text"], lang_code=lang, temperature=0.7, verbose=False)
        if engine == "clone":
            ra = expand(c["ref_audio"], assets)
            if not ra.is_file():
                die(f"参考音频不存在：{ra}")
            kwargs["ref_audio"] = str(ra)
            if c["ref_text"]:
                kwargs["ref_text"] = c["ref_text"]
        else:
            if not c["speaker"]:
                die(f"音色 {c['voice_id']} engine=custom 但缺 speaker")
            kwargs["voice"] = c["speaker"]
        pieces = []
        for res in model.generate(**kwargs):
            pieces.append(np.array(res.audio).reshape(-1).astype(np.float32))
        audio = np.concatenate(pieces) if len(pieces) > 1 else pieces[0]
        if c["speed"] != 1.0:
            audio = _resample_speed(audio, c["speed"])
        if c["volume"] != 1.0:
            audio = audio * c["volume"]
        wav_path = out_dir / f"role_{c['role_num']}_{i:02d}.wav"
        _write_wav(wav_path, audio, sample_rate)
        stream.append(audio)
        meta.append({
            "idx": i, "role_num": c["role_num"], "role_name": c["role_name"],
            "voice_id": c["voice_id"], "engine": engine,
            "file": str(wav_path), "duration_s": round(len(audio) / sample_rate, 2),
            "speed": c["speed"], "volume": c["volume"], "text": c["text"],
        })
        if not args.quiet:
            print(f"  [{i}/{len(cast_plan)}] {c['role_name']}({c['voice_id']}) "
                  f"{len(audio)/sample_rate:.1f}s → {wav_path.name}")

    if stream:
        full = np.concatenate(stream).astype(np.float32)
        full_path = out_dir / "cast_full.wav"
        _write_wav(full_path, full, sample_rate)
        if not args.quiet:
            print(f"[tts-cast] 完整对话 {len(full)/sample_rate:.1f}s → {full_path}")
        meta.append({"file": str(full_path), "duration_s": round(len(full) / sample_rate, 2),
                     "engine": "qwen3-tts", "role_name": "ALL", "idx": -1})
    (out_dir / "cast_meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[tts-cast] 完成：{len(cast_plan)} 句 / {len(meta)} 条台账 → {out_dir}")
    return 0


def _resample_speed(x, factor: float):
    """按系数变速（>1 加快，<1 减慢），保持采样率。"""
    import numpy as np
    n = int(len(x) / factor)
    if n <= 0:
        return x
    idx = np.linspace(0, len(x) - 1, n)
    return np.interp(idx, np.arange(len(x)), x).astype(np.float32)


def _write_wav(path: Path, samples, sr: int):
    import wave
    import numpy as np
    pcm = np.clip(samples, -1.0, 1.0)
    pcm16 = (pcm * 32767).astype(np.int16)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(pcm16.tobytes())


if __name__ == "__main__":
    sys.exit(main())
