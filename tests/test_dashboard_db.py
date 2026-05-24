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
