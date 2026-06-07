import json
import sqlite3
from datetime import datetime, timedelta
from html import escape
from pathlib import Path

from dashboard import analysis_db, db, evidence, manual_ai
from dashboard.app import (
    ALLOWED_SCREENSHOT_MIME_TYPES,
    app,
    append_screenshot_context,
    analysis_status_label,
    format_provider_error,
    market_context_default_enabled,
    provider_error_redirect,
    provider_raw_preview,
    provider_review_warning,
    provider_system_prompt,
    parse_market_context_json,
    normalize_news_text,
    parse_multipart_upload,
    summarize_klines,
)
from dashboard.market.base import Kline
from scripts.export_provider_ab_packet import export_run_packet

TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "dashboard" / "templates"


def history_ts(minutes_delta=0):
    return (datetime.now() + timedelta(minutes=minutes_delta)).strftime("%Y-%m-%d %H:%M:%S")


def create_history_db(path):
    conn = sqlite3.connect(path)
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
    return conn


def insert_flash(conn, item_id, published_at, title, content="", priority="T1_NORMAL"):
    conn.execute(
        """
        INSERT INTO flash_history (
            id, published_at, title, content, hit, high, important, has_bold,
            priority_level, has_pic, pic_url, news_source, source_url, source, created_at
        )
        VALUES (?, ?, ?, ?, 1, 0, ?, ?, ?, 0, '', '金十数据', '', 'rest', ?)
        """,
        (
            item_id,
            published_at,
            title,
            content,
            1 if priority == "T3_IMPORTANT" else 0,
            1 if priority == "T3_IMPORTANT" else 0,
            priority,
            published_at,
        ),
    )


def test_analysis_db_roundtrip_and_cascade_delete(tmp_path):
    db_path = tmp_path / "analysis.sqlite3"
    analysis_db.init_analysis_db(db_path)
    evidence_packet = [
        {
            "news_id": "n1",
            "published_at": "2026-05-23 09:30:00",
            "title": "BTC news",
            "relevance_score": 0.8,
            "matched_keywords": ["BTC"],
            "selected": True,
        },
        {
            "news_id": "n2",
            "published_at": "2026-05-23 09:35:00",
            "title": "Other news",
            "relevance_score": 0.2,
            "matched_keywords": [],
            "selected": False,
        },
    ]

    run_id = analysis_db.create_run(
        "Why did BTC move?",
        "BTC",
        "2026-05-23 09:00:00",
        "2026-05-23 10:00:00",
        evidence_packet,
        manual_prompt="prompt text",
        path=db_path,
    )
    analysis_db.save_answer(
        run_id,
        "answer text",
        manual_prompt="prompt text",
        answer_json={
            "judgement": "news_driven",
            "overall_confidence": 0.7,
            "catalysts": [
                {
                    "news_id": "n1",
                    "confidence": 0.75,
                    "impact_path": "risk appetite improved [#n1]",
                    "direction": "bullish",
                }
            ],
        },
        judgement="news_driven",
        overall_confidence=0.7,
        evidence_selections={"n1": True, "n2": False},
        path=db_path,
    )

    run = analysis_db.get_run(run_id, path=db_path)

    assert run["status"] == "done"
    assert run["selected_count"] == 1
    assert run["answer_parsed"]["judgement"] == "news_driven"
    assert run["evidence_rows"][0]["llm_confidence"] == 0.75
    assert run["evidence_rows"][0]["llm_direction"] == "bullish"

    analysis_db.delete_run(run_id, path=db_path)
    with analysis_db.open_analysis_db(db_path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM analysis_evidence").fetchone()[0] == 0


def test_analysis_db_init_creates_tables(tmp_path):
    db_path = tmp_path / "analysis.sqlite3"

    analysis_db.init_analysis_db(db_path)

    with analysis_db.open_analysis_db(db_path) as conn:
        tables = {
            row[0]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
        }

    assert {"analysis_runs", "analysis_evidence", "screenshots"}.issubset(tables)


def test_analysis_db_links_screenshot_to_run(tmp_path, monkeypatch):
    db_path = tmp_path / "analysis.sqlite3"
    monkeypatch.setattr(analysis_db, "SCREENSHOT_DIR", tmp_path / "screenshots")
    analysis_db.init_analysis_db(db_path)
    screenshot_id = analysis_db.save_screenshot(
        b"fakepng",
        "chart.png",
        user_description="突破截图",
        path=db_path,
    )
    run_id = analysis_db.create_run(
        "Question",
        "BTC",
        "2026-05-23 09:00:00",
        "2026-05-23 10:00:00",
        [],
        screenshot_id=screenshot_id,
        path=db_path,
    )

    run = analysis_db.get_run(run_id, path=db_path)

    assert run["screenshot_id"] == screenshot_id
    assert run["screenshot"]["user_description"] == "突破截图"


def test_get_runs_for_compare_returns_input_order_and_parsed_json(tmp_path):
    db_path = tmp_path / "analysis.sqlite3"
    analysis_db.init_analysis_db(db_path)
    first_id = analysis_db.create_run(
        "First question",
        "ETH",
        "2026-05-23 09:00:00",
        "2026-05-23 10:00:00",
        [{"news_id": "n1", "selected": True}],
        path=db_path,
    )
    second_id = analysis_db.create_run(
        "Second question",
        "ETH",
        "2026-05-24 09:00:00",
        "2026-05-24 10:00:00",
        [{"news_id": "n2", "selected": True}],
        path=db_path,
    )
    analysis_db.save_answer(
        first_id,
        "raw",
        answer_json={"judgement": "news_driven", "catalysts": [{"news_id": "n1"}]},
        judgement="news_driven",
        overall_confidence=0.8,
        path=db_path,
    )

    runs = analysis_db.get_runs_for_compare([second_id, first_id], path=db_path)

    assert [run["id"] for run in runs] == [second_id, first_id]
    assert runs[1]["answer_parsed"]["judgement"] == "news_driven"
    assert runs[1]["evidence_packet"][0]["news_id"] == "n1"


def test_get_runs_for_compare_empty_and_missing_ids(tmp_path):
    db_path = tmp_path / "analysis.sqlite3"
    analysis_db.init_analysis_db(db_path)

    assert analysis_db.get_runs_for_compare([], path=db_path) == []
    assert analysis_db.get_runs_for_compare(["missing"], path=db_path) == []


def test_analysis_db_is_separate_from_business_history(tmp_path):
    history_path = tmp_path / "history.sqlite3"
    analysis_path = tmp_path / "dashboard_analysis.sqlite3"
    conn = create_history_db(history_path)
    insert_flash(conn, "hist-1", "2026-05-23 09:30:00", "BTC title")
    conn.commit()
    conn.close()

    analysis_db.init_analysis_db(analysis_path)
    analysis_db.create_run(
        "Question",
        "BTC",
        "2026-05-23 09:00:00",
        "2026-05-23 10:00:00",
        [],
        path=analysis_path,
    )

    with sqlite3.connect(history_path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM flash_history").fetchone()[0] == 1
        assert "analysis_runs" not in {
            row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        }


def test_save_answer_transitions_to_done(tmp_path):
    db_path = tmp_path / "analysis.sqlite3"
    analysis_db.init_analysis_db(db_path)
    run_id = analysis_db.create_run(
        "Question",
        "ETH",
        "2026-05-23 09:00:00",
        "2026-05-23 10:00:00",
        [],
        path=db_path,
    )

    analysis_db.save_answer(
        run_id,
        "raw answer text",
        answer_json={"judgement": "news_driven", "overall_confidence": 0.75},
        judgement="news_driven",
        overall_confidence=0.75,
        provider_elapsed_ms=12345,
        path=db_path,
    )
    run = analysis_db.get_run(run_id, path=db_path)

    assert run["status"] == "done"
    assert run["answer_text"] == "raw answer text"
    assert run["judgement"] == "news_driven"
    assert run["overall_confidence"] == 0.75
    assert run["provider_elapsed_ms"] == 12345


def test_provider_error_is_persisted_until_success(tmp_path):
    db_path = tmp_path / "analysis.sqlite3"
    analysis_db.init_analysis_db(db_path)
    run_id = analysis_db.create_run(
        "Question",
        "ETH",
        "2026-05-23 09:00:00",
        "2026-05-23 10:00:00",
        [],
        path=db_path,
    )

    analysis_db.save_provider_error(
        run_id,
        "Provider 调用失败：Gemini stopped with finishReason=MAX_TOKENS",
        provider_elapsed_ms=9000,
        path=db_path,
    )
    run = analysis_db.get_run(run_id, path=db_path)

    assert run["status"] == "draft"
    assert "MAX_TOKENS" in run["provider_error"]
    assert run["provider_error_at"]
    assert run["provider_elapsed_ms"] == 9000

    analysis_db.save_answer(
        run_id,
        "raw answer text",
        answer_json={"judgement": "news_driven", "overall_confidence": 0.75},
        judgement="news_driven",
        overall_confidence=0.75,
        path=db_path,
    )
    run = analysis_db.get_run(run_id, path=db_path)

    assert run["status"] == "done"
    assert run["provider_error"] == ""
    assert run["provider_error_at"] == ""


def test_mark_provider_running_tracks_start_and_provider(tmp_path):
    db_path = tmp_path / "analysis.sqlite3"
    analysis_db.init_analysis_db(db_path)
    run_id = analysis_db.create_run(
        "Question",
        "ETH",
        "2026-05-23 09:00:00",
        "2026-05-23 10:00:00",
        [],
        path=db_path,
    )

    started = analysis_db.mark_provider_running(
        run_id,
        provider_name="compatible",
        provider_label="GLM:glm-4.7-flash",
        path=db_path,
    )
    run = analysis_db.get_run(run_id, path=db_path)

    assert started is True
    assert run["status"] == "running"
    assert run["provider_name"] == "compatible"
    assert run["provider_started_at"]
    assert run["model_label"] == "GLM:glm-4.7-flash"
    assert analysis_db.mark_provider_running(run_id, provider_name="gemini", path=db_path) is False


def test_provider_error_returns_running_run_to_draft(tmp_path):
    db_path = tmp_path / "analysis.sqlite3"
    analysis_db.init_analysis_db(db_path)
    run_id = analysis_db.create_run(
        "Question",
        "ETH",
        "2026-05-23 09:00:00",
        "2026-05-23 10:00:00",
        [],
        path=db_path,
    )
    analysis_db.mark_provider_running(run_id, provider_name="gemini", path=db_path)

    analysis_db.save_provider_error(
        run_id,
        "Provider 调用失败：timeout",
        provider_elapsed_ms=42000,
        path=db_path,
    )
    run = analysis_db.get_run(run_id, path=db_path)

    assert run["status"] == "draft"
    assert "timeout" in run["provider_error"]
    assert run["provider_elapsed_ms"] == 42000


def test_list_runs_includes_model_label(tmp_path):
    db_path = tmp_path / "analysis.sqlite3"
    analysis_db.init_analysis_db(db_path)
    run_id = analysis_db.create_run(
        "Question",
        "ETH",
        "2026-05-23 09:00:00",
        "2026-05-23 10:00:00",
        [],
        path=db_path,
    )
    analysis_db.save_answer(
        run_id,
        "raw answer text",
        model_label="gemini:gemini-2.5-flash",
        answer_json={"judgement": "news_driven"},
        judgement="news_driven",
        path=db_path,
    )

    runs = analysis_db.list_runs(path=db_path)

    assert runs[0]["model_label"] == "gemini:gemini-2.5-flash"


def test_export_provider_ab_packet_writes_fixed_inputs(tmp_path):
    db_path = tmp_path / "analysis.sqlite3"
    output_dir = tmp_path / "export"
    analysis_db.init_analysis_db(db_path)
    run_id = analysis_db.create_run(
        "BTC 为何上涨？",
        "BTC",
        "2026-06-07 10:00:00",
        "2026-06-07 11:00:00",
        [
            {
                "news_id": "n1",
                "published_at": "2026-06-07 10:15:00",
                "title": "BTC news",
                "relevance_score": 0.91,
                "selected": True,
            },
            {
                "news_id": "n2",
                "published_at": "2026-06-07 10:20:00",
                "title": "Noise",
                "relevance_score": 0.12,
                "selected": False,
            },
        ],
        manual_prompt="Prompt\n\n【结构化行情上下文】\nBinance Spot BTCUSDT",
        prompt_version="v3",
        path=db_path,
    )

    files = export_run_packet(run_id, db_path=db_path, output_dir=output_dir)

    assert set(files) == {"prompt", "evidence_packet", "scorecard", "metadata"}
    assert (output_dir / "prompt.md").read_text(encoding="utf-8").startswith("Prompt")
    packet = json.loads((output_dir / "evidence_packet.json").read_text(encoding="utf-8"))
    metadata = json.loads((output_dir / "metadata.json").read_text(encoding="utf-8"))
    scorecard = (output_dir / "ab_scorecard.md").read_text(encoding="utf-8")

    assert [item["news_id"] for item in packet] == ["n1", "n2"]
    assert packet[0]["selected"] is True
    assert packet[1]["selected"] is False
    assert metadata["run_id"] == run_id
    assert metadata["prompt_version"] == "v3"
    assert metadata["selected_count"] == 1
    assert metadata["market_context_state"] == "included"
    assert "Gemini" in scorecard
    assert "ChatGPT Plus" in scorecard
    assert "GLM Flash" in scorecard

    with sqlite3.connect(db_path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM analysis_runs").fetchone()[0] == 1


def test_export_provider_ab_packet_missing_run_fails_without_output(tmp_path):
    db_path = tmp_path / "analysis.sqlite3"
    output_dir = tmp_path / "export"
    analysis_db.init_analysis_db(db_path)

    try:
        export_run_packet("missing", db_path=db_path, output_dir=output_dir)
    except ValueError as exc:
        assert "analysis run not found" in str(exc)
    else:
        raise AssertionError("missing run should fail")

    assert not output_dir.exists()


def test_evidence_builder_scores_and_labels_news_id(tmp_path, monkeypatch):
    history_path = tmp_path / "history.sqlite3"
    conn = create_history_db(history_path)
    insert_flash(
        conn,
        "btc-1",
        "2026-05-23 09:30:00",
        "美联储暗示降息，比特币走高",
        "BTC 风险偏好改善",
        "T2_HIGH",
    )
    insert_flash(conn, "noise-1", "2026-05-23 09:31:00", "无关消息", "地方天气", "T0_NONE")
    conn.commit()
    conn.close()
    monkeypatch.setenv("HISTORY_DB", str(history_path))

    packet, boundary = evidence.build_evidence_for_preview(
        "BTC",
        "2026-05-23 09:00:00",
        "2026-05-23 10:00:00",
    )

    assert boundary == {
        "source": "local_sqlite_only",
        "label": "local_sqlite_only",
        "jin10_rest_called": False,
        "market_data_called": False,
    }
    assert [item["news_id"] for item in packet] == ["btc-1"]
    assert packet[0]["relevance_score"] > 0
    assert "BTC" in packet[0]["matched_keywords"] or "比特币" in packet[0]["matched_keywords"]
    assert packet[0]["score_reasons"]


def test_evidence_v2_prioritizes_macro_transmission_over_summary(tmp_path, monkeypatch):
    history_path = tmp_path / "history.sqlite3"
    conn = create_history_db(history_path)
    insert_flash(
        conn,
        "summary",
        "2026-06-05 23:08:00",
        "金十数据整理：欧盘美盘重要新闻汇总",
        "加息 伊朗 美联储 通胀 利率 特朗普 美国 中国",
        "T3_IMPORTANT",
    )
    insert_flash(
        conn,
        "macro",
        "2026-06-05 23:00:00",
        "美国5月非农就业人口远超预期，美元走强",
        "市场上调美联储加息概率，收益率上涨，风险偏好下降",
        "T2_HIGH",
    )
    conn.commit()
    conn.close()
    monkeypatch.setenv("HISTORY_DB", str(history_path))

    packet, _boundary = evidence.build_evidence_for_preview(
        "ETH",
        "2026-06-05 22:43:00",
        "2026-06-05 23:43:00",
    )

    assert [item["news_id"] for item in packet[:2]] == ["macro", "summary"]
    assert "利率/美元/流动性传导" in packet[0]["score_reasons"]
    assert "汇总/预告降权" in packet[1]["score_reasons"]
    assert packet[0]["selected"] is True
    assert packet[1]["selected"] is False
    assert packet[1]["selection_note"] == "汇总/预告默认不选"


def test_evidence_v3_default_selection_filters_low_relevance_noise(tmp_path, monkeypatch):
    history_path = tmp_path / "history.sqlite3"
    conn = create_history_db(history_path)
    insert_flash(
        conn,
        "macro",
        "2026-06-06 13:08:00",
        "美国非农强于预期，美元走强",
        "市场上调美联储加息概率，收益率上涨，风险偏好下降",
        "T2_HIGH",
    )
    insert_flash(conn, "noise", "2026-06-06 12:30:00", "地方停电消息", "与市场无关", "T2_HIGH")
    conn.commit()
    conn.close()
    monkeypatch.setenv("HISTORY_DB", str(history_path))

    packet, _boundary = evidence.build_evidence_for_preview(
        "ETH",
        "2026-06-06 12:00:00",
        "2026-06-06 13:10:00",
    )

    by_id = {item["news_id"]: item for item in packet}
    assert by_id["macro"]["selected"] is True
    assert by_id["noise"]["selected"] is False
    assert by_id["noise"]["selection_note"] == "低相关默认不选"


def test_evidence_builder_returns_empty_on_bad_window():
    packet, boundary = evidence.build_evidence_for_preview("BTC", "bad-date", "2026-05-23 10:00:00")

    assert packet == []
    assert boundary == "invalid_time_window"


def test_evidence_builder_returns_empty_when_end_before_start():
    packet, boundary = evidence.build_evidence_for_preview(
        "BTC",
        "2026-05-23 10:00:00",
        "2026-05-23 09:00:00",
    )

    assert packet == []
    assert boundary == "end_before_start"


def test_prompt_generation_includes_selected_evidence_and_question():
    prompt = manual_ai.generate_prompt(
        question="BTC 为何上涨",
        asset="BTC",
        window_start="2026-05-23 09:00:00",
        window_end="2026-05-23 10:00:00",
        evidence=[
            {
                "news_id": "ev001",
                "published_at": "2026-05-23 09:30:00",
                "title": "美联储暂停加息",
                "content": "",
                "priority_level": "T3_IMPORTANT",
                "news_source": "Reuters",
                "relevance_score": 0.85,
                "matched_keywords": ["美联储"],
                "score_reasons": ["利率/美元/流动性传导"],
                "selected": True,
            }
        ],
    )

    assert "BTC 为何上涨" in prompt
    assert "ev001" in prompt
    assert "美联储暂停加息" in prompt
    assert "利率/美元/流动性传导" in prompt
    assert "优先输出 4-8 条 catalysts" in prompt
    assert "news_driven：一条或几条具体新闻/数据能直接解释主要波动" in prompt
    assert "macro_sentiment：主要是利率、美元、通胀、就业、地缘风险等宏观风险偏好共同传导" in prompt


def test_prompt_generation_includes_optional_market_context():
    prompt = manual_ai.generate_prompt(
        question="BTC 是否新闻驱动",
        asset="BTC",
        window_start="2026-06-02 19:00:00",
        window_end="2026-06-02 20:00:00",
        evidence=[],
        market_context={
            "enabled": True,
            "ok": True,
            "source": "Binance Spot",
            "symbol": "BTCUSDT",
            "interval": "1m",
            "start": "2026-06-02 19:00:00",
            "end": "2026-06-02 20:00:00",
            "summary": {
                "count": 61,
                "first_close": 69470.32,
                "last_close": 69520.12,
                "move": 49.8,
                "move_pct": 0.0717,
                "high": 69600.0,
                "low": 69390.0,
            },
        },
    )

    assert "【结构化行情上下文】" in prompt
    assert "Binance Spot" in prompt
    assert "BTCUSDT" in prompt
    assert "行情上下文只说明价格变化" in prompt


def test_prompt_generation_marks_unavailable_market_context():
    prompt = manual_ai.generate_prompt(
        question="BTC 是否新闻驱动",
        asset="BTC",
        window_start="2026-06-02 19:00:00",
        window_end="2026-06-02 20:00:00",
        evidence=[],
        market_context={
            "enabled": True,
            "ok": False,
            "symbol": "BTCUSDT",
            "interval": "1m",
            "start": "2026-06-02 19:00:00",
            "end": "2026-06-02 20:00:00",
            "error": "market adapter not configured",
        },
    )

    assert "【结构化行情上下文】" in prompt
    assert "行情数据不可用：market adapter not configured" in prompt
    assert "不要把缺失行情数据当作价格没有波动" in prompt


def test_summarize_klines_returns_price_move_stats():
    summary = summarize_klines(
        [
            Kline(
                open_time="2026-06-02 19:00:00",
                open=100.0,
                high=102.0,
                low=99.0,
                close=101.0,
                volume=1.0,
            ),
            Kline(
                open_time="2026-06-02 19:01:00",
                open=101.0,
                high=104.0,
                low=100.0,
                close=103.0,
                volume=2.0,
            ),
        ]
    )

    assert summary == {
        "count": 2,
        "first_close": 101.0,
        "last_close": 103.0,
        "move": 2.0,
        "move_pct": 1.9802,
        "high": 104.0,
        "low": 99.0,
    }


def test_parse_market_context_json_accepts_only_json_objects():
    assert parse_market_context_json('{"enabled": true}') == {"enabled": True}
    assert parse_market_context_json("[]") == {}
    assert parse_market_context_json("{bad json") == {}


def test_market_context_default_requires_explicit_flag_and_adapter(monkeypatch):
    monkeypatch.delenv("MARKET_CONTEXT_DEFAULT_ENABLED", raising=False)
    monkeypatch.setenv("MARKET_ADAPTER", "binance")
    assert market_context_default_enabled() is False

    monkeypatch.setenv("MARKET_CONTEXT_DEFAULT_ENABLED", "1")
    monkeypatch.setenv("MARKET_ADAPTER", "")
    assert market_context_default_enabled() is False

    monkeypatch.setenv("MARKET_CONTEXT_DEFAULT_ENABLED", "1")
    monkeypatch.setenv("MARKET_ADAPTER", "binance")
    assert market_context_default_enabled() is True


def test_prompt_generation_excludes_deselected_evidence():
    prompt = manual_ai.generate_prompt(
        question="q",
        asset="BTC",
        window_start="2026-05-23 09:00:00",
        window_end="2026-05-23 10:00:00",
        evidence=[
            {
                "news_id": "sel01",
                "published_at": "2026-05-23 09:30:00",
                "title": "selected item",
                "priority_level": "T2_HIGH",
                "relevance_score": 0.6,
                "matched_keywords": [],
                "selected": True,
            },
            {
                "news_id": "rej02",
                "published_at": "2026-05-23 09:31:00",
                "title": "rejected item",
                "priority_level": "T1_NORMAL",
                "relevance_score": 0.2,
                "matched_keywords": [],
                "selected": False,
            },
        ],
    )

    assert "sel01" in prompt
    assert "rej02" not in prompt


def test_manual_answer_parse_and_render_links():
    raw = """
    ```json
    {
      "summary": "BTC 主要受新闻推动 [#n1]",
      "catalysts": [{
        "news_id": "n1",
        "time": "2026-05-23 09:30:00",
        "headline": "BTC headline",
        "impact_path": "风险偏好改善带动买盘 [#n1]",
        "confidence": 0.8,
        "direction": "bullish"
      }],
      "missing_evidence": ["成交量"],
      "judgement": "news_driven",
      "overall_confidence": 0.75,
      "caveat": "只基于本地证据"
    }
    ```
    """

    parsed = manual_ai.parse_answer(raw)
    rendered = manual_ai.render_answer_with_links(parsed)

    assert parsed["parse_error"] is False
    assert parsed["catalysts"][0]["news_id"] == "n1"
    assert 'href="/item/n1"' in rendered
    assert "05-23 09:30" in rendered
    assert "[↗ 05-23 09:30]" in rendered
    assert "▲ 偏利多" in rendered
    assert "新闻驱动" in rendered
    assert escape(manual_ai.CONFIDENCE_HELP) in rendered


def test_parse_answer_valid_json():
    parsed = manual_ai.parse_answer(
        '{"summary":"BTC涨","catalysts":[],"missing_evidence":["链上数据"],'
        '"judgement":"news_driven","overall_confidence":0.72,"caveat":"有限"}'
    )

    assert parsed["parse_error"] is False
    assert parsed["judgement"] == "news_driven"
    assert parsed["overall_confidence"] == 0.72


def test_render_answer_localizes_known_english_summary():
    rendered = manual_ai.render_answer_with_links(
        {
            "summary": "Judgement unclear: Evidence direction conflicts with price action.",
            "catalysts": [],
            "missing_evidence": [],
            "judgement": "unclear",
            "overall_confidence": 0.3,
            "caveat": "",
        }
    )

    assert "判断无法确认：证据方向与价格走势冲突。" in rendered
    assert "无法确认" in rendered
    assert "Judgement unclear" not in rendered


def test_parse_answer_unparseable_stores_raw_text():
    parsed = manual_ai.parse_answer("这是完全无法解析的文本，没有 JSON 结构。")

    assert parsed["parse_error"] is True
    assert parsed["raw_text"].startswith("这是完全无法解析")


def test_provider_error_redirect_quotes_message():
    response = provider_error_redirect("run-1", "bad json")

    assert response.status_code == 303
    assert response.headers["location"] == "/analyze/run-1?provider_error=bad+json"

    response = provider_error_redirect("run-1", "bad json", provider_name="compatible")

    assert response.headers["location"] == "/analyze/run-1?provider_error=bad+json&provider=compatible"


def test_analysis_status_label_includes_running():
    assert analysis_status_label("running") == "调用中"
    assert analysis_status_label("done") == "已完成"


def test_format_provider_error_uses_chinese_actionable_copy():
    assert format_provider_error("gemini:gemini-2.5-flash returned invalid JSON; draft was kept") == (
        "模型返回了不可解析 JSON，已保留草稿，请减少证据数量或重新调用。详情：gemini:gemini-2.5-flash"
    )
    assert format_provider_error(
        "GLM:glm-4.7-flash returned invalid JSON; draft was kept; raw preview: ```json bad"
    ) == (
        "模型返回了不可解析 JSON，已保留草稿，请减少证据数量或重新调用。"
        "详情：GLM:glm-4.7-flash; raw preview: ```json bad"
    )
    assert (
        format_provider_error("Gemini stopped with finishReason=MAX_TOKENS")
        == "Provider 调用失败：Gemini 输出被 MAX_TOKENS 截断，已保留草稿；请减少证据数量，或调高 GEMINI_MAX_TOKENS 后重试。"
    )


def test_provider_raw_preview_compacts_and_truncates_text():
    raw = "  hello\n\nworld  " + ("x" * 800)

    preview = provider_raw_preview(raw, limit=20)

    assert preview == "hello world xxxxxxxx..."


def test_provider_system_prompt_adds_glm_only_constraints():
    gemini_prompt = provider_system_prompt("gemini", "gemini-gemini-2.5-flash")
    glm_prompt = provider_system_prompt("compatible", "compatible-glm-4.7-flash")

    assert "GLM 专用补充约束" not in gemini_prompt
    assert "GLM 专用补充约束" in glm_prompt
    assert "必须使用中文" in glm_prompt
    assert "单条 indirect/mixed 证据不得给出 news_driven" in glm_prompt


def test_provider_review_warning_flags_glm_over_attribution_only():
    run = {
        "model_label": "GLM:glm-4.7-flash",
        "judgement": "news_driven",
        "overall_confidence": 0.75,
        "selected_count": 1,
        "answer_parsed": {"catalysts": [{"direction": "mixed"}]},
    }

    assert "GLM 可能过度归因" in provider_review_warning(run)
    run["model_label"] = "gemini:gemini-2.5-flash"
    assert provider_review_warning(run) == ""


def test_analysis_routes_are_registered_before_dynamic_detail():
    paths = [
        route.path
        for route in app.routes
        if hasattr(route, "path") and str(route.path).startswith("/analyze")
    ]

    assert "/analyze" in paths
    assert "/analyze/preview" in paths
    assert "/analyze/generate-prompt" in paths
    assert "/analyze/save-answer" in paths
    assert "/analyze/compare" in paths
    assert "/analyze/history" in paths
    assert "/analyze/{run_id}/run-provider" in paths
    assert "/analyze/{run_id}" in paths
    assert paths.index("/analyze/compare") < paths.index("/analyze/{run_id}")
    assert paths.index("/analyze/history") < paths.index("/analyze/{run_id}")


def test_dashboard_docs_routes_are_disabled():
    paths = [route.path for route in app.routes if hasattr(route, "path")]

    assert "/docs" not in paths
    assert "/redoc" not in paths
    assert "/openapi.json" not in paths


def test_run_dashboard_loads_dotenv_before_uvicorn():
    run_dashboard = (TEMPLATE_DIR.parent.parent / "run_dashboard.py").read_text()

    assert "from dotenv import load_dotenv" in run_dashboard
    assert "load_dotenv()" in run_dashboard


def test_dashboard_bugfix_routes_are_registered():
    paths = [route.path for route in app.routes if hasattr(route, "path")]

    assert "/static" in paths
    assert "/api/feed/latest-ts" in paths
    assert "/api/feed/page" in paths
    assert "/api/market/klines" in paths
    assert "/api/screenshots/upload" in paths
    assert "/screenshots/{screenshot_id}" in paths
    assert "/aggregation" in paths


def test_query_latest_published_at_respects_current_keyword_filter(tmp_path, monkeypatch):
    history_path = tmp_path / "history.sqlite3"
    conn = create_history_db(history_path)
    matching_ts = history_ts(-20)
    unrelated_ts = history_ts(-5)
    insert_flash(conn, "usd-1", matching_ts, "美元指数走高", "美元走强")
    insert_flash(conn, "btc-newer", unrelated_ts, "比特币快讯", "BTC 价格波动")
    conn.commit()
    conn.close()
    monkeypatch.setenv("HISTORY_DB", str(history_path))

    latest_ts = db.query_latest_published_at(keyword="美元", hours=24)

    assert latest_ts == matching_ts


def test_analyze_nav_active_rules_do_not_double_highlight_history():
    base_template = (TEMPLATE_DIR / "base.html").read_text()

    assert "request.url.path == '/analyze/history'" in base_template
    assert "not request.url.path.startswith('/analyze/history')" in base_template
    assert "not request.url.path.startswith('/analyze/compare')" in base_template
    assert "/analyze/compare" in base_template
    assert ".pill.none" in base_template
    assert ".pill.normal" in base_template
    assert "tr.row-normal" in base_template
    assert "tr.row-none" in base_template
    assert "box-sizing: border-box" in base_template


def test_analyze_compare_template_loads():
    from jinja2 import Environment, FileSystemLoader

    env = Environment(loader=FileSystemLoader(str(TEMPLATE_DIR)))

    assert env.get_template("analyze_compare.html") is not None


def test_analyze_template_has_optional_market_context_controls():
    analyze_template = (TEMPLATE_DIR / "analyze.html").read_text()

    assert "结构化行情上下文（可选）" in analyze_template
    assert 'name="market_enabled"' in analyze_template
    assert 'name="market_symbol"' in analyze_template
    assert 'name="market_interval"' in analyze_template
    assert 'name="market_context_json"' in analyze_template
    assert "默认不请求；开启后请求 market adapter" in analyze_template


def test_provider_and_market_boundaries_are_inert_without_config(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.delenv("COMPAT_LLM_API_KEY", raising=False)
    monkeypatch.delenv("MARKET_ADAPTER", raising=False)

    from dashboard.market.base import configured_market_adapter_name, get_market_adapter
    from dashboard.providers.base import CompletionResult, ProviderError, get_provider, provider_statuses

    assert "text" in CompletionResult.__dataclass_fields__
    assert issubclass(ProviderError, Exception)
    assert get_provider("manual") is None
    assert get_provider("openai") is None
    assert get_provider("anthropic") is None
    assert get_provider("gemini") is None
    assert get_provider("compatible") is None
    assert configured_market_adapter_name() == ""
    assert get_market_adapter() is None
    statuses = {status.key: status for status in provider_statuses()}
    assert statuses["manual"].available is True
    assert statuses["openai"].available is False
    assert statuses["anthropic"].available is False
    assert statuses["gemini"].available is False
    assert statuses["compatible"].available is False


def test_provider_adapters_report_configured_keys_without_network(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai-key")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-anthropic-key")
    monkeypatch.setenv("GEMINI_API_KEY", "test-gemini-key")
    monkeypatch.setenv("COMPAT_LLM_API_KEY", "test-compatible-key")
    monkeypatch.setenv("COMPAT_LLM_LABEL", "compatible")

    from dashboard.providers.base import get_provider

    assert get_provider("openai").is_available() is True
    assert get_provider("anthropic").is_available() is True
    assert get_provider("gemini").is_available() is True
    assert get_provider("compatible").is_available() is True


def test_provider_adapters_parse_successful_responses(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-anthropic-key")
    monkeypatch.setenv("GEMINI_API_KEY", "test-gemini-key")
    monkeypatch.setenv("COMPAT_LLM_API_KEY", "test-compatible-key")
    monkeypatch.setenv("COMPAT_LLM_LABEL", "compatible")

    from dashboard.providers.anthropic_provider import AnthropicProvider
    from dashboard.providers.compatible_provider import OpenAICompatibleProvider
    from dashboard.providers.gemini_provider import GeminiProvider

    class FakeAnthropic(AnthropicProvider):
        def _post_json(self, payload, *, api_key):
            assert api_key == "test-anthropic-key"
            return {
                "model": "claude-test",
                "content": [{"type": "text", "text": '{"judgement":"news_driven"}'}],
                "usage": {"input_tokens": 11, "output_tokens": 7},
            }

    class FakeGemini(GeminiProvider):
        def _post_json(self, payload, *, api_key):
            assert api_key == "test-gemini-key"
            assert payload["generationConfig"]["responseMimeType"] == "application/json"
            return {
                "candidates": [
                    {
                        "finishReason": "STOP",
                        "content": {"parts": [{"text": '{"judgement":"macro_sentiment"}'}]},
                    }
                ],
                "usageMetadata": {"promptTokenCount": 13, "candidatesTokenCount": 5},
            }

    class FakeCompatible(OpenAICompatibleProvider):
        def _post_json(self, payload, *, api_key):
            assert api_key == "test-compatible-key"
            return {
                "model": "deepseek-test",
                "choices": [{"message": {"content": '{"judgement":"unclear"}'}}],
                "usage": {"prompt_tokens": 17, "completion_tokens": 3},
            }

    anthropic = FakeAnthropic().complete("system", "user")
    gemini = FakeGemini().complete("system", "user")
    compatible = FakeCompatible().complete("system", "user")

    assert anthropic.text == '{"judgement":"news_driven"}'
    assert anthropic.model_label == "anthropic:claude-test"
    assert anthropic.input_tokens == 11
    assert gemini.model_label == "gemini:gemini-2.5-flash"
    assert gemini.output_tokens == 5
    assert compatible.model_label == "compatible:deepseek-test"
    assert compatible.input_tokens == 17


def test_gemini_provider_rejects_non_stop_finish_reason(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-gemini-key")

    from dashboard.providers.base import ProviderError
    from dashboard.providers.gemini_provider import GeminiProvider

    class FakeGemini(GeminiProvider):
        def _post_json(self, payload, *, api_key):
            return {
                "candidates": [
                    {
                        "finishReason": "MAX_TOKENS",
                        "content": {"parts": [{"text": '{"summary":"cut"'}]},
                    }
                ],
                "usageMetadata": {"promptTokenCount": 13, "candidatesTokenCount": 5},
            }

    try:
        FakeGemini().complete("system", "user")
    except ProviderError as exc:
        assert "finishReason=MAX_TOKENS" in str(exc)
    else:
        raise AssertionError("ProviderError was not raised")


def test_analyze_templates_expose_provider_run_controls():
    analyze_template = (TEMPLATE_DIR / "analyze.html").read_text()
    history_template = (TEMPLATE_DIR / "analyze_history.html").read_text()
    run_template = (TEMPLATE_DIR / "analyze_run.html").read_text()

    assert "/analyze/{{ run_id }}/run-provider" in analyze_template
    assert "/analyze/{{ run.id }}/run-provider" in run_template
    assert "provider_error" in run_template
    assert "run.provider_error" in run_template
    assert "run.provider_error_at" in run_template
    assert "selected_provider == provider.key" in run_template
    assert "provider_review_warning" in run_template
    assert "provider_elapsed_ms" in run_template
    assert "provider_started_at" in run_template
    assert "analysis_status_label(run.status)" in run_template
    assert "Provider 调用中" in run_template
    assert "后台调用" in run_template
    assert "provider_elapsed_ms" in history_template
    assert "provider_started_at" in history_template
    assert "analysis_status_label(run.status)" in history_template
    assert "judgement_label(run.judgement)" in run_template
    assert "judgement_label(run.judgement)" in history_template
    assert "分析 ID" in run_template
    assert "run-id-chip" in run_template
    assert "待调用 / 待回填" in run_template
    assert "copyDraftPrompt" in run_template
    assert "draft-prompt-text" in run_template
    assert "提交中..." in analyze_template
    assert "调用中..." in run_template


def test_analyze_templates_show_selection_hints_and_asset_market_sync():
    analyze_template = (TEMPLATE_DIR / "analyze.html").read_text()
    history_template = (TEMPLATE_DIR / "analyze_history.html").read_text()
    compare_template = (TEMPLATE_DIR / "analyze_compare.html").read_text()
    run_template = (TEMPLATE_DIR / "analyze_run.html").read_text()

    assert "assetToSymbol" in analyze_template
    assert "ETHUSDT" in analyze_template
    assert 'id="market-enabled" type="checkbox" name="market_enabled" value="1"{{ \' checked\' if market_default_enabled }}' in analyze_template
    assert "market-toggle-card" in analyze_template
    assert "market-switch" in analyze_template
    assert "加入行情摘要" in analyze_template
    assert "未启用，不请求行情数据" in analyze_template
    assert "updateMarketToggleCopy" in analyze_template
    assert "默认不请求，勾选后才请求 market adapter" in analyze_template
    assert "aria-label=\"分析步骤\"" in analyze_template
    assert "aria-disabled=\"true\"" in analyze_template
    assert "history.back()" in analyze_template
    assert "href=\"#answer-section\"" in analyze_template
    assert "id=\"answer-section\"" in analyze_template
    assert "本地相关度分数，不是模型置信度" in analyze_template
    assert "建议 5-10 条" in analyze_template
    assert "最多展示 40 条" in analyze_template
    assert "Provider 更容易超时或触发长度限制" in analyze_template
    assert "减少到 8-10 条高分且不重复的证据" in analyze_template
    assert "' checked' if ev.selected" in analyze_template
    assert "v3 默认只选高相关且不重复的证据" in analyze_template
    assert "选择策略：" in analyze_template
    assert "Prompt 约" in analyze_template
    assert "model_label" in history_template
    assert "待调用 / 待回填" in history_template
    assert "compare-top-btn" in history_template
    assert "topButton.disabled = ids.length !== 2" in history_template
    assert "model_label" in compare_template
    assert "缺失证据来自各次模型原始输出" in compare_template
    assert "run-overview" in run_template
    assert "answer-summary::before" in run_template
    assert 'content: "结论"' in run_template


def test_item_template_shows_published_at_to_second():
    item_template = (TEMPLATE_DIR / "item.html").read_text()

    assert '{{ (center.published_at or "")[:19] }}' in item_template
    assert '{{ (item.published_at or "")[:19] }}' in item_template


def test_item_template_has_user_triggered_market_overlay():
    item_template = (TEMPLATE_DIR / "item.html").read_text()
    vendor_path = TEMPLATE_DIR.parent / "static" / "vendor" / "lightweight-charts"

    assert "行情上下文" in item_template
    assert "id=\"market-load\"" in item_template
    assert "id=\"market-chart\"" in item_template
    assert "lightweight-charts.standalone.production.js" in item_template
    assert "LightweightCharts.CandlestickSeries" in item_template
    assert "LightweightCharts.HistogramSeries" in item_template
    assert "}, 1);" in item_template
    assert "subscribeCrosshairMove" in item_template
    assert "formatBeijingChartTime" in item_template
    assert "formatBeijingTickTime" in item_template
    assert "tickMarkFormatter" in item_template
    assert "priceLineVisible: false" in item_template
    assert "separatorColor" in item_template
    assert "attributionLogo: false" in item_template
    assert "market-volume-divider" in item_template
    assert "chart.timeScale().width()" in item_template
    assert "coordinate < 0 || coordinate > chartWidth" in item_template
    assert "volumeSeries.priceToCoordinate(0)" in item_template
    assert "marketNewsLine.style.height" in item_template
    assert "scaleMargins: {top: 0.06, bottom: 0}" in item_template
    assert "newsChartTime" in item_template
    assert "indexAtOrBeforeNews" in item_template
    assert 'type="datetime-local"' in item_template
    assert "market-window-tabs" in item_template
    assert "marketInputText" in item_template
    assert "开 ${formatNumber(candle.open)}" in item_template
    assert "快讯前收盘" in item_template
    assert "成交量合计" in item_template
    assert "最大单根成交量" in item_template
    assert "#market-panel" in item_template
    assert "已加载 ${data.klines.length} 根 K 线" in item_template
    assert "loadMarketData();" in item_template
    assert "data-news-time" in item_template
    assert "market-table-summary" in item_template
    assert "/api/market/klines?" in item_template
    assert "准备加载行情..." in item_template
    assert "addEventListener(\"click\"" in item_template
    assert (vendor_path / "lightweight-charts.standalone.production.js").exists()
    assert (vendor_path / "LICENSE").exists()


def test_feed_rows_hide_internal_fields_and_empty_messages():
    feed_rows = (TEMPLATE_DIR / "_feed_rows.html").read_text()

    assert "style_flags" not in feed_rows
    assert "is_empty" in feed_rows
    assert "display_content or display_title" in feed_rows
    assert "补拉" in feed_rows
    assert "{{ (item.published_at or '')[:19] }}" in feed_rows
    assert "tg_confirmed_sent_at" in feed_rows


def test_normalize_news_text_collapses_invisible_spacing():
    assert normalize_news_text("  A\u00a0 \n B\tC  ") == "A B C"


def test_multipart_upload_parser_extracts_image_and_description():
    boundary = "abc123"
    body = (
        b"--abc123\r\n"
        b'Content-Disposition: form-data; name="description"\r\n\r\n'
        b"\xe4\xbb\xb7\xe6\xa0\xbc\xe7\xaa\x81\xe7\xa0\xb4\r\n"
        b"--abc123\r\n"
        b'Content-Disposition: form-data; name="file"; filename="chart.png"\r\n'
        b"Content-Type: image/png\r\n\r\n"
        b"\x89PNG\r\n"
        b"--abc123--\r\n"
    )

    file_bytes, filename, mime_type, description = parse_multipart_upload(
        body,
        "multipart/form-data; boundary=abc123",
    )

    assert file_bytes == b"\x89PNG"
    assert filename == "chart.png"
    assert mime_type == "image/png"
    assert description == "价格突破"


def test_screenshot_mime_whitelist_excludes_svg():
    assert "image/png" in ALLOWED_SCREENSHOT_MIME_TYPES
    assert "image/jpeg" in ALLOWED_SCREENSHOT_MIME_TYPES
    assert "image/webp" in ALLOWED_SCREENSHOT_MIME_TYPES
    assert "image/gif" in ALLOWED_SCREENSHOT_MIME_TYPES
    assert "image/svg+xml" not in ALLOWED_SCREENSHOT_MIME_TYPES


def test_append_screenshot_context_includes_manual_description():
    context = append_screenshot_context(
        "原始补充",
        screenshot_id="sc_1",
        screenshot_description="1 分钟 K 线放量突破",
    )

    assert "原始补充" in context
    assert "screenshot_id=sc_1" in context
    assert "1 分钟 K 线放量突破" in context
