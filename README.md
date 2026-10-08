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

1. `build_audio.py` — 文案 → TT 语音，节奏感知（A1）
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
- **御姐音 TTS**：SiliconFlow 模型 + 自定义 prompt，口播自然度达标
- **卡拉 OK 逐字字幕**：逐字对齐 + 逐字高亮
- **片尾口播**：build_audio 生成结尾口播，post_process 拼接到成片

## 安装

```bash
# 1. 克隆
git clone <repo-url>
cd hyperframes-douyin-pipeline

# 2. 创建虚拟环境
python3 -m venv venv
source venv/bin/activate

# 3. 安装依赖
pip install scipy
# 或使用 uv：uv sync

# 4. 确认工具链
ffmpeg -version
whisper-cli --version
npx hyperframes --version

# 5. 下载 whisper.cpp 模型
curl -L -o models/ggml-small.bin   https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-small.bin

# 6. 确认 HyperFrames 已安装（本地或 npm 全局）
npx hyperframes --version
```

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
│   ├── storyctl.py          ← 主控（new / build / qc）
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
