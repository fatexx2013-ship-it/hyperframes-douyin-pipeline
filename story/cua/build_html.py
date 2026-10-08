# -*- coding: utf-8 -*-
"""从 script.json 生成 index.html（琥珀暖调主题 #E9A23B，9 场景短篇）

设计基线（相对上一期 iopaint 的迭代，均为视觉/排版层，不触碰产线门禁与共享参数真源）：
  D1 调色体系：从电光青蓝单色 → 琥珀主色 + 冷灰蓝反转色，色阶分 3 级（hi/mid/deep）并落到
     kicker / 数值 / 边框 / 进度条各自的角色上，不再整片一个青色。
  D2 质感层：背景由「两层网格 + 三团渐变」升级为「网点阵列 + 十字网格 + 暖色主光 + 冷色反光
     + 暗角 + 四边细线内框」，并新增卡片内高光（inset 1px 亮线）与两级投影。
  D3 信息分层：新增 eyebrow 前置短规（kicker rule）、可视化编号（01/09）、页面内页栏与
     REC 状态点，卡片左缘双色竖条，主副标题字号/字距分档，正文统一 tabular-nums 对齐。
  D4 视觉模块：新增 3 个模块 screen / action / split，补齐「实况屏 → 动作分解 → 能力边界」的
     画面语言；既有 chip / extract / stats / quote 模块重做质感与配色。
  D5 动效克制化：去掉不可寻址的伪元素扫光（.card::after）与「入场 scale + 无限 yoyo scale」
     的 AI 味呼吸动画；改为入场位移驱动 + 仅在独立选择器上做低幅透明度呼吸，全部挂在
     GSAP 时间轴上，seek 安全。
  D6 渲染精度：渲染侧精度由 storyctl 的 STORYCTL_RENDER_RESOLUTION 白名单 opt-in 控制，
     交付尺寸与编码仍由 post_process 从 config/param_contract.json 真源收口（本文件不参与）。

场景视觉由 scenes[].visual 选择：screen / action / split / chip / quote / extract / stats；
每场文案与清单全部从 script.json 的 card.vis 读取，本文件不再硬编码台词。
"""
import json, os, html

STORY = os.path.dirname(os.path.abspath(__file__))


def esc(x):
    return html.escape(str(x if x is not None else ""))


def render_stat(s):
    return "".join(
        f'<div class="stat"><div class="k">{esc(x["k"])}</div><div class="v">{esc(x["v"])}</div></div>'
        for x in s)


def _vcfg(sc):
    """取该场 card.vis 配置；缺失键由各视觉函数回退为默认值。"""
    return (sc.get("card") or {}).get("vis") or {}


def _pair(v, key, n=2, dflt=None):
    """取长度为 n 的字符串列表（自动补齐/截断，全部转义）。"""
    vals = [esc(x) for x in (v.get(key) or [])]
    dflt = dflt or [""] * n
    vals = (vals + dflt[len(vals):n])[:n]
    return vals


def _no(i):
    """可视化编号：视觉模块右上角的页码标记。"""
    return f'<div class="vis-no">{i + 1:02d}</div>'


# ---------- 视觉模块（全部静态 DOM + 固定坐标，动效另挂时间轴）----------

def vis_screen(i, sc):
    """实况屏：模拟一个应用窗口（标题栏 / 应用区 / 任务侧栏 / AI 光标 + 点击涟漪 + 轨迹）。"""
    v = _vcfg(sc)
    w_title = esc(v.get("window_title", "App"))
    side = esc(v.get("side_title", "AI 的动作记录"))
    target = esc(v.get("target", "GO"))
    foot = esc(v.get("foot", ""))
    badge = esc(v.get("badge", ""))
    rows = v.get("rows") or []
    rows_html = "".join(
        f'<div class="sc-row"><span class="sc-k">{esc(k)}</span><span class="sc-v">{esc(val)}</span></div>'
        for k, val in rows)
    return f'''<div class="vis v-screen" id="vis-{i}">
      {_no(i)}
      <div class="scr-shell" id="scr-{i}">
        <div class="scr-bar">
          <span class="scr-dots"><i></i><i></i><i></i></span>
          <span class="scr-title">{w_title}</span>
          <span class="scr-rec" id="rec-{i}"><b></b>REC</span>
        </div>
        <div class="scr-body">
          <div class="scr-app">
            <div class="scr-line w1"></div>
            <div class="scr-line w2"></div>
            <div class="scr-btnrow">
              <span class="scr-btn"></span>
              <span class="scr-btn"></span>
              <span class="scr-target" id="tgt-{i}">{target}
                <svg class="scr-cursor" id="cur-{i}" viewBox="0 0 40 52">
                  <path d="M4 2 L4 40 L14 31 L21 47 L27 44 L20 28 L34 27 Z"
                        fill="#F6C77A" stroke="#141719" stroke-width="2.5"/>
                </svg>
                <span class="scr-ripple" id="rip-{i}"></span>
              </span>
            </div>
            <div class="scr-line w3"></div>
            <div class="scr-line w4"></div>
          </div>
          <div class="scr-side">
            <div class="scr-side-title">{side}</div>
            {rows_html}
          </div>
          <svg class="scr-trace" viewBox="0 0 620 320" preserveAspectRatio="none">
            <path d="M40 302 C 180 300, 300 236, 470 150" fill="none"
                  stroke="rgba(233,162,59,.50)" stroke-width="2.5" stroke-dasharray="8 10"/>
          </svg>
        </div>
      </div>
      <div class="scr-foot">{foot}</div>
      <div class="vis-badge">{badge}</div>
    </div>'''


def vis_action(i, sc):
    """动作分解：编号 + 动作 + 说明 + 结果四列，末尾行高亮为「已验证」。"""
    v = _vcfg(sc)
    side = esc(v.get("side_title", "一次操作的完整链路"))
    foot = esc(v.get("foot", ""))
    badge = esc(v.get("badge", ""))
    steps = v.get("steps") or []
    rows = []
    for k, st in enumerate(steps):
        last = " last" if k == len(steps) - 1 else ""
        tick = "" if k == len(steps) - 1 else '<span class="act-tick"></span>'
        rows.append(
            f'<div class="act-row{last}">{tick}'
            f'<span class="act-no">{esc(st.get("n", f"{k+1:02d}"))}</span>'
            f'<span class="act-act">{esc(st.get("act", ""))}</span>'
            f'<span class="act-desc">{esc(st.get("desc", ""))}</span>'
            f'<span class="act-res">{esc(st.get("res", ""))}</span></div>')
    return f'''<div class="vis v-action" id="vis-{i}">
      {_no(i)}
      <div class="act-wrap" id="act-{i}">
        <div class="act-head">{side}</div>
        {''.join(rows)}
      </div>
      <div class="scr-foot">{foot}</div>
      <div class="vis-badge">{badge}</div>
    </div>'''


def vis_split(i, sc):
    """能力边界：左「能做什么」/ 中 VS / 右「先看清什么」三栏，底部一句官方口径。"""
    v = _vcfg(sc)
    lt = esc(v.get("left_title", "它能做什么"))
    rt = esc(v.get("right_title", "先看清什么"))
    li = [esc(x) for x in (v.get("left_items") or [])]
    ri = [esc(x) for x in (v.get("right_items") or [])]
    verdict = esc(v.get("verdict", ""))
    badge = esc(v.get("badge", ""))
    left = "".join(f'<div class="spl-item"><span class="spl-mark">+</span><span>{x}</span></div>' for x in li)
    right = "".join(f'<div class="spl-item"><span class="spl-mark">!</span><span>{x}</span></div>' for x in ri)
    return f'''<div class="vis v-split" id="vis-{i}">
      {_no(i)}
      <div class="spl-wrap" id="spl-{i}">
        <div class="spl-pane left">
          <div class="spl-title">{lt}</div>
          {left}
        </div>
        <div class="spl-mid"><span class="spl-vs" id="vs-{i}">VS</span></div>
        <div class="spl-pane plus">
          <div class="spl-title">{rt}</div>
          {right}
        </div>
      </div>
      <div class="spl-verdict">{verdict}</div>
      <div class="vis-badge">{badge}</div>
    </div>'''


def vis_quote(i, sc):
    v = _vcfg(sc)
    quote = esc(v.get("quote", ""))
    accent = esc(v.get("accent", ""))
    badge = esc(v.get("badge", ""))
    return f'''<div class="vis v-quote" id="vis-{i}">
      {_no(i)}
      <div class="q-stage">
        <div class="q-mark">&ldquo;</div>
        <div class="q-text">{quote}</div>
        <div class="q-rule"></div>
        <div class="q-accent">{accent}</div>
      </div>
      <div class="vis-badge">{badge}</div>
    </div>'''


def vis_extract(i, sc):
    v = _vcfg(sc)
    lw = esc(v.get("left_who", "你敲的命令"))
    rw = esc(v.get("right_who", "它给了什么"))
    lines = [esc(x) for x in (v.get("left_lines") or [])]
    rows = v.get("right_rows") or []
    badge = esc(v.get("badge", ""))
    lh = "".join(f'<div class="ex-line">{x}</div>' for x in lines)
    rh = "".join(f'<div class="ex-row"><span>{esc(k)}</span><b>{esc(val)}</b></div>' for k, val in rows)
    return f'''<div class="vis v-extract" id="vis-{i}">
      {_no(i)}
      <div class="ex-wrap">
        <div class="ex-messy" id="exm-{i}">
          <div class="ex-who">{lw}</div>
          {lh}
        </div>
        <div class="ex-arrow" id="exa-{i}">
          <svg viewBox="0 0 60 40">
            <path d="M4 20 H44" stroke="#E9A23B" stroke-width="6" stroke-linecap="round"/>
            <path d="M36 9 L52 20 L36 31" fill="none" stroke="#E9A23B" stroke-width="6"
                  stroke-linecap="round" stroke-linejoin="round"/>
          </svg>
        </div>
        <div class="ex-tidy" id="ext-{i}">
          <div class="ex-who">{rw}</div>
          {rh}
        </div>
      </div>
      <div class="vis-badge">{badge}</div>
    </div>'''


def vis_stats(i, sc):
    v = _vcfg(sc)
    badge = esc(v.get("badge", ""))
    stats = sc["card"].get("stats") or []
    return f'''<div class="vis v-stats" id="vis-{i}">
      {_no(i)}
      <div class="st-board" id="st-{i}">{render_stat(stats)}</div>
      <div class="vis-badge">{badge}</div>
    </div>'''


def vis_chip(i, sc):
    v = _vcfg(sc)
    left = esc(v.get("left", "一句话"))
    r1, r2 = _pair(v, "right", 2, ["答案", "第一行"])
    small = esc(v.get("small", "1st line"))
    footer = esc(v.get("footer", "action => first"))
    label = esc(v.get("label", ""))
    badge = esc(v.get("badge", ""))
    return f'''<div class="vis v-chip" id="vis-{i}">
      {_no(i)}
      <div class="chip-stage">
        <div class="chip" id="chip-{i}">
          <svg viewBox="0 0 260 200">
            <g opacity="0.34">
              <rect x="14" y="52" width="96" height="96" rx="14" fill="none"
                    stroke="#7E8791" stroke-width="5"/>
              <text x="62" y="112" font-size="22" fill="#7E8791" text-anchor="middle"
                    font-family="monospace" font-weight="800">{left}</text>
            </g>
            <path d="M118 100 H146" stroke="#E9A23B" stroke-width="7" stroke-linecap="round"/>
            <path d="M134 87 L154 100 L134 113" fill="none" stroke="#E9A23B" stroke-width="7"
                  stroke-linecap="round" stroke-linejoin="round"/>
            <g>
              <rect x="156" y="30" width="98" height="140" rx="18"
                    fill="rgba(233,162,59,.13)" stroke="#E9A23B" stroke-width="5"/>
              <text x="205" y="78" font-size="22" fill="#F6C77A" text-anchor="middle"
                    font-family="monospace" font-weight="800">{r1}</text>
              <text x="205" y="110" font-size="22" fill="#F6C77A" text-anchor="middle"
                    font-family="monospace" font-weight="800">{r2}</text>
              <text x="205" y="148" font-size="16" fill="#B9AE9D" text-anchor="middle"
                    font-family="monospace" font-weight="700">{small}</text>
            </g>
            <text x="130" y="186" font-size="19" fill="#8A8175" text-anchor="middle"
                  font-family="monospace">{footer}</text>
          </svg>
        </div>
        <div class="chip-label">{label}</div>
      </div>
      <div class="vis-badge">{badge}</div>
    </div>'''


VIS = {"screen": vis_screen, "action": vis_action, "split": vis_split,
       "chip": vis_chip, "extract": vis_extract, "toolcall": vis_extract,
       "stats": vis_stats, "quote": vis_quote}


# ---------- 场景动效（全部挂在 GSAP 时间轴上，seek 安全；不使用 CSS 动画）----------
# 约束（对齐 design_ai_gate 配方黑名单）：同一选择器不同时出现「入场 scale」与「to yoyo+repeat scale」；
# 呼吸类动效一律只改 opacity/位移，且落在与入场不同的选择器上。

def anim_screen(i, s, e):
    return f'''tl.from("#scr-{i}", {{ y: 34, opacity: 0, duration: 0.6, ease: "power3.out" }}, {s+0.15:.2f});
      tl.from("#vis-{i} .scr-bar", {{ y: -14, opacity: 0, duration: 0.4, ease: "power2.out" }}, {s+0.5:.2f});
      tl.from("#vis-{i} .scr-side .sc-row", {{ x: 18, opacity: 0, duration: 0.35, stagger: 0.12, ease: "power2.out" }}, {s+0.9:.2f});
      tl.from("#tgt-{i}", {{ scale: 0.86, opacity: 0, duration: 0.4, ease: "back.out(1.4)" }}, {s+1.4:.2f});
      tl.from("#cur-{i}", {{ x: -46, y: -34, opacity: 0, duration: 0.5, ease: "power2.out" }}, {s+1.7:.2f});
      tl.fromTo("#rip-{i}", {{ scale: 0.40, opacity: 0.85 }}, {{ scale: 1.85, opacity: 0, duration: 1.1, repeat: 5, ease: "power1.out" }}, {s+2.0:.2f});
      tl.from("#vis-{i} .scr-trace", {{ opacity: 0, duration: 0.5, ease: "power2.out" }}, {s+1.85:.2f});
      tl.to("#rec-{i}", {{ opacity: 0.3, duration: 0.6, yoyo: true, repeat: 8, ease: "sine.inOut" }}, {s+0.9:.2f});
      tl.from("#vis-{i} .scr-foot", {{ y: 14, opacity: 0, duration: 0.45, ease: "power2.out" }}, {s+2.2:.2f});
      tl.from("#vis-{i} .vis-badge", {{ y: 22, opacity: 0, duration: 0.5, ease: "power2.out" }}, {s+0.4:.2f});'''


def anim_action(i, s, e):
    return f'''tl.from("#vis-{i} .act-head", {{ y: 16, opacity: 0, duration: 0.4, ease: "power2.out" }}, {s+0.3:.2f});
      tl.from("#vis-{i} .act-row", {{ y: 24, opacity: 0, duration: 0.4, stagger: 0.16, ease: "power3.out" }}, {s+0.5:.2f});
      tl.from("#vis-{i} .act-tick", {{ scaleY: 0, opacity: 0, duration: 0.25, stagger: 0.16, ease: "power1.out" }}, {s+0.7:.2f});
      tl.from("#vis-{i} .act-row.last .act-res", {{ x: 14, opacity: 0, duration: 0.4, ease: "power2.out" }}, {s+1.5:.2f});
      tl.from("#vis-{i} .scr-foot", {{ y: 14, opacity: 0, duration: 0.45, ease: "power2.out" }}, {s+1.9:.2f});
      tl.from("#vis-{i} .vis-badge", {{ y: 22, opacity: 0, duration: 0.5, ease: "power2.out" }}, {s+0.4:.2f});'''


def anim_split(i, s, e):
    return f'''tl.from("#vis-{i} .spl-pane.left", {{ x: -30, opacity: 0, duration: 0.55, ease: "power2.out" }}, {s+0.25:.2f});
      tl.from("#vs-{i}", {{ scale: 0.5, opacity: 0, duration: 0.45, ease: "back.out(1.8)" }}, {s+0.7:.2f});
      tl.from("#vis-{i} .spl-pane.plus", {{ x: 30, opacity: 0, duration: 0.55, ease: "power2.out" }}, {s+0.55:.2f});
      tl.from("#vis-{i} .spl-item", {{ y: 18, opacity: 0, duration: 0.35, stagger: 0.1, ease: "power2.out" }}, {s+1.0:.2f});
      tl.from("#vis-{i} .spl-verdict", {{ y: 16, opacity: 0, duration: 0.45, ease: "power2.out" }}, {s+1.9:.2f});
      tl.to("#vis-{i} .spl-vs", {{ opacity: 0.55, duration: 0.55, yoyo: true, repeat: 7, ease: "sine.inOut" }}, {s+1.2:.2f});
      tl.from("#vis-{i} .vis-badge", {{ y: 22, opacity: 0, duration: 0.5, ease: "power2.out" }}, {s+0.4:.2f});'''


def anim_extract(i, s, e):
    return f'''tl.from("#exm-{i}", {{ x: -40, opacity: 0, duration: 0.5, ease: "power2.out" }}, {s+0.2:.2f});
      tl.from("#exa-{i}", {{ y: -16, opacity: 0, duration: 0.4, ease: "power2.out" }}, {s+0.7:.2f});
      tl.from("#ext-{i}", {{ x: 40, opacity: 0, duration: 0.6, ease: "power2.out" }}, {s+1.0:.2f});
      tl.from("#ext-{i} .ex-row", {{ x: 14, opacity: 0, duration: 0.3, stagger: 0.1, ease: "power1.out" }}, {s+1.2:.2f});
      tl.to("#exa-{i}", {{ y: 8, duration: 0.5, yoyo: true, repeat: 6, ease: "sine.inOut" }}, {s+1.7:.2f});
      tl.from("#vis-{i} .vis-badge", {{ y: 22, opacity: 0, duration: 0.5, ease: "power2.out" }}, {s+0.4:.2f});'''


def anim_stats(i, s, e):
    return f'''tl.from("#vis-{i} .stat", {{ y: 26, opacity: 0, duration: 0.4, stagger: 0.12, ease: "power2.out" }}, {s+0.5:.2f});
      tl.from("#vis-{i} .stat .v", {{ y: 14, opacity: 0, duration: 0.35, stagger: 0.12, ease: "power2.out" }}, {s+0.7:.2f});
      tl.from("#vis-{i} .vis-badge", {{ y: 22, opacity: 0, duration: 0.5, ease: "power2.out" }}, {s+0.4:.2f});'''


def anim_quote(i, s, e):
    return f'''tl.from("#vis-{i} .q-mark", {{ scale: 0.6, opacity: 0, duration: 0.5, ease: "power2.out" }}, {s+0.2:.2f});
      tl.from("#vis-{i} .q-text", {{ y: 26, opacity: 0, duration: 0.55, ease: "power2.out" }}, {s+0.35:.2f});
      tl.from("#vis-{i} .q-rule", {{ scaleX: 0, opacity: 0, duration: 0.5, ease: "power2.out" }}, {s+0.7:.2f});
      tl.from("#vis-{i} .q-accent", {{ y: 20, opacity: 0, duration: 0.5, ease: "power2.out" }}, {s+0.85:.2f});
      tl.from("#vis-{i} .vis-badge", {{ y: 22, opacity: 0, duration: 0.5, ease: "power2.out" }}, {s+0.4:.2f});'''


def anim_chip(i, s, e):
    return f'''tl.fromTo("#chip-{i}", {{ scale: 0.72, rotation: -8, opacity: 0 }}, {{ scale: 1, rotation: 0, opacity: 1, duration: 0.7, ease: "back.out(1.6)" }}, {s+0.2:.2f});
      tl.to("#vis-{i} .chip-label", {{ opacity: 0.55, duration: 0.6, yoyo: true, repeat: 5, ease: "sine.inOut" }}, {s+0.9:.2f});
      tl.from("#vis-{i} .chip-label", {{ y: 20, opacity: 0, duration: 0.5, ease: "power2.out" }}, {s+0.5:.2f});
      tl.from("#vis-{i} .vis-badge", {{ y: 22, opacity: 0, duration: 0.5, ease: "power2.out" }}, {s+0.4:.2f});'''


ANIM = {"screen": anim_screen, "action": anim_action, "split": anim_split,
        "chip": anim_chip, "extract": anim_extract, "toolcall": anim_extract,
        "stats": anim_stats, "quote": anim_quote}


# ---------- 卡片 ----------

def card_html(sc, i):
    c = sc["card"]
    t = sc["type"]
    if t == "header":
        body = f'''<p class="eyebrow anim">{esc(c["eyebrow"])}</p>
        <h1 class="anim">{c["title"]}</h1>
        <p class="hsubtitle anim">{esc(c["subtitle"])}</p>
        <div class="stats anim">{render_stat(c["stats"])}</div>'''
    elif t == "outro":
        body = f'''<div class="otitle anim">{c["title"]}</div>
        <div class="octa anim">{esc(c["cta"])}</div>
        <div class="osub anim">{esc(c["sub"])}</div>'''
    else:
        sub = f'<p class="hsubtitle anim">{esc(c["subtitle"])}</p>' if c.get("subtitle") else ""
        body = f'''<p class="eyebrow anim">{esc(c["eyebrow"])}</p>
        <h2 class="anim">{c["title"]}</h2>
        {sub}'''
    return f'<div class="card{" ocard" if t=="outro" else ""}">{body}</div>'


CSS = """
      @font-face { font-family: "PingFang SC"; src: local("PingFang SC"); }
      :root {
        /* 琥珀暖调主题（与电光青蓝拉开一档）：主色三级 + 冷色反转 + 语义色 */
        --theme:#E9A23B; --theme-hi:#F6C77A; --theme-deep:#A96A16;
        --cool:#5B7684; --ok:#7FD1A8;
        --ink:#F4EFE7; --ink-2:#B9AE9D; --ink-3:#8A8175;
        --line:rgba(233,162,59,.20); --line-2:rgba(244,239,231,.07);
        --card:rgba(27,30,36,.94);
      }
      * { box-sizing:border-box; margin:0; padding:0; }
      html, body { width:1080px; height:1920px; overflow:hidden;
        font-family:"PingFang SC",sans-serif; color:var(--ink); line-height:1.6;
        font-variant-numeric:tabular-nums;
        background:
          radial-gradient(1400px 1000px at 50% 48%, transparent 46%, rgba(6,7,9,.42) 100%),
          radial-gradient(1200px 820px at 4% -14%, rgba(198,132,44,.52), transparent 62%),
          radial-gradient(940px 640px at 104% -6%, rgba(122,152,170,.30), transparent 60%),
          radial-gradient(900px 900px at 50% 114%, rgba(10,12,15,.80), transparent 64%),
          radial-gradient(1600px 1200px at 50% 34%, rgba(233,162,59,.07), transparent 72%),
          radial-gradient(rgba(240,178,80,.30) 2px, transparent 2.2px) 0 0/44px 44px,
          radial-gradient(rgba(246,199,122,.16) 1px, transparent 1.1px) 22px 22px/44px 44px,
          linear-gradient(rgba(120,150,168,.13) 1px, transparent 1px) 0 0/240px 240px,
          linear-gradient(90deg, rgba(120,150,168,.13) 1px, transparent 1px) 0 0/240px 240px,
          linear-gradient(170deg,#161B21 0%,#1A1F26 46%,#0F1318 100%);
      }
      body::after { content:""; position:fixed; inset:26px; z-index:5; pointer-events:none;
        border:1px solid rgba(233,162,59,.18); border-radius:8px; }
      .scene { position:absolute; inset:0; display:flex; flex-direction:column;
        align-items:center; padding:150px 56px 400px; }
      .topbar { position:absolute; top:56px; left:56px; right:56px; display:flex;
        justify-content:space-between; align-items:center; z-index:20;
        font-size:24px; color:var(--ink-3); }
      .topbar .brand { font-weight:700; color:var(--theme); letter-spacing:.08em;
        display:flex; align-items:center; }
      .topbar .brand i { width:12px; height:12px; border-radius:3px; background:var(--theme);
        display:inline-block; margin-right:12px; }
      .topbar .date { font-family:monospace; letter-spacing:.05em; }
      .progress { position:absolute; top:0; left:0; height:4px; width:0%; z-index:30;
        background:linear-gradient(90deg,var(--theme-deep),var(--theme-hi));
        box-shadow:0 0 14px rgba(233,162,59,.75); }
      .wm { position:absolute; right:40px; bottom:104px; z-index:25; font-size:44px; font-weight:600;
        color:rgba(244,239,231,.55);
        text-shadow:0 0 3px rgba(0,0,0,.55),0 1px 3px rgba(0,0,0,.40),0 -1px 2px rgba(0,0,0,.30); }

      /* ---------- 视觉容器 ---------- */
      .vis { width:100%; height:560px; border-radius:20px; overflow:hidden; position:relative;
        border:1px solid var(--line);
        box-shadow:inset 0 1px 0 rgba(244,239,231,.05), 0 26px 64px -30px rgba(0,0,0,.88);
        margin-bottom:36px; background:#151A20; }
      .vis::before { content:""; position:absolute; inset:14px; z-index:3; pointer-events:none; opacity:.34;
        border-radius:12px;
        background:
          linear-gradient(var(--theme) 0 0) left top/18px 1px no-repeat,
          linear-gradient(var(--theme) 0 0) left top/1px 18px no-repeat,
          linear-gradient(var(--theme) 0 0) right top/18px 1px no-repeat,
          linear-gradient(var(--theme) 0 0) right top/1px 18px no-repeat,
          linear-gradient(var(--theme) 0 0) left bottom/18px 1px no-repeat,
          linear-gradient(var(--theme) 0 0) left bottom/1px 18px no-repeat,
          linear-gradient(var(--theme) 0 0) right bottom/18px 1px no-repeat,
          linear-gradient(var(--theme) 0 0) right bottom/1px 18px no-repeat; }
      .vis-no { position:absolute; right:24px; top:18px; z-index:4; font-family:monospace;
        font-size:20px; letter-spacing:.16em; color:rgba(244,239,231,.32); }
      .vis-badge { position:absolute; left:22px; bottom:20px; z-index:4; font-size:21px; font-weight:700;
        letter-spacing:.05em; color:#15181D; background:var(--theme); padding:9px 18px; border-radius:9px;
        box-shadow:0 10px 26px -12px rgba(233,162,59,.85); }
      .scr-foot { position:absolute; left:56px; right:56px; bottom:92px; font-size:19px;
        color:var(--ink-3); letter-spacing:.01em; }

      /* ---------- v-screen：实况屏 ---------- */
      .v-screen { background:
          radial-gradient(760px 420px at 26% 6%, rgba(233,162,59,.10), transparent 62%),#151A20; }
      .scr-shell { position:absolute; left:44px; right:44px; top:44px; height:390px; overflow:hidden;
        border-radius:18px; border:1px solid rgba(244,239,231,.10);
        background:linear-gradient(180deg,#1A1D23,#131619);
        box-shadow:inset 0 1px 0 rgba(244,239,231,.06), 0 28px 60px -32px rgba(0,0,0,.92); }
      .scr-bar { height:46px; display:flex; align-items:center; gap:14px; padding:0 18px;
        background:rgba(244,239,231,.04); border-bottom:1px solid rgba(244,239,231,.08); }
      .scr-dots { display:flex; gap:8px; }
      .scr-dots i { width:11px; height:11px; border-radius:50%; background:rgba(244,239,231,.20); }
      .scr-dots i:first-child { background:var(--theme); }
      .scr-title { font-family:monospace; font-size:19px; letter-spacing:.05em; color:var(--ink-2); }
      .scr-rec { margin-left:auto; display:flex; align-items:center; gap:8px;
        font-family:monospace; font-size:18px; letter-spacing:.16em; color:var(--theme); }
      .scr-rec b { width:12px; height:12px; border-radius:50%; background:var(--theme);
        box-shadow:0 0 12px rgba(233,162,59,.85); }
      .scr-body { position:relative; display:flex; height:344px; }
      .scr-app { flex:1; padding:26px 28px; display:flex; flex-direction:column; gap:18px; }
      .scr-line { height:14px; border-radius:7px; background:rgba(244,239,231,.09); }
      .scr-line.w1 { width:58%; } .scr-line.w2 { width:82%; }
      .scr-line.w3 { width:44%; } .scr-line.w4 { width:68%; }
      .scr-btnrow { display:flex; align-items:center; gap:16px; margin:8px 0; }
      .scr-btn { width:76px; height:38px; border-radius:10px;
        background:rgba(244,239,231,.10); border:1px solid rgba(244,239,231,.08); }
      .scr-target { position:relative; margin-left:auto; padding:12px 28px; border-radius:12px;
        font-family:monospace; font-size:26px; font-weight:800; color:#15181D;
        background:linear-gradient(180deg,var(--theme-hi),var(--theme));
        box-shadow:0 0 0 6px rgba(233,162,59,.14), 0 16px 32px -16px rgba(233,162,59,.75); }
      .scr-cursor { position:absolute; right:-24px; bottom:-30px; width:34px; height:44px;
        filter:drop-shadow(0 8px 12px rgba(0,0,0,.65)); }
      .scr-ripple { position:absolute; right:-14px; bottom:-14px; width:74px; height:74px;
        border-radius:50%; border:3px solid rgba(246,199,122,.85); transform-origin:center; }
      .scr-trace { position:absolute; left:0; top:0; width:100%; height:100%; z-index:1; }
      .scr-side { width:318px; flex:none; padding:24px; display:flex; flex-direction:column; gap:12px;
        background:rgba(244,239,231,.03); border-left:1px solid rgba(244,239,231,.08); }
      .scr-side-title { font-size:18px; font-weight:800; letter-spacing:.16em; color:var(--theme); }
      .sc-row { display:flex; justify-content:space-between; gap:10px; font-size:21px;
        color:var(--ink-2); padding-bottom:9px; border-bottom:1px dashed rgba(244,239,231,.10); }
      .sc-v { font-family:monospace; font-weight:700; color:var(--theme-hi); }

      /* ---------- v-action：动作分解 ---------- */
      .v-action { background:
          radial-gradient(700px 400px at 76% 90%, rgba(233,162,59,.09), transparent 62%),#151A20; }
      .act-wrap { position:absolute; left:56px; right:56px; top:48px; }
      .act-head { font-size:19px; font-weight:800; letter-spacing:.18em; color:var(--theme);
        margin-bottom:18px; }
      .act-row { position:relative; display:flex; align-items:center; gap:20px;
        margin-bottom:12px; padding:14px 22px; border-radius:14px;
        background:rgba(244,239,231,.035); border:1px solid rgba(244,239,231,.07); }
      .act-row.last { background:linear-gradient(90deg, rgba(233,162,59,.16), rgba(233,162,59,.03));
        border-color:rgba(233,162,59,.34); }
      .act-tick { position:absolute; left:46px; bottom:-13px; width:2px; height:13px;
        background:rgba(233,162,59,.30); transform-origin:top center; }
      .act-no { width:48px; height:48px; flex:none; display:flex; align-items:center;
        justify-content:center; border-radius:14px; font-family:monospace; font-size:21px;
        font-weight:800; color:var(--theme-hi); background:rgba(233,162,59,.12);
        border:1px solid rgba(233,162,59,.30); }
      .act-act { width:148px; flex:none; font-size:26px; font-weight:800; }
      .act-desc { flex:1; font-size:21px; color:var(--ink-2); }
      .act-res { font-family:monospace; font-size:20px; font-weight:700; color:var(--ok); }

      /* ---------- v-split：能力边界 ---------- */
      .v-split { background:
          radial-gradient(700px 400px at 50% 0%, rgba(233,162,59,.09), transparent 62%),#151A20; }
      .spl-wrap { position:absolute; left:48px; right:48px; top:58px; display:flex; align-items:stretch; }
      .spl-pane { flex:1; min-height:322px; padding:26px 24px; border-radius:18px;
        background:rgba(244,239,231,.035); border:1px solid rgba(244,239,231,.08); }
      .spl-pane.plus { border-radius:22px; background:rgba(233,162,59,.08);
        border-color:rgba(233,162,59,.28); }
      .spl-title { font-size:21px; font-weight:800; letter-spacing:.06em; margin-bottom:16px;
        color:var(--ink-2); }
      .spl-pane.plus .spl-title { color:var(--theme-hi); }
      .spl-item { display:flex; gap:12px; margin-bottom:14px; font-size:23px; line-height:1.45; }
      .spl-mark { width:22px; flex:none; font-family:monospace; font-weight:800; color:var(--ink-3); }
      .spl-pane.plus .spl-mark { color:var(--ok); }
      .spl-mid { position:relative; width:104px; flex:none; display:flex;
        align-items:center; justify-content:center; }
      .spl-mid::before { content:""; position:absolute; top:8px; bottom:8px; left:50%; width:1px;
        background:linear-gradient(180deg,transparent,rgba(244,239,231,.20) 18%,
          rgba(244,239,231,.20) 82%,transparent); }
      .spl-vs { position:relative; z-index:2; width:64px; height:64px; border-radius:50%;
        display:flex; align-items:center; justify-content:center; font-family:monospace;
        font-size:22px; font-weight:800; color:var(--theme-hi); background:#15181D;
        border:1px solid rgba(233,162,59,.40); box-shadow:0 0 0 9px rgba(15,18,22,.92); }
      .spl-verdict { position:absolute; left:48px; right:48px; bottom:96px; text-align:center;
        font-size:20px; color:var(--ink-3); }

      /* ---------- v-quote ---------- */
      .v-quote { display:flex; align-items:center; justify-content:center;
        background:radial-gradient(700px 420px at 50% 45%, rgba(233,162,59,.12), transparent 65%),#151A20; }
      .q-stage { display:flex; flex-direction:column; align-items:center; gap:16px; }
      .q-mark { font-size:132px; line-height:.5; font-weight:900; color:var(--theme); opacity:.5; }
      .q-text { max-width:860px; text-align:center; font-size:40px; font-weight:800; line-height:1.45; }
      .q-rule { width:96px; height:3px; border-radius:2px;
        background:linear-gradient(90deg,var(--theme-deep),var(--theme-hi)); }
      .q-accent { font-family:monospace; font-size:28px; letter-spacing:.06em; color:var(--theme);
        text-align:center; padding:0 60px; }

      /* ---------- v-extract ---------- */
      .v-extract { display:flex; align-items:center; justify-content:center;
        background:radial-gradient(700px 420px at 50% 50%, rgba(233,162,59,.09), transparent 62%),#151A20; }
      .ex-wrap { display:flex; align-items:center; gap:26px; padding:0 46px; }
      .ex-messy { width:330px; flex:none; padding:24px; border-radius:18px;
        background:rgba(244,239,231,.045); border:1px dashed rgba(244,239,231,.16); }
      .ex-who { font-size:18px; font-weight:800; letter-spacing:.16em; color:var(--theme);
        margin-bottom:12px; }
      .ex-line { font-family:monospace; font-size:20px; line-height:1.7; color:var(--ink-2); }
      .ex-arrow { width:56px; flex:none; filter:drop-shadow(0 6px 14px rgba(233,162,59,.45)); }
      .ex-tidy { width:366px; flex:none; padding:24px; border-radius:24px;
        background:rgba(233,162,59,.07); border:1px solid rgba(233,162,59,.26); }
      .ex-row { display:flex; justify-content:space-between; gap:10px; font-size:20px; line-height:1.8;
        color:var(--ink-3); border-bottom:1px solid rgba(244,239,231,.06); }
      .ex-row b { font-family:monospace; font-weight:700; color:var(--ok); }

      /* ---------- v-stats ---------- */
      .v-stats { display:flex; align-items:center; justify-content:center;
        background:radial-gradient(700px 420px at 50% 45%, rgba(233,162,59,.12), transparent 65%),#151A20; }
      .st-board { display:flex; flex-wrap:wrap; gap:26px; justify-content:center; padding:0 52px; }
      .st-board .stat { min-width:330px; text-align:center; border-radius:22px;
        background:rgba(233,162,59,.09); }
      .st-board .stat .v { font-size:48px; }

      /* ---------- v-chip ---------- */
      .v-chip { display:flex; align-items:center; justify-content:center;
        background:radial-gradient(700px 420px at 50% 45%, rgba(233,162,59,.12), transparent 65%),#151A20; }
      .chip-stage { display:flex; flex-direction:column; align-items:center; gap:18px; }
      .chip { width:520px; }
      .chip-label { font-size:32px; font-weight:800; letter-spacing:.02em; color:var(--ink); }

      /* ---------- 文案卡 ---------- */
      .card { position:relative; width:100%; overflow:hidden;
        background:linear-gradient(168deg, rgba(33,37,44,.96), rgba(23,26,32,.96));
        border:1px solid var(--line); border-radius:26px; padding:48px 46px 50px;
        box-shadow:inset 0 1px 0 rgba(244,239,231,.05), 0 2px 4px rgba(0,0,0,.35),
          0 34px 70px -34px rgba(0,0,0,.85); }
      .card::before { content:""; position:absolute; left:0; top:40px; bottom:40px; width:6px;
        border-radius:0 4px 4px 0;
        background:linear-gradient(180deg,var(--theme-hi),var(--theme-deep));
        box-shadow:2px 0 0 rgba(246,199,122,.28); }
      .eyebrow { display:flex; align-items:center; font-size:23px; font-weight:700;
        letter-spacing:.2em; color:var(--theme); margin-bottom:22px; }
      .eyebrow::before { content:""; width:28px; height:2px; margin-right:14px;
        background:var(--theme); }
      h1 { font-size:68px; line-height:1.24; font-weight:800; letter-spacing:-.015em; }
      h2 { font-size:46px; line-height:1.3; font-weight:800; letter-spacing:-.005em; }
      .accent { color:var(--theme-hi); border-bottom:3px solid rgba(233,162,59,.45); }
      .hsubtitle { margin-top:24px; font-size:27px; line-height:1.5; color:var(--ink-2); }
      .stats { margin-top:38px; display:flex; flex-wrap:wrap; gap:16px; }
      .stat { min-width:250px; padding:20px 28px; border-radius:16px;
        background:rgba(233,162,59,.08); border:1px solid var(--line); }
      .stat .k { font-size:17px; letter-spacing:.1em; color:var(--ink-3); }
      .stat .v { margin-top:6px; font-size:40px; font-weight:800; color:var(--theme-hi); }
      .ocard { text-align:center; padding:72px 46px; }
      .otitle { font-size:58px; font-weight:900; line-height:1.25; }
      .octa { margin-top:34px; font-size:38px; font-weight:800; color:var(--theme-hi); }
      .osub { margin-top:22px; font-size:28px; color:var(--ink-3); }

      /* ---------- 字幕（几何与历史成片保持一致，仅换配色） ---------- */
      .subtitle { position:absolute; left:56px; right:56px; bottom:150px; z-index:15;
        display:flex; justify-content:center; pointer-events:none; }
      .sub-inner { max-width:100%; padding:26px 34px; border-radius:22px;
        background:rgba(9,10,13,.92); backdrop-filter:blur(10px);
        box-shadow:0 14px 36px -18px rgba(0,0,0,.8); border-left:6px solid var(--theme);
        font-size:33px; font-weight:600; color:var(--ink); line-height:1.5; }
"""


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
        scene_divs.append(
            f'<div id="scene-{i}" class="scene clip" data-start="{s:.2f}" '
            f'data-duration="{e-s:.2f}" data-track-index="3">'
            f'{VIS.get(v, vis_extract)(i, sc)}{card_html(sc, i)}</div>')

    sub_divs, tl_lines = [], []
    for i, ln in enumerate(lines):
        s, e = ln["start"], ln["end"]
        sub_divs.append(
            f'<div id="sub-{i}" class="subtitle clip" data-start="{s:.2f}" '
            f'data-duration="{e-s:.2f}" data-track-index="10">'
            f'<div class="sub-inner">{html.escape(ln["text"])}</div></div>')
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
      tl.from("#scene-{i} .vis-no", {{ opacity: 0, duration: 0.5, ease: "power1.out" }}, {s+0.5:.2f});
      tl.to("#scene-{i} .card", {{ opacity: 0, y: -18, duration: 0.3, ease: "power2.in" }}, {e-0.32:.2f});
      tl.set("#scene-{i} .card", {{ opacity: 0 }}, {e:.2f});''')

    page = f'''<!doctype html>
<html lang="zh-CN">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=1080, height=1920" />
    <script src="https://cdn.jsdelivr.net/npm/gsap@3.14.2/dist/gsap.min.js"></script>
    <style>{CSS}</style>
  </head>
  <body>
    <div id="root" data-composition-id="main" data-start="0" data-duration="{DUR}" data-width="1080" data-height="1920">
      <div id="progress" class="progress clip" data-start="0" data-duration="{DUR}" data-track-index="100"></div>
      <div id="topbar" class="topbar clip" data-start="0" data-duration="{DUR}" data-track-index="1">
        <span class="brand"><i></i>{html.escape(wm)} · 开源情报站</span>
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
        "name": "cua", "width": 1080, "height": 1920, "fps": 30,
        "duration": DUR, "output": "output.mp4"
    }, ensure_ascii=False, indent=2))
    print(f"index.html 已生成，总时长 {DUR}s，{len(scenes)} 场景")


if __name__ == "__main__":
    main()
