#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从 script.json 生成 index.html（电光青蓝主题，anyps5：PS5 原生移植场景）

主题换装说明（相对 ace-step-ui 赤焰热力）：
  --theme      #FF5926 -> #00A2C7（主色）
  --theme-deep #B03D1A -> #0E6E8C（深色，用于渐变上端/描边深档）
  --theme-mid  #E85122 -> #23AFD0（中间亮色）
  渐变 #FF5926->#FFB08A（暖）-> #00A2C7->#7FE3F5（冷）
  背景径向辉光由 橙红 改为 青；卡片 ::before 强调条同步。
  其余结构（clip/track/字幕/GSAP 时间轴）保持一致，确保渲染确定性不变。
"""
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
              <rect x="10" y="38" width="100" height="124" rx="16" fill="none" stroke="#5A6E78" stroke-width="5"/>
              <text x="60" y="112" font-size="26" fill="#5A6E78" text-anchor="middle" font-family="monospace" font-weight="800">PS5</text>
            </g>
            <path d="M116 101 H144" stroke="#23AFD0" stroke-width="7" stroke-linecap="round"/>
            <path d="M132 88 L152 101 L132 114" fill="none" stroke="#23AFD0" stroke-width="7" stroke-linecap="round" stroke-linejoin="round"/>
            <g>
              <rect x="156" y="30" width="98" height="140" rx="18" fill="rgba(0,162,199,.14)" stroke="#00A2C7" stroke-width="5"/>
              <text x="205" y="86" font-size="22" fill="#00A2C7" text-anchor="middle" font-family="monospace" font-weight="800">原生</text>
              <text x="205" y="118" font-size="22" fill="#00A2C7" text-anchor="middle" font-family="monospace" font-weight="800">运行</text>
              <text x="205" y="148" font-size="18" fill="#7FE3F5" text-anchor="middle" font-family="monospace" font-weight="700">无模拟层</text>
            </g>
            <text x="130" y="186" font-size="19" fill="#7A8A92" text-anchor="middle" font-family="monospace">PS5 exe => native</text>
          </svg>
        </div>
        <div class="chip-label">PS5 可执行文件 · 重链接成电脑原生程序</div>
      </div>
      <div class="vis-badge">原生移植 · 非模拟器</div>
    </div>'''


def vis_ladder(i):
    # 性能阶梯：模拟器损耗大 vs 原生运行高效
    steps = [
        (150, 230, "模拟器"),
        (420, 330, "半翻译"),
        (720, 420, "原生"),
    ]
    bars = []
    for idx, (x, h, lbl) in enumerate(steps):
        elite = idx == 2
        bars.append(f'''<g class="rung" data-h="{h}">
            <rect x="{x}" y="{540-h}" width="120" height="{h}" rx="10" fill="{"#00A2C7" if elite else "url(#lg-"+str(i)+")"}" stroke="{"#7FE3F5" if elite else "#0E6E8C"}" stroke-width="3"/>
            <text x="{x+60}" y="{540-h/2+12}" font-size="30" fill="{"#0A1216" if elite else "#CFE8F0"}" text-anchor="middle" font-weight="800" font-family="monospace">{lbl}</text>
          </g>''')
    return f'''<div class="vis v-ladder" id="vis-{i}">
      <svg viewBox="0 0 960 560" class="vis-svg" id="lad-{i}">
        <defs>
          <linearGradient id="lg-{i}" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0" stop-color="#0B5A72"/><stop offset="1" stop-color="#092E3C"/>
          </linearGradient>
        </defs>
        <rect width="960" height="560" fill="#0A1216"/>
        <text x="40" y="58" font-size="26" fill="#6E8A96" font-family="PingFang SC,sans-serif">同样硬件，三种跑法的帧数天花板</text>
        <line x1="40" y1="540" x2="920" y2="540" stroke="#1E323B" stroke-width="3"/>
        {"".join(bars)}
        <g id="flag-{i}" transform="translate(720,90)">
          <rect x="-118" y="-46" width="236" height="44" rx="12" fill="rgba(0,162,199,.14)" stroke="#00A2C7" stroke-width="2"/>
          <text x="0" y="-17" font-size="21" fill="#00A2C7" text-anchor="middle" font-weight="700" font-family="PingFang SC,sans-serif">GTX 1050 Ti 稳 60 帧</text>
          <path d="M0 0 L-9 -6 L9 -6 Z" fill="rgba(0,162,199,.14)" stroke="#00A2C7" stroke-width="2"/>
        </g>
      </svg>
      <div class="vis-badge">没有模拟层白吃性能</div>
    </div>'''


def vis_extract(i):
    # 场景 2（性能实证）：配置 → 帧数；场景 4（现状）：新项目 → 只验证一款
    if i == 2:
        return f'''<div class="vis v-extract" id="vis-{i}">
      <div class="ex-stage">
        <div class="ex-messy" id="exm-{i}">
          <div class="ex-who">实测配置</div>
          <div class="ex-line">GTX 1050 Ti + i5-7500</div>
          <div class="ex-line">Intel 核显 HD 620</div>
          <div class="ex-line">游戏：Dreaming Sarah</div>
        </div>
        <div class="ex-arrow" id="exa-{i}">
          <svg viewBox="0 0 80 120"><path d="M40 8 V96 M22 74 L40 100 L58 74" fill="none" stroke="currentColor" stroke-width="7" stroke-linecap="round" stroke-linejoin="round"/></svg>
        </div>
        <div class="ex-tidy" id="ext-{i}">
          <div class="ex-who">原生运行帧数</div>
          <div class="ex-row"><span>独显</span><b>稳定 60 帧</b></div>
          <div class="ex-row"><span>核显</span><b>36 帧</b></div>
          <div class="ex-row"><span>模拟层</span><b>无损耗</b></div>
        </div>
      </div>
      <div class="vis-badge">老配置也能跑 · 数据来自项目兼容性表</div>
    </div>'''
    # 场景 4：项目现状（诚实口径）
    return f'''<div class="vis v-extract" id="vis-{i}">
      <div class="ex-stage">
        <div class="ex-messy" id="exm-{i}">
          <div class="ex-who">优势：很新很活跃</div>
          <div class="ex-line">2026 年 8 月刚开源</div>
          <div class="ex-line">系统库覆盖持续推进</div>
          <div class="ex-line">进度徽章全部公开</div>
        </div>
        <div class="ex-arrow" id="exa-{i}">
          <svg viewBox="0 0 80 120"><path d="M40 8 V96 M22 74 L40 100 L58 74" fill="none" stroke="currentColor" stroke-width="7" stroke-linecap="round" stroke-linejoin="round"/></svg>
        </div>
        <div class="ex-tidy" id="ext-{i}">
          <div class="ex-who">但现状得讲清</div>
          <div class="ex-row"><span>已验证</span><b>仅 1 款游戏</b></div>
          <div class="ex-row"><span>大作</span><b>暂不支持</b></div>
          <div class="ex-row"><span>系统库</span><b>仍在补全</b></div>
        </div>
      </div>
      <div class="vis-badge">早期项目 · 想玩大作再等等</div>
    </div>'''


def vis_toolcall(i):
    # 场景 3（着色器翻译）与场景 5（法律边界）共用流转结构
    if i == 3:
        left_who = "PS5 侧"
        left_lines = ["游戏可执行文件", "专有着色器代码", "系统库调用（prx）"]
        right_who = "PC 侧（翻译后）"
        right_rows = [("exe", "重链接为原生格式"), ("shader", "转 SPIR-V 通用格式"), ("libs", "重实现供动态链接"), ("check", "SPIRV-Tools 校验")]
        badge = "Vulkan SPIR-V · SDL 手柄全支持"
    else:
        left_who = "项目提供"
        left_lines = ["重链接器与系统库实现", "移植工具链", "GPL-2.0 开源代码"]
        right_who = "项目不含（合规边界）"
        right_rows = [("firmware", "不分发版权固件"), ("keys", "不含加密密钥"), ("games", "不分发游戏本体"), ("you", "合规自行承担")]
        badge = "定位：研究 · 互操作 · 游戏保存"
    left_items = "".join(f'<div class="ex-line">{html.escape(x)}</div>' for x in left_lines)
    right_items = "".join(f'<div class="ex-row"><span>{html.escape(k)}</span><b>{html.escape(v)}</b></div>' for k, v in right_rows)
    return f'''<div class="vis v-extract" id="vis-{i}">
      <div class="ex-stage">
        <div class="ex-messy" id="exm-{i}">
          <div class="ex-who">{html.escape(left_who)}</div>
          {left_items}
        </div>
        <div class="ex-arrow" id="exa-{i}">
          <svg viewBox="0 0 80 120"><path d="M40 8 V96 M22 74 L40 100 L58 74" fill="none" stroke="currentColor" stroke-width="7" stroke-linecap="round" stroke-linejoin="round"/></svg>
        </div>
        <div class="ex-tidy" id="ext-{i}">
          <div class="ex-who">{html.escape(right_who)}</div>
          {right_items}
        </div>
      </div>
      <div class="vis-badge">{html.escape(badge)}</div>
    </div>'''


VIS = {"chip": vis_chip, "ladder": vis_ladder, "extract": vis_extract, "toolcall": vis_toolcall}

def anim_chip(i, s, e):
    n = int((e - s) / 0.6) + 2
    return f'''tl.fromTo("#chip-{i}", {{ scale: 0.7, opacity: 0, rotation: -8 }}, {{ scale: 1, opacity: 1, rotation: 0, duration: 0.7, ease: "back.out(1.6)" }}, {s:.2f});
      tl.to("#chip-{i}", {{ scale: 1.05, duration: 0.6, yoyo: true, repeat: {n}, ease: "sine.inOut" }}, {s+0.8:.2f});
      tl.from("#vis-{i} .chip-label", {{ y: 20, opacity: 0, duration: 0.5, ease: "power2.out" }}, {s+0.5:.2f});
      tl.from("#vis-{i} .vis-badge", {{ y: 22, opacity: 0, duration: 0.5, ease: "power2.out" }}, {s+0.4:.2f});'''

def anim_ladder(i, s, e):
    return f'''tl.from("#lad-{i} .rung rect", {{ scaleY: 0, duration: 0.55, stagger: 0.1, ease: "power2.out", transformOrigin: "50% 100%" }}, {s+0.3:.2f});
      tl.from("#lad-{i} .rung text", {{ opacity: 0, y: 12, duration: 0.4, stagger: 0.1, ease: "power1.out" }}, {s+0.6:.2f});
      tl.fromTo("#flag-{i}", {{ opacity: 0 }}, {{ opacity: 1, duration: 0.5, ease: "power2.out" }}, {s+1.8:.2f});
      tl.from("#vis-{i} .vis-badge", {{ y: 22, opacity: 0, duration: 0.5, ease: "power2.out" }}, {s+0.4:.2f});'''

def anim_extract(i, s, e):
    return f'''tl.from("#exm-{i}", {{ x: -40, opacity: 0, duration: 0.5, ease: "power2.out" }}, {s+0.2:.2f});
      tl.from("#exa-{i}", {{ y: -16, opacity: 0, duration: 0.4, ease: "power2.out" }}, {s+0.7:.2f});
      tl.from("#ext-{i}", {{ x: 40, opacity: 0, duration: 0.6, ease: "power2.out" }}, {s+1.0:.2f});
      tl.from("#ext-{i} .ex-row", {{ opacity: 0, x: 14, duration: 0.3, stagger: 0.1, ease: "power1.out" }}, {s+1.2:.2f});
      tl.to("#exa-{i}", {{ y: 8, duration: 0.5, yoyo: true, repeat: 8, ease: "sine.inOut" }}, {s+1.7:.2f});
      tl.from("#vis-{i} .vis-badge", {{ y: 22, opacity: 0, duration: 0.5, ease: "power2.out" }}, {s+0.4:.2f});'''

ANIM = {"chip": anim_chip, "ladder": anim_ladder, "extract": anim_extract, "toolcall": anim_extract}

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
        body = f'''<p class="eyebrow anim">{html.escape(c["eyebrow"])}</p>
        <h2 class="anim">{c["title"]}</h2>
        {sub}'''
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
        /* 电光青蓝主题（替换赤焰热力） */
        --theme:#00A2C7; --theme-deep:#0E6E8C; --theme-mid:#23AFD0;
        --ink:#EAF6FA; --ink-2:#8FA9B4; --ink-3:#6E8A96;
        --line:rgba(0,162,199,.18); --card:rgba(16,24,28,.92);
      }}
      * {{ box-sizing:border-box; margin:0; padding:0; }}
      html, body {{ width:1080px; height:1920px; overflow:hidden;
        font-family:"PingFang SC",sans-serif; color:var(--ink); line-height:1.6;
        background:
          linear-gradient(rgba(0,162,199,.05) 1px, transparent 1px) 0 0/72px 72px,
          linear-gradient(90deg, rgba(0,162,199,.05) 1px, transparent 1px) 0 0/72px 72px,
          radial-gradient(1100px 780px at 6% -12%, rgba(14,110,140,.40), transparent 60%),
          radial-gradient(900px 620px at 102% 0%, rgba(0,162,199,.16), transparent 58%),
          radial-gradient(820px 820px at 50% 112%, rgba(10,18,22,.95), transparent 62%),
          linear-gradient(168deg,#0C1418 0%,#101A20 46%,#080D10 100%);
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
        box-shadow:0 0 12px rgba(0,162,199,.9); }}
      .wm {{ position:absolute; right:40px; bottom:104px; z-index:25; font-size:44px; font-weight:600;
        color:rgba(255,255,255,.55); text-shadow:0 0 3px rgba(0,0,0,.55),0 1px 3px rgba(0,0,0,.40),0 -1px 2px rgba(0,0,0,.30); }}

      .vis {{ width:100%; height:560px; border-radius:20px; overflow:hidden; position:relative;
        border:1px solid var(--line); box-shadow:0 24px 60px -28px rgba(0,0,0,.85);
        margin-bottom:36px; background:#080D10; }}
      .vis-svg {{ width:100%; height:100%; display:block; }}
      .vis-badge {{ position:absolute; left:20px; bottom:20px; font-size:22px; font-weight:700;
        letter-spacing:.06em; color:#06141A; background:var(--theme); padding:9px 18px; border-radius:9px;
        box-shadow:0 0 20px rgba(0,162,199,.55); }}

      /* chip：PS5 → 原生运行 */
      .v-chip {{ display:flex; align-items:center; justify-content:center;
        background:radial-gradient(700px 420px at 50% 45%, rgba(0,162,199,.12), transparent 65%),#0A1216; }}
      .chip-stage {{ display:flex; flex-direction:column; align-items:center; gap:26px; }}
      .chip {{ width:300px; height:300px; filter:drop-shadow(0 0 30px rgba(0,162,199,.45)); }}
      .chip-label {{ font-size:28px; font-weight:800; color:var(--ink-2); letter-spacing:.04em; }}

      /* extract：左右流转 */
      .v-extract {{ display:flex; align-items:center;
        background:radial-gradient(700px 420px at 50% 40%, rgba(0,162,199,.10), transparent 65%),#0A1216; }}
      .ex-stage {{ width:100%; height:100%; display:flex; align-items:center; justify-content:center; gap:14px; padding:0 24px; }}
      .ex-messy {{ width:330px; flex:none; background:rgba(255,255,255,.05); border:1px dashed #3A545E; border-radius:16px; padding:24px; }}
      .ex-who {{ font-size:18px; font-weight:800; color:var(--theme); letter-spacing:.16em; margin-bottom:12px; }}
      .ex-line {{ font-size:21px; line-height:1.7; color:var(--ink-2); }}
      .ex-arrow {{ width:52px; color:var(--theme); flex:none; filter:drop-shadow(0 0 8px rgba(0,162,199,.6)); }}
      .ex-tidy {{ width:360px; flex:none; background:#060C0F; border:1px solid var(--line); border-radius:16px; padding:22px 24px; }}
      .ex-row {{ display:flex; justify-content:space-between; font-family:monospace; font-size:20px;
        line-height:1.8; color:var(--ink-3); border-bottom:1px solid rgba(255,255,255,.06); }}
      .ex-row b {{ color:#8FE3C8; font-weight:700; }}

      .card {{ position:relative; width:100%; background:var(--card); border:1px solid var(--line);
        border-radius:24px; padding:48px 46px 50px;
        box-shadow:0 1px 2px rgba(0,0,0,.3),0 30px 60px -30px rgba(0,0,0,.7);
        overflow:hidden; }}
      .card::before {{ content:""; position:absolute; left:0; top:40px; bottom:40px; width:6px;
        border-radius:0 4px 4px 0; background:linear-gradient(180deg,var(--theme-mid),var(--theme-deep)); }}
      .card::after {{ content:""; position:absolute; top:0; left:0; width:40%; height:100%;
        background:linear-gradient(100deg,transparent,rgba(0,162,199,.16),transparent);
        transform:skewX(-18deg) translateX(-250%); pointer-events:none; }}
      .eyebrow {{ font-size:24px; letter-spacing:.2em; color:var(--theme); font-weight:700; margin-bottom:22px; }}
      h1 {{ font-size:66px; line-height:1.24; font-weight:800; letter-spacing:-.01em; }}
      h2 {{ font-size:46px; line-height:1.3; font-weight:800; letter-spacing:-.005em; }}
      .accent {{ color:var(--theme); text-shadow:0 0 18px rgba(0,162,199,.5); }}
      .hsubtitle {{ margin-top:24px; color:var(--ink-2); font-size:27px; line-height:1.5; }}
      .stats {{ margin-top:38px; display:flex; flex-wrap:wrap; gap:16px; }}
      .stat {{ background:rgba(0,162,199,.08); border:1px solid var(--line); border-radius:16px;
        padding:20px 28px; min-width:250px; }}
      .stat .k {{ font-size:17px; letter-spacing:.1em; color:var(--ink-3); }}
      .stat .v {{ font-size:40px; font-weight:800; color:var(--theme); margin-top:6px; }}
      .ocard {{ text-align:center; padding:72px 46px; }}
      .otitle {{ font-size:58px; font-weight:900; line-height:1.25; }}
      .octa {{ margin-top:34px; font-size:38px; font-weight:800; color:var(--theme);
        text-shadow:0 0 18px rgba(0,162,199,.45); }}
      .osub {{ margin-top:22px; font-size:28px; color:var(--ink-3); }}

      .subtitle {{ position:absolute; left:56px; right:56px; bottom:150px; z-index:15;
        display:flex; justify-content:center; pointer-events:none; }}
      .sub-inner {{ max-width:100%; padding:26px 34px; border-radius:24px;
        background:rgba(6,12,15,.9); backdrop-filter:blur(10px);
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
        "name": "anyps5", "width": 1080, "height": 1920, "fps": 30,
        "duration": DUR, "output": "output.mp4"
    }, ensure_ascii=False, indent=2))
    print(f"index.html 已生成，总时长 {DUR}s，{len(scenes)} 场景")

if __name__ == "__main__":
    main()
