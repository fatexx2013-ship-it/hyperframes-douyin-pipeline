#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从 script.json 生成 index.html（电光青蓝主题，lunatranslator：实时翻译原理场景）"""
import json, os, html

STORY = os.path.dirname(os.path.abspath(__file__))

def render_stat(s):
    return "".join(f'<div class="stat"><div class="k">{html.escape(x["k"])}</div><div class="v">{html.escape(x["v"])}</div></div>' for x in s)

# ---------- 场景动效 ----------

def vis_chip(i):
    return f'''<div class="vis v-chip" id="vis-{i}">
      <div class="chip-stage">
        <div class="chip" id="chip-{i}">
          <svg viewBox="0 0 260 200">
            <g opacity="0.38">
              <rect x="12" y="46" width="104" height="108" rx="16" fill="none" stroke="#5A6E78" stroke-width="5"/>
              <text x="64" y="108" font-size="22" fill="#5A6E78" text-anchor="middle" font-family="monospace" font-weight="800">ゲーム</text>
            </g>
            <path d="M124 100 H150" stroke="#23AFD0" stroke-width="7" stroke-linecap="round"/>
            <path d="M140 87 L160 100 L140 113" fill="none" stroke="#23AFD0" stroke-width="7" stroke-linecap="round" stroke-linejoin="round"/>
            <g>
              <rect x="160" y="30" width="92" height="140" rx="18" fill="rgba(0,162,199,.14)" stroke="#00A2C7" stroke-width="5"/>
              <text x="206" y="82" font-size="21" fill="#00A2C7" text-anchor="middle" font-family="monospace" font-weight="800">实时</text>
              <text x="206" y="112" font-size="21" fill="#00A2C7" text-anchor="middle" font-family="monospace" font-weight="800">中文</text>
              <text x="206" y="146" font-size="17" fill="#7FE3F5" text-anchor="middle" font-family="monospace" font-weight="700">不改本体</text>
            </g>
            <text x="130" y="186" font-size="19" fill="#7A8A92" text-anchor="middle" font-family="monospace">JP => ZH live</text>
          </svg>
        </div>
        <div class="chip-label">游戏照常跑 · 它在旁边实时翻译</div>
      </div>
      <div class="vis-badge">视觉小说翻译器 · 本地零成本</div>
    </div>'''


def vis_extract(i):
    # 场景 1：HOOK 原理（游戏函数 → 拦截 → 翻译）
    if i == 1:
        return f'''<div class="vis v-extract" id="vis-{i}">
      <div class="ex-stage">
        <div class="ex-messy" id="exm-{i}">
          <div class="ex-who">游戏进程内</div>
          <div class="ex-line">显示文字调用函数</div>
          <div class="ex-line">参数 = 日文原文</div>
        </div>
        <div class="ex-arrow" id="exa-{i}">
          <svg viewBox="0 0 80 120"><path d="M40 8 V96 M22 74 L40 100 L58 74" fill="none" stroke="currentColor" stroke-width="7" stroke-linecap="round" stroke-linejoin="round"/></svg>
        </div>
        <div class="ex-tidy" id="ext-{i}">
          <div class="ex-who">钩子拦截后</div>
          <div class="ex-row"><span>inject</span><b>注入钩子</b></div>
          <div class="ex-row"><span>hook</span><b>截下原文</b></div>
          <div class="ex-row"><span>translate</span><b>译成中文</b></div>
          <div class="ex-row"><span>game</span><b>本体不改</b></div>
        </div>
      </div>
      <div class="vis-badge">HOOK 原理 · 内存层实时拦截</div>
    </div>'''
    # 场景 3：模拟器支持列表（诚实标注 GBA 缺席）
    return f'''<div class="vis v-extract" id="vis-{i}">
      <div class="ex-stage">
        <div class="ex-messy" id="exm-{i}">
          <div class="ex-who">官方支持</div>
          <div class="ex-line">NS · PSP · PSV</div>
          <div class="ex-line">PS2 · PS3</div>
        </div>
        <div class="ex-arrow" id="exa-{i}">
          <svg viewBox="0 0 80 120"><path d="M40 8 V96 M22 74 L40 100 L58 74" fill="none" stroke="currentColor" stroke-width="7" stroke-linecap="round" stroke-linejoin="round"/></svg>
        </div>
        <div class="ex-tidy" id="ext-{i}">
          <div class="ex-who">但得讲清楚</div>
          <div class="ex-row"><span>GBA</span><b>不在列表</b></div>
          <div class="ex-row"><span>GBA 玩法</span><b>只能 OCR</b></div>
          <div class="ex-row"><span>模拟器</span><b>要够新版本</b></div>
        </div>
      </div>
      <div class="vis-badge">主机平台覆盖广 · GBA 是例外</div>
    </div>'''


def vis_toolcall(i):
    # 场景 2：OCR 兜底 + 翻译引擎自选
    return f'''<div class="vis v-extract" id="vis-{i}">
      <div class="ex-stage">
        <div class="ex-messy" id="exm-{i}">
          <div class="ex-who">HOOK 搞不定时</div>
          <div class="ex-line">直接截图</div>
          <div class="ex-line">认屏幕上的字</div>
        </div>
        <div class="ex-arrow" id="exa-{i}">
          <svg viewBox="0 0 80 120"><path d="M40 8 V96 M22 74 L40 100 L58 74" fill="none" stroke="currentColor" stroke-width="7" stroke-linecap="round" stroke-linejoin="round"/></svg>
        </div>
        <div class="ex-tidy" id="ext-{i}">
          <div class="ex-who">OCR + 引擎自选</div>
          <div class="ex-row"><span>OCR</span><b>万能但慢</b></div>
          <div class="ex-row"><span>本地模型</span><b>零成本</b></div>
          <div class="ex-row"><span>在线 API</span><b>随你选</b></div>
          <div class="ex-row"><span>词典</span><b>可离线</b></div>
        </div>
      </div>
      <div class="vis-badge">万能兜底 · 翻译引擎全程自选</div>
    </div>'''


VIS = {"chip": vis_chip, "extract": vis_extract, "toolcall": vis_toolcall}

def anim_chip(i, s, e):
    n = int((e - s) / 0.6) + 2
    return f'''tl.fromTo("#chip-{i}", {{ scale: 0.7, opacity: 0, rotation: -8 }}, {{ scale: 1, opacity: 1, rotation: 0, duration: 0.7, ease: "back.out(1.6)" }}, {s:.2f});
      tl.to("#chip-{i}", {{ scale: 1.05, duration: 0.6, yoyo: true, repeat: {n}, ease: "sine.inOut" }}, {s+0.8:.2f});
      tl.from("#vis-{i} .chip-label", {{ y: 20, opacity: 0, duration: 0.5, ease: "power2.out" }}, {s+0.5:.2f});
      tl.from("#vis-{i} .vis-badge", {{ y: 22, opacity: 0, duration: 0.5, ease: "power2.out" }}, {s+0.4:.2f});'''

def anim_extract(i, s, e):
    return f'''tl.from("#exm-{i}", {{ x: -40, opacity: 0, duration: 0.5, ease: "power2.out" }}, {s+0.2:.2f});
      tl.from("#exa-{i}", {{ y: -16, opacity: 0, duration: 0.4, ease: "power2.out" }}, {s+0.7:.2f});
      tl.from("#ext-{i}", {{ x: 40, opacity: 0, duration: 0.6, ease: "power2.out" }}, {s+1.0:.2f});
      tl.from("#ext-{i} .ex-row", {{ opacity: 0, x: 14, duration: 0.3, stagger: 0.1, ease: "power1.out" }}, {s+1.2:.2f});
      tl.to("#exa-{i}", {{ y: 8, duration: 0.5, yoyo: true, repeat: 6, ease: "sine.inOut" }}, {s+1.7:.2f});
      tl.from("#vis-{i} .vis-badge", {{ y: 22, opacity: 0, duration: 0.5, ease: "power2.out" }}, {s+0.4:.2f});'''

ANIM = {"chip": anim_chip, "extract": anim_extract, "toolcall": anim_extract}

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
    DUR = round(lines[-1]["end"] + 0.35, 2)
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
      .vis-badge {{ position:absolute; left:20px; bottom:20px; font-size:22px; font-weight:700;
        letter-spacing:.06em; color:#06141A; background:var(--theme); padding:9px 18px; border-radius:9px;
        box-shadow:0 0 20px rgba(0,162,199,.55); }}

      .v-chip {{ display:flex; align-items:center; justify-content:center;
        background:radial-gradient(700px 420px at 50% 45%, rgba(0,162,199,.12), transparent 65%),#0A1216; }}
      .chip-stage {{ display:flex; flex-direction:column; align-items:center; gap:26px; }}
      .chip {{ width:300px; height:300px; filter:drop-shadow(0 0 30px rgba(0,162,199,.45)); }}
      .chip-label {{ font-size:28px; font-weight:800; color:var(--ink-2); letter-spacing:.04em; }}

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
        "name": "lunatranslator", "width": 1080, "height": 1920, "fps": 30,
        "duration": DUR, "output": "output.mp4"
    }, ensure_ascii=False, indent=2))
    print(f"index.html 已生成，总时长 {DUR}s，{len(scenes)} 场景")

if __name__ == "__main__":
    main()
