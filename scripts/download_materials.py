#!/usr/bin/env python3
"""
素材下载脚本 — Pexels API 下载竖屏视频素材 + 本地 B-roll 补位。

provider 链（增量3+5）：local-index（本地素材库复用）→ pexels（首选下载）→ local-gen（补位，ffmpeg 本地生成氛围镜头）→ placeholder（保底，V-BASE 提亮静帧）。

用法：
    python scripts/download_materials.py \
        --api-key "YOUR_PEXELS_API_KEY" \
        --query "artificial intelligence" \
        --output story/001/materials/ \
        --count 5
    # 无 API key / Pexels 零匹配时自动落 local-gen：
    python scripts/download_materials.py --query "量子芯片" --output story/001/materials/ --count 2

本地生成产物统一落 <output>/generated/，文件名带来源标记 localgen_/placeholder_；
台账写 <output>/ledger.json（记录来源、模型/参数、耗时、命令）。
"""

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

LOCAL_GEN_DIRNAME = "generated"
LEDGER_NAME = "ledger.json"
# 竖屏规格：与 scene_plan.json 对齐（1080x1920 / 30fps）
GEN_WIDTH, GEN_HEIGHT, GEN_FPS = 1080, 1920, 30


def _ffmpeg() -> str:
    """解析 ffmpeg 可执行文件：PATH → 常见 Homebrew 路径 → 环境变量覆盖。"""
    cand = shutil.which("ffmpeg") or os.environ.get("STORYCTL_FFMPEG")
    for p in ("/opt/homebrew/bin/ffmpeg", "/usr/local/bin/ffmpeg", "/usr/bin/ffmpeg"):
        if os.path.isfile(p) and os.access(p, os.X_OK):
            return p
    if cand:
        return cand
    raise FileNotFoundError("ffmpeg_not_found")


def search_pexels(api_key: str, query: str, orientation: str = "portrait",
                  per_page: int = 20, page: int = 1) -> dict:
    """搜索 Pexels 视频。"""
    import httpx

    headers = {"Authorization": api_key}
    params = {
        "query": query,
        "per_page": per_page,
        "page": page,
        "orientation": orientation,
    }

    resp = httpx.get(
        "https://api.pexels.com/videos/search",
        headers=headers,
        params=params,
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def download_video(url: str, dest: Path, max_retries: int = 3) -> bool:
    """下载视频文件到目标路径。"""
    import httpx

    for attempt in range(max_retries):
        try:
            resp = httpx.get(url, timeout=120, follow_redirects=True)
            resp.raise_for_status()

            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(resp.content)
            return True
        except Exception as e:
            print(f"  下载失败（尝试 {attempt + 1}/{max_retries}）：{e}", file=sys.stderr)
            if attempt < max_retries - 1:
                time.sleep(2)
    return False


def _seed_for(query: str, salt: str = "") -> int:
    """由 query 派生稳定 seed（幂等：同 query 同输出名）。"""
    return int(hashlib.md5(f"{query}|{salt}".encode()).hexdigest()[:8], 16)


def _ledger_path(output_dir: Path) -> Path:
    return output_dir / LEDGER_NAME


def _append_ledger(output_dir: Path, entry: dict) -> None:
    lp = _ledger_path(output_dir)
    data = []
    if lp.is_file():
        try:
            data = json.loads(lp.read_text(encoding="utf-8"))
        except Exception:
            data = []
    data.append(entry)
    lp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def gen_local_visual(query: str, output_dir: Path, duration: int = 5,
                     subtitle: str = "", source: str = "local-gen") -> Path | None:
    """本地生成补位镜头（ffmpeg，无网络、无模型依赖）。

    - source="local-gen"   ：gradients 动态氛围镜头 + 主题文字（B-roll 补位）
    - source="placeholder" ：V-BASE 提亮静帧（纯色渐变静帧，保底）
    产物落 <output>/generated/，文件名 localgen_<hash>.mp4 / placeholder_<hash>.mp4。
    """
    gen_dir = output_dir / LOCAL_GEN_DIRNAME
    gen_dir.mkdir(parents=True, exist_ok=True)
    tag = "localgen" if source == "local-gen" else "placeholder"
    out_name = f"{tag}_{_seed_for(query, source)}_{duration}s.mp4"
    dest = gen_dir / out_name
    if dest.exists():  # 幂等：同 query 已生成则复用
        print(f"  [local-gen] 已存在（幂等复用）：{dest.name}")
        _append_ledger(output_dir, {
            "file": str(dest), "source": source, "query": query,
            "duration_s": duration, "seed": _seed_for(query, source),
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "status": "reused", "command": "",
        })
        return dest

    ffmpeg = _ffmpeg()
    t0 = time.time()
    cmd = [ffmpeg, "-y", "-hide_banner", "-loglevel", "error"]
    if source == "local-gen":
        # 动态氛围背景（gradients 缓慢流动）+ 主题文字（PingFang）
        vf = "format=yuv420p"
        drawtext = ""
        if subtitle:
            font = "/System/Library/Fonts/PingFang.ttc"
            if os.path.isfile(font):
                drawtext = (f",drawtext=fontfile={font}:text={subtitle}:fontsize=64:"
                            f"fontcolor=white@0.9:x=(w-text_w)/2:y=h*0.78")
        cmd += ["-f", "lavfi", "-i",
                f"gradients=size={GEN_WIDTH}x{GEN_HEIGHT}:rate={GEN_FPS}:duration={duration}:"
                f"speed=0.05:seed={_seed_for(query, source)}",
                "-vf", vf + drawtext,
                "-c:v", "libx264", "-pix_fmt", "yuv420p", "-movflags", "+faststart",
                str(dest)]
    else:  # placeholder：V-BASE 提亮静帧（color 源 + eq 提亮，5 秒静帧）
        cmd += ["-f", "lavfi", "-i",
                f"color=c=0x1a1a2e:size={GEN_WIDTH}x{GEN_HEIGHT}:rate={GEN_FPS}:duration={duration}",
                "-vf", "eq=brightness=0.12:saturation=0.5,format=yuv420p",
                "-c:v", "libx264", "-pix_fmt", "yuv420p", "-movflags", "+faststart",
                str(dest)]

    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
        if r.returncode != 0:
            print(f"  [{tag}] 生成失败：{r.stderr[-300:]}", file=sys.stderr)
            return None
    except subprocess.TimeoutExpired:
        print(f"  [{tag}] 生成超时", file=sys.stderr)
        return None

    elapsed = round(time.time() - t0, 1)
    print(f"  [{tag}] 生成 OK（{elapsed}s, {dest.stat().st_size/1024/1024:.1f} MB）：{dest.name}")
    _append_ledger(output_dir, {
        "file": str(dest), "source": source, "query": query,
        "duration_s": duration, "seed": _seed_for(query, source),
        "resolution": f"{GEN_WIDTH}x{GEN_HEIGHT}", "fps": GEN_FPS,
        "engine": "ffmpeg(gradients/color)", "license": "FFmpeg LGPL/GPL（本机工具）",
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "elapsed_s": elapsed, "status": "generated",
        "command": " ".join(cmd[:8]) + " ...",
    })
    return dest


def main():
    parser = argparse.ArgumentParser(description="素材下载：Pexels 优先，零匹配自动落本地生成补位")
    parser.add_argument("--api-key", default=None, help="Pexels API Key（缺省/无效时跳过 pexels 直接 local-gen）")
    parser.add_argument("--query", "-q", required=True, help="搜索关键词")
    parser.add_argument("--output", "-o", required=True, help="输出目录")
    parser.add_argument("--count", "-n", type=int, default=5, help="下载/生成数量")
    parser.add_argument("--orientation", default="portrait",
                        choices=["portrait", "landscape", "square"],
                        help="画面方向（默认 portrait 竖屏）")
    parser.add_argument("--min-duration", type=int, default=3, help="最短时长（秒）")
    parser.add_argument("--max-duration", type=int, default=30, help="最长时长（秒）")
    parser.add_argument("--search-only", action="store_true",
                        help="只搜索不下载，打印结果列表")
    parser.add_argument("--provider", default="auto",
                        choices=["auto", "local-index", "pexels", "local-gen", "placeholder"],
                        help="provider 链：auto=local-index→pexels→local-gen→placeholder；显式指定则跳过前置")
    args = parser.parse_args()

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.search_only:
        if not args.api_key:
            print("search-only 需要 --api-key", file=sys.stderr)
            return 1
        data = search_pexels(args.api_key, args.query, args.orientation,
                             per_page=min(args.count * 3, 20))
        for v in data.get("videos", [])[: args.count]:
            print(f"- {v.get('title', '?')} ({v.get('duration', 0)}s)")
        return 0

    chain = (["local-index", "pexels", "local-gen", "placeholder"] if args.provider == "auto"
             else [args.provider])

    downloaded: list[str] = []

    # local-index：本地素材库复用（增量5）——命中则复制到新目录，不重新下载
    if "local-index" in chain:
        try:
            import sys as _sys
            sys.path.insert(0, str(Path(__file__).resolve().parent))
            import material_index as mi
            hits = mi.query_text(Path(__file__).resolve().parent.parent,
                                 args.query, "minilm", top_k=args.count * 2)
            reused = 0
            for h in hits:
                src_p = Path(h["file_path"])
                if not src_p.is_file():
                    continue
                dest = output_dir / src_p.name
                if dest.exists():
                    continue
                import shutil
                shutil.copy2(src_p, dest)
                reused += 1
                downloaded.append(str(dest))
                _append_ledger(output_dir, {
                    "file": str(dest), "source": f"local-index/{h.get('source','?')}",
                    "query": args.query, "reuse_from": str(src_p),
                    "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "status": "reused",
                })
                print(f"  [local-index] 复用本地素材：{src_p.name} ← {h.get('story','?')}")
                if reused >= args.count:
                    break
            if reused:
                print(f"[local-index] 命中 {reused} 条（本地库复用，无需重新下载）")
        except Exception as e:
            print(f"  [local-index] 不可用（{type(e).__name__}: {str(e)[:120]}），跳过", file=sys.stderr)

    if "pexels" in chain and args.api_key:
        print(f"搜索：'{args.query}' orientation={args.orientation}...")
        try:
            data = search_pexels(
                api_key=args.api_key,
                query=args.query,
                orientation=args.orientation,
                per_page=min(args.count * 3, 20),
            )
            videos = data.get("videos", [])
        except Exception as e:
            print(f"  [pexels] 请求失败（{e}）→ 转入 local-gen", file=sys.stderr)
            videos = []

        if videos:
            print(f"[pexels] 找到 {len(videos)} 个候选视频")
            for i, video in enumerate(videos[: args.count]):
                title = video.get("title", f"video_{i}")
                duration = video.get("duration", 0)
                if duration < args.min_duration or duration > args.max_duration:
                    print(f"  跳过（时长 {duration}s）：{title}")
                    continue
                video_files = video.get("video_files", [])
                portrait_files = [vf for vf in video_files
                                  if vf.get("width", 1) < vf.get("height", 1)]
                portrait_files.sort(key=lambda x: x.get("width", 0) * x.get("height", 0), reverse=True)
                if not portrait_files:
                    portrait_files = sorted(video_files,
                                            key=lambda x: x.get("width", 0) * x.get("height", 0),
                                            reverse=True)
                if not portrait_files:
                    continue
                best = portrait_files[0]
                url = best.get("link")
                if not url:
                    continue
                hash_str = f"{url}_{title}"
                file_hash = hashlib.md5(hash_str.encode()).hexdigest()[:8]
                filename = f"mat_{file_hash}.mp4"
                dest = output_dir / filename
                if dest.exists():
                    print(f"  已存在：{filename}")
                    downloaded.append(filename)
                    continue
                print(f"  下载 [{duration}s] {title} -> {filename}")
                if download_video(url, dest):
                    downloaded.append(filename)
                    print(f"    OK ({dest.stat().st_size / 1024 / 1024:.1f} MB)")
                else:
                    print(f"    FAILED", file=sys.stderr)
                time.sleep(0.1)
        else:
            print(f"[pexels] 零匹配/失败 → 转入 local-gen 补位", file=sys.stderr)

    # local-gen / placeholder 补位：补齐缺口数量
    if len(downloaded) < args.count and ("local-gen" in chain or "placeholder" in chain):
        need = args.count - len(downloaded)
        print(f"[local-provider] 需补 {need} 条（provider 链：{chain}）")
        local_src = "local-gen" if "local-gen" in chain else "placeholder"
        for i in range(need):
            p = gen_local_visual(args.query, output_dir,
                                 duration=5, subtitle=args.query[:12],
                                 source=local_src)
            if p:
                downloaded.append(str(p))
            else:
                # local-gen 失败时兜底 placeholder
                p2 = gen_local_visual(args.query, output_dir, duration=5,
                                      subtitle="", source="placeholder")
                if p2:
                    downloaded.append(str(p2))

    print(f"\n完成：{len(downloaded)}/{args.count} 条素材")
    print(f"保存位置：{output_dir}")
    if downloaded:
        list_file = output_dir / "file_list.txt"
        list_file.write_text("\n".join(str(output_dir / f) if "/" not in f else f for f in downloaded),
                             encoding="utf-8")
        print(f"文件列表已写入：{list_file}")
    return 0 if downloaded else 1


if __name__ == "__main__":
    sys.exit(main())
