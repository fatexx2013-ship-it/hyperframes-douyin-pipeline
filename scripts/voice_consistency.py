#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""KB-A9 单线音色一致性校验（单线「单音色」硬约束 + F0 漂移判据）

引入背景（2026-10-09）
--------------------
story/howtolivebetter-54k 成片被反馈"一会儿御姐音、一会儿普通女声"。根因：
build_audio.py 逐句调 qa.generate_qwen3_tts(text, raw, "answer")，其中
role != "question" 时走 match_emotion(text) **逐句**挑情绪参考音，句 3 命中
excited → 参考音由 yujie_thoughtful.wav 换成 yujie_excited.wav，同一片出现
两种音色。旧质检只有「逐段 F0 中位 > 1.3× 全曲中位」单边界判据，句 3 比值
1.17 未触发 → 漏检。

本脚本 = 单线音色一致性判据真源（接入 build_audio 配音构建 + storyctl build --qc）
-----------------------------------------------------------------------------
  判据1（硬，rc=2）参考音唯一性：全篇所有句子所用 ref_audio 必须为同一个。
        证据优先取 build_audio 实测落盘的 ref_audio + ref_sha256（manifest）；
        缺失时按 legacy match_emotion 规则对 script.json 文本推定，并在报告里
        标注 evidence="inferred"，不得当作实测同音色证据。
  判据2（漂移，rc=3）逐句 F0 中位 / 全篇 F0 中位 的双侧比值必须 ∈ [1/T, T]，
        T 由旧规范的单边界 1.3 **收紧为双侧 1.20**；另附高音区 P90 双侧 1.30
        检出项（advisory，句 3 型"高把位换音色"在 P90 上更敏感）。

适用范围：仅单人线（voice_mode=single_narrator 或 tts_line 以 "solo" 开头）。
双人线（gen_guimi_dub.py）与其他生成器**不适用** → SKIP（rc=0），不改其默认行为。

退出码：0 通过 / 1 内部故障 / 2 硬判据未过 / 3 仅漂移判据未过
        （--strict：把 3 升级为 2，供 storyctl --strict-voice 阻断用途）

F0 测点口径（本段即真源，同时写入报告 JSON 的 measurement 段）
-----------------------------------------------------------
  librosa.pyin，fmin=60Hz / fmax=400Hz / frame_length=40ms / hop_length=10ms；
  仅统计 voiced_prob>0.5 的浊音帧；句级取值 = 浊音帧 F0 的 中位数 与 P90。
  全篇基准 = 各句中位数的中位数（比"整轨混算"更抗单句长度与停顿权重影响）。
  依赖 librosa：若当前解释器缺库，自动 re-exec 到 qwen3 venv 解释器
  （~/Projects/qwen3-tts-apple-silicon/.venv/bin/python）。
"""
import argparse
import hashlib
import json
import os
import statistics
import sys
import time

ROOT = "/Volumes/PSSD/抖音视频"
DEFAULT_MAX_MEDIAN_RATIO = 1.20
DEFAULT_MAX_P90_RATIO = 1.30
MEASUREMENT = {
    "tool": "librosa.pyin",
    "fmin": 60, "fmax": 400, "frame_length_ms": 40, "hop_length_ms": 10,
    "voiced_prob_min": 0.5,
    "line_stat": "median_f0 / p90_f0 over voiced frames",
    "corpus_stat": "median of per-line medians",
}

EXIT_OK, EXIT_ORCH, EXIT_HARD, EXIT_DRIFT = 0, 1, 2, 3


# ── librosa 依赖：缺库时自愈 re-exec 到 qwen3 venv ────────────────────────
def _reexec_with_librosa() -> bool:
    """返回 True 表示可以继续（已具备 librosa）。缺库时尝试 re-exec。"""
    try:
        import librosa  # noqa: F401
        return True
    except Exception:
        pass
    if os.environ.get("VOICE_QC_REEXEC") == "1":
        return False
    venv = os.path.expanduser("~/Projects/qwen3-tts-apple-silicon/.venv/bin/python")
    if not os.path.exists(venv):
        return False
    env = dict(os.environ, VOICE_QC_REEXEC="1")
    os.execve(venv, [venv, os.path.abspath(__file__)] + sys.argv[1:], env)
    return False  # not reached


def _sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for blk in iter(lambda: f.read(1 << 20), b""):
            h.update(blk)
    return h.hexdigest()


def _is_single_line(script: dict) -> tuple:
    vm = str(script.get("voice_mode") or "").strip()
    tl = str(script.get("tts_line") or "").strip().lower()
    if vm == "single_narrator" or tl.startswith("solo"):
        return True, f"voice_mode={vm!r} tts_line={tl!r}"
    return False, f"voice_mode={vm!r} tts_line={tl!r}（非单人线）"


def _legacy_infer_refs(texts: list) -> list:
    """按 legacy 规则（generate_qa_video.match_emotion）推定每句参考音。"""
    sys.path.insert(0, ROOT)
    try:
        import generate_qa_video as qa  # noqa
    except Exception as e:  # pragma: no cover
        return [{"ref_audio": None, "emotion": None,
                 "ref_source": f"unavailable(import failed: {type(e).__name__})"}
                for _ in texts]
    out = []
    for t in texts:
        emo = qa.match_emotion(t)
        ref = qa.EMOTION_REFS.get(emo, {}).get("audio")
        out.append({"ref_audio": os.path.join(qa.QWEN3_DIR, "voices", ref) if ref else None,
                    "emotion": emo, "ref_source": "inferred(legacy match_emotion)"})
    return out


def _measure_f0(path: str) -> dict:
    import numpy as np
    import librosa
    import soundfile as sf
    y, sr = sf.read(path, dtype="float32")
    if getattr(y, "ndim", 1) > 1:
        y = y.mean(axis=1)
    if len(y) == 0:
        return {"voiced_frames": 0, "f0_median": None, "f0_p90": None}
    frame = int(MEASUREMENT["frame_length_ms"] / 1000 * sr)
    hop = int(MEASUREMENT["hop_length_ms"] / 1000 * sr)
    f0v, _, vprob = librosa.pyin(y, fmin=MEASUREMENT["fmin"], fmax=MEASUREMENT["fmax"], sr=sr,
                                 frame_length=frame, hop_length=hop)
    m = np.isfinite(f0v) & (vprob > MEASUREMENT["voiced_prob_min"])
    v = f0v[m]
    if len(v) == 0:
        return {"voiced_frames": 0, "f0_median": None, "f0_p90": None, "sample_rate": int(sr)}
    return {"voiced_frames": int(m.sum()), "f0_median": round(float(np.median(v)), 1),
            "f0_p90": round(float(np.percentile(v, 90)), 1), "sample_rate": int(sr)}


def _load_ref_evidence(sd: str, script: dict, refs_json: str) -> tuple:
    """返回 (evidence_list, evidence_level)。evidence_list[i] 对应当前 story 的第 i 句。"""
    if refs_json:
        data = json.load(open(refs_json, encoding="utf-8"))
        lines = data.get("lines", data if isinstance(data, list) else [])
        return ([{"ref_audio": ln.get("ref_audio"), "ref_sha256": ln.get("ref_sha256"),
                  "emotion": ln.get("emotion"), "ref_source": ln.get("ref_source", "cli-manifest")}
                 for ln in lines], "manifest")
    tj = os.path.join(sd, "timing.json")
    if os.path.exists(tj):
        try:
            data = json.load(open(tj, encoding="utf-8"))
        except Exception:
            data = []
        if isinstance(data, list) and data and any(isinstance(x, dict) and x.get("ref_audio") for x in data):
            return ([{"ref_audio": x.get("ref_audio"), "ref_sha256": x.get("ref_sha256"),
                      "emotion": x.get("emotion"), "ref_source": x.get("ref_source", "build_audio manifest")}
                     for x in data], "manifest")
    texts = [str((sc.get("lines") or [{}])[0].get("text") or "") for sc in (script.get("scenes") or [])]
    if not texts:
        texts = [str(ln.get("text") or "") for ln in (script.get("lines") or [])]
    return (_legacy_infer_refs(texts), "inferred")


def _audio_paths(sd: str, script: dict, n_refs: int) -> list:
    tj = os.path.join(sd, "timing.json")
    if os.path.exists(tj):
        try:
            data = json.load(open(tj, encoding="utf-8"))
            if isinstance(data, list) and data:
                paths = [x.get("path") for x in data if isinstance(x, dict)]
                if paths and all(paths):
                    return paths
        except Exception:
            pass
    n = max(n_refs, len(script.get("scenes") or []), len(script.get("lines") or []))
    return [os.path.join(sd, f"line_{i:02d}.wav") for i in range(n)]


def main() -> int:
    ap = argparse.ArgumentParser(description="KB-A9 单线音色一致性校验")
    ap.add_argument("story_dir")
    ap.add_argument("--refs-json", default="", help="外部参考音清单（含 ref_audio/ref_sha256）")
    ap.add_argument("--json", default="", help="报告落盘路径（默认 <story>/qc/voice_consistency.json）")
    ap.add_argument("--max-median-ratio", type=float, default=DEFAULT_MAX_MEDIAN_RATIO)
    ap.add_argument("--max-p90-ratio", type=float, default=DEFAULT_MAX_P90_RATIO)
    ap.add_argument("--strict", action="store_true", help="漂移判据升级为阻断（rc3→rc2）")
    ap.add_argument("--cast", action="store_true",
                    help="多角色模式（增量4）：断言角色间 F0 可分辨且组内无漂移")
    ap.add_argument("--cast-dir", default="", help="cast 音频目录（默认 <story>/cast/）")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    sd = os.path.abspath(os.path.expanduser(args.story_dir))
    if not os.path.isdir(sd):
        print(f"[voice-qc] 内部故障：story 目录不存在 {sd}", file=sys.stderr)
        return EXIT_ORCH
    if not _reexec_with_librosa():
        print("[voice-qc] 内部故障：解释器缺 librosa 且 qwen3 venv 不可用，"
              "无法测 F0（拒绝空口通过）", file=sys.stderr)
        return EXIT_ORCH

    if args.cast:
        return _cast_main(sd, args)

    script_path = os.path.join(sd, "script.json")
    script = json.load(open(script_path, encoding="utf-8")) if os.path.exists(script_path) else {}
    name = os.path.basename(sd)
    report = {
        "schema": "voice_consistency/v1",
        "story": name, "story_dir": sd, "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "thresholds": {"max_median_ratio": args.max_median_ratio,
                       "max_p90_ratio": args.max_p90_ratio, "strict": bool(args.strict)},
        "measurement": MEASUREMENT,
        "lines": [], "hard_failures": [], "drift_failures": [], "notes": [],
    }

    single, why = _is_single_line(script)
    if not single:
        report["verdict"] = "SKIP"
        report["mode"] = "not_single_narrator"
        report["notes"].append(f"非单人线，判据不适用（{why}）；双人线/其他生成器既有默认行为不变")
        _emit(report, sd, args)
        return EXIT_OK
    report["mode"] = "single_narrator"

    ev, level = _load_ref_evidence(sd, script, args.refs_json)
    report["ref_evidence_level"] = level
    audio_paths = _audio_paths(sd, script, len(ev))
    n = min(len(ev), len(audio_paths))

    # 逐句：参考音证据 + F0 测点
    for i in range(n):
        rec = {"index": i, "audio": audio_paths[i],
               "ref_audio": ev[i].get("ref_audio"), "ref_sha256": ev[i].get("ref_sha256"),
               "emotion": ev[i].get("emotion"), "ref_source": ev[i].get("ref_source")}
        if os.path.exists(audio_paths[i]):
            rec.update(_measure_f0(audio_paths[i]))
        else:
            rec.update({"voiced_frames": 0, "f0_median": None, "f0_p90": None, "flag": "audio_missing"})
            report["hard_failures"].append(f"line#{i} 音频缺失：{audio_paths[i]}")
        report["lines"].append(rec)

    # ── 判据1：参考音唯一性（硬） ─────────────────────────────
    keys = []
    for rec in report["lines"]:
        if rec.get("ref_sha256"):
            keys.append(("sha256", rec["ref_sha256"]))
        elif rec.get("ref_audio"):
            keys.append(("path", os.path.basename(str(rec["ref_audio"]))))
        else:
            keys.append(("none", f"line#{rec['index']}"))
    uniq = sorted({k for k in keys})
    report["ref_keys"] = [f"{k[0]}:{k[1]}" for k in uniq]
    if len(uniq) != 1:
        report["hard_failures"].append(
            "判据1 参考音唯一性未过：全篇出现 %d 个不同参考音 %s"
            % (len(uniq), [f"{k[0]}:{k[1]}" for k in uniq]))
    if level == "inferred":
        report["notes"].append(
            "参考音证据为 legacy 规则推定（build_audio 未落盘实测 ref_sha256），"
            "判定结果不作实测同音色证据，建议重跑 build_audio 固化证据")

    # ── 判据2：F0 中位双侧比值 + P90 双侧（漂移） ──────────────
    meds = [r["f0_median"] for r in report["lines"] if r.get("f0_median")]
    p90s = [r["f0_p90"] for r in report["lines"] if r.get("f0_p90")]
    if meds:
        base_med = statistics.median(meds)
        base_p90 = statistics.median(p90s) if p90s else None
        report["baseline_f0_median"] = round(base_med, 1)
        report["baseline_f0_p90"] = round(base_p90, 1) if base_p90 else None
        for r in report["lines"]:
            if not r.get("f0_median"):
                continue
            r_med = r["f0_median"] / base_med
            r["ratio_median"] = round(r_med, 3)
            if r.get("f0_p90") and base_p90:
                r_p90 = r["f0_p90"] / base_p90
                r["ratio_p90"] = round(r_p90, 3)
                if r_p90 > args.max_p90_ratio or r_p90 < 1 / args.max_p90_ratio:
                    r["flag_p90"] = "p90_drift"
                    report["notes"].append(
                        f"line#{r['index']} 高音区 P90 比值 {r_p90:.3f} 超 1±{args.max_p90_ratio - 1:.2f}"
                        f"（advisory：疑似高把位换音色）")
            if r_med > args.max_median_ratio or r_med < 1 / args.max_median_ratio:
                r["flag_median"] = "median_drift"
                report["drift_failures"].append(
                    f"line#{r['index']} F0 中位 {r['f0_median']}Hz / 全篇 {base_med:.1f}Hz = "
                    f"{r_med:.3f}，超双侧阈 1±{args.max_median_ratio - 1:.2f}")
    else:
        report["hard_failures"].append("判据2 无法执行：全篇无可用 F0 测点（拒绝空口通过）")

    strict = args.strict
    if report["hard_failures"]:
        report["verdict"] = "FAIL_REF"
        rc = EXIT_HARD
    elif report["drift_failures"]:
        report["verdict"] = "FAIL_DRIFT"
        rc = EXIT_HARD if strict else EXIT_DRIFT
    else:
        report["verdict"] = "PASS"
        rc = EXIT_OK
    report["exit_code"] = rc
    _emit(report, sd, args)
    return rc


def _cast_main(sd: str, args) -> int:
    """多角色模式（增量4）：按角色分组断言「组内无漂移 + 角色间可分辨」。

    cast 音频目录约定：<story>/cast/role_<role_num>_<idx>.wav
    - 判据A（硬）：每个角色至少 1 条音频，F0 可测；
    - 判据B（硬）：不同角色 F0 中位差异 ≥ 8% 才算可分辨（防同音色糊在一起）；
    - 判据C（advisory）：组内 F0 中位比值在 1±max_median_ratio 内（无漂移）。
    默认单人线逻辑不经过此分支。
    """
    cast_dir = os.path.abspath(os.path.expanduser(args.cast_dir or os.path.join(sd, "cast")))
    report = {
        "schema": "voice_consistency/v1", "mode": "multi_cast",
        "story": os.path.basename(sd), "story_dir": sd, "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "thresholds": {"min_role_sep_ratio": 0.08, "max_median_ratio": args.max_median_ratio,
                       "max_p90_ratio": args.max_p90_ratio},
        "roles": [], "hard_failures": [], "drift_failures": [], "notes": [],
    }
    if not os.path.isdir(cast_dir):
        report["hard_failures"].append(f"cast 目录不存在：{cast_dir}（先跑 tts_cast.py）")
        report["verdict"] = "FAIL_REF"
        report["exit_code"] = EXIT_HARD
        _emit(report, sd, args)
        return EXIT_HARD

    role_files: dict[int, list[str]] = {}
    for fn in sorted(os.listdir(cast_dir)):
        if not fn.startswith("role_") or not fn.endswith(".wav"):
            continue
        try:
            rid = int(fn.split("_")[1])
        except (IndexError, ValueError):
            continue
        role_files.setdefault(rid, []).append(os.path.join(cast_dir, fn))

    if len(role_files) < 3:
        report["hard_failures"].append(
            f"多角色验收需 ≥3 个角色，当前仅 {len(role_files)} 个（{sorted(role_files)}）")

    for rid in sorted(role_files):
        meds = []
        for p in role_files[rid]:
            m = _measure_f0(p)
            rec = {"role": rid, "file": p}
            rec.update(m)
            if m["f0_median"]:
                meds.append(m["f0_median"])
            if m["voiced_frames"] == 0:
                rec["flag"] = "audio_missing"
            report["roles"].append(rec)
        if not meds:
            report["hard_failures"].append(f"角色#{rid} 无可用 F0 测点（拒绝空口通过）")
        else:
            med = statistics.median(meds)
            for rec in report["roles"]:
                if rec["role"] != rid or not rec.get("f0_median"):
                    continue
                r_med = rec["f0_median"] / med
                rec["ratio_median_inrole"] = round(r_med, 3)
                if r_med > args.max_median_ratio or r_med < 1 / args.max_median_ratio:
                    rec["flag"] = (rec.get("flag") or "") + "|inrole_drift"
                    report["drift_failures"].append(
                        f"角色#{rid} 组内漂移：F0 {rec['f0_median']}Hz / 组内 {med:.1f}Hz = {r_med:.3f}")

    # 角色间可分辨性：组间 F0 中位差异 ≥ 8%
    group_med = {rid: statistics.median([r["f0_median"] for r in report["roles"]
                                         if r["role"] == rid and r.get("f0_median")])
                 for rid in role_files}
    report["role_f0_median"] = {str(k): round(v, 1) for k, v in sorted(group_med.items())}
    pairs = [(a, b) for i, a in enumerate(sorted(group_med)) for b in sorted(group_med)[i + 1:]]
    for a, b in pairs:
        va, vb = group_med[a], group_med[b]
        if not va or not vb:
            continue
        diff = abs(va - vb) / max(va, vb)
        if diff < 0.08:
            report["drift_failures"].append(
                f"角色#{a}({va:.0f}Hz) 与角色#{b}({vb:.0f}Hz) F0 差异 {diff:.1%} < 8%，不可分辨")

    if report["hard_failures"]:
        report["verdict"] = "FAIL_REF"
        rc = EXIT_HARD
    elif report["drift_failures"]:
        report["verdict"] = "FAIL_DRIFT"
        rc = EXIT_HARD if args.strict else EXIT_DRIFT
    else:
        report["verdict"] = "PASS"
        rc = EXIT_OK
    report["exit_code"] = rc
    _emit(report, sd, args)
    return rc


def _emit(report: dict, sd: str, args) -> None:
    out = args.json or os.path.join(sd, "qc", "voice_consistency.json")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    if args.quiet:
        print(f"[voice-qc] {report.get('verdict')} → {out}")
        return
    print(f"[voice-qc] story={report.get('story')} mode={report.get('mode')} "
          f"verdict={report.get('verdict')} rc={report.get('exit_code')}")
    if report.get("baseline_f0_median"):
        print(f"[voice-qc] 全篇 F0 中位 {report['baseline_f0_median']}Hz / P90 "
              f"{report.get('baseline_f0_p90')}Hz；阈值 中位双侧 1±"
              f"{report['thresholds']['max_median_ratio'] - 1:.2f}、P90 双侧 1±"
              f"{report['thresholds']['max_p90_ratio'] - 1:.2f}")
    for r in report.get("lines", []):
        print("  line#%02d ref=%-24s med=%-6s ratio=%-6s p90ratio=%-6s %s" % (
            r.get("index", -1), os.path.basename(str(r.get("ref_audio"))) if r.get("ref_audio") else "-",
            r.get("f0_median"), r.get("ratio_median"), r.get("ratio_p90"),
            ",".join(x for x in (r.get("flag_median"), r.get("flag_p90"), r.get("flag")) if x)))
    for t in report.get("hard_failures", []):
        print(f"  [HARD] {t}")
    for t in report.get("drift_failures", []):
        print(f"  [DRIFT] {t}")
    for t in report.get("notes", []):
        print(f"  [note] {t}")
    print(f"[voice-qc] 报告 → {out}")


if __name__ == "__main__":
    sys.exit(main())
