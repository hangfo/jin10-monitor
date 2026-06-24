#!/usr/bin/env python3
"""Run a guarded Provider A/B evaluation for exported analysis packets.

The default mode is a dry run. Real provider API calls require both
``--execute`` and ``--yes`` so a copied command cannot accidentally spend
tokens or hit external services.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Sequence

BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_ANALYSIS_DB = BASE_DIR / "data" / "dashboard_analysis.sqlite3"
DEFAULT_EXPORT_ROOT = BASE_DIR / "exports" / "provider_ab"
DEFAULT_PROVIDERS = ("gemini", "compatible")
SUPPORTED_PROVIDERS = ("gemini", "compatible", "openai", "anthropic")
MAX_DEFAULT_EXECUTE_RUNS = 5

if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))


@dataclass(frozen=True)
class ProviderPlan:
    key: str
    label: str
    configured: bool
    available: bool
    note: str
    will_run: bool
    reason: str = ""


@dataclass
class EvalResult:
    run_id: str
    provider_key: str
    provider_name: str
    status: str = "pending"
    started_at: str = ""
    elapsed_seconds: float = 0.0
    model_label: str = ""
    finish_reason: str = ""
    input_tokens: int | None = None
    output_tokens: int | None = None
    json_parse_stable: bool = False
    parsed: dict[str, Any] | None = None
    raw_output: str = ""
    error: str = ""

    def to_public_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data.pop("raw_output", None)
        data["parsed_keys"] = sorted((self.parsed or {}).keys())
        data["elapsed_seconds"] = round(self.elapsed_seconds, 2)
        data.pop("parsed", None)
        return data


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run Provider A/B evaluation for exported dashboard analysis packets. "
            "Dry-run is the default; use --execute --yes for real API calls."
        )
    )
    parser.add_argument("run_id", nargs="?", help="single analysis_runs.id to evaluate")
    parser.add_argument("--run-ids", nargs="+", default=None, help="batch mode analysis_runs.id values")
    parser.add_argument(
        "--providers",
        nargs="+",
        default=list(DEFAULT_PROVIDERS),
        help="provider keys to evaluate; default: gemini compatible",
    )
    parser.add_argument("--db", type=Path, default=DEFAULT_ANALYSIS_DB, help="analysis sqlite path")
    parser.add_argument(
        "--output-root",
        type=Path,
        default=DEFAULT_EXPORT_ROOT,
        help="root output directory for packets and results",
    )
    parser.add_argument(
        "--packet-dir",
        type=Path,
        default=None,
        help="single-run packet directory; invalid with --run-ids",
    )
    parser.add_argument(
        "--refresh-packet",
        action="store_true",
        help="re-export prompt/evidence packet before evaluation",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="explicitly select the default preview mode; no provider API calls",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="perform real provider API calls; still requires --yes",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="confirm that real provider API calls and possible costs are intended",
    )
    parser.add_argument(
        "--max-runs",
        type=int,
        default=MAX_DEFAULT_EXECUTE_RUNS,
        help="maximum run count allowed in execute mode; default 5",
    )
    return parser.parse_args(argv)


def normalize_provider_keys(values: Sequence[str] | None) -> list[str]:
    keys = [str(value or "").strip().lower() for value in (values or DEFAULT_PROVIDERS)]
    normalized: list[str] = []
    for key in keys:
        if key in {"glm", "openai_compatible"}:
            key = "compatible"
        if key == "manual":
            continue
        if key and key not in normalized:
            normalized.append(key)
    return normalized


def validate_args(args: argparse.Namespace) -> tuple[bool, str]:
    if args.run_id and args.run_ids:
        return False, "run_id and --run-ids cannot be used together"
    if not args.run_id and not args.run_ids:
        return False, "provide run_id or --run-ids"
    if args.packet_dir and args.run_ids:
        return False, "--packet-dir is only valid for single-run mode"
    provider_keys = normalize_provider_keys(args.providers)
    unknown = [key for key in provider_keys if key not in SUPPORTED_PROVIDERS]
    if unknown:
        return False, f"unknown provider(s): {', '.join(unknown)}"
    if not provider_keys:
        return False, "no callable provider selected"
    run_ids = collect_run_ids(args)
    if args.execute and not args.yes:
        return False, "real provider calls require both --execute and --yes"
    if args.execute and getattr(args, "dry_run", False):
        return False, "--dry-run cannot be combined with --execute"
    if args.execute and len(run_ids) > max(1, int(args.max_runs or 0)):
        return (
            False,
            f"execute mode refuses {len(run_ids)} runs; raise --max-runs only after reviewing the batch",
        )
    return True, ""


def collect_run_ids(args: argparse.Namespace) -> list[str]:
    if args.run_ids:
        return [str(run_id).strip() for run_id in args.run_ids if str(run_id).strip()]
    return [str(args.run_id).strip()]


def packet_dir_for(run_id: str, *, output_root: Path, packet_dir: Path | None = None) -> Path:
    return packet_dir if packet_dir is not None else output_root / run_id


def ensure_packet(run_id: str, *, db_path: Path, output_dir: Path, refresh: bool = False) -> dict[str, Path]:
    required = {
        "prompt": output_dir / "prompt.md",
        "evidence_packet": output_dir / "evidence_packet.json",
        "metadata": output_dir / "metadata.json",
        "scorecard": output_dir / "ab_scorecard.md",
    }
    if refresh or not all(path.exists() for path in required.values()):
        from scripts.export_provider_ab_packet import export_run_packet

        export_run_packet(run_id, db_path=db_path, output_dir=output_dir)
    missing = [str(path) for path in required.values() if not path.exists()]
    if missing:
        raise FileNotFoundError("packet is incomplete: " + ", ".join(missing))
    return required


def load_packet(packet_dir: Path) -> tuple[str, dict[str, Any], str]:
    prompt = (packet_dir / "prompt.md").read_text(encoding="utf-8").strip()
    metadata = read_json_dict(packet_dir / "metadata.json")
    evidence = (packet_dir / "evidence_packet.json").read_text(encoding="utf-8").strip()
    return prompt, metadata, evidence


def read_json_dict(path: Path) -> dict[str, Any]:
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def provider_plan(provider_keys: Sequence[str]) -> list[ProviderPlan]:
    from dashboard.providers.base import provider_statuses

    status_by_key = {status.key: status for status in provider_statuses()}
    plans: list[ProviderPlan] = []
    for key in provider_keys:
        status = status_by_key.get(key)
        if status is None:
            plans.append(
                ProviderPlan(
                    key=key,
                    label=key,
                    configured=False,
                    available=False,
                    note="unknown provider",
                    will_run=False,
                    reason="unknown",
                )
            )
            continue
        available = bool(status.configured and status.available)
        plans.append(
            ProviderPlan(
                key=key,
                label=status.label,
                configured=status.configured,
                available=status.available,
                note=status.note,
                will_run=available,
                reason="" if available else "not configured or unavailable",
            )
        )
    return plans


def _extract_json_object(text: str) -> dict[str, Any] | None:
    stripped = str(text or "").strip()
    fence_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", stripped, re.DOTALL)
    candidates = [fence_match.group(1)] if fence_match else []
    candidates.append(stripped)
    brace_match = re.search(r"\{.*\}", stripped, re.DOTALL)
    if brace_match:
        candidates.append(brace_match.group(0))
    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed
    return None


def parse_provider_json(text: str) -> tuple[bool, dict[str, Any]]:
    from dashboard.manual_ai import parse_answer

    parsed = _extract_json_object(text)
    if parsed is None:
        return False, {}
    validated = parse_answer(json.dumps(parsed, ensure_ascii=False))
    if validated.get("parse_error"):
        return False, {}
    return True, validated


def safe_filename(value: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(value or "").strip())
    return safe.strip("._") or "provider"


def format_tokens(input_tokens: int | None, output_tokens: int | None) -> str:
    if input_tokens is None and output_tokens is None:
        return "-"
    parts = []
    if input_tokens is not None:
        parts.append(f"in={input_tokens}")
    if output_tokens is not None:
        parts.append(f"out={output_tokens}")
    return " ".join(parts)


def run_provider(
    run_id: str,
    provider_key: str,
    provider: Any,
    *,
    manual_prompt: str,
) -> EvalResult:
    from dashboard.app import provider_system_prompt

    started_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    result = EvalResult(
        run_id=run_id,
        provider_key=provider_key,
        provider_name=str(getattr(provider, "name", provider_key) or provider_key),
        started_at=started_at,
    )
    start = time.monotonic()
    try:
        completion = provider.complete(provider_system_prompt(provider_key, result.provider_name), manual_prompt)
        result.elapsed_seconds = time.monotonic() - start
        result.raw_output = str(completion.text or "")
        result.model_label = str(completion.model_label or "")
        result.finish_reason = str(completion.finish_reason or "")
        result.input_tokens = completion.input_tokens
        result.output_tokens = completion.output_tokens
        result.json_parse_stable, result.parsed = parse_provider_json(result.raw_output)
        result.status = "done"
    except Exception as exc:  # noqa: BLE001 - CLI records provider failures and continues.
        result.elapsed_seconds = time.monotonic() - start
        result.status = "failed"
        result.error = f"{type(exc).__name__}: {exc}"
    return result


def write_result_files(packet_dir: Path, result: EvalResult) -> dict[str, Path]:
    prefix = safe_filename(result.provider_key)
    raw_path = packet_dir / f"{prefix}_raw.txt"
    parsed_path = packet_dir / f"{prefix}_parsed.json"
    meta_path = packet_dir / f"{prefix}_result.json"

    raw_path.write_text(result.raw_output or result.error or "", encoding="utf-8")
    if result.json_parse_stable and result.parsed is not None:
        parsed_path.write_text(json.dumps(result.parsed, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    elif parsed_path.exists():
        parsed_path.unlink()
    meta_path.write_text(json.dumps(result.to_public_dict(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    files = {"raw": raw_path, "metadata": meta_path}
    if parsed_path.exists():
        files["parsed"] = parsed_path
    return files


def append_scorecard(scorecard_path: Path, results: Sequence[EvalResult]) -> None:
    lines = [
        "",
        "---",
        "",
        f"## 自动 Provider A/B 结果（{datetime.now().strftime('%Y-%m-%d %H:%M')}）",
        "",
        "| Provider | 状态 | 耗时 | Token | finish_reason | JSON 稳定 | 错误 | 输出 |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for result in results:
        output_file = f"{safe_filename(result.provider_key)}_raw.txt"
        status = "done" if result.status == "done" else "failed"
        json_ok = "yes" if result.json_parse_stable else "no"
        error = (result.error or "-").replace("|", "/")[:120]
        lines.append(
            f"| {result.provider_key} / {result.provider_name} "
            f"| {status} "
            f"| {result.elapsed_seconds:.1f}s "
            f"| {format_tokens(result.input_tokens, result.output_tokens)} "
            f"| {result.finish_reason or '-'} "
            f"| {json_ok} "
            f"| {error} "
            f"| `{output_file}` |"
        )
    lines.extend(
        [
            "",
            "> 自动区块只记录客观运行结果；judgement、关键催化覆盖、缺失证据是否合理仍需人工复核。",
            "",
        ]
    )
    with scorecard_path.open("a", encoding="utf-8") as fh:
        fh.write("\n".join(lines))


def write_eval_results(packet_dir: Path, run_id: str, results: Sequence[EvalResult]) -> Path:
    path = packet_dir / "eval_results.json"
    path.write_text(
        json.dumps(
            {
                "run_id": run_id,
                "evaluated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "results": [result.to_public_dict() for result in results],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return path


def write_eval_plan(packet_dir: Path, run_id: str, plans: Sequence[ProviderPlan], *, prompt_chars: int) -> Path:
    path = packet_dir / "eval_plan.json"
    path.write_text(
        json.dumps(
            {
                "run_id": run_id,
                "planned_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "mode": "dry_run",
                "prompt_chars": prompt_chars,
                "providers": [asdict(plan) for plan in plans],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return path


def evaluate_run(
    run_id: str,
    *,
    db_path: Path,
    packet_dir: Path,
    provider_keys: Sequence[str],
    execute: bool,
    refresh_packet: bool,
    provider_factory: Callable[[str], Any] | None = None,
    stdout: Any = None,
) -> list[EvalResult]:
    stdout = stdout or sys.stdout
    ensure_packet(run_id, db_path=db_path, output_dir=packet_dir, refresh=refresh_packet)
    manual_prompt, metadata, evidence_json = load_packet(packet_dir)
    plans = provider_plan(provider_keys)

    print(f"\nProvider A/B run_id={run_id}", file=stdout)
    print(f"packet_dir={packet_dir}", file=stdout)
    print(
        "asset={asset} window={start} ~ {end} evidence={selected}/{total} prompt_chars={chars}".format(
            asset=metadata.get("asset") or "-",
            start=metadata.get("window_start") or "-",
            end=metadata.get("window_end") or "-",
            selected=metadata.get("selected_count") or "-",
            total=metadata.get("evidence_count") or "-",
            chars=len(manual_prompt),
        ),
        file=stdout,
    )
    if evidence_json:
        print(f"evidence_packet_chars={len(evidence_json)}", file=stdout)
    for plan in plans:
        state = "will-run" if plan.will_run else f"skip:{plan.reason}"
        print(f"- {plan.key}: {state} ({plan.label})", file=stdout)

    if not execute:
        plan_path = write_eval_plan(packet_dir, run_id, plans, prompt_chars=len(manual_prompt))
        print(f"dry-run only; wrote plan: {plan_path}", file=stdout)
        print("real calls require: --execute --yes", file=stdout)
        return []

    runnable = [plan for plan in plans if plan.will_run]
    if not runnable:
        print("no configured provider selected; nothing executed", file=stdout)
        return []

    from dashboard.providers.base import get_provider

    factory = provider_factory or get_provider
    results: list[EvalResult] = []
    for plan in runnable:
        provider = factory(plan.key)
        if provider is None:
            results.append(
                EvalResult(
                    run_id=run_id,
                    provider_key=plan.key,
                    provider_name=plan.key,
                    status="failed",
                    error="provider factory returned None",
                )
            )
            continue
        print(f"calling {plan.key}...", file=stdout)
        result = run_provider(run_id, plan.key, provider, manual_prompt=manual_prompt)
        write_result_files(packet_dir, result)
        results.append(result)
        if result.status == "done":
            print(
                f"  done {result.model_label or result.provider_name} "
                f"{result.elapsed_seconds:.1f}s json={'yes' if result.json_parse_stable else 'no'} "
                f"tokens={format_tokens(result.input_tokens, result.output_tokens)}",
                file=stdout,
            )
        else:
            print(f"  failed {result.error}", file=stdout)

    if results:
        append_scorecard(packet_dir / "ab_scorecard.md", results)
        results_path = write_eval_results(packet_dir, run_id, results)
        print(f"wrote results: {results_path}", file=stdout)
    return results


def print_batch_summary(all_results: dict[str, list[EvalResult]], *, stdout: Any = None) -> None:
    stdout = stdout or sys.stdout
    if not all_results:
        return
    provider_keys = sorted({result.provider_key for results in all_results.values() for result in results})
    if not provider_keys:
        print("\nBatch dry-run completed; no provider calls executed.", file=stdout)
        return
    print("\nProvider A/B batch summary", file=stdout)
    header = "run_id".ljust(24) + " ".join(key[:18].ljust(20) for key in provider_keys)
    print(header, file=stdout)
    print("-" * len(header), file=stdout)
    for run_id, results in all_results.items():
        by_key = {result.provider_key: result for result in results}
        cells = []
        for key in provider_keys:
            result = by_key.get(key)
            if result is None:
                cells.append("-".ljust(20))
            elif result.status == "done":
                cells.append(f"ok {result.elapsed_seconds:.1f}s json={'Y' if result.json_parse_stable else 'N'}"[:20].ljust(20))
            else:
                cells.append(("fail " + result.status)[:20].ljust(20))
        print(run_id[:24].ljust(24) + " ".join(cells), file=stdout)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    ok, message = validate_args(args)
    if not ok:
        print(f"run_ab_eval: {message}", file=sys.stderr)
        return 2

    provider_keys = normalize_provider_keys(args.providers)
    run_ids = collect_run_ids(args)
    if not args.execute:
        print("DRY-RUN: no provider API calls will be made.")
    else:
        print("EXECUTE MODE: provider API calls may incur cost.")

    all_results: dict[str, list[EvalResult]] = {}
    had_failure = False
    for run_id in run_ids:
        packet_dir = packet_dir_for(run_id, output_root=args.output_root, packet_dir=args.packet_dir)
        try:
            results = evaluate_run(
                run_id,
                db_path=args.db,
                packet_dir=packet_dir,
                provider_keys=provider_keys,
                execute=args.execute,
                refresh_packet=args.refresh_packet,
            )
        except Exception as exc:  # noqa: BLE001 - CLI reports per-run failures.
            had_failure = True
            print(f"run_ab_eval: {run_id} failed: {type(exc).__name__}: {exc}", file=sys.stderr)
            continue
        all_results[run_id] = results
        if any(result.status != "done" for result in results):
            had_failure = True
    print_batch_summary(all_results)
    return 1 if had_failure else 0


if __name__ == "__main__":
    raise SystemExit(main())
