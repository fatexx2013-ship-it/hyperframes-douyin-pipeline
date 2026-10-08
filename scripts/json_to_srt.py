#!/usr/bin/env python3
"""
字幕转换脚本 — 将 HyperFrames transcribe 输出的 transcript.json 转为 SRT 格式。

transcript.json 格式（HyperFrames Whisper 输出）：
[
  {"id": "w0", "text": "你好", "start": 0.0, "end": 0.5},
  {"id": "w1", "text": "世界", "start": 0.6, "end": 1.2}
]

用法：
    python scripts/json_to_srt.py story/transcript.json story/captions.srt
    python scripts/json_to_srt.py story/transcript.json story/captions.ass --format ass
"""

import argparse
import json
import sys
from pathlib import Path


def format_time(seconds: float) -> str:
    """将秒数转为 SRT 时间格式 HH:MM:SS,mmm"""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int(round((seconds - int(seconds)) * 1000))
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def normalize_transcript(data):
    """统一不同来源的 transcript 格式为 segment-level 数组 [{text, start, end}]。"""
    if isinstance(data, list):
        # HyperFrames 格式: [{text, start, end}, ...]
        return data
    if isinstance(data, dict):
        if "segments" in data:
            # Whisper 原生格式: 按 segment 分组
            segments = data["segments"]
            words = []
            widx = 0
            for seg in segments:
                text = seg.get("text", "").strip()
                if not text:
                    continue
                words.append({
                    "id": f"w{widx}",
                    "text": text,
                    "start": round(seg["start"], 2),
                    "end": round(seg["end"], 2),
                })
                widx += 1
            return words
        elif "words" in data:
            # 某些 Whisper 变体（word-level 时间戳）
            return data["words"]
    return []


def json_to_srt(words: list, group_size: int = 3) -> str:
    """
    将 word-level 时间戳聚合为句子级 SRT。
    group_size: 每组聚合多少个 word（3-5 个适合中文科普）。
    """
    srt_blocks = []
    idx = 0

    while idx < len(words):
        group = words[idx:idx + group_size]
        if not group:
            break

        start_time = group[0]["start"]
        end_time = group[-1]["end"]
        text = "".join(w.get("text", "") for w in group)

        # 清理空白
        text = text.strip().replace("  ", " ")

        if text:
            srt_blocks.append(
                f"{idx // group_size + 1}\n"
                f"{format_time(start_time)} --> {format_time(end_time)}\n"
                f"{text}"
            )

        idx += group_size

    return "\n\n".join(srt_blocks) + "\n"


def json_to_ass(words: list, group_size: int = 3) -> str:
    """
    将 word-level 时间戳转为 ASS 字幕（支持样式）。
    """
    header = """[Script Info]
Title: Generated Subtitles
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default, PingFang SC, 36, &H00FFFFFF, &H000000FF, &H00000000, &H00000000, 0, 0, 0, 0, 100, 100, 0, 0, 3, 2, 1, 10, 10, 10, 150, 1
Style: Highlight, PingFang SC, 36, &H00FFFF00, &H000000FF, &H00000000, &H00000000, 0, 0, 0, 0, 100, 100, 0, 0, 3, 2, 1, 10, 10, 150, 1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

    events = []
    idx = 0

    while idx < len(words):
        group = words[idx:idx + group_size]
        if not group:
            break

        start = format_time(group[0]["start"]).replace(",", ".")
        end = format_time(group[-1]["end"]).replace(",", ".")
        text = "".join(w.get("text", "") for w in group).strip()

        if text:
            events.append(
                f"Dialogue: 0,{start},{end},Default,,0,0,0,,{text}"
            )

        idx += group_size

    return header + "\n".join(events) + "\n"


def main():
    parser = argparse.ArgumentParser(description="transcript.json -> SRT/ASS")
    parser.add_argument("input", help="transcript.json 路径")
    parser.add_argument("output", help="输出字幕文件路径")
    parser.add_argument("--format", "-f", choices=["srt", "ass"], default="srt",
                        help="输出格式")
    parser.add_argument("--group-size", "-g", type=int, default=1,
                        help="每组聚合的 word 数量（默认 1，适合 segment-level 数据）")
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"错误：找不到文件 {input_path}", file=sys.stderr)
        sys.exit(1)

    words = json.loads(input_path.read_text(encoding="utf-8"))
    words = normalize_transcript(words)

    if args.format == "ass":
        content = json_to_ass(words, args.group_size)
    else:
        content = json_to_srt(words, args.group_size)

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(content, encoding="utf-8")

    print(f"字幕已生成：{output_path} ({args.format.upper()}, {len(words)} words -> {content.count(chr(10))} lines)")


if __name__ == "__main__":
    main()
