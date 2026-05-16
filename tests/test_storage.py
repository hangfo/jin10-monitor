import sqlite3
from datetime import datetime, timedelta

import pytest

import jin10_monitor as jm


def news_item(item_id="storage-1", *, when=None, **data_overrides):
    data = {
        "title": "Title",
        "content": "Content",
    }
    data.update(data_overrides)
    return {
        "id": item_id,
        "time": (when or datetime.now().replace(microsecond=0)).strftime("%Y-%m-%d %H:%M:%S"),
        "data": data,
    }


def close_thread_db():
    conn = getattr(jm._db_local, "conn", None)
    if conn is not None:
        conn.close()
        delattr(jm._db_local, "conn")


@pytest.fixture()
def temp_history_db(tmp_path, monkeypatch):
    close_thread_db()
    db_path = tmp_path / "history.sqlite3"
    monkeypatch.setattr(jm, "HISTORY_DB", db_path)
    jm.init_history_db()
    yield db_path
    close_thread_db()


def row_by_id(conn, item_id):
    conn.row_factory = sqlite3.Row
    return conn.execute("SELECT * FROM flash_history WHERE id = ?", (item_id,)).fetchone()


def state_value(conn, key):
    row = conn.execute("SELECT value FROM runtime_state WHERE key = ?", (key,)).fetchone()
    return row[0] if row else ""


def test_save_history_item_preserves_first_source_and_prevents_priority_downgrade(temp_history_db):
    high_item = news_item("same-id", title="<b>High title</b>", content="High content")
    normal_item = news_item("same-id", title="Normal title", content="Normal content")

    jm.save_history_item(
        high_item,
        hit=True,
        high=True,
        source="ws",
        priority_level=jm.PRIORITY_HIGH,
    )
    jm.save_history_item(
        normal_item,
        hit=True,
        high=False,
        source="rest",
        priority_level=jm.PRIORITY_NORMAL,
    )

    conn = sqlite3.connect(temp_history_db)
    row = row_by_id(conn, "same-id")

    assert row["source"] == "ws"
    assert row["hit"] == 1
    assert row["high"] == 1
    assert row["has_bold"] == 1
    assert row["priority_level"] == jm.PRIORITY_HIGH
    assert row["title"] == "Normal title"


def test_save_history_item_allows_priority_upgrade_without_changing_first_source(temp_history_db):
    normal_item = news_item("upgrade-id", title="Normal title", content="Normal content")
    important_item = {
        **news_item("upgrade-id", title="Important title", content="Important content"),
        "important": True,
    }

    jm.save_history_item(
        normal_item,
        hit=True,
        high=False,
        source="rest",
        priority_level=jm.PRIORITY_NORMAL,
    )
    jm.save_history_item(
        important_item,
        hit=True,
        high=True,
        source="ws",
        priority_level=jm.PRIORITY_IMPORTANT,
    )

    conn = sqlite3.connect(temp_history_db)
    row = row_by_id(conn, "upgrade-id")

    assert row["source"] == "rest"
    assert row["hit"] == 1
    assert row["high"] == 1
    assert row["important"] == 1
    assert row["priority_level"] == jm.PRIORITY_IMPORTANT
    assert row["title"] == "Important title"


def test_update_ingest_cursor_commits_state_to_disk(temp_history_db):
    item_dt = datetime.now().replace(microsecond=0) - timedelta(seconds=5)
    item = news_item("cursor-id", when=item_dt)

    jm.update_ingest_cursor(item)
    close_thread_db()

    conn = sqlite3.connect(temp_history_db)
    assert state_value(conn, "last_ingested_at") == item_dt.strftime("%Y-%m-%d %H:%M:%S")
    assert state_value(conn, "last_ingested_id") == "cursor-id"


def test_update_ingest_cursor_skips_far_future_items(temp_history_db):
    future_item = news_item("future-id", when=datetime(2999, 1, 1, 0, 0, 0))

    jm.update_ingest_cursor(future_item)

    conn = sqlite3.connect(temp_history_db)
    assert state_value(conn, "last_ingested_at") == ""
    assert state_value(conn, "last_ingested_id") == ""


def test_mark_delivery_records_sent_message_for_dedupe(temp_history_db):
    conn = jm.get_db()

    assert not jm.has_any_delivery(conn, "delivered-id", channel="telegram")

    jm.mark_delivery(conn, "delivered-id", channel="telegram", mode="realtime")
    conn.commit()

    assert jm.has_delivery(conn, "delivered-id", channel="telegram", mode="realtime")
    assert jm.has_any_delivery(conn, "delivered-id", channel="telegram")


def test_delivery_status_does_not_create_delivery_log_dedupe_record(temp_history_db):
    conn = jm.get_db()

    jm.record_telegram_delivery_status(
        conn,
        "status-only-id",
        mode="catchup",
        status=jm.TELEGRAM_STATUS_UNKNOWN_TIMEOUT,
        detail="timeout",
    )
    conn.commit()

    assert not jm.has_any_delivery(conn, "status-only-id", channel="telegram")
    status = conn.execute(
        """
        SELECT status, detail
        FROM telegram_delivery_status
        WHERE message_id = ? AND channel = ? AND mode = ?
        """,
        ("status-only-id", "telegram", "catchup"),
    ).fetchone()
    assert status == (jm.TELEGRAM_STATUS_UNKNOWN_TIMEOUT, "timeout")


def test_select_catchup_send_candidates_skips_already_delivered_rows():
    rows = [
        {
            "id": "already-sent",
            "should_push": True,
            "already_delivered": True,
            "priority_level": jm.PRIORITY_HIGH,
        },
        {
            "id": "new-important",
            "should_push": True,
            "already_delivered": False,
            "priority_level": jm.PRIORITY_IMPORTANT,
        },
        {
            "id": "new-normal",
            "should_push": True,
            "already_delivered": False,
            "priority_level": jm.PRIORITY_NORMAL,
        },
    ]

    selected = jm.select_catchup_send_candidates(rows, max_send=2)

    assert [row["id"] for row in selected] == ["new-important", "new-normal"]


def test_catch_up_window_filters_window_and_skips_delivered_candidates(temp_history_db, monkeypatch):
    start_dt = datetime(2026, 5, 17, 10, 0, 0)
    end_dt = datetime(2026, 5, 17, 10, 10, 0)
    existing = news_item("existing", when=datetime(2026, 5, 17, 10, 8, 0), content="plain")
    delivered = news_item("delivered", when=datetime(2026, 5, 17, 10, 7, 0), content="hit")
    fresh = news_item("fresh", when=datetime(2026, 5, 17, 10, 6, 0), content="urgent")
    page = [
        news_item("too-new", when=datetime(2026, 5, 17, 10, 11, 0), content="hit"),
        existing,
        delivered,
        fresh,
        news_item("too-old", when=datetime(2026, 5, 17, 9, 59, 0), content="hit"),
    ]
    jm.save_history_item(existing, hit=False, high=False, source="rest", priority_level=jm.PRIORITY_NONE)
    conn = jm.get_db()
    jm.mark_delivery(conn, "delivered", channel="telegram", mode="catchup")
    conn.commit()

    monkeypatch.setattr(jm, "APP_IDS", ["test-app"])
    monkeypatch.setattr(jm, "KEYWORDS", ["hit", "urgent"])
    monkeypatch.setattr(jm, "HIGH_PRIORITY", ["urgent"])
    monkeypatch.setattr(jm, "fetch_page_sync", lambda cursor, app_id: page)

    result = jm.catch_up_window(
        start_dt,
        end_dt,
        source="catchup_test",
        max_store=10,
        max_send=10,
        sleep_s=0,
    )

    assert result["ok"] is True
    assert result["pages"] == 1
    assert result["scanned"] == 3
    assert result["stored"] == 2
    assert result["already_stored"] == 1
    assert result["already_delivered"] == 1
    assert result["push_candidates"] == 2
    assert result["seen_item_ids"] == ["fresh", "delivered", "existing"]
    assert [row["id"] for row in result["send_candidates"]] == ["fresh"]


def test_catch_up_window_respects_max_store_truncation(temp_history_db, monkeypatch):
    start_dt = datetime(2026, 5, 17, 10, 0, 0)
    end_dt = datetime(2026, 5, 17, 10, 10, 0)
    page = [
        news_item("first", when=datetime(2026, 5, 17, 10, 9, 0), content="hit"),
        news_item("second", when=datetime(2026, 5, 17, 10, 8, 0), content="hit"),
    ]

    monkeypatch.setattr(jm, "APP_IDS", ["test-app"])
    monkeypatch.setattr(jm, "KEYWORDS", ["hit"])
    monkeypatch.setattr(jm, "HIGH_PRIORITY", [])
    monkeypatch.setattr(jm, "fetch_page_sync", lambda cursor, app_id: page)

    result = jm.catch_up_window(
        start_dt,
        end_dt,
        source="catchup_test",
        max_store=1,
        max_send=10,
        sleep_s=0,
    )

    assert result["ok"] is True
    assert result["truncated"] is True
    assert result["scanned"] == 1
    assert result["stored"] == 1
    assert result["seen_item_ids"] == ["first"]


def test_catch_up_window_advances_cursor_between_pages(temp_history_db, monkeypatch):
    start_dt = datetime(2026, 5, 17, 10, 0, 0)
    end_dt = datetime(2026, 5, 17, 10, 10, 0)
    first_page = [
        news_item("page1-new", when=datetime(2026, 5, 17, 10, 9, 0), content="hit"),
        news_item("page1-old", when=datetime(2026, 5, 17, 10, 5, 0), content="hit"),
    ]
    second_page = [
        news_item("page2-new", when=datetime(2026, 5, 17, 10, 4, 0), content="hit"),
        news_item("page2-old", when=datetime(2026, 5, 17, 9, 59, 0), content="hit"),
    ]
    cursors = []

    def fake_fetch_page(cursor, app_id):
        cursors.append(cursor)
        return first_page if len(cursors) == 1 else second_page

    monkeypatch.setattr(jm, "APP_IDS", ["test-app"])
    monkeypatch.setattr(jm, "KEYWORDS", ["hit"])
    monkeypatch.setattr(jm, "HIGH_PRIORITY", [])
    monkeypatch.setattr(jm, "fetch_page_sync", fake_fetch_page)
    monkeypatch.setattr(jm.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(jm.random, "uniform", lambda start, end: 0)

    result = jm.catch_up_window(
        start_dt,
        end_dt,
        source="catchup_test",
        max_store=10,
        max_send=10,
        sleep_s=0,
    )

    assert result["ok"] is True
    assert result["pages"] == 2
    assert cursors == ["2026-05-17 10:11:00", "2026-05-17 10:04:59"]
    assert result["seen_item_ids"] == ["page2-new", "page1-old", "page1-new"]
