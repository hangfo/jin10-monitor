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


def test_query_recent_items_filters_keyword(dashboard_history_db):
    rows = db.query_recent_items(keyword="Dashboard")

    assert [row["id"] for row in rows] == ["dash-1"]
    assert db.query_recent_items(keyword="missing keyword") == []


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
    assert health["delivery_latest"]["sent"]["message_id"] in {"ws-1", "catchup_summary:gap:start:end"}
    assert health["delivery_latest"]["unknown_timeout"]["message_id"] == "timeout-1"
    assert health["delivery_latest"]["failed"]["message_id"] == "failed-1"
    assert health["catchup_summary_latest"]["message_id"] == "catchup_summary:gap:start:end"


def test_query_system_health_reads_persisted_rest_backoff_state(dashboard_history_db):
    conn = sqlite3.connect(dashboard_history_db)
    conn.executemany(
        "INSERT INTO runtime_state (key, value) VALUES (?, ?)",
        [
            ("rest_status", "forbidden_backoff"),
            ("rest_forbidden_streak", "3"),
            ("rest_backoff_until", history_ts(5)),
            ("rest_last_error", "HTTP 403 4/4 entries; backoff 90s"),
            ("rest_last_error_at", history_ts(-1)),
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
    assert report["skip_records"] == []


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
