"""FastAPI application for the standalone dashboard."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.templating import Jinja2Templates


BASE_DIR = Path(__file__).resolve().parent.parent
TEMPLATE_DIR = Path(__file__).resolve().parent / "templates"
DEFAULT_HISTORY_DB = BASE_DIR / "data" / "jin10_history.sqlite3"

templates = Jinja2Templates(directory=str(TEMPLATE_DIR))


def history_db_path() -> Path:
    return Path(os.getenv("HISTORY_DB", str(DEFAULT_HISTORY_DB))).expanduser()


def dashboard_health() -> dict[str, Any]:
    db_path = history_db_path()
    return {
        "status": "ok" if db_path.exists() else "missing_history_db",
        "history_db": str(db_path),
        "history_db_exists": db_path.exists(),
        "read_boundary": "local_sqlite_readonly",
        "writes_business_db": False,
        "calls_jin10_rest": False,
        "sends_telegram": False,
    }


def create_app() -> FastAPI:
    app = FastAPI(title="Jin10 Monitor Dashboard")

    @app.get("/")
    async def index(request: Request):
        return templates.TemplateResponse(
            request,
            "index.html",
            {"health": dashboard_health()},
        )

    @app.get("/healthz")
    async def healthz():
        status_code = 200 if history_db_path().exists() else 503
        return JSONResponse(dashboard_health(), status_code=status_code)

    return app


app = create_app()
