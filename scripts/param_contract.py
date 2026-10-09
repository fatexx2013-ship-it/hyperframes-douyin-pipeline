#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
param_contract.py —— 参数快照（snapshot）与漂移比对（diff）

所属产线：/Volumes/PSSD/抖音视频（Python + FFmpeg + HyperFrames 竖屏短视频）
参数合同：config/param_contract.json（contract_version 1.0.0）
资料来源：AI-Film-Studio (qpzRm) 通用参数漂移清单 10 项 + 两级负控节奏

设计要点
--------
1. 快照对象是「一次真实产出的成片」，而不是单段中间产物出口——漂移只在拼接/交付边界暴露。
2. 视频侧参数一律用 ffprobe 实测（fps 取 r_frame_rate 有理数精确值）；
   配置侧参数（模型权重、精度、分块/降级）从项目现有配置文件与脚本读取。
3. 判定分两级：不变量级 → FAIL（阻断，退出码 2）；探索级 → WARN（不阻断）。
4. 版本类字段（model_weight_version / vae_version 的替代物）不与固定值绑定，
   只做 manifest 对 manifest 的基线对照。

用法
----
  # 1) 快照：从一次真实成片抽参数，产出 run manifest
  python3 scripts/param_contract.py snapshot --video github_trending.mp4 \
      --label baseline-github-trending --out reports/artifacts/manifest_a.json

  # 2) 比对：两份 manifest（含合同口径校验）
  python3 scripts/param_contract.py diff <baseline.json> <current.json>

  # 3) 单份校验：只对合同口径
  python3 scripts/param_contract.py check <manifest.json>

退出码：0 = 无阻断（含仅 WARN）；2 = 存在不变量级漂移；1 = 用法/环境错误
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime

MANIFEST_VERSION = "1.1.0"
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DEFAULT = os.path.dirname(SCRIPT_DIR)
CONTRACT_DEFAULT = os.path.join(ROOT_DEFAULT, "config", "param_contract.json")
CANONICALIZATION_DEFAULT = os.path.join(ROOT_DEFAULT, "config", "canonicalization.json")
FROZEN_BASELINE_DEFAULT = os.path.join(ROOT_DEFAULT, "config", "frozen_baseline.json")
PEAKS_DIR = os.path.join(ROOT_DEFAULT, "reports", "peaks")
DEFAULT_MODEL_DIR = os.path.expanduser(
    "~/Projects/qwen3-tts-apple-silicon/models/Qwen3-TTS-12Hz-1.7B-Base-8bit"
)
BREW_BIN = "/opt/homebrew/bin"

SEVERITY = {"OK": 0, "SKIP": 1, "WARN": 2, "FAIL": 3}


# ─────────────────────────────────────────────────────────────
# 基础工具
# ─────────────────────────────────────────────────────────────

def _pick(verdicts, empty_reason):
    """从多个判定中取最严重的一个。"""
    if not verdicts:
        return "SKIP", empty_reason
    return max(verdicts, key=lambda v: SEVERITY.get(v[0], 0))


def _first_exec(cands):
    for c in cands:
        if c and os.path.isfile(c) and os.access(c, os.X_OK):
            return c
    return None


def find_tool(name: str):
    """定位可执行文件：环境变量 → PATH → Homebrew/macOS 常见路径。"""
    return _first_exec([
        os.environ.get(name.upper().replace("-", "_")),
        shutil.which(name),
        os.path.join(BREW_BIN, name),
        os.path.join("/usr/local/bin", name),
        os.path.join("/opt/homebrew/opt/ffmpeg-full/bin", name),
        os.path.join("/usr/bin", name),
    ])


def brew_env():
    env = dict(os.environ)
    env["PATH"] = BREW_BIN + ":/usr/local/bin:" + env.get("PATH", "")
    return env


def now_iso():
    return datetime.now().strftime("%Y-%m-%dT%H:%M:%S")


def read_json(path, default=None):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def run(cmd, env=None, timeout=60):
    try:
        return subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=timeout)
    except Exception as e:  # noqa: BLE001
        return None if False else type("R", (), {"stdout": "", "stderr": str(e), "returncode": -1})()


def rational_to_float(s):
    if not s or s in ("0/0", "N/A"):
        return None
    try:
        if "/" in str(s):
            num, den = str(s).split("/")
            den = float(den)
            return round(float(num) / den, 6) if den else None
        return round(float(s), 6)
    except Exception:
        return None


def gcd_aspect(w, h):
    try:
        from math import gcd
        g = gcd(int(w), int(h))
        return f"{int(w) // g}:{int(h) // g}"
    except Exception:
        return "unknown"


def sha256_file(path, chunk=1 << 20):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(chunk), b""):
            h.update(block)
    return h.hexdigest()


def file_fingerprint(path):
    st = os.stat(path)
    size = st.st_size
    if size <= 200 * 1024 * 1024:
        try:
            return {"sha256": sha256_file(path), "mode": "full-content",
                    "size_bytes": size, "mtime": int(st.st_mtime)}
        except Exception:
            pass
    # 超大文件：头部 4MB + 尾部 4MB 的分段哈希
    h = hashlib.sha256()
    with open(path, "rb") as f:
        h.update(f.read(4 << 20))
        if size > (8 << 20):
            f.seek(-(4 << 20), os.SEEK_END)
            h.update(f.read(4 << 20))
    return {"sha256": h.hexdigest(), "mode": "head-tail-4MB",
            "size_bytes": size, "mtime": int(st.st_mtime)}


def dir_fingerprint(path, deep=False):
    """模型目录指纹：默认用「相对路径|大小|mtime」清单哈希（快）；deep 时逐文件内容哈希。"""
    if not path or not os.path.isdir(path):
        return None
    entries = []
    total = 0
    for root, dirs, files in os.walk(path):
        dirs.sort()
        for name in sorted(files):
            if name.startswith("."):
                continue
            fp = os.path.join(root, name)
            try:
                st = os.stat(fp)
            except Exception:
                continue
            rel = os.path.relpath(fp, path)
            total += st.st_size
            if deep:
                try:
                    entries.append(f"{rel}|{sha256_file(fp)}")
                except Exception:
                    entries.append(f"{rel}|ERR")
            else:
                entries.append(f"{rel}|{st.st_size}|{st.st_mtime_ns}")
    if not entries:
        return None
    digest = hashlib.sha256("\n".join(entries).encode("utf-8")).hexdigest()
    return {
        "fingerprint": "sha256:" + digest[:32],
        "mode": "deep-content" if deep else "metadata-manifest",
        "file_count": len(entries),
        "total_bytes": total,
        "path": path,
    }


# ─────────────────────────────────────────────────────────────
# ffprobe
# ─────────────────────────────────────────────────────────────

def probe_video(video):
    ffprobe = find_tool("ffprobe")
    if not ffprobe:
        raise RuntimeError("未找到 ffprobe（可设环境变量 FFPROBE 指定绝对路径）")
    r = run([ffprobe, "-v", "error", "-print_format", "json",
             "-show_streams", "-show_format", video], timeout=120)
    if not r or r.returncode != 0:
        raise RuntimeError(f"ffprobe 读取失败：{(r.stderr or '').strip()[:200]}")
    data = json.loads(r.stdout or "{}")
    vs = next((s for s in data.get("streams", []) if s.get("codec_type") == "video"), None)
    aus = next((s for s in data.get("streams", []) if s.get("codec_type") == "audio"), None)
    fmt = data.get("format", {}) or {}

    vout = None
    if vs:
        w, h = vs.get("width"), vs.get("height")
        rfr = vs.get("r_frame_rate")
        vout = {
            "codec": vs.get("codec_name"),
            "profile": vs.get("profile"),
            "level": vs.get("level"),
            "width": w, "height": h,
            "resolution": f"{w}x{h}",
            "aspect_ratio": gcd_aspect(w, h) if (w and h) else "unknown",
            "r_frame_rate_rational": rfr,
            "fps": rational_to_float(rfr),
            "avg_frame_rate": vs.get("avg_frame_rate"),
            "avg_fps": rational_to_float(vs.get("avg_frame_rate")),
            "pix_fmt": vs.get("pix_fmt"),
            "color_space": vs.get("color_space"),
            "color_transfer": vs.get("color_transfer"),
            "color_primaries": vs.get("color_primaries"),
            "duration": float(vs["duration"]) if vs.get("duration") else None,
            "nb_frames": int(vs["nb_frames"]) if str(vs.get("nb_frames", "")).isdigit() else None,
            "bit_rate": int(vs["bit_rate"]) if str(vs.get("bit_rate", "")).isdigit() else None,
        }
    aout = None
    if aus:
        aout = {
            "codec": aus.get("codec_name"),
            "sample_rate_hz": int(aus["sample_rate"]) if str(aus.get("sample_rate", "")).isdigit() else None,
            "channels": aus.get("channels"),
            "channel_layout": aus.get("channel_layout"),
            "duration": float(aus["duration"]) if aus.get("duration") else None,
            "bit_rate": int(aus["bit_rate"]) if str(aus.get("bit_rate", "")).isdigit() else None,
        }
    return {
        "video": vout,
        "audio": aout,
        "format": {
            "duration": float(fmt["duration"]) if str(fmt.get("duration", "")).replace(".", "", 1).isdigit() else None,
            "bit_rate": int(fmt["bit_rate"]) if str(fmt.get("bit_rate", "")).isdigit() else None,
            "format_name": fmt.get("format_name"),
        },
    }


# ─────────────────────────────────────────────────────────────
# 配置侧读取
# ─────────────────────────────────────────────────────────────

def parse_render_sh(root):
    path = os.path.join(root, "scripts", "render.sh")
    txt = ""
    if os.path.isfile(path):
        try:
            txt = open(path, "r", encoding="utf-8", errors="ignore").read()
        except Exception:
            txt = ""
    if not txt:
        return None
    out = {}
    for key in ("VIDEO_WIDTH", "VIDEO_HEIGHT", "FPS", "CRF", "HF_ENCODER",
                "HF_VIDEO_BITRATE", "HF_MAXRATE", "HF_BUFSIZE", "HF_PRESET"):
        m = re.search(rf'{key}="?\$\{{{key}:-([^}}"]+)\}}"?', txt)
        if m:
            v = m.group(1)
            out[key] = int(v) if v.isdigit() else v
    out["_source"] = "scripts/render.sh"
    return out or None


def parse_post_process(root):
    path = os.path.join(root, "post_process.py")
    if not os.path.isfile(path):
        return None
    txt = open(path, "r", encoding="utf-8", errors="ignore").read()
    out = {"_source": "post_process.py"}
    for key in ("TARGET_WIDTH", "TARGET_HEIGHT", "TARGET_FPS", "TARGET_MAX_BITRATE",
                "DOUYIN_AUDIO_BITRATE", "DOUYIN_VIDEO_BITRATE"):
        m = re.search(rf'^{key}\s*=\s*([^\n#]+)', txt, re.M)
        if m:
            raw = m.group(1).strip().strip('"').strip("'")
            try:
                out[key] = float(raw) if "." in raw else int(raw)
            except ValueError:
                out[key] = raw
    m = re.search(r'"?-ar"?\s*,\s*"(\d+)"', txt)
    if m:
        out["AUDIO_SAMPLE_RATE"] = int(m.group(1))
    return out


def parse_tts(root, model_dir):
    path = os.path.join(root, "generate_qa_video.py")
    if not os.path.isfile(path):
        return None
    txt = open(path, "r", encoding="utf-8", errors="ignore").read()
    out = {"_source": "generate_qa_video.py"}
    m = re.search(r'TTS_ENGINE\s*=\s*"([^"]+)"', txt)
    if m:
        out["engine"] = m.group(1)
    m = re.search(r'load_model\(os\.path\.join\("[^"]*",\s*"([^"]+)"\)\)', txt)
    if m:
        out["loaded_model_ref"] = m.group(1)
    ar = re.search(r'"-ar",\s*"(\d+)"', txt)
    ac = re.search(r'"-ac",\s*"(\d+)"', txt)
    if ar:
        out["output_sample_rate_hz"] = int(ar.group(1))
    if ac:
        out["output_channels"] = int(ac.group(1))

    # 采样参数是否显式固定（清单第 6 项在本产线的对应物）
    explicit_keys = [k for k in ("temperature", "top_p", "top_k", "seed", "repetition_penalty")
                     if re.search(rf'generate_audio\([^)]*{k}\s*=', txt, re.S)]
    out["explicit_sampling_params"] = bool(explicit_keys)
    out["sampling_param_keys"] = explicit_keys
    out["sampling_params"] = {}
    for k in explicit_keys:
        m = re.search(rf'generate_audio\([^)]*\b{k}\s*=\s*([0-9][0-9\.eE+-]*)', txt, re.S)
        if m:
            raw = m.group(1)
            try:
                out["sampling_params"][k] = float(raw) if ("." in raw or "e" in raw.lower()) else int(raw)
            except ValueError:
                pass
    if "seed" not in out["sampling_params"]:
        m = re.search(r'^\s*SEED\s*=\s*([0-9]+)', txt, re.M)
        if m:
            out["sampling_params"]["seed"] = int(m.group(1))

    out["model_dir"] = model_dir
    out["model_dir_exists"] = bool(model_dir and os.path.isdir(model_dir))
    # 精度模式：从模型目录名推断（-8bit → int8）
    name = os.path.basename(model_dir or "")
    memset = re.search(r'(\d+)bit', name)
    if memset:
        out["precision_mode"] = "int8" if memset.group(1) == "8" else f"int{memset.group(1)}"
    else:
        out["precision_mode"] = None
    fp = dir_fingerprint(model_dir, deep=False)
    if fp:
        out["model_fingerprint"] = fp
    return out


def parse_story_dir(story_dir):
    if not story_dir or not os.path.isdir(story_dir):
        return None
    out = {"_source": story_dir}
    hf = read_json(os.path.join(story_dir, "hyperframes.json"))
    if hf:
        out["hyperframes"] = {
            "fps": hf.get("fps"),
            "width": hf.get("width"),
            "height": hf.get("height"),
            "duration": hf.get("duration"),
            "scene_count": len(hf.get("scenes", [])) if isinstance(hf.get("scenes"), list) else None,
            "scenes": hf.get("scenes") if isinstance(hf.get("scenes"), list) else None,
        }
    script = read_json(os.path.join(story_dir, "script.json"))
    if script:
        out["script_total_duration"] = script.get("total_duration")
        out["script_scene_count"] = len(script.get("scenes", [])) if isinstance(script.get("scenes"), list) else None
    timing = read_json(os.path.join(story_dir, "timing.json"))
    if isinstance(timing, list):
        out["timing_line_count"] = len(timing)
    # 变更事件通道：render_window_frames 等硬停字段的放行依据（无文件即无事件）
    ce = read_json(os.path.join(story_dir, "change_events.json"))
    if ce:
        out["change_events"] = ce.get("events") if isinstance(ce, dict) else ce
    # 渲染分块产物
    for sub in ("hf/renders", "renders", "hf"):
        d = os.path.join(story_dir, sub)
        if os.path.isdir(d):
            n = len([f for f in os.listdir(d) if f.endswith(".mp4")])
            if n:
                out.setdefault("render_artifacts", {})[sub] = n
    # 自动降级标记（渲染/处理日志）
    flags = []
    for root, dirs, files in os.walk(story_dir):
        dirs[:] = [d for d in dirs if d not in ("_normalized",)]
        for name in files:
            if name.endswith((".log", ".txt")):
                try:
                    t = open(os.path.join(root, name), "r", encoding="utf-8", errors="ignore").read()
                except Exception:
                    continue
                if re.search(r"downgrad|降级|fallback|回退", t, re.I):
                    flags.append(os.path.relpath(os.path.join(root, name), story_dir))
    out["downgrade_flags"] = flags
    return out


def toolchain_versions(root):
    out = {}
    for name in ("ffmpeg", "ffprobe"):
        p = find_tool(name)
        if not p:
            out[name] = {"version": None, "path": None}
            continue
        r = run([p, "-version"], timeout=20)
        first = (r.stdout or "").splitlines()[0] if r and r.stdout else ""
        m = re.search(r"version\s+([0-9][^\s]*)", first)
        out[name] = {"version": m.group(1) if m else None, "path": p}
    hyper = find_tool("hyperframes")
    if hyper:
        r = run([hyper, "--version"], env=brew_env(), timeout=60)
        v = ((r.stdout or "") + (r.stderr or "")).strip().splitlines()
        out["hyperframes"] = {"version": v[-1].strip() if v else None, "path": hyper}
    else:
        out["hyperframes"] = {"version": None, "path": None}
    node = find_tool("node")
    out["node"] = {"version": ((run([node, "--version"], env=brew_env(), timeout=20).stdout or "").strip() or None) if node else None,
                   "path": node}
    return out


# ─────────────────────────────────────────────────────────────
# 扩展层：规范化器 / 冻结基线 / 峰值内存
# 资料来源：AI-Film-Studio 第二条私信 2026-09-26（8 字段漂移清单 + normalize_point 枚举）
# ─────────────────────────────────────────────────────────────

def load_canonicalizer():
    # normalize_point 枚举真源；顺序与签名同进签名域
    cfg = read_json(CANONICALIZATION_DEFAULT)
    if not cfg:
        return {"available": False, "canonicalizer_version": None, "signature": None,
                "order": None, "normalizer": None}
    return {
        "available": True,
        "canonicalizer_version": cfg.get("canonicalizer_version"),
        "signature": cfg.get("signature"),
        "order": cfg.get("normalize_point_order"),
        "normalizer": "scripts/normalize_point.py",
    }


def load_frozen_baseline():
    fb = read_json(FROZEN_BASELINE_DEFAULT)
    if not fb:
        return {"available": False, "digest": None, "ref_manifest": None, "label": None}
    fb["available"] = True
    return fb


def _normalize_text(text):
    # 走 normalize_point 枚举；不可用时退化为原样（报告标注 normalize_point_applied）
    try:
        if SCRIPT_DIR not in sys.path:
            sys.path.insert(0, SCRIPT_DIR)
        import normalize_point as npt
        return npt.normalize_text(text), True
    except Exception:
        return text, False


def canonical_digest(manifest):
    # 冻结基线重判：只取判定相关子集，规范化后取 sha256
    subset = {
        "label": manifest.get("label"),
        "video_fingerprint": (manifest.get("video_fingerprint") or {}).get("sha256"),
        "derived": manifest.get("derived"),
    }
    text = json.dumps(subset, ensure_ascii=False, sort_keys=True, indent=2)
    norm, ok = _normalize_text(text)
    return "sha256:" + hashlib.sha256(norm.encode("utf-8")).hexdigest(), ok


def latest_peak_profile():
    # 分阶段峰值记录法产物：取最新一份含 peak_overall 的 render_*.json
    if not os.path.isdir(PEAKS_DIR):
        return None, None
    cands = []
    for name in os.listdir(PEAKS_DIR):
        if name.startswith("render_") and name.endswith(".json"):
            p = os.path.join(PEAKS_DIR, name)
            cands.append((os.path.getmtime(p), p))
    for _, p in sorted(cands, reverse=True):
        prof = read_json(p) or {}
        if (prof.get("peak_overall") or {}).get("bytes"):
            return p, prof
    return None, None


def build_extended(v, a, fmt, story_cfg, tts, root, duration):
    # 扩展判定层 8 字段的原始证据（值取自实测与配置真源，不做判定）
    fps = v.get("fps")
    frames = None
    if duration is not None and fps:
        frames = int(round(float(duration) * float(fps)))

    w, h = v.get("width"), v.get("height")
    short_edge = min([int(x) for x in (w, h) if x]) if (w or h) else None

    peak_src, prof = latest_peak_profile()
    peak_gib = None
    if prof:
        peak_gib = round(((prof.get("peak_overall") or {}).get("bytes") or 0) / (1024 ** 3), 3)

    keys = (tts or {}).get("sampling_param_keys") or []
    params = (tts or {}).get("sampling_params") or {}
    seed_val = params.get("seed")
    explicit = bool((tts or {}).get("explicit_sampling_params"))

    canon = load_canonicalizer()
    fb = load_frozen_baseline()
    recomputed = None
    if fb.get("ref_manifest"):
        ref_path = fb["ref_manifest"]
        if not os.path.isabs(ref_path):
            ref_path = os.path.join(root, ref_path)
        ref_m = read_json(ref_path)
        if ref_m:
            recomputed, _ = canonical_digest(ref_m)

    return {
        "render_window_frames": {"value": frames, "fps": fps, "duration": duration},
        "resolution_short_edge": {"value": short_edge, "width": w, "height": h},
        "peak_vram": {"value_gib": peak_gib, "source": peak_src,
                      "note": "Mac 统一内存无独立显存，以分阶段 RSS 峰值近似"},
        "seed": {"value": seed_val, "explicit": explicit, "keys": keys},
        "tolerance_value": {"value": None, "source": "contract.tolerance_policy"},
        "canonicalizer_version": {"value": canon.get("signature"),
                                  "version": canon.get("canonicalizer_version"),
                                  "source": "config/canonicalization.json"},
        "expected_n": {"value": None, "source": "contract.expected_n_policy"},
        "frozen_baseline_digest": {"value": fb.get("digest"), "recomputed": recomputed,
                                   "ref_manifest": fb.get("ref_manifest"),
                                   "source": "config/frozen_baseline.json"},
        "change_events": ((story_cfg or {}).get("change_events") or []),
        "frozen_state": {"window": bool(fb.get("available"))},
    }


# ─────────────────────────────────────────────────────────────
# 快照
# ─────────────────────────────────────────────────────────────

def build_manifest(video, story_dir=None, model_dir=None, label=None, deep_hash=False,
                   root=ROOT_DEFAULT, with_toolchain=True):
    if not os.path.isfile(video):
        raise RuntimeError(f"成片不存在：{video}")
    probe = probe_video(video)
    v = probe["video"] or {}
    a = probe["audio"] or {}
    fmt = probe["format"] or {}

    story_cfg = parse_story_dir(story_dir)
    declared = None
    if story_cfg:
        declared = story_cfg.get("script_total_duration")
        if declared is None and story_cfg.get("hyperframes"):
            declared = story_cfg["hyperframes"].get("duration")

    duration = fmt.get("duration")
    delta = None
    if declared is not None and duration is not None:
        delta = round(duration - float(declared), 3)

    model_dir = model_dir or DEFAULT_MODEL_DIR
    tts = parse_tts(root, model_dir)

    derived = {
        "fps": {"value": v.get("fps"), "rational": v.get("r_frame_rate_rational"),
                "avg_fps": v.get("avg_fps")},
        "segment_duration": {"duration": duration, "declared_duration": declared, "delta": delta},
        "resolution_aspect": {"resolution": v.get("resolution"), "aspect_ratio": v.get("aspect_ratio"),
                              "width": v.get("width"), "height": v.get("height")},
        "colorspace_gamma": {"value": v.get("color_space") or "unspecified",
                             "color_space": v.get("color_space"),
                             "color_transfer": v.get("color_transfer"),
                             "color_primaries": v.get("color_primaries")},
        "model_weight_version": (tts or {}).get("model_fingerprint") or
                                {"fingerprint": None, "mode": "unavailable"},
        "sampler_steps_cfg_seed": {"explicit": bool((tts or {}).get("explicit_sampling_params")),
                                   "params": (tts or {}).get("sampling_params") or {},
                                   "keys": (tts or {}).get("sampling_param_keys") or []},
        "precision_mode": {"value": (tts or {}).get("precision_mode"),
                           "source": "model dir name"},
        "vae_version": {"value": None, "substitute": "toolchain_pins.ffmpeg",
                        "substitute_value": None},
        "audio_sample_rate_channels": {"sample_rate_hz": a.get("sample_rate_hz"),
                                       "channels": a.get("channels"),
                                       "channel_layout": a.get("channel_layout")},
        "chunk_size_auto_downgrade": {
            "render_chunk_mode": None, "scene_count": None,
            "render_artifacts": (story_cfg or {}).get("render_artifacts"),
            "auto_downgrade": None, "downgrade_flags": (story_cfg or {}).get("downgrade_flags"),
        },
    }
    if story_cfg:
        hf = story_cfg.get("hyperframes") or {}
        scenes = hf.get("scene_count")
        derived["chunk_size_auto_downgrade"]["scene_count"] = scenes
        if scenes:
            derived["chunk_size_auto_downgrade"]["render_chunk_mode"] = "per-scene"
        flags = story_cfg.get("downgrade_flags")
        derived["chunk_size_auto_downgrade"]["auto_downgrade"] = bool(flags)

    manifest = {
        "manifest_version": MANIFEST_VERSION,
        "generated_at": now_iso(),
        "label": label or os.path.basename(video),
        "video_path": os.path.abspath(video),
        "video_fingerprint": file_fingerprint(video),
        "story_dir": os.path.abspath(story_dir) if story_dir else None,
        "root": os.path.abspath(root),
        "video_side": probe,
        "config_side": {
            "render_sh": parse_render_sh(root),
            "post_process": parse_post_process(root),
            "tts": tts,
            "story": story_cfg,
        },
        "derived": derived,
    }
    if with_toolchain:
        manifest["toolchain"] = toolchain_versions(root)
        derived["vae_version"]["substitute_value"] = (manifest["toolchain"].get("ffmpeg") or {}).get("version")

    # 扩展判定层证据（AI-Film-Studio 第二条私信 8 字段）
    manifest["extended"] = build_extended(v, a, fmt, story_cfg, tts, root, duration)
    return manifest


# ─────────────────────────────────────────────────────────────
# 判定
# ─────────────────────────────────────────────────────────────

def _judge_fps(fdef, b, c):
    out = []
    tol = fdef.get("tolerance", 0.01)
    exp = fdef.get("expected")
    if c and c.get("value") is not None:
        if exp is not None and abs(float(c["value"]) - float(exp)) > tol:
            out.append(("FAIL", f"实际 {c['value']} fps ≠ 合同 {exp} fps"))
        else:
            out.append(("OK", f"{c['value']} fps 符合合同"))
    if b and c and b.get("value") is not None and c.get("value") is not None:
        if abs(float(b["value"]) - float(c["value"])) > tol:
            out.append(("FAIL", f"相对基线 {b['value']} → {c['value']} fps（时基变更）"))
    return _pick(out, "无 fps 数据")


def _judge_segment_duration(fdef, b, c):
    tol = fdef.get("tolerance_sec", 0.1)
    out = []
    if c:
        if c.get("declared_duration") is None:
            out.append(("SKIP", "无声明时长参照（散片），本字段不计入判定"))
        elif c.get("delta") is not None and abs(c["delta"]) > tol:
            out.append(("WARN", f"成片 {c['duration']}s 与声明 {c['declared_duration']}s 差 {c['delta']:+.3f}s > 容差 {tol}s"))
        else:
            out.append(("OK", f"Δ={c.get('delta'):+.3f}s 在容差 {tol}s 内"))
    if b and c and b.get("duration") and c.get("duration") and fdef.get("compare_across_runs"):
        if abs(b["duration"] - c["duration"]) > tol:
            out.append(("WARN", f"相对基线 {b['duration']}s → {c['duration']}s"))
    return _pick(out, "无时长数据")


def _judge_resolution(fdef, b, c):
    if not c:
        return "SKIP", "无分辨率数据"
    exp = (fdef.get("expected") or {})
    if c.get("resolution") != exp.get("resolution"):
        return "FAIL", f"实际 {c.get('resolution')}（{c.get('aspect_ratio')}）≠ 合同 {exp.get('resolution')}"
    if exp.get("aspect_ratio") and c.get("aspect_ratio") != exp.get("aspect_ratio"):
        return "FAIL", f"画幅 {c.get('aspect_ratio')} ≠ 合同 {exp.get('aspect_ratio')}"
    if b and b.get("resolution") and b["resolution"] != c.get("resolution"):
        return "FAIL", f"相对基线 {b.get('resolution')} → {c.get('resolution')}"
    return "OK", f"{c.get('resolution')} / {c.get('aspect_ratio')} 符合合同"


def _judge_colorspace(fdef, b, c):
    if not c:
        return "SKIP", "无色彩空间数据"
    val = c.get("value")
    allowed = fdef.get("allowed", ["bt709"])
    if val in (None, "unspecified", "unknown"):
        return "WARN", f"color_space 未标注（实际 {c.get('color_space')}），合同要求 {fdef.get('expected')}"
    if val not in allowed:
        return "WARN", f"实际 {val} ≠ 合同 {fdef.get('expected')}"
    if b and b.get("value") and b["value"] != val:
        return "WARN", f"相对基线 {b.get('value')} → {val}"
    return "OK", f"{val} 符合合同"


def _judge_model_weight(fdef, b, c):
    if not c or not c.get("fingerprint"):
        return "SKIP", "未取到模型权重指纹"
    fp = c["fingerprint"]
    if not b:
        return "SKIP", f"无基线对照，首见指纹已记录：{fp}"
    if not b.get("fingerprint"):
        return "SKIP", "基线缺失权重指纹"
    if b["fingerprint"] != fp:
        return "FAIL", f"权重指纹变化 {b['fingerprint']} → {fp}（同输入不可复现风险）"
    return "OK", f"权重指纹一致（{fp}）"


def _judge_sampler(fdef, b, c):
    if not c:
        return "SKIP", "无采样参数数据"
    if not c.get("explicit"):
        return "WARN", "TTS 推理采样参数未显式固定（依赖库默认值），存在阶段间默认值不一致风险"
    if b and b.get("params") != c.get("params"):
        return "WARN", "采样参数相对基线发生变化"
    return "OK", "采样参数已显式固定"


def _judge_precision(fdef, b, c):
    if not c or not c.get("value"):
        return "SKIP", "精度模式未知（模型目录不可用）"
    allowed = fdef.get("allowed", [])
    if allowed and c["value"] not in allowed:
        return "WARN", f"精度 {c['value']} 不在合同允许集 {allowed}"
    if b and b.get("value") and b["value"] != c["value"]:
        return "WARN", f"相对基线 {b.get('value')} → {c['value']}"
    return "OK", f"{c['value']} 符合合同"


def _judge_vae(fdef, b, c):
    return "SKIP", fdef.get("applicability_note", "本产线不适用")[:120]


def _judge_audio(fdef, b, c):
    if not c or c.get("sample_rate_hz") is None:
        return "SKIP", "无音频流数据"
    pair = (c.get("sample_rate_hz"), c.get("channels"))
    allowed = [(x.get("sample_rate_hz"), x.get("channels")) for x in fdef.get("allowed", [])]
    if allowed and pair not in allowed:
        return "FAIL", f"实际 {pair[0]}Hz/{pair[1]}ch 不在合同允许集 {allowed}"
    if b and b.get("sample_rate_hz") is not None:
        if (b.get("sample_rate_hz"), b.get("channels")) != pair:
            return "FAIL", f"相对基线 {b.get('sample_rate_hz')}Hz/{b.get('channels')}ch → {pair[0]}Hz/{pair[1]}ch"
    return "OK", f"{pair[0]}Hz/{pair[1]}ch 符合合同"


def _judge_chunk(fdef, b, c):
    if not c:
        return "SKIP", "无分块/降级数据"
    if c.get("auto_downgrade"):
        return "WARN", f"检测到自动降级标记：{c.get('downgrade_flags')}"
    mode = c.get("render_chunk_mode")
    exp = (fdef.get("expected") or {}).get("render_chunk_mode")
    if mode is None:
        return "SKIP", "无渲染分块证据（非 HyperFrames 多场景项目）"
    if exp and mode != exp:
        return "WARN", f"分块模式 {mode} ≠ 合同 {exp}"
    return "OK", f"分块模式 {mode}，未检测到自动降级"


_JUDGES = {
    "fps": _judge_fps,
    "segment_duration": _judge_segment_duration,
    "resolution_aspect": _judge_resolution,
    "colorspace_gamma": _judge_colorspace,
    "model_weight_version": _judge_model_weight,
    "sampler_steps_cfg_seed": _judge_sampler,
    "precision_mode": _judge_precision,
    "vae_version": _judge_vae,
    "audio_sample_rate_channels": _judge_audio,
    "chunk_size_auto_downgrade": _judge_chunk,
}


# ─────────────────────────────────────────────────────────────
# 扩展层判定（8 字段；签名 _(fdef, b, c, ctx)，ctx 携带合同侧真源与批次上下文）
# ─────────────────────────────────────────────────────────────

def _ext_change_events(ctx):
    evs = ctx.get("change_events") or []
    out = set()
    for e in evs:
        if isinstance(e, dict):
            if e.get("field"):
                out.add(e["field"])
            if e.get("covers"):
                out.update(e["covers"] if isinstance(e["covers"], list) else [e["covers"]])
            if e.get("all"):
                out.add("all")
        elif isinstance(e, str):
            out.add(e)
    return out


def _judge_render_window_frames(fdef, b, c, ctx):
    if not c or c.get("value") is None:
        return "SKIP", "无时长或帧率证据，渲染窗口帧数不可派生"
    v = int(c["value"])
    if not b or b.get("value") is None:
        return "SKIP", f"无基线对照，首见帧数已登记：{v}"
    bv = int(b["value"])
    if bv == v:
        return "OK", f"帧数 {v} 与冻结基线一致"
    ev = _ext_change_events(ctx)
    if "all" in ev or fdef.get("field") in ev:
        return "OK", f"帧数 {bv} → {v} 已由变更事件覆盖，放行"
    return "FAIL", f"帧数与冻结基线不同且无变更事件：{bv} → {v}（硬停）"


def _judge_resolution_short_edge(fdef, b, c, ctx):
    if not c or c.get("value") is None:
        return "SKIP", "无宽高证据"
    v = int(c["value"])
    allowed = fdef.get("allowed") or []
    if allowed and v not in allowed:
        return "WARN", f"短边 {v}px 不在合同允许集 {allowed}（降级+人工）"
    if b and b.get("value") is not None:
        bv = int(b["value"])
        band = float(fdef.get("tolerance_band", 0.02))
        if bv and abs(v - bv) / bv > band:
            return "WARN", f"短边相对基线偏移超容差带 {band:.0%}：{bv}px → {v}px"
    return "OK", f"短边 {v}px 符合合同"


def _judge_peak_vram(fdef, b, c, ctx):
    if not c or c.get("value_gib") is None:
        return "SKIP", "未采集峰值内存（0=未采集，不得读作无占用）"
    v = float(c["value_gib"])
    src = os.path.basename(c.get("source") or "-")
    if b and b.get("value_gib") is not None:
        bv = float(b["value_gib"])
        band = float(fdef.get("tolerance_band", 0.2))
        if bv > 0 and abs(v - bv) / bv > band:
            return "WARN", f"同配置下峰值内存超容差带 {band:.0%}：{bv:.2f}GiB → {v:.2f}GiB（仅记录，来源 {src}）"
        return "OK", f"峰值内存 {v:.2f}GiB 与基线 {bv:.2f}GiB 同带（来源 {src}）"
    return "OK", f"首见峰值内存 {v:.2f}GiB 已登记（来源 {src}）"


def _judge_seed(fdef, b, c, ctx):
    if not c or not c.get("explicit") or c.get("value") is None:
        return "SKIP", "TTS 推理 seed 未显式声明 → 不可复算（建议在采样调用处显式固定 seed）"
    v = c["value"]
    if b and b.get("explicit") and b.get("value") is not None and b["value"] != v:
        return "FAIL", f"seed 与冻结基线不同：{b['value']} → {v}（同输入不可复算，硬停）"
    if b and b.get("explicit") and b.get("value") is not None:
        return "OK", f"seed {v} 与基线一致"
    return "SKIP", f"无基线对照，首见 seed 已登记：{v}"


def _judge_tolerance_value(fdef, b, c, ctx):
    pol = ctx.get("tolerance_policy") or {}
    unit = pol.get("unit")
    val = pol.get("tolerance_value")
    if not unit:
        return "FAIL", "tolerance_value 单位缺失 → 判不可比（硬停）"
    if val is None:
        return "SKIP", "未声明 tolerance_value"
    if b and b.get("value") is not None and float(b["value"]) != float(val):
        return "WARN", f"容差取值相对基线变化：{b['value']}{unit} → {val}{unit}（登记复核）"
    return "OK", f"容差 {val}{unit}（单位已显式声明）"


def _judge_canonicalizer_version(fdef, b, c, ctx):
    declared = ctx.get("contract_canonicalizer_signature")
    cfg_now = (ctx.get("canonicalizer") or {}).get("signature")
    if cfg_now and declared and cfg_now != declared:
        return "FAIL", f"规范化器签名与合同不一致：配置 {cfg_now} ≠ 合同 {declared}（换实现未同步合同，硬停）"
    cur = (c or {}).get("value")
    if not cur:
        return "FAIL", "canonicalizer_version 为空（未版本化，硬停）"
    if declared and cur != declared:
        return "FAIL", f"当次快照签名 {cur} ≠ 合同声明 {declared}（硬停）"
    if b and b.get("value") and declared and b["value"] != declared:
        return "FAIL", f"基线签名 {b['value']} ≠ 合同声明 {declared}（硬停）"
    if not b or not b.get("value"):
        return "OK", f"规范化器签名 {cur}（首见登记）"
    return "OK", f"规范化器签名 {cur} 与基线一致"


def _judge_expected_n(fdef, b, c, ctx):
    pol = ctx.get("expected_n_policy") or {}
    declared = pol.get("declared")
    if declared is None:
        return "SKIP", "expected_n 未显式签发 → 不可判"
    actual = ctx.get("actual_entry_count")
    if actual is None:
        return "SKIP", "无法统计实际判定条目数"
    if int(declared) != int(actual):
        return "FAIL", f"实际判定条目 {actual} 条 ≠ 合同声明 {declared} 条（字段静默丢失，硬停）"
    return "OK", f"实际判定条目 {actual} 条 = 声明 {declared} 条（{pol.get('composition') or ''}）".strip()


def _judge_frozen_baseline_digest(fdef, b, c, ctx):
    fb = ctx.get("frozen_baseline") or {}
    declared = fb.get("digest")
    if not declared:
        return "SKIP", "基线未冻结（空=未冻结），无法重判"
    recomputed = ctx.get("recomputed_digest")
    if recomputed is None:
        return "SKIP", f"冻结摘要 {declared[:18]}… 无法重判（缺 ref_manifest 或读不到）"
    if recomputed != declared:
        return "FAIL", f"重判行与冻结摘要不一致：{declared[:18]}… ≠ {recomputed[:18]}…（基线被改写或规范化器变更）"
    cur = (c or {}).get("value")
    if cur and cur != declared:
        return "FAIL", f"当次快照摘要 {cur[:18]}… ≠ 冻结摘要 {declared[:18]}…（硬停）"
    if b and b.get("value") and b["value"] != declared:
        return "FAIL", f"基线条目摘要 {b['value'][:18]}… ≠ 冻结摘要 {declared[:18]}…（硬停）"
    return "OK", f"冻结摘要重判一致（{declared[:18]}…）"


_EXT_JUDGES = {
    "render_window_frames": _judge_render_window_frames,
    "resolution_short_edge": _judge_resolution_short_edge,
    "peak_vram": _judge_peak_vram,
    "seed": _judge_seed,
    "tolerance_value": _judge_tolerance_value,
    "canonicalizer_version": _judge_canonicalizer_version,
    "expected_n": _judge_expected_n,
    "frozen_baseline_digest": _judge_frozen_baseline_digest,
}


def evaluate(contract, base=None, cur=None):
    if cur is None:
        cur = base
        base = None
    rows = []
    counts = {"FAIL": 0, "WARN": 0, "OK": 0, "SKIP": 0}
    derived_b = (base or {}).get("derived") or {}
    derived_c = (cur or {}).get("derived") or {}
    for fdef in contract.get("fields", []):
        name = fdef["field"]
        fn = _JUDGES.get(name)
        if fn is None:
            verdict, reason = "SKIP", "无判定实现"
        else:
            verdict, reason = fn(fdef, derived_b.get(name), derived_c.get(name))
        counts[verdict] = counts.get(verdict, 0) + 1
        rows.append({
            "field": name,
            "label": fdef.get("label"),
            "stability": fdef.get("stability"),
            "applicability": fdef.get("applicability"),
            "verdict": verdict,
            "baseline": _summ(derived_b.get(name)),
            "current": _summ(derived_c.get(name)),
            "reason": reason,
            "drift_symptom": fdef.get("drift_symptom"),
            "remediation": fdef.get("remediation"),
        })

    # ── 扩展判定层（AI-Film-Studio 第二条私信 8 字段） ──
    ext_def = contract.get("extended_contract") or {}
    ext_fields = ext_def.get("fields") or []
    ext_b = (base or {}).get("extended") or {}
    ext_c = (cur or {}).get("extended") or {}
    canon = load_canonicalizer()
    frozen = load_frozen_baseline()
    ctx = {
        "tolerance_policy": contract.get("tolerance_policy") or {},
        "expected_n_policy": contract.get("expected_n_policy") or {},
        "canonicalizer": canon,
        "frozen_baseline": frozen,
        "contract_canonicalizer_signature": (contract.get("canonicalization_ref") or {}).get("signature"),
        "actual_entry_count": len(contract.get("fields", [])) + len(ext_fields),
        "change_events": (ext_c.get("change_events") or []),
        "recomputed_digest": (ext_c.get("frozen_baseline_digest") or {}).get("recomputed"),
    }
    if ctx["recomputed_digest"] is None and frozen.get("ref_manifest"):
        ref_path = frozen["ref_manifest"]
        if not os.path.isabs(ref_path):
            ref_path = os.path.join(ROOT_DEFAULT, ref_path)
        ref_m = read_json(ref_path)
        if ref_m:
            ctx["recomputed_digest"], _ok = canonical_digest(ref_m)

    ext_rows = []
    ext_counts = {"FAIL": 0, "WARN": 0, "OK": 0, "SKIP": 0}
    for fdef in ext_fields:
        name = fdef["field"]
        fn = _EXT_JUDGES.get(name)
        if fn is None:
            verdict, reason = "SKIP", "无判定实现"
        else:
            try:
                verdict, reason = fn(fdef, ext_b.get(name), ext_c.get(name), ctx)
            except Exception as e:  # 判定器自身异常不得静默通过
                verdict, reason = "FAIL", f"扩展判定器异常：{type(e).__name__}: {e}"
        ext_counts[verdict] = ext_counts.get(verdict, 0) + 1
        ext_rows.append({
            "field": name,
            "label": fdef.get("label") or name,
            "channel": "extended",
            "stability": fdef.get("stability"),
            "applicability": fdef.get("action"),
            "verdict": verdict,
            "baseline": _summ(ext_b.get(name)),
            "current": _summ(ext_c.get(name)),
            "reason": reason,
            "drift_symptom": fdef.get("drift_rule"),
            "remediation": fdef.get("action"),
        })

    # 正交对计数分流（issuer × actionability / judge_source × frozen_state）
    _ia = ext_c.get("issuer_actionability_records") or []
    _mfe = ext_c.get("manual_frozen_entries") or []
    total_entries = len(rows) + len(ext_rows)
    ortho_counts = {
        "auto_pass_denominator": total_entries - len(_mfe),
        "manual_frozen_excluded": len(_mfe),
        "skip_count": len([x for x in _ia if isinstance(x, dict) and x.get("issuer") in ("exec", "executor") and x.get("actionability") is False]),
        "not_applicable_count": len([x for x in _ia if isinstance(x, dict) and x.get("issuer") == "judge" and x.get("actionability") is False]),
        "rule": "人工判据在冻结窗内不进自动通过率分母；执行侧签 false 进跳过计数，判定侧签 false 进不适配计数",
    }

    # 工具链漂移（vae_version 的等价替代通道）
    t_base = (base or {}).get("toolchain") or {}
    t_cur = (cur or {}).get("toolchain") or {}
    tool_drift = []
    for key in ("ffmpeg", "ffprobe", "hyperframes", "node"):
        vb = (t_base.get(key) or {}).get("version")
        vc = (t_cur.get(key) or {}).get("version")
        if vb and vc and vb != vc:
            tool_drift.append({"tool": key, "baseline": vb, "current": vc, "verdict": "WARN"})

    total_fail = counts["FAIL"] + ext_counts["FAIL"]
    total_warn = counts["WARN"] + ext_counts["WARN"]
    if total_fail:
        overall = "INVARIANT_FAIL"
    elif total_warn or tool_drift:
        overall = "WARN_ONLY"
    else:
        overall = "OK"

    return {
        "contract_version": contract.get("contract_version"),
        "manifest_version": MANIFEST_VERSION,
        "generated_at": now_iso(),
        "baseline_label": (base or {}).get("label"),
        "current_label": (cur or {}).get("label"),
        "baseline_video": (base or {}).get("video_path"),
        "current_video": (cur or {}).get("video_path"),
        "counts": counts,
        "rows": rows,
        "extended_counts": ext_counts,
        "extended_rows": ext_rows,
        "toolchain_drift": tool_drift,
        "expected_n": {"declared": (contract.get("expected_n_policy") or {}).get("declared"),
                       "actual": ctx["actual_entry_count"]},
        "canonicalizer_version": canon.get("canonicalizer_version"),
        "canonicalizer_signature": canon.get("signature"),
        "frozen_baseline": {"available": frozen.get("available"), "digest": frozen.get("digest"),
                            "ref_manifest": frozen.get("ref_manifest")},
        "orthogonality_counts": ortho_counts,
        "overall": overall,
        "exit_code": 2 if total_fail else 0,
    }


def _summ(d):
    if not d:
        return "-"
    if "value" in d and d.get("value") is not None and len(d) <= 3:
        return str(d.get("value"))
    if "resolution" in d:
        return f"{d.get('resolution')}"
    if "sample_rate_hz" in d:
        return f"{d.get('sample_rate_hz')}Hz/{d.get('channels')}ch"
    if "fingerprint" in d:
        fp = d.get("fingerprint") or "-"
        return fp[:22] + "…" if len(fp) > 24 else fp
    if "duration" in d:
        extra = f" / 声明 {d['declared_duration']}" if d.get("declared_duration") is not None else ""
        return f"{d.get('duration')}s{extra}"
    if "explicit" in d:
        return f"explicit={d.get('explicit')}"
    if "render_chunk_mode" in d:
        return f"{d.get('render_chunk_mode')}/降级={d.get('auto_downgrade')}"
    return json.dumps(d, ensure_ascii=False)[:32]


def format_report(rep):
    lines = []
    lines.append("=" * 92)
    lines.append("参数漂移比对报告（param_contract）")
    lines.append("=" * 92)
    lines.append(f"合同版本 : {rep.get('contract_version')}")
    lines.append(f"基线     : {rep.get('baseline_label')}  {rep.get('baseline_video') or ''}")
    lines.append(f"当前     : {rep.get('current_label')}  {rep.get('current_video') or ''}")
    lines.append("-" * 92)
    lines.append(f"{'字段':<30}{'稳定级':<8}{'基线':<22}{'当前':<22}{'判定'}")
    lines.append("-" * 92)
    for r in rep["rows"] + rep.get("extended_rows", []):
        lvl = {"invariant": "不变", "exploratory": "探索"}.get(r["stability"], r["stability"])
        lines.append(f"{r['field'][:29]:<30}{lvl:<8}{str(r['baseline'])[:21]:<22}{str(r['current'])[:21]:<22}{r['verdict']}")
    lines.append("-" * 92)
    c = rep["counts"]
    lines.append(f"统计：FAIL {c['FAIL']} / WARN {c['WARN']} / OK {c['OK']} / SKIP {c['SKIP']}")
    ec = rep.get("extended_counts")
    if ec:
        lines.append(f"扩展层：FAIL {ec['FAIL']} / WARN {ec['WARN']} / OK {ec['OK']} / SKIP {ec['SKIP']}"
                     f"（合同 {rep.get('contract_version')} / manifest {rep.get('manifest_version')}）")
    en = rep.get("expected_n") or {}
    if en.get("declared") is not None:
        lines.append(f"条目数校验：声明 {en.get('declared')} 条 / 实际判定 {en.get('actual')} 条")
    o = rep.get("orthogonality_counts")
    if o:
        lines.append(f"正交计数：自动通过率分母 {o['auto_pass_denominator']}"
                     f"（剔除人工冻结 {o['manual_frozen_excluded']}）/ 跳过计数 {o['skip_count']}"
                     f" / 不适配计数 {o['not_applicable_count']}")
    if rep.get("toolchain_drift"):
        lines.append("工具链漂移：")
        for t in rep["toolchain_drift"]:
            lines.append(f"  - {t['tool']}: {t['baseline']} → {t['current']} ({t['verdict']})")
    lines.append("-" * 92)
    lines.append("逐项结论：")
    for r in rep["rows"] + rep.get("extended_rows", []):
        if r["verdict"] in ("FAIL", "WARN"):
            lines.append(f"  [{r['verdict']}] {r['field']}（{r['label']}）：{r['reason']}")
            if r.get("remediation"):
                lines.append(f"        处理：{r['remediation']}")
    skips = [r for r in rep["rows"] + rep.get("extended_rows", []) if r["verdict"] == "SKIP"]
    if skips:
        lines.append("  以下字段本次无对照证据，未计入判定：")
        for r in skips:
            lines.append(f"  [SKIP] {r['field']}：{r['reason']}")
    lines.append("-" * 92)
    verdict_text = {
        "INVARIANT_FAIL": f"结论：发现 {rep['counts']['FAIL'] + (rep.get('extended_counts') or {}).get('FAIL', 0)} 项不变量级漂移"
                          f"（核心 {rep['counts']['FAIL']} / 扩展 {(rep.get('extended_counts') or {}).get('FAIL', 0)}）→ 阻断（exit 2）",
        "WARN_ONLY": f"结论：无阻断，{rep['counts']['WARN'] + (rep.get('extended_counts') or {}).get('WARN', 0)} 项探索级漂移"
                     f"（核心 {rep['counts']['WARN']} / 扩展 {(rep.get('extended_counts') or {}).get('WARN', 0)}）→ 登记周回归（exit 0）",
        "OK": "结论：未发现漂移（exit 0）",
    }.get(rep.get("overall"), rep.get("overall"))
    lines.append(verdict_text)
    lines.append("=" * 92)
    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────

def cmd_freeze(args):
    contract = read_json(args.contract) or {}
    manifest = read_json(args.manifest)
    if not manifest:
        print(f"[error] 读不到 manifest：{args.manifest}", file=sys.stderr)
        return 1
    digest, norm_ok = canonical_digest(manifest)
    canon = load_canonicalizer()
    out = args.out or FROZEN_BASELINE_DEFAULT
    payload = {
        "frozen_at": now_iso(),
        "label": manifest.get("label"),
        "ref_manifest": os.path.relpath(os.path.abspath(args.manifest), args.root),
        "video_fingerprint": (manifest.get("video_fingerprint") or {}).get("sha256"),
        "digest": digest,
        "digest_rule": "sha256('sha256:') of json.dumps({label, video_fingerprint.sha256, derived}, sort_keys=True) 经 normalize_point 规范化",
        "canonicalizer_version": canon.get("canonicalizer_version"),
        "canonicalizer_signature": canon.get("signature"),
        "normalize_point_applied": norm_ok,
        "contract_version": contract.get("contract_version"),
        "note": "冻结基线真源：重判不一致即 FAIL（硬停）；重新冻结须显式执行 freeze",
    }
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print(f"[freeze] {manifest.get('label')}")
    print(f"  ref_manifest : {payload['ref_manifest']}")
    print(f"  digest       : {digest}")
    print(f"  canonicalizer: {canon.get('canonicalizer_version')} ({canon.get('signature')})")
    print(f"  输出         : {out}")
    return 0


def cmd_snapshot(args):
    contract = read_json(args.contract) or {}
    manifest = build_manifest(
        video=args.video,
        story_dir=args.story_dir,
        model_dir=args.model_dir,
        label=args.label,
        deep_hash=args.deep_hash,
        root=args.root,
    )
    manifest["contract_version"] = contract.get("contract_version")
    out = args.out or os.path.join(
        args.root, "reports", "artifacts",
        f"manifest_{re.sub(r'[^0-9A-Za-z_.-]', '_', args.label or os.path.basename(args.video))}.json")
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    d = manifest["derived"]
    print(f"[snapshot] {manifest['label']}")
    print(f"  成片      : {manifest['video_path']}  ({manifest['video_fingerprint']['sha256'][:16]}…)")
    print(f"  视频      : {d['resolution_aspect']['resolution']} / {d['fps']['value']} fps"
          f" / {d['colorspace_gamma']['value']}")
    print(f"  音频      : {d['audio_sample_rate_channels']['sample_rate_hz']}Hz"
          f" / {d['audio_sample_rate_channels']['channels']}ch")
    print(f"  时长      : {d['segment_duration']['duration']}s"
          + (f"（声明 {d['segment_duration']['declared_duration']}s）"
             if d['segment_duration']['declared_duration'] is not None else ""))
    print(f"  模型指纹  : {d['model_weight_version'].get('fingerprint')}")
    print(f"  manifest  : {out}")
    return 0


def cmd_diff(args, mode="diff"):
    contract = read_json(args.contract)
    if not contract:
        print(f"[error] 找不到参数合同：{args.contract}", file=sys.stderr)
        return 1
    if mode == "check":
        base = None
        current = read_json(getattr(args, "manifest", None) or "")
    else:
        base = read_json(getattr(args, "baseline", None) or "")
        current = read_json(getattr(args, "current", None) or "")
    if not current:
        print("[error] 读不到 manifest（路径错误或 JSON 解析失败）", file=sys.stderr)
        return 1
    rep = evaluate(contract, base=base, cur=current)
    print(format_report(rep))
    if args.json_out:
        os.makedirs(os.path.dirname(os.path.abspath(args.json_out)), exist_ok=True)
        with open(args.json_out, "w", encoding="utf-8") as f:
            json.dump(rep, f, ensure_ascii=False, indent=2)
        print(f"[json] {args.json_out}")
    return rep["exit_code"]


def main(argv=None):
    p = argparse.ArgumentParser(description="参数快照与漂移比对（param_contract）")
    p.add_argument("--root", default=ROOT_DEFAULT, help="产线根目录")
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("snapshot", help="从一次真实成片抽取参数，产出 run manifest")
    sp.add_argument("--video", required=True)
    sp.add_argument("--story-dir", default=None)
    sp.add_argument("--model-dir", default=DEFAULT_MODEL_DIR)
    sp.add_argument("--label", default=None)
    sp.add_argument("--out", default=None)
    sp.add_argument("--deep-hash", action="store_true", help="模型权重用逐文件内容哈希（慢但最严）")
    sp.add_argument("--contract", default=CONTRACT_DEFAULT)
    sp.set_defaults(func=cmd_snapshot)

    sd = sub.add_parser("diff", help="两份 manifest 比对")
    sd.add_argument("baseline")
    sd.add_argument("current")
    sd.add_argument("--contract", default=CONTRACT_DEFAULT)
    sd.add_argument("--json-out", default=None)
    sd.set_defaults(func=lambda a: cmd_diff(a, mode="diff"))

    sc = sub.add_parser("check", help="单份 manifest 对合同口径校验")
    sc.add_argument("manifest")
    sc.add_argument("--contract", default=CONTRACT_DEFAULT)
    sc.add_argument("--json-out", default=None)
    sc.set_defaults(func=lambda a: cmd_diff(a, mode="check"))

    sf = sub.add_parser("freeze", help="把一份 manifest 冻结为基线（写 config/frozen_baseline.json）")
    sf.add_argument("manifest")
    sf.add_argument("--contract", default=CONTRACT_DEFAULT)
    sf.add_argument("--out", default=None)
    sf.set_defaults(func=cmd_freeze)

    args = p.parse_args(argv)
    try:
        return args.func(args)
    except RuntimeError as e:
        print(f"[error] {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
