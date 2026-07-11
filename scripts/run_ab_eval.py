#!/usr/bin/env python3
"""Run a guarded Provider A/B evaluation for exported analysis packets.

The default mode is a dry run. Real provider API calls require both
``--execute`` and ``--yes`` so a copied command cannot accidentally spend
tokens or hit external services.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import json
import re
import subprocess
import sys
import time
from contextlib import contextmanager
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


def load_local_dotenv(env_path: Path | None = None) -> bool:
    """Load repo .env for CLI parity with run_dashboard.py without overwriting shell env."""
    path = env_path or BASE_DIR / ".env"
    if not path.exists():
        return False
    try:
        from dotenv import load_dotenv
    except ImportError:
        return False
    return bool(load_dotenv(path, override=False))


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
        default=None,
        metavar="KEY",
        help="provider keys to evaluate; default when omitted: gemini compatible",
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
    parser.add_argument(
        "--timeout",
        type=float,
        default=None,
        metavar="SECONDS",
        help="per-provider call timeout in seconds; overrides PROVIDER_TIMEOUT_SECONDS for this CLI run",
    )
    parser.add_argument(
        "--skip-existing",
        action="store_true",
        help="skip providers with an existing <provider>_result.json status=done result",
    )
    parser.add_argument(
        "--rebuild-comparisons",
        action="store_true",
        help="offline mode: rebuild comparison.md from existing provider result files; no API calls",
    )
    parser.add_argument(
        "--summary-report",
        nargs="?",
        const="",
        default=None,
        metavar="PATH",
        help=(
            "offline mode: write a batch Markdown summary from existing provider results; "
            "default path is <output-root>/summary.md"
        ),
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
    offline_mode = bool(args.rebuild_comparisons or args.summary_report is not None)
    if not args.run_id and not args.run_ids and not offline_mode:
        return False, "provide run_id or --run-ids"
    if args.packet_dir and args.run_ids:
        return False, "--packet-dir is only valid for single-run mode"
    if args.packet_dir and not (args.run_id or offline_mode):
        return False, "--packet-dir requires run_id unless using offline report mode"
    provider_values = list(args.providers or DEFAULT_PROVIDERS)
    if any(not str(value or "").strip() for value in provider_values):
        return False, "--providers contains an empty value; use gemini, compatible, openai, or anthropic"
    provider_keys = normalize_provider_keys(provider_values)
    unknown = [key for key in provider_keys if key not in SUPPORTED_PROVIDERS]
    if unknown:
        return False, f"unknown provider(s): {', '.join(unknown)}"
    if not provider_keys:
        return False, (
            "no callable provider selected; use gemini, compatible, openai, or anthropic "
            "(manual is not callable by this CLI)"
        )
    run_ids = collect_run_ids(args)
    if offline_mode and args.execute:
        return False, "offline report modes cannot be combined with --execute"
    if args.execute and not args.yes:
        return False, "real provider calls require both --execute and --yes"
    if args.execute and getattr(args, "dry_run", False):
        return False, "--dry-run cannot be combined with --execute"
    if args.execute and len(run_ids) > max(1, int(args.max_runs or 0)):
        return (
            False,
            f"execute mode refuses {len(run_ids)} runs; raise --max-runs only after reviewing the batch",
        )
    timeout = getattr(args, "timeout", None)
    if timeout is not None and (timeout < 1 or timeout > 600):
        return False, f"--timeout must be between 1 and 600 seconds, got {timeout:g}"
    return True, ""


def collect_run_ids(args: argparse.Namespace) -> list[str]:
    if args.run_ids:
        return [str(run_id).strip() for run_id in args.run_ids if str(run_id).strip()]
    if not args.run_id:
        return []
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


def sha256_text(value: str) -> str:
    return hashlib.sha256(str(value).encode("utf-8")).hexdigest()


def current_git_state() -> dict[str, Any]:
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=BASE_DIR,
            check=False,
            capture_output=True,
            text=True,
            timeout=2,
        )
        status = subprocess.run(
            ["git", "status", "--porcelain", "--untracked-files=no"],
            cwd=BASE_DIR,
            check=False,
            capture_output=True,
            text=True,
            timeout=2,
        )
    except (OSError, subprocess.SubprocessError):
        return {"commit": "", "dirty": None}
    return {
        "commit": commit.stdout.strip() if commit.returncode == 0 else "",
        "dirty": bool(status.stdout.strip()) if status.returncode == 0 else None,
    }


def public_provider_config(provider_key: str) -> dict[str, str]:
    env_names = {
        "gemini": ("GEMINI_MODEL", "GEMINI_MAX_TOKENS", "GEMINI_THINKING_BUDGET"),
        "compatible": ("COMPAT_LLM_MODEL", "COMPAT_LLM_MAX_TOKENS", "COMPAT_LLM_THINKING_TYPE"),
        "openai": ("OPENAI_MODEL", "OPENAI_MAX_TOKENS"),
        "anthropic": ("ANTHROPIC_MODEL", "ANTHROPIC_MAX_TOKENS"),
    }
    return {
        name: os.getenv(name, "").strip()
        for name in env_names.get(str(provider_key or "").strip().lower(), ())
        if os.getenv(name, "").strip()
    }


def write_execution_context(
    packet_dir: Path,
    *,
    run_id: str,
    provider_key: str,
    provider_name: str,
    manual_prompt: str,
    evidence_json: str,
    system_prompt: str,
    git_state: dict[str, Any] | None = None,
) -> dict[str, Any]:
    prefix = safe_filename(provider_key)
    user_prompt_sha256 = sha256_text(manual_prompt)
    evidence_packet_sha256 = sha256_text(evidence_json)
    system_prompt_sha256 = sha256_text(system_prompt)
    user_prompt_path = packet_dir / f"prompt_{user_prompt_sha256[:12]}.md"
    evidence_packet_path = packet_dir / f"evidence_packet_{evidence_packet_sha256[:12]}.json"
    system_prompt_path = packet_dir / f"{prefix}_system_prompt_{system_prompt_sha256[:12]}.txt"
    if not user_prompt_path.exists():
        user_prompt_path.write_text(manual_prompt, encoding="utf-8")
    if not evidence_packet_path.exists():
        evidence_packet_path.write_text(evidence_json + "\n", encoding="utf-8")
    if not system_prompt_path.exists():
        system_prompt_path.write_text(system_prompt, encoding="utf-8")

    path = packet_dir / "execution_context.json"
    context = read_json_dict(path)
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    resolved_git_state = git_state or current_git_state()
    effective_timeout = os.getenv("PROVIDER_TIMEOUT_SECONDS", "").strip()
    context.setdefault("run_id", run_id)
    context.setdefault("created_at", now)
    context["updated_at"] = now
    context["git"] = resolved_git_state
    context["user_prompt_file"] = "prompt.md"
    context["user_prompt_snapshot_file"] = user_prompt_path.name
    context["user_prompt_sha256"] = user_prompt_sha256
    context["evidence_packet_file"] = "evidence_packet.json"
    context["evidence_packet_snapshot_file"] = evidence_packet_path.name
    context["evidence_packet_sha256"] = evidence_packet_sha256
    providers = context.get("providers") if isinstance(context.get("providers"), dict) else {}
    provider_config = public_provider_config(provider_key)
    if effective_timeout:
        provider_config["PROVIDER_TIMEOUT_SECONDS"] = effective_timeout
    providers[provider_key] = {
        "provider_name": provider_name,
        "system_prompt_file": system_prompt_path.name,
        "system_prompt_sha256": system_prompt_sha256,
        "config": provider_config,
    }
    context["providers"] = providers
    path.write_text(json.dumps(context, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {
        "source_git_commit": resolved_git_state["commit"],
        "source_git_dirty": resolved_git_state["dirty"],
        "effective_timeout_seconds": effective_timeout or None,
        "user_prompt_snapshot_file": user_prompt_path.name,
        "user_prompt_sha256": user_prompt_sha256,
        "evidence_packet_snapshot_file": evidence_packet_path.name,
        "evidence_packet_sha256": evidence_packet_sha256,
        "system_prompt_snapshot_file": system_prompt_path.name,
        "system_prompt_sha256": system_prompt_sha256,
    }


def append_attempt_history(
    packet_dir: Path,
    result: EvalResult,
    *,
    timeout_seconds: float | None,
    hashes: dict[str, Any],
) -> Path:
    path = packet_dir / "attempt_history.jsonl"
    entry = result.to_public_dict()
    entry.update(
        {
            "recorded_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "timeout_override_seconds": timeout_seconds,
            **hashes,
        }
    )
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n")
    return path


def read_json_dict(path: Path) -> dict[str, Any]:
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def discover_packet_dirs(*, output_root: Path, run_ids: Sequence[str], packet_dir: Path | None = None) -> list[tuple[str, Path]]:
    if packet_dir is not None:
        run_id = run_ids[0] if run_ids else packet_dir.name
        return [(run_id, packet_dir)]
    if run_ids:
        return [(run_id, packet_dir_for(run_id, output_root=output_root)) for run_id in run_ids]
    if not output_root.exists():
        return []
    packet_dirs: list[tuple[str, Path]] = []
    for child in sorted(output_root.iterdir()):
        if not child.is_dir():
            continue
        if any(child.glob("*_result.json")):
            packet_dirs.append((child.name, child))
    return packet_dirs


def discover_result_provider_keys(packet_dir: Path) -> list[str]:
    keys: list[str] = []
    for result_path in sorted(packet_dir.glob("*_result.json")):
        key = result_path.name[: -len("_result.json")]
        result = read_json_dict(result_path)
        key = str(result.get("provider_key") or key).strip()
        if key and key not in keys:
            keys.append(key)
    ordered = [key for key in DEFAULT_PROVIDERS if key in keys]
    ordered.extend(key for key in keys if key not in ordered)
    return ordered


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


@contextmanager
def temporary_provider_timeout(timeout_seconds: float | None):
    if timeout_seconds is None:
        yield
        return
    original = os.environ.get("PROVIDER_TIMEOUT_SECONDS")
    os.environ["PROVIDER_TIMEOUT_SECONDS"] = str(timeout_seconds)
    try:
        yield
    finally:
        if original is None:
            os.environ.pop("PROVIDER_TIMEOUT_SECONDS", None)
        else:
            os.environ["PROVIDER_TIMEOUT_SECONDS"] = original


def run_provider(
    run_id: str,
    provider_key: str,
    provider: Any,
    *,
    manual_prompt: str,
    system_prompt: str | None = None,
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
        resolved_system_prompt = system_prompt or provider_system_prompt(provider_key, result.provider_name)
        completion = provider.complete(resolved_system_prompt, manual_prompt)
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


def write_comparison(packet_dir: Path, run_id: str, provider_keys: Sequence[str]) -> Path | None:
    rows: list[dict[str, Any]] = []
    for provider_key in provider_keys:
        prefix = safe_filename(provider_key)
        result = read_json_dict(packet_dir / f"{prefix}_result.json")
        if not result:
            continue
        parsed = read_json_dict(packet_dir / f"{prefix}_parsed.json")
        catalysts = parsed.get("catalysts") if isinstance(parsed.get("catalysts"), list) else []
        missing = parsed.get("missing_evidence") if isinstance(parsed.get("missing_evidence"), list) else []
        rows.append(
            {
                "provider": provider_key,
                "status": result.get("status") or "-",
                "model": result.get("model_label") or result.get("provider_name") or "-",
                "judgement": parsed.get("judgement") or "-",
                "confidence": parsed.get("overall_confidence", "-") if parsed else "-",
                "catalysts": len(catalysts),
                "missing": len(missing),
                "json": "yes" if result.get("json_parse_stable") else "no",
                "elapsed": result.get("elapsed_seconds", "-"),
                "tokens": format_tokens(result.get("input_tokens"), result.get("output_tokens")),
                "finish": result.get("finish_reason") or "-",
                "error": (result.get("error") or "-").replace("|", "/")[:120],
            }
        )
    if len(rows) < 2:
        return None

    lines = [
        f"# Provider A/B Comparison - {run_id}",
        "",
        f"更新时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        "| 字段 | " + " | ".join(row["provider"] for row in rows) + " |",
        "| --- | " + " | ".join("---" for _ in rows) + " |",
    ]
    field_labels = [
        ("status", "状态"),
        ("model", "模型"),
        ("judgement", "judgement"),
        ("confidence", "overall_confidence"),
        ("catalysts", "catalysts 数量"),
        ("missing", "missing_evidence 数量"),
        ("json", "JSON 稳定"),
        ("elapsed", "耗时秒"),
        ("tokens", "Token"),
        ("finish", "finish_reason"),
        ("error", "错误"),
    ]
    for key, label in field_labels:
        lines.append("| " + label + " | " + " | ".join(str(row[key]) for row in rows) + " |")
    lines.extend(
        [
            "",
            "> 自动对比只汇总客观字段和模型自报结构；关键催化覆盖、重复 news_id、缺失证据是否合理仍需人工复核。",
            "",
        ]
    )
    path = packet_dir / "comparison.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def rebuild_existing_comparisons(packet_dirs: Sequence[tuple[str, Path]], *, stdout: Any = None) -> list[Path]:
    stdout = stdout or sys.stdout
    written: list[Path] = []
    for run_id, packet_dir in packet_dirs:
        provider_keys = discover_result_provider_keys(packet_dir)
        if len(provider_keys) < 2:
            print(f"skip {run_id}: found {len(provider_keys)} provider result(s)", file=stdout, flush=True)
            continue
        path = write_comparison(packet_dir, run_id, provider_keys)
        if path is None:
            print(f"skip {run_id}: comparison requires at least two providers", file=stdout, flush=True)
            continue
        written.append(path)
        print(f"wrote comparison: {path}", file=stdout, flush=True)
    return written


def _summary_rows(packet_dirs: Sequence[tuple[str, Path]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for run_id, packet_dir in packet_dirs:
        provider_keys = discover_result_provider_keys(packet_dir)
        metadata = read_json_dict(packet_dir / "metadata.json")
        for provider_key in provider_keys:
            prefix = safe_filename(provider_key)
            result = read_json_dict(packet_dir / f"{prefix}_result.json")
            if not result:
                continue
            parsed = read_json_dict(packet_dir / f"{prefix}_parsed.json")
            catalysts = parsed.get("catalysts") if isinstance(parsed.get("catalysts"), list) else []
            missing = parsed.get("missing_evidence") if isinstance(parsed.get("missing_evidence"), list) else []
            news_ids = [str(item.get("news_id") or "") for item in catalysts if isinstance(item, dict)]
            duplicate_ids = sorted({news_id for news_id in news_ids if news_id and news_ids.count(news_id) > 1})
            rows.append(
                {
                    "run_id": run_id,
                    "asset": metadata.get("asset") or "-",
                    "question": metadata.get("question") or "-",
                    "provider": provider_key,
                    "status": result.get("status") or "-",
                    "model": result.get("model_label") or result.get("provider_name") or "-",
                    "judgement": parsed.get("judgement") or "-",
                    "confidence": parsed.get("overall_confidence", "-") if parsed else "-",
                    "catalysts": len(catalysts),
                    "missing": len(missing),
                    "duplicates": ", ".join(duplicate_ids) if duplicate_ids else "-",
                    "json": "yes" if result.get("json_parse_stable") else "no",
                    "elapsed": result.get("elapsed_seconds", "-"),
                    "tokens": format_tokens(result.get("input_tokens"), result.get("output_tokens")),
                    "error": (result.get("error") or "-").replace("|", "/")[:120],
                    "comparison": "yes" if (packet_dir / "comparison.md").exists() else "no",
                }
            )
    return rows


def write_summary_report(output_path: Path, packet_dirs: Sequence[tuple[str, Path]]) -> Path:
    rows = _summary_rows(packet_dirs)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Provider A/B Batch Summary",
        "",
        f"更新时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        f"- 扫描 run 数：{len(packet_dirs)}",
        f"- Provider 结果数：{len(rows)}",
        "- 边界：只汇总已有导出文件，不调用 Provider API，不写 analysis_runs，不请求金十 REST，不触发 Telegram。",
        "",
    ]
    if not rows:
        lines.extend(["未找到可汇总的 Provider 结果。", ""])
        output_path.write_text("\n".join(lines), encoding="utf-8")
        return output_path

    lines.extend(
        [
            "| run_id | asset | provider | model | status | judgement | confidence | catalysts | missing | duplicate_news_id | JSON | elapsed | tokens | comparison | error |",
            "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
        ]
    )
    for row in rows:
        lines.append(
            "| {run_id} | {asset} | {provider} | {model} | {status} | {judgement} | {confidence} | {catalysts} | {missing} | {duplicates} | {json} | {elapsed} | {tokens} | {comparison} | {error} |".format(
                **{key: str(value).replace("|", "/") for key, value in row.items()}
            )
        )
    lines.extend(
        [
            "",
            "## Run 摘要",
            "",
            "| run_id | question | providers | comparison.md |",
            "| --- | --- | --- | --- |",
        ]
    )
    by_run: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        by_run.setdefault(str(row["run_id"]), []).append(row)
    for run_id, run_rows in by_run.items():
        providers = ", ".join(str(row["provider"]) for row in run_rows)
        question = str(run_rows[0]["question"]).replace("|", "/")
        comparison = "yes" if any(row["comparison"] == "yes" for row in run_rows) else "no"
        lines.append(f"| {run_id} | {question} | {providers} | {comparison} |")
    lines.extend(
        [
            "",
            "> 自动汇总只记录客观字段和模型自报结构；关键催化覆盖、缺失证据是否合理、最终 pass/watch/fail 仍需人工复核。",
            "",
        ]
    )
    output_path.write_text("\n".join(lines), encoding="utf-8")
    return output_path


def summary_output_path(args: argparse.Namespace) -> Path:
    value = args.summary_report
    if value in (None, ""):
        return args.output_root / "summary.md"
    return Path(value)


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
    timeout_seconds: float | None = None,
    skip_existing: bool = False,
    provider_factory: Callable[[str], Any] | None = None,
    stdout: Any = None,
) -> list[EvalResult]:
    stdout = stdout or sys.stdout
    ensure_packet(run_id, db_path=db_path, output_dir=packet_dir, refresh=refresh_packet)
    manual_prompt, metadata, evidence_json = load_packet(packet_dir)
    # prompt.md already embeds the fixed evidence packet. evidence_json is only
    # used for a size diagnostic, keeping CLI calls aligned with /analyze Provider calls.
    plans = provider_plan(provider_keys)

    print(f"\nProvider A/B run_id={run_id}", file=stdout, flush=True)
    print(f"packet_dir={packet_dir}", file=stdout, flush=True)
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
        flush=True,
    )
    if evidence_json:
        print(f"evidence_packet_chars={len(evidence_json)}", file=stdout, flush=True)
    if timeout_seconds is not None:
        print(f"timeout_seconds={timeout_seconds:g}", file=stdout, flush=True)
    for plan in plans:
        state = "will-run" if plan.will_run else f"skip:{plan.reason}"
        print(f"- {plan.key}: {state} ({plan.label})", file=stdout, flush=True)

    if not execute:
        plan_path = write_eval_plan(packet_dir, run_id, plans, prompt_chars=len(manual_prompt))
        print(f"dry-run only; wrote plan: {plan_path}", file=stdout, flush=True)
        print("real calls require: --execute --yes", file=stdout, flush=True)
        return []

    runnable = [plan for plan in plans if plan.will_run]
    if not runnable:
        print("no configured provider selected; nothing executed", file=stdout, flush=True)
        return []

    from dashboard.providers.base import get_provider
    from dashboard.app import provider_system_prompt

    factory = provider_factory or get_provider
    results: list[EvalResult] = []
    source_git_state = current_git_state()
    for plan in runnable:
        if skip_existing:
            result_path = packet_dir / f"{safe_filename(plan.key)}_result.json"
            existing = read_json_dict(result_path)
            if existing.get("status") == "done":
                print(f"skip {plan.key}: existing done result found", file=stdout, flush=True)
                continue
        with temporary_provider_timeout(timeout_seconds):
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
            system_prompt = provider_system_prompt(plan.key, str(getattr(provider, "name", plan.key) or plan.key))
            hashes = write_execution_context(
                packet_dir,
                run_id=run_id,
                provider_key=plan.key,
                provider_name=str(getattr(provider, "name", plan.key) or plan.key),
                manual_prompt=manual_prompt,
                evidence_json=evidence_json,
                system_prompt=system_prompt,
                git_state=source_git_state,
            )
            print(f"calling {plan.key}...", file=stdout, flush=True)
            result = run_provider(
                run_id,
                plan.key,
                provider,
                manual_prompt=manual_prompt,
                system_prompt=system_prompt,
            )
        write_result_files(packet_dir, result)
        append_attempt_history(
            packet_dir,
            result,
            timeout_seconds=timeout_seconds,
            hashes=hashes,
        )
        results.append(result)
        if result.status == "done":
            print(
                f"  done {result.model_label or result.provider_name} "
                f"{result.elapsed_seconds:.1f}s json={'yes' if result.json_parse_stable else 'no'} "
                f"tokens={format_tokens(result.input_tokens, result.output_tokens)}",
                file=stdout,
                flush=True,
            )
        else:
            print(f"  failed {result.error}", file=stdout, flush=True)

    if results:
        append_scorecard(packet_dir / "ab_scorecard.md", results)
        results_path = write_eval_results(packet_dir, run_id, results)
        print(f"wrote results: {results_path}", file=stdout, flush=True)
    comparison_path = write_comparison(packet_dir, run_id, [plan.key for plan in runnable])
    if comparison_path is not None:
        print(f"wrote comparison: {comparison_path}", file=stdout, flush=True)
    return results


def print_batch_summary(all_results: dict[str, list[EvalResult]], *, stdout: Any = None) -> None:
    stdout = stdout or sys.stdout
    if not all_results:
        return
    provider_keys = sorted({result.provider_key for results in all_results.values() for result in results})
    if not provider_keys:
        print("\nBatch completed; no provider calls executed.", file=stdout, flush=True)
        return
    print("\nProvider A/B batch summary", file=stdout, flush=True)
    header = "run_id".ljust(24) + " ".join(key[:18].ljust(20) for key in provider_keys)
    print(header, file=stdout, flush=True)
    print("-" * len(header), file=stdout, flush=True)
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
        print(run_id[:24].ljust(24) + " ".join(cells), file=stdout, flush=True)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    load_local_dotenv()
    ok, message = validate_args(args)
    if not ok:
        print(f"run_ab_eval: {message}", file=sys.stderr)
        return 2

    run_ids = collect_run_ids(args)
    if args.rebuild_comparisons or args.summary_report is not None:
        packet_dirs = discover_packet_dirs(output_root=args.output_root, run_ids=run_ids, packet_dir=args.packet_dir)
        if not packet_dirs:
            print(f"run_ab_eval: no existing provider result directories found under {args.output_root}", file=sys.stderr)
            return 1
        if args.rebuild_comparisons:
            written = rebuild_existing_comparisons(packet_dirs)
            print(f"rebuilt comparisons: {len(written)}", flush=True)
        if args.summary_report is not None:
            path = write_summary_report(summary_output_path(args), packet_dirs)
            print(f"wrote summary report: {path}", flush=True)
        return 0

    provider_keys = normalize_provider_keys(args.providers)
    if not args.execute:
        print("DRY-RUN: no provider API calls will be made.", flush=True)
    else:
        print("EXECUTE MODE: provider API calls may incur cost.", flush=True)

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
                timeout_seconds=args.timeout,
                skip_existing=args.skip_existing,
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
