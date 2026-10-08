#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从 script.json 生成 index.html（赤焰热力主题，影石纽约：SVG 动效场景）"""
import json, os, html

STORY = "/Volumes/PSSD/抖音视频/story/insta360-nyc"

def render_stat(s):
    return "".join(f'<div class="stat"><div class="k">{html.escape(x["k"])}</div><div class="v">{html.escape(x["v"])}</div></div>' for x in s)

# ---------- 场景动效（SVG，全部挂在 GSAP 时间轴上，seek 安全）----------

def vis_times_square(i):
    wins = []
    for bx, by, bw, bh in ((40, 130, 200, 380), (300, 190, 340, 320), (720, 90, 200, 420)):
        for r in range(6):
            for c in range(4):
                if (r * 4 + c) % 3 != 0:
                    continue
                wx = bx + 22 + c * 44
                wy = by + 26 + r * 54
                if wy + 18 > by + bh:
                    continue
                wins.append(f'<rect class="win" x="{wx}" y="{wy}" width="16" height="20" rx="3" fill="#FF5926" opacity="{0.28 + (r % 3) * 0.22}"/>')
    persons = []
    for k in range(12):
        x = 250 + k * 46
        o = 1.0 if k < 10 else 0.45
        persons.append(f'''<g class="person" data-o="{o}" transform="translate({x},0)">
            <circle cx="0" cy="468" r="10" fill="#FF5926"/>
            <rect x="-7" y="480" width="14" height="38" rx="7" fill="#E85122"/>
          </g>''')
    return f'''<div class="vis v-ts" id="vis-{i}">
      <svg viewBox="0 0 960 560" class="vis-svg">
        <rect width="960" height="560" fill="#101013"/>
        <ellipse cx="480" cy="120" rx="520" ry="90" fill="rgba(255,89,38,.07)"/>
        <g class="bld" style="transform-box:fill-box;transform-origin:50% 100%;">
          <rect x="40" y="130" width="200" height="390" rx="10" fill="#1A1A20" stroke="#2A2A32" stroke-width="3"/>
          <rect x="300" y="190" width="340" height="330" rx="10" fill="#16161C" stroke="#2A2A32" stroke-width="3"/>
          <rect x="720" y="90" width="200" height="430" rx="10" fill="#1A1A20" stroke="#2A2A32" stroke-width="3"/>
          {"".join(wins)}
        </g>
        <g class="neon" transform="translate(720,52)">
          <rect x="-10" y="-26" width="220" height="52" rx="10" fill="rgba(255,89,38,.12)" stroke="#FF5926" stroke-width="2.5"/>
          <text x="100" y="10" font-size="26" fill="#FF5926" text-anchor="middle" font-weight="800" letter-spacing="3" font-family="monospace">INSTA360</text>
        </g>
        <g class="neon2" transform="translate(40,92)">
          <rect x="0" y="-24" width="150" height="48" rx="10" fill="rgba(255,89,38,.08)" stroke="#B03D1A" stroke-width="2.5"/>
          <text x="75" y="8" font-size="22" fill="#E85122" text-anchor="middle" font-weight="700" letter-spacing="2" font-family="monospace">TIMES SQ</text>
        </g>
        <line x1="20" y1="540" x2="940" y2="540" stroke="#2A2A32" stroke-width="4"/>
        <line x1="20" y1="552" x2="940" y2="552" stroke="rgba(255,89,38,.22)" stroke-width="2" stroke-dasharray="26 22"/>
        {"".join(persons)}
        <g class="flag61" transform="translate(880,420)">
          <path d="M0 0 V60" stroke="#FF5926" stroke-width="4" stroke-linecap="round"/>
          <rect x="4" y="0" width="76" height="46" rx="8" fill="rgba(255,89,38,.14)" stroke="#FF5926" stroke-width="2.5"/>
          <text x="42" y="30" font-size="24" fill="#FF5926" text-anchor="middle" font-weight="800" font-family="monospace">61s</text>
        </g>
      </svg>
      <div class="vis-badge">拐过两条街 · 跑到队尾 61 秒</div>
    </div>'''

def vis_queue_night(i):
    ticks = []
    for h in range(12):
        import math
        a = math.radians(h * 30 - 90)
        x1, y1 = 280 + 148 * math.cos(a), 280 + 148 * math.sin(a)
        x2, y2 = 280 + 162 * math.cos(a), 280 + 162 * math.sin(a)
        ticks.append(f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" stroke="#4A4A54" stroke-width="5" stroke-linecap="round"/>')
    return f'''<div class="vis v-qn" id="vis-{i}">
      <svg viewBox="0 0 960 560" class="vis-svg">
        <rect width="960" height="560" fill="#101013"/>
        <ellipse cx="280" cy="280" rx="230" ry="230" fill="rgba(255,89,38,.06)"/>
        <g class="clock" transform="translate(0,0)">
          <circle cx="280" cy="280" r="178" fill="#0A0B0C" stroke="#FF5926" stroke-width="5"/>
          <circle cx="280" cy="280" r="150" fill="none" stroke="rgba(255,89,38,.18)" stroke-width="2"/>
          {"".join(ticks)}
          <g id="hand-h-{i}" style="transform-box:fill-box;transform-origin:50% 100%;transform:rotate(75deg)">
            <rect x="272" y="160" width="16" height="128" rx="8" fill="#E85122"/>
          </g>
          <g id="hand-m-{i}" style="transform-box:fill-box;transform-origin:50% 100%;transform:rotate(180deg)">
            <rect x="275" y="130" width="10" height="158" rx="5" fill="#FF5926"/>
          </g>
          <circle cx="280" cy="280" r="12" fill="#FF5926"/>
        </g>
        <g id="moon-{i}" transform="translate(660,180)">
          <path d="M70 0 A110 110 0 1 0 70 220 A88 88 0 1 1 70 0 Z" fill="#E85122" opacity="0.95"/>
          <text x="70" y="268" font-size="24" fill="#9A9AA3" text-anchor="middle" font-weight="700">凌晨 2:30</text>
        </g>
        <g id="sun-{i}" transform="translate(660,180)" opacity="0">
          <g id="sunrays-{i}">
            <circle cx="70" cy="110" r="62" fill="#FF5926"/>
            <g stroke="#FFB08A" stroke-width="7" stroke-linecap="round">
              <path d="M70 18 V-14"/><path d="M162 110 H196"/><path d="M70 202 V234"/><path d="M-22 110 H-56"/>
              <path d="M135 45 L158 22"/><path d="M135 175 L158 198"/><path d="M5 175 L-18 198"/><path d="M5 45 L-18 22"/>
            </g>
          </g>
          <text x="70" y="268" font-size="24" fill="#FF8A5C" text-anchor="middle" font-weight="700">中午 12:00</text>
        </g>
        <g class="nightbar" transform="translate(480,470)">
          <rect x="0" y="0" width="430" height="64" rx="32" fill="rgba(255,89,38,.10)" stroke="#FF5926" stroke-width="2.5"/>
          <text x="215" y="42" font-size="28" fill="#F2F2F5" text-anchor="middle" font-weight="700">通宵排队 · 近 10 小时</text>
        </g>
      </svg>
      <div class="vis-badge">头号粉丝 · 黄金 logo 限量版</div>
    </div>'''

def vis_world_map(i):
    continents = (
        "M60 130 L240 88 L310 150 L290 250 L200 300 L90 262 Z",      # 北美
        "M205 322 L278 344 L262 478 L212 492 L182 402 Z",             # 南美
        "M450 108 L566 100 L588 196 L508 224 L446 182 Z",             # 欧洲
        "M462 232 L592 224 L624 358 L562 442 L492 402 L452 322 Z",    # 非洲
        "M602 82 L882 92 L902 258 L762 302 L642 242 L602 162 Z",      # 亚洲
    )
    return f'''<div class="vis v-wm" id="vis-{i}">
      <svg viewBox="0 0 960 560" class="vis-svg">
        <rect width="960" height="560" fill="#0D0F0F"/>
        <g class="land" fill="#1A1A20" stroke="#2A2A32" stroke-width="3" stroke-linejoin="round">
          {''.join(f'<path d="{d}"/>' for d in continents)}
        </g>
        <path class="route" d="M560 318 Q380 120 246 172" fill="none" stroke="#FF5926" stroke-width="4.5"
          stroke-linecap="round" stroke-dasharray="12 10" opacity="0.9"/>
        <g class="pin" transform="translate(246,172)">
          <circle r="10" fill="#FF5926"/>
          <circle r="20" fill="none" stroke="#FF5926" stroke-width="2.5" opacity="0.5"/>
          <rect x="26" y="-24" width="104" height="48" rx="10" fill="rgba(255,89,38,.12)" stroke="#FF5926" stroke-width="2"/>
          <text x="78" y="6" font-size="24" fill="#FF5926" text-anchor="middle" font-weight="800">纽约</text>
        </g>
        <g class="pin" transform="translate(560,318)">
          <circle r="10" fill="#B03D1A"/>
          <circle r="20" fill="none" stroke="#B03D1A" stroke-width="2.5" opacity="0.5"/>
          <rect x="-142" y="18" width="116" height="48" rx="10" fill="rgba(176,61,26,.12)" stroke="#B03D1A" stroke-width="2"/>
          <text x="-84" y="48" font-size="24" fill="#E85122" text-anchor="middle" font-weight="800">埃及</text>
        </g>
        <g id="plane-{i}" transform="translate(560,318)">
          <path d="M34 0 L-26 -20 L-10 0 L-26 20 Z" fill="#FF5926"/>
          <circle cx="30" cy="0" r="4" fill="#FFB08A"/>
        </g>
        <g class="kmdist" transform="translate(700,442)">
          <rect x="-118" y="-32" width="236" height="64" rx="32" fill="rgba(255,89,38,.10)" stroke="#FF5926" stroke-width="2.5"/>
          <text x="0" y="10" font-size="28" fill="#FF5926" text-anchor="middle" font-weight="800" font-family="monospace">≈ 9,800 km</text>
        </g>
      </svg>
      <div class="vis-badge">埃及没有经销商 · 专程飞纽约</div>
    </div>'''

def vis_product(i):
    return f'''<div class="vis v-pr" id="vis-{i}">
      <svg viewBox="0 0 960 560" class="vis-svg">
        <rect width="960" height="560" fill="#101013"/>
        <ellipse cx="480" cy="200" rx="330" ry="150" fill="rgba(255,89,38,.07)"/>
        <g id="ring-{i}" transform="translate(480,196)" style="transform-box:fill-box;transform-origin:50% 50%;">
          <circle r="148" fill="none" stroke="rgba(255,89,38,.28)" stroke-width="3" stroke-dasharray="10 14"/>
        </g>
        <g class="cam" transform="translate(330,96)">
          <rect x="0" y="0" width="300" height="200" rx="40" fill="#1A1A20" stroke="#FF5926" stroke-width="5"/>
          <circle cx="92" cy="100" r="56" fill="#0A0B0C" stroke="#FF5926" stroke-width="5"/>
          <circle cx="92" cy="100" r="30" fill="#2A1410" stroke="#E85122" stroke-width="3"/>
          <circle cx="80" cy="88" r="8" fill="rgba(255,255,255,.35)"/>
          <circle cx="208" cy="100" r="56" fill="#0A0B0C" stroke="#FF5926" stroke-width="5"/>
          <circle cx="208" cy="100" r="30" fill="#2A1410" stroke="#E85122" stroke-width="3"/>
          <circle cx="196" cy="88" r="8" fill="rgba(255,255,255,.35)"/>
          <rect x="118" y="152" width="64" height="14" rx="7" fill="#3A3A44"/>
        </g>
        <g class="tag" transform="translate(60,150)">
          <rect width="230" height="58" rx="29" fill="rgba(255,89,38,.10)" stroke="#FF5926" stroke-width="2.5"/>
          <text x="115" y="38" font-size="25" fill="#F2F2F5" text-anchor="middle" font-weight="700">Luna Ultra 双摄云台</text>
        </g>
        <g class="tag" transform="translate(670,150)">
          <rect width="230" height="58" rx="29" fill="rgba(255,89,38,.10)" stroke="#FF5926" stroke-width="2.5"/>
          <text x="115" y="38" font-size="25" fill="#F2F2F5" text-anchor="middle" font-weight="700">X6 全景相机</text>
        </g>
        <g class="rank" transform="translate(120,392)">
          <rect width="300" height="110" rx="18" fill="#0A0B0C" stroke="#FF5926" stroke-width="3"/>
          <text x="150" y="52" font-size="30" fill="#9A9AA3" text-anchor="middle" font-weight="700">中国电商销量榜</text>
          <text x="150" y="92" font-size="40" fill="#FF5926" text-anchor="middle" font-weight="900" font-family="monospace">No.1</text>
        </g>
        <g class="rank" transform="translate(540,392)">
          <rect width="300" height="110" rx="18" fill="#0A0B0C" stroke="#FF5926" stroke-width="3"/>
          <text x="150" y="52" font-size="30" fill="#9A9AA3" text-anchor="middle" font-weight="700">美国电商销量榜</text>
          <text x="150" y="92" font-size="40" fill="#FF5926" text-anchor="middle" font-weight="900" font-family="monospace">No.1</text>
        </g>
        <text id="cnt-{i}" x="480" y="356" font-size="46" fill="#FF8A5C" text-anchor="middle" font-weight="900" font-family="monospace">0 万台</text>
      </svg>
      <div class="vis-badge">全球出货突破 1,000 万台</div>
    </div>'''

def vis_decade(i):
    nodes = [
        (200, "Casey", "千万粉丝 Vlog 祖师爷", "开业站台"),
        (480, "100 名骑手", "纽约骑行社区穿城", "黄色车队"),
        (760, "Anthony", "8 年老用户 · 两届头号粉丝", "凌晨 3 点排队"),
    ]
    ndefs = []
    for x, name, sub, tag in nodes:
        ndefs.append(f'''<g class="dnode" transform="translate({x},0)">
            <circle cx="0" cy="280" r="13" fill="#FF5926"/>
            <circle cx="0" cy="280" r="24" fill="none" stroke="#FF5926" stroke-width="2.5" opacity="0.45"/>
            <rect x="-118" y="120" width="236" height="112" rx="16" fill="rgba(255,89,38,.08)" stroke="#FF5926" stroke-width="2.5"/>
            <text x="0" y="158" font-size="27" fill="#F2F2F5" text-anchor="middle" font-weight="800">{name}</text>
            <text x="0" y="192" font-size="20" fill="#9A9AA3" text-anchor="middle">{sub}</text>
            <text x="0" y="220" font-size="20" fill="#E85122" text-anchor="middle" font-weight="700">{tag}</text>
          </g>''')
    return f'''<div class="vis v-dc" id="vis-{i}">
      <svg viewBox="0 0 960 560" class="vis-svg">
        <rect width="960" height="560" fill="#101013"/>
        <line class="axis" x1="70" y1="280" x2="890" y2="280" stroke="#3A3A44" stroke-width="5" stroke-linecap="round"/>
        <line id="axisfill-{i}" x1="70" y1="280" x2="890" y2="280" stroke="#FF5926" stroke-width="5" stroke-linecap="round"
          pathLength="100" stroke-dasharray="100" stroke-dashoffset="100"/>
        <text x="70" y="330" font-size="26" fill="#9A9AA3" text-anchor="middle" font-weight="700" font-family="monospace">2016</text>
        <text x="890" y="330" font-size="26" fill="#FF5926" text-anchor="middle" font-weight="700" font-family="monospace">2026</text>
        {"".join(ndefs)}
        <g class="quote" transform="translate(480,470)">
          <rect x="-400" y="-44" width="800" height="88" rx="20" fill="rgba(255,89,38,.08)" stroke="#FF5926" stroke-width="2.5"/>
          <text x="0" y="14" font-size="30" fill="#F2F2F5" text-anchor="middle" font-weight="700">先让自己成为当地生活的一部分</text>
        </g>
      </svg>
      <div class="vis-badge">在美国深耕整整十年</div>
    </div>'''

VIS = {"times-square": vis_times_square, "queue-night": vis_queue_night,
       "world-map": vis_world_map, "product": vis_product, "decade": vis_decade}

def anim_times_square(i, s, e):
    return f'''tl.from("#vis-{i} .bld", {{ scaleY: 0, opacity: 0, duration: 0.7, ease: "power2.out", transformOrigin: "50% 100%" }}, {s+0.2:.2f});
      tl.from("#vis-{i} .win", {{ opacity: 0, duration: 0.3, stagger: 0.02, ease: "power1.out" }}, {s+0.5:.2f});
      tl.to("#vis-{i} .win", {{ opacity: 0.25, duration: 0.5, yoyo: true, repeat: 4, ease: "sine.inOut", stagger: {{ each: 0.04, from: "random" }} }}, {s+1.6:.2f});
      tl.from("#vis-{i} .person", {{ y: 26, opacity: 0, duration: 0.4, stagger: 0.07, ease: "back.out(1.6)" }}, {s+0.9:.2f});
      tl.to("#vis-{i} .neon", {{ opacity: 0.55, duration: 0.5, yoyo: true, repeat: 6, ease: "sine.inOut" }}, {s+1.2:.2f});
      tl.fromTo("#vis-{i} .flag61", {{ scale: 0.4, opacity: 0 }}, {{ scale: 1, opacity: 1, duration: 0.5, ease: "back.out(2)" }}, {s+2.0:.2f});
      tl.to("#vis-{i} .flag61", {{ y: -8, duration: 0.6, yoyo: true, repeat: 5, ease: "sine.inOut" }}, {s+2.6:.2f});
      tl.from("#vis-{i} .vis-badge", {{ y: 22, opacity: 0, duration: 0.5, ease: "power2.out" }}, {s+0.4:.2f});'''

def anim_queue_night(i, s, e):
    return f'''tl.from("#vis-{i} .clock", {{ scale: 0.7, opacity: 0, duration: 0.6, ease: "back.out(1.7)" }}, {s+0.2:.2f});
      tl.to("#hand-m-{i}", {{ rotation: "+=900", duration: 2.4, ease: "power1.inOut" }}, {s+0.8:.2f});
      tl.to("#hand-h-{i}", {{ rotation: "+=285", duration: 2.4, ease: "power1.inOut" }}, {s+0.8:.2f});
      tl.to("#moon-{i}", {{ opacity: 0, scale: 0.6, duration: 0.8, ease: "power2.in" }}, {s+2.2:.2f});
      tl.to("#sun-{i}", {{ opacity: 1, scale: 1, duration: 0.8, ease: "back.out(1.7)" }}, {s+2.4:.2f});
      tl.to("#sunrays-{i}", {{ rotation: 60, duration: 1.2, ease: "none" }}, {s+3.2:.2f});
      tl.from("#vis-{i} .nightbar", {{ y: 24, opacity: 0, duration: 0.5, ease: "power2.out" }}, {s+1.0:.2f});
      tl.from("#vis-{i} .vis-badge", {{ y: 22, opacity: 0, duration: 0.5, ease: "power2.out" }}, {s+0.4:.2f});'''

def anim_world_map(i, s, e):
    return f'''tl.from("#vis-{i} .land", {{ opacity: 0, duration: 0.6, stagger: 0.08, ease: "power1.out" }}, {s+0.2:.2f});
      tl.fromTo("#vis-{i} .route", {{ strokeDashoffset: 520 }}, {{ strokeDashoffset: 0, duration: 1.8, ease: "power1.inOut" }}, {s+0.7:.2f});
      tl.from("#vis-{i} .pin", {{ scale: 0.3, opacity: 0, duration: 0.5, stagger: 0.35, ease: "back.out(2)" }}, {s+1.0:.2f});
      tl.fromTo("#plane-{i}", {{ x: 560, y: 318 }}, {{ x: 246, y: 172, duration: 2.2, ease: "power1.inOut" }}, {s+0.9:.2f});
      tl.to("#plane-{i}", {{ rotation: -8, duration: 0.5, yoyo: true, repeat: 3, ease: "sine.inOut" }}, {s+1.4:.2f});
      tl.from("#vis-{i} .kmdist", {{ y: 20, opacity: 0, duration: 0.5, ease: "power2.out" }}, {s+1.6:.2f});
      tl.from("#vis-{i} .vis-badge", {{ y: 22, opacity: 0, duration: 0.5, ease: "power2.out" }}, {s+0.4:.2f});'''

def anim_product(i, s, e):
    counter = f'''var c{i} = {{v: 0}};
      tl.to(c{i}, {{v: 1000, duration: 1.3, ease: "power1.out", onUpdate: function() {{
        var el = document.getElementById("cnt-{i}");
        if (el) el.textContent = Math.round(c{i}.v) + " 万台";
      }}}}, {s+1.6:.2f});'''
    return f'''tl.from("#vis-{i} .cam", {{ scale: 0.6, opacity: 0, duration: 0.6, ease: "back.out(1.7)" }}, {s+0.2:.2f});
      tl.to("#ring-{i}", {{ rotation: 360, duration: 1.6, ease: "none", repeat: 2 }}, {s+0.5:.2f});
      tl.from("#vis-{i} .tag", {{ x: {{ from: -30 }}, opacity: 0, duration: 0.5, stagger: 0.2, ease: "power2.out" }}, {s+0.9:.2f});
      tl.from("#vis-{i} .rank", {{ y: 24, opacity: 0, duration: 0.5, stagger: 0.18, ease: "power2.out" }}, {s+1.3:.2f});
      {counter}
      tl.from("#vis-{i} .vis-badge", {{ y: 22, opacity: 0, duration: 0.5, ease: "power2.out" }}, {s+0.4:.2f});'''

def anim_decade(i, s, e):
    return f'''tl.fromTo("#axisfill-{i}", {{ strokeDashoffset: 100 }}, {{ strokeDashoffset: 0, duration: 1.6, ease: "power1.inOut" }}, {s+0.3:.2f});
      tl.from("#vis-{i} .dnode", {{ scale: 0.4, opacity: 0, duration: 0.5, stagger: 0.3, ease: "back.out(1.9)" }}, {s+0.9:.2f});
      tl.to("#vis-{i} .dnode circle:nth-child(1)", {{ scale: 1.25, duration: 0.6, yoyo: true, repeat: 4, ease: "sine.inOut", stagger: 0.3, transformOrigin: "50% 50%" }}, {s+2.4:.2f});
      tl.from("#vis-{i} .quote", {{ y: 26, opacity: 0, duration: 0.6, ease: "power2.out" }}, {s+2.0:.2f});
      tl.from("#vis-{i} .vis-badge", {{ y: 22, opacity: 0, duration: 0.5, ease: "power2.out" }}, {s+0.4:.2f});'''

ANIM = {"times-square": anim_times_square, "queue-night": anim_queue_night,
        "world-map": anim_world_map, "product": anim_product, "decade": anim_decade}

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
        v = sc.get("visual", "times-square")
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
        v = sc.get("visual", "times-square")
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
        "name": "insta360-nyc", "width": 1080, "height": 1920, "fps": 30,
        "duration": DUR, "output": "output.mp4"
    }, ensure_ascii=False, indent=2))
    print(f"index.html 已生成，总时长 {DUR}s，{len(scenes)} 场景")

if __name__ == "__main__":
    main()
