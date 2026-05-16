import asyncio
from datetime import datetime, timedelta

import jin10_monitor as jm


class NoNetworkSession:
    def post(self, *args, **kwargs):
        raise AssertionError("send_telegram should not call Telegram API")


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
