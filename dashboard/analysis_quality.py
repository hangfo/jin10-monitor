"""Deterministic evidence-packet identity and comparison helpers.

These helpers are deliberately pure: they never open a database or call a
Provider.  A frozen packet fingerprint is the boundary that makes two saved
analysis runs a valid Provider A/B comparison.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def evidence_fingerprint(packet: list[dict[str, Any]]) -> str:
    """Return an order-sensitive SHA-256 identity for a frozen evidence packet."""

    return hashlib.sha256(_canonical_json(packet).encode("utf-8")).hexdigest()


def prompt_fingerprint(prompt: str) -> str:
    """Return an exact SHA-256 identity for the saved Provider prompt."""

    return hashlib.sha256(str(prompt or "").encode("utf-8")).hexdigest()


def _news_ids(packet: list[dict[str, Any]], *, selected_only: bool) -> set[str]:
    values: set[str] = set()
    for item in packet:
        if not isinstance(item, dict):
            continue
        if selected_only and not item.get("selected", True):
            continue
        news_id = str(item.get("news_id") or item.get("id") or "").strip()
        if news_id:
            values.add(news_id)
    return values


def _jaccard(first: set[str], second: set[str]) -> float:
    union = first | second
    if not union:
        return 1.0
    return len(first & second) / len(union)


def compare_analysis_runs(first: dict[str, Any], second: dict[str, Any]) -> dict[str, Any]:
    """Describe whether two runs are a controlled, frozen-input comparison."""

    first_packet = first.get("evidence_packet") or []
    second_packet = second.get("evidence_packet") or []
    first_evidence_fp = str(first.get("evidence_fingerprint") or evidence_fingerprint(first_packet))
    second_evidence_fp = str(second.get("evidence_fingerprint") or evidence_fingerprint(second_packet))
    first_prompt_fp = str(first.get("prompt_fingerprint") or prompt_fingerprint(first.get("manual_prompt") or ""))
    second_prompt_fp = str(second.get("prompt_fingerprint") or prompt_fingerprint(second.get("manual_prompt") or ""))

    first_candidates = _news_ids(first_packet, selected_only=False)
    second_candidates = _news_ids(second_packet, selected_only=False)
    first_selected = _news_ids(first_packet, selected_only=True)
    second_selected = _news_ids(second_packet, selected_only=True)
    same_evidence = first_evidence_fp == second_evidence_fp
    same_prompt = first_prompt_fp == second_prompt_fp
    return {
        "valid_ab": same_evidence and same_prompt,
        "same_evidence": same_evidence,
        "same_prompt": same_prompt,
        "candidate_jaccard": _jaccard(first_candidates, second_candidates),
        "selected_jaccard": _jaccard(first_selected, second_selected),
        "first_evidence_fingerprint": first_evidence_fp,
        "second_evidence_fingerprint": second_evidence_fp,
        "first_prompt_fingerprint": first_prompt_fp,
        "second_prompt_fingerprint": second_prompt_fp,
    }


def _market_move_pct(prompt: str) -> float | None:
    match = re.search(r"涨跌：[^\n]*?\(([+-]?\d+(?:\.\d+)?)%\)", str(prompt or ""))
    if not match:
        return None
    try:
        return float(match.group(1))
    except ValueError:
        return None


def _direction_profile(catalysts: list[dict[str, Any]]) -> dict[str, int]:
    profile = {"bullish": 0, "bearish": 0, "mixed": 0}
    for catalyst in catalysts:
        direction = str(catalyst.get("direction") or "")
        if direction in profile:
            profile[direction] += 1
    return profile


def assess_run_quality(run: dict[str, Any]) -> dict[str, Any]:
    """Build a deterministic evidence-quality grade, not a probability."""

    packet = [item for item in (run.get("evidence_packet") or []) if isinstance(item, dict)]
    selected = [item for item in packet if item.get("selected", True)]
    selected_by_id = {
        str(item.get("news_id") or item.get("id") or ""): item
        for item in selected
        if str(item.get("news_id") or item.get("id") or "")
    }
    parsed = run.get("answer_parsed") or {}
    catalysts = [item for item in (parsed.get("catalysts") or []) if isinstance(item, dict)]
    catalyst_ids = [str(item.get("news_id") or "") for item in catalysts if item.get("news_id")]
    valid_ids = [news_id for news_id in catalyst_ids if news_id in selected_by_id]
    unique_valid_ids = set(valid_ids)

    coverage_score = min(25.0, len(selected) / 4 * 25.0)
    avg_relevance = (
        sum(max(0.0, min(1.0, float(item.get("relevance_score") or 0))) for item in selected) / len(selected)
        if selected else 0.0
    )
    relevance_score = avg_relevance * 25.0
    if catalysts:
        citation_score = len(valid_ids) / len(catalysts) * 20.0
    else:
        citation_score = 10.0 if str(parsed.get("judgement") or "") == "unclear" else 0.0

    profile = _direction_profile(catalysts)
    directional_count = profile["bullish"] + profile["bearish"]
    dominant_direction = ""
    consistency_score = 5.0
    if directional_count:
        dominant_direction = "bullish" if profile["bullish"] >= profile["bearish"] else "bearish"
        consistency_score = max(profile["bullish"], profile["bearish"]) / directional_count * 15.0

    move_pct = _market_move_pct(run.get("manual_prompt") or "")
    market_direction = ""
    alignment = "unavailable"
    alignment_score = 5.0
    if move_pct is not None:
        if move_pct > 0.1:
            market_direction = "bullish"
        elif move_pct < -0.1:
            market_direction = "bearish"
        else:
            market_direction = "flat"
        if market_direction == "flat":
            alignment = "neutral"
            alignment_score = 8.0
        elif dominant_direction:
            alignment = "aligned" if dominant_direction == market_direction else "conflict"
            alignment_score = 15.0 if alignment == "aligned" else 0.0

    duplicate_penalty = max(0, len(valid_ids) - len(unique_valid_ids)) * 5.0
    score = max(0.0, min(100.0, coverage_score + relevance_score + citation_score + consistency_score + alignment_score - duplicate_penalty))
    judgement = str(parsed.get("judgement") or "")
    if alignment == "conflict" or (profile["bullish"] and profile["bearish"]) or judgement == "unclear":
        score = min(score, 64.0)
    if len(selected) < 2 or (catalysts and len(unique_valid_ids) / len(catalysts) < 0.5):
        score = min(score, 49.0)
    grade = "A" if score >= 80 else "B" if score >= 65 else "C" if score >= 50 else "D"
    label = {"A": "证据扎实", "B": "可供决策", "C": "仅作观察", "D": "证据不足"}[grade]

    reasons: list[str] = []
    if len(selected) < 4:
        reasons.append(f"核心证据仅 {len(selected)} 条")
    if catalysts and len(valid_ids) < len(catalysts):
        reasons.append(f"有 {len(catalysts) - len(valid_ids)} 条催化未引用已选证据")
    if duplicate_penalty:
        reasons.append("存在重复引用同一消息")
    if alignment == "conflict":
        reasons.append("催化主方向与窗口价格方向冲突")
    if profile["bullish"] and profile["bearish"]:
        reasons.append("催化方向内部冲突")
    if move_pct is None:
        reasons.append("缺少可解析的结构化行情涨跌")
    if not reasons:
        reasons.append("核心证据、引用和行情方向相互一致")

    primary = "尚无被已选证据支持的主假设"
    ranked_valid = sorted(
        (item for item in catalysts if str(item.get("news_id") or "") in selected_by_id),
        key=lambda item: float(selected_by_id[str(item.get("news_id"))].get("relevance_score") or 0),
        reverse=True,
    )
    if ranked_valid:
        lead = ranked_valid[0]
        primary = str(lead.get("impact_path") or lead.get("headline") or "").strip() or primary

    counter_items = [
        item for item in ranked_valid
        if str(item.get("direction") or "") == "mixed"
        or (dominant_direction and str(item.get("direction") or "") not in {"", dominant_direction})
    ]
    counter = (
        str((counter_items[0].get("impact_path") or counter_items[0].get("headline") or "")).strip()
        if counter_items else "已选证据中未识别到明确反向催化"
    )
    missing = [str(item).strip() for item in (parsed.get("missing_evidence") or []) if str(item).strip()]
    action = (
        "证据尚不足以单独支持交易；等待缺口补齐或价格确认。"
        if grade in {"C", "D"} or alignment == "conflict" or judgement == "unclear"
        else "可进入价格、成交量和风控确认，但不应仅凭新闻归因建仓。"
    )
    return {
        "score": round(score),
        "grade": grade,
        "label": label,
        "reasons": reasons,
        "selected_count": len(selected),
        "valid_citation_count": len(valid_ids),
        "catalyst_count": len(catalysts),
        "direction_profile": profile,
        "dominant_direction": dominant_direction,
        "market_move_pct": move_pct,
        "market_direction": market_direction,
        "alignment": alignment,
        "primary_hypothesis": primary,
        "counter_evidence": counter,
        "missing_evidence": missing,
        "decision_rule": missing[0] if missing else "等待新增独立证据或价格/成交量确认",
        "action": action,
    }


def assess_packet_sensitivity(run: dict[str, Any]) -> dict[str, Any]:
    """Stress a saved answer against deterministic packet subsets without an LLM call."""

    packet = [dict(item) for item in (run.get("evidence_packet") or []) if isinstance(item, dict)]
    originally_selected = [
        str(item.get("news_id") or item.get("id") or "")
        for item in packet if item.get("selected", True)
    ]

    def assess_with_ids(selected_ids: set[str]) -> dict[str, Any]:
        variant = dict(run)
        variant["evidence_packet"] = [
            {**item, "selected": str(item.get("news_id") or item.get("id") or "") in selected_ids}
            for item in packet
        ]
        return assess_run_quality(variant)

    top_k: list[dict[str, Any]] = []
    ranked_ids = [str(item.get("news_id") or item.get("id") or "") for item in packet]
    for size in (4, 6, 8):
        selected_ids = {news_id for news_id in ranked_ids[:size] if news_id}
        quality = assess_with_ids(selected_ids)
        top_k.append({"size": size, "score": quality["score"], "grade": quality["grade"]})

    leave_one_out: list[dict[str, Any]] = []
    original_set = {news_id for news_id in originally_selected if news_id}
    for news_id in originally_selected[:8]:
        quality = assess_with_ids(original_set - {news_id})
        leave_one_out.append({"news_id": news_id, "score": quality["score"], "grade": quality["grade"]})

    baseline = assess_run_quality(run)
    scores = [baseline["score"], *(item["score"] for item in top_k), *(item["score"] for item in leave_one_out)]
    score_range = max(scores) - min(scores) if scores else 0
    grade_changes = any(item["grade"] != baseline["grade"] for item in [*top_k, *leave_one_out])
    label = "脆弱" if score_range >= 20 or grade_changes else "稳定" if score_range < 10 else "需复核"
    return {
        "baseline_score": baseline["score"],
        "baseline_grade": baseline["grade"],
        "top_k": top_k,
        "leave_one_out": leave_one_out,
        "score_range": score_range,
        "grade_changes": grade_changes,
        "label": label,
    }


def summarize_saved_run_stability(runs: list[dict[str, Any]]) -> dict[str, Any]:
    """Summarize comparability and output spread for saved analysis cohorts."""

    cohorts: dict[tuple[str, str, str, str], list[dict[str, Any]]] = {}
    for run in runs:
        key = (
            str(run.get("asset") or ""),
            str(run.get("window_start") or ""),
            str(run.get("window_end") or ""),
            str(run.get("question") or ""),
        )
        cohorts.setdefault(key, []).append(run)

    rows: list[dict[str, Any]] = []
    for key, cohort in cohorts.items():
        if len(cohort) < 2:
            continue
        fingerprints = {
            str(run.get("evidence_fingerprint") or evidence_fingerprint(run.get("evidence_packet") or []))
            for run in cohort
        }
        prompt_fingerprints = {
            str(run.get("prompt_fingerprint") or prompt_fingerprint(run.get("manual_prompt") or ""))
            for run in cohort
        }
        confidences = [float(run.get("overall_confidence") or 0) for run in cohort]
        judgements = {str(run.get("judgement") or "") for run in cohort}
        rows.append(
            {
                "asset": key[0],
                "window_start": key[1],
                "window_end": key[2],
                "question": key[3],
                "run_count": len(cohort),
                "strictly_comparable": len(fingerprints) == 1 and len(prompt_fingerprints) == 1,
                "evidence_version_count": len(fingerprints),
                "prompt_version_count": len(prompt_fingerprints),
                "judgement_count": len(judgements),
                "confidence_range": max(confidences) - min(confidences),
                "run_ids": [str(run.get("id") or "") for run in cohort],
            }
        )
    return {
        "cohort_count": len(rows),
        "strict_cohort_count": sum(1 for row in rows if row["strictly_comparable"]),
        "cohorts": rows,
    }
