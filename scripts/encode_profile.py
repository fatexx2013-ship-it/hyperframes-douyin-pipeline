#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""encode_profile.py —— 交付编码参数的「单一真源读取器」（S3 方案C）

设计目标
--------
render.sh / generate_*.py / per-story（hyperframes + post_process）
三条链路共享同一份交付参数；任何一处都不再各自维护副本。
本文件只做「读合同 → 派生参数 / 命令行」，**不持有第二套真值**，
也**没有**写合同的能力（合同变更由人工 + toolchain_lock 复核）。

真源映射（config/param_contract.json）
--------------------------------------
toolchain_pins.encoder_chain
    software                  → 编码器名（libx264）与 video_codec=h264
    hardware                  → 硬编备选名（h264_videotoolbox），仅记录不切换
    preset                    → -preset
    profile                   → -profile:v（小写传入 ffmpeg）
    level                     → -level
    pix_fmt                   → -pix_fmt
    gop_frames                → -g
    gop_accept_max_frames     → 交付判据 GOP 上界（非编码参数，供 is_delivery_ready）
    video_bitrate             → -b:v
    video_maxrate             → -maxrate
    video_bufsize             → -bufsize
    video_bitrate_max_accept  → 交付判据码率上限（非编码参数）
    audio_bitrate             → -b:a
fields[]（10 项已审计核心字段；画幅/帧率/采样率**不**在 encoder_chain 里重复定义）
    resolution_aspect.expected.resolution                        → width / height
    resolution_aspect.expected.aspect_ratio                      → aspect
    fps.expected                                                 → fps
    audio_sample_rate_channels.expected.deliver_sample_rate_hz   → audio_sample_rate
    audio_sample_rate_channels.allowed[stage_role ^= "deliver"]  → 声道接受集

回落与留痕
----------
读合同失败（文件缺失/非法 JSON/缺块）时，返回与合同同值的内置默认，
并在 _meta 标记 fallback_used=True + fallback_reason，同时把每个值的来源
写入 _meta.sources；调用方（post_process.py 等）会据此在 stderr 打 WARN。
**任何静默回落都是缺陷**——本文件的存在意义就是让"值来自哪里"可审计。

CLI
---
    python3 scripts/encode_profile.py --json            # 打印派生后的参数字典
    python3 scripts/encode_profile.py --ffmpeg-args     # 打印可直接拼接的编码参数
    python3 scripts/encode_profile.py --selftest        # 自检：真源可读 + 各项与合同一致
    python3 scripts/encode_profile.py --check FILE.mp4  # 用真源判据体检一个成片
    python3 scripts/encode_profile.py --get KEY         # 取单个键的原始值（供 shell 链路拼接）

判据唯一性（S3 收口修正）
------------------------
assert_delivery_spec() 是「成片是否满足抖音交付规格」的**全仓唯一判据**；
post_process.is_delivery_ready / 未来段2 A7 断言 / 任何其它链路都必须调用它，
禁止再写第二套判据（参数散落一处即缺陷）。同理 --get 是 shell 链路取值的唯一口。
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys

CONTRACT_REL = os.path.join("config", "param_contract.json")
CONTRACT_VERSION_EXPECTED = "1.3.0"

# 回落默认：仅在合同不可读时使用，取值与 1.3.0 合同同源（改动须同步合同）
# ⚠ audit_refs（A6b 冻结参照）**不进**回落表：读不到合同就返回 None，
#   由调用方回退旧口径并显式告警——冻结值被静默复制成常量即失去"冻结"意义。
FALLBACK = {
    "id": "douyin-vertical-1080x1920",
    "container": "mp4",
    "width": 1080,
    "height": 1920,
    "aspect": "9:16",
    "fps": 30,
    "video_codec": "h264",
    "encoder_sw": "libx264",
    "encoder_hw": "h264_videotoolbox",
    "video_preset": "medium",
    "profile": "High",
    "level": "4.2",
    "pix_fmt": "yuv420p",
    "gop_frames": 60,
    "gop_accept_max_frames": 120,
    "video_rate_control": "capped-crf",
    "video_crf": 18,
    "video_bitrate": "8M",
    "video_bitrate_role": "ceiling_reference_only",
    "video_bitrate_target_locked": False,
    "video_maxrate": "10M",
    "video_bufsize": "12M",
    "video_bitrate_max_accept": "11M",
    "audio_codec": "aac",
    "audio_bitrate": "128k",
    "audio_sample_rate": 44100,
    "audio_channels_accept": [1, 2],
    "faststart": True,
}


# ── 真源读取 ────────────────────────────────────────────────────────────────
def contract_path(root=None):
    """合同绝对路径。root 缺省取本文件所在仓库根（scripts/ 的上级）。"""
    if root is None:
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if os.path.isdir(root) and os.path.exists(os.path.join(root, CONTRACT_REL)):
        return os.path.join(root, CONTRACT_REL)
    return os.path.join(root, CONTRACT_REL)


def _field(raw, name):
    for e in (raw.get("fields") or []):
        if e.get("field") == name:
            return e
    raise KeyError(f"合同 fields[] 缺字段 {name}")


def _chain(raw):
    try:
        return raw["toolchain_pins"]["encoder_chain"]
    except Exception as exc:  # noqa: BLE001
        raise KeyError(f"合同缺 toolchain_pins.encoder_chain（{exc}）") from exc


def load_raw(root=None, contract=None):
    """读合同并派生交付参数；失败回落并留痕。返回的 dict 带 _meta。"""
    path = contract or contract_path(root)
    p = dict(FALLBACK)
    meta = {
        "contract_path": path,
        "contract_version": None,
        "contract_version_expected": CONTRACT_VERSION_EXPECTED,
        "fallback_used": False,
        "fallback_reason": "",
        "sources": {},
    }
    try:
        with open(path, encoding="utf-8") as f:
            raw = json.load(f)

        ch = _chain(raw)
        for key, out_key in (
            ("preset", "video_preset"), ("profile", "profile"), ("level", "level"),
            ("pix_fmt", "pix_fmt"), ("gop_frames", "gop_frames"),
            ("gop_accept_max_frames", "gop_accept_max_frames"),
            ("video_rate_control", "video_rate_control"), ("video_crf", "video_crf"),
            ("video_bitrate", "video_bitrate"),
            ("video_bitrate_role", "video_bitrate_role"),
            ("video_bitrate_target_locked", "video_bitrate_target_locked"),
            ("video_maxrate", "video_maxrate"),
            ("video_bufsize", "video_bufsize"),
            ("video_bitrate_max_accept", "video_bitrate_max_accept"),
            ("audio_bitrate", "audio_bitrate"), ("software", "encoder_sw"),
            ("hardware", "encoder_hw"),
        ):
            if key in ch:
                p[out_key] = ch[key]
                meta["sources"][out_key] = f"toolchain_pins.encoder_chain.{key}"

        res_spec = _field(raw, "resolution_aspect")["expected"]
        w, h = (int(x) for x in str(res_spec["resolution"]).lower().split("x"))
        p["width"], p["height"] = w, h
        meta["sources"]["width"] = "fields[resolution_aspect].expected.resolution"
        meta["sources"]["height"] = "fields[resolution_aspect].expected.resolution"
        if res_spec.get("aspect_ratio"):
            p["aspect"] = res_spec["aspect_ratio"]
            meta["sources"]["aspect"] = "fields[resolution_aspect].expected.aspect_ratio"

        p["fps"] = int(_field(raw, "fps")["expected"])
        meta["sources"]["fps"] = "fields[fps].expected"

        aud = _field(raw, "audio_sample_rate_channels")
        p["audio_sample_rate"] = int(aud["expected"]["deliver_sample_rate_hz"])
        meta["sources"]["audio_sample_rate"] = \
            "fields[audio_sample_rate_channels].expected.deliver_sample_rate_hz"
        chs = sorted({
            int(a["channels"]) for a in (aud.get("allowed") or [])
            if str(a.get("stage_role", "")).startswith("deliver") and "channels" in a
        })
        if chs:
            p["audio_channels_accept"] = chs
            meta["sources"]["audio_channels_accept"] = \
                "fields[audio_sample_rate_channels].allowed[stage_role=deliver].channels"

        p["video_codec"] = "h264"
        meta["sources"]["video_codec"] = "encoder_chain.software/hardware 归纳"
        meta["sources"]["audio_codec"] = "静态（交付容器口径 mp4/aac）"
        meta["sources"]["video_preset"] = meta["sources"].get(
            "video_preset", "内置默认（合同 encoder_chain 未声明 preset 时）")
        meta["contract_version"] = raw.get("contract_version")
        if str(raw.get("contract_version")) != CONTRACT_VERSION_EXPECTED:
            meta["version_note"] = (
                f"合同版本 {raw.get('contract_version')} 与读取器预期 "
                f"{CONTRACT_VERSION_EXPECTED} 不一致——请复核取值口径")
    except Exception as exc:  # noqa: BLE001
        meta["fallback_used"] = True
        meta["fallback_reason"] = f"{type(exc).__name__}: {exc}"

    out = dict(p)
    out["_meta"] = meta
    return out


def profile(root=None, contract=None):
    """交付参数字典（唯一入口）。带 _meta，调用方可据 fallback_used 留痕。"""
    return load_raw(root=root, contract=contract)


# ── 审计参照（audit_refs）：A6b 等门禁的冻结参照真源 ────────────────────────
def audit_refs(root=None, contract=None):
    """读合同顶层 audit_refs 块（门禁参照的冻结值真源）。

    读不到 / 未声明 → 返回空 dict：本函数**不猜、不填默认值**，
    缺字段必须由调用方回退旧口径并显式告警（方案B 发现B 的处置口径）。
    """
    path = contract or contract_path(root)
    try:
        with open(path, encoding="utf-8") as f:
            raw = json.load(f)
    except Exception:  # noqa: BLE001 —— 合同不可读不是本函数要报的错
        return {}
    blk = raw.get("audit_refs")
    return dict(blk) if isinstance(blk, dict) else {}


def audit_ref(key, root=None, contract=None):
    """取单个审计参照冻结值 → (value, source)；未声明 → (None, "")。

    source 形如 ``audit_refs.a6b_ref_mib_per_s``，供调用方写进报告留痕。
    """
    blk = audit_refs(root=root, contract=contract)
    v = blk.get(key)
    if v is None:
        return None, ""
    return v, f"audit_refs.{key}"


# ── 命令行派生 ──────────────────────────────────────────────────────────────
def video_args(p):
    """视频编码参数（-c:v/-preset/-profile/-level/-pix_fmt/码率控制/-maxrate/-bufsize/-r/-g）

    码率控制（S3 修复 · 方案B 发现A）：``video_rate_control == "capped-crf"`` 时以
    ``-crf video_crf`` 定质量档、``-maxrate/-bufsize`` 只作瞬时上限，**不输出 -b:v 目标**
    （即 S3 材料 C5「8M 目标无人锁死」的显式解除）；仅当合同声明了其它策略（如旧
    1.2.0 合同的 ABR）时才回落 ``-b:v``，保证回滚兼容。交付规格不受本分支影响。
    """
    rc = str(p.get("video_rate_control") or "capped-crf").strip().lower()
    if rc in ("capped-crf", "crf"):
        rc_args = ["-crf", str(int(p.get("video_crf") or 18))]
    else:
        rc_args = ["-b:v", str(p.get("video_bitrate") or "8M")]
    return [
        "-c:v", str(p.get("encoder_sw") or "libx264"),
        "-preset", str(p.get("video_preset") or "medium"),
        "-profile:v", str(p.get("profile") or "High").lower(),
        "-level", str(p.get("level") or "4.2"),
        "-pix_fmt", str(p.get("pix_fmt") or "yuv420p"),
        *rc_args,
        "-maxrate", str(p.get("video_maxrate") or "10M"),
        "-bufsize", str(p.get("video_bufsize") or "12M"),
        "-r", str(int(float(p.get("fps") or 30))),
        "-g", str(int(p.get("gop_frames") or 60)),
    ]


def audio_args(p):
    """音频编码参数（-c:a/-b:a/-ar）"""
    return [
        "-c:a", str(p.get("audio_codec") or "aac"),
        "-b:a", str(p.get("audio_bitrate") or "128k"),
        "-ar", str(int(p.get("audio_sample_rate") or 44100)),
    ]


def mux_args(p):
    """封装参数（-movflags +faststart）"""
    return ["-movflags", "+faststart"] if p.get("faststart", True) else []


def filter_args(p):
    """画幅规范化滤镜（scale+pad+setsar），供需要独立归一化的链路使用。"""
    w, h = int(p.get("width") or 1080), int(p.get("height") or 1920)
    fps = int(float(p.get("fps") or 30))
    return [
        "-vf",
        (f"scale={w}:{h}:force_original_aspect_ratio=decrease,"
         f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:color=#0a0a12,setsar=1"),
        "-r", str(fps),
    ]


def ffmpeg_args(p):
    """编码参数全串（video+audio+mux），render.sh 等 shell 链路可直接拼接。"""
    return video_args(p) + audio_args(p) + mux_args(p)


def _bps(text):
    """'11M' / '128k' / 十进制 → 比特/秒；不可解析返回 0。"""
    s = str(text or "").strip().upper()
    try:
        if s.endswith("M"):
            return int(float(s[:-1]) * 1000 * 1000)
        if s.endswith("K"):
            return int(float(s[:-1]) * 1000)
        return int(float(s))
    except ValueError:
        return 0


def probe_gop(path, sample=400):
    """采样窗口内关键帧间隔（帧，取最大）。不足 2 个关键帧无法判定 → None。

    ⚠ 只探测不判定；上界取自真源 gop_accept_max_frames（见 assert_delivery_spec）。
    """
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0",
             "-show_entries", "packet=flags", "-of", "csv=p=0",
             "-read_intervals", "%+#" + str(int(sample)), path],
            capture_output=True, text=True,
        )
        if r.returncode != 0:
            return None
        flags = [ln.strip() for ln in (r.stdout or "").splitlines() if ln.strip()]
        idx = [i for i, f in enumerate(flags) if f.startswith("K")]
        if len(idx) < 2:
            return None
        return max(idx[i + 1] - idx[i] for i in range(len(idx) - 1))
    except Exception:  # noqa: BLE001 —— 采样失败不阻断交付判定
        return None


def probe_spec(path):
    """只读探测成片关键规格（含 gop）。失败 / 无视频轨返回 None。

    ⚠ 本函数只「探测」，不「判定」——判据阈值一律取自真源（assert_delivery_spec）。
    """
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "error", "-show_streams", "-show_format",
             "-of", "json", path],
            capture_output=True, text=True,
        )
        if r.returncode != 0:
            return None
        data = json.loads(r.stdout or "{}")
    except Exception:  # noqa: BLE001
        return None
    streams = data.get("streams", [])
    v = next((s for s in streams if s.get("codec_type") == "video"), None)
    a = next((s for s in streams if s.get("codec_type") == "audio"), None)
    if not v:
        return None
    try:
        num, den = (v.get("r_frame_rate") or "0/1").split("/")
        fps = float(num) / float(den) if float(den) else 0.0
    except Exception:  # noqa: BLE001
        fps = 0.0
    vbitrate = 0
    for src in (v.get("bit_rate"), (data.get("format") or {}).get("bit_rate")):
        try:
            if src and int(src) > 0:
                vbitrate = int(src)
                break
        except Exception:  # noqa: BLE001
            continue
    return {
        "vcodec": v.get("codec_name"),
        "width": int(v.get("width") or 0),
        "height": int(v.get("height") or 0),
        "fps": fps,
        "profile": v.get("profile"),
        "level": v.get("level"),          # ffprobe 口径：整数 42 == 合同 4.2
        "pix_fmt": v.get("pix_fmt"),
        "vbitrate": vbitrate,
        "acodec": (a or {}).get("codec_name"),
        "sample_rate": int((a or {}).get("sample_rate") or 0),
        "channels": int((a or {}).get("channels") or 0),
        "gop": probe_gop(path),
    }


def _level_pair(value):
    """level 口径归一：'4.2' ↔ 42（ffprobe 给整数，合同写 4.2）。"""
    s = str(value or "").strip()
    if not s:
        return ""
    if "." in s:
        head, _, tail = s.partition(".")
        tail = tail.rstrip("0") or "0"
        try:
            return f"{int(head)}.{tail}"
        except ValueError:
            return s
    try:
        n = int(s)
    except ValueError:
        return s
    return f"{n // 10}.{n % 10}"


def assert_delivery_spec(spec, p=None):
    """交付规格断言 —— 全仓唯一判据（S3 收口修正 · 方案B 顺序耦合①）。

    spec：probe_spec() 的返回字典，或成片路径（内部自行探测）。
    p   ：交付参数字典（缺省读真源 profile()）。
    返回 (ok, reasons[])：reasons 为空即达标。

    契约：任何「该片是否已满足抖音交付规格」的判定都必须调用本函数——
    post_process.is_delivery_ready / 段2 A7 断言 / 其它链路一律不得另写判据
    （参数散落一处即缺陷）。全部阈值取自真源，本函数不持有魔法数。
    """
    p = p or profile()
    if isinstance(spec, (str, bytes, os.PathLike)):
        spec = probe_spec(spec)
    if not spec:
        return False, ["无法读取规格"]
    reasons = []
    if spec.get("vcodec") != p.get("video_codec", "h264"):
        reasons.append(f"编码器 {spec.get('vcodec')} 非 {p.get('video_codec', 'h264')}")
    exp_w, exp_h = int(p.get("width") or 1080), int(p.get("height") or 1920)
    if (spec.get("width"), spec.get("height")) != (exp_w, exp_h):
        reasons.append(f"尺寸 {spec.get('width')}x{spec.get('height')} 非 {exp_w}x{exp_h}")
    exp_fps = float(p.get("fps") or 30)
    if abs(float(spec.get("fps") or 0) - exp_fps) > 0.5:
        reasons.append(f"帧率 {float(spec.get('fps') or 0):.2f} 非 {exp_fps:.0f}")
    if str(spec.get("profile") or "").lower() != str(p.get("profile") or "High").lower():
        reasons.append(f"profile {spec.get('profile')} 非 {p.get('profile', 'High')}")
    if _level_pair(spec.get("level")) != _level_pair(p.get("level", "4.2")):
        reasons.append(f"level {spec.get('level')} 非 {p.get('level', '4.2')}")
    if spec.get("pix_fmt") != p.get("pix_fmt", "yuv420p"):
        reasons.append(f"pix_fmt {spec.get('pix_fmt')} 非 {p.get('pix_fmt', 'yuv420p')}")
    if spec.get("acodec") != p.get("audio_codec", "aac"):
        reasons.append(f"音频 {spec.get('acodec')} 非 {p.get('audio_codec', 'aac')}")
    if int(spec.get("sample_rate") or 0) != int(p.get("audio_sample_rate") or 0):
        reasons.append(f"音频采样率 {spec.get('sample_rate')} 非 {p.get('audio_sample_rate')}")
    ch_ok = [int(c) for c in (p.get("audio_channels_accept") or [1, 2])]
    if int(spec.get("channels") or 0) not in ch_ok:
        reasons.append(f"声道数 {spec.get('channels')} 不在 {ch_ok}")
    max_bps = _bps(p.get("video_bitrate_max_accept"))
    vb = int(spec.get("vbitrate") or 0)
    if vb and max_bps and vb > max_bps:
        reasons.append(f"码率 {vb / 1e6:.1f}Mbps 超 {max_bps / 1e6:.0f}Mbps")
    gop_accept = int(p.get("gop_accept_max_frames") or 0) or int(p.get("gop_frames") or 60) * 2
    gop = spec.get("gop")
    if gop and gop > gop_accept:
        reasons.append(f"关键帧间隔 {gop} 帧超上限 {gop_accept} 帧")
    return (len(reasons) == 0), reasons


def get(key, p=None):
    """取单个交付参数的原始值（供 shell 链路 --get 直接拼接）；未知键返回空串。"""
    p = p or profile()
    aliases = {"preset": "video_preset", "software": "encoder_sw", "hardware": "encoder_hw"}
    v = p.get(aliases.get(key, key))
    if v is None:
        # 审计参照冻结值（如 a6b_ref_mib_per_s）同样经本口可取，供 shell 链路复用
        v, _src = audit_ref(key)
    if v is None:
        return ""
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (list, tuple)):
        return ",".join(str(x) for x in v)
    return str(v)


def check_file(path, p=None):
    """按单一真源判据体检一个成片；返回 (ok, 明细列表)。只读探测 + 调用共享断言。"""
    p = p or profile()
    spec = probe_spec(path)
    if not spec:
        return False, [f"ffprobe 失败或无可判读视频轨：{path}"]
    ok, reasons = assert_delivery_spec(spec, p)
    max_bps = _bps(p.get("video_bitrate_max_accept"))
    gop_accept = int(p.get("gop_accept_max_frames") or 0) or int(p.get("gop_frames") or 60) * 2
    rows = [
        ("分辨率", f"{spec['width']}x{spec['height']}", f"{p['width']}x{p['height']}",
         f"{spec['width']}x{spec['height']}" == f"{p['width']}x{p['height']}"),
        ("编码器", spec["vcodec"], p["video_codec"], spec["vcodec"] == p["video_codec"]),
        ("profile", spec["profile"], p.get("profile"),
         str(spec["profile"] or "").lower() == str(p.get("profile") or "").lower()),
        ("level", spec["level"], p.get("level"),
         _level_pair(spec["level"]) == _level_pair(p.get("level"))),
        ("pix_fmt", spec["pix_fmt"], p.get("pix_fmt"), spec["pix_fmt"] == p.get("pix_fmt")),
        ("音频编码", spec["acodec"], p.get("audio_codec"), spec["acodec"] == p.get("audio_codec")),
        ("采样率", spec["sample_rate"], p.get("audio_sample_rate"),
         int(spec["sample_rate"] or 0) == int(p.get("audio_sample_rate") or 0)),
        ("声道", spec["channels"], p.get("audio_channels_accept"),
         int(spec["channels"] or 0) in [int(c) for c in (p.get("audio_channels_accept") or [1, 2])]),
        ("码率", (f"{spec['vbitrate'] / 1e6:.2f}Mbps" if spec["vbitrate"] else "N/A"),
         f"≤ {p.get('video_bitrate_max_accept')}",
         (not spec["vbitrate"]) or (not max_bps) or spec["vbitrate"] <= max_bps),
        ("关键帧间隔", (f"{spec['gop']} 帧" if spec.get("gop") else "N/A"),
         f"≤ {gop_accept} 帧", (not spec.get("gop")) or spec["gop"] <= gop_accept),
    ]
    detail = [f"{n}: {got} / 期望 {exp}{'' if row_ok else '  ✗'}"
              for n, got, exp, row_ok in rows]
    if reasons:
        detail.append("未达标原因: " + "; ".join(reasons))
    return ok, detail


# ── 自检 / CLI ──────────────────────────────────────────────────────────────
def selftest(root=None):
    p = profile(root)
    meta = p.get("_meta") or {}
    checks = []
    checks.append(("真源可读", not meta.get("fallback_used"),
                   meta.get("fallback_reason") or meta.get("contract_path", "")))
    checks.append(("合同版本", str(meta.get("contract_version")) == CONTRACT_VERSION_EXPECTED,
                   f"{meta.get('contract_version')} / 期望 {CONTRACT_VERSION_EXPECTED}"))
    checks.append(("画幅 1080x1920", (p["width"], p["height"]) == (1080, 1920),
                   f"{p['width']}x{p['height']}"))
    checks.append(("帧率 30", int(p["fps"]) == 30, str(p["fps"])))
    checks.append(("profile/level", (str(p["profile"]), str(p["level"])) == ("High", "4.2"),
                   f"{p['profile']}@{p['level']}"))
    checks.append(("音频 44100 采样率", int(p["audio_sample_rate"]) == 44100,
                   str(p["audio_sample_rate"])))
    checks.append(("声道接受集 ⊆ {1,2}",
                   set(int(c) for c in p["audio_channels_accept"]) <= {1, 2},
                   str(p["audio_channels_accept"])))
    checks.append(("GOP 上界 ≥ GOP", int(p["gop_accept_max_frames"]) >= int(p["gop_frames"]),
                   f"{p['gop_frames']} / 上界 {p['gop_accept_max_frames']}"))
    checks.append(("video_args 含 -g",
                   "-g" in video_args(p) and str(p["gop_frames"]) in video_args(p), ""))
    checks.append(("码率控制为 capped-crf",
                   str(p.get("video_rate_control")) == "capped-crf",
                   f"{p.get('video_rate_control')} / crf {p.get('video_crf')}"))
    checks.append(("video_args 用 -crf 且无 -b:v（8M 目标已解除）",
                   "-crf" in video_args(p) and "-b:v" not in video_args(p)
                   and str(p.get("video_crf") or "") in video_args(p),
                   " ".join(str(x) for x in video_args(p)[:12])))
    _a6b_v, _a6b_src = audit_ref("a6b_ref_mib_per_s", root)
    checks.append(("A6b 参照冻结值可读（audit_refs）",
                   _a6b_v is not None and float(_a6b_v) > 0,
                   f"{_a6b_v} MiB/s（{_a6b_src or '未声明'}）"))
    checks.append(("audio_args 含 -ar",
                   "-ar" in audio_args(p) and "44100" in audio_args(p), ""))
    checks.append(("码率上限可解析", _bps(p["video_bitrate_max_accept"]) > 0,
                   str(p["video_bitrate_max_accept"])))
    checks.append(("level 口径归一 (42↔4.2)",
                   _level_pair(42) == _level_pair("4.2") == "4.2"
                   and _level_pair(41) == "4.1" and _level_pair(50) == "5.0",
                   f"42→{_level_pair(42)} / 4.2→{_level_pair('4.2')} / 50→{_level_pair(50)}"))
    checks.append(("共享断言可调用",
                   callable(globals().get("assert_delivery_spec"))
                   and callable(globals().get("probe_spec")), ""))
    bad = [c for c in checks if not c[1]]
    print(f"[selftest] 真源 : {meta.get('contract_path')} "
          f"(contract_version={meta.get('contract_version')})")
    for name, ok, detail in checks:
        print(f"  [{'OK' if ok else 'FAIL'}] {name}" + (f" —— {detail}" if detail else ""))
    print("[selftest] " + ("全部通过" if not bad else f"存在失败项 {len(bad)} 项"))
    return 1 if bad else 0


def main():
    ap = argparse.ArgumentParser(description="交付参数单一真源读取器（S3 方案C）")
    ap.add_argument("--root", help="仓库根目录（缺省为本文件上级目录）")
    ap.add_argument("--json", action="store_true", help="打印派生后的参数字典")
    ap.add_argument("--ffmpeg-args", action="store_true", help="打印编码参数全串")
    ap.add_argument("--check", metavar="FILE", help="按真源判据体检一个成片")
    ap.add_argument("--selftest", action="store_true", help="自检")
    ap.add_argument("--get", metavar="KEY",
                    help="取单个键的原始值（供 shell 链路拼接；如 profile/level/gop_frames）")
    args = ap.parse_args()

    if args.get:
        val = get(args.get, profile(args.root))
        if val == "":
            sys.stderr.write("未知键: %s\n" % args.get)
            sys.exit(2)
        print(val)
        return
    if args.selftest:
        sys.exit(selftest(args.root))
    if args.check:
        ok, rows = check_file(args.check, profile(args.root))
        for r in rows:
            print("  " + r)
        print("=> " + ("达标" if ok else "未达标"))
        sys.exit(0 if ok else 2)
    p = profile(args.root)
    if args.ffmpeg_args:
        print(" ".join(ffmpeg_args(p)))
        return
    print(json.dumps(p, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
