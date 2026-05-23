# 034 - Dashboard Phase 1 handoff

Date: 2026-05-23

## Current state

Phase 1 of the standalone FastAPI/Jinja2 dashboard is implemented, committed, and pushed on `main`.

Latest commit:

```text
2a555b3 feat(dashboard): complete phase 1 pages
```

The working tree was clean after push.

## What was completed

- Kept the old `6330022` readonly `jin10_monitor.py --dashboard` MVP as fallback.
- Continued the official dashboard direction in standalone files only:
  - `run_dashboard.py`
  - `dashboard/app.py`
  - `dashboard/db.py`
  - `dashboard/templates/*`
- Did not extend `jin10_monitor.py`.
- Added a shared Jinja2 layout:
  - `dashboard/templates/base.html`
- Replaced the old standalone homepage template:
  - removed `dashboard/templates/index.html`
  - added `dashboard/templates/feed.html`
- Added Phase 1 pages:
  - `/`
  - `/item/{message_id}`
  - `/telegram-status`
  - `/system`
  - `/analyze` placeholder for Phase 2A
- Extended feed filters:
  - priority
  - keyword
  - recent hours
  - limit
  - confirmed Telegram sent only
- Corrected Telegram sent semantics:
  - `tg_sent_only` uses `delivery_log`
  - `telegram_delivery_status` remains diagnostic status only
- Added item detail enhancements:
  - context timeline
  - latest Telegram status
  - raw JSON foldout when available
  - prefilled `/analyze` link with `from_item_id`, `window_start`, and `window_end`
- Added readonly dashboard DB helpers:
  - `query_feed_density`
  - `query_keyword_heatmap`
  - `query_item`
  - `query_tg_status_for_item`
  - `query_tg_deliveries`
  - `query_tg_summary`
  - `query_system_health`
  - `query_nav_summary`
- Updated `README.md` and `CHANGELOG.md`.

## Validation

Last local test run:

```text
.venv/bin/python -m pytest -q
107 passed
```

Browser smoke checks passed for:

- `http://127.0.0.1:8765/`
- `http://127.0.0.1:8765/item/{message_id}`
- `http://127.0.0.1:8765/telegram-status`
- `http://127.0.0.1:8765/system`
- `http://127.0.0.1:8765/analyze`
- `http://127.0.0.1:8765/healthz`

Screenshot captured during verification:

```text
/private/tmp/jin10-dashboard-phase1-merge-fixed.png
```

## Boundaries preserved

- Phase 1 did not modify `jin10_monitor.py`.
- Dashboard opens the business SQLite with `mode=ro` and `PRAGMA query_only = ON`.
- Dashboard does not create the history DB when missing.
- Dashboard does not call Jin10 REST.
- Dashboard does not open WebSocket.
- Dashboard does not send Telegram.
- Dashboard does not implement retry, resend, or backfill actions.
- `delivery_log` remains the success-only Telegram dedupe authority.
- `telegram_delivery_status` remains diagnostic only.

## Known tradeoffs

- `query_keyword_heatmap` currently uses a small fixed dashboard keyword list. It can later be changed to reuse configured keywords, but that is not necessary for Phase 1.
- `/analyze` is only a placeholder. It accepts prefilled query parameters but does not build evidence packets, write analysis data, or call any AI API.
- The system page infers monitor freshness from `runtime_state.last_ingested_at`; it is a readonly health hint, not process supervision.

## Next recommended phase

Start Phase 2A: manual AI analysis loop.

Suggested order:

1. Add `dashboard/analysis_db.py`.
2. Create isolated `data/dashboard_analysis.sqlite3` schema.
3. Add tests proving analysis DB writes are isolated from the business history DB.
4. Add `dashboard/evidence.py` to build evidence packets from local SQLite only.
5. Add `dashboard/manual_ai.py` for prompt generation and permissive answer parsing.
6. Replace `/analyze` placeholder with the manual workflow:
   - choose question / symbol / time window
   - preview evidence packet
   - copy prompt
   - paste ChatGPT Business / Custom GPT answer
   - save answer and references locally

Important Phase 2A defaults:

- No Anthropic / Claude API dependency.
- No automatic model API dependency.
- Evidence builder reads local SQLite only.
- Evidence builder does not call Jin10 REST.
- Analysis writes only `data/dashboard_analysis.sqlite3`.
- Business history DB remains readonly.

## Model recommendation

Use `GPT-5.5 高` for the next Phase 2A session because it touches schema design, evidence boundaries, manual parsing, and UI workflow.
