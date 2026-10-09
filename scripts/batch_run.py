#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
批量出片编排器（增量2）

一次排队 N 条，自动逐条过门禁出片；中途失败不影响其余条目；可断点续跑。

用法:
    # 干跑：只打印计划不执行
    python3 scripts/batch_run.py --from-queue story/_queue/topics-20261009.json --take 3 --dry-run

    # 实跑：批量出片（每条独立过 storyctl build --qc）
    python3 scripts/batch_run.py --from-queue story/_queue/topics-20261009.json --take 3

    # 按已有 story 列表批量
    python3 scripts/batch_run.py --stories "topic-123456 topic-789012" --dry-run

设计要点:
    - 幂等：batch_state.json 记录每条每阶段状态，重跑自动跳过已完成条目
    - 失败隔离：单条失败标记 failed，继续下一条；Ctrl-C 保存状态后退出
    - 并发策略读 config/batch_pipeline.yaml（TTS 串行 / 下载并发 / 渲染串行 → 本版全串行执行）
    - 每条 story 出片前自动组装 script.json（文案来自 generate_script.py --demo 的 script.txt）
"""

import argparse
import json
import os
import re
import signal
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent.resolve()
QUEUE_DIR = BASE_DIR / "story" / "_queue"
STATE_FILE = QUEUE_DIR / "batch_state.json"
PIPELINE_YAML = BASE_DIR / "config" / "batch_pipeline.yaml"
REPORTS_DIR = BASE_DIR / "reports"
TEMPLATE_STORY = "compositor-mac"
PY = sys.executable

_state_dirty = False


def log(msg: str) -> None:
    print(f"[batch] {msg}", flush=True)


def load_pipeline() -> dict:
    try:
        import yaml
    except ImportError:
        yaml = None
    if yaml is None or not PIPELINE_YAML.is_file():
        return {"pipeline": "douyin-batch", "stages": []}
    with open(PIPELINE_YAML, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def load_state() -> dict:
    if STATE_FILE.is_file():
        try:
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            pass
    return {"created_at": datetime.now().isoformat(timespec="seconds"), "items": {}}


def save_state(state: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    state["updated_at"] = datetime.now().isoformat(timespec="seconds")
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n",
                          encoding="utf-8")


def load_queue(path: Path) -> list:
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return data if isinstance(data, list) else []


def story_name_for(item: dict, fallback: str) -> str:
    src = item.get("source_ref") or item.get("id") or fallback
    name = f"topic-{src}"
    name = re.sub(r"[^0-9A-Za-z._-]", "-", name)
    return name


def split_script_text(text: str, max_lines: int = 6) -> list[str]:
    """把 script.txt 文案按句切分，作为 script.json 的口播行。"""
    parts = re.split(r"(?<=[。！？.!?])", text.strip())
    lines = [p.strip() for p in parts if p.strip()]
    if not lines and text.strip():
        lines = [text.strip()]
    return lines[:max_lines]


def compose_topic_script(item: dict, story_dir: Path, script_lines: list[str]) -> None:
    """从队列条目组装 script.json（基于模板骨架，保证通过内容校验）。"""
    tpl_sp = BASE_DIR / "story" / TEMPLATE_STORY / "script.json"
    if not tpl_sp.is_file():
        raise RuntimeError(f"模板 script.json 缺失：{tpl_sp}")
    data = json.loads(tpl_sp.read_text(encoding="utf-8"))

    title = (item.get("title") or "选题情报")[:14]
    hook = item.get("hook") or title
    source_ref = item.get("source_ref") or ""
    source = f"RAG知识库/topics 广播选题池（source_ref={source_ref}）"

    lines = script_lines or [hook, "这期内容来自今日广播选题池，数据可溯源。", "更多细节评论区见。"]
    category = item.get("category") or "-"
    score = item.get("score") if item.get("score") is not None else "-"
    scenes = []
    # header 开场（对齐模板 scenes[0] 结构）
    scenes.append({
        "type": "header",
        "visual": "chip",
        "card": {
            "eyebrow": "广播选题 · 今日情报",
            "title": title,
            "subtitle": source,
            "stats": [
                {"k": "分类", "v": str(category)},
                {"k": "评分", "v": str(score)},
                {"k": "来源", "v": "RAG知识库"},
            ],
        },
        "lines": [{"role": "answer", "text": hook}],
    })
    # 中间 feature（模板 scenes[1..n-1] 结构）
    for i, line in enumerate(lines[1:], 1):
        scenes.append({
            "type": "feature",
            "visual": "chip",
            "card": {
                "eyebrow": f"广播选题 {i}/{max(len(lines), 1)}",
                "title": line[:22],
                "subtitle": source,
            },
            "lines": [{"role": "answer", "text": line}],
        })
    # outro 结尾（模板 scenes[-1] 结构，必须含 cta）
    scenes.append({
        "type": "outro",
        "visual": "chip",
        "card": {
            "title": "关注 jerrychen2001",
            "cta": "评论区聊聊",
            "sub": "完整数据与来源见评论区",
        },
        "lines": [{"role": "answer", "text": "这期内容来自今日广播选题池，数据可溯源。更多细节评论区见。"}],
    })
    # 去掉模板的 scenes，替换为自动组装场景
    data["scenes"] = scenes
    data["title"] = title
    data["date"] = datetime.now().strftime("%Y.%m.%d")
    data["source"] = source
    data["watermark"] = "jerrychen2001"
    data["voice_mode"] = "single_narrator"
    data["voice_engine"] = "qwen3"
    data["voice_role"] = "answer"
    data["epilogue"] = {
        "enabled": True,
        "text": "关注 jerrychen2001，评论区聊聊这个选题。",
        "emotion": "thoughtful",
        "bgm_volume": 0.18,
    }
    (story_dir / "script.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def run_step(cmd: list, cwd: Path, timeout: int = 3600) -> tuple[int, str]:
    log("执行: " + " ".join(str(c) for c in cmd[:3]) + " ...")
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout)
    tail = (r.stdout or "")[-400:] + (("\n[stderr] " + r.stderr[-400:]) if r.stderr else "")
    return r.returncode, tail


def ensure_path() -> None:
    """补齐 macOS 常用工具链 PATH（node/npx 位于 /opt/homebrew/bin），不影响脚本逻辑。"""
    extra = [p for p in ("/opt/homebrew/bin", "/usr/local/bin", os.path.expanduser("~/.npm-global/bin"))
             if os.path.isdir(p) and p not in os.environ.get("PATH", "").split(":")]
    if extra:
        os.environ["PATH"] = ":".join(extra + [os.environ.get("PATH", "")])
        log(f"PATH 已注入：{', '.join(extra)}")


def process_item(item: dict, name: str, state: dict, dry: bool) -> dict:
    """处理单条：文案 → 脚手架 → script.json → build --qc。返回该条阶段状态。"""
    st = state["items"].get(name, {"stages": {}})
    story_dir = BASE_DIR / "story" / name

    # 阶段 script：文案（幂等：script.txt 已有则跳过）
    if st.get("status") == "done":
        log(f"⏭️ {name} 已 done，跳过")
        return st
    if st["stages"].get("script", {}).get("status") == "done" and (story_dir / "script.txt").is_file():
        pass  # 已有文案
    elif not (story_dir / "script.txt").is_file():
        t0 = time.time()
        if dry:
            st["stages"]["script"] = {"status": "pending", "note": "dry-run"}
            log(f"  [dry] 生成文案 story/{name}/script.txt")
        else:
            out_script = story_dir / "script.txt"
            r = subprocess.run(
                [PY, str(BASE_DIR / "scripts" / "generate_script.py"),
                 "--topic", item.get("title", ""), "--demo", "--output", str(out_script)],
                cwd=BASE_DIR, capture_output=True, text=True, timeout=180)
            if r.returncode != 0:
                st["stages"]["script"] = {"status": "failed", "error": (r.stderr or "")[-200:],
                                          "elapsed": round(time.time() - t0, 1)}
                st["status"] = "failed"
                return st
            st["stages"]["script"] = {"status": "done", "elapsed": round(time.time() - t0, 1)}

    # 阶段 scaffold：storyctl new（幂等：目录存在且脚手架齐全则跳过；
    # 目录存在但缺脚手架（如仅 discovery 生成的 script.txt）→ 先移出文案再重建）
    scaffold_marker = story_dir / "build_audio.py"
    if not story_dir.is_dir():
        t0 = time.time()
        if dry:
            st["stages"]["scaffold"] = {"status": "pending", "note": "dry-run"}
            log(f"  [dry] storyctl new {name}")
        else:
            r = subprocess.run([PY, str(BASE_DIR / "scripts" / "storyctl.py"), "new", name],
                               cwd=BASE_DIR, capture_output=True, text=True, timeout=120)
            if r.returncode != 0:
                st["stages"]["scaffold"] = {"status": "failed", "error": (r.stderr or "")[-200:],
                                            "elapsed": round(time.time() - t0, 1)}
                st["status"] = "failed"
                return st
            st["stages"]["scaffold"] = {"status": "done", "elapsed": round(time.time() - t0, 1)}
    elif not scaffold_marker.is_file():
        # 续跑修复：仅含 script.txt 的目录（discovery 产物）→ 移出文案、重建脚手架
        t0 = time.time()
        if dry:
            st["stages"]["scaffold"] = {"status": "pending", "note": "dry-run(重建脚手架)"}
            log(f"  [dry] 重建脚手架 {name}（现有目录缺 build_audio.py）")
        else:
            moved = None
            script_file = story_dir / "script.txt"
            if script_file.is_file():
                moved = QUEUE_DIR / f".{name}.script.txt"
                moved.parent.mkdir(parents=True, exist_ok=True)
                script_file.replace(moved)
            try:
                story_dir.rmdir()  # 只对空目录生效；非空则报错走失败分支
            except OSError as exc:
                st["stages"]["scaffold"] = {"status": "failed",
                                            "error": f"目录非空无法重建: {exc}"}
                st["status"] = "failed"
                if moved is not None:
                    moved.replace(story_dir / "script.txt")
                return st
            r = subprocess.run([PY, str(BASE_DIR / "scripts" / "storyctl.py"), "new", name],
                               cwd=BASE_DIR, capture_output=True, text=True, timeout=120)
            if r.returncode != 0:
                st["stages"]["scaffold"] = {"status": "failed", "error": (r.stderr or "")[-200:],
                                            "elapsed": round(time.time() - t0, 1)}
                st["status"] = "failed"
                if moved is not None:
                    (story_dir / "script.txt").parent.mkdir(parents=True, exist_ok=True)
                    moved.replace(story_dir / "script.txt")
                return st
            if moved is not None:
                (story_dir / "script.txt").parent.mkdir(parents=True, exist_ok=True)
                moved.replace(story_dir / "script.txt")
            st["stages"]["scaffold"] = {"status": "done", "elapsed": round(time.time() - t0, 1),
                                        "note": "已重建脚手架"}
    else:
        st["stages"]["scaffold"] = {"status": "done", "note": "已存在（幂等）"}

    # 阶段 compose：组装 script.json（幂等：已有且非模板占位则跳过）
    sp = story_dir / "script.json"
    script_lines = []
    if (story_dir / "script.txt").is_file():
        script_lines = split_script_text((story_dir / "script.txt").read_text(encoding="utf-8"))
    need_compose = True
    if sp.is_file() and st["stages"].get("compose", {}).get("status") == "done":
        need_compose = False
    if need_compose:
        t0 = time.time()
        if dry:
            st["stages"]["compose"] = {"status": "pending", "note": "dry-run"}
            log(f"  [dry] 组装 script.json（{len(script_lines)} 句口播）")
        else:
            compose_topic_script(item, story_dir, script_lines)
            st["stages"]["compose"] = {"status": "done", "elapsed": round(time.time() - t0, 1)}

    # 阶段 build_qc：storyctl build --qc（两段门禁，全链路）
    t0 = time.time()
    if dry:
        st["stages"]["build_qc"] = {"status": "pending", "note": "dry-run"}
        log(f"  [dry] storyctl build --qc {name}")
        return st
    rc, tail = run_step([PY, str(BASE_DIR / "scripts" / "storyctl.py"), "build", "--qc", name],
                        BASE_DIR, timeout=5400)
    st["stages"]["build_qc"] = {
        "status": "done" if rc == 0 else "failed",
        "rc": rc,
        "elapsed": round(time.time() - t0, 1),
        "tail": tail[-500:],
    }
    st["status"] = "done" if rc == 0 else "failed"
    st["video"] = str(story_dir / "douyin_epilogue.mp4") if (story_dir / "douyin_epilogue.mp4").is_file() else ""
    return st


def write_batch_report(state: dict, queue_file: Path, take: int) -> Path:
    """产出 reports/batch-YYYYMMDD.md。"""
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    date = datetime.now().strftime("%Y-%m-%d")
    out = REPORTS_DIR / f"batch-{datetime.now().strftime('%Y%m%d')}.md"
    items = state["items"]
    ok = sum(1 for v in items.values() if v.get("status") == "done")
    failed = sum(1 for v in items.values() if v.get("status") == "failed")
    skipped = sum(1 for v in items.values() if v.get("status") == "skipped")
    lines = [
        f"# 批量出片报告 · {date}",
        "",
        f"> 队列：{queue_file.name} ｜ 目标：{take} 条 ｜ 完成：{ok} ｜ 失败：{failed} ｜ 跳过：{skipped}",
        "",
        "## 明细",
        "",
        "| story | 状态 | 耗时(s) | 视频路径 | 备注 |",
        "|---|---|---|---|---|",
    ]
    for name, v in items.items():
        bg = v.get("stages", {}).get("build_qc", {})
        lines.append(
            f"| {name} | {v.get('status', 'pending')} | "
            f"{bg.get('elapsed', '-')} | {v.get('video', '-')} | "
            f"{(bg.get('tail') or '')[:80]} |")
    lines += ["", "## 失败原因", ""]
    for name, v in items.items():
        for stage, sv in v.get("stages", {}).items():
            if sv.get("status") == "failed":
                lines.append(f"- **{name} / {stage}**：{sv.get('error', sv.get('tail', ''))[:200]}")
    lines.append("")
    out.write_text("\n".join(lines), encoding="utf-8")
    return out


def main() -> int:
    global _state_dirty
    parser = argparse.ArgumentParser(description="批量出片编排器（增量2）")
    parser.add_argument("--from-queue", default="", help="队列文件 story/_queue/topics-YYYYMMDD.json")
    parser.add_argument("--stories", default="", help="直接指定 story 名列表（空格分隔）")
    parser.add_argument("--take", type=int, default=0, help="最多处理 N 条")
    parser.add_argument("--dry-run", action="store_true", help="只打印计划不执行")
    args = parser.parse_args()

    pipeline = load_pipeline()
    if args.dry_run:
        log(f"流水线：{pipeline.get('pipeline', '?')}（阶段序列："
            + " → ".join(s["title"] for s in pipeline.get("stages", [])) + "）")

    # 构造条目
    queue_file = None
    items = []
    if args.from_queue:
        queue_file = Path(args.from_queue)
        if not queue_file.is_file():
            log(f"❌ 队列不存在：{queue_file}")
            return 2
        q = load_queue(queue_file)
        take = args.take or len(q)
        # 只从未处理（pending）条目中取前 take 条；已 done 的跳过不计入名额
        pending = [it for it in q if it.get("status", "pending") == "pending"]
        for it in pending[:take]:
            name = story_name_for(it, fallback=f"{datetime.now().strftime('%Y%m%d')}-{len(items)+1}")
            items.append((name, it))
        if args.dry_run:
            log(f"队列 {queue_file.name}：{len(q)} 条，待处理 {len(pending)} 条，本次处理 {len(items)} 条（take={take}）")
    elif args.stories:
        for s in args.stories.split():
            items.append((s.strip(), {"title": s.strip(), "hook": s.strip(), "source_ref": ""}))
    else:
        log("需要 --from-queue 或 --stories")
        return 2

    state = load_state()

    ensure_path()

    def _sigint(signum, frame):
        log("收到 Ctrl-C：保存状态后退出")
        save_state(state)
        sys.exit(130)

    signal.signal(signal.SIGINT, _sigint)

    for name, item in items:
        st = state["items"].get(name)
        if st and st.get("status") == "done":
            log(f"⏭️ 断点续跑跳过：{name}（已 done）")
            continue
        state["items"][name] = process_item(item, name, state, args.dry_run)
        _state_dirty = True
        save_state(state)

    report = write_batch_report(state, queue_file or Path(""), len(items))
    log(f"📄 批次报告：{report}")
    if args.dry_run:
        log("dry-run 完成（未执行任何脚本）")
    else:
        done = sum(1 for v in state["items"].values() if v.get("status") == "done")
        failed = sum(1 for v in state["items"].values() if v.get("status") == "failed")
        log(f"完成：{done} 成功 / {failed} 失败")
    return 0


if __name__ == "__main__":
    sys.exit(main())
