#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""anchors_check.py —— KB-A2 外观一致性锚点漂移检查 + KB-A7 shot 级光照阈值检查（v1.13.0）

统一口径（本机 hyperframes 竖屏产线，部署根由 PIPELINE_HOME / 仓库位置决定）：
  * 真源：story/<name>/anchors.json（由 build_html.py --emit-anchors 首次登记）
  * 被检对象：story/<name>/index.html 内由 build_html.py 写入的一行注释
        <!-- ANCHOR-SNAPSHOT {...} -->
    该快照**从已生成的 CSS/HTML 实际取值解析**（不是复述脚本常量）。
  * 比对：anchors.json["anchors"] 与快照逐键比对，任一键取值不等 = 漂移（drift）。
  * KB-A7：锚点表 light_thresholds 约束 shot 级光照覆写幅度（默认 lift Δ≤0.04，
        gain Δ≤0.10）；超幅 = 光照越界（light_out_of_range）。

注：本检查**只读**，不修改任何 composition 源；不参与两段门禁判据，默认 advisory。

退出码：
  0  通过（或 advisory 有告警）
  1  编排器侧故障（缺 index.html / 缺快照 / anchors.json 不可解析 / 用法错误）
  2  检出漂移或光照越界（仅在 --strict 下升级为拦截；默认不返回本码）

用法：
  python3 scripts/anchors_check.py story/<name> [--anchors PATH] [--json OUT]
          [--strict] [--quiet]
"""
import argparse
import json
import os
import re
import sys
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IMAGE_TYPES = {"theme", "theme_deep", "theme_mid", "card_bg_rgb", "vis_base"}


def _ts() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def load_snapshot(index_html: str):
    txt = open(index_html, encoding="utf-8").read()
    m = re.search(r"<!-- ANCHOR-SNAPSHOT (\{.*?\}) -->", txt, re.S)
    if not m:
        return None, "index.html 内未找到 ANCHOR-SNAPSHOT 注释（build_html.py 未接入 A2？）"
    try:
        return json.loads(m.group(1)), None
    except ValueError as exc:
        return None, f"ANCHOR-SNAPSHOT 注释不是合法 JSON: {exc}"


def _drift(expect, got):
    """取值比对：字典递归、字符串忽略大小写、数值容差 1e-9（浮点回读）。"""
    if isinstance(expect, dict) and isinstance(got, dict):
        out = []
        for k in expect:
            if k not in got:
                out.append({"key": k, "expected": expect[k], "actual": "<缺失>"})
            else:
                sub = _drift(expect[k], got[k])
                for s in sub:
                    s["key"] = f"{k}.{s['key']}"
                out += sub
        return out
    if isinstance(expect, str) and isinstance(got, str):
        if expect.lower() != got.lower():
            return [{"key": "", "expected": expect, "actual": got}]
        return []
    if isinstance(expect, (int, float)) and isinstance(got, (int, float)):
        if abs(float(expect) - float(got)) > 1e-9:
            return [{"key": "", "expected": expect, "actual": got}]
        return []
    if expect != got:
        return [{"key": "", "expected": expect, "actual": got}]
    return []


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("story", help="story 目录（story/<name>）或 name")
    ap.add_argument("--anchors", default=None, help="锚点表路径（默认 <story>/anchors.json）")
    ap.add_argument("--json", default=None, help="报告落盘路径（默认 <story>/qc/anchors.json）")
    ap.add_argument("--strict", action="store_true", help="漂移/越界升级为拦截（rc=2）")
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args()

    sd = a.story if os.path.isabs(a.story) else (
        os.path.join(ROOT, "story", a.story)
        if os.path.isdir(os.path.join(ROOT, "story", a.story))
        else os.path.join(ROOT, a.story))
    if not os.path.isdir(sd):
        print(f"[anchors] 用法错误：story 目录不存在 {sd}", file=sys.stderr)
        return 1
    name = os.path.basename(sd.rstrip("/"))
    index_html = os.path.join(sd, "index.html")
    anchors_path = a.anchors or os.path.join(sd, "anchors.json")
    out_path = a.json or os.path.join(sd, "qc", "anchors.json")

    if not os.path.isfile(index_html):
        print(f"[anchors] 编排器侧故障：缺 {index_html}（先跑 build_html.py）", file=sys.stderr)
        return 1
    snap, err = load_snapshot(index_html)
    if snap is None:
        print(f"[anchors] 编排器侧故障：{err}", file=sys.stderr)
        return 1

    registered = os.path.isfile(anchors_path)
    table = {}
    if registered:
        try:
            table = json.loads(open(anchors_path, encoding="utf-8").read())
        except (OSError, ValueError) as exc:
            print(f"[anchors] 编排器侧故障：锚点表不可解析 {anchors_path} —— {exc}",
                  file=sys.stderr)
            return 1

    drifts, checked = [], 0
    for k, v in (table.get("anchors") or {}).items():
        got = (snap.get("anchors") or {}).get(k, "<缺失>")
        checked += 1
        for d in _drift(v, got):
            drifts.append({"key": f"{k}{('.' + d['key']) if d['key'] else ''}",
                           "expected": d["expected"], "actual": d["actual"]})

    lt = table.get("light_thresholds") or {"lift_delta_max": 0.04, "gain_delta_max": 0.10}
    light, light_bad = snap.get("light") or {}, []
    for k, v in light.items():
        lift = float(v.get("bg_base_lift", 0.0) or 0.0)
        gain = float(v.get("glow_gain", 1.0) or 1.0)
        if abs(lift) > float(lt["lift_delta_max"]) + 1e-9 or \
           abs(gain - 1.0) > float(lt["gain_delta_max"]) + 1e-9:
            light_bad.append({"scene": k, "bg_base_lift": lift, "glow_gain": gain,
                              "limit": lt})

    ok = not drifts and not light_bad
    payload = {
        "check": "anchors(KB-A2)+light(KB-A7)",
        "story": name,
        "checked_at": _ts(),
        "index_html": index_html,
        "anchors_table": anchors_path if registered else None,
        "anchors_registered": registered,
        "anchor_keys_checked": checked,
        "snapshot_version": snap.get("version"),
        "resolution": (snap.get("anchors") or {}).get("resolution"),
        "fps": (snap.get("anchors") or {}).get("fps"),
        "drifts": drifts,
        "light": light,
        "light_thresholds": lt,
        "light_out_of_range": light_bad,
        "passed": ok,
    }
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    open(out_path, "w", encoding="utf-8").write(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n")

    if not a.quiet:
        tag = "✔ 锚点一致" if ok else "⚠ 锚点漂移/光照越界"
        print(f"[anchors/KB-A2+KB-A7] {name}: {tag}（比对 {checked} 键，"
              f"快照 {snap.get('anchor_count')} 键）")
        for d in drifts:
            print(f"    [drift] {d['key']}: 登记 {d['expected']!r} → 实际 {d['actual']!r}")
        for b in light_bad:
            print(f"    [light] scene {b['scene']}: lift={b['bg_base_lift']} "
                  f"gain={b['glow_gain']} 超出 {lt}")
        if not registered:
            print(f"    [note] 未登记锚点表（{anchors_path}）→ 仅做光照检查；"
                  f"登记：build_html.py --emit-anchors")
        print(f"    报告：{out_path}")
    if not ok and a.strict:
        print("[anchors] --strict：漂移/越界 = 退出码 2", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
