#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从 script.json 生成 index.html（赤焰热力主题，TurboFieldfare：SVG 动效场景）"""
import json, os, html

STORY = os.path.dirname(os.path.abspath(__file__))

def render_stat(s):
    return "".join(f'<div class="stat"><div class="k">{html.escape(x["k"])}</div><div class="v">{html.escape(x["v"])}</div></div>' for x in s)

# ---------- 场景动效（SVG，全部挂在 GSAP 时间轴上，seek 安全）----------

def vis_chip(i):
    return f'''<div class="vis v-chip" id="vis-{i}">
      <div class="chip-stage">
        <div class="chip" id="chip-{i}">
          <svg viewBox="0 0 260 200">
            <g opacity="0.40">
              <rect x="4" y="52" width="98" height="96" rx="16" fill="none" stroke="#9A9AA3" stroke-width="5"/>
              <text x="53" y="100" font-size="33" fill="#9A9AA3" text-anchor="middle" font-family="monospace" font-weight="800">26B</text>
              <text x="53" y="132" font-size="17" fill="#9A9AA3" text-anchor="middle" font-family="monospace">params</text>
            </g>
            <path d="M114 100 H152" stroke="#E85122" stroke-width="7" stroke-linecap="round"/>
            <path d="M140 87 L160 100 L140 113" fill="none" stroke="#E85122" stroke-width="7" stroke-linecap="round" stroke-linejoin="round"/>
            <g>
              <rect x="170" y="44" width="84" height="112" rx="18" fill="rgba(255,89,38,.14)" stroke="#FF5926" stroke-width="5"/>
              <text x="212" y="96" font-size="27" fill="#FF5926" text-anchor="middle" font-family="monospace" font-weight="800">2GB</text>
              <text x="212" y="128" font-size="21" fill="#FF5926" text-anchor="middle" font-family="monospace" font-weight="800">RAM</text>
            </g>
            <text x="130" y="186" font-size="18" fill="#9A9AA3" text-anchor="middle" font-family="monospace">26B =&gt; ~2GB memory</text>
          </svg>
        </div>
        <div class="chip-label">8GB 的 MacBook Air，也能跑</div>
      </div>
      <div class="vis-badge">Apache-2.0 · 本地推理</div>
    </div>'''


def vis_toolcall(i):
    return f'''<div class="vis v-toolcall" id="vis-{i}">
      <div class="tc-stage">
        <div class="tc-bubble" id="tcq-{i}">
          <div class="tc-who">整份权重</div>
          <div class="tc-text">14.3GB 模型，8GB 的机器装不下</div>
        </div>
        <div class="tc-arrow" id="tca-{i}">
          <svg viewBox="0 0 80 120"><path d="M40 8 V96 M22 74 L40 100 L58 74" fill="none" stroke="currentColor" stroke-width="7" stroke-linecap="round" stroke-linejoin="round"/></svg>
        </div>
        <div class="tc-code" id="tcc-{i}">
          <div class="tc-line"><span class="k">memory</span><span class="s">:</span></div>
          <div class="tc-line i1"><span class="f">resident</span><span class="s">:</span> <span class="v">1.35GB 共享核心</span></div>
          <div class="tc-line i1"><span class="f">kv_cache</span><span class="s">:</span> <span class="v">FP16 常驻</span></div>
          <div class="tc-line i1"><span class="f">experts</span><span class="s">:</span> <span class="v">按需从 SSD 取</span></div>
          <div class="tc-line"><span class="c">// Swift 6.2 + Metal 4</span></div>
          <div class="tc-line"><span class="c">// 不是 MLX 包装</span></div>
        </div>
      </div>
      <div class="vis-badge">自研运行时 · 非 MLX 包装</div>
    </div>'''


def vis_bench(i):
    nodes = [("实测解码速度", 380, 26, 200, True, 30),
             ("M2 · 8GB", 110, 176, 200, False, 30),
             ("M5 Pro · 24GB", 650, 176, 200, False, 30),
             ("5.1-6.3 tok/s", 110, 296, 200, True, 28),
             ("31-35 tok/s", 650, 296, 200, True, 28),
             ("macOS 26 · Metal 4 · Swift 6.2", 200, 440, 560, False, 26)]
    items = []
    for name, x, y, w, hl, fs in nodes:
        items.append(f'''<g class="dev" transform="translate({x},{y})">
            <rect x="0" y="0" width="{w}" height="76" rx="14" fill="rgba(255,89,38,.10)" stroke="{"#FF5926" if hl else "#B03D1A"}" stroke-width="4"/>
            <text x="{w/2:.0f}" y="49" font-size="{fs}" fill="{"#FF5926" if hl else "#F2F2F5"}" text-anchor="middle" font-weight="700" font-family="PingFang SC,sans-serif">{name}</text>
          </g>''')
    return f'''<div class="vis v-deploy" id="vis-{i}">
      <svg viewBox="0 0 960 560" class="vis-svg">
        <rect width="960" height="560" fill="#101013"/>
        <path d="M480 102 V140 M210 140 H750 M210 140 V176 M750 140 V176 M210 252 V296 M750 252 V296 M480 372 V440" stroke="#5A2A16" stroke-width="3" fill="none"/>
        {"".join(items)}
      </svg>
      <div class="vis-badge">README 实测 · 验证机为 8GB M2 Air</div>
    </div>'''


def vis_cost(i):
    bars = [("内存 ~2GB", 140, 60, True), ("视觉包 ~1.1GB", 340, 33, False),
            ("磁盘 14.3GB", 540, 429, False), ("首次下载 ~15GB", 740, 450, False)]
    items = []
    for lbl, x, h, hl in bars:
        items.append(f'''<g class="rung" data-h="{h}">
            <text x="{x+60}" y="{540-h-16}" font-size="24" fill="{"#FF5926" if hl else "#9A9AA3"}" text-anchor="middle" font-weight="800" font-family="monospace">{lbl}</text>
            <rect x="{x}" y="{540-h}" width="120" height="{h}" rx="10" fill="{"#FF5926" if hl else "url(#lg-"+str(i)+")"}" stroke="{"#FFB08A" if hl else "#B03D1A"}" stroke-width="3"/>
          </g>''')
    return f'''<div class="vis v-ladder" id="vis-{i}">
      <svg viewBox="0 0 960 560" class="vis-svg" id="lad-{i}">
        <defs>
          <linearGradient id="lg-{i}" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0" stop-color="#8A3A1A"/><stop offset="1" stop-color="#4A2412"/>
          </linearGradient>
        </defs>
        <rect width="960" height="560" fill="#101013"/>
        <text x="40" y="56" font-size="26" fill="#9A9AA3" font-family="PingFang SC,sans-serif">内存占用 vs 磁盘占用（按 1GB ≈ 30px）</text>
        <line x1="40" y1="540" x2="920" y2="540" stroke="#2A2A32" stroke-width="3"/>
        {"".join(items)}
        <g id="flag-{i}" transform="translate(120,28)">
          <path d="M0 0 V150 M0 0 H100 M0 30 H84" stroke="#FF5926" stroke-width="4" fill="none" stroke-linecap="round"/>
          <rect x="14" y="6" width="216" height="46" rx="10" fill="rgba(255,89,38,.14)" stroke="#FF5926" stroke-width="2"/>
          <text x="122" y="38" font-size="23" fill="#FF5926" text-anchor="middle" font-family="PingFang SC,sans-serif">内存只有 ~2GB</text>
        </g>
      </svg>
      <div class="vis-badge">拿磁盘换内存 · 14.3GB 换 ~2GB</div>
    </div>'''


def vis_usage(i):
    rows = [("macapp", "下载 / 装载 / 生成"), ("cli", "命令行直接问"),
            ("server", "OpenAI 兼容服务"), ("concurrency", "同时只跑一个")]
    rhtml = "".join(f'<div class="ex-row"><span>{k}</span><b>{v}</b></div>' for k, v in rows)
    return f'''<div class="vis v-extract" id="vis-{i}">
      <div class="ex-stage">
        <div class="ex-messy" id="exm-{i}">
          <div class="ex-who">三种入口</div>
          <div class="ex-line">原生 Mac 应用</div>
          <div class="ex-line">命令行 CLI</div>
          <div class="ex-line">本地 OpenAI 服务</div>
        </div>
        <div class="ex-arrow" id="exa-{i}">
          <svg viewBox="0 0 80 120"><path d="M40 8 V96 M22 74 L40 100 L58 74" fill="none" stroke="currentColor" stroke-width="7" stroke-linecap="round" stroke-linejoin="round"/></svg>
        </div>
        <div class="ex-tidy" id="ext-{i}">
          <div class="ex-who">同一份模型目录</div>
          {rhtml}
        </div>
      </div>
      <div class="vis-badge">103 条实测实验记录 · 全公开</div>
    </div>'''


def vis_outro(i):
    nodes = [("8GB MacBook Air", 380, 30, 200, True, 27),
             ("26B 大模型", 110, 190, 200, False, 30),
             ("约 2GB 内存", 650, 190, 200, True, 30),
             ("Apache-2.0 · 独立项目 · 非 Google 官方", 200, 350, 560, False, 26)]
    items = []
    for name, x, y, w, hl, fs in nodes:
        items.append(f'''<g class="dev" transform="translate({x},{y})">
            <rect x="0" y="0" width="{w}" height="76" rx="14" fill="rgba(255,89,38,.10)" stroke="{"#FF5926" if hl else "#B03D1A"}" stroke-width="4"/>
            <text x="{w/2:.0f}" y="49" font-size="{fs}" fill="{"#FF5926" if hl else "#F2F2F5"}" text-anchor="middle" font-weight="700" font-family="PingFang SC,sans-serif">{name}</text>
          </g>''')
    return f'''<div class="vis v-deploy" id="vis-{i}">
      <svg viewBox="0 0 960 560" class="vis-svg">
        <rect width="960" height="560" fill="#101013"/>
        <path d="M480 106 V150 M210 150 H750 M210 150 V190 M750 150 V190 M480 266 V350" stroke="#5A2A16" stroke-width="3" fill="none"/>
        {"".join(items)}
        <text x="480" y="490" font-size="26" fill="#9A9AA3" text-anchor="middle" font-family="monospace">github.com/drumih/turbo-fieldfare</text>
      </svg>
      <div class="vis-badge">磁盘换内存 · 路子野但能跑</div>
    </div>'''


VIS = {"chip": vis_chip, "toolcall": vis_toolcall, "bench": vis_bench, "cost": vis_cost, "usage": vis_usage, "outro": vis_outro}

def anim_chip(i, s, e):
    n = int((e - s) / 0.6) + 2
    return f'''tl.fromTo("#chip-{i}", {{ scale: 0.7, opacity: 0, rotation: -8 }}, {{ scale: 1, opacity: 1, rotation: 0, duration: 0.7, ease: "back.out(1.6)" }}, {s:.2f});
      tl.to("#chip-{i}", {{ scale: 1.05, duration: 0.6, yoyo: true, repeat: {n}, ease: "sine.inOut" }}, {s+0.8:.2f});
      tl.from("#vis-{i} .chip-label", {{ y: 20, opacity: 0, duration: 0.5, ease: "power2.out" }}, {s+0.5:.2f});
      tl.from("#vis-{i} .vis-badge", {{ y: 22, opacity: 0, duration: 0.5, ease: "power2.out" }}, {s+0.4:.2f});'''

def anim_toolcall(i, s, e):
    n = int((e - s) / 1.2) + 2
    return f'''tl.from("#tcq-{i}", {{ x: -40, opacity: 0, duration: 0.5, ease: "power2.out" }}, {s+0.2:.2f});
      tl.from("#tca-{i}", {{ y: -16, opacity: 0, duration: 0.4, ease: "power2.out" }}, {s+0.7:.2f});
      tl.from("#tcc-{i}", {{ x: 40, opacity: 0, duration: 0.6, ease: "power2.out" }}, {s+1.0:.2f});
      tl.from("#tcc-{i} .tc-line", {{ opacity: 0, x: 14, duration: 0.3, stagger: 0.11, ease: "power1.out" }}, {s+1.15:.2f});
      tl.to("#tca-{i}", {{ y: 8, duration: 0.5, yoyo: true, repeat: {n}, ease: "sine.inOut" }}, {s+1.6:.2f});
      tl.from("#vis-{i} .vis-badge", {{ y: 22, opacity: 0, duration: 0.5, ease: "power2.out" }}, {s+0.4:.2f});'''

def anim_extract(i, s, e):
    return f'''tl.from("#exm-{i}", {{ x: -40, opacity: 0, duration: 0.5, ease: "power2.out" }}, {s+0.2:.2f});
      tl.from("#exa-{i}", {{ y: -16, opacity: 0, duration: 0.4, ease: "power2.out" }}, {s+0.7:.2f});
      tl.from("#ext-{i}", {{ x: 40, opacity: 0, duration: 0.6, ease: "power2.out" }}, {s+1.0:.2f});
      tl.from("#ext-{i} .ex-row", {{ opacity: 0, x: 14, duration: 0.3, stagger: 0.1, ease: "power1.out" }}, {s+1.2:.2f});
      tl.to("#exa-{i}", {{ y: 8, duration: 0.5, yoyo: true, repeat: 8, ease: "sine.inOut" }}, {s+1.7:.2f});
      tl.from("#vis-{i} .vis-badge", {{ y: 22, opacity: 0, duration: 0.5, ease: "power2.out" }}, {s+0.4:.2f});'''

def anim_ladder(i, s, e):
    return f'''tl.from("#lad-{i} .rung rect", {{ scaleY: 0, duration: 0.55, stagger: 0.1, ease: "power2.out", transformOrigin: "50% 100%" }}, {s+0.3:.2f});
      tl.from("#lad-{i} .rung text", {{ opacity: 0, y: 12, duration: 0.4, stagger: 0.1, ease: "power1.out" }}, {s+0.6:.2f});
      tl.fromTo("#flag-{i}", {{ scale: 0.4, opacity: 0 }}, {{ scale: 1, opacity: 1, duration: 0.5, ease: "back.out(2)" }}, {s+1.8:.2f});
      tl.to("#flag-{i}", {{ y: -8, duration: 0.6, yoyo: true, repeat: 6, ease: "sine.inOut" }}, {s+2.4:.2f});
      tl.from("#vis-{i} .vis-badge", {{ y: 22, opacity: 0, duration: 0.5, ease: "power2.out" }}, {s+0.4:.2f});'''

def anim_deploy(i, s, e):
    return f'''tl.from("#vis-{i} .dev", {{ scale: 0.6, opacity: 0, duration: 0.5, stagger: 0.13, ease: "back.out(1.8)" }}, {s+0.3:.2f});
      tl.to("#vis-{i} .dev", {{ y: -10, duration: 0.7, yoyo: true, repeat: 4, ease: "sine.inOut", stagger: 0.1 }}, {s+1.6:.2f});
      tl.from("#vis-{i} .vis-badge", {{ y: 22, opacity: 0, duration: 0.5, ease: "power2.out" }}, {s+0.4:.2f});'''

ANIM = {"chip": anim_chip, "toolcall": anim_toolcall, "bench": anim_deploy, "cost": anim_ladder, "usage": anim_extract, "outro": anim_deploy}

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
        v = sc.get("visual", "chip")
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
        v = sc.get("visual", "chip")
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

      /* chip：8MB 芯片 */
      .v-chip {{ display:flex; align-items:center; justify-content:center;
        background:radial-gradient(700px 420px at 50% 45%, rgba(255,89,38,.12), transparent 65%),#101013; }}
      .chip-stage {{ display:flex; flex-direction:column; align-items:center; gap:26px; }}
      .chip {{ width:300px; height:300px; filter:drop-shadow(0 0 30px rgba(255,89,38,.45)); }}
      .chip-label {{ font-size:30px; font-weight:800; color:var(--ink-2); letter-spacing:.06em; }}

      /* toolcall / extract：左右流转 */
      .v-toolcall, .v-extract {{ display:flex; align-items:center;
        background:radial-gradient(700px 420px at 50% 40%, rgba(255,89,38,.10), transparent 65%),#101013; }}
      .tc-stage, .ex-stage {{ width:100%; height:100%; display:flex; align-items:center; justify-content:center; gap:14px; padding:0 24px; }}
      .tc-bubble, .ex-messy {{ width:330px; flex:none; }}
      .tc-bubble {{ background:rgba(255,89,38,.10); border:1px solid var(--line); border-radius:22px 22px 22px 6px; padding:26px 24px; }}
      .tc-who, .ex-who {{ font-size:18px; font-weight:800; color:var(--theme); letter-spacing:.16em; margin-bottom:12px; }}
      .tc-text {{ font-size:25px; line-height:1.5; color:var(--ink); }}
      .tc-arrow, .ex-arrow {{ width:52px; color:var(--theme); flex:none; filter:drop-shadow(0 0 8px rgba(255,89,38,.6)); }}
      .tc-code {{ width:430px; flex:none; background:#0A0B0C; border:1px solid var(--line); border-radius:16px;
        padding:24px 26px; font-family:monospace; }}
      .tc-line {{ font-size:21px; line-height:1.75; color:var(--ink-2); white-space:nowrap; }}
      .tc-line.i1 {{ padding-left:26px; }}
      .tc-line .k {{ color:#7FB2FF; }} .tc-line .f {{ color:#FF8A5C; font-weight:700; }}
      .tc-line .n {{ color:#9A9AA3; }} .tc-line .v {{ color:#8FE0B0; }} .tc-line .s {{ color:var(--ink-3); }}
      .tc-line .c {{ color:#5A5A64; font-size:18px; }}
      .ex-messy {{ background:rgba(255,255,255,.05); border:1px dashed #4A4A54; border-radius:16px; padding:24px; }}
      .ex-line {{ font-size:21px; line-height:1.7; color:var(--ink-2); }}
      .ex-tidy {{ width:360px; flex:none; background:#0A0B0C; border:1px solid var(--line); border-radius:16px; padding:22px 24px; }}
      .ex-row {{ display:flex; justify-content:space-between; font-family:monospace; font-size:21px;
        line-height:1.8; color:var(--ink-3); border-bottom:1px solid rgba(255,255,255,.06); }}
      .ex-row b {{ color:#8FE0B0; font-weight:700; }}

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
        <span class="brand">{html.escape(wm)} · 开源情报站</span>
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
        "name": "turbo-fieldfare", "width": 1080, "height": 1920, "fps": 30,
        "duration": DUR, "output": "output.mp4"
    }, ensure_ascii=False, indent=2))
    print(f"index.html 已生成，总时长 {DUR}s，{len(scenes)} 场景")

if __name__ == "__main__":
    main()
