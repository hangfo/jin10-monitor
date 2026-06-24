import sqlite3
from datetime import datetime, timedelta

import pytest

from dashboard.app import datetime_local_value, feed_params, normalize_datetime_input, parse_int
from dashboard import db


def history_ts(minutes_delta=0):
    return (datetime.now() + timedelta(minutes=minutes_delta)).strftime("%Y-%m-%d %H:%M:%S")


def create_dashboard_schema(db_path):
    conn = sqlite3.connect(db_path)
    conn.executescript(
        """
        CREATE TABLE flash_history (
            id TEXT PRIMARY KEY,
            published_at TEXT,
            title TEXT,
            content TEXT,
            hit INTEGER,
            high INTEGER,
            important INTEGER,
            has_bold INTEGER,
            priority_level TEXT,
            has_pic INTEGER,
            pic_url TEXT,
            news_source TEXT,
            source_url TEXT,
            source TEXT,
            created_at TEXT
        );
        CREATE TABLE runtime_state (key TEXT PRIMARY KEY, value TEXT);
        CREATE TABLE delivery_log (message_id TEXT, sent_at TEXT);
        CREATE TABLE telegram_delivery_status (
            message_id TEXT,
            channel TEXT,
            mode TEXT,
            status TEXT,
            detail TEXT,
            updated_at TEXT
        );
        """
    )
    conn.commit()
    return conn


def insert_flash(conn, item_id, published_at, title, priority="T1_NORMAL"):
    conn.execute(
        """
        INSERT INTO flash_history (
            id, published_at, title, content, hit, high, important, has_bold,
            priority_level, has_pic, pic_url, news_source, source_url, source, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            item_id,
            published_at,
            title,
            f"{title} content",
            1,
            0,
            0,
            0,
            priority,
            0,
            "",
            "金十数据",
            "",
            "rest",
            published_at,
        ),
    )


@pytest.fixture()
def dashboard_history_db(tmp_path, monkeypatch):
    db_path = tmp_path / "dashboard-history.sqlite3"
    conn = create_dashboard_schema(db_path)
    insert_flash(conn, "dash-1", history_ts(-10), "Dashboard title")
    conn.execute(
        """
        INSERT INTO telegram_delivery_status (
            message_id, channel, mode, status, detail, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        ("dash-1", "telegram", "realtime", "sent", "", history_ts(-9)),
    )
    conn.commit()
    conn.close()
    monkeypatch.setenv("HISTORY_DB", str(db_path))
    return db_path


def test_history_health_reports_ok_for_expected_schema(dashboard_history_db):
    health = db.history_health()

    assert health["status"] == "ok"
    assert health["history_db_exists"] is True
    assert health["missing_tables"] == []
    assert health["writes_business_db"] is False
    assert health["calls_jin10_rest"] is False
    assert health["sends_telegram"] is False


def test_open_readonly_connection_rejects_writes(dashboard_history_db):
    with db.open_readonly_connection() as conn:
        with pytest.raises(sqlite3.OperationalError):
            conn.execute("INSERT INTO runtime_state (key, value) VALUES ('x', 'y')")


def test_query_recent_items_reads_latest_status(dashboard_history_db):
    rows = db.query_recent_items(limit=10, with_status=True)

    assert len(rows) == 1
    assert rows[0]["id"] == "dash-1"
    assert rows[0]["telegram_status"] == "sent"
    assert rows[0]["telegram_mode"] == "realtime"
    assert rows[0]["has_title"] == ""
    assert rows[0]["style_flags"] == ""


def test_query_recent_items_filters_confirmed_telegram_delivery(dashboard_history_db):
    rows = db.query_recent_items(limit=10, tg_sent_only=True)
    assert rows == []

    conn = sqlite3.connect(dashboard_history_db)
    conn.execute(
        "INSERT INTO delivery_log (message_id, sent_at) VALUES (?, ?)",
        ("dash-1", history_ts(-9)),
    )
    conn.commit()
    conn.close()

    rows = db.query_recent_items(limit=10, tg_sent_only=True)

    assert len(rows) == 1
    assert rows[0]["id"] == "dash-1"
    assert rows[0]["tg_confirmed_sent"] == 1


def test_query_tg_deliveries_marks_delivery_log_confirmation(dashboard_history_db):
    conn = sqlite3.connect(dashboard_history_db)
    insert_flash(conn, "timeout-confirmed", history_ts(-4), "Confirmed timeout title")
    insert_flash(conn, "timeout-open", history_ts(-3), "Open timeout title")
    conn.executemany(
        """
        INSERT INTO telegram_delivery_status (
            message_id, channel, mode, status, detail, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        [
            ("timeout-confirmed", "telegram", "realtime", "unknown_timeout", "timeout", history_ts(-4)),
            ("timeout-open", "telegram", "realtime", "unknown_timeout", "timeout", history_ts(-3)),
        ],
    )
    conn.execute(
        "INSERT INTO delivery_log (message_id, sent_at) VALUES (?, ?)",
        ("timeout-confirmed", history_ts(-2)),
    )
    conn.commit()
    conn.close()

    rows = db.query_tg_deliveries(status_filter="unknown_timeout")
    by_id = {row["message_id"]: row for row in rows}
    summary = db.query_tg_summary()

    assert by_id["timeout-confirmed"]["confirmed_sent"] == 1
    assert by_id["timeout-confirmed"]["confirmed_sent_at"]
    assert by_id["timeout-open"]["confirmed_sent"] == 0
    assert summary["unknown_timeout"] == 2
    assert summary["unknown_timeout_confirmed"] == 1
    assert summary["unknown_timeout_unconfirmed"] == 1


def test_query_ws_initial_review_marks_cursor_and_delivery_state(dashboard_history_db):
    conn = sqlite3.connect(dashboard_history_db)
    insert_flash(conn, "ws-initial-new", history_ts(-2), "Initial newer title", priority="T2_HIGH")
    insert_flash(conn, "ws-initial-old", history_ts(-12), "Initial older title")
    conn.execute("UPDATE flash_history SET source = ? WHERE id = ?", ("ws_initial", "ws-initial-new"))
    conn.execute("UPDATE flash_history SET source = ? WHERE id = ?", ("ws_initial", "ws-initial-old"))
    conn.executemany(
        "INSERT INTO runtime_state (key, value) VALUES (?, ?)",
        [
            ("last_ingested_at", history_ts(-5)),
            ("last_ingested_id", "cursor-id"),
            ("last_ws_initial_at", history_ts(-1)),
            ("last_ws_initial_count", "40"),
            ("last_ws_initial_saved_count", "2"),
            ("last_ws_initial_oldest_published_at", history_ts(-12)),
            ("last_ws_initial_newest_published_at", history_ts(-2)),
        ],
    )
    conn.execute(
        """
        INSERT INTO telegram_delivery_status (
            message_id, channel, mode, status, detail, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        ("ws-initial-new", "telegram", "realtime", "sent", "", history_ts(-1)),
    )
    conn.execute(
        "INSERT INTO delivery_log (message_id, sent_at) VALUES (?, ?)",
        ("ws-initial-new", history_ts(-1)),
    )
    conn.commit()
    conn.close()

    review = db.query_ws_initial_review()
    by_id = {item["id"]: item for item in review["items"]}

    assert review["state"]["last_ingested_id"] == "cursor-id"
    assert review["last_ingested_at"] == history_ts(-5)
    assert review["total_reviewed"] == 2
    assert review["newer_than_cursor"] == 1
    assert by_id["ws-initial-new"]["newer_than_cursor"] is True
    assert by_id["ws-initial-new"]["telegram_status"] == "sent"
    assert by_id["ws-initial-new"]["tg_confirmed_sent"] == 1
    assert by_id["ws-initial-old"]["newer_than_cursor"] is False


def test_query_recent_items_filters_keyword(dashboard_history_db):
    rows = db.query_recent_items(keyword="Dashboard")

    assert [row["id"] for row in rows] == ["dash-1"]
    assert db.query_recent_items(keyword="missing keyword") == []


def test_query_keyword_escapes_sql_like_wildcards(dashboard_history_db):
    conn = sqlite3.connect(dashboard_history_db)
    percent_ts = history_ts(-8)
    insert_flash(conn, "percent-literal", percent_ts, "BTC 50%收益")
    insert_flash(conn, "percent-wildcard", history_ts(-7), "BTC 50X收益")
    insert_flash(conn, "underscore-literal", history_ts(-6), "BTC_突破")
    insert_flash(conn, "underscore-wildcard", history_ts(-5), "BTCA突破")
    conn.commit()
    conn.close()

    assert [row["id"] for row in db.query_recent_items(keyword="50%收益")] == ["percent-literal"]
    assert [row["id"] for row in db.query_feed_page(keyword="BTC_突破")] == ["underscore-literal"]
    assert db.query_latest_published_at(keyword="50%收益") == percent_ts


def test_query_recent_items_clamps_limit(dashboard_history_db):
    rows = db.query_recent_items(limit=0)

    assert len(rows) == 1
    assert rows[0]["id"] == "dash-1"


def test_query_recent_items_filters_priority(dashboard_history_db):
    rows = db.query_recent_items(priority="T3_IMPORTANT")

    assert rows == []


def test_query_system_health_includes_realtime_pipeline_diagnostics(dashboard_history_db):
    conn = sqlite3.connect(dashboard_history_db)
    insert_flash(conn, "ws-1", history_ts(-4), "WebSocket title")
    conn.execute("UPDATE flash_history SET source = ? WHERE id = ?", ("ws", "ws-1"))
    insert_flash(conn, "catchup-1", history_ts(-30), "Catchup title")
    conn.execute("UPDATE flash_history SET source = ? WHERE id = ?", ("catchup_auto", "catchup-1"))
    conn.executemany(
        "INSERT INTO runtime_state (key, value) VALUES (?, ?)",
        [
            ("last_ingested_at", history_ts(-4)),
            ("last_ingested_id", "ws-1"),
            ("last_startup_at", history_ts(-60)),
            ("last_catchup_at", history_ts(-30)),
            ("last_gap_summary_telegram_at", history_ts(-20)),
            ("last_ws_initial_at", history_ts(-1)),
            ("last_ws_initial_count", "40"),
            ("last_ws_initial_saved_count", "3"),
            ("last_ws_initial_newest_published_at", history_ts(-2)),
            ("last_ws_initial_oldest_published_at", history_ts(-12)),
        ],
    )
    conn.executemany(
        """
        INSERT INTO telegram_delivery_status (
            message_id, channel, mode, status, detail, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        [
            ("ws-1", "telegram", "realtime", "sent", "", history_ts(-3)),
            ("timeout-1", "telegram", "realtime", "unknown_timeout", "timeout", history_ts(-2)),
            ("failed-1", "telegram", "catchup", "failed", "bad request", history_ts(-1)),
            (
                "catchup_summary:gap:start:end",
                "telegram",
                "catchup_summary",
                "sent",
                "stored=1",
                history_ts(-1),
            ),
        ],
    )
    conn.commit()
    conn.close()

    health = db.query_system_health()

    assert health["last_ingested_id"] == "ws-1"
    assert health["last_startup"]
    assert health["last_catchup_at"]
    assert health["last_gap_summary_telegram_at"]
    sources = {source["key"]: source for source in health["realtime_sources"]}
    assert sources["ws"]["count_24h"] == 1
    assert sources["ws"]["latest_published_at"]
    assert sources["rest"]["count_24h"] == 1
    assert health["rest_status"] == "recent"
    assert health["today_unknown_timeout"] == 1
    assert health["delivery_latest"]["sent"]["message_id"] in {"ws-1", "catchup_summary:gap:start:end"}
    assert health["delivery_latest"]["unknown_timeout"]["message_id"] == "timeout-1"
    assert health["delivery_latest"]["failed"]["message_id"] == "failed-1"
    assert health["catchup_summary_latest"]["message_id"] == "catchup_summary:gap:start:end"
    assert health["telegram_counts"] == {
        "sent": 3,
        "unknown_timeout": 1,
        "unknown_timeout_confirmed": 0,
        "unknown_timeout_unconfirmed": 1,
        "failed": 1,
    }
    assert health["ws_initial_state"]["last_at"]
    assert health["ws_initial_state"]["count"] == "40"
    assert health["ws_initial_state"]["saved_count"] == "3"
    assert health["ws_initial_state"]["newest_published_at"]
    assert health["ws_initial_state"]["oldest_published_at"]
    assert health["ops_overview"]["summary"]["status"] == "degraded"
    assert health["ops_overview"]["summary"]["label"] == "降级运行"
    lanes = {lane["key"]: lane for lane in health["ops_overview"]["lanes"]}
    assert lanes["ws"]["badge"] == "可信主路"
    assert lanes["ws_initial"]["headline"] == "最近快照新增 3 条"
    assert "非 24h 累计" in lanes["ws_initial"]["detail"]
    assert lanes["telegram"]["status"] == "warn"
    assert "待确认 1" in lanes["telegram"]["headline"]
    assert any("核对最近 Telegram unknown_timeout" in action for action in health["ops_overview"]["actions"])
    notice_text = "\n".join(notice["text"] for notice in health["system_notices"])
    assert "WebSocket 初始历史最近快照新入库 3 条" in notice_text
    assert "可能覆盖了实时短缺口" in notice_text
    assert "仍需人工核对 1 条" in notice_text
    assert "不会自动重发" in notice_text


def test_query_system_health_ignores_confirmed_unknown_timeout_for_degraded(dashboard_history_db):
    conn = sqlite3.connect(dashboard_history_db)
    conn.executemany(
        "INSERT INTO runtime_state (key, value) VALUES (?, ?)",
        [
            ("last_ingested_at", history_ts(-1)),
            ("last_ingested_id", "dash-1"),
        ],
    )
    conn.execute(
        """
        INSERT INTO telegram_delivery_status (
            message_id, channel, mode, status, detail, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        ("timeout-confirmed", "telegram", "realtime", "unknown_timeout", "timeout", history_ts(-2)),
    )
    conn.execute(
        "INSERT INTO delivery_log (message_id, sent_at) VALUES (?, ?)",
        ("timeout-confirmed", history_ts(-2)),
    )
    conn.commit()
    conn.close()

    health = db.query_system_health()
    lanes = {lane["key"]: lane for lane in health["ops_overview"]["lanes"]}

    assert health["telegram_counts"]["unknown_timeout"] == 1
    assert health["telegram_counts"]["unknown_timeout_confirmed"] == 1
    assert health["telegram_counts"]["unknown_timeout_unconfirmed"] == 0
    assert health["ops_overview"]["summary"]["status"] == "ok"
    assert lanes["telegram"]["status"] == "ok"
    assert "待确认 0" in lanes["telegram"]["headline"]
    assert not any("核对最近 Telegram unknown_timeout" in action for action in health["ops_overview"]["actions"])
    assert any("均已在 delivery_log 确认" in notice["text"] for notice in health["system_notices"])


def test_query_system_health_reads_persisted_rest_backoff_state(dashboard_history_db):
    conn = sqlite3.connect(dashboard_history_db)
    conn.executemany(
        "INSERT INTO runtime_state (key, value) VALUES (?, ?)",
        [
            ("last_ingested_at", history_ts(-1)),
            ("rest_status", "forbidden_backoff"),
            ("rest_forbidden_streak", "3"),
            ("rest_backoff_until", history_ts(5)),
            ("rest_last_error", "HTTP 403 4/4 entries; backoff 90s"),
            ("rest_last_error_at", history_ts(-1)),
            ("rest_last_ok_at", history_ts(-10)),
        ],
    )
    conn.commit()
    conn.close()

    health = db.query_system_health()

    assert health["rest_status"] == "forbidden_backoff"
    assert health["rest_state"]["status"] == "forbidden_backoff"
    assert health["rest_state"]["forbidden_streak"] == "3"
    assert health["rest_state"]["backoff_until"]
    assert health["rest_state"]["backoff_remaining_seconds"] > 0
    assert "HTTP 403" in health["rest_state"]["last_error"]
    assert health["ops_overview"]["summary"]["status"] == "degraded"
    assert health["ops_overview"]["summary"]["state_since"]
    assert health["ops_overview"]["summary"]["state_duration"]
    rest_lane = next(lane for lane in health["ops_overview"]["lanes"] if lane["key"] == "rest")
    assert rest_lane["badge"] == "当前退避"
    assert rest_lane["headline"] == "403 退避中"
    assert any("观察 REST 退避截止时间" in action for action in health["ops_overview"]["actions"])
    assert any("REST 曾间歇恢复后当前再次退避" in notice["text"] for notice in health["system_notices"])


def test_query_recent_monitor_log_events_reads_error_tail(tmp_path):
    log_path = tmp_path / "jin10-monitor.log"
    log_path.write_text(
        "\n".join(
            [
                "00:01:00 [INFO] normal line",
                "00:02:00 [ERROR] Telegram 超时，送达状态未知",
                "scripts/run_monitor.sh: line 1: Proxy: command not found",
            ]
        ),
        encoding="utf-8",
    )

    result = db.query_recent_monitor_log_events(path=log_path)

    assert result["exists"] is True
    assert result["path"] == str(log_path)
    assert [event["level"] for event in result["events"]] == ["SHELL", "ERROR"]
    assert "command not found" in result["events"][0]["line"]
    assert "Telegram 超时" in result["events"][1]["line"]


def test_query_recent_monitor_log_events_handles_missing_file(tmp_path):
    result = db.query_recent_monitor_log_events(path=tmp_path / "missing.log")

    assert result["path"] == str(tmp_path / "missing.log")
    assert result["exists"] is False
    assert result["events"] == []
    assert result["file_size_kb"] == 0
    assert result["last_modified"] == ""


def test_query_recent_monitor_log_events_captures_exception_suffix(tmp_path):
    log_path = tmp_path / "jin10-monitor.log"
    log_path.write_text(
        "\n".join(
            [
                "2026-06-22 08:00:00 INFO normal",
                "aiohttp.ClientConnectorError: Cannot connect to host",
                "asyncio.TimeoutError",
                "RuntimeError: db locked",
                "2026-06-22 08:01:00 INFO recovered",
            ]
        ),
        encoding="utf-8",
    )

    result = db.query_recent_monitor_log_events(path=log_path)
    lines = [event["line"] for event in result["events"]]

    assert any("ClientConnectorError" in line for line in lines)
    assert any("TimeoutError" in line for line in lines)
    assert any("RuntimeError" in line for line in lines)


def test_query_recent_monitor_log_events_aggregates_traceback_block(tmp_path):
    log_path = tmp_path / "jin10-monitor.log"
    log_path.write_text(
        "\n".join(
            [
                "2026-06-22 08:00:01 INFO starting",
                "2026-06-22 08:01:15 ERROR send failed",
                "Traceback (most recent call last):",
                '  File "jin10_monitor.py", line 1402, in send_telegram',
                "    await session.post(url)",
                "asyncio.TimeoutError",
                "2026-06-22 08:02:00 INFO recovered",
            ]
        ),
        encoding="utf-8",
    )

    result = db.query_recent_monitor_log_events(path=log_path)
    tracebacks = [event for event in result["events"] if "Traceback" in event["line"]]

    assert len(tracebacks) == 1
    assert tracebacks[0]["level"] == "ERROR"
    assert "TimeoutError" in tracebacks[0]["line"]
    assert "→" in tracebacks[0]["line"]


def test_query_recent_monitor_log_events_metadata_fields(tmp_path):
    log_path = tmp_path / "jin10-monitor.log"
    log_path.write_text("2026-06-22 09:00:00 ERROR test error\n", encoding="utf-8")

    result = db.query_recent_monitor_log_events(path=log_path)

    assert result["file_size_kb"] > 0
    assert result["last_modified"]
    assert result["events"][0]["ts"] == "2026-06-22 09:00:00"


def test_query_feed_page_applies_offset_limit_and_filters(dashboard_history_db):
    conn = sqlite3.connect(dashboard_history_db)
    insert_flash(conn, "dash-2", history_ts(-8), "Second Dashboard title")
    insert_flash(conn, "noise-1", history_ts(-7), "Other title")
    conn.commit()
    conn.close()

    rows = db.query_feed_page(offset=1, limit=1, keyword="Dashboard")

    assert [row["id"] for row in rows] == ["dash-1"]
    assert rows[0]["has_title"] == ""
    assert rows[0]["style_flags"] == ""


def test_same_second_feed_order_uses_message_id_tiebreaker(dashboard_history_db):
    same_second = history_ts(-5)
    conn = sqlite3.connect(dashboard_history_db)
    insert_flash(conn, "20260529090000000001", same_second, "same-second lower")
    insert_flash(conn, "20260529090000000002", same_second, "same-second upper")
    conn.execute(
        "UPDATE flash_history SET created_at = ? WHERE id = ?",
        (history_ts(-1), "20260529090000000001"),
    )
    conn.execute(
        "UPDATE flash_history SET created_at = ? WHERE id = ?",
        (history_ts(-20), "20260529090000000002"),
    )
    conn.commit()
    conn.close()

    recent_rows = db.query_recent_items(limit=2, keyword="same-second")
    page_rows = db.query_feed_page(offset=0, limit=2, keyword="same-second")
    latest_ts = db.query_latest_published_at(keyword="same-second")

    assert [row["id"] for row in recent_rows] == ["20260529090000000002", "20260529090000000001"]
    assert [row["id"] for row in page_rows] == ["20260529090000000002", "20260529090000000001"]
    assert latest_ts == same_second


def test_context_window_orders_same_second_items_by_message_id(dashboard_history_db):
    same_second = history_ts(-5)
    conn = sqlite3.connect(dashboard_history_db)
    insert_flash(conn, "20260529090000000001", same_second, "context lower")
    insert_flash(conn, "20260529090000000002", same_second, "context upper")
    conn.execute(
        "UPDATE flash_history SET created_at = ? WHERE id = ?",
        (history_ts(-1), "20260529090000000001"),
    )
    conn.execute(
        "UPDATE flash_history SET created_at = ? WHERE id = ?",
        (history_ts(-20), "20260529090000000002"),
    )
    conn.commit()
    conn.close()

    _center, rows = db.query_item_context("20260529090000000001", minutes=0)

    assert [row["id"] for row in rows] == ["20260529090000000001", "20260529090000000002"]


def test_query_keyword_heatmap_uses_configured_keywords(dashboard_history_db, monkeypatch):
    monkeypatch.setattr(db, "HIGH_PRIORITY", ["Dashboard"])
    monkeypatch.setattr(db, "KEYWORDS", ["Dashboard", "unused-custom-keyword"])

    rows = db.query_keyword_heatmap(hours=24)

    assert rows[0] == {"keyword": "Dashboard", "count": 1, "is_high": True}


def test_query_aggregation_report_is_readonly(dashboard_history_db):
    report = db.query_aggregation_report()

    assert report["agg_enabled"] is False
    assert report["skipped_7d"] == 0
    assert report["skipped_24h"] == 0
    assert len(report["hourly_counts"]) == 24
    assert all(slot["count"] == 0 for slot in report["hourly_counts"])
    assert report["skip_records"] == []


def test_query_aggregation_report_counts_skipped_records(dashboard_history_db):
    conn = sqlite3.connect(dashboard_history_db)
    conn.execute(
        """
        INSERT INTO telegram_delivery_status (message_id, mode, status, detail, updated_at)
        VALUES ('agg-t1','realtime','skipped','aggregation_v2 similar_to=old-1', datetime('now')),
               ('agg-t2','realtime','skipped','aggregation_v2 similar_to=old-1', datetime('now'))
        """
    )
    conn.commit()
    conn.close()

    report = db.query_aggregation_report()

    assert report["skipped_7d"] >= 2
    assert report["skipped_24h"] >= 2
    assert sum(slot["count"] for slot in report["hourly_counts"]) >= 2
    ids = {row["message_id"] for row in report["skip_records"]}
    assert {"agg-t1", "agg-t2"}.issubset(ids)


def test_query_item_context_returns_window(dashboard_history_db):
    conn = sqlite3.connect(dashboard_history_db)
    insert_flash(conn, "dash-before", history_ts(-15), "Before title")
    insert_flash(conn, "dash-after", history_ts(-1), "After title")
    insert_flash(conn, "dash-outside", history_ts(1), "Outside title")
    conn.commit()
    conn.close()

    center, rows = db.query_item_context("dash-1", minutes=10)

    assert center["id"] == "dash-1"
    assert [row["id"] for row in rows] == ["dash-before", "dash-1", "dash-after"]


def test_query_item_context_missing_item_returns_empty(dashboard_history_db):
    center, rows = db.query_item_context("missing-id", minutes=10)

    assert center is None
    assert rows == []


def test_parse_int_clamps_invalid_and_out_of_range_values():
    assert parse_int("bad", 80, 1, 300) == 80
    assert parse_int("0", 80, 1, 300) == 1
    assert parse_int("999", 80, 1, 300) == 300


def test_datetime_local_helpers_normalize_browser_values():
    assert normalize_datetime_input("2026-05-24T21:30") == "2026-05-24 21:30:00"
    assert normalize_datetime_input("2026-05-24 21:30:45") == "2026-05-24 21:30:45"
    assert datetime_local_value("2026-05-24 21:30:45") == "2026-05-24T21:30"


def test_feed_params_normalizes_query_values():
    class Request:
        query_params = {
            "priority": "bad",
            "limit": "999",
            "keyword": "Dashboard",
            "hours": "6",
            "tg_sent_only": "1",
            "with_status": "on",
        }

    params = feed_params(Request())

    assert params == {
        "limit": 300,
        "priority": "",
        "keyword": "Dashboard",
        "hours": 6,
        "tg_sent_only": True,
        "with_status": True,
    }


def test_missing_history_db_does_not_create_file(tmp_path, monkeypatch):
    missing_db = tmp_path / "missing-dashboard.sqlite3"
    monkeypatch.setenv("HISTORY_DB", str(missing_db))

    health = db.history_health()

    assert health["status"] == "missing_history_db"
    assert not missing_db.exists()
    with pytest.raises(FileNotFoundError):
        db.open_readonly_connection()
    assert not missing_db.exists()
