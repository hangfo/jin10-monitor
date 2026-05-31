# 039 - Realtime ingest recovery and Dashboard V2 handoff

Date: 2026-05-31

## Current state

Latest pushed commit:

```text
26b7d7e feat(dashboard): add compare analysis and resilient realtime ingest
```

Branch state after push:

```text
main...origin/main
```

The standalone Dashboard entry remains:

```text
run_dashboard.py + dashboard/
```

Do not resume work by extending the old `jin10_monitor.py --dashboard`
prototype.

## What this session completed

This session finished two tracks:

1. Dashboard V2 second-round features
2. Realtime ingest / Telegram incident diagnosis and hardening

The code was committed and pushed in:

```text
26b7d7e feat(dashboard): add compare analysis and resilient realtime ingest
```

## Dashboard V2 additions

Added analysis comparison:

- `GET /analyze/compare`
- `dashboard/templates/analyze_compare.html`
- `analysis_db.get_runs_for_compare()`
- history page two-run checkbox selection
- run detail shortcuts for re-analysis and comparison

Added adapter boundaries:

- `dashboard/providers/` for future Phase 2B LLM providers
- OpenAI and Anthropic provider stubs that only check env configuration
- `dashboard/market/` for future price overlay adapters
- `GET /api/market/klines` placeholder that returns an empty fallback when no
  market adapter is configured

Added UI/status polish:

- system page provider status panel
- `.pill.normal`, `tr.row-normal`, and `tr.row-none` CSS completion
- navigation link for comparison

## Incident diagnosis

Observed user symptoms:

- Telegram stopped pushing after prior successful messages.
- Dashboard showed repeated Telegram timeout statuses.
- Dashboard latest news lagged behind Jin10 website.
- The Jin10 website had the latest Hezbollah item, while dashboard did not show
  it until the monitor was restarted.

Findings:

- Telegram bot token and chat id were valid.
- Telegram API was reachable:
  - `getMe`: HTTP 200
  - `getChat`: HTTP 200
  - `sendChatAction`: HTTP 200
  - live diagnostic `sendMessage`: `sent`
- Jin10 REST endpoint returned persistent 403 for all configured app ids and
  modes:
  - channel + app id 1: 403
  - channel + app id 2: 403
  - legacy + app id 1: 403
  - legacy + app id 2: 403
- Jin10 WebSocket was reachable, but the running monitor had entered a likely
  half-open connection state: process was alive, REST was looping, but WebSocket
  was not producing new history rows.

Conclusion:

- Telegram was not broken by dashboard code.
- REST 403 is an external access-policy / endpoint-compatibility problem.
- The dashboard lag was caused by REST being blocked plus WebSocket not
  reconnecting after going idle or half-open.

## Realtime hardening merged

`jin10_monitor.py` changes:

- added `WS_IDLE_TIMEOUT`
- WebSocket receive loop now uses an application-level idle timeout and
  reconnects when no messages arrive for the configured window
- added `REST_FORBIDDEN_BACKOFF_SECONDS`
- `poll_once()` now backs off after all REST entries return 403
- repeated 403 logs are summarized instead of emitted every few seconds
- WebSocket remains the realtime primary path while REST is blocked

Tests:

- added `test_poll_once_backs_off_after_all_rest_entries_return_403`

Operational actions:

- launchd service was reloaded after the code change
- dashboard server remained available at `http://127.0.0.1:8765`

## Current runtime evidence

After reload, WebSocket ingestion resumed:

```text
2026-05-31 13:31:34 | ws | 据韩联社：韩国与日本在国防会谈中讨论双边军事后勤支持协议。
2026-05-31 13:36:05 | ws | 国家数据局局长刘烈宏：高质量数据集是人工智能发展的核心基础
```

Telegram realtime delivery also resumed:

```text
20260531133134591800 | realtime | sent
20260531133605275800 | realtime | sent
```

The previously missing website item was recovered through WebSocket initial
history:

```text
2026-05-31 13:08:16 | ws_initial | 黎真主党称对以军发起多轮打击
```

REST is still blocked:

```text
REST 连续被 403 拒绝：4/4 个入口不可用，暂停 REST ...
```

That means realtime WebSocket is working, Telegram is working, but REST-based
catch-up remains degraded until a new REST-compatible source or request strategy
is chosen.

## Validation

Automated validation:

```text
.venv/bin/python -m pytest -q
145 passed in 0.79s

git diff --check
no output
```

Browser validation:

- dashboard feed loads at `http://127.0.0.1:8765/`
- the Hezbollah item appears in the feed after refresh
- `/analyze/history`, `/analyze/compare`, `/system`, and
  `/api/market/klines` were smoke-tested before commit

Git validation:

```text
git status --short --branch
## main...origin/main

git rev-parse HEAD
26b7d7ee9ad8c78e73df358dd1dc6a157ea10eaa

git rev-parse origin/main
26b7d7ee9ad8c78e73df358dd1dc6a157ea10eaa
```

## Important boundaries

Keep these boundaries:

- Do not continue extending the old `jin10_monitor.py --dashboard` prototype.
- Do not request Jin10 REST from dashboard pages.
- Do not write analysis output to the business history DB.
- Do not retry Telegram `unknown_timeout` rows automatically; preserve the
  success-only dedupe semantics.
- Do not make dashboard startup depend on OpenAI, Anthropic, market data, or any
  external API.

## Recommended next progress sequence

Recommended next step: build a runtime diagnostics panel before new feature
work.

Reason:

- The most recent problem was not a missing UI feature; it was observability.
- The system already had the data to diagnose it, but it required shell/log/SQL
  inspection.
- A system page panel can make the next incident immediately visible:
  - latest `ws` / `ws_initial` / `rest` row time
  - latest `last_ingested_at`
  - latest Telegram `sent`, `unknown_timeout`, and `failed`
  - REST 403 backoff state if persisted or inferable from recent logs/status
  - catch-up health and last summary status

Suggested implementation shape:

1. Add read-only dashboard DB helper(s) for runtime health.
2. Add a compact `/system` "Realtime pipeline" panel.
3. Keep it local and SQLite/log-derived.
4. Do not add active retry buttons yet.
5. Add focused tests for the helper output.

After that:

1. If REST remains 403, evaluate a catch-up source replacement.
2. Then continue optional market overlay UI / adapter work.
3. Provider Adapter should wait until runtime health is clearer, because manual
   analysis flow already works and provider calls add credentials, cost,
   timeout, and error boundaries.

## Suggested model choice

- GPT-5.5 中: system status panel, handoff docs, small dashboard UI, comparison
  polish, read-only diagnostics.
- GPT-5.5 高: REST replacement research, provider streaming, credential/error
  boundaries, or complex market-data normalization/caching.

## Ready-to-paste next-session prompt

```text
请继续 /Users/rich/jin10-monitor 项目。

建议模型：GPT-5.5 中，如果先做系统状态页增强、只读诊断面板或小型 Dashboard UI；GPT-5.5 高，如果要重新适配金十 REST/补拉源、做复杂行情 adapter，或开始 Phase 2B Provider Adapter。

先读取：
1. /Users/rich/jin10-monitor/AGENTS.md
2. /Users/rich/jin10-monitor/docs/status/039-2026-05-31-realtime-ingest-dashboard-v2-handoff.md
3. /Users/rich/jin10-monitor/docs/status/038-2026-05-29-dashboard-v2-bugfix-plan-handoff.md
4. /Users/rich/jin10-monitor/docs/design/004-dashboard-v2-plan.md
5. /Users/rich/jin10-monitor/docs/design/003-phase2b-phase3-spec.md
6. /Users/rich/jin10-monitor/docs/design/002-dashboard-ai-full-spec.md

先执行：
git branch --show-current
git status
git pull --rebase
git log --oneline -8

当前结论：
- Phase 1、Phase 2A、Phase 3A/3B/3C 已完成并推送。
- 当前正式入口是 run_dashboard.py + dashboard/。
- 不继续扩展旧 jin10_monitor.py 内置 dashboard。
- 最新提交是 26b7d7e feat(dashboard): add compare analysis and resilient realtime ingest。
- Dashboard V2 第二轮已完成：/analyze/compare、history 双选对比、Provider Adapter 骨架、Market Adapter 边界、/api/market/klines 占位、system provider 状态。
- 本轮已修复实时采集韧性：WebSocket idle watchdog、REST 403 退避汇总、launchd reload。
- 当前运行证据：WebSocket 已恢复入库，13:31 和 13:36 实时消息 Telegram 状态为 sent。
- REST 仍持续 403，这是外部 REST 接口拒绝当前请求方式；补拉/补拉摘要仍处于 REST 依赖降级状态。
- 不接模型 API，不请求金十 REST from dashboard，不写业务历史库，不自动重发 Telegram unknown_timeout。

下一步建议：
优先做 /system 运行诊断面板增强：展示 WebSocket 最近入库、REST 最近状态/403 退避、Telegram 最近 sent/timeout/failed、catch-up 最近状态。先做只读诊断，不做重试按钮。完成后再评估 REST 长期 403 下是否需要补拉源替代；行情叠加和 Provider Adapter 排在稳定性可视化之后。
```
