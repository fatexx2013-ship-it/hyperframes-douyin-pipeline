#!/usr/bin/env python3
"""腾讯元宝桌宠 - 抖音竖屏视频生成器（沿用产线规范，支持截图场景）"""
import json, os, re, shutil, subprocess, sys, time

PIPELINE_DIR = "/Volumes/PSSD/抖音视频"
sys.path.insert(0, PIPELINE_DIR)
import generate_news_card_video as g

FFMPEG, FFPROBE, HYPERFRAMES, OUTPUT_DIR = g.FFMPEG, g.FFPROBE, g.HYPERFRAMES, g.OUTPUT_DIR
C, batch_tts, get_audio_duration = g.C, g.batch_tts, g.get_audio_duration
esc, rich = g.escape_html, g.rich

# ── 卡片渲染器（复用产线 + 新增 image 类型）─────────────────
def card_image(card):
    img = card.get("image", "")
    stats = ""
    for s in card.get("stats", []):
        stats += ('<div class="stat"><div class="k">' + esc(s.get("k","")) + '</div>'
                  '<div class="v">' + esc(s.get("v","")) + '</div></div>')
    sub = card.get("subtitle", "")
    sub_html = f'<p class="hsubtitle anim">{esc(sub)}</p>' if sub else ""
    return f'''
      <div class="card imgcard">
        <img class="scene-img anim" src="{esc(img)}" />
        <p class="eyebrow anim">{esc(card.get("eyebrow",""))}</p>
        <h1 class="anim">{rich(card.get("title",""))}</h1>
        {sub_html}
        <div class="stats anim">{stats}</div>
      </div>'''

RENDERERS = {"header": g.card_header, "stat": g.card_stat, "compare": g.card_compare,
             "outro": g.card_outro, "image": card_image}

def log(*a): print(*a, flush=True)

# ── HTML 构建（在产线 CSS 基础上增加 imgcard）──────────────
def build_html(scenes, line_timings, total_duration, meta):
    sc_clips, sc_js = "", ""
    for si, sc in enumerate(scenes):
        s0, s1 = sc["_start"], sc["_end"]
        dur = s1 - s0
        inner = RENDERERS.get(sc["type"], g.card_header)(sc.get("card", {}))
        sid = f"scene-{si}"
        sc_clips += f'\n      <div id="{sid}" class="scene clip" data-start="{s0:.2f}" data-duration="{dur:.2f}" data-track-index="3">\n{inner}\n      </div>'
        sc_js += f'''
      tl.from("#{sid} .card",{{y:44,opacity:0,duration:0.5,ease:"power3.out"}},{s0:.2f});
      tl.from("#{sid} .anim",{{y:26,opacity:0,duration:0.45,stagger:0.09,ease:"power2.out"}},{s0+0.18:.2f});
      tl.to("#{sid} .card",{{opacity:0,y:-18,duration:0.3,ease:"power2.in"}},{s1-0.32:.2f});
      tl.set("#{sid} .card",{{opacity:0}},{s1:.2f});'''
        if sc["type"] == "compare":
            sc_js += f'''
      tl.to("#{sid} .cbar i",{{width:(i,el)=>el.dataset.w+"%",duration:0.7,stagger:0.14,ease:"power3.out"}},{s0+0.45:.2f});'''

    sub_clips, sub_js = "", ""
    for li, lt in enumerate(line_timings):
        ld = lt["end"] - lt["start"]
        sid = f"sub-{li}"
        sub_clips += f'\n      <div id="{sid}" class="subtitle clip" data-start="{lt["start"]:.2f}" data-duration="{ld:.2f}" data-track-index="10">\n        <div class="sub-inner">{esc(lt["text"])}</div>\n      </div>'
        sub_js += f'''
      tl.from("#{sid} .sub-inner",{{y:26,opacity:0,duration:0.25,ease:"power2.out"}},{lt["start"]:.2f});
      tl.to("#{sid} .sub-inner",{{opacity:0,duration:0.18,ease:"power2.in"}},{lt["end"]-0.18:.2f});
      tl.set("#{sid} .sub-inner",{{opacity:0}},{lt["end"]:.2f});'''

    wm = meta.get("watermark","")
    wm_h = (f'<div id="wm" class="wm clip" data-start="0" data-duration="{total_duration:.1f}" '
            f'data-track-index="2">{esc(wm)}</div>') if wm else ""

    return f'''<!doctype html>
<html lang="zh-CN">
  <head>
    <meta charset="UTF-8"/>
    <meta name="viewport" content="width=1080,height=1920"/>
    <script src="https://cdn.jsdelivr.net/npm/gsap@3.14.2/dist/gsap.min.js"></script>
    <style>
      @font-face{{font-family:"PingFang SC";src:local("PingFang SC")}}
      :root{{--theme:{C["theme"]};--theme-deep:{C["theme_deep"]};--theme-mid:{C["theme_mid"]};
        --ink:{C["ink"]};--ink-2:{C["ink2"]};--ink-3:{C["ink3"]};--line:{C["line"]};--card:{C["card"]}}}
      *{{box-sizing:border-box;margin:0;padding:0}}
      html,body{{width:1080px;height:1920px;overflow:hidden;
        font-family:"PingFang SC",sans-serif;color:var(--ink);line-height:1.6;
        background:
          linear-gradient(rgba(79,70,229,.05) 1px,transparent 1px) 0 0/72px 72px,
          linear-gradient(90deg,rgba(79,70,229,.05) 1px,transparent 1px) 0 0/72px 72px,
          radial-gradient(1100px 780px at 6% -12%,rgba(79,70,229,.30),transparent 60%),
          radial-gradient(900px 620px at 102% 0%,rgba(129,140,248,.26),transparent 58%),
          radial-gradient(820px 820px at 50% 112%,rgba(49,46,129,.14),transparent 62%),
          linear-gradient(168deg,#F4F5FF 0%,#E8EAFF 46%,#FBFBFE 100%)}}
      .scene{{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;padding:170px 56px 400px}}
      .topbar{{position:absolute;top:56px;left:56px;right:56px;display:flex;justify-content:space-between;align-items:center;z-index:20;font-size:24px;color:var(--ink-3)}}
      .topbar .brand{{font-weight:700;color:var(--theme)}}
      .topbar .date{{font-family:monospace;letter-spacing:.05em}}
      .progress{{position:absolute;top:0;left:0;height:4px;background:linear-gradient(90deg,var(--theme),var(--theme-mid));z-index:30;width:0%}}
      .wm{{position:absolute;right:40px;bottom:104px;z-index:25;font-size:44px;font-weight:600;color:rgba(255,255,255,.55);text-shadow:0 0 3px rgba(0,0,0,.55),0 1px 3px rgba(0,0,0,.40),0 -1px 2px rgba(0,0,0,.30)}}
      .card{{position:relative;width:100%;background:var(--card);border:1px solid var(--line);border-radius:24px;padding:56px 50px 52px;box-shadow:0 1px 2px rgba(18,23,43,.03),0 30px 60px -30px rgba(49,46,129,.34)}}
      .card::before{{content:"";position:absolute;left:0;top:40px;bottom:40px;width:6px;border-radius:0 4px 4px 0;background:linear-gradient(180deg,var(--theme-mid),var(--theme-deep))}}
      .eyebrow{{font-size:24px;letter-spacing:.2em;text-transform:uppercase;color:var(--theme);font-weight:700;margin-bottom:22px}}
      h1{{font-size:70px;line-height:1.22;font-weight:800;letter-spacing:-.01em}}
      h2{{font-size:48px;line-height:1.3;font-weight:800;letter-spacing:-.005em}}
      .accent{{color:var(--theme)}}
      .hsubtitle{{margin-top:24px;color:var(--ink-2);font-size:27px}}
      .stats{{margin-top:38px;display:flex;flex-wrap:wrap;gap:16px}}
      .stat{{background:#F6F7FE;border:1px solid var(--line);border-radius:16px;padding:20px 28px;min-width:250px}}
      .stat .k{{font-size:17px;letter-spacing:.1em;color:var(--ink-3)}}
      .stat .v{{font-size:42px;font-weight:800;color:var(--theme-deep);margin-top:6px}}
      .bigwrap{{margin-top:36px;background:linear-gradient(135deg,rgba(79,70,229,.10),rgba(99,102,241,.04));border:1px solid rgba(79,70,229,.16);border-radius:20px;padding:32px 40px}}
      .bignum{{font-size:126px;font-weight:900;line-height:1.05;background:linear-gradient(135deg,var(--theme) 0%,var(--theme-deep) 100%);-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text}}
      .biglabel{{margin-top:8px;font-size:24px;color:var(--ink-3);letter-spacing:.06em}}
      .items{{list-style:none;margin-top:32px;display:flex;flex-direction:column;gap:16px}}
      .items li{{display:flex;align-items:baseline;gap:18px;border-top:1px dashed var(--line);padding-top:16px}}
      .items li .ik{{flex:0 0 190px;font-size:23px;color:var(--ink-3);font-weight:600}}
      .items li .iv{{flex:1;font-size:29px;color:var(--ink);font-weight:700}}
      .rows{{margin-top:36px;display:flex;flex-direction:column;gap:26px}}
      .crow{{display:flex;align-items:center;gap:20px}}
      .cname{{flex:0 0 190px;font-size:27px;font-weight:700;color:var(--ink2,var(--ink-2))}}
      .cbar{{flex:1;height:34px;background:#F1F2FA;border-radius:999px;overflow:hidden}}
      .cbar i{{display:block;height:100%;border-radius:999px;background:linear-gradient(90deg,var(--theme-mid),var(--theme))}}
      .cval{{flex:0 0 168px;text-align:right;font-size:27px;font-weight:800;color:var(--theme-deep)}}
      .cfoot{{margin-top:30px;font-size:25px;color:var(--ink-3);text-align:right}}
      .ocard{{text-align:center;padding:80px 50px}}
      .otitle{{font-size:62px;font-weight:900;line-height:1.25}}
      .octa{{margin-top:34px;font-size:40px;font-weight:800;color:var(--theme)}}
      .osub{{margin-top:22px;font-size:28px;color:var(--ink-3)}}
      .imgcard{{text-align:center;padding:50px 40px 48px}}
      .scene-img{{max-width:88%;max-height:680px;object-fit:contain;border-radius:18px;margin-bottom:28px;box-shadow:0 6px 24px rgba(0,0,0,.12)}}
      .subtitle{{position:absolute;left:56px;right:56px;bottom:150px;z-index:15;display:flex;justify-content:center;pointer-events:none}}
      .sub-inner{{max-width:100%;padding:26px 34px;border-radius:24px;background:rgba(18,23,43,.86);backdrop-filter:blur(10px);box-shadow:0 14px 36px -18px rgba(18,23,43,.7);border-left:6px solid var(--theme);font-size:33px;font-weight:600;color:#fff;line-height:1.5}}
    </style>
  </head>
  <body>
    <div id="root" data-composition-id="main" data-start="0" data-duration="{total_duration:.1f}" data-width="1080" data-height="1920">
      <div id="progress" class="progress clip" data-start="0" data-duration="{total_duration:.1f}" data-track-index="100"></div>
      <div id="topbar" class="topbar clip" data-start="0" data-duration="{total_duration:.1f}" data-track-index="1">
        <span class="brand">{esc(meta.get("brand",""))}</span>
        <span class="date">{esc(meta.get("date",""))}</span>
      </div>
      {wm_h}
      {sc_clips}
      {sub_clips}
      <audio id="narration-audio" data-start="0" data-duration="{total_duration:.1f}" data-track-index="51" src="audio_combined.wav" data-volume="1.0"></audio>
    </div>
    <script>
      window.__timelines=window.__timelines||{{}};
      const tl=gsap.timeline({{paused:true}});
      const DUR={total_duration:.1f};
      tl.to("#progress",{{width:"100%",duration:DUR,ease:"none"}},0);
      {sc_js}
      {sub_js}
      window.__timelines["main"]=tl;
    </script>
  </body>
</html>'''


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("data")
    ap.add_argument("--emotion", default="thoughtful")
    ap.add_argument("--pad-line", type=float, default=0.30)
    ap.add_argument("--pad-scene", type=float, default=0.3)
    ap.add_argument("--lead", type=float, default=0.5)
    ap.add_argument("--scene-lead", type=float, default=0.2)
    ap.add_argument("--outro", type=float, default=0.3)
    ap.add_argument("--bgm-volume", type=float, default=0.18)
    ap.add_argument("--no-trim", action="store_true")
    args = ap.parse_args()

    with open(args.data, encoding="utf-8") as f:
        data = json.load(f)
    scenes = data["scenes"]
    title = data.get("title", "news")

    safe = re.sub(r'[^\w\u4e00-\u9fff]', '_', title)[:30]
    run_dir = os.path.join(OUTPUT_DIR, safe + "_" + str(int(time.time())))
    os.makedirs(run_dir, exist_ok=True)

    log("=== 腾讯元宝桌宠 · 抖音竖屏视频 ===")
    log("标题:", title, "| 场景:", len(scenes), "| 输出:", run_dir)

    # Step 1: TTS
    jobs, meta = [], []
    for si, sc in enumerate(scenes):
        for li, line in enumerate(sc["lines"]):
            out = os.path.join(run_dir, "line_%02d_%02d.wav" % (si, li))
            jobs.append((line["text"], out))
            meta.append({"si": si, "text": line["text"], "path": out, "emotion": line.get("emotion") or args.emotion})
    log("\n[1] TTS (emotion=%s)..." % args.emotion)
    n_ok = batch_tts(jobs, run_dir, args.emotion)
    log("  ok %d/%d" % (n_ok, len(jobs)))

    if not args.no_trim:
        log("[1.5] Trim silence...")
        saved = 0.0
        for m in meta:
            if not os.path.exists(m["path"]): continue
            raw = m["path"].replace(".wav", ".raw.wav")
            if not os.path.exists(raw): shutil.copy(m["path"], raw)
            before = get_audio_duration(raw)
            tmp = m["path"].replace(".wav", ".t.wav")
            subprocess.run([FFMPEG, "-y", "-v", "quiet", "-i", raw, "-af",
                "silenceremove=start_periods=1:start_duration=0.05:start_threshold=-45dB:detection=peak,"
                "areverse,silenceremove=start_periods=1:start_duration=0.05:start_threshold=-45dB:detection=peak,areverse",
                tmp], capture_output=True)
            if os.path.exists(tmp) and os.path.getsize(tmp) > 1000:
                os.replace(tmp, m["path"])
                saved += before - get_audio_duration(m["path"])
            elif os.path.exists(tmp):
                os.remove(tmp)
        log("  -%.2fs" % saved)

    la = []
    for m in meta:
        dur = get_audio_duration(m["path"])
        la.append(dict(m, dur=dur))

    # Step 2: Timeline
    log("[2] Timeline...")
    t = args.lead
    lt = []
    for x in la:
        lt.append({"si": x["si"], "start": t, "end": t + x["dur"], "text": x["text"]})
        t += x["dur"] + args.pad_line
    cursor = 0.0
    for si in range(len(scenes)):
        li = [l for l in lt if l["si"] == si]
        if not li: continue
        sd = (li[-1]["end"] - li[0]["start"]) + args.scene_lead + args.pad_scene
        scenes[si]["_start"] = cursor
        scenes[si]["_end"] = cursor + sd
        off = cursor + args.scene_lead - li[0]["start"]
        for l in li: l["start"] += off; l["end"] += off
        cursor = scenes[si]["_end"]
    first = next(s for s in scenes if "_start" in s)
    if first["_start"] > 0:
        d = first["_start"]
        for s in scenes:
            if "_start" in s: s["_start"] -= d; s["_end"] -= d
        for l in lt: l["start"] -= d; l["end"] -= d
        cursor -= d
    total = cursor + args.outro
    vt = sum(x["dur"] for x in la)
    log("  total=%.1fs (voice=%.1fs)" % (total, vt))

    # Step 3: Audio
    log("[3] Audio track...")
    narr = os.path.join(run_dir, "narration.wav")
    fa = [FFMPEG, "-y"]
    for x in la: fa += ["-i", x["path"]]
    n = len(la)
    parts = []
    for i, l in enumerate(lt):
        parts.append("[%d:a]adelay=%d:all=1[a%d]" % (i, int(l["start"] * 1000), i))
    parts.append("".join("[a%d]" % i for i in range(n)) + "amix=inputs=%d:duration=longest:normalize=0[voice]" % n)
    parts.append("[voice]apad=whole_dur=%.2f[va]" % total)
    fa += ["-filter_complex", ";".join(parts), "-map", "[va]", "-t", "%.2f" % total,
           "-ar", "24000", "-ac", "1", "-c:a", "pcm_s16le", narr]
    subprocess.run(fa, capture_output=True, text=True)

    comb = os.path.join(run_dir, "audio_combined.wav")
    bgm = data.get("bgm", "")
    if bgm and os.path.exists(bgm):
        bgm_d = os.path.join(run_dir, "bgm" + os.path.splitext(bgm)[1])
        shutil.copy(bgm, bgm_d)
        r = subprocess.run([FFMPEG, "-y", "-i", narr, "-stream_loop", "-1", "-i", bgm_d,
            "-filter_complex", "[1:a]volume=%.3f,atrim=0:%.2f,asetpts=PTS-STARTPTS[b];"
            "[0:a][b]amix=inputs=2:duration=first:normalize=0[m]" % (args.bgm_volume, total),
            "-map", "[m]", "-t", "%.2f" % total, "-ar", "24000", "-ac", "1",
            "-c:a", "pcm_s16le", comb], capture_output=True, text=True)
        log("  voice+BGM ok" if r.returncode == 0 else "  BGM mix failed")
        if r.returncode != 0: shutil.copy(narr, comb)
    else:
        shutil.copy(narr, comb)

    # Step 4: Copy images + HTML
    log("[4] HTML...")
    mat_dir = os.path.join(PIPELINE_DIR, "story/tencent-yuanbao-pet/materials")
    for sc in scenes:
        img = sc.get("card", {}).get("image", "")
        if img and not img.startswith("http"):
            src = os.path.join(mat_dir, img)
            if os.path.exists(src):
                dst = os.path.join(run_dir, img)
                shutil.copy(src, dst)
    meta_d = {"watermark": data.get("watermark",""), "date": data.get("date",""), "brand": "jerrychen2001 · AI 快讯"}
    with open(os.path.join(run_dir, "index.html"), "w", encoding="utf-8") as f:
        f.write(build_html(scenes, lt, total, meta_d))
    with open(os.path.join(run_dir, "hyperframes.json"), "w") as f:
        json.dump({"$schema":"https://hyperframes.heygen.com/schema/hyperframes.json",
                    "registry":"https://raw.githubusercontent.com/heygen-com/hyperframes/main/registry",
                    "paths":{"blocks":"compositions","components":"compositions/components","assets":"assets"},
                    "media":{"autoProxy":True}}, f, indent=2)
    with open(os.path.join(run_dir, "script.json"), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    # Step 5: Render
    log("[5] HyperFrames render...")
    out = os.path.join(run_dir, "output.mp4")
    with open(os.path.join(run_dir, "render.log"), "w") as lf:
        r = subprocess.run([HYPERFRAMES, "render", "--quality", "high", "-o", out, run_dir],
                           stdout=lf, stderr=subprocess.STDOUT)
    if r.returncode != 0 or not os.path.exists(out):
        log("  FAIL - see render.log")
    else:
        log("  ✓ %.1fs" % get_audio_duration(out))

    log("RESULT " + json.dumps({"run_dir": run_dir, "output": out, "duration": round(total, 2)}, ensure_ascii=False))

if __name__ == "__main__":
    main()
