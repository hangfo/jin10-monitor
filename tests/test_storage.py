import asyncio
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


class StopPollLoop(Exception):
    pass


def fake_datetime_from(times):
    timeline = list(times)

    class FakeDatetime:
        @classmethod
        def now(cls):
            if len(timeline) > 1:
                return timeline.pop(0)
            return timeline[0]

    return FakeDatetime


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


def telegram_status(conn, message_id, mode="catchup"):
    row = conn.execute(
        """
        SELECT status, detail
        FROM telegram_delivery_status
        WHERE message_id = ? AND channel = ? AND mode = ?
        """,
        (message_id, "telegram", mode),
    ).fetchone()
    return tuple(row) if row else None


def manual_catchup_result(candidate_id="manual-candidate", *, status_item=None):
    item = status_item or news_item(candidate_id, content="hit")
    return {
        "ok": True,
        "stored": 1,
        "truncated": False,
        "window": {
            "start": "2026-05-17 10:00:00",
            "end": "2026-05-17 10:10:00",
        },
        "push_candidates": 1,
        "send_candidates": [
            {
                "id": candidate_id,
                "item": item,
                "priority_level": jm.PRIORITY_NORMAL,
            }
        ],
    }


def manual_catchup_result_for_ids(candidate_ids):
    result = manual_catchup_result(candidate_ids[0])
    result["push_candidates"] = len(candidate_ids)
    result["send_candidates"] = [
        {
            "id": candidate_id,
            "item": news_item(candidate_id, content="hit"),
            "priority_level": jm.PRIORITY_NORMAL,
        }
        for candidate_id in candidate_ids
    ]
    return result


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


def test_handle_item_marks_realtime_delivery_after_successful_send(temp_history_db, monkeypatch):
    item = news_item("realtime-sent", content="hit")
    sent_messages = []

    async def fake_send_telegram(session, text):
        sent_messages.append(text)
        return jm.TelegramSendResult(jm.TELEGRAM_STATUS_SENT)

    monkeypatch.setattr(jm, "KEYWORDS", ["hit"])
    monkeypatch.setattr(jm, "HIGH_PRIORITY", [])
    monkeypatch.setattr(jm, "send_telegram", fake_send_telegram)

    asyncio.run(jm.handle_item(object(), item, source="rest"))

    conn = jm.get_db()
    row = row_by_id(conn, "realtime-sent")
    assert row["source"] == "rest"
    assert row["hit"] == 1
    assert row["priority_level"] == jm.PRIORITY_NORMAL
    assert len(sent_messages) == 1
    assert jm.has_delivery(conn, "realtime-sent", channel="telegram", mode="realtime")
    assert telegram_status(conn, "realtime-sent", mode="realtime") == (jm.TELEGRAM_STATUS_SENT, "")


def test_handle_item_records_failed_realtime_status_without_delivery_log(temp_history_db, monkeypatch):
    item = news_item("realtime-failed", content="hit")

    async def fake_send_telegram(session, text):
        return jm.TelegramSendResult(jm.TELEGRAM_STATUS_FAILED, "status=500")

    monkeypatch.setattr(jm, "KEYWORDS", ["hit"])
    monkeypatch.setattr(jm, "HIGH_PRIORITY", [])
    monkeypatch.setattr(jm, "send_telegram", fake_send_telegram)

    asyncio.run(jm.handle_item(object(), item, source="rest"))

    conn = jm.get_db()
    assert row_by_id(conn, "realtime-failed")["hit"] == 1
    assert not jm.has_any_delivery(conn, "realtime-failed", channel="telegram")
    assert telegram_status(conn, "realtime-failed", mode="realtime") == (
        jm.TELEGRAM_STATUS_FAILED,
        "status=500",
    )


def test_handle_item_stores_unmatched_item_without_sending(temp_history_db, monkeypatch):
    item = news_item("realtime-unmatched", content="plain")

    async def fail_send_telegram(session, text):
        raise AssertionError("unmatched realtime item should not send Telegram")

    monkeypatch.setattr(jm, "KEYWORDS", ["hit"])
    monkeypatch.setattr(jm, "HIGH_PRIORITY", [])
    monkeypatch.setattr(jm, "send_telegram", fail_send_telegram)

    asyncio.run(jm.handle_item(object(), item, source="rest"))

    conn = jm.get_db()
    row = row_by_id(conn, "realtime-unmatched")
    assert row["source"] == "rest"
    assert row["hit"] == 0
    assert row["priority_level"] == jm.PRIORITY_NONE
    assert not jm.has_any_delivery(conn, "realtime-unmatched", channel="telegram")
    assert telegram_status(conn, "realtime-unmatched", mode="realtime") is None


def test_handle_item_suppresses_similar_realtime_pushes_after_success(temp_history_db, monkeypatch):
    first = news_item("aggregate-first", title="Oil supply hit", content="hit", source="Reuters")
    second = news_item("aggregate-second", title="Oil supply hit", content="hit update", source="Reuters")
    sent_messages = []
    jm.aggregation_recent.clear()

    async def fake_send_telegram(session, text):
        sent_messages.append(text)
        return jm.TelegramSendResult(jm.TELEGRAM_STATUS_SENT)

    monkeypatch.setattr(jm, "KEYWORDS", ["hit"])
    monkeypatch.setattr(jm, "HIGH_PRIORITY", [])
    monkeypatch.setattr(jm, "AGGREGATION_V2", True)
    monkeypatch.setattr(jm, "AGGREGATION_WINDOW_SECONDS", 180)
    monkeypatch.setattr(jm, "AGGREGATION_BYPASS_IMPORTANT", True)
    monkeypatch.setattr(jm, "send_telegram", fake_send_telegram)

    asyncio.run(jm.handle_item(object(), first, source="rest"))
    asyncio.run(jm.handle_item(object(), second, source="rest"))

    conn = jm.get_db()
    assert len(sent_messages) == 1
    assert jm.has_delivery(conn, "aggregate-first", channel="telegram", mode="realtime")
    assert not jm.has_any_delivery(conn, "aggregate-second", channel="telegram")
    assert telegram_status(conn, "aggregate-first", mode="realtime") == (jm.TELEGRAM_STATUS_SENT, "")
    second_status = telegram_status(conn, "aggregate-second", mode="realtime")
    assert second_status[0] == jm.TELEGRAM_STATUS_SKIPPED
    assert "aggregation_v2 similar_to=aggregate-first" in second_status[1]


def test_handle_item_bypasses_aggregation_for_important_realtime_items(temp_history_db, monkeypatch):
    first = {
        **news_item("aggregate-important-1", title="Gold move hit", content="hit", source="Reuters"),
        "important": True,
    }
    second = {
        **news_item("aggregate-important-2", title="Gold move hit", content="hit update", source="Reuters"),
        "important": True,
    }
    sent_messages = []
    jm.aggregation_recent.clear()

    async def fake_send_telegram(session, text):
        sent_messages.append(text)
        return jm.TelegramSendResult(jm.TELEGRAM_STATUS_SENT)

    monkeypatch.setattr(jm, "KEYWORDS", ["hit"])
    monkeypatch.setattr(jm, "HIGH_PRIORITY", [])
    monkeypatch.setattr(jm, "PUSH_IMPORTANT", True)
    monkeypatch.setattr(jm, "AGGREGATION_V2", True)
    monkeypatch.setattr(jm, "AGGREGATION_WINDOW_SECONDS", 180)
    monkeypatch.setattr(jm, "AGGREGATION_BYPASS_IMPORTANT", True)
    monkeypatch.setattr(jm, "send_telegram", fake_send_telegram)

    asyncio.run(jm.handle_item(object(), first, source="rest"))
    asyncio.run(jm.handle_item(object(), second, source="rest"))

    conn = jm.get_db()
    assert len(sent_messages) == 2
    assert jm.has_delivery(conn, "aggregate-important-1", channel="telegram", mode="realtime")
    assert jm.has_delivery(conn, "aggregate-important-2", channel="telegram", mode="realtime")
    assert telegram_status(conn, "aggregate-important-1", mode="realtime") == (jm.TELEGRAM_STATUS_SENT, "")
    assert telegram_status(conn, "aggregate-important-2", mode="realtime") == (jm.TELEGRAM_STATUS_SENT, "")


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


def test_query_context_returns_window_around_message(temp_history_db):
    before = news_item("context-before", when=datetime(2026, 5, 20, 10, 50, 0), content="before")
    center = news_item("context-center", when=datetime(2026, 5, 20, 11, 0, 0), content="center")
    after = news_item("context-after", when=datetime(2026, 5, 20, 11, 10, 0), content="after")
    outside = news_item("context-outside", when=datetime(2026, 5, 20, 11, 20, 0), content="outside")

    for item in (before, center, after, outside):
        jm.save_history_item(item, hit=True, high=False, source="rest", priority_level=jm.PRIORITY_NORMAL)

    found, rows = jm.query_context("context-center", minutes=10)

    assert found["id"] == "context-center"
    assert [row["id"] for row in rows] == ["context-before", "context-center", "context-after"]


def test_query_context_missing_readonly_db_does_not_create_file(tmp_path, monkeypatch):
    missing_db = tmp_path / "missing.sqlite3"
    monkeypatch.setattr(jm, "HISTORY_DB", missing_db)

    with pytest.raises(FileNotFoundError):
        jm.query_context("missing-id")

    assert not missing_db.exists()


def test_dashboard_recent_items_reads_history_and_status(temp_history_db):
    item = news_item("dashboard-item", when=datetime(2026, 5, 21, 9, 30, 0), content="dashboard hit")
    jm.save_history_item(item, hit=True, high=False, source="rest", priority_level=jm.PRIORITY_NORMAL)
    jm.record_telegram_delivery_status(
        jm.get_db(),
        "dashboard-item",
        channel="telegram",
        mode="realtime",
        status=jm.TELEGRAM_STATUS_SENT,
    )
    jm.get_db().commit()

    rows = jm.query_dashboard_recent_items(limit=10, with_status=True)

    assert len(rows) == 1
    assert rows[0]["id"] == "dashboard-item"
    assert rows[0]["telegram_status"] == jm.TELEGRAM_STATUS_SENT
    assert rows[0]["telegram_mode"] == "realtime"


def test_dashboard_missing_readonly_db_does_not_create_file(tmp_path, monkeypatch):
    missing_db = tmp_path / "missing-dashboard.sqlite3"
    monkeypatch.setattr(jm, "HISTORY_DB", missing_db)

    with pytest.raises(FileNotFoundError):
        jm.query_dashboard_recent_items(limit=5)

    assert not missing_db.exists()


def test_render_dashboard_index_outputs_local_readonly_page(temp_history_db):
    item = news_item("dashboard-html", when=datetime(2026, 5, 21, 9, 35, 0), title="Dashboard title")
    jm.save_history_item(item, hit=True, high=False, source="rest", priority_level=jm.PRIORITY_NORMAL)

    html = jm.render_dashboard_index({}).decode("utf-8")

    assert "Jin10 Monitor Dashboard" in html
    assert "Dashboard title" in html
    assert "/item/dashboard-html" in html
    assert "SQLite mode=ro" in html


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


def test_catch_up_window_falls_back_to_next_app_id(temp_history_db, monkeypatch):
    start_dt = datetime(2026, 5, 17, 10, 0, 0)
    end_dt = datetime(2026, 5, 17, 10, 10, 0)
    page = [
        news_item("fallback-hit", when=datetime(2026, 5, 17, 10, 5, 0), content="hit"),
        news_item("too-old", when=datetime(2026, 5, 17, 9, 59, 0), content="hit"),
    ]
    calls = []

    def fake_fetch_page(cursor, app_id):
        calls.append((cursor, app_id))
        if app_id == "bad-app":
            raise RuntimeError("bad app id")
        return page

    monkeypatch.setattr(jm, "APP_IDS", ["bad-app", "good-app"])
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
    assert result["app_id"] == "good-app"
    assert calls == [
        ("2026-05-17 10:11:00", "bad-app"),
        ("2026-05-17 10:11:00", "good-app"),
    ]
    assert result["seen_item_ids"] == ["fallback-hit"]
    assert [row["id"] for row in result["send_candidates"]] == ["fallback-hit"]


def test_catch_up_window_stops_on_empty_page(temp_history_db, monkeypatch):
    start_dt = datetime(2026, 5, 17, 10, 0, 0)
    end_dt = datetime(2026, 5, 17, 10, 10, 0)

    monkeypatch.setattr(jm, "APP_IDS", ["test-app"])
    monkeypatch.setattr(jm, "fetch_page_sync", lambda cursor, app_id: [])

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
    assert result["scanned"] == 0
    assert result["stored"] == 0
    assert result["send_candidates"] == []
    assert result["seen_item_ids"] == []


def test_catch_up_window_dedupes_repeated_ids_across_pages(temp_history_db, monkeypatch):
    start_dt = datetime(2026, 5, 17, 10, 0, 0)
    end_dt = datetime(2026, 5, 17, 10, 10, 0)
    first_page = [
        news_item("dupe", when=datetime(2026, 5, 17, 10, 9, 0), content="hit first"),
    ]
    second_page = [
        news_item("dupe", when=datetime(2026, 5, 17, 10, 5, 0), content="hit second"),
        news_item("too-old", when=datetime(2026, 5, 17, 9, 59, 0), content="hit"),
    ]
    calls = []

    def fake_fetch_page(cursor, app_id):
        calls.append(cursor)
        return first_page if len(calls) == 1 else second_page

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
    assert result["scanned"] == 1
    assert result["stored"] == 1
    assert result["seen_item_ids"] == ["dupe"]
    assert [row["id"] for row in result["send_candidates"]] == ["dupe"]


def test_catch_up_window_stores_unmatched_items_without_send_candidate(temp_history_db, monkeypatch):
    start_dt = datetime(2026, 5, 17, 10, 0, 0)
    end_dt = datetime(2026, 5, 17, 10, 10, 0)
    page = [
        news_item("plain", when=datetime(2026, 5, 17, 10, 5, 0), content="plain macro update"),
    ]

    monkeypatch.setattr(jm, "APP_IDS", ["test-app"])
    monkeypatch.setattr(jm, "KEYWORDS", ["hit"])
    monkeypatch.setattr(jm, "HIGH_PRIORITY", [])
    monkeypatch.setattr(jm, "fetch_page_sync", lambda cursor, app_id: page)
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
    assert result["scanned"] == 1
    assert result["stored"] == 1
    assert result["push_candidates"] == 0
    assert result["send_candidates"] == []
    assert result["priority_counts"] == {
        jm.PRIORITY_IMPORTANT: 0,
        jm.PRIORITY_HIGH: 0,
        jm.PRIORITY_NORMAL: 0,
    }


def test_build_catchup_summary_items_prioritizes_important_and_high_only():
    rows = [
        {
            "id": "normal",
            "time": "2026-05-17 10:01:00",
            "item": news_item("normal", title="Normal", content="normal"),
            "should_push": True,
            "priority_level": jm.PRIORITY_NORMAL,
        },
        {
            "id": "high-late",
            "time": "2026-05-17 10:03:00",
            "item": news_item("high-late", title="High late", content="high"),
            "should_push": True,
            "priority_level": jm.PRIORITY_HIGH,
        },
        {
            "id": "important",
            "time": "2026-05-17 10:02:00",
            "item": news_item("important", title="Important", content="important"),
            "should_push": True,
            "priority_level": jm.PRIORITY_IMPORTANT,
        },
        {
            "id": "high-early",
            "time": "2026-05-17 10:01:30",
            "item": news_item("high-early", title="", content="High early content"),
            "should_push": True,
            "priority_level": jm.PRIORITY_HIGH,
        },
    ]

    items = jm.build_catchup_summary_items(rows, limit=3)

    assert [(row["priority_level"], row["text"]) for row in items] == [
        (jm.PRIORITY_IMPORTANT, "Important"),
        (jm.PRIORITY_HIGH, "High early content"),
        (jm.PRIORITY_HIGH, "High late"),
    ]


def test_catchup_summary_status_id_uses_trigger_and_window():
    result = {
        "trigger": "gap",
        "window": {
            "start": "2026-05-17 10:00:00",
            "end": "2026-05-17 10:10:00",
        },
    }

    assert jm.catchup_summary_status_id(result) == (
        "catchup_summary:gap:2026-05-17 10:00:00:2026-05-17 10:10:00"
    )


def test_catchup_summary_delivery_detail_includes_counts_and_detail():
    result = {
        "stored": 2,
        "push_candidates": 3,
        "truncated": True,
    }

    assert jm.catchup_summary_delivery_detail(result, detail="network skipped") == (
        "stored=2 push_candidates=3 truncated=True detail=network skipped"
    )


def test_format_catchup_summary_message_escapes_text_and_marks_gap(monkeypatch):
    monkeypatch.setattr(jm, "CATCHUP_MAX_HOURS", 12)
    monkeypatch.setattr(jm, "CATCHUP_MAX_STORE", 3)
    result = {
        "trigger": "gap",
        "window": {
            "start": "2026-05-17 10:00:00",
            "end": "2026-05-17 10:10:00",
        },
        "stored": 2,
        "already_stored": 1,
        "push_candidates": 2,
        "priority_counts": {
            jm.PRIORITY_IMPORTANT: 1,
            jm.PRIORITY_HIGH: 1,
            jm.PRIORITY_NORMAL: 0,
        },
        "summary_items": [
            {
                "time": "2026-05-17 10:02:00",
                "priority_level": jm.PRIORITY_IMPORTANT,
                "text": "A < B & C",
            },
        ],
        "limited_by_max_hours": True,
        "truncated": True,
    }

    message = jm.format_catchup_summary_message(result)

    assert "<b>金十自愈补拉完成</b>" in message
    assert "窗口：2026-05-17 10:00:00 → 2026-05-17 10:10:00" in message
    assert "入库：2 条" in message
    assert "已存在未重复入库：1 条" in message
    assert "分级：⚡ 1 / 🚨 1 / 📰 0" in message
    assert "1. ⚡ 2026-05-17 10:02:00 A &lt; B &amp; C" in message
    assert "已按 CATCHUP_MAX_HOURS=12 截断较早窗口。" in message
    assert "入库达到 CATCHUP_MAX_STORE=3 上限，窗口可能未完全覆盖。" in message


def test_run_catch_up_does_not_send_when_telegram_disabled(temp_history_db, monkeypatch):
    def fake_catch_up_window(*args, **kwargs):
        return manual_catchup_result("manual-disabled")

    async def fail_send_telegram(session, text):
        raise AssertionError("manual catch-up should not send Telegram when disabled")

    monkeypatch.setattr(jm, "catch_up_window", fake_catch_up_window)
    monkeypatch.setattr(jm, "send_telegram", fail_send_telegram)

    result = asyncio.run(
        jm.run_catch_up(
            datetime(2026, 5, 17, 10, 0, 0),
            datetime(2026, 5, 17, 10, 10, 0),
            telegram_enabled=False,
            max_store=10,
            max_send=10,
            send_interval=0,
        )
    )

    conn = jm.get_db()
    assert result["telegram_enabled"] is False
    assert result["telegram_sent"] == 0
    assert result["telegram_failed"] == 0
    assert result["telegram_skipped"] == 0
    assert not jm.has_any_delivery(conn, "manual-disabled", channel="telegram")
    assert telegram_status(conn, "manual-disabled") is None


def test_run_catch_up_passes_manual_window_limits_to_catch_up_window(temp_history_db, monkeypatch):
    calls = []

    def fake_catch_up_window(start_dt, end_dt, **kwargs):
        calls.append((start_dt, end_dt, kwargs))
        return manual_catchup_result("manual-args")

    monkeypatch.setattr(jm, "catch_up_window", fake_catch_up_window)

    result = asyncio.run(
        jm.run_catch_up(
            datetime(2026, 5, 17, 10, 0, 0),
            datetime(2026, 5, 17, 10, 10, 0),
            telegram_enabled=False,
            max_store=23,
            max_send=4,
            send_interval=0,
        )
    )

    assert result["ok"] is True
    assert len(calls) == 1
    assert calls[0][0] == datetime(2026, 5, 17, 10, 0, 0)
    assert calls[0][1] == datetime(2026, 5, 17, 10, 10, 0)
    assert calls[0][2] == {
        "source": "catchup_manual",
        "max_store": 23,
        "max_send": 4,
    }


def test_run_catch_up_does_not_send_when_window_fails(temp_history_db, monkeypatch):
    def fake_catch_up_window(*args, **kwargs):
        return {
            "ok": False,
            "error": "REST failed",
            "send_candidates": [
                {
                    "id": "manual-window-failed",
                    "item": news_item("manual-window-failed", content="hit"),
                    "priority_level": jm.PRIORITY_NORMAL,
                }
            ],
        }

    async def fail_send_telegram(session, text):
        raise AssertionError("manual catch-up should not send Telegram when window fails")

    monkeypatch.setattr(jm, "catch_up_window", fake_catch_up_window)
    monkeypatch.setattr(jm, "send_telegram", fail_send_telegram)

    result = asyncio.run(
        jm.run_catch_up(
            datetime(2026, 5, 17, 10, 0, 0),
            datetime(2026, 5, 17, 10, 10, 0),
            telegram_enabled=True,
            max_store=10,
            max_send=10,
            send_interval=0,
        )
    )

    conn = jm.get_db()
    assert result["ok"] is False
    assert result["telegram_sent"] == 0
    assert result["telegram_failed"] == 0
    assert not jm.has_any_delivery(conn, "manual-window-failed", channel="telegram")
    assert telegram_status(conn, "manual-window-failed") is None


def test_run_catch_up_records_skipped_status_without_delivery_log(temp_history_db, monkeypatch):
    def fake_catch_up_window(*args, **kwargs):
        return manual_catchup_result("manual-skipped")

    async def fail_send_telegram(session, text):
        raise AssertionError("manual catch-up should stop at skip guard")

    monkeypatch.setattr(jm, "catch_up_window", fake_catch_up_window)
    monkeypatch.setattr(jm, "telegram_skip_reason", lambda: "Telegram 未配置")
    monkeypatch.setattr(jm, "send_telegram", fail_send_telegram)

    result = asyncio.run(
        jm.run_catch_up(
            datetime(2026, 5, 17, 10, 0, 0),
            datetime(2026, 5, 17, 10, 10, 0),
            telegram_enabled=True,
            max_store=10,
            max_send=10,
            send_interval=0,
        )
    )

    conn = jm.get_db()
    assert result["telegram_skipped"] == 1
    assert result["telegram_skip_reason"] == "Telegram 未配置"
    assert not jm.has_any_delivery(conn, "manual-skipped", channel="telegram")
    assert telegram_status(conn, "manual-skipped") == (jm.TELEGRAM_STATUS_SKIPPED, "Telegram 未配置")


def test_run_catch_up_marks_delivery_only_after_successful_send(temp_history_db, monkeypatch):
    def fake_catch_up_window(*args, **kwargs):
        return manual_catchup_result("manual-sent")

    sent_messages = []

    async def fake_send_telegram(session, text):
        sent_messages.append(text)
        return jm.TelegramSendResult(jm.TELEGRAM_STATUS_SENT)

    monkeypatch.setattr(jm, "catch_up_window", fake_catch_up_window)
    monkeypatch.setattr(jm, "telegram_skip_reason", lambda: "")
    monkeypatch.setattr(jm, "send_telegram", fake_send_telegram)

    result = asyncio.run(
        jm.run_catch_up(
            datetime(2026, 5, 17, 10, 0, 0),
            datetime(2026, 5, 17, 10, 10, 0),
            telegram_enabled=True,
            max_store=10,
            max_send=10,
            send_interval=0,
        )
    )

    conn = jm.get_db()
    assert result["telegram_sent"] == 1
    assert result["telegram_failed"] == 0
    assert len(sent_messages) == 1
    assert jm.has_delivery(conn, "manual-sent", channel="telegram", mode="catchup")
    assert telegram_status(conn, "manual-sent") == (jm.TELEGRAM_STATUS_SENT, "")


def test_run_catch_up_records_failed_status_without_delivery_log(temp_history_db, monkeypatch):
    def fake_catch_up_window(*args, **kwargs):
        return manual_catchup_result("manual-failed")

    async def fake_send_telegram(session, text):
        return jm.TelegramSendResult(jm.TELEGRAM_STATUS_FAILED, "status=500")

    monkeypatch.setattr(jm, "catch_up_window", fake_catch_up_window)
    monkeypatch.setattr(jm, "telegram_skip_reason", lambda: "")
    monkeypatch.setattr(jm, "send_telegram", fake_send_telegram)

    result = asyncio.run(
        jm.run_catch_up(
            datetime(2026, 5, 17, 10, 0, 0),
            datetime(2026, 5, 17, 10, 10, 0),
            telegram_enabled=True,
            max_store=10,
            max_send=10,
            send_interval=0,
        )
    )

    conn = jm.get_db()
    assert result["telegram_sent"] == 0
    assert result["telegram_failed"] == 1
    assert not jm.has_any_delivery(conn, "manual-failed", channel="telegram")
    assert telegram_status(conn, "manual-failed") == (jm.TELEGRAM_STATUS_FAILED, "status=500")


def test_run_catch_up_records_mixed_send_results_and_waits_between_sends(temp_history_db, monkeypatch):
    def fake_catch_up_window(*args, **kwargs):
        return manual_catchup_result_for_ids(["manual-first", "manual-second"])

    send_results = [
        jm.TelegramSendResult(jm.TELEGRAM_STATUS_SENT),
        jm.TelegramSendResult(jm.TELEGRAM_STATUS_FAILED, "status=500"),
    ]
    sent_messages = []
    sleep_calls = []

    async def fake_send_telegram(session, text):
        sent_messages.append(text)
        return send_results.pop(0)

    async def fake_sleep(seconds):
        sleep_calls.append(seconds)

    monkeypatch.setattr(jm, "catch_up_window", fake_catch_up_window)
    monkeypatch.setattr(jm, "telegram_skip_reason", lambda: "")
    monkeypatch.setattr(jm, "send_telegram", fake_send_telegram)
    monkeypatch.setattr(jm.asyncio, "sleep", fake_sleep)

    result = asyncio.run(
        jm.run_catch_up(
            datetime(2026, 5, 17, 10, 0, 0),
            datetime(2026, 5, 17, 10, 10, 0),
            telegram_enabled=True,
            max_store=10,
            max_send=10,
            send_interval=1.5,
        )
    )

    conn = jm.get_db()
    assert result["telegram_sent"] == 1
    assert result["telegram_failed"] == 1
    assert len(sent_messages) == 2
    assert sleep_calls == [1.5, 1.5]
    assert jm.has_delivery(conn, "manual-first", channel="telegram", mode="catchup")
    assert not jm.has_any_delivery(conn, "manual-second", channel="telegram")
    assert telegram_status(conn, "manual-first") == (jm.TELEGRAM_STATUS_SENT, "")
    assert telegram_status(conn, "manual-second") == (jm.TELEGRAM_STATUS_FAILED, "status=500")


def test_run_catch_up_does_not_wait_when_send_interval_is_zero(temp_history_db, monkeypatch):
    def fake_catch_up_window(*args, **kwargs):
        return manual_catchup_result_for_ids(["manual-zero-wait-1", "manual-zero-wait-2"])

    async def fake_send_telegram(session, text):
        return jm.TelegramSendResult(jm.TELEGRAM_STATUS_SENT)

    async def fail_sleep(seconds):
        raise AssertionError("manual catch-up should not wait when send_interval is zero")

    monkeypatch.setattr(jm, "catch_up_window", fake_catch_up_window)
    monkeypatch.setattr(jm, "telegram_skip_reason", lambda: "")
    monkeypatch.setattr(jm, "send_telegram", fake_send_telegram)
    monkeypatch.setattr(jm.asyncio, "sleep", fail_sleep)

    result = asyncio.run(
        jm.run_catch_up(
            datetime(2026, 5, 17, 10, 0, 0),
            datetime(2026, 5, 17, 10, 10, 0),
            telegram_enabled=True,
            max_store=10,
            max_send=10,
            send_interval=0,
        )
    )

    conn = jm.get_db()
    assert result["telegram_sent"] == 2
    assert result["telegram_failed"] == 0
    assert jm.has_delivery(conn, "manual-zero-wait-1", channel="telegram", mode="catchup")
    assert jm.has_delivery(conn, "manual-zero-wait-2", channel="telegram", mode="catchup")
    assert telegram_status(conn, "manual-zero-wait-1") == (jm.TELEGRAM_STATUS_SENT, "")
    assert telegram_status(conn, "manual-zero-wait-2") == (jm.TELEGRAM_STATUS_SENT, "")


def test_run_auto_catch_up_recovers_future_cursor_from_history(temp_history_db, monkeypatch):
    conn = jm.get_db()
    valid_item = news_item("valid-cursor", when=datetime(2026, 5, 17, 10, 5, 0), content="hit")
    jm.save_history_item(valid_item, hit=True, high=False, source="rest", priority_level=jm.PRIORITY_NORMAL)
    jm.set_state(conn, "last_ingested_at", "2999-01-01 00:00:00")
    jm.set_state(conn, "last_ingested_id", "future-id")
    conn.commit()

    calls = []

    def fake_catch_up_window(start_dt, end_dt, **kwargs):
        calls.append((start_dt, end_dt, kwargs))
        return {
            "ok": True,
            "stored": 0,
            "truncated": False,
            "seen_item_ids": [],
            "window": {
                "start": start_dt.strftime("%Y-%m-%d %H:%M:%S"),
                "end": end_dt.strftime("%Y-%m-%d %H:%M:%S"),
            },
            "push_candidates": 0,
            "priority_counts": {},
            "summary_items": [],
        }

    monkeypatch.setattr(jm, "CATCHUP_TELEGRAM", False)
    monkeypatch.setattr(jm, "catch_up_window", fake_catch_up_window)

    result = asyncio.run(jm.run_auto_catch_up(object(), datetime(2026, 5, 17, 10, 10, 0), trigger="startup"))

    assert result["ok"] is True
    assert state_value(conn, "last_ingested_at") == "2026-05-17 10:05:00"
    assert state_value(conn, "last_ingested_id") == "valid-cursor"
    assert len(calls) == 1
    assert calls[0][0] == datetime(2026, 5, 17, 10, 3, 0)
    assert calls[0][1] == datetime(2026, 5, 17, 10, 10, 0)


def test_run_auto_catch_up_skips_future_cursor_without_history(temp_history_db):
    conn = jm.get_db()
    jm.set_state(conn, "last_ingested_at", "2999-01-01 00:00:00")
    conn.commit()

    result = asyncio.run(jm.run_auto_catch_up(object(), datetime(2026, 5, 17, 10, 10, 0), trigger="startup"))

    assert result["ok"] is True
    assert result["skipped"] is True
    assert "last_ingested_at 位于未来且暂无可恢复历史游标" in result["reason"]


def test_run_auto_catch_up_skips_without_last_ingested_at(temp_history_db, monkeypatch):
    def fail_catch_up_window(*args, **kwargs):
        raise AssertionError("auto catch-up should skip before calling catch_up_window")

    monkeypatch.setattr(jm, "catch_up_window", fail_catch_up_window)

    result = asyncio.run(jm.run_auto_catch_up(object(), datetime(2026, 5, 17, 10, 10, 0), trigger="startup"))

    assert result == {
        "ok": True,
        "skipped": True,
        "reason": "暂无 last_ingested_at",
        "trigger": "startup",
    }


def test_run_auto_catch_up_returns_error_for_invalid_last_ingested_at(temp_history_db, monkeypatch):
    conn = jm.get_db()
    jm.set_state(conn, "last_ingested_at", "not-a-date")
    conn.commit()

    def fail_catch_up_window(*args, **kwargs):
        raise AssertionError("auto catch-up should skip invalid cursor before calling catch_up_window")

    monkeypatch.setattr(jm, "catch_up_window", fail_catch_up_window)

    result = asyncio.run(jm.run_auto_catch_up(object(), datetime(2026, 5, 17, 10, 10, 0), trigger="startup"))

    assert result["ok"] is False
    assert "last_ingested_at 格式应为" in result["error"]
    assert result["trigger"] == "startup"


def test_run_auto_catch_up_skips_when_no_offline_window(temp_history_db, monkeypatch):
    conn = jm.get_db()
    jm.set_state(conn, "last_ingested_at", "2026-05-17 10:12:00")
    conn.commit()

    def fail_catch_up_window(*args, **kwargs):
        raise AssertionError("auto catch-up should skip empty window before calling catch_up_window")

    monkeypatch.setattr(jm, "catch_up_window", fail_catch_up_window)

    result = asyncio.run(jm.run_auto_catch_up(object(), datetime(2026, 5, 17, 10, 10, 0), trigger="startup"))

    assert result["ok"] is True
    assert result["skipped"] is True
    assert result["reason"] == "没有离线窗口"
    assert result["window"] == {
        "start": "2026-05-17 10:10:00",
        "end": "2026-05-17 10:10:00",
    }


def test_run_auto_catch_up_limits_window_by_max_hours(temp_history_db, monkeypatch):
    conn = jm.get_db()
    jm.set_state(conn, "last_ingested_at", "2026-05-17 00:00:00")
    conn.commit()
    calls = []

    def fake_catch_up_window(start_dt, end_dt, **kwargs):
        calls.append((start_dt, end_dt, kwargs))
        return {
            "ok": True,
            "stored": 0,
            "truncated": False,
            "seen_item_ids": [],
            "window": {
                "start": start_dt.strftime("%Y-%m-%d %H:%M:%S"),
                "end": end_dt.strftime("%Y-%m-%d %H:%M:%S"),
            },
            "push_candidates": 0,
            "priority_counts": {},
            "summary_items": [],
        }

    monkeypatch.setattr(jm, "CATCHUP_MAX_HOURS", 2)
    monkeypatch.setattr(jm, "CATCHUP_TELEGRAM", False)
    monkeypatch.setattr(jm, "catch_up_window", fake_catch_up_window)

    result = asyncio.run(jm.run_auto_catch_up(object(), datetime(2026, 5, 17, 10, 10, 0), trigger="startup"))

    assert result["ok"] is True
    assert result["limited_by_max_hours"] is True
    assert len(calls) == 1
    assert calls[0][0] == datetime(2026, 5, 17, 8, 10, 0)
    assert calls[0][1] == datetime(2026, 5, 17, 10, 10, 0)
    assert calls[0][2]["source"] == "catchup_auto"
    assert calls[0][2]["max_send"] == 0


def test_run_auto_catch_up_remembers_seen_item_ids(temp_history_db, monkeypatch):
    conn = jm.get_db()
    jm.set_state(conn, "last_ingested_at", "2026-05-17 10:00:00")
    conn.commit()
    jm.seen_ids.clear()

    def fake_catch_up_window(*args, **kwargs):
        return {
            "ok": True,
            "stored": 2,
            "truncated": False,
            "seen_item_ids": ["auto-seen-1", "auto-seen-2"],
            "window": {
                "start": "2026-05-17 09:58:00",
                "end": "2026-05-17 10:10:00",
            },
            "push_candidates": 0,
            "priority_counts": {},
            "summary_items": [],
        }

    monkeypatch.setattr(jm, "CATCHUP_TELEGRAM", False)
    monkeypatch.setattr(jm, "catch_up_window", fake_catch_up_window)

    result = asyncio.run(jm.run_auto_catch_up(object(), datetime(2026, 5, 17, 10, 10, 0), trigger="startup"))

    assert result["ok"] is True
    assert "auto-seen-1" in jm.seen_ids
    assert "auto-seen-2" in jm.seen_ids
    assert jm.is_new({"id": "auto-seen-1"}) is False
    assert jm.is_new({"id": "realtime-new"}) is True


def test_run_auto_catch_up_gap_summary_respects_cooldown(temp_history_db, monkeypatch):
    conn = jm.get_db()
    jm.set_state(conn, "last_ingested_at", "2026-05-17 10:00:00")
    jm.set_state(conn, "last_gap_summary_telegram_at", "2026-05-17 10:08:00")
    conn.commit()

    def fake_catch_up_window(*args, **kwargs):
        return {
            "ok": True,
            "stored": 1,
            "truncated": False,
            "seen_item_ids": ["gap-item"],
            "window": {
                "start": "2026-05-17 09:58:00",
                "end": "2026-05-17 10:10:00",
            },
            "push_candidates": 1,
            "priority_counts": {},
            "summary_items": [],
        }

    async def fail_send_telegram(session, text):
        raise AssertionError("gap summary should be throttled")

    monkeypatch.setattr(jm, "CATCHUP_TELEGRAM", True)
    monkeypatch.setattr(jm, "AUTO_CATCHUP_SUMMARY_COOLDOWN_SECONDS", 1800)
    monkeypatch.setattr(jm, "catch_up_window", fake_catch_up_window)
    monkeypatch.setattr(jm, "send_telegram", fail_send_telegram)

    result = asyncio.run(jm.run_auto_catch_up(object(), datetime(2026, 5, 17, 10, 10, 0), trigger="gap"))

    assert result["ok"] is True
    assert result["telegram_summary_sent"] is False
    assert result["telegram_summary_skipped"] is False
    assert state_value(conn, "last_gap_summary_telegram_at") == "2026-05-17 10:08:00"


def test_run_auto_catch_up_gap_summary_after_cooldown_updates_status(temp_history_db, monkeypatch):
    conn = jm.get_db()
    jm.set_state(conn, "last_ingested_at", "2026-05-17 10:00:00")
    jm.set_state(conn, "last_gap_summary_telegram_at", "2026-05-17 09:00:00")
    conn.commit()

    def fake_catch_up_window(*args, **kwargs):
        return {
            "ok": True,
            "stored": 1,
            "truncated": False,
            "seen_item_ids": ["gap-item"],
            "window": {
                "start": "2026-05-17 09:58:00",
                "end": "2026-05-17 10:10:00",
            },
            "push_candidates": 1,
            "priority_counts": {},
            "summary_items": [],
        }

    sent_messages = []

    async def fake_send_telegram(session, text):
        sent_messages.append(text)
        return jm.TelegramSendResult(jm.TELEGRAM_STATUS_SENT)

    monkeypatch.setattr(jm, "CATCHUP_TELEGRAM", True)
    monkeypatch.setattr(jm, "catch_up_window", fake_catch_up_window)
    monkeypatch.setattr(jm, "send_telegram", fake_send_telegram)
    monkeypatch.setattr(jm, "telegram_skip_reason", lambda: "")

    result = asyncio.run(jm.run_auto_catch_up(object(), datetime(2026, 5, 17, 10, 10, 0), trigger="gap"))

    assert result["ok"] is True
    assert result["telegram_summary_sent"] is True
    assert len(sent_messages) == 1
    assert state_value(conn, "last_gap_summary_telegram_at") == "2026-05-17 10:10:00"
    status = conn.execute(
        """
        SELECT status, detail
        FROM telegram_delivery_status
        WHERE message_id = ? AND channel = ? AND mode = ?
        """,
        (
            "catchup_summary:gap:2026-05-17 09:58:00:2026-05-17 10:10:00",
            "telegram",
            "catchup_summary",
        ),
    ).fetchone()
    assert status == (jm.TELEGRAM_STATUS_SENT, "stored=1 push_candidates=1 truncated=False")


def test_poll_loop_triggers_auto_catch_up_after_gap(monkeypatch):
    fake_datetime = fake_datetime_from(
        [
            datetime(2026, 5, 17, 10, 0, 0),
            datetime(2026, 5, 17, 10, 5, 0),
            datetime(2026, 5, 17, 10, 5, 0),
        ]
    )

    session = object()
    catchup_calls = []
    poll_calls = []

    async def fake_run_auto_catch_up(run_session, now, trigger):
        catchup_calls.append((run_session, now, trigger))
        return {"ok": True, "stored": 0, "push_candidates": 0, "window": {}}

    async def fake_poll_once(run_session):
        poll_calls.append(run_session)
        return []

    async def stop_sleep(seconds):
        raise StopPollLoop

    monkeypatch.setattr(jm, "AUTO_CATCHUP", True)
    monkeypatch.setattr(jm, "AUTO_CATCHUP_GAP_SECONDS", 300)
    monkeypatch.setattr(jm, "datetime", fake_datetime)
    monkeypatch.setattr(jm, "run_auto_catch_up", fake_run_auto_catch_up)
    monkeypatch.setattr(jm, "poll_once", fake_poll_once)
    monkeypatch.setattr(jm.random, "uniform", lambda start, end: 0)
    monkeypatch.setattr(jm.asyncio, "sleep", stop_sleep)

    with pytest.raises(StopPollLoop):
        asyncio.run(jm.poll_loop(session))

    assert catchup_calls == [(session, datetime(2026, 5, 17, 10, 5, 0), "gap")]
    assert poll_calls == [session]


def test_poll_loop_continues_polling_when_auto_catch_up_raises(monkeypatch, caplog):
    fake_datetime = fake_datetime_from(
        [
            datetime(2026, 5, 17, 10, 0, 0),
            datetime(2026, 5, 17, 10, 5, 0),
            datetime(2026, 5, 17, 10, 5, 0),
        ]
    )

    poll_calls = []

    async def fail_run_auto_catch_up(*args, **kwargs):
        raise RuntimeError("catch-up failed")

    async def fake_poll_once(session):
        poll_calls.append(session)
        return []

    async def stop_sleep(seconds):
        raise StopPollLoop

    monkeypatch.setattr(jm, "AUTO_CATCHUP", True)
    monkeypatch.setattr(jm, "AUTO_CATCHUP_GAP_SECONDS", 300)
    monkeypatch.setattr(jm, "datetime", fake_datetime)
    monkeypatch.setattr(jm, "run_auto_catch_up", fail_run_auto_catch_up)
    monkeypatch.setattr(jm, "poll_once", fake_poll_once)
    monkeypatch.setattr(jm.random, "uniform", lambda start, end: 0)
    monkeypatch.setattr(jm.asyncio, "sleep", stop_sleep)
    caplog.set_level("WARNING", logger="jin10")

    session = object()
    with pytest.raises(StopPollLoop):
        asyncio.run(jm.poll_loop(session))

    assert poll_calls == [session]
    assert "自愈补拉异常，继续实时监控：catch-up failed" in caplog.text


def test_poll_loop_handles_new_rest_items(monkeypatch):
    fake_datetime = fake_datetime_from(
        [
            datetime(2026, 5, 17, 10, 0, 0),
            datetime(2026, 5, 17, 10, 0, 1),
            datetime(2026, 5, 17, 10, 0, 1),
        ]
    )
    session = object()
    item = news_item("poll-new", when=datetime(2026, 5, 17, 10, 0, 0), content="hit")
    handle_calls = []

    async def fake_poll_once(run_session):
        assert run_session is session
        return [item]

    async def fake_handle_item(run_session, handled_item, source):
        handle_calls.append((run_session, handled_item, source))

    async def stop_sleep(seconds):
        raise StopPollLoop

    monkeypatch.setattr(jm, "AUTO_CATCHUP", False)
    monkeypatch.setattr(jm, "datetime", fake_datetime)
    monkeypatch.setattr(jm, "poll_once", fake_poll_once)
    monkeypatch.setattr(jm, "handle_item", fake_handle_item)
    monkeypatch.setattr(jm.random, "uniform", lambda start, end: 0)
    monkeypatch.setattr(jm.asyncio, "sleep", stop_sleep)
    jm.seen_ids.clear()

    with pytest.raises(StopPollLoop):
        asyncio.run(jm.poll_loop(session))

    assert handle_calls == [(session, item, "rest")]
    assert jm.is_new({"id": "poll-new"}) is False


@pytest.mark.parametrize(
    ("auto_catchup", "loop_now", "threshold"),
    [
        (False, datetime(2026, 5, 17, 10, 5, 0), 300),
        (True, datetime(2026, 5, 17, 10, 4, 59), 300),
    ],
)
def test_poll_loop_skips_auto_catch_up_when_disabled_or_gap_below_threshold(
    monkeypatch,
    auto_catchup,
    loop_now,
    threshold,
):
    fake_datetime = fake_datetime_from(
        [
            datetime(2026, 5, 17, 10, 0, 0),
            loop_now,
            loop_now,
        ]
    )

    async def fail_run_auto_catch_up(*args, **kwargs):
        raise AssertionError("poll_loop should not run auto catch-up")

    async def fake_poll_once(session):
        return []

    async def stop_sleep(seconds):
        raise StopPollLoop

    monkeypatch.setattr(jm, "AUTO_CATCHUP", auto_catchup)
    monkeypatch.setattr(jm, "AUTO_CATCHUP_GAP_SECONDS", threshold)
    monkeypatch.setattr(jm, "datetime", fake_datetime)
    monkeypatch.setattr(jm, "run_auto_catch_up", fail_run_auto_catch_up)
    monkeypatch.setattr(jm, "poll_once", fake_poll_once)
    monkeypatch.setattr(jm.random, "uniform", lambda start, end: 0)
    monkeypatch.setattr(jm.asyncio, "sleep", stop_sleep)

    with pytest.raises(StopPollLoop):
        asyncio.run(jm.poll_loop(object()))
