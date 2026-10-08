#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
design_ai_gate.py —— 反"AI 视觉痕迹"闸门（免费开源替代 impeccable 的视觉层）

所属产线：/Volumes/PSSD/抖音视频
规则真源：hyperframes-creative 的 house-style.md「Lazy Defaults to Question」
          + design-adherence.md（色彩/字体/一致性）
对齐口径：与 canon_guard.py / observability_anchors.py 一致
  - 退出码 0 = 通过；2 = 检出痕迹（拒绝）；1 = 用法/输入错误
  - 只做拒绝不做确认；每条命中带规则名 + 修复建议（PIPELINE G 项"拒绝须带触发规则名"）
  - 纯标准库（re + html.parser），无第三方依赖。

v2（2026-10-04）新增「渲染前模式 + 设计意图登记旁路」（只增不改，向后兼容）：
  - --mode pre      渲染前模式。当前为预留开关：不新增任何规则（GSAP 配方黑名单
                    待规则清单确认后再实现，本版禁止臆造）。
  - --registry P    读取 P 顶层 design_registry 数组做设计意图登记旁路；
                    仅当 rule 与 selector 双双匹配、且 theme_color 出现在该选择器
                    声明中（含 var(--x) 解析）时，该条不产生 blocker。
  - findings 增补 line / selector 字段（既有 rule/severity/message/fix/source/detail
    字段名与取值完全不变）。
  - 退出码收紧：目录内未找到 .html 由 2 改为 1；参数解析错误改为 1。
    （说明：旧版依赖 argparse 默认行为，解析错误以 2 退出，与"检出痕迹"撞码；
     本版重写 ArgumentParser.error 使其以 1 退出，彻底避免与 2 同码。）

v3（2026-10-05）在 v2 基础上增量改造（同样只增不改、不新增任何检测规则）：
  - --mode pre 默认只阻断 error 级；warn 级仍写入报告但不影响退出码。
  - 新增 --strict-warn（仅 --mode pre 下有效）：把 warn 级也计为阻断；
    与 --no-warn 语义冲突，二者同传按用法错误退出 1。
  - registry 校验改为 fail-closed：design_registry 条目缺 purpose / approved_by
    （含字段缺失、空串、纯空白）即视为无效登记，整次运行退出 1，
    报告逐条列出无效条目与缺失字段；rule/selector/theme_color 的匹配语义不变。
  - 修 GRADIENT_TEXT_RE 第三分支：去掉误粘的 \n（该分支原先实为
    "\n-webkit-text-fill-color..."，换行参与匹配，导致只有 text-fill-color、
    没有 background-clip 的渐变文字被漏检）。
  - 删除零调用点的死规则 BAD_HEX / MULTI_BG；GRAD_NEON_PAIR 在 hex 循环内
    实装为 warn 级（同一渐变函数实参内同时出现青与紫即命中）。

用法
----
  python3 scripts/design_ai_gate.py <composition.html> [--json-out report.json]
  python3 scripts/design_ai_gate.py --dir <project_dir>     # 递归扫描 .html
  python3 scripts/design_ai_gate.py <html> --mode pre [--registry script.json]
  python3 scripts/design_ai_gate.py <html> --mode pre --strict-warn [--registry p]
  --no-warn：只把 error 级当拒绝，warn 仅提示（与 --strict-warn 互斥）

返回：0=通过；2=命中（拒绝）；1=用法/输入错误
"""

import argparse
import html.parser
import json
import os
import re
import sys

# ---------------------------------------------------------------------------
# 规则：id -> (severity, message, fix)
# ---------------------------------------------------------------------------
RULES = {
    "GRADIENT_TEXT": ("error",
        "渐变文字（background-clip:text + gradient），首要 AI 视觉痕迹",
        "改用纯色 + 字号/字重层级；真需渐变必须写明设计意图且用主题色"),
    "NEON_CYAN": ("warn",
        "检测到默认霓虹青（#00ffff 一类）而非主题点缀",
        "转用 design.md 声明的 accent（如 Swiss Pulse 的 #0066FF），避免 00ffff"),
    "NEON_PURPLE": ("warn",
        "检测到默认霓虹紫（#a855f7 / #7c3aed 一类）",
        "用单主色 + 中性微调，紫色只做装饰点缀不做主色"),
    "BARE_BLACK_BG": ("warn",
        "使用纯 #000 作为背景，未向主色 tint",
        "背景向主色色温偏移（加 1-3% 主色）"),
    "PURE_WHITE_BG": ("warn",
        "使用纯 #fff 作为背景，未向主色 tint",
        "背景用暖白/冷白（如 #FAFAF8 或主色 1-2% 底色）"),
    "BANNED_FONT": ("warn",
        "使用违禁/AI 兜底字体",
        "替换为 Inter / Space Grotesk 或 design.md 声明字体"),
    "CARD_GRID_MATRIX": ("warn",
        "3+ 个尺寸一致、圆角一致的卡片，是 AI 卡片阵列默认",
        "打破同构：变化尺寸层级，做一主两辅，让眼有落点"),
    "GRAD_NEON_PAIR": ("warn",
        "渐变中同时出现青+紫，是 AI 科技默认渐变",
        "用单主色透明度渐变，不要紫青对"),
    # S1-a 提交③：GSAP 配方黑名单（warn 常驻，不阻断；裁决见 proposals 回执）
    # 判据边界（防后来者误扩）：from/fromTo 的 vars 含 scale 单独命中 109 处，
    # 全是 .vis 入场 scale:1.06 收敛到自然态，同源对照 19-47-58 vs 05-09-09
    # 最低 PSNR 55.49dB 证明安全，且入判据会让 11 同簇全违「一行不改」——
    # 故 from-scale 单独不入判据，只截「from-scale 与 to-yoyo-repeat 同元素交集」。
    "GSAP_REPEAT_YOYO_SCALE": ("warn",
        "GSAP 入场 scale 与 to yoyo+repeat 组合：HyperFrames 逐帧 seek 对 repeat+yoyo 末态不保证，"
        "元素可能卡在缩放中间态（同模板族呼吸动画属已知刻意设计，pre 不阻断，渲染侧 A0/A3 做事实校验）",
        "循环动画去掉 scale（改 y/opacity）；或把入场 from-scale 改为纯位移/透明度"),
}
# v3：BAD_HEX / MULTI_BG 经确认在 scan() 中零调用点（死规则），已删除。

# 渐变文字专用（背景渐变在 hyperframes 中是合法装饰，不算 AI 痕迹）
# v3：第三分支去掉误粘的 \n——该分支是独立备选项（text-fill-color 单独出现也算），
#     换行参与匹配会让「只有 -webkit-text-fill-color:transparent、没有 background-clip」
#     的渐变文字漏检。
GRADIENT_TEXT_RE = re.compile(
    r"-webkit-background-clip\s*:\s*text|background-clip\s*:\s*text|"
    r"-webkit-text-fill-color\s*:\s*transparent",
    re.IGNORECASE,
)
HEX_RE = re.compile(r"#[0-9a-fA-F]{3,8}\b")
# 青/紫默认集合（含常见变体）
CYAN_SET = {"00ffff", "0ff", "00e5ff", "1de9b6", "40e0d0", "00eaff"}
PURPLE_SET = {"800080", "a855f7", "7c3aed", "c084fc", "8b5cf6", "a78bfa",
              "9333ea", "9f7aea", "bb6bd9"}
BLACK_SET = {"000", "000000"}
WHITE_SET = {"fff", "ffffff"}
# 渐变里同时出现青与紫 → 用两组 hex 判断
BANNED_FONT_RE = re.compile(
    r"font-family\s*:\s*[^;]*(comic\s*sans|times\s*new\s*roman|arial|tahoma)",
    re.IGNORECASE,
)
RADIUS_RE = re.compile(r"border-radius\s*:\s*([0-9.]+)px")
# v3：渐变函数实参切取（GRAD_NEON_PAIR 实装用；按括号配平，避免被 var(--x) 的 ')' 截断）
GRADIENT_FN_RE = re.compile(
    r"(?:repeating-)?(?:linear|radial|conic)-gradient\s*\(", re.IGNORECASE)


def _gradient_spans(text):
    """返回 [(实参起点, 实参终点, 实参, 函数起点), ...]（按括号配平截取）。"""
    spans = []
    for m in GRADIENT_FN_RE.finditer(text):
        i = m.end()  # 已越过 '('
        depth = 1
        while i < len(text) and depth:
            ch = text[i]
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
                if depth == 0:
                    break
            i += 1
        spans.append((m.end(), i, text[m.end():i], m.start()))
    return spans


def _span_index(spans, idx):
    """下标 idx 落在哪个渐变实参内；不在任何渐变内返回 None。"""
    for n, (start, end, _body, _at) in enumerate(spans):
        if start <= idx < end:
            return n
    return None

# S1-a 提交③：GSAP 配方黑名单检测（仅 --mode pre 下由 scan() 调用）
# 匹配 tl.from/.fromTo/.to("selector", { vars })；vars 内不含 }，可直接跨行
GSAP_CALL_RE = re.compile(
    r"\.(?P<kind>from|fromTo|to)\s*\(\s*(?:\"(?P<sel>[^\"]*)\"|'(?P<sel2>[^']*)')"
    r"\s*,\s*\{(?P<vars>[^}]*)\}")
GSAP_YOYO_RE = re.compile(r"yoyo\s*:\s*true")
GSAP_REPEAT_RE = re.compile(r"repeat\s*:")
GSAP_SCALE_RE = re.compile(r"(?:^|[\s,;{])scale(?:X|Y)?\s*:")


# v2 新增：CSS 规则块 / 自定义属性（用于 line + selector 定位与 var() 解析）
CSS_BLOCK_RE = re.compile(r"([^{}]+)\{([^{}]*)\}", re.DOTALL)
CSS_VAR_DEF_RE = re.compile(r"(--[A-Za-z0-9_-]+)\s*:\s*(#[0-9a-fA-F]{3,8})")
CSS_VAR_USE_RE = re.compile(r"var\(\s*(--[A-Za-z0-9_-]+)")


class _Extractor(html.parser.HTMLParser):
    """抽取内联 style 文本 + 统计卡片圆角。"""

    def __init__(self):
        super().__init__()
        self.inline_styles = []
        self.card_count = 0
        self.card_radii = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        style = attrs.get("style", "")
        if style:
            self.inline_styles.append(style)
        cls = (attrs.get("class", "") or "").lower()
        if tag == "div" and ("card" in cls or "panel" in cls):
            self.card_count += 1
            m = RADIUS_RE.search(style)
            if m:
                self.card_radii.append(m.group(1))

    def handle_data(self, data):
        # 收集 <style> 块内容（handle_data 会拿到 style 标签内的 CSS 文本）
        self.inline_styles.append(data)

    def css_radii(self):
        """从收集到的所有 style 文本中提取全部圆角值（内联 + CSS 块）。"""
        radii = []
        for chunk in self.inline_styles:
            radii.extend(RADIUS_RE.findall(chunk))
        return radii


# ---------------------------------------------------------------------------
# v2 新增辅助：行号 / CSS 选择器定位 / design_registry 旁路
# ---------------------------------------------------------------------------
def _line_of(text, idx):
    """返回字符下标 idx 所在的 1-based 行号。"""
    return text.count("\n", 0, idx) + 1


def _css_blocks(text):
    """返回 [(body_start, body_end, selector, body), ...]，用于把命中位置映射到选择器。"""
    blocks = []
    for m in CSS_BLOCK_RE.finditer(text):
        blocks.append((m.start(2), m.end(2), m.group(1).strip(), m.group(2)))
    return blocks


def _css_context(blocks, idx):
    """返回命中下标 idx 所属的 (selector, body)；无法定位时返回 (None, "")。"""
    for start, end, sel, body in blocks:
        if start <= idx <= end:
            return sel, body
    return None, ""


def _var_defs(text):
    """收集文档内的自定义属性定义：--name -> hex（小写、去 #）。"""
    defs = {}
    for m in CSS_VAR_DEF_RE.finditer(text):
        defs[m.group(1)] = m.group(2).lower().lstrip("#")
    return defs


def _norm_hex(value):
    return (value or "").strip().lower().lstrip("#")


def _block_declares_color(body, hexv, defs):
    """判断某选择器声明块内是否出现指定颜色（含 var(--x) 解析）。"""
    target = _norm_hex(hexv)
    if not target:
        return False
    for h in HEX_RE.findall(body):
        if _norm_hex(h) == target:
            return True
    for name in CSS_VAR_USE_RE.findall(body):
        if defs.get(name) == target:
            return True
    return False


def _sel_match(hit_selector, registry_selector):
    """选择器匹配：整体相等，或逗号分组后存在交集（如 '.a' vs '.a, .b'）。"""
    if not hit_selector or not registry_selector:
        return False

    def _parts(s):
        return {p.strip() for p in s.split(",") if p.strip()}

    a, b = _parts(hit_selector), _parts(registry_selector)
    return bool(a & b)


def _registry_waive(rule_id, selector, body, registry, defs):
    """命中是否被 design_registry 登记放行。

    放行条件（须同时满足）：
      1) 登记条目的 rule 与命中 rule 相同；
      2) 登记条目的 selector 与命中处所属选择器匹配；
      3) 登记条目的 theme_color 出现在该选择器声明中（含 var(--x) 解析）。
    选择器无法解析（如内联 style 里的渐变）时不放行——见报告中的范围说明。
    """
    if not registry:
        return False
    for ent in registry:
        if not isinstance(ent, dict):
            continue
        if (ent.get("rule") or "").strip() != rule_id:
            continue
        if not _sel_match(selector, (ent.get("selector") or "").strip()):
            continue
        if _block_declares_color(body, ent.get("theme_color"), defs):
            return True
    return False


# v3：fail-closed 登记校验——这两项缺失（含空串/纯空白）即整次运行判无效
REQUIRED_REGISTRY_FIELDS = ("purpose", "approved_by")


def _registry_invalid_entries(entries):
    """逐条校验 design_registry：返回无效条目清单（含缺失字段），空列表表示全部有效。"""
    invalid = []
    for i, ent in enumerate(entries):
        if not isinstance(ent, dict):
            invalid.append({"index": i, "rule": None, "selector": None,
                            "missing": ["<条目不是 JSON 对象>"]})
            continue
        missing = [k for k in REQUIRED_REGISTRY_FIELDS
                   if not isinstance(ent.get(k), str) or not ent.get(k).strip()]
        if missing:
            invalid.append({"index": i,
                            "rule": ent.get("rule"),
                            "selector": ent.get("selector"),
                            "missing": missing})
    return invalid


def _load_registry(path):
    """读取 --registry 指向的 JSON；返回 (entries, error_msg, invalid_entries)。"""
    if not os.path.isfile(path):
        return None, f"registry 文件不存在：{path}", []
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except Exception as e:  # noqa: BLE001
        return None, f"registry 解析失败 {path}: {e}", []
    if not isinstance(data, dict):
        return None, f"registry 顶层必须是 JSON 对象：{path}", []
    entries = data.get("design_registry")
    if entries is None:
        return [], None, []
    if not isinstance(entries, list):
        return None, "design_registry 必须是数组", []
    return entries, None, _registry_invalid_entries(entries)


def _hit(rule_id, src, detail="", line=None, selector=None):
    sev, msg, fix = RULES[rule_id]
    return {"rule": rule_id, "severity": sev, "message": msg,
            "fix": fix, "source": src, "detail": detail,
            "line": line, "selector": selector}


# ---------------------------------------------------------------------------
# S1-a 提交③：GSAP 配方黑名单检测器（仅 --mode pre）
# ---------------------------------------------------------------------------
def _gsap_combo_findings(text, src):
    """「from-scale 与 to-yoyo-repeat 同元素交集」检测。

    两遍扫描 GSAP_CALL_RE：
      - from/fromTo 的 vars 含 scale       → 入 from_scale 字典
      - to 的 vars 同时含 yoyo:true + repeat → 入 to_yoyo 字典
    同一选择器同时出现在两字典即命中。warn 级，不阻断（裁决 (a)）。
    返回 (findings, 汇总计数)；汇总计数供报告固定字段留档。
    """
    from_scale, to_yoyo = {}, {}
    for m in GSAP_CALL_RE.finditer(text):
        kind = m.group("kind")
        sel = m.group("sel") or m.group("sel2")
        if not sel:
            continue
        vars_body = m.group("vars")
        if kind in ("from", "fromTo"):
            if GSAP_SCALE_RE.search(vars_body):
                from_scale.setdefault(sel, []).append(m)
        elif kind == "to":
            if GSAP_YOYO_RE.search(vars_body) and GSAP_REPEAT_RE.search(vars_body):
                to_yoyo.setdefault(sel, []).append(m)
    combo = [s for s in from_scale if s in to_yoyo]
    findings = []
    for sel in combo:
        # 行号取危险的那条 to-yoyo-repeat 调用
        line = _line_of(text, to_yoyo[sel][0].start())
        findings.append(_hit("GSAP_REPEAT_YOYO_SCALE", src,
                             detail="from-scale 入场 + to yoyo+repeat 组合",
                             line=line, selector=sel))
    return findings, len(combo)


def _gsap_sweep(text):
    """单文件 GSAP 黑名单扫描，返回 (命中数, 命中选择器列表)。

    供报告固定字段与逐轮比对使用；不做规则判定，不产生 finding。
    """
    from_scale, to_yoyo = set(), set()
    for m in GSAP_CALL_RE.finditer(text):
        sel = m.group("sel") or m.group("sel2")
        if not sel:
            continue
        vars_body = m.group("vars")
        if m.group("kind") in ("from", "fromTo"):
            if GSAP_SCALE_RE.search(vars_body):
                from_scale.add(sel)
        elif m.group("kind") == "to":
            if GSAP_YOYO_RE.search(vars_body) and GSAP_REPEAT_RE.search(vars_body):
                to_yoyo.add(sel)
    combo = sorted(from_scale & to_yoyo)
    return len(combo), combo


def _find_spec(html_path):
    """沿同目录向上找 frame.md / design.md / DESIGN.md，返回存在的第一个（与 hyperframes 优先级一致）。"""
    d = os.path.dirname(os.path.abspath(html_path))
    for name in ("frame.md", "design.md", "DESIGN.md"):
        p = os.path.join(d, name)
        if os.path.isfile(p):
            return p
    return None


def _extract_palette(spec_path):
    """从 spec 提取 frontmatter colors 区段中的所有 hex，返回归一化小写集合。"""
    palette = set()
    if not spec_path:
        return palette
    try:
        with open(spec_path, encoding="utf-8") as fh:
            content = fh.read()
    except Exception:  # noqa: BLE001
        return palette
    # 只取 frontmatter（--- 之间）里的 colors 块，避免正文误吸
    fm = re.match(r"\A---\s*\n(.*?)\n---", content, re.DOTALL)
    region = fm.group(1) if fm else content[:4000]
    for hexv in HEX_RE.findall(region):
        palette.add(hexv.lower().strip("#"))
    return palette


def scan(text, src, findings, palette, registry=None, waived=None,
         pre=False):
    """palette：已声明/允许的 hex 集合（来自 design.md/frame.md），命中声明色不算痕迹。

    registry：design_registry 条目列表（v2 旁路）；waived：被旁路放行的命中收集器。
    pre=True 时叠加 GSAP 配方黑名单扫描。
    """
    if waived is None:
        waived = []
    blocks = _css_blocks(text)
    defs = _var_defs(text)
    # v3：GRAD_NEON_PAIR 用——先在 hex 循环里按渐变函数分组累计颜色，循环后再判定
    grad_spans = _gradient_spans(text)
    grad_colors = {}

    # 1. 渐变文字（background-clip:text 才算；背景渐变合法）
    #    与旧版一致：每文件最多一条；v2 仅补充 line/selector 与登记旁路
    m = GRADIENT_TEXT_RE.search(text)
    if m:
        sel, body = _css_context(blocks, m.start())
        hit = _hit("GRADIENT_TEXT", src, line=_line_of(text, m.start()),
                   selector=sel)
        if _registry_waive("GRADIENT_TEXT", sel, body, registry, defs):
            waived.append(hit)
        else:
            findings.append(hit)
    # 2. 违禁字体
    for m in BANNED_FONT_RE.finditer(text):
        sel, _ = _css_context(blocks, m.start())
        findings.append(_hit("BANNED_FONT", src, f"字体 {m.group(1).strip()}",
                             line=_line_of(text, m.start()), selector=sel))
    # 3. 颜色痕迹：未声明的 AI 默认色才报；已声明视为有意设计
    for m in HEX_RE.finditer(text):
        hexv = m.group(0)
        h = hexv.lower().strip("#")
        if h in palette:
            continue  # 设计文档里声明过的颜色，不算痕迹
        # v3：把该 hex 归到它所处的渐变函数（GRAD_NEON_PAIR 判定用）
        gi = _span_index(grad_spans, m.start())
        if gi is not None:
            grad_colors.setdefault(gi, set()).add(h)
        sel, body = _css_context(blocks, m.start())
        if h in CYAN_SET:
            rid = "NEON_CYAN"
        elif h in PURPLE_SET:
            rid = "NEON_PURPLE"
        elif h in BLACK_SET:
            rid = "BARE_BLACK_BG"
        elif h in WHITE_SET:
            rid = "PURE_WHITE_BG"
        else:
            continue
        hit = _hit(rid, src, hexv, line=_line_of(text, m.start()), selector=sel)
        if _registry_waive(rid, sel, body, registry, defs):
            waived.append(hit)
        else:
            findings.append(hit)
    # 3b. GRAD_NEON_PAIR（v3 实装，warn 级）：同一个渐变函数实参内同时出现青与紫。
    #     只统计未被 design.md/frame.md 声明的颜色，与上面颜色规则口径一致；
    #     每个渐变函数最多产生一条命中。
    for gi in sorted(grad_colors):
        cols = grad_colors[gi]
        if not (cols & CYAN_SET) or not (cols & PURPLE_SET):
            continue
        at = grad_spans[gi][0]
        sel, body = _css_context(blocks, at)
        pair = "/".join(sorted(cols & (CYAN_SET | PURPLE_SET)))
        hit = _hit("GRAD_NEON_PAIR", src, f"渐变含青紫对 {pair}",
                   line=_line_of(text, at), selector=sel)
        if _registry_waive("GRAD_NEON_PAIR", sel, body, registry, defs):
            waived.append(hit)
        else:
            findings.append(hit)
    # 4) 卡片阵列（圆角一致性判定；网格/纯背景不算）
    p = _Extractor()
    p.feed(text)
    radii = p.css_radii()
    if p.card_count >= 3 and len(radii) >= 3 and len(set(radii)) <= 1:
        findings.append(_hit("CARD_GRID_MATRIX", src,
                             f"{p.card_count} 卡片，圆角 {sorted(set(radii))}"))

    # --- GSAP 配方黑名单（S1-a 提交③，仅 pre 模式）---
    if pre:
        gsap_findings, _ = _gsap_combo_findings(text, src)
        findings.extend(gsap_findings)


class _Parser(argparse.ArgumentParser):
    """v2：参数解析错误以 1 退出，避免与「检出痕迹」的 2 撞码。"""

    def error(self, message):
        self.print_usage(sys.stderr)
        print(f"{self.prog}: error: {message}", file=sys.stderr)
        sys.exit(1)


def main(argv=None):
    args = argv if argv is not None else sys.argv[1:]
    ap = _Parser(description="反 AI 视觉痕迹门禁")
    ap.add_argument("target", help="HTML 文件或 --dir 目录")
    ap.add_argument("--dir", action="store_true", help="递归扫描目录下 .html")
    ap.add_argument("--json-out", default=None, help="写 JSON 报告")
    ap.add_argument("--no-warn", action="store_true",
                    help="只把 error 级当作拒绝，warn 仅提示")
    ap.add_argument("--mode", choices=["pre"], default=None,
                    help="渲染前模式（pre）；不传则与旧行为一致（当前 pre 未新增规则）")
    ap.add_argument("--registry", default=None,
                    help="设计意图登记文件（script.json，读顶层 design_registry）")
    ap.add_argument("--strict-warn", action="store_true",
                    help="仅与 --mode pre 搭配：把 warn 级也计为阻断")
    a = ap.parse_args(args)

    if a.strict_warn and a.mode != "pre":
        print("错误：--strict-warn 仅适用于 --mode pre", file=sys.stderr)
        return 1
    if a.strict_warn and a.no_warn:
        print("错误：--strict-warn 与 --no-warn 互斥", file=sys.stderr)
        return 1

    registry = None
    registry_invalid = []
    if a.registry is not None:
        registry, err, registry_invalid = _load_registry(a.registry)
        if err:
            print(f"错误：{err}", file=sys.stderr)
            return 1
        if registry_invalid:
            # v3 fail-closed：登记无效即整次运行判失败（不扫描、不放行）
            print(f"错误：design_registry 有 {len(registry_invalid)} 条无效登记"
                  f"（fail-closed，缺 purpose / approved_by）：{a.registry}",
                  file=sys.stderr)
            for it in registry_invalid:
                print(f"  [{it['index']}] rule={it['rule']} "
                      f"selector={it['selector']} 缺失字段："
                      f"{'、'.join(it['missing'])}", file=sys.stderr)
            if a.json_out:
                with open(a.json_out, "w", encoding="utf-8") as fh:
                    json.dump({"scanned": [], "findings": [], "blocked": True,
                               "mode": a.mode,
                               "strict_warn": bool(a.strict_warn),
                               "registry": {"path": a.registry,
                                            "entries": len(registry or []),
                                            "valid": False,
                                            "invalid": registry_invalid},
                               "waived": []}, fh,
                              ensure_ascii=False, indent=2)
            return 1

    files = []
    if a.dir:
        for root, _, fns in os.walk(a.target):
            for fn in fns:
                if fn.endswith(".html"):
                    files.append(os.path.join(root, fn))
    elif os.path.isfile(a.target):
        files = [a.target]
    else:
        print(f"错误：找不到 {a.target}", file=sys.stderr)
        return 1
    if not files:
        print("未找到 .html 文件", file=sys.stderr)
        return 1

    findings = []
    waived = []
    gsap_sel = set()
    for f in files:
        try:
            with open(f, encoding="utf-8") as fh:
                text = fh.read()
        except Exception as e:  # noqa: BLE001
            print(f"读取失败 {f}: {e}", file=sys.stderr)
            continue
        spec = _find_spec(f)
        palette = _extract_palette(spec)
        scan(text, f, findings, palette, registry=registry, waived=waived,
             pre=(a.mode == "pre"))
        _n, _sels = _gsap_sweep(text)
        gsap_sel.update(_sels)

    errors = [x for x in findings if x["severity"] == "error"]
    if a.mode == "pre":
        # v3：pre 模式默认只阻断 error 级；--strict-warn 时 warn 也计为阻断
        blockers = findings if a.strict_warn else errors
    else:
        blockers = findings if not a.no_warn else errors

    out = {"scanned": files, "findings": findings,
           "blocked": bool(blockers)}
    if a.mode is not None or a.registry is not None:
        out["mode"] = a.mode
        out["strict_warn"] = bool(a.strict_warn)
        out["registry"] = {"path": a.registry,
                           "entries": len(registry) if registry else 0,
                           "valid": True,
                           "invalid": []}
        out["waived"] = waived
        out["registry_scope"] = {
            "level": "selector",
            "note": "仅 selector 级命中可被放行；选择器无法解析（如内联 style 中的"
                    "渐变）时不做整文件级放行，仍判为 blocker。",
        }
    # 报告固定字段：GSAP 黑名单命中集合，供逐轮比对不漂
    gsap_sels = sorted(gsap_sel)
    out["gsap_blacklist"] = {
        "rule": "GSAP_REPEAT_YOYO_SCALE",
        "severity": "warn",
        "hits": len(gsap_sels),
        "selectors": gsap_sels,
        "blocking": False,
        "note": "同模板族呼吸动画，属已知刻意设计；pre 门禁不阻断，"
                "渲染侧 A0/A3 做事实校验",
    }
    if a.json_out:
        with open(a.json_out, "w", encoding="utf-8") as fh:
            json.dump(out, fh, ensure_ascii=False, indent=2)

    if not blockers:
        print("OK：未命中反 AI 视觉痕迹，可放行渲染")
        if waived:
            print(f"（另有 {len(waived)} 处命中经 design_registry 登记放行）")
        return 0
    print(f"检测到 {len(blockers)} 处反 AI 视觉痕迹（拒绝渲染）：")
    for b in blockers:
        loc = f":{b['line']}" if b.get("line") else ""
        sel = f" ({b['selector']})" if b.get("selector") else ""
        print(f"  [{b['severity'].upper()}] {b['rule']} @ {b['source']}{loc}{sel}"
              + (f"（{b['detail']}）" if b["detail"] else "")
              + f" → {b['fix']}")
    return 2


if __name__ == "__main__":
    sys.exit(main())
