#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Immich 视频构建：HyperFrames 9:16 时间轴 + 卡片视觉 + 逐句字幕

产物：index.html（供 hyperframes render 使用）、hyperframes.json
主题：电光蓝（--theme #2BB8FF），与 needle（赤焰热力）、autoclip（电光紫）区分
"""
import os
import json
import html

STORY = "/Volumes/PSSD/抖音视频/story/immich"


def render_stat(s):
    return "".join(
        f'<div class="stat"><div class="k">{html.escape(x["k"])}</div>'
        f'<div class="v">{html.escape(x["v"])}</div></div>' for x in s)


# ── 场景视觉 ──────────────────────────────────────

def vis_album(i):
    tiles = "".join('<div class="alb-tile"></div>' for _ in range(12))
    return f'''<div class="vis v-album" id="vis-{i}">
      <div class="alb-stage">
        <div class="alb-phone" id="albp-{i}">
          <div class="alb-notch"></div>
          <div class="alb-grid">{tiles}</div>
          <div class="alb-cap">我的相册 · 115,239 张</div>
        </div>
        <div class="alb-side">
          <div class="alb-cloud" id="albc-{i}">
            <svg viewBox="0 0 120 70"><path d="M34 58 H92 A18 18 0 0 0 90 22 A26 26 0 0 0 40 26 A17 17 0 0 0 34 58 Z" fill="none" stroke="currentColor" stroke-width="5" stroke-linejoin="round"/></svg>
            <div class="alb-cloudcap">别人的服务器</div>
            <div class="alb-cloudprice">$9.99 / 月</div>
          </div>
          <div class="alb-arrow" id="alba-{i}">搬回</div>
          <div class="alb-disk" id="albd-{i}">
            <svg viewBox="0 0 120 90">
              <rect x="14" y="12" width="92" height="66" rx="10" fill="none" stroke="currentColor" stroke-width="5"/>
              <circle cx="60" cy="45" r="17" fill="none" stroke="currentColor" stroke-width="5"/>
              <circle cx="60" cy="45" r="5" fill="currentColor"/>
              <rect x="80" y="66" width="14" height="8" rx="2" fill="currentColor"/>
            </svg>
            <div class="alb-diskcap">你自己的硬盘</div>
          </div>
        </div>
      </div>
      <div class="vis-badge">GitHub 115,239 星 · AGPL-3.0 开源</div>
    </div>'''


def vis_backup(i):
    grid = "".join('<div class="bk-t"></div>' for _ in range(6))
    return f'''<div class="vis v-backup" id="vis-{i}">
      <div class="bk-stage">
        <div class="bk-phones">
          <div class="bk-phone" id="bkp1-{i}"><div class="bk-brand">iOS</div><div class="bk-grid">{grid}</div><div class="bk-badge">原生 App</div></div>
          <div class="bk-phone" id="bkp2-{i}"><div class="bk-brand">Android</div><div class="bk-grid">{grid}</div><div class="bk-badge">原生 App</div></div>
        </div>
        <div class="bk-flow">
          <div class="bk-flowlabel"><span>备份进度</span><span class="bk-pct" id="bkpc-{i}">0%</span></div>
          <div class="bk-track"><div class="bk-bar" id="bkb-{i}"></div></div>
          <div class="bk-chips"><span>打开即备份</span><span>可选相册</span><span>断点续传</span><span>防重复</span></div>
        </div>
      </div>
      <div class="vis-badge">后台增量备份 · 自动备份整库</div>
    </div>'''


def vis_search(i):
    tiles = ""
    for k in range(8):
        hit = k in (1, 4)
        tiles += (f'<div class="sr-t{" hit" if hit else ""}"><i></i>'
                  + ('<span class="sr-hit">命中</span>' if hit else '') + '</div>')
    return f'''<div class="vis v-search" id="vis-{i}">
      <div class="sr-stage">
        <div class="sr-box" id="srb-{i}">
          <svg class="sr-mag" viewBox="0 0 24 24"><circle cx="10.5" cy="10.5" r="6.5" fill="none" stroke="currentColor" stroke-width="2.4"/><path d="M15.5 15.5 L21 21" stroke="currentColor" stroke-width="2.4" stroke-linecap="round"/></svg>
          <span class="sr-q" id="srq-{i}">海滩上的狗</span>
          <span class="sr-caret" id="src-{i}"></span>
        </div>
        <div class="sr-grid">{tiles}</div>
        <div class="sr-tags"><span>人脸聚类</span><span>CLIP 语义</span><span>图内文字</span></div>
      </div>
      <div class="vis-badge">全部本地推理 · 一张照片都不出网</div>
    </div>'''


def vis_compare(i):
    return f'''<div class="vis v-compare" id="vis-{i}">
      <div class="cp-stage">
        <div class="cp-col bad" id="cpl-{i}">
          <div class="cp-h">订阅制云相册</div>
          <div class="cp-r"><span>存储</span><b class="bad">$9.99/月</b></div>
          <div class="cp-r"><span>隐私</span><b class="bad">云端扫描</b></div>
          <div class="cp-r"><span>数据锁定</span><b class="bad">导出困难</b></div>
        </div>
        <div class="cp-mid"><div class="cp-vs" id="cpv-{i}">VS</div></div>
        <div class="cp-col good" id="cpr-{i}">
          <div class="cp-h">Immich 自托管</div>
          <div class="cp-r"><span>存储</span><b class="good">0 元/月</b></div>
          <div class="cp-r"><span>隐私</span><b class="good">100% 本地</b></div>
          <div class="cp-r"><span>数据锁定</span><b class="good">标准文件</b></div>
        </div>
      </div>
      <div class="vis-badge">只有一次性硬件成本 · 之后只剩电费</div>
    </div>'''


def vis_terminal(i):
    return f'''<div class="vis v-term" id="vis-{i}">
      <div class="tm-win" id="tmw-{i}">
        <div class="tm-bar"><span class="tm-dot r"></span><span class="tm-dot y"></span><span class="tm-dot g"></span><span class="tm-title">immich · docker compose</span></div>
        <div class="tm-body">
          <div class="tm-cmd"><span class="tm-p">$</span><span class="tm-type" id="tmt-{i}">docker compose up -d</span></div>
          <div class="tm-lines" id="tmo-{i}">
            <div class="tm-l">✓ Container immich-server <i>Started</i></div>
            <div class="tm-l">✓ Container immich-machine-learning <i>Started</i></div>
            <div class="tm-l">➜ 打开 <b>http://localhost:2283</b></div>
          </div>
          <div class="tm-demo" id="tmd-{i}">在线 Demo：demo.immich.app · 能先试后装</div>
        </div>
      </div>
      <div class="vis-badge">默认端口 2283 · 目前仍在高速迭代</div>
    </div>'''


VIS = {"album": vis_album, "backup": vis_backup, "search": vis_search,
       "compare": vis_compare, "terminal": vis_terminal}


# ── 场景动效 ──────────────────────────────────────

def anim_album(i, s, e):
    n = max(2, int((e - s) / 0.9))
    return f'''tl.from("#albp-{i}", {{ x: -60, opacity: 0, duration: 0.6, ease: "power2.out" }}, {s+0.15:.2f});
      tl.from("#vis-{i} .alb-tile", {{ scale: 0.4, opacity: 0, duration: 0.4, stagger: 0.055, ease: "back.out(1.7)" }}, {s+0.5:.2f});
      tl.from("#albc-{i}", {{ x: 60, opacity: 0, duration: 0.5, ease: "power2.out" }}, {s+0.75:.2f});
      tl.to("#albc-{i}", {{ x: 8, duration: 0.34, yoyo: true, repeat: {n + 1}, ease: "sine.inOut" }}, {s+1.35:.2f});
      tl.from("#alba-{i}", {{ scale: 0.6, opacity: 0, duration: 0.4, ease: "back.out(2)" }}, {s+1.5:.2f});
      tl.to("#alba-{i}", {{ x: 10, duration: 0.5, yoyo: true, repeat: {n}, ease: "sine.inOut" }}, {s+1.9:.2f});
      tl.from("#albd-{i}", {{ scale: 0.7, opacity: 0, duration: 0.5, ease: "back.out(1.8)" }}, {s+1.75:.2f});
      tl.to("#albd-{i}", {{ filter: "drop-shadow(0 0 22px rgba(43,184,255,.95))", duration: 0.6, yoyo: true, repeat: {n}, ease: "sine.inOut" }}, {s+2.15:.2f});
      tl.from("#vis-{i} .vis-badge", {{ y: 22, opacity: 0, duration: 0.5, ease: "power2.out" }}, {s+0.45:.2f});'''


def anim_backup(i, s, e):
    n = max(2, int((e - s) / 0.9))
    return f'''tl.from("#bkp1-{i}", {{ x: -60, opacity: 0, duration: 0.55, ease: "power2.out" }}, {s+0.2:.2f});
      tl.from("#bkp2-{i}", {{ x: -60, opacity: 0, duration: 0.55, ease: "power2.out" }}, {s+0.4:.2f});
      tl.to("#bkp1-{i} .bk-t", {{ opacity: 1, duration: 0.3, stagger: 0.07, ease: "power1.out" }}, {s+0.7:.2f});
      tl.to("#bkp2-{i} .bk-t", {{ opacity: 1, duration: 0.3, stagger: 0.07, ease: "power1.out" }}, {s+0.95:.2f});
      tl.to("#bkb-{i}", {{ width: "100%", duration: 1.6, ease: "power1.inOut" }}, {s+1.0:.2f});
      tl.to({{ v: 0 }}, {{ v: 100, duration: 1.6, ease: "power1.inOut", onUpdate() {{ const el = document.querySelector("#bkpc-{i}"); if (el) el.textContent = Math.round(this.targets()[0].v) + "%"; }} }}, {s+1.0:.2f});
      tl.from("#vis-{i} .bk-chips span", {{ y: 16, opacity: 0, duration: 0.35, stagger: 0.12, ease: "power2.out" }}, {s+1.7:.2f});
      tl.to("#bkp1-{i}", {{ y: -9, duration: 0.5, yoyo: true, repeat: {n}, ease: "sine.inOut" }}, {s+2.7:.2f});
      tl.to("#bkp2-{i}", {{ y: -9, duration: 0.5, yoyo: true, repeat: {n}, ease: "sine.inOut" }}, {s+2.85:.2f});
      tl.from("#vis-{i} .vis-badge", {{ y: 22, opacity: 0, duration: 0.5, ease: "power2.out" }}, {s+0.45:.2f});'''


def anim_search(i, s, e):
    n = max(2, int((e - s) / 0.9))
    return f'''tl.from("#srb-{i}", {{ y: -34, opacity: 0, duration: 0.5, ease: "power2.out" }}, {s+0.2:.2f});
      tl.fromTo("#srq-{i}", {{ clipPath: "inset(0 100% 0 0)" }}, {{ clipPath: "inset(0 0% 0 0)", duration: 0.85, ease: "none" }}, {s+0.55:.2f});
      tl.to("#src-{i}", {{ opacity: 0, duration: 0.34, repeat: 5, yoyo: true, ease: "none" }}, {s+1.4:.2f});
      tl.from("#vis-{i} .sr-t", {{ scale: 0.6, opacity: 0, duration: 0.4, stagger: 0.09, ease: "back.out(1.8)" }}, {s+1.5:.2f});
      tl.from("#vis-{i} .sr-hit", {{ scale: 0.4, opacity: 0, duration: 0.4, stagger: 0.2, ease: "back.out(2.2)" }}, {s+2.35:.2f});
      tl.to("#vis-{i} .sr-t.hit", {{ opacity: 0.55, duration: 0.35, yoyo: true, repeat: {n * 2}, ease: "sine.inOut" }}, {s+2.8:.2f});
      tl.from("#vis-{i} .sr-tags span", {{ y: 16, opacity: 0, duration: 0.35, stagger: 0.12, ease: "power2.out" }}, {s+2.6:.2f});
      tl.from("#vis-{i} .vis-badge", {{ y: 22, opacity: 0, duration: 0.5, ease: "power2.out" }}, {s+0.45:.2f});'''


def anim_compare(i, s, e):
    n = max(2, int((e - s) / 0.9))
    return f'''tl.from("#cpl-{i}", {{ x: -70, opacity: 0, duration: 0.6, ease: "power2.out" }}, {s+0.2:.2f});
      tl.from("#cpl-{i} .cp-r", {{ opacity: 0, x: -22, duration: 0.35, stagger: 0.16, ease: "power1.out" }}, {s+0.7:.2f});
      tl.from("#cpv-{i}", {{ scale: 0.3, opacity: 0, duration: 0.5, ease: "back.out(2.4)" }}, {s+1.15:.2f});
      tl.from("#cpr-{i}", {{ x: 70, opacity: 0, duration: 0.6, ease: "power2.out" }}, {s+1.4:.2f});
      tl.from("#cpr-{i} .cp-r", {{ opacity: 0, x: 22, duration: 0.35, stagger: 0.16, ease: "power1.out" }}, {s+1.9:.2f});
      tl.to("#cpr-{i}", {{ boxShadow: "0 0 38px rgba(43,184,255,.35)", duration: 0.7, yoyo: true, repeat: {n}, ease: "sine.inOut" }}, {s+2.6:.2f});
      tl.from("#vis-{i} .vis-badge", {{ y: 22, opacity: 0, duration: 0.5, ease: "power2.out" }}, {s+0.45:.2f});'''


def anim_terminal(i, s, e):
    n = max(2, int((e - s) / 0.9))
    return f'''tl.from("#tmw-{i}", {{ scale: 0.94, opacity: 0, duration: 0.6, ease: "power2.out" }}, {s+0.2:.2f});
      tl.fromTo("#tmt-{i}", {{ clipPath: "inset(0 100% 0 0)" }}, {{ clipPath: "inset(0 0% 0 0)", duration: 1.15, ease: "none" }}, {s+0.8:.2f});
      tl.from("#tmo-{i} .tm-l", {{ opacity: 0, y: 14, duration: 0.35, stagger: 0.3, ease: "power1.out" }}, {s+2.1:.2f});
      tl.from("#tmd-{i}", {{ y: 18, opacity: 0, duration: 0.45, ease: "power2.out" }}, {s+3.3:.2f});
      tl.to("#tmd-{i}", {{ scale: 1.03, duration: 0.65, yoyo: true, repeat: {n}, ease: "sine.inOut" }}, {s+3.7:.2f});
      tl.from("#vis-{i} .vis-badge", {{ y: 22, opacity: 0, duration: 0.5, ease: "power2.out" }}, {s+0.45:.2f});'''


ANIM = {"album": anim_album, "backup": anim_backup, "search": anim_search,
        "compare": anim_compare, "terminal": anim_terminal}


# ── 卡片 ─────────────────────────────────────────

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
    return f'<div class="card{" ocard" if t == "outro" else ""}">{body}</div>'


CSS = '''
      @font-face { font-family: "PingFang SC"; src: local("PingFang SC"); }
      :root {
        /* 电光蓝主题 */
        --theme:#2BB8FF; --theme-deep:#0B62C4; --theme-mid:#1B8FEB;
        --ink:#F2F2F5; --ink-2:#9A9AA3; --ink-3:#7A7A84;
        --line:rgba(43,184,255,.20); --card:rgba(26,26,30,.92);
      }
      * { box-sizing:border-box; margin:0; padding:0; }
      html, body { width:1080px; height:1920px; overflow:hidden;
        font-family:"PingFang SC",sans-serif; color:var(--ink); line-height:1.6;
        background:
          linear-gradient(rgba(43,184,255,.05) 1px, transparent 1px) 0 0/72px 72px,
          linear-gradient(90deg, rgba(43,184,255,.05) 1px, transparent 1px) 0 0/72px 72px,
          radial-gradient(1100px 780px at 6% -12%, rgba(11,98,196,.42), transparent 60%),
          radial-gradient(900px 620px at 102% 0%, rgba(43,184,255,.16), transparent 58%),
          radial-gradient(820px 820px at 50% 112%, rgba(18,18,20,.95), transparent 62%),
          linear-gradient(168deg,#121214 0%,#17171B 46%,#0D0F0F 100%);
      }
      .scene { position:absolute; inset:0; display:flex; flex-direction:column;
        align-items:center; padding:150px 56px 400px; }
      .topbar { position:absolute; top:56px; left:56px; right:56px; display:flex;
        justify-content:space-between; align-items:center; z-index:20;
        font-size:24px; color:var(--ink-3); }
      .topbar .brand { font-weight:700; color:var(--theme); letter-spacing:.08em; }
      .topbar .date { font-family:monospace; letter-spacing:.05em; }
      .progress { position:absolute; top:0; left:0; height:4px;
        background:linear-gradient(90deg,var(--theme-deep),var(--theme)); z-index:30; width:0%;
        box-shadow:0 0 12px rgba(43,184,255,.9); }
      .wm { position:absolute; right:40px; bottom:104px; z-index:25; font-size:44px; font-weight:600;
        color:rgba(255,255,255,.55); text-shadow:0 0 3px rgba(0,0,0,.55),0 1px 3px rgba(0,0,0,.40),0 -1px 2px rgba(0,0,0,.30); }

      .vis { width:100%; height:560px; border-radius:20px; overflow:hidden; position:relative;
        border:1px solid var(--line); box-shadow:0 24px 60px -28px rgba(0,0,0,.85);
        margin-bottom:36px; background:#0D0F0F; }
      .vis-badge { position:absolute; left:20px; bottom:20px; font-size:22px; font-weight:700;
        letter-spacing:.06em; color:#121214; background:var(--theme); padding:9px 18px; border-radius:9px;
        box-shadow:0 0 20px rgba(43,184,255,.55); }

      /* 0 相册搬家 */
      .v-album { display:flex; align-items:center; justify-content:center;
        background:radial-gradient(700px 420px at 42% 45%, rgba(43,184,255,.12), transparent 65%),#101013; }
      .alb-stage { display:flex; align-items:center; gap:30px; padding:0 28px; }
      .alb-phone { width:244px; height:398px; border-radius:34px; border:3px solid var(--theme);
        background:#0A0B0C; padding:16px 14px 10px;
        box-shadow:0 0 34px rgba(43,184,255,.32), inset 0 0 24px rgba(43,184,255,.06); }
      .alb-notch { width:70px; height:8px; border-radius:6px; background:rgba(255,255,255,.18); margin:0 auto 12px; }
      .alb-grid { display:grid; grid-template-columns:repeat(3,1fr); gap:7px; }
      .alb-tile { height:92px; border-radius:9px;
        background:linear-gradient(140deg, rgba(43,184,255,.55), rgba(11,98,196,.35)); }
      .alb-tile:nth-child(3n) { background:linear-gradient(140deg, rgba(255,255,255,.18), rgba(43,184,255,.26)); }
      .alb-tile:nth-child(4n) { background:linear-gradient(140deg, rgba(43,184,255,.30), rgba(255,255,255,.10)); }
      .alb-cap { margin-top:12px; text-align:center; font-size:18px; color:var(--ink-3); font-family:monospace; }
      .alb-side { display:flex; flex-direction:column; align-items:center; gap:9px; }
      .alb-cloud { display:flex; flex-direction:column; align-items:center; gap:2px; width:236px;
        padding:12px; border-radius:16px; border:1px solid rgba(255,90,90,.35);
        background:rgba(255,90,90,.08); color:#FF7A7A; }
      .alb-cloud svg { width:82px; height:48px; }
      .alb-cloudcap { font-size:22px; font-weight:700; } .alb-cloudprice { font-size:20px; font-family:monospace; color:#FF9E9E; }
      .alb-arrow { font-size:23px; font-weight:800; color:var(--theme); letter-spacing:.1em;
        padding:3px 16px; border-radius:20px; background:rgba(43,184,255,.10); border:1px solid var(--line); }
      .alb-disk { display:flex; flex-direction:column; align-items:center; color:var(--theme); width:236px;
        padding:10px; border-radius:16px; border:1px solid var(--line); background:rgba(43,184,255,.07); }
      .alb-disk svg { width:82px; height:58px; }
      .alb-diskcap { font-size:22px; font-weight:800; color:var(--ink); }

      /* 1 手机自动备份 */
      .v-backup { display:flex; align-items:center; justify-content:center;
        background:radial-gradient(700px 420px at 50% 40%, rgba(43,184,255,.10), transparent 65%),#101013; }
      .bk-stage { width:100%; display:flex; flex-direction:column; align-items:center; gap:24px; padding:0 30px; }
      .bk-phones { display:flex; gap:42px; }
      .bk-phone { width:168px; border-radius:24px; border:2px solid var(--line); background:#0A0B0C;
        padding:14px 12px; text-align:center; }
      .bk-brand { font-size:20px; font-weight:800; color:var(--theme); letter-spacing:.08em; margin-bottom:10px; }
      .bk-grid { display:grid; grid-template-columns:repeat(3,1fr); gap:6px; }
      .bk-t { height:36px; border-radius:7px; background:rgba(43,184,255,.45); opacity:.12; }
      .bk-badge { margin-top:10px; font-size:17px; color:var(--ink-3); }
      .bk-flow { width:100%; }
      .bk-flowlabel { display:flex; justify-content:space-between; font-size:22px; color:var(--ink-2); margin-bottom:10px; }
      .bk-pct { font-family:monospace; color:var(--theme); font-weight:800; }
      .bk-track { height:16px; border-radius:10px; background:rgba(255,255,255,.08); overflow:hidden; }
      .bk-bar { width:0%; height:100%; border-radius:10px;
        background:linear-gradient(90deg,var(--theme-deep),var(--theme)); box-shadow:0 0 18px rgba(43,184,255,.8); }
      .bk-chips { display:flex; gap:12px; margin-top:16px; }
      .bk-chips span { font-size:20px; color:var(--ink-2); padding:6px 15px; border-radius:16px;
        background:rgba(43,184,255,.08); border:1px solid var(--line); }

      /* 2 本地 AI 搜索 */
      .v-search { display:flex; align-items:center; justify-content:center;
        background:radial-gradient(700px 420px at 50% 35%, rgba(43,184,255,.12), transparent 65%),#101013; }
      .sr-stage { width:100%; display:flex; flex-direction:column; align-items:center; gap:22px; padding:0 34px; }
      .sr-box { display:flex; align-items:center; gap:14px; width:100%; padding:18px 24px;
        border-radius:18px; background:#0A0B0C; border:1px solid var(--line); }
      .sr-mag { width:32px; height:32px; color:var(--theme); flex:none; }
      .sr-q { font-size:32px; font-weight:700; color:var(--ink); white-space:nowrap;
        clip-path:inset(0 100% 0 0); }
      .sr-caret { width:3px; height:32px; background:var(--theme); flex:none; }
      .sr-grid { display:grid; grid-template-columns:repeat(4,1fr); gap:12px; width:100%; }
      .sr-t { position:relative; height:84px; border-radius:12px; border:1px solid rgba(255,255,255,.06);
        background:rgba(255,255,255,.05); overflow:hidden; }
      .sr-t i { position:absolute; inset:0; opacity:.5;
        background:linear-gradient(140deg, rgba(255,255,255,.12), rgba(255,255,255,.02)); }
      .sr-t.hit { border-color:var(--theme); box-shadow:0 0 22px rgba(43,184,255,.35); }
      .sr-t.hit i { opacity:1; background:linear-gradient(140deg, rgba(43,184,255,.60), rgba(11,98,196,.30)); }
      .sr-hit { position:absolute; right:8px; bottom:8px; font-size:16px; font-weight:800; color:#121214;
        background:var(--theme); padding:3px 9px; border-radius:7px; }
      .sr-tags { display:flex; gap:12px; }
      .sr-tags span { font-size:19px; color:var(--ink-2); padding:5px 15px; border-radius:15px;
        background:rgba(43,184,255,.08); border:1px solid var(--line); }

      /* 3 算笔账对比 */
      .v-compare { display:flex; align-items:center; justify-content:center;
        background:radial-gradient(700px 420px at 50% 45%, rgba(43,184,255,.10), transparent 65%),#101013; }
      .cp-stage { display:flex; align-items:center; gap:18px; width:100%; padding:0 24px; }
      .cp-col { flex:1; border-radius:18px; padding:24px 20px; border:1px solid rgba(255,255,255,.08);
        background:rgba(255,255,255,.04); }
      .cp-col.good { border-color:var(--line); background:rgba(43,184,255,.07); }
      .cp-h { font-size:24px; font-weight:800; margin-bottom:16px; color:var(--ink-2); text-align:center; }
      .cp-col.good .cp-h { color:var(--theme); }
      .cp-r { display:flex; justify-content:space-between; align-items:baseline; padding:11px 2px;
        border-bottom:1px dashed rgba(255,255,255,.08); font-size:21px; color:var(--ink-3); }
      .cp-r:last-child { border-bottom:0; }
      .cp-r b { font-size:24px; font-weight:800; font-family:monospace; }
      .cp-r b.bad { color:#FF7A7A; } .cp-r b.good { color:var(--theme); }
      .cp-mid { display:flex; align-items:center; }
      .cp-vs { font-size:28px; font-weight:900; color:var(--ink-2); font-family:monospace;
        padding:12px 14px; border-radius:50%; border:1px solid var(--line); background:rgba(43,184,255,.08); }

      /* 4 终端部署 */
      .v-term { display:flex; align-items:center; justify-content:center;
        background:radial-gradient(700px 420px at 50% 40%, rgba(43,184,255,.12), transparent 65%),#101013; }
      .tm-win { width:100%; max-width:840px; border-radius:18px; overflow:hidden;
        border:1px solid var(--line); background:#0A0B0C; box-shadow:0 20px 50px -26px rgba(0,0,0,.9); }
      .tm-bar { display:flex; align-items:center; gap:10px; padding:13px 18px;
        background:rgba(255,255,255,.05); border-bottom:1px solid rgba(255,255,255,.06); }
      .tm-dot { width:14px; height:14px; border-radius:50%; }
      .tm-dot.r { background:#FF5F57; } .tm-dot.y { background:#FEBC2E; } .tm-dot.g { background:#28C840; }
      .tm-title { margin-left:10px; font-size:19px; color:var(--ink-3); font-family:monospace; }
      .tm-body { padding:22px 26px 24px; font-family:monospace; }
      .tm-cmd { font-size:27px; color:var(--ink); display:flex; align-items:center; }
      .tm-p { color:var(--theme); margin-right:10px; font-weight:800; }
      .tm-type { display:inline-block; white-space:nowrap; color:#8FE0B0; font-weight:700;
        clip-path:inset(0 100% 0 0); }
      .tm-lines { margin-top:16px; }
      .tm-l { font-size:21px; line-height:1.9; color:var(--ink-2); }
      .tm-l i { color:#8FE0B0; font-style:normal; } .tm-l b { color:var(--theme); }
      .tm-demo { margin-top:18px; display:inline-block; font-size:21px; color:var(--theme);
        padding:9px 18px; border-radius:12px; background:rgba(43,184,255,.10);
        border:1px solid var(--line); font-family:"PingFang SC",sans-serif; }

      .card { position:relative; width:100%; background:var(--card); border:1px solid var(--line);
        border-radius:24px; padding:48px 46px 50px;
        box-shadow:0 1px 2px rgba(0,0,0,.3),0 30px 60px -30px rgba(0,0,0,.7);
        overflow:hidden; }
      .card::before { content:""; position:absolute; left:0; top:40px; bottom:40px; width:6px;
        border-radius:0 4px 4px 0; background:linear-gradient(180deg,var(--theme-mid),var(--theme-deep)); }
      .eyebrow { font-size:24px; letter-spacing:.2em; color:var(--theme); font-weight:700; margin-bottom:22px; }
      h1 { font-size:66px; line-height:1.24; font-weight:800; letter-spacing:-.01em; }
      h2 { font-size:46px; line-height:1.3; font-weight:800; letter-spacing:-.005em; }
      .accent { color:var(--theme); text-shadow:0 0 18px rgba(43,184,255,.5); }
      .hsubtitle { margin-top:24px; color:var(--ink-2); font-size:27px; line-height:1.5; }
      .stats { margin-top:38px; display:flex; flex-wrap:wrap; gap:16px; }
      .stat { background:rgba(43,184,255,.08); border:1px solid var(--line); border-radius:16px;
        padding:20px 28px; min-width:250px; }
      .stat .k { font-size:17px; letter-spacing:.1em; color:var(--ink-3); }
      .stat .v { font-size:40px; font-weight:800; color:var(--theme); margin-top:6px; }
      .bigwrap { margin-top:36px; background:linear-gradient(135deg,rgba(43,184,255,.14),rgba(43,184,255,.04));
        border:1px solid rgba(43,184,255,.24); border-radius:20px; padding:32px 40px; }
      .bignum { font-size:108px; font-weight:900; line-height:1.05;
        background:linear-gradient(135deg,var(--theme) 0%,#9FD8FF 100%);
        -webkit-background-clip:text; -webkit-text-fill-color:transparent; background-clip:text; }
      .biglabel { margin-top:8px; font-size:23px; color:var(--ink-2); letter-spacing:.03em; line-height:1.5; }
      .ocard { text-align:center; padding:72px 46px; }
      .otitle { font-size:58px; font-weight:900; line-height:1.25; }
      .octa { margin-top:34px; font-size:38px; font-weight:800; color:var(--theme);
        text-shadow:0 0 18px rgba(43,184,255,.45); }
      .osub { margin-top:22px; font-size:28px; color:var(--ink-3); }

      .subtitle { position:absolute; left:56px; right:56px; bottom:150px; z-index:15;
        display:flex; justify-content:center; pointer-events:none; }
      .sub-inner { max-width:100%; padding:26px 34px; border-radius:24px;
        background:rgba(8,8,10,.9); backdrop-filter:blur(10px);
        box-shadow:0 14px 36px -18px rgba(0,0,0,.8); border-left:6px solid var(--theme);
        font-size:33px; font-weight:600; color:#fff; line-height:1.5; }
'''

PAGE = '''<!doctype html>
<html lang="zh-CN">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=1080, height=1920" />
    <script src="https://cdn.jsdelivr.net/npm/gsap@3.14.2/dist/gsap.min.js"></script>
    <style>
__CSS__
    </style>
  </head>
  <body>
    <div id="root" data-composition-id="main" data-start="0" data-duration="__DUR__" data-width="1080" data-height="1920">
      <div id="progress" class="progress clip" data-start="0" data-duration="__DUR__" data-track-index="100"></div>
      <div id="topbar" class="topbar clip" data-start="0" data-duration="__DUR__" data-track-index="1">
        <span class="brand">__WM__ · 开源情报站</span>
        <span class="date">__DATE__</span>
      </div>
      <div id="wm" class="wm clip" data-start="0" data-duration="__DUR__" data-track-index="2">__WM__</div>
      __SCENES__
      __SUBS__
      <audio id="narration-audio" data-start="0" data-duration="__DUR__" data-track-index="51" src="audio_combined.wav" data-volume="1.0"></audio>
    </div>
    <script>
      window.__timelines = window.__timelines || {};
      const tl = gsap.timeline({ paused: true });
      const DUR = __DUR__;
      tl.to("#progress", { width: "100%", duration: DUR, ease: "none" }, 0);
      __ANIM__
      __SUBT__
      window.__timelines["main"] = tl;
    </script>
  </body>
</html>'''


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
        v = sc.get("visual", "album")
        scene_divs.append(
            f'<div id="scene-{i}" class="scene clip" data-start="{s:.2f}" '
            f'data-duration="{e - s:.2f}" data-track-index="3">{VIS[v](i)}{card_html(sc, i)}</div>')

    sub_divs, tl_lines = [], []
    for i, ln in enumerate(lines):
        s, e = ln["start"], ln["end"]
        sub_divs.append(
            f'<div id="sub-{i}" class="subtitle clip" data-start="{s:.2f}" '
            f'data-duration="{e - s:.2f}" data-track-index="10">'
            f'<div class="sub-inner">{html.escape(ln["text"])}</div></div>')
        tl_lines.append(f'''tl.from("#sub-{i} .sub-inner", {{ y: 26, opacity: 0, duration: 0.25, ease: "power2.out" }}, {s:.2f});
      tl.to("#sub-{i} .sub-inner", {{ opacity: 0, duration: 0.18, ease: "power2.in" }}, {e - 0.18:.2f});
      tl.set("#sub-{i} .sub-inner", {{ opacity: 0 }}, {e:.2f});''')

    anim_lines = []
    for i, sc in enumerate(scenes):
        s, e = sc["_start"], sc["_end"]
        v = sc.get("visual", "album")
        anim_lines.append(ANIM[v](i, s, e))
        anim_lines.append(f'''tl.from("#scene-{i} .card", {{ y: 44, opacity: 0, duration: 0.5, ease: "power3.out" }}, {s:.2f});
      tl.from("#scene-{i} .anim", {{ y: 26, opacity: 0, duration: 0.45, stagger: 0.09, ease: "power2.out" }}, {s + 0.18:.2f});
      tl.from("#scene-{i} .vis", {{ scale: 1.06, opacity: 0, duration: 0.6, ease: "power2.out" }}, {s:.2f});
      tl.to("#scene-{i} .card", {{ opacity: 0, y: -18, duration: 0.3, ease: "power2.in" }}, {e - 0.32:.2f});
      tl.set("#scene-{i} .card", {{ opacity: 0 }}, {e:.2f});''')

    page = (PAGE
            .replace("__CSS__", CSS)
            .replace("__DUR__", f"{DUR}")
            .replace("__WM__", html.escape(wm))
            .replace("__DATE__", html.escape(date))
            .replace("__SCENES__", "\n      ".join(scene_divs))
            .replace("__SUBS__", "\n      ".join(sub_divs))
            .replace("__ANIM__", "\n      ".join(anim_lines))
            .replace("__SUBT__", "\n      ".join(tl_lines)))

    open(os.path.join(STORY, "index.html"), "w", encoding="utf-8").write(page)
    open(os.path.join(STORY, "hyperframes.json"), "w").write(json.dumps({
        "name": "immich", "width": 1080, "height": 1920, "fps": 30,
        "duration": DUR, "output": "output.mp4"
    }, ensure_ascii=False, indent=2))
    print(f"index.html 已生成，总时长 {DUR}s，{len(scenes)} 场景")


if __name__ == "__main__":
    main()
