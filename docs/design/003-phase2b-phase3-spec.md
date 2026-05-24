# Dashboard Phase 2B / Phase 3 Spec

Date: 2026-05-25

## 1. Purpose

This document freezes the next dashboard development boundary after Phase 2A.
It extends `002-dashboard-ai-full-spec.md` without replacing it.

Phase 2A is complete:

- standalone FastAPI/Jinja2 dashboard
- local readonly evidence packet builder
- manual ChatGPT Business / Custom GPT prompt flow
- isolated `data/dashboard_analysis.sqlite3`
- analysis history and traceable `/item/{id}` links

The next work must keep the same safety posture:

- dashboard remains a local sidecar tool
- business history DB remains readonly
- manual AI flow remains available
- model APIs are optional adapters, not startup requirements
- Telegram semantics are protected

## 2. Global Boundaries

Always preserve:

- no business-history writes from dashboard code
- no dashboard-triggered Jin10 REST catch-up
- no dashboard-triggered WebSocket connection
- no dashboard-triggered Telegram resend or retry
- no provider API key as a requirement for opening dashboard pages
- no deletion or weakening of the manual copy/paste analysis flow

When a feature needs `jin10_monitor.py`, it must be isolated in its own commit
and must include before/after tests for unchanged default behavior.

## 3. Phase 3A - Telegram Dashboard Deep Links

### Goal

Every Telegram push can optionally include a local dashboard link back to the
original news detail page:

```text
http://127.0.0.1:8765/item/{news_id}
```

### Configuration

Add optional environment variable:

```text
DASHBOARD_URL=http://127.0.0.1:8765
```

Rules:

- empty or unset `DASHBOARD_URL`: Telegram message text must remain unchanged
- set `DASHBOARD_URL`: append a dashboard link to the message
- trim trailing slash before appending `/item/{id}`
- do not change Telegram dedupe keys
- do not change `delivery_log`
- do not add callback receiver or inbound Telegram handling

### Implementation Scope

Likely files:

- `jin10_monitor.py`
- `.env.example`
- `README.md`
- tests covering `format_message()`

### Acceptance

- tests prove default formatted messages are unchanged when `DASHBOARD_URL` is
  unset
- tests prove configured URL appends one `/item/{id}` link
- no send/retry/backfill behavior changes

## 4. Phase 3B - Feed Infinite Loading

### Goal

The feed should load fast on first render and allow reading more history without
manual page reloads.

This is a single-column timeline/infinite loading feature, not a multi-column
masonry layout.

### Recommended UX

- first page: 50 items
- automatic append: 30 items per request
- automatic cap: 500 visible items
- after cap: show a manual "load more" action or stop with a clear label
- preserve current filters: priority, keyword, hours, Telegram sent only, status

### Backend

Add a readonly endpoint:

```text
GET /api/feed/page?offset=N&limit=30&...
```

Options:

- return HTML fragments rendered by a small row partial
- or return JSON and render client-side

Prefer an HTML partial if it keeps styling consistent with Jinja templates and
avoids duplicating rendering rules in JavaScript.

### Load and Pressure

Expected pressure is low:

- readonly SQLite
- bounded `LIMIT/OFFSET`
- local-only dashboard

Mitigations:

- cap `limit` to 50
- cap total auto-loaded rows to 500
- reuse existing filter normalization
- avoid polling and infinite loading fighting each other; auto-refresh should
  not reload while a pagination request is in progress

### Acceptance

- initial page still works without JavaScript
- scroll appends more rows
- filters are preserved
- no writes to business DB
- no network calls beyond local dashboard

## 5. Phase 3C - Screenshot Upload with Manual Description

### Goal

Allow users to attach a chart screenshot to an analysis run and manually describe
what the chart shows.

This does not require a model API.

### Current Asset

The analysis database already has:

```text
screenshots(id, file_path, original_filename, user_description, uploaded_at)
```

and helper code for saving screenshots.

### Recommended UX

In `/analyze`:

- file picker for image upload
- small preview
- text field for manual description
- description is appended to `user_context`
- saved screenshot can be linked from the analysis run

### Boundaries

- store files under `data/screenshots/`
- accept image MIME types only
- enforce a size cap, suggested 8 MB
- do not send images to any external API in Phase 3C
- manual description is the authoritative chart context until Vision exists

### Acceptance

- upload succeeds without API keys
- screenshot is saved outside business history DB
- deleting analysis history does not delete business news
- prompt includes user-supplied chart description

## 6. Confidence Tooltip

### Goal

Make clear that model confidence is a subjective estimate, not a trading signal
or statistical probability.

### Suggested UI Copy

```text
置信度是模型基于证据充分度、时间吻合度和因果链条清晰度给出的主观估计，不是交易信号。
≥75% 较可信；50-75% 仅供参考；<50% 证据不足。
```

### Placement

- `/analyze/{run_id}` next to overall confidence
- catalyst-level confidence hover/help text
- optionally `/analyze/history` column header

### Acceptance

- users can see the explanation without leaving the analysis page
- no schema change
- no provider dependency

## 7. Phase 2B - LLM Provider Adapter

### Goal

Add optional automatic model calls while keeping the manual copy/paste flow as a
permanent fallback.

### Provider Interface

Suggested structure:

```text
dashboard/providers/
├── __init__.py
├── base.py
├── openai_provider.py
└── anthropic_provider.py
```

Base interface:

```python
class AnalysisProvider:
    name: str

    def available(self) -> bool:
        ...

    async def analyze(self, prompt: str, *, attachments: list[Path] | None = None) -> ProviderResult:
        ...
```

Provider result:

```python
@dataclass
class ProviderResult:
    model_label: str
    raw_text: str
    usage: dict[str, object]
```

### Rules

- no API key: provider unavailable, manual flow still works
- provider failure: show error and keep generated prompt visible
- save provider result through the same `save_answer()` path
- `analysis_runs.model_label` records actual model
- do not change evidence builder boundaries
- do not send screenshots unless the selected provider explicitly supports
  Vision and user opts in

### Acceptance

- manual flow works with no provider packages or keys
- automatic path can be disabled
- provider errors do not lose prompt or evidence packet
- tests cover unavailable-provider fallback

## 8. Vision Recognition

### Goal

Automatically interpret uploaded chart screenshots when a Vision provider is
available.

### Requirement

Reliable chart interpretation needs a vision-capable model. Local OCR is not
enough for:

- symbol detection
- time-axis interpretation
- price-axis interpretation
- K-line movement
- timeframe and exchange context

### Output

Vision should return structured chart context:

```json
{
  "symbol": "ETH/USDT",
  "timeframe": "1h",
  "approx_window": "2026-05-24 21:30 - 22:00",
  "price_move": "2480 -> 2515",
  "trend": "up",
  "uncertainties": ["exchange not visible"]
}
```

The recognized text should enter `user_context`, not overwrite user input.

## 9. Market Data Overlay

### Goal

Show minute-level market context beside news context on `/item/{id}` and later
inside evidence packets.

### Candidate Sources

- Binance public REST for crypto pairs
- other market APIs later, if needed

### Boundaries

- market data is read-only
- cache responses locally or in memory to avoid repeated calls
- dashboard should work when market API is unavailable
- do not make market data a prerequisite for evidence packet generation

### Acceptance

- `/item/{id}` can show a small nearby price timeline
- failures degrade to "market data unavailable"
- no business DB writes unless a separate cache design is approved

## 10. Recommended Order

1. Phase 3A: Telegram dashboard deep links
2. Phase 3B: feed infinite loading
3. Phase 3C: screenshot upload with manual description
4. Confidence tooltip
5. Phase 2B provider adapter
6. Vision recognition
7. Market data overlay

Reasoning:

- Telegram links have the highest daily usefulness but touch Telegram formatting,
  so they need `GPT-5.5 高`.
- Infinite loading and screenshot upload are local dashboard features with no
  API dependency.
- Confidence tooltip is small and can be bundled with analysis UI polish.
- Provider and Vision work should wait until API keys and provider preference
  are clear.
- Market data overlay is useful, but it introduces external data reliability and
  caching questions.

## 11. Testing Strategy

Every phase must include:

- focused no-network unit tests where possible
- browser smoke for changed dashboard pages
- `git diff --check`
- full `pytest` before commit

For Telegram changes specifically:

- tests for default no-`DASHBOARD_URL` formatting
- tests for configured dashboard links
- no Telegram send in tests
- no changes to delivery dedupe semantics
