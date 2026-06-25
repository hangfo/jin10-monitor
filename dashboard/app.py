"""FastAPI application for the standalone dashboard."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import time
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import parse_qs, urlencode

from fastapi import BackgroundTasks, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .analysis_db import (
    BASE_DIR,
    create_run,
    delete_run,
    get_run,
    get_runs_for_compare,
    get_screenshot,
    init_analysis_db,
    list_runs,
    mark_provider_running,
    estimate_provider_completion_seconds,
    query_provider_call_stats,
    reset_stale_running_runs,
    save_answer,
    save_manual_prompt,
    save_provider_error,
    save_screenshot,
)
from .db import (
    DEFAULT_HOURS,
    HOURS_OPTIONS,
    history_health,
    parse_history_datetime,
    query_feed_density,
    query_item,
    query_item_context,
    query_keyword_heatmap,
    query_latest_published_at,
    query_feed_page,
    query_nav_summary,
    query_recent_items,
    query_system_health,
    query_tg_deliveries,
    query_tg_status_for_item,
    query_tg_summary,
    query_ws_initial_review,
    query_aggregation_report,
)
from .evidence import build_evidence_for_preview, known_assets
from .market.base import MarketAdapterError, configured_market_adapter_name, get_market_adapter
from .manual_ai import PROMPT_VERSION, generate_prompt, judgement_label, parse_answer, render_answer_with_links
from .providers.base import ProviderError, get_provider, provider_statuses

TEMPLATE_DIR = Path(__file__).resolve().parent / "templates"
STATIC_DIR = Path(__file__).resolve().parent / "static"
PRIORITY_OPTIONS = [
    ("", "全部"),
    ("T3_IMPORTANT", "T3 重要"),
    ("T2_HIGH", "T2 高优"),
    ("T1_NORMAL", "T1 普通"),
    ("T0_NONE", "T0 仅入库"),
]
ALLOWED_PRIORITIES = {value for value, _label in PRIORITY_OPTIONS}
STATUS_OPTIONS = [
    ("all", "全部"),
    ("sent", "sent"),
    ("failed", "failed"),
    ("unknown_timeout", "unknown_timeout"),
    ("skipped", "skipped"),
]
ALLOWED_STATUSES = {value for value, _label in STATUS_OPTIONS}
ANALYSIS_STATUS_OPTIONS = [
    ("all", "全部"),
    ("running", "调用中"),
    ("draft", "草稿"),
    ("done", "已完成"),
    ("recent_failed", "最近失败"),
]
ALLOWED_ANALYSIS_STATUSES = {value for value, _label in ANALYSIS_STATUS_OPTIONS}

templates = Jinja2Templates(directory=str(TEMPLATE_DIR))
log = logging.getLogger(__name__)
MAX_SCREENSHOT_BYTES = 8 * 1024 * 1024
ALLOWED_SCREENSHOT_MIME_TYPES = {"image/png", "image/jpeg", "image/webp", "image/gif"}
CONFIDENCE_HELP = (
    "置信度是模型基于证据充分度、时间吻合度和因果链条清晰度给出的主观估计，不是交易信号。"
    "≥75% 较可信；50-75% 仅供参考；<50% 证据不足。"
)


def compact_text(*parts: object, limit: int = 120) -> str:
    text = " ".join(str(part or "").strip() for part in parts if str(part or "").strip())
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1] + "..."


def normalize_news_text(value: object) -> str:
    return " ".join(str(value or "").split())


def priority_class(level: object) -> str:
    return {
        "T3_IMPORTANT": "important",
        "T2_HIGH": "high",
        "T1_NORMAL": "normal",
        "T0_NONE": "none",
    }.get(str(level or ""), "none")


def priority_css(level: object) -> str:
    return {
        "T3_IMPORTANT": "t3",
        "T2_HIGH": "t2",
        "T1_NORMAL": "t1",
        "T0_NONE": "t0",
    }.get(str(level or ""), "t0")


def callable_provider_statuses() -> list[dict[str, object]]:
    return [
        {"key": status.key, "label": status.label, "available": status.available, "note": status.note}
        for status in provider_statuses()
        if status.key != "manual"
    ]


def market_context_default_enabled() -> bool:
    """Default to no external market request unless explicitly enabled."""
    flag = str(os.getenv("MARKET_CONTEXT_DEFAULT_ENABLED", "") or "").strip().lower()
    if flag not in {"1", "true", "yes", "on"}:
        return False
    adapter_name = configured_market_adapter_name()
    return bool(adapter_name and get_market_adapter(adapter_name))


def provider_error_redirect(run_id: str, message: str, *, provider_name: str = "") -> RedirectResponse:
    params = {"provider_error": str(message or "provider error")[:180]}
    if provider_name:
        params["provider"] = provider_name
    return RedirectResponse(f"/analyze/{run_id}?{urlencode(params)}", status_code=303)


def save_and_redirect_provider_error(
    run_id: str,
    message: str,
    *,
    provider_name: str = "",
    provider_elapsed_ms: int = 0,
) -> RedirectResponse:
    save_provider_error(run_id, message, provider_elapsed_ms=provider_elapsed_ms)
    return provider_error_redirect(run_id, message, provider_name=provider_name)


def provider_raw_preview(raw_text: str, *, limit: int = 700) -> str:
    text = " ".join(str(raw_text or "").strip().split())
    if len(text) <= limit:
        return text
    return f"{text[:limit]}..."


def ensure_run_manual_prompt(run: dict[str, object]) -> str:
    prompt = str(run.get("manual_prompt") or "").strip()
    if prompt:
        return prompt
    rebuilt = generate_prompt(
        question=str(run.get("question") or ""),
        asset=str(run.get("asset") or ""),
        window_start=str(run.get("window_start") or ""),
        window_end=str(run.get("window_end") or ""),
        evidence=[item for item in (run.get("evidence_packet") or []) if isinstance(item, dict)],
        user_context=str(run.get("user_context") or ""),
    ).strip()
    if rebuilt:
        save_manual_prompt(str(run.get("id") or ""), rebuilt)
    return rebuilt


def provider_system_prompt(provider_name: str, provider_label: str = "") -> str:
    base_prompt = (
        "请严格执行用户 Prompt 中的系统指令，只输出一个合法 JSON object。"
        "不要添加前言、解释、Markdown 代码块或思考过程；"
        "JSON 内所有字符串值都必须使用双引号包裹，尤其是 summary、headline、impact_path、missing_evidence 和 caveat。"
        "如果新闻证据主方向与价格涨跌方向明显相反，且缺少成交量、订单流、清算、资金费率或 BTC/ETH 联动等直接市场证据，"
        "judgement 必须优先为 unclear 或低置信 macro_sentiment，并在 missing_evidence 写明缺口，不得强行解释为确定性上涨/下跌原因。"
    )
    provider_key = str(provider_name or "").strip().lower()
    if provider_key in {"compatible", "glm"} and is_glm_provider(provider_label):
        return (
            base_prompt
            + "\n\nGLM 专用补充约束："
            + "不要输出 reasoning_content，不要输出 <think> 或任何思考过程，只输出最终 JSON；"
            + "除 judgement 字段的枚举值外，summary、headline、impact_path、missing_evidence 和 caveat 必须使用中文；"
            + "caveat 必须是 JSON 字符串，不能写裸中文文本；"
            + "impact_path 末尾必须使用真实消息 ID，例如 [#20260624195807735800]，不得输出 [#news_id] 字面占位符；"
            + "如果唯一高相关证据不是标的直接新闻，或证据方向与价格方向不一致，judgement 必须优先为 unclear；"
            + "如果缺少成交量、订单流、清算、资金费率、BTC 联动或同步市场数据，不得写“资金流入”“导致上涨/下跌”等确定性因果；"
            + "单条 indirect/mixed 证据不得给出 news_driven，overall_confidence 不得高于 0.5。"
        )
    return base_prompt


def is_glm_provider(model_label: object) -> bool:
    label = str(model_label or "").strip().lower()
    return "glm" in label or "zhipu" in label


def provider_review_warning(run: dict[str, object]) -> str:
    parsed = run.get("answer_parsed") if isinstance(run.get("answer_parsed"), dict) else {}
    if isinstance(parsed, dict) and parsed.get("local_review_applied"):
        return "本地复核已调整：单条低相关、非标的直接证据不足以支撑 news_driven 高置信判断。"
    model_label = str(run.get("model_label") or "").lower()
    if not is_glm_provider(model_label):
        return ""
    judgement = str(run.get("judgement") or "")
    confidence = float(run.get("overall_confidence") or 0)
    selected_count = int(run.get("selected_count") or 0)
    parsed = run.get("answer_parsed") if isinstance(run.get("answer_parsed"), dict) else {}
    catalysts = parsed.get("catalysts") if isinstance(parsed, dict) else []
    has_mixed = any(
        isinstance(item, dict) and str(item.get("direction") or "").lower() == "mixed"
        for item in (catalysts or [])
    )
    if judgement == "news_driven" and selected_count <= 1 and (confidence >= 0.65 or has_mixed):
        return "GLM 可能过度归因：单条或 mixed 证据不足以支撑 news_driven 高置信判断，建议用 Gemini 或 ChatGPT Plus 复核。"
    return ""


def apply_local_evidence_guard(parsed: dict[str, object], run: dict[str, object]) -> dict[str, object]:
    """Keep weak single-evidence provider outputs from becoming high-confidence conclusions."""
    if not isinstance(parsed, dict) or parsed.get("parse_error"):
        return parsed
    selected_rows = [
        row
        for row in (run.get("evidence_rows") or [])
        if isinstance(row, dict) and int(row.get("selected") or 0) == 1
    ]
    if len(selected_rows) != 1:
        return parsed
    evidence = selected_rows[0]
    relevance = float(evidence.get("relevance_score") or 0)
    asset = str(run.get("asset") or "").strip().upper()
    evidence_text = " ".join(
        str(evidence.get(key) or "")
        for key in ("title", "content", "matched_keywords", "news_source")
    ).upper()
    judgement = str(parsed.get("judgement") or "")
    confidence = float(parsed.get("overall_confidence") or 0)
    catalysts = parsed.get("catalysts") if isinstance(parsed.get("catalysts"), list) else []
    catalyst_confidence = max(
        [float(item.get("confidence") or 0) for item in catalysts if isinstance(item, dict)] or [0]
    )
    if relevance >= 0.5 or (asset and asset in evidence_text):
        return parsed
    if judgement != "news_driven" and confidence <= 0.4 and catalyst_confidence <= 0.4:
        return parsed

    guarded = dict(parsed)
    guarded["judgement"] = "unclear"
    guarded["overall_confidence"] = min(confidence or 0.4, 0.4)
    guarded["summary"] = f"无法确认：仅有单条低相关、非{asset or '标的'}直接证据，不能高置信归因。"
    guarded["local_review_applied"] = True
    caveat = str(guarded.get("caveat") or "").strip()
    review_caveat = (
        f"本地复核：当前只有 1 条相关度 {relevance:.2f} 的非{asset or '标的'}直接证据，"
        "缺少成交量、BTC 联动、资金费率或订单流验证，已将判断降为 unclear。"
    )
    guarded["caveat"] = f"{review_caveat} {caveat}".strip()
    missing = guarded.get("missing_evidence") if isinstance(guarded.get("missing_evidence"), list) else []
    additions = [
        f"{asset or '标的'}/USDT 1分钟成交量",
        "BTC/USDT 同步行情",
        "资金费率",
        "订单流或大额成交",
    ]
    guarded["missing_evidence"] = list(dict.fromkeys([str(item) for item in missing + additions if str(item)]))
    guarded_catalysts = []
    for item in catalysts:
        if not isinstance(item, dict):
            continue
        adjusted = dict(item)
        adjusted["confidence"] = min(float(adjusted.get("confidence") or 0), 0.4)
        if str(adjusted.get("direction") or "").lower() == "bullish":
            adjusted["direction"] = "mixed"
        guarded_catalysts.append(adjusted)
    guarded["catalysts"] = guarded_catalysts
    return guarded


def format_provider_error(message: str) -> str:
    text = str(message or "").strip()
    if not text:
        return "Provider 调用失败，请稍后重试。"
    if "finishReason=MAX_TOKENS" in text:
        return "Provider 调用失败：Gemini 输出被 MAX_TOKENS 截断，已保留草稿；请减少证据数量，或调高 GEMINI_MAX_TOKENS 后重试。"
    if "finishReason=" in text:
        return f"Provider 调用失败：{text}"
    if "invalid JSON" in text or "parse" in text.lower():
        detail = text.replace("returned invalid JSON; draft was kept", "").strip(" ：:;；。")
        detail = detail.replace(" ;", ";")
        if detail:
            return f"模型返回了不可解析 JSON，已保留草稿，请减少证据数量或重新调用。详情：{detail}"
        return "模型返回了不可解析 JSON，已保留草稿，请减少证据数量或重新调用。"
    if "manual prompt is empty" in text:
        return "Provider 调用失败：Prompt 为空，请重新生成 Prompt。"
    if "manual answer is empty" in text:
        return "手动回填为空：请粘贴 AI 返回的 JSON 后再保存。"
    if "analysis run is already done" in text:
        return "Provider 调用失败：这条分析已经完成，请使用重新分析创建新草稿。"
    if "provider is already running" in text:
        return "Provider 正在调用中，请稍后刷新查看结果。"
    if "not configured" in text or "API_KEY" in text:
        return "Provider 调用失败：API Key 未配置或不可用。"
    if "not available" in text:
        return "Provider 调用失败：当前 Provider 不可用。"
    return f"Provider 调用失败：{text}"


def analysis_status_label(status: object) -> str:
    return {
        "done": "已完成",
        "running": "调用中",
        "draft": "草稿",
    }.get(str(status or ""), "草稿")


def analysis_status_class(status: object) -> str:
    return {
        "done": "sent",
        "running": "normal",
        "draft": "none",
    }.get(str(status or ""), "none")


def provider_display_label(run: dict[str, object]) -> str:
    status = str(run.get("status") or "")
    model_label = str(run.get("model_label") or "").strip()
    provider_name = str(run.get("provider_name") or "").strip()
    if status == "done" and model_label:
        return model_label
    if model_label and model_label != "manual_chatgpt_business":
        return model_label
    error = str(run.get("provider_error") or "")
    match = re.search(r"Provider 调用失败：([^:：]+):", error)
    if match:
        return match.group(1)
    if provider_name:
        return provider_name
    return "待调用 / 待回填"


def running_wait_seconds(run: dict[str, object]) -> int:
    started = parse_history_datetime(str(run.get("provider_started_at") or ""))
    if not started:
        return 0
    return max(0, int((datetime.now() - started).total_seconds()))


async def execute_provider_run(run_id: str, provider_name: str, manual_prompt: str) -> None:
    provider = get_provider(provider_name)
    if not provider:
        save_provider_error(run_id, format_provider_error("provider is not available"))
        return
    start_time = time.monotonic()
    try:
        result = await asyncio.to_thread(
            provider.complete,
            provider_system_prompt(provider_name, provider.name),
            manual_prompt,
        )
        provider_elapsed_ms = int((time.monotonic() - start_time) * 1000)
        parsed = parse_answer(result.text)
        if parsed.get("parse_error"):
            preview = provider_raw_preview(result.text)
            save_provider_error(
                run_id,
                format_provider_error(
                    f"{result.model_label} returned invalid JSON; draft was kept; elapsed={provider_elapsed_ms / 1000:.1f}s; raw preview: {preview}"
                ),
                provider_elapsed_ms=provider_elapsed_ms,
            )
            return
        run = get_run(run_id) or {}
        parsed = apply_local_evidence_guard(parsed, run)
        saved = save_answer(
            run_id=run_id,
            answer_text=result.text,
            manual_prompt=manual_prompt,
            model_label=result.model_label,
            answer_json=parsed,
            judgement=str(parsed.get("judgement") or "unclear"),
            overall_confidence=float(parsed.get("overall_confidence") or 0),
            provider_elapsed_ms=provider_elapsed_ms,
            expected_status="running",
        )
        if not saved:
            log.warning("Provider result skipped for %s because status changed before completion", run_id)
    except ProviderError as exc:
        provider_elapsed_ms = int((time.monotonic() - start_time) * 1000)
        save_provider_error(
            run_id,
            format_provider_error(f"{provider.name}: {exc}; elapsed={provider_elapsed_ms / 1000:.1f}s"),
            provider_elapsed_ms=provider_elapsed_ms,
        )
    except Exception as exc:  # pragma: no cover - defensive guard for background tasks.
        provider_elapsed_ms = int((time.monotonic() - start_time) * 1000)
        log.exception("Provider background task failed for %s", run_id)
        save_provider_error(
            run_id,
            format_provider_error(f"background task failed: {type(exc).__name__}: {exc}"),
            provider_elapsed_ms=provider_elapsed_ms,
        )


def parse_int(value: object, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(str(value))
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(parsed, maximum))


def feed_params(request: Request) -> dict[str, object]:
    query = request.query_params
    priority = str(query.get("priority", "") or "")
    if priority not in ALLOWED_PRIORITIES:
        priority = ""
    return {
        "limit": parse_int(query.get("limit", "50"), 50, 1, 300),
        "priority": priority,
        "keyword": str(query.get("keyword", "") or "").strip()[:80],
        "hours": parse_int(query.get("hours", str(DEFAULT_HOURS)), DEFAULT_HOURS, 1, 720),
        "tg_sent_only": str(query.get("tg_sent_only", "")).lower() in {"1", "true", "yes", "on"},
        "with_status": str(query.get("with_status", "")).lower() in {"1", "true", "yes", "on"},
    }


async def read_urlencoded_form(request: Request) -> dict[str, str]:
    body = (await request.body()).decode("utf-8", errors="replace")
    parsed = parse_qs(body, keep_blank_values=True)
    return {key: values[-1] if values else "" for key, values in parsed.items()}


def parse_evidence_json(value: object) -> list[dict[str, object]]:
    try:
        parsed = json.loads(str(value or "[]"))
    except Exception:
        return []
    if not isinstance(parsed, list):
        return []
    return [item for item in parsed if isinstance(item, dict)]


def append_screenshot_context(user_context: str, screenshot_id: str = "", screenshot_description: str = "") -> str:
    parts = [user_context.strip()] if user_context.strip() else []
    description = screenshot_description.strip()
    if screenshot_id or description:
        line = "截图上下文："
        if screenshot_id:
            line += f" screenshot_id={screenshot_id}"
        if description:
            line += f"；{description}"
        parts.append(line)
    return "\n".join(parts)


def parse_multipart_upload(body: bytes, content_type: str) -> tuple[bytes, str, str, str]:
    marker = "boundary="
    if marker not in content_type:
        raise ValueError("not multipart")
    boundary = content_type.split(marker, 1)[1].split(";", 1)[0].strip().strip('"')
    if not boundary:
        raise ValueError("missing boundary")
    file_bytes = b""
    filename = "screenshot.png"
    mime_type = ""
    description = ""
    for part in body.split(("--" + boundary).encode()):
        if b"Content-Disposition" not in part:
            continue
        header, _, data = part.partition(b"\r\n\r\n")
        if not _:
            continue
        data = data.rstrip(b"\r\n")
        header_text = header.decode("utf-8", errors="ignore")
        disposition = header_text.lower()
        if 'name="description"' in disposition:
            description = data.decode("utf-8", errors="ignore").strip()
            continue
        if 'name="file"' not in disposition:
            continue
        disposition_line = ""
        for line in header_text.splitlines():
            lower = line.lower()
            if lower.startswith("content-disposition:"):
                disposition_line = line
            if lower.startswith("content-type:"):
                mime_type = line.split(":", 1)[1].strip()
        for segment in disposition_line.split(";"):
            segment = segment.strip()
            if segment.startswith("filename="):
                filename = Path(segment.split("=", 1)[1].strip().strip('"')).name or filename
        file_bytes = data
    if not file_bytes:
        raise ValueError("no file in request")
    return file_bytes, filename, mime_type, description


def normalize_datetime_input(value: object) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    text = text.replace("T", " ")
    if len(text) == 16:
        text = f"{text}:00"
    parsed = parse_history_datetime(text)
    return parsed.strftime("%Y-%m-%d %H:%M:%S") if parsed else text


def datetime_local_value(value: object) -> str:
    parsed = parse_history_datetime(value)
    if parsed:
        return parsed.strftime("%Y-%m-%dT%H:%M")
    text = str(value or "").strip().replace(" ", "T")
    return text[:16]


def floor_to_minute(value):
    return value.replace(second=0, microsecond=0)


def ceil_to_minute(value):
    rounded = value.replace(second=0, microsecond=0)
    if value.second or value.microsecond:
        rounded = rounded + timedelta(minutes=1)
    return rounded


def form_bool(value: object) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def parse_market_context_json(value: object) -> dict[str, object]:
    try:
        parsed = json.loads(str(value or "{}"))
    except Exception:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def summarize_klines(klines: list[object]) -> dict[str, object]:
    if not klines:
        return {}
    first = klines[0]
    last = klines[-1]
    first_close = float(getattr(first, "close", 0.0) or 0.0)
    last_close = float(getattr(last, "close", 0.0) or 0.0)
    move = last_close - first_close
    move_pct = (move / first_close * 100) if first_close else 0.0
    return {
        "count": len(klines),
        "first_close": round(first_close, 8),
        "last_close": round(last_close, 8),
        "move": round(move, 8),
        "move_pct": round(move_pct, 4),
        "high": round(max(float(getattr(kline, "high", 0.0) or 0.0) for kline in klines), 8),
        "low": round(min(float(getattr(kline, "low", 0.0) or 0.0) for kline in klines), 8),
    }


def build_market_context_for_prompt(
    *,
    enabled: bool,
    symbol: str,
    interval: str,
    start: str,
    end: str,
) -> dict[str, object]:
    if not enabled:
        return {"enabled": False, "market_data_called": False}

    adapter_name = configured_market_adapter_name()
    adapter = get_market_adapter(adapter_name)
    base = {
        "enabled": True,
        "ok": False,
        "adapter": adapter_name,
        "symbol": str(symbol or "").upper()[:20],
        "interval": str(interval or "1m")[:12],
        "start": start,
        "end": end,
        "market_data_called": bool(adapter),
    }
    if not adapter:
        return {**base, "error": "market adapter not configured" if not adapter_name else "market adapter not implemented"}
    try:
        klines = adapter.fetch_klines(symbol=base["symbol"], interval=base["interval"], start=start, end=end)
    except MarketAdapterError as exc:
        return {**base, "error": str(exc)}
    except Exception:
        log.exception("market context fetch failed")
        return {**base, "error": "unexpected market adapter error"}
    return {
        **base,
        "ok": True,
        "adapter": adapter.name,
        "source": "Binance Spot",
        "summary": summarize_klines(klines),
    }


def create_app() -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        init_analysis_db()
        stale_count = reset_stale_running_runs()
        if stale_count:
            log.warning("重置了 %d 个 running 孤儿记录为 draft（服务重启中断）", stale_count)
        yield

    app = FastAPI(title="Jin10 Monitor Dashboard", docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
    templates.env.globals["compact_text"] = compact_text
    templates.env.globals["priority_class"] = priority_class
    templates.env.globals["priority_css"] = priority_css
    templates.env.globals["datetime_local_value"] = datetime_local_value
    templates.env.globals["confidence_help"] = CONFIDENCE_HELP
    templates.env.globals["normalize_news_text"] = normalize_news_text
    templates.env.globals["judgement_label"] = judgement_label
    templates.env.globals["analysis_status_label"] = analysis_status_label
    templates.env.globals["analysis_status_class"] = analysis_status_class
    templates.env.globals["provider_display_label"] = provider_display_label
    templates.env.globals["running_wait_seconds"] = running_wait_seconds

    @app.get("/")
    async def index(request: Request):
        health = history_health()
        params = feed_params(request)
        items = []
        density = []
        heatmap = []
        if health["status"] == "ok":
            items = query_recent_items(**params)
            for item in items:
                item["summary"] = compact_text(item.get("title"), item.get("content"), limit=140)
            density = query_feed_density(hours=int(params["hours"]))
            heatmap = query_keyword_heatmap(hours=int(params["hours"]))
        return templates.TemplateResponse(
            request,
            "feed.html",
            {
                "health": health,
                "items": items,
                "density": density,
                "heatmap": heatmap,
                "params": params,
                "priority_options": PRIORITY_OPTIONS,
                "hours_options": HOURS_OPTIONS,
                "nav": query_nav_summary(),
            },
        )

    @app.get("/item/{message_id}")
    async def item_detail(request: Request, message_id: str):
        minutes = parse_int(request.query_params.get("minutes", "15"), 15, 0, 120)
        center, context_items = query_item_context(message_id, minutes=minutes)
        if not center:
            raise HTTPException(status_code=404, detail="message not found")
        for item in [center, *context_items]:
            item["summary"] = compact_text(item.get("title"), item.get("content"), limit=180)
        detail = query_item(message_id) or center
        tg_status = query_tg_status_for_item(message_id)
        analyze_url = ""
        market_start = ""
        market_end = ""
        published_at = str(center.get("published_at") or "")
        center_dt = parse_history_datetime(published_at)
        if center_dt:
            window_start = (center_dt - timedelta(minutes=minutes)).strftime("%Y-%m-%d %H:%M:%S")
            window_end = (center_dt + timedelta(minutes=minutes)).strftime("%Y-%m-%d %H:%M:%S")
            market_start_dt = floor_to_minute(center_dt - timedelta(minutes=minutes))
            market_end_dt = ceil_to_minute(center_dt + timedelta(minutes=minutes))
            market_start = market_start_dt.strftime("%Y-%m-%d %H:%M:%S")
            market_end = market_end_dt.strftime("%Y-%m-%d %H:%M:%S")
            analyze_url = "/analyze?" + urlencode(
                {
                    "from_item_id": message_id,
                    "window_start": window_start,
                    "window_end": window_end,
                }
            )
        return templates.TemplateResponse(
            request,
            "item.html",
            {
                "health": history_health(),
                "center": center,
                "item": detail,
                "context_items": context_items,
                "minutes": minutes,
                "tg_status": tg_status,
                "analyze_url": analyze_url,
                "market_start": market_start,
                "market_end": market_end,
                "nav": query_nav_summary(),
            },
        )

    @app.get("/telegram-status")
    async def telegram_status(request: Request):
        status_filter = str(request.query_params.get("status", "all") or "all")
        if status_filter not in ALLOWED_STATUSES:
            status_filter = "all"
        health = history_health()
        deliveries = []
        summary = {}
        if health["status"] == "ok":
            deliveries = query_tg_deliveries(status_filter=status_filter)
            summary = query_tg_summary()
            for item in deliveries:
                item["summary"] = compact_text(item.get("title"), item.get("content"), limit=110)
        return templates.TemplateResponse(
            request,
            "telegram_status.html",
            {
                "health": health,
                "deliveries": deliveries,
                "summary": summary,
                "status_filter": status_filter,
                "status_options": STATUS_OPTIONS,
                "nav": query_nav_summary(),
            },
        )

    @app.get("/system")
    async def system(request: Request):
        health = history_health()
        system_health = query_system_health() if health["status"] == "ok" else {}
        provider_call_stats = query_provider_call_stats() if health["status"] == "ok" else {}
        return templates.TemplateResponse(
            request,
            "system.html",
            {
                "health": health,
                "system_health": system_health,
                "provider_statuses": provider_statuses(),
                "provider_call_stats": provider_call_stats,
                "nav": query_nav_summary(),
            },
        )

    @app.get("/api/system/log-events")
    async def api_system_log_events(limit: int = 8, force: bool = False, level: str = ""):
        from .db import _LOG_EVENTS_CACHE, monitor_log_path, query_recent_monitor_log_events

        if force:
            _LOG_EVENTS_CACHE.pop(str(monitor_log_path().expanduser()), None)
        result = query_recent_monitor_log_events(limit=limit)
        events = result.get("events", [])
        level_filter = str(level or "").strip().upper()
        if level_filter:
            events = [event for event in events if str(event.get("level") or "").upper() == level_filter]
        return {
            "ok": True,
            "path": result.get("path", ""),
            "exists": result.get("exists", False),
            "file_size_kb": result.get("file_size_kb", 0),
            "last_modified": result.get("last_modified", ""),
            "events": events,
            "cached": not force,
            "level": level_filter,
        }

    @app.get("/system/ws-initial")
    async def ws_initial_review(request: Request):
        health = history_health()
        review = query_ws_initial_review() if health["status"] == "ok" else {}
        if review:
            for item in review["items"]:
                item["summary"] = compact_text(item.get("title"), item.get("content"), limit=140)
        return templates.TemplateResponse(
            request,
            "ws_initial_review.html",
            {
                "health": health,
                "review": review,
                "nav": query_nav_summary(),
            },
        )

    @app.get("/analyze")
    async def analyze(request: Request):
        prefill = {
            "from_item_id": str(request.query_params.get("from_item_id", "") or ""),
            "window_start": str(request.query_params.get("window_start", "") or ""),
            "window_end": str(request.query_params.get("window_end", "") or ""),
            "asset": str(request.query_params.get("asset", "BTC") or "BTC"),
            "question": str(request.query_params.get("question", "") or ""),
        }
        return templates.TemplateResponse(
            request,
            "analyze.html",
            {
                "health": history_health(),
                "prefill": prefill,
                "known_assets": known_assets(),
                "market_default_enabled": market_context_default_enabled(),
                "step": "input",
                "nav": query_nav_summary(),
            },
        )

    @app.post("/analyze/preview")
    async def analyze_preview(request: Request):
        form = await read_urlencoded_form(request)
        question = form.get("question", "").strip()
        asset = form.get("asset", "BTC").strip() or "BTC"
        window_start = normalize_datetime_input(form.get("window_start", ""))
        window_end = normalize_datetime_input(form.get("window_end", ""))
        from_item_id = form.get("from_item_id", "").strip()
        screenshot_id = form.get("screenshot_id", "").strip()
        screenshot_description = form.get("screenshot_description", "").strip()
        user_context = form.get("user_context", "").strip()
        evidence, boundary = build_evidence_for_preview(asset, window_start, window_end)
        market_context = build_market_context_for_prompt(
            enabled=form_bool(form.get("market_enabled", "")),
            symbol=form.get("market_symbol", "BTCUSDT"),
            interval=form.get("market_interval", "1m"),
            start=window_start,
            end=window_end,
        )
        if isinstance(boundary, dict):
            boundary = {
                **boundary,
                "market_data_called": bool(market_context.get("market_data_called")),
            }
        return templates.TemplateResponse(
            request,
            "analyze.html",
            {
                "health": history_health(),
                "step": "preview",
                "question": question,
                "asset": asset,
                "window_start": window_start,
                "window_end": window_end,
                "from_item_id": from_item_id,
                "screenshot_id": screenshot_id,
                "screenshot_description": screenshot_description,
                "user_context": user_context,
                "market_context": market_context,
                "evidence": evidence,
                "boundary": boundary,
                "known_assets": known_assets(),
                "market_default_enabled": market_context_default_enabled(),
                "prefill": {},
                "nav": query_nav_summary(),
            },
        )

    @app.post("/analyze/generate-prompt")
    async def analyze_generate_prompt(request: Request):
        form = await read_urlencoded_form(request)
        init_analysis_db()
        question = form.get("question", "").strip()
        asset = form.get("asset", "BTC").strip() or "BTC"
        window_start = normalize_datetime_input(form.get("window_start", ""))
        window_end = normalize_datetime_input(form.get("window_end", ""))
        from_item_id = form.get("from_item_id", "").strip()
        screenshot_id = form.get("screenshot_id", "").strip()
        screenshot_description = form.get("screenshot_description", "").strip()
        user_context = append_screenshot_context(
            form.get("user_context", ""),
            screenshot_id=screenshot_id,
            screenshot_description=screenshot_description,
        )
        market_context = parse_market_context_json(form.get("market_context_json", "{}"))
        evidence = parse_evidence_json(form.get("evidence_json", "[]"))
        selected_ids = {
            key.removeprefix("sel_")
            for key, value in form.items()
            if key.startswith("sel_") and value in {"1", "on", "true"}
        }
        if selected_ids:
            for item in evidence:
                item["selected"] = str(item.get("news_id") or item.get("id") or "") in selected_ids
        prompt = generate_prompt(
            question=question,
            asset=asset,
            window_start=window_start,
            window_end=window_end,
            evidence=evidence,
            user_context=user_context,
            market_context=market_context,
        )
        selected_count = sum(1 for item in evidence if item.get("selected", True))
        run_id = create_run(
            question=question,
            asset=asset,
            window_start=window_start,
            window_end=window_end,
            evidence_packet=evidence,
            from_item_id=from_item_id,
            screenshot_id=screenshot_id,
            user_context=user_context,
            manual_prompt=prompt,
            prompt_version=PROMPT_VERSION,
        )
        return templates.TemplateResponse(
            request,
            "analyze.html",
            {
                "health": history_health(),
                "step": "prompt",
                "run_id": run_id,
                "question": question,
                "asset": asset,
                "window_start": window_start,
                "window_end": window_end,
                "from_item_id": from_item_id,
                "screenshot_id": screenshot_id,
                "user_context": user_context,
                "market_context": market_context,
                "evidence": evidence,
                "prompt": prompt,
                "prompt_length": len(prompt),
                "selected_count": selected_count,
                "provider_statuses": callable_provider_statuses(),
                "known_assets": known_assets(),
                "market_default_enabled": market_context_default_enabled(),
                "prefill": {},
                "nav": query_nav_summary(),
            },
        )

    @app.post("/analyze/save-answer")
    async def analyze_save_answer(request: Request):
        form = await read_urlencoded_form(request)
        init_analysis_db()
        run_id = form.get("run_id", "").strip()
        answer_text = form.get("answer_text", "")
        manual_prompt = form.get("manual_prompt", "")
        if not answer_text.strip():
            save_provider_error(run_id, format_provider_error("manual answer is empty"))
            return provider_error_redirect(run_id, format_provider_error("manual answer is empty"))
        parsed = parse_answer(answer_text)
        run = get_run(run_id) or {}
        parsed = apply_local_evidence_guard(parsed, run)
        saved = save_answer(
            run_id=run_id,
            answer_text=answer_text,
            manual_prompt=manual_prompt,
            model_label="manual_chatgpt_business",
            answer_json=parsed,
            judgement=str(parsed.get("judgement") or "unclear"),
            overall_confidence=float(parsed.get("overall_confidence") or 0),
            provider_name="",
            expected_status="draft",
        )
        if not saved:
            return provider_error_redirect(run_id, "保存失败：这条分析不是草稿状态，可能正在调用或已经完成。")
        return RedirectResponse(f"/analyze/{run_id}", status_code=303)

    @app.get("/analyze/compare")
    async def analyze_compare(request: Request):
        raw_ids = str(request.query_params.get("ids", "") or "")
        run_ids = [run_id.strip() for run_id in raw_ids.split(",") if run_id.strip()][:2]
        init_analysis_db()
        runs = get_runs_for_compare(run_ids) if run_ids else []
        return templates.TemplateResponse(
            request,
            "analyze_compare.html",
            {
                "health": history_health(),
                "runs": runs,
                "run_ids": run_ids,
                "nav": query_nav_summary(),
            },
        )

    @app.get("/analyze/history")
    async def analyze_history(request: Request):
        asset_filter = str(request.query_params.get("asset", "") or "")
        status_filter = str(request.query_params.get("status", "all") or "all")
        if status_filter not in ALLOWED_ANALYSIS_STATUSES:
            status_filter = "all"
        status_filter_label = dict(ANALYSIS_STATUS_OPTIONS).get(status_filter, status_filter)
        init_analysis_db()
        runs = list_runs(asset=asset_filter, status_filter=status_filter, limit=50)
        return templates.TemplateResponse(
            request,
            "analyze_history.html",
            {
                "health": history_health(),
                "runs": runs,
                "asset_filter": asset_filter,
                "status_filter": status_filter,
                "status_filter_label": status_filter_label,
                "analysis_status_options": ANALYSIS_STATUS_OPTIONS,
                "known_assets": known_assets(),
                "nav": query_nav_summary(),
            },
        )

    @app.get("/analyze/{run_id}")
    async def analyze_run_detail(request: Request, run_id: str):
        init_analysis_db()
        run = get_run(run_id)
        answer_html = ""
        if run and run.get("answer_parsed"):
            answer_html = render_answer_with_links(run["answer_parsed"])
        review_warning = provider_review_warning(run) if run else ""
        provider_estimate_seconds = (
            estimate_provider_completion_seconds(str(run.get("provider_name") or ""))
            if run and str(run.get("status") or "") == "running"
            else None
        )
        return templates.TemplateResponse(
            request,
            "analyze_run.html",
            {
                "health": history_health(),
                "run": run,
                "run_id": run_id,
                "answer_html": answer_html,
                "provider_review_warning": review_warning,
                "provider_statuses": callable_provider_statuses(),
                "provider_error": str(request.query_params.get("provider_error", "") or ""),
                "provider_success": str(request.query_params.get("provider_success", "") or ""),
                "provider_started": str(request.query_params.get("provider_started", "") or ""),
                "delete_error": str(request.query_params.get("delete_error", "") or ""),
                "provider_estimate_seconds": provider_estimate_seconds,
                "selected_provider": str(request.query_params.get("provider", "") or ""),
                "nav": query_nav_summary(),
            },
        )

    @app.post("/analyze/{run_id}/run-provider")
    async def analyze_run_provider(request: Request, run_id: str, background_tasks: BackgroundTasks):
        form = await read_urlencoded_form(request)
        provider_name = form.get("provider", "").strip()
        init_analysis_db()
        run = get_run(run_id)
        if not run:
            raise HTTPException(status_code=404, detail="analysis run not found")
        if str(run.get("status") or "") != "draft":
            return provider_error_redirect(
                run_id,
                format_provider_error(
                    "provider is already running" if str(run.get("status") or "") == "running" else "analysis run is already done"
                ),
                provider_name=provider_name,
            )
        manual_prompt = ensure_run_manual_prompt(run)
        if not manual_prompt:
            return save_and_redirect_provider_error(
                run_id,
                format_provider_error("manual prompt is empty; please recreate the analysis draft"),
                provider_name=provider_name,
            )
        provider = get_provider(provider_name)
        if not provider:
            return save_and_redirect_provider_error(
                run_id,
                format_provider_error("provider is not available"),
                provider_name=provider_name,
            )
        started = mark_provider_running(run_id, provider_name=provider_name, provider_label=provider.name)
        if not started:
            return provider_error_redirect(
                run_id,
                format_provider_error("provider is already running"),
                provider_name=provider_name,
            )
        background_tasks.add_task(execute_provider_run, run_id, provider_name, manual_prompt)
        return RedirectResponse(
            f"/analyze/{run_id}?{urlencode({'provider_started': provider.name, 'provider': provider_name})}",
            status_code=303,
        )

    @app.post("/analyze/{run_id}/delete")
    async def analyze_delete_run(run_id: str):
        init_analysis_db()
        deleted = delete_run(run_id, allowed_statuses=("draft",))
        if not deleted:
            return RedirectResponse(
                f"/analyze/{run_id}?{urlencode({'delete_error': '只能删除草稿记录；已完成或调用中的分析请保留用于复盘。'})}",
                status_code=303,
            )
        return RedirectResponse("/analyze/history?status=draft", status_code=303)

    @app.post("/api/screenshots/upload")
    async def api_screenshot_upload(request: Request):
        try:
            content_length = str(request.headers.get("content-length", "") or "").strip()
            if content_length:
                try:
                    if int(content_length) > MAX_SCREENSHOT_BYTES:
                        return JSONResponse({"ok": False, "error": "image is larger than 8 MB"}, status_code=413)
                except ValueError:
                    pass
            body = await request.body()
            file_bytes, filename, mime_type, description = parse_multipart_upload(
                body,
                request.headers.get("content-type", ""),
            )
            if mime_type.lower() not in ALLOWED_SCREENSHOT_MIME_TYPES:
                return JSONResponse(
                    {"ok": False, "error": "only png/jpeg/webp/gif uploads are accepted"},
                    status_code=400,
                )
            if len(file_bytes) > MAX_SCREENSHOT_BYTES:
                return JSONResponse({"ok": False, "error": "image is larger than 8 MB"}, status_code=413)
            init_analysis_db()
            screenshot_id = save_screenshot(file_bytes, filename, user_description=description)
            return JSONResponse({"ok": True, "screenshot_id": screenshot_id, "filename": filename})
        except ValueError as exc:
            return JSONResponse({"ok": False, "error": str(exc)}, status_code=400)
        except Exception:
            log.exception("screenshot upload failed")
            return JSONResponse({"ok": False, "error": "upload failed"}, status_code=500)

    @app.get("/screenshots/{screenshot_id}")
    async def screenshot_file(screenshot_id: str):
        init_analysis_db()
        screenshot = get_screenshot(screenshot_id)
        if not screenshot:
            raise HTTPException(status_code=404, detail="screenshot not found")
        file_path = (BASE_DIR / str(screenshot.get("file_path") or "")).resolve()
        screenshots_root = (BASE_DIR / "data" / "screenshots").resolve()
        if screenshots_root not in file_path.parents or not file_path.exists():
            raise HTTPException(status_code=404, detail="screenshot file not found")
        return FileResponse(file_path)

    @app.get("/api/feed/page")
    async def api_feed_page(request: Request):
        try:
            health = history_health()
            if health["status"] != "ok":
                return JSONResponse({"html": "", "items_count": 0, "has_more": False, "next_offset": 0})
            query = request.query_params
            params = feed_params(request)
            offset = parse_int(query.get("offset", "0"), 0, 0, 1000000)
            limit = parse_int(query.get("limit", "30"), 30, 1, 50)
            items = query_feed_page(
                offset=offset,
                limit=limit,
                priority=str(params["priority"]),
                keyword=str(params["keyword"]),
                hours=int(params["hours"]),
                tg_sent_only=bool(params["tg_sent_only"]),
                with_status=bool(params["with_status"]),
            )
            for item in items:
                item["summary"] = compact_text(item.get("title"), item.get("content"), limit=140)
            html = templates.env.get_template("_feed_rows.html").render(request=request, items=items)
            return JSONResponse(
                {
                    "html": html,
                    "items_count": len(items),
                    "has_more": len(items) == limit,
                    "next_offset": offset + len(items),
                }
            )
        except Exception:
            return JSONResponse({"html": "", "items_count": 0, "has_more": False, "next_offset": 0})

    @app.get("/api/feed/latest-ts")
    async def api_feed_latest_ts(request: Request):
        try:
            health = history_health()
            if health["status"] != "ok":
                return JSONResponse({"latest_ts": None})
            params = feed_params(request)
            latest_ts = query_latest_published_at(
                priority=str(params["priority"]),
                keyword=str(params["keyword"]),
                hours=int(params["hours"]),
                tg_sent_only=bool(params["tg_sent_only"]),
                with_status=bool(params["with_status"]),
            )
            return JSONResponse({"latest_ts": latest_ts})
        except Exception:
            return JSONResponse({"latest_ts": None})

    @app.get("/api/market/klines")
    async def api_market_klines(request: Request):
        query = request.query_params
        symbol = str(query.get("symbol", "") or "").upper()[:20]
        interval = str(query.get("interval", "1m") or "1m")[:12]
        start = str(query.get("start", "") or "")[:32]
        end = str(query.get("end", "") or "")[:32]
        adapter_name = configured_market_adapter_name()
        adapter = get_market_adapter(adapter_name)
        if not adapter:
            return JSONResponse(
                {
                    "ok": False,
                    "error": "market adapter not configured" if not adapter_name else "market adapter not implemented",
                    "adapter": adapter_name,
                    "hint": "configure a market adapter before enabling price overlays",
                    "symbol": symbol,
                    "interval": interval,
                    "start": start,
                    "end": end,
                    "klines": [],
                }
            )
        try:
            klines = await asyncio.to_thread(
                adapter.fetch_klines,
                symbol=symbol,
                interval=interval,
                start=start,
                end=end,
            )
            return JSONResponse(
                {
                    "ok": True,
                    "adapter": adapter.name,
                    "symbol": symbol,
                    "interval": interval,
                    "start": klines[0].open_time if klines else start,
                    "end": klines[-1].open_time if klines else end,
                    "klines": [kline.__dict__ for kline in klines],
                }
            )
        except MarketAdapterError as exc:
            return JSONResponse(
                {
                    "ok": False,
                    "error": "market data unavailable",
                    "detail": str(exc),
                    "adapter": adapter.name,
                    "symbol": symbol,
                    "interval": interval,
                    "start": start,
                    "end": end,
                    "klines": [],
                }
            )
        except Exception:
            log.exception("market klines fetch failed")
            return JSONResponse(
                {
                    "ok": False,
                    "error": "market data unavailable",
                    "detail": "unexpected adapter error",
                    "adapter": adapter.name,
                    "symbol": symbol,
                    "interval": interval,
                    "start": start,
                    "end": end,
                    "klines": [],
                }
            )

    @app.get("/aggregation")
    async def aggregation(request: Request):
        health = history_health()
        report = query_aggregation_report() if health["status"] == "ok" else {}
        return templates.TemplateResponse(
            request,
            "aggregation.html",
            {
                "health": health,
                "agg": report,
                "nav": query_nav_summary(),
            },
        )

    @app.get("/api/aggregation/stats")
    async def api_aggregation_stats():
        health = history_health()
        if health["status"] != "ok":
            return JSONResponse({"ok": False, "error": health["status"]}, status_code=503)
        return JSONResponse({"ok": True, **query_aggregation_report()})

    @app.get("/healthz")
    async def healthz():
        health = history_health()
        status_code = 200 if health["status"] == "ok" else 503
        return JSONResponse(health, status_code=status_code)

    return app


app = create_app()
