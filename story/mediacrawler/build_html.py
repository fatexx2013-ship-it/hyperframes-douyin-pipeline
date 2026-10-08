#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从 script.json 生成 index.html（赤焰热力主题，mediacrawler：SVG 动效场景）

本 story 走产线默认档：出厂脚手架（storyctl new 复制 compositor-mac 模板）本体不动，
只把 5 个 VIS 场景的 SVG 内容与卡片文案换成 MediaCrawler 题材，并新增 chip2（合规定版）
变体；CSS / 动效时间轴 / 渲染超采样与两段门禁判据全部沿用默认。

V-BASE 视觉提亮基线（真源 docs/产线规范.md v1.12.0，2026-10-07 默认化；依据 cua 成片实证）：
  本模板即 `storyctl new` 的出厂脚手架，故基线直接落在模板本体，新建 story 天生带基线。
  基线只调「亮度梯度 / 表面明度」，**不改主题色相、不动版面结构、不加减动效**，也不触碰
  门禁判据与 config/ 共享参数真源（交付尺寸 / 编码仍由 post_process 收口）。
  参数（角色 → 取值口径）：
    1) 全局基色    : 三段线性基色抬亮约 +3~4 阶（#121214/#17171B/#0D0F0F → #15181D/#1A1E24/#0F1216）
    2) 中心光雾    : 新增 radial-gradient(1600×1200 at 50% 34%, rgba(主题,.07), transparent 72%)
    3) 四角主光/反光: 左上主题暖光 .40→.46、右上主题冷光 .16→.22（暖冷对撞不变量保持）
    4) 暗角        : 新增 radial-gradient(1400×1000 at 50% 48%, transparent 46%, rgba(6,7,9,.42))
    5) 网格纹理    : rgba(主题,.05)→.08（仍为 72px 网格，不改密度）
    6) 卡片表面    : --card rgba(26,26,30,.92) → rgba(27,30,36,.94)（+明度、不透明 +.02）
    7) 可视底板    : .vis 与各 v-* 模块底板 #101013/#0D0F0F → #151A20，内嵌 1px 顶部亮线
    8) 面板层级    : 代码/清单面板 #0A0B0C → #12161B（仍比底板深，保住「底板>面板」深度分层）
    9) 文案卡/字幕 : 表面提亮 + 边框不变（字幕底 rgba(8,8,10,.9) → rgba(16,18,22,.92)）
  回退：本文件 .bak-20261007；模板侧回退不影响已出片 story 的历史产物。
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
          <svg viewBox="0 0 200 200">
            <g opacity="0.40">
              <text x="44" y="122" font-size="86" fill="#9A9AA3" text-anchor="middle" font-family="monospace" font-weight="800">7</text>
              <line x1="8" y1="86" x2="84" y2="100" stroke="#E85122" stroke-width="6" stroke-linecap="round"/>
            </g>
            <g>
              <rect x="100" y="40" width="92" height="92" rx="16" fill="rgba(255,89,38,.14)" stroke="#FF5926" stroke-width="5"/>
              <text x="146" y="101" font-size="27" fill="#FF5926" text-anchor="middle" font-family="monospace" font-weight="800">DATA</text>
            </g>
            <text x="100" y="170" font-size="15" fill="#9A9AA3" text-anchor="middle" font-family="PingFang SC,sans-serif">小红书 · 抖音 · 快手 · B站</text>
            <text x="100" y="192" font-size="15" fill="#9A9AA3" text-anchor="middle" font-family="PingFang SC,sans-serif">微博 · 贴吧 · 知乎</text>
          </svg>
        </div>
        <div class="chip-label">7 大平台 · 一套代码</div>
      </div>
      <div class="vis-badge">多平台自媒体数据采集工具</div>
    </div>'''


def vis_chip2(i):
    """outro 合规定版：同一 chip 版式，改为留档口径（仅限学习研究）。"""
    return f'''<div class="vis v-chip" id="vis-{i}">
      <div class="chip-stage">
        <div class="chip" id="chip-{i}">
          <svg viewBox="0 0 200 200">
            <g>
              <rect x="28" y="50" width="144" height="98" rx="18" fill="rgba(255,89,38,.14)" stroke="#FF5926" stroke-width="5"/>
              <text x="100" y="112" font-size="25" fill="#FF5926" text-anchor="middle" font-family="monospace" font-weight="800">STUDY</text>
            </g>
            <text x="100" y="176" font-size="16" fill="#9A9AA3" text-anchor="middle" font-family="PingFang SC,sans-serif">仅限学习研究 · 禁止商业用途</text>
          </svg>
        </div>
        <div class="chip-label">仅限学习研究</div>
      </div>
      <div class="vis-badge">请遵守当地法律法规</div>
    </div>'''


def vis_toolcall(i):
    return f'''<div class="vis v-toolcall" id="vis-{i}">
      <div class="tc-stage">
        <div class="tc-bubble" id="tcq-{i}">
          <div class="tc-who">你的 Chrome</div>
          <div class="tc-text">保留登录态、Cookie 与扩展，复用真实浏览器环境，降低风控检测风险</div>
        </div>
        <div class="tc-arrow" id="tca-{i}">
          <svg viewBox="0 0 80 120"><path d="M40 8 V96 M22 74 L40 100 L58 74" fill="none" stroke="currentColor" stroke-width="7" stroke-linecap="round" stroke-linejoin="round"/></svg>
        </div>
        <div class="tc-code" id="tcc-{i}">
          <div class="tc-line"><span class="k">context</span>: <span class="s">[</span></div>
          <div class="tc-line i1"><span class="f">登录态缓存</span>(<span class="n">reuse</span>: <span class="v">true</span>)</div>
          <div class="tc-line i1"><span class="f">JS 表达式</span>(<span class="n">sign</span>: <span class="v">直接取</span>)</div>
          <div class="tc-line i1"><span class="f">远程调试</span>(<span class="n">cdp</span>: <span class="v">9222</span>)</div>
          <div class="tc-line"><span class="s">]</span> <span class="c">// 无需 JS 逆向 · 门槛大降</span></div>
        </div>
      </div>
      <div class="vis-badge">CDP 默认开启 · 可切标准 Playwright</div>
    </div>'''


def vis_extract(i):
    return f'''<div class="vis v-extract" id="vis-{i}">
      <div class="ex-stage">
        <div class="ex-messy" id="exm-{i}">
          <div class="ex-who">抓到的原始数据</div>
          <div class="ex-line">评论 · 一级 / 二级</div>
          <div class="ex-line">笔记与图文内容</div>
          <div class="ex-line">视频信息与封面</div>
          <div class="ex-line">创作者主页作品</div>
        </div>
        <div class="ex-arrow" id="exa-{i}">
          <svg viewBox="0 0 80 120"><path d="M40 8 V96 M22 74 L40 100 L58 74" fill="none" stroke="currentColor" stroke-width="7" stroke-linecap="round" stroke-linejoin="round"/></svg>
        </div>
        <div class="ex-tidy" id="ext-{i}">
          <div class="ex-who">结构化落盘 · 5 种格式</div>
          <div class="ex-row"><span>csv</span><b>表格</b></div>
          <div class="ex-row"><span>json / jsonl</span><b>通用</b></div>
          <div class="ex-row"><span>excel</span><b>开箱即用</b></div>
          <div class="ex-row"><span>sqlite</span><b>单文件库</b></div>
          <div class="ex-row"><span>mysql</span><b>进数据库</b></div>
        </div>
      </div>
      <div class="vis-badge">媒体下载默认关闭 · 按需开启</div>
    </div>'''


def vis_ladder(i):
    steps = [(60, 250, "关键词"), (170, 228, "帖子ID"), (280, 268, "二级评论"),
             (390, 210, "主页"), (500, 292, "登录态"), (610, 246, "代理池"), (720, 224, "词云")]
    bars = []
    for x, h, lbl in steps:
        elite = lbl == "登录态"
        bars.append(f'''<g class="rung" data-h="{h}">
            <rect x="{x}" y="{540-h}" width="78" height="{h}" rx="8" fill="{"url(#lg-"+str(i)+")" if not elite else "#FF5926"}" stroke="{"#FF5926" if not elite else "#FFB08A"}" stroke-width="3"/>
            <text x="{x+39}" y="{540-h-16}" font-size="24" fill="{"#9A9AA3" if not elite else "#FF5926"}" text-anchor="middle" font-weight="700" font-family="PingFang SC,sans-serif">{lbl}</text>
          </g>''')
    return f'''<div class="vis v-ladder" id="vis-{i}">
      <svg viewBox="0 0 960 560" class="vis-svg" id="lad-{i}">
        <defs>
          <linearGradient id="lg-{i}" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0" stop-color="#8A3A1A"/><stop offset="1" stop-color="#4A2412"/>
          </linearGradient>
        </defs>
        <rect width="960" height="560" fill="#151A20"/>
        <line x1="40" y1="540" x2="920" y2="540" stroke="#2A2A32" stroke-width="3"/>
        {"".join(bars)}
        <g id="flag-{i}" transform="translate(590,120)">
          <path d="M0 0 V210 M0 0 H104 M0 34 H88" stroke="#FF5926" stroke-width="4" fill="none" stroke-linecap="round"/>
          <rect x="14" y="6" width="198" height="52" rx="10" fill="rgba(255,89,38,.14)" stroke="#FF5926" stroke-width="2"/>
          <text x="113" y="40" font-size="22" fill="#FF5926" text-anchor="middle" font-family="PingFang SC,sans-serif">7 项全支持</text>
        </g>
      </svg>
      <div class="vis-badge">可视化 WebUI · 也能点点鼠标</div>
    </div>'''


def vis_deploy(i):
    tags = [("小红书", "15"), ("抖音", "150"), ("快手", "285"), ("B站", "420"),
            ("微博", "555"), ("贴吧", "690"), ("知乎", "825")]
    icons = []
    for name, x in tags:
        fs = 22 if len(name) <= 2 else 20
        icons.append(f'''<g class="dev" transform="translate({x},60)">
            <rect x="0" y="0" width="120" height="86" rx="14" fill="rgba(255,89,38,.10)" stroke="#FF5926" stroke-width="4"/>
            <text x="60" y="54" font-size="{fs}" fill="#F2F2F5" text-anchor="middle" font-family="PingFang SC,sans-serif" font-weight="700">{name}</text>
          </g>''')
    return f'''<div class="vis v-deploy" id="vis-{i}">
      <svg viewBox="0 0 960 400" class="vis-svg">
        <rect width="960" height="400" fill="#151A20"/>
        {"".join(icons)}
        <g class="dev" transform="translate(80,250)">
          <rect x="0" y="0" width="360" height="96" rx="12" fill="rgba(255,89,38,.10)" stroke="#FF5926" stroke-width="4"/>
          <text x="180" y="47" font-size="26" fill="#FF5926" text-anchor="middle" font-weight="700">封面 / 视频 / 图文</text>
          <text x="180" y="78" font-size="22" fill="#9A9AA3" text-anchor="middle">按帖子 ID 自动归档</text>
        </g>
        <g class="dev" transform="translate(470,250)">
          <rect x="0" y="0" width="360" height="96" rx="12" fill="rgba(255,89,38,.10)" stroke="#FF5926" stroke-width="4"/>
          <text x="180" y="47" font-size="26" fill="#FF5926" text-anchor="middle" font-weight="700">B站 DASH 合流</text>
          <text x="180" y="78" font-size="22" fill="#9A9AA3" text-anchor="middle">装 ffmpeg 取最高画质</text>
        </g>
      </svg>
      <div class="vis-badge">贴吧 / 知乎 暂无媒体字段</div>
    </div>'''

VIS = {"chip": vis_chip, "chip2": vis_chip2, "toolcall": vis_toolcall, "extract": vis_extract, "ladder": vis_ladder, "deploy": vis_deploy}

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

ANIM = {"chip": anim_chip, "chip2": anim_chip, "toolcall": anim_toolcall, "extract": anim_extract, "ladder": anim_ladder, "deploy": anim_deploy}

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
        /* 赤焰热力主题（色相不动，V-BASE 只抬明度） */
        --theme:#FF5926; --theme-deep:#B03D1A; --theme-mid:#E85122;
        --ink:#F2F2F5; --ink-2:#9A9AA3; --ink-3:#7A7A84;
        --line:rgba(255,89,38,.18);
        /* V-BASE 提亮基线⑥：卡片表面 +明度 / +不透明 */
        --card:rgba(27,30,36,.94);
      }}
      * {{ box-sizing:border-box; margin:0; padding:0; }}
      /* V-BASE 提亮基线①–⑤：暗角 + 四角主光/反光增强 + 中心光雾 + 网格提亮 + 基色抬亮 */
      html, body {{ width:1080px; height:1920px; overflow:hidden;
        font-family:"PingFang SC",sans-serif; color:var(--ink); line-height:1.6;
        background:
          radial-gradient(1400px 1000px at 50% 48%, transparent 46%, rgba(6,7,9,.42) 100%),
          radial-gradient(1100px 780px at 6% -12%, rgba(196,72,34,.46), transparent 60%),
          radial-gradient(900px 620px at 102% 0%, rgba(255,89,38,.22), transparent 58%),
          radial-gradient(1600px 1200px at 50% 34%, rgba(255,89,38,.07), transparent 72%),
          radial-gradient(820px 820px at 50% 112%, rgba(18,18,20,.92), transparent 62%),
          linear-gradient(rgba(255,89,38,.08) 1px, transparent 1px) 0 0/72px 72px,
          linear-gradient(90deg, rgba(255,89,38,.08) 1px, transparent 1px) 0 0/72px 72px,
          linear-gradient(168deg,#15181D 0%,#1A1E24 46%,#0F1216 100%);
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

      /* V-BASE 提亮基线⑦：可视底板 #0D0F0F → #151A20，补 1px 顶部内嵌亮线 */
      .vis {{ width:100%; height:560px; border-radius:20px; overflow:hidden; position:relative;
        border:1px solid var(--line);
        box-shadow:inset 0 1px 0 rgba(255,255,255,.05),0 26px 64px -30px rgba(0,0,0,.88);
        margin-bottom:36px; background:#151A20; }}
      .vis-svg {{ width:100%; height:100%; display:block; }}
      .vis-badge {{ position:absolute; left:20px; bottom:20px; font-size:22px; font-weight:700;
        letter-spacing:.06em; color:#121214; background:var(--theme); padding:9px 18px; border-radius:9px;
        box-shadow:0 0 20px rgba(255,89,38,.55); }}

      /* chip：8MB 芯片（底板随 V-BASE⑦，主题径向光 +.02） */
      .v-chip {{ display:flex; align-items:center; justify-content:center;
        background:radial-gradient(700px 420px at 50% 45%, rgba(255,89,38,.14), transparent 65%),#151A20; }}
      .chip-stage {{ display:flex; flex-direction:column; align-items:center; gap:26px; }}
      .chip {{ width:300px; height:300px; filter:drop-shadow(0 0 30px rgba(255,89,38,.45)); }}
      .chip-label {{ font-size:30px; font-weight:800; color:var(--ink-2); letter-spacing:.06em; }}

      /* toolcall / extract：左右流转 */
      .v-toolcall, .v-extract {{ display:flex; align-items:center;
        background:radial-gradient(700px 420px at 50% 40%, rgba(255,89,38,.12), transparent 65%),#151A20; }}
      .tc-stage, .ex-stage {{ width:100%; height:100%; display:flex; align-items:center; justify-content:center; gap:14px; padding:0 24px; }}
      .tc-bubble, .ex-messy {{ width:330px; flex:none; }}
      .tc-bubble {{ background:rgba(255,89,38,.10); border:1px solid var(--line); border-radius:22px 22px 22px 6px; padding:26px 24px; }}
      .tc-who, .ex-who {{ font-size:18px; font-weight:800; color:var(--theme); letter-spacing:.16em; margin-bottom:12px; }}
      .tc-text {{ font-size:25px; line-height:1.5; color:var(--ink); }}
      .tc-arrow, .ex-arrow {{ width:52px; color:var(--theme); flex:none; filter:drop-shadow(0 0 8px rgba(255,89,38,.6)); }}
      .tc-code {{ width:430px; flex:none; background:#12161B; border:1px solid var(--line); border-radius:16px;
        padding:24px 26px; font-family:monospace; }}
      .tc-line {{ font-size:21px; line-height:1.75; color:var(--ink-2); white-space:nowrap; }}
      .tc-line.i1 {{ padding-left:26px; }}
      .tc-line .k {{ color:#7FB2FF; }} .tc-line .f {{ color:#FF8A5C; font-weight:700; }}
      .tc-line .n {{ color:#9A9AA3; }} .tc-line .v {{ color:#8FE0B0; }} .tc-line .s {{ color:var(--ink-3); }}
      .tc-line .c {{ color:#5A5A64; font-size:18px; }}
      .ex-messy {{ background:rgba(255,255,255,.07); border:1px dashed #4A4A54; border-radius:16px; padding:24px; }}
      .ex-line {{ font-size:21px; line-height:1.7; color:var(--ink-2); }}
      .ex-tidy {{ width:360px; flex:none; background:#12161B; border:1px solid var(--line); border-radius:16px; padding:22px 24px; }}
      .ex-row {{ display:flex; justify-content:space-between; font-family:monospace; font-size:21px;
        line-height:1.8; color:var(--ink-3); border-bottom:1px solid rgba(255,255,255,.06); }}
      .ex-row b {{ color:#8FE0B0; font-weight:700; }}

      /* V-BASE 提亮基线⑥：卡片表面提亮（var(--card)）+ 1px 顶部内嵌亮线 */
      .card {{ position:relative; width:100%; background:var(--card); border:1px solid var(--line);
        border-radius:24px; padding:48px 46px 50px;
        box-shadow:inset 0 1px 0 rgba(255,255,255,.04),0 1px 2px rgba(0,0,0,.3),0 32px 64px -30px rgba(0,0,0,.8);
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
      .stat {{ background:rgba(255,89,38,.10); border:1px solid var(--line); border-radius:16px;
        padding:20px 28px; min-width:250px; }}
      .stat .k {{ font-size:17px; letter-spacing:.1em; color:var(--ink-3); }}
      .stat .v {{ font-size:40px; font-weight:800; color:var(--theme); margin-top:6px; }}
      .bigwrap {{ margin-top:36px; background:linear-gradient(135deg,rgba(255,89,38,.16),rgba(255,89,38,.05));
        border:1px solid rgba(255,89,38,.26); border-radius:20px; padding:32px 40px; }}
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
        background:rgba(16,18,22,.92); backdrop-filter:blur(10px);
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
        "name": "mediacrawler", "width": 1080, "height": 1920, "fps": 30,
        "duration": DUR, "output": "output.mp4"
    }, ensure_ascii=False, indent=2))
    print(f"index.html 已生成，总时长 {DUR}s，{len(scenes)} 场景")

if __name__ == "__main__":
    main()
