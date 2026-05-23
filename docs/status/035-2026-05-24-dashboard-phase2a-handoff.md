# 035 - Dashboard Phase 2A handoff

Date: 2026-05-24

## Current state

Phase 2A of the standalone FastAPI/Jinja2 dashboard is implemented locally but
not committed or pushed yet.

Current branch:

```text
main
```

Current local changes include:

- `CHANGELOG.md`
- `dashboard/app.py`
- `dashboard/db.py`
- `dashboard/analysis_db.py`
- `dashboard/evidence.py`
- `dashboard/manual_ai.py`
- `dashboard/templates/feed.html`
- `dashboard/templates/analyze.html`
- `dashboard/templates/analyze_run.html`
- `dashboard/templates/analyze_history.html`
- `dashboard/templates/base.html`
- `tests/test_dashboard_analysis.py`

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
  - the feed page auto-refreshes every 30 seconds, but skips refresh while the
    user is editing filter inputs or when the page is hidden
- Added focused tests for:
  - analysis DB roundtrip
  - cascade delete
  - analysis DB separation from business history DB
  - evidence scoring and `news_id` labeling
  - answer parsing and link rendering
  - `/analyze/history` route ordering before `/analyze/{run_id}`
  - configured keyword heatmap behavior
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

## Validation

Latest local test run:

```text
.venv/bin/python -m pytest -q
121 passed in 0.64s
```

Route count check:

```text
12 dashboard routes:
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
/healthz
```

Browser smoke checks passed for:

- `http://127.0.0.1:8765/`
- `http://127.0.0.1:8765/?keyword=美元&hours=24`
- `/analyze`
- `/analyze/preview`
- `/analyze/generate-prompt`
- `/analyze/history`
- feed auto-refresh script presence and current filtered feed load

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
- Feed auto-refresh is a simple full-page reload, not HTMX/SSE. It preserves the
  current query string and skips refresh while editing, but it is still a coarse
  refresh rather than a live incremental stream.

## Next recommended step

Before commit:

1. Review the current diff.
2. If accepted, keep the current `CHANGELOG.md` entry.
3. Commit and push as a single Phase 2A dashboard feature.

Suggested commit title:

```text
feat(dashboard): add manual analysis workflow
```

Suggested next feature choices after commit:

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
- Phase 2A 手工 AI 分析流已本地实现，但还未 commit/push。
- 不修改 jin10_monitor.py。
- 不继续扩展旧 6330022 in-file dashboard。
- 不接 Claude / Anthropic / OpenAI 等模型 API 作为 Phase 2A 前置依赖。
- Evidence builder 默认只读本地 SQLite，不请求金十 REST。
- 分析结果只写 data/dashboard_analysis.sqlite3，不写业务历史库。

下一步：
先复查 diff、运行 pytest、浏览器 smoke /analyze 和 /analyze/history。
如果确认可接受，准备 CHANGELOG 一致性、commit message，并等我确认后 commit/push。
```
