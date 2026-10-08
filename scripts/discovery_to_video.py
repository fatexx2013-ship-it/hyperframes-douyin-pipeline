#!/usr/bin/env python3
"""
github-discovery → 抖音视频生成（两步工作流）

用法:
    # Step 1: 搜索潜力项目
    python scripts/discovery_to_video.py                     # 显示今日 Top 10
    python scripts/discovery_to_video.py --top 5             # 显示前5个
    python scripts/discovery_to_video.py --date 2026-09-13   # 指定日期

    # Step 2: 生成视频（选中项目后）
    python scripts/discovery_to_video.py --generate --repos "repo1 repo2 repo3"
    python scripts/discovery_to_video.py --generate --top 3  # 用今日前3个
    python scripts/discovery_to_video.py --generate --repos "owner/repo owner2/repo2" --voice zh1
"""

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

# ── 路径配置 ──────────────────────────────────────────────────

BASE_DIR = Path(__file__).parent.parent.resolve()
DISCOVERY_DIR = BASE_DIR / "github-discovery"
STORY_BASE = BASE_DIR / "story"
OUTPUT_DIR = BASE_DIR / "output"
DEFAULT_BGM = str(BASE_DIR / "github-hot-top3-20260720" / "bgm.mp3")
HOJO_TTS_SCRIPT = str(BASE_DIR / "scripts" / "hojo_tts.py")

# ── 配色方案 ──────────────────────────────────────────────────

COLORS = [
    ("#f59e0b", "#ef4444"), ("#a855f7", "#ec4899"),
    ("#10b981", "#00d4ff"), ("#ff6b35", "#f59e0b"),
    ("#6366f1", "#a855f7"), ("#14b8a6", "#10b981"),
    ("#f97316", "#ef4444"), ("#06b6d4", "#3b82f6"),
    ("#84cc16", "#10b981"), ("#ec4899", "#f43f5e"),
]

# ── 文案钩子模板 ─────────────────────────────────────────────

HOOK_TEMPLATES = [
    "今天GitHub日榜炸了！{n}个项目一天涨了上千颗星，最后一个直接帮你省下AI账单！",
    "GitHub疯了！{n}个项目一夜爆火，最后一个你绝对想不到！",
    "今天的GitHub热榜太狠了，{n}个项目全是大招，看完直接想写代码！",
    "GitHub日榜又出神仙项目了，{n}个必装神器，最后一个省你大几千！",
    "这几个GitHub项目太狠了，{n}个一天涨几千星，最后一个直接封神！",
]


def pick_hook(n):
    return HOOK_TEMPLATES[hash(datetime.now().strftime("%Y%m%d")) % len(HOOK_TEMPLATES)].format(n=n)


# ── 工具函数 ──────────────────────────────────────────────────

def find_latest_data():
    files = sorted(DISCOVERY_DIR.glob("data/discovery-*.json"))
    if not files:
        print("错误：找不到 discovery 数据文件", file=sys.stderr)
        sys.exit(1)
    return files[-1]


def load_discovery(filepath):
    with open(filepath) as f:
        return json.load(f)


def fmt_stars(n):
    if n >= 10000:
        return f"{n / 10000:.1f}万"
    elif n >= 1000:
        return f"{n / 1000:.1f}千"
    return str(n)


def repo_short_name(full_name):
    return full_name.split("/")[1]


def format_srt_time(seconds):
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int((seconds - int(seconds)) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def run_cmd(cmd, check=True):
    print(f"  $ {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if check and result.returncode != 0:
        print(f"  ERROR: {result.stderr}", file=sys.stderr)
        sys.exit(1)
    return result


# ── 搜索模式 ─────────────────────────────────────────────────

def search_repos(args):
    """Step 1: 搜索并展示潜力项目，等待用户选择。"""
    if args.date:
        data_file = DISCOVERY_DIR / "data" / f"discovery-{args.date}.json"
        if not data_file.exists():
            print(f"错误：找不到数据文件 {data_file}", file=sys.stderr)
            sys.exit(1)
    else:
        data_file = find_latest_data()
    print(f"📊 数据源: {data_file.name}")

    data = load_discovery(data_file)
    today = data["date"]
    new_repos = data.get("new", [])
    if not new_repos:
        print("错误：当天没有发现新项目", file=sys.stderr)
        sys.exit(1)

    top_n = args.top
    repos = new_repos[:top_n]

    print(f"\n🔥 GitHub Discovery — {today}  ·  Top {len(repos)} 潜力项目\n")
    print(f"{'排名':<6}{'项目':<35}{'Stars':>8}{'日增':>10}{'分数':>6}  来源")
    print("-" * 80)

    for i, r in enumerate(repos):
        rank = i + 1
        name = repo_short_name(r["full_name"])
        stars = r.get("stars", 0)
        daily = r.get("real_daily_stars", r.get("daily_stars", 0))
        growth = int(daily) if daily else 0
        score = r.get("scores", {}).get("total", 0)
        source = r.get("source", "?")
        desc = (r.get("description") or "")[:50]
        print(f"  #{rank:<5}{name:<35}{stars:>8}  +{growth:>8}/天  {score:>5}  [{source}]")
        print(f"       {r['full_name']}")
        if desc:
            print(f"       💡 {desc}")
        print()

    print("用法:")
    print(f"  python scripts/discovery_to_video.py --generate --repos \"{' '.join(repo_short_name(r['full_name']) for r in repos)}\"")
    print(f"  python scripts/discovery_to_video.py --generate --top {top_n}")
    print()


# ── 文案生成 ─────────────────────────────────────────────────

def build_script(repos, today):
    n = len(repos)
    hook = pick_hook(n)
    lines = [hook, ""]

    rank_names = ["第三名", "第二名", "第一名"] if n == 3 else \
                 ["第五名", "第四名", "第三名", "第二名", "第一名"] if n == 5 else \
                 [f"第{n-i}名" for i in range(n)]

    for i, r in enumerate(repos):
        name = repo_short_name(r["full_name"])
        stars = r.get("stars", 0)
        daily = r.get("real_daily_stars", r.get("daily_stars", 0))
        growth = int(daily) if daily else 0
        desc = (r.get("description") or "").strip()

        if i == n - 1:
            lines.append(f"第一名：{name}，一天涨{fmt_stars(growth)}星！")
        else:
            lines.append(f"{rank_names[i]}：{name}，一天涨{fmt_stars(growth)}星！")

        if desc:
            d = desc.replace("\n", " ").strip()
            if len(d) > 60:
                d = d[:57] + "..."
            lines.append(f"  {d}")
        lines.append("")

    lines.append(f"这{n}个你想试哪个？评论区告诉我！")
    lines.append("关注我，每天盘点GitHub最火开源项目！")
    return "\n".join(lines)


# ── HTML 生成 ────────────────────────────────────────────────

def build_index_html(repos, today_str, script_text, total_duration):
    n = len(repos)
    hook_dur = 8.0
    cta_dur = 7.0
    per_proj = (total_duration - hook_dur - cta_dur) / max(n, 1)

    scenes = []
    t = 0.0

    # Opening
    hook_text = script_text.split("\n")[0]
    badge = "今日热榜" if "今天" in hook_text else "GitHub日榜"
    title_lines = [l for l in hook_text.split("！") if l.strip()]
    title = title_lines[0] + "！" if title_lines else "GitHub日榜炸了！"

    opening = f'''
      <div id="scene-0" class="scene clip" data-start="{t}" data-duration="{hook_dur}" data-track-index="2">
        <div class="opening-icon">🔥</div>
        <div class="opening-badge">{badge}</div>
        <div class="opening-title">{title}</div>
        <div class="opening-sub">{script_text.split(chr(10))[1] if len(script_text.split(chr(10))) > 1 else ""}</div>
      </div>'''
    scenes.append(("scene-0", t, hook_dur, opening,
        f'''tl.from("#scene-0 .opening-icon", {{ scale: 0, opacity: 0, duration: 0.5, ease: "back.out(1.5)" }}, {t});
      tl.from("#scene-0 .opening-badge", {{ y: 30, opacity: 0, duration: 0.5, ease: "power3.out" }}, {t} + 0.3);
      tl.from("#scene-0 .opening-title", {{ y: 50, opacity: 0, duration: 0.6, ease: "power3.out" }}, {t} + 0.5);
      tl.from("#scene-0 .opening-sub", {{ y: 30, opacity: 0, duration: 0.5, ease: "power2.out" }}, {t} + 0.9);
      tl.to("#scene-0 .opening-badge", {{ scale: 1.05, duration: 0.4, ease: "sine.inOut", yoyo: true, repeat: 4 }}, {t} + 1.5);'''))
    t += hook_dur

    # Projects (reverse order: lowest rank first, highest rank last)
    for i in range(n - 1, -1, -1):
        r = repos[i]
        rank = n - i
        scene_idx = n - (n - 1 - i)
        color1, color2 = COLORS[i % len(COLORS)]
        name = repo_short_name(r["full_name"])
        stars = r.get("stars", 0)
        daily = r.get("real_daily_stars", r.get("daily_stars", 0))
        growth = int(daily) if daily else 0
        desc = (r.get("description") or "").strip()
        lang = r.get("language", "")

        stars_info = f"日增 +{fmt_stars(growth)} · 总星 {fmt_stars(stars)}"
        desc_html = (desc or lang or "GitHub Project").replace("\n", "<br />")[:120]
        if len(desc_html) > 120:
            desc_html = desc_html[:117] + "..."

        tags_html = ""
        if lang:
            tags_html += f'<span class="project-tag">{lang}</span>'
        desc_lower = (r.get("description") or "").lower()
        if "agent" in name.lower() or "agent" in desc_lower:
            tags_html += '<span class="project-tag">Agent</span>'
        if "ai" in desc_lower:
            tags_html += '<span class="project-tag">AI</span>'

        rank_text = f"第 {rank} 名" if rank > 1 else "🏆 第 一 名 🏆"
        dur = round(per_proj, 1)

        html = f'''
      <div id="scene-{scene_idx}" class="scene clip" data-start="{round(t,1)}" data-duration="{dur}" data-track-index="{scene_idx + 2}">
        <div class="rank-number" style="background: linear-gradient(180deg, {color1} 0%, {color2} 100%); -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text;">{rank}</div>
        <div class="rank-label">{rank_text}</div>
        <div class="project-name">{name}</div>
        <div class="project-stars"><span>⭐</span><span>{stars_info}</span></div>
        <div class="project-desc">{desc_html}</div>
        <div class="tags-row">{tags_html}</div>
      </div>'''
        gsap = f'''tl.from("#scene-{scene_idx} .rank-number", {{ x: -100, opacity: 0, rotate: -10, duration: 0.6, ease: "expo.out" }}, {round(t,1)});
      tl.from("#scene-{scene_idx} .rank-label", {{ y: 20, opacity: 0, duration: 0.4, ease: "power2.out" }}, {round(t,1)} + 0.4);
      tl.from("#scene-{scene_idx} .project-name", {{ y: 30, opacity: 0, duration: 0.5, ease: "power3.out" }}, {round(t,1)} + 0.7);
      tl.from("#scene-{scene_idx} .project-stars", {{ scale: 0.8, opacity: 0, duration: 0.4, ease: "back.out(1.3)" }}, {round(t,1)} + 1.1);
      tl.from("#scene-{scene_idx} .project-desc", {{ y: 20, opacity: 0, duration: 0.5, ease: "power2.out" }}, {round(t,1)} + 1.5);
      tl.from("#scene-{scene_idx} .tags-row .project-tag", {{ y: 15, opacity: 0, duration: 0.35, ease: "power2.out", stagger: 0.1 }}, {round(t,1)} + 1.9);'''
        scenes.append((f"scene-{scene_idx}", t, per_proj, html, gsap))
        t += per_proj

    # CTA
    html = f'''
      <div id="scene-{n+1}" class="scene clip" data-start="{round(t,1)}" data-duration="{cta_dur}" data-track-index="{n+3}">
        <div class="ending-icon">💬</div>
        <div class="ending-title">这{n}个<br />你想试哪个？</div>
        <div class="ending-cta">评论区告诉我！</div>
        <div class="ending-sub">关注我，每天盘点<br />GitHub 最火开源项目 🔥</div>
      </div>'''
    gsap = f'''tl.from("#scene-{n+1} .ending-icon", {{ scale: 0, rotate: -180, opacity: 0, duration: 0.6, ease: "back.out(1.5)" }}, {round(t,1)});
      tl.from("#scene-{n+1} .ending-title", {{ y: 40, opacity: 0, duration: 0.6, ease: "power3.out" }}, {round(t,1)} + 0.3);
      tl.from("#scene-{n+1} .ending-cta", {{ y: 20, opacity: 0, duration: 0.5, ease: "power2.out" }}, {round(t,1)} + 0.9);
      tl.from("#scene-{n+1} .ending-sub", {{ y: 20, opacity: 0, duration: 0.5, ease: "power2.out" }}, {round(t,1)} + 1.4);
      tl.to("#scene-{n+1} .ending-cta", {{ scale: 1.08, duration: 0.5, ease: "sine.inOut", yoyo: true, repeat: 4 }}, {round(t,1)} + 1.9);'''
    scenes.append((f"scene-{n+1}", t, cta_dur, html, gsap))

    # Captions
    caption_lines = [l.strip() for l in script_text.split("\n") if l.strip()]
    captions = []
    t_cap = 0.5
    dur_per_line = (total_duration - 1.0) / max(len(caption_lines), 1)
    for line in caption_lines:
        s = round(t_cap, 2)
        e = round(t_cap + dur_per_line * 0.85, 2)
        captions.append({"text": line, "start": s, "end": min(e, total_duration)})
        t_cap += dur_per_line

    caption_js = ",\n        ".join(
        f'{{ text: "{c["text"].replace(chr(34), chr(92)+chr(34))}", start: {c["start"]}, end: {c["end"]}}}'
        for c in captions
    )

    scenes_html = "\n".join(s[3] for s in scenes)
    gsap_blocks = "\n".join(s[4] for s in scenes)

    html = f"""<!doctype html>
<html lang="zh-CN">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=1080, height=1920" />
    <script src="https://cdn.jsdelivr.net/npm/gsap@3.14.2/dist/gsap.min.js"></script>
    <style>
      * {{ margin: 0; padding: 0; box-sizing: border-box; }}
      html, body {{ margin: 0; width: 1080px; height: 1920px; overflow: hidden; background: #0a0a0f; font-family: "PingFang SC", "Noto Sans CJK SC", "Microsoft YaHei", sans-serif; }}
      .bg-layer {{ position: absolute; inset: 0; z-index: 0; }}
      .bg-grid {{ position: absolute; inset: 0; background-image: linear-gradient(rgba(255,255,255,0.02) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,0.02) 1px, transparent 1px); background-size: 60px 60px; }}
      .bg-g1 {{ position: absolute; top: -10%; left: -20%; width: 800px; height: 800px; background: radial-gradient(circle, rgba(255,107,53,0.18) 0%, transparent 60%); }}
      .bg-g2 {{ position: absolute; bottom: -15%; right: -20%; width: 900px; height: 900px; background: radial-gradient(circle, rgba(0,212,255,0.12) 0%, transparent 60%); }}
      .scene {{ position: absolute; inset: 0; display: flex; flex-direction: column; justify-content: center; align-items: center; padding: 80px 60px; z-index: 2; }}
      .opening-icon {{ font-size: 120px; margin-bottom: 40px; }}
      .opening-badge {{ padding: 16px 36px; background: rgba(255,107,53,0.15); border: 2px solid rgba(255,107,53,0.4); border-radius: 999px; font-size: 32px; font-weight: 700; color: #ff6b35; letter-spacing: 0.08em; margin-bottom: 48px; }}
      .opening-title {{ font-size: 92px; font-weight: 900; line-height: 1.2; text-align: center; background: linear-gradient(135deg, #ffffff 0%, #ff6b35 100%); -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text; margin-bottom: 32px; }}
      .opening-sub {{ font-size: 40px; color: #8888a0; text-align: center; font-weight: 500; line-height: 1.5; }}
      .rank-number {{ font-size: 200px; font-weight: 900; line-height: 1; margin-bottom: 24px; font-family: "Impact", "Arial Black", sans-serif; }}
      .rank-label {{ font-size: 36px; color: #8888a0; font-weight: 600; margin-bottom: 48px; letter-spacing: 0.1em; }}
      .project-name {{ font-size: 64px; font-weight: 800; color: #ffffff; text-align: center; margin-bottom: 24px; font-family: "JetBrains Mono", "Consolas", monospace; }}
      .project-stars {{ display: inline-flex; align-items: center; gap: 16px; padding: 16px 36px; background: rgba(245,158,11,0.1); border: 2px solid rgba(245,158,11,0.3); border-radius: 999px; font-size: 36px; font-weight: 700; color: #f59e0b; margin-bottom: 48px; }}
      .project-desc {{ font-size: 40px; color: #d0d0e0; text-align: center; line-height: 1.6; font-weight: 500; max-width: 900px; }}
      .project-desc strong {{ color: #00d4ff; font-weight: 700; }}
      .tags-row {{ margin-top: 32px; display: flex; flex-wrap: wrap; justify-content: center; gap: 12px; }}
      .project-tag {{ display: inline-block; padding: 8px 20px; background: rgba(0,212,255,0.1); border: 1px solid rgba(0,212,255,0.3); border-radius: 8px; font-size: 24px; color: #00d4ff; margin: 0 6px; font-family: "JetBrains Mono", monospace; }}
      .ending-icon {{ font-size: 100px; margin-bottom: 40px; }}
      .ending-title {{ font-size: 72px; font-weight: 800; color: #ffffff; text-align: center; margin-bottom: 32px; line-height: 1.3; }}
      .ending-cta {{ font-size: 42px; color: #ff6b35; font-weight: 700; text-align: center; margin-bottom: 24px; }}
      .ending-sub {{ font-size: 32px; color: #8888a0; text-align: center; font-weight: 500; }}
      .caption-bar {{ position: absolute; bottom: 180px; left: 0; right: 0; z-index: 10; display: flex; justify-content: center; padding: 0 60px; }}
      .caption-text {{ font-size: 42px; font-weight: 700; color: #ffffff; text-align: center; line-height: 1.5; text-shadow: 0 2px 8px rgba(0,0,0,0.8), 0 0 30px rgba(0,0,0,0.5); max-width: 960px; }}
      .watermark {{ position: absolute; top: 48px; left: 60px; right: 60px; display: flex; justify-content: space-between; align-items: center; z-index: 5; }}
      .watermark-left {{ font-size: 28px; font-weight: 700; color: rgba(255,255,255,0.4); display: flex; align-items: center; gap: 12px; }}
      .watermark-right {{ font-size: 24px; color: rgba(255,255,255,0.3); font-family: "JetBrains Mono", monospace; }}
      .progress-bar {{ position: absolute; top: 0; left: 0; height: 4px; background: linear-gradient(90deg, #ff6b35, #a855f7); z-index: 20; width: 0%; }}
    </style>
  </head>
  <body>
    <div id="root" data-composition-id="main" data-start="0" data-duration="{total_duration}" data-width="1080" data-height="1920">
      <div id="progress-bar" class="progress-bar clip" data-start="0" data-duration="{total_duration}" data-track-index="100"></div>
      <div class="bg-layer clip" data-start="0" data-duration="{total_duration}" data-track-index="0">
        <div class="bg-grid"></div>
        <div class="bg-g1"></div>
        <div class="bg-g2"></div>
      </div>
      <div class="watermark clip" data-start="0" data-duration="{total_duration}" data-track-index="1">
        <div class="watermark-left"><span>🔥</span><span>GitHub热榜</span></div>
        <div class="watermark-right">{today_str}</div>
      </div>
{scenes_html}
      <div class="caption-bar clip" data-start="0" data-duration="{total_duration}" data-track-index="10">
        <div id="caption" class="caption-text"></div>
      </div>
      <audio id="bgm-audio" data-start="0" data-duration="{total_duration}" data-track-index="50" src="bgm.mp3" data-volume="0.22"></audio>
      <audio id="narration-audio" data-start="0" data-duration="{total_duration}" data-track-index="51" src="narration.mp3" data-volume="1.0"></audio>
    </div>
    <script>
      window.__timelines = window.__timelines || {{}};
      const tl = gsap.timeline({{ paused: true }});
      const DUR = {total_duration};
      tl.to("#progress-bar", {{ width: "100%", duration: DUR, ease: "none" }}, 0);
{gsap_blocks}
      const captions = [
        {caption_js}
      ];
      const captionEl = document.getElementById("caption");
      captions.forEach((cap, i) => {{
        tl.call(() => {{ captionEl.innerHTML = cap.text; }}, null, cap.start);
        tl.fromTo(captionEl, {{ opacity: 0, y: 10 }}, {{ opacity: 1, y: 0, duration: 0.2, ease: "power2.out" }}, cap.start);
        if (i < captions.length - 1) {{
          tl.to(captionEl, {{ opacity: 0.35, duration: 0.15, ease: "power2.in" }}, cap.end - 0.15);
        }}
      }});
      window.__timelines["main"] = tl;
    </script>
  </body>
</html>"""
    return html


# ── 生成模式 ─────────────────────────────────────────────────

def generate_video(args):
    """Step 2: 从选定项目生成抖音视频。"""
    # 加载数据
    if args.date:
        data_file = DISCOVERY_DIR / "data" / f"discovery-{args.date}.json"
    else:
        data_file = find_latest_data()
    data = load_discovery(data_file)
    today = data["date"]

    # 确定要用的项目
    if args.repos:
        repo_names = args.repos.split()
        all_repos = data.get("new", []) + data.get("repeat", [])
        repos = []
        for name in repo_names:
            for r in all_repos:
                if repo_short_name(r["full_name"]) == name or r["full_name"] == name:
                    repos.append(r)
                    break
        if len(repos) != len(repo_names):
            print(f"警告：{len(repo_names) - len(repos)} 个项目未在数据中找到", file=sys.stderr)
    else:
        top_n = args.top
        repos = data.get("new", [])[:top_n]

    if not repos:
        print("错误：没有找到任何项目", file=sys.stderr)
        sys.exit(1)

    print(f"🎯 生成视频 — {len(repos)} 个项目")
    for i, r in enumerate(repos):
        print(f"  #{i+1} {r['full_name']}  ⭐{r.get('stars',0)}")

    # 创建故事目录
    date_str = today.replace("-", ".")
    story_dir = STORY_BASE / f"github-{date_str}"
    story_dir.mkdir(parents=True, exist_ok=True)
    print(f"\n📁 {story_dir}")

    # 生成文案
    script_text = build_script(repos, today)
    script_path = story_dir / "script.txt"
    script_path.write_text(script_text, encoding="utf-8")
    print(f"📝 文案 ({len(script_text)} 字)")

    # 生成配音（Hojo TTS）
    narration_path = story_dir / "narration.mp3"
    voice = args.voice or "zh1"
    print(f"\n🎙️  Hojo-TTS-Light ({voice}) 配音...")
    run_cmd(["python3", HOJO_TTS_SCRIPT,
             "--input", str(script_path),
             "--output", str(narration_path),
             "--voice", voice])

    # 生成字幕
    srt_path = story_dir / "captions.srt"
    caption_lines = [l.strip() for l in script_text.split("\n") if l.strip()]
    srt_dur = args.duration
    srt_per_line = srt_dur / max(len(caption_lines), 1)
    srt_content = ""
    for i, line in enumerate(caption_lines):
        s = i * srt_per_line
        e = min((i + 1) * srt_per_line, srt_dur)
        srt_content += f"{i + 1}\n{format_srt_time(s)} --> {format_srt_time(e)}\n{line}\n\n"
    srt_path.write_text(srt_content.strip() + "\n", encoding="utf-8")
    print(f"   字幕: {srt_path.name}")

    # 生成 HTML
    html_path = story_dir / "index.html"
    html_path.write_text(
        build_index_html(repos, date_str, script_text, args.duration),
        encoding="utf-8"
    )
    print(f"🎬 HTML: {html_path.name}")

    # 复制 BGM
    if os.path.exists(DEFAULT_BGM):
        import shutil
        shutil.copy2(DEFAULT_BGM, story_dir / "bgm.mp3")
        print(f"   BGM 已复制")

    # 渲染
    if not args.skip_hyperframes and not args.no_render:
        print(f"\n🔄 HyperFrames 渲染...")
        orig = os.getcwd()
        os.chdir(story_dir)
        try:
            run_cmd(["npx", "hyperframes", "render", "--fps", "30",
                     "--quality", "high", "--output", "composition.mp4"], check=False)
        finally:
            os.chdir(orig)

        if not args.no_render and (story_dir / "composition.mp4").exists():
            print(f"\n🎞️  FFmpeg 终合成...")
            env = os.environ.copy()
            env["STORY_DIR"] = str(story_dir)
            env["VIDEO_WIDTH"] = "1080"
            env["VIDEO_HEIGHT"] = "1920"
            env["FPS"] = "30"
            env["CRF"] = "20"
            result = subprocess.run(
                ["bash", str(BASE_DIR / "scripts" / "render.sh")],
                env=env, capture_output=True, text=True
            )
            if result.returncode == 0:
                alt = Path(story_dir).parent / "output" / "final.mp4"
                output_video = alt if alt.exists() else Path(story_dir).parent / "output" / f"github-{date_str}.mp4"
                print(f"\n✅ 完成: {output_video}")
            else:
                print(f"⚠️  FFmpeg 合成失败（可手动运行 ./scripts/render.sh）")
    else:
        print(f"\n⏭️  跳过渲染")

    print(f"\n🎉 完成！")
    print(f"   文案:   {script_path.name}")
    print(f"   配音:   {narration_path.name}")
    print(f"   字幕:   {srt_path.name}")
    print(f"   页面:   {html_path.name}")


# ── 主入口 ──────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="github-discovery → 抖音视频（两步工作流）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 搜索潜力项目
  python scripts/discovery_to_video.py
  python scripts/discovery_to_video.py --top 5
  python scripts/discovery_to_video.py --date 2026-09-13

  # 生成视频
  python scripts/discovery_to_video.py --generate --repos "DeskcommCRM iloader Sonarr"
  python scripts/discovery_to_video.py --generate --top 3 --voice zh1
  python scripts/discovery_to_video.py --generate --repos "OmniRoute" --duration 40
        """,
    )
    parser.add_argument("--top", type=int, default=10, help="搜索时显示数量 (默认: 10)")
    parser.add_argument("--date", default=None, help="指定日期 (默认: 最新)")
    parser.add_argument("--voice", default="zh1",
                        choices=["zh1", "female_zh_95", "female_zh_89"],
                        help="Hojo TTS 语音 (默认: zh1)")
    parser.add_argument("--duration", type=float, default=50.0, help="目标时长秒数 (默认: 50)")

    gen = parser.add_argument_group("生成模式")
    gen.add_argument("--generate", action="store_true", help="生成视频（需先 --search）")
    gen.add_argument("--repos", default=None, help="指定项目名（空格分隔），如 'Repo1 Repo2'")
    gen.add_argument("--skip-hyperframes", action="store_true", help="跳过 HyperFrames 渲染")
    gen.add_argument("--no-render", action="store_true", help="只到配音+HTML，不跑 FFmpeg")

    args = parser.parse_args()

    if args.generate:
        generate_video(args)
    else:
        search_repos(args)


if __name__ == "__main__":
    main()
