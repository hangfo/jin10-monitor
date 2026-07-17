"""Deterministic evidence-packet identity and comparison helpers.

These helpers are deliberately pure: they never open a database or call a
Provider.  A frozen packet fingerprint is the boundary that makes two saved
analysis runs a valid Provider A/B comparison.
"""

from __future__ import annotations

import hashlib
import json
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
