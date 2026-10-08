#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""storyctl.py — 抖音竖屏产线编排器（S1-b 入口收敛 · 骨架）

依据：proposals/方案定稿_编排器与质量门禁_v2.1_接口契约与验收细则.md §三 / §五
定位：S1-b「入口收敛」。把既有 per-story 链路与两段质量门禁串成单入口，
      并把门禁退出码按契约分叉，杜绝「把 1 当 2」。

────────────────────────────────────────────────────────────────────────
编排器边界（写死，勿越界）
────────────────────────────────────────────────────────────────────────
本编排器只覆盖 HyperFrames per-story 路线（story/ 下 11 个双脚本同簇项目）：

    build_audio → build_html → [段1 渲染前门禁] → hyperframes render
                → post_process → append_epilogue

`render.sh + Pexels` 路线与根目录 `generate_*_video.py` **暂不纳入**：
保持现状、不改动、不收编、不删除。违反此边界会造出新的「文档与实现分叉」。

────────────────────────────────────────────────────────────────────────
子命令
────────────────────────────────────────────────────────────────────────
  storyctl new <name>                 脚手架（复制模板 story，注入 STORY/name，不再手抄）
                                      · post-copy 显式清理模板残留（qc/ · *.log / index.html /
                                        timing.json/旧交付报告），不依赖 _IGNORE 是否生效
                                      · 生成的 script.json **不带** delivery_spec_waiver 键
                                        （缺键 = 无豁免）
  storyctl build <name> [--no-gate] [--no-check] [--qc]
                                      编排既有链路；段1 内联在 HTML 产出后 / 渲染前
                                      · --check（默认开启）内容层校验前置，--no-check 跳过
                                      · --qc 显式 opt-in：出片后串联两段门禁（默认只跑段1）
  storyctl qc <name> [--ref <mp4>] [--baseline <…>] [--store-baseline] [--check]
                                      两段门禁，可单独重跑，不依赖 build
                                      · --check 为显式 opt-in（保持 qc 原语义）
  storyctl catalog voice|video|frontend
  storyctl doctor [--tts]              跨平台自检：工具链/字体/不变量/TTS provider 配置

产物命名收口：`douyin.mp4` + `douyin_epilogue.mp4`
（废弃 `douyin_final.mp4` / `output.mp4` 旧命名；既有项目不改动）

────────────────────────────────────────────────────────────────────────
退出码映射（钉死，严禁把 1 当 2）
────────────────────────────────────────────────────────────────────────
  0  成功
  1  编排器侧故障 —— 用法/输入错误、链路命令失败、门禁返回 1（用法/输入错误：
                     registry 缺失/格式错/无效登记、HTML 找不到、参数错）
  2  成片检出问题 —— 门禁返回 2（检出痕迹 / 审计断言失败），属设计问题不是 bug

  1 与 2 的处理动作不同：1 → 中断并提示「修输入」；2 → 提示「去 script.json 的
  design_registry 登记该 selector，或改纯色」。二者不得互相顶替。

  逃生口 `--no-gate` **只跳 build 内联的段1，不影响 qc**；跳过的落盘报告
  （story/<name>/qc/pre.json）必须注明跳过原因。
────────────────────────────────────────────────────────────────────────
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

# 跨平台适配层（scripts/platform_env.py）与 TTS provider 抽象（scripts/tts_provider.py）
# 与本脚本同目录：先确保同目录在 sys.path 上，再导入（不依赖调用方式）。
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import platform_env  # noqa: E402
import tts_provider  # noqa: E402

# ── 路径常量（全部以本脚本位置为准，避免硬编码 cwd） ──────────────────────
ROOT = Path(__file__).resolve().parent.parent          # 仓库根（自动推导，不写死绝对路径）
STORY_ROOT = ROOT / "story"
SCRIPTS = ROOT / "scripts"
GATE_PY = SCRIPTS / "design_ai_gate.py"                # 段1：渲染前门禁
AUDIT_PY = SCRIPTS / "frame_audit.py"                  # 段2：渲染后审计
POST_PROCESS_PY = ROOT / "post_process.py"
APPEND_EPILOGUE_PY = ROOT / "append_epilogue.py"
DEAI_LINT_PY = ROOT / "scripts" / "deai_lint.py"
# v1.13.0 知识库候选落地（KB-* 命名，避开 frame_audit 既有的 A0–A7 断言编号）
KB_ANCHORS_PY = ROOT / "scripts" / "anchors_check.py"      # KB-A2 锚点漂移 + KB-A7 光照阈值
KB_PAUSE_PY = ROOT / "scripts" / "pause_audit.py"          # KB-A6 无意义停顿
KB_SEMANTIC_PY = ROOT / "scripts" / "semantic_axis.py"     # KB-A4 语义轴（ASR 回读）
KB_NONDET_PY = ROOT / "scripts" / "nondeterminism.py"      # KB-A5 渲染非确定段单列
KB_SLOTS_PY = ROOT / "scripts" / "template_slots.py"       # KB-A8 模板库槽位化
CATALOG_JSON = ROOT / "config" / "selection_catalog.json"

# ── 可调外部命令（环境变量可覆盖，便于换 venv / 本地 CLI） ────────────────
# 跨平台解析：环境变量 > 仓库 venv > PATH/平台常见目录（Windows 补 .exe）> 兜底


def _resolve_python() -> str:
    env = os.environ.get("STORYCTL_PYTHON", "").strip()
    if env:
        return env
    for rel in (".venv/bin/python", ".venv/Scripts/python.exe",
                "venv/bin/python", "venv/Scripts/python.exe"):
        cand = ROOT / rel
        if cand.is_file():
            return str(cand)
    return (platform_env.find_tool("python3") or platform_env.find_tool("python")
            or sys.executable or "python3")


def _resolve_hyperframes() -> list:
    raw = os.environ.get("STORYCTL_HYPERFRAMES", "").strip()
    if raw:
        return raw.split()
    hit = platform_env.find_tool("hyperframes")
    if hit:
        return [hit]
    npx = platform_env.find_tool("npx") or platform_env.find_tool("npx.cmd") or "npx"
    return [npx, "hyperframes"]


PY = _resolve_python()
HYPERFRAMES = _resolve_hyperframes()

# ── 脚手架模板（per-story 双脚本路线的样板 story） ───────────────────────
DEFAULT_TEMPLATE = os.environ.get("STORYCTL_TEMPLATE", "compositor-mac")

# ── 退出码 ────────────────────────────────────────────────────────────────
EXIT_OK = 0
EXIT_ORCH = 1       # 编排器侧故障
EXIT_DETECT = 2     # 成片检出问题

# ── 产物命名收口 ──────────────────────────────────────────────────────────
PRODUCT_MAIN = "douyin.mp4"
PRODUCT_EPILOGUE = "douyin_epilogue.mp4"

# ── 渲染精度（2026-10-07 加装 opt-in；2026-10-07 默认化 = 产线默认工作流）────
# 背景：交付编码参数唯一真源是 config/param_contract.json → delivery_profile
# （1080×1920 / capped-CRF，读取器 scripts/encode_profile.py），两段门禁判据不动。
# 因此「成片画质再上一档」只剩渲染侧自由度：hyperframes 的 --resolution 走
# Chrome deviceScaleFactor 整数倍超采样（portrait-4k = 2×），版面按 2160×3840
# 采样后再由 post_process 收口回合同尺寸 → 文字/细线边缘更干净，且交付判据不变。
# 默认化（真源 docs/产线规范.md v1.12.0；依据 cua 成片实证，段1/段2 门禁全绿）：
#   · 未设 / 空 env   → 默认 portrait-4k（超采样默认启用）
#   · =portrait       → 白名单 1× 档（显式回退，A/B 对照复现）
#   · =off|none|1x    → 不追加 --resolution，命令行与默认化前逐字节一致（一键关）
#   · 其它值          → 拒绝非登记档位（用法错误，退出码 1）
# 边界：只影响渲染采样精度，**不触碰 config/**，不改变交付尺寸/编码与两段门禁判据。
RENDER_RESOLUTION_ENV = "STORYCTL_RENDER_RESOLUTION"
RENDER_RESOLUTION_DEFAULT = "portrait-4k"
RENDER_RESOLUTION_PRESETS = {
    "portrait-4k": "Chrome deviceScaleFactor=2 超采样（1080×1920 版面按 2160×3840 采样）",
    "portrait": "1× 采样（与出厂完全一致，留作 A/B 对照复现）",
}
RENDER_RESOLUTION_OFF = ("off", "none", "1x")

# A7 豁免登记键（与 frame_audit.A7_WAIVER_KEY 同名同义）。脚手架**不预埋**该键：
# 缺键 = 无豁免（frame_audit 侧对缺键返回空表，不报错）—— 方案 B 裁定 d。
A7_WAIVER_KEY = "delivery_spec_waiver"

NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


# ══════════════════════════════════════════════════════════════════════════
# 基础设施
# ══════════════════════════════════════════════════════════════════════════

class _Parser(argparse.ArgumentParser):
    """把 argparse 的用法/输入错误统一收敛为退出码 1（编排器侧故障）。

    契约 §三：design_ai_gate 已重写 Parser.error 以 1 退出，避免与「检出痕迹」撞码；
    storyctl 同样口径 —— 用法错误属于编排器侧故障，绝不与 2 混用。
    """

    def error(self, message):
        self.print_usage(sys.stderr)
        sys.stderr.write(f"storyctl: 用法/输入错误: {message}\n")
        sys.exit(EXIT_ORCH)


def _ts() -> str:
    return datetime.now().strftime("%Y-%m-%dT%H:%M:%S")


def _log(msg: str) -> None:
    print(f"[storyctl] {msg}", flush=True)


def _err(msg: str) -> None:
    print(f"[storyctl][ERROR] {msg}", file=sys.stderr, flush=True)


def _sha256(path: Path) -> str:
    import hashlib
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for blk in iter(lambda: fh.read(1 << 20), b""):
            h.update(blk)
    return h.hexdigest()


def resolve_story(name: str) -> Path:
    """解析 story 目录；非法或不存在一律视为编排器侧故障（1）。"""
    if not name or not NAME_RE.match(name):
        raise _UsageError(f"非法的 story 名: {name!r}（只允许字母/数字/._-，且不以符号开头）")
    sd = STORY_ROOT / name
    if not sd.is_dir():
        raise _UsageError(f"story 目录不存在: {sd}")
    return sd


class _UsageError(Exception):
    """输入/用法错误 —— 统一映射为 exit 1。"""


def run_step(step: str, cmd, cwd: Path, dry_run: bool = False) -> int:
    """执行链路中的一步，返回其退出码（不做码值翻译，交由上层的门禁翻译器处理）。"""
    _log(f"▶ {step}")
    _log(f"  cwd={cwd}")
    _log(f"  $ {' '.join(str(c) for c in cmd)}")
    if dry_run:
        _log("  [dry-run] 未执行")
        return EXIT_OK
    try:
        # 注入跨平台工具链 PATH（node/npx 等 shim 依赖 PATH，避免调用方 shell PATH 精简导致 rc=127）
        proc = subprocess.run([str(c) for c in cmd], cwd=str(cwd), env=platform_env.tool_env())
    except FileNotFoundError as exc:
        _err(f"{step}: 找不到可执行文件 —— {exc}")
        return EXIT_ORCH
    _log(f"  ← rc={proc.returncode}")
    return proc.returncode


# ══════════════════════════════════════════════════════════════════════════
# 门禁退出码翻译器（唯一分叉点，严禁把 1 当 2）
# ══════════════════════════════════════════════════════════════════════════

def interpret_gate_rc(segment: str, rc: int) -> int:
    """把门禁退出码按契约翻译为 storyctl 退出码，并打印对应处置提示。

    | gate rc | 含义                       | storyctl 行为                       |
    |---------|----------------------------|-------------------------------------|
    | 0       | 通过                       | 0，继续                              |
    | 1       | 用法/输入错误              | 1（编排器侧故障，中断 + 修输入提示） |
    | 2       | 检出痕迹（设计问题，非 bug）| 2（中断 + 登记/改纯色提示）          |
    """
    if rc == EXIT_OK:
        _log(f"✔ {segment} 通过（rc=0）")
        return EXIT_OK
    if rc == EXIT_ORCH:
        _err(f"{segment} 返回 1 = 用法/输入错误（编排器侧故障，不是门禁拒绝）")
        _err("  → 排查：script.json 的 design_registry 是否缺 purpose/approved_by、")
        _err("          registry 文件是否存在且为对象、目标 HTML 是否存在、参数是否正确")
        return EXIT_ORCH
    if rc == EXIT_DETECT:
        _err(f"{segment} 返回 2 = 检出痕迹（设计问题，不是 bug）")
        _err("  → 处置：去 script.json 的 design_registry 登记该 selector，或改纯色")
        return EXIT_DETECT
    _err(f"{segment} 返回未登记退出码 {rc} —— 按编排器侧故障处理")
    return EXIT_ORCH


# ══════════════════════════════════════════════════════════════════════════
# 段1：渲染前门禁（design_ai_gate --mode pre）
# ══════════════════════════════════════════════════════════════════════════

def run_kb_step(step: str, script: Path, sd: Path, extra_args, dry_run: bool = False,
                skip: bool = False, strict: bool = False, strict_hint: str = "--strict",
                pre_register=None, pre_register_when=None) -> int:
    """KB-* 增量步骤统一入口（v1.13.0 知识库候选落地的共同调用约定）。

    设计口径（与 A9 deai_lint 一致）：
      * **advisory 默认**：脚本 rc=2（检出）只告警不拦截，报告照落盘 qc/*.json；
      * `strict=True`（CLI 的 --strict-xxx）时 rc=2 升级为拦截；
      * **orchestrator 故障（rc=1）一律返回 EXIT_ORCH**，便于上层如实区分
        "脚本坏了" 与 "片子有问题"；
      * 脚本缺失 / 显式 skip → 视为跳过（rc=0），但必须留痕。
    """
    (sd / "qc").mkdir(parents=True, exist_ok=True)
    if skip:
        _err(f"⚠ 已跳过 {step}（显式关闭开关）—— 留痕在日志")
        return EXIT_OK
    if not script.is_file():
        _err(f"⚠ 已跳过 {step}（脚本缺失：{script}）")
        return EXIT_OK
    if pre_register and pre_register_when and pre_register_when():
        _err(f"  {step}：无登记表 → 先 --emit-anchors 首次登记当前取值")
        rc = run_step(f"{step} · 首次登记", pre_register, cwd=sd, dry_run=dry_run)
        if rc != EXIT_OK:
            return EXIT_ORCH
    cmd = [PY, str(script), str(sd)] + list(extra_args or [])
    if strict:
        cmd.append(strict_hint)
    rc = run_step(step, cmd, cwd=ROOT, dry_run=dry_run)
    if rc == EXIT_ORCH:
        return EXIT_ORCH
    if rc == EXIT_DETECT and not strict:
        _err(f"⚠ {step} 存在检出项（advisory 默认不拦；加 {strict_hint} 可升级为阻断）")
        return EXIT_OK
    return rc


def run_kb_axes(sd: Path, name: str, dry_run: bool = False, semantic: bool = True,
                nondet: bool = True, strict: bool = False) -> int:
    """qc 侧 KB 增强轴：KB-A4 语义轴（ASR 回读）+ KB-A5 渲染非确定段单列。

    与两段门禁的关系：**只增不改**。两段门禁判据（design_ai_gate / frame_audit）
    原样保留、退出码语义不变；本函数在两段全绿之后追加 advisory 走查，脚本缺失或
    输入不足（无音轨等）只告警不阻断。
    """
    jobs = []
    if semantic:
        jobs.append(("KB-A4 semantic_axis.py（成片回读 vs 稿子）", KB_SEMANTIC_PY,
                     ["--json", str(sd / "qc" / "semantic_axis.json"), "--quiet"],
                     "--strict-semantic"))
    if nondet:
        jobs.append(("KB-A5 nondeterminism.py（渲染非确定段单列）", KB_NONDET_PY,
                     ["--json", str(sd / "qc" / "nondeterminism.json"), "--quiet"],
                     "--strict-nondet"))
    for step, script, extra, hint in jobs:
        if not script.is_file():
            _err(f"⚠ 已跳过 {step}（脚本缺失：{script}）")
            continue
        (sd / "qc").mkdir(parents=True, exist_ok=True)
        cmd = [PY, str(script), str(sd)] + extra + ([hint] if strict else [])
        rc = run_step(step, cmd, cwd=ROOT, dry_run=dry_run)
        if rc == EXIT_ORCH:
            _err(f"⚠ {step} 未完成（输入不足或脚本故障）—— 该轴跳过，不影响两段门禁结论")
            continue
        if rc == EXIT_DETECT and not strict:
            _err(f"⚠ {step} 存在检出项（advisory 默认不拦；加 {hint} 可升级为阻断）")
    return EXIT_OK


def run_pre_gate(sd: Path, dry_run: bool = False) -> int:
    """段1。契约 §五：默认不传 --no-warn 也不传 --strict-warn。

    依赖 pre 模式「默认只阻断 error 级」的语义，保证文档示例与实现不分叉。
    """
    html = sd / "index.html"
    if not html.is_file():
        _err(f"段1 前置检查失败：{html} 不存在（请先执行 build_html）")
        return EXIT_ORCH
    qc_dir = sd / "qc"
    qc_dir.mkdir(parents=True, exist_ok=True)
    cmd = [
        PY, GATE_PY, str(html),
        "--mode", "pre",
        "--registry", str(sd / "script.json"),
        "--json-out", str(qc_dir / "pre.json"),
    ]
    rc = run_step("段1 渲染前门禁 design_ai_gate --mode pre", cmd, cwd=ROOT, dry_run=dry_run)
    if dry_run:
        return EXIT_OK
    return interpret_gate_rc("段1 渲染前门禁", rc)


def write_gate_skip_report(sd: Path, reason: str) -> Path:
    """--no-gate 逃生口的落盘留痕：必须注明跳过原因（契约 §五）。"""
    qc_dir = sd / "qc"
    qc_dir.mkdir(parents=True, exist_ok=True)
    out = qc_dir / "pre.json"
    payload = {
        "skipped": True,
        "segment": 1,
        "gate": "scripts/design_ai_gate.py",
        "mode": "pre",
        "reason": reason,
        "skipped_at": _ts(),
        "note": "仅跳过 storyctl build 内联的段1；storyctl qc 仍会全跑两段，不受此影响",
        "html": str(sd / "index.html"),
        "registry": str(sd / "script.json"),
    }
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return out


# ══════════════════════════════════════════════════════════════════════════
# 段2：渲染后审计（frame_audit）
# ══════════════════════════════════════════════════════════════════════════

def run_frame_audit(sd: Path, ref: str = None, baseline: str = None,
                    store_baseline: bool = False, dry_run: bool = False) -> int:
    """段2。契约 §五：qc 的段2 以 douyin_epilogue.mp4 为被测件。

    baseline：A0 同源基线透传口（S3 补，此前无此口 → A0 无法经 qc 启用）。
    A0 维持 opt-in，不进默认段2：实证两项目 build 前后 index.html sha256 必变
    （build_html 写入时长轴 + TTS 旁白轴），纳入默认会让每次 qc 必拒；
    仅在显式 `storyctl qc <name> --baseline <…>` 时才向下传。
    store_baseline：S3 收口修正——此前 qc 无此口，operator 只能绕道直调
    frame_audit。注意存的是**段2 被测件**（douyin_epilogue.mp4）的 size/帧快照，
    即以片尾件为基线锚点；需要以原片（douyin.mp4）为锚点时请直调 frame_audit。
    """
    video = sd / PRODUCT_EPILOGUE
    if not video.is_file():
        _err(f"段2 前置检查失败：{video} 不存在（请先 storyctl build 出片）")
        return EXIT_ORCH
    qc_dir = sd / "qc"
    qc_dir.mkdir(parents=True, exist_ok=True)
    cmd = [
        PY, AUDIT_PY,
        "--video", str(video),
        "--script", str(sd / "script.json"),
        "--json-out", str(qc_dir / "report.json"),
    ]
    if ref:
        cmd += ["--ref", str(Path(ref).expanduser())]
    if baseline:
        # S3 收口修正：此前 --baseline 只收不发（口存在但从不透传）→ 显式传了也不生效
        cmd += ["--baseline", str(Path(baseline).expanduser())]
    if store_baseline:
        cmd += ["--store-baseline"]
    rc = run_step("段2 渲染后审计 frame_audit", cmd, cwd=ROOT, dry_run=dry_run)
    if dry_run:
        return EXIT_OK
    return interpret_gate_rc("段2 渲染后审计", rc)


# ══════════════════════════════════════════════════════════════════════════
# 内容层校验（--check：build 默认前置；方案 B MVP 裁定 d）
# ══════════════════════════════════════════════════════════════════════════
# error 集（缺即拦下，退出码 2）：title / scenes+lines / epilogue 文案 /
#                                voice_role+voice_engine / source
# warn  集（落报告不拦）：facts / date / watermark
# 另加：模板占位符泄漏扫描（{{…}} / TODO / 待填 …）
CHECK_PLACEHOLDER_PATTERNS = (
    "{{", "}}", "TODO", "FIXME", "TBD", "XXX", "占位", "待填", "待补",
    "placeholder", "PLACEHOLDER", "REPLACE_ME", "示例文案", "这里是",
)
CHECK_DATE_RE = re.compile(r"^\d{4}\.\d{2}\.\d{2}$")


def _iter_strings(node, path=""):
    """递归产出 (json 路径, 字符串值)，供占位符扫描定位。"""
    if isinstance(node, str):
        yield path, node
    elif isinstance(node, dict):
        for k, v in node.items():
            yield from _iter_strings(v, f"{path}.{k}" if path else str(k))
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from _iter_strings(v, f"{path}[{i}]")


def _placeholder_hits(script: dict) -> list:
    """模板占位符泄漏扫描：命中即 error（防模板文案被原样交付）。"""
    hits = []
    for path, val in _iter_strings(script):
        for pat in CHECK_PLACEHOLDER_PATTERNS:
            if pat in val:
                hits.append((path, pat, val[:60]))
                break
    return hits


def _content_findings(script: dict) -> tuple:
    """内容层校验判据（方案 B MVP 裁定 d）。返回 (errors, warns)。

    实测校准（2026-10-06，全仓 21 个 script.json）：本集下 11 个双脚本项目
    0 error（gods-eye-view 因 source 缺失 → 本批按证据回填后通过）；
    easyvoice-*（半成品）/ cn-llm-price-war（旧路线）会报 error，
    但它们本就不走本编排器链路（cmd_build 已前置拒绝非双脚本项目）。
    """
    errors, warns = [], []

    def _need_str(key: str, label: str, field: str) -> None:
        v = script.get(key)
        if not isinstance(v, str) or not v.strip():
            errors.append(f"{field}: 缺 {label}（顶层 '{key}' 为空或非字符串）")

    _need_str("title", "标题", "title")
    _need_str("voice_role", "配音角色", "voice_role+voice_engine")
    _need_str("voice_engine", "配音引擎", "voice_role+voice_engine")
    _need_str("source", "素材/数据来源", "source")

    scenes = script.get("scenes")
    if not isinstance(scenes, list) or not scenes:
        errors.append("scenes+lines: 'scenes' 为空或非数组")
    else:
        for i, sc in enumerate(scenes):
            if not isinstance(sc, dict):
                errors.append(f"scenes+lines: scenes[{i}] 非对象")
                continue
            lines = sc.get("lines")
            if not isinstance(lines, list) or not lines:
                errors.append(f"scenes+lines: scenes[{i}]（{sc.get('type', '?')}）无 lines")
                continue
            for j, ln in enumerate(lines):
                if not isinstance(ln, dict) or not str(ln.get("text") or "").strip():
                    errors.append(f"scenes+lines: scenes[{i}].lines[{j}] 缺 text")
                elif not str(ln.get("role") or "").strip():
                    errors.append(f"scenes+lines: scenes[{i}].lines[{j}] 缺 role")

    top_lines = script.get("lines")
    if not isinstance(top_lines, list) or not top_lines:
        errors.append("scenes+lines: 顶层 'lines'（旁白轴）为空或非数组")
    else:
        for i, ln in enumerate(top_lines):
            if not isinstance(ln, dict) or not str(ln.get("text") or "").strip():
                errors.append(f"scenes+lines: lines[{i}] 缺 text")

    epi = script.get("epilogue")
    if not isinstance(epi, dict):
        errors.append("epilogue 文案: 缺 'epilogue' 对象")
    elif epi.get("enabled", True):
        if not str(epi.get("text") or "").strip():
            errors.append("epilogue 文案: epilogue.text 为空")
    else:
        warns.append("epilogue 文案: epilogue.enabled=false（片尾件将为空壳）")

    if not script.get("facts"):
        warns.append("facts: 缺上屏数据表（warn，不拦）")
    if not CHECK_DATE_RE.match(str(script.get("date") or "")):
        warns.append("date: 缺或格式非 YYYY.MM.DD（warn，不拦）")
    if not str(script.get("watermark") or "").strip():
        warns.append("watermark: 缺（warn，不拦）")

    for path, pat, val in _placeholder_hits(script):
        errors.append(f"占位符泄漏: {path} 含 {pat!r} —— {val!r}")
    return errors, warns


def run_content_check(sd: Path, dry_run: bool = False) -> int:
    """内容层校验（--check）。报告落 story/<name>/qc/content.json。

    退出码：0 通过 / 1 script.json 不可读或不可解析（编排器侧故障）/ 2 检出 error。
    """
    sp = sd / "script.json"
    _log(f"内容校验 --check：{sp}")
    try:
        script = json.loads(sp.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        _err(f"内容校验：script.json 不可读/不可解析 —— {exc}")
        return EXIT_ORCH
    if not isinstance(script, dict):
        _err("内容校验：script.json 顶层须为对象")
        return EXIT_ORCH

    errors, warns = _content_findings(script)
    qc_dir = sd / "qc"
    qc_dir.mkdir(parents=True, exist_ok=True)
    out = qc_dir / "content.json"
    payload = {
        "check": "content",
        "script": str(sp),
        "script_sha256": _sha256(sp),
        "checked_at": _ts(),
        "error_set": ["title", "scenes+lines", "epilogue 文案",
                      "voice_role+voice_engine", "source", "占位符泄漏扫描"],
        "warn_set": ["facts", "date", "watermark"],
        "errors": errors,
        "warns": warns,
        "passed": not errors,
    }
    if dry_run:
        _log(f"  [dry-run] 校验结果未落盘：{out}")
    else:
        out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                       encoding="utf-8")
    _log(f"  内容校验 error {len(errors)} 项 / warn {len(warns)} 项")
    for e in errors:
        _err(f"    [error] {e}")
    for w in warns:
        _log(f"    [warn ] {w}")
    if not dry_run:
        _log(f"  报告：{out}")
    if errors:
        _err("内容校验未通过（内容层缺陷 = 退出码 2，不是编排器故障）")
        return EXIT_DETECT
    _log("✔ 内容校验通过（error 0 项）")
    return EXIT_OK


# ══════════════════════════════════════════════════════════════════════════
# 子命令：new
# ══════════════════════════════════════════════════════════════════════════

_IGNORE = shutil.ignore_patterns(
    "renders", "qc", "epilogue", "node_modules", "__pycache__", ".git",
    "*.mp4", "*.wav", "*.mp3", "*.m4a", "*.srt", "*.ass",
    "*.json.bak*", "*.py.bak*", "line_*",
    # MVP 骨架收口（方案 B 裁定 a，2026-10-06）：模板根目录遗留的构建日志、
    # 渲染中间产物与旧交付报告一律不进新项目。_IGNORE 只是**第一道**，复制后
    # 仍由 purge_scaffold() 逐项显式删除（第二道，防忽略规则被改坏/模板换名）。
    "*.log", "index.html", "timing.json", "交付质检报告_*", "*.tmp", "*.bak",
)

# ── MVP 骨架收口：post-copy 显式删除清单（方案 B 裁定 a） ─────────────────
# 背景（本机实测证据，2026-10-06，见 proposals/实施回执 第5批章节）：
#   * 默认模板 compositor-mac 的**story 根目录**残留 4 个构建日志
#     （build_audio.log / epilogue.log / render.log / render_direct.log）、
#     index.html、timing.json 与旧交付报告 交付质检报告_compositor-mac.md；
#     旧 _IGNORE 不含这些模式 → 会被 copytree 原样带进新项目（已复现）。
#   * `qc` 的 _IGNORE 规则经实测**生效**（copytree 后目标树无 qc/、模板 qc/ 内
#     5 个文件均未带入）→ 不属 bug；此处仍显式删 qc/ 作第二道防线。
_PURGE_DIRS = ("qc",)
_PURGE_FILES = ("index.html", "timing.json")
_PURGE_GLOBS = ("*.log", "*.tmp", "*.bak")
_PURGE_TPL_FILES = ("交付质检报告_{tpl}.md",)      # 旧交付报告（模板名后缀）


def purge_scaffold(target: Path, tpl: str) -> list:
    """复制后逐项显式删除模板残留，返回已删条目（相对路径）列表。

    与 _IGNORE 的分工：_IGNORE 是复制期过滤（省 IO，但依赖模式列表正确）；
    本函数是复制后的兜底，**不信** _IGNORE 是否生效 —— 即使未来模板改名、
    忽略规则被误删，残留也不会进新项目。
    """
    removed = []

    def _unlink(p: Path) -> None:
        p.unlink()
        removed.append(os.path.relpath(str(p), str(target)))

    def _rmtree(p: Path) -> None:
        n = sum(len(fs) for _, _, fs in os.walk(p))
        shutil.rmtree(p)
        removed.append(f"{os.path.relpath(str(p), str(target))}/（{n} 个文件）")

    for d in _PURGE_DIRS:
        p = target / d
        if p.is_dir():
            _rmtree(p)
        elif p.is_file():
            _unlink(p)
    for f in _PURGE_FILES:
        p = target / f
        if p.is_file():
            _unlink(p)
    for pat in _PURGE_GLOBS:
        for p in sorted(target.glob(pat)):
            if p.is_file():
                _unlink(p)
    for pat in _PURGE_TPL_FILES:
        for p in sorted(target.glob(pat.format(tpl=tpl))):
            if p.is_file():
                _unlink(p)
    return removed


def cmd_new(args) -> int:
    name = args.name
    if not name and not getattr(args, "list_kinds", False):
        raise _UsageError("new 需要 story 名（或 --list-kinds）")

    # KB-A8：模板库槽位化 —— --list-kinds 直接列模板库后退出
    if getattr(args, "list_kinds", False):
        if not KB_SLOTS_PY.is_file():
            raise _UsageError(f"模板库脚本缺失：{KB_SLOTS_PY}")
        return run_step("template_slots.py --list（KB-A8 模板库）",
                        [PY, str(KB_SLOTS_PY), "--list"], cwd=ROOT)

    # KB-A8：kind → 模板 story（真源 templates/registry.json）。
    # --template 显式给出时优先（既有行为完全不变）；否则由 kind 解析，
    # kind=default → compositor-mac（与加装前逐字节一致）。
    tpl = args.template
    if tpl is None:
        if not KB_SLOTS_PY.is_file():
            raise _UsageError(f"--kind 需要模板库脚本：{KB_SLOTS_PY}")
        r = subprocess.run([PY, str(KB_SLOTS_PY), "--resolve", args.kind],
                           cwd=ROOT, capture_output=True, text=True)
        if r.returncode != 0:
            raise _UsageError(
                f"--kind {args.kind!r} 未在模板库登记（{r.stderr.strip()[:120]}）")
        tpl = r.stdout.strip()
        _log(f"  KB-A8 模板库解析：kind={args.kind} → 模板 {tpl}")

    if not NAME_RE.match(name):
        raise _UsageError(f"非法的 story 名: {name!r}")
    target = STORY_ROOT / name
    if target.exists():
        raise _UsageError(f"目标已存在，拒绝脚手架覆盖: {target}")
    src = STORY_ROOT / tpl
    if not src.is_dir():
        raise _UsageError(f"模板 story 不存在: {src}")

    _log(f"脚手架：{src} → {target}（复制双脚本，忽略产物/缓存）")
    shutil.copytree(src, target, ignore=_IGNORE)

    # 方案 B 裁定 a：post-copy 显式删 qc/、*.log、index.html、timing.json（+ 旧交付报告）
    removed = purge_scaffold(target, tpl)
    _log(f"  复制后显式清理模板残留 {len(removed)} 项：")
    for r in removed or ["（无）"]:
        _log(f"    - {r}")

    for sub in ("renders", "qc"):
        (target / sub).mkdir(exist_ok=True)

    # 注入 STORY / name（模板内为硬编码绝对路径与 name 字段）
    touched = []
    for fname in ("build_audio.py", "build_html.py", "hyperframes.json", "script.json"):
        f = target / fname
        if not f.is_file():
            continue
        text = f.read_text(encoding="utf-8")
        new_text = text.replace(f"story/{tpl}", f"story/{name}")
        new_text = new_text.replace(f'"name": "{tpl}"', f'"name": "{name}"')
        new_text = new_text.replace(f'"name":"{tpl}"', f'"name":"{name}"')
        if new_text != text:
            f.write_text(new_text, encoding="utf-8")
            touched.append(fname)

    _log(f"✔ 脚手架完成：{target}")
    _log(f"  已注入 STORY/name 的文件：{touched or '（无匹配，请人工核对）'}")

    # 方案 B 裁定 d：脚手架生成的 script.json **不带** delivery_spec_waiver 键
    # （缺键即视为无豁免 —— frame_audit._a7_waivers 对缺键返回空表且不报错）。
    sp = target / "script.json"
    if sp.is_file():
        try:
            sd_data = json.loads(sp.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise _UsageError(f"模板 script.json 解析失败（脚手架中止前已复制）：{sp} —— {exc}")
        if A7_WAIVER_KEY in sd_data:
            sd_data.pop(A7_WAIVER_KEY)
            sp.write_text(json.dumps(sd_data, ensure_ascii=False, indent=2) + "\n",
                          encoding="utf-8")
            _log(f"  script.json 已移除模板携带的 {A7_WAIVER_KEY} 键（骨架不带该键）")
        _log(f"  ✔ script.json 无 {A7_WAIVER_KEY} 键（缺键 = 无豁免，非错误）")

    # KB-A8 槽位化：把该 kind 的槽位清单落盘为 slots.json 并校验必填槽位填充状态
    # （只写清单文件，不修改 story 内任何既有文件；advisory，不改变退出码）
    if KB_SLOTS_PY.is_file():
        run_step(f"{name} · KB-A8 槽位清单（kind={args.kind}）",
                 [PY, str(KB_SLOTS_PY), "--emit", "--kind", args.kind,
                  "--story", str(target)], cwd=ROOT)

    _log("  待人工：改写 script.json 的 scenes/cards/header/outro 文案；")
    _log("          design_registry 登记由方案 B 填（本脚本不触碰）。")
    _log(f"  下一步：storyctl build {name}")
    return EXIT_OK


# ══════════════════════════════════════════════════════════════════════════
# 子命令：build
# ══════════════════════════════════════════════════════════════════════════

def _render_output(sd: Path, name: str) -> Path:
    """hyperframes render 输出到 renders/<name>_<YYYY-MM-DD_HH-MM-SS>.mp4（沿用既有落盘命名）。"""
    stamp = time.strftime("%Y-%m-%d_%H-%M-%S")
    return sd / "renders" / f"{name}_{stamp}.mp4"


def tts_preflight(dry_run: bool = False) -> int:
    """build_audio 前置：TTS provider 配置自检（跨平台可插拔 provider 闸门）。

    口径（与 config/tts.json 真源一致）：
      · 自检在 build 实际使用的解释器（PY）里执行，确保 mlx-audio 等依赖的可见性
        与被测解释器一致；
      · provider 未配置/依赖缺失/凭据缺失 → 明确报错并中止（退出码 1），
        **不静默降级**到其它 provider；
      · 只读检查：不写盘、不联网（云端 provider 的凭据仅从环境变量读取）。
    """
    if dry_run:
        _log("▶ TTS provider 自检（dry-run 仍执行：只读、不联网）")
    try:
        proc = subprocess.run([PY, str(SCRIPTS / "tts_provider.py")],
                              cwd=str(ROOT), capture_output=True, text=True)
    except FileNotFoundError as exc:
        _err(f"TTS 自检失败：找不到解释器 {PY}（{exc}）")
        return EXIT_ORCH
    msg = (proc.stdout or "").strip() or (proc.stderr or "").strip()
    first = msg.splitlines()[0] if msg else ""
    if proc.returncode != 0:
        _err("TTS provider 配置未就绪，build_audio 未启动（未配置即失败，不静默降级）：\n"
             + (msg or "（无输出）"))
        return EXIT_ORCH
    _log(f"1/6 前置 · TTS provider 自检 —— 就绪：{first}")
    if msg and msg != first:
        for line in msg.splitlines()[1:]:
            _log(f"    {line}")
    return EXIT_OK


def cmd_build(args) -> int:
    name = args.name
    sd = resolve_story(name)
    script = sd / "script.json"
    for req in ("build_audio.py", "build_html.py"):
        if not (sd / req).is_file():
            raise _UsageError(f"{name} 非 per-story 双脚本路线（缺 {req}）—— 本编排器边界外")
    if not script.is_file():
        raise _UsageError(f"缺 script.json: {script}")

    dry = args.dry_run
    renders = sd / "renders"
    renders.mkdir(exist_ok=True)
    render_mp4 = _render_output(sd, name)

    _log(f"build {name} · 链路：build_audio → [KB-A6] → build_html → [KB-A2/A7] → [段1] → render → post_process → append_epilogue"
         + (" → [qc]" if args.qc else ""))

    # 0) 内容层校验（--check 默认前置；--no-check 跳过）—— 方案 B MVP 裁定 d
    #    放在最前：内容层缺陷（缺 title/source、占位符泄漏…）比渲染失败更廉价可拦。
    if args.check:
        rc = run_content_check(sd, dry_run=dry)
        if rc != EXIT_OK:
            _err("build 在内容校验被拦下：未进入 build_audio（内容层缺陷 = 退出码 2）")
            return rc
        _log("0/6 内容校验 —— 完成")
    else:
        _err("⚠ 已跳过内容校验（--no-check）：不校验 title/scenes+lines/epilogue 文案/"
             "voice_role+voice_engine/source 与占位符泄漏扫描")

    # 0.5) 文案层去 AI 味量化闸门（A9，真源 docs/产线规范.md v1.13.0）
    #      设计口径：**advisory 默认**——走查并落盘 qc/deai.json，但不改两段门禁
    #      判据、不默认阻断既有 story；--strict-deai 时 FAIL（rc=2）升级为拦截。
    #      --no-deai 可整步跳过（逃生口，留痕在日志）。
    if args.no_deai or not DEAI_LINT_PY.is_file():
        _err("⚠ 已跳过文案去 AI 味闸门（--no-deai 或 scripts/deai_lint.py 缺失）")
    else:
        (sd / "qc").mkdir(parents=True, exist_ok=True)
        rc = run_step("0.5/6 deai_lint.py（文案去 AI 味量化）",
                      [PY, str(DEAI_LINT_PY), str(sd),
                       "--json", str(sd / "qc" / "deai.json"), "--quiet"],
                      cwd=ROOT, dry_run=dry)
        if rc == EXIT_ORCH:
            _err(f"deai_lint 自身故障（rc={rc}：用法/输入错误）—— 编排器侧故障")
            return EXIT_ORCH
        if rc == EXIT_DETECT:
            if args.strict_deai:
                _err("build 在文案去 AI 味闸门被拦下（--strict-deai：FAIL 级命中 = 退出码 2）")
                return rc
            _err("⚠ 文案去 AI 味存在 FAIL 级命中（advisory 默认不拦；"
                 "加 --strict-deai 可升级为阻断）—— 报告见 qc/deai.json")
        else:
            _log("0.5/6 文案去 AI 味 —— 完成（无 FAIL 级命中）")

    # 1) 配音 + 时间轴回填
    #    前置：TTS provider 配置自检（跨平台可插拔 provider；未配置即明确报错，
    #    严禁静默降级到其它 provider）。自检在 build 实际使用的解释器（PY）里执行，
    #    避免「storyctl 的解释器」与「build_audio 的解释器」不一致导致误判。
    rc = tts_preflight(dry_run=dry)
    if rc != EXIT_OK:
        return rc
    rc = run_step("1/6 build_audio.py（逐句配音 + 时间轴回填）",
                  [PY, str(sd / "build_audio.py")], cwd=sd, dry_run=dry)
    if rc != EXIT_OK:
        _err(f"build_audio 失败（rc={rc}）—— 编排器侧故障")
        return EXIT_ORCH

    # 1.5) KB-A6 无意义停顿检测（真源 docs/产线规范.md v1.13.0）
    #      设计口径：**advisory 默认** —— 时间轴层给候选、音频层 silencedetect 交叉
    #      验证，落盘 qc/pause_audit.json；不改两段门禁判据、不默认阻断既有 story。
    #      --strict-pause 时问题项（rc=2）升级为拦截；--no-pause-audit 整步跳过。
    rc = run_kb_step("1.5/6 pause_audit.py（KB-A6 无意义停顿）",
                     KB_PAUSE_PY, sd,
                     ["--json", str(sd / "qc" / "pause_audit.json"), "--quiet"],
                     dry, skip=args.no_pause_audit, strict=args.strict_pause,
                     strict_hint="--strict-pause")
    if rc == EXIT_ORCH:
        _err("pause_audit 自身故障 —— 编排器侧故障")
        return EXIT_ORCH
    if rc == EXIT_DETECT:
        _err("build 在 KB-A6 无意义停顿检测被拦下（--strict-pause：rc=2）")
        return rc

    # 2) 生成 index.html + hyperframes.json
    rc = run_step("2/6 build_html.py（生成 index.html）",
                  [PY, str(sd / "build_html.py")], cwd=sd, dry_run=dry)
    if rc != EXIT_OK:
        _err(f"build_html 失败（rc={rc}）—— 编排器侧故障")
        return EXIT_ORCH

    # 2.5) KB-A2 外观一致性锚点漂移 + KB-A7 shot 级光照阈值（advisory 默认）
    #      首次运行（无 anchors.json）先调 build_html.py --emit-anchors 登记当前取值，
    #      再比对；未登记 story 不产生漂移（fail-safe，不改变既有 story 行为）。
    rc = run_kb_step("2.5/6 anchors_check.py（KB-A2 锚点漂移 + KB-A7 光照阈值）",
                     KB_ANCHORS_PY, sd,
                     ["--json", str(sd / "qc" / "anchors.json"), "--quiet"],
                     dry, skip=args.no_anchors, strict=args.strict_anchors,
                     strict_hint="--strict-anchors",
                     pre_register=[PY, str(sd / "build_html.py"), "--emit-anchors"],
                     pre_register_when=lambda: not (sd / "anchors.json").is_file())
    if rc == EXIT_ORCH:
        _err("anchors_check 自身故障 —— 编排器侧故障")
        return EXIT_ORCH
    if rc == EXIT_DETECT:
        _err("build 在 KB-A2/KB-A7 被拦下（--strict-anchors：rc=2）")
        return rc

    # 3) 段1：渲染前门禁（内联在「HTML 已产出 / 尚未渲染」这一节点）
    #    理由（契约 §五）：渲染前就拦，秒级成本 —— build 要的是「别把已知坏片子渲染两分半」。
    if args.no_gate:
        reason = args.no_gate_reason or (
            "storyctl build --no-gate：调试门禁误杀时手动跳过渲染前门禁（段1）"
        )
        p = sd / "qc" / "pre.json"
        _err(f"⚠ 已跳过段1 渲染前门禁（--no-gate）：{reason}")
        if dry:
            _err(f"  [dry-run] 跳过留痕将写入：{p}（未落盘）")
        else:
            p = write_gate_skip_report(sd, reason)
            _err(f"  跳过留痕已落盘：{p}")
        _log("3/6 段1 渲染前门禁 —— 已按 --no-gate 跳过")
    else:
        rc = run_pre_gate(sd, dry_run=dry)
        _log("3/6 段1 渲染前门禁 —— 完成")
        if rc != EXIT_OK:
            _err("build 在渲染前被拦下：未渲染任何帧（这正是段1 的价值）")
            return rc

    # 4) 渲染
    #    渲染精度默认启用（详见文件头 RENDER_RESOLUTION_* 注释）：未设 / 空 env
    #    时默认 portrait-4k 超采样；显式置白名单档位覆盖，置 off/none/1x 则完全不
    #    追加 --resolution（命令行与默认化前逐字节一致）。交付尺寸/编码仍由
    #    post_process 从合同真源收口。
    render_cmd = list(HYPERFRAMES) + ["render", "--fps", "30", "--quality", "high"]
    _raw = os.environ.get(RENDER_RESOLUTION_ENV)
    _explicit = _raw is not None and _raw.strip() != ""
    res = _raw.strip() if _explicit else RENDER_RESOLUTION_DEFAULT
    _origin = f"{RENDER_RESOLUTION_ENV}={res}" if _explicit else \
        f"默认启用（未设/空 {RENDER_RESOLUTION_ENV}）"
    if res.lower() in RENDER_RESOLUTION_OFF:
        _log(f"  渲染精度：显式关闭（{_origin}）—— 不追加 --resolution，"
             f"命令行与默认化前逐字节一致")
    else:
        if res not in RENDER_RESOLUTION_PRESETS:
            raise _UsageError(
                f"{RENDER_RESOLUTION_ENV}={res!r} 不在白名单 "
                f"{sorted(RENDER_RESOLUTION_PRESETS)}，也不属关闭档 "
                f"{list(RENDER_RESOLUTION_OFF)} —— 拒绝非登记档位"
            )
        render_cmd += ["--resolution", res]
        _log(f"  渲染精度：--resolution {res}（{RENDER_RESOLUTION_PRESETS[res]}；{_origin}）；"
             f"交付仍由 post_process 收口合同尺寸/编码（合同与门禁未改）")
    rc = run_step("4/6 hyperframes render", render_cmd + ["--output", str(render_mp4)],
                  cwd=sd, dry_run=dry)
    if rc != EXIT_OK:
        _err(f"hyperframes render 失败（rc={rc}）—— 编排器侧故障")
        return EXIT_ORCH

    # 5) 终合成 → douyin.mp4（不追加片尾，片尾交给第 6 步统一追加）
    rc = run_step("5/6 post_process.py（终合成 → douyin.mp4）",
                  [PY, str(POST_PROCESS_PY), str(render_mp4),
                   "-o", str(sd / PRODUCT_MAIN), "--no-epilogue"],
                  cwd=ROOT, dry_run=dry)
    if rc != EXIT_OK:
        _err(f"post_process 失败（rc={rc}）—— 编排器侧故障")
        return EXIT_ORCH

    # 6) 追加片尾 → douyin_epilogue.mp4
    rc = run_step("6/6 append_epilogue.py（追加片尾 → douyin_epilogue.mp4）",
                  [PY, str(APPEND_EPILOGUE_PY), str(sd), "--force"],
                  cwd=ROOT, dry_run=dry)
    if rc != EXIT_OK:
        _err(f"append_epilogue 失败（rc={rc}）—— 编排器侧故障")
        return EXIT_ORCH

    # 产物命名收口自检
    if not dry:
        missing = [p for p in (sd / PRODUCT_MAIN, sd / PRODUCT_EPILOGUE) if not p.is_file()]
        if missing:
            _err("产物缺失（命名收口要求 douyin.mp4 + douyin_epilogue.mp4）：")
            for p in missing:
                _err(f"  缺 {p}")
            return EXIT_ORCH

    _log(f"✔ build {name} 完成")
    _log(f"  产物: {sd / PRODUCT_MAIN}")
    _log(f"        {sd / PRODUCT_EPILOGUE}")
    if not dry:
        _log(f"  sha256({PRODUCT_MAIN}) = {_sha256(sd / PRODUCT_MAIN)}")
        _log(f"  sha256({PRODUCT_EPILOGUE}) = {_sha256(sd / PRODUCT_EPILOGUE)}")

    # 7) --qc 显式 opt-in：build 出片后串联两段门禁（默认不跑，默认行为不变）
    #    复用 _run_qc 同一实现 → 退出码语义/翻译点与 `storyctl qc` 完全一致。
    #    内容校验已在上游 0/6 做过（--no-check 时同样不重复校），故此处 check=False。
    if args.qc:
        rc = _run_qc(sd, name, dry_run=dry, check=False, semantic=args.semantic,
                     nondet=args.nondet, strict_kb=args.strict_kb)
        if rc != EXIT_OK:
            _err("build --qc：串联的两段门禁未通过（1=编排器侧故障 / 2=成片检出问题）")
            return rc
        _log(f"✔ build --qc {name} 完成：一条命令出片 + 两段门禁全绿")
        return EXIT_OK

    _log(f"  完整复审请跑：storyctl qc {name}（或 build --qc 串联）")
    return EXIT_OK


# ══════════════════════════════════════════════════════════════════════════
# 子命令：qc
# ══════════════════════════════════════════════════════════════════════════

def _run_qc(sd: Path, name: str, ref=None, baseline=None, store_baseline: bool = False,
            dry_run: bool = False, check: bool = False, semantic: bool = True,
            nondet: bool = True, strict_kb: bool = False) -> int:
    """两段门禁主体。`storyctl qc` 与 `storyctl build --qc` **共用同一实现**，
    退出码语义与 rc 翻译点完全一致（0 通过 / 1 编排器侧故障 / 2 成片检出问题）。

    check=True 时在段1 之前先跑内容层校验（qc 侧为显式 opt-in，保持 qc 原语义）。
    """
    _log(f"qc {name} · 两段门禁（段1 渲染前 + 段2 渲染后），可单独重跑")

    if check:
        rc = run_content_check(sd, dry_run=dry_run)
        if rc != EXIT_OK:
            _err("qc 内容校验未通过 —— 不进入段1/段2")
            return rc

    rc = run_pre_gate(sd, dry_run=dry_run)
    if rc != EXIT_OK:
        _err("qc 段1 未通过 —— 硬依赖成立，段2 不再执行（避免对旧片做无意义复审）")
        return rc

    rc = run_frame_audit(sd, ref=ref, baseline=baseline,
                         store_baseline=store_baseline, dry_run=dry_run)
    if rc != EXIT_OK:
        _err("qc 段2 未通过")
        return rc

    # KB 增强轴（v1.13.0，只增不改）：KB-A4 语义轴 + KB-A5 渲染非确定段单列。
    # advisory：不参与两段门禁判据，不改变本函数退出码语义（仍只由段1/段2 决定）。
    run_kb_axes(sd, name, dry_run=dry_run, semantic=semantic, nondet=nondet,
                strict=strict_kb)

    _log(f"✔ qc {name} 两段全绿" + ("（含 KB 增强轴走查）" if (semantic or nondet) else ""))
    _log(f"  段1 报告: {sd / 'qc' / 'pre.json'}")
    _log(f"  段2 报告: {sd / 'qc' / 'report.json'}")
    if semantic:
        _log(f"  KB-A4 报告: {sd / 'qc' / 'semantic_axis.json'}")
    if nondet:
        _log(f"  KB-A5 报告: {sd / 'qc' / 'nondeterminism.json'}")
    return EXIT_OK


def cmd_qc(args) -> int:
    name = args.name
    sd = resolve_story(name)
    if not (sd / "script.json").is_file():
        raise _UsageError(f"缺 script.json: {sd / 'script.json'}")
    return _run_qc(sd, name, ref=args.ref, baseline=args.baseline,
                   store_baseline=args.store_baseline, dry_run=args.dry_run,
                   check=args.check, semantic=args.semantic, nondet=args.nondet,
                   strict_kb=args.strict_kb)


# ══════════════════════════════════════════════════════════════════════════
# 子命令：catalog
# ══════════════════════════════════════════════════════════════════════════

def _scan_category(category: str) -> list:
    """config/selection_catalog.json 未落地（S4）时的文件系统启发式兜底。"""
    out = []
    if not STORY_ROOT.is_dir():
        return out
    for sd in sorted(p for p in STORY_ROOT.iterdir() if p.is_dir()):
        if category == "voice":
            hit = [f for f in ("narration.wav", "audio_combined.wav")
                   if (sd / f).is_file()] or [p.name for p in sd.glob("line_*.wav")][:1]
        elif category == "video":
            hit = [p.name for p in (sd / "renders").glob("*.mp4")][:1] or \
                  [p.name for p in sd.glob("douyin*.mp4")][:1]
        else:  # frontend
            hit = ["index.html"] if (sd / "index.html").is_file() else []
        if hit:
            out.append({"name": sd.name, "path": str(sd), "evidence": hit[0]})
    return out


def cmd_catalog(args) -> int:
    category = args.category
    entries, source = [], None

    if CATALOG_JSON.is_file():
        try:
            data = json.loads(CATALOG_JSON.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise _UsageError(f"catalog 配置解析失败: {CATALOG_JSON} —— {exc}")
        if not isinstance(data, dict):
            raise _UsageError(f"catalog 顶层须为对象: {CATALOG_JSON}")
        raw = data.get(category, [])
        if not isinstance(raw, list):
            raise _UsageError(f"catalog['{category}'] 须为数组")
        for item in raw:
            if isinstance(item, dict):
                entries.append({"name": item.get("name") or item.get("id") or "?",
                                "path": item.get("path", ""),
                                "evidence": item.get("note", "")})
            else:
                entries.append({"name": str(item), "path": "", "evidence": ""})
        source = str(CATALOG_JSON)
    else:
        _err(f"未找到 {CATALOG_JSON}（S4 落盘项）→ 回退到文件系统启发式扫描")
        entries = _scan_category(category)
        source = "文件系统扫描（启发式）"

    print(f"catalog: {category}   来源: {source}   命中: {len(entries)}")
    if not entries:
        print("  （空）")
        return EXIT_OK
    width = max(len(e["name"]) for e in entries)
    for e in entries:
        line = f"  {e['name']:<{width}}  {e['path']}"
        if e["evidence"]:
            line += f"   [{e['evidence']}]"
        print(line)
    return EXIT_OK


# ══════════════════════════════════════════════════════════════════════════
# CLI
# ══════════════════════════════════════════════════════════════════════════

def cmd_doctor(args) -> int:
    """跨平台自检（scripts/doctor.py 的编排器入口）。

    检查项：平台/架构、python 与工具链（ffmpeg/ffprobe/node/hyperframes/whisper-cli）、
    中文字体候选、不变量（只读 param_contract.json：1080×1920 / 30fps / 编码链）、
    TTS provider 配置。退出码沿用 doctor.py：0 = 无阻塞项，1 = 存在阻塞项。
    """
    cmd = [PY, str(SCRIPTS / "doctor.py")]
    if args.tts:
        cmd.append("--tts")
    if args.verbose:
        cmd.append("--verbose")
    return run_step("doctor.py（跨平台自检）", cmd, cwd=ROOT, dry_run=args.dry_run)


def build_parser() -> _Parser:
    ap = _Parser(
        prog="storyctl",
        description="抖音竖屏产线编排器（仅 HyperFrames per-story 路线）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="退出码：0=成功 / 1=编排器侧故障（含门禁用法错误）/ 2=成片检出问题\n"
               "产物命名收口：douyin.mp4 + douyin_epilogue.mp4",
    )
    sub = ap.add_subparsers(dest="command", metavar="{new,build,qc,catalog,doctor}",
                            parser_class=_Parser)

    p_new = sub.add_parser("new", help="脚手架：复制模板 story 并注入 STORY/name")
    p_new.add_argument("name", nargs="?", help="新 story 名（字母/数字/._-）；"
                                                "--list-kinds 时可不给")
    p_new.add_argument("--template", default=None,
                       help=f"模板 story（显式给出时优先于 --kind；默认由 --kind 解析，"
                            f"kind=default 时即 {DEFAULT_TEMPLATE}）")
    p_new.add_argument("--kind", default="default",
                       help="模板库 kind（真源 templates/registry.json；KB-A8 槽位化）。"
                            "default = 既有行为（模板 compositor-mac）")
    p_new.add_argument("--list-kinds", action="store_true",
                       help="只列出模板库 kind 后退出")
    p_new.set_defaults(func=cmd_new)

    p_build = sub.add_parser(
        "build",
        help="编排既有链路（末尾内联渲染前门禁）",
        epilog=f"渲染精度默认启用（2026-10-07 默认化）：未设/空 {RENDER_RESOLUTION_ENV} → "
               f"默认 {RENDER_RESOLUTION_DEFAULT}（超采样）；显式置 "
               f"{sorted(RENDER_RESOLUTION_PRESETS)} 之一则取该白名单档位（portrait = 1× "
               f"A/B 对照）；置 {list(RENDER_RESOLUTION_OFF)} 任一则不追加 --resolution，"
               f"命令行与默认化前逐字节一致；其它值拒绝执行",
    )
    p_build.add_argument("name", help="story 名")
    p_build.add_argument("--no-gate", action="store_true",
                         help="逃生口：跳过内联的段1 渲染前门禁（落盘报告须注明跳过原因）")
    p_build.add_argument("--no-gate-reason", default=None,
                         help="--no-gate 的跳过原因（写入 qc/pre.json）")
    p_build.add_argument("--check", dest="check", action="store_true", default=True,
                         help="内容层校验前置（**默认开启**，可 --no-check 跳过）："
                              "error 集＝title/scenes+lines/epilogue 文案/"
                              "voice_role+voice_engine/source + 占位符泄漏扫描；"
                              "warn 集＝facts/date/watermark（仅落报告不拦）")
    p_build.add_argument("--no-check", dest="check", action="store_false",
                         help="跳过内容层校验（不推荐；跳过即不在 build 里拦内容层缺陷）")
    p_build.add_argument("--no-deai", dest="no_deai", action="store_true",
                         help="跳过文案去 AI 味闸门（A9，默认开启但 advisory 不拦）")
    p_build.add_argument("--strict-deai", dest="strict_deai", action="store_true",
                         help="把 A9 文案去 AI 味闸门的 FAIL 级命中升级为拦截（退出码 2）")
    p_build.add_argument("--no-pause-audit", dest="no_pause_audit", action="store_true",
                         help="跳过 KB-A6 无意义停顿检测（默认开启，advisory 不拦）")
    p_build.add_argument("--strict-pause", dest="strict_pause", action="store_true",
                         help="把 KB-A6 停顿检出项升级为拦截（退出码 2）")
    p_build.add_argument("--no-anchors", dest="no_anchors", action="store_true",
                         help="跳过 KB-A2 锚点漂移 + KB-A7 光照阈值检查（默认开启，advisory）")
    p_build.add_argument("--strict-anchors", dest="strict_anchors", action="store_true",
                         help="把 KB-A2/KB-A7 漂移或越界升级为拦截（退出码 2）")
    p_build.add_argument("--no-semantic", dest="semantic", action="store_false", default=True,
                         help="--qc 串联时跳过 KB-A4 语义轴（ASR 回读）")
    p_build.add_argument("--no-nondet", dest="nondet", action="store_false", default=True,
                         help="--qc 串联时跳过 KB-A5 渲染非确定段单列")
    p_build.add_argument("--strict-kb", dest="strict_kb", action="store_true",
                         help="把 KB-A4/KB-A5 检出项升级为拦截（退出码 2）")
    p_build.add_argument("--qc", action="store_true",
                         help="显式 opt-in：build 出片后**串联**两段门禁（默认只跑 build "
                              "内联的段1，默认行为不变）。退出码语义同 storyctl qc")
    p_build.add_argument("--dry-run", action="store_true", help="只打印链路不执行")
    p_build.set_defaults(func=cmd_build)

    p_qc = sub.add_parser("qc", help="两段门禁（段1 渲染前 + 段2 渲染后），可单独重跑")
    p_qc.add_argument("name", help="story 名")
    p_qc.add_argument("--ref", default=None, help="A2/A3 参照片（同 story 已修复成片）")
    p_qc.add_argument("--baseline", default=None,
                      help="A0 同源基线（mp4 或 qc/baseline 目录）→ 透传 frame_audit；"
                           "A0 维持 opt-in，不传即不跑（build 前后 index.html sha256 必变）。"
                           "注：传 mp4 基线时 frame_audit 侧还需 --same-source 声明同源，"
                           "storyctl 只透传 --baseline，不代传 --same-source")
    p_qc.add_argument("--store-baseline", action="store_true",
                      help="存段2 被测件（douyin_epilogue.mp4）的 size/帧快照为 A6b 基线，"
                           "透传 frame_audit --store-baseline；需以原片 douyin.mp4 为锚点时"
                           "请直调 frame_audit（S3 收口修正前 qc 无此口）")
    p_qc.add_argument("--check", dest="check", action="store_true", default=False,
                      help="显式 opt-in：段1 之前先跑内容层校验（默认不跑，保持 qc 原语义；"
                           "build 侧 --check 才是默认开启）")
    p_qc.add_argument("--no-check", dest="check", action="store_false",
                      help="（默认即不跑，此口为显式对称）")
    p_qc.add_argument("--no-semantic", dest="semantic", action="store_false", default=True,
                      help="跳过 KB-A4 语义轴（ASR 回读；两段门禁判据不受影响）")
    p_qc.add_argument("--no-nondet", dest="nondet", action="store_false", default=True,
                      help="跳过 KB-A5 渲染非确定段单列")
    p_qc.add_argument("--strict-kb", dest="strict_kb", action="store_true",
                      help="把 KB-A4/KB-A5 检出项升级为拦截（退出码 2）")
    p_qc.add_argument("--dry-run", action="store_true", help="只打印链路不执行")
    p_qc.set_defaults(func=cmd_qc)

    p_cat = sub.add_parser("catalog", help="列出 voice|video|frontend 选材目录")
    p_cat.add_argument("category", choices=["voice", "video", "frontend"])
    p_cat.set_defaults(func=cmd_catalog)

    p_doc = sub.add_parser("doctor", help="跨平台自检：工具链/字体/不变量/TTS provider")
    p_doc.add_argument("--tts", action="store_true",
                       help="只跑 TTS provider 配置自检（跨平台可插拔 provider 的配置体检）")
    p_doc.add_argument("--verbose", action="store_true", help="打印每个工具命中的路径明细")
    p_doc.add_argument("--dry-run", action="store_true", help="只打印命令不执行")
    p_doc.set_defaults(func=cmd_doctor)

    return ap


def main(argv=None) -> int:
    ap = build_parser()
    args = ap.parse_args(argv)
    if not getattr(args, "command", None):
        ap.print_help(sys.stderr)
        _err("缺少子命令，可选：new / build / qc / catalog / doctor")
        return EXIT_ORCH
    try:
        return args.func(args)
    except _UsageError as exc:
        _err(str(exc))
        return EXIT_ORCH
    except KeyboardInterrupt:
        _err("被用户中断")
        return EXIT_ORCH
    except Exception as exc:  # noqa: BLE001 —— 编排器侧故障统一收敛为 1
        _err(f"未预期异常（编排器侧故障）: {type(exc).__name__}: {exc}")
        return EXIT_ORCH


if __name__ == "__main__":
    sys.exit(main())
