#!/usr/bin/env python3
"""
镜头拆分脚本 — 读取 script.txt，按语义拆分为 scene_plan.json。

用法：
    python scripts/split_scenes.py --input story/001/script.txt --output story/001/scene_plan.json
    python scripts/split_scenes.py --input story/001/script.txt --target-duration 45
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path

# ── 视觉主题映射 ─────────────────────────────────────────────

VISUAL_THEMES = [
    "dark-tech particles",
    "abstract data flow",
    "neural network visualization",
    "futuristic cityscape",
    "robot close-up",
    "code on screen",
    "hologram interface",
    "circuit board macro",
    "digital globe",
    "quantum computing visualization",
    "AI chip close-up",
    "augmented reality overlay",
    "smartphone screen recording",
    "laboratory equipment",
    "nature timelapse",
    "crowd of people",
    "office workspace",
    "server room",
    "drone aerial shot",
    "slow motion water",
]

CAMERA_MOVES = [
    "slow-zoom-in",
    "slow-zoom-out",
    "pan-left",
    "pan-right",
    "tilt-up",
    "static",
    "tracking-shot",
    "crane-up",
]

EMOTIONS = [
    "excited",
    "impressed",
    "curious",
    "serious",
    "wonder",
    "urgent",
    "calm",
    "inspiring",
]

# ── LLM 拆分（可选）──────────────────────────────────────────

SYSTEM_SPLIT_PROMPT = """你是一个短视频分镜师。将文案拆分为多个镜头场景。

每个场景需要包含：
- id: 场景编号（scene1, scene2...）
- text: 该场景的文案片段
- duration: 预计时长（秒）
- visual_theme: 视觉主题关键词
- camera: 镜头运动方式
- emotion: 情绪基调

输出 JSON 数组，格式如下：
[
  {
    "id": "scene1",
    "text": "...",
    "duration": 5,
    "visual_theme": "...",
    "camera": "...",
    "emotion": "..."
  }
]"""


def split_with_llm(script_text: str, target_duration: int = 45) -> dict:
    """使用 LLM API 智能拆分镜头。"""
    import httpx

    api_key = os.environ.get("OPENAI_API_KEY")
    base_url = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
    model = os.environ.get("LLM_MODEL", "agnes-2.0-flash")

    if not api_key:
        raise ValueError("请设置环境变量 OPENAI_API_KEY")

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_SPLIT_PROMPT},
            {"role": "user", "content": f"文案：\n{script_text}\n\n目标时长：{target_duration}秒"},
        ],
        "response_format": {"type": "json_object"},
        "temperature": 0.7,
        "max_tokens": 2000,
    }

    resp = httpx.post(base_url + "/chat/completions", json=payload, headers=headers, timeout=120)
    resp.raise_for_status()
    content = resp.json()["choices"][0]["message"]["content"]

    # 解析可能包裹在 code block 中的 JSON
    content = re.sub(r"^```(?:json)?\s*", "", content.strip())
    content = re.sub(r"\s*\```$", "", content.strip())

    scenes_data = json.loads(content)

    # 兼容 LLM 可能返回的嵌套结构
    if isinstance(scenes_data, dict):
        # 检查是否是单个 scene 对象（LLM 没按要求输出数组）
        if "duration" in scenes_data and "text" in scenes_data:
            scenes_data = [scenes_data]
        else:
            for key in ("scenes", "shots", "data"):
                if key in scenes_data:
                    scenes_data = scenes_data[key]
                    break
            else:
                scenes_data = [scenes_data]
    if isinstance(scenes_data, dict):
        scenes_data = [scenes_data]

    # 标准化 scene id（整数→字符串）
    for i, s in enumerate(scenes_data):
        if "id" in s and not isinstance(s["id"], str):
            s["id"] = f"scene{s['id']}" if isinstance(s["id"], int) else f"scene{i+1}"

    total_duration = sum(s.get("duration", 5) for s in scenes_data)
    # 归一化到目标时长
    if total_duration > 0 and abs(total_duration - target_duration) > 5:
        scale = target_duration / total_duration
        for s in scenes_data:
            s["duration"] = max(3, round(s["duration"] * scale))

    return {
        "total_duration": sum(s["duration"] for s in scenes_data),
        "scenes": scenes_data,
    }


def split_heuristic(script_text: str, target_duration: int = 45) -> dict:
    """启发式拆分（不依赖 LLM，使用规则分割）。"""
    # 按空行或句号分段
    paragraphs = re.split(r'\n\s*\n|\.(?:\s|$)', script_text)
    paragraphs = [p.strip() for p in paragraphs if p.strip()]

    # 合并短句
    chunks = []
    current = ""
    for p in paragraphs:
        if len(current) + len(p) > 60 and current:
            chunks.append(current)
            current = p
        else:
            current += ". " + p if current else p

    if current:
        chunks.append(current)

    # 估算时长：每段约 3-5 字/秒
    scenes = []
    per_scene_duration = max(4, round(target_duration / max(len(chunks), 1)))

    for i, chunk in enumerate(chunks):
        # 清理前导标点
        chunk = chunk.lstrip(". 。、")

        # 随机但确定性地选择视觉元素
        hash_val = sum(ord(c) for c in chunk)
        theme = VISUAL_THEMES[hash_val % len(VISUAL_THEMES)]
        camera = CAMERA_MOVES[hash_val % len(CAMERA_MOVES)]
        emotion = EMOTIONS[hash_val % len(EMOTIONS)]

        scenes.append({
            "id": f"scene{i + 1}",
            "text": chunk,
            "duration": per_scene_duration,
            "visual_theme": theme,
            "camera": camera,
            "emotion": emotion,
        })

    # 调整总时长
    total = sum(s["duration"] for s in scenes)
    if total > target_duration:
        # 缩短最后一句
        scenes[-1]["duration"] -= (total - target_duration)

    return {
        "total_duration": sum(s["duration"] for s in scenes),
        "scenes": scenes,
    }


def main():
    parser = argparse.ArgumentParser(description="拆分文案为镜头场景")
    parser.add_argument("--input", "-i", required=True, help="文案文件路径")
    parser.add_argument("--output", "-o", default=None, help="输出 scene_plan.json 路径")
    parser.add_argument("--target-duration", "-d", type=int, default=45, help="目标时长（秒）")
    parser.add_argument("--mode", choices=["llm", "heuristic"], default="llm",
                        help="拆分模式")
    args = parser.parse_args()

    script_path = Path(args.input)
    if not script_path.exists():
        print(f"错误：找不到文件 {script_path}", file=sys.stderr)
        sys.exit(1)

    script_text = script_path.read_text(encoding="utf-8")

    if args.mode == "llm":
        try:
            plan = split_with_llm(script_text, args.target_duration)
        except Exception as e:
            print(f"LLM 拆分失败：{e}，回退到启发式拆分", file=sys.stderr)
            plan = split_heuristic(script_text, args.target_duration)
    else:
        plan = split_heuristic(script_text, args.target_duration)

    # 确定输出路径
    if args.output:
        output_path = Path(args.output)
    else:
        output_path = script_path.with_suffix(".json")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"镜头拆分完成：{output_path}")
    print(f"共 {len(plan['scenes'])} 个场景，总时长 {plan['total_duration']} 秒")

    for scene in plan["scenes"]:
        print(f"  {scene['id']}: [{scene['duration']}s] {scene['text'][:40]}...")


if __name__ == "__main__":
    main()
