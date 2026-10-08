#!/usr/bin/env python3
"""easyVoice 介绍视频 - PIL字幕帧合成版
1. 用 PIL 为每句生成 1080×1920 深色背景+黄字字幕图片
2. ffmpeg 按每句时长生成视频段
3. 拼接 + 混入配音 → douyin_raw.mp4
4. 直接用 ffmpeg 压缩到抖音规格（跳过 post_process 的字幕滤镜）
"""
import os, sys, json, subprocess, math
from PIL import Image, ImageDraw, ImageFont

os.environ["PATH"] = "/opt/homebrew/bin:/usr/local/bin:" + os.environ.get("PATH", "")

WORK = "/Volumes/PSSD/抖音视频/story/easyvoice-intro"
META_JSON = os.path.join(WORK, "tts_meta.json")
NARRATION_WAV = os.path.join(WORK, "narration.wav")
FRAMES_DIR = os.path.join(WORK, "pil_frames")
SEGMENTS_DIR = os.path.join(WORK, "segments")
RAW_MP4 = os.path.join(WORK, "douyin_raw.mp4")
DOUYIN_MP4 = os.path.join(WORK, "douyin.mp4")
WATERMARK = "jerrychen2001"

os.makedirs(FRAMES_DIR, exist_ok=True)
os.makedirs(SEGMENTS_DIR, exist_ok=True)

# 加载元数据
with open(META_JSON, encoding="utf-8") as f:
    meta = json.load(f)

# ── 字幕画幅参数 ──
W, H = 1080, 1920
BG_COLOR = (10, 14, 20)        # #0a0e14
SUB_COLOR = (255, 200, 50)      # 黄字
OUTLINE_COLOR = (0, 0, 0)       # 黑边
WATERMARK_COLOR = (255, 255, 255, 140)  # 半透白

FONT_PATH = "/System/Library/Fonts/STHeiti Medium.ttc"
FONT_MAIN = ImageFont.truetype(FONT_PATH, 72)
FONT_SUB = ImageFont.truetype(FONT_PATH, 64)
FONT_WM = ImageFont.truetype(FONT_PATH, 36)

def wrap_text(text, font, max_width, draw):
    """按像素宽度折行"""
    lines = []
    current = ""
    for ch in text:
        test = current + ch
        bbox = draw.textbbox((0, 0), test, font=font)
        if bbox[2] - bbox[0] > max_width and current:
            lines.append(current)
            current = ch
        else:
            current = test
    if current:
        lines.append(current)
    return lines

def make_frame(text, out_path, is_hook=False):
    """生成一帧 1080×1920 深色背景+字幕图片"""
    img = Image.new("RGB", (W, H), BG_COLOR)
    draw = ImageDraw.Draw(img)
    
    # 字体选择（钩子句用大字）
    font = FONT_MAIN if is_hook else FONT_SUB
    
    # 折行（最大宽度 900px，留 90px 左右边距）
    lines = wrap_text(text, font, 900, draw)
    
    # 计算总高度
    line_heights = []
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        line_heights.append(bbox[3] - bbox[1] + 20)
    total_h = sum(line_heights) + (len(lines) - 1) * 10
    
    # 居中偏下（MarginV 约 400px from bottom）
    y = H - 500 - total_h // 2
    
    for i, line in enumerate(lines):
        bbox = draw.textbbox((0, 0), line, font=font)
        w = bbox[2] - bbox[0]
        x = (W - w) // 2
        # 黑边描边
        for ox, oy in [(-2,-2),(-2,2),(2,-2),(2,2),(-2,0),(2,0),(0,-2),(0,2)]:
            draw.text((x+ox, y+oy), line, fill=OUTLINE_COLOR, font=font)
        # 黄字
        draw.text((x, y), line, fill=SUB_COLOR, font=font)
        y += line_heights[i] + 10
    
    # 水印（右下角）
    wm_bbox = draw.textbbox((0, 0), WATERMARK, font=FONT_WM)
    wm_w = wm_bbox[2] - wm_bbox[0]
    draw.text((W - wm_w - 40, H - 100), WATERMARK, fill=(255,255,255,140), font=FONT_WM)
    
    img.save(out_path, quality=95)

# ── 1. 为每句生成字幕帧 ──
print("=== 1. 生成字幕帧图片 ===")
for item in meta:
    idx = item["index"]
    text = item["text"]
    is_hook = (idx == 1)
    frame_path = os.path.join(FRAMES_DIR, f"frame_{idx:02d}.png")
    make_frame(text, frame_path, is_hook)
    print(f"  [{idx:02d}] {text[:30]}... → {frame_path}")

# ── 2. 每帧生成视频段 ──
print("\n=== 2. 生成视频段 ===")
segment_files = []
for item in meta:
    idx = item["index"]
    dur = item["duration"]
    frame_path = os.path.join(FRAMES_DIR, f"frame_{idx:02d}.png")
    seg_path = os.path.join(SEGMENTS_DIR, f"seg_{idx:02d}.mp4")
    
    # 图片 → 视频（30fps，指定时长）
    cmd = [
        "ffmpeg", "-y", "-v", "error",
        "-loop", "1", "-i", frame_path,
        "-t", f"{dur:.2f}",
        "-r", "30",
        "-c:v", "libx264", "-preset", "fast",
        "-pix_fmt", "yuv420p",
        "-vf", "scale=1080:1920",
        seg_path
    ]
    subprocess.run(cmd, check=True)
    segment_files.append(seg_path)
    print(f"  [{idx:02d}] {dur:.1f}s → {seg_path}")

# ── 3. 拼接视频段 + 混入音频 ──
print("\n=== 3. 拼接视频段 ===")
concat_list = os.path.join(WORK, "concat_segments.txt")
with open(concat_list, "w") as f:
    for seg in segment_files:
        f.write(f"file '{seg}'\n")

# 先拼接视频（无音轨）
silent_mp4 = os.path.join(WORK, "silent_concat.mp4")
subprocess.run([
    "ffmpeg", "-y", "-v", "error",
    "-f", "concat", "-safe", "0", "-i", concat_list,
    "-c:v", "libx264", "-preset", "fast", "-pix_fmt", "yuv420p",
    silent_mp4
], check=True)

# 混入音频
subprocess.run([
    "ffmpeg", "-y", "-v", "error",
    "-i", silent_mp4, "-i", NARRATION_WAV,
    "-c:v", "copy",
    "-c:a", "aac", "-b:a", "128k", "-ar", "44100",
    "-shortest", "-movflags", "+faststart",
    RAW_MP4
], check=True)
print(f"粗剪视频: {RAW_MP4}")

# 清理临时文件
os.remove(silent_mp4)

# ── 4. 压缩到抖音规格 ──
print("\n=== 4. 压缩到抖音规格 ===")
subprocess.run([
    "ffmpeg", "-y", "-v", "error",
    "-i", RAW_MP4,
    "-c:v", "libx264", "-preset", "medium",
    "-profile:v", "high", "-level", "4.2",
    "-pix_fmt", "yuv420p",
    "-b:v", "8M", "-maxrate", "10M", "-bufsize", "12M",
    "-r", "30", "-g", "60",
    "-c:a", "aac", "-b:a", "128k", "-ar", "44100",
    "-movflags", "+faststart",
    DOUYIN_MP4
], check=True)
print(f"成片: {DOUYIN_MP4}")

# ── 5. 追加标准片尾 ──
print("\n=== 5. 追加标准片尾 ===")
# 准备 script.json 供 append_epilogue 使用
script_json = os.path.join(WORK, "script.json")
epilogue_data = {
    "epilogue": {
        "enabled": True,
        "text": "关注 jerrychen2001，评论区聊聊你还想拆哪个项目。"
    }
}
with open(script_json, "w", encoding="utf-8") as f:
    json.dump(epilogue_data, f, ensure_ascii=False, indent=2)

# 复制 narration.wav 到成片目录（append_epilogue 需要）
narration_copy = os.path.join(os.path.dirname(DOUYIN_MP4), "narration.wav")
if not os.path.exists(narration_copy):
    import shutil
    shutil.copy2(NARRATION_WAV, narration_copy)

result = subprocess.run([
    "python3", "/Volumes/PSSD/抖音视频/append_epilogue.py",
    os.path.dirname(DOUYIN_MP4), "--force"
], capture_output=True, text=True)
print(result.stdout[-500:] if result.stdout else "")
if result.returncode != 0:
    print(f"片尾追加失败: {result.stderr[-300:]}")

# ── 6. 验收 ──
print("\n=== 6. 验收 ===")
final = os.path.join(os.path.dirname(DOUYIN_MP4), "douyin_epilogue.mp4")
if not os.path.exists(final):
    final = DOUYIN_MP4

r = subprocess.run(
    ["ffprobe", "-v", "quiet", "-print_format", "json",
     "-show_streams", "-show_format", final],
    capture_output=True, text=True
)
data = json.loads(r.stdout)
v = next(s for s in data["streams"] if s["codec_type"] == "video")
a = next(s for s in data["streams"] if s["codec_type"] == "audio")
print(f"成片: {final}")
print(f"分辨率: {v['width']}x{v['height']}")
print(f"帧率: {eval(v['r_frame_rate']):.0f}fps")
print(f"编码: {v['codec_name']}")
print(f"音频: {a['codec_name']} {a['sample_rate']}Hz")
print(f"时长: {float(data['format']['duration']):.1f}s")
print(f"文件大小: {os.path.getsize(final)/1024/1024:.1f}MB")
