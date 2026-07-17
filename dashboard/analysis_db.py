"""Read/write access for the dashboard analysis database.

The analysis database is intentionally separate from the monitor's business
history database. Dashboard analysis writes go to data/dashboard_analysis.sqlite3
only.
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional

from .analysis_quality import evidence_fingerprint, prompt_fingerprint


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
    provider_name TEXT NOT NULL DEFAULT '',
    provider_started_at TEXT NOT NULL DEFAULT '',
    provider_error TEXT NOT NULL DEFAULT '',
    provider_error_at TEXT NOT NULL DEFAULT '',
    provider_elapsed_ms INTEGER NOT NULL DEFAULT 0,
    prompt_version TEXT NOT NULL DEFAULT 'v1',
    parent_run_id TEXT NOT NULL DEFAULT '',
    evidence_fingerprint TEXT NOT NULL DEFAULT '',
    prompt_fingerprint TEXT NOT NULL DEFAULT '',
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


def open_analysis_db_readonly(path: Optional[Path] = None) -> sqlite3.Connection:
    db_path = analysis_db_path(path).resolve()
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA query_only = ON")
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
    if "provider_error" not in columns:
        conn.execute("ALTER TABLE analysis_runs ADD COLUMN provider_error TEXT NOT NULL DEFAULT ''")
    if "provider_error_at" not in columns:
        conn.execute("ALTER TABLE analysis_runs ADD COLUMN provider_error_at TEXT NOT NULL DEFAULT ''")
    if "provider_elapsed_ms" not in columns:
        conn.execute("ALTER TABLE analysis_runs ADD COLUMN provider_elapsed_ms INTEGER NOT NULL DEFAULT 0")
    if "provider_name" not in columns:
        conn.execute("ALTER TABLE analysis_runs ADD COLUMN provider_name TEXT NOT NULL DEFAULT ''")
    if "provider_started_at" not in columns:
        conn.execute("ALTER TABLE analysis_runs ADD COLUMN provider_started_at TEXT NOT NULL DEFAULT ''")
    if "parent_run_id" not in columns:
        conn.execute("ALTER TABLE analysis_runs ADD COLUMN parent_run_id TEXT NOT NULL DEFAULT ''")
    if "evidence_fingerprint" not in columns:
        conn.execute("ALTER TABLE analysis_runs ADD COLUMN evidence_fingerprint TEXT NOT NULL DEFAULT ''")
    if "prompt_fingerprint" not in columns:
        conn.execute("ALTER TABLE analysis_runs ADD COLUMN prompt_fingerprint TEXT NOT NULL DEFAULT ''")


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
    parent_run_id: str = "",
    path: Optional[Path] = None,
) -> str:
    run_id = new_run_id()
    created_at = now_text()
    selected_count = sum(1 for item in evidence_packet if item.get("selected", True))
    packet_json = json.dumps(evidence_packet, ensure_ascii=False)
    packet_fingerprint = evidence_fingerprint(evidence_packet)
    saved_prompt_fingerprint = prompt_fingerprint(manual_prompt)
    with open_analysis_db(path) as conn:
        conn.execute(
            """
            INSERT INTO analysis_runs (
                id, question, asset, window_start, window_end, from_item_id,
                screenshot_id, user_context, evidence_packet_json, manual_prompt, model_label,
                prompt_version, parent_run_id, evidence_fingerprint, prompt_fingerprint,
                evidence_count, selected_count, status,
                created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'draft', ?, ?)
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
                parent_run_id,
                packet_fingerprint,
                saved_prompt_fingerprint,
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


def clone_run(run_id: str, *, path: Optional[Path] = None) -> Optional[str]:
    """Create a draft with the source run's exact frozen inputs, without a Provider call."""

    source = get_run(run_id, path=path)
    if not source or source.get("status") == "running":
        return None
    return create_run(
        question=str(source.get("question") or ""),
        asset=str(source.get("asset") or ""),
        window_start=str(source.get("window_start") or ""),
        window_end=str(source.get("window_end") or ""),
        evidence_packet=source.get("evidence_packet") or [],
        from_item_id=str(source.get("from_item_id") or ""),
        screenshot_id=str(source.get("screenshot_id") or ""),
        user_context=str(source.get("user_context") or ""),
        manual_prompt=str(source.get("manual_prompt") or ""),
        model_label="manual_chatgpt_business",
        prompt_version=str(source.get("prompt_version") or "v1"),
        parent_run_id=run_id,
        path=path,
    )


def save_provider_error(
    run_id: str,
    message: str,
    *,
    provider_elapsed_ms: int = 0,
    path: Optional[Path] = None,
) -> None:
    updated_at = now_text()
    with open_analysis_db(path) as conn:
        conn.execute(
            """
            UPDATE analysis_runs
            SET provider_error = ?, provider_error_at = ?, provider_elapsed_ms = ?, status = 'draft', updated_at = ?
            WHERE id = ? AND status IN ('draft', 'running')
            """,
            (str(message or "")[:1200], updated_at, max(0, int(provider_elapsed_ms or 0)), updated_at, run_id),
        )
        conn.commit()


def save_manual_prompt(run_id: str, manual_prompt: str, *, path: Optional[Path] = None) -> bool:
    prompt = str(manual_prompt or "").strip()
    if not prompt:
        return False
    updated_at = now_text()
    with open_analysis_db(path) as conn:
        cursor = conn.execute(
            """
            UPDATE analysis_runs
            SET manual_prompt = ?, prompt_fingerprint = ?, updated_at = ?
            WHERE id = ? AND status = 'draft'
            """,
            (prompt, prompt_fingerprint(prompt), updated_at, run_id),
        )
        conn.commit()
    return cursor.rowcount == 1


def mark_provider_running(
    run_id: str,
    *,
    provider_name: str,
    provider_label: str = "",
    path: Optional[Path] = None,
) -> bool:
    updated_at = now_text()
    with open_analysis_db(path) as conn:
        cursor = conn.execute(
            """
            UPDATE analysis_runs
            SET status = 'running',
                provider_name = ?,
                provider_started_at = ?,
                provider_error = '',
                provider_error_at = '',
                provider_elapsed_ms = 0,
                model_label = ?,
                updated_at = ?
            WHERE id = ? AND status = 'draft'
            """,
            (
                str(provider_name or "")[:80],
                updated_at,
                str(provider_label or provider_name or "")[:120],
                updated_at,
                run_id,
            ),
        )
        conn.commit()
    return cursor.rowcount == 1


def reset_stale_running_runs(path: Optional[Path] = None) -> int:
    updated_at = now_text()
    with open_analysis_db(path) as conn:
        cursor = conn.execute(
            """
            UPDATE analysis_runs
            SET status = 'draft',
                provider_error = ?,
                provider_error_at = ?,
                updated_at = ?
            WHERE status = 'running'
            """,
            ("服务重启，后台任务已中断，可重新调用。", updated_at, updated_at),
        )
        conn.commit()
    return cursor.rowcount


def estimate_provider_completion_seconds(provider_name: str, *, path: Optional[Path] = None) -> Optional[float]:
    provider = str(provider_name or "").strip()
    if not provider:
        return None
    with open_analysis_db_readonly(path) as conn:
        rows = conn.execute(
            """
            SELECT provider_elapsed_ms
            FROM analysis_runs
            WHERE provider_name = ?
              AND status = 'done'
              AND provider_elapsed_ms > 0
            ORDER BY created_at DESC
            LIMIT 10
            """,
            (provider,),
        ).fetchall()
    if not rows:
        return None
    values = sorted(int(row["provider_elapsed_ms"] or 0) for row in rows)
    return values[len(values) // 2] / 1000


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
    provider_elapsed_ms: int = 0,
    provider_name: Optional[str] = None,
    expected_status: str = "draft",
    path: Optional[Path] = None,
) -> bool:
    answer_json = answer_json or {}
    updated_at = now_text()
    selected_count: Optional[int] = None
    with open_analysis_db(path) as conn:
        expected = str(expected_status or "").strip()
        row = conn.execute(
            "SELECT status, evidence_packet_json FROM analysis_runs WHERE id = ?",
            (run_id,),
        ).fetchone()
        if not row:
            return False
        if expected:
            if str(row["status"] or "") != expected:
                return False

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
            "prompt_fingerprint = ?",
            "model_label = ?",
            "provider_error = ?",
            "provider_error_at = ?",
            "provider_elapsed_ms = ?",
            "judgement = ?",
            "overall_confidence = ?",
            "status = ?",
            "updated_at = ?",
        ]
        params: list[Any] = [
            answer_text,
            json.dumps(answer_json, ensure_ascii=False),
            manual_prompt,
            prompt_fingerprint(manual_prompt),
            model_label or "manual_chatgpt_business",
            "",
            "",
            max(0, int(provider_elapsed_ms or 0)),
            judgement,
            float(overall_confidence or 0),
            "done",
            updated_at,
        ]
        if provider_name is not None:
            assignments.append("provider_name = ?")
            params.append(str(provider_name or "")[:120])
        if selected_count is not None:
            assignments.append("selected_count = ?")
            params.append(selected_count)
            packet = parse_json_list(row["evidence_packet_json"] if row else "[]")
            for item in packet:
                if not isinstance(item, dict):
                    continue
                news_id = str(item.get("news_id") or item.get("id") or "")
                if news_id in evidence_selections:
                    item["selected"] = bool(evidence_selections[news_id])
            assignments.extend(("evidence_packet_json = ?", "evidence_fingerprint = ?"))
            params.extend((json.dumps(packet, ensure_ascii=False), evidence_fingerprint(packet)))
        params.append(run_id)
        where = "WHERE id = ?"
        if expected:
            where += " AND status = ?"
            params.append(expected)
        cursor = conn.execute(
            f"UPDATE analysis_runs SET {', '.join(assignments)} {where}",
            params,
        )
        conn.commit()
    return cursor.rowcount == 1


def get_run(run_id: str, path: Optional[Path] = None) -> Optional[dict[str, Any]]:
    with open_analysis_db(path) as conn:
        row = conn.execute("SELECT * FROM analysis_runs WHERE id = ?", (run_id,)).fetchone()
        if not row:
            return None
        run = row_to_dict(row)
        screenshot_id = str(run.get("screenshot_id") or "")
        run["screenshot"] = get_screenshot(screenshot_id, path=path) if screenshot_id else None
        run["evidence_packet"] = parse_json_list(run.get("evidence_packet_json"))
        run["evidence_fingerprint"] = str(run.get("evidence_fingerprint") or evidence_fingerprint(run["evidence_packet"]))
        run["prompt_fingerprint"] = str(run.get("prompt_fingerprint") or prompt_fingerprint(run.get("manual_prompt") or ""))
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
                row_dict["score_reasons"] = packet_item.get("score_reasons", [])
            enriched_rows.append(row_dict)
        run["evidence_rows"] = enriched_rows
    return run


def list_runs(
    *,
    asset: str = "",
    status_filter: str = "all",
    limit: int = 50,
    path: Optional[Path] = None,
) -> list[dict[str, Any]]:
    safe_limit = max(1, min(int(limit), 200))
    clauses: list[str] = []
    params: list[Any] = []
    if asset:
        clauses.append("asset = ?")
        params.append(asset)
    order_by = "created_at DESC"
    if status_filter in {"draft", "running", "done"}:
        clauses.append("status = ?")
        params.append(status_filter)
    elif status_filter == "recent_failed":
        clauses.append("status = 'draft'")
        clauses.append("provider_error <> ''")
        order_by = "COALESCE(NULLIF(provider_error_at, ''), updated_at, created_at) DESC"
    where = "WHERE " + " AND ".join(clauses) if clauses else ""
    params.append(safe_limit)
    with open_analysis_db(path) as conn:
        rows = conn.execute(
            f"""
            SELECT id, question, asset, window_start, window_end, judgement,
                   overall_confidence, status, evidence_count, selected_count,
                   model_label, provider_name, provider_started_at,
                   provider_error, provider_error_at, provider_elapsed_ms,
                   created_at, updated_at
            FROM analysis_runs
            {where}
            ORDER BY {order_by}
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
        run["evidence_fingerprint"] = str(run.get("evidence_fingerprint") or evidence_fingerprint(run["evidence_packet"]))
        run["prompt_fingerprint"] = str(run.get("prompt_fingerprint") or prompt_fingerprint(run.get("manual_prompt") or ""))
        run["answer_parsed"] = parse_json_dict(run.get("answer_json"))
        runs_by_id[str(run.get("id") or "")] = run
    return [runs_by_id[run_id] for run_id in clean_ids if run_id in runs_by_id]


def list_completed_runs_with_packets(limit: int = 50, path: Optional[Path] = None) -> list[dict[str, Any]]:
    """Return recent completed inputs for read-only local stability analysis."""

    safe_limit = max(1, min(int(limit), 200))
    with open_analysis_db_readonly(path) as conn:
        rows = conn.execute(
            """
            SELECT * FROM analysis_runs
            WHERE status = 'done'
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (safe_limit,),
        ).fetchall()
    runs: list[dict[str, Any]] = []
    for row in rows:
        run = row_to_dict(row)
        run["evidence_packet"] = parse_json_list(run.get("evidence_packet_json"))
        run["answer_parsed"] = parse_json_dict(run.get("answer_json"))
        run["evidence_fingerprint"] = str(run.get("evidence_fingerprint") or evidence_fingerprint(run["evidence_packet"]))
        run["prompt_fingerprint"] = str(run.get("prompt_fingerprint") or prompt_fingerprint(run.get("manual_prompt") or ""))
        runs.append(run)
    return runs


def delete_run(
    run_id: str,
    *,
    allowed_statuses: Optional[tuple[str, ...]] = None,
    path: Optional[Path] = None,
) -> bool:
    with open_analysis_db(path) as conn:
        params: list[Any] = [run_id]
        status_clause = ""
        if allowed_statuses is not None:
            clean_statuses = tuple(str(status or "").strip() for status in allowed_statuses if str(status or "").strip())
            if not clean_statuses:
                return False
            placeholders = ",".join("?" for _ in clean_statuses)
            status_clause = f" AND status IN ({placeholders})"
            params.extend(clean_statuses)
        cursor = conn.execute(f"DELETE FROM analysis_runs WHERE id = ?{status_clause}", params)
        conn.commit()
    return cursor.rowcount == 1


def _empty_provider_call_stats(hours: int) -> dict[str, Any]:
    return {
        "hours": hours,
        "total_calls": 0,
        "success_count": 0,
        "failure_count": 0,
        "running_count": 0,
        "uncounted_count": 0,
        "providers": [],
        "recent_timeline": [],
    }


def _seconds(value: int) -> float:
    return round(max(0, int(value or 0)) / 1000, 1)


def query_provider_call_stats(*, hours: int = 24, path: Optional[Path] = None) -> dict[str, Any]:
    safe_hours = max(1, min(int(hours or 24), 168))
    db_path = analysis_db_path(path)
    if not db_path.exists():
        return _empty_provider_call_stats(safe_hours)
    since = (datetime.now() - timedelta(hours=safe_hours)).strftime("%Y-%m-%d %H:%M:%S")
    conn: Optional[sqlite3.Connection] = None
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT id, status, provider_name, model_label, provider_started_at,
                   provider_error, provider_error_at, provider_elapsed_ms,
                   created_at, updated_at
            FROM analysis_runs
            WHERE provider_name <> ''
              AND (
                provider_started_at >= ?
                OR provider_error_at >= ?
                OR updated_at >= ?
              )
            ORDER BY COALESCE(NULLIF(provider_error_at, ''), NULLIF(updated_at, ''), NULLIF(provider_started_at, ''), created_at) DESC
            """,
            (since, since, since),
        ).fetchall()
    except sqlite3.Error:
        return _empty_provider_call_stats(safe_hours)
    finally:
        if conn is not None:
            conn.close()

    providers: dict[str, dict[str, Any]] = {}
    total_calls = 0
    success_count = 0
    failure_count = 0
    running_count = 0
    uncounted_count = 0
    recent_timeline: list[dict[str, Any]] = []
    for row in rows:
        provider_name = str(row["provider_name"] or "").strip()
        if not provider_name:
            continue
        total_calls += 1
        status = str(row["status"] or "")
        provider = providers.setdefault(
            provider_name,
            {
                "provider_name": provider_name,
                "model_label": str(row["model_label"] or provider_name),
                "calls": 0,
                "success_count": 0,
                "failure_count": 0,
                "running_count": 0,
                "elapsed_values": [],
                "last_started_at": "",
                "recent_error": "",
                "recent_error_at": "",
            },
        )
        provider["calls"] += 1
        if row["provider_started_at"] and not provider["last_started_at"]:
            provider["last_started_at"] = str(row["provider_started_at"])
        if status == "done":
            success_count += 1
            provider["success_count"] += 1
            timeline_status = "done"
        elif status == "running":
            running_count += 1
            provider["running_count"] += 1
            timeline_status = "running"
        elif row["provider_error"]:
            failure_count += 1
            provider["failure_count"] += 1
            timeline_status = "failed"
            if not provider["recent_error"]:
                provider["recent_error"] = str(row["provider_error"])
                provider["recent_error_at"] = str(row["provider_error_at"] or row["updated_at"] or "")
        else:
            uncounted_count += 1
            provider["uncounted_count"] = int(provider.get("uncounted_count") or 0) + 1
            timeline_status = "uncounted"
        elapsed = int(row["provider_elapsed_ms"] or 0)
        if elapsed > 0:
            provider["elapsed_values"].append(elapsed)
        if len(recent_timeline) < 50:
            recent_timeline.append({
                "run_id": str(row["id"] or ""),
                "provider_name": provider_name,
                "model_label": str(row["model_label"] or provider_name),
                "status": timeline_status,
                "started_at": str(row["provider_started_at"] or ""),
                "updated_at": str(row["updated_at"] or ""),
                "elapsed_seconds": _seconds(elapsed),
            })

    provider_rows = []
    for provider in providers.values():
        provider["uncounted_count"] = int(provider.get("uncounted_count") or 0)
        elapsed_values = sorted(provider.pop("elapsed_values"))
        if elapsed_values:
            provider["avg_elapsed_seconds"] = _seconds(sum(elapsed_values) // len(elapsed_values))
            provider["p50_elapsed_seconds"] = _seconds(elapsed_values[len(elapsed_values) // 2])
            provider["max_elapsed_seconds"] = _seconds(max(elapsed_values))
        else:
            provider["avg_elapsed_seconds"] = 0
            provider["p50_elapsed_seconds"] = 0
            provider["max_elapsed_seconds"] = 0
        provider_rows.append(provider)

    provider_rows.sort(key=lambda item: (-int(item["calls"]), str(item["provider_name"])))
    return {
        "hours": safe_hours,
        "total_calls": total_calls,
        "success_count": success_count,
        "failure_count": failure_count,
        "running_count": running_count,
        "uncounted_count": uncounted_count,
        "providers": provider_rows,
        "recent_timeline": recent_timeline,
    }


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
