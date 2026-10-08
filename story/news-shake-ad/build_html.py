#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从 script.json 生成 index.html（赤焰热力主题，新闻话题版：SVG 动效场景，无 GIF）"""
import json, os, html

STORY = "/Volumes/PSSD/抖音视频/story/news-shake-ad"

def render_stat(s):
    return "".join(f'<div class="stat"><div class="k">{html.escape(x["k"])}</div><div class="v">{html.escape(x["v"])}</div></div>' for x in s)

# ---------- 场景动效（SVG，全部挂在 GSAP 时间轴上，seek 安全）----------

def vis_shake(i):
    rain = ""
    return f'''<div class="vis v-shake" id="vis-{i}">
      <div class="shake-stage">
        <div class="phone" id="ph-{i}">
          <div class="phone-screen">
            <div class="ad-tag">开屏广告</div>
            <div class="ad-sk"></div>
            <div class="ad-sk w80"></div>
            <div class="ad-sk w60"></div>
          </div>
        </div>
        <div class="jump-arrow" id="ar-{i}">
          <svg viewBox="0 0 80 60"><path d="M6 30 H64 M48 12 L70 30 L48 48" fill="none" stroke="currentColor" stroke-width="7" stroke-linecap="round" stroke-linejoin="round"/></svg>
        </div>
        <div class="ad-target" id="tg-{i}">
          <svg viewBox="0 0 90 90" class="bag"><path d="M18 28 H72 L64 78 H26 Z" fill="none" stroke="currentColor" stroke-width="5"/><path d="M34 28 V20 a11 11 0 0 1 22 0 v8" fill="none" stroke="currentColor" stroke-width="5"/></svg>
          <div class="t-name">某电商平台</div>
          <div class="t-sub">自动跳转完成</div>
        </div>
      </div>
      <div class="vis-badge">10 次打开 · 8 次跳转</div>
    </div>'''

def vis_highway(i):
    rain = []
    for k in range(16):
        x = 60 + (k * 57) % 860
        y = -50 + (k * 73) % 170
        rain.append(f'<line class="rdrop" x1="{x}" y1="{y}" x2="{x-14}" y2="{y+36}" stroke="#7FB2FF" stroke-width="4" opacity="0.5" stroke-linecap="round"/>')
    return f'''<div class="vis v-highway" id="vis-{i}">
      <svg viewBox="0 0 960 560" class="vis-svg" id="road-{i}">
        <defs>
          <linearGradient id="sky-{i}" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0" stop-color="#0D0F0F"/><stop offset="1" stop-color="#1B1410"/>
          </linearGradient>
        </defs>
        <rect width="960" height="560" fill="url(#sky-{i})"/>
        <polygon points="0,350 960,350 960,560 0,560" fill="#16161B"/>
        <line x1="0" y1="350" x2="960" y2="350" stroke="#2A2A32" stroke-width="4"/>
        <line class="dash" x1="480" y1="350" x2="480" y2="560" stroke="#FF5926" stroke-width="12" stroke-dasharray="44 44" opacity="0.9"/>
        <line class="dash2" x1="180" y1="350" x2="180" y2="560" stroke="#3A3A44" stroke-width="6" stroke-dasharray="30 34"/>
        <line class="dash2" x1="780" y1="350" x2="780" y2="560" stroke="#3A3A44" stroke-width="6" stroke-dasharray="30 34"/>
        <g id="rain-{i}">{"".join(rain)}</g>
        <g id="car-{i}" transform="translate(300,372)">
          <rect x="0" y="0" width="300" height="66" rx="18" fill="#24242B" stroke="#FF5926" stroke-width="3"/>
          <path d="M62,2 L102,-44 L206,-44 L246,2 Z" fill="#24242B" stroke="#FF5926" stroke-width="3"/>
          <rect x="112" y="-34" width="84" height="32" rx="6" fill="rgba(255,89,38,.35)"/>
          <circle cx="82" cy="72" r="26" fill="#0D0F0F" stroke="#8A8A94" stroke-width="6"/>
          <circle cx="220" cy="72" r="26" fill="#0D0F0F" stroke="#8A8A94" stroke-width="6"/>
        </g>
        <g id="jump-{i}" transform="translate(610,52)">
          <rect width="290" height="76" rx="14" fill="#1A1A1E" stroke="#FF5926" stroke-width="2"/>
          <text x="145" y="48" font-size="28" fill="#F2F2F5" text-anchor="middle" font-family="PingFang SC,sans-serif">导航 ⟶ 电商</text>
        </g>
      </svg>
      <div class="vis-badge">暴雨高速 · 颠簸即触发「摇一摇」</div>
    </div>'''

def vis_sensor(i):
    bars = []
    for k in range(24):
        x = 42 + k * 37
        bars.append(f'<rect class="bar" x="{x}" y="400" width="23" height="140" rx="6" fill="url(#barg-{i})"/>')
    H = [0.35,0.6,0.95,0.45,1.3,0.8,1.6,0.5,1.1,0.75,1.45,0.55,0.9,0.65,1.25,0.4,0.85,1.05,0.5,1.4,0.7,1.0,0.6,1.15]
    arr = ",".join(f"{h}" for h in H)
    return f'''<div class="vis v-sensor" id="vis-{i}">
      <svg viewBox="0 0 960 560" class="vis-svg" id="wave-{i}">
        <defs>
          <linearGradient id="barg-{i}" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0" stop-color="#FF8A5C"/><stop offset="1" stop-color="#B03D1A"/>
          </linearGradient>
        </defs>
        <rect width="960" height="560" fill="#101013"/>
        <line id="thr-{i}" x1="40" y1="300" x2="920" y2="300" stroke="#FF5926" stroke-width="3" stroke-dasharray="14 12" opacity="0.9"/>
        <text x="904" y="282" font-size="24" fill="#FF5926" text-anchor="end" font-family="PingFang SC,sans-serif">灵敏度临界值</text>
        <text x="40" y="282" font-size="24" fill="#9A9AA3" font-family="PingFang SC,sans-serif">加速度传感器 · 陀螺仪</text>
        {"".join(bars)}
      </svg>
      <div class="vis-badge">走路 / 坐车的自然晃动 = 被判定「主动摇」</div>
    </div>'''

def vis_hammer(i):
    return f'''<div class="vis v-hammer" id="vis-{i}">
      <div class="doc" id="doc-{i}">
        <div class="doc-head">关于侵害用户权益行为的 APP 通报</div>
        <div class="doc-line w92"></div>
        <div class="doc-line w78"></div>
        <div class="doc-line w85"></div>
        <div class="doc-line w60"></div>
      </div>
      <div class="stamp" id="stamp-{i}">
        <svg viewBox="0 0 120 120">
          <circle cx="60" cy="60" r="54" fill="none" stroke="#FF5926" stroke-width="7"/>
          <circle cx="60" cy="60" r="44" fill="none" stroke="#FF5926" stroke-width="2" opacity="0.6"/>
          <text x="60" y="74" font-size="36" fill="#FF5926" text-anchor="middle" font-weight="800" font-family="PingFang SC,sans-serif">通报</text>
        </svg>
      </div>
      <div class="vis-badge">工信部通报 · 26 款 APP 及 SDK</div>
    </div>'''

def vis_scale(i):
    return f'''<div class="vis v-scale" id="vis-{i}">
      <div class="cmp" id="cmp-{i}">
        <div class="cmp-col">
          <div class="bar bar-cost"></div>
          <div class="cmp-label">违法成本</div>
        </div>
        <div class="vs">VS</div>
        <div class="cmp-col">
          <div class="bar bar-gain"></div>
          <div class="cmp-label">违法收益</div>
        </div>
      </div>
      <div class="vis-badge">罚款不够它一天赚的 · 已触碰法律红线</div>
    </div>'''

VIS = {"shake": vis_shake, "highway": vis_highway, "sensor": vis_sensor, "hammer": vis_hammer, "scale": vis_scale}

def anim_shake(i, s, e):
    n = int((e - s) / 0.2) + 2
    return f'''tl.to("#ph-{i}", {{ rotation: 5, duration: 0.1, yoyo: true, repeat: {n}, transformOrigin: "50% 90%", ease: "sine.inOut" }}, {s:.2f});
      tl.fromTo("#ar-{i}", {{ x: -26, opacity: 0 }}, {{ x: 26, opacity: 1, duration: 0.5, yoyo: true, repeat: {n}, ease: "power1.inOut" }}, {s+0.5:.2f});
      tl.fromTo("#tg-{i}", {{ scale: 0.92, opacity: 0.45 }}, {{ scale: 1, opacity: 1, duration: 0.6, yoyo: true, repeat: {n}, ease: "power1.inOut" }}, {s+0.7:.2f});
      tl.from("#vis-{i} .vis-badge", {{ y: 22, opacity: 0, duration: 0.5, ease: "power2.out" }}, {s+0.4:.2f});'''

def anim_highway(i, s, e):
    dur = e - s
    n = int(dur / 0.6) + 2
    nr = int(dur / 0.35) + 2
    nc = int(dur / 0.6) + 4
    return f'''tl.to("#road-{i} line.dash", {{ strokeDashoffset: -88, duration: 0.6, repeat: {n}, ease: "none" }}, {s:.2f});
      tl.to("#road-{i} line.dash2", {{ strokeDashoffset: -64, duration: 0.6, repeat: {n}, ease: "none" }}, {s:.2f});
      tl.to("#car-{i}", {{ y: -8, duration: 0.3, yoyo: true, repeat: {nc}, ease: "sine.inOut" }}, {s:.2f});
      tl.to("#rain-{i} .rdrop", {{ y: 96, duration: 0.35, repeat: {nr}, ease: "none", stagger: 0.04 }}, {s:.2f});
      tl.fromTo("#jump-{i}", {{ opacity: 0, scale: 0.7 }}, {{ opacity: 1, scale: 1, duration: 0.5, yoyo: true, repeat: {n}, ease: "power1.inOut" }}, {s+0.8:.2f});
      tl.from("#vis-{i} .vis-badge", {{ y: 22, opacity: 0, duration: 0.5, ease: "power2.out" }}, {s+0.4:.2f});'''

def anim_sensor(i, s, e):
    H = [0.35,0.6,0.95,0.45,1.3,0.8,1.6,0.5,1.1,0.75,1.45,0.55,0.9,0.65,1.25,0.4,0.85,1.05,0.5,1.4,0.7,1.0,0.6,1.15]
    arr = ",".join(f"{h}" for h in H)
    n = int((e - s) / 0.9) + 2
    return f'''const WAVE_{i} = [{arr}];
      tl.fromTo("#wave-{i} rect.bar", {{ scaleY: 0.2 }}, {{ scaleY: (idx) => WAVE_{i}[idx % {len(H)}], duration: 0.45, yoyo: true, repeat: {n}, ease: "sine.inOut", stagger: 0.05, transformOrigin: "50% 100%" }}, {s+0.3:.2f});
      tl.fromTo("#thr-{i}", {{ opacity: 0.4 }}, {{ opacity: 1, duration: 0.6, yoyo: true, repeat: {n}, ease: "power1.inOut" }}, {s+0.5:.2f});
      tl.from("#vis-{i} .vis-badge", {{ y: 22, opacity: 0, duration: 0.5, ease: "power2.out" }}, {s+0.4:.2f});'''

def anim_hammer(i, s, e):
    return f'''tl.fromTo("#doc-{i}", {{ y: 30, opacity: 0 }}, {{ y: 0, opacity: 1, duration: 0.5, ease: "power2.out" }}, {s:.2f});
      tl.fromTo("#stamp-{i}", {{ rotation: -28, y: -95, opacity: 0, scale: 1.4 }}, {{ rotation: 0, y: 0, opacity: 1, scale: 1, duration: 0.32, ease: "back.in(2.4)", repeat: 2, repeatDelay: 1.0 }}, {s+0.8:.2f});
      tl.from("#vis-{i} .vis-badge", {{ y: 22, opacity: 0, duration: 0.5, ease: "power2.out" }}, {s+0.4:.2f});'''

def anim_scale(i, s, e):
    return f'''tl.from("#cmp-{i} .bar-cost", {{ scaleY: 0, duration: 0.7, ease: "power2.out", transformOrigin: "50% 100%" }}, {s+0.4:.2f});
      tl.from("#cmp-{i} .bar-gain", {{ scaleY: 0, duration: 1.0, ease: "power2.out", transformOrigin: "50% 100%" }}, {s+0.75:.2f});
      tl.from("#cmp-{i} .cmp-label", {{ y: 20, opacity: 0, duration: 0.5, stagger: 0.15, ease: "power2.out" }}, {s+1.3:.2f});
      tl.fromTo("#cmp-{i} .vs", {{ scale: 0.5, opacity: 0 }}, {{ scale: 1, opacity: 1, duration: 0.4, ease: "back.out(2)" }}, {s+1.9:.2f});
      tl.from("#vis-{i} .vis-badge", {{ y: 22, opacity: 0, duration: 0.5, ease: "power2.out" }}, {s+0.4:.2f});'''

ANIM = {"shake": anim_shake, "highway": anim_highway, "sensor": anim_sensor, "hammer": anim_hammer, "scale": anim_scale}

# ---------- 卡片 ----------

def card_html(sc, i):
    c = sc["card"]
    t = sc["type"]
    if t == "header":
        body = f'''<p class="eyebrow anim">{html.escape(c["eyebrow"])}</p>
        <h1 class="anim">{c["title"]}</h1>
        <p class="hsubtitle anim">{html.escape(c["subtitle"])}</p>
        <div class="stats anim">{render_stat(c["stats"])}</div>'''
    elif t == "outro":
        body = f'''<p class="eyebrow anim">{html.escape(c["eyebrow"])}</p>
        <div class="otitle anim">{c["title"]}</div>
        <p class="hsubtitle anim">{html.escape(c["subtitle"])}</p>
        <div class="octa anim">{html.escape(c["cta"])}</div>
        <div class="osub anim">{html.escape(c["sub"])}</div>'''
    else:
        big = ""
        if c.get("big"):
            big = f'''<div class="bigwrap anim"><div class="bignum">{html.escape(c["big"])}</div>
            <div class="biglabel">{html.escape(c["big_label"])}</div></div>'''
        sub = f'<p class="hsubtitle anim">{html.escape(c["subtitle"])}</p>' if c.get("subtitle") else ""
        body = f'''<p class="eyebrow anim">{html.escape(c["eyebrow"])}</p>
        <h2 class="anim">{c["title"]}</h2>
        {sub}
        {big}'''
    return f'<div class="card{" ocard" if t=="outro" else ""}">{body}</div>'

def main():
    script = json.load(open(os.path.join(STORY, "script.json"), encoding="utf-8"))
    scenes = script["scenes"]
    lines = script["lines"]
    DUR = round(lines[-1]["end"] + 0.4, 2)
    wm = script.get("watermark", "jerrychen2001")
    date = script.get("date", "")

    scene_divs = []
    for i, sc in enumerate(scenes):
        s, e = sc["_start"], sc["_end"]
        v = sc.get("visual", "shake")
        scene_divs.append(f'''<div id="scene-{i}" class="scene clip" data-start="{s:.2f}" data-duration="{e-s:.2f}" data-track-index="3">{VIS[v](i)}{card_html(sc, i)}</div>''')

    sub_divs, tl_lines = [], []
    for i, ln in enumerate(lines):
        s, e = ln["start"], ln["end"]
        sub_divs.append(f'''<div id="sub-{i}" class="subtitle clip" data-start="{s:.2f}" data-duration="{e-s:.2f}" data-track-index="10"><div class="sub-inner">{html.escape(ln["text"])}</div></div>''')
        tl_lines.append(f'''tl.from("#sub-{i} .sub-inner", {{ y: 26, opacity: 0, duration: 0.25, ease: "power2.out" }}, {s:.2f});
      tl.to("#sub-{i} .sub-inner", {{ opacity: 0, duration: 0.18, ease: "power2.in" }}, {e-0.18:.2f});
      tl.set("#sub-{i} .sub-inner", {{ opacity: 0 }}, {e:.2f});''')

    anim_lines = []
    for i, sc in enumerate(scenes):
        s, e = sc["_start"], sc["_end"]
        v = sc.get("visual", "shake")
        anim_lines.append(ANIM[v](i, s, e))
        anim_lines.append(f'''tl.from("#scene-{i} .card", {{ y: 44, opacity: 0, duration: 0.5, ease: "power3.out" }}, {s:.2f});
      tl.from("#scene-{i} .anim", {{ y: 26, opacity: 0, duration: 0.45, stagger: 0.09, ease: "power2.out" }}, {s+0.18:.2f});
      tl.from("#scene-{i} .vis", {{ scale: 1.06, opacity: 0, duration: 0.6, ease: "power2.out" }}, {s:.2f});
      tl.fromTo("#scene-{i} .card::after", {{ xPercent: 0 }}, {{ xPercent: 375, duration: 0.9, ease: "power2.inOut" }}, {s+0.35:.2f});
      tl.to("#scene-{i} .card", {{ opacity: 0, y: -18, duration: 0.3, ease: "power2.in" }}, {e-0.32:.2f});
      tl.set("#scene-{i} .card", {{ opacity: 0 }}, {e:.2f});''')

    page = f'''<!doctype html>
<html lang="zh-CN">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=1080, height=1920" />
    <script src="https://cdn.jsdelivr.net/npm/gsap@3.14.2/dist/gsap.min.js"></script>
    <style>
      @font-face {{ font-family: "PingFang SC"; src: local("PingFang SC"); }}
      :root {{
        /* 赤焰热力主题（参考 theme-heat-red.css）R/G/B=1/0.35/0.15 推导色阶 */
        --theme:#FF5926; --theme-deep:#B03D1A; --theme-mid:#E85122;
        --ink:#F2F2F5; --ink-2:#9A9AA3; --ink-3:#7A7A84;
        --line:rgba(255,89,38,.18); --card:rgba(26,26,30,.92);
        --heat-bg:#121214; --heat-surface:#1A1A1E; --heat-surface-2:#23232A;
      }}
      * {{ box-sizing:border-box; margin:0; padding:0; }}
      html, body {{ width:1080px; height:1920px; overflow:hidden;
        font-family:"PingFang SC",sans-serif; color:var(--ink); line-height:1.6;
        background:
          linear-gradient(rgba(255,89,38,.05) 1px, transparent 1px) 0 0/72px 72px,
          linear-gradient(90deg, rgba(255,89,38,.05) 1px, transparent 1px) 0 0/72px 72px,
          radial-gradient(1100px 780px at 6% -12%, rgba(176,61,26,.40), transparent 60%),
          radial-gradient(900px 620px at 102% 0%, rgba(255,89,38,.16), transparent 58%),
          radial-gradient(820px 820px at 50% 112%, rgba(18,18,20,.95), transparent 62%),
          linear-gradient(168deg,#121214 0%,#17171B 46%,#0D0F0F 100%);
      }}
      .scene {{ position:absolute; inset:0; display:flex; flex-direction:column;
        align-items:center; padding:150px 56px 400px; }}
      .topbar {{ position:absolute; top:56px; left:56px; right:56px; display:flex;
        justify-content:space-between; align-items:center; z-index:20;
        font-size:24px; color:var(--ink-3); }}
      .topbar .brand {{ font-weight:700; color:var(--theme); letter-spacing:.08em; }}
      .topbar .date {{ font-family:monospace; letter-spacing:.05em; }}
      .progress {{ position:absolute; top:0; left:0; height:4px;
        background:linear-gradient(90deg,var(--theme-deep),var(--theme)); z-index:30; width:0%;
        box-shadow:0 0 12px rgba(255,89,38,.9); }}
      .wm {{ position:absolute; right:40px; bottom:104px; z-index:25; font-size:44px; font-weight:600;
        color:rgba(255,255,255,.55); text-shadow:0 0 3px rgba(0,0,0,.55),0 1px 3px rgba(0,0,0,.40),0 -1px 2px rgba(0,0,0,.30); }}

      .vis {{ width:100%; height:560px; border-radius:20px; overflow:hidden; position:relative;
        border:1px solid var(--line); box-shadow:0 24px 60px -28px rgba(0,0,0,.85);
        margin-bottom:36px; background:#0D0F0F; }}
      .vis-svg {{ width:100%; height:100%; display:block; }}
      .vis-badge {{ position:absolute; left:20px; bottom:20px; font-size:22px; font-weight:700;
        letter-spacing:.06em; color:#121214; background:var(--theme); padding:9px 18px; border-radius:9px;
        box-shadow:0 0 20px rgba(255,89,38,.55); }}

      /* shake：手机 + 箭头 + 电商 */
      .v-shake {{ display:flex; align-items:center; }}
      .shake-stage {{ width:100%; height:100%; display:flex; align-items:center; justify-content:center; gap:26px;
        background:radial-gradient(700px 420px at 50% 40%, rgba(255,89,38,.10), transparent 65%),#101013; }}
      .phone {{ width:236px; height:472px; border-radius:38px; background:#0A0B0C; border:3px solid #3A3A44;
        box-shadow:0 18px 50px -20px rgba(0,0,0,.9); padding:14px 12px; flex:none; }}
      .phone-screen {{ width:100%; height:100%; border-radius:28px; background:#15161B; padding:26px 20px;
        display:flex; flex-direction:column; gap:16px; }}
      .ad-tag {{ font-size:18px; font-weight:700; color:var(--theme); letter-spacing:.16em; }}
      .ad-sk {{ height:22px; border-radius:6px; background:rgba(255,89,38,.16); }}
      .ad-sk.w80 {{ width:80%; }} .ad-sk.w60 {{ width:60%; }}
      .jump-arrow {{ width:74px; color:var(--theme); filter:drop-shadow(0 0 10px rgba(255,89,38,.7)); flex:none; }}
      .ad-target {{ width:216px; text-align:center; color:var(--theme); flex:none;
        padding:34px 14px; border-radius:20px; background:rgba(255,89,38,.07); border:1px solid var(--line); }}
      .ad-target .bag {{ width:86px; height:86px; }}
      .t-name {{ font-size:27px; font-weight:800; color:var(--ink); margin-top:10px; }}
      .t-sub {{ font-size:19px; color:var(--ink-3); margin-top:4px; }}

      /* hammer：通报文件 + 红印章 */
      .v-hammer {{ display:flex; align-items:center; justify-content:center;
        background:radial-gradient(700px 420px at 50% 40%, rgba(255,89,38,.10), transparent 65%),#101013; }}
      .doc {{ width:520px; background:#E9E6DE; border-radius:14px; padding:52px 48px;
        box-shadow:0 24px 60px -26px rgba(0,0,0,.85); position:relative; }}
      .doc-head {{ font-size:29px; font-weight:900; color:#1A1A1E; text-align:center; margin-bottom:34px; letter-spacing:.02em; }}
      .doc-line {{ height:16px; border-radius:8px; background:#C9C4B8; margin-bottom:20px; }}
      .doc-line.w92 {{ width:92%; }} .doc-line.w78 {{ width:78%; }} .doc-line.w85 {{ width:85%; }} .doc-line.w60 {{ width:60%; }}
      .stamp {{ position:absolute; right:44px; bottom:52px; width:140px; height:140px;
        filter:drop-shadow(0 6px 14px rgba(0,0,0,.35)); }}

      /* scale：成本 vs 收益 */
      .v-scale {{ display:flex; align-items:center; justify-content:center;
        background:radial-gradient(700px 420px at 50% 40%, rgba(255,89,38,.10), transparent 65%),#101013; }}
      .cmp {{ display:flex; align-items:flex-end; justify-content:center; gap:64px; }}
      .cmp-col {{ display:flex; flex-direction:column; align-items:center; }}
      .bar {{ width:150px; border-radius:16px 16px 0 0; }}
      .bar-cost {{ height:118px; background:linear-gradient(180deg,#4A4A54,#2A2A32); border:1px solid #3A3A44; }}
      .bar-gain {{ height:388px; background:linear-gradient(180deg,#FF8A5C,#B03D1A);
        box-shadow:0 0 40px rgba(255,89,38,.45); border:1px solid rgba(255,89,38,.5); }}
      .cmp-label {{ margin-top:20px; font-size:26px; font-weight:800; color:var(--ink-2); }}
      .vs {{ font-size:34px; font-weight:900; color:var(--theme); padding-bottom:180px;
        text-shadow:0 0 16px rgba(255,89,38,.5); }}

      .card {{ position:relative; width:100%; background:var(--card); border:1px solid var(--line);
        border-radius:24px; padding:48px 46px 50px;
        box-shadow:0 1px 2px rgba(0,0,0,.3),0 30px 60px -30px rgba(0,0,0,.7);
        overflow:hidden; }}
      .card::before {{ content:""; position:absolute; left:0; top:40px; bottom:40px; width:6px;
        border-radius:0 4px 4px 0; background:linear-gradient(180deg,var(--theme-mid),var(--theme-deep)); }}
      /* 热力扫光：卡片入场时一道橘红高光从左掠过 */
      .card::after {{ content:""; position:absolute; top:0; left:0; width:40%; height:100%;
        background:linear-gradient(100deg,transparent,rgba(255,89,38,.16),transparent);
        transform:skewX(-18deg) translateX(-250%); pointer-events:none; }}
      .eyebrow {{ font-size:24px; letter-spacing:.2em; color:var(--theme); font-weight:700; margin-bottom:22px; }}
      h1 {{ font-size:66px; line-height:1.24; font-weight:800; letter-spacing:-.01em; }}
      h2 {{ font-size:46px; line-height:1.3; font-weight:800; letter-spacing:-.005em; }}
      .accent {{ color:var(--theme); text-shadow:0 0 18px rgba(255,89,38,.5); }}
      .hsubtitle {{ margin-top:24px; color:var(--ink-2); font-size:27px; line-height:1.5; }}
      .stats {{ margin-top:38px; display:flex; flex-wrap:wrap; gap:16px; }}
      .stat {{ background:rgba(255,89,38,.08); border:1px solid var(--line); border-radius:16px;
        padding:20px 28px; min-width:250px; }}
      .stat .k {{ font-size:17px; letter-spacing:.1em; color:var(--ink-3); }}
      .stat .v {{ font-size:40px; font-weight:800; color:var(--theme); margin-top:6px; }}
      .bigwrap {{ margin-top:36px; background:linear-gradient(135deg,rgba(255,89,38,.14),rgba(255,89,38,.04));
        border:1px solid rgba(255,89,38,.24); border-radius:20px; padding:32px 40px; }}
      .bignum {{ font-size:86px; font-weight:900; line-height:1.1;
        background:linear-gradient(135deg,var(--theme) 0%,#FFB08A 100%);
        -webkit-background-clip:text; -webkit-text-fill-color:transparent; background-clip:text; }}
      .biglabel {{ margin-top:10px; font-size:23px; color:var(--ink-2); letter-spacing:.03em; line-height:1.5; }}
      .ocard {{ text-align:center; padding:72px 46px; }}
      .otitle {{ font-size:54px; font-weight:900; line-height:1.25; }}
      .octa {{ margin-top:34px; font-size:38px; font-weight:800; color:var(--theme);
        text-shadow:0 0 18px rgba(255,89,38,.45); }}
      .osub {{ margin-top:22px; font-size:28px; color:var(--ink-3); }}

      .subtitle {{ position:absolute; left:56px; right:56px; bottom:150px; z-index:15;
        display:flex; justify-content:center; pointer-events:none; }}
      .sub-inner {{ max-width:100%; padding:26px 34px; border-radius:24px;
        background:rgba(8,8,10,.9); backdrop-filter:blur(10px);
        box-shadow:0 14px 36px -18px rgba(0,0,0,.8); border-left:6px solid var(--theme);
        font-size:33px; font-weight:600; color:#fff; line-height:1.5; }}
    </style>
  </head>
  <body>
    <div id="root" data-composition-id="main" data-start="0" data-duration="{DUR}" data-width="1080" data-height="1920">
      <div id="progress" class="progress clip" data-start="0" data-duration="{DUR}" data-track-index="100"></div>
      <div id="topbar" class="topbar clip" data-start="0" data-duration="{DUR}" data-track-index="1">
        <span class="brand">{html.escape(wm)} · 热点深观察</span>
        <span class="date">{html.escape(date)}</span>
      </div>
      <div id="wm" class="wm clip" data-start="0" data-duration="{DUR}" data-track-index="2">{html.escape(wm)}</div>
      {chr(10).join(scene_divs)}
      {chr(10).join(sub_divs)}
      <audio id="narration-audio" data-start="0" data-duration="{DUR}" data-track-index="51" src="audio_combined.wav" data-volume="1.0"></audio>
    </div>
    <script>
      window.__timelines = window.__timelines || {{}};
      const tl = gsap.timeline({{ paused: true }});
      const DUR = {DUR};
      tl.to("#progress", {{ width: "100%", duration: DUR, ease: "none" }}, 0);
      {chr(10).join("      " + l for l in anim_lines)}
      {chr(10).join("      " + l for l in tl_lines)}
      window.__timelines["main"] = tl;
    </script>
  </body>
</html>'''

    open(os.path.join(STORY, "index.html"), "w", encoding="utf-8").write(page)
    open(os.path.join(STORY, "hyperframes.json"), "w").write(json.dumps({
        "name": "news-shake-ad", "width": 1080, "height": 1920, "fps": 30,
        "duration": DUR, "output": "output.mp4"
    }, ensure_ascii=False, indent=2))
    print(f"index.html 已生成，总时长 {DUR}s，{len(scenes)} 场景")

if __name__ == "__main__":
    main()
