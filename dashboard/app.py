"""FastAPI application for the standalone dashboard."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.templating import Jinja2Templates

from .db import history_db_path, history_health

TEMPLATE_DIR = Path(__file__).resolve().parent / "templates"

templates = Jinja2Templates(directory=str(TEMPLATE_DIR))


def create_app() -> FastAPI:
    app = FastAPI(title="Jin10 Monitor Dashboard")

    @app.get("/")
    async def index(request: Request):
        return templates.TemplateResponse(
            request,
            "index.html",
            {"health": history_health()},
        )

    @app.get("/healthz")
    async def healthz():
        health = history_health()
        status_code = 200 if health["status"] == "ok" else 503
        return JSONResponse(health, status_code=status_code)

    return app


app = create_app()
