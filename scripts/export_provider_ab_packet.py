#!/usr/bin/env python3
"""Export a saved dashboard analysis run as a provider A/B packet.

This script is read-only against the analysis database. It does not call any
provider API and writes only the requested export files.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_ANALYSIS_DB = BASE_DIR / "data" / "dashboard_analysis.sqlite3"
DEFAULT_EXPORT_ROOT = BASE_DIR / "exports" / "provider_ab"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export a provider A/B evidence packet.")
    parser.add_argument("run_id", help="analysis_runs.id to export")
    parser.add_argument("--db", type=Path, default=DEFAULT_ANALYSIS_DB, help="analysis sqlite path")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="output directory; defaults to exports/provider_ab/<run_id>",
    )
    return parser.parse_args()


def open_readonly_db(path: Path) -> sqlite3.Connection:
    db_path = path.expanduser().resolve()
    if not db_path.exists():
        raise FileNotFoundError(f"analysis database not found: {db_path}")
    uri = f"file:{db_path}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {key: row[key] for key in row.keys()}


def parse_json_list(value: object) -> list[dict[str, Any]]:
    try:
        parsed = json.loads(str(value or "[]"))
    except json.JSONDecodeError:
        return []
    if not isinstance(parsed, list):
        return []
    return [item for item in parsed if isinstance(item, dict)]


def load_run(conn: sqlite3.Connection, run_id: str) -> dict[str, Any]:
    row = conn.execute("SELECT * FROM analysis_runs WHERE id = ?", (run_id,)).fetchone()
    if not row:
        raise ValueError(f"analysis run not found: {run_id}")
    run = row_to_dict(row)
    packet = parse_json_list(run.get("evidence_packet_json"))
    evidence_rows = conn.execute(
        """
        SELECT news_id, rank, relevance_score, matched_keywords, selected,
               llm_confidence, llm_impact_path, llm_direction
        FROM analysis_evidence
        WHERE run_id = ?
        ORDER BY rank ASC
        """,
        (run_id,),
    ).fetchall()
    selected_by_id = {str(row["news_id"]): bool(row["selected"]) for row in evidence_rows}
    for item in packet:
        news_id = str(item.get("news_id") or item.get("id") or "")
        if news_id in selected_by_id:
            item["selected"] = selected_by_id[news_id]
    run["evidence_packet"] = packet
    run["evidence_rows"] = [row_to_dict(row) for row in evidence_rows]
    return run


def export_metadata(run: dict[str, Any], *, db_path: Path) -> dict[str, Any]:
    packet = run["evidence_packet"]
    selected = [item for item in packet if item.get("selected", True)]
    return {
        "run_id": run["id"],
        "asset": run["asset"],
        "question": run["question"],
        "window_start": run["window_start"],
        "window_end": run["window_end"],
        "prompt_version": run["prompt_version"],
        "model_label": run["model_label"],
        "status": run["status"],
        "evidence_count": len(packet),
        "selected_count": len(selected),
        "market_context_state": infer_market_context_state(str(run.get("manual_prompt") or "")),
        "analysis_db": str(db_path.expanduser().resolve()),
    }


def infer_market_context_state(prompt: str) -> str:
    if "【结构化行情上下文】" not in prompt:
        return "not_included"
    if "行情数据不可用" in prompt:
        return "included_unavailable"
    return "included"


def render_scorecard(metadata: dict[str, Any]) -> str:
    providers = [
        ("Gemini", "API provider"),
        ("ChatGPT Plus", "manual paste"),
        ("GLM Flash", "OpenAI-compatible provider or manual paste"),
    ]
    rows = "\n".join(
        f"| {label} | {mode} |  |  |  |  |  |  |  |  |"
        for label, mode in providers
    )
    return f"""# Provider A/B Scorecard

## Fixed Inputs

| Field | Value |
| --- | --- |
| run_id | `{metadata["run_id"]}` |
| asset | `{metadata["asset"]}` |
| window | `{metadata["window_start"]}` - `{metadata["window_end"]}` |
| prompt_version | `{metadata["prompt_version"]}` |
| evidence | `{metadata["selected_count"]}` selected / `{metadata["evidence_count"]}` shown |
| market_context_state | `{metadata["market_context_state"]}` |

## Provider Results

| Provider | Mode | Key catalysts hit? | Duplicate news_id? | Judgement | Missing evidence reasonable? | JSON parse stable? | Prompt/runtime notes | Winner notes | Output file |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
{rows}

## Checks

- Use `prompt.md` unchanged for every provider.
- Use `evidence_packet.json` as the fixed evidence reference.
- Do not add or remove evidence between provider runs.
- Record repeated catalyst `news_id` values explicitly.
- Save raw provider output next to this file before judging quality.
"""


def write_export(run: dict[str, Any], output_dir: Path, *, db_path: Path) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    metadata = export_metadata(run, db_path=db_path)
    files = {
        "prompt": output_dir / "prompt.md",
        "evidence_packet": output_dir / "evidence_packet.json",
        "scorecard": output_dir / "ab_scorecard.md",
        "metadata": output_dir / "metadata.json",
    }
    files["prompt"].write_text(str(run.get("manual_prompt") or ""), encoding="utf-8")
    files["evidence_packet"].write_text(
        json.dumps(run["evidence_packet"], ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    files["scorecard"].write_text(render_scorecard(metadata), encoding="utf-8")
    files["metadata"].write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return files


def export_run_packet(run_id: str, *, db_path: Path, output_dir: Path) -> dict[str, Path]:
    with open_readonly_db(db_path) as conn:
        run = load_run(conn, run_id)
    return write_export(run, output_dir, db_path=db_path)


def main() -> int:
    args = parse_args()
    output_dir = args.output_dir or DEFAULT_EXPORT_ROOT / args.run_id
    try:
        files = export_run_packet(args.run_id, db_path=args.db, output_dir=output_dir)
    except (FileNotFoundError, ValueError, sqlite3.Error) as exc:
        print(f"export failed: {exc}", file=sys.stderr)
        return 1
    print(f"Exported provider A/B packet to {output_dir}")
    for label, path in files.items():
        print(f"- {label}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
