# 036 - Dashboard UX polish and Phase 3 planning handoff

Date: 2026-05-24

## Current state

The latest pushed commit before this handoff is:

```text
7c39fc8 fix(dashboard): polish analyze and item templates
```

This handoff records the next dashboard UX batch prepared for:

```text
feat(dashboard): improve analysis timing and news rendering
```

The batch keeps the standalone dashboard architecture from Phase 1/2A:

- `run_dashboard.py` remains the dashboard entrypoint.
- `jin10_monitor.py` is not modified.
- The business history DB remains readonly.
- No model API, Jin10 REST, WebSocket, Telegram send, retry, resend, or backfill
  action is introduced.

## What was implemented

### 1. Analyze time-window UX

The `/analyze` input form now uses native browser `datetime-local` controls for
`window_start` and `window_end`.

Quick window buttons were added:

- past 5 minutes
- past 15 minutes
- past 30 minutes
- past 1 hour
- past 4 hours

When `/analyze` is opened without a prefilled item window, the form defaults to
the past 30 minutes. When opened from `/item/{id}`, the existing prefilled
window is preserved.

Backend normalization converts browser values such as:

```text
2026-05-24T21:30
```

to the existing dashboard format:

```text
2026-05-24 21:30:00
```

### 2. Jin10-like news rendering

The feed and item detail pages now render local news rows using the style
signals already stored in `flash_history`:

- `important`
- `has_title`
- `has_bold`
- `has_pic`
- `pic_url`
- `source_url`
- `style_flags`

Important news is rendered in red, titled news gets a stronger headline,
`has_bold` controls bold body text, images render as lazy-loaded thumbnails, and
source links stay clickable.

Compatibility with older history DB schemas is preserved: `has_title` and
`style_flags` are selected through the existing optional-column helper and fall
back to empty values if absent.

### 3. Analysis result readability

Analysis detail rendering now reduces raw `news_id` noise:

- catalyst entries show a timestamp label such as `05-23 09:30`
- `[#news_id]` links render as friendlier `[↗ 05-23 09:30]` labels
- full `news_id` is preserved in the link target and hover title
- the evidence sidebar shows time + headline/content summary first, with the
  raw ID de-emphasized underneath

`analysis_db.get_run()` enriches evidence rows from the stored evidence packet
so the template can show `published_at`, title/content, priority, and source
without querying or writing the business DB.

### 4. Draft status style

`.pill.none` was added to the shared CSS so draft analysis records are styled
instead of appearing as plain white pills.

## Feature assessment

### Feed infinite loading

Feasible and low pressure. The right interpretation is not masonry layout, but
single-column infinite loading. A safe implementation would add a readonly JSON
or HTML-fragment endpoint using `LIMIT/OFFSET`.

Recommended limits:

- initial page: 50
- each load: 30
- automatic cap: 500
- after 500: show a manual "load more" action instead of automatic triggering

This should be Phase 3B, after the current UX batch is committed.

### Screenshot recognition

Two-step path:

- no API: upload screenshot and let the user provide manual context; store the
  screenshot locally and include the text description in the prompt
- with API: add Vision recognition through a provider adapter

Reliable automatic recognition of chart symbols, time axes, price axes, and K
line structure needs a vision-capable model. Local OCR alone is not reliable
enough for this use case.

Recommended placement: screenshot upload can be Phase 3C; automatic recognition
belongs after Phase 2B provider adapter work.

### Confidence explanation

The confidence value is a model self-assessment, not a statistical probability.

Suggested UI copy for a later small patch:

```text
置信度是模型基于证据充分度、时间吻合度和因果链条清晰度给出的主观估计，不是交易信号。
≥75% 较可信；50-75% 仅供参考；<50% 证据不足。
```

## Validation

Latest validation before handoff:

```text
.venv/bin/python -m pytest tests/test_dashboard_db.py tests/test_dashboard_analysis.py -q
33 passed

.venv/bin/python -m pytest -q
128 passed

git diff --check
no output
```

Browser smoke checks passed for:

- `/analyze`
- `/`
- `/item/{id}`
- `/analyze/history`

## Boundaries preserved

- Did not modify `jin10_monitor.py`.
- Did not modify launchd config.
- Did not add dependencies.
- Did not add `python-multipart`.
- Did not connect any model API.
- Did not call Jin10 REST or market-data APIs.
- Did not send Telegram.
- Did not write the business history DB.
- Analysis writes remain isolated to `data/dashboard_analysis.sqlite3`.

## Remaining work

Recommended sequence:

1. Commit and push this UX batch:

```text
feat(dashboard): improve analysis timing and news rendering
```

2. Write `docs/design/003-phase2b-phase3-spec.md` to freeze:
   - Telegram `/item/{id}` deep links
   - screenshot upload boundaries
   - market data overlay boundaries
   - LLM provider adapter interface

3. Phase 3A: Telegram message deep link with `DASHBOARD_URL`; when unset,
   Telegram message text must remain byte-for-byte equivalent to current output.

4. Phase 3B: feed infinite loading with safe caps.

5. Phase 3C: screenshot upload + manual chart description.

6. Phase 2B: provider adapter and optional Vision recognition after API keys are
   available.

## Ready-to-paste next-session prompt

```text
请继续 /Users/rich/jin10-monitor 项目。

建议模型：GPT-5.5 高，如果要改 Telegram 消息格式或写 003 spec；如果只是提交当前 dashboard UX 批次，用 GPT-5.5 中也可以。

先读取：
1. /Users/rich/jin10-monitor/AGENTS.md
2. /Users/rich/jin10-monitor/docs/status/036-2026-05-24-dashboard-ux-phase3-planning-handoff.md
3. /Users/rich/jin10-monitor/docs/design/002-dashboard-ai-full-spec.md

先执行：
git branch --show-current
git status
git pull --rebase
git log --oneline -8

当前结论：
- Phase 2A 已完成并推送。
- 当前 UX 批次实现了 /analyze 时间选择器、金十样式消息渲染、分析详情时间戳和 news_id 降噪。
- 仍不修改 jin10_monitor.py。
- 不接模型 API。
- 不写业务历史库。

下一步：
若当前 UX 批次已提交推送，优先写 003 Phase 2B/Phase 3 spec；若还未提交，先复查 diff、跑测试、浏览器 smoke，再提交推送。
```
