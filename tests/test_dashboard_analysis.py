import json
import sqlite3

from dashboard import analysis_db, evidence, manual_ai
from dashboard.app import app


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

    assert boundary == "local_sqlite_only"
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
    assert "/analyze/history" in paths
    assert "/analyze/{run_id}" in paths
    assert paths.index("/analyze/history") < paths.index("/analyze/{run_id}")
