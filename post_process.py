#!/usr/bin/env python3
"""
抖音视频后期处理器
- 压缩到抖音推荐规格：H.264 High@4.2, 1080x1920, 30fps, capped-CRF(crf18, ≤10M 瞬时), AAC 128k
  （上述取值不写死在本文件：由 config/param_contract.json 单一真源提供，见下方 _delivery()）
- 可选：叠加 SRT 字幕（抖音风：黄字黑边大字号）
- 可选：叠加水印（右下角）
- 可选：追加片尾关注卡（2-3 秒）
- 默认：追加标准片尾（关注引导 + 评论区互动，见 epilogue_template.json / append_epilogue.py）

用法:
  python post_process.py <input.mp4> [--srt subtitles.srt] [--watermark "@大瑞"] [--end-card] [--no-epilogue]
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))


# 回落用常量（真源 1.3.0 同值）：capped-CRF 为交付编码策略 —— 质量档取 CRF，
# -maxrate/-bufsize 只作瞬时上限；8M 已降级为历史目标参考，不再作为 -b:v 目标输出。
DOUYIN_VIDEO_RATE_CONTROL = "capped-crf"
DOUYIN_VIDEO_CRF = 18
DOUYIN_VIDEO_BITRATE = "8M"
DOUYIN_AUDIO_BITRATE = "128k"
DOUYIN_MAX_BITRATE = "10M"
DOUYIN_BUFSIZE = "12M"


# ── 交付参数单一真源（S3 方案C）──────────────────────────────────────────────
# 真源：config/param_contract.json → toolchain_pins.encoder_chain（编码/码率/GOP）
#       + fields（画幅 fields.resolution_aspect、帧率 fields.fps、音频 fields.audio_sample_rate_channels）
# 读取器：scripts/encode_profile.py；三链共享同一份参数，本文件不再自行维护第二套常量
# （真源读不到才回落，且必须留痕）。
_DELIVERY_CACHE = None
_ENC_MOD = None  # 单一真源读取器模块（scripts/encode_profile.py），回落时为 None
DELIVERY_FALLBACK = {
    "width": 1080, "height": 1920, "fps": 30,
    "video_codec": "h264", "video_preset": "medium",
    "profile": "High", "level": "4.2", "pix_fmt": "yuv420p",
    "gop_frames": 60, "gop_accept_max_frames": 120,
    "video_rate_control": "capped-crf", "video_crf": 18,
    "video_bitrate": "8M", "video_maxrate": "10M", "video_bufsize": "12M",
    "video_bitrate_max_accept": "11M",
    "audio_codec": "aac", "audio_sample_rate": 44100,
    "audio_channels_accept": [1, 2], "audio_bitrate": "128k",
}


def _delivery():
    """取交付参数（进程内缓存）。真源不可用时回落内置默认并在 stderr 留痕。"""
    global _DELIVERY_CACHE, _ENC_MOD
    if _DELIVERY_CACHE is None:
        try:
            sdir = os.path.join(SCRIPT_DIR, "scripts")
            if sdir not in sys.path:
                sys.path.insert(0, sdir)
            import encode_profile  # 单一真源读取器（scripts/encode_profile.py）
            _DELIVERY_CACHE = encode_profile.profile(SCRIPT_DIR)
            _ENC_MOD = encode_profile
            meta = _DELIVERY_CACHE.get("_meta") or {}
            if meta.get("fallback_used"):
                print("  WARN: 交付参数真源回落（%s）→ 本次使用内置默认值"
                      % meta.get("fallback_reason"), file=sys.stderr)
        except Exception as exc:  # noqa: BLE001
            print("  WARN: 读不到交付参数真源（%s: %s）→ 回落内置默认（与合同同值）"
                  % (type(exc).__name__, exc), file=sys.stderr)
            _DELIVERY_CACHE = dict(DELIVERY_FALLBACK)
    return _DELIVERY_CACHE


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


def _enc_args(d=None):
    """视频+音频+封装参数串（S3：值取自单一真源，本文件不维护第二套常量）。

    真源读取器可用时直接由它派生；仅当读取器不可用（回落）时才用下方内置映射，
    两处取值同源自合同，回落路径亦留痕（见 _delivery() 的 WARN）。
    码率控制：capped-crf —— 输出 ``-crf <video_crf>``，**不输出 -b:v 目标**
    （S3 材料 C5「8M 目标无人锁死」已解除）；仅当合同声明其它策略时才回落 -b:v。
    """
    d = d or _delivery()
    if _ENC_MOD is not None:
        return _ENC_MOD.video_args(d) + _ENC_MOD.audio_args(d) + _ENC_MOD.mux_args(d)
    rc = str(d.get("video_rate_control") or DOUYIN_VIDEO_RATE_CONTROL).strip().lower()
    if rc in ("capped-crf", "crf"):
        rc_args = ["-crf", str(int(d.get("video_crf") or DOUYIN_VIDEO_CRF))]
    else:
        rc_args = ["-b:v", str(d.get("video_bitrate") or DOUYIN_VIDEO_BITRATE)]
    return [
        "-c:v", "libx264", "-preset", str(d.get("video_preset") or "medium"),
        "-profile:v", str(d.get("profile") or "High").lower(),
        "-level", str(d.get("level") or "4.2"),
        "-pix_fmt", str(d.get("pix_fmt") or "yuv420p"),
        *rc_args,
        "-maxrate", str(d.get("video_maxrate") or DOUYIN_MAX_BITRATE),
        "-bufsize", str(d.get("video_bufsize") or DOUYIN_BUFSIZE),
        "-r", str(int(float(d.get("fps") or 30))),
        "-g", str(int(d.get("gop_frames") or 60)),
        "-c:a", str(d.get("audio_codec") or "aac"),
        "-b:a", str(d.get("audio_bitrate") or DOUYIN_AUDIO_BITRATE),
        "-ar", str(int(d.get("audio_sample_rate") or 44100)),
    ]


def run(cmd, check=True):
    print("  $", " ".join(str(c) for c in cmd[:12]) + ("..." if len(cmd) > 12 else ""))
    r = subprocess.run(cmd, capture_output=True, text=True)
    if check and r.returncode != 0:
        print("  ERROR:", r.stderr[:800])
        sys.exit(1)
    return r


def probe_duration(path):
    r = subprocess.run(
        ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", path],
        capture_output=True, text=True
    )
    return float(r.stdout.strip())


def has_filter(name):
    """检测当前 ffmpeg 是否编译了指定滤镜"""
    try:
        r = subprocess.run(["ffmpeg", "-hide_banner", "-filters"], capture_output=True, text=True)
        return name in r.stdout
    except Exception:
        return False


# 交付画幅/帧率/码率上限的「回落默认值」；真源可用时判定值取自 _delivery()（S3）
TARGET_WIDTH = 1080
TARGET_HEIGHT = 1920
TARGET_FPS = 30.0
TARGET_MAX_BITRATE = 11 * 1000 * 1000


def probe_stream_spec(path):
    """读取首个视频流 + 音频流的关键规格，失败返回 None"""
    r = subprocess.run(
        ["ffprobe", "-v", "quiet", "-print_format", "json",
         "-show_streams", "-show_format", path],
        capture_output=True, text=True,
    )
    if r.returncode != 0:
        return None
    try:
        data = json.loads(r.stdout or "{}")
    except Exception:
        return None
    streams = data.get("streams", [])
    v = next((s for s in streams if s.get("codec_type") == "video"), None)
    a = next((s for s in streams if s.get("codec_type") == "audio"), None)
    if not v:
        return None
    fps = 0.0
    try:
        num, den = (v.get("r_frame_rate") or "0/1").split("/")
        fps = float(num) / float(den) if float(den) else 0.0
    except Exception:
        pass
    bitrate = 0
    for src in (v.get("bit_rate"), (data.get("format") or {}).get("bit_rate")):
        try:
            if src and int(src) > 0:
                bitrate = int(src)
                break
        except Exception:
            continue
    return {
        "vcodec": v.get("codec_name"),
        "width": int(v.get("width") or 0),
        "height": int(v.get("height") or 0),
        "fps": fps,
        "vbitrate": bitrate,
        "acodec": (a or {}).get("codec_name"),
        # S3：补采交付判据所需四项。此前缺失，导致 hyperframes 直出的
        # 48000Hz / High@L5.0 / GOP250 中间件被判"已达标" → copy 直出，绕过归一化。
        "profile": v.get("profile"),
        "level": v.get("level"),
        "pix_fmt": v.get("pix_fmt"),
        "sample_rate": int((a or {}).get("sample_rate") or 0),
        "channels": int((a or {}).get("channels") or 0),
    }


def is_delivery_ready(path):
    """判断输入是否已满足抖音交付规格；返回 (bool, 原因)

    S3 收口修正（方案B 顺序耦合①）：本函数不再自带判据与阈值，一律转调共享断言
    scripts/encode_profile.py::assert_delivery_spec()。
    此前六项判据（profile/level/pix_fmt/采样率/声道/GOP）+ 码率上限在本文件另写
    一套，与真源读取器构成"第二套判据"（使参数散落点从 6 处变 7 处）；现收敛为单点：
    探测与判定都在 encode_profile，本文件只做转调、缓存与留痕。

    注：判据不可用时**不得放行**（fail-closed）——宁可重编码，也不把未验证的源
    当达标源 copy 直出（否则 48000Hz/High@L5.0 中间件会再次绕过归一化）。
    """
    if _ENC_MOD is None:
        _delivery()  # 再试一次初始化（内含 WARN 留痕）
    if _ENC_MOD is None:
        return False, "交付判据不可用：scripts/encode_profile.py 未加载（拒绝按达标直通）"
    return _ENC_MOD.assert_delivery_spec(path, _delivery())


def compress_douyin(input_mp4, output_mp4, srt=None, watermark=None):
    """抖音规格压缩 + 可选字幕/水印叠加（编码参数取自单一真源，S3）"""
    d = _delivery()
    tw, th = int(d.get("width") or TARGET_WIDTH), int(d.get("height") or TARGET_HEIGHT)
    vf_parts = []

    # 确保交付画幅（真源 width×height）
    vf_parts.append(f"scale={tw}:{th}:force_original_aspect_ratio=decrease")
    vf_parts.append(f"pad={tw}:{th}:(ow-iw)/2:(oh-ih)/2:color=#0a0a12")

    # 字幕（抖音风：大字号、黄字黑边、居中偏下）
    if srt and os.path.exists(srt):
        # 转义路径中的特殊字符（: 需要 \\:）
        srt_escaped = srt.replace(":", "\\:").replace("'", "\\'")
        vf_parts.append(
            f"subtitles='{srt_escaped}':force_style='"
            f"FontName=PingFang SC,FontSize=22,PrimaryColour=&H0024BFFB,"  # 黄字 &HAABBGGRR
            f"OutlineColour=&H00000000,BorderStyle=1,Outline=2,Shadow=1,"
            f"Alignment=2,MarginV=180,Bold=1'"
        )

    # 水印（右下角）
    if watermark:
        if not has_filter("drawtext"):
            print("  WARN: 当前 ffmpeg 未编译 drawtext 滤镜，跳过水印叠加（水印请由生成阶段写入画面）")
        else:
            wm_escaped = watermark.replace("'", "\\'").replace(":", "\\:")
            vf_parts.append(
                f"drawtext=text='{wm_escaped}':fontfile=/System/Library/Fonts/PingFang.ttc:"
                f"fontsize=46:fontcolor=white@0.55:borderw=2:bordercolor=black@0.4:"
                f"x=w-tw-40:y=h-th-100"
            )

    vf = ",".join(vf_parts)

    # 编码参数全部取自单一真源（S3）：profile/level/GOP/码率/音频规格不再本地硬编码
    cmd = ["ffmpeg", "-y", "-i", input_mp4, "-vf", vf] + _enc_args(d) + [output_mp4]
    run(cmd)


def append_end_card(input_mp4, output_mp4, title="点关注 不迷路", sub="每天一个 AI 小知识", duration=2.5):
    """生成片尾关注卡并追加到视频末尾"""
    dur = probe_duration(input_mp4)
    d = _delivery()
    tw, th = int(d.get("width") or TARGET_WIDTH), int(d.get("height") or TARGET_HEIGHT)
    fps = int(float(d.get("fps") or TARGET_FPS))
    sr = int(d.get("audio_sample_rate") or 44100)

    # 用 lavfi 生成与交付同画幅的片尾（深色底 + 大标题 + 副标题 + 淡入淡出）
    # 画幅/帧率/音频采样率与编码参数取自单一真源（S3），与压缩段同源同规格
    end_cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", f"color=c=#0a0a12:s={tw}x{th}:d={duration}:r={fps}",
        "-f", "lavfi", "-i", f"anullsrc=r={sr}:cl=stereo:d={duration}",
        "-vf",
        f"drawtext=fontfile=/System/Library/Fonts/PingFang.ttc:text='{title}':"
        f"fontsize=110:fontcolor=#fbbf24:borderw=4:bordercolor=black:"
        f"x=(w-text_w)/2:y=(h-text_h)/2-40,"
        f"drawtext=fontfile=/System/Library/Fonts/PingFang.ttc:text='{sub}':"
        f"fontsize=52:fontcolor=white@0.85:"
        f"x=(w-text_w)/2:y=(h-text_h)/2+110,"
        f"fade=t=in:st=0:d=0.4,fade=t=out:st={duration-0.4}:d=0.4",
    ] + _enc_args(d) + [
        "-shortest",
        "/tmp/_endcard.mp4"
    ]
    run(end_cmd)

    # concat
    list_file = "/tmp/_concat.txt"
    with open(list_file, "w") as f:
        f.write(f"file '{input_mp4}'\nfile '/tmp/_endcard.mp4'\n")
    concat_cmd = [
        "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", list_file,
        "-c", "copy", "-movflags", "+faststart", output_mp4
    ]
    run(concat_cmd)



def append_standard_epilogue(run_dir):
    """追加标准片尾（关注引导 + 评论区互动）。

    依赖同目录 append_epilogue.py + epilogue_template.json；
    需 run_dir 内存在 narration.wav（用于重建整条音轨）。
    任何前置条件缺失都只跳过并提示，不影响已产出的 douyin.mp4。
    """
    epi = os.path.join(SCRIPT_DIR, "append_epilogue.py")
    if not os.path.exists(epi):
        print("\n[3/3] 未找到 append_epilogue.py，跳过片尾追加")
        return
    if not os.path.exists(os.path.join(run_dir, "narration.wav")):
        print("\n[3/3] 缺少 narration.wav，跳过片尾追加")
        return

    enabled = True
    sp = os.path.join(run_dir, "script.json")
    if os.path.exists(sp):
        try:
            with open(sp, encoding="utf-8") as f:
                enabled = (json.load(f) or {}).get("epilogue", {}).get("enabled", True)
        except Exception:
            pass
    if enabled is False:
        print("\n[3/3] script.json 中 epilogue.enabled=false，跳过片尾追加")
        return

    exe = None
    for cand in (sys.executable, shutil.which("python3"), "/usr/bin/python3"):
        if cand and subprocess.run([cand, "-c", "import numpy"],
                                   capture_output=True).returncode == 0:
            exe = cand
            break
    if not exe:
        print("\n[3/3] 未找到含 numpy 的 Python 解释器，跳过片尾追加")
        return

    print("\n[3/3] 追加标准片尾（关注引导 + 评论区互动）...")
    subprocess.run([exe, epi, run_dir, "--force"])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("input", help="输入 mp4（通常是 output.mp4）")
    ap.add_argument("--srt", help="叠加 SRT 字幕（抖音风黄字黑边）")
    ap.add_argument("--watermark", help="右下角水印文字，如 @大瑞")
    ap.add_argument("--end-card", action="store_true", help="追加 2.5s 片尾关注卡")
    ap.add_argument("--end-title", default="点关注 不迷路")
    ap.add_argument("--end-sub", default="每天一个 AI 小知识")
    ap.add_argument("-o", "--output", help="输出路径，默认同目录 douyin.mp4")
    ap.add_argument("--no-epilogue", action="store_true",
                    help="不追加标准片尾（默认会追加 关注引导 + 评论区互动 片尾）")
    ap.add_argument("--force-reencode", action="store_true",
                    help="即使输入已满足交付规格也强制重编码（默认达标则直通复用，不再损失画质）")
    args = ap.parse_args()

    input_mp4 = os.path.abspath(args.input)
    if not os.path.exists(input_mp4):
        print(f"ERROR: input not found: {input_mp4}")
        sys.exit(1)

    out_dir = os.path.dirname(input_mp4)
    if args.output:
        final_out = os.path.abspath(args.output)
    else:
        final_out = os.path.join(out_dir, "douyin.mp4")

    print(f"=== 抖音后期处理 ===")
    print(f"  输入: {input_mp4}")
    print(f"  时长: {probe_duration(input_mp4):.1f}s")

    # 第一步：规格体检（已达标则直通）或压缩 + 可选字幕/水印
    tmp_compressed = os.path.join(out_dir, "_compressed.mp4")
    spec = probe_stream_spec(input_mp4)
    if spec:
        print(f"  规格: {spec['vcodec']} {spec['width']}x{spec['height']} "
              f"@{spec['fps']:.2f}fps {spec['vbitrate'] / 1e6:.2f}Mbps / 音频 {spec['acodec']}")

    ready, why = is_delivery_ready(input_mp4)
    skip = ready and not args.srt and not args.watermark and not args.force_reencode

    if skip:
        print(f"\n[1/2] 规格已达交付标准（{why}）→ 跳过重编码，直接复用源文件")
        shutil.copy2(input_mp4, tmp_compressed)
    else:
        if args.force_reencode:
            reason = "指定 --force-reencode"
        elif ready and (args.srt or args.watermark):
            reason = "需叠加字幕/水印"
        else:
            reason = why
        _d = _delivery()
        print(f"\n[1/2] 抖音规格压缩 (H.264 {_d.get('profile')}@{_d.get('level')}, "
              f"{_d.get('width')}x{_d.get('height')}, {int(float(_d.get('fps') or 30))}fps, "
              f"capped-CRF crf{_d.get('video_crf')} ≤{_d.get('video_maxrate')})"
              f"... 原因: {reason}")
        compress_douyin(input_mp4, tmp_compressed, srt=args.srt, watermark=args.watermark)

    # 第二步：可选片尾
    if args.end_card:
        print(f"\n[2/2] 追加片尾关注卡 ({args.end_title})...")
        append_end_card(tmp_compressed, final_out, title=args.end_title, sub=args.end_sub)
        os.remove(tmp_compressed)
    else:
        try:
            os.rename(tmp_compressed, final_out)
        except OSError as e:
            # 跨文件系统（EXDEV）或目标卷不可 rename：退回 copy+删（-o 指向他卷时出现）
            if getattr(e, "errno", None) != 18:
                raise
            print(f"  [注] 目标与临时件跨卷，改用复制落盘：{final_out}")
            shutil.move(tmp_compressed, final_out)
        print(f"\n[2/2] 跳过片尾卡")

    size_mb = os.path.getsize(final_out) / 1024 / 1024
    dur = probe_duration(final_out)
    print(f"\n[2/3] 完成: {final_out}")
    print(f"   时长 {dur:.1f}s / 体积 {size_mb:.1f}MB")

    # 第三步：标准片尾（默认追加，可用 --no-epilogue 关闭）
    if args.no_epilogue:
        print("\n[3/3] 已通过 --no-epilogue 跳过片尾追加")
    else:
        append_standard_epilogue(out_dir)


if __name__ == "__main__":
    main()
