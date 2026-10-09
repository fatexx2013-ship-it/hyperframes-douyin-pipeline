#!/usr/bin/env python3
"""
Edge TTS 配音生成脚本 — 封装 edge-tts CLI，支持语速/音调调节。

用法：
    python scripts/edge_tts.py --input story/001/script.txt --output story/001/narration.mp3
    python scripts/edge_tts.py --voice zh-CN-YunxiNeural --rate "+20%" --output narration.mp3
    python scripts/edge_tts.py --voice-list
"""

import argparse
import logging
import subprocess
import sys


VOICE_MAP = {
    "xiaoxiao": "zh-CN-XiaoxiaoNeural",      # 女声·温暖·新闻/小说（默认）
    "xiaoyi": "zh-CN-XiaoyiNeural",           # 女声·活泼·卡通/小说
    "yunjian": "zh-CN-YunjianNeural",         # 男声·热情·体育/小说
    "yunxi": "zh-CN-YunxiNeural",             # 男声·阳光·小说
    "yunxia": "zh-CN-YunxiaNeural",           # 男声·可爱·卡通/小说
    "yunyang": "zh-CN-YunyangNeural",         # 男声·专业·新闻
}

RATE_DEFAULT = "+10%"  # 科普类稍微加快节奏
PITCH_DEFAULT = "+0Hz"


def main():
    parser = argparse.ArgumentParser(description="Edge TTS 配音生成")
    parser.add_argument("--input", "-i", required=True, help="文案文件路径")
    parser.add_argument("--output", "-o", required=True, help="输出音频文件路径")
    parser.add_argument("--voice", "-v", default="xiaoxiao",
                        help="语音名称（默认 xiaoxiao）")
    parser.add_argument("--rate", default=RATE_DEFAULT,
                        help="语速调节 (default: %(default)s)")
    parser.add_argument("--pitch", default=PITCH_DEFAULT,
                        help="音调调节 (default: %(default)s)")
    parser.add_argument("--voice-list", action="store_true",
                        help="列出所有可用中文语音")
    args = parser.parse_args()

    if args.voice_list:
        print("可用中文 Edge TTS 语音：")
        print(f"{'别名':<15} {'Azure Voice ID':<35} {'类型'}")
        print("-" * 70)
        for alias, voice_id in VOICE_MAP.items():
            print(f"  {alias:<13} {voice_id:<35} (Female/Male)")
        print("\n用法: edge-tts --list-voices 查看所有可用语音")
        return

    # 解析语音 ID
    voice_id = VOICE_MAP.get(args.voice, args.voice)
    if not voice_id.startswith("zh-"):
        # 用户可能直接传了 Azure Voice ID
        voice_id = args.voice

    # 构建 edge-tts 命令
    cmd = [
        "edge-tts",
        "-f", args.input,
        "-v", voice_id,
        "--rate", args.rate,
        "--pitch", args.pitch,
        "--write-media", args.output,
    ]

    print(f"生成配音：{args.input} -> {args.output}")
    print(f"  语音: {voice_id}")
    print(f"  语速: {args.rate}")
    print(f"  音调: {args.pitch}")

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"错误：{result.stderr}", file=sys.stderr)
        sys.exit(1)

    # 获取输出文件时长
    try:
        import subprocess as sp
        dur_result = sp.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "csv=p=0", args.output],
            capture_output=True, text=True, timeout=10
        )
        duration = dur_result.stdout.strip()
        print(f"配音时长: {duration}s")
    except Exception as exc:
        logging.getLogger(__name__).warning("edge_tts 获取配音时长失败: %r", exc)

    print("完成！")


if __name__ == "__main__":
    main()
