---
AIGC:
    Label: "1"
    ContentProducer: 001191440300708461136T1XGW3
    ProduceID: b82594f1be8e85c02fc42784acc7d5b8_4ee0d069c19011f1884b525400cd780f
    ReservedCode1: ftjaikJbuBHOpgPeezHUvOt6sgxeweQhyP1GCni8nnBc0mU6114BM+1JR/GNf+VJcJ7b57ugQ8Bfin8hRIB3AD3DjI75TRazLB0yqYueU2BzLeFNLpaB6iJUWZwNK8ijqmA5tWSQV9zAzpSgDqNoowQJJN3gIotCYpSPQvM3VCn2I0O/k0El/5Jq/Ro=
    ContentPropagator: 001191440300708461136T1XGW3
    PropagateID: b82594f1be8e85c02fc42784acc7d5b8_4ee0d069c19011f1884b525400cd780f
    ReservedCode2: ftjaikJbuBHOpgPeezHUvOt6sgxeweQhyP1GCni8nnBc0mU6114BM+1JR/GNf+VJcJ7b57ugQ8Bfin8hRIB3AD3DjI75TRazLB0yqYueU2BzLeFNLpaB6iJUWZwNK8ijqmA5tWSQV9zAzpSgDqNoowQJJN3gIotCYpSPQvM3VCn2I0O/k0El/5Jq/Ro=
---







# 流水线操作手册

## 快速开始

### 前置条件

1. **Python 3.8+** — 已安装
2. **Node.js >= 22** — 已安装
3. **FFmpeg** — 已安装 (`brew install ffmpeg`)
4. **Qwen3-TTS 本地模型（默认配音引擎）** — 仓库 `~/Projects/qwen3-tts-apple-silicon/`，模型 `models/Qwen3-TTS-12Hz-1.7B-Base-8bit`，御姐参考音 `voices/yujie_*.wav`。本机 MLX 推理，**不调用任何云端 TTS、不需要 TTS API Key**
5. **Pexels API Key** — 免费注册 https://www.pexels.com/api/
6. **LLM API Key** — 任选其一：
   - `OPENAI_API_KEY` (OpenAI / 兼容 API)
   - `ANTHROPIC_API_KEY` (Claude)

>配音引擎已于 2026-09 起由 Edge TTS 晓晓切换为**本地 Qwen3-TTS 慵懒御姐音**。Edge TTS 相关脚本（`scripts/edge_tts.py`、`generate_qa_video.py:generate_edge_tts`）保留为历史遗留，默认不启用。权威口径见 `docs/产线规范.md` 第五章。

### 一键流水线

```bash
cd /Volumes/PSSD/抖音视频

# 1. 生成文案（演示模式，无需 API key）
python scripts/generate_script.py \
  --topic "2025年AI领域最值得关注的5个方向" \
  --style hook \
  --demo \
  --output story/001-ai-future/script.txt

# 2. 拆分镜头
python scripts/split_scenes.py \
  --input story/001-ai-future/script.txt \
  --output story/001-ai-future/scene_plan.json \
  --target-duration 45

# 3. 下载素材（需要 Pexels API Key）
export PEXELS_API_KEY="your_api_key_here"
python scripts/download_materials.py \
  --api-key "$PEXELS_API_KEY" \
  --query "artificial intelligence technology" \
  --output story/001-ai-future/materials/ \
  --count 5

# 4. 生成配音（Qwen3-TTS 慵懒御姐音，本地 MLX，无需 API key）
~/Projects/qwen3-tts-apple-silicon/.venv/bin/python \
  ~/Projects/qwen3-tts-apple-silicon/batch_generate.py \
  --file story/001-ai-future/script.txt \
  --ref ~/Projects/qwen3-tts-apple-silicon/voices/yujie_thoughtful.wav \
  --ref-text "这个事情其实挺有意思的，让我慢慢跟你说。" \
  --output narration
# 输出：~/Projects/qwen3-tts-apple-silicon/outputs/批量配音/narration/*.wav
# 需要逐句 G 版停顿重排 + 时间轴回填的完整做法见下方「Step 4」

# 5. 生成字幕
#    先把逐句 wav 拼成单条旁白（batch_generate 按行输出多个文件）
for f in ~/Projects/qwen3-tts-apple-silicon/outputs/批量配音/narration/*.wav; do
  echo "file '$f'"
done > /tmp/narr_concat.txt
FFMPEG="$(python3 scripts/platform_env.py tool ffmpeg || command -v ffmpeg)"
"$FFMPEG" -y -f concat -safe 0 -i "$TMPDIR/narr_concat.txt" \
  -ar 24000 -ac 1 -c:a pcm_s16le story/001-ai-future/narration.wav

export KMP_DUPLICATE_LIB_OK=TRUE
whisper story/001-ai-future/narration.wav \
  --model small --language zh --output_format json --output_dir story/001-ai-future/

python scripts/json_to_srt.py \
  story/001-ai-future/narration.json \
  story/001-ai-future/captions.srt --group-size 1

# 6. 准备 BGM（复制一个示例 bgm 或使用自由音乐）
# cp path/to/bgm.mp3 story/001-ai-future/bgm.mp3

# 7. 用 HyperFrames 构建视频包装
# （详见下方「手动模式」部分）

# 8. FFmpeg 终合成
export STORY_DIR=story/001-ai-future
./scripts/render.sh
```

---

## 两种工作模式

### 模式 A: 全自动（推荐初期）

只用到脚本 + FFmpeg，不经过 HyperFrames：

```
文案 → 配音 → 字幕 → FFmpeg 合成 → 成片
```

适合快速验证，质量中等。

### 模式 B: 完整流水线（推荐生产）

```
文案 → 镜头拆分 → 素材下载 → 配音 → 字幕 → HyperFrames 包装 → FFmpeg 终合成 → 成片
```

获得最佳视觉效果。

---

## 模式 B 详细步骤

### Step 1: 生成文案

```bash
# 演示模式（无需 API）
python scripts/generate_script.py --topic "量子计算入门" --style hook --demo -o story/002/script.txt

# 真实 LLM 模式
export OPENAI_API_KEY="sk-xxx"
python scripts/generate_script.py --topic "量子计算入门" --style professional -o story/002/script.txt
```

支持的 `--style`：
- `hook` — 强钩子爆款风（默认）
- `professional` — 专业科普风
- `story` — 故事叙述风

### Step 2: 拆分镜头

```bash
python scripts/split_scenes.py -i story/002/script.txt -o story/002/scene_plan.json -d 45
```

- `--mode llm`（默认）：调用 LLM 智能拆分，需要 `OPENAI_API_KEY`
- `--mode heuristic`：启发式规则拆分，无需 API

### Step 3: 下载素材

```bash
python scripts/download_materials.py \
  --api-key "$PEXELS_API_KEY" \
  --query "quantum computing" \
  --output story/002/materials/ \
  --count 5 \
  --orientation portrait
```

### Step 4: 生成配音（Qwen3-TTS 慵懒御姐音，本地 MLX）

> 2026-09 起的默认引擎。Edge TTS 晓晓已弃用，相关脚本保留为历史遗留兜底，默认不启用。

#### 引擎与音色

| 项 | 值 |
|---|---|
| 引擎 | 本地 Qwen3-TTS（`Qwen3-TTS-12Hz-1.7B-Base-8bit`，mlx_audio） |
| 仓库 | `~/Projects/qwen3-tts-apple-silicon/`（用其 `.venv/bin/python` 跑） |
| 单人线音色 | **慵懒御姐音**，基准参考音 `voices/yujie_thoughtful.wav` |
| 情绪参考音 | 6 个：`yujie_thoughtful / excited / surprised / calm / playful / serious.wav`，由 `match_emotion()` 按文案关键词自动匹配 |
| 双人线 | 两个女生时走 `scripts/gen_guimi_dub.py`（林悦=御姐 / 苏苏=少女音），**不改动** |
| 云端 | **不启用**。链路失败应报错停下来修，不得自动切 Edge TTS |

#### 选线判据（机械执行，结果写入成片 `tts_line` 字段）

1. 抽对白句集合 D（`名字：台词` / 成对引号）
2. 数说话人数 N
3. 判定：`N≥2 且交替出现` → 双人线；`N≥2 但对白占比 <10%` → 单人线；`N≤1` → 单人线；判不准 → 默认单人线并标注 `solo-yujie (待确认)`
4. 出现男声角色或对话人数 ≥3 → 停下回报用户，不得套用双人流程

#### 单人线 G 版参数（默认）

| 环节 | 参数 |
|---|---|
| 静音修剪 | `-52dB / 0.30s`：仅句内长于 0.30s 的静音截到 0.30s；≤0.30s 短停顿保留 |
| 句首前导 | 0.12s（句尾 0.08s） |
| 句间停顿 | 逗号 0.25s / 句末 0.75s / 段落 1.20s |
| 语速/变调 | speed=1.0，不变调 |
| 输出 | 24000Hz / mono PCM_16 |
| **硬指标** | 句内静音 ≥0.40s 的档位必须为 **0** |

F 版（合并单元·动态停顿）仅在配音总时长超目标时长时改选，可省约 4.6s，但**需同步重算卡片时间轴**。完整口径见 `docs/产线规范.md` 5.3。

#### 标准做法（逐句 + 时间轴回填）

生产中不手敲单句，而是复制一个现成项目目录改 `script.json`：

```bash
# 以 paperclip 为模板（赤焰热力主题 + 御姐音，最近一次跑通的范例）
cp -r story/paperclip story/<你的项目>
cd story/<你的项目>
# 两个 build 脚本的 STORY 路径和项目名都是硬编码的，先改掉
sed -i '' 's#story/paperclip#story/<你的项目>#' build_audio.py build_html.py
sed -i '' 's#"name": "paperclip"#"name": "<你的项目>"#' build_html.py
# 编辑 script.json：改 title / scenes[].card / scenes[].lines[].text / facts / epilogue

python3 build_audio.py    # 逐句 Qwen3 御姐配音 + G 版重排 + 拼接 + 时间轴回填
```

`build_audio.py` 会产出 `line_NN.wav` / `audio_combined.wav` / `narration.wav`，并把每句起止时间回填进 `script.json` 的 `lines[]` 和 `scenes[]._start/_end`——这一步是后面 `build_html.py` 卡片时间轴的唯一依据。

#### 单段配音（不走 G 版重排）

```bash
~/Projects/qwen3-tts-apple-silicon/.venv/bin/python \
  ~/Projects/qwen3-tts-apple-silicon/batch_generate.py \
  --file story/002/script.txt \
  --ref ~/Projects/qwen3-tts-apple-silicon/voices/yujie_thoughtful.wav \
  --ref-text "这个事情其实挺有意思的，让我慢慢跟你说。" \
  --output my_clips
# 输出：~/Projects/qwen3-tts-apple-silicon/outputs/批量配音/my_clips/*.wav
```

> `--ref` 必须配对的 `--ref-text` 要是该参考音的原文（见上表 6 情绪参考音原文），否则音色会漂。

#### 给 HyperFrames 项目直接灌配音

```bash
~/Projects/qwen3-tts-apple-silicon/.venv/bin/python \
  ~/Projects/qwen3-tts-apple-silicon/gen_video_vo.py \
  --project <hyperframes 项目目录> --script SCRIPT.md \
  --ref voices/yujie_calm.wav --speed 1.0
# 逐句写入 assets/voice/NN.wav 并回填 audio_meta.json（24kHz mono，已 trim 首尾静音）
```

### Step 5: 生成字幕

```bash
# Whisper 转录（需设置 OpenMP 兼容）；Qwen3 出口是 24k mono wav
export KMP_DUPLICATE_LIB_OK=TRUE
whisper story/002/narration.wav \
  --model small --language zh --output_format json --output_dir story/002/

# JSON → SRT
python scripts/json_to_srt.py \
  story/002/narration.json \
  story/002/captions.srt --group-size 1
```

#### 逐字卡拉OK字幕（v1.10.0 新增，默认开启，可一键切回）

```bash
# 1) 逐字时间轴（whisper.cpp DTW，t_dtw 单位 1/100s）
python3 scripts/whisper_dtw.py --audio story/002/narration.wav \
  --out story/002/captions.dtw.json

# 2) SRT 句界 × DTW 逐字 → \kf 逐字上色 ASS（不覆盖 captions.srt / captions.ass）
python3 scripts/build_karaoke_ass.py --srt story/002/captions.srt \
  --dtw story/002/captions.dtw.json --out story/002/captions.kara.ass

# 3) 渲染：默认 KARAOKE=auto（读 config/karaoke.json 的 enabled）
KARAOKE=on  ./scripts/render.sh      # 启用逐字卡拉OK
KARAOKE=off ./scripts/render.sh      # 一键切回整句 SRT→ASS（原链路，行为等价）
```

开关与三档回退（单次切回 / 长期 `enabled=false` / 失败自动回退）、单位一致性与试点证据见 `docs/产线规范.md`「字幕层（v1.10.0）」；决策与债务见 `docs/决策记录与技术债.md`。

### Step 6: HyperFrames 包装

#### 赤焰热力生产线（推荐，与 Step 4 模板法一脉相承）

沿用 Step 4 复制出来的项目目录，`build_html.py` 直接读 `script.json`（含已回填的时间轴）生成赤焰热力主题 `index.html`：

```bash
cd story/<你的项目>
python3 build_html.py
# 产出 index.html + hyperframes.json（1080x1920 / 30fps）
```

主题说明见 `templates/hot-ranking/design.md`：暗底 `#121214` + 热力红橙 `#FF5926`，12 档色阶派生自差异热力图通道系数。卡片 / 数据条 / 画中画全部由 `script.json` 的 `scenes[].card` 驱动，支持变量 `pipEnabled` / `pip` / `pipLabel`（画中画）、`aigcVariant` / `aigcEnabled`（AI 生成标识，默认关闭）。

#### 通用流程（其它模板）

```bash
# 在视频目录创建 HyperFrames 项目
cd /Volumes/PSSD/视频
npx hyperframes init ai-002 --non-interactive
cd ai-002

# 复制素材
cp /Volumes/PSSD/抖音视频/story/002/narration.wav .
cp /Volumes/PSSD/抖音视频/story/002/transcript.json .
cp -r /Volumes/PSSD/抖音视频/story/002/materials/ .

# 编辑 index.html — 使用 templates/ 中的组件
# 开场: compositions/intro.html
# 结尾: compositions/outro.html
# 主场景: index.html 中的视频 + 字幕层
```

### Step 7: 渲染与合成（storyctl 单入口 · 两段门禁）

> **S3 起本条已收口到 `scripts/storyctl.py`**（per-story 双脚本路线）。旧手动链
> （`hyperframes lint/inspect` + `scripts/render.sh`）自 S3 起不再是交付路径；它与根目录
> `generate_*_video.py` 按编排器边界声明「保持现状、不改动、不收编、不删除」，见下方附录。

```bash
cd /Volumes/PSSD/抖音视频

# 7a. 第1跳 · 出片（默认只跑段1 渲染前门禁，内联在「HTML 已产出 / 尚未渲染」节点）
python3 scripts/storyctl.py build <story>     # 调试跳段1：--no-gate [--no-gate-reason "…"]
#    链路：build_audio → build_html → [段1] → hyperframes render → post_process → append_epilogue
#    注：不传 --qc 时 build 不含段2；跑完 build 只说明「段1 绿」，不代表交付合格
#    内容校验默认前置（--check），error 集拦停、warn 集放行；调试跳：--no-check

# 7a'. 一条命令出片 + 两段门禁（MVP 起，显式 opt-in）
python3 scripts/storyctl.py build <story> --qc
#    = 上述 7a 链路跑完再自动接 7b；退出码语义不变（0/1/2）。默认不传 --qc 行为完全不变

# 7b. 第2跳 · 段2 门禁（渲染后；qc 会重跑段1 + 段2，不依赖 build，可单独执行）
python3 scripts/storyctl.py qc <story>

#     三个 opt-in 口，不传即不跑：
python3 scripts/storyctl.py qc <story> --baseline story/<story>/qc/baseline   # A0 同源门（推荐主路径：传目录）
python3 scripts/storyctl.py qc <story> --ref story/<story>/douyin_epilogue.mp4 # A2/A3 参照
python3 scripts/storyctl.py qc <story> --store-baseline                        # 存 A6b 基线
```

**两段齐绿需两跳**：`build` 只在渲染前内联段1（拦住「别把已知坏片渲染两分半」），成片落盘后
还需第 2 跳 `qc`（`qc` 会重跑段1 + 段2）。只跑 `build` 不等于交付合格。
**单命令口（MVP，2026-10-06）**：`build --qc` 把两跳串成一条命令（显式 `--qc` opt-in，默认行为不变），
gods-eye-view 端到端回放实测 `EXIT=0` / `blocked=false`；两跳语义与报告落盘位置完全一致。

**画质默认工作流（2026-10-07 起默认；真源见 `docs/产线规范.md`「画质默认层（v1.12.0）」）**：
- **渲染超采样默认启用**：`storyctl build <story>` 在**未设** `STORYCTL_RENDER_RESOLUTION` 时默认追加 `--resolution portrait-4k`（Chrome DPR=2，按 2160×3840 采样），仍由 `post_process` 收口回 1080×1920 / crf18 / 30fps。
- **一键回退对照**：`STORYCTL_RENDER_RESOLUTION=off`（或 `none` / `1x`）→ 不追加 `--resolution`，第 4/6 步命令行与默认化前逐字节一致；`=portrait` → 白名单 1× 档（A/B 对照）；其它值拒绝执行（exit 1）。
- **视觉提亮基线 V-BASE**：已固化进出厂模板 `story/compositor-mac/build_html.py`（`storyctl new` 新建 story 自动继承），共 9 项提亮参数；模板与脚本回退点均为 `.bak-20261007`。

| 跳 | 命令 | 覆盖门禁 | 节点 |
|---|---|---|---|
| 第 1 跳 | `storyctl build <story>` | 段1（渲染前） | HTML 已产出 / 尚未渲染 |
| 第 2 跳 | `storyctl qc <story>` | 段1 重跑 + 段2（渲染后） | `douyin_epilogue.mp4` |

- 退出码：`0` 成功 / `1` 编排器侧故障（用法、输入、链路命令失败）/ `2` 成片检出问题
- 被测件：`story/<story>/douyin_epilogue.mp4`；报告：`qc/pre.json`（段1）、`qc/report.json`（段2）
- 产物命名收口：`story/<story>/douyin.mp4` + `douyin_epilogue.mp4`

**参数唯一真源**：`config/param_contract.json` → `delivery_profile`，读取器 `scripts/encode_profile.py`
（`--json` / `--ffmpeg-args` / `--get <key>` / `--check <mp4>` / `--selftest`）。
`post_process.py` 与 `render.sh` 均从该真源取 profile / level：`render.sh` 走「`jq` →
`python3 scripts/encode_profile.py --get` → 内置默认 4.2」三级回落，全仓不存在第二处硬编码
4.1 / 4.2。**交付合格判据的唯一实现**是 `encode_profile.assert_delivery_spec()`，
`post_process.is_delivery_ready()` 只做转调（不再自行维护判据，取不到真源时 fail-closed）。

**编码口径（契约 `contract_version=1.3.0`，2026-10-06 起）**：视频编码统一
`rate_control=capped-crf`（真源 `toolchain_pins.encoder_chain`）—— 质量档由 `-crf video_crf=18`
决定，`-maxrate 10M -bufsize 12M` 只作**瞬时上限**；`video_bitrate="8M"` 降级为
**ceiling reference**（`video_bitrate_role`），并以 `video_bitrate_target_locked=false` 声明
「不存在必须打到 8M 的锁死目标」。**任何链路（`post_process.py` / `append_epilogue.py` /
`render.sh` / `generate_*.py`）不得再以 `-b:v` 作为编码目标**；交付码率判据仍只取
`video_bitrate_max_accept=11M`。变更缘由（归一后体积膨胀 2.3–2.9×）与实证见
`proposals/s3_batch_backup/ab_fix_2026-10-06/`。

**断言开关与阈值（S3 口径）**：

| 断言 | 内容 | 开关 | 缺省行为 |
|---|---|---|---|
| A0 | 同源门（build 前后 `index.html` sha256 必变：时长轴 + TTS 旁白轴） | `qc --baseline <qc/baseline 目录>` **（推荐）** | **opt-in，不传即不跑**；**推荐主路径是传目录** `story/<story>/qc/baseline/`（逐帧对比，A0 语义完整） |
| A2 | 场景标签差集 | `qc --ref <同 story 已修复成片>` | **opt-in，无 ref 不跑** |
| A3 | 元素位置 / 形变（逐场景前景块 vs 参照，偏移 > 40px 或尺度比越界即 warn） | 同 A2 的 `--ref` | **opt-in，无 ref 不跑** |
| A5 | 声明时长比对：**双 target** —— `douyin.mp4`（锚点 `script.json total_duration`）与 `douyin_epilogue.mp4`（锚点 `total_duration + gap_before + dur(epilogue.wav) + tail_silence`） | 恒开（有 `total_duration` 即比对） | 分辨率 / 帧率 / 音画错位 = error；时长偏差 > ±2.00s = warn；口径不可得 = info 跳过并注明原因。**MVP 起两个 target 各自出结论**（此前只校主片、片尾件被跳过） |
| A6b | 码率旗标（MiB/s > **5×** 参照） | 恒开；`qc --store-baseline` 存基线 | 阈值 S3 由 3.0→**5.0**，**恒 warn-only、不进阻断**；参照四级取值：CLI > per-story `qc/baseline/bitrate.json` > **真源冻结 `audit_refs.a6b_ref_mib_per_s=0.115`** > 旧口径（旧口径命中时显式 WARN） |
| A7 | 交付规格（`sample_rate` / `channels` / `profile` / `level` / `pix_fmt` = error 级；`gop` = warn 级） | 恒开，含片尾件 `douyin_epilogue.mp4` | **已启用**（2026-10-06 上线）：判据唯一取自 `encode_profile.assert_delivery_spec()`；豁免登记见下方「A7 豁免登记」 |

> **A0 基线说明（v2.1 勘误补）**：`--baseline` **推荐传目录** `story/<story>/qc/baseline/`（主路径）；
> `--baseline` 传 mp4 属**调试口** —— 该路径下 mp4 自带不了溯源，需**直调** `scripts/frame_audit.py`
> 并**显式加 `--same-source`** 才不被拒；`storyctl qc` 对 `--baseline` **只透传、不代传** `--same-source`。

> **A7 豁免登记（`delivery_spec_waiver`）**：落位各 story `script.json` **顶层键**，与 `design_registry`
> 同文件、同读取路径（`frame_audit --script` 已强制）。条目 **6 字段缺一即无效**：`target`（被测件
> basename）/ `target_sha256`（64 位小写 hex，软失效锚点）/ `fields`（∈ `sample_rate`、`channels`、
> `profile`、`level`、`pix_fmt`、`gop`）/ `reason` / `approved_by` / `expires_at`（`YYYY-MM-DD`，
> 建议 +30 天、上限 +90 天）。放行需四者同时成立：target 匹配 ∧ 字段在 fields 内 ∧
> 当前件 sha256 == `target_sha256` ∧ 未过期；**同一 target 多条登记判无效**。fail-closed 口径照搬
> `design_ai_gate._registry_invalid_entries`：任一条目非法 → 整次运行 `exit 1` 并列出无效条目。
> 被抑制的 error **不删**，改写 `severity=info` 并附 `waived` / `reason` / `approved_by` / `expires_at`
> 留痕。**软失效**（sha 不符 = 成片已重建）报 INFO；**硬失效**（超期）不放行。
> 9 个存量项目（见下表）一律走**归一**，不留任何实际豁免条目。

**A7 上线与存量归一状态（2026-10-06，11/11 项目；编码口径 contract 1.3.0 / capped-CRF 已全量落地）**：

归一字段（9 个存量项目）：`level` 50→**42**、`sample_rate` 48000→**44100**、
`gop` 250/200→**60**（`profile=High` / `channels=2` / `pix_fmt=yuv420p` 前后一致）；
逐项 `assert_delivery_spec` 全绿（`a7_ok=true`）、qc 两段全绿（rc=0、`blocked=false`、A7 零 error）。

| # | 项目 | 角色 | capped-CRF 后体积 MiB（`douyin` / `epilogue`） | 体积回落比（vs A7 归一态） |
|---|---|---|---|---|
| 1 | ace-step-ui | 试点（口径验证） | 9.93 / 10.64 | 2.60× / 2.54× |
| 2 | gods-eye-view | 试点（口径验证） | 11.59 / 12.20 | 2.27× / 2.25× |
| 3 | aicomicbuilder | 存量 | 14.11 / 14.76 | 2.38× / 2.35× |
| 4 | autoclip | 存量 | 11.58 / 12.32 | 2.46× / 2.42× |
| 5 | immich | 存量 | 12.05 / 12.64 | 2.75× / 2.70× |
| 6 | compositor-mac | 存量 | 9.79 / 10.47 | 2.63× / 2.57× |
| 7 | insta360-nyc | 存量 | 9.74 / 10.38 | 2.29× / 2.26× |
| 8 | needle | 存量 | 8.60 / 9.19 | 2.50× / 2.46× |
| 9 | news-shake-ad | 存量 | 9.37 / 10.01 | 2.51× / 2.46× |
| 10 | paperclip | 存量 | 9.46 / 10.15 | 2.64× / 2.58× |
| 11 | turbo-fieldfare | 存量 | 12.14 / 12.83 | 2.44× / 2.40× |

- 存量收尾方式：复用各自 `renders/` 直编，`post_process --no-epilogue` + `append_epilogue --force`
  + 逐项 `qc`（**不重跑 `build`**，故时长/帧数零变化）。
- 备份（回滚点）：A7 归一态 `proposals/s3_batch_backup/a7_batch/`（第一组）、
  `a7_batch_round2/`（第二组 + `preseed/` 9 件 `script.json` 预埋前快照）；
  capped-CRF 全量修复前成片 `proposals/s3_batch_backup/ab_fix_full_2026-10-06/`
  （18 件 `.before` + `sha256_before.tsv` / `sha256_after_full.tsv`）。

> A6b 存基线说明：`--store-baseline` 以段2 被测件 `douyin_epilogue.mp4` 的 size / 帧快照为锚点；
> 需以原片 `douyin.mp4` 为锚点时直调 `scripts/frame_audit.py --store-baseline`（S3 收口修正前
> `qc` 无此口，只能绕道直调）。
> **A6b 真源冻结参照（契约 1.3.0）**：全局参照原先隐式取 `story/ace-step-ui/douyin_epilogue.mp4`，
> 该件自身随归一由 0.115 漂至 0.287 MiB/s（2.5×），使 5× 阈值失效；现改为真源冻结值
> `audit_refs.a6b_ref_mib_per_s=0.115`（含来源 / 冻结日 / 盘上依据），`frame_audit` 按
> 「CLI > per-story 基线 > 冻结值 > 旧口径」四级取参照。per-story 基线 `qc/baseline/bitrate.json`
> **schema 已定（方案 B，2026-10-06）**：`version` / `captured_at` / `entries[]`（`target`、`mib_per_s`、
> `size_bytes`、`duration_s`、`captured_from`、`captured_sha256`）；**只在显式 `qc --store-baseline`
> 时写入、绝不自动刷新**（缺条目回落真源冻结 0.115）。

**附：非 storyctl 路线（S3 方案C：结构不动、不收编）**

```bash
# 旧手动链（仅存量排查参考，不再作为交付路径）
npx hyperframes lint && npx hyperframes inspect
python3 scripts/design_ai_gate.py . --dir
npx hyperframes render --fps 30 --quality high --output composition.mp4
cd /Volumes/PSSD/抖音视频 && STORY_DIR=story/002 ./scripts/render.sh   # Pexels 路线
```

---

## 模板系统

### 可用模板

| 模板 | 目录 | 风格 |
|------|------|------|
| **赤焰热力（热榜）** | `templates/hot-ranking/` | 暗底 + 热力红橙 + 可动数据进度条 + 顶部网络视频画中画叠加。**当前生产首选**，Step 4/6 的 `build_html.py` 用的就是它 |
| 科普 | `templates/science-popularization/` | 黑底 + 大字 + 粒子 |
| 科技新闻 | `templates/tech-news/` | 白底 + 卡片 + 动态数据 |
| 数据分析 | `templates/data-analysis/` | 暗色 + 图表 + 数字滚动 |

> 赤焰热力最配数据榜单 / 热度排行 / 指数涨跌 / 竞争排名；财经科普、情感、亲子类慎用（红色长时段易引发紧张联想）。完整适配度评估见 `templates/hot-ranking/design.md` 第三章。

> `hot-ranking` 依赖 `templates/_shared/`，渲染时项目根取 `templates/`：`hyperframes render -c hot-ranking/intro.html -o out.mp4`。其画中画素材取自模板内 `assets/`（变量 `pip` 留空即用内置示例；渲染根不同时脚本会自动回退到 `hot-ranking/assets/…`）。示例成片见 `output/samples/theme-heat-ranking-pip.mp4`。

### 使用模板

1. 复制模板目录到你的项目：
   ```bash
   cp -r templates/science-popularization story/002/hyperframes/
   cd story/002/hyperframes/
   ```

2. 用 HyperFrames 变量替换内容：
   ```bash
   npx hyperframes render \
     --variables '{"title":"量子计算入门","accent":"#00d4ff"}' \
     --output composition.mp4
   ```

---

## API 密钥管理

创建 `config/api_keys.env`：

```bash
# LLM
OPENAI_API_KEY=sk-xxx
OPENAI_BASE_URL=https://api.openai.com/v1  # 可选，兼容 API
ANTHROPIC_API_KEY=sk-ant-xxx               # 可选

# 素材
PEXELS_API_KEY=xxx-xxx-xxx

# 视频规格
VIDEO_WIDTH=1080
VIDEO_HEIGHT=1920
FPS=30
CRF=20
```

使用时：
```bash
set -a
source config/api_keys.env
set +a
```

> 配音**不需要任何 API Key**——Qwen3-TTS 是本机 MLX 推理。这里只有 LLM（文案 / 镜头拆分）和 Pexels（素材下载）两处用得到 key。

---

## 故障排查

| 问题 | 解决方案 |
|------|----------|
| Qwen3-TTS 合成失败 | 不要切云端。检查 `~/Projects/qwen3-tts-apple-silicon/models/Qwen3-TTS-12Hz-1.7B-Base-8bit` 是否在；用该仓库 `.venv/bin/python` 跑；参考音 `voices/yujie_*.wav` 是否齐全（缺失会打印 `falling back to Edge TTS` 并返回 False，这是告警不是通过） |
| Qwen3 参考音音色漂移 | 换情绪参考音重试；逐段 F0 中位 > 1.3× 全曲中位时判定漂移，重合成或做 +1~+2 半音回拉 |
| 句内卡顿（"说一半就断"） | G 版硬指标：`silence_ge_040s` 必须为 0，`build_audio.py` 会逐句打印并汇总 |
| Edge TTS 相关报错 | 已弃用的历史链路（`scripts/edge_tts.py`）。默认不应被触发；若被触发说明 Qwen3 链路静默降级了，回去修 Qwen3 |
| Whisper OpenMP 警告 | 运行前 `export KMP_DUPLICATE_LIB_OK=TRUE` |
| Whisper 转录翻译了英文 | 确保用了 `--language zh` 而不是 `.en` 模型 |
| FFmpeg 字幕乱码 | 确保系统安装了中文字体（PingFang SC / Noto Sans CJK） |
| Pexels 下载失败 | 检查 API key，确保账户已激活 |
| HyperFrames 渲染黑屏 | 运行 `npx hyperframes lint` 检查 composition 配置 |
| 视频尺寸不对 | 确保 Pexels 下载的是 `orientation=portrait` 素材 |
| 片尾未追加 | 检查 `narration.wav` 是否在成片目录；`script.json` 中 `epilogue.enabled` 是否为 true |
| 片尾段渲染失败（node not found） | 确保 `node` / `hyperframes` 可被解析到（PATH，或 `export PIPELINE_HYPERFRAMES=/绝对/路径/hyperframes`），自检 `python3 scripts/doctor.py` |

---

## 标准片尾（默认追加）

从 2026-09-17 起，所有成片**默认**在结尾追加统一片尾：**关注引导 + 评论区互动**。

- 模板定义：`epilogue_template.json`
- 追加器：`append_epilogue.py`
- 接入点：`post_process.py` 第 3 步（默认执行，`--no-epilogue` 关闭）

### 片尾内容（固定文案）

| 项 | 内容 |
|---|---|
| 口播 / 字幕 | 关注 jerrychen2001，评论区聊聊你还想拆哪个项目。 |
| 卡片 · 主标 | 关注 jerrychen2001 |
| 卡片 · 强调 | 评论区聊聊 |
| 卡片 · 副标 | 你还想拆哪个项目？ |
| 配音 | G 版慵懒御姐音（thoughtful） |

### 节奏参数

| 参数 | 值 | 说明 |
|---|---|---|
| gap_before | 0.40s | 上一句结束 → 片尾口播开始 的过渡静音 |
| inner_cap | 0.30s | 句内 > -52dB 长静音截断上限 |
| lead_silence | 0.12s | 句首 / 句尾留白 |
| tail_silence | 0.50s | 片尾口播结束后停留（卡片保持到结束） |
| bgm_volume | 0.18 | BGM 铺底音量（与原片一致） |

### 单独使用

```bash
# 给已完成的成片补片尾（不覆盖原片，输出 douyin_epilogue.mp4）
python3 /Volumes/PSSD/抖音视频/append_epilogue.py \
  /Volumes/PSSD/抖音视频/output/<成片目录> --force
```

### 每片自定义

在成片目录的 `script.json` 中增加 `epilogue` 字段即可覆盖模板（字段与 `epilogue_template.json` 的 `epilogue` 完全一致），例如：

```json
{
  "epilogue": {
    "enabled": true,
    "text": "关注 jerrychen2001，评论区聊聊你还想拆哪个项目。"
  }
}
```

### 输出约定

- 原片 `douyin.mp4` **零改动**（视频流逐帧一致），新增文件 `douyin_epilogue.mp4`
- 片尾段严格复用原片卡片 / 字幕 / topbar / 进度条 / 水印样式与 BGM
- 片尾段时长 = gap_before + 口播时长 + tail_silence

*（内容由AI生成，仅供参考）*
## 生产加固规范（2026-09-28 增补）

> 来源：EigenFlux 同行实践（vidknot、E-commerce Short-Video Assistant、Ethan Brooks、钮仔），均为通用口径，已按本流水线环节对齐落点。
> 修改前备份：`/Volumes/PSSD/抖音视频/output/backup/PIPELINE_备份_20260928.md`（产线根绝对路径；同份副本另存 Marvis workspace `output/backup/`，两处 sha256 一致）

### A. 缓存键与错误码分层（落点：Step 1 / Step 4 / Step 5）

| 规范 | 做法 | 落点 |
|------|------|------|
| 缓存键绑产物哈希 | 缓存键 = 规范化后的处理器**产物哈希**（转写文本 + 行号 + 时间戳），不绑原始文件路径（路径变了内容没变，绑路径会全量失效） | TTS / Whisper 产物复用 |
| 错误码按层独立 | ASR / LLM / NETWORK / FETCH 各层独立错误码，禁止合并成一个通用码（合并后无法定位是哪层静默截断） | 全链路错误处理 |
| 陈旧缓存强制失效 | 检测到缓存陈旧必须**强制下一轮失效**，禁止"一次性重试"（重试会撞回同一份陈旧缓存） | 重跑逻辑 |
| 幂等写入 | 心跳 / 回执 / 进度落盘幂等，重复写入不重复计数 | 批量渲染循环 |

### B. 口播质检 SOP（落点：Step 5 字幕生成之后、Step 7 终合成之前）

1. **ASR 逐字对齐回读**：成片音轨重新转写，与 `script.json` 逐字比对，标记不一致位置。
2. **能量包络定位**：用能量包络定位卡壳、吞字、异常停顿；句内长静音阈值沿用片尾的 -52dB。
3. **句边界重剪**：只在标记处重剪该句，不做整段重录。
4. **成片回读一致率**：输出质检报告，人工返工从"整段重听"压缩到"只看标记处"。

### C. TTS take 选择与字幕对齐（落点：Step 4 / Step 5）

- 同一文案生成 **4 个 take**；Whisper 转写与脚本**不完全逐字匹配的 take 一律丢弃**（口播稿与字幕行是两套格式，不混用）。
- 动画 cue 按**词级时间**对齐；同时输出 JSON cue sheet + SRT/VTT。
- 母版响度统一 **-14 LUFS**。

### D. 参数契约与负控（落点：Step 2 分镜 / Step 7 验收）

- 参数契约加**可观测激活判据**：检测"声明了但从未被消费"的参数（静默失败）。
- 每轮迭代注入一个**必然失败的负控用例**，验证校验框架本身有效。
- 参数表签发方本身也作为被签对象登记；参数变更走数据事件通道，不做静默替换。

### E. 素材与封面图本地生成（可选，落点：Step 3 / Step 6）

- Apple Silicon 原生 FP16 的 Qwen-Image 2.1 运行时 + Gradio 本地部署（多参考图、OpenPose/DWPose、outpainting），可替代部分 Pexels 素材与封面图。
- 注意：模型权重商用受限，商用前核对许可。

*（内容由AI生成，仅供参考）*

### F. 降级与兜底动作独立记账（落点：Step 7 终合成验收 / post_process 质检）

> 来源：EigenFlux 同行实践（EigenFlux01「降级通道的假绿」）。均为通用口径，已按本流水线环节对齐落点。

| 规范 | 做法 | 落点 |
|------|------|------|
| 降级/兜底单独成流 | 降级与兜底动作不进主链路日志，独立 `fallback_event` 流，每行带三格：降级类型、签发方、签发时刻；**签发方必须落在被测链路之外** | 渲染 / 编码 / 字幕环节 |
| 由产物侧判降级 | 「有没有走降级」不由链路自述；判据 = 期望产物清单 − 实际落盘产物，**非空即记降级** | Step 7 验收 |
| 自报值降级为未观测 | 链路的自报路径、自报 as_of 不单独充当健康信号或路径判据 | 全链路 |
| 零值语义写死 | 空返回 / 查不到 / 拒发一律出 `UNKNOWN` 并单独计数，**不与「确认的无」合并**；拒发也须留回执 | 错误处理 |

### G. 验收信号独立性与产物指纹（落点：Step 7 终合成验收）

> 来源：EigenFlux 同行实践（巡灯：可靠性信号相关性）。

- 退出码、完成标记、索引更新**可能共享同一条失败路径**，不得当作互相独立的成功证据。
- 产物判定必须带**内容指纹**（内容哈希 + 大小 + mtime），用于区分本轮产物与上一轮残留。典型反例：编码器 exit 0，但写入与上一轮共享的 staging 目录，挂载退化时「产物存在」校验命中上一轮旧文件（旧指纹、偶发 0 字节）。
- 共用同一输入快照的两次校验只记 `unverified`，不得写 `independent`；独立性用**定向故障注入**证伪——单次只动一条支路：只故障写入路径 / 只制造一次缓存命中 / 只让上游改一次参数快照，再观察降级事件与主链路绿灯是否同时出现。

### H. 挂起项年龄与翻案率口径（落点：Step 5 后质检闸门 / 拒绝型闸门）

> 来源：EigenFlux 同行实践（AI-Film-Studio：发布侧默认拒绝闸门 + 误拒率）。

- 闸门只做**拒绝**不做确认；每条拒绝必须带**触发规则名**，否则调参只能靠猜。
- 挂起项绑定「起始时刻 + 重跑成本档」，输出**年龄分布分位 P50/P90/P99**（不只报条数）——「一撮老的」与「一片新的」处置动作完全不同。
- 阈值基数取**当轮新增挂起数**，存量另出桶；存量做分母会随积压老化把读数自动洗好，把真实积压抹掉。
- 翻案率分母只算**已人工复核的拒绝**；未复核挂起项单独出桶，不进分母，否则翻案率随积压量漂移。
- 适用环节：音画同步、字幕安全区等等待签（重跑昂贵）环节。

### I. 负对照用例退役与冻结金标准留痕（2026-10-05 吸纳 W036 第二、三项）

> 来源：W036《负对照集退役与注入-命中双计数》第二项（冻结金标准 / 拒绝留痕）+ 第三项（负对照集退役，含 append-only 轮次台账与退役补位）。
> **边界**：只吸纳第二、三项；第一项「注入-命中双计数」不落地（不引入 `injected_n` / `caught_n` 报数要求）；`scripts/negcontrol.py` 判定分支与退出码语义**不改**。

- **负对照用例退役**（S4/A4/A5）：单条负控**连续 3 轮命中且无翻案**即转 `retired`——留档不删除、移出活跃用例集、单列 `retired` 清单；streak 任一未命中即归零。达 N 轮的用例登记退役时刻 + 替代样本 ID。
- **退役必须补位**（S5）：每次退役同步补入同规则族替代样本，否则活跃用例单调衰减、命中率重新虚高。
- **轮次台账 append-only**（A3）：每轮负控运行**追加一行**至 `reports/negcontrol/ledger.jsonl`（`run_at` + `caseset_version` + `contract_version` + 逐用例 verdict）；仅有覆盖式 `last_run.json`（叠加手工 `.bak`）会导致 streak 被重置、退役结论不可复现，判「退役规则不可判定」；台账只增不改写。
- **冻结金标准换尺硬停**（S8/A8，与 G 节同源）：以冻结数据集摘要（`config/frozen_baseline.json`）为真源；**摘要变更即视为换尺 → 硬停 + 重新标定**，禁止沿用旧对照基线；素材 / 样本指纹（sha256）被替换 → 旧基线失效，先重跑 `verify-materials` 复核再沿用（呼应红线 5）。
- **未达期望是缺陷信号**：期望判红却判绿 = 检测器缺口，先修检测器或改用例口径，**禁止删用例、放宽期望或静音**。
- **拒绝留痕衔接**（S12）：沿用 H 节口径（只拒绝不确认、拒绝必带触发规则名、年龄 P50/P90/P99、阈值基数取当轮新增、翻案率分母只算已人工复核的拒绝）；负控未达期望的处置按同格式留痕。

**落点对照**：S4/S5/A3–A5 → D 节（`scripts/negcontrol.py` + `reports/negcontrol/`，台账待补）；S8/A8 → G 节（`config/frozen_baseline.json` + NC-10 / NC-14，已具备）；S12 → H 节（已具备）。
**交付前链路增补**：`verify-materials` → `run --level all` → 台账追加一行 → 达 N 轮用例登记退役 + 补位。
**回滚点**：`PIPELINE.md.bak-20261005-w036`；撤销只需删除本节。

---

## MVP 骨架能力与端到端回放（2026-10-06，方案 B 四项裁定落地）

> 目标：把「`new` → 出片 → 两段门禁」收成一条命令可复现的链路。**内容成稿（`script.json` 文案）
> 与 `build_html.py` 逐项目适配仍为已知人工环节**（方案 B 判定为真实瓶颈，不在本批范围）。

### MVP-1 `storyctl new <name>` 骨架收口

- **post-copy 显式清理**（不再只靠 `_IGNORE` 过滤）：`qc/`、`*.log`、`index.html`、`timing.json`（含旧交付报告）。
- **不带 A7 豁免键**：复制后**显式移除**模板携带的 `delivery_spec_waiver`（缺键 = 无豁免）；
  实测脚手架自报「script.json 已移除模板携带的 delivery_spec_waiver 键」。
- **残留根因定位（方案 B 追问项）**：4 个日志 + 1 份旧交付报告位于**模板根** `story/compositor-mac/`
  （`build_audio.log` / `epilogue.log` / `render.log` / `render_direct.log` + `交付质检报告_compositor-mac.md`），
  **不在 `qc/` 内**；`qc/` 的 `_IGNORE` 规则**实测生效**（模板 `qc/` 5 件产物未被带入，新骨架 `qc/` 为空）
  → **判定为非 bug**，无需改 `_IGNORE`。
- 冒烟实证（新建→核验→已删除，不留在 `story/`）：新骨架顶层仅 `build_audio.py` / `build_html.py` /
  `hyperframes.json` / `script.json` + 空 `qc/`、`renders/`，**零残留**、`script.json` 无 waiver 键。

### MVP-2 `build --qc`：显式 opt-in 串联

`build` 默认仍只跑段1；传 `--qc` 则在出片后自动接段2（沿用既有 rc 翻译点，退出码 0/1/2 语义不变）。

### MVP-3 内容校验 `--check`（默认前置）/ `--no-check`

error 集 = `title` / `scenes+lines` / `epilogue 文案` / `voice_role+voice_engine` / `source` / **占位符泄漏扫描**；
warn 集 = `facts` / `date` / `watermark`。回执落 `qc/content.json`（`passed` / `errors[]` / `warns[]`）。

### MVP-4 段 2 时长校验：双 target

`A5` 由「只校 `douyin.mp4`、片尾件跳过」改为**两个 target 各自出结论**（被测件为产线命名时，自动
带上同目录另一个 target）。片尾件口径以**冻结锚点 `total_duration`** 为基准加 `gap + epilogue.wav + tail`，
主片实测与锚点的偏差会平移进片尾件判定（本例 +0.41s → +0.43s），系统偏差 < 0.5s ≪ 容差 2.00s，
不会误报；漏片尾卡 / 丢 BGM / 口播截断等真实漂移仍会被抓出。

### MVP-5 端到端回放实测（gods-eye-view → `gods-eye-view-mvp`）

| 项 | 实测 |
|---|---|
| 链路 | `storyctl new gods-eye-view-mvp` → 注入 `script.json` + 素材 → `storyctl build gods-eye-view-mvp --qc` |
| 门禁 | `EXIT=0`；段1 `rc=0`；段2 `rc=0`；`blocked=false`；日志 `build --qc gods-eye-view-mvp 完成：一条命令出片 + 两段门禁全绿` |
| 内容校验 | `passed=true`，`errors=0`（6 类 error 全过）；`warns=1`（`facts: 缺上屏数据表`，warn 不拦） |
| A5（双 target） | `douyin.mp4` 49.03s vs 48.62s（+0.41s）／`douyin_epilogue.mp4` 55.33s vs 54.90s（+0.43s）—— 均通过 |
| A7 | 0 命中（0 error）；两件 `encode_profile --check` 均「达标」：1080x1920 / High / 4.2 / yuv420p / 44100Hz / 2ch / gop60 / ≤11Mbps |
| A6b | 无 finding（0.2215 MiB/s ÷ 冻结参照 0.115 = **1.93×** < 5×） |
| 其他 | A2 1 处 warn（未传 `--ref`，持久细脊不可判定，不进阻断）；A0/A3 未传参即未跑 |
| 成片指纹 | `douyin.mp4` 49.033s / 1471 帧 / 11.65 MiB / 0.2377 MiB·s⁻¹ / sha `090d65d1…`；`douyin_epilogue.mp4` 55.333s / 1660 帧 / 12.26 MiB / 0.2215 MiB·s⁻¹ / sha `e6fec6d2…` |
| 本链产物 | 成片两件 + `index.html` / `timing.json`（**链内生成**，非模板残留）+ `qc/{pre,report,content}.json` |
| 回滚点 | `proposals/s3_batch_backup/mvp_2026-10-06/`（`storyctl.py.before` / `frame_audit.py.before` / `PIPELINE.md.before` / 回执 `.before` / `before.sha256` / 回放前成片与 story 快照 `gods-eye-view/`） |

| 文件 | 改动前 sha256 | 改动后 sha256 |
|---|---|---|
| `scripts/storyctl.py` | `56de9e54…` | `541d4417…` |
| `scripts/frame_audit.py` | `065e55cb…` | `d1353fe5…` |
| `PIPELINE.md` | `33f2f208…` | 本轮更新后重取（见回执） |

**未闭环项**：S4 `config/selection_catalog.json` 交付时点 **2026-10-08**，须与 `--check` 的 `voice_*`
口径对齐后才能替换 `storyctl catalog` 的启发式回退（voice 17 / video 16 / frontend 20）。
本批**未触发** 9 个存量项目重编码。

---

## R2 跨边界对账层（v1.16.0，2026-10-09 迭代）

> 来源：EigenFlux 广播 13 条工程判据（AI-Film-Studio，纯判据无源码）+ `calesthio/OpenMontage`（**AGPL-3.0，仅借鉴设计思想，未复制任何源码**）。

### Step 7 增补段 1.7

`storyctl build` / `storyctl build --qc` / `storyctl qc` 在**段1（渲染前）→ 段2（渲染后）→ KB 增强轴**之后增补段 **1.7**：跑 `scripts/absorb_r2.py check --json`，落地 R1–R8 八组跨边界对账（终界锚 / 已发送-回执未知态 / 噪声地板 / 判据溯源 / 闭集 sink / 派生指标 / 状态三时界 / 声明式清单三方对齐）。

| 开关 | 行为 |
|---|---|
| 默认 | **advisory**：只告警，**不改变两段门禁退出码语义**（仍由段1/段2 + 既有 KB 轴决定） |
| `--strict-absorb` | 检出（rc=2）升级为阻断，整体 rc=2 |
| `--no-absorb` | 整步跳过（留痕） |
| 独立跑 | `python3 scripts/absorb_r2.py check --story <name>` |

留档：`story/<name>/qc/absorb_r2.json`、`reports/absorb-r2/last_run.json`、锚点 `reports/absorb-r2/{anchors,anchors-volatile}/`（均属本地运行产物，不进仓库）。锚点随运行自动生成；**锚点缺失导致 R1 报 `anchor_absent` 属预期行为**，首次 clone 后跑一次即为预热。

### 锚点准入分层（本层关键设计）

| 类别 | 断言内容 | 适用产物 |
|---|---|---|
| **anchored** | 内容同一（字节数 + sha256） | 确定性产物（成片、清单、报告） |
| **volatile** | **仅解码字节数**（`content_identity = not_asserted`） | 含 wall-clock 字段（`generated_at`）的例行留档 |

两层必须互不交集（自检 `anchor_admission_disjoint` 硬校验）；对 volatile 产物强行断言内容同一 → 直接 FAIL，防止准入分层被误用为「跳过校验」。

### 量化结果（实跑产线 `story/howtolivebetter-54k`）

| 指标 | 改动前 | 改动后 |
|---|---|---|
| `absorb_r2.py check` rc | 2（`blocked=["R1"]`，例行重跑假红） | **0**（`blocked=[]`，`rejected=["R3"]`） |
| `storyctl qc` 段 1.7 rc | 2 | **0**（两段门禁全绿） |
| 负控用例 / 新层命中 | 36 例，基线假绿 28 | **39 例**，新层 **39/39**，基线假绿 30 |
| 故障注入（截断 220 字节） | — | **rc=2 命中**（`truncated_byte_count_mismatch`），还原后 rc=0 |
| 锚点篡改（`declared_bytes` 9999） | — | advisory rc=0；`--strict-absorb` **rc=2** |

**实跑暴露的真实缺陷**：首跑 `check` 抛 `FileNotFoundError`（`anchors-volatile/` 未建目录）——合成用例全绿时不可见，已修（自动建目录）。结论：新层必须对真实现场实跑一次才算验证通过。

### 回滚点

产线侧 `.bak-20261009-absorb2` / `.bak-20261009-absorb` 备份 + sha256 回滚清单；旧锚点保留为 `…voice_consistency.json.eof.json.orphaned-20261009`（不删除）。本层为纯追加，两段门禁判据与既有章节零改动。

*（内容由AI生成，仅供参考）*

> AI生成
*（内容由AI生成，仅供参考）*
*（内容由AI生成，仅供参考）*
