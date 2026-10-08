# AutoClip 抖音竖屏短视频 · 交付质检报告

- 生成时间：2026-09-29
- 选题：GitHub 开源项目 `zhouxiaoka/autoclip`（AI 高光提取与自动剪辑二创工具，Python / MIT / ★9,019 / Fork 1,660）
- 产线：`/Volumes/PSSD/抖音视频`（产线规范 v1.2.0，合同 param_contract v1.1.0）
- 工程目录：`story/autoclip/`
- 成片：`story/autoclip/douyin_final.mp4`

---

## 一、成片参数（ffprobe 直读＋param_contract）

| 项 | 实测值 | 结论 |
|---|---|---|
| 分辨率 | 1080×1920（9:16 竖屏） | 合同允许集内 OK |
| 帧率 | 30/1（avg 30.019） | 与基线一致 OK |
| 视频编码 | H.264 High L5.0 / yuv420p / bt709 | OK |
| 视频码率 | 740 kbps | — |
| 音频 | AAC LC 44100Hz / 2ch / 128 kbps | 符合合同允许集 OK |
| 总码率 | 875 kbps | — |
| 时长 | 106.43 s（正片 98.89 s + 片尾段 7.54 s） | WARN（见下） |
| 文件大小 | 11,638,890 字节（11.10 MiB） | — |
| 指纹 | sha256 `903ab60fe2fefe6251a9e108b5741b96a3ab7dbbd3b57af04afd9e3dd94cb9ee` | recheck 重算一致 |
| 渲染窗口帧数 | 3193 帧 @30fps | 经 change_events 放行 |
| 渲染峰值 RSS | 1.807 GiB @ hyperframes-render（上限 24GB 的 7.5%，未触发降级） | OK |

## 二、合同判定结果

| 检查 | 结论 | 明细 |
|---|---|---|
| `param_contract check`（无基线自检） | **WARN_ONLY**，FAIL 0 / WARN 2 / OK 5 / SKIP 3，exit 0 | — |
| `param_contract diff`（vs 冻结基线 paperclip-1.1.0） | **WARN_ONLY**，FAIL 0 / WARN 2 / OK 6 / SKIP 2，exit 0 | 帧数差异已登记放行 |

- WARN-1 `segment_duration`：成片 106.43s 与旁白声明 98.89s 差 +7.540s，系固定片尾卡（含 0.4s 前置留白、0.5s 尾静音）导致，属产线既有设计，非漂移。
- WARN-2 `sampler_steps_cfg_seed`：TTS 采样参数依赖库默认值未显式固定，属产线既有已知项（各选题一致）。
- `frozen_baseline_digest`：冻结摘要重判一致（`sha256:cdfb67ff463…`），冻结基线未被篡改。
- `render_window_frames`：冻结基线 2507 帧 → 本片 3193 帧，差异由选题文案时长决定，已在 `story/autoclip/change_events.json` 登记（CE-20260929-01），判定 OK 放行；画幅、帧率、色彩空间均与基线逐项一致。

## 三、内容与事实口径

- 旁白 6 句（Qwen3-TTS-12Hz-1.7B-Base-8bit 本地 MLX，参照音 `yujie_thoughtful.wav` 慵懒御姐音，情绪自动匹配）：

| # | 起始 | 时长 | 首句（截断） |
|---|---|---|---|
| 1 | 0.00 | 12.63 s | GitHub 上有个项目叫 AutoClip，九千多颗星… |
| 2 | 13.83 | 13.36 s | 用法很直接：导入一段带字幕的视频… |
| 3 | 28.39 | 17.28 s | 它适合访谈、播客、课程和直播回放… |
| 4 | 46.87 | 18.58 s | 模型这块给得很宽：Qwen、OpenAI、Gemini… |
| 5 | 66.65 | 17.76 s | 入口不止一个：桌面版内置 Python 和 FFmpeg… |
| 6 | 85.61 | 13.28 s | 项目按 MIT 协议开源，macOS 和 Windows… |

- 句内静音门（≥0.40s 档位）计数：**0**（真实零值，`timing.json` 留档）。
- BGM：《Karma - Michael Ramir C. (mixkit 1183)》铺底，音量 0.18。
- 固定片尾："关注 jerrychen2001，评论区聊聊你想用 AutoClip 剪哪段视频。"（含关注卡）
- 水印：jerrychen2001（渲染层烧录）。
- 字幕：渲染层烧录硬字幕（不另挂外挂 SRT）。
- 事实对账：`qc/README_raw.md`（README 原文 6,541 字节）+ `qc/README_verified.md`，10 条事实逐条比对 README/GitHub API，无编造、无误引用（Star 9,019、Fork 1,660、Python、MIT、创建于 2025-07-08、Trendshift 榜 repository 25801）。

## 四、视觉抽帧核验

- 抽帧点：2s / 20s / 35s / 55s / 75s / 95s / 101s / 103.5s（8 帧）。
- 结论：7 帧正常；95s 帧（片尾场景）在整帧缩略图判读中被提示"上方文字重叠"，经同帧三段 1.5× 放大复核（`qc/frames_r2/`），确认**无文字叠压**——该处为片尾卡上方三枚数据方框（MIT / 9,019 Star / 1,660 Fork）在缩略尺寸下的密集排版误判；中部文字逐字可读（"关注 jerrychen2001 / 评论区聊聊 / 你想先剪哪段视频？"），仅提示对比度偏低，不影响阅读。
- 黑帧检测：`blackdetect d=0.5:pix_th=0.10` 未检出任何 ≥0.5s 黑段。
- 布局修正记录：渲染后首轮抽帧发现第 4 帧（成本对比场景）标志框与柱体压字，已调整柱高（440→380）并将标注框右移＋加引导线，重渲染后复抽帧确认无重叠。

## 五、验收套件证据（acceptance-kit v1.0.1-20260927）

| 项 | 命令 | 结论 | 证据 |
|---|---|---|---|
| 独立指纹 | `acceptance_fingerprint.py record / recheck` | MATCH，exit 0 | `reports/acceptance/fingerprint_autoclip.json` |
| 三态台账 | `tri_state_ledger.py append ×6 / check` | `ok: true`，exit 0（4 条 effect_verified＋2 条按政策 SKIP） | `reports/acceptance/tri_state_autoclip.jsonl` |
| 输出完整性 | `output_integrity.py run / classify` | **CLEAN**（字节/解析/条数三项一致），exit 0 | `oi_ffprobe_capture_autoclip.json`、`oi_ffprobe_classify_autoclip.json` |
| 版本锁定 | `toolchain_lock.py lock / check / regression` | drift 0，verdict OK / MATCH，digest `31415c6c…` | `config/toolchain_lock.json` |
| 故障注入自测 | `acceptance_fault_injection.py` | 注入 20 / 检出 20（100.0%），负控 11 / 误报 0 | `reports/acceptance/fault_injection_report_autoclip.json` |
| 真实产线集成 | `tests/run_real_integration.sh` | rc 0（跳检期间存在人为破坏，判定正确） | `temp/evidence/real-integration/20260929_072023` |

## 六、质检脚本前置自检

| 项 | 结论 |
|---|---|
| `negcontrol.py run --level all` | PASS **14 / 14**，未达期望 0，rc 0（`reports/negcontrol/last_run.json`，2026-09-29T07:19:14） |
| `extended_selftest.py` | **61 / 61 PASS** |
| `judgement_rules` self-test | 全部通过 |
| `observability_anchors.py check` | **overall OK**，四口径全过：三锚（字节 10,132 / 18 条 / 版本 1.1.0）＋执行健康（exit 0）＋台账（14 条回执，success_ratio 1.0，无未完成）＋双新鲜度（read/content 均 FRESH，EVENT_OBSERVED）（`reports/observability/check_autoclip_result.json`） |
| 资源峰值档案 | `reports/peaks/render_autoclip.json`（1.8GB 峰值，未顶 24GB 上限，无降级/OOM 关键词） |

## 七、结论

成片满足 1080×1920 / 30fps / 御姐音配音 / 硬字幕烧录 / BGM 铺底 / 水印 jerrychen2001 / 固定片尾全部规格要求；事实口径经 README 原文逐条比对；合同判定无 FAIL（2 项 WARN 均为产线既有设计项，跨选题帧数差异已按约定登记 change_events）；验收套件五项全过、负控 14/14、故障注入 20/20、观测四口径 OK。**准予交付。**
