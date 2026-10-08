#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""make_covers.py —— KB-A3 封面×标题 2×2（v1.13.0）

一次产出 4 张封面（2 个标题版本 × 2 个封面底帧），全部 1080x1920（与成片同尺寸，
不破坏竖屏尺寸不变量）：
  标题版 A = script.json 的 title 全文（信息完整）
  标题版 B = title 的短版（取主句，主体更醒目）——可用 cover_title_b 直接指定
  底帧 A   = 片头稳定帧（默认 0.5s，避开入场动画）
  底帧 B   = 片中高信息帧（默认 duration*0.35，可用 --frame-b 覆盖）

样式锚点与成片一致：主题色 #FF5926、底衬 rgba(27,30,36,.94)、PingFang SC、
右下角水印。字体内嵌失败时回退 Hiragino Sans GB → Songti → 系统默认，并在报告中
标记 font_used（封面为宣发物料，不参与两段门禁判据）。

输出：story/<name>/covers/cover_{A|B}{1|2}.jpg + qc/covers.json 报告。

用法：
  python3 scripts/make_covers.py story/<name> [--out DIR] [--title-b "..."]
          [--frame-a 0.5] [--frame-b 27.4] [--video PATH] [--quiet]
"""
import argparse
import glob
import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime

from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 跨平台适配层（真源 scripts/platform_env.py）：工具与中文字体按平台探测，
# 支持环境变量覆盖（FONT_FILE / STORY_FONT_FAMILY / PIPELINE_FFMPEG ...）。
_SDIR = os.path.dirname(os.path.abspath(__file__))
if _SDIR not in sys.path:
    sys.path.insert(0, _SDIR)
import platform_env  # noqa: E402


def _which(name: str) -> str:
    """解析可执行文件：环境变量 → PATH → 平台常见安装位（跨平台）。"""
    return platform_env.find_tool(name) or name


THEME = (255, 89, 38)
INK = (242, 242, 245)
INK3 = (154, 154, 163)
CARD = (27, 30, 36)
W, H = 1080, 1920


def _ts() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def pick_font(size: int):
    """按平台挑中文字体：macOS PingFang / Linux Noto Sans CJK / Windows 微软雅黑。

    三个平台都找不到时抛 FontNotFound，报错含各平台安装命令（不静默退回 PIL 默认字体，
    否则封面会出现方块字）。
    """
    hit = platform_env.require_font_file(purpose="封面渲染中文字体")
    try:
        return ImageFont.truetype(hit, size), os.path.basename(hit)
    except OSError as exc:
        raise platform_env.FontNotFound(
            f"字体文件无法被 PIL 加载：{hit}（{exc}）\n"
            f"  请更换字体文件：export {platform_env.FONT_FILE_ENV}=/绝对/路径/字体.ttf|ttc\n"
            f"  自检：python3 scripts/doctor.py"
        ) from exc


def wrap(draw, text, font, max_w):
    out, cur = [], ""
    for ch in text:
        if draw.textlength(cur + ch, font=font) <= max_w:
            cur += ch
        else:
            out.append(cur)
            cur = ch
    if cur:
        out.append(cur)
    return out


def short_title(t: str) -> str:
    """标题版 B：取主句/前段，改成更醒目的短钩子（确定性，不新增事实主张）。

    1) 按声明分隔符切主句（含中文问号/叹号），取长度 4-14 字的一段；
       切点是问号/叹号时保留该标点（"Photoshop 太贵？"）。
    2) 切不出合规主句 → 退化为截断（前 12 字 + "…"）。
    3) 本身已很短且切不动 → 原样返回（此时 A/B 会重合，报告里标 degenerate）。
    """
    for sep in ("？", "?", "！", "!", "·", "｜", "|", "：", ":", "—", "，", ","):
        if sep in t:
            head = t.split(sep)[0].strip()
            if 4 <= len(head) <= 14:
                return head + ("？" if sep in ("？", "?") else "")
    if len(t) > 14:
        return t[:12].rstrip() + "…"
    return t


def compose(frame: str, title: str, out: str, brand: str, tag: str, font_used: list):
    img = Image.open(frame).convert("RGB").resize((W, H), Image.LANCZOS)
    top = img.crop((0, 0, W, int(H * 0.58)))
    dark = Image.new("RGB", top.size, (8, 10, 13))
    img.paste(Image.blend(top, dark, 0.34), (0, 0))

    d = ImageDraw.Draw(img, "RGBA")
    # 顶部品牌条（与成片 topbar 同位置语义：56px 边距）
    fb, _ = pick_font(30)
    d.text((56, 62), f"{brand} · 开源情报站", font=fb, fill=INK3)
    d.text((W - 56 - d.textlength(tag, font=fb), 62), tag, font=fb, fill=INK3)
    d.line([(56, 120), (W - 56, 120)], fill=(255, 89, 38, 46), width=2)
    # 主题色强调块 + 标题
    d.rectangle([56, 236, 56 + 96, 246], fill=THEME)
    ft, tname = pick_font(96) if len(title) <= 12 else pick_font(78)
    font_used.append(tname)
    y = 292
    for ln in wrap(d, title, ft, W - 112)[:3]:
        d.text((56, y), ln, font=ft, fill=INK)
        y += int(ft.size * 1.28)
    # 底部信息卡（与成片卡片同底色/同圆角风格）
    card_h = 130
    d.rounded_rectangle([56, H - 300, W - 56, H - 300 + card_h], radius=18,
                        fill=tuple(CARD) + (240,))
    fs, _ = pick_font(34)
    d.text((88, H - 300 + 30), "完整数据与出处见片内 · 1080×1920 竖屏",
           font=fs, fill=INK3)
    d.text((88, H - 300 + 74), brand, font=fs, fill=THEME)
    d.text((W - 56 - 40 - d.textlength(tag, font=fs), H - 300 + 74), tag,
           font=fs, fill=INK3)
    img.save(out, "JPEG", quality=92)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("story")
    ap.add_argument("--out", default=None)
    ap.add_argument("--title-b", default=None)
    ap.add_argument("--frame-a", type=float, default=0.5)
    ap.add_argument("--frame-b", type=float, default=None)
    ap.add_argument("--video", default=None)
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args()

    sd = a.story if os.path.isabs(a.story) else (
        os.path.join(ROOT, "story", a.story)
        if os.path.isdir(os.path.join(ROOT, "story", a.story))
        else os.path.join(ROOT, a.story))
    name = os.path.basename(sd.rstrip("/"))
    sp = os.path.join(sd, "script.json")
    if not os.path.isfile(sp):
        print(f"[covers] 编排器侧故障：缺 {sp}", file=sys.stderr)
        return 1
    script = json.loads(open(sp, encoding="utf-8").read())
    video = a.video or os.path.join(sd, "douyin_epilogue.mp4")
    if not os.path.isfile(video):
        video = os.path.join(sd, "douyin.mp4")
    if not os.path.isfile(video):
        print(f"[covers] 编排器侧故障：未找到成片（douyin.mp4 / douyin_epilogue.mp4）",
              file=sys.stderr)
        return 1
    dur = float(subprocess.run(
        [_which("ffprobe"), "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", video],
        capture_output=True, text=True).stdout.strip() or 0)
    fb_at = a.frame_b if a.frame_b is not None else round(dur * 0.35, 3)

    title_full = str(script.get("title") or name)
    title_b = a.title_b or script.get("cover_title_b") or short_title(title_full)
    brand = str(script.get("watermark") or script.get("brand") or name)
    date = str(script.get("date") or "")
    outdir = a.out or os.path.join(sd, "covers")
    os.makedirs(outdir, exist_ok=True)

    tmp = tempfile.mkdtemp(prefix="covers_", dir=outdir)
    frames, font_used = {}, []
    for key, at in (("1", a.frame_a), ("2", fb_at)):
        fp = os.path.join(tmp, f"frame{key}.png")
        r = subprocess.run([_which("ffmpeg"), "-hide_banner", "-loglevel", "error", "-y",
                            "-ss", str(at), "-i", video, "-frames:v", "1", fp],
                           capture_output=True, text=True)
        if r.returncode != 0 or not os.path.isfile(fp):
            print(f"[covers] 编排器侧故障：抽帧失败 @{at}s —— {r.stderr[-200:]}",
                  file=sys.stderr)
            return 1
        frames[key] = fp

    made = []
    for tk, tv in (("A", title_full), ("B", title_b)):
        for fk in ("1", "2"):
            out = os.path.join(outdir, f"cover_{tk}{fk}.jpg")
            compose(frames[fk], tv, out, brand, date, font_used)
            made.append({"file": out, "title_version": tk, "frame_version": fk,
                         "title": tv, "frame_at_s": a.frame_a if fk == "1" else fb_at,
                         "size": list(Image.open(out).size)})
    bad = [m for m in made if m["size"] != [W, H]]
    payload = {
        "check": "covers(KB-A3)",
        "story": name,
        "generated_at": _ts(),
        "video": video,
        "video_duration_s": dur,
        "title_a": title_full,
        "title_b_source": ("cli" if a.title_b else
                           ("script.cover_title_b" if script.get("cover_title_b")
                            else "short_title")),
        "ab_degenerate": title_b == title_full,
        "title_b": title_b,
        "font_used": sorted(set(x for x in font_used if x)),
        "style_anchors": {"theme": "#FF5926", "card_bg": "rgba(27,30,36,.94)",
                          "size": f"{W}x{H}", "font_family": platform_env.font_family()},
        "covers": made,
        "size_ok": not bad,
        "passed": not bad,
    }
    rp = os.path.join(sd, "qc", "covers.json")
    os.makedirs(os.path.dirname(rp), exist_ok=True)
    open(rp, "w", encoding="utf-8").write(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    import shutil
    shutil.rmtree(tmp, ignore_errors=True)

    if not a.quiet:
        print(f"[covers/KB-A3] {name}: 生成 {len(made)} 张封面（2 标题版 × 2 底帧），"
              f"尺寸断言 {'通过' if not bad else '失败'}，字体 {payload['font_used']}")
        for m in made:
            print(f"    {os.path.basename(m['file'])}  标题版{m['title_version']} "
                  f"底帧{m['frame_version']} @{m['frame_at_s']}s  {m['size']}")
        print(f"    报告：{rp}")
    return 0 if not bad else 2


if __name__ == "__main__":
    sys.exit(main())
