# 037 - Dashboard Phase 3 spec handoff

Date: 2026-05-25

## Current state

The latest local commit prepared by this handoff is:

```text
4726a97 docs(dashboard): define phase 2b and phase 3 plan
```

Before starting this handoff, the latest pushed dashboard UX commit was:

```text
7b190c4 feat(dashboard): improve analysis timing and news rendering
```

This handoff records the Phase 2B / Phase 3 planning checkpoint after reviewing
the `phase 2a function 2&4&5.zip` proposal.

## Zip review result

The zip contained six files:

- `manual_ai.py`
- `analyze.html`
- `analyze_run.html`
- `base.html`
- `feed.html`
- `item.html`

The current repository implementation is already more complete for most of
these files. Direct replacement would regress the current UX in several places:

- `manual_ai.py`: would revert friendlier timestamp-based news links back toward
  raw `[#news_id]` style labels.
- `analyze.html`: would replace the cleaner `data-minutes` quick-window
  controls with more inline JavaScript.
- `analyze_run.html`: would reduce the evidence sidebar from
  time + headline/content + relevance to a thinner ID/time display.
- `base.html`: would remove or rewrite existing shared news and datetime styles.
- `feed.html` and `item.html`: the message-rendering approach was not better
  than the current Jin10-style renderer.

Only one useful behavior was adopted:

- image thumbnails now hide themselves if `pic_url` is dead or fails to load
  (`onerror="this.closest('a').style.display='none'"`)

## What changed

### 1. Phase 2B / Phase 3 spec

Added:

```text
docs/design/003-phase2b-phase3-spec.md
```

The spec freezes the next dashboard plan:

1. Phase 3A: Telegram `/item/{id}` deep links through `DASHBOARD_URL`
2. Phase 3B: feed infinite loading with safe caps
3. Phase 3C: screenshot upload with manual chart context
4. confidence tooltip explaining that model confidence is subjective
5. Phase 2B provider adapter for optional LLM API usage
6. Vision recognition after provider/API keys are available
7. market data overlay for item timelines

### 2. Image fallback

Updated:

- `dashboard/templates/feed.html`
- `dashboard/templates/item.html`

If a Jin10 image URL fails, the broken thumbnail link is hidden instead of
leaving a broken image in the feed or item detail page.

### 3. Changelog

Updated:

- `CHANGELOG.md`

The changelog now records the new 003 spec and its planned boundaries.

## Validation

Latest validation:

```text
.venv/bin/python -m pytest -q
128 passed

git diff --check
no output

curl -s -o /tmp/jin10_root.html -w "%{http_code}" http://127.0.0.1:8765/
200

curl -s -o /tmp/jin10_analyze.html -w "%{http_code}" http://127.0.0.1:8765/analyze
200
```

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

## Next recommended work

Recommended next sequence:

1. Push the local planning commit if it has not already been pushed.
2. Phase 3A: add Telegram `/item/{id}` deep links.
3. Phase 3B: add feed infinite loading with:
   - initial page: 50 rows
   - each append: 30 rows
   - automatic cap: 500 rows
4. Phase 3C: add screenshot upload and manual chart description.
5. Add confidence tooltip to analysis results.
6. Phase 2B provider adapter only after API keys are available.

Suggested model:

- GPT-5.5 高 for Phase 3A because it touches Telegram message formatting.
- GPT-5.5 中 is enough for feed infinite loading and confidence tooltip after
  Phase 3A is committed.

## Ready-to-paste next-session prompt

```text
请继续 /Users/rich/jin10-monitor 项目。

建议模型：GPT-5.5 高，如果要做 Phase 3A Telegram /item/{id} 深链；如果只是做快讯流无限加载或置信度 tooltip，用 GPT-5.5 中即可。

先读取：
1. /Users/rich/jin10-monitor/AGENTS.md
2. /Users/rich/jin10-monitor/docs/status/037-2026-05-25-dashboard-phase3-spec-handoff.md
3. /Users/rich/jin10-monitor/docs/design/003-phase2b-phase3-spec.md
4. /Users/rich/jin10-monitor/docs/design/002-dashboard-ai-full-spec.md

先执行：
git branch --show-current
git status
git pull --rebase
git log --oneline -8

当前结论：
- Phase 1 和 Phase 2A Dashboard 已完成。
- 当前正式入口是 run_dashboard.py + dashboard/。
- 不继续扩展旧 jin10_monitor.py 内置 dashboard。
- Phase 2A 手工 AI 分析流已完成：本地 SQLite evidence packet + ChatGPT/Claude 手工复制粘贴 + 独立分析库保存。
- 003 Phase 2B / Phase 3 规格已新增。
- phase 2a function 2&4&5.zip 已评估，除图片死链兜底外，其余实现相对当前 repo 都是回退或低收益替代，未采用。
- 不接模型 API，不请求金十 REST，不写业务历史库。

下一步：
优先做 Phase 3A：Telegram 消息附 /item/{id} 深链。按 003 spec 实现 DASHBOARD_URL 环境变量；为空时 Telegram 文本保持当前行为不变。先给计划，确认后小步修改、测试、更新 CHANGELOG、提交推送。
```
