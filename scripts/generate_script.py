#!/usr/bin/env python3
"""
文案生成脚本 — 使用 LLM API 生成中文科普类短视频文案。

支持两种模式：
1. OpenAI-compatible API（默认）：OPENAI_BASE_URL + OPENAI_API_KEY + OPENAI_MODEL
2. Anthropic Claude API：ANTHROPIC_API_KEY

用法：
    python scripts/generate_script.py --topic "2025年AI领域最值得关注的5个方向" \
        --output story/001-ai-future/script.txt
    python scripts/generate_script.py --topic "量子计算入门" --tone professional
    python scripts/generate_script.py --topic "大模型微调实战" --style hook
"""

import argparse
import json
import os
import sys
from pathlib import Path

# ── LLM 调用层 ──────────────────────────────────────────────

def call_openai(prompt: str, system: str, api_key: str, base_url: str = None, model: str = None) -> str:
    """通过 OpenAI compatible API 调用大模型。"""
    import httpx

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model or "gpt-4o",
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.8,
        "max_tokens": 2000,
    }

    url = (base_url or "https://api.openai.com/v1") + "/chat/completions"
    resp = httpx.post(url, json=payload, headers=headers, timeout=60)
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]


def call_claude(prompt: str, system: str, api_key: str) -> str:
    """通过 Anthropic Claude API 调用。"""
    import anthropic

    client = anthropic.Anthropic(api_key=api_key)
    msg = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=2000,
        temperature=0.8,
        system=system,
        messages=[{"role": "user", "content": prompt}],
    )
    return msg.content[0].text


# ── 提示词模板 ──────────────────────────────────────────────

SYSTEM_PROMPTS = {
    "hook": """你是一个专业的短视频文案策划师。你的任务是写一篇有吸引力的中文科普短视频文案。

要求：
- 开头必须有强钩子（震撼事实/反常识观点/悬念提问）
- 内容通俗易懂，用比喻和类比解释复杂概念
- 节奏紧凑，每句话都要有信息量
- 结尾要有行动号召（点赞、关注、评论）
- 总字数 200-400 字，适合 45-60 秒口播
- 口语化表达，避免书面语""",

    "professional": """你是一个专业的科普内容创作者。写一篇中文科普短视频文案。

要求：
- 开头简洁引入主题
- 内容准确、有深度但不晦涩
- 适当引用数据或案例增强说服力
- 节奏平稳，适合 45-60 秒口播
- 总字数 250-450 字
- 语言专业但不枯燥""",

    "story": """你是一个讲故事的高手。用叙事的方式写一篇中文科普短视频文案。

要求：
- 以一个故事或场景开头
- 在叙事中自然引入知识点
- 有情感起伏，让听众产生共鸣
- 结尾给出启发性思考
- 总字数 200-400 字，适合 45-60 秒口播""",
}

STYLE_OPTIONS = {
    "hook": "强钩子爆款风",
    "professional": "专业科普风",
    "story": "故事叙述风",
}


def build_user_prompt(topic: str, style: str = "hook") -> str:
    """构建用户 prompt。"""
    return f"""请为以下主题写一篇短视频文案：

主题：{topic}
风格：{STYLE_OPTIONS.get(style, style)}

请直接输出文案正文，每句话占一行。不要输出标题、序号或其他元信息。"""


# ── 主流程 ─────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="生成短视频文案")
    parser.add_argument("--topic", required=True, help="视频主题")
    parser.add_argument("--output", "-o", default=None, help="输出文件路径")
    parser.add_argument("--style", choices=list(SYSTEM_PROMPTS.keys()),
                        default="hook", help="文案风格")
    parser.add_argument("--provider", choices=["openai", "claude"],
                        default="openai", help="LLM 提供商")
    parser.add_argument("--base-url", default=None, help="OpenAI compatible API base URL")
    parser.add_argument("--model", default=None, help="模型名称")
    parser.add_argument("--demo", action="store_true",
                        help="不使用 API，直接输出示例文案（演示模式）")
    args = parser.parse_args()

    # 确定输出路径
    if args.output:
        output_path = Path(args.output)
    else:
        # 默认：story/{sanitized-topic}/script.txt
        safe_topic = "".join(c if c.isalnum() or c == "-" else "_" for c in args.topic)[:30]
        output_path = Path("story") / safe_topic / "script.txt"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # 获取系统提示
    system_prompt = SYSTEM_PROMPTS[args.style]
    user_prompt = build_user_prompt(args.topic, args.style)

    # 生成文案
    if args.demo:
        # 演示模式：直接生成示例文案
        content = generate_demo_script(args.topic, args.style)
    elif args.provider == "claude":
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            print("错误：请设置环境变量 ANTHROPIC_API_KEY", file=sys.stderr)
            sys.exit(1)
        content = call_claude(user_prompt, system_prompt, api_key)
    else:
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            print("错误：请设置环境变量 OPENAI_API_KEY", file=sys.stderr)
            sys.exit(1)
        base_url = args.base_url or os.environ.get("OPENAI_BASE_URL")
        model = args.model or os.environ.get("LLM_MODEL")
        content = call_openai(user_prompt, system_prompt, api_key,
                              base_url=base_url, model=model)

    # 清理输出
    content = content.strip()
    # 移除可能的引号包裹
    if content.startswith('"') and content.endswith('"'):
        content = content[1:-1]

    # 写入文件
    output_path.write_text(content, encoding="utf-8")
    print(f"文案已生成：{output_path}")
    print(f"字数：{len(content)} 字")


def generate_demo_script(topic: str, style: str) -> str:
    """演示模式：生成示例文案。"""
    demos = {
        "hook": (
            "你知道吗？AI 已经在下围棋、写代码、画画甚至做电影了。\n"
            "而这一切，才刚刚开始。\n\n"
            "2025 年，有五个 AI 方向值得所有人关注。\n\n"
            "第一，多模态大模型。不只是文字，AI 现在能看懂图片、听懂声音、理解视频。\n"
            "第二，AI Agent。它能自己规划任务、调用工具、完成复杂工作流。\n"
            "第三，端侧 AI。手机、电脑本地就能跑大模型，不用联网。\n"
            "第四，AI 生成视频。输入一段文字，几秒钟就是一条电影级短片。\n"
            "第五，AI 科学发现。从蛋白质折叠到新材料研发，AI 正在改变科学研究的方式。\n\n"
            "未来三年，这些技术会从实验室走向每个人的生活。\n"
            "你准备好了吗？\n\n"
            "关注我，获取更多 AI 干货。"
        ),
        "professional": (
            "人工智能正在以前所未有的速度重塑我们的世界。\n\n"
            "根据 Gartner 的最新报告，到 2027 年，全球超过 80% 的企业将使用某种形式的 AI 服务。\n\n"
            "今天我们来聊聊最值得关注的五个方向。\n\n"
            "第一，多模态 AI。现在的模型已经不再局限于单一的文字处理，而是能够同时理解文本、图像、音频和视频。\n"
            "这意味着 AI 的应用边界正在被极大拓展。\n\n"
            "第二，AI Agent。自主智能体技术让 AI 不仅能回答问题，还能执行复杂的任务序列。\n\n"
            "第三，边缘 AI。随着模型压缩技术的突破，大模型已经可以在手机上流畅运行。\n\n"
            "第四，AIGC 视频。从文字到视频的生成管线日趋成熟，创作门槛大幅降低。\n\n"
            "第五，AI for Science。在生物学、材料学、药物研发等领域，AI 正在加速科学发现的进程。\n\n"
            "这五个方向的交汇，将定义下一个十年的技术格局。"
        ),
        "story": (
            "三年前，如果有人告诉你 AI 能写诗、能画画、能做视频，你可能不信。\n\n"
            "但现在，这些曾经只出现在科幻电影里的场景，已经成为日常。\n\n"
            "让我给你讲一个真实的故事。\n\n"
            "去年，一位日本游戏开发者只用了一段文字描述，就让 AI 生成了一条两分钟的游戏预告。\n"
            "那条预告的画面质量，让很多玩家误以为是新游戏发布的正式 PV。\n\n"
            "这不是终点。\n\n"
            "现在，有五条技术线索正在汇聚成一个更大的浪潮。\n\n"
            "第一条是多模态——AI 开始像人一样同时用眼睛看、用耳朵听、用心智理解。\n"
            "第二条是 Agent——AI 从被动的问答者变成主动的执行者。\n"
            "第三条是边缘计算——强大的 AI 不再需要云端，就在你的手机里。\n"
            "第四条是视频生成——文字变成画面的门槛，已经降到了零。\n"
            "第五条是科学 AI——AI 不仅在创造内容，还在创造知识。\n\n"
            "当这五条线索交汇的那一天，你会发现：未来不是来的，是被创造的。"
        ),
    }
    return demos.get(style, demos["hook"])


if __name__ == "__main__":
    main()
