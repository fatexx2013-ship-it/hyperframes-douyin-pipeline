#!/usr/bin/env python3
"""easyVoice 介绍视频 v4 - 动效引擎版
核心升级：
1. 每句不再是单张静止图，而是 15fps 连续动画（文字飞入/数字滚动/进度条推进/光晕脉动）
2. 背景升级：径向渐变 + 双色光斑 + 细网格 + 顶部光带
3. 排版升级：大小字对比 + 等宽数字 + 中英混排装饰 + 角标 + 状态条
4. 渲染优化：静态层预渲染，动态层逐帧叠加
"""
import os, sys, json, subprocess, math
from PIL import Image, ImageDraw, ImageFont, ImageFilter

os.environ["PATH"] = "/opt/homebrew/bin:/usr/local/bin:" + os.environ.get("PATH", "")

WORK = "/Volumes/PSSD/抖音视频/story/easyvoice-intro"
META_JSON = os.path.join(WORK, "tts_meta.json")
NARRATION_WAV = os.path.join(WORK, "narration.wav")
ANIM_DIR = os.path.join(WORK, "anim_frames")
RAW_MP4 = os.path.join(WORK, "douyin_raw.mp4")
DOUYIN_MP4 = os.path.join(WORK, "douyin.mp4")
os.makedirs(ANIM_DIR, exist_ok=True)

with open(META_JSON, encoding="utf-8") as f:
    meta = json.load(f)

W, H = 1080, 1920
FONT_PATH = "/System/Library/Fonts/STHeiti Medium.ttc"
MONO_PATH = "/System/Library/Fonts/Menlo.ttc"
_font_cache = {}
def F(size, mono=False):
    key = (size, mono)
    if key not in _font_cache:
        _font_cache[key] = ImageFont.truetype(MONO_PATH if mono else FONT_PATH, size)
    return _font_cache[key]

# 色板
BG = (8, 11, 17)
WHITE = (235, 242, 250)
DIM = (148, 165, 192)
DIM2 = (95, 112, 140)
CYAN = (34, 211, 238)
MAGENTA = (244, 114, 182)
GREEN = (74, 222, 128)
AMBER = (251, 191, 36)
VIOLET = (167, 139, 250)
CARD_BG = (16, 23, 36)
CARD_BG2 = (20, 28, 44)
LINE = (38, 52, 78)
LINE2 = (56, 76, 112)

WM = "jerrychen2001"
ANIM_FPS = 15  # 动画帧率，视频输出时 ×2 → 30fps

def ease_out(t):  # cubic ease-out
    t = max(0.0, min(1.0, t))
    return 1 - (1 - t) ** 3
def ease_in_out(t):
    t = max(0.0, min(1.0, t))
    return t * t * (3 - 2 * t)
def lerp(a, b, t): return a + (b - a) * t
def lerp3(c1, c2, t): return tuple(int(lerp(a, b, t)) for a, b in zip(c1, c2))

# ─────────── 静态背景层（每场景预渲染一张） ───────────
def render_static_bg(spot1, spot2, tag, tag_color, scene_idx, total_scenes):
    """径向渐变背景 + 光斑 + 网格 + 顶栏 + 水印 + 底部状态条"""
    img = Image.new("RGB", (W, H), BG)
    # 1) 大径向渐变：中心偏亮
    grad = Image.new("L", (W, H), 0)
    gd = ImageDraw.Draw(grad)
    cx, cy = W // 2, H // 2 - 100
    maxr = int(math.hypot(W, H))
    for r in range(maxr, 0, -8):
        v = int(26 * (1 - r / maxr) ** 2)
        gd.ellipse([cx - r, cy - r, cx + r, cy + r], fill=v)
    base = Image.new("RGB", (W, H), (14, 20, 31))
    img = Image.composite(base, img, grad)
    # 2) 两个彩色光斑（模糊的彩色椭圆）
    spots = Image.new("RGB", (W, H), (0, 0, 0))
    sd = ImageDraw.Draw(spots)
    for (sx, sy, r, color) in [spot1, spot2]:
        sd.ellipse([sx - r, sy - r, sx + r, sy + r], fill=color)
    spots = spots.filter(ImageFilter.GaussianBlur(120))
    img = Image.blend(img, spots, 0.30)
    # 3) 细网格
    d = ImageDraw.Draw(img, "RGBA")
    for x in range(0, W, 72):
        d.line([x, 0, x, H], fill=(255, 255, 255, 7), width=1)
    for y in range(0, H, 72):
        d.line([0, y, W, y], fill=(255, 255, 255, 7), width=1)
    # 4) 顶部光带
    for i in range(60):
        a = int(20 * (1 - i / 60))
        d.line([0, i, W, i], fill=(*tag_color, a))
    # 5) 顶栏：tag 徽章 + 场景进度点
    d.rectangle([0, 0, W, 6], fill=tag_color)
    f = F(26, mono=True)
    tb = d.textbbox((0, 0), tag, font=f)
    tw = tb[2] - tb[0]
    d.rounded_rectangle([44, 64, 44 + tw + 28, 108], radius=8, fill=(10, 14, 20), outline=tag_color, width=2)
    d.text((58, 72), tag, fill=tag_color, font=f)
    # 进度点
    dot_r, gap = 5, 18
    total_w = total_scenes * gap
    sx = W - 60 - total_w
    for i in range(total_scenes):
        cxp = sx + i * gap
        if i <= scene_idx:
            d.ellipse([cxp - dot_r, 82 - dot_r, cxp + dot_r, 82 + dot_r], fill=tag_color)
        else:
            d.ellipse([cxp - dot_r, 82 - dot_r, cxp + dot_r, 82 + dot_r], outline=(90, 105, 130), width=1)
    # 6) 水印（右上角，场景进度点下方）
    fw = F(27, mono=True)
    wb = d.textbbox((0, 0), WM, font=fw)
    ww = wb[2] - wb[0]
    d.text((W - 54 - ww, 128), WM, fill=(255, 255, 255, 66), font=fw)
    # 7) 底部状态条
    d.rectangle([0, H - 5, W, H], fill=(30, 42, 61))
    # 8) 角落装饰
    d.line([36, 150, 36, 196], fill=tag_color, width=3)
    d.line([36, 150, 82, 150], fill=tag_color, width=3)
    d.line([W - 36, H - 160, W - 36, H - 206], fill=(60, 76, 106), width=3)
    d.line([W - 82, H - 160, W - 36, H - 160], fill=(60, 76, 106), width=3)
    return img

# ─────────── 动效元素绘制 ───────────
def elem_state(t0, t, in_dur=0.5):
    """元素在 t0 时刻进场，in_dur 秒完成；返回 (visible, p, hold)"""
    if t < t0: return False, 0, False
    dt = t - t0
    if dt < in_dur:
        return True, ease_out(dt / in_dur), False
    return True, 1.0, True

def draw_text_anim(d, t, t0, text, cx, y, size, color, mono=False, anim="slide_up", in_dur=0.5, anchor_center=True, glow=False, tracking=0):
    """文字动效：slide_up / fade / scale_in / typewriter"""
    vis, p, hold = elem_state(t0, t, in_dur)
    if not vis: return
    f = F(size, mono)
    bb = d.textbbox((0, 0), text, font=f)
    tw = bb[2] - bb[0]
    x = (W - tw) // 2 if anchor_center else cx
    alpha = int(255 * p)
    yy = y
    if anim == "slide_up":
        yy = y + int((1 - p) * 60)
    elif anim == "typewriter":
        if not hold:
            n = max(1, int(len(text) * p))
            text = text[:n]
            f2 = F(size, mono)
            bb2 = d.textbbox((0, 0), text, font=f2)
            tw2 = bb2[2] - bb2[0]
            x = (W - tw2) // 2 if anchor_center else cx
    # 描边 + 主体
    col = (*color, alpha)
    for ox, oy in [(-2,-2),(-2,2),(2,-2),(2,2)]:
        d.text((x+ox, yy+oy), text, fill=(0,0,0,alpha), font=f)
    d.text((x, yy), text, fill=col, font=f)
    if glow and p > 0.5:
        # 文字底部光条
        gw = int(tw * p)
        if gw > 8:
            d.rounded_rectangle([(W-gw)//2, yy + size + 14, (W+gw)//2, yy + size + 20], radius=3, fill=(*color, int(120*p)))

def draw_count_anim(d, t, t0, target, unit, cx, y, size, color, in_dur=1.2, hold_extra=0.4):
    """数字滚动：从 0 滚到 target"""
    vis, p, hold = elem_state(t0, t, in_dur)
    if not vis: return
    if hold: p = 1.0
    val = int(target * p)
    text = f"{val:,}{unit}" if unit else f"{val:,}"
    f = F(size, mono=False)
    bb = d.textbbox((0,0), text, font=f)
    tw = bb[2]-bb[0]
    x = (W - tw)//2
    alpha = int(255 * min(1.0, p*2))
    for ox, oy in [(-3,-3),(-3,3),(3,-3),(3,3)]:
        d.text((x+ox, y+oy), text, fill=(0,0,0,alpha), font=f)
    d.text((x, y), text, fill=(*color, alpha), font=f)

def draw_card_anim(d, t, t0, x, y, w, h, border_color, in_dur=0.4, title=None, lines=None, title_color=None, icon=None):
    vis, p, hold = elem_state(t0, t, in_dur)
    if not vis: return
    cy = y + int((1-p)*24)
    a = int(255*p)
    d.rounded_rectangle([x, cy, x+w, cy+h], radius=18, fill=(*CARD_BG, a), outline=(*border_color, a), width=2)
    # 顶部高光线
    d.line([x+16, cy+2, x+w-16, cy+2], fill=(*lerp3(border_color,(255,255,255),0.5), int(a*0.8)))
    if icon:
        d.text((x+28, cy+22), icon, fill=(*border_color, a), font=F(44))
    if title:
        d.text((x+28 if icon else x+28, cy + (70 if icon else 30)), title, fill=(*(title_color or WHITE), a), font=F(38))
    if lines:
        ly = cy + (130 if icon else 90)
        for line in lines:
            if line:
                d.text((x+28, ly), line, fill=(*DIM, int(a*0.9)), font=F(30))
            ly += 46

def draw_bar_anim(d, t, t0, y, fill_ratio, color, label=None, in_dur=0.8, width=W-240):
    vis, p, hold = elem_state(t0, t, in_dur)
    if not vis: return
    x = 120
    d.rounded_rectangle([x, y, x+width, y+14], radius=7, fill=(*LINE, int(255*p)))
    fr = fill_ratio * p
    if fr > 0.01:
        d.rounded_rectangle([x, y, x+int(width*fr), y+14], radius=7, fill=(*color, int(255*p)))
        # 端点光
        d.ellipse([x+int(width*fr)-6, y-1, x+int(width*fr)+8, y+15], fill=(*lerp3(color,(255,255,255),0.4), int(255*p)))
    if label:
        d.text((x, y-44), label, fill=(*DIM, int(255*p)), font=F(30))

def draw_pulse(d, t, cx, cy, base_r, color, phase=0.0, max_alpha=36):
    """光晕呼吸脉动"""
    s = 0.5 + 0.5 * math.sin(t * 2.2 + phase)
    r = int(base_r * (0.92 + 0.08 * s))
    a = int(max_alpha * (0.5 + 0.5 * s))
    for i in range(r, 0, -6):
        aa = int(a * (i / r))
        d.ellipse([cx-i, cy-i, cx+i, cy+i], outline=(*color, aa))
    d.ellipse([cx-10, cy-10, cx+10, cy+10], fill=(*color, min(90, a*2)))

def draw_arrow_anim(d, t, t0, cx, cy, color, size=64, in_dur=0.4):
    vis, p, hold = elem_state(t0, t, in_dur)
    if not vis: return
    # 下箭头（用三角形）
    bounce = 0 if hold else 0
    yy = cy + int((1-p)*30) + bounce
    a = int(255*p)
    s = size
    d.polygon([(cx-s//2, yy-s//6), (cx+s//2, yy-s//6), (cx, yy+s//3)], fill=(*color, a))

def draw_caption(d, t, t0, text, y=1430, size=48, color=WHITE):
    """底部解说字幕（每帧都有的兜底字幕）"""
    vis, p, hold = elem_state(t0, t, 0.4)
    if not vis: return
    a = int(255*p)
    f = F(size)
    # 自动折行
    lines = []
    cur = ""
    for ch in text:
        test = cur + ch
        bb = d.textbbox((0,0), test, font=f)
        if bb[2]-bb[0] > W-160 and cur:
            lines.append(cur); cur = ch
        else:
            cur = test
    lines.append(cur)
    yy = y
    for line in lines:
        bb = d.textbbox((0,0), line, font=f)
        lw = bb[2]-bb[0]
        x = (W-lw)//2
        for ox,oy in [(-2,-2),(-2,2),(2,-2),(2,2)]:
            d.text((x+ox,yy+oy), line, fill=(0,0,0,a), font=f)
        d.text((x,yy), line, fill=(*color,a), font=f)
        yy += size + 16

def draw_particle(d, t, seed, cx, cy, spread, color, n=6):
    """漂浮光点装饰"""
    import random as _r
    rnd = _r.Random(seed)
    for i in range(n):
        px = cx + rnd.randint(-spread, spread)
        py = cy + rnd.randint(-spread, spread)
        ph = rnd.uniform(0, 6.28)
        s = 0.5 + 0.5*math.sin(t*1.8 + ph)
        a = int(70 * s)
        r = rnd.randint(2, 4)
        d.ellipse([px-r, py-r, px+r, py+r], fill=(*color, a))

# ─────────── 16 个场景定义（每场景一个函数：scene(draw, t, dur)） ───────────

def sc_01(d, t, dur):
    tag_c = CYAN
    draw_pulse(d, t, W//2, 620, 190, CYAN, 0)
    draw_particle(d, t, 1, W//2, 620, 260, CYAN, 5)
    draw_count_anim(d, t, 0.15, 100000, "", W//2, 380, 150, WHITE)
    draw_text_anim(d, t, 0.5, "字小说", W//2, 560, 56, DIM, anim="fade")
    draw_arrow_anim(d, t, 0.9, W//2, 780, CYAN, 72)
    draw_text_anim(d, t, 1.2, "有声书", W//2, 830, 110, AMBER, anim="scale_up" if False else "slide_up")
    draw_text_anim(d, t, 1.7, "一键转换 · 多角色配音 · 完全免费", W//2, 1000, 36, DIM, anim="fade")
    draw_text_anim(d, t, 2.1, "·", W//2, 1060, 28, CYAN, anim="fade")
    draw_caption(d, t, 2.3, "10万字的小说，一键变成多角色有声书，还不花一分钱")

def sc_02(d, t, dur):
    draw_pulse(d, t, 900, 350, 120, MAGENTA, 1.5)
    draw_text_anim(d, t, 0.2, "easyVoice", W//2, 420, 110, WHITE, mono=True, anim="slide_up")
    draw_text_anim(d, t, 0.6, "开源文字转语音解决方案", W//2, 600, 42, DIM, anim="fade")
    draw_bar_anim(d, t, 0.8, 730, 0.35, CYAN, in_dur=0.6)
    tags = [("无字数限制", CYAN, 1.1), ("无时长上限", MAGENTA, 1.35), ("完全免费", GREEN, 1.6)]
    f = F(34)
    for label, color, t0 in tags:
        vis, p, hold = elem_state(t0, t, 0.4)
        if not vis: continue
        bb = d.textbbox((0,0), label, font=f)
        lw = bb[2]-bb[0]
        x = (W - (lw*3 + 100)) // 2 + int([0,1,2][[tt for _,_,tt in tags].index(t0)] * (lw + 50))
        a = int(255*p)
        yy = 830 + int((1-p)*20)
        d.rounded_rectangle([x, yy, x+lw+30, yy+58], radius=10, fill=(*CARD_BG, a), outline=(*color, a), width=2)
        d.text((x+15, yy+10), label, fill=(*color, a), font=f)
    draw_caption(d, t, 2.0, "这个开源项目叫 easyVoice，它专门干一件事——把文字变成声音")

def sc_03(d, t, dur):
    draw_text_anim(d, t, 0.2, "市面 TTS 工具的", W//2, 320, 50, DIM, anim="fade")
    draw_text_anim(d, t, 0.4, "两个硬限制", W//2, 400, 66, AMBER, anim="slide_up")
    draw_card_anim(d, t, 0.9, 80, 580, 920, 300, AMBER,
                   icon="①", title="按字数收费",
                   lines=["超了就不让用", "越用越贵，长文劝退"])
    draw_card_anim(d, t, 1.5, 80, 920, 920, 300, AMBER,
                   icon="②", title="有时长上限",
                   lines=["超了就截断", "一整本书只能听个开头"])
    draw_caption(d, t, 2.2, "要么按字数收费，要么有时长上限，超了就不让用")

def sc_04(d, t, dur):
    draw_pulse(d, t, W//2, 560, 150, GREEN, 0.3)
    draw_text_anim(d, t, 0.2, "全砍了", W//2, 420, 120, GREEN, anim="slide_up")
    draw_text_anim(d, t, 0.5, "ALL LIMITS REMOVED", W//2, 600, 30, DIM2, mono=True, anim="fade")
    items = [("字数限制", 0.8), ("时长上限", 1.05), ("充值订阅", 1.3)]
    for label, t0 in items:
        vis, p, hold = elem_state(t0, t, 0.4)
        if not vis: continue
        a = int(255*p)
        idx = [x[1] for x in items].index(t0)
        y = 780 + idx*130 + int((1-p)*18)
        d.rounded_rectangle([140, y, 940, y+100], radius=14, fill=(*CARD_BG, a), outline=(*LINE2, a), width=2)
        d.text((200, y+26), label, fill=(*DIM, a), font=F(42))
        # 打叉动画
        cx1, cy1 = 850, y+50
        cp = ease_out(min(1.0, (t - t0 - 0.1)/0.3)) if t > t0+0.1 else 0
        if cp > 0:
            d.line([cx1-24*cp, cy1-24*cp, cx1+24*cp, cy1+24*cp], fill=(*AMBER, a), width=8)
            d.line([cx1-24*cp, cy1+24*cp, cx1+24*cp, cy1-24*cp], fill=(*AMBER, a), width=8)
    draw_caption(d, t, 2.0, "easyVoice 把这两个限制全砍了")

def sc_05(d, t, dur):
    draw_text_anim(d, t, 0.2, "一键转换流程", W//2, 300, 54, CYAN, anim="slide_up")
    steps = [("10万字小说", CYAN, 0.5), ("AI 处理", MAGENTA, 0.9), ("多角色有声书", GREEN, 1.3)]
    sw, gap = 280, 50
    total = sw*3 + gap*2
    sx = (W-total)//2
    f = F(36)
    for label, color, t0 in steps:
        vis, p, hold = elem_state(t0, t, 0.5)
        if not vis: continue
        i = [s[2] for s in steps].index(t0)
        x = sx + i*(sw+gap)
        y = 550 + int((1-p)*30)
        a = int(255*p)
        d.rounded_rectangle([x, y, x+sw, y+190], radius=16, fill=(*CARD_BG, a), outline=(*color, a), width=3)
        bb = d.textbbox((0,0), label, font=f)
        lw = bb[2]-bb[0]
        # 两行处理
        if lw > sw-40:
            half = len(label)//2
            for j, part in enumerate([label[:half], label[half:]]):
                bb2 = d.textbbox((0,0), part, font=f)
                d.text((x+(sw-(bb2[2]-bb2[0]))//2, y+60+j*55), part, fill=(*color, a), font=f)
        else:
            d.text((x+(sw-lw)//2, y+80), label, fill=(*color, a), font=f)
        if i < 2:
            ax = x + sw + 4
            ap = ease_out(min(1.0, (t - t0 - 0.15)/0.3)) if t > t0+0.15 else 0
            if ap > 0:
                d.text((ax, y+70), "→", fill=(*DIM, int(255*ap)), font=F(46))
    draw_text_anim(d, t, 2.0, "不同角色自动分配不同音色，不用手动调", W//2, 900, 40, DIM, anim="fade")
    draw_caption(d, t, 2.4, "你把一整本10万字的小说丢进去，它一键转成多角色有声书")

def sc_06(d, t, dur):
    draw_text_anim(d, t, 0.2, "语音 + 字幕", W//2, 320, 80, MAGENTA, anim="slide_up")
    draw_text_anim(d, t, 0.5, "同步生成", W//2, 430, 44, DIM, anim="fade")
    # 模拟字幕卡
    vis, p, hold = elem_state(0.8, t, 0.5)
    if vis:
        a = int(255*p)
        d.rounded_rectangle([80, 620, 1000, 1050], radius=18, fill=(*CARD_BG, a), outline=(*LINE2, a), width=2)
        lines = [("「从前有座山，", CYAN, 1.0), ("山里有座庙，", CYAN, 1.2), ("庙里有个老和尚」", AMBER, 1.4)]
        f = F(46)
        for text, color, lt in lines:
            lp = ease_out(min(1.0, (t-0.8-lt+0.8)/0.4)) if t > lt-0.3 else 0
            # 逐行淡入
            idx = lines.index((text, color, lt))
            line_t0 = 1.0 + idx*0.35
            lv, lp, lh = elem_state(line_t0, t, 0.35)
            if lv:
                la = int(255*lp)
                d.text((160, 700+idx*80), text, fill=(*color, la), font=f)
        d.text((160, 990), "[字幕与语音逐字同步]", fill=(*GREEN, int(255*p)), font=F(28))
    draw_caption(d, t, 2.2, "它还能同步生成字幕，语音和文字一起出，听着看都行")

def sc_07(d, t, dur):
    draw_text_anim(d, t, 0.2, "流式传输", W//2, 300, 76, CYAN, anim="slide_up")
    draw_text_anim(d, t, 0.5, "STREAMING", W//2, 420, 30, DIM2, mono=True, anim="fade")
    bars = [("章节 1", 1.0, CYAN, 0.7), ("章节 2", 0.85, MAGENTA, 0.95), ("章节 3", 0.9, GREEN, 1.2), ("章节 4", 0.8, AMBER, 1.45), ("章节 10", 0.95, VIOLET, 1.7)]
    for label, fr, color, t0 in bars:
        idx = [b[3] for b in bars].index(t0)
        draw_bar_anim(d, t, t0, 620 + idx*90, fr, color, label=label)
    vis, p, hold = elem_state(2.2, t, 0.4)
    if vis:
        a = int(255*p)
        d.text((160, 1130), "✓ 不用等整本转完", fill=(*GREEN, a), font=F(38))
        d.text((160, 1190), "✓ 多长都能立刻播放", fill=(*GREEN, a), font=F(38))
    draw_caption(d, t, 2.6, "多长的文本都能立刻开始播放，不用等整本转完")

def sc_08(d, t, dur):
    draw_text_anim(d, t, 0.2, "AI 智能推荐", W//2, 300, 70, MAGENTA, anim="slide_up")
    draw_text_anim(d, t, 0.5, "配音风格", W//2, 400, 60, WHITE, anim="slide_up")
    styles = [("御姐音", AMBER, "慵懒", 0.8, 0), ("少女音", CYAN, "清甜", 1.0, 1), ("正太音", GREEN, "活力", 1.2, 2), ("大叔音", MAGENTA, "低沉", 1.4, 3)]
    for label, color, trait, t0, i in styles:
        x = 80 + (i%2)*460
        y = 700 + (i//2)*220
        draw_card_anim(d, t, t0, x, y, 420, 180, color, icon="♪", title=label, lines=[f"{trait} · 自动匹配"])
    draw_caption(d, t, 2.2, "AI 还会智能推荐配音风格，你不用懂什么音色参数")

def sc_09(d, t, dur):
    draw_pulse(d, t, W//2, 640, 230, GREEN, 0)
    draw_particle(d, t, 9, W//2, 640, 300, GREEN, 6)
    draw_text_anim(d, t, 0.2, "最关键的三个字", W//2, 330, 46, DIM, anim="fade")
    draw_text_anim(d, t, 0.5, "完全免费", W//2, 450, 140, GREEN, anim="slide_up")
    draw_text_anim(d, t, 1.1, "100% FREE · OPEN SOURCE", W//2, 700, 30, DIM2, mono=True, anim="fade")
    draw_caption(d, t, 1.4, "最关键的三个字——完全免费")

def sc_10(d, t, dur):
    draw_text_anim(d, t, 0.2, "五个「不」", W//2, 300, 66, GREEN, anim="slide_up")
    items = [("无时长限制", GREEN, 0.5), ("无字数限制", GREEN, 0.75), ("不充值", AMBER, 1.0), ("不订阅", AMBER, 1.25), ("不弹广告", MAGENTA, 1.5)]
    for label, color, t0 in items:
        idx = [x[2] for x in items].index(t0)
        vis, p, hold = elem_state(t0, t, 0.35)
        if not vis: continue
        a = int(255*p)
        y = 480 + idx*130 + int((1-p)*16)
        d.rounded_rectangle([100, y, 980, y+105], radius=14, fill=(*CARD_BG, a), outline=(*color, int(a*0.7)), width=2)
        cp = ease_out(min(1.0, (t-t0-0.05)/0.25)) if t > t0+0.05 else 0
        if cp > 0:
            cx1, cy1 = 180, y+52
            r = 20*cp
            d.ellipse([cx1-r, cy1-r, cx1+r, cy1+r], fill=(*color, a))
            d.line([cx1-9*cp, cy1+1, cx1-2*cp, cy1+9*cp], fill=(8,11,17,a), width=5)
            d.line([cx1-2*cp, cy1+9*cp, cx1+11*cp, cy1-8*cp], fill=(8,11,17,a), width=5)
        d.text((250, y+28), label, fill=(*WHITE, a), font=F(46))
    draw_caption(d, t, 2.0, "无时长限制，无字数限制，不充值，不订阅，不弹广告")

def sc_11(d, t, dur):
    draw_text_anim(d, t, 0.2, "同样功能，两种价格", W//2, 300, 54, WHITE, anim="slide_up")
    draw_card_anim(d, t, 0.6, 80, 480, 920, 330, AMBER, icon="✗",
                   title="商业有声书平台", lines=["一年收费好几百块", "按月订阅，越用越贵"])
    draw_card_anim(d, t, 1.2, 80, 860, 920, 330, GREEN, icon="✓",
                   title="easyVoice 开源", lines=["谁都能用，谁都能改", "MIT 协议 · GitHub 公开"])
    vis, p, hold = elem_state(1.8, t, 0.4)
    if vis:
        a = int(255*p)
        f = F(34, mono=True)
        d.text((300, 1260), "github.com/symbxx/easyVoice", fill=(*CYAN, a), font=f)
    draw_caption(d, t, 2.1, "同样的功能，商业平台一年好几百块，而它免费开源")

def sc_12(d, t, dur):
    draw_pulse(d, t, 880, 380, 100, CYAN, 2.0)
    draw_text_anim(d, t, 0.2, "听书党", W//2, 350, 100, CYAN, anim="slide_up")
    draw_text_anim(d, t, 0.6, "AUDIBLE LOVER", W//2, 500, 28, DIM2, mono=True, anim="fade")
    draw_text_anim(d, t, 0.9, "手机里攒了半年的小说", W//2, 640, 44, WHITE, anim="fade")
    draw_text_anim(d, t, 1.2, "终于能一口气听完了", W//2, 720, 44, GREEN, anim="fade")
    # 书堆
    for i in range(5):
        vis, p, hold = elem_state(1.4 + i*0.15, t, 0.3)
        if not vis: continue
        a = int(255*p)
        x = 260 + i*36
        y = 950 - i*28
        color = [CYAN, MAGENTA, GREEN, AMBER, VIOLET][i]
        d.rounded_rectangle([x, y, x+220, y+56], radius=8, fill=(*CARD_BG, a), outline=(*color, a), width=2)
        d.text((x+20, y+10), f"第{i+1}本", fill=(*color, a), font=F(30))
    draw_caption(d, t, 2.3, "对听书党来说，攒了半年的小说终于能一口气听完了")

def sc_13(d, t, dur):
    draw_text_anim(d, t, 0.2, "内容创作者", W//2, 350, 84, MAGENTA, anim="slide_up")
    draw_text_anim(d, t, 0.5, "CREATOR", W//2, 470, 28, DIM2, mono=True, anim="fade")
    # 流程
    nodes = [("文章/脚本", CYAN, 0.8, 0), ("音频内容", MAGENTA, 1.1, 1), ("新分发渠道", GREEN, 1.4, 2)]
    f = F(40)
    for label, color, t0, i in nodes:
        vis, p, hold = elem_state(t0, t, 0.4)
        if not vis: continue
        a = int(255*p)
        x = 90 + i*320
        y = 750 + int((1-p)*20)
        d.rounded_rectangle([x, y, x+270, y+130], radius=16, fill=(*CARD_BG, a), outline=(*color, a), width=3)
        bb = d.textbbox((0,0), label, font=f)
        lw = bb[2]-bb[0]
        if lw > 230:
            d.text((x+40, y+35), label[:2], fill=(*color, a), font=f)
            d.text((x+40, y+80), label[2:], fill=(*color, a), font=f)
        else:
            d.text((x+(270-lw)//2, y+42), label, fill=(*color, a), font=f)
        if i < 2:
            ap = ease_out(min(1.0,(t-t0-0.1)/0.3)) if t > t0+0.1 else 0
            if ap > 0:
                d.text((x+278, y+40), "→", fill=(*DIM, int(255*ap)), font=F(48))
    draw_text_anim(d, t, 2.0, "零成本的音频分发渠道", W//2, 1000, 44, GREEN, anim="fade")
    draw_caption(d, t, 2.3, "你的文章和脚本，多了一个零成本的音频分发渠道")

def sc_14(d, t, dur):
    draw_text_anim(d, t, 0.2, "开发者", W//2, 320, 90, GREEN, anim="slide_up")
    draw_text_anim(d, t, 0.5, "DEVELOPER", W//2, 440, 28, DIM2, mono=True, anim="fade")
    # 代码块
    vis, p, hold = elem_state(0.8, t, 0.4)
    if vis:
        a = int(255*p)
        d.rounded_rectangle([70, 580, 1010, 1180], radius=18, fill=(6,10,16), outline=(*LINE2, a), width=2)
        d.text((100, 608), "● ● ●", fill=(*DIM2, a), font=F(24, mono=True))
        d.text((180, 610), "easyvoice_demo.py", fill=(*DIM2, a), font=F(24, mono=True))
        d.line([70, 648, 1010, 648], fill=(*LINE, a))
        code = [
            ("from easyvoice import TTS", CYAN, 1.0),
            ("", DIM2, 1.1),
            ("# 1 分钟上手", DIM2, 1.2),
            ("tts = TTS(voice='御姐')", WHITE, 1.35),
            ("tts.convert('小说.txt')", WHITE, 1.5),
            ("# → audio.mp3 + srt 字幕", GREEN, 1.7),
        ]
        f = F(34, mono=True)
        for line, color, lt in code:
            idx = code.index((line, color, lt))
            line_t0 = 0.9 + idx*0.15
            lv, lp, lh = elem_state(line_t0, t, 0.25)
            if lv and line:
                la = int(255*lp)
                d.text((110, 690 + idx*62), line, fill=(*color, la), font=f)
    draw_caption(d, t, 2.2, "对开发者来说，这是可以直接二次开发的 TTS 方案")

def sc_15(d, t, dur):
    draw_text_anim(d, t, 0.2, "三类人建议收藏", W//2, 280, 60, AMBER, anim="slide_up")
    people = [
        ("① 听书党", "半年没听的小说终于能听完", CYAN, 0.6),
        ("② 创作者", "文章脚本多一个音频渠道", MAGENTA, 0.95),
        ("③ 开发者", "零成本 TTS 二次开发", GREEN, 1.3),
    ]
    for title, desc, color, t0 in people:
        idx = [x[3] for x in people].index(t0)
        draw_card_anim(d, t, t0, 80, 500 + idx*300, 920, 250, color,
                       icon="★", title=title, lines=[desc])
    draw_caption(d, t, 2.0, "三类人建议收藏：听书党、创作者、开发者")

def sc_16(d, t, dur):
    """收尾帧：极简干净——只保留光晕 + 一句大字 + 一行地址"""
    draw_pulse(d, t, W//2, 780, 160, GREEN, 0)
    draw_text_anim(d, t, 0.2, "项目地址我放评论区了", W//2, 560, 66, WHITE, anim="slide_up")
    draw_text_anim(d, t, 0.8, "github.com/symbxx/easyVoice", W//2, 760, 38, CYAN, mono=True, anim="fade")
    draw_caption(d, t, 1.4, "项目地址我放评论区了，自己去看")

SCENES = [sc_01, sc_02, sc_03, sc_04, sc_05, sc_06, sc_07, sc_08,
          sc_09, sc_10, sc_11, sc_12, sc_13, sc_14, sc_15, sc_16]
SPOTS = [
    ((150, 250, 200, (20,60,80)), (900, 500, 180, (60,20,50))),   # 1 cyan/magenta
    ((900, 400, 200, (50,20,45)), (200, 700, 160, (30,50,80))),    # 2 magenta/cyan
    ((180, 350, 180, (70,55,15)), (900, 600, 170, (45,30,70))),    # 3 amber/violet
    ((200, 400, 190, (15,55,35)), (880, 550, 170, (50,20,45))),    # 4 green/magenta
    ((150, 300, 180, (18,50,75)), (920, 500, 190, (60,20,50))),    # 5 cyan/magenta
    ((880, 350, 180, (50,18,45)), (220, 650, 160, (30,45,75))),    # 6 magenta/cyan
    ((160, 400, 170, (18,50,75)), (900, 600, 180, (55,40,15))),    # 7 cyan/amber
    ((900, 300, 180, (50,18,45)), (200, 700, 170, (40,18,55))),    # 8 magenta/violet
    ((200, 350, 200, (14,55,32)), (880, 600, 180, (14,55,32))),    # 9 green/green
    ((160, 400, 180, (14,55,32)), (920, 550, 170, (60,45,12))),   # 10 green/amber
    ((200, 350, 180, (70,55,15)), (880, 600, 170, (14,50,30))),    # 11 amber/green
    ((880, 350, 170, (18,50,75)), (220, 650, 180, (18,50,75))),    # 12 cyan/cyan
    ((900, 400, 180, (50,18,45)), (200, 700, 160, (30,18,55))),    # 13 magenta/violet
    ((180, 350, 180, (14,50,32)), (900, 600, 170, (30,45,70))),    # 14 green/cyan
    ((200, 300, 180, (60,45,12)), (880, 650, 170, (45,18,50))),    # 15 amber/magenta
    ((880, 400, 190, (14,55,32)), (220, 700, 170, (14,55,32))),    # 16 green/green
]
TAGS = ["HOOK", "PROJECT", "PAIN POINT", "SOLUTION", "WORKFLOW", "SUBTITLE", "STREAMING",
        "AI VOICE", "FREE", "ZERO COST", "VS", "AUDIBLE", "CREATOR", "DEVELOPER", "SUMMARY", "NEXT"]
TAG_COLORS = [CYAN, MAGENTA, AMBER, GREEN, CYAN, MAGENTA, CYAN, MAGENTA,
              GREEN, GREEN, AMBER, CYAN, MAGENTA, GREEN, AMBER, GREEN]

# ─────────── 渲染 ───────────
print("=== 生成动画帧 ===")
total_frames = 0
for si, item in enumerate(meta):
    idx = item["index"]
    dur = item["duration"]
    n_frames = max(2, int(dur * ANIM_FPS))
    # 预渲染静态背景
    static = render_static_bg(SPOTS[si][0], SPOTS[si][1], TAGS[si], TAG_COLORS[si], si, len(meta))
    scene = SCENES[si]
    for fi in range(n_frames):
        t = (fi + 1) / n_frames * max(dur, 2.5)  # 归一化进度映射到场景时间
        # 用场景时间：让动画在前2.5秒内完成，之后保持
        t_scene = min((fi+1)/n_frames * dur, 3.0) if dur > 3.0 else (fi+1)/n_frames*dur
        img = static.copy()
        d = ImageDraw.Draw(img, "RGBA")
        scene(d, t_scene, dur)
        fp = os.path.join(ANIM_DIR, f"s{si+1:02d}_{fi:04d}.png")
        img.save(fp)
        total_frames += 1
    print(f"  场景 {idx:02d} ({dur:.1f}s) → {n_frames} 帧")

print(f"共生成 {total_frames} 帧动画图片")

# ─────────── 用 ffmpeg 序列合成 ───────────
print("\n=== 合成视频 ===")
# 方案：每个场景的帧按 ANIM_FPS 输入，然后统一转 30fps
# 逐场景生成视频段（用 image2 序列 + 重复帧达 30fps）
seg_files = []
for si, item in enumerate(meta):
    idx = item["index"]
    dur = item["duration"]
    n_frames = max(2, int(dur * ANIM_FPS))
    seg_path = os.path.join(WORK, f"anim_seg_{idx:02d}.mp4")
    pattern = os.path.join(ANIM_DIR, f"s{si+1:02d}_%04d.png")
    # image2 输入 ANIM_FPS，输出 30fps（ffmpeg 自动帧重复）
    subprocess.run(["ffmpeg","-y","-v","error",
        "-framerate", str(ANIM_FPS), "-start_number", "0",
        "-i", pattern,
        "-t", f"{dur:.2f}",
        "-vf", "scale=1080:1920",
        "-r", "30",
        "-c:v","libx264","-preset","fast","-pix_fmt","yuv420p",
        seg_path], check=True)
    seg_files.append(seg_path)
    os.remove if False else None

# 拼接
concat_list = os.path.join(WORK, "anim_concat.txt")
with open(concat_list, "w") as f:
    for seg in seg_files:
        f.write(f"file '{seg}'\n")
silent_mp4 = os.path.join(WORK, "anim_silent.mp4")
subprocess.run(["ffmpeg","-y","-v","error","-f","concat","-safe","0",
    "-i",concat_list,"-c:v","libx264","-preset","fast","-pix_fmt","yuv420p",silent_mp4], check=True)

# 混音频
subprocess.run(["ffmpeg","-y","-v","error","-i",silent_mp4,"-i",NARRATION_WAV,
    "-c:v","copy","-c:a","aac","-b:a","128k","-ar","44100",
    "-shortest","-movflags","+faststart",RAW_MP4], check=True)
os.remove(silent_mp4)
print(f"粗剪: {RAW_MP4}")

# 压缩
subprocess.run(["ffmpeg","-y","-v","error","-i",RAW_MP4,
    "-c:v","libx264","-preset","medium","-profile:v","high","-level","4.2",
    "-pix_fmt","yuv420p","-b:v","8M","-maxrate","10M","-bufsize","12M",
    "-r","30","-g","60",
    "-c:a","aac","-b:a","128k","-ar","44100","-movflags","+faststart",DOUYIN_MP4], check=True)
print(f"成片: {DOUYIN_MP4}")

# 片尾
print("\n=== 追加标准片尾 ===")
import shutil
ncopy = os.path.join(os.path.dirname(DOUYIN_MP4), "narration.wav")
if not os.path.exists(ncopy):
    shutil.copy2(NARRATION_WAV, ncopy)
r = subprocess.run(["python3","/Volumes/PSSD/抖音视频/append_epilogue.py",
    os.path.dirname(DOUYIN_MP4),"--force"], capture_output=True, text=True)
if r.returncode != 0:
    print(f"片尾失败: {r.stderr[-200:]}")

# 验收
final = os.path.join(os.path.dirname(DOUYIN_MP4), "douyin_epilogue.mp4")
if not os.path.exists(final): final = DOUYIN_MP4
probe = subprocess.run(["ffprobe","-v","quiet","-print_format","json",
    "-show_streams","-show_format",final], capture_output=True, text=True)
data = json.loads(probe.stdout)
v = next(s for s in data["streams"] if s["codec_type"]=="video")
a = next(s for s in data["streams"] if s["codec_type"]=="audio")
dur_f = float(data["format"]["duration"])
fps_f = eval(v["r_frame_rate"])
size = os.path.getsize(final)/1024/1024
print(f"\n=== 验收 ===")
print(f"  分辨率: {v['width']}x{v['height']} {'✓' if v['width']==1080 else '✗'}")
print(f"  帧率: {fps_f:.0f}fps {'✓' if abs(fps_f-30)<0.5 else '✗'}")
print(f"  编码: {v['codec_name']} / {a['codec_name']} {'✓' if v['codec_name']=='h264' else '✗'}")
print(f"  时长: {dur_f:.1f}s {'✓' if dur_f<=180 else '✗'}")
print(f"  大小: {size:.1f}MB")
print(f"\n成片: {final}")
