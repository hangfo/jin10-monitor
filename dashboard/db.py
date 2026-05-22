"""Readonly SQLite access for the standalone dashboard."""

from __future__ import annotations

import os
import sqlite3
import urllib.parse
from pathlib import Path
from typing import Any, Optional


BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_HISTORY_DB = BASE_DIR / "data" / "jin10_history.sqlite3"

REQUIRED_TABLES = {
    "flash_history",
    "runtime_state",
    "delivery_log",
    "telegram_delivery_status",
}


def history_db_path() -> Path:
    return Path(os.getenv("HISTORY_DB", str(DEFAULT_HISTORY_DB))).expanduser()


def open_readonly_connection(path: Optional[Path] = None) -> sqlite3.Connection:
    db_path = (path or history_db_path()).expanduser()
    db_path = db_path if db_path.is_absolute() else Path.cwd() / db_path
    if not db_path.exists():
        raise FileNotFoundError(str(db_path))
    uri = f"file:{urllib.parse.quote(str(db_path), safe='/')}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA query_only = ON")
    return conn


def row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {key: row[key] for key in row.keys()}


def existing_tables(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
    return {str(row["name"]) for row in rows}


def history_health() -> dict[str, Any]:
    db_path = history_db_path()
    health: dict[str, Any] = {
        "status": "missing_history_db",
        "history_db": str(db_path),
        "history_db_exists": db_path.exists(),
        "read_boundary": "local_sqlite_readonly",
        "writes_business_db": False,
        "calls_jin10_rest": False,
        "sends_telegram": False,
        "missing_tables": [],
    }
    if not db_path.exists():
        return health

    with open_readonly_connection(db_path) as conn:
        missing = sorted(REQUIRED_TABLES - existing_tables(conn))
        health["missing_tables"] = missing
        health["status"] = "missing_schema" if missing else "ok"
    return health


def query_recent_items(
    *,
    limit: int = 80,
    priority: str = "",
    with_status: bool = False,
) -> list[dict[str, Any]]:
    safe_limit = max(1, min(int(limit), 300))
    clauses = []
    params: list[object] = []
    if priority:
        clauses.append("h.priority_level = ?")
        params.append(priority)
    if with_status:
        clauses.append("EXISTS (SELECT 1 FROM telegram_delivery_status t WHERE t.message_id = h.id)")
    where = "WHERE " + " AND ".join(clauses) if clauses else ""
    params.append(safe_limit)

    with open_readonly_connection() as conn:
        rows = conn.execute(
            f"""
            SELECT h.id, h.published_at, h.title, h.content, h.hit, h.high, h.important,
                   h.has_bold, h.priority_level, h.has_pic, h.pic_url, h.news_source,
                   h.source_url, h.source, h.created_at,
                   (
                       SELECT t.status
                       FROM telegram_delivery_status t
                       WHERE t.message_id = h.id
                       ORDER BY t.updated_at DESC
                       LIMIT 1
                   ) AS telegram_status,
                   (
                       SELECT t.mode
                       FROM telegram_delivery_status t
                       WHERE t.message_id = h.id
                       ORDER BY t.updated_at DESC
                       LIMIT 1
                   ) AS telegram_mode
            FROM flash_history h
            {where}
            ORDER BY h.published_at DESC, h.created_at DESC
            LIMIT ?
            """,
            params,
        ).fetchall()
    return [row_to_dict(row) for row in rows]
