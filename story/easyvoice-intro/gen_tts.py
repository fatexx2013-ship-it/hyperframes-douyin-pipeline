#!/usr/bin/env python3
"""easyVoice 介绍视频 - 逐句 Qwen3-TTS 御姐音配音"""
import os, sys, json, time, subprocess

os.environ["PATH"] = "/opt/homebrew/bin:/usr/local/bin:" + os.environ.get("PATH", "")

WORK = "/Volumes/PSSD/抖音视频/story/easyvoice-intro"
SCRIPT_TXT = os.path.join(WORK, "script.txt")
AUDIO_DIR = os.path.join(WORK, "audio_parts")
os.makedirs(AUDIO_DIR, exist_ok=True)

# 读取解说稿按句拆分
text = open(SCRIPT_TXT, encoding='utf-8').read().strip()
lines = [l.strip() for l in text.split('\n') if l.strip()]

# 过滤掉非解说内容（如"AI生成"水印行）
lines = [l for l in lines if not l.startswith('AI生成')]

print(f"共 {len(lines)} 句待配音")

# 使用 generate_qa_video.py 的 generate_qwen3_tts
sys.path.insert(0, "/Volumes/PSSD/抖音视频")
from generate_qa_video import generate_qwen3_tts

results = []
for i, line in enumerate(lines, 1):
    out_wav = os.path.join(AUDIO_DIR, f"part_{i:02d}.wav")
    if os.path.exists(out_wav) and os.path.getsize(out_wav) > 1000:
        dur = subprocess.run(["ffprobe","-v","quiet","-show_entries","format=duration",
            "-of","default=noprint_wrappers=1:nokey=1", out_wav],
            capture_output=True, text=True).stdout.strip()
        print(f"  [{i:02d}/{len(lines)}] 跳过(已存在) {dur}s")
        results.append({"index": i, "path": out_wav, "text": line, "duration": float(dur)})
        continue
    print(f"  [{i:02d}/{len(lines)}] 配音中: {line[:30]}...")
    t0 = time.time()
    # 全句统一 yujie_thoughtful（慵懒御姐音），与标准片尾同源，消除"换主播"割裂感
    ok = generate_qwen3_tts(line, out_wav, "answer", force_emotion="thoughtful")
    elapsed = time.time() - t0
    if ok and os.path.exists(out_wav):
        # 转 24k mono
        norm_wav = out_wav.replace(".wav", "_24k.wav")
        subprocess.run(["ffmpeg","-y","-v","quiet","-i",out_wav,
            "-ar","24000","-ac","1",norm_wav], check=True)
        os.replace(norm_wav, out_wav)
        dur = subprocess.run(["ffprobe","-v","quiet","-show_entries","format=duration",
            "-of","default=noprint_wrappers=1:nokey=1", out_wav],
            capture_output=True, text=True).stdout.strip()
        print(f"    OK ({elapsed:.1f}s) 时长 {dur}s")
        results.append({"index": i, "path": out_wav, "text": line, "duration": float(dur)})
    else:
        print(f"    FAIL ({elapsed:.1f}s)")

# 保存元数据
meta_path = os.path.join(WORK, "tts_meta.json")
with open(meta_path, "w", encoding="utf-8") as f:
    json.dump(results, f, ensure_ascii=False, indent=2)

# 拼接所有音频片段
print("\n拼接音频...")
list_file = os.path.join(WORK, "concat_list.txt")
with open(list_file, "w") as f:
    for r in results:
        f.write(f"file '{r['path']}'\n")

narration_wav = os.path.join(WORK, "narration.wav")
subprocess.run(["ffmpeg","-y","-v","quiet","-f","concat","-safe","0",
    "-i",list_file,"-ar","24000","-ac","1",narration_wav], check=True)

total_dur = subprocess.run(["ffprobe","-v","quiet","-show_entries","format=duration",
    "-of","default=noprint_wrappers=1:nokey=1",narration_wav],
    capture_output=True, text=True).stdout.strip()
print(f"\n配音完成！总时长 {total_dur}s → {narration_wav}")
print(f"元数据 → {meta_path}")
