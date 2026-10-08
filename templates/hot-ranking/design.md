---
AIGC:
    Label: "1"
    ContentProducer: 001191440300708461136T1XGW3
    ProduceID: b82594f1be8e85c02fc42784acc7d5b8_8cdb9e1eb62c11f183e7525400de85a5
    ReservedCode1: cBMSiz0cvkBztNpzyEevVne+680qWILp4kdJV0e1ROpYtLqK3+/eNvntXm/e/Zo7pO5SU+/bZAy2ztv+o5HLk+MdCuUE/VyulmaADR4aXovEowmi9NI5vS3lJRhQO1SYzlmHwzwZ0nDdUjes1YjQKWa3a0ZWv73VPzJMMhjp2DJr0SVVYSZL5m53VWk=
    ContentPropagator: 001191440300708461136T1XGW3
    PropagateID: b82594f1be8e85c02fc42784acc7d5b8_8cdb9e1eb62c11f183e7525400de85a5
    ReservedCode2: cBMSiz0cvkBztNpzyEevVne+680qWILp4kdJV0e1ROpYtLqK3+/eNvntXm/e/Zo7pO5SU+/bZAy2ztv+o5HLk+MdCuUE/VyulmaADR4aXovEowmi9NI5vS3lJRhQO1SYzlmHwzwZ0nDdUjes1YjQKWa3a0ZWv73VPzJMMhjp2DJr0SVVYSZL5m53VWk=
---





# hot-ranking / intro.html — 赤焰热力主题（Heat Red）

## 一、色标来源（真实代码参数，非人工调色）

本模板配色全部派生自 P0/P1 差异热力图的生成逻辑（`temp/build_compare.py`）：

```python
diff = ImageChops.difference(a, b).convert("L")
diff = diff.point(lambda v: min(255, int(v * 2.6)))        # 差异强度（对比增强 2.6×）
heat = Image.merge("RGB", (diff, diff * 0.35, diff * 0.15)) # 通道系数 R=1.0 / G=0.35 / B=0.15
canvas_bg = (18, 18, 20)                                    # 热力图画布底色
```

推导结论：

| 项 | 数值 |
|---|---|
| 通道系数 (R, G, B) | (1.000, 0.350, 0.150) |
| 色相 | 恒定 14.1° |
| 满强度色 | `#FF5926`（RGB 255, 89, 38；饱和度 85.1%） |
| 画布底色 | `#121214`（RGB 18, 18, 20） |

12 档色阶由该系数按强度 26/40/56/76/98/122/148/176/205/232/245/255 逐一推导：

| 档 | HEX | 档 | HEX |
|---|---|---|---|
| heat-1 | `#1A0903` | heat-7 | `#943316` |
| heat-2 | `#280E06` | heat-8 | `#B03D1A` |
| heat-3 | `#381308` | heat-9 | `#CD471E` |
| heat-4 | `#4C1A0B` | heat-10 | `#E85122` |
| heat-5 | `#62220E` | heat-11 | `#F55524` |
| heat-6 | `#7A2A12` | heat-12 | `#FF5926` |

基础层：`--heat-bg #121214` 直取画布底色；surface / surface-2 / border 为 bg 等量提亮派生（+8 / +17 / +31）。
中性层文字色沿用现有 `radix-slate-dark` 变量（带十六进制兜底），未新增中性色板。

## 二、与现有设计 token 体系的关系（不冲突）

- 色相隔离：新主题色相恒定 14.1°，现有默认主题为 slate（中性）+ cyan（≈190°）+ violet（≈255°），无重叠。
- 命名对齐：主题内以同名语义变量（`--bg-app / --card / --border-subtle / --text-primary / --primary / --primary-muted`）赋值，只换取值，不新增命名空间。
- 作用域隔离：全部规则收敛在 `html.theme-heat, body.theme-heat` 下，特异性高于 `:root`；不加 class 的模板（data-analysis / science-popularization / tech-news）完全不受影响 → 默认主题零改动。
- 文件：`_shared/tokens/theme-heat-red.css`，引用方式 `<link rel="stylesheet" href="_shared/tokens/theme-heat-red.css" />`。

## 三、适用题材

| 适配度 | 题材 | 理由 |
|---|---|---|
| ★★★ 最佳 | 数据榜单、热度排行、指数/涨跌、竞争排名 | 色阶本身就是"强度量化"语义，条形长度 + 色温双编码，红→橘红天然表达"热"、高、紧迫 |
| ★★★ | 警示/风险类、监测面板、异常告警 | 红橘色系是通用警示语汇，暗底高对比适合承载告警数字 |
| ★★☆ | 科技资讯快报、发布会要点 | 暗底 + 高饱和强调色足够科技感，但长文段落易疲劳 |
| ★★☆ | 高燃混剪卡点、游戏/赛事战报 | 强情绪色，适合快节奏；不适合温和叙事 |
| ★☆☆ 慎用 | 财经科普、教育长讲解、生活向内容 | 红色在长时段易引发紧张/负面联想，且与"safety red"语义混淆 |
| ★☆☆ 慎用 | 情感、亲子、医疗健康 | 色彩情绪与题材调性冲突 |

## 四、动效配方（沿用 P1 配方）

- 遮罩/光晕：顶部 radial 热力光晕淡入（1.2s）
- 交错入场：5 行 stagger 0.16，power3.out
- 数据条生长：`scaleX` 由 GSAP `fromTo` 接管（CSS 不预设 transform，避免 `gsap_css_transform_conflict`）
- 缓动：CustomEase `vtStandard` = 0.2,0.8,0.2,1
- 尾段：fade-out 至 0.18 交叠收尾

## 五、校验记录

- 字体：`@font-face` 显式声明 PingFang SC（400 / 600-900）与 SF Pro Display
- 资产路径：同级 `_shared/` 相对路径（避免 `invalid_parent_traversal`）
- lint：渲染前过 `hyperframes render --lint-verbose`，要求 0 error
- AIGC 标识改动后复验：`--strict` 渲染通过（0 error / 0 warning），150 帧全量成功（详见第六章）

## 六、AI 生成标识（AIGC 显式标识）

### 6.1 定位排查：交付样片画面内原本不存在「AI生成」字样

| 排查位置 | 方法 | 结论 |
|---|---|---|
| 模板 HTML/CSS | 检索 `templates/` 全量 | 仅榜单第 2 行条目名「AI 视频生成」（`<span class="row__name">`，intro.html 第 167 行，位于画面中部榜单区）与之相关，非角标元素 |
| 渲染器 | 检查 hyperframes CLI/源码 | 仅提供通用 `addWatermark`（通用水印开关）与 `labels` 参数，**无内建中文 AIGC 标识逻辑**，不会自动叠加 |
| 后期处理 | 检查渲染管线脚本 | 无文字叠加步骤；输出 MP4 元数据亦无 AIGC 文本标签 |
| 像素级验证 | 对交付样片 30 帧扫描右下/左下角安全区 | 角标区峰值亮度 32（≈ 背景 `#121214`），无任何文字像素 |

结论：用户所指右下角「AI生成」大字，**并非出自本工作流**（模板 / 渲染器 / 后期三处均无），最可能来自播放端或发布平台的 AIGC 自动标识（素材侧无法控制其样式与位置）。

应对：在画面内**主动、可控地**建立一个克制版显式标识，样式与位置完全由我们掌握，避免与平台侧标识叠加时视觉过载，同时保住合规可辨识性。

### 6.2 标识 token（`_shared/tokens/theme-heat-red.css`，作用域 `html.theme-heat`）

| token | 值 | 说明 |
|---|---|---|
| `--aigc-fg-strong` | `rgba(242,242,245,0.72)` | 胶囊主字色 |
| `--aigc-fg-soft` | `rgba(242,242,245,0.52)` | 无底字色 |
| `--aigc-dot` | `color-mix(in oklab, var(--heat-12) 34%, transparent)` | 方案 C 指示点（派生自热力满强度色） |
| `--aigc-surface` | `rgba(8,8,10,0.72)` | 胶囊底（比画布深一档） |
| `--aigc-border` | `rgba(255,255,255,0.14)` | 胶囊描边 |
| `--aigc-size` / `--aigc-tracking` | `20px` / `0.06em` | 字号（画面高度 1.04%）与字距 |
| `--aigc-inset-x` / `--aigc-inset-y` | `88px` / `96px` | 无底方案安全边距（对齐正文 88px 栅格） |

### 6.3 四种克制方案

| 方案 | 呈现 | 位置 | 字号 | 字色不透明度 | 合成色 / 对比度 | 特点 |
|---|---|---|---|---|---|---|
| a | 极简无底字 | 右下 88 / 96 | 20px / 500 | 0.52 | `#86868A` / 5.1:1 | 最轻，无任何底衬 |
| **b（默认/推荐）** | 半透明胶囊 | 右下 44 / 44 | 20px / 500 | 0.72 | `#B3B4B5` / 8.9:1 | 有底有框，最规范、最清晰，仍不抢眼 |
| c | 圆点＋文字 | 右下 88 / 96 | 20px / 500 | 0.52 | 同 A / 5.1:1 | 赤焰色指示点，与主题同源 |
| d | 左下角小字 | 左下 88 / 96 | 20px / 500 | 0.52 | 同 A / 5.1:1 | 避开右下角平台标识位，防叠字 |

改动前样片对比：原交付样片角标区峰值亮度 32（无标识）；改动后 a/c/d 峰值 134、b 峰值 180，均为低亮度轻量元素，不构成视觉焦点。

### 6.4 渲染方式（变量化，无需复制模板）

```bash
cd /Volumes/PSSD/抖音视频/templates
hyperframes render . -c hot-ranking/intro.html \
  --variables '{"aigcVariant":"b"}' -q high -f 30 --strict \
  -o ../output/samples/aigc-label-b.mp4
```

- `aigcVariant` ∈ `a|b|c|d`（默认 `b`），`aigc` 可整体替换标识文案（默认「AI生成」）
- 两种变量已登记在 `data-composition-variables`，支持 `--strict-variables` 校验

### 6.5 合规硬约束（启用状态下必须遵守；2026-09-20 起画面内角标默认关闭）

> 本节为 `aigcEnabled=true` 启用角标时必须遵守的约束，数值全部保留未改；默认关闭的原因见 6.7。

1. **不得移除、隐藏或改为不可辨识**：标识 t=3.85s 淡入后保持 100% 不透明度至结束，不参与尾段 fade-out；`z-index: 40` 高于收尾遮罩（30），保证全程可见。
2. **可读性下限**：小字对比度 ≥ 4.5:1（WCAG AA）。当前最低档（a/c/d）实测 5.1:1，仍保有安全余量；若进一步降低不透明度即视为违规。
3. **不遮挡主体**：标识仅占角落空白安全区（正文栅格 88px 外侧或 44px 内边区），不覆盖榜单、标题与数据条。

### 6.6 回滚点

改动前全量备份：`/Volumes/PSSD/抖音视频/backup_aigc_label_20260920/`
（含 `hot-ranking/intro.html`、`hot-ranking/design.md`、`_shared/tokens/theme-heat-red.css`、`samples/theme-heat-ranking-intro.baseline.mp4`；备份样片与改动前交付样片 sha256 一致，可直接回滚）

### 6.7 默认关闭（2026-09-20 决策）

- **背景**：成片右下角「AI生成」大字经溯源确认为交付平台转码强制烧录（容器含 `TAG:AIGC` 隐式标识，`encoder=Lavf59.17.102`，与本机渲染 `Lavf63.1.101` 不同源），素材侧无法去除；模板自制角标与平台标识位置重叠，形成重复叠加。
- **决策**：保留模板角标代码与 token 作为可配置能力，但**默认不渲染**——`aigcEnabled` 默认 `false`；`.aigc-label` 默认 `display:none`，仅当脚本判定启用时加 `.is-on`（`display:inline-flex`）并挂入 t=3.85s 淡入动画。
- **不变项**：`design.md` 头部 AIGC 合规元数据段、文件隐式标识（`TAG:AIGC`）与 `_shared/tokens` 全部数值均保留，未做删改。
- **本次回滚点**：`/Volumes/PSSD/抖音视频/backup_aigc_disable_20260920/`（含改动前 `hot-ranking/intro.html`、`hot-ranking/design.md`、`_shared/tokens/theme-heat-red.css`；已通过 shasum 校验一致）
- **子样片**：`output/samples/aigc-label-b.mp4` 等既有样片保留，可作历史对照，不随本次改动失效。

---

## 7. 画中画叠加区（2026-09-22 合入）

### 7.1 来源与目标

把成片 `output/浏览器里开出军用驾驶舱_1790040240/build_html.py` 中「画面上方叠加网络下载视频素材」的做法（`.gifwrap` 区）合入本模板：保留赤焰热力配色与可动数据进度条，新增顶部画中画区，形成「红色风格 + 可动进度条 + 网络视频画中画」的出片模板。

### 7.2 结构与素材

- DOM：`.content` 首个子元素 `.pip#pip-el`，内含 `img.pip__media#pip-img` 与 `span.pip__tag#pip-tag`
- 版面：宽 100%（内容区 1080 − 88×2 = 904px）、高 600px、圆角 24px、下间距 44px
- 默认素材：`assets/pip-sample.gif`（由成片素材 `06-cockpit-ar.gif` 复制而来）；`data-alt-src="hot-ranking/assets/pip-sample.gif"` 用于渲染根取 `templates/` 时的路径回退

### 7.3 与原 gifwrap 的对应关系

| 原实现（HUD 青） | 本模板（赤焰热力） |
| --- | --- |
| 容器 `border-radius:20px` / `height:560px` | `border-radius:24px` / `height:600px` |
| 容器底色 `#04101C` | `var(--heat-1)` = #1A0903 |
| 描边青色 `--line`（16%） | `color-mix(in oklab, var(--heat-12) 26%, transparent)` |
| 无外发光 | 叠加 `var(--heat-glow)` |
| 角标 `LIVE · 实时数据`（青底深字） | `LIVE · 实时画面`（`var(--heat-12)` 底 + #1A0903 字，前置圆点） |
| 无下沿过渡 | 底部 140px 渐隐，与 `--heat-bg` 衔接 |
| 入场 `scale 1.06 → 1`，0.6s `power2.out` | 一致（0s 起）；角标 0.5s 补入 |

### 7.4 可配置变量

`pipEnabled`（boolean，默认 true；传 false 时整区不渲染，回到纯榜单版式）、`pip`（素材路径，留空用内置示例素材）、`pipLabel`（角标文案）。

### 7.5 尺寸重排

为容纳 600px 画中画区，原版面等比压缩：内容区 padding `120px 88px` → `110px 88px 96px`；标题 104px → 88px；徽章 `26px / 14px 30px` → `24px / 12px 26px`；榜单行 `26px 30px / mb 22` → `22px 30px / mb 18`；序号 `86px/46px` → `80px/44px`；条目名 34px → 32px；数值 `152px/42px` → `146px/40px`。内容总高约 1811px（画布 1920px），无溢出。

### 7.6 动画时序（总时长 5.0s 不变）

`glow 0` → `pip 0`（0.6s 缩放淡入）→ `pip 角标 0.5` → `badge 0.35` → `title 0.5` → `sep 1.0` → `rows 1.15`（stagger 0.15）→ `fills 1.7` → `values 2.1` → 榜首脉冲 `3.4` → `foot 3.65` → `aigc 3.85`（默认关闭）→ `fade 4.4`。

### 7.7 交付与回滚点

- 示例成片：`/Volumes/PSSD/抖音视频/output/samples/theme-heat-ranking-pip.mp4`（1080×1920 / 30fps / H.264 / 5.0s）
- 示例页预览图：`/Volumes/PSSD/抖音视频/output/samples/theme-heat-ranking-pip-preview.png`
- 渲染命令：项目根取 `templates/`，`hyperframes render -c hot-ranking/intro.html -o <out>.mp4`
- 改动前备份：`/Volumes/PSSD/抖音视频/backup_hot_ranking_20260922/`
- 对照样片（未含画中画）：`output/samples/theme-heat-ranking-intro.mp4`

*（内容由AI生成，仅供参考）*
*（内容由AI生成，仅供参考）*
*（内容由AI生成，仅供参考）*
