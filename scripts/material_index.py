#!/usr/bin/env python3
"""
素材库复用与多模态检索（增量5）。

功能：
  --build <story_dir>        扫描 story/*/materials/（图片+视频关键帧语义）入库 LanceDB；
                             幂等增量更新（已入库文件跳过，不重建全库）。
  --query "<文本>"           以文搜图：文本嵌入检索素材。
  --query-image <文件>       以图搜图：dHash 感知哈希 + 文本嵌入双路检索相似素材。
  --stats                    索引统计。

嵌入后端（--embedding auto 默认）：
  gemma2  → EmbeddingGemma 2（多模态首选；本机无权重/下载受限时自动降级并警告）
  minilm  → all-MiniLM-L6-v2（离线可用，文本嵌入 384 维；图像侧用 dHash 感知哈希双路）

向量库：story/_queue/material_index.lance（LanceDB v0.40 本地嵌入式，零服务运维）
素材语义描述：来自所属 story 的 script.json title + script.txt 前 300 字（素材服务于该选题）。
"""

import argparse
import hashlib
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

import lancedb
import numpy as np

INDEX_DIR = "materials.lance"
SCRIPT_TEXT_PREFIX_LEN = 300

_TEXT_MODEL = None
_TEXT_MODEL_NAME = None


def _log(msg):
    print(f"[material-index] {msg}")


def _text_encoder(embedding: str):
    """加载文本嵌入模型。auto：优先 gemma2，缺失降级 minilm。

    降级策略：本机已存在失败标记（.gemma2_failed）时不再尝试联网下载，
    直接使用 minilm（本地优先、幂等，避免每次查询卡网络重试）。
    """
    global _TEXT_MODEL, _TEXT_MODEL_NAME
    if _TEXT_MODEL is not None:
        return _TEXT_MODEL, _TEXT_MODEL_NAME
    gemma_failed_flag = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".gemma2_failed")
    if embedding in ("gemma2", "auto"):
        if os.path.exists(gemma_failed_flag):
            _log("警告：检测到 EmbeddingGemma 2 失败标记，跳过联网尝试，降级 all-MiniLM-L6-v2")
        else:
            try:
                from sentence_transformers import SentenceTransformer
                _TEXT_MODEL = SentenceTransformer(
                    "google/embeddinggemma-2-7b", device="cpu", trust_remote_code=True)
                _TEXT_MODEL_NAME = "EmbeddingGemma-2-7B"
                _log(f"嵌入后端：{_TEXT_MODEL_NAME}")
                return _TEXT_MODEL, _TEXT_MODEL_NAME
            except Exception as e:
                if embedding == "gemma2":
                    raise RuntimeError(f"EmbeddingGemma 2 不可用：{e}")
                _log(f"警告：EmbeddingGemma 2 加载失败（{type(e).__name__}），降级 all-MiniLM-L6-v2")
                try:
                    Path(gemma_failed_flag).write_text(
                        f"EmbeddingGemma 2 下载失败（{type(e).__name__}），已降级 all-MiniLM-L6-v2\n", encoding="utf-8")
                    _log(f"失败标记已写入 {gemma_failed_flag}，后续不再联网尝试")
                except Exception:
                    pass
    from sentence_transformers import SentenceTransformer
    _TEXT_MODEL = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2", device="cpu")
    _TEXT_MODEL_NAME = "all-MiniLM-L6-v2"
    _log(f"嵌入后端：{_TEXT_MODEL_NAME}")
    return _TEXT_MODEL, _TEXT_MODEL_NAME


def _encode_texts(texts: list[str], embedding: str) -> list[list[float]]:
    model, _ = _text_encoder(embedding)
    return [list(map(float, v)) for v in model.encode(texts)]


def _dhash(data: bytes, size: int = 16) -> str:
    """感知哈希（dHash）：灰度图相邻像素差分 → 位串。无模型，图片/视频首帧相似检索。"""
    try:
        from PIL import Image
        import io
        img = Image.open(io.BytesIO(data)).convert("L").resize((size + 1, size))
        pix = img.load()
        bits = []
        for y in range(size):
            for x in range(size):
                bits.append(1 if pix[x, y] > pix[x + 1, y] else 0)
        return "".join(map(str, bits))
    except Exception:
        return ""


def _video_first_frame(path: Path, max_bytes: int = 1_048_576) -> bytes | None:
    """抽取视频首帧（ffmpeg → PNG bytes）。"""
    import shutil, subprocess
    ffmpeg = shutil.which("ffmpeg")
    for p in ("/opt/homebrew/bin/ffmpeg", "/usr/local/bin/ffmpeg", "/usr/bin/ffmpeg"):
        if os.path.isfile(p):
            ffmpeg = p
            break
    if not ffmpeg:
        return None
    r = subprocess.run(
        [ffmpeg, "-y", "-v", "error", "-ss", "0", "-i", str(path),
         "-frames:v", "1", "-f", "image2pipe", "-vcodec", "png", "-"],
        capture_output=True, timeout=30)
    if r.returncode != 0 or not r.stdout:
        return None
    return r.stdout[:max_bytes]


def _hamming(a: str, b: str) -> int:
    return sum(1 for x, y in zip(a, b) if x != y)


def _material_desc(story_dir: Path) -> str:
    """素材语义描述：script.json title + script.txt 前 300 字。"""
    parts = []
    sj = story_dir / "script.json"
    if sj.is_file():
        try:
            d = json.loads(sj.read_text(encoding="utf-8"))
            if d.get("title"):
                parts.append(d["title"])
        except Exception:
            pass
    st = story_dir / "script.txt"
    if st.is_file():
        txt = st.read_text(encoding="utf-8").strip()[:SCRIPT_TEXT_PREFIX_LEN]
        if txt:
            parts.append(txt)
    return " ".join(parts)


def _scan_story_materials(story_dir: Path) -> list[dict]:
    """扫描单个 story 的 materials/（含 generated/）。"""
    mat_dir = story_dir / "materials"
    out = []
    if not mat_dir.is_dir():
        return out
    for f in sorted(mat_dir.rglob("*")):
        if not f.is_file():
            continue
        if f.suffix.lower() in (".mp4", ".mov", ".webm", ".mkv"):
            ftype = "video"
        elif f.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif"):
            ftype = "image"
        elif f.name == "file_list.txt" or f.suffix in (".txt", ".json"):
            continue
        else:
            continue
        out.append({
            "file_path": str(f),
            "story": story_dir.name,
            "file_type": ftype,
            "source": "localgen" if "localgen" in f.name else
                      ("placeholder" if "placeholder" in f.name else
                       ("pexels" if f.name.startswith("mat_") else "local")),
            "size": f.stat().st_size,
            "text_desc": _material_desc(story_dir),
        })
    return out


def _index_path(story_root: Path) -> Path:
    return story_root / "story" / "_queue" / INDEX_DIR


def build(story_root: Path, embedding: str) -> int:
    index_p = _index_path(story_root)
    db = lancedb.connect(str(index_p.parent))
    tbl_name = "materials"
    existing: set[str] = set()
    tbl = None
    try:
        tbl = db.open_table(tbl_name)
        # 不依赖 to_lance：用 search 拉全量 file_path（空表返回空）
        try:
            existing = {r["file_path"] for r in tbl.search(np.zeros(384)).limit(100000).to_list()}
        except Exception:
            existing = {r["file_path"] for r in tbl.to_lance().to_table(columns=["file_path"]).to_pylist()}
    except Exception:
        tbl = None

    rows = []
    story_dir = story_root / "story"
    for sd in sorted(story_dir.iterdir()):
        if not sd.is_dir() or sd.name.startswith("_"):
            continue
        for m in _scan_story_materials(sd):
            if m["file_path"] in existing:
                continue
            rows.append(m)

    if not rows:
        _log(f"无新素材（已有 {len(existing)} 条，增量更新完成）")
        return 0

    texts = [r["text_desc"] or r["file_path"] for r in rows]
    vecs = _encode_texts(texts, embedding)
    hashes = []
    for r in rows:
        p = Path(r["file_path"])
        h = ""
        if r["file_type"] == "video":
            frame = _video_first_frame(p)
            if frame:
                h = _dhash(frame)
        else:
            try:
                h = _dhash(p.read_bytes())
            except Exception:
                h = ""
        hashes.append(h)

    data = []
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    for r, v, h in zip(rows, vecs, hashes):
        data.append({
            "file_path": r["file_path"], "story": r["story"],
            "file_type": r["file_type"], "source": r["source"],
            "size": r["size"], "text_desc": r["text_desc"][:200],
            "dhash": h, "vector": v, "created_at": now,
        })

    if tbl is None:
        tbl = db.create_table(tbl_name, data=data)
    else:
        tbl.add(data)
    _log(f"新增入库 {len(data)} 条（累计 {len(existing) + len(data)} 条），LanceDB：{index_p}")
    return 0


def query_text(story_root: Path, q: str, embedding: str, top_k: int = 10) -> list[dict]:
    index_p = _index_path(story_root)
    if not index_p.exists():
        _log("索引不存在，先运行 --build")
        return []
    tbl = lancedb.connect(str(index_p.parent)).open_table("materials")
    vec = _encode_texts([q], embedding)[0]
    hits = tbl.search(vec).limit(top_k).to_list()
    return hits


def query_image(story_root: Path, img_path: Path, embedding: str, top_k: int = 10) -> list[dict]:
    index_p = _index_path(story_root)
    if not index_p.exists():
        _log("索引不存在，先运行 --build")
        return []
    tbl = lancedb.connect(str(index_p.parent)).open_table("materials")
    try:
        if img_path.suffix.lower() in (".mp4", ".mov", ".webm", ".mkv"):
            data = _video_first_frame(img_path)
        else:
            data = img_path.read_bytes()
        target_h = _dhash(data)
    except Exception:
        target_h = ""
    target_v = _encode_texts([img_path.name], embedding)[0]
    all_rows = tbl.to_lance().to_table().to_pylist()
    scored = []
    for row in all_rows:
        sim = float(np.dot(np.array(row["vector"]), np.array(target_v)))
        ham = _hamming(row["dhash"], target_h) if target_h and row["dhash"] else 999
        scored.append((sim, ham, row))
    # 融合：余弦相似为主，dHash 近重复大幅加分
    scored.sort(key=lambda x: x[0] + (1.0 if x[1] <= 12 else 0.0), reverse=True)
    return [s[2] for s in scored[:top_k]]


def stats(story_root: Path) -> int:
    index_p = _index_path(story_root)
    if not index_p.exists():
        _log("索引不存在")
        return 1
    tbl = lancedb.connect(str(index_p.parent)).open_table("materials")
    rows = tbl.to_lance().to_table().to_pylist()
    from collections import Counter
    print(f"素材总数：{len(rows)}")
    print("来源分布：", dict(Counter(r["source"] for r in rows)))
    print("类型分布：", dict(Counter(r["file_type"] for r in rows)))
    print("覆盖 story：", len(set(r["story"] for r in rows)))
    return 0


def main():
    ap = argparse.ArgumentParser(description="素材库复用与多模态检索（增量5）")
    ap.add_argument("--build", metavar="STORY_ROOT", help="扫描建/增量更新索引（默认 /Volumes/PSSD/抖音视频）")
    ap.add_argument("--query", help="以文搜图")
    ap.add_argument("--query-image", metavar="FILE", help="以图搜图")
    ap.add_argument("--stats", action="store_true", help="索引统计")
    ap.add_argument("--top-k", type=int, default=10)
    ap.add_argument("--embedding", choices=["auto", "gemma2", "minilm"], default="auto")
    args = ap.parse_args()

    root = Path(args.build) if args.build else Path("/Volumes/PSSD/抖音视频")

    if args.stats:
        return stats(root)
    if args.query:
        for h in query_text(root, args.query, args.embedding, args.top_k):
            src = h.get("source", "?")
            print(f"[{h.get('file_type','?')}|{src}|{h.get('story','?')}] {h['file_path']}")
        return 0
    if args.query_image:
        for h in query_image(root, Path(args.query_image), args.embedding, args.top_k):
            print(f"[{h.get('file_type','?')}|{h.get('source','?')}|{h.get('story','?')}] {h['file_path']}")
        return 0
    if args.build:
        return build(root, args.embedding)
    ap.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
