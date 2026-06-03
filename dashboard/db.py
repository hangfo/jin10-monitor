"""Readonly SQLite access for the standalone dashboard."""

from __future__ import annotations

import os
import sqlite3
import urllib.parse
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional

from jin10_monitor import HIGH_PRIORITY, KEYWORDS


BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_HISTORY_DB = BASE_DIR / "data" / "jin10_history.sqlite3"

REQUIRED_TABLES = {
    "flash_history",
    "runtime_state",
    "delivery_log",
    "telegram_delivery_status",
}

HOURS_OPTIONS = [1, 6, 24, 72]
DEFAULT_HOURS = 24


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


def table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return {str(row["name"]) for row in rows}


def optional_column(columns: set[str], name: str, alias: Optional[str] = None) -> str:
    if name in columns:
        return f"h.{name}"
    return f"'' AS {alias or name}"


def since_text(hours: int) -> str:
    safe_hours = max(1, min(int(hours), 720))
    return (datetime.now() - timedelta(hours=safe_hours)).strftime("%Y-%m-%d %H:%M:%S")


def env_int(name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(os.getenv(name, str(default)) or default)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(parsed, maximum))


def parse_history_datetime(value: object) -> Optional[datetime]:
    text = str(value or "").strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(text[:19], fmt)
        except ValueError:
            continue
    return None


def safe_int(value: object, default: int = 0) -> int:
    try:
        return int(value or default)
    except (TypeError, ValueError):
        return default


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
    keyword: str = "",
    hours: int = DEFAULT_HOURS,
    tg_sent_only: bool = False,
    with_status: bool = False,
) -> list[dict[str, Any]]:
    safe_limit = max(1, min(int(limit), 300))
    clauses = ["h.published_at >= ?"]
    params: list[object] = [since_text(hours)]
    if priority:
        clauses.append("h.priority_level = ?")
        params.append(priority)
    if keyword:
        clauses.append("(h.title LIKE ? OR h.content LIKE ?)")
        pattern = f"%{keyword[:80]}%"
        params.extend([pattern, pattern])
    if tg_sent_only:
        clauses.append("EXISTS (SELECT 1 FROM delivery_log dl WHERE dl.message_id = h.id)")
    if with_status:
        clauses.append("EXISTS (SELECT 1 FROM telegram_delivery_status t WHERE t.message_id = h.id)")
    where = "WHERE " + " AND ".join(clauses)
    params.append(safe_limit)

    with open_readonly_connection() as conn:
        columns = table_columns(conn, "flash_history")
        rows = conn.execute(
            f"""
            SELECT h.id, h.published_at, h.title, h.content, h.hit, h.high, h.important,
                   h.has_bold, h.priority_level, h.has_pic, h.pic_url, h.news_source,
                   h.source_url, h.source, h.created_at,
                   {optional_column(columns, "has_title")},
                   {optional_column(columns, "style_flags")},
                   (
                       SELECT t.status
                       FROM telegram_delivery_status t
                       WHERE t.message_id = h.id
                       ORDER BY t.updated_at DESC
                       LIMIT 1
                   ) AS telegram_status,
                   (
                       SELECT datetime(t.updated_at, 'localtime')
                       FROM telegram_delivery_status t
                       WHERE t.message_id = h.id
                       ORDER BY t.updated_at DESC
                       LIMIT 1
                   ) AS telegram_updated_at,
                   (
                       SELECT t.mode
                       FROM telegram_delivery_status t
                       WHERE t.message_id = h.id
                       ORDER BY t.updated_at DESC
                       LIMIT 1
                   ) AS telegram_mode,
                   (
                       SELECT datetime(dl.sent_at, 'localtime')
                       FROM delivery_log dl
                       WHERE dl.message_id = h.id
                       ORDER BY dl.sent_at DESC
                       LIMIT 1
                   ) AS tg_confirmed_sent_at,
                   EXISTS (
                       SELECT 1 FROM delivery_log dl WHERE dl.message_id = h.id
                   ) AS tg_confirmed_sent
            FROM flash_history h
            {where}
            ORDER BY h.published_at DESC, h.id DESC
            LIMIT ?
            """,
            params,
        ).fetchall()
    return [row_to_dict(row) for row in rows]


def query_feed_page(
    *,
    offset: int = 0,
    limit: int = 30,
    priority: str = "",
    keyword: str = "",
    hours: int = DEFAULT_HOURS,
    tg_sent_only: bool = False,
    with_status: bool = False,
) -> list[dict[str, Any]]:
    safe_offset = max(0, int(offset))
    safe_limit = max(1, min(int(limit), 50))
    clauses = ["h.published_at >= ?"]
    params: list[object] = [since_text(hours)]
    if priority:
        clauses.append("h.priority_level = ?")
        params.append(priority)
    if keyword:
        clauses.append("(h.title LIKE ? OR h.content LIKE ?)")
        pattern = f"%{keyword[:80]}%"
        params.extend([pattern, pattern])
    if tg_sent_only:
        clauses.append("EXISTS (SELECT 1 FROM delivery_log dl WHERE dl.message_id = h.id)")
    if with_status:
        clauses.append("EXISTS (SELECT 1 FROM telegram_delivery_status t WHERE t.message_id = h.id)")
    where = "WHERE " + " AND ".join(clauses)
    params.extend([safe_limit, safe_offset])

    with open_readonly_connection() as conn:
        columns = table_columns(conn, "flash_history")
        rows = conn.execute(
            f"""
            SELECT h.id, h.published_at, h.title, h.content, h.hit, h.high, h.important,
                   h.has_bold, h.priority_level, h.has_pic, h.pic_url, h.news_source,
                   h.source_url, h.source, h.created_at,
                   {optional_column(columns, "has_title")},
                   {optional_column(columns, "style_flags")},
                   (
                       SELECT t.status
                       FROM telegram_delivery_status t
                       WHERE t.message_id = h.id
                       ORDER BY t.updated_at DESC
                       LIMIT 1
                   ) AS telegram_status,
                   (
                       SELECT datetime(t.updated_at, 'localtime')
                       FROM telegram_delivery_status t
                       WHERE t.message_id = h.id
                       ORDER BY t.updated_at DESC
                       LIMIT 1
                   ) AS telegram_updated_at,
                   (
                       SELECT t.mode
                       FROM telegram_delivery_status t
                       WHERE t.message_id = h.id
                       ORDER BY t.updated_at DESC
                       LIMIT 1
                   ) AS telegram_mode,
                   (
                       SELECT datetime(dl.sent_at, 'localtime')
                       FROM delivery_log dl
                       WHERE dl.message_id = h.id
                       ORDER BY dl.sent_at DESC
                       LIMIT 1
                   ) AS tg_confirmed_sent_at,
                   EXISTS (
                       SELECT 1 FROM delivery_log dl WHERE dl.message_id = h.id
                   ) AS tg_confirmed_sent
            FROM flash_history h
            {where}
            ORDER BY h.published_at DESC, h.id DESC
            LIMIT ? OFFSET ?
            """,
            params,
        ).fetchall()
    return [row_to_dict(row) for row in rows]


def query_latest_published_at(
    *,
    priority: str = "",
    keyword: str = "",
    hours: int = DEFAULT_HOURS,
    tg_sent_only: bool = False,
    with_status: bool = False,
) -> Optional[str]:
    clauses = ["h.published_at >= ?"]
    params: list[object] = [since_text(hours)]
    if priority:
        clauses.append("h.priority_level = ?")
        params.append(priority)
    if keyword:
        clauses.append("(h.title LIKE ? OR h.content LIKE ?)")
        pattern = f"%{keyword[:80]}%"
        params.extend([pattern, pattern])
    if tg_sent_only:
        clauses.append("EXISTS (SELECT 1 FROM delivery_log dl WHERE dl.message_id = h.id)")
    if with_status:
        clauses.append("EXISTS (SELECT 1 FROM telegram_delivery_status t WHERE t.message_id = h.id)")
    where = "WHERE " + " AND ".join(clauses)

    with open_readonly_connection() as conn:
        row = conn.execute(
            f"""
            SELECT h.published_at
            FROM flash_history h
            {where}
            ORDER BY h.published_at DESC, h.id DESC
            LIMIT 1
            """,
            params,
        ).fetchone()
    return str(row["published_at"]) if row else None


def query_feed_density(*, hours: int = DEFAULT_HOURS) -> list[dict[str, Any]]:
    with open_readonly_connection() as conn:
        rows = conn.execute(
            """
            SELECT strftime('%H', published_at) AS hour_slot,
                   SUM(CASE WHEN priority_level IN ('T3_IMPORTANT', 'T2_HIGH') THEN 1 ELSE 0 END) AS hot_count,
                   COUNT(*) AS total_count
            FROM flash_history
            WHERE published_at >= ?
            GROUP BY hour_slot
            ORDER BY hour_slot ASC
            """,
            (since_text(hours),),
        ).fetchall()
    return [row_to_dict(row) for row in rows]


def query_keyword_heatmap(*, hours: int = DEFAULT_HOURS, limit: int = 14) -> list[dict[str, Any]]:
    high_keywords = set(HIGH_PRIORITY)
    keywords = list(dict.fromkeys([*HIGH_PRIORITY, *KEYWORDS]))[:50]
    rows: list[dict[str, Any]] = []
    with open_readonly_connection() as conn:
        for keyword in keywords:
            count = conn.execute(
                """
                SELECT COUNT(*)
                FROM flash_history
                WHERE published_at >= ? AND (title LIKE ? OR content LIKE ?)
                """,
                (since_text(hours), f"%{keyword}%", f"%{keyword}%"),
            ).fetchone()[0]
            if count:
                rows.append({"keyword": keyword, "count": count, "is_high": keyword in high_keywords})
    return sorted(rows, key=lambda row: row["count"], reverse=True)[: max(1, min(limit, 24))]


def query_item(message_id: str) -> Optional[dict[str, Any]]:
    with open_readonly_connection() as conn:
        columns = table_columns(conn, "flash_history")
        row = conn.execute(
            f"""
            SELECT h.id, h.published_at, h.title, h.content, h.hit, h.high, h.important,
                   h.has_bold, h.priority_level, h.has_pic, h.pic_url, h.news_source,
                   h.source_url, h.source, h.created_at,
                   {optional_column(columns, "has_title")},
                   {optional_column(columns, "style_flags")},
                   {optional_column(columns, "raw_json")}
            FROM flash_history h
            WHERE h.id = ?
            """,
            (message_id,),
        ).fetchone()
    return row_to_dict(row) if row else None


def query_item_context(message_id: str, *, minutes: int = 15) -> tuple[Optional[dict[str, Any]], list[dict[str, Any]]]:
    safe_minutes = max(0, min(int(minutes), 120))
    with open_readonly_connection() as conn:
        columns = table_columns(conn, "flash_history")
        select_fields = f"""
            h.id, h.published_at, h.title, h.content, h.hit, h.high, h.important,
            h.has_bold, h.priority_level, h.has_pic, h.pic_url, h.news_source,
            h.source_url, h.source, h.created_at,
            {optional_column(columns, "has_title")},
            {optional_column(columns, "style_flags")},
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
        """
        center = conn.execute(
            f"""
            SELECT {select_fields}
            FROM flash_history h
            WHERE h.id = ?
            """,
            (message_id,),
        ).fetchone()
        if not center:
            return None, []

        rows = conn.execute(
            f"""
            SELECT {select_fields}
            FROM flash_history h
            WHERE h.published_at BETWEEN datetime(?, ?) AND datetime(?, ?)
            ORDER BY h.published_at ASC, h.id ASC
            """,
            (
                center["published_at"],
                f"-{safe_minutes} minutes",
                center["published_at"],
                f"+{safe_minutes} minutes",
            ),
        ).fetchall()
    return row_to_dict(center), [row_to_dict(row) for row in rows]


def query_tg_status_for_item(message_id: str) -> Optional[dict[str, Any]]:
    with open_readonly_connection() as conn:
        row = conn.execute(
            """
            SELECT status, detail, mode, datetime(updated_at, 'localtime') AS updated_at
            FROM telegram_delivery_status
            WHERE message_id = ?
            ORDER BY updated_at DESC
            LIMIT 1
            """,
            (message_id,),
        ).fetchone()
    return row_to_dict(row) if row else None


def query_tg_deliveries(*, status_filter: str = "all", limit: int = 120) -> list[dict[str, Any]]:
    safe_limit = max(1, min(int(limit), 500))
    clauses = []
    params: list[object] = []
    if status_filter != "all":
        clauses.append("t.status = ?")
        params.append(status_filter)
    where = "WHERE " + " AND ".join(clauses) if clauses else ""
    params.append(safe_limit)
    with open_readonly_connection() as conn:
        rows = conn.execute(
            f"""
            SELECT t.message_id, t.status, t.mode, t.detail,
                   datetime(t.updated_at, 'localtime') AS updated_at,
                   h.title, h.content, h.published_at, h.priority_level,
                   (
                       SELECT datetime(MAX(dl.sent_at), 'localtime')
                       FROM delivery_log dl
                       WHERE dl.message_id = t.message_id
                   ) AS confirmed_sent_at,
                   EXISTS (
                       SELECT 1 FROM delivery_log dl WHERE dl.message_id = t.message_id
                   ) AS confirmed_sent
            FROM telegram_delivery_status t
            LEFT JOIN flash_history h ON h.id = t.message_id
            {where}
            ORDER BY t.updated_at DESC
            LIMIT ?
            """,
            params,
        ).fetchall()
    return [row_to_dict(row) for row in rows]


def query_tg_summary(*, hours: int = DEFAULT_HOURS) -> dict[str, Any]:
    since = since_text(hours)
    with open_readonly_connection() as conn:
        rows = conn.execute(
            """
            SELECT status, COUNT(*) AS count
            FROM telegram_delivery_status
            WHERE updated_at >= ?
            GROUP BY status
            """,
            (since,),
        ).fetchall()
        counts = {str(row["status"]): int(row["count"]) for row in rows}
        confirmed_sent = conn.execute(
            "SELECT COUNT(*) FROM delivery_log WHERE sent_at >= ?",
            (since,),
        ).fetchone()[0]
        unknown_confirmed = conn.execute(
            """
            SELECT COUNT(*)
            FROM telegram_delivery_status t
            WHERE t.status = 'unknown_timeout'
              AND t.updated_at >= ?
              AND EXISTS (SELECT 1 FROM delivery_log dl WHERE dl.message_id = t.message_id)
            """,
            (since,),
        ).fetchone()[0]
    sent = counts.get("sent", 0)
    failed = counts.get("failed", 0)
    unknown_timeout = counts.get("unknown_timeout", 0)
    unknown_unconfirmed = max(0, unknown_timeout - int(unknown_confirmed))
    return {
        "sent": sent,
        "failed": failed,
        "unknown_timeout": unknown_timeout,
        "unknown_timeout_confirmed": int(unknown_confirmed),
        "unknown_timeout_unconfirmed": unknown_unconfirmed,
        "skipped": counts.get("skipped", 0),
        "confirmed_sent": confirmed_sent,
        "success_rate": round(sent / max(sent + failed, 1) * 100),
    }


def build_ops_overview(
    *,
    monitor_status: str,
    minutes_stale: Optional[float],
    rest_status: str,
    rest_state: dict[str, Any],
    ws_initial_state: dict[str, Any],
    realtime_sources: list[dict[str, Any]],
    delivery_counts: dict[str, int],
) -> dict[str, Any]:
    source_map = {source["key"]: source for source in realtime_sources}
    ws_count = safe_int(source_map.get("ws", {}).get("count_24h"))
    ws_initial_saved = safe_int(ws_initial_state.get("saved_count"))
    sent_count = delivery_counts.get("sent", 0)
    unknown_timeout_count = delivery_counts.get("unknown_timeout", 0)
    failed_count = delivery_counts.get("failed", 0)

    if monitor_status == "error":
        summary_status = "error"
        summary_label = "需要立即排查"
        summary_text = "主路入库已明显变旧，先确认 WebSocket 进程、launchd 状态和历史库写入。"
    elif monitor_status == "warn":
        summary_status = "warn"
        summary_label = "需要关注"
        summary_text = "主路仍有记录但新鲜度下降，建议观察 WebSocket 与补拉链路是否继续推进。"
    elif rest_status == "forbidden_backoff" or unknown_timeout_count or failed_count:
        summary_status = "degraded"
        summary_label = "降级运行"
        summary_text = "WebSocket 主路仍可观察，但 REST 或 Telegram 存在降级信号，需要人工看一眼。"
    elif monitor_status == "ok":
        summary_status = "ok"
        summary_label = "运行正常"
        summary_text = "WebSocket 主路新鲜，未发现需要立即处理的投递或补拉告警。"
    else:
        summary_status = "unknown"
        summary_label = "状态未知"
        summary_text = "暂无 last_ingested_at，先确认监控进程是否已完成启动并写入历史库。"

    freshness = "无游标"
    if minutes_stale is not None:
        freshness = f"{minutes_stale} 分钟未入库"

    ops_lanes = [
        {
            "key": "ws",
            "label": "WebSocket 主路",
            "status": "ok" if monitor_status == "ok" else monitor_status,
            "badge": "可信主路" if monitor_status in {"ok", "warn"} else "需排查",
            "headline": freshness,
            "detail": "实时采集的第一判断来源。",
            "latest": source_map.get("ws", {}).get("latest_published_at", ""),
            "count_24h": ws_count,
        },
        {
            "key": "rest",
            "label": "REST 轮询",
            "status": "degraded" if rest_status == "forbidden_backoff" else ("ok" if rest_status in {"ok", "recent"} else "warn"),
            "badge": "当前退避" if rest_status == "forbidden_backoff" else ("可用" if rest_status in {"ok", "recent"} else "仅观察"),
            "headline": rest_state.get("status") or rest_status,
            "detail": "辅助补拉信号，不代表整体采集是否中断。",
            "latest": source_map.get("rest", {}).get("latest_published_at", ""),
            "count_24h": safe_int(source_map.get("rest", {}).get("count_24h")),
        },
        {
            "key": "ws_initial",
            "label": "Initial History",
            "status": "info" if ws_initial_saved else "idle",
            "badge": "补到新消息" if ws_initial_saved else "等待快照",
            "headline": f"新入库 {ws_initial_saved} 条",
            "detail": "重连快照可辅助人工判断短缺口。",
            "latest": ws_initial_state.get("newest_published_at", ""),
            "count_24h": safe_int(source_map.get("ws_initial", {}).get("count_24h")),
        },
        {
            "key": "telegram",
            "label": "Telegram 投递",
            "status": "warn" if unknown_timeout_count or failed_count else "ok",
            "badge": "需人工核对" if unknown_timeout_count or failed_count else "确认正常",
            "headline": f"sent {sent_count} / timeout {unknown_timeout_count} / failed {failed_count}",
            "detail": "unknown_timeout 不自动重发，成功去重仍看 delivery_log。",
            "latest": "",
            "count_24h": sent_count + unknown_timeout_count + failed_count,
        },
    ]

    ops_actions = []
    if monitor_status in {"warn", "error", "unknown"}:
        ops_actions.append("先确认 WebSocket 主路是否继续推进 last_ingested_at。")
    if rest_status == "forbidden_backoff":
        ops_actions.append("观察 REST 退避截止时间和最近恢复时间，不把 403 退避误判为整体停采。")
    if ws_initial_saved:
        ops_actions.append("查看 WebSocket initial history 新入库记录，人工判断是否覆盖短缺口。")
    if unknown_timeout_count:
        ops_actions.append("核对最近 Telegram unknown_timeout 项；不要自动重发，避免破坏 delivery_log 去重语义。")
    if failed_count:
        ops_actions.append("检查最近 Telegram failed 明细，区分配置错误和单条消息异常。")
    if not ops_actions:
        ops_actions.append("无需立即动作，继续观察 WebSocket 新鲜度和 Telegram sent 数。")

    max_source_count = max((safe_int(source.get("count_24h")) for source in realtime_sources), default=0)
    max_telegram_count = max(delivery_counts.values(), default=0)
    return {
        "summary": {
            "status": summary_status,
            "label": summary_label,
            "text": summary_text,
            "freshness": freshness,
        },
        "lanes": ops_lanes,
        "actions": ops_actions,
        "max_source_count": max(1, max_source_count),
        "max_telegram_count": max(1, max_telegram_count),
    }


def query_system_health() -> dict[str, Any]:
    db_path = history_db_path()
    since = since_text(24)
    with open_readonly_connection() as conn:
        total_items = conn.execute("SELECT COUNT(*) FROM flash_history").fetchone()[0]
        today_t3 = conn.execute(
            "SELECT COUNT(*) FROM flash_history WHERE priority_level = 'T3_IMPORTANT' AND published_at >= ?",
            (since,),
        ).fetchone()[0]
        today_t2 = conn.execute(
            "SELECT COUNT(*) FROM flash_history WHERE priority_level = 'T2_HIGH' AND published_at >= ?",
            (since,),
        ).fetchone()[0]
        today_sent = conn.execute(
            "SELECT COUNT(*) FROM delivery_log WHERE sent_at >= ?",
            (since,),
        ).fetchone()[0]
        today_failed = conn.execute(
            "SELECT COUNT(*) FROM telegram_delivery_status WHERE status = 'failed' AND updated_at >= ?",
            (since,),
        ).fetchone()[0]
        source_rows = conn.execute(
            """
            SELECT source, MAX(published_at) AS latest_published_at, COUNT(*) AS count_24h
            FROM flash_history
            WHERE source IN ('ws', 'ws_initial', 'rest', 'catchup_auto', 'catchup_manual')
              AND published_at >= ?
            GROUP BY source
            """,
            (since,),
        ).fetchall()
        delivery_rows = conn.execute(
            """
            SELECT status, mode, message_id, detail, datetime(updated_at, 'localtime') AS updated_at
            FROM (
                SELECT status, mode, message_id, detail, updated_at,
                       ROW_NUMBER() OVER (PARTITION BY status ORDER BY updated_at DESC) AS rn
                FROM telegram_delivery_status
                WHERE status IN ('sent', 'unknown_timeout', 'failed')
            )
            WHERE rn = 1
            ORDER BY status
            """
        ).fetchall()
        delivery_count_rows = conn.execute(
            """
            SELECT status, COUNT(*) AS count_24h
            FROM telegram_delivery_status
            WHERE status IN ('sent', 'unknown_timeout', 'failed')
              AND updated_at >= ?
            GROUP BY status
            """,
            (since,),
        ).fetchall()
        catchup_summary_row = conn.execute(
            """
            SELECT status, mode, message_id, detail, datetime(updated_at, 'localtime') AS updated_at
            FROM telegram_delivery_status
            WHERE mode = 'catchup_summary'
            ORDER BY updated_at DESC
            LIMIT 1
            """
        ).fetchone()
        state_rows = conn.execute("SELECT key, value FROM runtime_state").fetchall()
    state = {str(row["key"]): str(row["value"]) for row in state_rows}
    sources = {str(row["source"]): row_to_dict(row) for row in source_rows}
    delivery_latest = {str(row["status"]): row_to_dict(row) for row in delivery_rows}
    delivery_counts = {str(row["status"]): int(row["count_24h"]) for row in delivery_count_rows}
    last_ingested_at = state.get("last_ingested_at", "")
    last_dt = parse_history_datetime(last_ingested_at)
    minutes_stale = round((datetime.now() - last_dt).total_seconds() / 60, 1) if last_dt else None
    if minutes_stale is None:
        monitor_status = "unknown"
    elif minutes_stale < 5:
        monitor_status = "ok"
    elif minutes_stale < 30:
        monitor_status = "warn"
    else:
        monitor_status = "error"
    realtime_sources = [
        {"key": "ws", "label": "WebSocket 实时", **sources.get("ws", {})},
        {"key": "ws_initial", "label": "WebSocket 初始历史", **sources.get("ws_initial", {})},
        {"key": "rest", "label": "REST 轮询", **sources.get("rest", {})},
        {"key": "catchup_auto", "label": "自动补拉", **sources.get("catchup_auto", {})},
        {"key": "catchup_manual", "label": "手动补拉", **sources.get("catchup_manual", {})},
    ]
    for source in realtime_sources:
        source.setdefault("latest_published_at", "")
        source.setdefault("count_24h", 0)

    rest_recent = sources.get("rest", {})
    rest_state = {
        "status": state.get("rest_status", ""),
        "forbidden_streak": state.get("rest_forbidden_streak", ""),
        "backoff_until": state.get("rest_backoff_until", ""),
        "last_error": state.get("rest_last_error", ""),
        "last_error_at": state.get("rest_last_error_at", ""),
        "last_ok_at": state.get("rest_last_ok_at", ""),
    }
    ws_initial_state = {
        "last_at": state.get("last_ws_initial_at", ""),
        "count": state.get("last_ws_initial_count", ""),
        "saved_count": state.get("last_ws_initial_saved_count", ""),
        "newest_published_at": state.get("last_ws_initial_newest_published_at", ""),
        "oldest_published_at": state.get("last_ws_initial_oldest_published_at", ""),
    }
    backoff_dt = parse_history_datetime(rest_state["backoff_until"])
    rest_state["backoff_remaining_seconds"] = (
        max(0, int((backoff_dt - datetime.now()).total_seconds())) if backoff_dt else 0
    )
    if rest_state["status"] == "forbidden_backoff":
        rest_status = "forbidden_backoff"
    elif rest_state["status"] == "ok":
        rest_status = "ok"
    elif rest_state["status"] == "error":
        rest_status = "error"
    else:
        rest_status = "recent" if rest_recent.get("latest_published_at") else "no_recent_success"

    system_notices = []
    if rest_status == "forbidden_backoff" and monitor_status == "ok":
        rest_notice = "REST 当前退避中，但 WebSocket 主路仍在入库；不要把 REST 状态误判为整体采集中断。"
        if rest_state["last_ok_at"]:
            rest_notice = "REST 曾间歇恢复后当前再次退避，但 WebSocket 主路仍在入库；不要把 REST 状态误判为整体采集中断。"
        system_notices.append({
            "level": "warn",
            "text": rest_notice,
        })
    try:
        ws_initial_saved_count = int(ws_initial_state["saved_count"] or 0)
    except ValueError:
        ws_initial_saved_count = 0
    if ws_initial_saved_count > 0:
        system_notices.append({
            "level": "info",
            "text": f"WebSocket 初始历史最近快照新入库 {ws_initial_saved_count} 条，可人工核对是否覆盖短缺口。",
        })
    ws_initial_newest_dt = parse_history_datetime(ws_initial_state["newest_published_at"])
    if ws_initial_newest_dt and last_dt and ws_initial_newest_dt > last_dt:
        system_notices.append({
            "level": "info",
            "text": "WebSocket 初始历史最新时间晚于最后入库游标，可能覆盖了实时短缺口；当前仅提示，不推进游标、不补发 Telegram。",
        })
    unknown_timeout_24h = delivery_counts.get("unknown_timeout", 0)
    if unknown_timeout_24h > 0:
        system_notices.append({
            "level": "warn",
            "text": f"24h 内 Telegram unknown_timeout {unknown_timeout_24h} 条，建议人工核对投递状态；当前不会自动重发，成功去重仍以 delivery_log 为准。",
        })
    telegram_counts = {
        "sent": delivery_counts.get("sent", 0),
        "unknown_timeout": unknown_timeout_24h,
        "failed": delivery_counts.get("failed", 0),
    }
    ops_overview = build_ops_overview(
        monitor_status=monitor_status,
        minutes_stale=minutes_stale,
        rest_status=rest_status,
        rest_state=rest_state,
        ws_initial_state=ws_initial_state,
        realtime_sources=realtime_sources,
        delivery_counts=telegram_counts,
    )
    return {
        "monitor_status": monitor_status,
        "minutes_stale": minutes_stale,
        "last_ingested_at": last_ingested_at,
        "last_ingested_id": state.get("last_ingested_id", ""),
        "last_startup": state.get("last_startup_at", ""),
        "last_catchup_at": state.get("last_catchup_at", ""),
        "last_gap_summary_telegram_at": state.get("last_gap_summary_telegram_at", ""),
        "db_path": str(db_path),
        "db_size_mb": round(db_path.stat().st_size / 1024 / 1024, 2) if db_path.exists() else 0,
        "total_items": total_items,
        "today_t3": today_t3,
        "today_t2": today_t2,
        "today_sent": today_sent,
        "today_failed": today_failed,
        "today_unknown_timeout": unknown_timeout_24h,
        "realtime_sources": realtime_sources,
        "rest_status": rest_status,
        "rest_state": rest_state,
        "ws_initial_state": ws_initial_state,
        "system_notices": system_notices,
        "telegram_counts": telegram_counts,
        "ops_overview": ops_overview,
        "delivery_latest": delivery_latest,
        "catchup_summary_latest": row_to_dict(catchup_summary_row) if catchup_summary_row else {},
    }


def query_nav_summary() -> dict[str, Any]:
    try:
        with open_readonly_connection() as conn:
            since = since_text(24)
            t3 = conn.execute(
                "SELECT COUNT(*) FROM flash_history WHERE priority_level = 'T3_IMPORTANT' AND published_at >= ?",
                (since,),
            ).fetchone()[0]
            total = conn.execute(
                "SELECT COUNT(*) FROM flash_history WHERE published_at >= ?",
                (since,),
            ).fetchone()[0]
        return {"ok": True, "t3": t3, "total": total}
    except (FileNotFoundError, sqlite3.Error):
        return {"ok": False, "t3": 0, "total": 0}


def query_aggregation_report() -> dict[str, Any]:
    import re

    since_7d = since_text(24 * 7)
    agg_enabled = os.getenv("AGGREGATION_V2", "0").lower() in {"1", "true", "yes", "on"}
    agg_window_seconds = env_int("AGGREGATION_WINDOW_SECONDS", 180, 1, 3600)
    agg_bypass_important = os.getenv("AGGREGATION_BYPASS_IMPORTANT", "1").lower() not in {
        "0",
        "false",
        "no",
        "off",
    }
    similar_pattern = re.compile(r"similar_to=(\S+)")

    with open_readonly_connection() as conn:
        skipped_7d = conn.execute(
            """
            SELECT COUNT(*)
            FROM telegram_delivery_status
            WHERE status = 'skipped' AND updated_at >= ?
            """,
            (since_7d,),
        ).fetchone()[0]
        rows = conn.execute(
            """
            SELECT t.message_id, t.detail, t.updated_at, t.mode,
                   h.title, h.content, h.published_at, h.priority_level
            FROM telegram_delivery_status t
            LEFT JOIN flash_history h ON h.id = t.message_id
            WHERE t.status = 'skipped'
            ORDER BY t.updated_at DESC
            LIMIT 60
            """
        ).fetchall()

        skip_records = []
        similar_ids = set()
        for row in rows:
            detail = str(row["detail"] or "")
            match = similar_pattern.search(detail)
            similar_to_id = match.group(1) if match else ""
            if similar_to_id:
                similar_ids.add(similar_to_id)
            record = row_to_dict(row)
            record["similar_to_id"] = similar_to_id
            record["summary"] = (str(row["title"] or "") or str(row["content"] or ""))[:100]
            skip_records.append(record)

        similar_items = {}
        if similar_ids:
            placeholders = ",".join("?" for _item in similar_ids)
            similar_rows = conn.execute(
                f"""
                SELECT id, published_at, title, content, priority_level
                FROM flash_history
                WHERE id IN ({placeholders})
                """,
                list(similar_ids),
            ).fetchall()
            similar_items = {str(row["id"]): row_to_dict(row) for row in similar_rows}

        daily_rows = conn.execute(
            """
            SELECT strftime('%Y-%m-%d', updated_at) AS day, COUNT(*) AS count
            FROM telegram_delivery_status
            WHERE status = 'skipped' AND updated_at >= ?
            GROUP BY day
            ORDER BY day DESC
            """,
            (since_7d,),
        ).fetchall()

    return {
        "agg_enabled": agg_enabled,
        "agg_window_seconds": agg_window_seconds,
        "agg_bypass_important": agg_bypass_important,
        "skipped_7d": skipped_7d,
        "skip_records": skip_records,
        "similar_items": similar_items,
        "daily_counts": [row_to_dict(row) for row in daily_rows],
    }
