---
AIGC:
    Label: "1"
    ContentProducer: 001191440300708461136T1XGW3
    ProduceID: b82594f1be8e85c02fc42784acc7d5b8_725f2e0dbed711f1884b525400cd780f
    ReservedCode1: uTddVlXn4d3Al44J4EWBYOcHovOTOKLwCPTWdtdkefqdswVp/HuLD67kKEhl0Zw1zqOwNaLhK+kZyS337ZRVe2rbAoxpxvDhA7yc46Qq4eR3tDcAX4SKFkT4onuWBo705kY9wpSJ4yGYo+NlpAQGJjgHGXf32bZj7NcyL8PkSV5USONZ1IQp6h7gig8=
    ContentPropagator: 001191440300708461136T1XGW3
    PropagateID: b82594f1be8e85c02fc42784acc7d5b8_725f2e0dbed711f1884b525400cd780f
    ReservedCode2: uTddVlXn4d3Al44J4EWBYOcHovOTOKLwCPTWdtdkefqdswVp/HuLD67kKEhl0Zw1zqOwNaLhK+kZyS337ZRVe2rbAoxpxvDhA7yc46Qq4eR3tDcAX4SKFkT4onuWBo705kY9wpSJ4yGYo+NlpAQGJjgHGXf32bZj7NcyL8PkSV5USONZ1IQp6h7gig8=
---

# immich 抖音竖屏成片 · 交付质检报告

- 生成时间：2026-10-03 10:45
- 选题：GitHub `immich-app/immich`（高性能自托管照片 / 视频管理方案，Google Photos 的开源替代；AGPL-3.0）
- 流水线：video-pipeline-douyin（产线规范 + 参数合同 1.1.0 / 负控 1.1.0 / 观测 1.1.0）
- 事实口径：全部取自仓库 README 原文、官方 docker-compose 与 releases 重定向核验，逐项留档 `qc/README_verified.md`（README 原文 5,543 字节，2026-10-03 拉取），无编造数字

## 一、成片参数

| 项 | 值 |
|---|---|
| 成片 | `story/immich/douyin_final.mp4` |
| 分辨率 / 画幅 | 1080x1920（9:16 竖屏） |
| 帧率 / 像素格式 | 30 fps（30/1）/ yuv420p / bt709 |
| 视频编码 | h264 High L5.0，933 kbps |
| 音频编码 | aac LC 44100 Hz 2ch 128 kbps（合成出口 24 kHz mono） |
| 总码率 | 1.07 Mbps |
| 总帧数 | 2,861 帧（正片 2,685 + 片尾 176） |
| 时长 | 95.36 s（正片 89.50 s / 2,685 帧 + 统一关注卡片尾 5.87 s / 176 帧） |
| 文件体积 | 12.13 MB（12,724,960 字节；sha256 `4d943e66ed22eb470a17b9c72b96770e5eb5dac8c3436ce2cc5ee0cdcd795bf2`） |

> 渲染链路：`hyperframes render --quality high`（workerCount 4 / captureMode beginframe）→ `append_epilogue.py` 追加固定片尾 → 复制为 `douyin_final.mp4`。中间产物 `douyin.mp4`、`douyin_epilogue.mp4` 保留在工程目录内备查。

## 二、口播（TTS 选线）

- 选线：单人女声「慵懒御姐」G 版（`voice_mode=single_narrator` / `voice_role=answer`），句级合成，全本地 Qwen3-TTS MLX，无云调用。
- 5 句口播逐句合成成功，旁白总时长 89.08 s；句内静音 ≥0.40 s 档位 = 0（真实零值）。
- 时间轴已回填 `script.json` / `timing.json`；5 场景时间轴：0–13.91 / 15.11–30.63 / 31.83–48.44 / 49.64–67.64 / 68.84–89.08。

## 三、内容结构（5 场景，fact-checked）

| # | 场景 | 关键事实（一手口径） |
|---|---|---|
| 1 | 开场定位 | 自托管照片 / 视频管理方案（README 原句）；GitHub 11.5 万星；AGPL-3.0；最新稳定版 v3.2.4 |
| 2 | 核心能力 · 手机备份 | iOS / Android 原生 App，整库自动备份、可选相册、后台增量备份（README 功能表三项均 Yes） |
| 3 | 核心能力 · 本地 AI | 人脸聚类 / CLIP 语义搜索 / 物体识别 / 图内文字搜索；机器学习服务为独立容器（compose 中 `immich-machine-learning` 镜像） |
| 4 | 算笔账 | Google Photos 2TB 档约 9.99 美元/月（外部公开定价口径）vs Immich 零订阅费、仅一次性硬件成本；数据以标准文件存储可迁出 |
| 5 | 收尾 | Docker Compose 一键启动（`'2283:2283'`）；官方 Demo `demo.immich.app`；官方 3-2-1 备份警示（README 原文） |

## 四、参数合同（1.1.0）

| 检查 | 命令 | 结果 |
|---|---|---|
| 快照 | `param_contract.py snapshot --video story/immich/douyin_final.mp4 --story-dir story/immich --label immich` | `reports/artifacts/manifest_immich.json`；模型指纹 `sha256:dd741ebb…`；落盘日志 `qc/param_snapshot.log`（= `qc/param_all.log`） |
| check | `param_contract.py check reports/artifacts/manifest_immich.json` | FAIL 0 / WARN 2 / OK 5 / SKIP 3，exit 0 → `WARN_ONLY`（`reports/artifacts/param_check_immich.log`） |
| diff | `param_contract.py diff …manifest_paperclip_v110.json …manifest_immich.json` | FAIL 0 / WARN 2 / OK 6 / SKIP 2，exit 0（`reports/artifacts/param_diff_immich.log`） |

### 4.1 跨选题帧数变更登记（硬停项已放行）

首次 diff 命中扩展层硬停：`render_window_frames 2507 → 2861（无变更事件）`。按产线既有约定（turbo-fieldfare、autoclip 先例）登记变更事件后放行：

- 登记文件：`story/immich/change_events.json`，事件号 `CE-20261003-01-render-window-frames`
- 依据：冻结基线 paperclip-1.1.0 为正片 83.56 s（2,507 帧）；本片正片 89.50 s（2,685 帧）、追加片尾段 5.87 s（176 帧）后成片 95.36 s（2,861 帧）。差异由选题文案时长决定，非渲染降级、非参数漂移；分辨率 / fps / 色彩空间与基线一致（已核验）。
- 放行结果：重跑 diff 后 `render_window_frames` 判 OK，全表 FAIL 0。

### 4.2 两项探索级 WARN（不阻断，登记周回归）

- `segment_duration`：成片 95.36 s 与声明（旁白累计）89.08 s 差 +6.280 s > 容差 0.1 s —— 该差值 = 统一片尾段 5.87 s + 正片相对旁白声明的 0.41 s 装配余量（场景间 1.2 s 停顿与首尾静音），属产线固定结构，非漂移。
- `sampler_steps_cfg_seed`：TTS 推理采样参数未显式固定（依赖库默认值），为既有链路观测口径，延续 turbo-fieldfare / autoclip 记录。
- 说明：`chunk_size_auto_downgrade` 在首轮 diff 中曾因 `qc/param_all.log` 内自含「降级」字样产生关键词误命中（自指），已将 `qc/param_all.log` 规范为快照输出、check/diff 全量日志改落 `reports/artifacts/`，复跑后该项回到 SKIP，误命中消除。

## 五、负控与自测

| 检查 | 命令 | 结果 |
|---|---|---|
| 负控素材指纹 | `negcontrol.py verify-materials` | 6/6 一致，exit 0 |
| 负控用例 | `negcontrol.py run --level all` | PASS 14 / 未达期望 0，`ALL_CASES_AS_EXPECTED`（`reports/negcontrol/last_run.json`，run_at 2026-10-03T10:37:14） |
| 扩展自测 | `extended_selftest.py` | 61/61 PASS |
| 判定规则自测 | `judgement_rules.py self-test` | 全部通过（含人工冻结窗排除数 = 1） |

## 六、观测四口径（1.1.0）

- 观测单：`reports/observability/obs_immich_positive.json`（三锚指向本次 `check_immich.json`：字节 10,118 / 条目 18 = 10 核心 + 8 扩展 / 版本 1.1.0）
- 检查命令：`observability_anchors.py check --file reports/observability/obs_immich_positive.json`
- 结果：`overall=OK`，exit 0，`failed_sections=[]`；台账 14 条全部 COMPLETE，`incomplete_count=0`，`success_ratio=1.0`；双新鲜度 FRESH / `EVENT_OBSERVED`（读级 + 内容级均新鲜）
- 留档：`reports/observability/check_immich_result.json`

## 七、资源峰值

- 命令：`resource_peaks.py monitor --name immich-qc-verify --interval 0.5 --rss-limit 24GB -- …（ffprobe + blackdetect + param_contract check）`
- 结果：rc=0；整段峰值 RSS 120.5 MB / 24 GB = 0.5%，未顶上限；命令输出未命中降级 / OOM 关键词
- 档案：`reports/peaks/immich_qc.json`
- 口径限制（如实登记）：本次峰值监控挂在**输出侧复核链**上；正片渲染在上一轮已完成，未挂 `resource_peaks` 分阶段监控，渲染阶段峰值无档案。渲染侧证据为 `render.log` 真实帧数与 worker 记录（总帧 2,685 + 片尾 176 = 2,861，与成片 nb_frames 一致）。

## 八、抽帧核验

- 抽帧点：2 / 20 / 35 / 50 / 65 / 80 / 90 / 93 s，共 8 帧（`story/immich/qc/qc_immich_*.jpg`）。
- 视觉模型核验：8 帧均无文字溢出卡边、无排版错位、无黑屏；右下角水印 `jerrychen2001` 可见。
- 首轮判读在 50 s 帧报「底部字幕被卡片遮挡」，遂对该帧做 y=1400–1920 区间 2 倍放大复核（`qc/frames_r2/f_50_low.png`）：放大后确认**卡片底边与字幕框之间存在背景间隔，未发生重叠或遮挡**，首轮判断为缩略图尺度下的误判，已排除。
- `blackdetect`（d=0.5，pix_th=0.10）未检出任何黑段。

## 九、结论

- 成片：`/Volumes/PSSD/抖音视频/story/immich/douyin_final.mp4`（1080x1920 / 30 fps / 95.36 s / 12.13 MB / 2,861 帧）。
- 验收结论：**通过**。参数合同 check 与 diff 均 FAIL 0、exit 0（仅 2 项探索级 WARN，且均为既有观测口径或固定片尾结构）；负控 14/14 达期望、素材指纹 6/6 一致；扩展自测 61/61；观测四口径 overall=OK；抽帧 8 帧无排版与黑屏问题；事实口径全部逐项核验留档。
- 登记事项：跨选题帧数变更 `CE-20261003-01-render-window-frames` 已登记放行。
- 待办（不在本次范围）：发布环节未执行（无发布脚本）；本次未采集渲染阶段峰值档案，后续如重渲建议以 `resource_peaks.py monitor` 包裹渲染命令补齐。
*（内容由AI生成，仅供参考）*
