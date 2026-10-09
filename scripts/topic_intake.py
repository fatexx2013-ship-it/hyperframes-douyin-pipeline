#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
选题摄入器（增量1：自动选题闭环）

从 RAG 知识库选题池（entries.json / candidates.json / scored-*.md 评分榜）
摄入候选选题，过滤 + 去重后落盘排队队列，供 discovery_to_video.py --from-queue
与 batch_run.py --from-queue 消费。

用法:
    python3 scripts/topic_intake.py --pull 10
    python3 scripts/topic_intake.py --pull 10 --min-score 8 --categories 科技,健康
    python3 scripts/topic_intake.py --status            # 只展示队列状态

设计要点（幂等）:
    - 输出 story/_queue/topics-YYYYMMDD.json，每条含 title/hook/source_ref/score/category
    - 同日重复运行：已入队的 source_ref 自动跳过（不重复入队）
    - 与 story/ 现有选题去重：标题关键词 Jaccard 重叠 ≥ 阈值 视为重复
    - 只读回写标记：不修改知识库正文（队列条目带 source_ref 供溯源）
"""

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path

# ── 路径配置 ──────────────────────────────────────────────────

BASE_DIR = Path(__file__).parent.parent.resolve()
QUEUE_DIR = BASE_DIR / "story" / "_queue"
TOPICS_BASE = Path("/Volumes/PSSD/RAG知识库/topics")
STORY_ROOT = BASE_DIR / "story"

# 分类白名单映射：domains → 产线分类（可配置，默认放行 科技/健康/热点）
CATEGORY_ALIASES = {
    "technology": "科技", "ai": "科技", "open-source": "科技",
    "developer-tools": "科技", "software-engineering": "科技",
    "software-development": "科技", "ai-agents": "科技",
    "graphics": "科技", "video-generation": "科技", "content-creation": "科技",
    "health": "健康", "medical": "健康", "medicine": "健康",
    "hot": "热点", "news": "热点", "trending": "热点",
    "entertainment": "热点", "cybersecurity": "科技",
}

DEFAULT_CATEGORIES = ["科技", "健康", "热点"]

# 与既有 story 去重的 Jaccard 关键词重叠阈值
DEDUP_JACCARD_THRESHOLD = 0.5


def load_entries() -> list:
    """加载 entries.json（信息/需求广播条目）。"""
    p = TOPICS_BASE / "entries.json"
    if not p.is_file():
        return []
    with open(p, encoding="utf-8") as f:
        data = json.load(f)
    return data if isinstance(data, list) else []


def load_candidates() -> list:
    """加载 candidates.json（候选条目）。"""
    p = TOPICS_BASE / "candidates.json"
    if not p.is_file():
        return []
    with open(p, encoding="utf-8") as f:
        data = json.load(f)
    return data if isinstance(data, list) else []


def latest_scored() -> Path | None:
    """最新 scored-*.md 评分榜文件。"""
    files = sorted(TOPICS_BASE.glob("scored-*.md"))
    return files[-1] if files else None


def parse_scored(text: str) -> list[dict]:
    """解析 scored-*.md：提取 (score, agent, date, domains, keywords, summary, source_id)。"""
    items = []
    cur = None
    for line in text.splitlines():
        m = re.match(r"### #(\d+) · ([\d.]+) 分 · (.+?) · (\d{4}-\d{2}-\d{2})", line)
        if m:
            if cur:
                items.append(cur)
            cur = {
                "rank": int(m.group(1)),
                "score": float(m.group(2)),
                "agent": m.group(3).strip(),
                "date": m.group(4),
                "domains": [], "keywords": [], "summary": "", "source_id": "",
            }
            continue
        if cur is not None:
            lm = re.match(r"- 领域：(.+)", line)
            if lm:
                cur["domains"] = [d.strip() for d in lm.group(1).split("/") if d.strip()]
                continue
            km = re.match(r"- 关键词：(.+)", line)
            if km:
                cur["keywords"] = [k.strip() for k in km.group(1).split("、") if k.strip()]
                continue
            sm = re.match(r"- 摘要：(.+)", line)
            if sm:
                cur["summary"] = sm.group(1).strip()
                continue
            tm = re.match(r"- 溯源：(\d+)", line)
            if tm:
                cur["source_id"] = tm.group(1)
                continue
    if cur:
        items.append(cur)
    return items


def map_category(domains: list[str]) -> str:
    """domains → 产线分类（取第一个命中白名单映射）。"""
    for d in domains or []:
        c = CATEGORY_ALIASES.get(d.lower())
        if c:
            return c
    return "其他"


def make_hook(item: dict) -> str:
    """从条目生成一句话钩子。"""
    kw = item.get("keywords") or []
    summary = item.get("summary") or ""
    # 优先取关键词前两个组成钩子
    if len(kw) >= 2:
        return f"{kw[0]} + {kw[1]}，这波情报值得做一条！"
    if summary:
        s = summary.strip()
        cut = min(len(s), 60)
        return (s[:cut] + "…") if len(s) > cut else s
    return "选题情报，值得做一条！"


def normalize_keywords(text: str) -> set:
    """关键词集合规范化（小写 + 去停用词）。"""
    stopwords = {"the", "a", "an", "of", "for", "and", "in", "on", "to", "with",
                 "是", "的", "了", "和", "与", "在", "一个", "一款", "开源"}
    parts = re.findall(r"[a-zA-Z0-9]+|[\u4e00-\u9fff]{2,}", text.lower())
    return {p for p in parts if p not in stopwords}


def jaccard(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def collect_existing_titles() -> list[dict]:
    """收集 story/ 下既有选题标题与关键词（用于去重）。"""
    existing = []
    for sd in sorted(STORY_ROOT.iterdir()):
        if not sd.is_dir() or sd.name.startswith("."):
            continue
        sp = sd / "script.json"
        if sp.is_file():
            try:
                data = json.loads(sp.read_text(encoding="utf-8"))
                title = data.get("title", "")
                source = data.get("source", "")
                existing.append({
                    "story": sd.name,
                    "title": title,
                    "keywords": normalize_keywords(f"{title} {source}"),
                })
            except (OSError, ValueError):
                pass
        # script.txt 兜底（generate_script --demo 产物）
        tp = sd / "script.txt"
        if tp.is_file() and not sp.is_file():
            text = tp.read_text(encoding="utf-8")[:300]
            existing.append({
                "story": sd.name,
                "title": text.splitlines()[0] if text else sd.name,
                "keywords": normalize_keywords(text),
            })
    return existing


def is_duplicate(item: dict, existing: list[dict], threshold: float) -> bool:
    """与既有 story 或队列条目判断重复（关键词 Jaccard）。"""
    title = item.get("title") or ""
    kw = set(normalize_keywords(title))
    if item.get("keywords"):
        kw |= set(normalize_keywords(" ".join(item["keywords"])))
    for ex in existing:
        j = jaccard(kw, ex.get("keywords", set()))
        if j >= threshold:
            return True
    return False


def main() -> int:
    parser = argparse.ArgumentParser(description="选题摄入器（自动选题闭环入口）")
    parser.add_argument("--pull", type=int, default=0, help="摄入 N 条候选队列（0=只算不落盘）")
    parser.add_argument("--min-score", type=float, default=10.0,
                        help="最低评分阈值（scored 榜为 0-25 分制，默认 10.0）")
    parser.add_argument("--categories", default=",".join(DEFAULT_CATEGORIES),
                        help="分类白名单，逗号分隔（默认 科技,健康,热点）")
    parser.add_argument("--jaccard-threshold", type=float, default=DEDUP_JACCARD_THRESHOLD,
                        help="与既有 story 去重的关键词重叠阈值")
    parser.add_argument("--status", action="store_true", help="只展示队列状态")
    parser.add_argument("--force", action="store_true",
                        help="当日队列已存在时强制重新摄入（默认复用已存在队列）")
    args = parser.parse_args()

    QUEUE_DIR.mkdir(parents=True, exist_ok=True)
    whitelist = {c.strip() for c in args.categories.split(",") if c.strip()}

    if args.status:
        today = datetime.now().strftime("%Y%m%d")
        f = QUEUE_DIR / f"topics-{today}.json"
        if not f.is_file():
            print(f"队列不存在：{f}（先运行 --pull）")
            return 1
        data = json.loads(f.read_text(encoding="utf-8"))
        status = {}
        for it in data:
            status.setdefault(it.get("status", "pending"), 0)
            status[it.get("status", "pending")] += 1
        print(f"队列 {f.name}：共 {len(data)} 条 → {json.dumps(status, ensure_ascii=False)}")
        return 0

    # 幂等：当日队列已存在且未要求 --force 时直接复用（不重复摄入、不扩容）
    today = datetime.now().strftime("%Y%m%d")
    queue_file = QUEUE_DIR / f"topics-{today}.json"
    if queue_file.is_file() and not args.force and args.pull:
        try:
            old = json.loads(queue_file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            old = []
        if old:
            print(f"⏭️ 当日队列已存在（{len(old)} 条）：复用 {queue_file.name}"
                  "（如需重建请加 --force）")
            return 0

    # 1) 加载选题池
    scored_file = latest_scored()
    scored_items = []
    if scored_file:
        scored_items = parse_scored(scored_file.read_text(encoding="utf-8"))
        print(f"📊 评分榜：{scored_file.name}（{len(scored_items)} 条候选）")

    entries = load_entries()
    candidates = load_candidates()
    print(f"📥 entries.json：{len(entries)} 条；candidates.json：{len(candidates)} 条")

    # 2) 合并：以 scored 榜为主，缺 summary/domains 时从 entries/candidates 补
    by_id = {str(it.get("item_id") or it.get("id")): it
             for it in entries + candidates if it.get("item_id") or it.get("id")}
    merged = []
    for it in scored_items:
        sid = str(it.get("source_id") or "")
        extra = by_id.get(sid, {})
        if not it["summary"]:
            it["summary"] = extra.get("summary", "")
        if not it["keywords"]:
            it["keywords"] = extra.get("keywords", [])
        if not it["domains"]:
            it["domains"] = extra.get("domains", [])
        cat = map_category(it["domains"])
        if cat not in whitelist:
            continue
        if it["score"] < args.min_score:
            continue
        merged.append({**it, "category": cat})
    # 无 scored 榜时兜底：从 entries/candidates 按 kind/分类摄入
    if not merged and scored_file is None:
        for it in entries + candidates:
            cat = map_category(it.get("domains", []))
            if cat not in whitelist:
                continue
            score = 0.0
            merged.append({
                "score": score, "agent": it.get("agent", ""),
                "date": (it.get("time") or "")[:10],
                "domains": it.get("domains", []),
                "keywords": it.get("keywords", []),
                "summary": it.get("summary", ""),
                "source_id": str(it.get("item_id") or it.get("id") or ""),
                "category": cat,
            })
    print(f"🎯 白名单分类 {sorted(whitelist)} · 阈值 ≥{args.min_score} → {len(merged)} 条候选")

    # 3) 与既有 story 去重
    existing = collect_existing_titles()
    # 也加载当日已有队列（幂等：同日重复运行不重复入队）
    today = datetime.now().strftime("%Y%m%d")
    queue_file = QUEUE_DIR / f"topics-{today}.json"
    queued_refs = set()
    if queue_file.is_file():
        try:
            for it in json.loads(queue_file.read_text(encoding="utf-8")):
                queued_refs.add(it.get("source_ref", ""))
        except (OSError, ValueError):
            pass

    picked = []
    for it in merged:
        sid = it.get("source_id", "")
        if sid and sid in queued_refs:
            continue
        if is_duplicate(it, existing, args.jaccard_threshold):
            continue
        title = it.get("summary", "")[:24] or "选题情报"
        picked.append({
            "title": title,
            "hook": make_hook(it),
            "source_ref": sid,
            "score": it["score"],
            "category": it["category"],
            "agent": it.get("agent", ""),
            "keywords": it.get("keywords", [])[:8],
            "status": "pending",
        })
        if args.pull and len(picked) >= args.pull:
            break

    if not args.pull:
        print(f"（--pull 未给，仅试算）可入队 {len(picked)} 条")
        return 0

    print(f"✅ 去重后入选 {len(picked)} 条（目标 {args.pull}）")
    for i, it in enumerate(picked, 1):
        print(f"  #{i} [{it['score']:>4}分][{it['category']}] {it['title']}（{it['source_ref']}）")

    # 4) 落盘：同日文件合并（幂等），保留既有条目状态
    if queue_file.is_file():
        old = json.loads(queue_file.read_text(encoding="utf-8"))
        picked = old + [p for p in picked if p["source_ref"] not in {o.get("source_ref") for o in old}]
    queue_file.write_text(
        json.dumps(picked, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"💾 队列落盘：{queue_file}（共 {len(picked)} 条）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
