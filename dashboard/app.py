"""FastAPI application for the standalone dashboard."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.templating import Jinja2Templates

from .db import history_health, query_item_context, query_recent_items

TEMPLATE_DIR = Path(__file__).resolve().parent / "templates"
PRIORITY_OPTIONS = [
    ("", "全部"),
    ("T3_IMPORTANT", "T3 重要"),
    ("T2_HIGH", "T2 高优"),
    ("T1_NORMAL", "T1 普通"),
    ("T0_NONE", "T0 仅入库"),
]
ALLOWED_PRIORITIES = {value for value, _label in PRIORITY_OPTIONS}

templates = Jinja2Templates(directory=str(TEMPLATE_DIR))


def compact_text(*parts: object, limit: int = 120) -> str:
    text = " ".join(str(part or "").strip() for part in parts if str(part or "").strip())
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1] + "..."


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
        "with_status": str(query.get("with_status", "")).lower() in {"1", "true", "yes", "on"},
    }


def create_app() -> FastAPI:
    app = FastAPI(title="Jin10 Monitor Dashboard")

    @app.get("/")
    async def index(request: Request):
        health = history_health()
        params = feed_params(request)
        items = []
        if health["status"] == "ok":
            items = query_recent_items(**params)
            for item in items:
                item["summary"] = compact_text(item.get("title"), item.get("content"), limit=140)
        return templates.TemplateResponse(
            request,
            "index.html",
            {
                "health": health,
                "items": items,
                "params": params,
                "priority_options": PRIORITY_OPTIONS,
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
        return templates.TemplateResponse(
            request,
            "item.html",
            {"center": center, "context_items": context_items, "minutes": minutes},
        )

    @app.get("/healthz")
    async def healthz():
        health = history_health()
        status_code = 200 if health["status"] == "ok" else 503
        return JSONResponse(health, status_code=status_code)

    return app


app = create_app()
