#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
resource_peaks.py —— 分阶段统一内存（RSS）峰值记录

所属产线：hyperframes 竖屏短视频产线（部署根由 PIPELINE_HOME / 仓库位置决定）
来源思路：AI-Film-Studio (qpzRm) 的「峰值显存分阶段记录法」
  —— 决定 OOM 风险的是单阶段峰值，整段均值会把它抹平；
     分阶段还能定位是哪一段触发了降级。

本机适配（关键前提）
------------------
  Mac M1 Pro 无独立显存，不存在 VRAM；等价物是「统一内存」。
  因此本脚本把思路落成：按阶段采样【进程树 RSS 峰值】，并记录
  - 每阶段峰值 / 均值 / 采样数 / 持续时长 / 峰值出现时刻
  - 整段峰值（含落在哪个阶段）
  - 是否顶到设定上限（--rss-limit）→ 降级风险标记
  - 被监控命令输出里出现的降级/OOM 关键词 → 降级证据
  统一内存被压缩（compressed memory）时 RSS 会低估真实压力，
  这是本适配相对显存口径的已知偏差，见报告「局限」。

阶段标记
--------
  被监控命令向 stdout 打印 `#STAGE <name>` 即切换到该阶段，
  例如：  bash -c 'echo "#STAGE loading"; ffmpeg ...; echo "#STAGE composing"; ffmpeg ...'

用法
----
  python3 scripts/resource_peaks.py monitor --name render_1080x1920 --rss-limit 24GB \\
      -- bash -c 'echo "#STAGE loading"; ffmpeg -v error -i in.mp4 -f null -; ...'

  python3 scripts/resource_peaks.py show --profile reports/peaks/<name>.json
  python3 scripts/resource_peaks.py compare --baseline a.json --current b.json   # 阶段峰值对照

退出码：0 = 被监控命令成功且未超上限；2 = 超上限（降级风险）；被监控命令非零则透传其码
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import platform
import re
import subprocess
import sys
import threading
import time
from datetime import datetime

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DEFAULT = os.path.dirname(SCRIPT_DIR)
PROFILE_DIR = os.path.join(ROOT_DEFAULT, "reports", "peaks")

DOWNGRADE_KEYWORDS = [
    "downgrade", "fallback", "out of memory", "oom", "killed", "low memory",
    "swapping", "降级", "回退", "内存不足",
]

SIZE_UNITS = [("KIB", 1024), ("MIB", 1024 ** 2), ("GIB", 1024 ** 3),
              ("KB", 1024), ("MB", 1024 ** 2), ("GB", 1024 ** 3),
              ("K", 1024), ("M", 1024 ** 2), ("G", 1024 ** 3), ("B", 1)]


def parse_size(s):
    txt = str(s).strip().upper()
    for unit, mult in SIZE_UNITS:
        if txt.endswith(unit):
            return int(float(txt[: -len(unit)]) * mult)
    return int(float(txt))


def human(n):
    if n is None:
        return "n/a"
    n = float(n)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(n) < 1024 or unit == "TB":
            return f"{n:.1f}{unit}" if unit != "B" else f"{int(n)}B"
        n /= 1024


def total_memory_bytes():
    try:
        return int(subprocess.run(["sysctl", "-n", "hw.memsize"], capture_output=True, text=True).stdout.strip())
    except Exception:
        return None


def machine_info():
    info = {
        "platform": platform.platform(),
        "machine": platform.machine(),
        "total_memory_bytes": total_memory_bytes(),
        "note": "Mac 统一内存：无独立显存，用进程树 RSS 峰值近似显存峰值",
    }
    try:
        info["cpu"] = subprocess.run(["sysctl", "-n", "machdep.cpu.brand_string"],
                                     capture_output=True, text=True).stdout.strip()
    except Exception:
        info["cpu"] = None
    return info


def tree_rss_bytes(root_pid):
    """返回 root_pid 及其所有子孙进程的 RSS 合计（字节）。"""
    try:
        out = subprocess.run(["ps", "-axo", "pid=,ppid=,rss="], capture_output=True, text=True).stdout
    except Exception:
        return None
    children = {}
    rss = {}
    for line in out.splitlines():
        parts = line.split()
        if len(parts) < 3:
            continue
        try:
            pid, ppid, kb = int(parts[0]), int(parts[1]), int(parts[2])
        except ValueError as exc:
            logging.getLogger(__name__).warning("resource_peaks 解析 ps 行失败 %r: %r", parts, exc)
            continue
        rss[pid] = kb * 1024
        children.setdefault(ppid, []).append(pid)
    seen, stack, total = set(), [root_pid], 0
    while stack:
        pid = stack.pop()
        if pid in seen:
            continue
        seen.add(pid)
        total += rss.get(pid, 0)
        stack.extend(children.get(pid, []))
    return total


def cmd_monitor(args):
    if not args.command:
        print("[error] 缺少被监控命令，用法：monitor -- <command>", file=sys.stderr)
        return 1

    interval = args.interval
    limit = parse_size(args.rss_limit) if args.rss_limit else None
    stage_lock = threading.Lock()
    current_stage = {"name": args.initial_stage}
    samples = []
    stop = threading.Event()

    print("=" * 96)
    print("分阶段统一内存（RSS）峰值记录")
    print("=" * 96)
    print(f"任务名   : {args.name}")
    print(f"阶段标记 : 被监控命令向 stdout 打印 '#STAGE <name>' 即切换阶段")
    print(f"采样间隔 : {interval}s    上限: {human(limit) if limit else '未设'}")
    print(f"命令     : {' '.join(args.command)}")
    print("-" * 96)

    t0 = time.time()
    proc = subprocess.Popen(args.command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            text=True, bufsize=1, cwd=args.root, errors="replace")

    def sampler():
        while not stop.is_set():
            with stage_lock:
                st = current_stage["name"]
            rss = tree_rss_bytes(proc.pid)
            samples.append({"t": round(time.time() - t0, 3), "stage": st, "rss_bytes": rss})
            stop.wait(interval)

    th = threading.Thread(target=sampler, daemon=True)
    th.start()

    stdout_lines = []
    for line in proc.stdout:
        raw = line.rstrip("\n")
        stdout_lines.append(raw)
        m = re.match(r"^#STAGE\s+(.+?)\s*$", raw)
        if m:
            with stage_lock:
                current_stage["name"] = m.group(1)
            print(f"  [stage] → {m.group(1)}  (t={time.time() - t0:.2f}s, rss={human(samples[-1]['rss_bytes']) if samples else 'n/a'})")
    proc.wait()
    stop.set()
    th.join(timeout=2)

    exit_code = proc.returncode
    if exit_code != 0:
        print(f"[warn] 被监控命令退出码 {exit_code}，最后 8 行输出：")
        for line in stdout_lines[-8:]:
            print(f"         | {line[:160]}")

    # ── 汇总 ──
    stage_order, per_stage = [], {}
    for s in samples:
        if s["stage"] not in per_stage:
            per_stage[s["stage"]] = {"peak": 0, "peak_at": None, "sum": 0, "n": 0, "first": s["t"], "last": s["t"]}
            stage_order.append(s["stage"])
        bucket = per_stage[s["stage"]]
        v = s["rss_bytes"] or 0
        bucket["sum"] += v
        bucket["n"] += 1
        bucket["last"] = s["t"]
        if v > bucket["peak"]:
            bucket["peak"] = v
            bucket["peak_at"] = s["t"]

    peak_overall = {"bytes": 0, "stage": None, "at_sec": None}
    for s in samples:
        v = s["rss_bytes"] or 0
        if v > peak_overall["bytes"]:
            peak_overall = {"bytes": v, "stage": s["stage"], "at_sec": s["t"]}

    flags = []
    for line in stdout_lines:
        low = line.lower()
        for kw in DOWNGRADE_KEYWORDS:
            if kw in low:
                flags.append(f"{kw} :: {line[:120]}")

    exceeded = bool(limit and peak_overall["bytes"] and peak_overall["bytes"] > limit)

    print("-" * 96)
    print(f"{'阶段':<22}{'峰值RSS':>12}{'均值RSS':>12}{'样本':>7}{'时长(s)':>10}  峰值时刻")
    for st in stage_order:
        b = per_stage[st]
        print(f"{st:<22}{human(b['peak']):>12}{human(b['sum'] / max(b['n'], 1)):>12}"
              f"{b['n']:>7}{b['last'] - b['first']:>10.2f}  t={b['peak_at']}s")
    print("-" * 96)
    print(f"整段峰值 : {human(peak_overall['bytes'])} @ 阶段「{peak_overall['stage']}」"
          f"  t={peak_overall['at_sec']}s")
    if limit:
        print(f"上限判定 : {human(peak_overall['bytes'])} / {human(limit)}"
              f" = {(peak_overall['bytes'] / limit * 100):.1f}% → "
              f"{'超上限，降级风险高' if exceeded else '未顶到上限'}")
    print(f"降级证据 : {'命中关键词 ' + str(len(flags)) + ' 处' if flags else '未在命令输出中命中降级/OOM 关键词'}")
    for f in flags[:5]:
        print(f"           - {f}")
    print(f"命令退出码: {exit_code}")
    if stage_order == [args.initial_stage]:
        print("[warn] 只采到单一阶段：被监控命令没有打印 '#STAGE <name>' 标记，分阶段定位不可用")
    print("=" * 96)

    profile = {
        "profile_version": "1.0.0",
        "name": args.name,
        "sampled_at": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        "command": " ".join(args.command),
        "interval_sec": interval,
        "machine": machine_info(),
        "rss_limit_bytes": limit,
        "stage_order": stage_order,
        "stages": [{
            "stage": st,
            "peak_bytes": per_stage[st]["peak"],
            "peak_at_sec": per_stage[st]["peak_at"],
            "mean_bytes": int(per_stage[st]["sum"] / max(per_stage[st]["n"], 1)),
            "samples": per_stage[st]["n"],
            "duration_sec": round(per_stage[st]["last"] - per_stage[st]["first"], 3),
        } for st in stage_order],
        "peak_overall": peak_overall,
        "degradation": {
            "rss_limit_exceeded": exceeded,
            "ratio_to_limit": round(peak_overall["bytes"] / limit, 4) if (limit and peak_overall["bytes"]) else None,
            "keyword_flags": flags,
            "note": "统一内存压缩场景下 RSS 会低估真实内存压力，命中 0 关键词不等于没降级",
        },
        "command_exit_code": exit_code,
        "command_output_tail": stdout_lines[-200:],
        "raw_samples": samples if args.keep_samples else [],
    }
    os.makedirs(PROFILE_DIR, exist_ok=True)
    out = args.out or os.path.join(PROFILE_DIR, f"{args.name}.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(profile, f, ensure_ascii=False, indent=2)
    print(f"[archive] 分阶段峰值档案：{out}")

    if exit_code != 0:
        return exit_code
    return 2 if exceeded else 0


def _load(path):
    if not os.path.isabs(path):
        path = os.path.join(ROOT_DEFAULT, path)
    if not os.path.isfile(path):
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def cmd_show(args):
    p = _load(args.profile)
    if not p:
        print(f"[error] 档案不存在：{args.profile}", file=sys.stderr)
        return 1
    print(f"任务 {p['name']}  采样于 {p['sampled_at']}  间隔 {p['interval_sec']}s")
    print(f"机器 {p['machine'].get('cpu')}  统一内存 {human(p['machine'].get('total_memory_bytes'))}")
    print(f"命令 {p['command']}")
    for s in p["stages"]:
        print(f"  {s['stage']:<22} peak {human(s['peak_bytes']):>10}  mean {human(s['mean_bytes']):>10}"
              f"  {s['samples']} 样本  {s['duration_sec']}s")
    po = p["peak_overall"]
    print(f"  整段峰值 {human(po['bytes'])} @ {po['stage']} (t={po['at_sec']}s)")
    d = p["degradation"]
    print(f"  降级：超上限={d['rss_limit_exceeded']}  关键词命中={len(d['keyword_flags'])}")
    return 0


def cmd_compare(args):
    a, b = _load(args.baseline), _load(args.current)
    if not a or not b:
        print("[error] 档案缺失", file=sys.stderr)
        return 1
    sa = {s["stage"]: s for s in a["stages"]}
    sb = {s["stage"]: s for s in b["stages"]}
    print("=" * 88)
    print(f"阶段峰值对照：{a['name']} → {b['name']}")
    print("=" * 88)
    print(f"{'阶段':<22}{'基线峰值':>12}{'当前峰值':>12}{'变化':>14}")
    for st in [s["stage"] for s in b["stages"]]:
        pa = sa.get(st, {}).get("peak_bytes")
        pb = sb.get(st, {}).get("peak_bytes")
        if pa and pb:
            print(f"{st:<22}{human(pa):>12}{human(pb):>12}{(pb - pa) / pa * 100:>13.1f}%")
        else:
            print(f"{st:<22}{human(pa) if pa else 'n/a':>12}{human(pb) if pb else 'n/a':>12}{'新增/缺失':>14}")
    print("=" * 88)
    return 0


def main(argv=None):
    p = argparse.ArgumentParser(description="分阶段统一内存(RSS)峰值记录")
    p.add_argument("--root", default=ROOT_DEFAULT)
    sub = p.add_subparsers(dest="cmd", required=True)

    mp = sub.add_parser("monitor", help="监控一条命令，按 #STAGE 标记分阶段采峰值")
    mp.add_argument("--name", required=True)
    mp.add_argument("--interval", type=float, default=0.25)
    mp.add_argument("--rss-limit", default=None, help="统一内存上限，如 24GB；超过判降级风险")
    mp.add_argument("--initial-stage", default="start")
    mp.add_argument("--out", default=None)
    mp.add_argument("--keep-samples", action="store_true", help="把逐次采样也写进档案（默认不写，避免档案过大）")
    mp.add_argument("command", nargs=argparse.REMAINDER, help="-- 之后的被监控命令")
    mp.set_defaults(func=cmd_monitor)

    sp = sub.add_parser("show", help="查看档案")
    sp.add_argument("--profile", required=True)
    sp.set_defaults(func=cmd_show)

    cp = sub.add_parser("compare", help="两份档案的阶段峰值对照")
    cp.add_argument("--baseline", required=True)
    cp.add_argument("--current", required=True)
    cp.set_defaults(func=cmd_compare)

    args = p.parse_args(argv)
    if args.cmd == "monitor" and args.command and args.command[0] == "--":
        args.command = args.command[1:]
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
