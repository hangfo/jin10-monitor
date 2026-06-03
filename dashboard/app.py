"""FastAPI application for the standalone dashboard."""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import timedelta
from pathlib import Path
from urllib.parse import parse_qs, urlencode

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
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
    save_answer,
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
    query_aggregation_report,
)
from .evidence import build_evidence_for_preview, known_assets
from .market.base import MarketAdapterError, configured_market_adapter_name, get_market_adapter
from .manual_ai import PROMPT_VERSION, generate_prompt, parse_answer, render_answer_with_links
from .providers.base import provider_statuses

TEMPLATE_DIR = Path(__file__).resolve().parent / "templates"
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
    app = FastAPI(title="Jin10 Monitor Dashboard", docs_url=None, redoc_url=None, openapi_url=None)
    templates.env.globals["compact_text"] = compact_text
    templates.env.globals["priority_class"] = priority_class
    templates.env.globals["priority_css"] = priority_css
    templates.env.globals["datetime_local_value"] = datetime_local_value
    templates.env.globals["confidence_help"] = CONFIDENCE_HELP
    templates.env.globals["normalize_news_text"] = normalize_news_text

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
            market_start = window_start
            market_end = window_end
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
        return templates.TemplateResponse(
            request,
            "system.html",
            {
                "health": health,
                "system_health": system_health,
                "provider_statuses": provider_statuses(),
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
                "known_assets": known_assets(),
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
        parsed = parse_answer(answer_text)
        save_answer(
            run_id=run_id,
            answer_text=answer_text,
            manual_prompt=manual_prompt,
            answer_json=parsed,
            judgement=str(parsed.get("judgement") or "unclear"),
            overall_confidence=float(parsed.get("overall_confidence") or 0),
        )
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
        init_analysis_db()
        runs = list_runs(asset=asset_filter, limit=50)
        return templates.TemplateResponse(
            request,
            "analyze_history.html",
            {
                "health": history_health(),
                "runs": runs,
                "asset_filter": asset_filter,
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
        return templates.TemplateResponse(
            request,
            "analyze_run.html",
            {
                "health": history_health(),
                "run": run,
                "run_id": run_id,
                "answer_html": answer_html,
                "nav": query_nav_summary(),
            },
        )

    @app.post("/analyze/{run_id}/delete")
    async def analyze_delete_run(run_id: str):
        init_analysis_db()
        delete_run(run_id)
        return RedirectResponse("/analyze/history", status_code=303)

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
                    "start": start,
                    "end": end,
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

    @app.get("/healthz")
    async def healthz():
        health = history_health()
        status_code = 200 if health["status"] == "ok" else 503
        return JSONResponse(health, status_code=status_code)

    return app


app = create_app()
