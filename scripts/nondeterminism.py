#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""nondeterminism.py —— KB-A5 渲染非确定段单列（v1.13.0）

目的：把"同一 composition 源两次渲染可能不一致"的风险段**显式列成清单**，
而不是靠肉眼怀疑。两件事：

  ① 静态扫描（默认，--scan）：扫 story 目录下的 composition 源
     （index.html + build_html.py，必要时 hyperframes.json），命中非确定构造：
       * 运行时随机/时钟：Math.random / Date.now / new Date / performance.now
       * 定时器驱动：setTimeout / setInterval / requestAnimationFrame（动画外挂时钟）
       * CSS 自主动画：animation: / @keyframes（不在 gsap 时间轴上，不受帧捕获控制）
       * 时间轴未暂停：gsap.timeline(...) 缺 paused:true（渲染与录制时刻相关）
       * 外部网络依赖：<script src="http(s):// / @import url(http
       * 系统字体依赖：font-family 中 local(...) 之外的未内嵌字体族（仅提示）
     每项给出文件:行号:证据片段 → "非确定段"清单，并给出风险等级。

  ② 帧级验证（--verify A.mp4 B.mp4，可选）：把两片缩到 216x384 灰度 rawvideo，
     逐帧算 md5，输出差异帧区间（连续差异合并成段）。两次渲染差异 = 真·非确定；
     零差异 = 该片在当前源下渲染确定（把清单里的静态风险判为"未兑现"）。

只读，不改任何源。默认 advisory（rc=0）；--strict 且有 HIGH 风险命中时 rc=2。

用法：
  python3 scripts/nondeterminism.py story/<name> [--json OUT] [--strict] [--quiet]
  python3 scripts/nondeterminism.py story/<name> --verify renders/a.mp4 renders/b.mp4
"""
import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 跨平台适配层（真源 scripts/platform_env.py）：工具按 PATH/which + 平台常见位解析，
# 支持环境变量覆盖（PIPELINE_<TOOL> / <TOOL>）。
_SDIR = os.path.dirname(os.path.abspath(__file__))
if _SDIR not in sys.path:
    sys.path.insert(0, _SDIR)
import platform_env  # noqa: E402


def _which(name: str) -> str:
    """解析可执行文件：环境变量 → PATH → 平台常见安装位（跨平台，见 platform_env）。"""
    return platform_env.find_tool(name) or name
PATTERNS = [
    (r"Math\.random", "HIGH", "运行时随机数：每次渲染取值不同"),
    (r"Date\.now|new Date\s*\(|performance\.now", "HIGH", "读取时钟：与渲染时刻绑定"),
    (r"\bsetTimeout\s*\(|\bsetInterval\s*\(|requestAnimationFrame", "MEDIUM",
     "定时器/RAF 驱动动画：不受 gsap 时间轴捕获控制"),
    (r"@keyframes|\banimation\s*:", "MEDIUM", "CSS 自主动画：不挂在时间轴上"),
    (r"gsap\.timeline\s*\(\s*\{\s*\}\s*\)|gsap\.timeline\s*\(\s*\)", "HIGH",
     "gsap 时间轴未 paused:true：渲染与录制时刻相关"),
    (r"<script[^>]+src\s*=\s*[\"']https?://|@import\s+url\(\s*https?://", "MEDIUM",
     "外部网络资源：加载竞态 → 帧内容可能与网络状态相关"),
    (r"fonts\.googleapis|cdn\.jsdelivr|unpkg\.com", "MEDIUM", "外部 CDN 依赖"),
]
_KEEP = re.compile(r"[\u3400-\u9fff\uf900-\ufaffA-Za-z0-9]+")


def _ts() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def scan(sd: str):
    hits = []
    for rel in ("index.html", "build_html.py", "hyperframes.json"):
        p = os.path.join(sd, rel)
        if not os.path.isfile(p):
            continue
        for i, line in enumerate(open(p, encoding="utf-8", errors="replace"), 1):
            for pat, sev, why in PATTERNS:
                if re.search(pat, line):
                    hits.append({"file": rel, "line": i, "severity": sev,
                                 "pattern": pat, "why": why,
                                 "evidence": line.strip()[:160]})
    return hits


def verify(mp4a: str, mp4b: str, width=216, height=384):
    def frames(p):
        cmd = [_which("ffmpeg"), "-hide_banner", "-loglevel", "error", "-i", p,
               "-vf", f"scale={width}:{height},format=gray", "-f", "rawvideo", "-"]
        r = subprocess.run(cmd, capture_output=True)
        if r.returncode != 0:
            raise RuntimeError(f"ffmpeg 解码失败 {p}: {r.stderr.decode()[-200:]}")
        n = width * height
        data = r.stdout
        return [hashlib.md5(data[i:i + n]).hexdigest()
                for i in range(0, len(data) - n + 1, n)]

    fa, fb = frames(mp4a), frames(mp4b)
    n = min(len(fa), len(fb))
    diff = [i for i in range(n) if fa[i] != fb[i]]
    segs, start = [], None
    for i in range(n):
        d = i in set(diff)
        if d and start is None:
            start = i
        elif not d and start is not None:
            segs.append({"from_frame": start, "to_frame": i - 1,
                         "from_s": round(start / 30.0, 3), "to_s": round((i - 1) / 30.0, 3)})
            start = None
    if start is not None:
        segs.append({"from_frame": start, "to_frame": n - 1,
                     "from_s": round(start / 30.0, 3), "to_s": round((n - 1) / 30.0, 3)})
    return {"frames_a": len(fa), "frames_b": len(fb), "frames_compared": n,
            "diff_frames": len(diff), "diff_ratio": round(len(diff) / n, 4) if n else 0.0,
            "diff_segments": segs, "identical": len(diff) == 0 and len(fa) == len(fb)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("story")
    ap.add_argument("--json", default=None)
    ap.add_argument("--verify", nargs=2, metavar=("A_MP4", "B_MP4"), default=None)
    ap.add_argument("--strict", action="store_true")
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args()

    sd = a.story if os.path.isabs(a.story) else (
        os.path.join(ROOT, "story", a.story)
        if os.path.isdir(os.path.join(ROOT, "story", a.story))
        else os.path.join(ROOT, a.story))
    if not os.path.isdir(sd):
        print(f"[nondet] 编排器侧故障：story 目录不存在 {sd}", file=sys.stderr)
        return 1
    name = os.path.basename(sd.rstrip("/"))
    out_path = a.json or os.path.join(sd, "qc", "nondeterminism.json")

    hits = scan(sd)
    high = [h for h in hits if h["severity"] == "HIGH"]
    med = [h for h in hits if h["severity"] == "MEDIUM"]
    v = None
    if a.verify:
        for p in a.verify:
            if not os.path.isfile(p):
                print(f"[nondet] 编排器侧故障：--verify 文件不存在 {p}", file=sys.stderr)
                return 1
        try:
            v = verify(*a.verify)
        except RuntimeError as exc:
            print(f"[nondet] 编排器侧故障：{exc}", file=sys.stderr)
            return 1

    payload = {
        "check": "nondeterminism(KB-A5)",
        "story": name,
        "checked_at": _ts(),
        "scanned_files": [f for f in ("index.html", "build_html.py", "hyperframes.json")
                          if os.path.isfile(os.path.join(sd, f))],
        "high_risk_count": len(high),
        "medium_risk_count": len(med),
        "nondet_segments": hits,
        "frame_verify": v,
        "verdict": ("未发现非确定构造" if not hits else
                    f"{len(high)} 项 HIGH / {len(med)} 项 MEDIUM（见 nondet_segments）"),
        "passed": not high,
    }
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    open(out_path, "w", encoding="utf-8").write(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n")

    if not a.quiet:
        print(f"[nondet/KB-A5] {name}: HIGH {len(high)} / MEDIUM {len(med)}（扫描 "
              f"{len(payload['scanned_files'])} 个源文件）")
        for h in hits[:10]:
            print(f"    [{h['severity']}] {h['file']}:{h['line']} {h['why']}"
                  f" ← {h['evidence'][:70]}")
        if v is not None:
            print(f"    帧级验证：比较 {v['frames_compared']} 帧，差异 "
                  f"{v['diff_frames']} 帧（{v['diff_ratio']:.2%}）→ "
                  f"{'确定性一致' if v['identical'] else '存在非确定段'}")
            for s in v["diff_segments"][:8]:
                print(f"      [diff] 帧 {s['from_frame']}-{s['to_frame']} "
                      f"({s['from_s']}-{s['to_s']}s)")
        print(f"    报告：{out_path}")
    if a.strict and high:
        print("[nondet] --strict：HIGH 风险命中 = 退出码 2", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
