# 038 - Dashboard V2 bugfix and plan handoff

Date: 2026-05-29

## Current state

Latest pushed commit:

```text
304929a fix(dashboard): polish feed bugs and v2 plan
```

Branch state after push:

```text
main...origin/main
```

The standalone Dashboard entry remains:

```text
run_dashboard.py + dashboard/
```

Do not resume work by extending the old `jin10_monitor.py --dashboard` prototype.

## What this session completed

Reviewed two proposal bundles:

- `phase 2a:b:c bug fix和dashaboard v2计划（v1).zip`
- `phase 2a:b:c bug fix（v2).zip`

Final verdict:

- v2 is the better code baseline.
- v1's unique value is the Dashboard V2 planning HTML.
- The HTML plan was not added as an app route because it would create a second
  maintenance surface and included stale wording.
- Its useful roadmap content was distilled into:

```text
docs/design/004-dashboard-v2-plan.md
```

## Bugfixes merged

Dashboard feed and analysis UI:

- removed `style_flags` from feed rendering
- hid empty messages where both `title` and `content` are blank
- fixed duplicate body rendering when `has_title=0`
- truncated feed timestamps to minute precision
- added a visible `补拉` label for `catchup_auto` / `catchup_manual`
- localized Telegram status labels in the feed
- localized LLM direction labels as catalyst semantics:
  - `▲ 偏利多`
  - `▼ 偏利空`
  - `◆ 多空混合`
- added global `box-sizing: border-box`
- fixed analysis form grid overflow with `min-width: 0`

Ordering and upload safety:

- changed same-second feed and context tie-breaker from `created_at` to Jin10
  message `id`
- added `normalize_news_text()` for stable whitespace-insensitive title/content
  comparison
- screenshot upload now checks `Content-Length` before reading the body when
  possible
- screenshot MIME is limited to `png/jpeg/webp/gif`
- screenshot upload 500 errors no longer echo raw exception text

## Files changed in commit 304929a

- `CHANGELOG.md`
- `dashboard/app.py`
- `dashboard/db.py`
- `dashboard/manual_ai.py`
- `dashboard/templates/_feed_rows.html`
- `dashboard/templates/analyze.html`
- `dashboard/templates/analyze_run.html`
- `dashboard/templates/base.html`
- `tests/test_dashboard_analysis.py`
- `tests/test_dashboard_db.py`
- `docs/design/004-dashboard-v2-plan.md`

## Validation

Automated validation:

```text
.venv/bin/python -m pytest -q
139 passed in 0.55s

git diff --check
no output
```

Browser / local server smoke:

- server restarted on `http://127.0.0.1:8765`
- `/` renders with no visible `style_flags`
- feed status labels render in Chinese
- feed timestamp length is 16 characters (`YYYY-MM-DD HH:MM`)
- `#feed-sentinel` exists for infinite loading
- `/api/feed/page?offset=50&limit=2` returns rows and `has_more=true`
- `/analyze` renders with screenshot upload controls
- analysis grid does not overflow its container
- SVG screenshot upload is rejected
- oversized `Content-Length` is rejected before body parsing

## Relationship between 003 and 004

`003-phase2b-phase3-spec.md` is the original Phase 2B / Phase 3 specification.
It defined what to build next:

- Phase 3A Telegram `/item/{id}` links
- Phase 3B feed infinite loading
- Phase 3C screenshot upload
- confidence tooltip
- later Provider Adapter
- later Vision
- later market overlay

`004-dashboard-v2-plan.md` does not replace `003`; it updates the roadmap after
Phase 3A/3B/3C were completed and after the v1/v2 bugfix bundles were reviewed.
The main differences are:

- `004` records which v1/v2 bundle ideas were accepted or rejected.
- `004` treats Phase 3 as complete and moves the project into V2 planning.
- `004` sharpens bugfix decisions that `003` did not cover:
  - hide empty messages only in dashboard rendering, not monitor ingestion
  - use Jin10 `id` rather than `created_at` as same-second tie-breaker
  - use catalyst direction wording rather than prediction wording
  - harden screenshot upload MIME and size handling
- `004` softens the market overlay plan from a concrete Binance-first feature
  into an optional market adapter boundary, because dashboard startup should not
  depend on any external market-data API.
- `004` makes the next sequence clearer:
  - stabilization and summary
  - analysis comparison
  - optional market overlay
  - Phase 2B Provider Adapter
  - Vision only after provider/API setup is stable

## Recommended next progress sequence

Recommended order:

1. Stabilization closeout
   - keep current `304929a` as the Phase 3 + V2 bugfix baseline
   - keep the local dashboard server running only for manual inspection
   - avoid adding new feature code before the next scope is chosen

2. Analysis comparison, no external API
   - add `/analyze/compare` or a history-page compare mode
   - select two existing analysis runs
   - compare judgement, confidence, selected catalysts, missing evidence, and
     referenced news
   - this uses only `dashboard_analysis.sqlite3`

3. Market overlay adapter, optional and bounded
   - define a small `dashboard/market/` interface before choosing a data source
   - only fetch when the user opens a relevant item or explicitly requests it
   - do not call Jin10 REST
   - do not make dashboard startup depend on network access

4. Phase 2B Provider Adapter
   - define `dashboard/providers/`
   - keep manual copy/paste flow as the default fallback
   - no provider key should be required for opening dashboard pages
   - write provider results only to the isolated analysis DB

5. Vision recognition
   - only after Provider Adapter is stable and API key choice is clear
   - use Vision to suggest structured `user_context`
   - never overwrite the user's manual screenshot description automatically

## Adapter vs market overlay recommendation

Recommended next feature: analysis comparison first, then market overlay, then
Provider Adapter.

If choosing strictly between Provider Adapter and market overlay, prefer market
overlay first.

Reasoning:

- Provider Adapter introduces external model credentials, provider-specific
  errors, cost/rate-limit behavior, and streaming or timeout design. It is a
  larger architectural boundary.
- The current manual ChatGPT/Claude flow already works and remains acceptable
  for the user's workflow, so Provider Adapter is not blocking value.
- Market overlay can be built as a read-only, optional, user-triggered adapter
  that improves evidence interpretation without changing the AI flow.
- A well-designed market adapter also benefits later Provider Adapter and Vision
  work, because price context can become another evidence input.

Do not start with market overlay as a hardcoded Binance feature. Start by
freezing the local interface and fallback behavior, then choose the first data
source deliberately.

## Suggested model choice

- GPT-5.5 中: summary docs, diff review, analysis comparison, small dashboard UI
  improvements.
- GPT-5.5 高: Provider Adapter, streaming model calls, credential/error boundary,
  or a market adapter if it expands into multi-source caching and normalization.

## Ready-to-paste next-session prompt

```text
请继续 /Users/rich/jin10-monitor 项目。

建议模型：GPT-5.5 中，如果先做分析对比或小型 Dashboard V2 UI；GPT-5.5 高，如果要做 Phase 2B Provider Adapter、外部模型调用边界，或复杂行情 adapter。

先读取：
1. /Users/rich/jin10-monitor/AGENTS.md
2. /Users/rich/jin10-monitor/docs/status/038-2026-05-29-dashboard-v2-bugfix-plan-handoff.md
3. /Users/rich/jin10-monitor/docs/design/004-dashboard-v2-plan.md
4. /Users/rich/jin10-monitor/docs/design/003-phase2b-phase3-spec.md
5. /Users/rich/jin10-monitor/docs/design/002-dashboard-ai-full-spec.md

先执行：
git branch --show-current
git status
git pull --rebase
git log --oneline -8

当前结论：
- Phase 1、Phase 2A、Phase 3A/3B/3C 已完成并推送。
- 当前正式入口是 run_dashboard.py + dashboard/。
- 不继续扩展旧 jin10_monitor.py 内置 dashboard。
- 最新提交是 304929a fix(dashboard): polish feed bugs and v2 plan。
- 004 Dashboard V2 计划已新增：v2 补丁作为修复基线，v1 HTML 计划仅吸收为 Markdown 设计文档。
- 已修复 style_flags 外露、空消息纯数字行、正文重复、同秒排序、截图上传安全、方向标签语义、分析页溢出。
- 不接模型 API，不请求金十 REST，不写业务历史库，不触发 Telegram 重发。

下一步建议：
先做无外部 API 的分析对比功能，或先设计 market adapter 的最小边界；如果必须在 Provider Adapter 和行情叠加二选一，优先做行情叠加的 adapter 边界，不要先硬编码 Binance，也不要让 dashboard 启动依赖网络。
```
