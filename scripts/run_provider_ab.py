#!/usr/bin/env python3
"""Run offline provider A/B calls for saved dashboard analysis packets.

The runner is intentionally read-only against the analysis database. It exports
fixed prompt/evidence packets, calls the selected providers with those fixed
inputs, and writes raw outputs plus a compact markdown summary under exports/.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import sys
import time
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - python-dotenv is a project dependency.
    load_dotenv = None  # type: ignore[assignment]

BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_ANALYSIS_DB = BASE_DIR / "data" / "dashboard_analysis.sqlite3"
DEFAULT_PACKET_ROOT = BASE_DIR / "exports" / "provider_ab"
DEFAULT_RUN_ROOT = BASE_DIR / "exports" / "provider_ab_runs"
DEFAULT_PROVIDERS = ("gemini", "compatible")

if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Gemini/GLM A/B on fixed dashboard analysis packets.")
    parser.add_argument("run_ids", nargs="+", help="analysis_runs.id values to export and run")
    parser.add_argument("--db", type=Path, default=DEFAULT_ANALYSIS_DB, help="analysis sqlite path")
    parser.add_argument("--packet-root", type=Path, default=DEFAULT_PACKET_ROOT, help="fixed packet export root")
    parser.add_argument("--output-dir", type=Path, default=None, help="output directory for this run")
    parser.add_argument(
        "--providers",
        default=",".join(DEFAULT_PROVIDERS),
        help="comma-separated provider keys; default: gemini,compatible",
    )
    parser.add_argument("--retry", type=int, default=1, help="retry count for retryable provider failures")
    parser.add_argument("--retry-delay", type=float, default=45.0, help="seconds to sleep between retries")
    parser.add_argument("--between-calls", type=float, default=0.0, help="seconds to sleep between provider calls")
    parser.add_argument("--provider-timeout", type=float, default=180.0, help="PROVIDER_TIMEOUT_SECONDS override")
    parser.add_argument("--gemini-max-tokens", type=int, default=4096, help="GEMINI_MAX_TOKENS override")
    parser.add_argument("--compatible-max-tokens", type=int, default=1800, help="COMPAT_LLM_MAX_TOKENS override")
    parser.add_argument("--no-dotenv", action="store_true", help="do not load .env from the project root")
    return parser.parse_args()


def load_project_env(*, no_dotenv: bool = False) -> None:
    if no_dotenv or load_dotenv is None:
        return
    load_dotenv(BASE_DIR / ".env")


def apply_provider_env(args: argparse.Namespace) -> None:
    os.environ["PROVIDER_TIMEOUT_SECONDS"] = str(max(1.0, float(args.provider_timeout)))
    os.environ["GEMINI_MAX_TOKENS"] = str(max(1, int(args.gemini_max_tokens)))
    os.environ["COMPAT_LLM_MAX_TOKENS"] = str(max(1, int(args.compatible_max_tokens)))


def provider_list(raw: str) -> list[str]:
    providers = [item.strip().lower() for item in str(raw or "").split(",") if item.strip()]
    return providers or list(DEFAULT_PROVIDERS)


def safe_dir_name(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(value or "").strip())
    return cleaned[:120] or "packet"


def short_text(value: object, *, limit: int = 150) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


def answer_metrics(parsed: dict[str, Any]) -> dict[str, Any]:
    catalysts = parsed.get("catalysts") if isinstance(parsed.get("catalysts"), list) else []
    news_ids = [
        str(item.get("news_id"))
        for item in catalysts
        if isinstance(item, dict) and item.get("news_id")
    ]
    missing = parsed.get("missing_evidence")
    if isinstance(missing, list):
        missing_count = len(missing)
    elif isinstance(missing, str):
        missing_count = 1 if missing.strip() else 0
    else:
        missing_count = 0
    return {
        "judgement": str(parsed.get("judgement") or ""),
        "overall_confidence": parsed.get("overall_confidence"),
        "summary": str(parsed.get("summary") or ""),
        "catalyst_count": len(catalysts),
        "duplicate_news_id_count": sum(count - 1 for count in Counter(news_ids).values() if count > 1),
        "missing_evidence_count": missing_count,
        "parse_error": bool(parsed.get("parse_error")),
    }


def is_retryable_error(error: str) -> bool:
    lowered = str(error or "").lower()
    return any(
        token in lowered
        for token in (
            "429",
            "503",
            "unavailable",
            "high demand",
            "访问量过大",
            "rate limit",
            "temporarily",
        )
    )


def ensure_packet(run_id: str, *, db_path: Path, packet_root: Path) -> Path:
    from scripts.export_provider_ab_packet import export_run_packet

    output_dir = packet_root / run_id
    prompt_path = output_dir / "prompt.md"
    metadata_path = output_dir / "metadata.json"
    if prompt_path.exists() and metadata_path.exists():
        return output_dir
    export_run_packet(run_id, db_path=db_path, output_dir=output_dir)
    return output_dir


def call_provider(packet_dir: Path, *, provider_name: str, attempt: int) -> dict[str, Any]:
    from dashboard.app import provider_system_prompt
    from dashboard.manual_ai import parse_answer
    from dashboard.providers.base import ProviderError, get_provider

    prompt = (packet_dir / "prompt.md").read_text(encoding="utf-8")
    metadata = json.loads((packet_dir / "metadata.json").read_text(encoding="utf-8"))
    provider = get_provider(provider_name)
    started = time.monotonic()
    record: dict[str, Any] = {
        "source_run_id": str(metadata.get("run_id") or packet_dir.name),
        "provider_key": provider_name,
        "attempt": attempt,
        "source_metadata": metadata,
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    if not provider:
        record.update(ok=False, error="provider not available")
        return record
    try:
        result = provider.complete(provider_system_prompt(provider_name, provider.name), prompt)
        parsed = parse_answer(result.text)
        record.update(
            ok=True,
            provider_name=provider.name,
            model_label=result.model_label,
            elapsed_ms=int((time.monotonic() - started) * 1000),
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
            finish_reason=result.finish_reason,
            raw_text=result.text,
            parsed=parsed,
            metrics=answer_metrics(parsed),
        )
    except ProviderError as exc:
        record.update(
            ok=False,
            provider_name=provider.name,
            elapsed_ms=int((time.monotonic() - started) * 1000),
            error=str(exc),
        )
    except Exception as exc:  # pragma: no cover - defensive for ad-hoc provider runs.
        record.update(
            ok=False,
            provider_name=getattr(provider, "name", ""),
            elapsed_ms=int((time.monotonic() - started) * 1000),
            error=f"{type(exc).__name__}: {exc}",
        )
    return record


def run_with_retries(
    packet_dir: Path,
    *,
    provider_name: str,
    retry_count: int,
    retry_delay_seconds: float,
    progress: bool = True,
) -> dict[str, Any]:
    attempts = max(1, int(retry_count) + 1)
    record: dict[str, Any] = {}
    for attempt in range(1, attempts + 1):
        record = call_provider(packet_dir, provider_name=provider_name, attempt=attempt)
        error = str(record.get("error") or "")
        should_retry = (not record.get("ok")) and attempt < attempts and is_retryable_error(error)
        if not should_retry:
            return record
        if progress:
            print(
                f"{packet_dir.name}\t{provider_name}\tretryable failure on attempt {attempt}; sleeping {retry_delay_seconds:.0f}s",
                flush=True,
            )
        time.sleep(max(0.0, float(retry_delay_seconds)))
    return record


def render_summary(results: Iterable[dict[str, Any]]) -> str:
    lines = [
        "# Provider A/B Offline Run",
        "",
        f"Generated: `{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}`",
        "",
        "| Source Run | Provider | Model | OK | Attempt | Elapsed | Judgement | Confidence | Catalysts | Missing | Dup IDs | Summary/Error |",
        "| --- | --- | --- | --- | ---: | ---: | --- | ---: | ---: | ---: | ---: | --- |",
    ]
    for result in results:
        metrics = result.get("metrics") if isinstance(result.get("metrics"), dict) else {}
        summary = short_text(metrics.get("summary") or result.get("error") or "").replace("|", "/")
        lines.append(
            "| {run_id} | {provider} | {model} | {ok} | {attempt} | {elapsed} | {judgement} | {confidence} | {catalysts} | {missing} | {dup} | {summary} |".format(
                run_id=result.get("source_run_id") or "",
                provider=result.get("provider_key") or "",
                model=result.get("model_label") or result.get("provider_name") or "",
                ok="yes" if result.get("ok") else "no",
                attempt=result.get("attempt") or "",
                elapsed=result.get("elapsed_ms") or 0,
                judgement=metrics.get("judgement") or "",
                confidence=metrics.get("overall_confidence") if metrics.get("overall_confidence") is not None else "",
                catalysts=metrics.get("catalyst_count") if metrics else "",
                missing=metrics.get("missing_evidence_count") if metrics else "",
                dup=metrics.get("duplicate_news_id_count") if metrics else "",
                summary=summary,
            )
        )
    return "\n".join(lines) + "\n"


def run_ab(args: argparse.Namespace) -> tuple[Path, list[dict[str, Any]]]:
    db_path = args.db.expanduser().resolve()
    packet_root = args.packet_root.expanduser().resolve()
    output_dir = args.output_dir or DEFAULT_RUN_ROOT / datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = output_dir.expanduser().resolve()
    providers = provider_list(args.providers)
    output_dir.mkdir(parents=True, exist_ok=True)
    results: list[dict[str, Any]] = []

    for run_id in args.run_ids:
        packet_dir = ensure_packet(run_id, db_path=db_path, packet_root=packet_root)
        for provider_name in providers:
            if results and float(args.between_calls) > 0:
                time.sleep(max(0.0, float(args.between_calls)))
            record = run_with_retries(
                packet_dir,
                provider_name=provider_name,
                retry_count=max(0, int(args.retry)),
                retry_delay_seconds=max(0.0, float(args.retry_delay)),
            )
            run_output_dir = output_dir / safe_dir_name(run_id)
            run_output_dir.mkdir(parents=True, exist_ok=True)
            (run_output_dir / f"{safe_dir_name(provider_name)}.json").write_text(
                json.dumps(record, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            results.append(record)
            status = "ok" if record.get("ok") else "fail"
            print(
                f"{run_id}\t{provider_name}\t{status}\t{record.get('elapsed_ms', 0)}ms\t{record.get('model_label') or record.get('error', '')}",
                flush=True,
            )
    (output_dir / "summary.md").write_text(render_summary(results), encoding="utf-8")
    return output_dir, results


def main() -> int:
    args = parse_args()
    load_project_env(no_dotenv=bool(args.no_dotenv))
    apply_provider_env(args)
    try:
        output_dir, _results = run_ab(args)
    except (FileNotFoundError, ValueError, sqlite3.Error) as exc:
        print(f"provider A/B run failed: {exc}", file=sys.stderr)
        return 1
    print(f"REPORT\t{output_dir / 'summary.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
