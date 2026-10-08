# 科技资讯类视频模板 — design.md

> E9 新增模板（P1）。全部设计变量来自共享 token 层，不新增自定义色值。

## 复用资产（共享，不重复落盘）

| 资产 | 路径 | 许可 |
|------|------|------|
| 色阶语义 | `../_shared/tokens/radix-*-dark.css`（Radix Colors 3.0.0） | MIT |
| 尺寸/圆角/阴影 | `../_shared/tokens/open-props-{sizes,shadows,borders}.min.css`（Open Props 1.7.23） | MIT |
| 动效运行时 | `../_shared/vendor/gsap.min.js` + `CustomEase.min.js` | MIT（GSAP 标准许可） |

来源归档：`/Volumes/PSSD/RAG知识库/sources/网页提升质量/{Radix-Colors,Open-Props,shadcn-ui}/项目资料.md`

## 色板（Radix 语义槽位 → 科技青）

| 槽位 | 变量 | 取值 | 用途 |
|------|------|------|------|
| 背景 | `--slate-1` | `#111113` | 画布底色 |
| 卡片 | `--slate-3` | `#212225` | Card / 徽章底 |
| 边框 | `--slate-6` | `#363a3f` | 1px 描边、细线分隔 |
| 主文字 | `--slate-12` | `#edeef0` | 标题 |
| 次文字 | `--slate-11` | `#b0b4ba` | 副标题 / 元信息 |
| 实心主色 | `--cyan-9` | `#00a2c7` | 徽章圆点、装饰段、CTA |
| 强调文字 | `--cyan-11` | `#4ccce6` | 数据高亮 |

换品牌色只需替换 `--primary` 指向的 Radix 色阶（如 `--violet-9`），其余不动。

## 字体

- 标题：`"PingFang SC"` weight 900，字号 112px（intro）/ 52px（outro 正文）
- 副标题：weight 500，46px
- 数据/元信息：weight 400-500，24-26px

## 动效签名（P1 配方，与 p1-enhanced.html 一致）

| 语义 | 参数 | 来源 |
|------|------|------|
| 元素入场（Anime.js 翻译） | stagger `0.08s`（原 `stagger(80)`）；outQuad → `power1.out` | Anime.js |
| 卡片入场（Motion 翻译） | `y:40→0 / 0.6s / power3.out`；chip stagger `0.12s` | Motion |
| 标题惯性（Lenis 借鉴） | `y:120→0 / 1.0s / expo.out` | Lenis |
| 转场标准曲线 | `cubic-bezier(.2,.8,.2,1)` → CustomEase `vtStandard` | View Transitions API |
| 分镜时长 | 240-400ms（网页）→ `0.65s`（竖屏放大 1.5-2 倍） | View Transitions API |

## 转场三语义

- **Slide**：全屏色条 `scaleX: 1→0`，`transform-origin: left`，0.65s
- **Morph**：CSS 印记从画面左上放大（scale 3）位移至右上角，1.0s `expo.out`
- **Fade**：尾段 0.5s 交叠层（`opacity → 0.16`）；outro 开场由叠化反向进入

## 视频规范

- 画布 1080x1920（竖屏 9:16），30fps
- 时长：intro 5s / outro 4s
- 零外部素材依赖（底纹为纯 CSS 网格），仅需共享 token 与 GSAP

## 不做

- 不用位图背景（资讯类以文字为主，避免压缩糊化）
- 不在时间线上插值颜色与阴影（HyperFrames 动画属性白名单外的属性一律静态）
- 不在同一帧放超过两行正文
