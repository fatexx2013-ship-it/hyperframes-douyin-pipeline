# 跨平台部署手册（DEPLOY）

> 目标：在 **macOS / Linux / Windows(WSL2)** 上把 `hyperframes-douyin-pipeline` 从零跑通到
> `storyctl build <story> --qc` 两段门禁全绿。
>
> 本文档为部署唯一入口；`README.md` 安装章节只保留摘要并指向本文。

---

## 0. 平台支持与验证状态（必读）

| 平台 | 推荐运行方式 | 工具链安装 | 本地 TTS（mlx） | 云端 TTS（openai 兼容） | 实机验证状态 |
|---|---|---|---|---|---|
| **macOS**（Apple Silicon） | 原生终端 | Homebrew | ✅ 可用（默认档） | ✅ 可用 | **已完成端到端实机验证**（`storyctl build --qc` 双门禁全绿） |
| **macOS**（Intel） | 原生终端 | Homebrew | ❌ 不可用（mlx 需 arm64） | ✅ 可用 | 未实机验证（仅静态检查） |
| **Linux**（Debian/Ubuntu 系） | 原生 shell | apt / conda | ❌ 不可用（mlx 仅 Apple Silicon） | ✅ 可用 | **未实机验证**（仅静态检查：路径解析、依赖声明、脚本语法） |
| **Windows**（WSL2 + Ubuntu） | WSL2 内 shell | apt（同 Linux） | ❌ 不可用 | ✅ 可用 | **未实机验证**（仅静态检查） |
| **Windows**（Git Bash 原生） | Git Bash | winget / scoop / choco | ❌ 不可用 | ✅ 可用 | **未实机验证**（仅静态检查；非首选路径） |

> **诚实声明**：除 macOS(Apple Silicon) 外，本文档中的所有命令均为**按平台常规安装方式编写、
> 未在本机实机验证**。未验证项集中在 Linux/Windows 的「whisper.cpp 编译产物名」「Node/hyperframes
> 全局 bin 位置」「字体文件实际路径」三处，若与本机不符，请用第 9 节的**环境变量覆盖**兜底，
> 并以第 8 节 `doctor.py` 的输出来定位。
>
> 不变量：交付规格 **1080×1920 / 30fps** 与编码链为硬约束，任何平台都不得修改
> （`config/param_contract.json` 为真源，`doctor.py` 会做只读校验）。

---

## 1. 依赖总览

| # | 依赖 | 用途 | 是否必需 |
|---|---|---|---|
| 1 | Python ≥ 3.10 | 产线脚本运行 | 必需 |
| 2 | FFmpeg / ffprobe | 配音转码、静音检测、终合成收口 | 必需 |
| 3 | Node.js LTS（含 npm/npx）+ hyperframes | 渲染引擎（HTML → MP4） | 必需 |
| 4 | whisper.cpp（`whisper-cli`）+ ggml 模型 | A4 语义轴回读、卡拉 OK 逐字对齐 | 语义轴/卡拉OK 需要；缺失仅 WARN |
| 5 | TTS provider（mlx 或 openai 兼容） | 配音合成 | 必需（二者择一） |
| 6 | 中文字体（CJK） | 字幕 / 水印 drawtext | 必需 |
| 7 | Python 包：`scipy` | A1 节奏分析、音频处理 | 必需 |

工具一律通过 `scripts/platform_env.py` 解析：**环境变量 → PATH → 平台常见安装目录**（Windows 自动补
`.exe/.cmd/.bat`），因此「装在非标准位置」永远可用第 9 节的 `PIPELINE_<TOOL>` 环境变量指定。

---

## 2. 通用步骤（三平台共用，命令在各自章节已内联）

```bash
git clone <repo-url> hyperframes-douyin-pipeline
cd hyperframes-douyin-pipeline

python3 -m venv venv                    # Windows Git Bash: python -m venv venv
source venv/bin/activate                # Windows Git Bash: source venv/Scripts/activate
pip install -U pip
pip install scipy                       # 或：pip install -e .（读取 pyproject.toml）

mkdir -p models
curl -L -o models/ggml-small.bin \
  https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-small.bin
# 可选（whisper_dtw.py 交叉校验档）：
curl -L -o models/ggml-large-v3-turbo-q5_0.bin \
  https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-large-v3-turbo-q5_0.bin

python scripts/doctor.py                # 首次运行自检（见第 8 节）
```

> `models/` 与 `venv/` 不入库（见 `.gitignore`），每个部署点需自行下载/创建。

---

## 3. macOS（Homebrew）

```bash
# 3.1 Homebrew（未安装时）
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# 3.2 Python
brew install python@3.12

# 3.3 FFmpeg / ffprobe（ffmpeg-full 自带 libass/fontconfig 等全量组件，字幕烧录更稳）
brew install ffmpeg-full
brew link --overwrite --force ffmpeg-full 2>/dev/null || true
ffmpeg -version && ffprobe -version

# 3.4 Node.js + hyperframes 渲染引擎
brew install node
npm i -g hyperframes
hyperframes --version      # 未全局安装也可用 npx hyperframes（doctor 会给出 WARN）

# 3.5 whisper.cpp（提供 whisper-cli + ggml 模型）
brew install whisper-cpp
whisper-cli --help | head -3          # 若你的 formula 可执行名不是 whisper-cli，
                                      # 见第 9 节 PIPELINE_WHISPER_CLI

# 3.6 中文字体：macOS 自带 PingFang SC，无需安装
#     仅当系统裁剪过字体时：brew install --cask font-noto-sans-cjk-sc

# 3.7 venv + 依赖 + 模型（见第 2 节通用步骤）
python3 -m venv venv && source venv/bin/activate
pip install -U pip && pip install scipy

# 3.8 首次自检
python scripts/doctor.py
```

**macOS 本地 TTS（默认档 mlx，Apple Silicon）**：

```bash
# 3.9 安装 mlx-audio（仅 Apple Silicon 可装；Intel Mac 请改用第 6.2 节云端档）
venv/bin/pip install mlx-audio

# 3.10 指向 TTS 驱动模块目录（含 generate_qa_video.py / generate_news_card_video.py）
export TTS_MLX_MODULE_DIR=/absolute/path/to/tts-modules

# 3.11 指向模型根目录（应含 models/ 与 voices/ 子目录）
export QWEN3_TTS_DIR=~/Projects/qwen3-tts-apple-silicon

python scripts/doctor.py --tts
```

---

## 4. Linux（Debian / Ubuntu，apt）

```bash
# 4.1 基础依赖
sudo apt update
sudo apt install -y python3 python3-venv python3-pip ffmpeg git curl cmake build-essential

# 4.2 中文字体（字幕/水印必需）
sudo apt install -y fonts-noto-cjk fonts-noto-cjk-extra
fc-list :lang=zh | head -3            # 确认字体已注册

# 4.3 Node.js LTS + hyperframes
curl -fsSL https://deb.nodesource.com/setup_lts.x | sudo -E bash -
sudo apt install -y nodejs
sudo npm i -g hyperframes
hyperframes --version

# 4.4 whisper.cpp（源码编译；产物名以本机为准，通常为 build/bin/whisper-cli）
git clone https://github.com/ggerganov/whisper.cpp.git
cd whisper.cpp && cmake -B build && cmake --build build --config Release -j
sudo cp build/bin/whisper-cli /usr/local/bin/       # 若无该文件名，改用 PIPELINE_WHISPER_CLI 指定
whisper-cli --help | head -3
cd ..

# 4.5 venv + 依赖 + 模型（见第 2 节通用步骤）
python3 -m venv venv && source venv/bin/activate
pip install -U pip && pip install scipy

# 4.6 首次自检
python scripts/doctor.py
```

**conda / mamba 备选**（无 sudo 或需隔离环境时）：

```bash
conda create -y -n hfpipeline python=3.12 nodejs ffmpeg -c conda-forge
conda activate hfpipeline
npm i -g hyperframes
# 字体：conda install -y -c conda-forge fonts-conda-ecosystem 或 系统 apt 安装 fonts-noto-cjk
# 其余（whisper.cpp 编译、venv、模型下载）同上
```

**Linux 上的 TTS**：mlx 不可用（仅 Apple Silicon），必须使用云端档 → 见第 6.2 节。

---

## 5. Windows

### 5.1 首选：WSL2 + Ubuntu（与 Linux 完全一致）

```powershell
# 5.1.1 管理员 PowerShell：安装 WSL2 + Ubuntu
wsl --install -d Ubuntu
```

```bash
# 5.1.2 以下在 WSL2 的 Ubuntu shell 内执行（同第 4 节）
sudo apt update && sudo apt install -y python3 python3-venv python3-pip ffmpeg git curl cmake build-essential fonts-noto-cjk
curl -fsSL https://deb.nodesource.com/setup_lts.x | sudo -E bash - && sudo apt install -y nodejs
sudo npm i -g hyperframes
# whisper.cpp 编译同 4.4；venv / 依赖 / 模型下载同第 2 节；自检：python scripts/doctor.py
```

> WSL2 下项目建议放在 Linux 文件系统内（如 `~/hyperframes-douyin-pipeline`），
> 放在 `/mnt/c/...` 会显著拖慢渲染与 IO。

### 5.2 备选：Windows 原生 + Git Bash（未实机验证）

```powershell
# 5.2.1 工具链（PowerShell；winget 亦可换 scoop/choco）
winget install -e --id Python.Python.3.12
winget install -e --id Gyan.FFmpeg
winget install -e --id OpenJS.NodeJS.LTS
winget install -e --id Git.Git
npm i -g hyperframes

# 5.2.2 whisper.cpp：下载官方 Release 预编译包（Windows 版产物名通常为 whisper-cli.exe），
#       解压后把目录加入 PATH，或后续用 PIPELINE_WHISPER_CLI 指定绝对路径。
```

```bash
# 5.2.3 之后在 Git Bash 内执行
python -m venv venv && source venv/Scripts/activate
pip install -U pip && pip install scipy
mkdir -p models && curl -L -o models/ggml-small.bin \
  https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-small.bin
python scripts/doctor.py
```

Windows 注意事项：

- 字体：系统自带 Microsoft YaHei（`C:\Windows\Fonts\msyh.ttc`），无需安装。
- 环境变量设置：`setx TTS_MODEL "gpt-4o-mini-tts"`（永久）或 Git Bash 内 `export TTS_MODEL=...`（当前会话）。
- WSL2 与 Git Bash 是**两套独立环境**，venv、模型、环境变量需各自准备，不要混用。
- 产线含 POSIX shell 脚本（`scripts/render.sh` 等），因此 **WSL2 是 Windows 上的推荐路径**。

---

## 6. TTS provider 配置（核心）

真源：`config/tts.json`（**只声明 provider 行为与环境变量名，严禁写入任何凭据**）。
切换方式：环境变量 `TTS_PROVIDER`（优先级最高）> `config/tts.json` 的 `provider` 字段（默认 `mlx`）。

> **未配置即失败**：指定了 provider 但依赖/凭据缺失时，链路会**明确报错并中止**，绝不静默降级。
> `storyctl build` 在执行 `build_audio.py` 之前有 TTS 前置闸门（`tts_preflight`），未就绪直接拦下。

### 6.1 本地档：`mlx`（Qwen3-TTS，默认，仅 macOS Apple Silicon）

| 环境变量 | 必需 | 说明 | 默认值 |
|---|---|---|---|
| `TTS_PROVIDER` | 否 | 设为 `mlx`（默认档，可省略） | `mlx` |
| `TTS_MLX_MODULE_DIR` | **是** | 含 `generate_qa_video.py` 与 `generate_news_card_video.py` 的目录 | 无（缺失即报错） |
| `QWEN3_TTS_DIR` | **是** | 模型根目录，应含 `models/` 与 `voices/` | `~/Projects/qwen3-tts-apple-silicon` |
| `TTS_MLX_VOICE_ROLE` | 否 | 旁白音色角色 | `answer` |
| `TTS_MLX_EMOTION` | 否 | 片尾口播默认情绪 | `thoughtful` |
| `PIPELINE_HOME` | 否 | 备选模块搜索目录（同时可作旧产线根） | 空 |

```bash
export TTS_PROVIDER=mlx
export TTS_MLX_MODULE_DIR=/absolute/path/to/tts-modules
export QWEN3_TTS_DIR=~/Projects/qwen3-tts-apple-silicon
venv/bin/pip install mlx-audio          # 仅 Apple Silicon
python scripts/doctor.py --tts
```

硬件前提：macOS + arm64（Apple Silicon）。Intel Mac / Linux / Windows 一律改用 6.2 云端档。

### 6.2 云端档：`openai`（OpenAI 兼容，**全平台可用**）

任何实现 `POST {base_url}/audio/speech` 的服务均可：OpenAI、Azure OpenAI、硅基流动、本地
vLLM / OpenAI-Server 等。

| 环境变量 | 必需 | 说明 | 默认值 |
|---|---|---|---|
| `TTS_PROVIDER` | **是** | 设为 `openai` | `mlx`（故必须显式设置） |
| `TTS_BASE_URL` | **是** | 服务基址，形如 `https://api.openai.com/v1`（含 `/v1`，不带尾部 `/`） | 无 |
| `TTS_API_KEY` | **是** | 凭据，**只读环境变量**：不落盘、不写日志、不回显 | 无 |
| `TTS_MODEL` | **是** | 模型名，如 `tts-1` / `gpt-4o-mini-tts` / 兼容服务模型名 | 无 |
| `TTS_VOICE` | **是** | 默认音色，如 `alloy` / `zh-CN-XiaoxiaoNeural` | 无 |
| `TTS_VOICE_THOUGHTFUL` | 否 | 片尾「thoughtful」情绪音色（缺省回落到 `TTS_VOICE`） | 回落 `TTS_VOICE` |
| `TTS_VOICE_QUESTION` | 否 | 「question」情绪音色（缺省回落到 `TTS_VOICE`） | 回落 `TTS_VOICE` |
| `TTS_RESPONSE_FORMAT` | 否 | 响应格式 | `wav` |
| `TTS_SPEED` | 否 | 语速（数字） | `1.0` |
| `TTS_TIMEOUT_S` | 否 | 单次请求超时（秒） | `120` |
| `TTS_EXTRA_HEADERS` | 否 | 额外请求头，JSON object 字符串 | 空 |

```bash
export TTS_PROVIDER=openai
export TTS_BASE_URL=https://api.openai.com/v1
export TTS_API_KEY=<你的密钥>
export TTS_MODEL=gpt-4o-mini-tts
export TTS_VOICE=alloy
export TTS_VOICE_THOUGHTFUL=alloy
export TTS_VOICE_QUESTION=nova
python scripts/doctor.py --tts
```

```powershell
# Windows PowerShell 对应写法
$env:TTS_PROVIDER="openai"; $env:TTS_BASE_URL="https://api.openai.com/v1"
$env:TTS_API_KEY="<你的密钥>"; $env:TTS_MODEL="gpt-4o-mini-tts"; $env:TTS_VOICE="alloy"
```

**安全红线**：凭据只能放在环境变量或本地未入库的 `config/api_keys.env`（该文件已被 `.gitignore`
排除），**禁止**写入 `config/tts.json` 或任何入库文件。

---

## 7. 字体依赖

| 平台 | 需安装的 CJK 字体 | 字幕族名（`font_family()`） | 安装方式 |
|---|---|---|---|
| macOS | PingFang SC（系统自带） | `PingFang SC` | 无需安装 |
| Linux | Noto Sans CJK SC | `Noto Sans CJK SC` | `sudo apt install fonts-noto-cjk` |
| Windows | Microsoft YaHei（系统自带） | `Microsoft YaHei` | 无需安装 |

字体解析顺序：`FONT_FILE` 环境变量 → 按平台候选路径（含 glob）→ 找不到即明确报错。
渲染用字体族名可用 `STORY_FONT_FAMILY` 覆盖（例如自定义下载的思源黑体）。

```bash
export FONT_FILE=/absolute/path/to/font.ttc      # 显式指定字体文件
export STORY_FONT_FAMILY="Noto Sans CJK SC"      # 显式指定字幕族名
python scripts/platform_env.py                   # 打印平台/架构 + 全部工具与字体的实际解析结果
```

---

## 8. 首次运行自检：`doctor.py`

```bash
python scripts/doctor.py            # 全量：平台/工具链/字体/不变量/TTS
python scripts/doctor.py --tts      # 只看 TTS provider
python scripts/doctor.py --json     # 机器可读（CI 可解析）
```

检查项与判据：

| 分组 | 检查内容 | 缺失判定 |
|---|---|---|
| 环境 | Python ≥ 3.10、平台/架构/Apple Silicon 标记 | FAIL |
| 工具链 | ffmpeg、ffprobe、node、npx | FAIL |
| 工具链 | whisper-cli | WARN（卡拉OK/语义轴不可用） |
| 工具链 | hyperframes（未全局装但有 npx 时） | WARN |
| 字体 | CJK 字体文件解析 | FAIL |
| 不变量 | 1080×1920 / 30fps / 编码链（**只读**，不修改） | FAIL |
| TTS | 当前 provider 的依赖/凭据就绪性（不联网） | FAIL |

退出码：`0` = 全部通过（可含 WARN）；`1` = 存在 FAIL（阻塞项）。
`storyctl` 侧等价入口：`./scripts/storyctl.py doctor`。

---

## 9. 环境变量总表（覆盖与调优）

### 9.1 工具路径覆盖（`platform_env.find_tool`）

优先级：`PIPELINE_<TOOL>` > `<TOOL>` 裸名 > PATH > 平台常见安装目录。

| 环境变量 | 作用 |
|---|---|
| `PIPELINE_FFMPEG` / `FFMPEG` | FFmpeg 可执行文件绝对路径 |
| `PIPELINE_FFPROBE` / `FFPROBE` | ffprobe 绝对路径 |
| `PIPELINE_NODE` / `NODE` | Node.js 绝对路径 |
| `PIPELINE_NPX` / `NPX` | npx 绝对路径 |
| `PIPELINE_HYPERFRAMES` / `HYPERFRAMES` | hyperframes 可执行文件绝对路径 |
| `PIPELINE_WHISPER_CLI` / `WHISPER_CLI` | whisper-cli 绝对路径（产物名不同的平台必需） |
| `PIPELINE_PYTHON3` / `PYTHON3` | python3 绝对路径 |
| `STORY_EXTRA_PATH` | 追加搜索目录（`:` / `;` 分隔），排在最前 |

> 显式指定但文件不存在/不可执行 → **直接报错**，不静默回退（避免“以为配好了其实没生效”）。

### 9.2 编排与渲染

| 环境变量 | 作用 | 默认 |
|---|---|---|
| `STORYCTL_PYTHON` | `storyctl` 调用子脚本所用的解释器（建议指向 venv） | 仓库 `venv` → PATH |
| `STORYCTL_HYPERFRAMES` | hyperframes 命令（可含参数） | 自动解析 |
| `PATH`（自动注入，无需手动设） | `storyctl` 执行每一步子进程时按 `platform_env.tool_env()` 注入平台工具链目录（Homebrew / `/usr/local/bin` 等），保证 `hyperframes`/`node` 等 shim 在 PATH 精简的 shell 中也可用 | 自动 |
| `STORYCTL_TEMPLATE` | `storyctl new --kind default` 使用的模板 | `compositor-mac` |
| `STORYCTL_RENDER_RESOLUTION` | 渲染精度档：`portrait-4k`（2× 超采样）/ `portrait`（1×）/ `off` | `portrait-4k` |
| `PIPELINE_ROOT` | 仓库根覆盖（story 被搬迁/软链时） | 自动推导 |
| `PIPELINE_HOME` | 旧产线根 / TTS 模块备选搜索目录 | 空 |

推荐的最小可用配置（非 macOS）：

```bash
export TTS_PROVIDER=openai
export TTS_BASE_URL=... TTS_API_KEY=... TTS_MODEL=... TTS_VOICE=...
export STORYCTL_PYTHON="$PWD/venv/bin/python"
# Windows Git Bash: export STORYCTL_PYTHON="$PWD/venv/Scripts/python.exe"
```

---

## 10. 快速验收（冒烟）

```bash
source venv/bin/activate
export STORYCTL_PYTHON="$PWD/venv/bin/python"
# 非 macOS 另需：export TTS_PROVIDER=openai + 四个云端变量

./scripts/storyctl.py new smoke-test --kind short-chips
./scripts/storyctl.py qc smoke-test                       # 只跑门禁
./scripts/storyctl.py build smoke-test --qc               # 全链路出片 + 两段门禁
```

通过判据：日志出现 `✔ build --qc smoke-test 完成：一条命令出片 + 两段门禁全绿`，
产物 `story/smoke-test/douyin.mp4` 与 `story/smoke-test/douyin_epilogue.mp4` 存在，
`story/smoke-test/qc/` 下门禁报告无阻断项。

> 注：`frame_audit` 的非阻断 WARN（如 A2 持久细脊未给 `--ref`）与 KB-A4 语义轴在缺 ASR
> 模型时的 `编排器侧故障（该轴跳过）`均**不影响**两段门禁结论——门禁只认「阻断 0」。

---

## 11. 未实机验证项（技术债，透明披露）

1. **Linux / Windows 全链路未实机跑通**：仅完成静态检查（路径解析、依赖声明、脚本语法）。
   首次在目标平台部署时，建议先跑 `scripts/doctor.py`，再按第 10 节冒烟。
2. **whisper.cpp 编译产物名**：不同发行版/版本的可执行名可能不是 `whisper-cli`
   （历史上曾为 `main` / `whisper-cpp`），需用 `PIPELINE_WHISPER_CLI` 指定。
3. **Linux 字体实际文件路径**：`platform_env.py` 用 glob 覆盖了 Debian/Ubuntu/Fedora/Arch
   常见位置，其他发行版（如 Alpine、openSUSE）可能需要 `FONT_FILE` 显式指定。
4. **Windows 原生 Git Bash 路径**：`C:\Windows\Fonts\*` 与 winget/scoop 的 bin 位置按常规
   编写，未实机核对；建议 Windows 用户优先走 WSL2。
5. **云端 TTS provider 未做真实联网调用验证**：`openai` 档的请求/响应路径按 OpenAI
   `/audio/speech` 规范实现，本机无有效凭据，故仅验证「未配置时明确报错」分支。
6. **`story/<其它story>/` 下遗留的一次性脚本**：`build_audio.py` / `build_html.py` 系列的旧产线绝对路径
   已于本轮批量清理（改为按 `__file__` 自推导 + `platform_env` 解析工具链，共 48 个文件，覆盖 24 个 story），
   可跨平台直接复用；但 `story/easyvoice-intro/compose_v2~v4.py`、`gen_tts.py` 等**实验期脚本**仍写死
   macOS 字体（`/System/Library/Fonts/STHeiti Medium.ttc`）与旧产线根，不参与 `storyctl` 链路，未改造。
7. **`config/selection_catalog.json`** 等 RAG 知识库索引仍含旧产线绝对路径（数据类残留），
   不影响出片链路，未在本轮改造范围内。

---

## 12. 排错速查

| 现象 | 原因 | 处置 |
|---|---|---|
| `找不到可执行文件 ffmpeg` | 未安装或不在 PATH | 按第 3/4/5 节安装，或 `export PIPELINE_FFMPEG=/abs/path/ffmpeg` |
| `provider=mlx 仅支持 Apple Silicon` | 在非 macOS/非 arm64 上用了默认档 | `export TTS_PROVIDER=openai` 并配齐 4 个云端变量 |
| `provider=openai 配置不完整，缺失：...` | 云端变量未配全 | 按第 6.2 节补全 `TTS_BASE_URL/TTS_API_KEY/TTS_MODEL/TTS_VOICE` |
| `provider=mlx 找不到 TTS 驱动模块 generate_qa_video.py` | `TTS_MLX_MODULE_DIR` 未指向驱动模块目录 | `export TTS_MLX_MODULE_DIR=/含该 py 的目录` |
| `找不到可用的中文字体` | 未装 CJK 字体 | Linux：`sudo apt install fonts-noto-cjk`；或 `export FONT_FILE=...` |
| `hyperframes 未找到，且 node/npx 不可用` | 未装 Node.js | 装 Node LTS；`npm i -g hyperframes` |
| `--resolution ... 不在白名单` | `STORYCTL_RENDER_RESOLUTION` 取值非法 | 用 `portrait-4k` / `portrait` / `off` |
| 渲染极慢 | 项目放在 `/mnt/c`（WSL）或机械盘 | 移到 Linux 原生文件系统或内置 SSD |
| `env: node: No such file or directory`（rc=127） | 调用方 shell 的 PATH 未含 Node 目录，`hyperframes` shim 找不到 node | `storyctl` 已自动注入平台工具链 PATH（见 9.2）；自建脚本请自行 `export PATH="/opt/homebrew/bin:$PATH"`，或 `PIPELINE_NODE` 指定 node 绝对路径 |
| `./scripts/storyctl.py: Permission denied` | 克隆/解压后脚本执行位丢失 | `chmod +x scripts/*.py scripts/*.sh`（仓库内带 shebang 的脚本均以 755 入库） |
| `[semantic] 编排器侧故障：缺 ASR 模型 …/models/ggml-small.bin` | 未下载 whisper 模型 | 按第 2 节下载；该轴跳过，**不影响两段门禁结论** |

---

## 附：一键自检脚本（可复制）

```bash
set -e
cd "$(dirname "$0")/.." 2>/dev/null || true
python3 -m venv venv 2>/dev/null || true
source venv/bin/activate
pip install -q -U pip scipy
export STORYCTL_PYTHON="$PWD/venv/bin/python"
python scripts/doctor.py
```
