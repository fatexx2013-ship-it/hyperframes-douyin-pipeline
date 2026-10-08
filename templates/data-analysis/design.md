# 数据分析类视频模板 — design.md

> E9 新增模板（P1）。全部设计变量来自共享 token 层，不新增自定义色值。

## 复用资产（共享，不重复落盘）

| 资产 | 路径 | 许可 |
|------|------|------|
| 色阶语义 | `../_shared/tokens/radix-*-dark.css`（Radix Colors 3.0.0） | MIT |
| 尺寸/圆角/阴影 | `../_shared/tokens/open-props-{sizes,shadows,borders}.min.css`（Open Props 1.7.23） | MIT |
| 动效运行时 | `../_shared/vendor/gsap.min.js` + `CustomEase.min.js` | MIT（GSAP 标准许可） |

来源归档：`/Volumes/PSSD/RAG知识库/sources/网页提升质量/{Radix-Colors,Open-Props,shadcn-ui}/项目资料.md`

## 色板（Radix 语义槽位 → 数据紫）

| 槽位 | 变量 | 取值 | 用途 |
|------|------|------|------|
| 背景 | `--slate-1` | `#111113` | 画布底色 |
| 卡片 | `--slate-3` | `#212225` | 数据卡底 |
| 轨道 | `--slate-a4` | 半透明层 | 数据条未填充部分 |
| 边框 | `--slate-6` | `#363a3f` | 1px 描边、细线分隔 |
| 主文字 | `--slate-12` | `#edeef0` | 标题 |
| 次文字 | `--slate-11` | `#b0b4ba` | 标签 / 口径说明 |
| 实心主色 | `--violet-9` | 见 token 文件 | 数据条填充 |
| 强调文字 | `--violet-11` | 见 token 文件 | 数值 |

与科技资讯模板的唯一差异是 `--primary` 指向的 Radix 色阶不同，其余 token 与动效配方完全共享。

## 字体

- 标题：`"PingFang SC"` weight 900，112px
- 数据标签：weight 500，30px
- 数值：weight 700，40px（用强调色，保证小屏可读）
- 口径说明：weight 400，24px

## 动效签名（P1 配方）

| 语义 | 参数 | 来源 |
|------|------|------|
| 数据条生长 | `scaleX: 0 → data-w`，`0.8s / power3.out`，`stagger 0.12s` | Motion / Anime.js 翻译 |
| 数值浮现 | `y:12→0 / opacity 0→1 / 0.4s / power1.out`，同 `stagger 0.12s` | Anime.js（outQuad） |
| 标题惯性 | `y:120→0 / 1.0s / expo.out` | Lenis |
| 卡片入场 | `y:40→0 / 0.6s / power3.out` | Motion |
| 转场标准曲线 | `cubic-bezier(.2,.8,.2,1)` → CustomEase `vtStandard` | View Transitions API |

## 转场三语义

- **Slide**：全屏色条 `scaleX: 1→0`，`transform-origin: left`，0.65s
- **Fade**：尾段 0.5s 交叠层；outro 开场反向叠化
- 本模板不含 Morph（无共享元素场景），按需在分镜间复用 Slide/Fade 即可

## 视频规范

- 画布 1080x1920（竖屏 9:16），30fps
- 时长：intro 5s / outro 4s
- 零外部素材依赖，数据值由 `data-w` 属性驱动，改数只改一处

## 不做

- 不用 Pie/3D 图表（竖屏小尺寸下辨识度低，且 HyperFrames 不做 SVG 路径补间）
- 不在时间线上插值颜色与阴影（白名单外属性一律静态）
- 不堆叠超过 3 条数据行（超过则拆分为多个分镜）
