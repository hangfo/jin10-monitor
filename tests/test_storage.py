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
