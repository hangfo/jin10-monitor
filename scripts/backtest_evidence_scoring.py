#!/usr/bin/env python3
"""Backtest dashboard evidence scoring against saved analysis runs.

This script is read-only. It compares saved v1 relevance scores with the
current evidence scorer by using LLM catalyst confidence as weak labels.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path
from statistics import mean
from typing import Any

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from jin10_monitor import parse_cursor_datetime

from dashboard.evidence import apply_diversity_penalty, resolve_asset_keywords, score_row


DEFAULT_ANALYSIS_DB = BASE_DIR / "data" / "dashboard_analysis.sqlite3"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Backtest dashboard evidence scoring.")
    parser.add_argument("--db", type=Path, default=DEFAULT_ANALYSIS_DB, help="analysis sqlite path")
    parser.add_argument("--top-k", type=int, default=10, help="top rows to evaluate")
    parser.add_argument("--threshold", type=float, default=0.7, help="LLM confidence positive threshold")
    return parser.parse_args()


def open_db(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def parse_packet(value: object) -> list[dict[str, Any]]:
    try:
        data = json.loads(str(value or "[]"))
    except json.JSONDecodeError:
        return []
    return [item for item in data if isinstance(item, dict)] if isinstance(data, list) else []


def confidence_by_news(conn: sqlite3.Connection, run_id: str) -> dict[str, float]:
    rows = conn.execute(
        "SELECT news_id, llm_confidence FROM analysis_evidence WHERE run_id = ?",
        (run_id,),
    ).fetchall()
    return {str(row["news_id"]): float(row["llm_confidence"] or 0) for row in rows}


def evaluate_ranking(
    ranked: list[dict[str, Any]],
    confidence_map: dict[str, float],
    *,
    threshold: float,
    top_k: int,
) -> dict[str, float]:
    positives = {news_id for news_id, confidence in confidence_map.items() if confidence >= threshold}
    if not positives:
        return {"eligible": 0, "precision": 0, "recall": 0, "hits": 0, "positive_count": 0}
    top = ranked[:top_k]
    top_ids = {str(item.get("news_id") or item.get("id") or "") for item in top}
    hits = len(top_ids & positives)
    return {
        "eligible": 1,
        "precision": hits / max(1, len(top)),
        "recall": hits / len(positives),
        "hits": hits,
        "positive_count": len(positives),
    }


def recompute_v2(run: sqlite3.Row, packet: list[dict[str, Any]]) -> list[dict[str, Any]]:
    asset = str(run["asset"] or "")
    asset_keywords = resolve_asset_keywords(asset)
    window_start = parse_cursor_datetime(str(run["window_start"] or ""))
    window_end = parse_cursor_datetime(str(run["window_end"] or ""))
    rows = []
    for item in packet:
        row = dict(item)
        row["id"] = str(item.get("news_id") or item.get("id") or "")
        rows.append(score_row(row, asset_keywords, asset=asset, window_start=window_start, window_end=window_end))
    apply_diversity_penalty(rows)
    return sorted(rows, key=lambda item: (float(item.get("relevance_score") or 0), item.get("published_at") or ""), reverse=True)


def main() -> int:
    args = parse_args()
    conn = open_db(args.db)
    runs = conn.execute(
        """
        SELECT id, asset, window_start, window_end, evidence_packet_json
        FROM analysis_runs
        WHERE status = 'done'
        ORDER BY created_at ASC
        """
    ).fetchall()
    v1_metrics = []
    v2_metrics = []
    rows_used = 0
    for run in runs:
        packet = parse_packet(run["evidence_packet_json"])
        if not packet:
            continue
        confidence_map = confidence_by_news(conn, str(run["id"]))
        v1_ranked = sorted(
            packet,
            key=lambda item: (float(item.get("relevance_score") or 0), item.get("published_at") or ""),
            reverse=True,
        )
        v2_ranked = recompute_v2(run, packet)
        v1 = evaluate_ranking(v1_ranked, confidence_map, threshold=args.threshold, top_k=args.top_k)
        v2 = evaluate_ranking(v2_ranked, confidence_map, threshold=args.threshold, top_k=args.top_k)
        if not v1["eligible"]:
            continue
        rows_used += 1
        v1_metrics.append(v1)
        v2_metrics.append(v2)
        print(
            f"{run['id']} {run['asset']} positives={int(v1['positive_count'])} "
            f"v1_hits={int(v1['hits'])} v1_recall={v1['recall']:.2f} "
            f"v2_hits={int(v2['hits'])} v2_recall={v2['recall']:.2f}"
        )
    if not rows_used:
        print("No eligible runs with positive LLM labels.")
        return 1
    print("-" * 72)
    print(f"eligible_runs={rows_used} top_k={args.top_k} threshold={args.threshold}")
    for label, metrics in [("v1", v1_metrics), ("v2", v2_metrics)]:
        print(
            f"{label}: precision={mean(item['precision'] for item in metrics):.3f} "
            f"recall={mean(item['recall'] for item in metrics):.3f} "
            f"hits={mean(item['hits'] for item in metrics):.2f}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
