#!/usr/bin/env python3
"""easyVoice 介绍视频 - 合成脚本
等 narration.wav 就位后：
1. 用 tts_meta.json 构造 SRT 字幕（文本已知，无需 ASR）
2. 生成深色背景视频（科技简报风 #0a0e14）
3. 混入配音音轨 → 粗剪 douyin.mp4
4. post_process.py 压缩+字幕+水印+片尾
"""
import os, sys, json, subprocess

os.environ["PATH"] = "/opt/homebrew/bin:/usr/local/bin:" + os.environ.get("PATH", "")

WORK = "/Volumes/PSSD/抖音视频/story/easyvoice-intro"
META_JSON = os.path.join(WORK, "tts_meta.json")
NARRATION_WAV = os.path.join(WORK, "narration.wav")
SRT_PATH = os.path.join(WORK, "captions.srt")
RAW_MP4 = os.path.join(WORK, "douyin_raw.mp4")
DOUYIN_MP4 = os.path.join(WORK, "douyin.mp4")

# ── 1. 构造 SRT 字幕 ──
def build_srt():
    with open(META_JSON, encoding="utf-8") as f:
        meta = json.load(f)
    
    def fmt(t):
        h = int(t // 3600)
        m = int(t % 3600 // 60)
        s = t % 60
        return f"{h:02d}:{m:02d}:{int(s):02d},{int((s%1)*1000):03d}"
    
    srt_lines = []
    cursor = 0.0
    for i, item in enumerate(meta, 1):
        dur = item["duration"]
        start = cursor
        end = cursor + dur
        text = item["text"]
        srt_lines.append(f"{i}\n{fmt(start)} --> {fmt(end)}\n{text}\n")
        cursor = end + 0.1  # 句间 0.1s 间隔
    
    with open(SRT_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(srt_lines))
    print(f"字幕已生成: {SRT_PATH} ({len(meta)} 条)")
    return cursor  # 总时长

# ── 2. 生成深色背景 + 配音 → 粗剪视频 ──
def build_raw_video(total_dur):
    # 深色背景 #0a0e14, 1080x1920, 30fps, 时长=配音时长
    bg_color = "0x0a0e14"
    cmd = [
        "ffmpeg", "-y", "-v", "error",
        "-f", "lavfi", "-i", f"color=c={bg_color}:s=1080x1920:r=30:d={total_dur:.1f}",
        "-i", NARRATION_WAV,
        "-c:v", "libx264", "-preset", "fast", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "128k", "-ar", "44100",
        "-shortest",
        "-movflags", "+faststart",
        RAW_MP4
    ]
    print(f"生成深色背景视频: {total_dur:.1f}s → {RAW_MP4}")
    subprocess.run(cmd, check=True)
    print(f"粗剪视频已生成: {RAW_MP4}")

# ── 3. post_process 压缩+字幕+水印+片尾 ──
def post_process():
    cmd = [
        "python3", "/Volumes/PSSD/抖音视频/post_process.py",
        RAW_MP4,
        "--srt", SRT_PATH,
        "--watermark", "jerrychen2001"
    ]
    print(f"post_process 处理中...")
    subprocess.run(cmd, check=True)
    # post_process 输出到同目录 douyin.mp4
    if os.path.exists(DOUYIN_MP4):
        print(f"成片已生成: {DOUYIN_MP4}")
    else:
        # 查找 post_process 输出
        d = os.path.dirname(RAW_MP4)
        for f in os.listdir(d):
            if f.startswith("douyin") and f.endswith(".mp4") and f != "douyin_raw.mp4":
                print(f"成片: {os.path.join(d, f)}")
                break

# ── 主流程 ──
if __name__ == "__main__":
    if not os.path.exists(NARRATION_WAV):
        print(f"ERROR: {NARRATION_WAV} 不存在，TTS 尚未完成")
        sys.exit(1)
    if not os.path.exists(META_JSON):
        print(f"ERROR: {META_JSON} 不存在")
        sys.exit(1)
    
    print("=== 1. 构造 SRT 字幕 ===")
    total_dur = build_srt()
    print(f"总时长: {total_dur:.1f}s")
    
    print("\n=== 2. 生成深色背景视频 ===")
    build_raw_video(total_dur)
    
    print("\n=== 3. post_process 压缩+字幕+水印+片尾 ===")
    post_process()
    
    print("\n=== 完成！===")
