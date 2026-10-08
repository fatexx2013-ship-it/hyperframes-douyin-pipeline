#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
frame_audit.py —— 渲染后抽帧断言（成片质量门禁第 2 段）

所属产线：hyperframes 竖屏短视频产线（部署根由 PIPELINE_HOME / 仓库位置决定）
上游契约：见 proposals/方案定稿_编排器与质量门禁_v2.md §三（v3 口径）
对齐口径：与 design_ai_gate.py 一致
  - 退出码 0 = 通过；1 = 用法/输入错误；2 = 检出问题（阻断）
  - --warn-only 时恒 0（除用法错），报告照出
  - 纯 numpy / scipy / PIL + 系统 ffmpeg、ffprobe，无其它依赖

断言清单
  A0 渲染确定性   同 HTML + 同渲染参数两版成片逐帧 PSNR ≥ 40dB（或帧哈希一致）
  A1 全黑帧       blackdetect，黑场 ≥ 0.1s
  A2 悬空细长亮线 逐场景时间窗持久细脊；--ref 给定时取「被测 − 参照」差集
  A3 元素位置/形变 逐场景时间窗前景块几何 vs --ref，任一抽帧偏差 > 40px 或尺度比越界
  A4 字幕安全区   底部 15% 出现非字幕带的大块前景且持久
  A5 规格/时长    1080×1920、30fps（error）；音视频时长差 > 0.1s（error）；
                  成片时长 vs script.json total_duration 偏差 > 2.0s（warn）
  A6a 同骨架体积  |Δ体积| ≤ 10% vs per-story 基线；无基线跳过不告警（error）
  A6b 码率旗标    MiB/s > 5× 参照 → 旗标（恒 warn-only，不阻断）
                  参照四级优先级：--bitrate-ref > per-story qc/baseline/bitrate.json
                  > 真源 audit_refs.a6b_ref_mib_per_s（冻结 0.115 MiB/s）> 旧口径（告警）
  A7 交付规格     判据唯一取自 scripts/encode_profile.py::assert_delivery_spec()；
                  字段分级 sample_rate/channels/profile/level/pix_fmt = error，
                  gop = warn（未点名字段默认 error，fail-closed）；覆盖含片尾件
                  douyin_epilogue.mp4（qc 段2 的被测件）；豁免登记走 script.json
                  顶层键 delivery_spec_waiver（6 字段 + sha256 锚点；四条件须同时
                  成立才放行；软失效报 INFO、硬失效不放行；登记非法即 exit 1）

用法
----
  python3 scripts/frame_audit.py --video <mp4> --script <script.json> \\
      [--ref <参考成片.mp4>] [--html <index.html>] \\
      [--baseline <基线.mp4|qc/baseline目录>] [--store-baseline] \\
      [--size-baseline <bytes>] [--bitrate-ref <MiB/s>] \\
      [--warn-only] [--json-out P]

返回：0=通过；2=检出问题（--warn-only 时恒 0）；1=用法/输入错误
"""

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import time

import numpy as np
from PIL import Image
from scipy import ndimage
# 跨平台适配层（真源 scripts/platform_env.py）：ffmpeg/ffprobe 等按 PATH + 平台常见位解析，
# 支持环境变量覆盖（PIPELINE_FFMPEG / FFMPEG、PIPELINE_FFPROBE / FFPROBE）。
_SDIR = os.path.dirname(os.path.abspath(__file__))
if _SDIR not in sys.path:
    sys.path.insert(0, _SDIR)
import platform_env  # noqa: E402

# ---------------------------------------------------------------------------
# 常量（全部阈值集中在此，调参只动这里）
# ---------------------------------------------------------------------------
SIG_THR = 150          # 显著性阈值：max(饱和度*1.6, 亮度) > SIG_THR 视为前景
RIDGE_K = 9            # 细脊检测的腐蚀核边长（细于此厚度的亮线才保留）
RIDGE_MIN_AREA = 60    # 细脊最小像素面积
RIDGE_MIN_AR = 6.0     # 细脊最小长宽比
BLOB_MIN_AREA = 800    # 前景连通块最小像素面积
BORDER = 10            # 贴边忽略带（像素）
PERSIST_RATIO = 0.75   # 持久性：某候选在场景抽帧中出现比例 ≥ 此值才算持久
BBOX_TOL = 60          # 包围盒近似匹配容差（像素）
SCENE_FRACS = (0.10, 0.25, 0.40, 0.55, 0.70, 0.85)  # 场景窗口内抽帧位置（比例）
PSNR_MIN = 40.0        # A0 逐帧 PSNR 下限（dB）
A3_MAX_SHIFT = 40.0    # A3 中心偏移阈值（像素）
A3_SCALE_MIN = 0.80    # A3 尺度比下限
A3_SCALE_MAX = 1.25    # A3 尺度比上限
A4_SAFE_RATIO = 0.85   # A4 安全区：帧高 × 此值以下视为底部 15%
A4_BLOB_MIN_AREA = 6000  # A4 入侵前景块最小面积
A4_SUBTITLE_BOTTOM = 150  # HTML .subtitle 的 bottom 声明（像素），该带内豁免
A4_SUBTITLE_HEIGHT = 160  # 字幕带假定高度（像素）
A5_DUR_SYNC_TOL = 0.10    # 音视频时长错位容差（秒，error）
A5_DECLARED_TOL = 2.00    # 成片 vs total_duration 容差（秒，warn）

# ── A5 段2 双 target（MVP 收口；方案 B 裁定：段2 时长校验须覆盖 douyin.mp4 与片尾件）──
# 此前 run_a5 只对 basename=="douyin.mp4" 比对 total_duration，片尾件被跳过（info）
# → 片尾件时长漂移无人守。现补片尾件口径（见 epilogue_expected()）。
EPILOGUE_GAP_DEFAULT = 0.40     # script.json epilogue.gap_before 缺省（与 append_epilogue 一致）
EPILOGUE_TAIL_DEFAULT = 0.50    # script.json epilogue.tail_silence 缺省（同上）
A5_TARGETS = ("douyin.mp4", "douyin_epilogue.mp4")   # 段2 覆盖的两个 target
A6A_TOL = 0.10            # A6a 体积偏差容差（10%）
A6B_RATIO = 5.0           # A6b 码率倍数阈值（S3：3.0→5.0，保 warn 不降级）
A6B_DEFAULT_REF = "story/ace-step-ui/douyin_epilogue.mp4"  # A6b 旧口径参照（相对 CWD，仅四级兜底）
A6B_CONTRACT_KEY = "a6b_ref_mib_per_s"   # 真源 audit_refs 冻结参照键（方案B 发现B 修法；判据真源）
A6B_STORY_BASELINE = ("baseline", "bitrate.json")  # per-story 参照（B 认定 schema 见下，只读+显式写）
A6B_STORY_SCHEMA_VERSION = "1.0"   # 方案B 2026-10-06 裁定 schema：version/captured_at/entries[]


class InputError(Exception):
    """用法/输入错误 → exit 1。"""


class _Parser(argparse.ArgumentParser):
    """参数解析错误以 1 退出，与 design_ai_gate.py 退出码口径一致。"""

    def error(self, message):
        self.print_usage(sys.stderr)
        print(f"{self.prog}: error: {message}", file=sys.stderr)
        sys.exit(1)


def parse_args(argv):
    ap = _Parser(description="渲染后抽帧断言（成片质量门禁第 2 段）")
    ap.add_argument("--video", required=True, help="待审成片 mp4")
    ap.add_argument("--script", required=True,
                    help="story 的 script.json（提供 total_duration 与场景时间窗）")
    ap.add_argument("--ref", default=None,
                    help="参照成片（同 story 的已修复版）；A2/A3 做差集时必需")
    ap.add_argument("--html", default=None,
                    help="index.html；A4 据此豁免字幕带")
    ap.add_argument("--baseline", default=None,
                    help="A0 基线：另一版 mp4（走 PSNR）或 qc/baseline 目录（走帧哈希）")
    ap.add_argument("--store-baseline", action="store_true",
                    help="把当前成片写入 qc/baseline/（size.json + frames.json）")
    ap.add_argument("--size-baseline", type=int, default=None,
                    help="A6a 体积基线（bytes）；缺省读 qc/baseline/size.json")
    ap.add_argument("--bitrate-ref", type=float, default=None,
                    help="A6b 码率参照（MiB/s）；缺省按四级优先级取："
                         "per-story qc/baseline/bitrate.json > 真源 audit_refs.%s"
                         "（冻结值）> 旧口径现场探测 ace-step-ui 成片（命中即告警）"
                         % A6B_CONTRACT_KEY)
    ap.add_argument("--duration-expected", type=float, default=None,
                    help="A5 声明时长显式口：目标含片尾时给出期望总长"
                         "（= total_duration + gap + seg_duration），按该值比对，容差不变")
    ap.add_argument("--same-source", action="store_true",
                    help="A0 mp4 基线同源显式声明（仅调试）：跳过溯源校验，风险自负；"
                         "目录基线自动校验，无需此参数")
    ap.add_argument("--warn-only", action="store_true",
                    help="只报告不阻断（恒 exit 0，除用法错）")
    ap.add_argument("--json-out", default=None,
                    help="报告写盘路径；缺省 <video所在目录>/qc/report.json")
    return ap.parse_args(argv)

# ---------------------------------------------------------------------------
# ffmpeg / ffprobe 发现与执行
# ---------------------------------------------------------------------------
_BIN_CACHE = {}


def _find_bin(names):
    """在环境变量/PATH 及平台常见安装位中查找可执行文件，返回绝对路径或 None。

    跨平台解析统一委托 platform_env.find_tool（macOS Homebrew/MacPorts、Linux
    /usr/local|snap|linuxbrew|~/.local、Windows WinGet Links/scoop shims/Program Files）。
    """
    if names in _BIN_CACHE:
        return _BIN_CACHE[names]
    found = None
    for name in names:
        found = platform_env.find_tool(name)
        if found:
            break
    _BIN_CACHE[names] = found
    return found


def ffmpeg():
    b = _find_bin(("ffmpeg",))
    if not b:
        raise InputError("找不到 ffmpeg，请确认已安装并在 PATH 中")
    return b


def ffprobe():
    b = _find_bin(("ffprobe",))
    if not b:
        raise InputError("找不到 ffprobe，请确认已安装并在 PATH 中")
    return b


def _run(cmd, capture=True, check=True):
    """执行子进程；check=True 时非零返回码抛 InputError。"""
    r = subprocess.run(cmd, capture_output=capture, text=True)
    if check and r.returncode != 0:
        tail = (r.stderr or "").strip().splitlines()[-3:]
        raise InputError("命令执行失败：%s\n%s" % (" ".join(cmd), "\n".join(tail)))
    return r


def _parse_fps(rate):
    """'30/1' -> 30.0；'30000/1001' -> 29.97。"""
    if not rate:
        return None
    if "/" in rate:
        a, b = rate.split("/", 1)
        try:
            b = float(b)
            return float(a) / b if b else None
        except ValueError:
            return None
    try:
        return float(rate)
    except ValueError:
        return None


def video_meta(path):
    """ffprobe 取规格；返回元信息 dict（含体积与码率口径）。"""
    if not os.path.isfile(path):
        raise InputError(f"视频不存在：{path}")
    cmd = [
        ffprobe(), "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "stream=nb_frames,r_frame_rate,duration,width,height",
        "-show_entries", "format=duration",
        "-of", "json", path,
    ]
    d = json.loads(_run(cmd).stdout)
    streams = d.get("streams") or []
    if not streams:
        raise InputError(f"未取到视频流：{path}")
    s = streams[0]
    fmt = d.get("format") or {}
    try:
        duration = float(s.get("duration") or fmt.get("duration") or 0.0)
    except (TypeError, ValueError):
        duration = 0.0
    fps = _parse_fps(s.get("r_frame_rate"))
    try:
        nb_frames = int(s.get("nb_frames"))
    except (TypeError, ValueError):
        nb_frames = int(round(duration * fps)) if fps and duration else 0
    # 音频轨时长
    acmd = [
        ffprobe(), "-v", "error",
        "-select_streams", "a:0",
        "-show_entries", "stream=duration",
        "-of", "csv=p=0", path,
    ]
    ar = _run(acmd, check=False)
    audio_duration = None
    if ar.returncode == 0 and ar.stdout.strip():
        try:
            audio_duration = float(ar.stdout.strip())
        except ValueError:
            audio_duration = None
    size = os.path.getsize(path)
    mib = size / (1024.0 * 1024.0)
    mib_per_s = mib / duration if duration else None
    return {
        "path": path,
        "width": int(s.get("width") or 0),
        "height": int(s.get("height") or 0),
        "fps": fps,
        "duration": duration,
        "nb_frames": nb_frames,
        "audio_duration": audio_duration,
        "has_audio": audio_duration is not None,
        "bytes": size,
        "mib": round(mib, 2),
        "mib_per_s": round(mib_per_s, 3) if mib_per_s else None,
    }

# ---------------------------------------------------------------------------
# script.json：场景时间窗 + 抽帧
# ---------------------------------------------------------------------------
def load_script(path):
    """读 script.json；返回 (data, total_duration)。"""
    if not os.path.isfile(path):
        raise InputError(f"script 不存在：{path}")
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except Exception as e:  # noqa: BLE001
        raise InputError(f"script 解析失败 {path}: {e}")
    if not isinstance(data, dict):
        raise InputError(f"script 顶层必须是 JSON 对象：{path}")
    td = data.get("total_duration")
    try:
        td = float(td) if td is not None else None
    except (TypeError, ValueError):
        td = None
    return data, td


def scene_windows(script_data, fallback_duration=None):
    """从 scenes 的 _start/_end 产出 [(name, start, end), ...]。

    script.json 无几何声明（仅时间戳），场景时间窗是 frame_audit 能从 script 拿到的
    唯一结构；缺场景时退化为单个全长窗口。
    """
    scenes = script_data.get("scenes")
    wins = []
    if isinstance(scenes, list):
        for i, sc in enumerate(scenes):
            if not isinstance(sc, dict):
                continue
            start, end = sc.get("_start"), sc.get("_end")
            try:
                start = float(start) if start is not None else None
                end = float(end) if end is not None else None
            except (TypeError, ValueError):
                start = end = None
            if start is None or end is None or end <= start:
                continue
            wins.append((f"scene-{i}", start, end))
    if not wins:
        dur = fallback_duration or 0.0
        if dur > 0:
            wins.append(("full", 0.0, dur))
    return wins


def _scene_sample_times(win):
    """场景窗口内按 SCENE_FRACS 产出抽帧时间点（秒）。"""
    name, start, end = win
    span = end - start
    return [(name, start + f * span) for f in SCENE_FRACS]


def extract_frames(video, times, suffix="ja"):
    """对 video 在给定时间点各抽一帧到临时目录，返回 [路径, ...]。"""
    if not times:
        return []
    tmp = tempfile.mkdtemp(prefix="fa_%s_" % suffix)
    out = []
    for i, t in enumerate(times):
        p = os.path.join(tmp, "f%03d.jpg" % i)
        cmd = [ffmpeg(), "-v", "error", "-ss", "%.3f" % t, "-i", video,
               "-frames:v", "1", "-y", p]
        _run(cmd)
        if not os.path.isfile(p):
            raise InputError(f"抽帧失败 t={t:.3f}s：{video}")
        out.append(p)
    return out


def _read_gray(path):
    return np.asarray(Image.open(path).convert("L"), dtype=np.float32)


def _read_rgb(path):
    return np.asarray(Image.open(path).convert("RGB"), dtype=np.float32)


def qc_dir(video):
    """报告/基线目录：<video所在目录>/qc。"""
    return os.path.join(os.path.dirname(os.path.abspath(video)), "qc")

# ---------------------------------------------------------------------------
# 像素层：显著性掩码、细脊（A2）、前景块（A3/A4）
# ---------------------------------------------------------------------------
def _sig_mask(gray, rgb):
    """显著像素掩码：高饱和（主题橙 #FF5926 一类）或高亮度。

    主题橙 #FF5926 亮度仅约 132，纯亮度阈值会漏检；用 max(饱和度*1.6, 亮度) 兼顾。
    """
    sat = (rgb.max(axis=2) - rgb.min(axis=2)) * 1.6
    return np.maximum(sat, gray) > SIG_THR


def find_ridges(gray, rgb):
    """细长亮脊（悬空线候选）。返回 [{"bbox", "area", "aspect"}, ...]，贴边忽略。"""
    mask = _sig_mask(gray, rgb)
    eroded = ndimage.binary_erosion(mask, structure=np.ones((RIDGE_K, RIDGE_K)))
    thin = mask & ~eroded
    labeled, n = ndimage.label(thin)
    h, w = gray.shape
    out = []
    for i in range(1, n + 1):
        ys, xs = np.where(labeled == i)
        y0, y1, x0, x1 = int(ys.min()), int(ys.max()), int(xs.min()), int(xs.max())
        if y0 < BORDER or x0 < BORDER or y1 > h - 1 - BORDER or x1 > w - 1 - BORDER:
            continue
        bh, bw = y1 - y0 + 1, x1 - x0 + 1
        area = int(len(ys))
        aspect = max(bh, bw) / max(min(bh, bw), 1)
        if area >= RIDGE_MIN_AREA and aspect >= RIDGE_MIN_AR:
            out.append({"bbox": (x0, y0, x1, y1), "area": area,
                        "aspect": round(float(aspect), 1)})
    return out


def find_blobs(gray, rgb):
    """前景连通块（按面积降序）。返回 [{"bbox","area","w","h","cx","cy"}, ...]。"""
    mask = _sig_mask(gray, rgb)
    labeled, n = ndimage.label(mask)
    h, w = gray.shape
    out = []
    for i in range(1, n + 1):
        ys, xs = np.where(labeled == i)
        area = int(len(ys))
        if area < BLOB_MIN_AREA:
            continue
        y0, y1, x0, x1 = int(ys.min()), int(ys.max()), int(xs.min()), int(xs.max())
        if y0 < BORDER or x0 < BORDER or y1 > h - 1 - BORDER or x1 > w - 1 - BORDER:
            continue
        out.append({"bbox": (x0, y0, x1, y1), "area": area,
                    "w": x1 - x0 + 1, "h": y1 - y0 + 1,
                    "cx": (x0 + x1) / 2.0, "cy": (y0 + y1) / 2.0})
    out.sort(key=lambda d: -d["area"])
    return out


def _bbox_near(a, b, tol=BBOX_TOL):
    """两包围盒是否位置近似（用于跨帧同一候选的归并）。"""
    return (abs(a[0] - b[0]) <= tol and abs(a[1] - b[1]) <= tol and
            abs(a[2] - b[2]) <= tol and abs(a[3] - b[3]) <= tol)


def persistent_ridges(video, scenes):
    """逐场景抽帧，取持久细脊（出现比例 ≥ PERSIST_RATIO）。

    返回 [{"scene","bbox","area","aspect","hits","n"}, ...]。
    抽帧按场景窗口的比例位置（SCENE_FRACS），被测与参照同比例采样，
    抵消两版总时长可能不同（如 85.37s vs 83.87s）带来的错位。
    """
    result = []
    for win in scenes:
        times = _scene_sample_times(win)
        frames = extract_frames(video, [t for _, t in times], suffix="rdg")
        per_frame = []
        for p in frames:
            per_frame.append(find_ridges(_read_gray(p), _read_rgb(p)))
        kept = []
        for rs in per_frame:
            for r in rs:
                if any(_bbox_near(r["bbox"], q["bbox"]) for q in kept):
                    continue
                hits = sum(1 for rs2 in per_frame
                           if any(_bbox_near(r["bbox"], q["bbox"]) for q in rs2))
                if hits / max(len(per_frame), 1) >= PERSIST_RATIO:
                    kept.append({"scene": win[0], "bbox": r["bbox"],
                                 "area": r["area"], "aspect": r["aspect"],
                                 "hits": hits, "n": len(per_frame)})
        result.extend(kept)
    return result

# ---------------------------------------------------------------------------
# A0：渲染确定性（PSNR / 帧哈希）
# ---------------------------------------------------------------------------
def _dhash(path):
    """差异哈希：9×8 灰度 → 64-bit hex（16 字符）。"""
    img = Image.open(path).convert("L").resize((9, 8), Image.LANCZOS)
    a = np.asarray(img, dtype=np.int16)
    bits = (a[:, 1:] > a[:, :-1]).flatten()
    return "%016x" % (int("".join("1" if b else "0" for b in bits), 2))


def _hash_frames(video, duration, n=12):
    """全片均匀抽 n 帧并哈希，返回 (hashes, times)。"""
    if duration <= 1:
        return [], []
    span = duration - 1.0
    times = [0.5 + span * i / max(n - 1, 1) for i in range(n)]
    frames = extract_frames(video, times, suffix="hsh")
    return [_dhash(p) for p in frames], times


def store_baseline(video, meta, script_data, html_path=None, script_path=None):
    """把当前成片写入 qc/baseline/：size.json（A6a）+ frames.json（A0）+ source.json（同源溯源）。

    source.json 记 html/script 的绝对路径与 sha256 指纹，供 A0 同源前置门校验。
    """
    base = os.path.join(qc_dir(video), "baseline")
    os.makedirs(base, exist_ok=True)
    with open(os.path.join(base, "size.json"), "w", encoding="utf-8") as fh:
        json.dump({"path": video, "bytes": meta["bytes"], "mib": meta["mib"],
                   "duration": meta["duration"], "mib_per_s": meta["mib_per_s"]},
                  fh, ensure_ascii=False, indent=2)
    hashes, times = _hash_frames(video, meta["duration"])
    with open(os.path.join(base, "frames.json"), "w", encoding="utf-8") as fh:
        json.dump({"path": video, "times": times, "hashes": hashes},
                  fh, ensure_ascii=False, indent=2)
    html_abs = _locate_html(video, html_path)
    if html_abs:
        print("A0 溯源：index.html = %s（sha256 %s）" % (html_abs, _sha256_of(html_abs)))
    write_source_baseline(base, video, meta, html_abs, script_path)
    if meta.get("mib_per_s"):
        write_story_bitrate_baseline(base, video, meta)
    return base


def _sha256_of(path):
    """文件 sha256 的前 12 位（溯源指纹，短而够用）。"""
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()[:12]


def _locate_html(video, explicit=None):
    """定位 index.html：优先 --html 显式值，否则从 video 所在目录逐级向上找最近一个。

    隐式查找仅用于「猜一个默认值」，找到后照样落绝对路径；source.json 记的是
    绝对路径，校验时按路径精确匹配（story 目录下可能同时存在主件与 epilogue/ 子件）。
    """
    if explicit:
        return os.path.abspath(explicit)
    d = os.path.dirname(os.path.abspath(video))
    for _ in range(6):
        p = os.path.join(d, "index.html")
        if os.path.isfile(p):
            return p
        parent = os.path.dirname(d)
        if parent == d:
            break
        d = parent
    return None


def write_source_baseline(base_dir, video, meta, html_path, script_path):
    """把同源溯源快照写入 qc/baseline/source.json。"""
    src = {"video": os.path.abspath(video),
           "html": os.path.abspath(html_path) if html_path else None,
           "html_sha256": _sha256_of(html_path) if html_path else None,
           "script": os.path.abspath(script_path) if script_path else None,
           "script_sha256": _sha256_of(script_path) if script_path else None,
           "params": {k: meta.get(k) for k in
                      ("width", "height", "fps", "duration", "nb_frames")}}
    with open(os.path.join(base_dir, "source.json"), "w", encoding="utf-8") as fh:
        json.dump(src, fh, ensure_ascii=False, indent=2)
    return src


def check_source_baseline(base_dir, video, meta, html_path, script_path):
    """A0 同源前置门：source.json 与当前 html/script 指纹任一不符即 InputError。

    失败返回 exit 1（用法/输入错误），不退 2——基线喂错不是「渲染不确定」。
    """
    p = os.path.join(base_dir, "source.json")
    if not os.path.isfile(p):
        raise InputError("A0 基线目录缺少 source.json（同源溯源快照）：%s" % base_dir)
    with open(p, encoding="utf-8") as fh:
        ref = json.load(fh)
    for key, path, label in (("html", html_path, "index.html"),
                             ("script", script_path, "script.json")):
        ref_path = ref.get(key)
        ref_fp = ref.get(key + "_sha256")
        if not ref_path or not ref_fp:
            continue
        if os.path.abspath(ref_path) != os.path.abspath(path):
            raise InputError(
                "A0 基线不同源：%s 路径不符（基线 %s vs 当前 %s）" % (label, ref_path, path))
        cur_fp = _sha256_of(path)
        if cur_fp != ref_fp:
            raise InputError(
                "A0 基线不同源：%s 自基线建立后已被改动（sha256 基线=%s 当前=%s）。"
                "A0 要求同 HTML 同渲染参数；请对当前 HTML 重新 --store-baseline，"
                "或加 --same-source 显式声明后重跑（仅调试）" % (label, ref_fp, cur_fp))
    return ref


def psnr_compare(video_a, video_b):
    """ffmpeg psnr 滤镜逐帧比对，返回 {"min","avg","n"}；完全相同帧记为 inf。"""
    if video_meta(video_a)["nb_frames"] != video_meta(video_b)["nb_frames"]:
        raise InputError("A0 帧数不一致，无法逐帧 PSNR 比对")
    fd, stats_path = tempfile.mkstemp(suffix=".stats")
    os.close(fd)
    cmd = [ffmpeg(), "-loglevel", "error", "-i", video_a, "-i", video_b,
           "-lavfi", "[0:v][1:v]psnr=stats_file=%s" % stats_path, "-f", "null", "-"]
    try:
        _run(cmd)
        vals = []
        with open(stats_path, encoding="utf-8") as fh:
            for line in fh:
                m = re.search(r"psnr_avg:([0-9.]+|inf)", line)
                if m:
                    vals.append(float("inf") if m.group(1) == "inf"
                                else float(m.group(1)))
    finally:
        try:
            os.remove(stats_path)
        except OSError:
            pass
    if not vals:
        raise InputError("A0 未取到任何 psnr 统计行")
    finite = [v for v in vals if v != float("inf")]
    return {"min": min(finite) if finite else float("inf"),
            "avg": sum(finite) / len(finite) if finite else float("inf"),
            "n": len(vals)}


def run_a0(video, baseline, meta, html_path=None, script_path=None,
           same_source=False):
    """A0：同 HTML + 同渲染参数两版成片应逐帧一致（含同源前置门）。

    baseline 为目录 → 先过同源门（source.json 的 html/script 指纹），再读
    frames.json 做帧哈希比对；baseline 为 mp4 → 无溯源信息，须显式 --same-source
    声明同源，否则拒绝比对。同源不成立属输入错误（InputError → exit 1），
    不当作「渲染不确定」（exit 2）。
    """
    out = []
    if os.path.isdir(baseline):
        check_source_baseline(baseline, video, meta, html_path, script_path)
        fp = os.path.join(baseline, "frames.json")
        if not os.path.isfile(fp):
            raise InputError(f"A0 基线目录缺少 frames.json：{baseline}")
        with open(fp, encoding="utf-8") as fh:
            ref = json.load(fh)
        hashes, times = _hash_frames(video, meta["duration"])
        if len(hashes) != len(ref.get("hashes", [])):
            return [{"assertion": "A0", "severity": "error",
                     "message": "A0 帧数与基线不一致：%d vs %d，渲染不确定" %
                                (len(hashes), len(ref["hashes"]))}]
        diff = [i for i, (a, b) in enumerate(zip(hashes, ref["hashes"])) if a != b]
        if diff:
            return [{"assertion": "A0", "severity": "error",
                     "message": "A0 帧哈希不一致，共 %d/%d 帧变化（首帧 t=%.2fs）" %
                                (len(diff), len(hashes), ref["times"][diff[0]])}]
        return out
    if not os.path.isfile(baseline):
        raise InputError(f"A0 基线不存在：{baseline}")
    if not same_source:
        raise InputError(
            "A0 mp4 基线无溯源信息，无法证明同源。改用 --baseline <qc/baseline 目录>"
            "（自动校验同源），或加 --same-source 显式声明（仅调试）。")
    stats = psnr_compare(video, baseline)
    if stats["min"] < PSNR_MIN:
        out.append({"assertion": "A0", "severity": "error",
                    "message": "A0 逐帧 PSNR 最低 %.2f dB < %.1f dB，渲染不确定（avg %.2f，%d 帧）"
                               % (stats["min"], PSNR_MIN, stats["avg"], stats["n"])})
    return out


# ---------------------------------------------------------------------------
# A1：全黑帧
# ---------------------------------------------------------------------------
def run_a1(video):
    """ffmpeg blackdetect：黑场 ≥ 0.1s 即告警。"""
    cmd = [ffmpeg(), "-loglevel", "info", "-i", video,
           "-vf", "blackdetect=d=0.1:pix_th=0.10", "-an", "-f", "null", "-"]
    r = _run(cmd, check=False)
    out = []
    for line in (r.stderr or "").splitlines():
        m = re.search(r"black_start:([0-9.]+)\s+black_end:([0-9.]+)\s+black_duration:([0-9.]+)", line)
        if m:
            out.append({"assertion": "A1", "severity": "error",
                        "message": "A1 全黑帧 %.2fs–%.2fs（时长 %.2fs）" %
                                   (float(m.group(1)), float(m.group(2)), float(m.group(3)))})
    return out

# ---------------------------------------------------------------------------
# A2：孤立悬空细长亮线
# ---------------------------------------------------------------------------
def fmt_bbox(bbox):
    """bbox=(x0,y0,x1,y1) → 'x100-300 y200-400'（先 x 后 y）。

    统一全部 message / _format 的坐标口径：*bbox 解包成 (x0,y0,x1,y1) 塞进
    "x%d-%d y%d-%d" 会让 x 段塞入 y 坐标，逐处改不如收拢到一个函数。
    """
    return "x%d-%d y%d-%d" % (bbox[0], bbox[2], bbox[1], bbox[3])


def run_a2(video, scenes, ref=None):
    """持久细脊；--ref 给定时取「被测 − 参照」差集，抑制合法设计元素。"""
    base = persistent_ridges(video, scenes)
    if not ref:
        if not base:
            return []
        return [{"assertion": "A2", "severity": "warn",
                 "message": "A2 持久细脊 %d 条，未给 --ref 无法判定是否合法：%s" %
                            (len(base), ", ".join(
                                "%s %s" % (r["scene"], fmt_bbox(r["bbox"]))  # S3：r["scene"] 已含 "scene-" 前缀（原拼出 scenescene-0）
                                for r in base))}]
    refp = persistent_ridges(ref, scenes)
    extras = [r for r in base
              if not any(_bbox_near(r["bbox"], q["bbox"]) for q in refp)]
    return [{"assertion": "A2", "severity": "warn", "scene": r["scene"],
             "bbox": list(r["bbox"]),
             "message": "A2 参照之外多出持久细脊：x%d-%d y%d-%d（area=%d aspect=%s）"
                        % (r["bbox"][0], r["bbox"][2], r["bbox"][1], r["bbox"][3],
                           r["area"], r["aspect"])}
            for r in extras]


# ---------------------------------------------------------------------------
# A3：元素位置 / 形变（vs --ref）
# ---------------------------------------------------------------------------
def _scene_blobs(video, win):
    """某场景窗口抽帧的前景块序列：[{"t", blobs}, ...]。"""
    times = _scene_sample_times(win)
    frames = extract_frames(video, [t for _, t in times], suffix="a3")
    return [{"t": t, "blobs": find_blobs(_read_gray(p), _read_rgb(p))}
            for (_, t), p in zip(times, frames)]


def run_a3(video, ref, scenes):
    """逐场景逐抽帧比对最大前景块：中心偏移或尺度比越界即告警。

    script.json 无几何声明，A3 只能是相对断言（vs --ref）；这既复现了
    「气泡 y+51px / scale 0.56」一类的手工坐标反推，也复现了「被测无前景而参照有」
    的元素丢失情形。
    """
    out = []
    for win in scenes:
        tb = _scene_blobs(video, win)
        rb = _scene_blobs(ref, win)
        for i, (tframe, rframe) in enumerate(zip(tb, rb)):
            t0 = tframe["blobs"][0] if tframe["blobs"] else None
            r0 = rframe["blobs"][0] if rframe["blobs"] else None
            if r0 and not t0:
                out.append({"assertion": "A3", "severity": "warn",
                            "scene": win[0], "t": tframe["t"],
                            "bbox": list(r0["bbox"]),
                            "message": "A3 %s t=%.2fs：参照有前景而被测缺失（参照 %s）"
                                       % (win[0], tframe["t"], fmt_bbox(r0["bbox"]))})
                continue
            if not (t0 and r0):
                continue
            dx, dy = t0["cx"] - r0["cx"], t0["cy"] - r0["cy"]
            wr = t0["w"] / max(r0["w"], 1)
            hr = t0["h"] / max(r0["h"], 1)
            shifted = abs(dx) > A3_MAX_SHIFT or abs(dy) > A3_MAX_SHIFT
            scaled = not (A3_SCALE_MIN <= wr <= A3_SCALE_MAX) or \
                     not (A3_SCALE_MIN <= hr <= A3_SCALE_MAX)
            if shifted or scaled:
                out.append({"assertion": "A3", "severity": "warn",
                            "scene": win[0], "t": tframe["t"],
                            "bbox": list(t0["bbox"]),
                            "message": "A3 %s t=%.2fs：dx=%+.0f dy=%+.0f 宽比=%.2f 高比=%.2f"
                                       "（阈值 偏移±%.0f 尺度%.2f–%.2f）"
                                       % (win[0], tframe["t"], dx, dy, wr, hr,
                                          A3_MAX_SHIFT, A3_SCALE_MIN, A3_SCALE_MAX)})
    return out

# ---------------------------------------------------------------------------
# A4：字幕安全区遮挡
# ---------------------------------------------------------------------------
def _parse_subtitle_bottom(html_path):
    """从 --html 的 .subtitle 规则取 bottom 声明（像素），失败返回缺省值。"""
    default = A4_SUBTITLE_BOTTOM
    if not html_path or not os.path.isfile(html_path):
        return default
    try:
        with open(html_path, encoding="utf-8") as fh:
            text = fh.read()
    except OSError:
        return default
    m = re.search(r"\.subtitle\s*\{[^}]*bottom\s*:\s*([0-9]+)px", text)
    return int(m.group(1)) if m else default


def run_a4(video, scenes, html=None):
    """底部 15% 安全区内出现非字幕带的大块持久前景即告警（warn）。"""
    meta = video_meta(video)
    h = meta["height"] or 1920
    safe_y = h * A4_SAFE_RATIO
    sub_bottom = _parse_subtitle_bottom(html)
    # 字幕带：帧底以上 sub_bottom 处、假定高 A4_SUBTITLE_HEIGHT 的区域，带内豁免
    sub_top = h - sub_bottom - A4_SUBTITLE_HEIGHT
    sub_bottom_y = h - sub_bottom

    intrusions = []
    for win in scenes:
        times = _scene_sample_times(win)
        frames = extract_frames(video, [t for _, t in times], suffix="a4")
        hits = 0
        first = None
        for p in frames:
            gray, rgb = _read_gray(p), _read_rgb(p)
            mask = _sig_mask(gray, rgb)
            labeled, n = ndimage.label(mask)
            for i in range(1, n + 1):
                ys, xs = np.where(labeled == i)
                if len(ys) < A4_BLOB_MIN_AREA:
                    continue
                y0, y1 = int(ys.min()), int(ys.max())
                x0, x1 = int(xs.min()), int(xs.max())
                if y0 < BORDER or x0 < BORDER or y1 > h - 1 - BORDER:
                    continue
                # 主体落在安全区内，且与字幕带不重叠
                if y1 > safe_y and not (y0 < sub_bottom_y and y1 > sub_top):
                    if first is None:
                        first = (x0, y0, x1, y1)
                    hits += 1
                    break
        if hits / max(len(frames), 1) >= PERSIST_RATIO and first:
            intrusions.append({"scene": win[0], "bbox": list(first), "hits": hits,
                               "n": len(frames)})
    return [{"assertion": "A4", "severity": "warn", "scene": it["scene"],
             "bbox": it["bbox"],
             "message": "A4 %s 底部安全区（y>%.0f）出现持久前景 %d/%d 抽帧：%s"
                        % (it["scene"], safe_y, it["hits"], it["n"],
                           fmt_bbox(it["bbox"]))}
            for it in intrusions]


# ---------------------------------------------------------------------------
# A5：规格与时长错位
# ---------------------------------------------------------------------------
def _wav_duration(path):
    """读 wav 时长（秒）。失败返回 None。"""
    import wave
    try:
        with wave.open(path, "rb") as wf:
            rate = wf.getframerate()
            if not rate:
                return None
            return wf.getnframes() / float(rate)
    except Exception:
        return None


def epilogue_expected(script_data, video, total_duration):
    """片尾件（douyin_epilogue.mp4）声明时长口径 —— 返回 (expected_seconds, None)
    或 (None, 跳过原因)。

    append_epilogue.py 实测口径（见其 main 的 seg_dur/输出 RESULT）：
        epilogue_total = vdur + gap_before + epi_voice_dur + tail_silence
      · vdur      = 原片**实际**时长（拼接时用实测值；对 gods-eye-view 为 49.867s）
      · epi_voice = epilogue/epilogue.wav 时长（片尾口播，含 BGM 渲染后的实际语速）
      · gap/tail  = script.json epilogue.gap_before / tail_silence（缺省 0.40 / 0.50）
                    —— 即片尾卡前的过渡静音与片尾卡后的停留，均已含在片尾件内

    与**冻结基线锚点** script.json `total_duration` 的关系（方案 B 明确：锚点是
    total_duration，试点 build 侧 ±1.3~4.4s 的时长偏差不纳入基线）：
        expected = total_duration + gap_before + dur(epilogue.wav) + tail_silence
    锚点与实际拼接用量的差 = |vdur − total_duration|（gods-eye-view 实测 +0.43s），
    故本口径对片尾件的判定天然带 ~0.45s 系统偏差，仍远小于 A5_DECLARED_TOL=2.00，
    不会误报；真实漂移（漏加片尾卡/BGM、口播被截断）则会被抓出。
    """
    epi = (script_data or {}).get("epilogue")
    if not isinstance(epi, dict):
        return None, "script.json 缺 epilogue 对象"
    if not epi.get("enabled", True):
        return None, "epilogue.enabled=false（无片尾段可比）"
    if not total_duration:
        return None, "script.json 缺 total_duration 锚点"
    seg = None
    if video:
        sdir = os.path.dirname(os.path.abspath(video))
        for cand in ("epilogue/epilogue.wav", "epilogue/epilogue.24k.wav"):
            seg = _wav_duration(os.path.join(sdir, cand))
            if seg:
                break
    if not seg:
        return None, "取不到 epilogue/epilogue.wav 时长（无法定片尾口播长度）"
    try:
        gap = float(epi.get("gap_before", EPILOGUE_GAP_DEFAULT))
        tail = float(epi.get("tail_silence", EPILOGUE_TAIL_DEFAULT))
    except (TypeError, ValueError):
        gap, tail = EPILOGUE_GAP_DEFAULT, EPILOGUE_TAIL_DEFAULT
    return float(total_duration) + gap + seg + tail, None


def _a5_targets(video, meta):
    """段2 声明时长比对的被测件清单：被测件本身 + 同目录下 A5_TARGETS 其余成员。

    MVP 裁定（方案 B）：段2 必须**同时**覆盖 douyin.mp4（锚点 script.json
    total_duration）与 douyin_epilogue.mp4（锚点 = total_duration+gap+口播+tail）；
    此前只校主片、片尾件被跳过。同目录缺失的 target 自然不入列（单选件场景不报错）。
    """
    items, seen = [], set()
    vbase = os.path.basename(video) if video else None
    if video:
        items.append((vbase, video, meta))
        seen.add(os.path.abspath(video))
    vdir = os.path.dirname(os.path.abspath(video)) if video else None
    if vdir:
        for t in A5_TARGETS:
            tp = os.path.join(vdir, t)
            if os.path.abspath(tp) in seen or not os.path.isfile(tp):
                continue
            try:
                items.append((t, tp, video_meta(tp)))
            except Exception as exc:      # 探测失败不阻断主判据
                items.append((t, tp, {"duration": None, "_probe_error": str(exc)}))
    return items


def _a5_expected(tname, tpath, script_data, total_duration, video, duration_expected):
    """单个被测件的 (expected, label, skip_reason)。口径与冻结锚点关系见 epilogue_expected。"""
    if duration_expected is not None and video and tname == os.path.basename(video):
        return float(duration_expected), "--duration-expected", None
    if tname == A5_TARGETS[0]:
        return total_duration, "script.json total_duration（主片锚点）", None
    if tname == A5_TARGETS[1]:
        exp, why = epilogue_expected(script_data, tpath or video, total_duration)
        if exp is None:
            return None, None, why
        return exp, "片尾件口径 total_duration+gap+epilogue.wav+tail", None
    return None, None, "非本产线命名（%s）" % tname


def run_a5(meta, script_data, total_duration, video=None, duration_expected=None):
    """分辨率/帧率/音视频同步判 error；声明时长比对本批起覆盖**两个 target**：
    douyin.mp4（锚点 total_duration）与 douyin_epilogue.mp4（锚点 total_duration
    + gap + epilogue.wav + tail，见 epilogue_expected）：被测件为产线命名时，除自身
    外还会带上同目录另一个 target（见 _a5_targets），**两个 target 各自出结论**。
    仍可用 --duration-expected 显式覆盖被测件；非本产线命名或口径不可得时跳过并注明
    （info）。"""
    out = []
    if meta["width"] != 1080 or meta["height"] != 1920:
        out.append({"assertion": "A5", "severity": "error",
                    "message": "A5 分辨率 %dx%d，应为 1080x1920" %
                               (meta["width"], meta["height"])})
    if not meta["fps"] or abs(meta["fps"] - 30.0) > 0.5:
        out.append({"assertion": "A5", "severity": "error",
                    "message": "A5 帧率 %s，应为 30fps" % meta["fps"]})
    if meta["has_audio"] and meta["audio_duration"] is not None:
        sync = abs(meta["audio_duration"] - meta["duration"])
        if sync > A5_DUR_SYNC_TOL:
            out.append({"assertion": "A5", "severity": "error",
                        "message": "A5 音视频时长错位 %.2fs（视频 %.2fs / 音频 %.2fs）"
                                   % (sync, meta["duration"], meta["audio_duration"])})
    elif not meta["has_audio"]:
        out.append({"assertion": "A5", "severity": "error",
                    "message": "A5 无音频轨"})
    if total_duration and meta["duration"]:
        for tname, tpath, tmeta in _a5_targets(video, meta):
            t_dur = tmeta.get("duration")
            if not t_dur:
                out.append({"assertion": "A5", "severity": "info",
                            "message": "A5 跳过声明时长比对（%s）：取不到时长（%s）"
                                       % (tname, tmeta.get("_probe_error", "无视频流"))})
                continue
            expected, label, skip_reason = _a5_expected(
                tname, tpath, script_data, total_duration, video, duration_expected)
            if expected is None:
                out.append({"assertion": "A5", "severity": "info",
                            "message": "A5 跳过声明时长比对（%s）：%s；含片尾件可传 "
                                       "--duration-expected <total_duration+gap+seg>"
                                       % (tname, skip_reason or ("total_duration 仅覆盖"
                                                                 "旁白轴，不含片尾/渲染垫片"))})
                continue
            drift = t_dur - expected
            if abs(drift) > A5_DECLARED_TOL:
                out.append({"assertion": "A5", "severity": "warn",
                            "message": "A5 成片时长 %.2fs vs %s %.2fs"
                                       "（偏差 %+.2fs，阈值 ±%.2f）[target=%s]"
                                       % (t_dur, label, expected, drift,
                                          A5_DECLARED_TOL, tname)})
            else:
                out.append({"assertion": "A5", "severity": "info",
                            "message": "A5 时长比对通过：%.2fs vs %s %.2fs"
                                       "（偏差 %+.2fs，阈值 ±%.2f）[target=%s]"
                                       % (t_dur, label, expected, drift,
                                          A5_DECLARED_TOL, tname)})
    return out

# ---------------------------------------------------------------------------
# A6a：同骨架体积一致性
# ---------------------------------------------------------------------------
def _size_baseline(video, cli_baseline):
    """A6a 体积基线（bytes）：--size-baseline > qc/baseline/size.json，取不到返回 None。"""
    if cli_baseline is not None:
        return cli_baseline
    p = os.path.join(qc_dir(video), "baseline", "size.json")
    if os.path.isfile(p):
        try:
            with open(p, encoding="utf-8") as fh:
                return int(json.load(fh).get("bytes"))
        except (OSError, ValueError, TypeError):
            return None
    return None


def run_a6a(video, meta, cli_baseline):
    """|Δ体积| ≤ A6A_TOL（默认 10%）vs per-story 基线；无基线跳过不告警。

    同骨架重建场景才启用；首次出片未 --store-baseline 时静默跳过。
    """
    base = _size_baseline(video, cli_baseline)
    if not base:
        return []
    ratio = abs(meta["bytes"] - base) / float(base)
    if ratio > A6A_TOL:
        return [{"assertion": "A6a", "severity": "error",
                 "baseline_bytes": base, "bytes": meta["bytes"],
                 "message": "A6a 体积偏差 %.1f%%（%.2fMiB vs 基线 %.2fMiB），阈值 %.0f%%"
                            % (ratio * 100, meta["mib"], base / (1024.0 * 1024.0),
                               A6A_TOL * 100)}]
    return []


# ---------------------------------------------------------------------------
# A6b：码率异常旗标（恒 warn-only）
# ---------------------------------------------------------------------------
def _legacy_bitrate_ref():
    """旧口径参照：现场探测 ace-step-ui 成片（CWD 相对路径）。仅作四级兜底，
    命中时调用方必须显式告警 —— 该参照件自身会随归一漂移（方案B 发现B 的成因）。"""
    p = A6B_DEFAULT_REF
    if os.path.isfile(p):
        try:
            return video_meta(p).get("mib_per_s")
        except InputError:
            return None
    return None


def _contract_bitrate_ref():
    """真源冻结参照：config/param_contract.json → audit_refs.a6b_ref_mib_per_s。

    返回 (value, source)；缺字段 → (None, "")，由调用方继续回退并告警。
    该值不随任何项目的归一/重编码漂移（方案B 发现B 修法 B：冻结 0.115 MiB/s）。
    """
    mod = _enc_module()
    if mod is None:
        return None, ""
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    try:
        val, src = mod.audit_ref(A6B_CONTRACT_KEY, root=root)
    except Exception as exc:  # noqa: BLE001
        print("WARN: A6b 真源参照读取失败（%s: %s）" % (type(exc).__name__, exc),
              file=sys.stderr)
        return None, ""
    if val is None:
        return None, ""
    try:
        return float(val), src
    except (TypeError, ValueError):
        print("WARN: A6b 真源参照非法（%r），按缺字段处理" % (val,), file=sys.stderr)
        return None, ""


def _story_bitrate_entries(raw):
    """从 per-story bitrate.json 抽出 {target: mib_per_s}（B 裁定 schema）。

    兼容两代形态：
      · v1.0（裁定 schema）：{"version":"1.0","captured_at":…,"entries":[{target,…,
        mib_per_s,size_bytes,duration_s,captured_from,captured_sha256}, …]}
      · 过渡扁平形态：{"mib_per_s": …} / {"ref_mib_per_s": …}（无 target，占位 "__flat__"）
    非法条目跳过（不 fail-closed，只是该 target 无参照 → 落真源）。
    """
    out = {}
    raw_entries = raw.get("entries")
    if isinstance(raw_entries, list):
        for ent in raw_entries:
            if not isinstance(ent, dict):
                continue
            tgt = ent.get("target")
            val = ent.get("mib_per_s")
            if not tgt or val is None:
                continue
            try:
                out[str(tgt)] = float(val)
            except (TypeError, ValueError):
                continue
    for key in ("mib_per_s", "ref_mib_per_s", "bitrate_ref_mib_per_s"):
        if raw.get(key) is not None:
            try:
                out.setdefault("__flat__", float(raw[key]) if not isinstance(raw[key], str)
                               else float(raw[key]))
            except (TypeError, ValueError):
                pass
            break
    return out


def write_story_bitrate_baseline(base_dir, video, meta):
    """写 per-story qc/baseline/bitrate.json（B 裁定 schema；**只在 --store-baseline 时写**）。

    · 只更新/追加**当前被测 target** 的那一条 entry，其余 target 条目原样保留 ——
      「绝不自动刷新」的落地方式：不传 --store-baseline 就完全不碰该文件。
    · captured_from 记调用来源（argv 摘要），captured_sha256 记被测件指纹，便于溯源对账。
    """
    import datetime
    entries = {}
    meta_p = os.path.join(base_dir, "bitrate.json")
    if os.path.isfile(meta_p):
        try:
            with open(meta_p, encoding="utf-8") as fh:
                prev = json.load(fh)
            for tgt, val in _story_bitrate_entries(prev).items():
                if tgt != "__flat__":
                    entries[tgt] = {"target": tgt, "mib_per_s": val,
                                    "size_bytes": None, "duration_s": None,
                                    "captured_from": "preserved", "captured_sha256": None}
        except (OSError, ValueError):
            pass
    raw = dict(entries.get(os.path.basename(video), {}))
    raw.update({
        "target": os.path.basename(video),
        "mib_per_s": round(float(meta["mib_per_s"]), 6) if meta["mib_per_s"] else None,
        "size_bytes": meta["bytes"],
        "duration_s": round(float(meta["duration"]), 3) if meta["duration"] else None,
        "captured_from": "frame_audit --store-baseline",
        "captured_sha256": _sha256_of(video),
    })
    entries[os.path.basename(video)] = raw
    doc = {
        "version": A6B_STORY_SCHEMA_VERSION,
        "captured_at": datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        "entries": [entries[k] for k in sorted(entries)],
    }
    with open(meta_p, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, ensure_ascii=False, indent=2)
    print("A6b per-story 参照已写（schema %s，target=%s，%.4f MiB/s）：%s"
          % (A6B_STORY_SCHEMA_VERSION, os.path.basename(video),
             float(meta["mib_per_s"] or 0.0), meta_p))
    return meta_p


def _story_bitrate_ref(video):
    """per-story 参照 qc/baseline/bitrate.json（B 裁定 schema；只读）。

    取条口径：优先进测件同名 target（douyin_epilogue.mp4）→ 次选 douyin.mp4（原片参照）
    → 仅一条 entry 时取之；命中即返回 (mib_per_s, "<path>#entries[<target>]")，
    取不到返回 (None, "")，由四级链落到真源冻结值。
    """
    if not video:
        return None, ""
    p = os.path.join(qc_dir(video), *A6B_STORY_BASELINE)
    if not os.path.isfile(p):
        return None, ""
    try:
        with open(p, encoding="utf-8") as fh:
            raw = json.load(fh)
    except (OSError, ValueError) as exc:
        print("WARN: A6b per-story 参照不可读（%s: %s）" % (type(exc).__name__, exc),
              file=sys.stderr)
        return None, ""
    if not isinstance(raw, dict):
        print("WARN: A6b per-story 参照格式非法（非对象）：%s" % p, file=sys.stderr)
        return None, ""
    entries = _story_bitrate_entries(raw)
    if not entries:
        print("WARN: A6b per-story 参照无可用 entry（需 version/captured_at/entries[]）：%s"
              % p, file=sys.stderr)
        return None, ""
    base = os.path.basename(video)
    for cand in (base, A5_TARGETS[0], A5_TARGETS[1]):
        if cand in entries:
            return entries[cand], "%s#entries[%s]" % (p, cand)
    if len(entries) == 1 and "__flat__" not in entries:
        tgt = next(iter(entries))
        return entries[tgt], "%s#entries[%s]" % (p, tgt)
    if "__flat__" in entries:
        return entries["__flat__"], "%s#mib_per_s" % p
    print("WARN: A6b per-story 参照无匹配 target（%s）：%s" % (base, p), file=sys.stderr)
    return None, ""


def resolve_bitrate_ref(cli_ref, video=None):
    """A6b 参照四级优先级（方案B 发现B 修法）：返回 (ref, source)。

    ① --bitrate-ref（CLI 显式，最高优先）
    ② per-story story/<proj>/qc/baseline/bitrate.json
    ③ 真源 config/param_contract.json → audit_refs.a6b_ref_mib_per_s（冻结值）
    ④ 旧口径：现场探测 ace-step-ui 参照件 —— 命中即显式 WARN 告警（可能已漂移）
    """
    if cli_ref is not None:
        return cli_ref, "cli:--bitrate-ref"
    v, src = _story_bitrate_ref(video)
    if v:
        return v, src
    v, src = _contract_bitrate_ref()
    if v:
        return v, src
    v = _legacy_bitrate_ref()
    if v:
        print("WARN: A6b 参照回退旧口径 —— 现场探测 %s = %.4f MiB/s；"
              "该参照件自身可能已随归一漂移（判据可能失真），"
              "建议核对真源 audit_refs.%s" % (A6B_DEFAULT_REF, v, A6B_CONTRACT_KEY),
              file=sys.stderr)
        return v, "legacy:%s" % A6B_DEFAULT_REF
    return None, ""


def run_a6b(meta, cli_ref, video=None):
    """MiB/s > A6B_RATIO × 参照 → 旗标；恒 warn，不进入阻断。"""
    if not meta["mib_per_s"]:
        return []
    ref, src = resolve_bitrate_ref(cli_ref, video)
    if not ref:
        return []
    ratio = meta["mib_per_s"] / float(ref)
    if ratio > A6B_RATIO:
        return [{"assertion": "A6b", "severity": "warn",
                 "mib_per_s": meta["mib_per_s"], "ref": ref, "ratio": round(ratio, 2),
                 "ref_source": src,
                 "message": "A6b 码率 %.3f MiB/s，为参照 %.3f 的 %.2f 倍"
                            "（阈值 %.0f×，参照来源 %s）——旗标仅触发排查，不阻断"
                            % (meta["mib_per_s"], ref, ratio, A6B_RATIO,
                               src or "unknown")}]
    return []


# ---------------------------------------------------------------------------
# A7：交付规格断言（S3 收口 · 判据唯一取自 encode_profile.assert_delivery_spec）
# ---------------------------------------------------------------------------
# 方案B 裁定（A7）：分字段分级、不连坐 —— sample_rate/channels/profile/level/pix_fmt
# = error，gop = warn；未点名字段默认 error（fail-closed）。判据**不得**在本文件重写
# 一套硬编码，一律转调 scripts/encode_profile.py::assert_delivery_spec()（全仓唯一判据）。
# 退出码沿用既有分叉：error → 阻断（exit 2）；判据不可用 / 登记非法 → InputError（exit 1）。
#
# ---- 交付规格豁免登记 schema（方案 B 给定，本仓唯一实现；不另立第二套登记） ----
# 落位 script.json **顶层键** delivery_spec_waiver（与 design_registry 同文件、同读取路径；
# frame_audit 的 --script 已强制）。条目 6 字段缺一即无效：
#   target（被测件 basename）/ target_sha256（64 位小写 hex，软失效锚点）/
#   fields（∈ A7_WAIVER_ALLOWED_FIELDS）/ reason / approved_by / expires_at（YYYY-MM-DD）
# 放行需四者同时成立：target 匹配 ∧ 字段在 fields 内 ∧ 当前件 sha256 == target_sha256 ∧ 未过期。
# 同一 target 多条登记判无效；fail-closed 口径对齐 design_ai_gate._registry_invalid_entries
# （任一条目非法 → 整次运行 exit 1 并列无效条目）。被抑制的 error 不删，改写
# severity=info 并附 waived/reason/approved_by/expires_at 留痕。失效两层独立：
# 软失效（sha 不符 = 成片已重建，报 INFO）/ 硬失效（超期 = 不予放行）。
A7_WAIVER_KEY = "delivery_spec_waiver"
A7_WAIVER_REQUIRED = ("target", "target_sha256", "fields", "reason", "approved_by", "expires_at")
A7_WAIVER_ALLOWED_FIELDS = ("sample_rate", "channels", "profile", "level", "pix_fmt", "gop")
A7_WAIVER_SHA_RE = re.compile(r"^[0-9a-f]{64}$")
A7_WAIVER_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
A7_WAIVER_MAX_DAYS = 90           # 时限上限 +90 天（建议 +30 天，仅登记规范、不代填）
A7_DEFAULT_GRADE = "error"                # 未被点名的规格字段按 error（fail-closed）
# (assert_delivery_spec 的 reason 前缀, 规格字段, 分级)；前缀须互不为前缀，长前缀在前
A7_FIELD_GRADE = (
    ("关键帧间隔", "gop", "warn"),
    ("音频采样率", "sample_rate", "error"),
    ("声道数", "channels", "error"),
    ("编码器", "vcodec", "error"),
    ("尺寸", "size", "error"),
    ("帧率", "fps", "error"),
    ("profile", "profile", "error"),
    ("level", "level", "error"),
    ("pix_fmt", "pix_fmt", "error"),
    ("音频", "acodec", "error"),
    ("码率", "bitrate", "error"),
    ("无法读取规格", "probe", "error"),
)
_ENC_MOD_CACHE = {"tried": False, "mod": None}
_ENC_PROFILE_CACHE = None


def _ensure_ffprobe_on_path():
    """把本仓解析到的 ffprobe 目录补进 PATH。

    encode_profile.probe_spec 走裸 `ffprobe`（依赖 PATH）；非登录 shell（如
    storyctl 经 nohup/子进程调用）下 PATH 可能不含工具安装目录，会让 A7
    误报「无法读取规格」并错记成片问题。此处只补 PATH，不复写任何探测/判据逻辑。
    找不到 ffprobe → InputError（编排器故障，exit 1），不降级成片问题。
    """
    probe = ffprobe()
    d = os.path.dirname(probe)
    cur = os.environ.get("PATH", "")
    if d and d not in cur.split(os.pathsep):
        os.environ["PATH"] = d + os.pathsep + cur
    return probe


def _enc_module():
    """加载单一真源读取器 / 全仓唯一交付判据（scripts/encode_profile.py）；失败返回 None。"""
    if not _ENC_MOD_CACHE["tried"]:
        _ENC_MOD_CACHE["tried"] = True
        sdir = os.path.dirname(os.path.abspath(__file__))
        try:
            if sdir not in sys.path:
                sys.path.insert(0, sdir)
            import encode_profile  # noqa: WPS433 —— 同目录脚本，运行时按需加载
            _ENC_MOD_CACHE["mod"] = encode_profile
        except Exception as exc:  # noqa: BLE001
            print(f"WARN: A7 判据不可用（encode_profile 加载失败：{exc}）", file=sys.stderr)
    return _ENC_MOD_CACHE["mod"]


def _enc_profile():
    """交付参数（真源派生，进程内缓存）。"""
    global _ENC_PROFILE_CACHE
    mod = _enc_module()
    if mod is None:
        return None
    if _ENC_PROFILE_CACHE is None:
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        _ENC_PROFILE_CACHE = mod.profile(root)
    return _ENC_PROFILE_CACHE


def _a7_grade(reason):
    """把 assert_delivery_spec 的一句 reason 归到 (规格字段, 分级)。"""
    text = str(reason or "")
    for prefix, field, grade in A7_FIELD_GRADE:
        if text.startswith(prefix):
            return field, grade
    return "unknown", A7_DEFAULT_GRADE


def _sha256_file(path):
    """成片 sha256（流式，64 位小写 hex）—— 豁免登记的软失效锚点。"""
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for blk in iter(lambda: fh.read(1 << 20), b""):
            h.update(blk)
    return h.hexdigest()


def _waiver_invalid_entries(entries):
    """逐条校验 delivery_spec_waiver：返回无效条目清单（空列表 = 全部有效）。

    fail-closed 口径对齐 design_ai_gate._registry_invalid_entries：任一条目非法 →
    整次运行 exit 1 并列出无效条目。额外一条校验：**同一 target 多条登记判无效**
    （歧义登记不允许静默择一）。
    """
    if not isinstance(entries, list):
        return [{"index": None, "target": None,
                 "missing": ["<delivery_spec_waiver 顶层键必须是数组>"]}]
    targets = [e.get("target") for e in entries if isinstance(e, dict)]
    dup = {t for t in targets if t and targets.count(t) > 1}
    invalid = []
    for i, ent in enumerate(entries):
        if not isinstance(ent, dict):
            invalid.append({"index": i, "target": None, "missing": ["<条目不是 JSON 对象>"]})
            continue
        bad = [k for k in A7_WAIVER_REQUIRED
               if ent.get(k) is None
               or (isinstance(ent.get(k), str) and not ent.get(k).strip())]
        flds = ent.get("fields")
        if isinstance(flds, list):
            if not flds:
                bad.append("fields（空数组）")
            else:
                off = [f for f in flds if f not in A7_WAIVER_ALLOWED_FIELDS]
                if off:
                    bad.append("fields（非法取值：%s）" % ",".join(str(x) for x in off))
        elif "fields" not in bad:
            bad.append("fields（必须是数组）")
        sha = ent.get("target_sha256")
        if isinstance(sha, str) and sha.strip() and not A7_WAIVER_SHA_RE.match(sha.strip()):
            bad.append("target_sha256（须为 64 位小写 hex）")
        exp = ent.get("expires_at")
        if isinstance(exp, str) and exp.strip() and not A7_WAIVER_DATE_RE.match(exp.strip()):
            bad.append("expires_at（须为 YYYY-MM-DD）")
        if ent.get("target") in dup:
            bad.append("target（同一 target 存在多条登记，判无效）")
        if bad:
            invalid.append({"index": i, "target": ent.get("target"), "missing": bad})
    return invalid


def _a7_waivers(script_data):
    """读 script.json 顶层 delivery_spec_waiver（方案 B schema）。**只读**，不改任何登记。

    未登记（键缺失）→ 空表（不豁免，但不算错）；键存在但条目非法 → InputError（exit 1）。
    """
    entries = (script_data or {}).get(A7_WAIVER_KEY)
    if entries is None:
        return []
    invalid = _waiver_invalid_entries(entries)
    if invalid:
        raise InputError(
            "delivery_spec_waiver 登记非法（fail-closed → exit 1）；无效条目：%s"
            % json.dumps(invalid, ensure_ascii=False))
    return list(entries)


def _a7_waiver_hit(field, target, cur_sha, waivers, today):
    """返回 (登记, 放行?, 失效原因) —— 放行需四条同时成立。

    target 匹配 ∧ 字段在 fields 内 ∧ 当前件 sha256 == target_sha256 ∧ 未过期。
    未放行时 why ∈ {soft（sha 不符，成片已重建）, hard（超期）}；未命中登记 → (None, False, "")。
    """
    for w in waivers:
        if str(w.get("target") or "") != target:
            continue
        if field.lower() not in [str(f).lower() for f in (w.get("fields") or [])]:
            continue
        exp = str(w.get("expires_at") or "").strip()[:10]
        if exp and today > exp:
            return w, False, "hard"
        reg_sha = str(w.get("target_sha256") or "").strip()
        if A7_WAIVER_SHA_RE.match(reg_sha) and reg_sha != cur_sha:
            return w, False, "soft"
        return w, True, ""
    return None, False, ""


def run_a7(video, script_data=None):
    """A7 交付规格断言：判据唯一取自 encode_profile.assert_delivery_spec()。

    video：待审成片（douyin.mp4 或 douyin_epilogue.mp4 —— qc 段2 的被测件即片尾件，
    故 A7 天然覆盖 epilogue）。script_data：script.json 内容，供读 delivery_spec_waiver。
    判据模块/真源不可用、或登记非法 → InputError（exit 1；拒绝静默跳过交付断言）。
    """
    mod = _enc_module()
    if mod is None:
        raise InputError("A7 交付判据不可用：scripts/encode_profile.py 未加载"
                         "（编排器故障，拒绝跳过交付规格断言）")
    _ensure_ffprobe_on_path()
    ok, reasons = mod.assert_delivery_spec(video, _enc_profile())
    if ok:
        return []
    waivers = _a7_waivers(script_data)   # 非法登记 → InputError（exit 1，fail-closed）
    today = time.strftime("%Y-%m-%d")
    target = os.path.basename(video)
    cur_sha = _sha256_file(video)
    out, soft = [], {}
    for reason in reasons:
        field, grade = _a7_grade(reason)
        w, passed, why = _a7_waiver_hit(field, target, cur_sha, waivers, today)
        if w is not None and why == "hard":
            out.append({"assertion": "A7", "severity": grade, "field": field,
                        "message": "A7 交付规格未达标：%s（登记豁免已于 %s 过期 —— "
                                   "硬失效，不予放行）"
                                   % (reason, str(w.get("expires_at")).strip()[:10])})
            continue
        if w is not None and why == "soft":
            out.append({"assertion": "A7", "severity": grade, "field": field,
                        "message": "A7 交付规格未达标：%s（登记豁免软失效："
                                   "成片已重建，sha 不符）" % reason})
            soft.setdefault(id(w), {"w": w, "fields": []})["fields"].append(field)
            continue
        if w is not None and passed:
            # 被抑制的 error 不删：改写 severity=info 并附豁免留痕
            out.append({"assertion": "A7", "severity": "info", "field": field,
                        "waived": True, "reason": w.get("reason"),
                        "approved_by": w.get("approved_by"),
                        "expires_at": w.get("expires_at"),
                        "message": "A7 交付规格未达标（已登记豁免至 %s，批准 %s，理由：%s）：%s"
                                   % (str(w.get("expires_at")).strip()[:10],
                                      w.get("approved_by"), w.get("reason"), reason)})
            continue
        out.append({"assertion": "A7", "severity": grade, "field": field,
                    "message": "A7 交付规格未达标：%s" % reason})
    for it in soft.values():   # 软失效独立报 INFO（机器可判：下次出片前必须归一）
        w = it["w"]
        out.append({"assertion": "A7", "severity": "info",
                    "field": ",".join(sorted(set(it["fields"]))),
                    "message": "A7 豁免软失效（INFO）：target=%s 登记 sha256=%s 与当前件 "
                               "sha256=%s 不符 —— 成片已重建，下次出片前必须归一或重签登记"
                               "（批准 %s，有效期至 %s）"
                               % (w.get("target"), w.get("target_sha256"), cur_sha,
                                  w.get("approved_by"), str(w.get("expires_at")).strip()[:10])})
    return out

# ---------------------------------------------------------------------------
# 报告与主流程
# ---------------------------------------------------------------------------
ASSERTION_ORDER = ["A0", "A1", "A2", "A3", "A4", "A5", "A6a", "A6b", "A7"]


def _write_report(path, report):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=2)


def _format(f):
    loc = ""
    if f.get("scene"):
        loc += " " + f["scene"]
    if f.get("t") is not None:
        loc += " t=%.2fs" % f["t"]
    if f.get("bbox"):
        loc += " " + fmt_bbox(f["bbox"])
    return "  [%s] %s%s\n      %s" % (f["severity"].upper(), f["assertion"],
                                      loc, f["message"])


def main(argv=None):
    a = parse_args(None if argv is None else argv)
    try:
        if not os.path.isfile(a.video):
            raise InputError(f"视频不存在：{a.video}")
        if not os.path.isfile(a.script):
            raise InputError(f"script 不存在：{a.script}")
        if a.ref and not os.path.isfile(a.ref):
            raise InputError(f"--ref 视频不存在：{a.ref}")
        if a.html and not os.path.isfile(a.html):
            raise InputError(f"--html 不存在：{a.html}")
        if a.baseline and not (os.path.isfile(a.baseline) or os.path.isdir(a.baseline)):
            raise InputError(f"--baseline 既非文件也非目录：{a.baseline}")

        meta = video_meta(a.video)
        script_data, total_duration = load_script(a.script)
        scenes = scene_windows(script_data, meta["duration"])
    except InputError as e:
        print(f"错误：{e}", file=sys.stderr)
        return 1

    findings = []
    try:
        if a.store_baseline:
            base = store_baseline(a.video, meta, script_data,
                                  html_path=a.html, script_path=a.script)
            print(f"基线已写入：{base}")
        if a.baseline:
            findings += run_a0(a.video, a.baseline, meta,
                               html_path=a.html, script_path=a.script,
                               same_source=a.same_source)
        findings += run_a1(a.video)
        findings += run_a2(a.video, scenes, ref=a.ref)
        if a.ref:
            findings += run_a3(a.video, a.ref, scenes)
        findings += run_a4(a.video, scenes, html=a.html)
        findings += run_a5(meta, script_data, total_duration,
                           video=a.video, duration_expected=a.duration_expected)
        findings += run_a6a(a.video, meta, a.size_baseline)
        findings += run_a6b(meta, a.bitrate_ref, video=a.video)
        findings += run_a7(a.video, script_data)
    except InputError as e:
        print(f"错误：{e}", file=sys.stderr)
        return 1

    findings.sort(key=lambda f: (ASSERTION_ORDER.index(f["assertion"])
                                if f["assertion"] in ASSERTION_ORDER else 99,
                                f["severity"] != "error"))
    blockers = [] if a.warn_only else \
        [f for f in findings if f["severity"] == "error"]

    report = {
        "video": a.video, "script": a.script, "ref": a.ref,
        "warn_only": bool(a.warn_only),
        "meta": {k: meta[k] for k in ("width", "height", "fps", "duration",
                                      "nb_frames", "has_audio", "audio_duration",
                                      "bytes", "mib", "mib_per_s")},
        "scenes": [{"name": n, "start": s, "end": e} for n, s, e in scenes],
        "findings": findings,
        "blocked": bool(blockers),
    }
    out_path = a.json_out or os.path.join(qc_dir(a.video), "report.json")
    _write_report(out_path, report)

    if not findings:
        print("OK：A0–A6 全部通过，无告警")
    else:
        print("检出 %d 处问题（阻断 %d）：" % (len(findings), len(blockers)))
        for f in findings:
            print(_format(f))
    print("报告：" + out_path)

    if a.warn_only:
        return 0
    return 2 if blockers else 0


if __name__ == "__main__":
    sys.exit(main())
