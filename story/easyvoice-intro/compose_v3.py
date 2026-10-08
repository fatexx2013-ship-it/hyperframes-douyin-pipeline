#!/usr/bin/env python3
"""easyVoice 介绍视频 - 科技简报风视觉画面版
按用户记忆中的视觉风格：
- 极简深色底 #0a0e14
- Kinetic Typography 大字排版
- 数据卡片
- 青/洋红/绿点缀色
- 右上角水印 jerrychen2001
每句一个独立视觉画面，绝不黑屏。
"""
import os, sys, json, subprocess, math, random
from PIL import Image, ImageDraw, ImageFont

os.environ["PATH"] = "/opt/homebrew/bin:/usr/local/bin:" + os.environ.get("PATH", "")

WORK = "/Volumes/PSSD/抖音视频/story/easyvoice-intro"
META_JSON = os.path.join(WORK, "tts_meta.json")
NARRATION_WAV = os.path.join(WORK, "narration.wav")
FRAMES_DIR = os.path.join(WORK, "vis_frames")
SEGMENTS_DIR = os.path.join(WORK, "vis_segments")
RAW_MP4 = os.path.join(WORK, "douyin_raw.mp4")
DOUYIN_MP4 = os.path.join(WORK, "douyin.mp4")

os.makedirs(FRAMES_DIR, exist_ok=True)
os.makedirs(SEGMENTS_DIR, exist_ok=True)

with open(META_JSON, encoding="utf-8") as f:
    meta = json.load(f)

# ── 色彩系统 ──
W, H = 1080, 1920
BG = (10, 14, 20)
BG2 = (15, 21, 32)
CYAN = (34, 211, 238)
MAGENTA = (244, 114, 182)
GREEN = (74, 222, 128)
AMBER = (251, 191, 36)
WHITE = (229, 237, 247)
DIM = (139, 155, 180)
DIM2 = (91, 107, 133)
LINE = (30, 42, 61)
LINE2 = (42, 58, 85)
FONT_PATH = "/System/Library/Fonts/STHeiti Medium.ttc"
MONO_PATH = "/System/Library/Fonts/Menlo.ttc"

def F(size): return ImageFont.truetype(FONT_PATH, size)
def FM(size): return ImageFont.truetype(MONO_PATH, size)

WM_TEXT = "jerrychen2001"

# ── 工具函数 ──
def draw_bg(draw):
    """深色渐变底"""
    draw.rectangle([0,0,W,H], fill=BG)

def draw_grid(draw, spacing=60, alpha=20):
    """微妙网格"""
    for x in range(0, W, spacing):
        draw.line([x,0,x,H], fill=(20,30,45), width=1)
    for y in range(0, H, spacing):
        draw.line([0,y,W,y], fill=(20,30,45), width=1)

def draw_glow_circle(draw, cx, cy, r, color, alpha=30):
    """光晕圆"""
    for i in range(r, 0, -3):
        a = int(alpha * (i/r))
        c = (*color, a)
        draw.ellipse([cx-i,cy-i,cx+i,cy+i], outline=c)

def draw_card(draw, x, y, w, h, fill=BG2, border=LINE2, radius=16):
    """圆角卡片"""
    draw.rounded_rectangle([x,y,x+w,y+h], radius=radius, fill=fill, outline=border, width=2)

def draw_text_cn(draw, text, x, y, font, color, outline=False):
    """带描边中文"""
    if outline:
        for ox,oy in [(-2,-2),(-2,2),(2,-2),(2,2)]:
            draw.text((x+ox,y+oy), text, fill=(0,0,0), font=font)
    draw.text((x,y), text, fill=color, font=font)

def center_x(text, font, draw):
    bbox = draw.textbbox((0,0), text, font=font)
    return (W - (bbox[2]-bbox[0])) // 2

def draw_watermark(draw):
    """右上角水印"""
    font = FM(28)
    bbox = draw.textbbox((0,0), WM_TEXT, font=font)
    w = bbox[2]-bbox[0]
    # 半透背景
    draw.rectangle([W-w-50, 20, W-30, 60], fill=(10,14,20))
    draw.text((W-w-44, 26), WM_TEXT, fill=(180,180,180,100), font=font)

def draw_top_bar(draw, label, color=CYAN):
    """顶部标签条"""
    font = FM(24)
    draw.rectangle([0,0,W,5], fill=color)
    bbox = draw.textbbox((0,0), label, font=font)
    lw = bbox[2]-bbox[0]
    draw.rectangle([40, 90, 40+lw+24, 130], fill=BG2, outline=color, width=2)
    draw.text((52, 98), label, fill=color, font=font)

def draw_progress_bar(draw, y, progress, color=GREEN):
    """进度条"""
    bar_w = W - 120
    x = 60
    draw.rounded_rectangle([x,y,x+bar_w,y+8], radius=4, fill=LINE)
    if progress > 0:
        draw.rounded_rectangle([x,y,x+int(bar_w*progress),y+8], radius=4, fill=color)

# ── 每句的视觉画面 ──
def frame_01(draw):
    """钩子：10万字→有声书 巨字"""
    draw_bg(draw); draw_grid(draw)
    draw_glow_circle(draw, W//2, 600, 200, CYAN, 15)
    draw_top_bar(draw, "OPEN SOURCE", CYAN)
    # 巨字
    f1 = F(120)
    t1 = "10万字"
    x1 = center_x(t1, f1, draw)
    draw_text_cn(draw, t1, x1, 400, f1, WHITE, outline=True)
    # 箭头
    f2 = F(80)
    draw.text((center_x("↓", f2, draw), 560), "↓", fill=CYAN, font=f2)
    # 有声书
    f3 = F(90)
    t3 = "有声书"
    x3 = center_x(t3, f3, draw)
    draw_text_cn(draw, t3, x3, 700, f3, AMBER, outline=True)
    # 副标
    f4 = F(36)
    sub = "一键转换 · 多角色配音 · 完全免费"
    x4 = center_x(sub, f4, draw)
    draw.text((x4, 880), sub, fill=DIM, font=f4)
    # 底部字幕
    f5 = F(52)
    cap = "10万字的小说，一键变成多角色有声书"
    x5 = center_x(cap, f5, draw)
    draw_text_cn(draw, cap, x5, 1200, f5, WHITE, outline=True)
    f6 = F(44)
    cap2 = "还不花一分钱"
    x6 = center_x(cap2, f6, draw)
    draw_text_cn(draw, cap2, x6, 1280, f6, GREEN, outline=True)
    draw_watermark(draw)

def frame_02(draw):
    """项目名 easyVoice"""
    draw_bg(draw); draw_grid(draw)
    draw_glow_circle(draw, 200, 1600, 150, MAGENTA, 12)
    draw_top_bar(draw, "PROJECT", MAGENTA)
    # 大标题
    f1 = FM(100)
    t1 = "easyVoice"
    x1 = center_x(t1, f1, draw)
    draw.text((x1, 500), t1, fill=WHITE, font=f1)
    # 下划线
    bbox = draw.textbbox((0,0), t1, f1)
    lw = bbox[2]-bbox[0]
    draw.rounded_rectangle([x1, 620, x1+lw, 628], radius=4, fill=CYAN)
    # 副标
    f2 = F(40)
    sub = "开源文字转语音解决方案"
    x2 = center_x(sub, f2, draw)
    draw.text((x2, 700), sub, fill=DIM, font=f2)
    # 三标签
    tags = ["无字数限制", "无时长上限", "完全免费"]
    f3 = F(32)
    tx = 120
    for i, tag in enumerate(tags):
        bbox = draw.textbbox((0,0), tag, f3)
        tw = bbox[2]-bbox[0]
        draw.rounded_rectangle([tx, 850, tx+tw+30, 910], radius=10, fill=BG2, outline=GREEN if i==2 else CYAN, width=2)
        draw.text((tx+15, 862), tag, fill=GREEN if i==2 else CYAN, font=f3)
        tx += tw + 50
    # 底部字幕
    f4 = F(50)
    cap = "专门干一件事——把文字变成声音"
    x4 = center_x(cap, f4, draw)
    draw_text_cn(draw, cap, x4, 1200, f4, WHITE, outline=True)
    draw_watermark(draw)

def frame_03(draw):
    """痛点：两个硬限制"""
    draw_bg(draw); draw_grid(draw)
    draw_top_bar(draw, "PAIN POINT", AMBER)
    f1 = F(56)
    draw_text_cn(draw, "市面 TTS 工具的", 120, 400, f1, DIM)
    draw_text_cn(draw, "两个硬限制", 120, 480, f1, AMBER, outline=True)
    # 限制卡 1
    draw_card(draw, 80, 620, 920, 280, fill=BG2, border=AMBER)
    f2 = F(42)
    draw.text((110, 650), "①", fill=AMBER, font=F(60))
    draw.text((180, 660), "按字数收费", fill=WHITE, font=f2)
    f3 = F(32)
    draw.text((180, 730), "超了就不让用", fill=DIM, font=f3)
    draw.text((180, 780), "越用越贵，长文劝退", fill=DIM2, font=f3)
    # 限制卡 2
    draw_card(draw, 80, 940, 920, 280, fill=BG2, border=AMBER)
    draw.text((110, 970), "②", fill=AMBER, font=F(60))
    draw.text((180, 980), "有时长上限", fill=WHITE, font=f2)
    draw.text((180, 1050), "超了就截断", fill=DIM, font=f3)
    draw.text((180, 1100), "一整本书只能听个开头", fill=DIM2, font=f3)
    # 底部
    f4 = F(44)
    cap = "要么按字数收费，要么有时长上限"
    x4 = center_x(cap, f4, draw)
    draw_text_cn(draw, cap, x4, 1300, f4, WHITE, outline=True)
    draw_watermark(draw)

def frame_04(draw):
    """砍掉限制"""
    draw_bg(draw); draw_grid(draw)
    draw_glow_circle(draw, W//2, 700, 180, GREEN, 20)
    draw_top_bar(draw, "SOLUTION", GREEN)
    f1 = F(80)
    t1 = "全砍了"
    x1 = center_x(t1, f1, draw)
    draw_text_cn(draw, t1, x1, 500, f1, GREEN, outline=True)
    # 对比
    f2 = F(40)
    items = [("字数限制", "✗", AMBER), ("时长上限", "✗", AMBER), ("充值订阅", "✗", AMBER)]
    y = 750
    for label, icon, color in items:
        bbox = draw.textbbox((0,0), label, f2)
        lw = bbox[2]-bbox[0]
        draw_card(draw, 140, y, 800, 100, fill=BG2, border=LINE2)
        draw.text((200, y+28), label, fill=DIM, font=f2)
        draw.text((820, y+20), icon, fill=color, font=F(56))
        y += 120
    f3 = F(50)
    cap = "easyVoice 把这两个限制全砍了"
    x3 = center_x(cap, f3, draw)
    draw_text_cn(draw, cap, x3, 1300, f3, WHITE, outline=True)
    draw_watermark(draw)

def frame_05(draw):
    """核心功能：丢进去→转成有声书"""
    draw_bg(draw); draw_grid(draw)
    draw_top_bar(draw, "CORE", CYAN)
    # 流程图
    f1 = F(36)
    steps = [("10万字\n小说", CYAN), ("AI\n处理", MAGENTA), ("多角色\n有声书", GREEN)]
    y = 500
    step_w = 260
    gap = 40
    total_w = step_w * 3 + gap * 2
    sx = (W - total_w) // 2
    for i, (label, color) in enumerate(steps):
        x = sx + i * (step_w + gap)
        draw_card(draw, x, y, step_w, 200, fill=BG2, border=color)
        lines = label.split("\n")
        for j, line in enumerate(lines):
            f2 = F(44) if j == 0 else F(32)
            lx = center_x(line, f2, draw)
            draw.text((x + (step_w-(draw.textbbox((0,0),line,f2)[2]-draw.textbbox((0,0),line,f2)[0]))//2, y+40+j*60), line, fill=color, font=f2)
        if i < 2:
            ax = x + step_w + 8
            draw.text((ax, y+80), "→", fill=DIM, font=F(50))
    # 底部字幕
    f3 = F(46)
    cap = "一键转成多角色有声书，不同角色不同音色"
    x3 = center_x(cap, f3, draw)
    draw_text_cn(draw, cap, x3, 1300, f3, WHITE, outline=True)
    draw_watermark(draw)

def frame_06(draw):
    """同步字幕"""
    draw_bg(draw); draw_grid(draw)
    draw_top_bar(draw, "FEATURE", MAGENTA)
    f1 = F(70)
    t1 = "语音+字幕"
    x1 = center_x(t1, f1, draw)
    draw_text_cn(draw, t1, x1, 400, f1, MAGENTA, outline=True)
    t2 = "同步出"
    x2 = center_x(t2, f1, draw)
    draw_text_cn(draw, t2, x2, 520, f1, WHITE, outline=True)
    # 模拟字幕画面
    draw_card(draw, 80, 800, 920, 400, fill=BG2, border=LINE2)
    f2 = F(44)
    draw.text((140, 860), "「从前有座山，", fill=CYAN, font=f2)
    draw.text((140, 930), " 山里有座庙，", fill=CYAN, font=f2)
    draw.text((140, 1000), " 庙里有个老和尚」", fill=AMBER, font=f2)
    # 字幕标记
    f3 = F(28)
    draw.text((140, 1100), "[字幕同步显示]", fill=GREEN, font=f3)
    f4 = F(46)
    cap = "语音和文字一起出，听着看都行"
    x4 = center_x(cap, f4, draw)
    draw_text_cn(draw, cap, x4, 1350, f4, WHITE, outline=True)
    draw_watermark(draw)

def frame_07(draw):
    """流式传输"""
    draw_bg(draw); draw_grid(draw)
    draw_top_bar(draw, "TECH", CYAN)
    f1 = F(64)
    t1 = "流式传输"
    x1 = center_x(t1, f1, draw)
    draw_text_cn(draw, t1, x1, 400, f1, CYAN, outline=True)
    # 波形/进度条动画感
    for i in range(5):
        y = 700 + i*80
        draw_progress_bar(draw, y, 1.0 - i*0.15, [CYAN, MAGENTA, GREEN, AMBER, CYAN][i])
    f2 = F(36)
    draw.text((120, 1120), "✓ 不用等整本转完", fill=GREEN, font=f2)
    draw.text((120, 1180), "✓ 多长都能立刻播放", fill=GREEN, font=f2)
    f3 = F(46)
    cap = "多长的文本都能立刻开始播放"
    x3 = center_x(cap, f3, draw)
    draw_text_cn(draw, cap, x3, 1350, f3, WHITE, outline=True)
    draw_watermark(draw)

def frame_08(draw):
    """AI 智能推荐"""
    draw_bg(draw); draw_grid(draw)
    draw_top_bar(draw, "AI", MAGENTA)
    f1 = F(60)
    t1 = "AI 智能推荐"
    x1 = center_x(t1, f1, draw)
    draw_text_cn(draw, t1, x1, 400, f1, MAGENTA, outline=True)
    t2 = "配音风格"
    x2 = center_x(t2, f1, draw)
    draw_text_cn(draw, t2, x2, 500, f1, WHITE, outline=True)
    # 音色卡
    styles = [("御姐音", AMBER), ("少女音", CYAN), ("正太音", GREEN), ("大叔音", MAGENTA)]
    for i, (style, color) in enumerate(styles):
        x = 80 + (i % 2) * 460
        y = 750 + (i // 2) * 200
        draw_card(draw, x, y, 420, 160, fill=BG2, border=color)
        f2 = F(40)
        draw.text((x+40, y+50), style, fill=color, font=f2)
        f3 = F(28)
        draw.text((x+40, y+110), "自动匹配", fill=DIM, font=f3)
    f3 = F(44)
    cap = "你不用懂音色参数，它自己帮你选"
    x3 = center_x(cap, f3, draw)
    draw_text_cn(draw, cap, x3, 1350, f3, WHITE, outline=True)
    draw_watermark(draw)

def frame_09(draw):
    """完全免费 巨字"""
    draw_bg(draw); draw_grid(draw)
    draw_glow_circle(draw, W//2, 700, 250, GREEN, 25)
    draw_top_bar(draw, "KEY POINT", GREEN)
    f1 = F(140)
    t1 = "免费"
    x1 = center_x(t1, f1, draw)
    draw_text_cn(draw, t1, x1, 450, f1, GREEN, outline=True)
    f2 = F(50)
    t2 = "完全"
    x2 = center_x(t2, f2, draw)
    draw.text((x2, 350), t2, fill=DIM, font=f2)
    f3 = F(44)
    cap = "最关键的三个字——完全免费"
    x3 = center_x(cap, f3, draw)
    draw_text_cn(draw, cap, x3, 1300, f3, WHITE, outline=True)
    draw_watermark(draw)

def frame_10(draw):
    """五免费"""
    draw_bg(draw); draw_grid(draw)
    draw_top_bar(draw, "FREE", GREEN)
    f1 = F(50)
    items = [
        ("无时长限制", GREEN), ("无字数限制", GREEN),
        ("不充值", AMBER), ("不订阅", AMBER), ("不弹广告", MAGENTA)
    ]
    y = 400
    for i, (item, color) in enumerate(items):
        bbox = draw.textbbox((0,0), item, f1)
        iw = bbox[2]-bbox[0]
        draw_card(draw, 120, y, 840, 120, fill=BG2, border=color)
        draw.text((180, y+35), "✓", fill=color, font=F(44))
        draw.text((280, y+35), item, fill=WHITE, font=f1)
        y += 140
    draw_watermark(draw)

def frame_11(draw):
    """对比：商业 vs 开源"""
    draw_bg(draw); draw_grid(draw)
    draw_top_bar(draw, "VS", AMBER)
    f1 = F(40)
    draw.text((120, 350), "商业有声书平台", fill=AMBER, font=f1)
    draw.text((120, 410), "一年好几百块", fill=AMBER, font=F(56))
    f2 = F(40)
    draw.text((120, 580), "easyVoice 开源", fill=GREEN, font=f2)
    draw.text((120, 640), "谁都能用，谁都能改", fill=GREEN, font=F(56))
    # 中间分割线
    draw.line([120, 780, 960, 780], fill=LINE2, width=2)
    # GitHub 标记
    draw.text((120, 830), "GitHub 开源", fill=CYAN, font=FM(36))
    draw.text((120, 890), "MIT 协议", fill=DIM, font=FM(28))
    f3 = F(44)
    cap = "代码就放在 GitHub 上"
    x3 = center_x(cap, f3, draw)
    draw_text_cn(draw, cap, x3, 1350, f3, WHITE, outline=True)
    draw_watermark(draw)

def frame_12(draw):
    """听书党"""
    draw_bg(draw); draw_grid(draw)
    draw_glow_circle(draw, 900, 300, 120, CYAN, 15)
    draw_top_bar(draw, "WHO", CYAN)
    f1 = F(80)
    t1 = "听书党"
    x1 = center_x(t1, f1, draw)
    draw_text_cn(draw, t1, x1, 400, f1, CYAN, outline=True)
    f2 = F(40)
    draw.text((140, 600), "手机里攒了半年的小说", fill=WHITE, font=f2)
    draw.text((140, 680), "终于能一口气听完了", fill=GREEN, font=f2)
    # 书堆图标模拟
    for i in range(5):
        x = 200 + i*30
        y = 850 + i*15
        draw.rounded_rectangle([x, y, x+180, y+40], radius=6, fill=BG2, outline=[CYAN,MAGENTA,GREEN,AMBER,CYAN][i], width=2)
    f3 = F(44)
    cap = "手机里攒了半年的小说，终于能一口气听完了"
    x3 = center_x(cap, f3, draw)
    draw_text_cn(draw, cap, x3, 1350, f3, WHITE, outline=True)
    draw_watermark(draw)

def frame_13(draw):
    """创作者"""
    draw_bg(draw); draw_grid(draw)
    draw_top_bar(draw, "WHO", MAGENTA)
    f1 = F(70)
    t1 = "内容创作者"
    x1 = center_x(t1, f1, draw)
    draw_text_cn(draw, t1, x1, 400, f1, MAGENTA, outline=True)
    f2 = F(38)
    draw.text((140, 580), "文章 / 脚本", fill=WHITE, font=f2)
    draw.text((140, 650), "→ 多一个零成本音频分发渠道", fill=GREEN, font=f2)
    # 流程
    f3 = F(36)
    draw_card(draw, 80, 800, 350, 140, fill=BG2, border=CYAN)
    draw.text((150, 850), "文章", fill=CYAN, font=F(48))
    draw.text((440, 860), "→", fill=DIM, font=F(50))
    draw_card(draw, 500, 800, 350, 140, fill=BG2, border=MAGENTA)
    draw.text((540, 850), "音频", fill=MAGENTA, font=F(48))
    draw.text((860, 860), "→", fill=DIM, font=F(50))
    draw.text((900, 850), "✓", fill=GREEN, font=F(60))
    f4 = F(44)
    cap = "你的文章和脚本，多了一个零成本音频分发渠道"
    x4 = center_x(cap, f4, draw)
    draw_text_cn(draw, cap, x4, 1350, f4, WHITE, outline=True)
    draw_watermark(draw)

def frame_14(draw):
    """开发者"""
    draw_bg(draw); draw_grid(draw)
    draw_top_bar(draw, "WHO", GREEN)
    f1 = F(70)
    t1 = "开发者"
    x1 = center_x(t1, f1, draw)
    draw_text_cn(draw, t1, x1, 400, f1, GREEN, outline=True)
    f2 = F(36)
    draw.text((140, 580), "直接拿来做二次开发", fill=WHITE, font=f2)
    draw.text((140, 650), "的 TTS 方案", fill=WHITE, font=f2)
    # 代码块模拟
    draw_card(draw, 80, 780, 920, 400, fill=(7,11,18), border=LINE2)
    f3 = FM(28)
    code_lines = [
        ("from easyvoice import TTS", CYAN),
        ("", DIM),
        ("tts = TTS(voice='yujie')", WHITE),
        ("tts.convert('novel.txt')", WHITE),
        ("# → audio.mp3 + subtitles.srt", GREEN),
        ("# 10万字，一键搞定", AMBER),
    ]
    for i, (line, color) in enumerate(code_lines):
        draw.text((120, 820 + i*50), line, fill=color, font=f3)
    f4 = F(44)
    cap = "可以直接拿来做二次开发的 TTS 方案"
    x4 = center_x(cap, f4, draw)
    draw_text_cn(draw, cap, x4, 1350, f4, WHITE, outline=True)
    draw_watermark(draw)

def frame_15(draw):
    """三类人收藏"""
    draw_bg(draw); draw_grid(draw)
    draw_top_bar(draw, "SUMMARY", AMBER)
    f1 = F(56)
    draw_text_cn(draw, "三类人建议收藏", center_x("三类人建议收藏", f1, draw), 350, f1, AMBER, outline=True)
    # 三人卡
    people = [
        ("① 听书党", "半年没听的小说\n终于能听完了", CYAN),
        ("② 创作者", "文章脚本\n多一个音频渠道", MAGENTA),
        ("③ 开发者", "零成本\nTTS 二次开发", GREEN),
    ]
    for i, (title, desc, color) in enumerate(people):
        y = 550 + i * 280
        draw_card(draw, 80, y, 920, 240, fill=BG2, border=color)
        draw.text((120, y+30), title, fill=color, font=F(48))
        for j, line in enumerate(desc.split("\n")):
            draw.text((120, y+100+j*50), line, fill=DIM, font=F(34))
    draw_watermark(draw)

def frame_16(draw):
    """收尾：评论区见"""
    draw_bg(draw); draw_grid(draw)
    draw_glow_circle(draw, W//2, 700, 200, GREEN, 20)
    draw_top_bar(draw, "END", GREEN)
    f1 = F(90)
    t1 = "评论区见"
    x1 = center_x(t1, f1, draw)
    draw_text_cn(draw, t1, x1, 500, f1, GREEN, outline=True)
    f2 = F(36)
    sub = "项目地址我放评论区了"
    x2 = center_x(sub, f2, draw)
    draw.text((x2, 700), sub, fill=DIM, font=f2)
    # GitHub 标记
    f3 = FM(40)
    draw.text((center_x("github.com", f3, draw), 850), "github.com", fill=CYAN, font=f3)
    f4 = F(44)
    cap = "项目地址我放评论区了，自己去看"
    x4 = center_x(cap, f4, draw)
    draw_text_cn(draw, cap, x4, 1350, f4, WHITE, outline=True)
    draw_watermark(draw)

FRAME_FUNCS = [frame_01, frame_02, frame_03, frame_04, frame_05, frame_06,
               frame_07, frame_08, frame_09, frame_10, frame_11, frame_12,
               frame_13, frame_14, frame_15, frame_16]

# ── 生成所有帧 ──
print("=== 1. 生成 16 帧科技简报风画面 ===")
for i, item in enumerate(meta):
    idx = item["index"]
    frame_path = os.path.join(FRAMES_DIR, f"frame_{idx:02d}.png")
    img = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(img)
    FRAME_FUNCS[i](draw)
    img.save(frame_path, quality=95)
    print(f"  [{idx:02d}] → {frame_path}")

# ── 每帧生成视频段 ──
print("\n=== 2. 生成视频段 ===")
segment_files = []
for item in meta:
    idx = item["index"]
    dur = item["duration"]
    frame_path = os.path.join(FRAMES_DIR, f"frame_{idx:02d}.png")
    seg_path = os.path.join(SEGMENTS_DIR, f"seg_{idx:02d}.mp4")
    cmd = ["ffmpeg","-y","-v","error","-loop","1","-i",frame_path,
           "-t",f"{dur:.2f}","-r","30",
           "-c:v","libx264","-preset","fast","-pix_fmt","yuv420p",
           "-vf","scale=1080:1920", seg_path]
    subprocess.run(cmd, check=True)
    segment_files.append(seg_path)
    print(f"  [{idx:02d}] {dur:.1f}s")

# ── 拼接 + 混音频 ──
print("\n=== 3. 拼接 ===")
concat_list = os.path.join(WORK, "vis_concat.txt")
with open(concat_list, "w") as f:
    for seg in segment_files:
        f.write(f"file '{seg}'\n")
silent_mp4 = os.path.join(WORK, "vis_silent.mp4")
subprocess.run(["ffmpeg","-y","-v","error","-f","concat","-safe","0",
    "-i",concat_list,"-c:v","libx264","-preset","fast","-pix_fmt","yuv420p",silent_mp4], check=True)
subprocess.run(["ffmpeg","-y","-v","error","-i",silent_mp4,"-i",NARRATION_WAV,
    "-c:v","copy","-c:a","aac","-b:a","128k","-ar","44100",
    "-shortest","-movflags","+faststart",RAW_MP4], check=True)
os.remove(silent_mp4)
print(f"粗剪: {RAW_MP4}")

# ── 压缩 ──
print("\n=== 4. 压缩到抖音规格 ===")
subprocess.run(["ffmpeg","-y","-v","error","-i",RAW_MP4,
    "-c:v","libx264","-preset","medium","-profile:v","high","-level","4.2",
    "-pix_fmt","yuv420p","-b:v","8M","-maxrate","10M","-bufsize","12M",
    "-r","30","-g","60",
    "-c:a","aac","-b:a","128k","-ar","44100","-movflags","+faststart",DOUYIN_MP4], check=True)
print(f"成片: {DOUYIN_MP4}")

# ── 片尾 ──
print("\n=== 5. 追加标准片尾 ===")
import shutil
narration_copy = os.path.join(os.path.dirname(DOUYIN_MP4), "narration.wav")
if not os.path.exists(narration_copy):
    shutil.copy2(NARRATION_WAV, narration_copy)
result = subprocess.run(["python3","/Volumes/PSSD/抖音视频/append_epilogue.py",
    os.path.dirname(DOUYIN_MP4),"--force"], capture_output=True, text=True)
print(result.stdout[-300:] if result.stdout else "")
if result.returncode != 0:
    print(f"片尾失败: {result.stderr[-200:]}")

# ── 验收 ──
print("\n=== 6. 验收 ===")
final = os.path.join(os.path.dirname(DOUYIN_MP4), "douyin_epilogue.mp4")
if not os.path.exists(final): final = DOUYIN_MP4
r = subprocess.run(["ffprobe","-v","quiet","-print_format","json",
    "-show_streams","-show_format",final], capture_output=True, text=True)
data = json.loads(r.stdout)
v = next(s for s in data["streams"] if s["codec_type"]=="video")
a = next(s for s in data["streams"] if s["codec_type"]=="audio")
dur = float(data["format"]["duration"])
size = os.path.getsize(final)/1024/1024
fps = eval(v["r_frame_rate"])
checks = [
    ("分辨率", f"{v['width']}x{v['height']}", v['width']==1080 and v['height']==1920),
    ("帧率", f"{fps:.0f}fps", abs(fps-30)<0.5),
    ("编码", v['codec_name'], v['codec_name']=='h264'),
    ("音频", f"{a['codec_name']} {a['sample_rate']}Hz", a['codec_name']=='aac'),
    ("时长", f"{dur:.1f}s", dur<=180),
    ("大小", f"{size:.1f}MB", True),
]
for name, val, ok in checks:
    print(f"  {name}: {val} {'✓' if ok else '✗'}")
print(f"\n成片: {final}")
