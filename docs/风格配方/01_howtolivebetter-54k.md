# 01_howtolivebetter-54k · 高性价比人生指南（节奏+配乐配方）

文件：`story/howtolivebetter-54k`（成片 `douyin.mp4` / 配乐版 `douyin_music_bpm.mp4`）
规格：1080×1920 / 30fps / 总时长 84.4s / 6 场景 6 行配音（行级节奏已参数化）

## 性能（motion_audit 实测 2026-10-10，480×270 抽帧）
- 运动面积 0.28%（相邻帧变化 >12 像素占比均值）
- 静止帧对 78.1%（diffs<0.05% 占比）——偏静，适合「讲解+卡片」型内容
- 跳变 42（峰值/中位数 >6 且峰值 >3%）；多为有意节拍闪（结论见 qa.md）
- 抽帧耗时 0.72ms/帧；确定性 SKIP（ffmpeg 解码链路非逐字节确定）

## 节奏配方
- beat 分布：[2,3,3,4,4,5]，首段冷静陈述 → 末段爆发收尾（1–5 情绪强度）
- emotion: `thoughtful` → 配乐档位 `mild-progress`（闪避默认 8dB）
- BGM：`Karma - Michael Ramir C. [mixkit 1183]`（选曲模式）
- BPM 网格模式（v1.19.0 新增，本卡同款验证样本）：
  - 128 BPM / 八分音符 0.2344s / 网格零点 0.028s / D 小调 i–VI–III–VII 和声
  - 逐段按 beat 换配器：1-2=sine 长音、3=triangle、4=saw+低通、5=square+鼓
  - 逐段响度对齐 -26 LUFS → 整体 loudnorm I=-19/TP=-1.5/LRA=11
  - 实测：闪避深度 8.0dB、旁白保持 |Δ|=0.2 LU、削波 0

## 管线
- 渲染：HyperFrames（`index.html` 6 个 `.scene.clip` 卡片场景）
- 视觉：V-BASE 默认基座（超采样 + 视觉提亮，v1.12.0 口径）
- 配音：Qwen3-TTS 本地模型（御姐参考音）+ 节奏参数（beat/pause 由 rhythm.py 解析）
- 配乐：`build_music.py`（选曲模式或 `--bpm-grid` 模式）
- 质检：canon_guard A0–A7 + frame_audit + motion_audit + music_qc

## 母题动画
- 场景 0 开场：项目星标数字（GitHub 54k star）→ 卡片入场
- 场景 1–2：证据分级表（A 级 438 条 / B 级 179 条）、来源卡严格性清单
- 场景 3：备选单 vs 任务清单的对比强调
- 场景 4：官方声明（无代币）警示卡片
- 场景 5：收尾清单沉淀（「先存下来」C 卡片）

## 运动量返修建议
- 静止帧对 78.1% 偏高：可给「卡片强调」增加 5–10% 的局部位移动画（非全屏闪烁），
  目标降至 55–65%；跳变 42 需逐帧复核：若为节拍闪可保留，若为穿帮需修。

## 短板（诚实留痕）
- 无确定性证据：ffmpeg 抽帧链路非逐字节确定，qa.json 中 deterministic 恒 SKIP；
  如需确定性需在渲染端（HTML 同参两版）比对，非抽帧链路能力。
- BPM 模式非配音段（lines 间隙）无音符（-65 LUFS 静音），节奏仅在配音段内推进；
  如需全片连续铺底需扩展段表覆盖间隙。
