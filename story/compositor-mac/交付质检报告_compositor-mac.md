---
AIGC:
    Label: "1"
    ContentProducer: 001191440300708461136T1XGW3
    ProduceID: b82594f1be8e85c02fc42784acc7d5b8_f81fb292b82c11f18442525400de85a5
    ReservedCode1: 6TfEeas0QGkomITVgevE18iFBY88H2w6utwbwNeAzFXNI+R/PAePwKs2/WyCIkc+iQlibTH4dfwQoap9GHcKzjUKj6ZdTsn9xZ1nB9U/L30sfm5ScE9vFdw4czMEqV54eiUTg9lJJUr7AEF+iFHEYenT7ztgGmC25qQ4zlb6iKlYalU5rn2aiWkCRhs=
    ContentPropagator: 001191440300708461136T1XGW3
    PropagateID: b82594f1be8e85c02fc42784acc7d5b8_f81fb292b82c11f18442525400de85a5
    ReservedCode2: 6TfEeas0QGkomITVgevE18iFBY88H2w6utwbwNeAzFXNI+R/PAePwKs2/WyCIkc+iQlibTH4dfwQoap9GHcKzjUKj6ZdTsn9xZ1nB9U/L30sfm5ScE9vFdw4czMEqV54eiUTg9lJJUr7AEF+iFHEYenT7ztgGmC25qQ4zlb6iKlYalU5rn2aiWkCRhs=
---

# compositor-mac 抖音竖屏成片 · 交付质检报告

- 日期：2026-09-24
- 选题：robbietilton/Compositor —— Mac 上的免费开源 Photoshop 替代品（事实口径取自官方仓库 README，未引用星标数字）
- 成片：[douyin_final.mp4](/Volumes/PSSD/抖音视频/story/compositor-mac/douyin_final.mp4)

## 一、成片参数

| 项 | 实测值 | 合同要求 | 判定 |
|---|---|---|---|
| 时长 | 83.21s | 目标 70–90s | OK |
| 体积 | 10.97MB（11505020 字节） | — | OK |
| 分辨率 / 画幅 | 1080x1920 / 9:16 | 1080x1920 / 9:16 | OK |
| 帧率 | 30 fps（30/1） | 30fps | OK |
| 视频编码 | H.264 High / yuv420p / 0.97 Mbps | H.264 High@4.2 | OK |
| 音频 | AAC LC / 44100Hz / 2ch / 128kbps | 44100Hz，含 BGM 立体声 2ch | OK |
| 水印 | jerrychen2001（全程右下角） | jerrychen2001 | OK |
| 片尾 | 统一关注卡（关注 jerrychen2001 / 评论区聊聊 / 你还想拆哪个项目？） | 统一关注卡 | OK |

## 二、口播（TTS 选线）

- 选线判定：单人女声口播 → **单人线 `solo-yujie`**，判定结果已写入 `script.json` 的 `tts_line` 字段。
- 引擎：本地 **Qwen3-TTS 12Hz 1.7B Base 8bit（MLX）**，参考音 `yujie_thoughtful.wav`（慵懒御姐音），**未启用任何云端 TTS**。
- 版本：**G 版**（逐句·对比停顿），与逐句 TTS + 卡片时间轴天然对齐。
- 参数：句内静音修剪 `-52dB / 0.30s`；句首留白 0.12s / 句尾 0.08s；句间停顿 逗号 0.25s / 句末 0.75s / 段落 1.20s；出口 24kHz mono → 成片 44.1kHz。
- 硬指标：**句内静音 ≥0.40s 的档位 = 0**（6/6 句全部为 0）。
- 时长：旁白 76.56s（含尾部静音 76.96s），逐句 8.08–14.52s。

## 三、交付前清单执行结果

| # | 动作 | 命令 | 结果 |
|---|---|---|---|
| 1 | 成片快照 | `param_contract.py snapshot` | `reports/artifacts/manifest_compositor-mac.json` 已生成 |
| 2 | 对合同校验 | `param_contract.py check` | **FAIL 0** / WARN 3 / OK 5 / SKIP 2，exit 0 |
| 3 | 基线比对 | `diff manifest_story_howtolivebetter.json manifest_compositor-mac.json` | **无不变量级漂移**，FAIL 0，exit 0 |
| 4 | 负控素材指纹 | `negcontrol.py verify-materials` | 6/6 素材指纹一致，exit 0 |
| 5 | TTS 选线确认 | 见第五节判据 | `solo-yujie`（已写入 script.json 备注） |
| 6 | 资源峰值（渲染阶段） | `resource_peaks.py monitor --rss-limit 24GB` | 峰值 **1.7GB / 24GB = 7.2%**，未顶上限、无降级证据 |

节奏类动作（本次一并执行）：

- `negcontrol.py run`：**PASS 8 / 未达期望 0**，两级负控（不变量级 2 例 + 探索级 5 例 + 正控 1 例）全部达到期望，留档 `reports/negcontrol/last_run.json`。

## 四、3 项探索级 WARN（不阻断，登记周回归）

| 字段 | 现象 | 结论 |
|---|---|---|
| segment_duration | 成片 83.21s vs 脚本声明 76.56s，差 +6.65s | 差异等于追加的片尾段 6.24s + 尾静音，属口径差（声明时长为旁白时长），非漂移 |
| sampler_steps_cfg_seed | TTS 推理采样参数未显式固定（依赖库默认） | 既有链路现象，与上一版基线一致；建议后续在 `generate_qwen3_tts` 显式传 temperature/top_p/seed |
| chunk_size_auto_downgrade | 命中关键词 `render.log`（日志中"降级证据：未在命令输出中命中降级关键词"一行） | 检测器关键词误命中，实测峰值 1.7GB / 24GB、无降级；属文档噪声 |

## 五、抽帧核验

抽帧文件位于 `story/compositor-mac/qc/`：f_06s.jpg、f_40s.jpg、f_81s_epilogue.jpg。视觉核验结论：

- 第 6s：开场介绍（Photoshop / GIMP 价格对比 → 完全免费 MIT 开源），水印 jerrychen2001 在右下角。
- 第 40s：选区工具功能展示，水印正常。
- 第 81s：关注引导片尾卡，卡片文字为「关注 jerrychen2001 / 评论区聊聊 / 你还想拆哪个项目？」，水印正常。

## 六、链路与工具链

- 链路：`build_audio.py`（逐句 Qwen3 御姐配音 + G 版静音修剪/留白）→ `build_html.py`（赤焰热力主题 index.html + 卡片时间轴）→ `hyperframes render --quality high`（峰值监控包装）→ `post_process.py --no-epilogue`（规格直通）→ `append_epilogue.py`（G 版重排 + 统一关注卡片尾 + 44.1kHz 立体声重建）。
- 工具链 pin 实测：ffmpeg/ffprobe **9.0.1**、hyperframes **0.8.13**、node **v26.8.1**，与规范 §4 口径一致。

## 七、遗留与建议

1. TTS 采样参数（temperature/top_p/seed）目前依赖库默认值，建议在 TTS 调用处显式固定并登记 manifest。
2. 成片视频码率 0.97Mbps 偏低（本次画面以文字/矢量卡片为主，编码器压缩效率高），如需更高码率可在渲染阶段提码率，而非在后期二次编码。
3. `chunk_size_auto_downgrade` 检测器对"降级"关键词的日志误命中建议加白名单（排除 resource_peaks 报告文本）。
*（内容由AI生成，仅供参考）*
