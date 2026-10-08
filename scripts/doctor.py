#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
doctor.py —— 首次运行 / 故障排查自检（macOS / Linux / Windows 通用）

用法
----
    python3 scripts/doctor.py          # 全量自检
    python3 scripts/doctor.py --tts    # 只看 TTS provider
    python3 scripts/doctor.py --json   # 机器可读输出

退出码：0 = 全部通过（或有非阻塞 WARN）；1 = 存在 FAIL（阻塞项）。
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(_HERE)
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import platform_env  # noqa: E402
import tts_provider  # noqa: E402

PASS, WARN, FAIL = "PASS", "WARN", "FAIL"


def _run(cmd, timeout=20):
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout,
                           env=platform_env.tool_env())
        return p.returncode, (p.stdout or p.stderr or "").strip()
    except Exception as exc:  # noqa: BLE001
        return 1, f"{type(exc).__name__}: {exc}"


def check_python():
    v = sys.version_info
    ok = v >= (3, 10)
    msg = f"Python {v.major}.{v.minor}.{v.micro}（要求 >= 3.10）"
    return (PASS if ok else FAIL), msg


def check_tool(name, version_args=("--version",), optional=False):
    path = platform_env.find_tool(name)
    if not path:
        note = "（可选，缺失时卡拉OK字幕/云渲染会不可用）" if optional else ""
        return (WARN if optional else FAIL), f"{name}: 未找到{note}；安装见 docs/DEPLOY.md"
    rc, out = _run([path, *version_args])
    ver = out.splitlines()[0] if out else ""
    return PASS, f"{name}: {path}  {ver[:80]}"


def check_hyperframes():
    path = platform_env.find_tool("hyperframes")
    if path:
        rc, out = _run([path, "--version"])
        return PASS, f"hyperframes: {path}  {out.splitlines()[0][:60] if out else ''}"
    npx = platform_env.find_tool("npx")
    if npx:
        return WARN, ("hyperframes 未全局安装；可用 `npx hyperframes render ...` 兜底，"
                      "或 `npm i -g hyperframes`（见 docs/DEPLOY.md）")
    return FAIL, "hyperframes 未找到，且 node/npx 不可用；请先安装 Node.js LTS"


def check_fonts():
    f = platform_env.require_font_file  # noqa: F841  (保持语义清晰)
    try:
        path = platform_env.find_font_file()
    except Exception as exc:  # noqa: BLE001
        return FAIL, str(exc)
    if not path:
        return FAIL, ("未找到中文字体；Debian/Ubuntu: sudo apt install fonts-noto-cjk；"
                      "或 export FONT_FILE=/绝对/路径/字体.ttc")
    return PASS, f"字体: {path}（字幕族名 {platform_env.font_family()}）"


def check_tts():
    try:
        name = tts_provider.provider_name()
    except tts_provider.TtsConfigError as exc:
        return FAIL, str(exc)
    ok, why = tts_provider.probe(name=name)
    return (PASS if ok else FAIL), f"TTS provider={name}: {why}"


def check_invariants():
    """不变量校验：只读取、不修改（1080×1920 / 30fps / 编码链）。"""
    p = os.path.join(REPO_ROOT, "config", "param_contract.json")
    if not os.path.isfile(p):
        return WARN, f"缺少 {os.path.relpath(p, REPO_ROOT)}，跳过不变量校验"
    with open(p, encoding="utf-8") as f:
        cfg = json.load(f)
    chain = (cfg.get("toolchain_pins") or {}).get("encoder_chain") or {}
    fps = res = None
    for fld in cfg.get("fields") or []:
        exp = fld.get("expected")
        if isinstance(exp, dict) and exp.get("resolution"):
            res = exp["resolution"]
        elif fld.get("unit", "").startswith("整数 (fps)"):
            fps = exp
        elif fld.get("unit", "").startswith("整数") and exp in (24, 25, 30, 60) and fps is None:
            fps = exp
    facts = [f"分辨率={res or '未声明'}", f"fps={fps if fps is not None else '未声明'}"]
    for k in ("profile", "level", "pix_fmt", "video_rate_control", "gop_frames"):
        if chain.get(k) is not None:
            facts.append(f"{k}={chain[k]}")
    bad = []
    if res and res != "1080x1920":
        bad.append(f"分辨率不变量被改动：{res} != 1080x1920")
    if fps is not None and int(fps) != 30:
        bad.append(f"fps 不变量被改动：{fps} != 30")
    detail = "不变量（只读）: " + ", ".join(str(x) for x in facts)
    if bad:
        return FAIL, detail + " | " + "；".join(bad)
    return PASS, detail


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tts", action="store_true", help="只检查 TTS provider")
    ap.add_argument("--json", action="store_true", help="JSON 输出")
    args = ap.parse_args()

    results = []
    if not args.tts:
        results.append(("环境", check_python()))
        results.append(("环境", (PASS, platform_env.describe())))
        for t, ver in (("ffmpeg", ("-version",)), ("ffprobe", ("-version",)),
                       ("node", ("--version",)), ("npx", ("--version",))):
            results.append(("工具链", check_tool(t, ver)))
        results.append(("工具链", check_tool("whisper-cli", ("--help",), optional=True)))
        results.append(("工具链", check_hyperframes()))
        results.append(("字体", check_fonts()))
        results.append(("不变量", check_invariants()))
    results.append(("TTS", check_tts()))

    if args.json:
        print(json.dumps([{"group": g, "status": s, "detail": d} for g, (s, d) in results],
                         ensure_ascii=False, indent=2))
    else:
        width = max(len(g) for g, _ in results)
        print(f"hyperframes-douyin-pipeline 自检  ({platform_env.platform_name()})")
        print("-" * 72)
        for g, (s, d) in results:
            print(f"[{s:4}] {g:<{width}}  {d}")
        print("-" * 72)
        fails = [d for _, (s, d) in results if s == FAIL]
        print("结果：" + ("全部通过" if not fails else f"{len(fails)} 项阻塞"))
    return 1 if any(s == FAIL for _, (s, _) in results) else 0


if __name__ == "__main__":
    sys.exit(main())
