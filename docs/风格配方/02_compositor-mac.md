# 02_compositor-mac · 开源修图软件评测（V-BASE 视觉配方）

文件：`story/compositor-mac`（成片 `douyin_final.mp4`）
规格：1080×1920 / 30fps / 总时长 77.99s / 6 场景 6 行配音

## 性能（motion_audit 实测 2026-10-10，480×270 抽帧）
- 运动面积 0.29%（相邻帧变化 >12 像素占比均值）
- 静止帧对 69.6% —— 中等偏静，卡片切换为主
- 跳变 33；抽帧耗时 1.25ms/帧；确定性 SKIP

## 视觉配方（V-BASE 默认层，v1.12.0 口径）
- 渲染超采样默认启用（storyctl `--resolution portrait-4k` 2160×3840 → 归一化 1080×1920）
- 视觉提亮：背景网点阵列/十字网格/暖冷光晕亮度密度抬升，深底亮像素占比 ≥4%
- 该 story 是 V-BASE 默认视觉基座落点模板（compositor-mac/build_html.py 模板口径）

## 节奏配方
- beat：行级未参数化（默认 3 常态档）；emotion 未设置 → 配乐默认「温和推进」档
- BGM：`Karma - Michael Ramir C. [mixkit 1183]`
- 建议：如需更强的评测节奏感，可显式给 lines 补 beat（2–5），走 rhythm.py 参数化

## 管线
- 渲染：HyperFrames 6 个 `.scene.clip`（功能清单卡片 + 界面截图/演示动图）
- 视觉：V-BASE 默认（本 story 即模板源）
- 配音：Qwen3-TTS 本地；质检：canon_guard + frame_audit + motion_audit

## 母题动画
- 场景 0：痛点开场（Photoshop 贵 / GIMP 不顺手）→ 软件名 logo 入场
- 场景 1：图层/文件夹嵌套、混合模式功能卡（与 PS 一致性对比）
- 场景 2：调整层（色阶/曲线/曝光/渐变映射）与 GPU 渲染特性卡
- 场景 3：选框/套索/魔棒/对象工具 Tab 切换交互演示
- 场景 4：PSD/PSB 兼容性与转换预告
- 场景 5：MIT 协议 + macOS 26.5/Xcode 26 要求收尾

## 运动量返修建议
- 0.29% 偏静：功能演示卡可加「工具切换高亮」局部动画（±1–2% 运动增量）；
- 跳变 33：截图/动图切换帧复核，排除整屏闪白。

## 短板（诚实留痕）
- 行级节奏未参数化：无法表达评测中段「高潮功能」的情绪推进；
  返修方向：为 2–3 段补 beat=4/5 后复跑 motion_audit。
