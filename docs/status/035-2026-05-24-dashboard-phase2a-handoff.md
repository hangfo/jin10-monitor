# 035 - Dashboard Phase 2A handoff

Date: 2026-05-24

## Current state

Phase 2A of the standalone FastAPI/Jinja2 dashboard was committed and pushed as
`bd303ae feat(dashboard): add manual analysis workflow`.

This handoff also records the follow-up dashboard polish/bugfix patch prepared
for `fix(dashboard): polish phase 2a dashboard`.

Current branch:

```text
main
```

Follow-up patch scope:

- `CHANGELOG.md`
- `dashboard/app.py`
- `dashboard/db.py`
- `dashboard/evidence.py`
- `dashboard/templates/feed.html`
- `dashboard/templates/analyze.html`
- `dashboard/templates/base.html`
- `dashboard/templates/system.html`
- `dashboard/templates/aggregation.html`
- `docs/status/035-2026-05-24-dashboard-phase2a-handoff.md`
- `tests/test_dashboard_analysis.py`
- `tests/test_dashboard_db.py`

The dashboard dev server is currently running at:

```text
http://127.0.0.1:8765/
```

## What was completed

- Replaced the Phase 1 `/analyze` placeholder with the Phase 2A manual analysis
  workflow:
  - input question, asset, time window, optional source item, optional context
  - preview local evidence packet
  - select evidence rows
  - generate copy/paste prompt for ChatGPT Business or Custom GPT
  - paste answer back into dashboard
  - save and view analysis history/details
- Added an isolated analysis database layer:
  - writes to `data/dashboard_analysis.sqlite3`
  - creates `analysis_runs`, `analysis_evidence`, and `screenshots`
  - enables WAL and foreign-key cascade delete
  - preserves separation from `data/jin10_history.sqlite3`
- Added a local-only evidence builder:
  - reads `flash_history` through the existing readonly dashboard connection
  - scores by asset keywords, high-priority keywords, macro keywords, priority,
    important, and bold flags
  - adds `news_id` for downstream prompt/database/template consistency
  - caps packet size to 25 items
- Added manual AI helpers:
  - prompt generation with strict evidence-only JSON instruction
  - permissive answer parsing from fenced JSON, bare JSON, or best-effort JSON
    block extraction
  - rendered answer links from `[#news_id]` back to `/item/{id}`
- Added analysis templates:
  - `analyze.html`
  - `analyze_run.html`
  - `analyze_history.html`
- Improved the feed page:
  - keyword heatmap now uses the real configured `KEYWORDS` and
    `HIGH_PRIORITY` lists from `jin10_monitor.py`
  - high-priority heatmap keywords are marked for highlighting
  - the feed page polls `/api/feed/latest-ts` every 20 seconds and refreshes
    only when a newer `published_at` is detected; polling stops while the page
    is hidden and refresh skips while the user edits filter inputs
  - the polling endpoint keeps the current feed filters, so keyword/priority
    pages are not refreshed by unrelated newer items
- Added Phase 2A polish/fix items:
  - disabled default FastAPI `/docs`, `/redoc`, and `/openapi.json`
  - added navigation links for analysis history and aggregation report
  - changed evidence boundary from a plain string to a structured object with
    `source`, `jin10_rest_called`, and `market_data_called`
  - added a readonly `/aggregation` foundation page backed by skipped
    `telegram_delivery_status` diagnostics
  - improved `/system` monitor status with colored Chinese status labels
- Added focused tests for:
  - analysis DB roundtrip
  - cascade delete
  - analysis DB separation from business history DB
  - evidence scoring and `news_id` labeling
  - answer parsing and link rendering
  - `/analyze/history` route ordering before `/analyze/{run_id}`
  - configured keyword heatmap behavior
  - disabled docs routes
  - aggregation report readonly helper
- Updated `CHANGELOG.md`.

## Code intake notes

The uploaded `phase 2a.zip` was useful but not safe to apply as a direct
overwrite.

Issues fixed during merge:

- The uploaded `app.py` registered `GET /analyze` twice, so the old placeholder
  route would keep winning.
- The uploaded route order placed `/analyze/{run_id}` before
  `/analyze/history`, which would route `history` as a run id.
- The uploaded evidence path queried `id` but downstream code expected
  `news_id`.
- The uploaded `save_answer()` update path had a selected-count parameter order
  risk.
- The uploaded `db.py` and `base.html` conflicted with already validated Phase 1
  behavior, so they were not applied wholesale.
- No `python-multipart` dependency was added; form parsing uses lightweight
  URL-encoded body parsing to avoid making Phase 2A startup depend on a new
  package.
- The uploaded `phase 2a update.zip` added useful ideas, but was also not safe
  to apply wholesale. The merged parts were the configured keyword heatmap,
  additional Phase 2A tests, compatible analyze templates where useful, and the
  feed auto-refresh behavior. Its `app.py` was not adopted because it reintroduced
  `Form(...)` / `python-multipart` as a hard startup dependency.
- The uploaded `phase 2a bug fix.zip` was reviewed and merged selectively:
  - adopted: docs/openapi disablement, analysis history and aggregation nav,
    colored `/system` monitor status, structured evidence boundary, readonly
    `/aggregation`, and timestamp polling for feed refresh
  - adapted: `/api/feed/latest-ts` now preserves current feed filters; aggregation
    env parsing is clamped and tolerant of invalid values; tests use dynamic
    timestamps instead of a fixed current-date fixture
  - not adopted as-is: wholesale `app.py`, `db.py`, and templates because they
    would overwrite already validated Phase 2A behavior or reduce compatibility
    with the existing design system

## Validation

Latest local test run:

```text
.venv/bin/python -m pytest -q
125 passed in 0.75s
```

Route count check:

```text
14 dashboard routes:
/
/item/{message_id}
/telegram-status
/system
/analyze
/analyze/preview
/analyze/generate-prompt
/analyze/save-answer
/analyze/history
/analyze/{run_id}
/analyze/{run_id}/delete
/api/feed/latest-ts
/aggregation
/healthz
```

Browser smoke checks passed for:

- `http://127.0.0.1:8765/`
- `http://127.0.0.1:8765/?keyword=美元&hours=24`
- `/aggregation`
- `/system`
- `/analyze`
- `/analyze/preview`
- `/analyze/generate-prompt`
- `/analyze/history`
- feed auto-refresh script presence and current filtered feed load
- `/api/feed/latest-ts`, including a keyword-filtered request
- `/docs` and `/openapi.json` returning 404

The smoke-test analysis run was deleted after verification, and
`analysis_runs` was empty afterward.

## Boundaries preserved

- Did not modify `jin10_monitor.py`.
- Did not extend the old `6330022` in-file dashboard fallback.
- Did not connect OpenAI, Anthropic, Claude, or any model API.
- Did not add an automatic model API dependency.
- Evidence builder reads local SQLite only.
- Evidence builder does not call Jin10 REST.
- Dashboard does not open WebSocket.
- Dashboard does not send Telegram.
- Dashboard does not implement retry, resend, or backfill actions.
- Business history DB remains readonly through `mode=ro` and `query_only`.
- Analysis results write only to `data/dashboard_analysis.sqlite3`.
- `delivery_log` remains the success-only Telegram dedupe authority.
- `telegram_delivery_status` remains diagnostic only.

## Known tradeoffs

- The analysis workflow currently accepts URL-encoded forms only. That is enough
  for Phase 2A and avoids a new `python-multipart` dependency.
- There is no screenshot upload route wired yet, although the analysis DB schema
  includes the `screenshots` table and helper.
- Prompt generation is manual copy/paste only; no streaming UI and no provider
  adapter is included.
- Evidence scoring is heuristic and local-only. It can miss market-moving
  context that is absent from the local history DB.
- `/analyze/preview` does not create the analysis DB; the DB is created on
  prompt generation, answer save, history, detail, or delete.
- Feed auto-refresh uses lightweight timestamp polling rather than HTMX/SSE. It
  preserves the current query string and reloads only when a newer matching
  local SQLite item appears.

## Next recommended step

Suggested next feature choices:

- Small polish with `GPT-5.5 中`:
  - improve `/analyze` empty/error states
  - add clearer prompt-copy affordance
  - add screenshots to README
  - add a readonly analysis DB health row on `/system`
- Heavier next phase with `GPT-5.5 高`:
  - Phase 2B provider adapter design
  - screenshot upload and attachment workflow
  - richer evidence packet with price/market overlays
  - analysis result editing/versioning

## Ready-to-paste next-session prompt

```text
请继续 /Users/rich/jin10-monitor 项目。

建议模型：GPT-5.5 中，除非要做 Phase 2B provider adapter 或截图/行情增强，再用 GPT-5.5 高。

先读取：
1. /Users/rich/jin10-monitor/AGENTS.md
2. /Users/rich/jin10-monitor/docs/status/035-2026-05-24-dashboard-phase2a-handoff.md
3. /Users/rich/jin10-monitor/docs/design/002-dashboard-ai-full-spec.md

先执行：
git branch --show-current
git status
git pull --rebase
git log --oneline -8

当前结论：
- Phase 2A 手工 AI 分析流已在 bd303ae commit/push。
- Phase 2A follow-up polish/bugfix 已完成，最新 commit 应包含 `fix(dashboard): polish phase 2a dashboard`。
- 不修改 jin10_monitor.py。
- 不继续扩展旧 6330022 in-file dashboard。
- 不接 Claude / Anthropic / OpenAI 等模型 API 作为 Phase 2A 前置依赖。
- Evidence builder 默认只读本地 SQLite，不请求金十 REST。
- 分析结果只写 data/dashboard_analysis.sqlite3，不写业务历史库。

下一步：
先确认 `git status` 干净、`git pull --rebase` 无新冲突，再按需要选择下一阶段。
```
