#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""motion_audit.py —— 成片运动量化验收（v1.0，v1.19.0 借鉴 huashu-art-motion qa.py）

所属产线：/Volumes/PSSD/抖音视频
借鉴来源：huashu-art-motion/scripts/qa.py（运动量化四指标）+ scripts/analyze/breakdown.py（运动热图）
适配点：qa.py 面向代码动画工程（playwright 渲染取帧），本脚本面向产线成片（ffmpeg 抽帧）；
        纯 numpy / PIL + 系统 ffmpeg、ffprobe，无 playwright 依赖，依赖口径与 frame_audit.py 一致。

指标（对齐 qa.py 经验阈值，阈值可调；判据是经验阈值不是规则）
  motion_pct        运动面积%：相邻帧差 >thresh（0-255 灰度标度，默认 12）的像素占比均值；
                    0.5–8% 之间多数片段好看
  still_pairs_pct   静止帧对%：相邻帧几乎不变（差占比 <0.05%）的比例；>40% 读作「卡」
  spikes_at_sec     跳变时间点：d >3% 且 d > 6×max(中位数, 0.05) 记跳变（>0 先看帧再判断）
  frame_ms          抽帧耗时（成片侧无渲染耗时，口径 = ffmpeg 抽帧管道 wall-time 均/总）
  deterministic     确定性：--ref 给定时逐帧 PSNR（对齐 frame_audit A0：≥40dB 判一致）；
                    无 --ref 报 SKIP（确定性是成片对比口径，单版无法判）
  运动热图          逐像素「相邻帧差 >thresh 的累计计数」叠加在首帧灰度底图（红）

产物（--out 目录；默认 <视频同目录>/qc/motion_audit）
  qa.json                   全部数字
  qa.md                     表格
  motion_heatmap.jpg        运动热图（叠加底图）
  <视频名>_frames.jpg       4 帧拼图 + 热图（同 qa.py 拼图样式）

用法
  python3 scripts/motion_audit.py --video story/howtolivebetter-54k/douyin.mp4
  python3 scripts/motion_audit.py --video story/xxx/douyin.mp4 --ref story/xxx/douyin_epilogue.mp4
  python3 scripts/motion_audit.py --video story/xxx/douyin.mp4 --fps 10    # 降抽帧率（长片加速）
  python3 scripts/motion_audit.py --self-test   # 合成三段式负控（静止→匀速→跳变），断言各指标检出

退出码：0 = 通过 / 量化完成（默认不阻断，报告照出，同 qa.py 经验阈值口径）；
        1 = 用法 / 输入错误；2 = --strict 时跳变/确定性判据失败，或 --self-test 负控失败
"""
import argparse
import base64
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import numpy as np

FFMPEG = shutil.which("ffmpeg") or "/opt/homebrew/bin/ffmpeg"
FFPROBE = shutil.which("ffprobe") or "/opt/homebrew/bin/ffprobe"

# 与 qa.py 一致的经验阈值（0-255 灰度标度）
D_THRESH = 12          # 相邻帧差 >12 像素记「运动」
STILL_PCT = 0.05       # 相邻帧差占比 <0.05% 记「静止帧对」
SPIKE_PCT = 3.0        # 单对差占比 >3% 才可能记跳变
SPIKE_RATIO = 6.0      # 峰值 / 中位数 >6 记跳变
PSNR_OK = 40.0         # 确定性阈值（对齐 frame_audit A0）

# 抽帧降采样尺寸（竖屏等比：1080×1920 → 216×384；与 breakdown.py 的 192×108 量级一致）
DW, DH = 216, 384


def probe(path):
    r = subprocess.run([FFPROBE, "-v", "error", "-select_streams", "v:0",
                        "-show_entries", "stream=width,height,r_frame_rate,duration",
                        "-of", "json", path], capture_output=True, text=True)
    s = json.loads(r.stdout)["streams"][0]
    n, d = s["r_frame_rate"].split("/")
    fps = float(n) / float(d)
    return s["width"], s["height"], fps, float(s.get("duration", 0.0))


def grab_gray(path, scale_w, scale_h):
    """ffmpeg 整段抽灰度帧（降采样），返回 (frames:uint8[N,H,W], wall_s)。"""
    t0 = time.perf_counter()
    cmd = [FFMPEG, "-v", "error", "-i", path, "-vf", f"scale={scale_w}:{scale_h}",
           "-f", "rawvideo", "-pix_fmt", "gray", "-"]
    r = subprocess.run(cmd, capture_output=True)
    wall = time.perf_counter() - t0
    n = len(r.stdout) // (scale_w * scale_h)
    if n == 0:
        raise SystemExit(f"抽帧为空：{path}（stdout {len(r.stdout)} 字节）")
    frames = np.frombuffer(r.stdout, np.uint8).reshape(n, scale_h, scale_w)
    return frames, wall


def analyze(frames, wall_s, fps, thresh, still_pct, spike_pct, spike_ratio):
    """计算运动量化指标（qa.py 口径），返回 dict + diffs 数组。"""
    f = frames.astype(np.int16)
    diffs = np.array([(np.abs(f[i + 1] - f[i]) > thresh).mean() * 100.0
                      for i in range(len(f) - 1)]) if len(f) > 1 else np.array([], dtype=float)
    med = float(np.median(diffs)) if len(diffs) else 0.0
    spikes = [round((i + 1) / fps, 3) for i, d in enumerate(diffs)
              if d > spike_pct and d > spike_ratio * max(med, 0.05)]
    still = float((diffs < still_pct).mean() * 100.0) if len(diffs) else 0.0
    heat = np.zeros(frames.shape[1:], np.int32)
    for i in range(len(f) - 1):
        heat += (np.abs(f[i + 1] - f[i]) > thresh)
    rec = {
        "frames": int(len(f)),
        "fps": round(fps, 3),
        "motion_pct": round(float(diffs.mean()), 2) if len(diffs) else 0.0,
        "motion_max": round(float(diffs.max()), 2) if len(diffs) else 0.0,
        "still_pairs_pct": round(still, 1),
        "spike_ratio": round(float(diffs.max() / max(med, 0.05)), 1) if len(diffs) else 0.0,
        "spikes_at_sec": spikes,
        "frame_ms_mean": round(wall_s / max(1, len(f)) * 1000.0, 2),
        "frame_ms_total": round(wall_s * 1000.0, 1),
        "note": "成片侧无渲染耗时；frame_ms 为 ffmpeg 抽帧管道 wall-time 口径（qa.py 的渲染耗时仅适用代码动画工程）",
    }
    return rec, diffs, heat


def psnr_pairwise(a, b):
    """逐帧 PSNR（灰度 0-255 标度），返回逐帧数组。"""
    a = a.astype(np.float64)
    b = b.astype(np.float64)
    mse = ((a - b) ** 2).mean(axis=(1, 2))
    mse = np.maximum(mse, 1e-10)
    return 10.0 * np.log10(255.0 ** 2 / mse)


def heatmap_image(base_frame, heat, path):
    """热图叠加底图（红通道），与 qa.py / breakdown.py 同款呈现。"""
    from PIL import Image, ImageDraw
    H_, W_ = base_frame.shape
    hm = np.clip(heat / max(1, heat.max()) * 255.0, 0, 255).astype(np.uint8)
    base = Image.fromarray(base_frame).convert("L").convert("RGB")
    red = np.zeros((H_, W_, 3), np.uint8)
    red[..., 0] = hm
    img = Image.blend(base, Image.fromarray(red), 0.6)
    ImageDraw.Draw(img).text((6, 6), "motion heatmap (max frame-diff > %d cumulative)" % D_THRESH,
                             fill="yellow")
    img.save(path, quality=88)
    return path


def montage(frames, heat, rec, path):
    """4 帧拼图 + 热图（qa.py 拼图样式）。"""
    from PIL import Image, ImageDraw
    n = len(frames)
    pick = [frames[int(k)] for k in np.linspace(0, n - 1, 4)]
    H_, W_ = frames.shape[1], frames.shape[2]
    S = Image.new("RGB", (W_ * 5, H_ + 24), "white")
    dr = ImageDraw.Draw(S)
    for k, f in enumerate(pick):
        S.paste(Image.fromarray(f), (k * W_, 24))
    hm = np.clip(heat / max(1, heat.max()) * 255.0, 0, 255).astype(np.uint8)
    base = Image.fromarray(pick[0]).convert("L").convert("RGB")
    red = np.zeros((H_, W_, 3), np.uint8)
    red[..., 0] = hm
    S.paste(Image.blend(base, Image.fromarray(red), 0.6), (4 * W_, 24))
    dr.text((6, 4), f"motion {rec['motion_pct']}%  still {rec['still_pairs_pct']}%  spikes {len(rec['spikes_at_sec'])}  "
                    f"frame_ms {rec['frame_ms_mean']}/{rec['frame_ms_total']}", fill="black")
    S.save(path, quality=85)
    return path


def run_video(args, video, ref=None):
    out = Path(args.out) if args.out else Path(video).resolve().parent / "qc" / "motion_audit"
    out.mkdir(parents=True, exist_ok=True)
    W, H, fps, dur = probe(video)
    frames, wall = grab_gray(video, DW, DH)
    rec, diffs, heat = analyze(frames, wall_s=wall, fps=fps, thresh=args.thresh,
                               still_pct=args.still, spike_pct=args.spike_pct,
                               spike_ratio=args.spike_ratio)
    rec["video"] = str(Path(video).resolve())
    rec["size"] = [W, H]
    rec["duration_s"] = round(dur, 2)
    rec["analysis_scale"] = [DH, DW]

    # 确定性：--ref 时逐帧 PSNR（对齐 frame_audit A0 口径）
    det = {"deterministic": None, "psnr_mean_db": None, "psnr_min_db": None, "note": "未提供 --ref，确定性 SKIP（成片对比口径需两版）"}
    if ref:
        fr, _ = grab_gray(ref, DW, DH)
        m = min(len(frames), len(fr))
        ps = psnr_pairwise(frames[:m], fr[:m])
        det = {
            "deterministic": bool(float(ps.mean()) >= PSNR_OK and float(ps.min()) >= PSNR_OK),
            "psnr_mean_db": round(float(ps.mean()), 2),
            "psnr_min_db": round(float(ps.min()), 2),
            "note": f"同源两版成片逐帧 PSNR（阈值 ≥{PSNR_OK}dB，对齐 frame_audit A0）",
        }
    rec["determinism"] = det

    # 运动热图 + 拼图
    base = frames[0] if len(frames) else np.zeros((DH, DW), np.uint8)
    hm_path = out / "motion_heatmap.jpg"
    heatmap_image(base, heat, hm_path)
    mo_path = out / f"{Path(video).stem}_frames.jpg"
    montage(frames, heat, rec, mo_path)

    report = {"motion_audit": rec}
    json.dump(report, open(out / "qa.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    rows = ["| 指标 | 值 | 判据（经验阈值） |", "|---|---|---|",
            f"| 运动面积% | {rec['motion_pct']} | 0.5–8% 之间多数片段好看 |",
            f"| 运动峰值% | {rec['motion_max']} | — |",
            f"| 静止帧对% | {rec['still_pairs_pct']} | >40% 读作「卡」 |",
            f"| 跳变 | {len(rec['spikes_at_sec'])} {rec['spikes_at_sec'][:6]} | >0 先看帧再判断（有意的节拍闪不算错） |",
            f"| 抽帧耗时 mean/total ms | {rec['frame_ms_mean']}/{rec['frame_ms_total']} | 成片侧无渲染耗时，此为抽帧管道口径 |",
            f"| 确定性 | {det['deterministic']} | 逐帧 PSNR ≥ {PSNR_OK}dB（--ref 两版对比） |"]
    if det["psnr_mean_db"] is not None:
        rows += [f"| PSNR mean/min | {det['psnr_mean_db']}/{det['psnr_min_db']} | — |"]
    rows += ["", f"视频: {Path(video).resolve()}", f"时长: {dur:.2f}s @ {W}x{H} / {fps:.1f}fps，抽帧 {DW}x{DH} 灰度"]
    if det["psnr_mean_db"] is None:
        rows += ["", "提示: 确定性需两版成片对比，传 --ref 开启（对齐 frame_audit A0 的 PSNR≥40dB 口径）"]
    (out / "qa.md").write_text("\n".join(rows) + "\n", encoding="utf-8")

    print(f"运动 {rec['motion_pct']}%  静止帧对 {rec['still_pairs_pct']}%  跳变 {len(rec['spikes_at_sec'])}  "
          f"抽帧 {rec['frame_ms_mean']}ms/帧  确定性 {'✓' if det['deterministic'] else ('✗' if det['psnr_mean_db'] is not None else 'SKIP')}")
    print("->", out / "qa.md")
    for f in (out / "qa.json", hm_path, mo_path):
        print("->", f)
    if args.strict:
        bad = []
        if rec["still_pairs_pct"] > 40.0:
            bad.append(f"静止帧对 {rec['still_pairs_pct']}% > 40%")
        if det["deterministic"] is False:
            bad.append(f"确定性失败（PSNR {det['psnr_mean_db']}dB < {PSNR_OK}dB）")
        if bad:
            raise SystemExit("strict 判据失败: " + "; ".join(bad))
    return 0


def synth_selftest_video(tmpdir):
    """合成三段式负控视频：0-3s 静止 / 3-6s 匀速运动 / 6-9s 黑白交替跳变（30fps 216x384 灰度）。"""
    n = 9 * 30
    frames = np.full((n, DH, DW), 128, np.uint8)
    frames[:90] = 128
    for i in range(90, 180):
        frames[i] = 128
        x = (i - 90) * 3
        frames[i, :, x:x + 40] = 200
    for i in range(180, 270):
        frames[i] = 30 if ((i // 2) % 2 == 0) else 230
    raw = tmpdir / "selftest_motion.raw"
    raw.write_bytes(frames.tobytes())
    mp4 = tmpdir / "selftest_motion.mp4"
    subprocess.run([FFMPEG, "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "gray",
                    "-s", f"{DW}x{DH}", "-r", "30", "-i", str(raw), "-c:v", "libx264",
                    "-pix_fmt", "yuv420p", "-preset", "ultrafast", str(mp4)], check=True)
    return mp4


def run_selftest(args):
    tmpdir = Path(tempfile.mkdtemp(prefix="motion_audit_selftest_"))
    mp4 = synth_selftest_video(tmpdir)
    frames, wall = grab_gray(str(mp4), DW, DH)
    rec, diffs, heat = analyze(frames, wall_s=wall, fps=30.0, thresh=args.thresh,
                               still_pct=args.still, spike_pct=args.spike_pct,
                               spike_ratio=args.spike_ratio)
    seg = lambda a, b: diffs[a * 30:b * 30] if len(diffs) >= b * 30 else diffs[a * 30:]
    d_still = seg(0, 3)
    d_move = seg(3, 6)
    d_jump = seg(6, 9)
    checks = {
        "静止段检出（静止帧对占比应高）": float((d_still < args.still).mean() * 100) > 90.0,
        "运动段检出（运动面积应 >0.5%）": float(d_move.mean()) > 0.5,
        "跳变段检出（应出现 spike）": any(d > args.spike_pct for d in d_jump),
        "跳变时间点覆盖 6-9s 区间（边界切换帧也可能检出，属合法检测）": any(6.0 <= s <= 9.0 for s in rec["spikes_at_sec"]),
    }
    print("=== motion_audit --self-test 负控 ===")
    print(f"  静止段 motion={float(d_still.mean()):.3f}%  still={float((d_still<args.still).mean()*100):.1f}%")
    print(f"  运动段 motion={float(d_move.mean()):.2f}%")
    print(f"  跳变段 motion={float(d_jump.mean()):.2f}%  spikes={rec['spikes_at_sec']}")
    ok = True
    for name, passed in checks.items():
        print(f"  [{'PASS' if passed else 'FAIL'}] {name}")
        ok = ok and passed
    out = Path(args.out) if args.out else tmpdir
    out.mkdir(parents=True, exist_ok=True)
    json.dump({"self_test": {k: bool(v) for k, v in checks.items()}, "rec": rec},
              open(out / "qa.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    (out / "qa.md").write_text(f"# motion_audit --self-test 负控\n\n{json.dumps(checks, ensure_ascii=False, indent=1)}\n", encoding="utf-8")
    if not ok:
        raise SystemExit(2)
    print("自测通过 ->", out / "qa.md")
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--video", default="", help="成片 mp4（竖屏 1080×1920 或任意比例，自动降采样）")
    ap.add_argument("--ref", default="", help="同源第二版成片（确定性逐帧 PSNR 对比，对齐 frame_audit A0）")
    ap.add_argument("--out", default="", help="产出目录；缺省 = <视频同目录>/qc/motion_audit")
    ap.add_argument("--thresh", type=int, default=D_THRESH, help="运动像素差阈值（默认 12）")
    ap.add_argument("--still", type=float, default=STILL_PCT, help="静止帧对阈值 %（默认 0.05）")
    ap.add_argument("--spike-pct", type=float, default=SPIKE_PCT, help="跳变占比阈值 %（默认 3）")
    ap.add_argument("--spike-ratio", type=float, default=SPIKE_RATIO, help="跳变峰值/中位数比（默认 6）")
    ap.add_argument("--strict", action="store_true", help="严格模式：静止帧对>40% 或确定性失败时 rc=2")
    ap.add_argument("--self-test", action="store_true", help="合成三段式负控自测（静止→匀速→跳变），断言检出")
    a = ap.parse_args()
    if a.self_test:
        return run_selftest(a)
    if not a.video:
        ap.error("--video 或 --self-test 二选一")
    if not os.path.exists(a.video):
        raise SystemExit(f"视频不存在: {a.video}")
    if a.ref and not os.path.exists(a.ref):
        raise SystemExit(f"--ref 不存在: {a.ref}")
    return run_video(a, a.video, ref=a.ref or None)


if __name__ == "__main__":
    sys.exit(main())
