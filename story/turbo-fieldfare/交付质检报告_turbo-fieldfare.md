# turbo-fieldfare 抖音竖屏成片 · 交付质检报告

- 生成时间：2026-09-27 22:32
- 选题：GitHub `drumih/turbo-fieldfare`（Gemma 4 26B-A4B 在约 2GB 内存的 Apple Silicon Mac 上本地推理；Swift + Metal 自研运行时；Apache-2.0）
- 流水线：video-pipeline-douyin（产线规范 v1.2.0 + 验收套件 v1.0.1）
- 事实口径：全部取自仓库 README 实测数据，已用 `qc/README_verified.md`（README 原文 18674 字符，2026-09-27 拉取）逐项复核，无编造数字

## 一、成片参数

| 项 | 值 |
|---|---|
| 成片 | `story/turbo-fieldfare/douyin_final.mp4` |
| 分辨率 / 画幅 | 1080x1920（9:16 竖屏） |
| 帧率 / 像素格式 | 30 fps / yuv420p |
| 视频编码 | h264 High L5.0，0.84 Mbps |
| 音频编码 | aac LC 44100 Hz 2ch 128 kbps（合成出口 24 kHz mono） |
| 总码率 | 0.97 Mbps |
| 时长 | 106.56 s（正片 100.28 s + 统一关注卡片尾） |
| 文件体积 | 12.96 MB（sha256 `30ee48369025098364e18fab1411828180e17d69b856199af6410f20f6a57033`） |

## 二、口播（TTS 选线）

- 选线：单人女声「慵懒御姐」G 版，逐句合成；全本地 Qwen3-TTS MLX，无云调用。
- 6 场景逐句合成成功，旁白总时长 99.88 s；句内静音 ≥0.40 s 档位 = 0（真实零值，已在三态台账登记 `TRUE_ZERO`）。
- 时间轴已回填 `script.json` / `timing.json`。

## 三、内容结构（6 场景，fact-checked）

| # | 场景 | 关键事实（README 原文口径） |
|---|---|---|
| 1 | 开场定位 | 26B-A4B 推理约 2 GB RAM；任意 Apple Silicon Mac（含 8 GB）；Apache-2.0 |
| 2 | 架构做法 | 常驻 1.35 GB 共享核心 + FP16 KV cache，专家权重按 token 从 SSD 流式读取；不用 MLX、不用 llama.cpp |
| 3 | 实测解码 | M2（8 GB Air）5.1-6.3 tok/s；M5 Pro（24 GB）31-35 tok/s |
| 4 | 内存 / 磁盘 | 常驻约 2 GB；文本模型约 14.3 GB；可选图像包约 1.1 GB；安装不落地整份 checkpoint |
| 5 | 三种入口 | Mac 应用 + CLI + 仅回环地址的 OpenAI 兼容服务；含 function-tool 风险提示 |
| 6 | 收尾 | Apache-2.0；作者 Andrey Mikhaylov；独立研究项目，与 Google 无关 |

> 说明：README 顶部汇总表另有「2.78T parameters / 1.56 TB checkpoint on disk / 8.24 GB peak RSS / 176 KB engine / 0 GPUs」一组数字，出自其引用的 Kimi K3 单 CPU 项目，**不属于本项目口径，未采纳进文案**，避免误读。

## 四、交付前清单执行结果（产线必跑）

| 检查 | 命令 | 结果 |
|---|---|---|
| 参数合同快照 | `param_contract.py snapshot` | `reports/artifacts/manifest_turbo-fieldfare.json`；模型指纹 `sha256:dd741ebb…` |
| 参数合同 check | `param_contract.py check` | FAIL 0 / WARN 3 / OK 5 / SKIP 2，exit 0 → `WARN_ONLY` |
| 参数合同 diff | `param_contract.py diff`（vs paperclip 基线） | FAIL 0 / WARN 3 / OK 6 / SKIP 1，exit 0 |
| 负控素材指纹 | `negcontrol.py verify-materials` | 6/6 一致，exit 0 |
| 负控用例 | `negcontrol.py run --level all` | PASS 14 / 未达期望 0，`ALL_CASES_AS_EXPECTED`，exit 0 |
| 扩展自测 | `extended_selftest.py` | 61/61 PASS |
| 判定规则自测 | `judgement_rules.py self-test` | 全通过 |
| 观测四口径 | `observability_anchors.py check` | `overall=OK`，exit 0（三锚 / 健康 / 计量 / 双新鲜度全 OK，台账 14 条 COMPLETE，`success_ratio=1.0`，`incomplete_count=0`） |
| 资源峰值 | `resource_peaks.py monitor` 包裹渲染 | rc=0；峰值 RSS 1.70 GB / 24 GB = 6.9%，未顶上限，无降级证据 |

### 4.1 三项探索级 WARN（不阻断，登记周回归）

`segment_duration` / `sampler_steps_cfg_seed` / `chunk_size_auto_downgrade` 三项为关键词误命中（视频时长段与生成式采样参数对本地 TTS 链不适用），与 paperclip 基线 diff 结果一致，属既有观测口径，非本次回归。

## 五、验收套件执行结果（acceptance v1.0.1）

| # | 验收项 | 命令 | 结果 |
|---|---|---|---|
| ① | 产物独立验收指纹 | `acceptance_fingerprint.py record` + `recheck` | **MATCH**（rc=0）；sha256 由独立进程重算 = `30ee4836…`，byte_length 12,933,582，结构键 digest `eb364bb5…` |
| ② | 三态台账 | `tri_state_ledger.py append`（6 条）+ `check` | 6 条全部 `accepted=true`；`check ok=true` rc=0：4 条 `effect_verified`（TTS 合成 / 静音门 / 渲染 / 交付编码）、1 条 `recorded_only`（字幕未叠外挂 SRT，记因 `SKIP_BY_POLICY`）、1 条 `unresolved`（发布未执行，记因 `SKIP_BY_POLICY`） |
| ③ | 输出完整性与解析域 | `output_integrity.py run`（包住真实 ffprobe / param_contract check）+ `classify` | 两路均 **CLEAN**（rc=0，blocking=false）；另实测一次 PATH 缺 ffprobe 时判 **UNEXECUTABLE**（blocking=true，无 traceback），验证「命令不可执行」亦为一等失败态 |
| ④ | 版本锁定 / 回归 | `toolchain_lock.py lock / check / regression` | lock 写 `config/toolchain_lock.json`（工具版本 python3 3.11.9 / ffmpeg·ffprobe 9.0.1 / node v26.8.1 / opencode 1.18.31）；check `drift_count=0 verdict=OK`；regression `MATCH`（baseline_digest = current_digest = `31415c6c…`） |
| — | 故障注入自测 | `acceptance_fault_injection.py`（沙箱） | 注入 20 / 检出 20（100%），负控 11 / 误报 0（0%），`SUITE_EXIT=0` |
| — | 真实产线集成实测 | `bash tests/run_real_integration.sh` | rc=0；R1 指纹漂移检出、R2 真实 ffprobe 三态（CLEAN / TRUNCATED / PARSE_DOMAIN_DIRTY / MID_GAP）、R3 台账污染行 rc=2、R4 漂移+回滚、R5 UNEXECUTABLE 均符合预期 |

证据落盘目录：`reports/acceptance/`（指纹记录与重算、两份 output_integrity 判定、台账 jsonl 与 check、fault injection 报告、集成实测日志）。

## 六、抽帧核验

- 抽帧点：2 / 18 / 35 / 55 / 75 / 95 / 104 s，共 7 帧（`story/turbo-fieldfare/qc/`）。
- 视觉模型核验：7 帧均**无文字溢出、无遮挡、无排版错位、无黑屏**；画面数字与 README 口径一致（2 GB / 1.35 GB / 14.3 GB / 1.1 GB / 5.1-6.3 tok/s / 31-35 tok/s / 103 条实验）。
- `blackdetect`（d=0.5，pix_th=0.10）未检出任何长黑段。

## 七、结论

- 成片：`/Volumes/PSSD/抖音视频/story/turbo-fieldfare/douyin_final.mp4`（1080x1920 / 30fps / 106.56 s / 12.96 MB）。
- 验收结论：**通过**。验收套件四项（独立指纹 / 三态台账 / 输出完整性 / 版本锁定回归）全绿；故障注入 20/20 检出、负控 0 误报；真实产线集成实测 rc=0；产线必跑清单 FAIL 0，仅 3 项既有探索级 WARN。
- 待办（不在本次范围）：发布环节未执行（无发布脚本），已在台账记为 `unresolved`。
