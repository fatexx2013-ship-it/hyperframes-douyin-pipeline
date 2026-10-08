#!/usr/bin/env python3
"""
素材下载脚本 — 通过 Pexels API 下载竖屏视频素材。

用法：
    python scripts/download_materials.py \
        --api-key "YOUR_PEXELS_API_KEY" \
        --query "artificial intelligence" \
        --output story/001/materials/ \
        --count 5
"""

import argparse
import hashlib
import os
import sys
import time
from pathlib import Path


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


def main():
    parser = argparse.ArgumentParser(description="从 Pexels 下载视频素材")
    parser.add_argument("--api-key", required=True, help="Pexels API Key")
    parser.add_argument("--query", "-q", required=True, help="搜索关键词")
    parser.add_argument("--output", "-o", required=True, help="输出目录")
    parser.add_argument("--count", "-n", type=int, default=5, help="下载数量")
    parser.add_argument("--orientation", default="portrait",
                        choices=["portrait", "landscape", "square"],
                        help="画面方向（默认 portrait 竖屏）")
    parser.add_argument("--min-duration", type=int, default=3, help="最短时长（秒）")
    parser.add_argument("--max-duration", type=int, default=30, help="最长时长（秒）")
    parser.add_argument("--search-only", action="store_true",
                        help="只搜索不下载，打印结果列表")
    args = parser.parse_args()

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"搜索：'{args.query}' orientation={args.orientation}...")
    data = search_pexels(
        api_key=args.api_key,
        query=args.query,
        orientation=args.orientation,
        per_page=min(args.count * 3, 20),  # 多搜一些以便筛选
    )

    videos = data.get("videos", [])
    if not videos:
        print("未找到匹配的视频素材。", file=sys.stderr)
        sys.exit(1)

    print(f"找到 {len(videos)} 个候选视频\n")

    downloaded = []
    for i, video in enumerate(videos[: args.count]):
        title = video.get("title", f"video_{i}")
        duration = video.get("duration", 0)

        # 时长过滤
        if duration < args.min_duration or duration > args.max_duration:
            print(f"  跳过（时长 {duration}s）：{title}")
            continue

        # 找最高分辨率的竖屏版本
        video_files = video.get("video_files", [])
        portrait_files = [
            vf for vf in video_files
            if vf.get("width", 1) < vf.get("height", 1)  # 竖屏
        ]
        # 按分辨率排序，取最高
        portrait_files.sort(key=lambda x: x.get("width", 0) * x.get("height", 0), reverse=True)

        if not portrait_files:
            # 没有竖屏？取最高分辨率横屏
            portrait_files = sorted(video_files,
                                    key=lambda x: x.get("width", 0) * x.get("height", 0),
                                    reverse=True)

        if not portrait_files:
            continue

        best = portrait_files[0]
        url = best.get("link")
        if not url:
            continue

        # 文件名：基于 URL 哈希保证唯一
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

        # API 限流：每次请求间隔
        time.sleep(0.1)

    print(f"\n下载完成：{len(downloaded)}/{len(videos)} 个视频")
    print(f"保存位置：{output_dir}")

    # 输出文件列表（供后续脚本使用）
    if downloaded:
        list_file = output_dir / "file_list.txt"
        list_file.write_text("\n".join(str(output_dir / f) for f in downloaded), encoding="utf-8")
        print(f"文件列表已写入：{list_file}")


if __name__ == "__main__":
    main()
