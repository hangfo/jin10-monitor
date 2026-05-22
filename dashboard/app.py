"""FastAPI application for the standalone dashboard."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.templating import Jinja2Templates

from .db import history_health, query_recent_items

TEMPLATE_DIR = Path(__file__).resolve().parent / "templates"

templates = Jinja2Templates(directory=str(TEMPLATE_DIR))


def compact_text(*parts: object, limit: int = 120) -> str:
    text = " ".join(str(part or "").strip() for part in parts if str(part or "").strip())
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1] + "..."


def create_app() -> FastAPI:
    app = FastAPI(title="Jin10 Monitor Dashboard")

    @app.get("/")
    async def index(request: Request):
        health = history_health()
        items = []
        if health["status"] == "ok":
            items = query_recent_items(limit=80)
            for item in items:
                item["summary"] = compact_text(item.get("title"), item.get("content"), limit=140)
        return templates.TemplateResponse(
            request,
            "index.html",
            {"health": health, "items": items},
        )

    @app.get("/healthz")
    async def healthz():
        health = history_health()
        status_code = 200 if health["status"] == "ok" else 503
        return JSONResponse(health, status_code=status_code)

    return app


app = create_app()
