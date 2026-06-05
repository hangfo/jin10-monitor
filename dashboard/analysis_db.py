"""Read/write access for the dashboard analysis database.

The analysis database is intentionally separate from the monitor's business
history database. Dashboard analysis writes go to data/dashboard_analysis.sqlite3
only.
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Optional


BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_ANALYSIS_DB = BASE_DIR / "data" / "dashboard_analysis.sqlite3"
SCREENSHOT_DIR = BASE_DIR / "data" / "screenshots"


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS analysis_runs (
    id TEXT PRIMARY KEY,
    question TEXT NOT NULL,
    asset TEXT NOT NULL DEFAULT '',
    window_start TEXT NOT NULL DEFAULT '',
    window_end TEXT NOT NULL DEFAULT '',
    from_item_id TEXT NOT NULL DEFAULT '',
    screenshot_id TEXT NOT NULL DEFAULT '',
    user_context TEXT NOT NULL DEFAULT '',
    evidence_packet_json TEXT NOT NULL DEFAULT '[]',
    manual_prompt TEXT NOT NULL DEFAULT '',
    answer_text TEXT NOT NULL DEFAULT '',
    answer_json TEXT NOT NULL DEFAULT '{}',
    model_label TEXT NOT NULL DEFAULT 'manual_chatgpt_business',
    prompt_version TEXT NOT NULL DEFAULT 'v1',
    evidence_count INTEGER NOT NULL DEFAULT 0,
    selected_count INTEGER NOT NULL DEFAULT 0,
    judgement TEXT NOT NULL DEFAULT '',
    overall_confidence REAL NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'draft',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_analysis_runs_created
ON analysis_runs(created_at DESC);

CREATE INDEX IF NOT EXISTS idx_analysis_runs_asset
ON analysis_runs(asset);

CREATE INDEX IF NOT EXISTS idx_analysis_runs_status
ON analysis_runs(status);

CREATE TABLE IF NOT EXISTS analysis_evidence (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL REFERENCES analysis_runs(id) ON DELETE CASCADE,
    news_id TEXT NOT NULL,
    rank INTEGER NOT NULL DEFAULT 0,
    relevance_score REAL NOT NULL DEFAULT 0,
    matched_keywords TEXT NOT NULL DEFAULT '',
    selected INTEGER NOT NULL DEFAULT 1,
    llm_confidence REAL NOT NULL DEFAULT 0,
    llm_impact_path TEXT NOT NULL DEFAULT '',
    llm_direction TEXT NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_analysis_evidence_run_id
ON analysis_evidence(run_id);

CREATE INDEX IF NOT EXISTS idx_analysis_evidence_news_id
ON analysis_evidence(news_id);

CREATE TABLE IF NOT EXISTS screenshots (
    id TEXT PRIMARY KEY,
    file_path TEXT NOT NULL,
    original_filename TEXT NOT NULL DEFAULT '',
    user_description TEXT NOT NULL DEFAULT '',
    uploaded_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""


def analysis_db_path(path: Optional[Path] = None) -> Path:
    return (path or DEFAULT_ANALYSIS_DB).expanduser()


def open_analysis_db(path: Optional[Path] = None) -> sqlite3.Connection:
    db_path = analysis_db_path(path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_analysis_db(path: Optional[Path] = None) -> None:
    with open_analysis_db(path) as conn:
        conn.executescript(SCHEMA_SQL)
        ensure_analysis_columns(conn)
        conn.commit()


def row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {key: row[key] for key in row.keys()}


def ensure_analysis_columns(conn: sqlite3.Connection) -> None:
    columns = {row["name"] for row in conn.execute("PRAGMA table_info(analysis_runs)").fetchall()}
    if "screenshot_id" not in columns:
        conn.execute("ALTER TABLE analysis_runs ADD COLUMN screenshot_id TEXT NOT NULL DEFAULT ''")


def now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def new_run_id() -> str:
    return f"ar_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"


def new_screenshot_id() -> str:
    return f"sc_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:4]}"


def create_run(
    question: str,
    asset: str,
    window_start: str,
    window_end: str,
    evidence_packet: list[dict[str, Any]],
    *,
    from_item_id: str = "",
    screenshot_id: str = "",
    user_context: str = "",
    manual_prompt: str = "",
    model_label: str = "manual_chatgpt_business",
    prompt_version: str = "v1",
    path: Optional[Path] = None,
) -> str:
    run_id = new_run_id()
    created_at = now_text()
    selected_count = sum(1 for item in evidence_packet if item.get("selected", True))
    packet_json = json.dumps(evidence_packet, ensure_ascii=False)
    with open_analysis_db(path) as conn:
        conn.execute(
            """
            INSERT INTO analysis_runs (
                id, question, asset, window_start, window_end, from_item_id,
                screenshot_id, user_context, evidence_packet_json, manual_prompt, model_label,
                prompt_version, evidence_count, selected_count, status,
                created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'draft', ?, ?)
            """,
            (
                run_id,
                question,
                asset,
                window_start,
                window_end,
                from_item_id,
                screenshot_id,
                user_context,
                packet_json,
                manual_prompt,
                model_label,
                prompt_version,
                len(evidence_packet),
                selected_count,
                created_at,
                created_at,
            ),
        )
        for rank, item in enumerate(evidence_packet):
            conn.execute(
                """
                INSERT INTO analysis_evidence (
                    run_id, news_id, rank, relevance_score, matched_keywords,
                    selected
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    str(item.get("news_id") or item.get("id") or ""),
                    rank,
                    float(item.get("relevance_score") or 0),
                    ",".join(str(k) for k in item.get("matched_keywords") or []),
                    1 if item.get("selected", True) else 0,
                ),
            )
        conn.commit()
    return run_id


def save_answer(
    run_id: str,
    answer_text: str,
    *,
    manual_prompt: str = "",
    model_label: str = "",
    answer_json: Optional[dict[str, Any]] = None,
    judgement: str = "",
    overall_confidence: float = 0,
    evidence_selections: Optional[dict[str, bool]] = None,
    path: Optional[Path] = None,
) -> None:
    answer_json = answer_json or {}
    updated_at = now_text()
    selected_count: Optional[int] = None
    with open_analysis_db(path) as conn:
        if evidence_selections is not None:
            for news_id, selected in evidence_selections.items():
                conn.execute(
                    """
                    UPDATE analysis_evidence
                    SET selected = ?
                    WHERE run_id = ? AND news_id = ?
                    """,
                    (1 if selected else 0, run_id, news_id),
                )
            selected_count = int(
                conn.execute(
                    """
                    SELECT COUNT(*)
                    FROM analysis_evidence
                    WHERE run_id = ? AND selected = 1
                    """,
                    (run_id,),
                ).fetchone()[0]
            )

        for catalyst in answer_json.get("catalysts") or []:
            if not isinstance(catalyst, dict) or not catalyst.get("news_id"):
                continue
            conn.execute(
                """
                UPDATE analysis_evidence
                SET llm_confidence = ?, llm_impact_path = ?, llm_direction = ?
                WHERE run_id = ? AND news_id = ?
                """,
                (
                    float(catalyst.get("confidence") or 0),
                    str(catalyst.get("impact_path") or ""),
                    str(catalyst.get("direction") or ""),
                    run_id,
                    str(catalyst.get("news_id")),
                ),
            )

        assignments = [
            "answer_text = ?",
            "answer_json = ?",
            "manual_prompt = ?",
            "model_label = ?",
            "judgement = ?",
            "overall_confidence = ?",
            "status = ?",
            "updated_at = ?",
        ]
        params: list[Any] = [
            answer_text,
            json.dumps(answer_json, ensure_ascii=False),
            manual_prompt,
            model_label or "manual_chatgpt_business",
            judgement,
            float(overall_confidence or 0),
            "done",
            updated_at,
        ]
        if selected_count is not None:
            assignments.append("selected_count = ?")
            params.append(selected_count)
        params.append(run_id)
        conn.execute(
            f"UPDATE analysis_runs SET {', '.join(assignments)} WHERE id = ?",
            params,
        )
        conn.commit()


def get_run(run_id: str, path: Optional[Path] = None) -> Optional[dict[str, Any]]:
    with open_analysis_db(path) as conn:
        row = conn.execute("SELECT * FROM analysis_runs WHERE id = ?", (run_id,)).fetchone()
        if not row:
            return None
        run = row_to_dict(row)
        screenshot_id = str(run.get("screenshot_id") or "")
        run["screenshot"] = get_screenshot(screenshot_id, path=path) if screenshot_id else None
        run["evidence_packet"] = parse_json_list(run.get("evidence_packet_json"))
        run["answer_parsed"] = parse_json_dict(run.get("answer_json"))
        packet_by_id = {
            str(item.get("news_id") or item.get("id") or ""): item
            for item in run["evidence_packet"]
            if isinstance(item, dict)
        }
        evidence_rows = conn.execute(
            """
            SELECT *
            FROM analysis_evidence
            WHERE run_id = ?
            ORDER BY rank ASC
            """,
            (run_id,),
        ).fetchall()
        enriched_rows = []
        for evidence in evidence_rows:
            row_dict = row_to_dict(evidence)
            packet_item = packet_by_id.get(str(row_dict.get("news_id") or ""), {})
            if packet_item:
                row_dict["published_at"] = packet_item.get("published_at", "")
                row_dict["title"] = packet_item.get("title", "")
                row_dict["content"] = packet_item.get("content", "")
                row_dict["priority_level"] = packet_item.get("priority_level", "")
                row_dict["news_source"] = packet_item.get("news_source", "")
            enriched_rows.append(row_dict)
        run["evidence_rows"] = enriched_rows
    return run


def list_runs(
    *,
    asset: str = "",
    limit: int = 50,
    path: Optional[Path] = None,
) -> list[dict[str, Any]]:
    safe_limit = max(1, min(int(limit), 200))
    clauses: list[str] = []
    params: list[Any] = []
    if asset:
        clauses.append("asset = ?")
        params.append(asset)
    where = "WHERE " + " AND ".join(clauses) if clauses else ""
    params.append(safe_limit)
    with open_analysis_db(path) as conn:
        rows = conn.execute(
            f"""
            SELECT id, question, asset, window_start, window_end, judgement,
                   overall_confidence, status, evidence_count, selected_count,
                   model_label, created_at, updated_at
            FROM analysis_runs
            {where}
            ORDER BY created_at DESC
            LIMIT ?
            """,
            params,
        ).fetchall()
    return [row_to_dict(row) for row in rows]


def get_runs_for_compare(run_ids: list[str], path: Optional[Path] = None) -> list[dict[str, Any]]:
    clean_ids = [str(run_id or "").strip() for run_id in run_ids if str(run_id or "").strip()][:2]
    if not clean_ids:
        return []
    placeholders = ",".join("?" for _ in clean_ids)
    with open_analysis_db(path) as conn:
        rows = conn.execute(
            f"""
            SELECT *
            FROM analysis_runs
            WHERE id IN ({placeholders})
            """,
            clean_ids,
        ).fetchall()
    runs_by_id: dict[str, dict[str, Any]] = {}
    for row in rows:
        run = row_to_dict(row)
        run["evidence_packet"] = parse_json_list(run.get("evidence_packet_json"))
        run["answer_parsed"] = parse_json_dict(run.get("answer_json"))
        runs_by_id[str(run.get("id") or "")] = run
    return [runs_by_id[run_id] for run_id in clean_ids if run_id in runs_by_id]


def delete_run(run_id: str, path: Optional[Path] = None) -> None:
    with open_analysis_db(path) as conn:
        conn.execute("DELETE FROM analysis_runs WHERE id = ?", (run_id,))
        conn.commit()


def save_screenshot(
    file_bytes: bytes,
    original_filename: str,
    *,
    user_description: str = "",
    path: Optional[Path] = None,
) -> str:
    screenshot_id = new_screenshot_id()
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    suffix = Path(original_filename).suffix or ".png"
    file_path = SCREENSHOT_DIR / f"{screenshot_id}{suffix}"
    file_path.write_bytes(file_bytes)
    try:
        relative_path = str(file_path.relative_to(BASE_DIR))
    except ValueError:
        relative_path = str(file_path)
    with open_analysis_db(path) as conn:
        conn.execute(
            """
            INSERT INTO screenshots (
                id, file_path, original_filename, user_description, uploaded_at
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                screenshot_id,
                relative_path,
                original_filename,
                user_description,
                now_text(),
            ),
        )
        conn.commit()
    return screenshot_id


def get_screenshot(screenshot_id: str, path: Optional[Path] = None) -> Optional[dict[str, Any]]:
    if not screenshot_id:
        return None
    with open_analysis_db(path) as conn:
        row = conn.execute("SELECT * FROM screenshots WHERE id = ?", (screenshot_id,)).fetchone()
    return row_to_dict(row) if row else None


def parse_json_list(value: object) -> list[dict[str, Any]]:
    try:
        parsed = json.loads(str(value or "[]"))
    except json.JSONDecodeError:
        return []
    return parsed if isinstance(parsed, list) else []


def parse_json_dict(value: object) -> dict[str, Any]:
    try:
        parsed = json.loads(str(value or "{}"))
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}
