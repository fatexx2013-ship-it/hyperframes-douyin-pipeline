#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
eof_anchor.py —— 终界锚（EOF anchor）工具 · 层 r2-1.0.0

吸纳口径（AI-Film-Studio 广播 366326255814967296）：
    「无人值守链路上 exit code=0 会掩盖 stdout 中途截断；成功判据必须落在
      跨边界完整性证明上，而不是本地进程状态。」
实现：
    1) seal   —— 为长输出工序产物签发终界锚（字节数 + sha256 + 终界标记 + 序号 + 签发域）
    2) verify —— 用锚校验实收内容；exit code 只作附注，绝不作成功判据
    3) verify-dir —— 按 config/absorb_r2.json 的 anchored_artifacts 全量校验
    4) selftest —— 正例 + 三条负控（截断 / 锚被篡改 / 无锚）

退出码：0=全部 OK（或 SKIP）；2=检出问题；1=工具自身故障
本工具只新增文件，不修改任何存量脚本/配置。
"""
from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import os
import shutil
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(ROOT, "config", "absorb_r2.json")
ANCHOR_VERSION = "eof-1.0.0"
ISSUER = "eof_anchor.py@eof-1.0.0"
DEFAULT_END_MARKER = "__EOF__"
READ_CHUNK = 1 << 20
TAIL_PROBE = 4096


def _now() -> str:
    return _dt.datetime.now().strftime("%Y-%m-%dT%H:%M:%S")


def load_policy() -> dict:
    with open(CONFIG_PATH, "r", encoding="utf-8") as fh:
        cfg = json.load(fh)
    policy = dict(cfg.get("eof_anchor", {}))
    policy.setdefault("end_marker", DEFAULT_END_MARKER)
    policy.setdefault("anchor_dir", "reports/absorb-r2/anchors")
    policy.setdefault("end_marker_required", False)
    policy.setdefault("anchored_artifacts", [])
    return policy


def file_facts(path: str) -> dict:
    """字节数 + sha256 + 尾部终界标记探测（流式，不整读入内存）。"""
    h = hashlib.sha256()
    size = 0
    tail = b""
    with open(path, "rb") as fh:
        while True:
            chunk = fh.read(READ_CHUNK)
            if not chunk:
                break
            h.update(chunk)
            size += len(chunk)
            tail = (tail + chunk)[-TAIL_PROBE:]
    return {"bytes": size, "sha256": h.hexdigest(), "tail": tail}


def anchor_path_for(rel: str, anchor_dir: str) -> str:
    safe = rel.replace("/", "__").replace("\\", "__")
    return os.path.join(ROOT, anchor_dir, safe + ".eof.json")


def cmd_seal(args) -> int:
    policy = load_policy()
    rel = os.path.relpath(os.path.abspath(args.artifact), ROOT)
    if not os.path.exists(args.artifact):
        print(json.dumps({"verdict": "ABSENT", "artifact": rel, "reason": "artifact_not_found"}, ensure_ascii=False))
        return 2
    facts = file_facts(args.artifact)
    anchor = {
        "anchor_version": ANCHOR_VERSION,
        "artifact": os.path.abspath(args.artifact),
        "artifact_rel": rel,
        "declared_bytes": facts["bytes"],
        "declared_sha256": facts["sha256"],
        "end_marker": policy["end_marker"],
        "end_marker_present": policy["end_marker"].encode("utf-8") in facts["tail"],
        "marker_required": policy["end_marker_required"],
        "seq": int(_dt.datetime.now().timestamp()),
        "issuer": ISSUER,
        "sealed_at": _now(),
    }
    out = args.out or anchor_path_for(rel, policy["anchor_dir"])
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(anchor, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    print(json.dumps({"verdict": "OK", "action": "seal", "artifact": rel,
                      "declared_bytes": facts["bytes"], "anchor": os.path.relpath(out, ROOT)},
                     ensure_ascii=False))
    return 0


def verify_one(anchor: dict, artifact_path: str, exit_code=None) -> dict:
    res = {
        "artifact": anchor.get("artifact_rel") or anchor.get("artifact"),
        "declared_bytes": anchor.get("declared_bytes"),
        "declared_sha256": anchor.get("declared_sha256"),
        "anchor_version": anchor.get("anchor_version"),
        "issuer": anchor.get("issuer"),
    }
    if not os.path.exists(artifact_path):
        res.update(verdict="ABSENT", reason="artifact_missing")
        return res
    facts = file_facts(artifact_path)
    res.update(actual_bytes=facts["bytes"], actual_sha256=facts["sha256"])
    declared_bytes = anchor.get("declared_bytes")
    marker_required = bool(anchor.get("marker_required"))
    marker_present = anchor.get("end_marker", DEFAULT_END_MARKER).encode("utf-8") in facts["tail"]

    if facts["bytes"] != declared_bytes:
        res.update(verdict="TRUNCATED" if facts["bytes"] < declared_bytes else "ANCHOR_MISMATCH",
                   reason="byte_count_mismatch")
    elif facts["sha256"] != anchor.get("declared_sha256"):
        res.update(verdict="ANCHOR_MISMATCH", reason="sha256_mismatch")
    elif marker_required and not marker_present:
        res.update(verdict="TRUNCATED", reason="end_marker_missing")
    else:
        res.update(verdict="OK", reason="integrity_proven")

    if exit_code is not None:
        res["exit_code"] = exit_code
        res["zero_exit_masking"] = bool(exit_code == 0 and res["verdict"] != "OK")
        # 铁律：exit code 不参与 verdict
    return res


def cmd_verify(args) -> int:
    with open(args.anchor, "r", encoding="utf-8") as fh:
        anchor = json.load(fh)
    artifact = args.artifact or anchor.get("artifact")
    res = verify_one(anchor, artifact, args.exit_code)
    print(json.dumps(res, ensure_ascii=False))
    return 0 if res["verdict"] in ("OK",) else 2


def cmd_verify_dir(args) -> int:
    policy = load_policy()
    results = []
    for rel in policy["anchored_artifacts"]:
        ap = anchor_path_for(rel, policy["anchor_dir"])
        if not os.path.exists(ap):
            results.append({"artifact": rel, "verdict": "ABSENT", "reason": "anchor_not_sealed_yet"})
            continue
        with open(ap, "r", encoding="utf-8") as fh:
            anchor = json.load(fh)
        results.append(verify_one(anchor, anchor.get("artifact")))
    bad = [r for r in results if r["verdict"] != "OK"]
    print(json.dumps({"layer": "eof_anchor@r2-1.0.0", "total": len(results),
                      "ok": len(results) - len(bad), "bad": len(bad), "results": results},
                     ensure_ascii=False, indent=2))
    return 0 if not bad else 2


# --------------------------------------------------------------------------- #
# 自检：正例 + 三条负控
# --------------------------------------------------------------------------- #
def cmd_selftest(args) -> int:
    policy = load_policy()
    tmp = tempfile.mkdtemp(prefix="eof_anchor_selftest_")
    cases = []

    # 正例：真实产物（若不存在则退化为自造样本）
    real = None
    for rel in policy["anchored_artifacts"]:
        cand = os.path.join(ROOT, rel)
        if os.path.exists(cand):
            real = cand
            break
    if real is None:
        real = os.path.join(tmp, "synthetic.bin")
        with open(real, "wb") as fh:
            fh.write(os.urandom(65536))
    good_anchor = {
        "anchor_version": ANCHOR_VERSION, "artifact": real, "artifact_rel": os.path.relpath(real, ROOT),
        "end_marker": policy["end_marker"], "marker_required": policy["end_marker_required"],
        "issuer": ISSUER,
    }
    good_anchor.update({k: v for k, v in zip(("declared_bytes", "declared_sha256"),
                                             (file_facts(real)["bytes"], file_facts(real)["sha256"]))})

    cases.append({"case": "pos-intact", "expect": "OK",
                  "got": verify_one(good_anchor, real)["verdict"]})

    # 负控 1：截断（真实产物去掉尾部 1024 字节，模拟 stdout 中途截断，且进程 exit 0）
    trunc = os.path.join(tmp, "truncated.bin")
    shutil.copyfile(real, trunc)
    with open(trunc, "r+b") as fh:
        fh.truncate(os.path.getsize(trunc) - min(1024, max(1, os.path.getsize(trunc) // 10)))
    r = verify_one(good_anchor, trunc, exit_code=0)
    cases.append({"case": "neg-truncated-zero-exit", "expect": "TRUNCATED", "got": r["verdict"],
                  "zero_exit_masking": r.get("zero_exit_masking")})

    # 负控 2a：锚被篡改（声明的 sha256 与实体不符）
    tampered = dict(good_anchor)
    tampered["declared_sha256"] = "0" * 64
    cases.append({"case": "neg-anchor-mismatch-sha", "expect": "ANCHOR_MISMATCH",
                  "got": verify_one(tampered, real)["verdict"]})

    # 负控 2b：锚声明字节数高于实体（锚侧虚报 / 内容被截）
    over = dict(good_anchor)
    over["declared_bytes"] = good_anchor["declared_bytes"] + 1
    cases.append({"case": "neg-declared-overcount", "expect": "TRUNCATED",
                  "got": verify_one(over, real)["verdict"]})

    # 负控 3：无锚/产物缺失
    cases.append({"case": "neg-absent", "expect": "ABSENT",
                  "got": verify_one(good_anchor, os.path.join(tmp, "does_not_exist.bin"))["verdict"]})

    # 负控 4：终界标记缺失（marker_required=True 时）
    marked = dict(good_anchor)
    marked["marker_required"] = True
    marked["declared_bytes"] = os.path.getsize(real)
    marked["declared_sha256"] = file_facts(real)["sha256"]
    cases.append({"case": "neg-end-marker-missing", "expect": "TRUNCATED",
                  "got": verify_one(marked, real)["verdict"]})

    bad = [c for c in cases if c["got"] != c["expect"]]
    print(json.dumps({"layer": "eof_anchor@r2-1.0.0", "mode": "selftest",
                      "real_artifact": os.path.relpath(real, ROOT),
                      "total": len(cases), "passed": len(cases) - len(bad), "failed": len(bad),
                      "cases": cases}, ensure_ascii=False, indent=2))
    shutil.rmtree(tmp, ignore_errors=True)
    return 0 if not bad else 2


def main() -> int:
    ap = argparse.ArgumentParser(description="终界锚工具（层 r2-1.0.0）")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("seal", help="为产物签发终界锚")
    p.add_argument("artifact")
    p.add_argument("--out", default=None)
    p.set_defaults(func=cmd_seal)

    p = sub.add_parser("verify", help="用锚校验产物")
    p.add_argument("anchor")
    p.add_argument("--artifact", default=None)
    p.add_argument("--exit-code", type=int, default=None)
    p.set_defaults(func=cmd_verify)

    p = sub.add_parser("verify-dir", help="按 config 全量校验已签发锚")
    p.set_defaults(func=cmd_verify_dir)

    p = sub.add_parser("selftest", help="正例 + 负控自检")
    p.set_defaults(func=cmd_selftest)

    args = ap.parse_args()
    try:
        return args.func(args)
    except Exception as exc:  # 工具自身故障
        print(json.dumps({"verdict": "TOOL_FAILURE", "error": repr(exc)}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    sys.exit(main())
