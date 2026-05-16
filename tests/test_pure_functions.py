import asyncio
from datetime import datetime, timedelta

import jin10_monitor as jm


class NoNetworkSession:
    def post(self, *args, **kwargs):
        raise AssertionError("send_telegram should not call Telegram API")


class FakeTelegramResponse:
    def __init__(self, status, body=""):
        self.status = status
        self.body = body

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def text(self):
        return self.body


class FakeTelegramSession:
    def __init__(self, response=None, exc=None):
        self.response = response
        self.exc = exc
        self.calls = []

    def post(self, url, **kwargs):
        self.calls.append((url, kwargs))
        if self.exc:
            raise self.exc
        return self.response


def news_item(**overrides):
    item = {
        "id": "test-1",
        "time": "2026-05-16 20:30:00",
        "data": {
            "title": "Title",
            "content": "Content",
        },
    }
    item.update(overrides)
    return item


def test_env_min_float_keeps_value_at_or_above_minimum(monkeypatch):
    monkeypatch.setenv("TEST_DELAY", "2.5")

    assert jm.env_min_float("TEST_DELAY", 5, 1.0) == 2.5


def test_env_min_float_clamps_value_below_minimum(monkeypatch, caplog):
    monkeypatch.setenv("TEST_DELAY", "0")

    assert jm.env_min_float("TEST_DELAY", 5, 1.0) == 1.0
    assert "TEST_DELAY=0.0 低于下限 1.0" in caplog.text


def test_env_min_float_keeps_invalid_value_on_default_path(monkeypatch, caplog):
    monkeypatch.setenv("TEST_DELAY", "bad")

    assert jm.env_min_float("TEST_DELAY", 5, 1.0) == 5
    assert "TEST_DELAY='bad' 不是有效数字，使用默认值 5" in caplog.text


def test_env_range_float_keeps_value_inside_range(monkeypatch):
    monkeypatch.setenv("TEST_INTERVAL", "10")

    assert jm.env_range_float("TEST_INTERVAL", 3, 1.0, 60.0) == 10


def test_env_range_float_clamps_value_below_minimum(monkeypatch, caplog):
    monkeypatch.setenv("TEST_INTERVAL", "-5")

    assert jm.env_range_float("TEST_INTERVAL", 3, 1.0, 60.0) == 1.0
    assert "TEST_INTERVAL=-5.0 低于下限 1.0" in caplog.text


def test_env_range_float_clamps_value_above_maximum(monkeypatch, caplog):
    monkeypatch.setenv("TEST_INTERVAL", "120")

    assert jm.env_range_float("TEST_INTERVAL", 3, 1.0, 60.0) == 60.0
    assert "TEST_INTERVAL=120.0 高于上限 60.0" in caplog.text


def test_env_range_int_keeps_value_inside_range(monkeypatch):
    monkeypatch.setenv("TEST_LIMIT", "100")

    assert jm.env_range_int("TEST_LIMIT", 50, 20, 5000) == 100


def test_env_range_int_clamps_value_below_minimum(monkeypatch, caplog):
    monkeypatch.setenv("TEST_LIMIT", "0")

    assert jm.env_range_int("TEST_LIMIT", 50, 20, 5000) == 20
    assert "TEST_LIMIT=0 低于下限 20" in caplog.text


def test_env_range_int_clamps_value_above_maximum(monkeypatch, caplog):
    monkeypatch.setenv("TEST_LIMIT", "9999")

    assert jm.env_range_int("TEST_LIMIT", 50, 20, 5000) == 5000
    assert "TEST_LIMIT=9999 高于上限 5000" in caplog.text


def test_env_range_int_keeps_invalid_value_on_default_path(monkeypatch, caplog):
    monkeypatch.setenv("TEST_LIMIT", "bad")

    assert jm.env_range_int("TEST_LIMIT", 50, 20, 5000) == 50
    assert "TEST_LIMIT='bad' 不是有效整数，使用默认值 50" in caplog.text


def test_item_datetime_parses_unix_seconds():
    value = 1_715_000_000

    assert jm.item_datetime({"time": value}) == datetime.fromtimestamp(value).replace(microsecond=0)


def test_item_datetime_parses_unix_milliseconds():
    seconds = 1_715_000_000

    assert jm.item_datetime({"time": seconds * 1000}) == datetime.fromtimestamp(seconds).replace(microsecond=0)


def test_item_datetime_parses_full_rest_datetime():
    assert jm.item_datetime({"time": "2026-05-16 20:30:45"}) == datetime(2026, 5, 16, 20, 30, 45)


def test_item_datetime_parses_minute_rest_datetime():
    assert jm.item_datetime({"time": "2026-05-16 20:30"}) == datetime(2026, 5, 16, 20, 30)


def test_item_datetime_returns_none_for_empty_or_invalid_time():
    assert jm.item_datetime({"time": ""}) is None
    assert jm.item_datetime({"time": "not-a-time"}) is None


def test_classify_priority_prefers_important_over_high():
    assert jm.classify_priority({"important": True}, hit=True, high=True) == jm.PRIORITY_IMPORTANT


def test_classify_priority_prefers_high_over_normal_hit():
    assert jm.classify_priority({}, hit=True, high=True) == jm.PRIORITY_HIGH


def test_classify_priority_returns_normal_for_keyword_hit():
    assert jm.classify_priority({}, hit=True, high=False) == jm.PRIORITY_NORMAL


def test_classify_priority_returns_none_without_hit():
    assert jm.classify_priority({}, hit=False, high=False) == jm.PRIORITY_NONE


def test_telegram_send_result_ok_only_for_sent_status():
    assert jm.TelegramSendResult(jm.TELEGRAM_STATUS_SENT).ok is True

    for status in (
        jm.TELEGRAM_STATUS_FAILED,
        jm.TELEGRAM_STATUS_UNKNOWN_TIMEOUT,
        jm.TELEGRAM_STATUS_SKIPPED,
    ):
        assert jm.TelegramSendResult(status).ok is False


def test_send_telegram_skips_when_credentials_are_missing(monkeypatch):
    monkeypatch.setattr(jm, "TG_TOKEN", "")
    monkeypatch.setattr(jm, "TG_CHAT_ID", "")
    monkeypatch.setattr(jm, "HISTORY_DB", jm.Path("data/test.sqlite3"))

    result = asyncio.run(jm.send_telegram(NoNetworkSession(), "test message"))

    assert result.status == jm.TELEGRAM_STATUS_SKIPPED
    assert result.ok is False
    assert result.detail == "Telegram 未配置"


def test_send_telegram_skips_temp_history_db_without_override(tmp_path, monkeypatch):
    monkeypatch.setattr(jm, "TG_TOKEN", "test-token")
    monkeypatch.setattr(jm, "TG_CHAT_ID", "test-chat")
    monkeypatch.setattr(jm, "HISTORY_DB", tmp_path / "history.sqlite3")
    monkeypatch.setattr(jm, "ALLOW_TMP_TELEGRAM", False)

    result = asyncio.run(jm.send_telegram(NoNetworkSession(), "test message"))

    assert result.status == jm.TELEGRAM_STATUS_SKIPPED
    assert result.ok is False
    assert "临时测试库" in result.detail


def test_send_telegram_returns_sent_for_200_response(monkeypatch):
    monkeypatch.setattr(jm, "TG_TOKEN", "test-token")
    monkeypatch.setattr(jm, "TG_CHAT_ID", "test-chat")
    monkeypatch.setattr(jm, "HISTORY_DB", jm.Path("data/test.sqlite3"))
    session = FakeTelegramSession(FakeTelegramResponse(200, '{"ok":true}'))

    result = asyncio.run(jm.send_telegram(session, "test message"))

    assert result.status == jm.TELEGRAM_STATUS_SENT
    assert result.ok is True
    assert len(session.calls) == 1
    assert session.calls[0][1]["json"]["text"] == "test message"


def test_send_telegram_returns_failed_for_500_response_without_retry_delay(monkeypatch):
    monkeypatch.setattr(jm, "TG_TOKEN", "test-token")
    monkeypatch.setattr(jm, "TG_CHAT_ID", "test-chat")
    monkeypatch.setattr(jm, "HISTORY_DB", jm.Path("data/test.sqlite3"))
    monkeypatch.setattr(jm, "TELEGRAM_RETRY_DELAYS", ())
    session = FakeTelegramSession(FakeTelegramResponse(500, "server error"))

    result = asyncio.run(jm.send_telegram(session, "test message"))

    assert result.status == jm.TELEGRAM_STATUS_FAILED
    assert result.ok is False
    assert result.detail == "status=500 body=server error"
    assert len(session.calls) == 1


def test_send_telegram_returns_unknown_timeout_without_retry(monkeypatch):
    monkeypatch.setattr(jm, "TG_TOKEN", "test-token")
    monkeypatch.setattr(jm, "TG_CHAT_ID", "test-chat")
    monkeypatch.setattr(jm, "HISTORY_DB", jm.Path("data/test.sqlite3"))
    session = FakeTelegramSession(exc=asyncio.TimeoutError("slow telegram"))

    result = asyncio.run(jm.send_telegram(session, "test message"))

    assert result.status == jm.TELEGRAM_STATUS_UNKNOWN_TIMEOUT
    assert result.ok is False
    assert "slow telegram" in result.detail
    assert len(session.calls) == 1


def test_previous_page_cursor_moves_before_oldest_item():
    dated = [
        (datetime(2026, 5, 16, 20, 30, 10), {"id": "newer"}),
        (datetime(2026, 5, 16, 20, 30, 5), {"id": "oldest"}),
    ]

    assert jm.previous_page_cursor(dated, "2026-05-16 20:31:00") == "2026-05-16 20:30:04"


def test_previous_page_cursor_never_moves_forward_on_duplicate_cursor_time():
    dated = [(datetime(2026, 5, 16, 20, 30, 5), {"id": "same-second"})]

    assert jm.previous_page_cursor(dated, "2026-05-16 20:30:04") == "2026-05-16 20:30:03"


def test_previous_page_cursor_accepts_minute_precision_current_cursor():
    dated = [(datetime(2026, 5, 16, 20, 30, 5), {"id": "same-minute"})]

    assert jm.previous_page_cursor(dated, "2026-05-16 20:30") == "2026-05-16 20:29:59"


def test_crawl_window_filters_scores_and_advances_cursor(monkeypatch):
    start_dt = datetime(2026, 5, 17, 10, 0, 0)
    end_dt = datetime(2026, 5, 17, 10, 10, 0)
    first_page = [
        news_item(id="too-new", time="2026-05-17 10:11:00", data={"title": "", "content": "cpi"}),
        news_item(id="high", time="2026-05-17 10:09:00", data={"title": "High", "content": "urgent macro"}),
        news_item(id="normal", time="2026-05-17 10:05:00", data={"title": "Normal", "content": "cpi plain"}),
    ]
    second_page = [
        news_item(id="too-old", time="2026-05-17 09:59:00", data={"title": "", "content": "cpi"}),
    ]
    cursors = []

    def fake_fetch_page(cursor, app_id):
        cursors.append(cursor)
        return first_page if len(cursors) == 1 else second_page

    monkeypatch.setattr(jm, "APP_IDS", ["test-app"])
    monkeypatch.setattr(jm, "KEYWORDS", ["cpi", "urgent"])
    monkeypatch.setattr(jm, "HIGH_PRIORITY", ["urgent"])
    monkeypatch.setattr(jm, "fetch_page_sync", fake_fetch_page)
    monkeypatch.setattr(jm.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(jm.random, "uniform", lambda start, end: 0)

    result = jm.crawl_window(start_dt, end_dt, ["cpi", "urgent"], max_pages=3, sleep_s=0)

    assert result["ok"] is True
    assert result["pages"] == 2
    assert cursors == ["2026-05-17 10:11:00", "2026-05-17 10:04:59"]
    assert [row["id"] for row in result["all_items"]] == ["normal", "high"]
    assert [row["id"] for row in result["matched_items"]] == ["normal", "high"]
    assert result["all_items"][0]["matched_keywords"] == ["cpi"]
    assert result["all_items"][0]["match_score"] == 1
    assert result["all_items"][0]["priority_level"] == jm.PRIORITY_NORMAL
    assert result["all_items"][1]["matched_keywords"] == ["urgent"]
    assert result["all_items"][1]["priority_level"] == jm.PRIORITY_HIGH


def test_crawl_window_falls_back_to_next_app_id(monkeypatch):
    start_dt = datetime(2026, 5, 17, 10, 0, 0)
    end_dt = datetime(2026, 5, 17, 10, 10, 0)
    calls = []

    def fake_fetch_page(cursor, app_id):
        calls.append((cursor, app_id))
        if app_id == "bad-app":
            raise RuntimeError("bad app id")
        return [news_item(id="ok", time="2026-05-17 10:05:00", data={"title": "", "content": "cpi"})]

    monkeypatch.setattr(jm, "APP_IDS", ["bad-app", "good-app"])
    monkeypatch.setattr(jm, "KEYWORDS", ["cpi"])
    monkeypatch.setattr(jm, "HIGH_PRIORITY", [])
    monkeypatch.setattr(jm, "fetch_page_sync", fake_fetch_page)
    monkeypatch.setattr(jm.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(jm.random, "uniform", lambda start, end: 0)

    result = jm.crawl_window(start_dt, end_dt, ["cpi"], max_pages=1, sleep_s=0)

    assert result["ok"] is True
    assert result["app_id"] == "good-app"
    assert calls == [
        ("2026-05-17 10:11:00", "bad-app"),
        ("2026-05-17 10:11:00", "good-app"),
    ]
    assert [row["id"] for row in result["matched_items"]] == ["ok"]


def test_crawl_window_stops_on_empty_page(monkeypatch):
    start_dt = datetime(2026, 5, 17, 10, 0, 0)
    end_dt = datetime(2026, 5, 17, 10, 10, 0)

    monkeypatch.setattr(jm, "APP_IDS", ["test-app"])
    monkeypatch.setattr(jm, "fetch_page_sync", lambda cursor, app_id: [])

    result = jm.crawl_window(start_dt, end_dt, ["cpi"], max_pages=3, sleep_s=0)

    assert result["ok"] is True
    assert result["pages"] == 1
    assert result["all_items"] == []
    assert result["matched_items"] == []


def test_crawl_window_dedupes_repeated_ids(monkeypatch):
    start_dt = datetime(2026, 5, 17, 10, 0, 0)
    end_dt = datetime(2026, 5, 17, 10, 10, 0)
    page = [
        news_item(id="dupe", time="2026-05-17 10:06:00", data={"title": "", "content": "cpi first"}),
        news_item(id="dupe", time="2026-05-17 10:05:00", data={"title": "", "content": "cpi second"}),
    ]

    monkeypatch.setattr(jm, "APP_IDS", ["test-app"])
    monkeypatch.setattr(jm, "KEYWORDS", ["cpi"])
    monkeypatch.setattr(jm, "HIGH_PRIORITY", [])
    monkeypatch.setattr(jm, "fetch_page_sync", lambda cursor, app_id: page)
    monkeypatch.setattr(jm.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(jm.random, "uniform", lambda start, end: 0)

    result = jm.crawl_window(start_dt, end_dt, ["cpi"], max_pages=1, sleep_s=0)

    assert [row["id"] for row in result["all_items"]] == ["dupe"]
    assert result["all_items"][0]["content"] == "cpi first"
    assert [row["id"] for row in result["matched_items"]] == ["dupe"]


def test_crawl_window_keeps_unmatched_items_out_of_matched_items(monkeypatch):
    start_dt = datetime(2026, 5, 17, 10, 0, 0)
    end_dt = datetime(2026, 5, 17, 10, 10, 0)
    page = [
        news_item(id="plain", time="2026-05-17 10:05:00", data={"title": "Plain", "content": "macro update"}),
    ]

    monkeypatch.setattr(jm, "APP_IDS", ["test-app"])
    monkeypatch.setattr(jm, "KEYWORDS", ["cpi"])
    monkeypatch.setattr(jm, "HIGH_PRIORITY", [])
    monkeypatch.setattr(jm, "fetch_page_sync", lambda cursor, app_id: page)
    monkeypatch.setattr(jm.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(jm.random, "uniform", lambda start, end: 0)

    result = jm.crawl_window(start_dt, end_dt, ["cpi"], max_pages=1, sleep_s=0)

    assert [row["id"] for row in result["all_items"]] == ["plain"]
    assert result["all_items"][0]["match_score"] == 0
    assert result["all_items"][0]["matched_keywords"] == []
    assert result["all_items"][0]["priority_level"] == jm.PRIORITY_NONE
    assert result["matched_items"] == []


def test_item_text_uses_data_title_and_content_and_cleans_html():
    title, content = jm.item_text(news_item(data={"title": "<b>Title</b>", "content": "Line<br>Two"}))

    assert title == "Title"
    assert content == "Line\nTwo"


def test_item_text_extracts_bracket_title_from_raw_content():
    title, content = jm.item_text(news_item(data={"title": "", "content": "<b>【Fed】</b> cuts rates"}))

    assert title == "Fed"
    assert content == "cuts rates"


def test_indicator_item_text_formats_indicator_packet():
    title, content = jm.indicator_item_text({
        "type": 1,
        "data": {
            "name": "US CPI",
            "time_period": "Apr",
            "measure": "YoY",
            "actual": "3.4",
            "unit": "%",
            "consensus": "3.5",
            "previous": "3.2",
            "revised": "3.3",
            "country": "US",
        },
    })

    assert title == "US CPI Apr YoY"
    assert content.splitlines() == [
        "公布值：3.4%",
        "预期：3.5%",
        "前值：3.2%",
        "修正：3.3%",
        "市场：US",
    ]


def test_indicator_item_text_returns_empty_for_unknown_packet():
    assert jm.indicator_item_text({"type": 2, "data": {"name": "US CPI"}}) == ("", "")


def test_format_message_escapes_text_and_source_links():
    item = news_item(data={
        "title": "A < B",
        "content": "Use & check",
        "source": "Source & Co",
        "source_link": "https://example.com/?a=1&b=2",
    })

    message = jm.format_message(item, jm.PRIORITY_NORMAL)

    assert "<b>A &lt; B</b>" in message
    assert "Use &amp; check" in message
    assert '来源：<a href="https://example.com/?a=1&amp;b=2">Source &amp; Co</a>' in message


def test_format_message_marks_catchup_and_picture_link():
    item = news_item(data={
        "title": "Title",
        "content": "Content",
        "pic": "https://example.com/a.png?x=1&y=2",
    })

    message = jm.format_message(item, jm.PRIORITY_HIGH, catchup=True)

    assert "金十快讯 [补拉]" in message
    assert "发生时间：2026-05-16 20:30:00" in message
    assert '图片：<a href="https://example.com/a.png?x=1&amp;y=2">查看</a>' in message


def test_format_message_bolds_bold_content_when_title_is_absent(monkeypatch):
    now = datetime(2026, 5, 16, 20, 30, 30)
    item = news_item(
        time=now - timedelta(seconds=30),
        data={"title": "", "content": "<b>Important content</b>"},
    )
    monkeypatch.setattr(jm, "SHOW_DELAY_IF_SECONDS", 0)

    message = jm.format_message(item, jm.PRIORITY_HIGH)

    assert "<b>Important content</b>" in message
