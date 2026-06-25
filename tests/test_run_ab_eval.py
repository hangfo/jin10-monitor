import json
import os
from pathlib import Path

from dashboard import analysis_db
from dashboard.providers.base import CompletionResult
from scripts import run_ab_eval


def create_analysis_run(db_path: Path, *, manual_prompt: str = "prompt text") -> str:
    analysis_db.init_analysis_db(db_path)
    evidence_packet = [
        {
            "news_id": "n1",
            "published_at": "2026-06-25 09:30:00",
            "title": "BTC ETF inflow rises",
            "content": "BTC spot ETF records inflows.",
            "relevance_score": 0.88,
            "selected": True,
            "matched_keywords": ["BTC"],
        }
    ]
    return analysis_db.create_run(
        "Why did BTC move?",
        "BTC",
        "2026-06-25 09:00:00",
        "2026-06-25 10:00:00",
        evidence_packet,
        manual_prompt=manual_prompt,
        path=db_path,
    )


class FakeProvider:
    name = "gemini-fake"

    def __init__(self):
        self.calls = []

    def complete(self, system_prompt, user_prompt):
        self.calls.append((system_prompt, user_prompt))
        return CompletionResult(
            text=json.dumps(
                {
                    "summary": "news driven",
                    "catalysts": [
                        {
                            "news_id": "n1",
                            "time": "2026-06-25 09:30:00",
                            "headline": "ETF inflow",
                            "impact_path": "ETF inflow improves risk appetite [#n1]",
                            "confidence": 0.7,
                            "direction": "bullish",
                        }
                    ],
                    "missing_evidence": [],
                    "judgement": "news_driven",
                    "overall_confidence": 0.72,
                    "caveat": "short window",
                }
            ),
            model_label="gemini:fake",
            input_tokens=100,
            output_tokens=80,
            finish_reason="STOP",
        )


def test_validate_args_requires_run_id():
    args = run_ab_eval.parse_args([])
    ok, message = run_ab_eval.validate_args(args)
    assert ok is False
    assert "run_id" in message


def test_validate_args_rejects_execute_without_yes():
    args = run_ab_eval.parse_args(["ar_1", "--execute"])
    ok, message = run_ab_eval.validate_args(args)
    assert ok is False
    assert "--execute and --yes" in message


def test_validate_args_rejects_dry_run_with_execute():
    args = run_ab_eval.parse_args(["ar_1", "--dry-run", "--execute", "--yes"])
    ok, message = run_ab_eval.validate_args(args)
    assert ok is False
    assert "--dry-run cannot be combined" in message


def test_validate_args_rejects_oversized_execute_batch():
    args = run_ab_eval.parse_args(["--run-ids", "ar_1", "ar_2", "ar_3", "--execute", "--yes", "--max-runs", "2"])
    ok, message = run_ab_eval.validate_args(args)
    assert ok is False
    assert "refuses 3 runs" in message


def test_normalize_provider_keys_keeps_gemini_compatible_baseline():
    assert run_ab_eval.normalize_provider_keys(None) == ["gemini", "compatible"]
    assert run_ab_eval.normalize_provider_keys(["glm", "manual", "gemini", "glm"]) == ["compatible", "gemini"]


def test_parse_provider_json_handles_markdown_fenced_json():
    ok, parsed = run_ab_eval.parse_provider_json(
        """```json
{"summary":"x","judgement":"unclear","overall_confidence":0.2,"catalysts":[],"missing_evidence":[],"caveat":"y"}
```"""
    )
    assert ok is True
    assert parsed["judgement"] == "unclear"


def test_parse_provider_json_rejects_plain_text():
    ok, parsed = run_ab_eval.parse_provider_json("not json")
    assert ok is False
    assert parsed == {}


def test_load_local_dotenv_reads_provider_config(monkeypatch, tmp_path):
    env_path = tmp_path / ".env"
    env_path.write_text("GEMINI_API_KEY=dotenv-gemini\nCOMPAT_LLM_LABEL=GLM\n", encoding="utf-8")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("COMPAT_LLM_LABEL", raising=False)

    assert run_ab_eval.load_local_dotenv(env_path) is True

    assert os.getenv("GEMINI_API_KEY") == "dotenv-gemini"
    assert os.getenv("COMPAT_LLM_LABEL") == "GLM"


def test_load_local_dotenv_preserves_shell_env(monkeypatch, tmp_path):
    env_path = tmp_path / ".env"
    env_path.write_text("GEMINI_API_KEY=dotenv-gemini\n", encoding="utf-8")
    monkeypatch.setenv("GEMINI_API_KEY", "shell-gemini")

    assert run_ab_eval.load_local_dotenv(env_path) is True

    assert os.getenv("GEMINI_API_KEY") == "shell-gemini"


def test_evaluate_run_dry_run_exports_packet_but_does_not_call_provider(tmp_path, monkeypatch):
    db_path = tmp_path / "analysis.sqlite3"
    run_id = create_analysis_run(db_path)
    output_dir = tmp_path / "exports" / run_id
    provider = FakeProvider()

    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    results = run_ab_eval.evaluate_run(
        run_id,
        db_path=db_path,
        packet_dir=output_dir,
        provider_keys=["gemini"],
        execute=False,
        refresh_packet=False,
        provider_factory=lambda _key: provider,
    )

    assert results == []
    assert provider.calls == []
    assert (output_dir / "prompt.md").exists()
    assert (output_dir / "evidence_packet.json").exists()
    plan = json.loads((output_dir / "eval_plan.json").read_text(encoding="utf-8"))
    assert plan["mode"] == "dry_run"
    assert plan["providers"][0]["will_run"] is True
    assert not (output_dir / "gemini_raw.txt").exists()


def test_evaluate_run_execute_writes_raw_parsed_and_scorecard(tmp_path, monkeypatch):
    db_path = tmp_path / "analysis.sqlite3"
    run_id = create_analysis_run(db_path, manual_prompt="dashboard prompt")
    output_dir = tmp_path / "exports" / run_id
    provider = FakeProvider()

    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    results = run_ab_eval.evaluate_run(
        run_id,
        db_path=db_path,
        packet_dir=output_dir,
        provider_keys=["gemini"],
        execute=True,
        refresh_packet=False,
        provider_factory=lambda _key: provider,
    )

    assert len(results) == 1
    assert results[0].status == "done"
    assert results[0].json_parse_stable is True
    assert "严格执行用户 Prompt" in provider.calls[0][0]
    assert provider.calls[0][1] == "dashboard prompt"
    assert (output_dir / "gemini_raw.txt").exists()
    parsed = json.loads((output_dir / "gemini_parsed.json").read_text(encoding="utf-8"))
    assert parsed["judgement"] == "news_driven"
    eval_results = json.loads((output_dir / "eval_results.json").read_text(encoding="utf-8"))
    assert eval_results["results"][0]["model_label"] == "gemini:fake"
    assert "自动 Provider A/B 结果" in (output_dir / "ab_scorecard.md").read_text(encoding="utf-8")


def test_evaluate_run_execute_records_provider_failure(tmp_path, monkeypatch):
    db_path = tmp_path / "analysis.sqlite3"
    run_id = create_analysis_run(db_path)
    output_dir = tmp_path / "exports" / run_id

    class FailingProvider:
        name = "gemini-failing"

        def complete(self, system_prompt, user_prompt):
            raise RuntimeError("quota exceeded")

    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    results = run_ab_eval.evaluate_run(
        run_id,
        db_path=db_path,
        packet_dir=output_dir,
        provider_keys=["gemini"],
        execute=True,
        refresh_packet=False,
        provider_factory=lambda _key: FailingProvider(),
    )

    assert results[0].status == "failed"
    assert "quota exceeded" in results[0].error
    assert "quota exceeded" in (output_dir / "gemini_raw.txt").read_text(encoding="utf-8")
    assert not (output_dir / "gemini_parsed.json").exists()


def test_main_dry_run_returns_zero_and_writes_plan(tmp_path, monkeypatch):
    db_path = tmp_path / "analysis.sqlite3"
    run_id = create_analysis_run(db_path)
    output_root = tmp_path / "exports"

    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    code = run_ab_eval.main(
        [
            run_id,
            "--db",
            str(db_path),
            "--output-root",
            str(output_root),
            "--providers",
            "gemini",
        ]
    )

    assert code == 0
    assert (output_root / run_id / "eval_plan.json").exists()


def test_print_batch_summary_handles_dry_run(capsys):
    run_ab_eval.print_batch_summary({"ar_1": []})
    assert "Batch dry-run completed" in capsys.readouterr().out


def test_write_result_files_sanitizes_provider_filename(tmp_path):
    result = run_ab_eval.EvalResult(
        run_id="ar_1",
        provider_key="compatible",
        provider_name="GLM:glm/4.7",
        status="done",
        raw_output="{}",
    )
    files = run_ab_eval.write_result_files(tmp_path, result)
    assert files["raw"].name == "compatible_raw.txt"
    assert files["metadata"].name == "compatible_result.json"


def test_write_result_files_removes_stale_parsed_json(tmp_path):
    stale = tmp_path / "gemini_parsed.json"
    stale.write_text('{"old": true}', encoding="utf-8")
    result = run_ab_eval.EvalResult(
        run_id="ar_1",
        provider_key="gemini",
        provider_name="gemini-fake",
        status="failed",
        error="timeout",
        json_parse_stable=False,
    )
    run_ab_eval.write_result_files(tmp_path, result)
    assert not stale.exists()
