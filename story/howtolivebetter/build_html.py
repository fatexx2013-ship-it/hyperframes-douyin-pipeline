#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从 script.json 生成 index.html（赤焰热力主题，HowToLiveBetter：SVG 动效场景）"""
import json, os, html

STORY = os.path.dirname(os.path.abspath(__file__))

def render_stat(s):
    return "".join(f'<div class="stat"><div class="k">{html.escape(x["k"])}</div><div class="v">{html.escape(x["v"])}</div></div>' for x in s)

# ---------- 场景动效（SVG，全部挂在 GSAP 时间轴上，seek 安全）----------

def vis_hero_repo(i):
    """GitHub 仓库卡：星标数滚动 + 星星散布"""
    stars = []
    import random
    random.seed(7)
    for k in range(16):
        x, y = random.randint(60, 900), random.randint(40, 220)
        stars.append(f'<path class="spark" d="M{x} {y} l6 14 l14 6 l-14 6 l-6 14 l-6 -14 l-14 -6 l14 -6 Z" fill="#FF5926" opacity="{random.choice([0.25,0.4,0.6])}"/>')
    return f'''<div class="vis v-hr" id="vis-{i}">
      <svg viewBox="0 0 960 560" class="vis-svg">
        <rect width="960" height="560" fill="#101013"/>
        <ellipse cx="480" cy="120" rx="520" ry="90" fill="rgba(255,89,38,.07)"/>
        {"".join(stars)}
        <g class="repocard" transform="translate(130,170)">
          <rect width="700" height="240" rx="22" fill="#16161C" stroke="#FF5926" stroke-width="3"/>
          <rect x="0" y="0" width="700" height="64" rx="22" fill="rgba(255,89,38,.10)"/>
          <circle cx="44" cy="32" r="14" fill="#FF5926"/>
          <circle cx="88" cy="32" r="14" fill="#E85122"/>
          <circle cx="132" cy="32" r="14" fill="#B03D1A"/>
          <text x="660" y="41" font-size="26" fill="#9A9AA3" text-anchor="end" font-family="monospace">README.md</text>
          <text x="44" y="130" font-size="34" fill="#F2F2F5" font-weight="800" font-family="monospace">eternity4719/HowToLiveBetter</text>
          <text x="44" y="180" font-size="27" fill="#9A9AA3">按性价比排序的循证生活指南</text>
          <g transform="translate(44,196)">
            <rect width="150" height="30" rx="15" fill="rgba(255,89,38,.12)" stroke="#FF5926" stroke-width="2"/>
            <text x="75" y="21" font-size="20" fill="#FF5926" text-anchor="middle" font-weight="700">HTML</text>
          </g>
          <g class="starbtn" transform="translate(560,196)">
            <path d="M18 0 l5 12 l12 5 l-12 5 l-5 12 l-5 -12 l-12 -5 l12 -5 Z" fill="#FF5926"/>
            <text x="40" y="17" font-size="22" fill="#F2F2F5" font-weight="800" font-family="monospace">Star</text>
          </g>
        </g>
        <g class="starcnt" transform="translate(480,470)">
          <rect x="-230" y="-44" width="460" height="88" rx="20" fill="rgba(255,89,38,.09)" stroke="#FF5926" stroke-width="2.5"/>
          <text id="cnt-{i}" x="0" y="16" font-size="44" fill="#FF8A5C" text-anchor="middle" font-weight="900" font-family="monospace">0 stars</text>
        </g>
      </svg>
      <div class="vis-badge">GitHub 热门 · 一天冲上榜单</div>
    </div>'''

def vis_rank_list(i):
    """性价比排行榜：高低条形 + 排名"""
    rows = [
        ("低成本 · 证据硬", 0.95, "排最前"),
        ("成本中 · 证据中", 0.62, ""),
        ("花大钱 · 证据弱", 0.30, "往后靠"),
    ]
    bars = []
    for k, (label, w, tag) in enumerate(rows):
        y = 120 + k * 130
        bars.append(f'''<g class="rrow" transform="translate(0,{y})">
            <text x="60" y="52" font-size="28" fill="#F2F2F5" font-weight="700">{label}</text>
            <rect x="60" y="70" width="700" height="30" rx="15" fill="#1A1A20" stroke="#2A2A32" stroke-width="2"/>
            <rect class="rfill" data-w="{int(w*700)}" x="60" y="70" width="0" height="30" rx="15" fill="{ "#FF5926" if k==0 else ("#E85122" if k==1 else "#B03D1A")}"/>
            <text x="830" y="94" font-size="24" fill="#9A9AA3" text-anchor="end" font-weight="700">{tag}</text>
          </g>''')
    return f'''<div class="vis v-rl" id="vis-{i}">
      <svg viewBox="0 0 960 560" class="vis-svg">
        <rect width="960" height="560" fill="#101013"/>
        <ellipse cx="480" cy="80" rx="480" ry="70" fill="rgba(255,89,38,.06)"/>
        <text x="60" y="74" font-size="30" fill="#9A9AA3" font-weight="700" letter-spacing="4">性 价 比 排 序</text>
        {"".join(bars)}
        <g class="crown" transform="translate(150,120)">
          <path d="M0 40 L40 0 L80 40 L120 0 L160 40 L160 90 L0 90 Z" fill="rgba(255,89,38,.14)" stroke="#FF5926" stroke-width="3"/>
          <text x="80" y="72" font-size="22" fill="#FF5926" text-anchor="middle" font-weight="800">最值</text>
        </g>
      </svg>
      <div class="vis-badge">照着清单从上往下做</div>
    </div>'''

def vis_shield_law(i):
    """盾牌 + 法律红线：急救与法律红线"""
    return f'''<div class="vis v-sl" id="vis-{i}">
      <svg viewBox="0 0 960 560" class="vis-svg">
        <rect width="960" height="560" fill="#101013"/>
        <ellipse cx="480" cy="100" rx="460" ry="80" fill="rgba(255,89,38,.07)"/>
        <g id="shield-{i}" transform="translate(380,90)" style="transform-box:fill-box;transform-origin:50% 20%;">
          <path d="M100 0 L190 32 V150 C190 220 148 268 100 292 C52 268 10 220 10 150 V32 Z"
            fill="rgba(255,89,38,.10)" stroke="#FF5926" stroke-width="5"/>
          <path class="pulse" d="M100 30 L165 55 V148 C165 200 134 238 100 258 C66 238 35 200 35 148 V55 Z"
            fill="none" stroke="#E85122" stroke-width="3" opacity="0.7"/>
          <text x="100" y="130" font-size="40" fill="#FF5926" text-anchor="middle" font-weight="900">红线</text>
          <text x="100" y="178" font-size="24" fill="#F2F2F5" text-anchor="middle" font-weight="700">不能踩</text>
        </g>
        <g class="skills" transform="translate(660,110)">
          <rect width="250" height="76" rx="16" fill="rgba(255,89,38,.09)" stroke="#FF5926" stroke-width="2.5"/>
          <text x="125" y="34" font-size="25" fill="#F2F2F5" text-anchor="middle" font-weight="800">海姆立克急救</text>
          <text x="125" y="62" font-size="21" fill="#9A9AA3" text-anchor="middle">最省事的学法</text>
        </g>
        <g class="skills" transform="translate(660,210)">
          <rect width="250" height="76" rx="16" fill="rgba(255,89,38,.09)" stroke="#E85122" stroke-width="2.5"/>
          <text x="125" y="34" font-size="25" fill="#F2F2F5" text-anchor="middle" font-weight="800">心肺复苏 CPR</text>
          <text x="125" y="62" font-size="21" fill="#9A9AA3" text-anchor="middle">关键时刻能救命</text>
        </g>
        <g class="skills" transform="translate(660,310)">
          <rect width="250" height="76" rx="16" fill="rgba(255,89,38,.09)" stroke="#B03D1A" stroke-width="2.5"/>
          <text x="125" y="34" font-size="25" fill="#F2F2F5" text-anchor="middle" font-weight="800">失业 / 工伤</text>
          <text x="125" y="62" font-size="21" fill="#9A9AA3" text-anchor="middle">官方文件给依据</text>
        </g>
        <g class="lawbar" transform="translate(80,440)">
          <rect width="520" height="70" rx="35" fill="rgba(255,89,38,.10)" stroke="#FF5926" stroke-width="2.5"/>
          <text x="260" y="45" font-size="27" fill="#F2F2F5" text-anchor="middle" font-weight="700">医保社保 · 每条给出官方依据</text>
        </g>
      </svg>
      <div class="vis-badge">踩红线的代价是真金白银</div>
    </div>'''

def vis_ten_domains(i):
    """十大领域网格：逐格点亮"""
    names = ["长寿防病","急救技能","省钱理财","法律红线","失业工伤","医保社保","恋爱婚育","怀孕育儿","创业合规","出国技能"]
    cells = []
    for k, nm in enumerate(names):
        cx, cy = 80 + (k % 5) * 168, 130 + (k // 5) * 190
        cells.append(f'''<g class="dcell" transform="translate({cx},{cy})">
            <rect width="150" height="150" rx="20" fill="#16161C" stroke="#FF5926" stroke-width="3"/>
            <circle class="ddot" cx="75" cy="52" r="14" fill="#FF5926"/>
            <text x="75" y="108" font-size="23" fill="#F2F2F5" text-anchor="middle" font-weight="800">{nm}</text>
          </g>''')
    return f'''<div class="vis v-td" id="vis-{i}">
      <svg viewBox="0 0 960 560" class="vis-svg">
        <rect width="960" height="560" fill="#101013"/>
        <ellipse cx="480" cy="80" rx="480" ry="60" fill="rgba(255,89,38,.06)"/>
        <text x="480" y="72" font-size="28" fill="#9A9AA3" text-anchor="middle" font-weight="700" letter-spacing="4">十 大 领 域 全 覆 盖</text>
        {"".join(cells)}
      </svg>
      <div class="vis-badge">拿不到论文依据的 · 一律不收</div>
    </div>'''

def vis_compass_map(i):
    """指南针：循证生活地图"""
    ticks = []
    import math
    for h in range(24):
        a = math.radians(h * 15 - 90)
        x1, y1 = 480 + 148 * math.cos(a), 280 + 148 * math.sin(a)
        x2, y2 = 480 + 168 * math.cos(a), 280 + 168 * math.sin(a)
        ticks.append(f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" stroke="#4A4A54" stroke-width="{5 if h%6==0 else 3}" stroke-linecap="round"/>')
    return f'''<div class="vis v-cm" id="vis-{i}">
      <svg viewBox="0 0 960 560" class="vis-svg">
        <rect width="960" height="560" fill="#0D0F0F"/>
        <g id="compass-{i}" transform="translate(0,0)" style="transform-box:fill-box;transform-origin:50% 50%;">
          <circle cx="480" cy="280" r="178" fill="#0A0B0C" stroke="#FF5926" stroke-width="5"/>
          <circle cx="480" cy="280" r="150" fill="none" stroke="rgba(255,89,38,.18)" stroke-width="2"/>
          {"".join(ticks)}
          <g id="needle-{i}" style="transform-box:fill-box;transform-origin:50% 50%;">
            <path d="M480 150 L508 280 L480 410 L452 280 Z" fill="#FF5926"/>
            <path d="M480 150 L480 280 L452 280 Z" fill="#FFB08A"/>
          </g>
          <circle cx="480" cy="280" r="12" fill="#FF5926"/>
          <text x="480" y="118" font-size="26" fill="#FF5926" text-anchor="middle" font-weight="900" letter-spacing="6">证 据</text>
          <text x="480" y="470" font-size="26" fill="#9A9AA3" text-anchor="middle" font-weight="700" letter-spacing="6">性 价 比</text>
        </g>
        <g class="routeline" transform="translate(720,120)">
          <rect x="-150" y="-40" width="200" height="80" rx="18" fill="rgba(255,89,38,.10)" stroke="#FF5926" stroke-width="2.5"/>
          <text x="-50" y="10" font-size="24" fill="#F2F2F5" text-anchor="middle" font-weight="800">每条查得到出处</text>
        </g>
      </svg>
      <div class="vis-badge">循证生活 · 有证据的地图</div>
    </div>'''

VIS = {"hero-repo": vis_hero_repo, "rank-list": vis_rank_list,
       "shield-law": vis_shield_law, "ten-domains": vis_ten_domains,
       "compass-map": vis_compass_map}

def anim_hero_repo(i, s, e):
    counter = f'''var c{i} = {{v: 0}};
      tl.to(c{i}, {{v: 12900, duration: 1.8, ease: "power1.out", onUpdate: function() {{
        var el = document.getElementById("cnt-{i}");
        if (el) el.textContent = Math.round(c{i}.v).toLocaleString() + " stars";
      }}}}, {s+1.2:.2f});'''
    return f'''tl.from("#vis-{i} .repocard", {{ scale: 0.7, opacity: 0, duration: 0.7, ease: "back.out(1.6)" }}, {s+0.2:.2f});
      tl.from("#vis-{i} .spark", {{ scale: 0, opacity: 0, duration: 0.4, stagger: 0.04, ease: "back.out(2)" }}, {s+0.6:.2f});
      tl.to("#vis-{i} .spark", {{ rotation: 90, duration: 1.2, yoyo: true, repeat: 3, ease: "sine.inOut", stagger: {{ each: 0.03, from: "random" }} }}, {s+1.6:.2f});
      tl.from("#vis-{i} .starbtn", {{ scale: 0.4, opacity: 0, duration: 0.5, ease: "back.out(2.2)" }}, {s+1.0:.2f});
      tl.to("#vis-{i} .starbtn", {{ scale: 1.15, duration: 0.4, yoyo: true, repeat: 4, ease: "sine.inOut" }}, {s+2.2:.2f});
      tl.from("#vis-{i} .starcnt", {{ y: 24, opacity: 0, duration: 0.5, ease: "power2.out" }}, {s+0.9:.2f});
      {counter}
      tl.from("#vis-{i} .vis-badge", {{ y: 22, opacity: 0, duration: 0.5, ease: "power2.out" }}, {s+0.4:.2f});'''

def anim_rank_list(i, s, e):
    fills = f'''document.querySelectorAll("#vis-{i} .rfill").forEach(function(el, k) {{
        var w = el.getAttribute("data-w");
        gsap.fromTo(el, {{ width: 0 }}, {{ width: w, duration: 0.9, ease: "power2.out", delay: k * 0.28 }});
      }});'''
    return f'''tl.from("#vis-{i} .rrow", {{ x: -40, opacity: 0, duration: 0.5, stagger: 0.25, ease: "power2.out" }}, {s+0.3:.2f});
      {fills}
      tl.from("#vis-{i} .crown", {{ scale: 0.3, opacity: 0, rotation: -20, duration: 0.6, ease: "back.out(2)" }}, {s+1.2:.2f});
      tl.to("#vis-{i} .crown", {{ y: -8, duration: 0.6, yoyo: true, repeat: 4, ease: "sine.inOut" }}, {s+2.0:.2f});
      tl.from("#vis-{i} .vis-badge", {{ y: 22, opacity: 0, duration: 0.5, ease: "power2.out" }}, {s+0.4:.2f});'''

def anim_shield_law(i, s, e):
    return f'''tl.from("#shield-{i}", {{ scale: 0.5, opacity: 0, duration: 0.7, ease: "back.out(1.7)" }}, {s+0.2:.2f});
      tl.to("#shield-{i} .pulse", {{ scale: 1.18, opacity: 0, duration: 1.1, ease: "power2.out", repeat: 3, repeatDelay: 0.5, transformOrigin: "50% 50%" }}, {s+1.0:.2f});
      tl.from("#vis-{i} .skills", {{ x: 60, opacity: 0, duration: 0.5, stagger: 0.22, ease: "power2.out" }}, {s+0.8:.2f});
      tl.from("#vis-{i} .lawbar", {{ y: 26, opacity: 0, duration: 0.5, ease: "power2.out" }}, {s+1.8:.2f});
      tl.to("#shield-{i}", {{ rotation: 2, duration: 0.5, yoyo: true, repeat: 4, ease: "sine.inOut" }}, {s+2.4:.2f});
      tl.from("#vis-{i} .vis-badge", {{ y: 22, opacity: 0, duration: 0.5, ease: "power2.out" }}, {s+0.4:.2f});'''

def anim_ten_domains(i, s, e):
    return f'''tl.from("#vis-{i} .dcell", {{ scale: 0.3, opacity: 0, duration: 0.45, stagger: 0.12, ease: "back.out(1.8)" }}, {s+0.2:.2f});
      tl.to("#vis-{i} .ddot", {{ scale: 1.5, duration: 0.5, yoyo: true, repeat: 3, ease: "sine.inOut", stagger: 0.1, transformOrigin: "50% 50%" }}, {s+1.8:.2f});
      tl.from("#vis-{i} .vis-badge", {{ y: 22, opacity: 0, duration: 0.5, ease: "power2.out" }}, {s+0.4:.2f});'''

def anim_compass_map(i, s, e):
    return f'''tl.from("#compass-{i}", {{ scale: 0.6, opacity: 0, duration: 0.8, ease: "back.out(1.6)" }}, {s+0.2:.2f});
      tl.to("#compass-{i}", {{ rotation: 8, duration: 1.4, yoyo: true, repeat: 3, ease: "sine.inOut" }}, {s+1.2:.2f});
      tl.to("#needle-{i}", {{ rotation: 360, duration: 2.6, ease: "power1.inOut" }}, {s+0.8:.2f});
      tl.from("#vis-{i} .routeline", {{ x: 40, opacity: 0, duration: 0.5, ease: "power2.out" }}, {s+1.6:.2f});
      tl.from("#vis-{i} .vis-badge", {{ y: 22, opacity: 0, duration: 0.5, ease: "power2.out" }}, {s+0.4:.2f});'''

ANIM = {"hero-repo": anim_hero_repo, "rank-list": anim_rank_list,
        "shield-law": anim_shield_law, "ten-domains": anim_ten_domains,
        "compass-map": anim_compass_map}

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
        body = f'''<div class="otitle anim">{c["title"]}</div>
        <div class="octa anim">{html.escape(c["cta"])}</div>
        <div class="osub anim">{html.escape(c["sub"])}</div>'''
    else:
        sub = f'<p class="hsubtitle anim">{html.escape(c["subtitle"])}</p>' if c.get("subtitle") else ""
        big = ""
        if c.get("big"):
            big = f'''<div class="bigwrap anim"><div class="bignum">{html.escape(c["big"])}</div>
            <div class="biglabel">{html.escape(c["big_label"])}</div></div>'''
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
        v = sc.get("visual", "hero-repo")
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
        v = sc.get("visual", "hero-repo")
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
        /* 赤焰热力主题 */
        --theme:#FF5926; --theme-deep:#B03D1A; --theme-mid:#E85122;
        --ink:#F2F2F5; --ink-2:#9A9AA3; --ink-3:#7A7A84;
        --line:rgba(255,89,38,.18); --card:rgba(26,26,30,.92);
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

      .card {{ position:relative; width:100%; background:var(--card); border:1px solid var(--line);
        border-radius:24px; padding:48px 46px 50px;
        box-shadow:0 1px 2px rgba(0,0,0,.3),0 30px 60px -30px rgba(0,0,0,.7);
        overflow:hidden; }}
      .card::before {{ content:""; position:absolute; left:0; top:40px; bottom:40px; width:6px;
        border-radius:0 4px 4px 0; background:linear-gradient(180deg,var(--theme-mid),var(--theme-deep)); }}
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
      .bignum {{ font-size:108px; font-weight:900; line-height:1.05;
        background:linear-gradient(135deg,var(--theme) 0%,#FFB08A 100%);
        -webkit-background-clip:text; -webkit-text-fill-color:transparent; background-clip:text; }}
      .biglabel {{ margin-top:8px; font-size:23px; color:var(--ink-2); letter-spacing:.03em; line-height:1.5; }}
      .ocard {{ text-align:center; padding:72px 46px; }}
      .otitle {{ font-size:58px; font-weight:900; line-height:1.25; }}
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
        <span class="brand">{html.escape(wm)} · 热点情报站</span>
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
        "name": "howtolivebetter", "width": 1080, "height": 1920, "fps": 30,
        "duration": DUR, "output": "output.mp4"
    }, ensure_ascii=False, indent=2))
    print(f"index.html 已生成，总时长 {DUR}s，{len(scenes)} 场景")

if __name__ == "__main__":
    main()
