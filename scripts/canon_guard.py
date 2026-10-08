#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
canon_guard.py —— 工程口径吸纳层校验器（对等交换三轮共 22 组口径）

所属产线：hyperframes 竖屏短视频产线（部署根由 PIPELINE_HOME / 仓库位置决定）
真源    ：config/engineering_canons.json（canons 1.5.0，纯新增，未改动任何存量真源）
对接存量：config/param_contract.json / canonicalization.json / frozen_baseline.json
          / observability_rules.json / negcontrol_cases.json（只读引用，不修改）

覆盖口径（每组一条检查 + 负例）
------------------------------
  A. pending_ledger       挂起与判据账本（挂起原因落约束 / 同组织布尔 / 处置与变更触发分列）
  B. cache_key_grid       缓存键漂移五格（五类漂移 × 五维；前四格带签发方与版本；第五格降级命名不可覆盖）
  C. stop_degrade_tiers   硬停四类 / 降级三类；降级隔离标记；回落显式标记且标记自身不可回落
  D. zero_semantics       零值三态；音频流数缺失按失败处理；断言必须绑定失败动作
  E. drift_fieldset       最易漂字段集；翻案率按规则一行、按规则版本分组不跨版本求和；降级须带原因码与来源
  F. manifest_columns     清单五列填满；缺列视为未声明；回执必须带观测时刻
  G. field_registry       对存量 18 字段（10 核心 + 8 扩展）的零值三态归一与断言动作绑定
  H. bridge               与存量真源的对接一致性（字段集合、签名、摘要、负控用例引用）

第二轮（canons 1.1.0）
--------------------
  I. silent_rewrite           静默改写判定（显式指定变化可降级；未指定被静默改写升硬停）
  J. criteria_identity        判据身份三格（版本 + 签发方 + 生效起点）；版本换代单独出桶
  K. zero_declared_vs_default 零值语义补一格：未声明 ≠ 默认，不得合并取值
  L. pending_age_distribution 挂起年龄分布（起始时刻 + 重跑成本档；P50/P90/P99；阈值基数取当轮新增）
  M. overturn_denominator     翻案率分母只算已人工复核拒绝，未复核挂起单独出桶
  N. dependency_version_triple 依赖版本三段（来源 / 内容 / 已加载），只对上两段最危险
  O. timebase_triple          时基三格（单位 / 时钟域 / 取整时机），缺一按单位不一致处理
  P. pagination_completeness  has_more 是声明不是凭据；第三态 unreachable；合并判空去重断言与终止原因分账
  Q. gate_three_numbers       gate 三数同行（分子/分母/显式跳过数+原因码），缺任一判 UNKNOWN；跳过由发起侧记账
  R. degrade_product_side     降级由产物侧判定（期望产物 − 实际落盘），链路自报降级为未观测
  S. failure_domain_buckets   失败域四段分桶（前置素材/渲染/编码/合成）+ 至少一条「本应不存在」断言
  T. shared_fault_domain      共享故障域反例（探针同源 / 名义外部同体 / 共用去重表）
  U. portable_evidence        可携带判据最小三件（输入清单 + 产物指纹 + 判据表达式）；私有证据单独出桶
  V. defect_coverage          缺陷类覆盖清单（8 类缺陷各带检测入口，入口须真实存在于 CHECKS）
  W. repair_matrix            8 类缺陷 × 5 道工序覆盖矩阵，不得有空行空列
  X. adoption_map             吸纳对照表完整登记（status / 缺口 / 落地位置 / 校验入口）
  AA. degrade_double_write       降级态双写（命名层 + 账本层同源）；账本缺失按未声明降级态硬停，禁止按命名反推
  AB. version_overlap_ambiguous  口径版本交叠且生效起点不可判 → AMBIGUOUS 交人工；禁止后签发者优先等自动消歧
  AC. loaded_version_attestation 已加载版本由运行侧按产物指纹（内容 SHA-256 前 16hex）反推并带 load_at；自报只作 claim
  AD. impl_suspect_branch        摘要不一致而版本一致 → IMPL_SUSPECT 第三分支（需证据前提）；UNABLE_TO_COMPARE 须联签

第四轮（canons 1.3.0，2026-09-30）
--------------------

第三轮（canons 1.2.0，2026-09-30）
--------------------
  X. restoration_chain_order  画质修复链路顺序不可交换（去隔行→修复→细节重建）；修复类产物须声明为生成式重建；增益上限与禁用采样器族
  Y. tile_seam_integrity      分块产物须带「接缝/逐块闪烁本应不存在」断言；块尺寸须落在训练桶内；guide 禁用空间 tiled 编码
  Z. asr_segment_silence      分段转写静默失败三数（声明时长/实际覆盖/显式跳过）；边界须可回溯 source_event_id；句边界完整性；双引擎须独立

第五轮（canons 1.4.0，2026-10-02）6 组判据层口径
--------------------
  AE. cross_shot_anchor_consistency   跨镜头一致性：固定锚点 + 硬/软特征解耦 + 分级回滚 + 回滚前快照硬停
  AF. truncation_threshold_indeterminate 截断阈值对齐判 INDETERMINATE + 跨周期冷读第二票
  AG. producer_set_rank_conflict      来源按唯一生产者集合计数 + 同源异内容判 CONFLICT
  AH. evaluator_computed_digest       回执摘要哈希评估者计算结果（可独立复算）
  AI. unattested_state                UNATTESTED 第五态 + 证据因果/行政独立 + 外部签名时间戳
  AJ. semantic_window_default_drift   语义窗口默认值漂移 + 展开前内容寻址摘要

第六轮（canons 1.5.0，2026-10-02）4 组「竖屏画面包装设计口径」
来源：pbakaus/impeccable@4adabaf2c2bd3148f162d35aaa6acd7025343649（Apache-2.0）
适用面：composition/*.html（HyperFrames 单镜）与 templates/**/*.html（母版）；只读扫描，不改画面产物
--------------------
  AK. hyperframes_design_bans       画面包装 HTML 禁用项登记制 + 正则自证 + 只读扫描对账（templates 阻断制 / composition 登记制）
  AL. hyperframes_type_rhythm_floor 五角色字号地板 + 层级步进 ≥1.25 + 字距下限 -0.04em + 深底补偿 + 平台安全区
  AM. hyperframes_motion_authorship 一镜一署名动效时刻 + 缓动/时长分档 + 只动 transform/opacity/filter + 默认可见 + reduced-motion
  AN. hyperframes_color_depth_roles 语义色分工 + WCAG AA 逐帧对比地板 + 深度分层（禁零偏移色晕/硬偏移阴影）+ 渐变须承载信息

用法
----
  python3 scripts/canon_guard.py check                 # 静态自洽 + 存量对接 + 写留档
  python3 scripts/canon_guard.py check --manifest <m>  # 额外对真实 manifest 做零值语义补判（overlay）
  python3 scripts/canon_guard.py selftest              # 内置正/负例成对自测
  python3 scripts/canon_guard.py make-fixtures         # 从正本派生正/负例夹具到 tests/fixtures/canons/
  python3 scripts/canon_guard.py drill                 # 对落盘夹具跑负控（负例必须判红、正例必须判绿）
  python3 scripts/canon_guard.py signature             # 打印口径签名

退出码：0 = 全部通过；2 = 存在未通过项；1 = 用法/环境错误
"""

from __future__ import annotations

import argparse
import copy
import glob
import hashlib
import json
import os
import re
import sys
from datetime import datetime

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DEFAULT = os.path.dirname(SCRIPT_DIR)

CANONS_DEFAULT = os.path.join(ROOT_DEFAULT, "config", "engineering_canons.json")
CONTRACT_DEFAULT = os.path.join(ROOT_DEFAULT, "config", "param_contract.json")
CANONICALIZATION_DEFAULT = os.path.join(ROOT_DEFAULT, "config", "canonicalization.json")
FROZEN_DEFAULT = os.path.join(ROOT_DEFAULT, "config", "frozen_baseline.json")
OBS_DEFAULT = os.path.join(ROOT_DEFAULT, "config", "observability_rules.json")
NEGCASES_DEFAULT = os.path.join(ROOT_DEFAULT, "config", "negcontrol_cases.json")
FIXTURE_DIR_DEFAULT = os.path.join(ROOT_DEFAULT, "tests", "fixtures", "canons")
OUT_DEFAULT = os.path.join(ROOT_DEFAULT, "reports", "canons", "last_check.json")

ZERO_STATES = {"CONFIRMED_ZERO", "UNOBSERVED", "NOT_APPLICABLE"}
ACTIONS = {"hardstop", "degrade", "record_only"}
MISSING_VERDICTS = {"FAIL", "UNOBSERVED"}
CONSEQUENCES = {"silent_stale_hit", "explicit_failure", "degraded_naming_no_overwrite"}
CACHE_FACET_IDS = ["canonicalization_rule_version", "input_snapshot_digest", "clock_watermark",
                   "unit_dimension", "invalidation"]
FIVE_DIMS = ["field_name", "type", "domain", "drift_trigger", "consequence"]
HARDSTOP_IDS = {"denominator_definition", "identity_or_scope", "failure_definition", "external_dependency"}
DEGRADE_IDS = {"performance_concurrency", "sampling_batch", "presentation_order"}
MANIFEST_COLUMNS = ["field_name", "type", "domain", "zero_semantics", "disposition"]
LEDGER_COLUMNS = {"suspension_id", "subject", "pending_reason", "constraint_binding",
                  "discovered_at", "observed_at", "disposition", "change_trigger"}
MIN_DRIFT_FIELDS = 15
EXPECT_ADOPTION_ENTRIES = 43
HARD_FEATURE_SET = {"face", "color", "props"}
SOFT_FEATURE_SET = {"lighting", "grain"}
UNATTESTED_STATES = ["PASS", "FAIL", "UNKNOWN", "PENDING", "UNATTESTED"]
SEMANTIC_WINDOW_TRIPLE = ["snapshot_address", "as_of", "rule_version"]
# 吸纳层自身覆盖度（V/W 两项自检）：8 类缺陷 × 5 道工序，不得空洞
DEFECT_CLASS_IDS = {"silent_rewrite", "denominator_shrink", "declaration_as_credential",
                    "unobserved_as_zero", "self_report_as_evidence", "shared_fault_domain",
                    "unknown_version", "invisible_degrade"}
REPAIR_STAGES = ["pre_asset", "render", "encode", "compose", "delivery"]
# ── v1.8.0 吸纳层：竖屏画面包装设计口径（上游 pbakaus/impeccable，Apache-2.0）────
# 适用面：composition/*.html（HyperFrames 单镜）与 templates/**/*.html（母版）
DESIGN_BAN_RULE_IDS = {
    "gradient_text", "hard_offset_shadow", "zero_offset_glow", "side_stripe_border",
    "eyebrow_kicker", "tracking_too_tight", "identical_card_grids", "hero_metric_template",
    "glyph_icons", "glass_blur_decoration", "numbered_section_marker",
    "system_display_face", "rough_sketch_svg", "repeating_stripes_bg",
}
DESIGN_RULE_VERDICTS = {"ban", "default"}
DESIGN_DETECTORS = {"regex", "manual"}
DESIGN_SCOPES = ("composition", "templates")
TYPE_ROLE_IDS = {"hook", "heading", "body", "label", "meta"}
TYPE_TRACKING_FLOOR_EM = -0.04
TYPE_MIN_SCALE_STEP = 1.25
TYPE_COMPENSATION_AXES = {"line_height", "tracking", "weight"}
MOTION_TIER_IDS = ("feedback", "state", "layout", "focal")
MOTION_BANNED_PROPS = {"width", "height", "top", "left", "margin", "padding"}
MOTION_BANNED_EASINGS = {"bounce", "elastic", "back"}
COLOR_ROLE_IDS = {"surface", "ink", "accent", "warn"}
COLOR_CONTRAST_FLOOR = {"body_min_ratio": 4.5, "large_text_min_ratio": 3.0,
                        "ui_component_min_ratio": 3.0}
COLOR_DEPTH_LAYERS = {"elevation", "scale", "blur", "contrast"}
COLOR_DEPTH_FORBIDDEN = {"zero_offset_glow", "hard_offset_shadow", "decorative_border"}


# ── v1.9.0 吸纳层：参数溯源不可比 / 归一动作落账 / 快照寿命与回收前提同源 ──────
PARAM_PROVENANCE_STATES = {"declared", "defaulted_explicitly", "absent"}
PARAM_CROSS_STATE_VERDICT = "INCOMPARABLE"
PARAM_VERDICT_RULE = {"regression": "out_of_tolerance_and_attributable",
                      "unknown": "within_tolerance_and_unattributable",
                      "unknown_silent_rebaseline": "REJECT"}
NORM_DRIFT_FORMS = ["field_name", "type", "representation", "precision", "default_source"]
NORM_VERSION_TRIO = ["alias_table_version", "contract_version", "canonicalizer_version"]
NORM_REPRESENTATION_STATES = {"null", "missing", "empty_string", "empty_array"}
SNAPSHOT_LIFETIME_SOURCE = "same_as_recycle_precondition"
SNAPSHOT_SELF_SIGNED_VERDICT = "NOT_EVIDENCE"

# ── v1.10.0 吸纳层：验证锚点外置 / 期望集版本化签发 ──────────────────────────
ANCHOR_OPPOSITE_SIDE = "opposite_side_of_checked_data"
ANCHOR_SAME_SIDE_VERDICT = "SILENT_PASS_FORBIDDEN"
ANCHOR_DELTA_MODE = "actual_vs_expected_delta"
EXPECT_SIGNING_LEDGER_FIELDS = {"expectation_set_version", "issuer", "occurred_at"}
EXPECT_PATH_BINDING = {"path", "content_hash"}


def now_iso():
    return datetime.now().strftime("%Y-%m-%dT%H:%M:%S")


def read_json(path, default=None):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def signature_of(doc):
    payload = json.dumps(doc, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()[:16]


# ─────────────────────────────────────────────────────────────
# 静态检查：每条口径一个函数 → (ok, detail, problems)
# ─────────────────────────────────────────────────────────────

def chk_pending_ledger(c, ctx):
    p = c.get("pending_ledger") or {}
    pr = []
    cols = set(p.get("columns") or [])
    sep = set((p.get("column_separation") or {}).get("must_be_separate") or [])
    for k in ("disposition", "change_trigger"):
        if k not in cols:
            pr.append(f"挂起账本缺列 {k}")
        if k not in sep:
            pr.append(f"处置(disposition)与变更触发(change_trigger)必须分列：{k} 未列入 must_be_separate")
    if (p.get("column_separation") or {}).get("merged_verdict") != "REJECT":
        pr.append("处置与变更触发合并时未判 REJECT")
    rb = set((p.get("constraint_binding") or {}).get("required_dimensions") or [])
    if rb != {"rule_id", "platform", "field"}:
        pr.append("挂起原因未落到约束（需 rule_id/platform/field 三维齐）")
    iso = p.get("issuer_scope") or {}
    if iso.get("type") != "bool" or not iso.get("field"):
        pr.append("判据签发者缺『签发方与交付方是否同一组织』布尔位")
    if iso.get("unknown_handling") is None:
        pr.append("同组织布尔缺 UNKNOWN 处理（缺失不得默认 true）")
    ok = not pr
    return ok, "挂起原因落约束 + 同组织布尔 + 处置/变更触发分列 齐备" if ok else "；".join(pr), pr


def chk_cache_key_grid(c, ctx):
    g = c.get("cache_key_grid") or {}
    pr = []
    facets = g.get("facets") or []
    ids = [f.get("id") for f in facets]
    if ids != CACHE_FACET_IDS:
        pr.append(f"缓存键五格不全或顺序不符：实得 {ids}")
    for dim in g.get("five_dimensions") or []:
        if dim not in FIVE_DIMS:
            pr.append(f"未声明的维度 {dim}")
    for dim in FIVE_DIMS:
        if dim not in (g.get("five_dimensions") or []):
            pr.append(f"五维缺 {dim}")
    for i, f in enumerate(facets):
        fid = f.get("id")
        for dim in FIVE_DIMS:
            if not f.get(dim):
                pr.append(f"格 {fid} 缺维度 {dim}")
        if f.get("consequence") not in CONSEQUENCES:
            pr.append(f"格 {fid} 后果取值非法：{f.get('consequence')}")
        if i < 4 and f.get("issuer_version_required") is not True:
            pr.append(f"格 {fid} 参与缓存键/命中判定，必须带签发方与版本")
    if len(facets) >= 5:
        last = facets[4]
        if last.get("consequence") != "degraded_naming_no_overwrite" or not last.get("naming_rule"):
            pr.append("第五格（失效条件）必须让降级产物在命名上不可覆盖")
    kp = g.get("key_policy") or {}
    if kp.get("first_four_must_carry_issuer_and_version") is not True:
        pr.append("未声明『前四格必须带签发方与版本』")
    if kp.get("fifth_must_make_degraded_uncollidable") is not True:
        pr.append("未声明『第五格必须让降级产物不可覆盖』")
    ok = not pr
    return ok, "五格 × 五维齐备；前四格带签发方版本；第五格降级命名不可覆盖" if ok else "；".join(pr), pr


def chk_stop_degrade_tiers(c, ctx):
    t = c.get("stop_degrade_tiers") or {}
    pr = []
    hs = {x.get("id") for x in (t.get("hardstop_classes") or [])}
    dg = {x.get("id") for x in (t.get("degrade_classes") or [])}
    if hs != HARDSTOP_IDS:
        pr.append(f"硬停四类不全：缺 {sorted(HARDSTOP_IDS - hs)}")
    if dg != DEGRADE_IDS:
        pr.append(f"降级三类不全：缺 {sorted(DEGRADE_IDS - dg)}")
    iso = t.get("degrade_isolation") or {}
    if iso.get("marker") is None or not set(iso.get("must_carry") or []) >= {"reason_code", "source"}:
        pr.append("降级期间结果未要求单独标记（须带 reason_code 与 source）")
    fm = t.get("fallback_marker") or {}
    if not fm.get("token"):
        pr.append("缺回落显式标记")
    if fm.get("marker_itself_not_reversible") is not True:
        pr.append("回落标记自身必须不可被回落")
    if not t.get("tier_switch_rule"):
        pr.append("缺硬停/降级分流规则")
    ok = not pr
    return ok, "硬停四类 + 降级三类 + 降级隔离 + 回落标记不可回落 齐备" if ok else "；".join(pr), pr


def chk_zero_semantics(c, ctx):
    z = c.get("zero_semantics") or {}
    pr = []
    states = [s.get("id") for s in (z.get("states") or [])]
    if set(states) != ZERO_STATES:
        pr.append(f"零值三态不全：实得 {states}")
    if z.get("must_declare_per_field") is not True:
        pr.append("未要求逐字段声明零值语义")
    am = z.get("audio_stream_missing") or {}
    if am.get("verdict") != "FAIL":
        pr.append(f"音频流数缺失必须判 FAIL（实得 {am.get('verdict')}）")
    ab = z.get("assertion_binding") or {}
    if set(ab.get("actions") or []) != ACTIONS:
        pr.append(f"断言动作集不全：{ab.get('actions')}")
    if ab.get("unbound_verdict") != "REJECT_CONFIG":
        pr.append("未绑定失败动作的断言必须 REJECT_CONFIG（等于注释，不得进配置面）")
    ok = not pr
    return ok, "零值三态 + 音频缺失判 FAIL + 断言绑定动作 齐备" if ok else "；".join(pr), pr


def chk_drift_fieldset(c, ctx):
    d = c.get("drift_fieldset") or {}
    pr = []
    fields = d.get("easiest_drift_fields") or []
    ids = [f.get("id") for f in fields]
    if len(fields) < MIN_DRIFT_FIELDS:
        pr.append(f"最易漂字段集不足 {MIN_DRIFT_FIELDS} 项（实得 {len(fields)}）")
    if len(set(ids)) != len(ids):
        pr.append("最易漂字段集存在重复项")
    if len(d.get("hardstop_triggers") or []) != 3:
        pr.append("硬停三类未声明齐（字段缺失或来源不明 / 判据签发方缺失 / 时基单位不一致）")
    if len(d.get("degrade_triggers") or []) != 3:
        pr.append("降级三类未声明齐（参数值变化来源可追 / 依赖集变化可复算 / 非关键路径默认值变化）")
    if not set(d.get("degrade_must_carry") or []) >= {"reason_code", "source"}:
        pr.append("降级必须带原因码与来源，不许静默回退")
    if d.get("degrade_silent_rollback_forbidden") is not True:
        pr.append("未禁止静默回退")
    o = d.get("overturn_rate") or {}
    if o.get("no_cross_version_sum") is not True:
        pr.append("翻案率不得跨版本求和")
    if "rule_version" not in (o.get("group_fields") or []):
        pr.append("翻案率必须按规则版本分组（group_fields 须含 rule_version）")
    if not set(o.get("fields") or []) >= {"rule_id", "rule_version", "overturns", "evaluations", "rate"}:
        pr.append("翻案率行缺字段（须每条规则一行：rule_id/rule_version/overturns/evaluations/rate）")
    mv = d.get("manifest_versioning") or {}
    if mv.get("requires_version") is not True or mv.get("requires_issuer_version") is not True:
        pr.append("清单本身须带版本号与签发方")
    ok = not pr
    return ok, "最易漂字段集 + 硬停三类 + 降级三类 + 翻案率分组 + 清单版签 齐备" if ok else "；".join(pr), pr


def chk_manifest_columns(c, ctx):
    m = c.get("manifest_columns") or {}
    r = c.get("receipt_policy") or {}
    pr = []
    if list(m.get("columns") or []) != MANIFEST_COLUMNS:
        pr.append(f"清单五列必须填满：实得 {m.get('columns')}")
    if m.get("must_fill_all") is not True:
        pr.append("未声明五列必填")
    if m.get("missing_column_verdict") != "UNDECLARED":
        pr.append("缺列必须判 UNDECLARED（视为未声明）")
    for k in MANIFEST_COLUMNS:
        if not (m.get("column_rules") or {}).get(k):
            pr.append(f"列规则缺 {k}")
    if not m.get("container_shape_rule"):
        pr.append("未声明容器形状规则（空数组合法 vs 空等价于未声明）")
    if r.get("observed_at_required") is not True:
        pr.append("回执必须带观测时刻 observed_at")
    if not r.get("stale_handling"):
        pr.append("缺 observed_at 缺失时的处理口径")
    ok = not pr
    return ok, "清单五列 + 容器形状 + 缺列判 UNDECLARED + 回执带观测时刻 齐备" if ok else "；".join(pr), pr


def chk_field_registry(c, ctx):
    reg = {f.get("field"): f for f in ((c.get("field_registry") or {}).get("fields") or [])}
    expect = set(ctx.get("contract_fields") or [])
    pr = []
    if not reg:
        pr.append("字段注册表为空")
    missing = expect - set(reg)
    extra = set(reg) - expect
    if missing:
        pr.append(f"注册表未覆盖存量字段：{sorted(missing)}")
    if extra:
        pr.append(f"注册表出现存量不存在的字段：{sorted(extra)}")
    for n, f in reg.items():
        if f.get("zero_semantics") not in ZERO_STATES:
            pr.append(f"{n} 零值三态非法：{f.get('zero_semantics')}")
        if f.get("assertion_action") not in ACTIONS:
            pr.append(f"{n} 断言未绑显式失败动作：{f.get('assertion_action')}")
        if f.get("missing_verdict") not in MISSING_VERDICTS:
            pr.append(f"{n} 缺失判定非法：{f.get('missing_verdict')}")
    ok = not pr
    return ok, f"18 字段零值三态归一 + 断言动作绑定齐备（共 {len(reg)} 字段）" if ok else "；".join(pr), pr


def chk_adoption_map(c, ctx):
    am = c.get("adoption_map") or []
    pr = []
    if len(am) != EXPECT_ADOPTION_ENTRIES:
        pr.append(f"吸纳对照条目应为 {EXPECT_ADOPTION_ENTRIES} 条，实得 {len(am)}")
    for e in am:
        for f in ("id", "source", "title", "status", "gap", "landing", "enforced_by"):
            if not e.get(f):
                pr.append(f"{e.get('id', '?')} 缺 {f}")
        if e.get("status") not in {"covered", "partial", "new"}:
            pr.append(f"{e.get('id')} status 非法：{e.get('status')}")
    ok = not pr
    return ok, f"吸纳对照 {len(am)} 条均登记 status / 缺口 / 落地位置 / 校验入口" if ok else "；".join(pr), pr


def chk_bridge(c, ctx):
    """与存量真源对接一致性（只读）。"""
    pr = []
    contract = ctx.get("contract") or {}
    fields = {f.get("field") for f in (contract.get("fields") or [])}
    ext = {f.get("field") for f in ((contract.get("extended_contract") or {}).get("fields") or [])}
    if not fields or not ext:
        pr.append("存量 param_contract 字段读不到")
    if ctx.get("canonicalizer_signature") is None:
        pr.append("存量 canonicalization.json 缺签名（缓存键第一格失去真源）")
    if ctx.get("frozen_digest") is None:
        pr.append("存量 frozen_baseline.json 缺摘要（缓存键第二格失去真源）")
    if not ctx.get("observability_ok"):
        pr.append("存量 observability_rules.json 不可解析或为空")
    bad = ctx.get("negcase_problems") or []
    if bad:
        pr.append("负控用例与合同字段对接异常：" + "；".join(bad[:5]))
    ok = not pr
    return ok, f"对接存量：合同 {len(fields)}+{len(ext)} 字段 / 规范化器签名 / 冻结摘要 / 观测规则 / 负控用例 全部一致" if ok else "；".join(pr), pr


def chk_silent_rewrite(c, ctx):
    s = c.get("silent_rewrite") or {}
    pr = []
    ex = s.get("explicit_change") or {}
    sw = s.get("silent_rewrite") or {}
    if ex.get("verdict") != "degrade":
        pr.append("显式指定变化须判 degrade")
    if sw.get("verdict") != "hardstop":
        pr.append("未指定被静默改写须升 hardstop，不得降级")
    if not {"reason_code", "source"} <= set(ex.get("must_carry") or []):
        pr.append("降级须带 reason_code 与 source")
    ap = set(s.get("field_scope") or [])
    need = {"sampler_scheduler_identity", "precision_quantization"}
    if not need <= ap:
        pr.append(f"适用项缺 {'/'.join(sorted(need - ap))}")
    if not s.get("detect"):
        pr.append("未声明静默改写的判定方法（显式集合 vs 实际生效值）")
    if not s.get("negative_case"):
        pr.append("缺可判红负例")
    ok = not pr
    return ok, "静默改写判定：显式变化→降级 / 静默改写→硬停，适用项与携带项齐备" if ok else "；".join(pr), pr


def chk_criteria_identity(c, ctx):
    s = c.get("criteria_identity") or {}
    pr = []
    if list(s.get("required_triple") or []) != ["version", "issuer", "effective_from"]:
        pr.append(f"判据身份须为三格（版本/签发方/生效起点）：实得 {s.get('required_triple')}")
    if s.get("missing_effective_from_verdict") != "UNCOMPARABLE_ACROSS_CYCLES":
        pr.append("缺生效起点须判 UNCOMPARABLE_ACROSS_CYCLES（跨周期不可比）")
    vg = s.get("version_generation_event") or {}
    if not vg.get("bucket"):
        pr.append("版本换代须记独立事件并单独出桶")
    if "drift_count" not in (vg.get("excluded_from") or []):
        pr.append("版本换代事件不得并进 drift_count（须列入 excluded_from）")
    if not s.get("negative_case"):
        pr.append("缺可判红负例")
    ok = not pr
    return ok, "判据身份三格 + 版本换代独立出桶 齐备" if ok else "；".join(pr), pr


def chk_zero_declared_vs_default(c, ctx):
    s = c.get("zero_declared_vs_default") or {}
    vals = set(s.get("states") or [])
    pr = []
    need = {"UNDECLARED", "EXPLICIT_DEFAULT"}
    if vals != need:
        pr.append(f"未声明与显式默认须拆为两个取值：缺 {'/'.join(sorted(need - vals))} / 多 {'/'.join(sorted(vals - need))}")
    if s.get("merged_verdict") != "REJECT":
        pr.append("两取值不得合并（merged_verdict 须为 REJECT）")
    ok = not pr
    return ok, "未声明 ≠ 默认：取值拆分 + 禁止合并 齐备" if ok else "；".join(pr), pr


def chk_pending_age_distribution(c, ctx):
    s = c.get("pending_age_distribution") or {}
    pr = []
    if not {"suspension_started_at", "rerun_cost_tier"} <= set(s.get("required_fields") or []):
        pr.append("挂起项须绑『起始时刻 + 重跑成本档』")
    if list((s.get("report") or {}).get("quantiles") or []) != ["P50", "P90", "P99"]:
        pr.append(f"存量桶须报年龄分位 P50/P90/P99：实得 {(s.get('report') or {}).get('quantiles')}")
    tb = s.get("threshold_base") or {}
    if "新增" not in str(tb.get("denominator") or ""):
        pr.append("阈值基数须取当轮新增挂起数（threshold_base.denominator）")
    if not tb.get("stock_bucket"):
        pr.append("未声明存量挂起另出桶")
    ok = not pr
    return ok, "挂起年龄分布：绑起始时刻+成本档 / 分位 / 阈值基数当轮新增 / 存量另桶 齐备" if ok else "；".join(pr), pr


def chk_overturn_denominator(c, ctx):
    s = c.get("overturn_denominator") or {}
    pr = []
    if s.get("denominator") != "human_reviewed_rejections":
        pr.append("翻案率分母须只算已人工复核的拒绝")
    if not s.get("unreviewed_bucket"):
        pr.append("未复核挂起须单独出桶、不进分母")
    if not ((c.get("drift_fieldset") or {}).get("overturn_rate")):
        pr.append("未声明所扩展的存量字段（drift_fieldset.overturn_rate）")
    ok = not pr
    return ok, "翻案率分母：只算已复核拒绝 + 未复核单独出桶 齐备" if ok else "；".join(pr), pr


def chk_dependency_version_triple(c, ctx):
    s = c.get("dependency_version_triple") or {}
    pr = []
    if list(s.get("segments") or []) != ["source_version", "content_hash", "loaded_version"]:
        pr.append(f"依赖版本须为三段（来源/内容/已加载）：实得 {s.get('segments')}")
    if "两段" not in str(s.get("danger") or ""):
        pr.append("未声明『只对上两段』的危险形态")
    if not s.get("extra_rule"):
        pr.append("未声明『只锁路径不锁版本等于没锁』")
    if not s.get("negative_case"):
        pr.append("缺可判红负例")
    ok = not pr
    return ok, "依赖版本三段 + 两段一致危险形态 齐备" if ok else "；".join(pr), pr


def chk_timebase_triple(c, ctx):
    s = c.get("timebase_triple") or {}
    pr = []
    if list(s.get("required_triple") or []) != ["unit", "clock_domain", "rounding_moment"]:
        pr.append(f"时基须三格（单位/时钟域/取整时机）：实得 {s.get('required_triple')}")
    if s.get("missing_rounding_verdict") != "TIMEBASE_UNIT_INCONSISTENT":
        pr.append("缺取整时机须按『时基单位不一致』处理")
    if set(s.get("rounding_moment_enum") or []) != {"on_write", "on_read"}:
        pr.append("取整时机枚举须为 on_write / on_read")
    if not s.get("negative_case"):
        pr.append("缺可判红负例")
    ok = not pr
    return ok, "时基三格（含取整时机）+ 缺格判单位不一致 齐备" if ok else "；".join(pr), pr


def chk_pagination_completeness(c, ctx):
    s = c.get("pagination_completeness") or {}
    ts = s.get("third_state") or {}
    pr = []
    if ts.get("id") != "unreachable":
        pr.append("『声明为真、凭据不可达』须显式落成第三态 unreachable")
    if "取尽" not in str(ts.get("forbidden") or ""):
        pr.append("unreachable 不得折叠进『已取尽』")
    reasons = list(s.get("termination_reasons") or [])
    if len(reasons) < 2:
        pr.append(f"终止原因须分账（拉空 / 到轮数上限）：实得 {reasons}")
    if not s.get("dedup_assertion"):
        pr.append("合并判空须加去重断言")
    if not s.get("round_cap_rule"):
        pr.append("轮数上限须配『未取尽』出口")
    ok = not pr
    return ok, "分页第三态 unreachable + 去重断言 + 终止原因分账 + 未取尽出口 齐备" if ok else "；".join(pr), pr


def chk_gate_three_numbers(c, ctx):
    s = c.get("gate_three_numbers") or {}
    cells = set(s.get("must_be_same_row") or [])
    need = {"numerator", "denominator", "skipped", "skip_reason_code"}
    pr = []
    if not need <= cells:
        pr.append(f"三数须同行落盘（分子/分母/跳过数+原因码）：缺 {'/'.join(sorted(need - cells))}")
    if s.get("missing_any_verdict") != "UNKNOWN":
        pr.append("缺任一数须判 UNKNOWN（不得判 PASS）")
    if s.get("skip_accounting_side") != "initiator":
        pr.append("跳过须由发起侧记账，不得在应答侧去重后记")
    ok = not pr
    return ok, "gate 三数同行 + 缺数判 UNKNOWN + 跳过发起侧记账 齐备" if ok else "；".join(pr), pr


def chk_degrade_product_side(c, ctx):
    s = c.get("degrade_product_side") or {}
    pr = []
    if "期望" not in str(s.get("method") or ""):
        pr.append("降级须由产物侧判定（期望产物清单减实际落盘）")
    if "未观测" not in str(s.get("self_report_handling") or ""):
        pr.append("链路自报路径须降级为未观测，不得单独充当健康信号")
    if not s.get("issuer_constraint"):
        pr.append("降级事件签发方须落在被测链路之外")
    ok = not pr
    return ok, "降级由产物侧判定 + 自报降为未观测 + 外部签发 齐备" if ok else "；".join(pr), pr


def chk_failure_domain_buckets(c, ctx):
    s = c.get("failure_domain_buckets") or {}
    pr = []
    ids = [b.get("id") for b in (s.get("buckets") or [])]
    if ids != ["pre_asset", "render", "encode", "compose"]:
        pr.append(f"失败域须四段分桶：实得 {ids}")
    for b in (s.get("buckets") or []):
        if not b.get("shape"):
            pr.append(f"分桶 {b.get('id')} 缺漂移项形状")
    if not s.get("assertion_requirement"):
        pr.append("未声明『至少一条本应不存在』断言要求")
    ok = not pr
    return ok, "失败域四段分桶 + 本应不存在断言要求 齐备" if ok else "；".join(pr), pr


def chk_shared_fault_domain(c, ctx):
    s = c.get("shared_fault_domain") or {}
    ids = {x.get("id") for x in (s.get("counter_examples") or [])}
    pr = []
    need = {"probe_shares_upstream", "external_id_same_issuer", "ack_shares_dedup_table"}
    if not need <= ids:
        pr.append(f"共享故障域反例缺 {'/'.join(sorted(need - ids))}")
    if s.get("verdict_when_shared") != "unverified":
        pr.append("共享源须记 unverified，不得写 independent")
    if not s.get("zero_match_rule"):
        pr.append("零匹配须作为显式状态处理，不得落成『无数据』")
    ok = not pr
    return ok, "共享故障域三反例 + unverified 判定 齐备" if ok else "；".join(pr), pr


def chk_portable_evidence(c, ctx):
    s = c.get("portable_evidence") or {}
    pr = []
    pieces = set()
    for x in (s.get("min_pieces") or []):
        pieces.add(str(x).split("（")[0].split("(")[0].strip())
    need = {"input_manifest", "artifact_fingerprint", "criteria_expression"}
    if not need <= pieces:
        pr.append(f"可携带判据最小三件缺 {'/'.join(sorted(need - pieces))}")
    if s.get("missing_any_verdict") != "PRIVATE_EVIDENCE":
        pr.append("缺任一件须降级为私有证据")
    if not s.get("private_evidence_bucket"):
        pr.append("私有证据须单独出桶、不得混入对外结论分母")
    ok = not pr
    return ok, "可携带判据最小三件 + 私有证据单独出桶 齐备" if ok else "；".join(pr), pr


def chk_defect_coverage(c, ctx):
    s = c.get("defect_coverage") or {}
    classes = s.get("classes") or []
    ids = {x.get("id") for x in classes}
    pr = []
    if ids != DEFECT_CLASS_IDS or len(classes) != len(DEFECT_CLASS_IDS):
        pr.append(f"缺陷类须覆盖 8 类：缺 {sorted(DEFECT_CLASS_IDS - ids)} / 多 {sorted(ids - DEFECT_CLASS_IDS)}")
    fn_names = {fn.__name__ for _cid, _lab, fn in CHECKS}
    for x in classes:
        det = x.get("detector")
        if not det:
            pr.append(f"缺陷类 {x.get('id')} 缺检测入口")
        elif det not in fn_names:
            pr.append(f"缺陷类 {x.get('id')} 检测入口 {det} 不在校验器 CHECKS 内")
    ok = not pr
    return ok, f"缺陷类覆盖 {len(classes)} 类，检测入口均存在于校验器" if ok else "；".join(pr), pr


def chk_repair_matrix(c, ctx):
    s = c.get("repair_matrix") or {}
    stages = s.get("stages") or []
    matrix = s.get("matrix") or {}
    pr = []
    if stages != REPAIR_STAGES:
        pr.append(f"工序集不符：实得 {stages}")
    if set(matrix) != DEFECT_CLASS_IDS:
        pr.append(f"矩阵缺陷类与缺陷覆盖清单不一致：{sorted(set(matrix) ^ DEFECT_CLASS_IDS)}")
    for cls, ss in matrix.items():
        ss = ss or []
        if not ss:
            pr.append(f"缺陷类 {cls} 为空行（无工序覆盖）")
        bad = [x for x in ss if x not in stages]
        if bad:
            pr.append(f"缺陷类 {cls} 含非法工序 {bad}")
    for st in stages:
        if not any(st in (ss or []) for ss in matrix.values()):
            pr.append(f"工序 {st} 为空列（无缺陷类覆盖）")
    ok = not pr
    return ok, "8 类缺陷 × 5 道工序覆盖矩阵无空行空列" if ok else "；".join(pr), pr


def chk_restoration_chain_order(c, ctx):
    s = c.get("restoration_chain_order") or {}
    pr = []
    stages = [x for x in (s.get("ordered_stages") or [])]
    if stages[:3] != ["deinterlace", "restore", "refine_details"]:
        pr.append("链路顺序须为 deinterlace → restore → refine_details（顺序不可交换）")
    if s.get("order_immutable") is not True:
        pr.append("未声明顺序不可交换")
    forb = set(s.get("preprocess_forbidden_before_guide") or [])
    if not {"denoise", "sharpen"} <= forb:
        pr.append("进 guide 前须禁止去噪与锐化（会先锐化损伤、压低颜色推断）")
    gd = s.get("generative_declaration") or {}
    if gd.get("required") is not True or not gd.get("label"):
        pr.append("修复类产物须带生成式重建声明（AI 重建，非历史记录）")
    gc = s.get("gain_ceiling") or {}
    if not gc.get("peak") or not gc.get("basis"):
        pr.append("增益上限须声明峰值与依据，超限须判 WARN")
    sf = s.get("sampler_family_constraint") or {}
    if not {"euler", "heun", "dpm_2"} <= set(sf.get("allowed") or []):
        pr.append("分块融合允许的采样器族缺 euler/heun/dpm_2")
    if not sf.get("forbidden"):
        pr.append("须显式列出禁用的采样器族（历史/自适应/祖先族）")
    if sf.get("violation_verdict") != "hardstop":
        pr.append("采样器族不匹配须判 hardstop")
    if not s.get("negative_case"):
        pr.append("缺可判红负例")
    ok = not pr
    return ok, "修复链路顺序不可交换 + 生成式重建声明 + 采样器族约束 齐备" if ok else "；".join(pr), pr


def chk_tile_seam_integrity(c, ctx):
    s = c.get("tile_seam_integrity") or {}
    pr = []
    tb = s.get("tile_bucket") or {}
    if not {"restore", "refine"} <= set(tb):
        pr.append("须声明分块训练桶尺寸（restore / refine）")
    if not tb.get("overlap"):
        pr.append("须声明块间重叠比例")
    need = {"no_seam_on_tile_boundary", "no_per_tile_flicker"}
    if not need <= set(s.get("forbidden_assertion_set") or []):
        pr.append("须带「接缝/逐块闪烁本应不存在」断言（渲染无报错 ≠ 产物合格）")
    if s.get("oversize_verdict") != "FAIL":
        pr.append("块尺寸越出训练桶须判 FAIL（越桶即编造纹理）")
    if not s.get("single_tile_pass_only_if"):
        pr.append("单块直出的放行条件须声明")
    wr = s.get("window_rule") or {}
    if not wr.get("preferred_frames"):
        pr.append("须声明窗口帧档位与超窗后果")
    ge = s.get("guide_encode_constraint") or {}
    if ge.get("use_tiled_encode") is not False:
        pr.append("guide 不得使用空间 tiled 编码（会把网格印进条件）")
    if not s.get("negative_case"):
        pr.append("缺可判红负例")
    ok = not pr
    return ok, "分块接缝/闪烁负向断言 + 训练桶约束 + guide 编码约束 齐备" if ok else "；".join(pr), pr


def chk_asr_segment_silence(c, ctx):
    s = c.get("asr_segment_silence") or {}
    pr = []
    trip = set(s.get("required_triple") or [])
    need = {"declared_duration", "transcribed_coverage", "explicit_skipped_segments"}
    if not need <= trip:
        pr.append(f"分段转写三数缺 {'/'.join(sorted(need - trip))}")
    if s.get("missing_any_verdict") != "UNKNOWN":
        pr.append("三数缺任一须判 UNKNOWN，不得判通过")
    bt = s.get("boundary_traceability") or {}
    if bt.get("field") != "source_event_id":
        pr.append("分段/章节边界须可回溯 source_event_id")
    if bt.get("missing_verdict") != "PRIVATE_EVIDENCE":
        pr.append("边界不可回溯的覆盖声明须降级为私有证据")
    sb = s.get("sentence_boundary_assertion") or {}
    must = set(sb.get("must") or [])
    if not {"first_sentence_complete", "last_sentence_complete"} <= must:
        pr.append("须断言首句与末句完整（防长视频 ASR 句尾截断）")
    if sb.get("violation_verdict") != "FAIL":
        pr.append("句边界不完整须判 FAIL")
    de = s.get("dual_engine_alignment") or {}
    if de.get("required") is not True or de.get("independence_required") is not True:
        pr.append("双引擎交叉对齐须要求引擎独立性（不得共用同一解码上游）")
    if not s.get("dedup_assertion"):
        pr.append("须有相邻分段去重断言（防服务端重放）")
    if not (s.get("dry_run_baseline") or {}).get("required"):
        pr.append("须有干跑基线检查以检出编码/容器漂移")
    if not s.get("negative_case"):
        pr.append("缺可判红负例")
    ok = not pr
    return ok, "转写三数 + 边界可回溯 + 句边界完整性 + 双引擎独立性 齐备" if ok else "；".join(pr), pr


def chk_degrade_double_write(c, ctx):
    d = c.get("degrade_double_write") or {}
    pr = []
    for k in ("version", "source", "rule", "negative_case"):
        if not d.get(k):
            pr.append(f"degrade_double_write 缺 {k}")
    if set(d.get("layers") or []) != {"naming_layer", "ledger_layer"}:
        pr.append(f"降级态必须双写命名层与账本层两层键，实得 {d.get('layers')}")
    if d.get("key_consistency") != "same_degrade_key_in_both_layers":
        pr.append("两层必须写同一个降级键（key_consistency 未声明同源）")
    if d.get("ledger_is_authoritative") is not True:
        pr.append("账本层必须是降级态的唯一权威来源")
    if d.get("ledger_missing_verdict") != "hardstop":
        pr.append(f"账本字段缺失应判 hardstop（未声明降级态），实得 {d.get('ledger_missing_verdict')}")
    if d.get("naming_inference_forbidden") is not True:
        pr.append("必须显式禁止按命名层反推降级态（否则『忘写账本』被读成『未走降级』）")
    ok = not pr
    return ok, "降级态双写两层键、账本权威、缺失即硬停且禁止命名反推 齐备" if ok else "；".join(pr), pr


def chk_version_overlap_ambiguous(c, ctx):
    v = c.get("version_overlap_ambiguous") or {}
    pr = []
    for k in ("version", "source", "rule", "negative_case"):
        if not v.get(k):
            pr.append(f"version_overlap_ambiguous 缺 {k}")
    states = v.get("overlap_states") or []
    if "AMBIGUOUS" not in states:
        pr.append(f"交叠态枚举缺 AMBIGUOUS：{states}")
    if v.get("verdict_when_overlap") != "AMBIGUOUS":
        pr.append(f"交叠区间应判 AMBIGUOUS，实得 {v.get('verdict_when_overlap')}")
    forbid = set(v.get("auto_resolution_forbidden") or [])
    for x in ("later_issuer_wins", "timestamp_latest_wins", "version_string_order"):
        if x not in forbid:
            pr.append(f"未显式禁止自动消歧方式 {x}")
    if v.get("human_required") is not True:
        pr.append("AMBIGUOUS 必须交人工裁决（human_required 非真）")
    carry = set(v.get("must_carry") or [])
    for x in ("overlap_window", "candidate_versions", "issuers"):
        if x not in carry:
            pr.append(f"AMBIGUOUS 行缺必填要素 {x}")
    ok = not pr
    return ok, "交叠判 AMBIGUOUS、交人工、禁止后签发者优先且要素齐备" if ok else "；".join(pr), pr


def chk_loaded_version_attestation(c, ctx):
    a = c.get("loaded_version_attestation") or {}
    pr = []
    for k in ("version", "source", "rule", "negative_case"):
        if not a.get(k):
            pr.append(f"loaded_version_attestation 缺 {k}")
    if a.get("attestor") != "runtime_side":
        pr.append(f"已加载版本必须由运行侧判定，实得 {a.get('attestor')}")
    if a.get("fingerprint_form") != "content_sha256_first16hex":
        pr.append(f"指纹形态须为内容 SHA-256 前 16 hex，实得 {a.get('fingerprint_form')}")
    if a.get("anchor_registry_required") is not True:
        pr.append("指纹须与锚登记逐条比对（anchor_registry_required 非真）")
    if a.get("load_at_required") is not True:
        pr.append("加载指纹必须带 load_at 时间锚（无 load_at 时先后不可判）")
    if a.get("self_report_excluded") is not True or a.get("fallback_to_self_report_forbidden") is not True:
        pr.append("签发方自报不得进账、也不得作为缺失时的回落（自报只作 claim）")
    if a.get("missing_fingerprint_verdict") != "UNKNOWN":
        pr.append(f"指纹缺失应判 UNKNOWN，实得 {a.get('missing_fingerprint_verdict')}")
    ok = not pr
    return ok, "已加载版本运行侧反推 + 指纹形态 + 锚登记 + load_at + 自报排除 齐备" if ok else "；".join(pr), pr


def chk_impl_suspect_branch(c, ctx):
    i = c.get("impl_suspect_branch") or {}
    pr = []
    for k in ("version", "source", "rule", "negative_case"):
        if not i.get(k):
            pr.append(f"impl_suspect_branch 缺 {k}")
    br = set(i.get("branches") or [])
    for x in ("CANONICALIZER_VERSION_MISMATCH", "ROW_SET_DIVERGED", "IMPL_SUSPECT"):
        if x not in br:
            pr.append(f"分支枚举缺 {x}")
    pre = set(i.get("third_branch_precondition") or [])
    for x in ("row_set_reproduced", "producer_re_digest"):
        if x not in pre:
            pr.append(f"第三分支缺证据前提 {x}")
    if i.get("fallback_verdict") != "UNABLE_TO_COMPARE":
        pr.append(f"缺证据前提时应判 UNABLE_TO_COMPARE，实得 {i.get('fallback_verdict')}")
    if i.get("merge_into_row_set_verdict") != "REJECT":
        pr.append("IMPL_SUSPECT 不得并入行集分歧桶（合并应判 REJECT）")
    if i.get("countersign_required") is not True:
        pr.append("UNABLE_TO_COMPARE 台账行必须要求联签")
    parties = set(i.get("countersign_parties") or [])
    for x in ("digest_producer", "independent_reader"):
        if x not in parties:
            pr.append(f"联签方须含 {x}")
    if i.get("self_signed_excluded") is not True:
        pr.append("仅消费方自签的行必须排除在对外数字之外")
    ok = not pr
    return ok, "第三分支 + 证据前提 + 不得并桶 + 联签与自签排除 齐备" if ok else "；".join(pr), pr



def chk_cross_shot_anchor_consistency(c, ctx):
    x = c.get("cross_shot_anchor_consistency") or {}
    pr = []
    for k in ("version", "source", "rule"):
        if not x.get(k):
            pr.append(f"cross_shot_anchor_consistency 缺 {k}")
    if x.get("reference_mode") != "fixed_anchor":
        pr.append(f"基准须为固定锚点图，实得 {x.get('reference_mode')}")
    if x.get("sequential_comparison_forbidden") is not True:
        pr.append("顺序比对必须显式禁用")
    fc = x.get("feature_classes") or {}
    if set(fc.get("hard") or []) != HARD_FEATURE_SET:
        pr.append(f"硬特征集须为 {sorted(HARD_FEATURE_SET)}，实得 {fc.get('hard')}")
    if set(fc.get("soft") or []) != SOFT_FEATURE_SET:
        pr.append(f"软特征集须为 {sorted(SOFT_FEATURE_SET)}，实得 {fc.get('soft')}")
    if fc.get("tolerance_policy") != "per_class":
        pr.append(f"容差须按硬/软分档（per_class），实得 {fc.get('tolerance_policy')}")
    if fc.get("merged_tolerance_verdict") != "REJECT":
        pr.append("合并为单一容差必须判 REJECT（防过度滤波）")
    rt = x.get("rollback_tiers") or {}
    if len(rt.get("tiers") or []) < 3:
        pr.append(f"回滚分级不足三级，实得 {rt.get('tiers')}")
    if rt.get("mapping") != "by_change_severity":
        pr.append("回滚范围须按变更严重度映射")
    ps = x.get("pre_rollback_snapshot_check") or {}
    if ps.get("required") is not True:
        pr.append("回滚前快照存在性校验必须强制")
    if ps.get("missing_verdict") != "hardstop":
        pr.append(f"快照缺失须硬停，实得 {ps.get('missing_verdict')}")
    ok = not pr
    return ok, "固定锚点 + 硬/软特征解耦 + 三级回滚 + 回滚前快照硬停 齐备" if ok else "；".join(pr), pr


def chk_truncation_threshold_indeterminate(c, ctx):
    x = c.get("truncation_threshold_indeterminate") or {}
    pr = []
    for k in ("version", "source", "rule"):
        if not x.get(k):
            pr.append(f"truncation_threshold_indeterminate 缺 {k}")
    ta = x.get("threshold_alignment") or {}
    if ta.get("verdict") != "INDETERMINATE":
        pr.append(f"长度恰等阈值须判 INDETERMINATE，实得 {ta.get('verdict')}")
    if ta.get("may_pass") is not False:
        pr.append("阈值对齐读数不得判过（may_pass 必须为 false）")
    sv = x.get("second_vote") or {}
    if sv.get("mode") != "cross_cycle_cold_read":
        pr.append(f"第二票须跨周期磁盘冷读，实得 {sv.get('mode')}")
    if sv.get("same_cycle_reread_verdict") != "REJECT":
        pr.append("同周期同路径重读必须判 REJECT（故障域未隔离）")
    if sv.get("fault_domain_isolation_required") is not True:
        pr.append("二次投票必须强制故障域隔离")
    if set(x.get("required_triple") or []) != {"byte_length", "truncation_threshold", "read_cycle_id"}:
        pr.append(f"三格须为 byte_length/truncation_threshold/read_cycle_id，实得 {x.get('required_triple')}")
    ok = not pr
    return ok, "阈值对齐判不定 + 跨周期冷读第二票 齐备" if ok else "；".join(pr), pr


def chk_producer_set_rank_conflict(c, ctx):
    x = c.get("producer_set_rank_conflict") or {}
    pr = []
    for k in ("version", "source", "rule"):
        if not x.get(k):
            pr.append(f"producer_set_rank_conflict 缺 {k}")
    co = x.get("counting") or {}
    if co.get("unit") != "unique_producer_set":
        pr.append(f"来源计数单位须为唯一生产者集合，实得 {co.get('unit')}")
    for f in ("message_volume", "raw_rows"):
        if f not in set(co.get("forbidden_units") or []):
            pr.append(f"禁用计数单位须含 {f}")
    if co.get("wrong_unit_verdict") != "REJECT":
        pr.append("按消息量计数必须判 REJECT")
    cl = x.get("classification") or {}
    if cl.get("same_source_diff_content") != "CONFLICT":
        pr.append(f"同源异内容须判 CONFLICT，实得 {cl.get('same_source_diff_content')}")
    if cl.get("merge_into_duplicate_verdict") != "REJECT":
        pr.append("同源异内容并入重复桶必须判 REJECT")
    if cl.get("silent_dedup_forbidden") is not True:
        pr.append("静默去重必须显式禁止")
    nt = x.get("negative_testing") or {}
    for k, label in (("must_fail_cases_required", "must-fail 负例"), ("positive_control_paired", "正控配对"), ("event_code_explicit", "显式事件码")):
        if nt.get(k) is not True:
            pr.append(f"两规则须配 {label}")
    ok = not pr
    return ok, "唯一生产者集合计数 + 同源异内容判冲突 + must-fail 负例 齐备" if ok else "；".join(pr), pr


def chk_evaluator_computed_digest(c, ctx):
    x = c.get("evaluator_computed_digest") or {}
    pr = []
    for k in ("version", "source", "rule"):
        if not x.get(k):
            pr.append(f"evaluator_computed_digest 缺 {k}")
    if x.get("digest_input") != "evaluator_computed_result":
        pr.append(f"摘要输入域须为评估者计算结果，实得 {x.get('digest_input')}")
    forb = set(x.get("forbidden_inputs") or [])
    for f in ("claimed_expected_value", "declarer_self_report"):
        if f not in forb:
            pr.append(f"禁用摘要输入须含 {f}")
    if x.get("wrong_input_verdict") != "REJECT":
        pr.append("哈希声称期望值必须判 REJECT")
    if x.get("reproducible_without_trust") is not True:
        pr.append("回执须可独立复算（不依赖信任声明方）")
    for f in ("digest_alg", "digest_input_domain", "recompute_hint"):
        if f not in set(x.get("receipt_fields") or []):
            pr.append(f"回执字段须含 {f}")
    ok = not pr
    return ok, "回执摘要哈希评估者计算结果 + 可独立复算 齐备" if ok else "；".join(pr), pr


def chk_unattested_state(c, ctx):
    x = c.get("unattested_state") or {}
    pr = []
    for k in ("version", "source", "rule"):
        if not x.get(k):
            pr.append(f"unattested_state 缺 {k}")
    st = list(x.get("states") or [])
    if st != UNATTESTED_STATES:
        pr.append(f"状态枚举须为五态 {UNATTESTED_STATES}，实得 {st}")
    if "UNATTESTED" not in st:
        pr.append("UNATTESTED 必须作为并列第五态存在")
    if x.get("binary_collapse_verdict") != "REJECT":
        pr.append("中间态静默二值坍缩必须判 REJECT")
    ei = x.get("evidence_independence") or {}
    if set(ei.get("dimensions") or []) != {"causal", "administrative"}:
        pr.append(f"证据源独立性须含因果与行政两维，实得 {ei.get('dimensions')}")
    if ei.get("shared_source_verdict") != "REJECT":
        pr.append("校验方与被校验方同源必须判 REJECT")
    ts = x.get("timestamp") or {}
    if ts.get("mode") != "externally_signed":
        pr.append(f"时间戳须外部签名，实得 {ts.get('mode')}")
    if ts.get("wall_clock_assertion_verdict") != "REJECT":
        pr.append("墙钟自断言必须判 REJECT")
    ok = not pr
    return ok, "UNATTESTED 第五态 + 证据双重独立 + 外部签名时间戳 齐备" if ok else "；".join(pr), pr


def chk_semantic_window_default_drift(c, ctx):
    x = c.get("semantic_window_default_drift") or {}
    pr = []
    for k in ("version", "source", "rule"):
        if not x.get(k):
            pr.append(f"semantic_window_default_drift 缺 {k}")
    si = x.get("snapshot_insufficiency") or {}
    if si.get("param_hash_unchanged_is_sufficient") is not False:
        pr.append("参数哈希不变不得判快照等价")
    if si.get("missed_dimension") != "default_expansion":
        pr.append(f"须显式点名漏判维度 default_expansion，实得 {si.get('missed_dimension')}")
    ca = x.get("content_addressable") or {}
    if ca.get("pre_expanded_defaults_required") is not True:
        pr.append("须存展开前默认值的内容寻址摘要")
    if ca.get("digest_scope") != "pre_expansion_effective_window":
        pr.append(f"摘要口径须为展开前有效窗口，实得 {ca.get('digest_scope')}")
    if set(x.get("exhaustiveness_binding_triple") or []) != set(SEMANTIC_WINDOW_TRIPLE):
        pr.append(f"穷尽性须绑定三元组 {SEMANTIC_WINDOW_TRIPLE}，实得 {x.get('exhaustiveness_binding_triple')}")
    if x.get("stale_validation_inheritance_verdict") != "REJECT":
        pr.append("陈旧验证继承必须判 REJECT")
    ok = not pr
    return ok, "默认值漂移落盘 + 展开前内容寻址摘要 + 穷尽性三元绑定 齐备" if ok else "；".join(pr), pr


# ─────────────────────────────────────────────────────────────
# v1.8.0 吸纳层：竖屏画面包装设计口径（AK–AN）
# 上游：pbakaus/impeccable（Apache-2.0）；对真实 HTML 只读扫描，不写入、不修改画面产物
# ─────────────────────────────────────────────────────────────

def _design_scope_files(root, pattern):
    return sorted(glob.glob(os.path.join(root, pattern), recursive=True))


def _design_scan(files, rx_rules):
    hits = {}
    for rid, rx in rx_rules:
        n = 0
        for f in files:
            try:
                with open(f, encoding="utf-8", errors="ignore") as fh:
                    n += len(rx.findall(fh.read()))
            except OSError:
                continue
        hits[rid] = n
    return hits


def chk_hyperframes_design_bans(c, ctx):
    """AK：画面包装 HTML 禁用项登记 + 正则自证 + 只读扫描对账。"""
    x = c.get("hyperframes_design_bans") or {}
    pr = []
    for k in ("version", "source", "rule", "negative_case"):
        if not x.get(k):
            pr.append(f"hyperframes_design_bans 缺 {k}")
    up = x.get("upstream") or {}
    if up.get("repo") != "pbakaus/impeccable":
        pr.append(f"上游仓须为 pbakaus/impeccable，实得 {up.get('repo')!r}")
    if up.get("license") != "Apache-2.0":
        pr.append(f"许可须为 Apache-2.0，实得 {up.get('license')!r}")
    commit = str(up.get("commit") or "")
    if len(commit) != 40 or any(ch not in "0123456789abcdef" for ch in commit):
        pr.append(f"本地 clone commit 须为 40 位小写十六进制，实得 {commit!r}")
    if not up.get("reference_docs"):
        pr.append("缺 reference_docs 溯源清单（来源文档 + 摘要）")

    rules = x.get("rules") or []
    ids = [r.get("id") for r in rules]
    idset = set(ids)
    if len(ids) != len(idset):
        pr.append("禁用项规则 id 存在重复")
    if idset != DESIGN_BAN_RULE_IDS:
        pr.append("禁用项规则集须与登记集一致（缺 "
                  f"{sorted(DESIGN_BAN_RULE_IDS - idset)} / 多 {sorted(idset - DESIGN_BAN_RULE_IDS)}）")
    for r in rules:
        rid = r.get("id")
        for k in ("name", "verdict", "basis_rule"):
            if not r.get(k):
                pr.append(f"规则 {rid} 缺 {k}")
        if r.get("verdict") and r["verdict"] not in DESIGN_RULE_VERDICTS:
            pr.append(f"规则 {rid} 的 verdict 须为 ban/default，实得 {r.get('verdict')!r}")
        det = r.get("detector")
        if det not in DESIGN_DETECTORS:
            pr.append(f"规则 {rid} 的 detector 须为 regex/manual，实得 {det!r}")
            continue
        if det == "manual":
            if not r.get("review_entry"):
                pr.append(f"规则 {rid} 为人工评审项，须声明 review_entry 落点")
            continue
        pat, hit, pas = r.get("pattern"), r.get("should_hit"), r.get("should_pass")
        if not pat or not hit or not pas:
            pr.append(f"规则 {rid} 缺 pattern/should_hit/should_pass（正则项须带自证样本）")
            continue
        try:
            rx = re.compile(pat, re.IGNORECASE)
        except re.error as exc:
            pr.append(f"规则 {rid} 正则不可编译：{exc}")
            continue
        if not rx.search(hit):
            pr.append(f"规则 {rid} 自证失败：pattern 未命中 should_hit")
        if rx.search(pas):
            pr.append(f"规则 {rid} 自证失败：pattern 误伤 should_pass")

    scope = x.get("scan_scope") or {}
    if set(scope) != set(DESIGN_SCOPES):
        pr.append(f"scan_scope 须含 {list(DESIGN_SCOPES)} 两域，实得 {sorted(scope)}")
    root = ctx.get("root") or ROOT_DEFAULT
    files_by_scope, n_files = {}, {}
    for key in DESIGN_SCOPES:
        cfg = scope.get(key) or {}
        pat = cfg.get("glob")
        files = _design_scope_files(root, pat) if pat else []
        if not pat:
            pr.append(f"scan_scope.{key} 缺 glob")
        files_by_scope[key] = files
        n_files[key] = len(files)
        mn = cfg.get("min_files")
        if not isinstance(mn, int) or mn < 1:
            pr.append(f"scan_scope.{key}.min_files 须为正整数（空扫描不得判过）")
        elif len(files) < mn:
            pr.append(f"scan_scope.{key} 扫描面萎缩：实得 {len(files)} 个 HTML < 登记下限 {mn}（材料缺失不得判过）")

    inv = x.get("legacy_inventory") or {}
    rx_rules = [(r["id"], re.compile(r["pattern"], re.IGNORECASE)) for r in rules
                if r.get("detector") == "regex" and r.get("pattern")]
    rx_ids = {rid for rid, _ in rx_rules}
    live = {key: _design_scan(files_by_scope.get(key) or [], rx_rules) for key in DESIGN_SCOPES}
    drift = {key: [] for key in DESIGN_SCOPES}
    for key in DESIGN_SCOPES:
        declared = inv.get(key)
        if not isinstance(declared, dict):
            pr.append(f"legacy_inventory.{key} 缺失（存量命中欠账清单）")
            continue
        miss = sorted(rx_ids - set(declared))
        if miss:
            pr.append(f"legacy_inventory.{key} 未登记正则项 {miss}")
        for rid in sorted(rx_ids):
            d, l = declared.get(rid, 0), live[key][rid]
            if l > d:
                drift[key].append(f"{rid} {d}→{l}")
    if drift["templates"]:
        pr.append("templates 域出现未登记禁用项命中（母版按阻断制）：" + "、".join(drift["templates"]))
    if "composition" not in n_files or sum(n_files.values()) == 0:
        pr.append("扫描未取到任何 HTML（材料缺失不得判过）")

    if pr:
        return False, "；".join(pr[:8]), pr
    reg = sum(1 for r in rules if r.get("detector") == "regex")
    tot = sum(sum(v.values()) for v in live.values())
    detail = (f"禁用项 {len(rules)} 条登记（正则 {reg} 条自证通过 / 人工评审 {len(rules) - reg} 条）；"
              f"只读扫描 composition {n_files['composition']} 个 + 模板 {n_files['templates']} 个 HTML，"
              f"存量命中 {tot} 处（templates 阻断制 / composition 登记制）")
    if drift["composition"]:
        detail += "；composition 欠账登记：" + "、".join(drift["composition"])
    return True, detail, []


def chk_hyperframes_type_rhythm_floor(c, ctx):
    """AL：五角色字号地板 + 层级步进 + 字距下限 + 深底补偿 + 平台安全区。"""
    x = c.get("hyperframes_type_rhythm_floor") or {}
    pr = []
    for k in ("version", "source", "rule", "negative_case"):
        if not x.get(k):
            pr.append(f"hyperframes_type_rhythm_floor 缺 {k}")
    if not x.get("local_derivation"):
        pr.append("须登记 local_derivation：区分「原样吸纳」与「竖屏折算」")
    roles = x.get("role_scale") or []
    rids = {r.get("role") for r in roles}
    if rids != TYPE_ROLE_IDS:
        pr.append(f"文字角色集须为 {sorted(TYPE_ROLE_IDS)}，实得 {sorted(rids)}")
    if x.get("tracking_floor_em") != TYPE_TRACKING_FLOOR_EM:
        pr.append(f"字距下限须为 {TYPE_TRACKING_FLOOR_EM}em，实得 {x.get('tracking_floor_em')}")
    step = x.get("scale_step_min")
    if not isinstance(step, (int, float)) or step < TYPE_MIN_SCALE_STEP:
        pr.append(f"层级步进下限须 ≥{TYPE_MIN_SCALE_STEP}，实得 {step}")
    for r in roles:
        rid = r.get("role")
        for k in ("min_px", "weight", "tracking_em", "line_height"):
            if r.get(k) is None:
                pr.append(f"角色 {rid} 缺 {k}")
        t = r.get("tracking_em")
        if isinstance(t, (int, float)) and t < TYPE_TRACKING_FLOOR_EM:
            pr.append(f"角色 {rid} 字距 {t}em 紧于下限 {TYPE_TRACKING_FLOOR_EM}em")
        lh = r.get("line_height")
        if isinstance(lh, (int, float)) and not 1.0 <= lh <= 1.8:
            pr.append(f"角色 {rid} 行高 {lh} 不在 1.0–1.8 可读区间")
    sized = [r for r in roles if isinstance(r.get("min_px"), (int, float))]
    for a, b in zip(sized, sized[1:]):
        if b.get("min_px"):
            if b["min_px"] >= a["min_px"]:
                pr.append(f"role_scale 须按字号降序：{a.get('role')}({a['min_px']}) → {b.get('role')}({b['min_px']})")
            elif a["min_px"] / b["min_px"] < step:
                pr.append(f"角色 {a.get('role')}→{b.get('role')} 字号步进仅 "
                          f"{a['min_px'] / b['min_px']:.2f}（<{step}，层级不可辨）")
    dc = x.get("dark_surface_compensation") or {}
    if set(dc.get("axes") or []) != TYPE_COMPENSATION_AXES:
        pr.append(f"深底补偿轴须为 {sorted(TYPE_COMPENSATION_AXES)}，实得 {sorted(dc.get('axes') or [])}")
    if dc.get("direct_copy_verdict") != "REJECT":
        pr.append("深底直接套用浅底排版数值须判 REJECT")
    me = x.get("measure") or {}
    if not isinstance(me.get("body_chars_per_line_max"), int) or me.get("body_chars_per_line_max", 0) < 1:
        pr.append("measure.body_chars_per_line_max 须为正整数")
    if me.get("over_limit_verdict") != "REJECT":
        pr.append("行宽超限须判 REJECT（禁缩字蒙混）")
    fp = x.get("font_policy") or {}
    for k in ("ship_only_used_weights", "metric_compatible_fallback", "fallback_without_layout_shift"):
        if fp.get(k) is not True:
            pr.append(f"font_policy.{k} 须为 true")
    if (x.get("numeric_policy") or {}).get("tabular_numerals") is not True:
        pr.append("数字类画面须启用 tabular-nums（numeric_policy.tabular_numerals=true）")
    sa = x.get("platform_safe_area") or {}
    top, bot = sa.get("title_safe_margin_ratio"), sa.get("bottom_caption_reserve_ratio")
    if not (isinstance(top, (int, float)) and isinstance(bot, (int, float))
            and top > 0 and bot > 0 and top + bot < 0.5):
        pr.append(f"平台安全区比例须为 (0,0.5) 内正值：实得 margin={top} / reserve={bot}")
    if sa.get("overlap_verdict") != "REJECT":
        pr.append("关键文字压入字幕/按钮遮挡区须判 REJECT")
    ok = not pr
    return ok, (f"五角色字号地板与步进 ≥{step}、字距下限 {x.get('tracking_floor_em')}em、"
                f"深底补偿 {sorted(TYPE_COMPENSATION_AXES)}、平台安全区 {top}/{bot} 已登记") if ok else "；".join(pr), pr


def chk_hyperframes_motion_authorship(c, ctx):
    """AM：一镜一署名动效 + 缓动/时长分档 + 只动 transform/opacity/filter + 默认可见 + reduced-motion。"""
    x = c.get("hyperframes_motion_authorship") or {}
    pr = []
    for k in ("version", "source", "rule", "negative_case"):
        if not x.get(k):
            pr.append(f"hyperframes_motion_authorship 缺 {k}")
    fm = x.get("focal_moment") or {}
    if fm.get("max_per_shot") != 1:
        pr.append(f"一镜署名动效时刻须恰为 1（实得 {fm.get('max_per_shot')}）")
    if fm.get("over_limit_verdict") != "REJECT":
        pr.append("署名时刻超限须判 REJECT（多处强动效互相抵消）")
    ez = x.get("easing") or {}
    if not ez.get("primary"):
        pr.append("缺主缓动曲线 easing.primary")
    if set(ez.get("banned_families") or []) != MOTION_BANNED_EASINGS:
        pr.append(f"禁用缓动族须为 {sorted(MOTION_BANNED_EASINGS)}，实得 {sorted(ez.get('banned_families') or [])}")
    if ez.get("bounce_verdict") != "REJECT":
        pr.append("弹跳/回弹族须判 REJECT")
    tiers = x.get("duration_tiers") or {}
    if set(tiers) != set(MOTION_TIER_IDS):
        pr.append(f"时长分档须含 {list(MOTION_TIER_IDS)}，实得 {sorted(tiers)}")
    prev_hi = 0
    for k in MOTION_TIER_IDS:
        rng = tiers.get(k)
        if not (isinstance(rng, list) and len(rng) == 2 and rng[0] < rng[1]):
            pr.append(f"时长档 {k} 须为 [下限,上限] 且下限<上限：实得 {rng}")
            continue
        if rng[0] < prev_hi:
            pr.append(f"时长档 {k} 与上一档重叠（{prev_hi} > {rng[0]}）")
        prev_hi = rng[1]
    if x.get("duration_over_verdict") != "REJECT":
        pr.append("动效时长越档须判 REJECT")
    ex = x.get("exit_faster_than_enter") or {}
    if ex.get("enabled") is not True or not (isinstance(ex.get("max_ratio"), (int, float))
                                              and 0 < ex.get("max_ratio", 0) < 1):
        pr.append("退出须快于进入（enabled=true 且 max_ratio∈(0,1)）")
    dv = x.get("default_visible") or {}
    if dv.get("required") is not True or dv.get("missing_script_verdict") != "REJECT":
        pr.append("内容默认可见（脚本失败不得白屏）：required=true 且 missing_script_verdict=REJECT")
    ap = x.get("animatable_properties") or {}
    if set(ap.get("allowed") or []) != {"transform", "opacity", "filter"}:
        pr.append(f"可动属性须为 transform/opacity/filter，实得 {sorted(ap.get('allowed') or [])}")
    if set(ap.get("banned_layout") or []) != MOTION_BANNED_PROPS:
        pr.append(f"禁动布局属性须为 {sorted(MOTION_BANNED_PROPS)}，实得 {sorted(ap.get('banned_layout') or [])}")
    if ap.get("layout_animation_verdict") != "REJECT":
        pr.append("动布局属性须判 REJECT（逐帧重排丢帧、缩放失真）")
    rm = x.get("reduced_motion_path") or {}
    if rm.get("required") is not True or "prefers-reduced-motion" not in str(rm.get("css") or ""):
        pr.append("须提供 prefers-reduced-motion 降级路径")
    if not rm.get("fallback"):
        pr.append("缺 reduced-motion 降级形态（静态定格帧且信息完整）")
    st = x.get("stagger") or {}
    m = st.get("max_items")
    if not isinstance(m, int) or not 1 <= m <= 6:
        pr.append(f"错峰项数上限须为 1–6 的整数，实得 {m}")
    ok = not pr
    return ok, (f"署名时刻上限 {fm.get('max_per_shot')}、缓动族禁用 {sorted(MOTION_BANNED_EASINGS)}、"
                f"时长四档不重叠、默认可见与 reduced-motion 已登记") if ok else "；".join(pr), pr


def chk_hyperframes_color_depth_roles(c, ctx):
    """AN：语义色分工 + WCAG AA 对比地板 + 深度分层 + 渐变须承载信息。"""
    x = c.get("hyperframes_color_depth_roles") or {}
    pr = []
    for k in ("version", "source", "rule", "negative_case"):
        if not x.get(k):
            pr.append(f"hyperframes_color_depth_roles 缺 {k}")
    roles = x.get("roles") or {}
    if set(roles) != COLOR_ROLE_IDS:
        pr.append(f"颜色角色须为 {sorted(COLOR_ROLE_IDS)}，实得 {sorted(roles)}")
    for k, v in roles.items():
        if not (v or {}).get("usage"):
            pr.append(f"颜色角色 {k} 缺 usage（语义用途）")
    ct = x.get("contrast") or {}
    for k, v in COLOR_CONTRAST_FLOOR.items():
        if ct.get(k) != v:
            pr.append(f"对比度地板 {k} 须为 {v}:1，实得 {ct.get(k)}")
    if ct.get("standard") != "WCAG 2.2 AA":
        pr.append(f"对比度标准须标 WCAG 2.2 AA，实得 {ct.get('standard')!r}")
    if (x.get("color_space") or {}).get("preferred") != "oklch":
        pr.append("色彩空间须优先 oklch")
    dp = x.get("depth") or {}
    if set(dp.get("layers") or []) != COLOR_DEPTH_LAYERS:
        pr.append(f"深度分层须为 {sorted(COLOR_DEPTH_LAYERS)}，实得 {sorted(dp.get('layers') or [])}")
    if set(dp.get("forbidden") or []) != COLOR_DEPTH_FORBIDDEN:
        pr.append(f"禁用深度手段须为 {sorted(COLOR_DEPTH_FORBIDDEN)}，实得 {sorted(dp.get('forbidden') or [])}")
    if dp.get("verdict") != "REJECT":
        pr.append("使用禁用深度手段须判 REJECT")
    gp = x.get("gradient_policy") or {}
    if gp.get("decorative_gradient_verdict") != "ban":
        pr.append("纯装饰性渐变须判 ban")
    ms = gp.get("max_stops")
    if not isinstance(ms, int) or ms > 3:
        pr.append(f"渐变色停上限须 ≤3，实得 {ms}")
    if gp.get("meaningful_only") is not True:
        pr.append("渐变须承载信息或品牌授权（meaningful_only=true）")
    ab = x.get("accent_budget") or {}
    mr = ab.get("max_roles")
    if not isinstance(mr, int) or mr > 2:
        pr.append(f"同帧强调色分工上限须 ≤2，实得 {mr}")
    if ab.get("over_limit_verdict") != "REJECT":
        pr.append("强调色超预算须判 REJECT")
    ok = not pr
    return ok, (f"四色角色语义分工、对比地板 {COLOR_CONTRAST_FLOOR['body_min_ratio']}:1/"
                f"{COLOR_CONTRAST_FLOOR['large_text_min_ratio']}:1、深度分层与渐变策略已登记") if ok else "；".join(pr), pr


def chk_param_provenance_incomparable(c, ctx):
    """AO：参数溯源三态独立 + absent/显式默认判不可比 + 处置档按归因能力。"""
    x = c.get("param_provenance_incomparable") or {}
    pr = []
    for k in ("version", "source", "rule", "negative_case"):
        if not x.get(k):
            pr.append(f"param_provenance_incomparable 缺 {k}")
    states = set(x.get("provenance_states") or [])
    if states != PARAM_PROVENANCE_STATES:
        pr.append("溯源状态集须恰为 declared/defaulted_explicitly/absent，缺 "
                  f"{sorted(PARAM_PROVENANCE_STATES - states)} / 多 {sorted(states - PARAM_PROVENANCE_STATES)}")
    if x.get("absent_is_value") is not False:
        pr.append("absent 是状态而非取值：absent_is_value 必须为 false（折叠为取值即判红）")
    if x.get("cross_state_verdict") != PARAM_CROSS_STATE_VERDICT:
        pr.append("absent-run 与 explicitly-defaulted-run 之间必须判 "
                  f"{PARAM_CROSS_STATE_VERDICT}，实得 {x.get('cross_state_verdict')!r}")
    vr = x.get("verdict_rule") or {}
    for k, v in PARAM_VERDICT_RULE.items():
        if vr.get(k) != v:
            pr.append(f"处置档 {k} 须为 {v}，实得 {vr.get(k)!r}")
    if "zero_declared_vs_default" not in set(x.get("orthogonal_to") or []):
        pr.append("须声明与 K-declared-vs-default 的分工（orthogonal_to 缺 zero_declared_vs_default）")
    ok = not pr
    return ok, ("参数溯源三态独立 + absent 与显式默认判不可比 + 处置档按归因能力（unknown 不得静默升基准）"
                if ok else "；".join(pr)), pr


def chk_normalization_act_ledger(c, ctx):
    """AP：漂移形态→归一动作成表 + 归一动作落账 + 三版本随键 + 表示四态不互归。"""
    x = c.get("normalization_act_ledger") or {}
    pr = []
    for k in ("version", "source", "rule", "negative_case"):
        if not x.get(k):
            pr.append(f"normalization_act_ledger 缺 {k}")
    forms = list(x.get("drift_forms") or [])
    if forms != NORM_DRIFT_FORMS:
        pr.append(f"漂移形态清单须恰为 {NORM_DRIFT_FORMS}，实得 {forms}")
    acts = x.get("normalization_actions") or []
    if len(acts) != len(NORM_DRIFT_FORMS):
        pr.append(f"漂移形态→归一动作须逐形态成对（应 {len(NORM_DRIFT_FORMS)} 条，实得 {len(acts)}）")
    for i, a in enumerate(acts):
        for k in ("drift_form", "action", "ledger_entry"):
            if not a.get(k):
                pr.append(f"归一动作 {i} 缺 {k}")
        if i < len(forms) and a.get("drift_form") != forms[i]:
            pr.append(f"归一动作 {i} 的 drift_form 与形态清单错位（{a.get('drift_form')!r}）")
        vs = set(a.get("ledger_key_versions") or [])
        if vs != set(NORM_VERSION_TRIO):
            pr.append(f"归一动作 {a.get('drift_form')!r} 随键版本须齐三件，实得 {sorted(vs)}")
    if x.get("normalization_is_semantic_change") is not True:
        pr.append("归一动作本身即语义变更：normalization_is_semantic_change 须为 true")
    if x.get("alignment_ledger_required") is not True:
        pr.append("归一动作必须落账：alignment_ledger_required 须为 true")
    trio = list(x.get("version_trio") or [])
    if trio != NORM_VERSION_TRIO:
        pr.append(f"随键版本三件须为 {NORM_VERSION_TRIO}，实得 {trio}")
    reps = set(x.get("representation_states") or [])
    if reps != NORM_REPRESENTATION_STATES:
        pr.append(f"表示漂移四态须为 {sorted(NORM_REPRESENTATION_STATES)}，实得 {sorted(reps)}")
    if x.get("merge_representation_verdict") != "REJECT":
        pr.append("null/缺失/空串/空数组 互相归一时必须判 REJECT")
    if x.get("undeclared_equivalence_action") != "treat_as_new_semantics":
        pr.append("未显式声明等价的形态不得归一，须按新语义处理（treat_as_new_semantics）")
    ok = not pr
    return ok, ("漂移形态→归一动作 5 对齐全、归一动作落账且三版本随键、表示四态不互归"
                if ok else "；".join(pr)), pr


def chk_snapshot_lifetime_alignment(c, ctx):
    """AQ：快照签发方 / 只认 as_of 读数 / 留存期与回收前提同源。"""
    x = c.get("snapshot_lifetime_alignment") or {}
    pr = []
    for k in ("version", "source", "rule", "negative_case"):
        if not x.get(k):
            pr.append(f"snapshot_lifetime_alignment 缺 {k}")
    if x.get("snapshot_issuer_required") is not True:
        pr.append("快照必须显式带签发方：snapshot_issuer_required 须为 true")
    if x.get("self_signed_verdict") != SNAPSHOT_SELF_SIGNED_VERDICT:
        pr.append(f"签发方同时是判据与执行者时判 {SNAPSHOT_SELF_SIGNED_VERDICT}，"
                  f"实得 {x.get('self_signed_verdict')!r}")
    if x.get("as_of_only") is not True:
        pr.append("判定只认可显式快照 as_of 时刻读数：as_of_only 须为 true")
    if x.get("current_read_forbidden") is not True:
        pr.append("禁用『当前』读数回溯判定：current_read_forbidden 须为 true")
    if x.get("lifetime_source") != SNAPSHOT_LIFETIME_SOURCE:
        pr.append(f"快照留存期须与回收前提同源（{SNAPSHOT_LIFETIME_SOURCE}），"
                  f"实得 {x.get('lifetime_source')!r}")
    if x.get("retention_mismatch_verdict") != "REJECT":
        pr.append("留存期与回收前提不同源时必须判 REJECT")
    if not (x.get("related_to") or x.get("evidence_ref")):
        pr.append("须声明与既有证据类口径的关系（related_to）")
    ok = not pr
    return ok, ("快照带签发方且自签不计证据、只认 as_of 读数、留存期与回收前提同源"
                if ok else "；".join(pr)), pr


def chk_verify_anchor_outside_chain(c, ctx):
    """AS：验证锚点位于被检链外 / 发布期冻结清单随产物落盘 / 恢复侧按差集判定 / 内容段与结构段分离。"""
    x = c.get("verify_anchor_outside_chain") or {}
    pr = []
    for k in ("version", "source", "rule", "negative_case"):
        if not x.get(k):
            pr.append(f"verify_anchor_outside_chain 缺 {k}")
    if x.get("anchor_side_requirement") != ANCHOR_OPPOSITE_SIDE:
        pr.append(f"验证锚点须位于被检数据另一侧（{ANCHOR_OPPOSITE_SIDE}），"
                  f"实得 {x.get('anchor_side_requirement')!r}")
    if x.get("same_side_verdict") != ANCHOR_SAME_SIDE_VERDICT:
        pr.append(f"锚点与被检数据同侧须判静默误过、禁止判过"
                  f"（{ANCHOR_SAME_SIDE_VERDICT}），实得 {x.get('same_side_verdict')!r}")
    if x.get("manifest_frozen_at_release") is not True:
        pr.append("期望清单须在发布时冻结：manifest_frozen_at_release 须为 true")
    if x.get("manifest_persisted_with_artifact") is not True:
        pr.append("冻结清单须与产物同批落盘：manifest_persisted_with_artifact 须为 true")
    if x.get("recovery_verdict_mode") != ANCHOR_DELTA_MODE:
        pr.append(f"恢复 / 校验侧须按『实际 vs 期望』差集判定（{ANCHOR_DELTA_MODE}），"
                  f"实得 {x.get('recovery_verdict_mode')!r}")
    if x.get("self_attestation_verdict") != "NOT_EVIDENCE":
        pr.append("链内锚点自证不计证据：self_attestation_verdict 须为 NOT_EVIDENCE")
    if set(x.get("segment_separation_required") or []) != {"content", "structure"}:
        pr.append("内容段与结构段须在套用转义机制前分离："
                  "segment_separation_required 须为 content + structure")
    if x.get("segment_merge_verdict") != "REJECT":
        pr.append("内容段与结构段混合后套用转义机制须判 REJECT")
    if not (x.get("related_to") or x.get("evidence_ref")):
        pr.append("须声明与既有证据类口径的关系（related_to）")
    ok = not pr
    return ok, ("锚点落被检链外、发布期冻结清单随产物同批落盘、恢复侧按差集判定、内容段与结构段分离"
                if ok else "；".join(pr)), pr


def chk_expectation_set_signing_event(c, ctx):
    """AT：期望集非常量 / 变更作版本化签发事件入账 / 取数路径连同内容哈希进签名域冻结。"""
    x = c.get("expectation_set_signing_event") or {}
    pr = []
    for k in ("version", "source", "rule", "negative_case"):
        if not x.get(k):
            pr.append(f"expectation_set_signing_event 缺 {k}")
    if x.get("expectation_set_is_constant") is not False:
        pr.append("期望集不得被当作常量：expectation_set_is_constant 须为 false")
    if x.get("change_is_versioned_signing_event") is not True:
        pr.append("期望集变更须为版本化签发事件：change_is_versioned_signing_event 须为 true")
    if x.get("change_ledger_required") is not True:
        pr.append("期望集变更须入账：change_ledger_required 须为 true")
    if set(x.get("change_ledger_fields") or []) != EXPECT_SIGNING_LEDGER_FIELDS:
        pr.append(f"变更账本须含 {sorted(EXPECT_SIGNING_LEDGER_FIELDS)}，"
                  f"实得 {x.get('change_ledger_fields')!r}")
    if x.get("silent_change_verdict") != "REJECT":
        pr.append("期望集变更静默生效须判 REJECT")
    if x.get("data_path_in_signature_domain") is not True:
        pr.append("取数路径须进签名域：data_path_in_signature_domain 须为 true")
    if set(x.get("path_freeze_binding") or []) != EXPECT_PATH_BINDING:
        pr.append(f"取数路径冻结须绑定 {sorted(EXPECT_PATH_BINDING)}，"
                  f"实得 {x.get('path_freeze_binding')!r}")
    if x.get("path_drift_verdict") != "REJECT":
        pr.append("取数路径静默替换（隐式标准漂移）须判 REJECT")
    if not (x.get("related_to") or x.get("evidence_ref")):
        pr.append("须声明与既有证据类口径的关系（related_to）")
    ok = not pr
    return ok, ("期望集非常量、变更作版本化签发事件入账、取数路径连同内容哈希进签名域冻结"
                if ok else "；".join(pr)), pr


CHECKS = [
    ("A-pending-ledger", "挂起与判据账本", chk_pending_ledger),
    ("B-cache-key-grid", "缓存键漂移五格", chk_cache_key_grid),
    ("C-stop-degrade-tiers", "硬停与降级分层", chk_stop_degrade_tiers),
    ("D-zero-semantics", "零值语义与断言绑定", chk_zero_semantics),
    ("E-drift-fieldset", "漂移字段与翻案率", chk_drift_fieldset),
    ("F-manifest-receipt", "清单规范与回执", chk_manifest_columns),
    ("G-field-registry", "存量字段零值/断言归一", chk_field_registry),
    ("H-bridge", "与存量真源对接", chk_bridge),
    ("I-silent-rewrite", "静默改写判定（显式降级 / 静默升硬停）", chk_silent_rewrite),
    ("J-criteria-identity", "判据身份三格与版本换代出桶", chk_criteria_identity),
    ("K-declared-vs-default", "未声明 ≠ 默认", chk_zero_declared_vs_default),
    ("L-pending-age", "挂起年龄分布与阈值基数", chk_pending_age_distribution),
    ("M-overturn-denominator", "翻案率分母口径", chk_overturn_denominator),
    ("N-dependency-triple", "依赖版本三段", chk_dependency_version_triple),
    ("O-timebase-triple", "时基三格（含取整时机）", chk_timebase_triple),
    ("P-pagination", "分页第三态与合并判空", chk_pagination_completeness),
    ("Q-gate-three-numbers", "gate 三数同行与跳过发起侧记账", chk_gate_three_numbers),
    ("R-degrade-product-side", "降级由产物侧判定", chk_degrade_product_side),
    ("S-failure-domain", "失败域四段分桶", chk_failure_domain_buckets),
    ("T-shared-fault-domain", "共享故障域反例", chk_shared_fault_domain),
    ("U-portable-evidence", "可携带判据与私有证据出桶", chk_portable_evidence),
    ("V-defect-coverage", "缺陷类覆盖度自检", chk_defect_coverage),
    ("W-repair-matrix", "缺陷类 × 工序修复矩阵自检", chk_repair_matrix),
    ("X-restoration-chain-order", "修复链路顺序与生成式重建声明", chk_restoration_chain_order),
    ("Y-tile-seam-integrity", "分块接缝/闪烁负向断言", chk_tile_seam_integrity),
    ("Z-asr-segment-silence", "分段转写静默失败与句边界完整性", chk_asr_segment_silence),
    ("AA-degrade-double-write", "降级态双写与账本缺失硬停", chk_degrade_double_write),
    ("AB-version-overlap-ambiguous", "版本交叠判 AMBIGUOUS 交人工", chk_version_overlap_ambiguous),
    ("AC-loaded-version-attestation", "已加载版本运行侧指纹反推", chk_loaded_version_attestation),
    ("AD-impl-suspect-branch", "IMPL_SUSPECT 第三分支与联签", chk_impl_suspect_branch),
    ("AE-cross-shot-anchor-consistency", "跨镜头一致性：固定锚点与硬/软特征解耦", chk_cross_shot_anchor_consistency),
    ("AF-truncation-threshold-indeterminate", "截断阈值对齐判不定与跨周期冷读第二票", chk_truncation_threshold_indeterminate),
    ("AG-producer-set-rank-conflict", "来源计数按唯一生产者集合与同源异内容判冲突", chk_producer_set_rank_conflict),
    ("AH-evaluator-computed-digest", "回执摘要哈希评估者计算结果", chk_evaluator_computed_digest),
    ("AI-unattested-state", "UNATTESTED 第五态与证据源双重独立", chk_unattested_state),
    ("AJ-semantic-window-default-drift", "语义窗口默认值漂移与展开前内容寻址摘要", chk_semantic_window_default_drift),
    ("AK-hyperframes-design-bans", "画面包装 HTML 禁用项登记与只读扫描对账", chk_hyperframes_design_bans),
    ("AL-hyperframes-type-rhythm-floor", "画面文字节奏地板（字号/步进/字距/安全区）", chk_hyperframes_type_rhythm_floor),
    ("AM-hyperframes-motion-authorship", "画面动效署名与可达性（一镜一时刻/reduced-motion）", chk_hyperframes_motion_authorship),
    ("AN-hyperframes-color-depth-roles", "画面颜色角色与深度分层（WCAG AA/禁色晕）", chk_hyperframes_color_depth_roles),
    ("AO-param-provenance-incomparable", "参数溯源三态与跨状态不可比", chk_param_provenance_incomparable),
    ("AP-normalization-act-ledger", "归一动作落账与三版本随键", chk_normalization_act_ledger),
    ("AQ-snapshot-lifetime-alignment", "快照签发方/ as_of 读数 / 留存期同源", chk_snapshot_lifetime_alignment),
    ("AS-verify-anchor-outside-chain", "验证锚点落链外 / 发布期冻结清单 / 差集判定 / 段分离", chk_verify_anchor_outside_chain),
    ("AT-expectation-set-signing-event", "期望集非常量 / 版本化签发入账 / 取数路径进签名域", chk_expectation_set_signing_event),
]


# ─────────────────────────────────────────────────────────────
# overlay：对真实 manifest 做零值语义补判（音频流缺失 → FAIL）
# ─────────────────────────────────────────────────────────────

def overlay_manifest(path):
    m = read_json(path)
    if not m:
        return [{"field": "-", "overlay_verdict": "UNEXECUTABLE",
                 "reason": f"manifest 不可解析：{path}"}]
    a = ((m.get("derived") or {}).get("audio_sample_rate_channels")) or {}
    out = []
    if a.get("sample_rate_hz") is None:
        out.append({
            "field": "audio_sample_rate_channels",
            "overlay_verdict": "FAIL",
            "reason": "音频流缺失：未观测 ≠ 0，按失败处理（无音轨与静音共用分支会静默产出无声视频仍过检）",
            "zero_state": "UNOBSERVED",
            "action": "hardstop",
        })
    else:
        out.append({
            "field": "audio_sample_rate_channels",
            "overlay_verdict": "OK",
            "reason": f"{a.get('sample_rate_hz')}Hz/{a.get('channels')}ch 已观测",
            "zero_state": "CONFIRMED_ZERO" if a.get("sample_rate_hz") else "UNOBSERVED",
            "action": "hardstop",
        })
    return out


# ─────────────────────────────────────────────────────────────
# 上下文装配
# ─────────────────────────────────────────────────────────────

def build_ctx(root, canons):
    contract = read_json(os.path.join(root, "config", "param_contract.json")) or {}
    canon_json = read_json(os.path.join(root, "config", "canonicalization.json")) or {}
    frozen = read_json(os.path.join(root, "config", "frozen_baseline.json")) or {}
    obs = read_json(os.path.join(root, "config", "observability_rules.json")) or {}
    negcases = read_json(os.path.join(root, "config", "negcontrol_cases.json")) or {}

    fields = {f.get("field") for f in (contract.get("fields") or [])}
    ext = {f.get("field") for f in ((contract.get("extended_contract") or {}).get("fields") or [])}
    all_fields = fields | ext

    negcase_problems = []
    for case in negcases.get("cases") or []:
        cid = case.get("id")
        if not case.get("trigger") or not case.get("input") or not case.get("expect"):
            negcase_problems.append(f"{cid} 缺 trigger/input/expect")
            continue
        for e in case.get("expect") or []:
            if e.get("field") not in all_fields:
                negcase_problems.append(f"{cid} 期望字段 {e.get('field')} 不在合同字段集")

    return {
        "root": root,
        "contract": contract,
        "contract_fields": sorted(all_fields),
        "canonicalizer_signature": canon_json.get("signature"),
        "frozen_digest": frozen.get("digest"),
        "observability_ok": bool(obs) and len(obs) > 0,
        "negcase_problems": negcase_problems,
        "canons": canons,
    }


def run_checks(canons, ctx, verbose=True):
    results = []
    if verbose:
        print("=" * 100)
        print("工程口径吸纳层校验（canon_guard）")
        print("=" * 100)
        print(f"口径真源 : {CANONS_DEFAULT}")
        print(f"版本     : {canons.get('canons_version')}   签名 {signature_of(canons)}")
        print(f"存量字段 : {len(ctx.get('contract_fields') or [])} 条（10 核心 + 8 扩展）")
        print("-" * 100)
    for cid, label, fn in CHECKS:
        ok, detail, problems = fn(canons, ctx)
        results.append({"id": cid, "label": label, "pass": ok, "detail": detail, "problems": problems})
        if verbose:
            print(f"[{'PASS' if ok else 'FAIL'}] {cid}  {label}")
            print(f"        {detail}")
    n_fail = sum(1 for r in results if not r["pass"])
    if verbose:
        print("-" * 100)
        print(f"结果：PASS {len(results) - n_fail} / FAIL {n_fail}")
        print("=" * 100)
    return results, n_fail


# ─────────────────────────────────────────────────────────────
# 命令
# ─────────────────────────────────────────────────────────────

def cmd_check(args):
    canons = read_json(args.canons)
    if not canons:
        print(f"[error] 口径真源读不到：{args.canons}", file=sys.stderr)
        return 1
    ctx = build_ctx(args.root, canons)
    results, n_fail = run_checks(canons, ctx)

    overlay = None
    if args.manifest:
        overlay = overlay_manifest(args.manifest)
        print("─ 零值语义补判（overlay，未观测 ≠ 0）")
        for o in overlay:
            mark = "FAIL" if o["overlay_verdict"] == "FAIL" else ("OK" if o["overlay_verdict"] == "OK" else "ERR")
            print(f"  [{mark}] {o['field']}：{o['reason']}")
        if any(o["overlay_verdict"] == "FAIL" for o in overlay):
            print("  → 补判存在阻断项（overlay FAIL）")
            n_fail += 1

    out = args.out or OUT_DEFAULT
    payload = {
        "run_at": now_iso(),
        "canons_version": canons.get("canons_version"),
        "canons_signature": signature_of(canons),
        "contract_version": (ctx.get("contract") or {}).get("contract_version"),
        "context": {k: v for k, v in ctx.items() if k != "contract"},
        "results": results,
        "overlay": overlay,
        "summary": {
            "total": len(results),
            "pass": sum(1 for r in results if r["pass"]),
            "fail": sum(1 for r in results if not r["pass"]),
            "verdict": "ALL_CANONS_ENFORCED" if n_fail == 0 else "GAP_FOUND",
        },
    }
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print(f"[archive] 校验留档：{out}")
    return 2 if n_fail else 0


def _neg_mutators():
    def m1(c):  # 处置与变更触发合并
        cs = c["pending_ledger"]["column_separation"]
        cs["must_be_separate"] = [x for x in cs["must_be_separate"] if x != "disposition"]
        cs["merged_verdict"] = "ALLOW"
    def m2(c):  # 五格缺维 + 第五格可覆盖
        del c["cache_key_grid"]["facets"][0]["drift_trigger"]
        c["cache_key_grid"]["facets"][4]["consequence"] = "silent_stale_hit"
        c["cache_key_grid"]["facets"][4]["naming_rule"] = ""
    def m3(c):  # 硬停四类缺一 + 回落标记可被回落
        c["stop_degrade_tiers"]["hardstop_classes"] = c["stop_degrade_tiers"]["hardstop_classes"][:3]
        c["stop_degrade_tiers"]["fallback_marker"]["marker_itself_not_reversible"] = False
    def m4(c):  # 音频缺失降级 + 断言未绑定
        c["zero_semantics"]["audio_stream_missing"]["verdict"] = "WARN"
        c["zero_semantics"]["assertion_binding"]["unbound_verdict"] = "ALLOW"
    def m5(c):  # 翻案率跨版本求和 + 最易漂字段集不足
        c["drift_fieldset"]["overturn_rate"]["no_cross_version_sum"] = False
        c["drift_fieldset"]["easiest_drift_fields"] = c["drift_fieldset"]["easiest_drift_fields"][:10]
    def m6(c):  # 清单五列缺一 + 缺列不判未声明
        c["manifest_columns"]["columns"] = [x for x in c["manifest_columns"]["columns"] if x != "domain"]
        c["manifest_columns"]["missing_column_verdict"] = "IGNORE"
    def m7(c):  # 注册表漏字段 + 断言动作非法
        c["field_registry"]["fields"] = [f for f in c["field_registry"]["fields"] if f["field"] != "audio_sample_rate_channels"]
        c["field_registry"]["fields"][3]["assertion_action"] = "unknown_action"
    def m8(c):  # 同组织布尔缺失
        del c["pending_ledger"]["issuer_scope"]["type"]
        c["pending_ledger"]["issuer_scope"]["unknown_handling"] = None
    def m9(c):  # 静默改写被按显式变化降级
        c["silent_rewrite"]["silent_rewrite"]["verdict"] = "degrade"
    def m10(c):  # 判据缺生效起点 + 版本换代并桶
        c["criteria_identity"]["required_triple"] = ["version", "issuer"]
        c["criteria_identity"]["version_generation_event"]["excluded_from"] = []
    def m11(c):  # 未声明与显式默认合并
        c["zero_declared_vs_default"]["states"] = ["UNDECLARED"]
        c["zero_declared_vs_default"]["merged_verdict"] = "ALLOW"
    def m12(c):  # 阈值基数改用存量
        c["pending_age_distribution"]["threshold_base"]["denominator"] = "存量挂起总数"
    def m13(c):  # 翻案率分母含未复核
        c["overturn_denominator"]["denominator"] = "all_rejections"
    def m14(c):  # 依赖版本只剩两段
        c["dependency_version_triple"]["segments"] = ["source_version", "content_hash"]
    def m15(c):  # 时基缺取整时机
        c["timebase_triple"]["required_triple"] = ["unit", "clock_domain"]
    def m16(c):  # 分页第三态被折叠进取尽
        c["pagination_completeness"]["third_state"]["id"] = "exhausted"
    def m17(c):  # gate 跳过在应答侧记账
        c["gate_three_numbers"]["skip_accounting_side"] = "responder"
    def m18(c):  # 降级改由链路自报
        c["degrade_product_side"]["method"] = "由链路自报是否走降级"
    def m19(c):  # 失败域少一段分桶
        c["failure_domain_buckets"]["buckets"] = c["failure_domain_buckets"]["buckets"][:3]
    def m20(c):  # 共享故障域反例缺一
        c["shared_fault_domain"]["counter_examples"] = c["shared_fault_domain"]["counter_examples"][:2]
    def m21(c):  # 可携带判据缺产物指纹
        c["portable_evidence"]["min_pieces"] = [
            x for x in c["portable_evidence"]["min_pieces"]
            if not str(x).startswith("artifact_fingerprint")
        ]
    def m22(c):  # 缺陷覆盖缺一类
        c["defect_coverage"]["classes"] = c["defect_coverage"]["classes"][:7]
    def m23(c):  # 修复矩阵出现空行
        k = next(iter(c["repair_matrix"]["matrix"]))
        c["repair_matrix"]["matrix"][k] = []
    def m24(c):  # 修复链路顺序倒置 + 缺生成式声明 + 禁用采样器族放行
        r = c["restoration_chain_order"]
        r["ordered_stages"] = ["deinterlace", "refine_details", "restore"]
        r["generative_declaration"] = {"required": False}
        r["sampler_family_constraint"] = {"allowed": ["dpmpp_2m", "ancestral"]}
    def m25(c):  # 分块缺接缝断言 + 越桶只警告 + guide 用空间 tiled 编码
        t = c["tile_seam_integrity"]
        t["forbidden_assertion_set"] = []
        t["oversize_verdict"] = "WARN"
        t["guide_encode_constraint"] = {"use_tiled_encode": True}
    def m26(c):  # 转写三数缺一 + 双引擎不独立 + 缺末句断言
        a = c["asr_segment_silence"]
        a["required_triple"] = ["declared_duration", "transcribed_coverage"]
        a["dual_engine_alignment"] = {"required": True, "independence_required": False}
        a["sentence_boundary_assertion"] = {"must": ["first_sentence_complete"],
                                           "violation_verdict": "FAIL"}

    def m27(c):  # 降级态只写命名层 + 账本缺失不硬停 + 允许按命名反推
        d = c["degrade_double_write"]
        d["layers"] = ["naming_layer"]
        d["ledger_is_authoritative"] = False
        d["ledger_missing_verdict"] = "WARN"
        d["naming_inference_forbidden"] = False
    def m28(c):  # 版本交叠按后签发者优先自动消歧
        v = c["version_overlap_ambiguous"]
        v["verdict_when_overlap"] = "LATEST_WINS"
        v["auto_resolution_forbidden"] = ["timestamp_latest_wins"]
        v["human_required"] = False
        v["must_carry"] = ["overlap_window"]
    def m29(c):  # 已加载版本改由签发方自报 + 无 load_at
        a = c["loaded_version_attestation"]
        a["attestor"] = "issuer_side"
        a["load_at_required"] = False
        a["self_report_excluded"] = False
        a["fallback_to_self_report_forbidden"] = False
        a["missing_fingerprint_verdict"] = "LOADED_AS_REPORTED"
    def m30(c):  # 摘要不一致并入行集分歧 + 自定义行入账
        i = c["impl_suspect_branch"]
        i["branches"] = ["CANONICALIZER_VERSION_MISMATCH", "ROW_SET_DIVERGED"]
        i["merge_into_row_set_verdict"] = "ALLOW"
        i["fallback_verdict"] = "ROW_SET_DIVERGED"
        i["countersign_required"] = False
        i["self_signed_excluded"] = False

    def m31(c):  # 跨镜头：顺序比对 + 单一容差 + 回滚前不检快照
        x = c["cross_shot_anchor_consistency"]
        x["reference_mode"] = "sequential"
        x["sequential_comparison_forbidden"] = False
        x["feature_classes"]["tolerance_policy"] = "single"
        x["feature_classes"]["merged_tolerance_verdict"] = "ALLOW"
        x["pre_rollback_snapshot_check"]["missing_verdict"] = "WARN"
    def m32(c):  # 阈值对齐判过 + 同周期重读
        x = c["truncation_threshold_indeterminate"]
        x["threshold_alignment"]["verdict"] = "PASS"
        x["threshold_alignment"]["may_pass"] = True
        x["second_vote"]["mode"] = "same_cycle_reread"
        x["second_vote"]["fault_domain_isolation_required"] = False
    def m33(c):  # 来源按消息量计数 + 同源异内容并入重复 + 无负例
        x = c["producer_set_rank_conflict"]
        x["counting"]["unit"] = "message_volume"
        x["classification"]["same_source_diff_content"] = "DUPLICATE"
        x["classification"]["merge_into_duplicate_verdict"] = "ALLOW"
        x["negative_testing"]["must_fail_cases_required"] = False
    def m34(c):  # 回执哈希声称期望值 + 不可复算
        x = c["evaluator_computed_digest"]
        x["digest_input"] = "claimed_expected_value"
        x["wrong_input_verdict"] = "ALLOW"
        x["reproducible_without_trust"] = False
        x["receipt_fields"] = ["digest_alg"]
    def m35(c):  # 缺第五态 + 同源自证 + 墙钟时间戳
        x = c["unattested_state"]
        x["states"] = ["PASS", "FAIL", "UNKNOWN", "PENDING"]
        x["binary_collapse_verdict"] = "ALLOW"
        x["evidence_independence"]["shared_source_verdict"] = "ALLOW"
        x["timestamp"]["mode"] = "wall_clock_assertion"
    def m36(c):  # 参数哈希即等价 + 缺展开前摘要 + 三元组缺 as_of
        x = c["semantic_window_default_drift"]
        x["snapshot_insufficiency"]["param_hash_unchanged_is_sufficient"] = True
        x["content_addressable"]["pre_expanded_defaults_required"] = False
        x["exhaustiveness_binding_triple"] = ["snapshot_address", "rule_version"]
        x["stale_validation_inheritance_verdict"] = "ALLOW"
    def m37(c):  # 禁用项未登记新增 + 规则集被删项 + 存量欠账清单被清零
        x = c["hyperframes_design_bans"]
        x["rules"] = [r for r in x["rules"] if r["id"] != "tracking_too_tight"]
        for scope in ("composition", "templates"):
            for rid in ("gradient_text", "glass_blur_decoration", "side_stripe_border", "zero_offset_glow"):
                x["legacy_inventory"][scope][rid] = 0
        x["scan_scope"]["templates"]["min_files"] = 1
    def m38(c):  # 字号层级塌陷 + 字距过紧 + 深底直接套用浅底数值
        x = c["hyperframes_type_rhythm_floor"]
        for r, px in zip(x["role_scale"], (40, 38, 36, 34, 32)):
            r["min_px"] = px
        x["role_scale"][2]["tracking_em"] = -0.06
        x["dark_surface_compensation"]["direct_copy_verdict"] = "ALLOW"
    def m39(c):  # 一镜多署名 + 弹跳缓动 + 时长档重叠 + 动布局属性 + 无 reduced-motion
        x = c["hyperframes_motion_authorship"]
        x["focal_moment"]["max_per_shot"] = 3
        x["easing"]["banned_families"] = ["elastic"]
        x["duration_tiers"]["state"] = [120, 300]
        x["animatable_properties"]["allowed"] = ["transform", "opacity", "width"]
        x["reduced_motion_path"]["required"] = False
    def m40(c):  # 对比地板下调 + 装饰渐变放行 + 深度手段收窄
        x = c["hyperframes_color_depth_roles"]
        x["contrast"]["body_min_ratio"] = 3.0
        x["color_space"]["preferred"] = "hex"
        x["depth"]["forbidden"] = ["hard_offset_shadow"]
        x["gradient_policy"]["decorative_gradient_verdict"] = "ALLOW"

    def m41(c):  # absent 折叠为取值 + 跨态直接比数值 + unknown 静默升基准
        x = c["param_provenance_incomparable"]
        x["provenance_states"] = ["declared", "defaulted"]
        x["absent_is_value"] = True
        x["cross_state_verdict"] = "COMPARABLE"
        x["verdict_rule"]["unknown_silent_rebaseline"] = "ALLOW"
    def m42(c):  # 归一动作不落账 + 表示四态互归 + 随键版本不足三件
        x = c["normalization_act_ledger"]
        x["normalization_actions"][0]["ledger_entry"] = ""
        x["normalization_actions"][1]["ledger_key_versions"] = ["contract_version"]
        x["alignment_ledger_required"] = False
        x["representation_states"] = ["null", "missing"]
        x["merge_representation_verdict"] = "ALLOW"
    def m43(c):  # 快照不带签发方 + 用当前读数回溯 + 留存期不同源
        x = c["snapshot_lifetime_alignment"]
        x["snapshot_issuer_required"] = False
        x["self_signed_verdict"] = "EVIDENCE"
        x["as_of_only"] = False
        x["current_read_forbidden"] = False
        x["lifetime_source"] = "independent_of_recycle_precondition"
        x["retention_mismatch_verdict"] = "ALLOW"

    def m44(c):  # 锚点落链内 + 清单不与产物同批落盘 + 链内自证当证据 + 段混合套转义
        x = c["verify_anchor_outside_chain"]
        x["anchor_side_requirement"] = "same_side_of_checked_data"
        x["same_side_verdict"] = "PASS"
        x["manifest_frozen_at_release"] = False
        x["manifest_persisted_with_artifact"] = False
        x["recovery_verdict_mode"] = "anchor_self_check"
        x["self_attestation_verdict"] = "EVIDENCE"
        x["segment_merge_verdict"] = "ALLOW"
    def m45(c):  # 期望集当常量 + 变更不入账 + 路径不进签名域
        x = c["expectation_set_signing_event"]
        x["expectation_set_is_constant"] = True
        x["change_is_versioned_signing_event"] = False
        x["change_ledger_required"] = False
        x["change_ledger_fields"] = ["expectation_set_version"]
        x["silent_change_verdict"] = "ALLOW"
        x["data_path_in_signature_domain"] = False
        x["path_freeze_binding"] = ["path"]
        x["path_drift_verdict"] = "ALLOW"

    return [
        ("neg_pending_merged_columns", m1, "pending_ledger"),
        ("neg_cache_missing_dim_overwritable", m2, "cache_key_grid"),
        ("neg_tiers_missing_class_marker_reversible", m3, "stop_degrade_tiers"),
        ("neg_zero_audio_warn_unbound_assertion", m4, "zero_semantics"),
        ("neg_drift_cross_version_sum", m5, "drift_fieldset"),
        ("neg_manifest_missing_column", m6, "manifest_columns"),
        ("neg_registry_gap_bad_action", m7, "field_registry"),
        ("neg_pending_issuer_bool_missing", m8, "pending_ledger"),
        ("neg_silent_rewrite_degraded", m9, "silent_rewrite"),
        ("neg_criteria_missing_effective_start", m10, "criteria_identity"),
        ("neg_zero_unspecified_merged_with_default", m11, "zero_declared_vs_default"),
        ("neg_pending_age_stock_base", m12, "pending_age_distribution"),
        ("neg_overturn_denominator_unreviewed", m13, "overturn_denominator"),
        ("neg_dependency_two_of_three_not_hardstop", m14, "dependency_version_triple"),
        ("neg_timebase_missing_rounding_moment", m15, "timebase_triple"),
        ("neg_pagination_third_state_folded", m16, "pagination_completeness"),
        ("neg_gate_skip_responder_side", m17, "gate_three_numbers"),
        ("neg_degrade_chain_self_report", m18, "degrade_product_side"),
        ("neg_failure_bucket_missing_stage", m19, "failure_domain_buckets"),
        ("neg_shared_fault_domain_examples_short", m20, "shared_fault_domain"),
        ("neg_portable_evidence_missing_fingerprint", m21, "portable_evidence"),
        ("neg_defect_coverage_class_missing", m22, "defect_coverage"),
        ("neg_repair_matrix_empty_row", m23, "repair_matrix"),
        ("neg_restoration_order_inverted_undeclared", m24, "restoration_chain_order"),
        ("neg_tile_seam_assertion_missing_oversize_warn", m25, "tile_seam_integrity"),
        ("neg_asr_triple_missing_engines_not_independent", m26, "asr_segment_silence"),
        ("neg_degrade_single_layer_no_hardstop", m27, "degrade_double_write"),
        ("neg_version_overlap_latest_wins", m28, "version_overlap_ambiguous"),
        ("neg_loaded_version_self_reported", m29, "loaded_version_attestation"),
        ("neg_impl_suspect_merged_into_row_set", m30, "impl_suspect_branch"),
        ("neg_anchor_sequential_merged_tolerance", m31, "cross_shot_anchor_consistency"),
        ("neg_threshold_pass_same_cycle_reread", m32, "truncation_threshold_indeterminate"),
        ("neg_producer_volume_count_merge_dup", m33, "producer_set_rank_conflict"),
        ("neg_receipt_hash_claimed_expected", m34, "evaluator_computed_digest"),
        ("neg_unattested_collapsed_self_witness", m35, "unattested_state"),
        ("neg_semantic_window_param_hash_only", m36, "semantic_window_default_drift"),
        ("neg_hyperframes_untracked_ban_and_rule_drop", m37, "hyperframes_design_bans"),
        ("neg_hyperframes_type_scale_collapse", m38, "hyperframes_type_rhythm_floor"),
        ("neg_hyperframes_motion_multi_focal_bounce", m39, "hyperframes_motion_authorship"),
        ("neg_hyperframes_contrast_below_floor", m40, "hyperframes_color_depth_roles"),
        ("neg_param_provenance_folded_comparable", m41, "param_provenance_incomparable"),
        ("neg_normalization_act_unledgered", m42, "normalization_act_ledger"),
        ("neg_snapshot_no_issuer_stale_read", m43, "snapshot_lifetime_alignment"),
        ("neg_anchor_same_side_manifest_unpersisted", m44, "verify_anchor_outside_chain"),
        ("neg_expectation_set_constant_unledgered", m45, "expectation_set_signing_event"),
    ]


def _neg_expected_check(name):
    table = {
        "neg_pending_merged_columns": "A-pending-ledger",
        "neg_cache_missing_dim_overwritable": "B-cache-key-grid",
        "neg_tiers_missing_class_marker_reversible": "C-stop-degrade-tiers",
        "neg_zero_audio_warn_unbound_assertion": "D-zero-semantics",
        "neg_drift_cross_version_sum": "E-drift-fieldset",
        "neg_manifest_missing_column": "F-manifest-receipt",
        "neg_registry_gap_bad_action": "G-field-registry",
        "neg_pending_issuer_bool_missing": "A-pending-ledger",
        "neg_silent_rewrite_degraded": "I-silent-rewrite",
        "neg_criteria_missing_effective_start": "J-criteria-identity",
        "neg_zero_unspecified_merged_with_default": "K-declared-vs-default",
        "neg_pending_age_stock_base": "L-pending-age",
        "neg_overturn_denominator_unreviewed": "M-overturn-denominator",
        "neg_dependency_two_of_three_not_hardstop": "N-dependency-triple",
        "neg_timebase_missing_rounding_moment": "O-timebase-triple",
        "neg_pagination_third_state_folded": "P-pagination",
        "neg_gate_skip_responder_side": "Q-gate-three-numbers",
        "neg_degrade_chain_self_report": "R-degrade-product-side",
        "neg_failure_bucket_missing_stage": "S-failure-domain",
        "neg_shared_fault_domain_examples_short": "T-shared-fault-domain",
        "neg_portable_evidence_missing_fingerprint": "U-portable-evidence",
        "neg_defect_coverage_class_missing": "V-defect-coverage",
        "neg_repair_matrix_empty_row": "W-repair-matrix",
        "neg_restoration_order_inverted_undeclared": "X-restoration-chain-order",
        "neg_tile_seam_assertion_missing_oversize_warn": "Y-tile-seam-integrity",
        "neg_asr_triple_missing_engines_not_independent": "Z-asr-segment-silence",
        "neg_degrade_single_layer_no_hardstop": "AA-degrade-double-write",
        "neg_version_overlap_latest_wins": "AB-version-overlap-ambiguous",
        "neg_loaded_version_self_reported": "AC-loaded-version-attestation",
        "neg_impl_suspect_merged_into_row_set": "AD-impl-suspect-branch",
        "neg_anchor_sequential_merged_tolerance": "AE-cross-shot-anchor-consistency",
        "neg_threshold_pass_same_cycle_reread": "AF-truncation-threshold-indeterminate",
        "neg_producer_volume_count_merge_dup": "AG-producer-set-rank-conflict",
        "neg_receipt_hash_claimed_expected": "AH-evaluator-computed-digest",
        "neg_unattested_collapsed_self_witness": "AI-unattested-state",
        "neg_semantic_window_param_hash_only": "AJ-semantic-window-default-drift",
        "neg_hyperframes_untracked_ban_and_rule_drop": "AK-hyperframes-design-bans",
        "neg_hyperframes_type_scale_collapse": "AL-hyperframes-type-rhythm-floor",
        "neg_hyperframes_motion_multi_focal_bounce": "AM-hyperframes-motion-authorship",
        "neg_hyperframes_contrast_below_floor": "AN-hyperframes-color-depth-roles",
        "neg_param_provenance_folded_comparable": "AO-param-provenance-incomparable",
        "neg_normalization_act_unledgered": "AP-normalization-act-ledger",
        "neg_snapshot_no_issuer_stale_read": "AQ-snapshot-lifetime-alignment",
        "neg_anchor_same_side_manifest_unpersisted": "AS-verify-anchor-outside-chain",
        "neg_expectation_set_constant_unledgered": "AT-expectation-set-signing-event",
    }
    return table.get(name)


def _check_one(canons, ctx, check_id):
    for cid, _label, fn in CHECKS:
        if cid == check_id:
            return fn(canons, ctx)
    raise RuntimeError(f"未知检查项 {check_id}")


def cmd_selftest(args):
    base = read_json(args.canons)
    if not base:
        print("[error] 口径真源读不到，selftest 无法进行", file=sys.stderr)
        return 1
    ctx = build_ctx(args.root, base)
    print("=" * 100)
    print("canon_guard 内置自测（正例 1 + 负例 26，成对）")
    print("=" * 100)
    results = []

    pos_res, pos_fail = run_checks(base, ctx, verbose=False)
    pos_pass = pos_fail == 0 and all(r["pass"] for r in pos_res)
    print(f"  [{'PASS' if pos_pass else 'FAIL'}] 正例：口径真源自身自洽")
    results.append(pos_pass)

    for name, mut, _keyword in _neg_mutators():
        doc = copy.deepcopy(base)
        mut(doc)
        expect_id = _neg_expected_check(name)
        _ok, _detail, problems = _check_one(doc, ctx, expect_id)
        hit = bool(problems)
        print(f"  [{'PASS' if hit else 'FAIL'}] 负例 {name} → {expect_id} 必须判红"
              + (f"\n          {problems[0]}" if hit else "\n          未被判红（检测器失效）"))
        results.append(hit)

    # 负例必须只打自己的靶：其余检查项不得被误伤
    for name, mut, _kw in _neg_mutators():
        doc = copy.deepcopy(base)
        mut(doc)
        expect_id = _neg_expected_check(name)
        others, _n = run_checks(doc, ctx, verbose=False)
        collateral = [r["id"] for r in others if not r["pass"] and r["id"] != expect_id]
        clean = not collateral
        print(f"  [{'PASS' if clean else 'WARN'}] 负例 {name} 无外溢（仅目标检查项判红）"
              + ("" if clean else f"\n          外溢：{collateral}"))
        results.append(clean)

    # overlay 负例：无音轨 manifest 必须补判 FAIL
    noaudio = {"derived": {"audio_sample_rate_channels": {"sample_rate_hz": None, "channels": None}}}
    tmp = os.path.join(args.root, "tests", "fixtures", "canons", "_tmp_noaudio.json")
    os.makedirs(os.path.dirname(tmp), exist_ok=True)
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(noaudio, f, ensure_ascii=False)
    items = overlay_manifest(tmp)
    ov_ok = bool(items) and items[0]["overlay_verdict"] == "FAIL"
    print(f"  [{'PASS' if ov_ok else 'FAIL'}] overlay：无音轨 manifest 补判 FAIL（未观测 ≠ 0）")
    results.append(ov_ok)
    withaudio = {"derived": {"audio_sample_rate_channels": {"sample_rate_hz": 48000, "channels": 2}}}
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(withaudio, f, ensure_ascii=False)
    items2 = overlay_manifest(tmp)
    ov2_ok = bool(items2) and items2[0]["overlay_verdict"] == "OK"
    print(f"  [{'PASS' if ov2_ok else 'FAIL'}] overlay：有音轨 manifest 判 OK（正控，不得永远报红）")
    results.append(ov2_ok)
    os.remove(tmp)

    n_fail = sum(1 for r in results if not r)
    print("-" * 100)
    print(f"结论：共 {len(results)} 项，PASS {len(results) - n_fail} / FAIL {n_fail}")
    print("=" * 100)
    return 2 if n_fail else 0


def cmd_make_fixtures(args):
    base = read_json(args.canons)
    if not base:
        print("[error] 口径真源读不到", file=sys.stderr)
        return 1
    d = args.fixture_dir or FIXTURE_DIR_DEFAULT
    os.makedirs(d, exist_ok=True)
    written = []

    def dump(name, doc):
        path = os.path.join(d, name)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(doc, f, ensure_ascii=False, indent=2)
            f.write("\n")
        written.append(path)

    dump("positive.json", base)
    for name, mut, _kw in _neg_mutators():
        doc = copy.deepcopy(base)
        mut(doc)
        dump(name + ".json", doc)
    print("=" * 100)
    print(f"夹具已从正本派生（正例 1 + 负例 {len(_neg_mutators())}）→ {d}")
    for p in written:
        print(f"  - {os.path.relpath(p, args.root)}")
    print("=" * 100)
    return 0


def cmd_drill(args):
    d = args.fixture_dir or FIXTURE_DIR_DEFAULT
    if not os.path.isdir(d):
        print(f"[error] 夹具目录不存在，请先执行 make-fixtures：{d}", file=sys.stderr)
        return 1
    base = read_json(os.path.join(d, "positive.json"))
    if not base:
        print("[error] positive.json 缺失", file=sys.stderr)
        return 1
    ctx = build_ctx(args.root, base)
    print("=" * 100)
    print("canon_guard 落地负控（drill）：负例必须判红，正例必须判绿")
    print("=" * 100)
    results = []

    pos_res, pos_fail = run_checks(base, ctx, verbose=False)
    pos_ok = pos_fail == 0
    print(f"  [{'PASS' if pos_ok else 'FAIL'}] 正控 positive.json：全项判绿（不得永远报红）")
    results.append(pos_ok)

    for name, _mut, _kw in _neg_mutators():
        path = os.path.join(d, name + ".json")
        doc = read_json(path)
        if doc is None:
            print(f"  [FAIL] 负例缺夹具：{name}.json")
            results.append(False)
            continue
        expect_id = _neg_expected_check(name)
        _ok, _detail, problems = _check_one(doc, ctx, expect_id)
        hit = bool(problems)
        print(f"  [{'PASS' if hit else 'FAIL'}] {name} → {expect_id} 判红"
              + (f"（{problems[0][:60]}）" if hit else "（未被判红）"))
        results.append(hit)

    n_fail = sum(1 for r in results if not r)
    print("-" * 100)
    print(f"结论：共 {len(results)} 项，PASS {len(results) - n_fail} / FAIL {n_fail}")
    print("=" * 100)
    return 2 if n_fail else 0


def cmd_signature(args):
    doc = read_json(args.canons)
    if not doc:
        print("[error] 口径真源读不到", file=sys.stderr)
        return 1
    print(f"canons_version    : {doc.get('canons_version')}")
    print(f"canons_signature  : {signature_of(doc)}")
    for cid, label, _fn in CHECKS:
        print(f"  - {cid:<24}{label}")
    return 0


def main(argv=None):
    p = argparse.ArgumentParser(description="工程口径吸纳层校验器")
    p.add_argument("--root", default=ROOT_DEFAULT)
    p.add_argument("--canons", default=CANONS_DEFAULT)
    p.add_argument("--fixture-dir", default=None)
    sub = p.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("check", help="静态自洽 + 存量对接（可选 overlay 补判）")
    c.add_argument("--manifest", default=None, help="对真实 manifest 做零值语义补判")
    c.add_argument("--out", default=None)
    c.set_defaults(func=cmd_check)

    s = sub.add_parser("selftest", help="内置正/负例成对自测")
    s.set_defaults(func=cmd_selftest)

    m = sub.add_parser("make-fixtures", help="从正本派生正/负例夹具")
    m.set_defaults(func=cmd_make_fixtures)

    d = sub.add_parser("drill", help="对落盘夹具跑负控")
    d.set_defaults(func=cmd_drill)

    g = sub.add_parser("signature", help="打印口径签名")
    g.set_defaults(func=cmd_signature)

    args = p.parse_args(argv)
    try:
        return args.func(args)
    except RuntimeError as e:
        print(f"[error] {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
