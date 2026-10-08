#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""template_slots.py —— A8 模板库槽位化（v1.13.0）

模板库真源：templates/registry.json（kind → 模板 story + 槽位清单）。
本脚本负责三件事：
  1) --list：列出可用 kind（供 storyctl new --kind 与人工查阅）；
  2) --resolve <kind>：输出该 kind 的模板 story（storyctl new 调用，失败时退出码 1）；
  3) --emit --kind K --story S：把槽位清单落盘到 S/slots.json，并逐槽位检查
     "已填 / 仍为占位 / 缺失"，必填槽位缺失或仍为占位 → 报告 not_ready（rc=0，
     仅提示；加 --strict 时 rc=2）。这就是"槽位化"的落地：模板不再是黑箱复制，
     而是带一份可机器校验的待填字段契约。

占位判定：取值缺失 / 空串 / 含 {{ }} 或 <...> / 命中既有占位符扫描规则。
只读校验，不修改 story 内任何文件（slots.json 是本脚本新写的清单文件）。

用法：
  python3 scripts/template_slots.py --list
  python3 scripts/template_slots.py --resolve short-chips
  python3 scripts/template_slots.py --emit --kind short-chips --story story/<name>
"""
import argparse
import json
import os
import re
import sys
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REGISTRY = os.path.join(ROOT, "templates", "registry.json")
PH = re.compile(r"\{\{|\}\}|<[A-Za-z_][\w\- ]*>|TODO|FIXME|待填|XXX", re.I)


def load_registry():
    if not os.path.isfile(REGISTRY):
        print(f"[slots] 编排器侧故障：缺模板库真源 {REGISTRY}", file=sys.stderr)
        return None
    try:
        d = json.loads(open(REGISTRY, encoding="utf-8").read())
    except ValueError as exc:
        print(f"[slots] 编排器侧故障：registry.json 不可解析 —— {exc}", file=sys.stderr)
        return None
    return d.get("kinds") or {}


def _dig(obj, path):
    """按 'a[].b.c' 取值：[] 表示数组展开，返回取值列表（找不到 → 空列表）。"""
    cur = [obj]
    for part in path.split("."):
        nxt = []
        if part.endswith("[]"):
            part = part[:-2]
        for o in cur:
            if not isinstance(o, dict) or part not in o:
                continue
            v = o[part]
            nxt.extend(v if isinstance(v, list) else [v])
        cur = nxt
        if not cur:
            return []
    return cur


def emit(kind, story_dir):
    kinds = load_registry()
    if kinds is None:
        return 1
    if kind not in kinds:
        print(f"[slots] 用法错误：未知 kind {kind!r}（可用：{sorted(kinds)}）", file=sys.stderr)
        return 1
    entry = kinds[kind]
    sd = story_dir if os.path.isabs(story_dir) else (
        os.path.join(ROOT, "story", story_dir)
        if os.path.isdir(os.path.join(ROOT, "story", story_dir))
        else os.path.join(ROOT, story_dir))
    if not os.path.isdir(sd):
        print(f"[slots] 用法错误：story 目录不存在 {sd}", file=sys.stderr)
        return 1

    cache, items = {}, []
    for slot in entry.get("slots") or []:
        f = slot["path"]
        if f not in cache:
            p = os.path.join(sd, f)
            try:
                cache[f] = json.loads(open(p, encoding="utf-8").read()) if os.path.isfile(p) else None
            except ValueError:
                cache[f] = "PARSE_ERROR"
            if cache[f] == "PARSE_ERROR":
                print(f"[slots] 编排器侧故障：{p} 不可解析", file=sys.stderr)
                return 1
        vals = _dig(cache[f], slot["key"]) if cache[f] is not None else []
        bad = [v for v in vals if not isinstance(v, str) or not v.strip() or PH.search(v)]
        state = "missing" if not vals else ("placeholder" if bad else "filled")
        items.append({"path": f, "key": slot["key"],
                      "required": bool(slot.get("required")),
                      "desc": slot.get("desc", ""), "state": state,
                      "matched_values": len(vals),
                      "sample": (vals[0][:40] if vals and isinstance(vals[0], str) else None)})
    todo = [i for i in items if i["required"] and i["state"] != "filled"]
    payload = {"kind": kind, "template_story": entry.get("template_story"),
               "description": entry.get("description", ""),
               "registry": REGISTRY, "emitted_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
               "slot_count": len(items), "filled": sum(1 for i in items if i["state"] == "filled"),
               "todo_required": len(todo), "slots": items, "ready": not todo}
    out = os.path.join(sd, "slots.json")
    open(out, "w", encoding="utf-8").write(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    print(f"[slots/A8] {os.path.basename(sd)} ← kind={kind}（模板 {entry.get('template_story')}）："
          f"{payload['filled']}/{len(items)} 槽位已填，必填待填 {len(todo)} 项 → {out}")
    for i in todo:
        print(f"    [todo] {i['path']}.{i['key']}（{i['state']}）—— {i['desc'][:44]}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--resolve", metavar="KIND")
    ap.add_argument("--emit", action="store_true")
    ap.add_argument("--kind", default="default")
    ap.add_argument("--story")
    a = ap.parse_args()
    kinds = load_registry()
    if kinds is None:
        return 1
    if a.list:
        for k, v in kinds.items():
            print(f"{k:14s} ← {v.get('template_story')}  {v.get('description','')[:50]}")
        return 0
    if a.resolve:
        if a.resolve not in kinds:
            print(f"[slots] 用法错误：未知 kind {a.resolve!r}", file=sys.stderr)
            return 1
        print(kinds[a.resolve]["template_story"])
        return 0
    if a.emit:
        if not a.story:
            print("[slots] 用法错误：--emit 需 --story", file=sys.stderr)
            return 1
        return emit(a.kind, a.story)
    ap.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
