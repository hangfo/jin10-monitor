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
    parse_market_context_json,
    normalize_news_text,
    parse_multipart_upload,
    summarize_klines,
)
from dashboard.market.base import Kline

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
        path=db_path,
    )
    run = analysis_db.get_run(run_id, path=db_path)

    assert run["status"] == "done"
    assert run["answer_text"] == "raw answer text"
    assert run["judgement"] == "news_driven"
    assert run["overall_confidence"] == 0.75


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
                "selected": True,
            }
        ],
    )

    assert "BTC 为何上涨" in prompt
    assert "ev001" in prompt
    assert "美联储暂停加息" in prompt


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
    assert escape(manual_ai.CONFIDENCE_HELP) in rendered


def test_parse_answer_valid_json():
    parsed = manual_ai.parse_answer(
        '{"summary":"BTC涨","catalysts":[],"missing_evidence":["链上数据"],'
        '"judgement":"news_driven","overall_confidence":0.72,"caveat":"有限"}'
    )

    assert parsed["parse_error"] is False
    assert parsed["judgement"] == "news_driven"
    assert parsed["overall_confidence"] == 0.72


def test_parse_answer_unparseable_stores_raw_text():
    parsed = manual_ai.parse_answer("这是完全无法解析的文本，没有 JSON 结构。")

    assert parsed["parse_error"] is True
    assert parsed["raw_text"].startswith("这是完全无法解析")


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
    assert "只在勾选后请求 market adapter" in analyze_template


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

    from dashboard.providers.base import get_provider

    assert get_provider("openai").is_available() is True
    assert get_provider("anthropic").is_available() is True
    assert get_provider("gemini").is_available() is True
    assert get_provider("compatible").is_available() is True


def test_provider_adapters_parse_successful_responses(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-anthropic-key")
    monkeypatch.setenv("GEMINI_API_KEY", "test-gemini-key")
    monkeypatch.setenv("COMPAT_LLM_API_KEY", "test-compatible-key")

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
            return {
                "candidates": [{"content": {"parts": [{"text": '{"judgement":"macro_sentiment"}'}]}}],
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


def test_analyze_templates_expose_provider_run_controls():
    analyze_template = (TEMPLATE_DIR / "analyze.html").read_text()
    run_template = (TEMPLATE_DIR / "analyze_run.html").read_text()

    assert "/analyze/{{ run_id }}/run-provider" in analyze_template
    assert "/analyze/{{ run.id }}/run-provider" in run_template
    assert "provider_error" in run_template


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
