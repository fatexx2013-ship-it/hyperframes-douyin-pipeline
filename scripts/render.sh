#!/bin/bash
# FFmpeg 终合成脚本
# 将 HyperFrames 渲染的视频 + 字幕 + 配音 + BGM 合成为最终成片
#
# 用法：
#   ./scripts/render.sh \
#       --composition composition.mp4 \
#       --narration story/001/narration.wav \
#       --bgm story/001/bgm.mp3 \
#       --captions story/001/captions.srt \
#       --output output/final.mp4
#
#   # 或使用环境变量（推荐）：
#   export STORY_DIR=story/001-ai-future
#   ./scripts/render.sh

set -euo pipefail

# ── 默认值 ─────────────────────────────────────────────────

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PIPELINE_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

STORY_DIR="${STORY_DIR:-story}"
COMPOSITION=""
NARRATION=""
BGM=""
CAPTIONS=""
OUTPUT=""
VIDEO_WIDTH="${VIDEO_WIDTH:-1080}"
VIDEO_HEIGHT="${VIDEO_HEIGHT:-1920}"
FPS="${FPS:-30}"
CRF="${CRF:-20}"

# ── P0 编码链改造（E6） ────────────────────────────────────
# HF_ENCODER: videotoolbox(默认, Apple Silicon 硬件编码) | libx264(兼容回退)
# 硬件编码模式下终合成直接输出抖音交付规格，post_process.py 检测到达标即跳过重编码
HF_ENCODER="${HF_ENCODER:-videotoolbox}"
HF_VIDEO_BITRATE="${HF_VIDEO_BITRATE:-8M}"
HF_MAXRATE="${HF_MAXRATE:-10M}"
HF_BUFSIZE="${HF_BUFSIZE:-12M}"
HF_PRESET="${HF_PRESET:-medium}"

# ── 交付编码参数单一真源（S3 方案C · 收口修正） ─────────────
# 真源：config/param_contract.json → toolchain_pins.encoder_chain
# 读取优先级：jq → python3 scripts/encode_profile.py --get → 内置默认
# 硬约束：内置默认必须与真源同值（level=4.2）；离线也不得回到历史值 4.1，
#         否则口令会重新出现 4.1/4.2 两值并存。
PARAM_CONTRACT="${PARAM_CONTRACT:-${PIPELINE_ROOT}/config/param_contract.json}"
ENCODE_PROFILE_PY="${PIPELINE_ROOT}/scripts/encode_profile.py"

_chain_get() {  # $1=encoder_chain 键名  $2=内置默认（与真源同值）
    local key="$1" fb="$2" v=""
    if [[ -f "$PARAM_CONTRACT" ]]; then
        if command -v jq >/dev/null 2>&1; then
            v="$(jq -r --arg k "$key" '.toolchain_pins.encoder_chain[$k] // empty' "$PARAM_CONTRACT" 2>/dev/null || true)"
        fi
        if [[ -z "$v" ]] && command -v python3 >/dev/null 2>&1 && [[ -f "$ENCODE_PROFILE_PY" ]]; then
            v="$(python3 "$ENCODE_PROFILE_PY" --get "$key" 2>/dev/null || true)"
        fi
    fi
    if [[ -z "$v" || "$v" == "null" ]]; then
        v="$fb"
        echo "  提示: 真源未取到 encoder_chain.$key → 使用内置默认 $fb（与真源同值）" >&2
    fi
    printf '%s' "$v"
}
HF_PROFILE="${HF_PROFILE:-$(_chain_get profile High)}"
HF_LEVEL="${HF_LEVEL:-$(_chain_get level 4.2)}"

# ── 逐字卡拉OK字幕（默认关闭；关闭 = 一键回退整句 SRT->ASS 链路） ──
# KARAOKE: auto(默认, 读 config/karaoke.json 的 enabled) | on | off
KARAOKE="${KARAOKE:-auto}"
KARAOKE_CONFIG="${KARAOKE_CONFIG:-${PIPELINE_ROOT}/config/karaoke.json}"

# ── 参数解析 ───────────────────────────────────────────────

while [[ $# -gt 0 ]]; do
    case $1 in
        --composition) COMPOSITION="$2"; shift 2 ;;
        --narration)   NARRATION="$2";   shift 2 ;;
        --bgm)         BGM="$2";         shift 2 ;;
        --captions)    CAPTIONS="$2";    shift 2 ;;
        --output)      OUTPUT="$2";      shift 2 ;;
        --width)       VIDEO_WIDTH="$2"; shift 2 ;;
        --height)      VIDEO_HEIGHT="$2"; shift 2 ;;
        --fps)         FPS="$2";         shift 2 ;;
        --crf)         CRF="$2";         shift 2 ;;
        --karaoke)     KARAOKE="on";     shift ;;
        --no-karaoke)  KARAOKE="off";    shift ;;
        --karaoke-config) KARAOKE_CONFIG="$2"; shift 2 ;;
        --help)
            echo "用法: $0 [--composition VIDEO] [--narration WAV] [--bgm MP3] [--captions SRT] [--output MP4]"
            echo ""
            echo "环境变量:"
            echo "  STORY_DIR      素材目录 (默认: story)"
            echo "  VIDEO_WIDTH    输出宽度 (默认: 1080)"
            echo "  VIDEO_HEIGHT   输出高度 (默认: 1920)"
            echo "  FPS            帧率 (默认: 30)"
            echo "  CRF            编码质量 (默认: 20, 仅 libx264 模式生效)"
            echo "  HF_ENCODER     视频编码器: videotoolbox(默认,硬件) | libx264"
            echo "  HF_VIDEO_BITRATE 视频码率 (默认: 8M, 抖音交付规格)"
            echo "  HF_MAXRATE     峰值码率 (默认: 10M)"
            echo "  HF_BUFSIZE     码率缓冲 (默认: 12M)"
            echo "  HF_PROFILE     视频 profile (默认: 取真源 encoder_chain.profile, 即 High)"
            echo "  HF_LEVEL       视频 level (默认: 取真源 encoder_chain.level, 即 4.2)"
            echo "  KARAOKE        逐字卡拉OK字幕: auto(默认,读 config/karaoke.json) | on | off"
            echo "                 关闭/KARAOKE=off 即回退到整句 SRT->ASS 烧录（默认链路）"
            echo "  KARAOKE_CONFIG 卡拉OK配置路径 (默认: config/karaoke.json)"
            exit 0
            ;;
        *) echo "未知参数: $1"; exit 1 ;;
    esac
done

# ── 自动检测 ───────────────────────────────────────────────

if [[ -z "$COMPOSITION" ]]; then
    COMPOSITION="${STORY_DIR}/composition.mp4"
fi
if [[ -z "$NARRATION" ]]; then
    # 优先找 mp3（Edge TTS 输出），回退到 wav（Kokoro 输出）
    if [[ -f "${STORY_DIR}/narration.mp3" ]]; then
        NARRATION="${STORY_DIR}/narration.mp3"
    else
        NARRATION="${STORY_DIR}/narration.wav"
    fi
fi
if [[ -z "$BGM" ]]; then
    if [[ -f "${STORY_DIR}/bgm.mp3" ]]; then
        BGM="${STORY_DIR}/bgm.mp3"
    else
        BGM=""
    fi
fi
if [[ -z "$CAPTIONS" ]]; then
    CAPTIONS="${STORY_DIR}/captions.srt"
fi
if [[ -z "$OUTPUT" ]]; then
    OUTPUT="${STORY_DIR}/../output/final.mp4"
fi

# ── 文件检查 ───────────────────────────────────────────────

# 检查是否有 composition（HyperFrames 模式）或素材（直出模式）
HAS_COMPOSITION=false
HAS_MATERIALS=false
if [[ -f "$COMPOSITION" ]]; then
    HAS_COMPOSITION=true
fi
MAT_COUNT=$(set +o pipefail; ls "${STORY_DIR}/materials/"*.mp4 2>/dev/null | wc -l | tr -d ' ')
if [[ "$MAT_COUNT" -gt 0 ]]; then
    HAS_MATERIALS=true
fi

if [[ "$HAS_COMPOSITION" == "false" && "$HAS_MATERIALS" == "false" ]]; then
    echo "错误：既没有 composition.mp4（HyperFrames 渲染产物），也没有素材视频"
    echo "请先用 HyperFrames 渲染或用素材生成拼接视频"
    exit 1
fi

# ── 绝对路径 ───────────────────────────────────────────────

STORY_DIR="$(cd "$STORY_DIR" 2>/dev/null && pwd)" || STORY_DIR="$(pwd)/$STORY_DIR"
COMPOSITION="$(cd "$(dirname "$COMPOSITION")" 2>/dev/null && pwd)/$(basename "$COMPOSITION")" || COMPOSITION="$(pwd)/$COMPOSITION"
NARRATION="$(cd "$(dirname "$NARRATION")" 2>/dev/null && pwd)/$(basename "$NARRATION")" || NARRATION="$(pwd)/$NARRATION"
if [[ -n "$BGM" ]]; then
    BGM="$(cd "$(dirname "$BGM")" 2>/dev/null && pwd)/$(basename "$BGM")" || BGM=""
fi
CAPTIONS="$(cd "$(dirname "$CAPTIONS")" 2>/dev/null && pwd)/$(basename "$CAPTIONS")" || CAPTIONS="$(pwd)/$CAPTIONS"
OUTPUT="$(cd "$(dirname "$OUTPUT")" 2>/dev/null && pwd)/$(basename "$OUTPUT")" || OUTPUT="$(pwd)/$OUTPUT"

# ── 生成 ASS 字幕（如果需要） ──────────────────────────────

ASS_FILE="${STORY_DIR}/captions.ass"
if [[ ! -f "$ASS_FILE" && -f "$CAPTIONS" && "$CAPTIONS" != *.ass ]]; then
    echo "--- 生成 ASS 字幕 ---"
    python3 -c "
import re, sys
srt = open('$CAPTIONS', encoding='utf-8').read()
lines = srt.strip().split('\n\n')
ass = '''[Script Info]
Title: Auto-generated
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default, PingFang SC, 36, &H00FFFFFF, &H000000FF, &H00000000, &H00000000, 0, 0, 0, 0, 100, 100, 0, 0, 3, 2, 1, 2, 30, 30, 150, 1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
'''
for line in lines:
    parts = line.strip().split('\n')
    if len(parts) >= 3:
        time_line = parts[1]
        text = ' '.join(parts[2:])
        # Convert SRT time to ASS time
        m = re.match(r'(\d{2}):(\d{2}):(\d{2}),(\d{3})\s*-->\s*(\d{2}):(\d{2}):(\d{2}),(\d{3})', time_line)
        if m:
            h = m.group(1)
            mi = m.group(2)
            s = m.group(3)
            ms = m.group(4)
            eh = m.group(5)
            emi = m.group(6)
            es = m.group(7)
            ems = m.group(8)
            s_start = f'{h}:{mi}:{s}.{ms}'
            s_end = f'{eh}:{emi}:{es}.{ems}'
            ass += f'Dialogue: 0,{s_start},{s_end},Default,,0,0,0,,{text}\n'
with open('$ASS_FILE', 'w', encoding='utf-8') as f:
    f.write(ass)
print(f'ASS 字幕已生成: $ASS_FILE')
"
fi

mkdir -p "$(dirname "$OUTPUT")"

# ── 逐字卡拉OK字幕（P1，可一键回退） ───────────────────────
# on 时：narration -> DTW 时间轴 -> captions.kara.ass；任何一步不合规/不达标 → 回退整句 SRT->ASS
KARA_DTW=""
KARA_ASS=""
KARAOKE_READY=false
SUBTITLE_MODE="整句 SRT->ASS"
if [[ "$KARAOKE" == "auto" ]]; then
    KARAOKE=$(python3 -c "import json,sys
try:
    print('on' if (json.load(open(sys.argv[1],encoding='utf-8')) or {}).get('enabled') else 'off')
except Exception:
    print('off')" "$KARAOKE_CONFIG")
fi
if [[ "$KARAOKE" == "on" ]]; then
    KARA_DTW="${STORY_DIR}/captions.dtw.json"
    KARA_ASS="${STORY_DIR}/captions.kara.ass"
    if [[ ! -f "$KARA_DTW" && -f "$NARRATION" ]]; then
        echo "--- 生成逐字 DTW 时间轴（whisper.cpp token 级） ---"
        set +e
        python3 "${PIPELINE_ROOT}/scripts/whisper_dtw.py" --audio "$NARRATION" --out "$KARA_DTW" --config "$KARAOKE_CONFIG"
        RC=$?
        set -e
        if [[ $RC -ne 0 ]]; then
            echo "警告：DTW 时间轴生成失败（exit $RC）→ 回退整句 SRT->ASS"
            KARA_DTW=""
        fi
    fi
    if [[ -n "$KARA_DTW" && -f "$KARA_DTW" ]]; then
        echo "--- 生成逐字卡拉OK ASS ---"
        set +e
        python3 "${PIPELINE_ROOT}/scripts/build_karaoke_ass.py" --srt "$CAPTIONS" --dtw "$KARA_DTW" --out "$KARA_ASS" --config "$KARAOKE_CONFIG"
        RC=$?
        set -e
        if [[ $RC -eq 0 && -f "$KARA_ASS" ]]; then
            KARAOKE_READY=true
            SUBTITLE_MODE="逐字卡拉OK(\\kf)"
        else
            echo "警告：逐字卡拉OK ASS 未生成（exit $RC）→ 回退整句 SRT->ASS"
        fi
    fi
fi

# ── 模式检测 ───────────────────────────────────────────────

if [[ "$HAS_COMPOSITION" == "true" ]]; then
    MODE="hyperframes"
    INPUT_VIDEO="$COMPOSITION"
else
    MODE="materials"
    INPUT_VIDEO=""
fi

echo "=== FFmpeg 终合成 (模式: $MODE) ==="
if [[ -n "$INPUT_VIDEO" ]]; then
    echo "  视频:   $INPUT_VIDEO"
else
    echo "  视频:   素材拼接 (${MAT_COUNT} 个)"
fi
echo "  配音:   $NARRATION"
echo "  BGM:    ${BGM:-（无）}"
echo "  字幕:   $CAPTIONS"
echo "  字幕模式: $SUBTITLE_MODE"
echo "  输出:   $OUTPUT"
echo "  尺寸:   ${VIDEO_WIDTH}x${VIDEO_HEIGHT}"
echo "  帧率:   ${FPS}fps"
if [[ "$HF_ENCODER" == "libx264" ]]; then
    echo "  编码:   libx264 (CRF ${CRF})"
else
    echo "  编码:   h264_videotoolbox (硬件, ${HF_VIDEO_BITRATE}, 直出交付规格)"
fi
echo ""

# ── 素材拼接（直出模式） ───────────────────────────────────

if [[ "$MODE" == "materials" ]]; then
    echo "--- 拼接素材视频 ---"
    # 创建 concat list
    CONCAT_LIST="${STORY_DIR}/concat_list.txt"
    > "$CONCAT_LIST"
    NORM_DIR="${STORY_DIR}/_normalized"
    mkdir -p "$NORM_DIR"
    IDX=0
    for mat in "${STORY_DIR}"/materials/*.mp4; do
        NORM="${NORM_DIR}/norm_${IDX}.mp4"
        echo "规范化 $(basename "$mat")..."
        /opt/homebrew/opt/ffmpeg-full/bin/ffmpeg -y -i "$mat" -vf "scale=${VIDEO_WIDTH}:${VIDEO_HEIGHT}:force_original_aspect_ratio=decrease,pad=${VIDEO_WIDTH}:${VIDEO_HEIGHT}:(ow-iw)/2:(oh-ih)/2:black,setsar=1,fps=${FPS}" -c:v libx264 -preset medium -crf 24 -pix_fmt yuv420p "$NORM" 2>/dev/null
        echo "file '$NORM'" >> "$CONCAT_LIST"
        IDX=$((IDX + 1))
    done
    # 拼接
    /opt/homebrew/opt/ffmpeg-full/bin/ffmpeg -y -f concat -safe 0 -i "$CONCAT_LIST" -c:v libx264 -preset medium -crf 22 -pix_fmt yuv420p -r "$FPS" -an "${STORY_DIR}/_concat_temp.mp4" 2>/dev/null
    INPUT_VIDEO="${STORY_DIR}/_concat_temp.mp4"
    DURATION=$(/opt/homebrew/opt/ffmpeg-full/bin/ffprobe -v error -show_entries format=duration -of csv=p=0 "$INPUT_VIDEO" 2>/dev/null | tr -d '\r')
    echo "拼接完成，时长 ${DURATION}s"
else
    DURATION=$(/opt/homebrew/opt/ffmpeg-full/bin/ffprobe -v error -show_entries format=duration -of csv=p=0 "$INPUT_VIDEO" 2>/dev/null | tr -d '\r')
    echo "视频时长: ${DURATION}s"
fi

# ── 获取配音时长 ───────────────────────────────────────────

NARR_DURATION=$(/opt/homebrew/opt/ffmpeg-full/bin/ffprobe -v error -show_entries format=duration -of csv=p=0 "$NARRATION" 2>/dev/null | tr -d '\r')
echo "配音时长: ${NARR_DURATION}s"

# ── 构建滤镜图 ─────────────────────────────────────────────

# 构建输入参数
INPUTS=("-i" "$INPUT_VIDEO")
if [[ -n "$NARRATION" ]]; then
    INPUTS+=("-i" "$NARRATION")
fi
if [[ -n "$BGM" ]]; then
    INPUTS+=("-i" "$BGM")
fi
INPUTS+=("-i" "$CAPTIONS")

NUM_INPUTS=${#INPUTS[@]}
# 实际输入数 = 1 (视频) + (配音?1:0) + (BGM?1:0) + 1 (字幕) = 2..4

# ── 构建 filter_complex ────────────────────────────────────

FILTER_PARTS=()

# [0:v] 视频缩放 + 字幕叠加（两阶段避免分号冲突）
SIMPLE_ASS="${STORY_DIR}/sub.ass"
ASS_FILE="${STORY_DIR}/captions.ass"
if [[ "$KARAOKE_READY" == "true" ]]; then
    # 逐字卡拉OK：sub.ass 指向逐字 ASS（不动 captions.ass 整句链路，随时可切回）
    cp -f "$KARA_ASS" "$SIMPLE_ASS"
elif [[ -f "$ASS_FILE" && ! -f "$SIMPLE_ASS" ]]; then
    cp "$ASS_FILE" "$SIMPLE_ASS"
fi

if [[ -f "$SIMPLE_ASS" ]]; then
    ln -sf "$SIMPLE_ASS" ./sub.ass
    FILTER_PARTS+=("[0:v]scale=${VIDEO_WIDTH}:${VIDEO_HEIGHT}:force_original_aspect_ratio=decrease,pad=${VIDEO_WIDTH}:${VIDEO_HEIGHT}:(ow-iw)/2:(oh-ih)/2:black,drawtext=text=\"抖音号 jerrychen2001\":x=w-tw-20:y=h-th-20:fontsize=24:fontcolor=white@0.6:borderw=1:bordercolor=black@0.8,ass=./sub.ass,format=yuv420p[vout]")
else
    ln -sf "$CAPTIONS" ./sub.srt
    FILTER_PARTS+=("[0:v]scale=${VIDEO_WIDTH}:${VIDEO_HEIGHT}:force_original_aspect_ratio=decrease,pad=${VIDEO_WIDTH}:${VIDEO_HEIGHT}:(ow-iw)/2:(oh-ih)/2:black,drawtext=text=\"抖音号 jerrychen2001\":x=w-tw-20:y=h-th-20:fontsize=24:fontcolor=white@0.6:borderw=1:bordercolor=black@0.8,ass=./sub.srt:force_style='FontSize=36,FontName=PingFang SC,Alignment=2,MarginV=150,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,BorderStyle=3,Outline=2,Shadow=1',format=yuv420p[vout]")
fi

# [1:a] 配音处理（如果有）
if [[ -n "$NARRATION" && -n "$NARR_DURATION" ]]; then
    FADE_END=$(echo "$NARR_DURATION" | awk '{printf "%.1f", $1 - 2}')
    AUDIO_FILTER="[1:a]loudnorm=I=-16:TP=-1.5:LRA=7,"
    AUDIO_FILTER+="afade=t=out:st=${FADE_END}:d=2[a1]"
    FILTER_PARTS+=("$AUDIO_FILTER")
else
    FILTER_PARTS+=("[0:a]anull[a1]")
fi

# [2:a] BGM 处理（如果有）
if [[ -n "$BGM" ]]; then
    BGM_FADE_OUT=$(echo "$DURATION" | awk '{printf "%.1f", $1 - 3}')
    BG_FILTER="[2:a]volume=0.12,"
    BG_FILTER+="afade=t=in:st=0:d=3,"
    BG_FILTER+="afade=t=out:st=${BGM_FADE_OUT}:d=3,"
    BG_FILTER+="loudnorm=I=-23:TP=-1.5:LRA=9[bgm]"
    FILTER_PARTS+=("$BG_FILTER")
fi

# 取最短时长裁剪（配音或视频，以短的为准）
if [[ -n "$NARR_DURATION" ]]; then
    TRIM_DURATION=$(echo "$DURATION $NARR_DURATION" | awk '{print ($1 < $2) ? $1 : $2}')
else
    TRIM_DURATION="$DURATION"
fi
if [[ -n "$BGM" && -n "$NARRATION" ]]; then
    FILTER_PARTS+=("[a1][bgm]amix=inputs=2:duration=first:dropout_transition=2[aout]")
elif [[ -n "$NARRATION" ]]; then
    FILTER_PARTS+=("[a1]anull[aout]")
else
    FILTER_PARTS+=("[0:a]anull[aout]")
fi

FILTER_COMPLEX=$(IFS=';'; echo "${FILTER_PARTS[*]}")

# ── 构建完整命令 ───────────────────────────────────────────

CMD=(/opt/homebrew/opt/ffmpeg-full/bin/ffmpeg)
CMD+=(-y)
CMD+=("${INPUTS[@]}")
CMD+=(-filter_complex "$FILTER_COMPLEX")
CMD+=(-map "[vout]" -map "[aout]")
if [[ "$HF_ENCODER" == "libx264" ]]; then
    # 兼容回退：软件编码 + CRF 质量模式
    CMD+=(-c:v libx264)
    CMD+=(-preset "$HF_PRESET")
    CMD+=(-crf "$CRF")
else
    # 硬件编码：一次重编码直出交付规格，避免后续二次转码
    CMD+=(-c:v h264_videotoolbox)
    CMD+=(-b:v "$HF_VIDEO_BITRATE")
    CMD+=(-maxrate "$HF_MAXRATE")
    CMD+=(-bufsize "$HF_BUFSIZE")
    CMD+=(-allow_sw 1)
    CMD+=(-prio_speed 1)
fi
CMD+=(-pix_fmt yuv420p)
# 交付档位取自单一真源（config/param_contract.json → encoder_chain.profile/level）：
# 不再出现硬编码 -level 4.1；真源不可读时由 _chain_get 回落到与真源同值的 4.2。
CMD+=(-profile:v "$(printf '%s' "$HF_PROFILE" | tr '[:upper:]' '[:lower:]')")
CMD+=(-level "$HF_LEVEL")
CMD+=(-c:a aac -b:a 128k -ar 44100 -ac 2)
CMD+=(-movflags +faststart)
CMD+=(-t "$TRIM_DURATION")
CMD+=("$OUTPUT")

echo "执行合成命令..."
echo ""
"${CMD[@]}"

echo ""
echo "=== 合成完成 ==="
SIZE_MB=$(du -mh "$OUTPUT" 2>/dev/null | cut -f1 || echo "?")
echo "输出文件: $OUTPUT (${SIZE_MB})"
echo "尺寸: ${VIDEO_WIDTH}x${VIDEO_HEIGHT} @ ${FPS}fps"
if [[ "$HF_ENCODER" != "libx264" ]]; then
    echo "提示: 已直出抖音交付规格；post_process.py 检测达标后将跳过重编码（--force-reencode 可强制）"
fi
