"""FastAPI application for the standalone dashboard."""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path
from urllib.parse import urlencode

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.templating import Jinja2Templates

from .db import (
    DEFAULT_HOURS,
    HOURS_OPTIONS,
    history_health,
    parse_history_datetime,
    query_feed_density,
    query_item,
    query_item_context,
    query_keyword_heatmap,
    query_nav_summary,
    query_recent_items,
    query_system_health,
    query_tg_deliveries,
    query_tg_status_for_item,
    query_tg_summary,
)

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


def compact_text(*parts: object, limit: int = 120) -> str:
    text = " ".join(str(part or "").strip() for part in parts if str(part or "").strip())
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1] + "..."


def priority_class(level: object) -> str:
    return {
        "T3_IMPORTANT": "important",
        "T2_HIGH": "high",
        "T1_NORMAL": "normal",
        "T0_NONE": "none",
    }.get(str(level or ""), "none")


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
        "limit": parse_int(query.get("limit", "80"), 80, 1, 300),
        "priority": priority,
        "keyword": str(query.get("keyword", "") or "").strip()[:80],
        "hours": parse_int(query.get("hours", str(DEFAULT_HOURS)), DEFAULT_HOURS, 1, 720),
        "tg_sent_only": str(query.get("tg_sent_only", "")).lower() in {"1", "true", "yes", "on"},
        "with_status": str(query.get("with_status", "")).lower() in {"1", "true", "yes", "on"},
    }


def create_app() -> FastAPI:
    app = FastAPI(title="Jin10 Monitor Dashboard")
    templates.env.globals["compact_text"] = compact_text
    templates.env.globals["priority_class"] = priority_class

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
        published_at = str(center.get("published_at") or "")
        center_dt = parse_history_datetime(published_at)
        if center_dt:
            window_start = (center_dt - timedelta(minutes=minutes)).strftime("%Y-%m-%d %H:%M:%S")
            window_end = (center_dt + timedelta(minutes=minutes)).strftime("%Y-%m-%d %H:%M:%S")
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
                "nav": query_nav_summary(),
            },
        )

    @app.get("/analyze")
    async def analyze(request: Request):
        prefill = {
            "from_item_id": str(request.query_params.get("from_item_id", "") or ""),
            "window_start": str(request.query_params.get("window_start", "") or ""),
            "window_end": str(request.query_params.get("window_end", "") or ""),
        }
        return templates.TemplateResponse(
            request,
            "analyze.html",
            {
                "health": history_health(),
                "prefill": prefill,
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
