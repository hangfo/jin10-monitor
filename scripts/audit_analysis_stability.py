#!/usr/bin/env python3
"""Offline, read-only audit of saved dashboard analysis stability."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from dashboard.analysis_db import DEFAULT_ANALYSIS_DB, list_completed_runs_with_packets
from dashboard.analysis_quality import assess_packet_sensitivity, assess_run_quality, summarize_saved_run_stability


def build_report(db_path: Path, limit: int) -> dict[str, object]:
    runs = list_completed_runs_with_packets(limit=limit, path=db_path)
    cohort_summary = summarize_saved_run_stability(runs)
    return {
        "boundary": {
            "database": str(db_path.resolve()),
            "mode": "sqlite_readonly",
            "provider_called": False,
            "business_db_written": False,
        },
        "completed_run_count": len(runs),
        **cohort_summary,
        "runs": [
            {
                "run_id": str(run.get("id") or ""),
                "provider_name": str(run.get("provider_name") or ""),
                "quality": assess_run_quality(run),
                "sensitivity": assess_packet_sensitivity(run),
            }
            for run in runs
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DEFAULT_ANALYSIS_DB)
    parser.add_argument("--limit", type=int, default=50)
    args = parser.parse_args()
    print(json.dumps(build_report(args.db, max(1, min(args.limit, 200))), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
