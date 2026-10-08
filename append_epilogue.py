#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
片尾追加器 · 抖音新闻卡片御姐音成片通用模板
================================================================
给任意已完成的 news-card 成片（run_dir 内含 douyin.mp4 / narration.wav /
index.html / script.json）追加一段标准片尾：
    口播（G 版慵懒御姐音）+ 卡片 + 字幕 + BGM 铺底 + 右下角水印

设计原则
--------
1. 原片零改动：不重渲染整条，只新增片尾段，再 concat + 换音轨
2. 模板化：片尾文案 / 卡片 / 字幕样式全部由 script.json 的 "epilogue" 配置驱动
3. G 版节奏：句内 >-52dB 长静音截到 0.30s，句首/句尾留白 0.12s
4. 字幕与配音严格同起止：字幕窗 = 语音边界 start-0.05s ~ end+0.15s

用法
----
  python3 append_epilogue.py <run_dir> [--out douyin_epilogue.mp4] [--force]

  <run_dir>  成片目录（如 /Volumes/PSSD/抖音视频/output/xxx_123456）
  --out      输出文件名（默认 douyin_epilogue.mp4，绝不覆盖原片）
  --force    已存在时覆盖同名输出

script.json 中的配置项（缺省时使用 DEFAULT_EPILOGUE）
----------------------------------------------------
  "epilogue": {
    "enabled": true,
    "text": "关注 jerrychen2001，评论区聊聊你还想拆哪个项目。",
    "emotion": "thoughtful",
    "gap_before": 0.40,
    "tail_silence": 0.50,
    "lead_silence": 0.12,
    "inner_cap": 0.30,
    "card": { "title": "...", "cta": "...", "sub": "..." }
  }
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import wave

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
TEMPLATE_PATH = os.path.join(HERE, "epilogue_template.json")
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "scripts"))

# 跨平台工具解析（真源 scripts/platform_env.py）：
#   · 一律走 PATH/which 查找（Windows 自动补 .exe/.cmd），不再写死 /opt/homebrew/bin；
#   · 支持环境变量覆盖：PIPELINE_FFMPEG / PIPELINE_FFPROBE / PIPELINE_HYPERFRAMES；
#   · 兼容旧行为：homebrew 前缀（macOS 上存在时）作为候选之一参与探测。
import platform_env  # noqa: E402
import tts_provider  # noqa: E402

platform_env.ensure_brew_path()
FFMPEG = platform_env.find_tool("ffmpeg")
FFPROBE = platform_env.find_tool("ffprobe")
HYPERFRAMES = platform_env.find_tool("hyperframes")


def require_tools() -> None:
    """入口处一次性校验外部工具（缺失给出各平台安装提示，而不是 None 崩栈）。"""
    missing = [n for n, p in (("ffmpeg", FFMPEG), ("ffprobe", FFPROBE),
                              ("hyperframes", HYPERFRAMES)) if not p]
    if not missing:
        return
    lines = []
    for n in missing:
        try:
            platform_env.find_tool(n)
            lines.append(f"找不到可执行文件 {n}（用途：片尾追加）")
        except platform_env.ToolNotFound as exc:
            lines.append(str(exc))
    raise SystemExit("\n".join(lines))

# ── 片尾默认模板（后续所有成片默认追加这一段）────────────────
DEFAULT_EPILOGUE = {
    "enabled": True,
    "text": "关注 jerrychen2001，评论区聊聊你还想拆哪个项目。",
    "emotion": "thoughtful",
    "gap_before": 0.40,      # 上一句结束 → 片尾口播开始 的过渡静音
    "tail_silence": 0.50,    # 片尾口播结束后的停留
    "lead_silence": 0.12,    # G 版：句首留白
    "inner_cap": 0.30,       # G 版：句内长静音上限
    "card": {
        "title": "关注 jerrychen2001",
        "cta": "评论区聊聊",
        "sub": "你还想拆哪个项目？",
    },
    "bgm_volume": 0.18,
}

# 原片（post_process 抖音规格）编码基线，片尾段必须对齐才能 concat -c copy。
# 码率控制与 post_process 同源（真源 1.3.0）：capped-CRF(-crf 18, -maxrate/-bufsize 仅作瞬时上限)；
# 8M 已降级为历史目标参考，不再输出 -b:v 目标（S3 材料 C5「8M 目标无人锁死」已解除）。
CODEC_V = ["-c:v", "libx264", "-preset", "medium", "-profile:v", "high",
           "-level", "4.2", "-pix_fmt", "yuv420p", "-r", "30", "-g", "60",
           "-crf", "18", "-maxrate", "10M", "-bufsize", "12M"]
CODEC_A = ["-c:a", "aac", "-b:a", "128k", "-ar", "44100", "-ac", "2"]

_ENC_MOD = None  # scripts/encode_profile.py（真源读取器）；不可用为 False


def video_codec_args():
    """片尾段视频编码串：优先真源 scripts/encode_profile.py::video_args，
    读不到则回落内置 CODEC_V（值与真源同），并显式告警。"""
    global _ENC_MOD
    if _ENC_MOD is None:
        try:
            root = os.path.dirname(os.path.abspath(__file__))
            sdir = os.path.join(root, "scripts")
            if sdir not in sys.path:
                sys.path.insert(0, sdir)
            import encode_profile
            _ENC_MOD = encode_profile
        except Exception as exc:  # noqa: BLE001
            log("  WARN: 片尾编码真源读取器不可用（%s）→ 回落内置 CODEC_V"
                % type(exc).__name__)
            _ENC_MOD = False
    if _ENC_MOD:
        try:
            root = os.path.dirname(os.path.abspath(__file__))
            return _ENC_MOD.video_args(_ENC_MOD.profile(root))
        except Exception as exc:  # noqa: BLE001
            log("  WARN: 片尾编码参数取真源失败（%s）→ 回落内置 CODEC_V"
                % type(exc).__name__)
    return CODEC_V


def log(*a):
    print(*a, flush=True)


def run(cmd, quiet=True):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        log("  ERROR:", " ".join(str(c) for c in cmd[:8]), "...")
        log("  ", (r.stderr or "")[-800:])
        raise SystemExit(1)
    return r


def dur_of(path):
    r = subprocess.run([FFPROBE, "-v", "quiet", "-show_entries", "format=duration",
                        "-of", "default=noprint_wrappers=1:nokey=1", path],
                       capture_output=True, text=True)
    return float(r.stdout.strip())


def probe_video(path):
    r = subprocess.run([FFPROBE, "-v", "error", "-select_streams", "v:0",
                        "-show_entries", "stream=width,height,r_frame_rate",
                        "-show_entries", "format=duration", "-of", "json", path],
                       capture_output=True, text=True)
    j = json.loads(r.stdout)
    st = j["streams"][0]
    return {"w": st["width"], "h": st["height"],
            "fps": st.get("r_frame_rate", "30/1"),
            "duration": float(j["format"]["duration"])}


# ── G 版口播重排 ─────────────────────────────────────────────
def reshape_g(src, dst, lead_s=0.12, cap_s=0.30, thr_db=-52.0):
    """句内 >thr_db 长静音截到 cap_s，句首/句尾各补 lead_s 留白。返回实测语音边界。"""
    with wave.open(src, "rb") as w:
        sr, ch, sw = w.getframerate(), w.getnchannels(), w.getsampwidth()
        raw = w.readframes(w.getnframes())
    x = np.frombuffer(raw, dtype=np.int16).astype(np.float32)
    if ch > 1:
        x = x.reshape(-1, ch).mean(axis=1)

    thr = 10 ** (thr_db / 20.0)
    fl, hop = max(1, int(sr * 0.02)), max(1, int(sr * 0.01))
    nfr = max(0, (len(x) - fl) // hop + 1)
    rms = np.array([np.sqrt(np.mean(x[i * hop:i * hop + fl] ** 2) + 1e-12) for i in range(nfr)])
    sil = rms < thr

    segs, i = [], 0
    while i < nfr:
        if not sil[i]:
            j = i
            while j + 1 < nfr and not sil[j + 1]:
                j += 1
            segs.append((i, j))
            i = j + 1
        else:
            i += 1
    if not segs:
        raise SystemExit("片尾口播未检测到有效语音")

    s0 = segs[0][0] * hop
    s1 = min(len(x), segs[-1][1] * hop + fl)
    x = x[s0:s1]

    out, prev_end = [], None
    for (a, b) in segs:
        a_s = max(0, a * hop - s0)
        b_s = min(len(x), b * hop + fl - s0)
        if prev_end is None:
            out.append(x[:b_s])
        else:
            gap = (a_s - prev_end) / sr
            out.append(np.zeros(int(min(gap, cap_s) * sr), dtype=np.float32))
            out.append(x[a_s:b_s])
        prev_end = b_s
    y = np.concatenate(out)
    y = np.concatenate([np.zeros(int(lead_s * sr), dtype=np.float32), y,
                        np.zeros(int(lead_s * sr), dtype=np.float32)])
    y = np.clip(y, -32768, 32767).astype(np.int16)
    with wave.open(dst, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(y.tobytes())

    # 实测语音边界（-45dB），用于字幕窗口
    yf = y.astype(np.float32)
    thr2 = 10 ** (-45.0 / 20.0)
    n2 = max(0, (len(yf) - fl) // hop + 1)
    r2 = np.array([np.sqrt(np.mean(yf[i * hop:i * hop + fl] ** 2) + 1e-12) for i in range(n2)])
    nz = np.where(r2 > thr2)[0]
    v_start = nz[0] * hop / sr if len(nz) else lead_s
    v_end = min(len(yf), nz[-1] * hop + fl) / sr if len(nz) else len(yf) / sr
    return {"sr": sr, "dur": len(y) / sr,
            "voice_start": float(v_start), "voice_end": float(v_end)}


# ── 片尾段 HTML（严格复用原片 CSS）────────────────────────────
def extract_style(index_html):
    m = re.search(r"<style>(.*?)</style>", index_html, re.S)
    if not m:
        raise SystemExit("原 index.html 中未找到 <style> 块")
    return m.group(1)


def extract_meta(index_html):
    brand = re.search(r'<span class="brand">(.*?)</span>', index_html, re.S)
    date = re.search(r'<span class="date">(.*?)</span>', index_html, re.S)
    wm = re.search(r'<div id="wm"[^>]*>(.*?)</div>', index_html, re.S)
    return {"brand": brand.group(1).strip() if brand else "",
            "date": date.group(1).strip() if date else "",
            "watermark": wm.group(1).strip() if wm else ""}


def build_epilogue_html(css, meta, card, text, total, card_start, sub_start, sub_dur):
    esc = lambda s: (str(s).replace("&", "&amp;").replace("<", "&lt;")
                     .replace(">", "&gt;").replace('"', "&quot;"))
    html = f'''<!doctype html>
<html lang="zh-CN">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=1080, height=1920" />
    <script src="https://cdn.jsdelivr.net/npm/gsap@3.14.2/dist/gsap.min.js"></script>
    <style>{css}</style>
  </head>
  <body>
    <div id="root" data-composition-id="main" data-start="0" data-duration="{total:.2f}" data-width="1080" data-height="1920">
      <div id="progress" class="progress clip" data-start="0" data-duration="{total:.2f}" data-track-index="100" style="width:100%"></div>
      <div id="topbar" class="topbar clip" data-start="0" data-duration="{total:.2f}" data-track-index="1">
        <span class="brand">{esc(meta["brand"])}</span>
        <span class="date">{esc(meta["date"])}</span>
      </div>
      <div id="wm" class="wm clip" data-start="0" data-duration="{total:.2f}" data-track-index="2">{esc(meta["watermark"])}</div>
      <div id="scene-ep" class="scene clip" data-start="0" data-duration="{total:.2f}" data-track-index="3">
          <div class="card ocard">
            <div class="otitle anim">{esc(card["title"])}</div>
            <div class="octa anim">{esc(card["cta"])}</div>
            <div class="osub anim">{esc(card["sub"])}</div>
          </div>
      </div>
      <div id="sub-ep" class="subtitle clip" data-start="{sub_start:.2f}" data-duration="{sub_dur:.2f}" data-track-index="10">
        <div class="sub-inner">{esc(text)}</div>
      </div>
    </div>
    <script>
      window.__timelines = window.__timelines || {{}};
      const tl = gsap.timeline({{ paused: true }});
      tl.from("#scene-ep .card", {{ y: 44, opacity: 0, duration: 0.5, ease: "power3.out" }}, {card_start:.2f});
      tl.from("#scene-ep .anim", {{ y: 26, opacity: 0, duration: 0.45, stagger: 0.09, ease: "power2.out" }}, {card_start + 0.18:.2f});
      tl.from("#sub-ep .sub-inner", {{ y: 26, opacity: 0, duration: 0.25, ease: "power2.out" }}, {sub_start:.2f});
      tl.to("#sub-ep .sub-inner", {{ opacity: 0, duration: 0.18, ease: "power2.in" }}, {sub_start + sub_dur - 0.18:.2f});
      window.__timelines["main"] = tl;
    </script>
  </body>
</html>'''
    return html


def main():
    require_tools()
    ap = argparse.ArgumentParser()
    ap.add_argument("run_dir")
    ap.add_argument("--out", default="douyin_epilogue.mp4")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    run_dir = os.path.abspath(args.run_dir)
    src_mp4 = os.path.join(run_dir, "douyin.mp4")
    index_html_path = os.path.join(run_dir, "index.html")
    script_json_path = os.path.join(run_dir, "script.json")
    for p in (src_mp4, index_html_path):
        if not os.path.exists(p):
            raise SystemExit("缺少必需文件: " + p)

    script = {}
    if os.path.exists(script_json_path):
        with open(script_json_path, encoding="utf-8") as f:
            script = json.load(f)
    # 配置优先级：内置默认 → 工作流模板文件 → 本片 script.json
    cfg = dict(DEFAULT_EPILOGUE)
    if os.path.exists(TEMPLATE_PATH):
        try:
            with open(TEMPLATE_PATH, encoding="utf-8") as f:
                cfg.update(json.load(f).get("epilogue", {}) or {})
            log("  模板: " + TEMPLATE_PATH)
        except Exception as e:
            log("  模板读取失败，改用内置默认: %s" % e)
    cfg.update(script.get("epilogue", {}) or {})
    if not cfg.get("enabled", True):
        log("script.json 中 epilogue.enabled = false，跳过")
        return

    out_mp4 = os.path.join(run_dir, args.out)
    if os.path.exists(out_mp4) and not args.force:
        raise SystemExit(f"输出已存在（如需覆盖请加 --force）: {out_mp4}")

    work = os.path.join(run_dir, "epilogue")
    os.makedirs(work, exist_ok=True)

    vinfo = probe_video(src_mp4)
    vdur = vinfo["duration"]
    log(f"=== 片尾追加 ===")
    log(f"  原片: {src_mp4}")
    log(f"  参数: {vinfo['w']}x{vinfo['h']} @{vinfo['fps']} / {vdur:.2f}s")

    # 1) TTS 片尾口播
    raw_wav = os.path.join(work, "epilogue.raw.wav")
    meta_path = os.path.join(work, "epilogue.meta.json")
    want = {"text": cfg["text"], "emotion": cfg["emotion"]}
    cached = {}
    if os.path.exists(meta_path):
        try:
            with open(meta_path, encoding="utf-8") as f:
                cached = json.load(f) or {}
        except Exception:
            cached = {}
    # 缓存键 = 文案 + 音色：任一变化即失效重生成（历史坑：仅按文件是否存在判断，
    # 改 emotion 后仍复用旧音色素材，导致片尾音色与全片不统一）
    stale = (cached.get("text") != want["text"]) or (cached.get("emotion") != want["emotion"])
    if os.path.exists(raw_wav) and stale:
        old = raw_wav + ".stale-%s" % (cached.get("emotion") or "unknown")
        os.replace(raw_wav, old)
        log("\n[1/6] 片尾口播缓存失效（%s → %s），重新生成；旧素材另存 %s"
            % (cached.get("emotion"), want["emotion"], os.path.basename(old)))
    if not os.path.exists(raw_wav):
        log("\n[1/6] 生成片尾口播（御姐音 · %s）..." % cfg["emotion"])
        # TTS 走可插拔 provider 抽象（真源 config/tts.json）：
        #   默认 provider=mlx 时与旧链路逐参数一致（本地 Qwen3-TTS 御姐音）；
        #   切到 openai 等云端 provider 即可在非 Apple Silicon 平台出片。
        #   未配置/依赖缺失一律明确报错，不静默降级。
        try:
            tts_provider.synthesize(cfg["text"], raw_wav, role="epilogue",
                                    emotion=cfg["emotion"], work_dir=work)
        except tts_provider.TtsConfigError as exc:
            raise SystemExit("片尾口播 TTS 配置/依赖错误：%s" % exc)
        if not os.path.exists(raw_wav):
            raise SystemExit("片尾口播生成失败")
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(want, f, ensure_ascii=False, indent=2)
        log("  ok")
    else:
        log("\n[1/6] 复用已有片尾口播素材（音色 %s，缓存键匹配）" % want["emotion"])

    # 2) G 版重排
    log("\n[2/6] G 版节奏重排（句内静音 ≤%.2fs / 句首尾留白 %.2fs）..." % (cfg["inner_cap"], cfg["lead_silence"]))
    epi24 = os.path.join(work, "epilogue.24k.wav")
    run([FFMPEG, "-y", "-v", "error", "-i", raw_wav, "-ar", "24000", "-ac", "1", epi24])
    epi_wav = os.path.join(work, "epilogue.wav")
    info = reshape_g(epi24, epi_wav, lead_s=cfg["lead_silence"], cap_s=cfg["inner_cap"])
    epi_dur = info["dur"]
    log("  %.3fs（语音 %.3f~%.3f）" % (epi_dur, info["voice_start"], info["voice_end"]))

    gap = float(cfg["gap_before"])
    tail = float(cfg["tail_silence"])
    seg_dur = round(gap + epi_dur + tail, 3)      # 片尾段时长
    total = round(vdur + seg_dur, 3)              # 新成片总时长

    # 3) 重建整条音轨（原人声 + 过渡 + 片尾 + 停留，再混 BGM）
    log("\n[3/6] 重建音轨（原人声 + 片尾 + BGM %.0f%%）..." % (cfg["bgm_volume"] * 100))
    narration = os.path.join(run_dir, "narration.wav")
    if not os.path.exists(narration):
        raise SystemExit("缺少 narration.wav，无法重建音轨")
    voice = os.path.join(work, "voice_full.wav")
    run([FFMPEG, "-y", "-v", "error", "-i", narration,
         "-i", epi_wav,
         "-filter_complex",
         f"[0:a]atrim=0:{vdur:.3f},asetpts=PTS-STARTPTS,apad=whole_dur={total:.3f}[n];"
         f"[1:a]adelay={int((vdur + gap) * 1000)}:all=1,apad=whole_dur={total:.3f}[e];"
         f"[n][e]amix=inputs=2:duration=longest:normalize=0,atrim=0:{total:.3f},"
         f"asetpts=PTS-STARTPTS,apad=whole_dur={total:.3f}[v]",
         "-map", "[v]", "-ar", "24000", "-ac", "1", "-c:a", "pcm_s16le", voice])

    combined = os.path.join(work, "audio_combined_new.wav")
    bgm = script.get("bgm", "")
    if bgm and os.path.exists(bgm):
        res = subprocess.run([FFMPEG, "-y", "-v", "error", "-i", voice, "-stream_loop", "-1", "-i", bgm,
                              "-filter_complex",
                              f"[1:a]volume={cfg['bgm_volume']:.3f},atrim=0:{total:.3f},asetpts=PTS-STARTPTS[b];"
                              f"[0:a][b]amix=inputs=2:duration=first:normalize=0[m]",
                              "-map", "[m]", "-t", f"{total:.3f}", "-ar", "24000", "-ac", "1",
                              "-c:a", "pcm_s16le", combined], capture_output=True, text=True)
        if res.returncode != 0:
            log("  BGM 混音失败，退化为纯人声")
            shutil.copy(voice, combined)
    else:
        log("  BGM 缺失，仅人声")
        shutil.copy(voice, combined)

    # 4) 渲染片尾段
    log("\n[4/6] 渲染片尾段（卡片 + 字幕）...")
    css = extract_style(open(index_html_path, encoding="utf-8").read())
    meta = extract_meta(open(index_html_path, encoding="utf-8").read())
    card_start = gap
    sub_start = max(0.0, gap + info["voice_start"] - 0.05)
    sub_end = min(seg_dur, gap + info["voice_end"] + 0.15)
    html = build_epilogue_html(css, meta, cfg["card"], cfg["text"], seg_dur, card_start,
                               sub_start, sub_end - sub_start)
    with open(os.path.join(work, "index.html"), "w", encoding="utf-8") as f:
        f.write(html)
    with open(os.path.join(work, "hyperframes.json"), "w") as f:
        json.dump({"$schema": "https://hyperframes.heygen.com/schema/hyperframes.json",
                   "registry": "https://raw.githubusercontent.com/heygen-com/hyperframes/main/registry",
                   "paths": {"blocks": "compositions", "components": "compositions/components",
                             "assets": "assets"},
                   "media": {"autoProxy": True}}, f, indent=2)
    seg_raw = os.path.join(work, "_seg_raw.mp4")
    with open(os.path.join(work, "render.log"), "w") as lf:
        r = subprocess.run([HYPERFRAMES, "render", "--quality", "high", "-o", seg_raw, work],
                           stdout=lf, stderr=subprocess.STDOUT)
    if r.returncode != 0 or not os.path.exists(seg_raw):
        raise SystemExit("片尾段渲染失败，见 " + os.path.join(work, "render.log"))
    log("  段渲染 %.2fs" % dur_of(seg_raw))

    # 5) 对齐原片编码
    log("\n[5/6] 片尾段重编码对齐原片参数...")
    seg = os.path.join(work, "_seg.mp4")
    run([FFMPEG, "-y", "-v", "error", "-i", seg_raw, "-vf",
         f"scale={vinfo['w']}:{vinfo['h']}:force_original_aspect_ratio=decrease,"
         f"pad={vinfo['w']}:{vinfo['h']}:(ow-iw)/2:(oh-ih)/2:color=#0a0a12",
         *video_codec_args(), "-t", f"{seg_dur:.3f}", "-an", seg])

    # 6) concat 视频流 + 换音轨
    log("\n[6/6] 拼接并换音轨...")
    concat_txt = os.path.join(work, "_concat.txt")
    with open(concat_txt, "w") as f:
        f.write(f"file '{src_mp4}'\nfile '{seg}'\n")
    vtmp = os.path.join(work, "_video_only.mp4")
    run([FFMPEG, "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", concat_txt,
         "-an", "-c:v", "copy", vtmp])
    # mono->stereo 必须显式复制声道（SWR 默认上混会带来 -3dB 衰减）
    run([FFMPEG, "-y", "-v", "error", "-i", vtmp, "-i", combined,
         "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy",
         "-af", "pan=stereo|c0=c0|c1=c0", *CODEC_A,
         "-t", f"{total:.3f}", "-movflags", "+faststart", out_mp4])

    size_mb = os.path.getsize(out_mp4) / 1024 / 1024
    odur = dur_of(out_mp4)
    log("\n完成: " + out_mp4)
    log("  时长 %.2fs / 体积 %.1fMB" % (odur, size_mb))
    log("RESULT " + json.dumps({
        "run_dir": run_dir, "output": out_mp4,
        "duration": round(odur, 2), "size_mb": round(size_mb, 2),
        "epilogue_duration": round(epi_dur, 3), "seg_duration": seg_dur,
        "gap_before": gap, "tail_silence": tail,
        "voice_start": round(info["voice_start"], 3), "voice_end": round(info["voice_end"], 3),
        "card_start": round(card_start, 2), "sub_start": round(sub_start, 2),
        "sub_end": round(sub_end, 2)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
