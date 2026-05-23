"""FastAPI application for the standalone dashboard."""

from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path
from urllib.parse import parse_qs, urlencode

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from .analysis_db import create_run, delete_run, get_run, init_analysis_db, list_runs, save_answer
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
from .evidence import build_evidence_for_preview, known_assets
from .manual_ai import PROMPT_VERSION, generate_prompt, parse_answer, render_answer_with_links

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
        "limit": parse_int(query.get("limit", "80"), 80, 1, 300),
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


def create_app() -> FastAPI:
    app = FastAPI(title="Jin10 Monitor Dashboard")
    templates.env.globals["compact_text"] = compact_text
    templates.env.globals["priority_class"] = priority_class
    templates.env.globals["priority_css"] = priority_css

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
        window_start = form.get("window_start", "").strip()
        window_end = form.get("window_end", "").strip()
        from_item_id = form.get("from_item_id", "").strip()
        user_context = form.get("user_context", "").strip()
        evidence, boundary = build_evidence_for_preview(asset, window_start, window_end)
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
                "user_context": user_context,
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
        window_start = form.get("window_start", "").strip()
        window_end = form.get("window_end", "").strip()
        from_item_id = form.get("from_item_id", "").strip()
        user_context = form.get("user_context", "").strip()
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
        )
        run_id = create_run(
            question=question,
            asset=asset,
            window_start=window_start,
            window_end=window_end,
            evidence_packet=evidence,
            from_item_id=from_item_id,
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
                "user_context": user_context,
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

    @app.get("/healthz")
    async def healthz():
        health = history_health()
        status_code = 200 if health["status"] == "ok" else 503
        return JSONResponse(health, status_code=status_code)

    return app


app = create_app()
