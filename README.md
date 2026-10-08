# hyperframes-douyin-pipeline

**抖音竖屏 AI 短视频本地零成本产线** — 基于 [HyperFrames](https://github.com/hyperframes/hyperframes) 渲染引擎，零 API 调用费，所有工具链在本地跑通。

## 架构概览

```
story/<name>/
├── index.html          ← 竖屏 HTML 源（composition）
├── script.json         ← 文案 / 场景 / 字幕 / tts_params
├── douyin.mp4          ← 成片（1080×1920/30fps）
├── douyin_epilogue.mp4 ← 含片尾件 + 口播结尾的成片
└── qc/                 ← 两段门禁 + 九项 KB 工作流报告
```

**出片链路**：

1. `build_audio.py` — 文案 → TTS 语音（provider 可插拔），节奏感知（A1）
2. `build_html.py` — 字幕 + 语音对齐，渲染前门禁登记（A2/A7）
3. `hyperframes render` — 渲染（默认 portrait-4k 超采样 + 视觉提亮）
4. `post_process.py` — 收口合同规格 1080×1920/30fps
5. `design_ai_gate` — 段1 渲染前门禁
6. `frame_audit` — 段2 渲染后门禁
7. `--qc` 串联：A1 节奏 → A6 停顿 → A4 语义轴 → A5 非确定段 → 两段门禁

## 特性

- **默认画质档位**：渲染超采样（portrait-4k / deviceScaleFactor=2 → 收口 1080×1920）+ 视觉提亮，已在产线代码中默认化
- **A1 情感节奏**：beat 声明驱动停顿档位和入场倍率，音频与画面双向对齐
- **A2 外观一致性锚点**：渲染前登记锚点表，漂移即告警
- **A3 封面 × 标题 2×2**：一次产出 4 张 1080×1920 封面
- **A4 语义轴**：whisper.cpp 回读成片音轨 vs 稿子，语义一致性
- **A5 非确定段单列**：静态扫描 + 帧级比对，识别渲染非确定性
- **A6 停顿检测**：含音轨层（silence_segments），未声明长停顿即不通过
- **A7 光照阈值**：shot 级 bg_base_lift / glow_gain 覆写 + 越界阈值
- **A8 模板库槽位化**：kind → template_story + slots.json，new 后自动校验
- **A9 去 AI 味 lint**：连接词密度、套话、排比、句长方差等 12 类阈值
- **两段门禁**：渲染前 design_ai_gate + 渲染后 frame_audit，阻断=0 放行
- **TTS 可插拔 provider**：默认本地 `mlx`（Qwen3-TTS，Apple Silicon 零成本）/ 可切 `openai` 兼容云端档（OpenAI、Azure、硅基流动、本地 vLLM 等）。provider 由 `config/tts.json` 声明、`TTS_PROVIDER` 环境变量覆盖，凭据只读环境变量；未配置即明确报错，**不静默降级**
- **跨平台工具链解析**：`scripts/platform_env.py` 统一解析 ffmpeg/ffprobe/node/hyperframes/whisper-cli 与中文字体（PATH + 平台常见目录 + 环境变量覆盖，Windows 自动补 `.exe`），不再依赖 macOS 绝对路径；`story/<name>/` 下的 build 脚本按 `__file__` 自推导路径（仓库可整体搬迁/改名），`storyctl` 还会为每一步子进程注入工具链 PATH，PATH 精简的 shell 也能跑通渲染
- **卡拉 OK 逐字字幕**：逐字对齐 + 逐字高亮
- **片尾口播**：build_audio 生成结尾口播，post_process 拼接到成片

## 平台支持矩阵

| 平台 | 状态 | 本地 TTS（mlx） | 云端 TTS（openai 兼容） | 说明 |
|---|---|---|---|---|
| **macOS（Apple Silicon）** | ✅ **已实机验证** | ✅ 可用（默认档） | ✅ 可用 | 端到端 `storyctl build --qc` 双门禁全绿 |
| macOS（Intel） | ⚠️ 未实机验证 | ❌ 不可用（mlx 需 arm64） | ✅ 可用 | 需显式切 `TTS_PROVIDER=openai` |
| **Linux（Debian/Ubuntu）** | ⚠️ 未实机验证（仅静态检查） | ❌ 不可用 | ✅ 可用 | 部署命令见 [docs/DEPLOY.md](docs/DEPLOY.md) |
| **Windows（WSL2）** | ⚠️ 未实机验证（仅静态检查） | ❌ 不可用 | ✅ 可用 | 推荐路径，命令同 Linux |
| Windows（Git Bash 原生） | ⚠️ 未实机验证（仅静态检查） | ❌ 不可用 | ✅ 可用 | 非首选；产线含 POSIX shell 脚本 |

> 未实机验证项与已知技术债的完整清单见 [docs/DEPLOY.md](docs/DEPLOY.md) 第 11 节。
> 不变量 **1080×1920 / 30fps** 与编码链在所有平台一致，`scripts/doctor.py` 会做只读校验。

## 安装

完整的三平台可复制命令见 **[docs/DEPLOY.md](docs/DEPLOY.md)**（macOS Homebrew / Linux apt 或 conda / Windows WSL2 与 Git Bash，含 TTS 环境变量逐项清单与排错表）。摘要：

```bash
# 1. 克隆
git clone <repo-url>
cd hyperframes-douyin-pipeline

# 2. 工具链（各平台安装方式见 docs/DEPLOY.md）
#    ffmpeg / ffprobe、Node.js LTS + hyperframes、whisper.cpp（whisper-cli）、中文字体
ffmpeg -version && npx hyperframes --version && whisper-cli --help | head -3

# 3. Python 环境
python3 -m venv venv
source venv/bin/activate          # Windows Git Bash: source venv/Scripts/activate
pip install -U pip && pip install scipy

# 4. whisper.cpp 模型
mkdir -p models && curl -L -o models/ggml-small.bin \
  https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-small.bin

# 5. TTS provider（二者择一；凭据只放环境变量，禁止入库）
#    A) 本地档 mlx（默认，仅 macOS Apple Silicon）
#       venv/bin/pip install mlx-audio
export TTS_MLX_MODULE_DIR=/absolute/path/to/tts-modules
export QWEN3_TTS_DIR=~/Projects/qwen3-tts-apple-silicon
#    B) 云端档 openai 兼容（全平台可用）
#       export TTS_PROVIDER=openai TTS_BASE_URL=... TTS_API_KEY=... TTS_MODEL=... TTS_VOICE=...

# 6. 首次运行自检（工具链 / 字体 / 不变量 / TTS）
python scripts/doctor.py
```

> `models/`、`venv/`、成片与音轨均不入库，每个部署点需自行准备。
> 若工具装在非标准位置，用 `PIPELINE_<TOOL>` 覆盖（如 `PIPELINE_WHISPER_CLI=/abs/path/whisper-cli`）。
> 脚本以 755 执行位入库；若克隆/解压后执行位丢失，`chmod +x scripts/*.py scripts/*.sh`。

## 使用

```bash
# 新建故事
./scripts/storyctl.py new my-story --kind short-chips

# 编辑文案
# 编辑 story/my-story/script.json + story/my-story/index.html

# 一键出片
./scripts/storyctl.py build my-story

# 带门禁质检
./scripts/storyctl.py build my-story --qc

# 只跑门禁（已有产出）
./scripts/storyctl.py qc my-story
```

## Contributing

1. Fork 本仓库
2. 创建功能分支：`git checkout -b feature/xxx`
3. 修改后运行 `./scripts/storyctl.py qc <story-name>` 验证门禁
4. 提交 PR，附上故事出片截图

### 开发规范

- **产线代码本次只评估不修改**（如需修改请走 review）
- 新工作流脚本放在 `scripts/` 下，以 `KB-Ax` 或 `kb_ax_` 前缀
- `config/` 为共享真源，改动前备份 `.bak-20261008`
- 1080×1920 / 30fps 为不变量，不得破坏

## 仓库结构

```
hyperframes-douyin-pipeline/
├── PIPELINE.md              ← 产线总说明书
├── pyproject.toml           ← 项目元数据与依赖
├── append_epilogue.py       ← 片尾口播拼接
├── post_process.py          ← 收口 1080×1920 / 30fps
├── epilogue_template.json   ← 片尾模板
├── scripts/                 ← 产线脚本集
│   ├── storyctl.py          ← 主控（new / build / qc / doctor）
│   ├── platform_env.py      ← 跨平台适配层（工具链 / 字体 / 环境变量覆盖）
│   ├── tts_provider.py      ← TTS 可插拔 provider（mlx / openai 兼容）
│   ├── doctor.py            ← 首次运行自检（只读：工具链 / 字体 / 不变量 / TTS）
│   ├── canon_guard.py       ← 规范守卫
│   ├── design_ai_gate.py    ← 段1 渲染前门禁
│   ├── frame_audit.py       ← 段2 渲染后门禁
│   ├── rhythm.py (A1)、anchors_check.py (A2)、make_covers.py (A3)
│   ├── semantic_axis.py (A4)、nondeterminism.py (A5)、pause_audit.py (A6)
│   ├── template_slots.py (A8)、deai_lint.py (A9)
│   ├── render.sh、whisper_dtw.py、build_karaoke_ass.py、encode_profile.py …
├── config/                  ← 共享真源（canon / 参数合同 / 选择目录 / 工具链锁）
├── docs/                    ← 产线规范.md、决策记录与技术债.md
├── templates/               ← 模板库（registry.json + 各 kind 模板 + _shared tokens/vendor）
├── story/<name>/            ← 每个故事：script.json、timing.json、index.html 源、build_*.py
└── tests/、tools/            ← 回归基线、fixtures、辅助工具
```

**不入库内容**（详见 `.gitignore`）：成片与音轨（`*.mp4` / `*.wav` / `*.mp3`）、渲染中间物（`story/*/renders/`、`covers/`、`qc/`）、`output/`、模型权重 `models/`、虚拟环境 `venv/`，以及凭据文件 `config/api_keys.env`。

## License

MIT License. See [LICENSE-MIT](LICENSE-MIT).
