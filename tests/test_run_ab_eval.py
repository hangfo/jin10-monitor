import json
import os
import io
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


def test_validate_args_rejects_invalid_timeout():
    args = run_ab_eval.parse_args(["ar_1", "--timeout", "0"])
    ok, message = run_ab_eval.validate_args(args)
    assert ok is False
    assert "timeout" in message


def test_validate_args_rejects_extreme_timeout():
    args = run_ab_eval.parse_args(["ar_1", "--timeout", "601"])
    ok, message = run_ab_eval.validate_args(args)
    assert ok is False
    assert "between 1 and 600" in message


def test_validate_args_accepts_valid_timeout_and_skip_existing():
    args = run_ab_eval.parse_args(["ar_1", "--timeout", "120", "--skip-existing"])
    ok, message = run_ab_eval.validate_args(args)
    assert ok is True
    assert message == ""
    assert args.timeout == 120
    assert args.skip_existing is True


def test_providers_help_mentions_default_baseline(capsys):
    try:
        run_ab_eval.parse_args(["--help"])
    except SystemExit as exc:
        assert exc.code == 0
    help_text = capsys.readouterr().out
    normalized = " ".join(help_text.split())
    assert "--providers KEY" in help_text
    assert "default when omitted: gemini compatible" in normalized


def test_validate_args_allows_offline_modes_without_run_id():
    args = run_ab_eval.parse_args(["--rebuild-comparisons", "--summary-report"])
    ok, message = run_ab_eval.validate_args(args)
    assert ok is True
    assert message == ""


def test_validate_args_rejects_execute_with_offline_mode():
    args = run_ab_eval.parse_args(["ar_1", "--rebuild-comparisons", "--execute", "--yes"])
    ok, message = run_ab_eval.validate_args(args)
    assert ok is False
    assert "offline report modes" in message


def test_validate_args_rejects_empty_provider_value():
    args = run_ab_eval.parse_args(["ar_1", "--providers", ""])
    ok, message = run_ab_eval.validate_args(args)
    assert ok is False
    assert "empty value" in message


def test_validate_args_manual_provider_message_is_actionable():
    args = run_ab_eval.parse_args(["ar_1", "--providers", "manual"])
    ok, message = run_ab_eval.validate_args(args)
    assert ok is False
    assert "gemini" in message
    assert "manual is not callable" in message


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
    context = json.loads((output_dir / "execution_context.json").read_text(encoding="utf-8"))
    system_prompt = (output_dir / context["providers"]["gemini"]["system_prompt_file"]).read_text(encoding="utf-8")
    assert system_prompt == provider.calls[0][0]
    assert context["run_id"] == run_id
    assert context["user_prompt_sha256"] == run_ab_eval.sha256_text("dashboard prompt")
    assert context["providers"]["gemini"]["system_prompt_sha256"] == run_ab_eval.sha256_text(system_prompt)
    assert (output_dir / context["user_prompt_snapshot_file"]).read_text(encoding="utf-8") == "dashboard prompt"
    assert (output_dir / context["evidence_packet_snapshot_file"]).exists()
    assert "GEMINI_API_KEY" not in json.dumps(context)
    attempts = [json.loads(line) for line in (output_dir / "attempt_history.jsonl").read_text().splitlines()]
    assert len(attempts) == 1
    assert attempts[0]["status"] == "done"
    assert attempts[0]["user_prompt_sha256"] == context["user_prompt_sha256"]
    assert attempts[0]["system_prompt_snapshot_file"] == context["providers"]["gemini"]["system_prompt_file"]


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
    attempts = [json.loads(line) for line in (output_dir / "attempt_history.jsonl").read_text().splitlines()]
    assert attempts[0]["status"] == "failed"
    assert "quota exceeded" in attempts[0]["error"]


def test_evaluate_run_records_provider_factory_none_as_attempt(tmp_path, monkeypatch):
    db_path = tmp_path / "analysis.sqlite3"
    run_id = create_analysis_run(db_path)
    output_dir = tmp_path / "exports" / run_id

    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    results = run_ab_eval.evaluate_run(
        run_id,
        db_path=db_path,
        packet_dir=output_dir,
        provider_keys=["gemini"],
        execute=True,
        refresh_packet=False,
        provider_factory=lambda _key: None,
    )

    assert results[0].status == "failed"
    assert results[0].error == "provider factory returned None"
    latest = json.loads((output_dir / "gemini_result.json").read_text(encoding="utf-8"))
    assert latest["status"] == "failed"
    attempts = [json.loads(line) for line in (output_dir / "attempt_history.jsonl").read_text().splitlines()]
    assert attempts[0]["status"] == "failed"
    assert attempts[0]["error"] == "provider factory returned None"
    context = json.loads((output_dir / "execution_context.json").read_text(encoding="utf-8"))
    assert context["run_id"] == run_id
    assert context["providers"]["gemini"]["provider_name"] == "gemini"
    assert len(context["user_prompt_sha256"]) == 64
    assert len(context["providers"]["gemini"]["system_prompt_sha256"]) == 64


def test_temporary_provider_timeout_restores_env(monkeypatch):
    monkeypatch.setenv("PROVIDER_TIMEOUT_SECONDS", "99")

    with run_ab_eval.temporary_provider_timeout(15):
        assert os.getenv("PROVIDER_TIMEOUT_SECONDS") == "15"

    assert os.getenv("PROVIDER_TIMEOUT_SECONDS") == "99"


def test_temporary_provider_timeout_restores_env_on_exception(monkeypatch):
    monkeypatch.delenv("PROVIDER_TIMEOUT_SECONDS", raising=False)

    try:
        with run_ab_eval.temporary_provider_timeout(7):
            assert os.getenv("PROVIDER_TIMEOUT_SECONDS") == "7"
            raise RuntimeError("boom")
    except RuntimeError:
        pass

    assert os.getenv("PROVIDER_TIMEOUT_SECONDS") is None


def test_evaluate_run_timeout_is_visible_before_provider_factory(tmp_path, monkeypatch):
    db_path = tmp_path / "analysis.sqlite3"
    run_id = create_analysis_run(db_path)
    output_dir = tmp_path / "exports" / run_id
    captured = {}

    def fake_factory(key):
        captured["timeout"] = os.getenv("PROVIDER_TIMEOUT_SECONDS")
        return FakeProvider()

    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setenv("PROVIDER_TIMEOUT_SECONDS", "99")
    results = run_ab_eval.evaluate_run(
        run_id,
        db_path=db_path,
        packet_dir=output_dir,
        provider_keys=["gemini"],
        execute=True,
        refresh_packet=False,
        timeout_seconds=15,
        provider_factory=fake_factory,
    )

    assert results[0].status == "done"
    assert captured["timeout"] == "15"
    assert os.getenv("PROVIDER_TIMEOUT_SECONDS") == "99"


def test_evaluate_run_skip_existing_skips_done_result(tmp_path, monkeypatch):
    db_path = tmp_path / "analysis.sqlite3"
    run_id = create_analysis_run(db_path)
    output_dir = tmp_path / "exports" / run_id
    output_dir.mkdir(parents=True)
    (output_dir / "gemini_result.json").write_text(
        json.dumps({"provider_key": "gemini", "status": "done"}),
        encoding="utf-8",
    )
    calls = []

    def fake_factory(key):
        calls.append(key)
        return FakeProvider()

    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    stdout = io.StringIO()
    results = run_ab_eval.evaluate_run(
        run_id,
        db_path=db_path,
        packet_dir=output_dir,
        provider_keys=["gemini"],
        execute=True,
        refresh_packet=False,
        skip_existing=True,
        provider_factory=fake_factory,
        stdout=stdout,
    )

    assert results == []
    assert calls == []
    assert "skip gemini" in stdout.getvalue()


def test_evaluate_run_skip_existing_reruns_failed_result(tmp_path, monkeypatch):
    db_path = tmp_path / "analysis.sqlite3"
    run_id = create_analysis_run(db_path)
    output_dir = tmp_path / "exports" / run_id
    output_dir.mkdir(parents=True)
    (output_dir / "gemini_result.json").write_text(
        json.dumps({"provider_key": "gemini", "status": "failed", "error": "timeout"}),
        encoding="utf-8",
    )
    calls = []

    def fake_factory(key):
        calls.append(key)
        return FakeProvider()

    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    results = run_ab_eval.evaluate_run(
        run_id,
        db_path=db_path,
        packet_dir=output_dir,
        provider_keys=["gemini"],
        execute=True,
        refresh_packet=False,
        skip_existing=True,
        provider_factory=fake_factory,
    )

    assert calls == ["gemini"]
    assert results[0].status == "done"


def test_append_attempt_history_preserves_failure_then_retry(tmp_path):
    hashes = {
        "user_prompt_sha256": "user-hash",
        "evidence_packet_sha256": "evidence-hash",
        "system_prompt_sha256": "system-hash",
    }
    failed = run_ab_eval.EvalResult(
        run_id="ar_retry",
        provider_key="compatible",
        provider_name="GLM",
        status="failed",
        error="timeout",
    )
    done = run_ab_eval.EvalResult(
        run_id="ar_retry",
        provider_key="compatible",
        provider_name="GLM",
        status="done",
        model_label="GLM:test",
        json_parse_stable=True,
    )

    run_ab_eval.append_attempt_history(tmp_path, failed, timeout_seconds=120, hashes=hashes)
    run_ab_eval.append_attempt_history(tmp_path, done, timeout_seconds=180, hashes=hashes)

    attempts = [json.loads(line) for line in (tmp_path / "attempt_history.jsonl").read_text().splitlines()]
    assert [attempt["status"] for attempt in attempts] == ["failed", "done"]
    assert [attempt["timeout_override_seconds"] for attempt in attempts] == [120, 180]
    assert all(attempt["system_prompt_sha256"] == "system-hash" for attempt in attempts)


def test_public_provider_config_excludes_secrets(monkeypatch):
    monkeypatch.setenv("GEMINI_MODEL", "gemini-test")
    monkeypatch.setenv("GEMINI_MAX_TOKENS", "4096")
    monkeypatch.setenv("GEMINI_API_KEY", "must-not-leak")

    config = run_ab_eval.public_provider_config("gemini")

    assert config == {"GEMINI_MODEL": "gemini-test", "GEMINI_MAX_TOKENS": "4096"}


def test_write_comparison_summarizes_multiple_provider_results(tmp_path):
    gemini = run_ab_eval.EvalResult(
        run_id="ar_1",
        provider_key="gemini",
        provider_name="Gemini",
        status="done",
        model_label="gemini:test",
        elapsed_seconds=3.2,
        input_tokens=10,
        output_tokens=5,
        finish_reason="STOP",
        json_parse_stable=True,
        parsed={
            "judgement": "news_driven",
            "overall_confidence": 0.72,
            "catalysts": [{"news_id": "n1"}],
            "missing_evidence": [],
        },
        raw_output="{}",
    )
    compatible = run_ab_eval.EvalResult(
        run_id="ar_1",
        provider_key="compatible",
        provider_name="GLM",
        status="done",
        model_label="GLM:test",
        elapsed_seconds=8.5,
        input_tokens=11,
        output_tokens=6,
        json_parse_stable=True,
        parsed={
            "judgement": "macro_sentiment",
            "overall_confidence": 0.65,
            "catalysts": [{"news_id": "n1"}, {"news_id": "n2"}],
            "missing_evidence": ["volume"],
        },
        raw_output="{}",
    )
    run_ab_eval.write_result_files(tmp_path, gemini)
    run_ab_eval.write_result_files(tmp_path, compatible)

    path = run_ab_eval.write_comparison(tmp_path, "ar_1", ["gemini", "compatible"])

    assert path is not None
    text = path.read_text(encoding="utf-8")
    assert "| judgement | news_driven | macro_sentiment |" in text
    assert "| catalysts 数量 | 1 | 2 |" in text
    assert "关键催化覆盖" in text


def test_write_comparison_skips_single_provider(tmp_path):
    result = run_ab_eval.EvalResult(
        run_id="ar_1",
        provider_key="gemini",
        provider_name="Gemini",
        status="done",
    )
    run_ab_eval.write_result_files(tmp_path, result)

    assert run_ab_eval.write_comparison(tmp_path, "ar_1", ["gemini"]) is None
    assert not (tmp_path / "comparison.md").exists()


def test_rebuild_existing_comparisons_discovers_provider_results(tmp_path):
    run_dir = tmp_path / "ar_1"
    run_dir.mkdir()
    gemini = run_ab_eval.EvalResult(
        run_id="ar_1",
        provider_key="gemini",
        provider_name="Gemini",
        status="done",
        json_parse_stable=True,
        parsed={"judgement": "news_driven", "catalysts": [], "missing_evidence": []},
    )
    compatible = run_ab_eval.EvalResult(
        run_id="ar_1",
        provider_key="compatible",
        provider_name="GLM",
        status="done",
        json_parse_stable=True,
        parsed={"judgement": "macro_sentiment", "catalysts": [{"news_id": "n1"}], "missing_evidence": ["volume"]},
    )
    run_ab_eval.write_result_files(run_dir, compatible)
    run_ab_eval.write_result_files(run_dir, gemini)

    written = run_ab_eval.rebuild_existing_comparisons([("ar_1", run_dir)])

    assert written == [run_dir / "comparison.md"]
    text = (run_dir / "comparison.md").read_text(encoding="utf-8")
    assert "| judgement | news_driven | macro_sentiment |" in text


def test_write_summary_report_summarizes_existing_results(tmp_path):
    run_dir = tmp_path / "ar_1"
    run_dir.mkdir()
    (run_dir / "metadata.json").write_text(
        json.dumps({"asset": "ETH", "question": "ETH why moved?"}),
        encoding="utf-8",
    )
    result = run_ab_eval.EvalResult(
        run_id="ar_1",
        provider_key="gemini",
        provider_name="Gemini",
        status="done",
        model_label="gemini:test",
        elapsed_seconds=2.5,
        input_tokens=10,
        output_tokens=7,
        json_parse_stable=True,
        parsed={
            "judgement": "news_driven",
            "overall_confidence": 0.8,
            "catalysts": [{"news_id": "n1"}, {"news_id": "n1"}],
            "missing_evidence": [],
        },
    )
    run_ab_eval.write_result_files(run_dir, result)
    output_path = tmp_path / "summary.md"

    path = run_ab_eval.write_summary_report(output_path, [("ar_1", run_dir)])

    assert path == output_path
    text = output_path.read_text(encoding="utf-8")
    assert "Provider A/B Batch Summary" in text
    assert "| model |" in text
    assert "gemini:test" in text
    assert "| ar_1 | ETH | gemini | gemini:test | done | news_driven | 0.8 | 2 | 0 | n1 | yes |" in text
    assert "ETH why moved?" in text


def test_write_summary_report_model_label_distinguishes_variants(tmp_path):
    run_dir = tmp_path / "ar_model"
    run_dir.mkdir()
    (run_dir / "metadata.json").write_text(
        json.dumps({"asset": "BTC", "question": "BTC move?"}),
        encoding="utf-8",
    )
    for model_label in ["gemini-2.5-pro", "gemini-2.0-flash"]:
        key = f"gemini_{model_label.replace('-', '_').replace('.', '_')}"
        result = run_ab_eval.EvalResult(
            run_id="ar_model",
            provider_key=key,
            provider_name="Gemini",
            status="done",
            model_label=model_label,
            json_parse_stable=True,
            parsed={"judgement": "unclear", "catalysts": [], "missing_evidence": []},
        )
        run_ab_eval.write_result_files(run_dir, result)

    output_path = tmp_path / "model_summary.md"
    run_ab_eval.write_summary_report(output_path, [("ar_model", run_dir)])
    text = output_path.read_text(encoding="utf-8")

    assert "gemini-2.5-pro" in text
    assert "gemini-2.0-flash" in text


def test_main_offline_summary_and_rebuild_scan_output_root(tmp_path):
    run_dir = tmp_path / "ar_1"
    run_dir.mkdir()
    for key, judgement in [("gemini", "news_driven"), ("compatible", "macro_sentiment")]:
        result = run_ab_eval.EvalResult(
            run_id="ar_1",
            provider_key=key,
            provider_name=key,
            status="done",
            json_parse_stable=True,
            parsed={"judgement": judgement, "catalysts": [], "missing_evidence": []},
        )
        run_ab_eval.write_result_files(run_dir, result)

    code = run_ab_eval.main(["--output-root", str(tmp_path), "--rebuild-comparisons", "--summary-report"])

    assert code == 0
    assert (run_dir / "comparison.md").exists()
    assert (tmp_path / "summary.md").exists()


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
    assert "Batch completed; no provider calls executed" in capsys.readouterr().out


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
