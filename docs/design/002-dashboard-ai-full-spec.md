# Jin10 Monitor Dashboard + AI 分析最终规格

更新时间：2026-05-22（Asia/Shanghai）

## 1. 文档定位

本文是 Dashboard 后续开发的 Phase 0 冻结文档，合并以下输入后形成最终执行口径：

- `/Users/rich/Downloads/002-dashboard-ai-full-spec.md`
- `/Users/rich/Downloads/jin10_dashboard_master_plan.html`
- `/Users/rich/Downloads/jin10_monitor_architecture_and_roadmap.svg`
- 已提交的只读 Dashboard MVP 原型：`6330022 feat(dashboard): add readonly local dashboard mvp`

后续实现以本文为准。旧 Dashboard MVP 原型保留，但不继续在 `jin10_monitor.py` 里扩展新 dashboard 功能。

## 2. 当前结论

### 2.1 已完成资产

`6330022` 已提供一个可运行的本地只读 Dashboard MVP 原型：

```bash
.venv/bin/python jin10_monitor.py --dashboard
```

默认访问：

```text
http://127.0.0.1:8765/
```

当前原型已经覆盖：

- 最近快讯流。
- 单条消息详情和前后上下文。
- Telegram 投递状态诊断。
- 聚合候选报告占位。
- 首页自动刷新和卡片点击。

### 2.2 原型定位

当前原型不需要 revert，原因是：

- 产品方向正确：本地、只读、可回看、可诊断。
- 安全边界正确：不触发 REST、WebSocket、补拉或 Telegram 发送。
- 可作为正式 dashboard 的交互参考和 fallback。

但它有架构债：实现位于 `jin10_monitor.py` 内。正式开发从 Phase 1 起切到独立 FastAPI/Jinja2 dashboard，不再把新页面、新 AI 功能或新分析存储塞进 `jin10_monitor.py`。

### 2.3 最终方向

正式 dashboard 是旁路本地工具：

- 采集和推送进程仍由 `jin10_monitor.py` 和 launchd 负责。
- Dashboard 只解释已经落库的事实。
- Dashboard 默认只监听 `127.0.0.1`。
- Dashboard 不写业务库，不触发补拉，不发送 Telegram。
- AI 分析先走 evidence packet + ChatGPT Business / Custom GPT 手工复制粘贴 + 回填保存。
- Anthropic / Claude API 不作为 P0 或 P1 前置依赖。

## 3. 目标和非目标

### 3.1 目标

Dashboard 要解决四类问题：

1. 最近有哪些重要快讯入库，哪些已推送 Telegram。
2. 某条消息前后 5/15/30/60 分钟发生了什么。
3. Telegram 投递状态、监控健康和本地库状态是否正常。
4. 某段行情是否可能由本地新闻催化，证据链是什么，缺什么证据。

### 3.2 非目标

P0/P1 不做：

- 不公网暴露。
- 不做用户系统。
- 不做 Telegram callback receiver。
- 不在页面里提供 Telegram 重试或补发按钮。
- 不触发 Jin10 REST 补拉。
- 不连接 Jin10 WebSocket。
- 不接管或重启 launchd 常驻监控进程。
- 不开启或放宽 AGGREGATION_V2 suppress 规则。
- 不把 Claude / Anthropic API 作为前置依赖。
- Phase 1 和 Phase 2A 不修改 `jin10_monitor.py`。

## 4. 技术选型

### 4.1 Web 框架

正式 dashboard 使用 FastAPI + Jinja2。

选择原因：

- Python 一栈，便于复用现有 SQLite 数据模型和解析函数。
- 比 Streamlit 更适合多页面、上传、局部刷新、SSE 和可点击证据引用。
- 比前端框架更轻，不需要 Next.js 或复杂构建链。
- 适合本地工具的低运维目标。

HTMX 可以在 Phase 2 或后续增强中引入，用于局部刷新、证据预览和流式体验，但不是 Phase 1 必需项。

### 4.2 启动方式

正式入口：

```bash
.venv/bin/python run_dashboard.py
```

默认监听：

```text
127.0.0.1:8765
```

`run_dashboard.py` 只负责启动 dashboard，不启动采集、不启动补拉、不启动 Telegram 推送。

### 4.3 文件结构

目标结构：

```text
jin10-monitor/
├── jin10_monitor.py
├── run_dashboard.py
├── dashboard/
│   ├── __init__.py
│   ├── app.py
│   ├── db.py
│   ├── analysis_db.py
│   ├── evidence.py
│   ├── manual_ai.py
│   ├── routers/
│   │   ├── __init__.py
│   │   ├── feed.py
│   │   ├── item.py
│   │   ├── telegram_status.py
│   │   ├── system.py
│   │   └── analyze.py
│   └── templates/
│       ├── base.html
│       ├── feed.html
│       ├── item.html
│       ├── telegram_status.html
│       ├── system.html
│       └── analyze.html
├── data/
│   ├── jin10_history.sqlite3
│   ├── dashboard_analysis.sqlite3
│   └── screenshots/
└── docs/
    └── design/
        ├── 001-dashboard-mvp.md
        └── 002-dashboard-ai-full-spec.md
```

`manual_ai.py` 用于生成手工复制给 ChatGPT Business / Custom GPT 的 prompt、解析回填内容和保存分析结果。后续如果做 API adapter，再新增独立模块，不替换 Phase 2A 手工流。

## 5. 数据来源

### 5.1 业务库，只读

业务库：

```text
data/jin10_history.sqlite3
```

只读数据表：

- `flash_history`：快讯、优先级、来源、原始 JSON。
- `runtime_state`：游标、启动时间、补拉状态等运行状态。
- `delivery_log`：成功发送过 Telegram 的权威去重记录。
- `telegram_delivery_status`：sent / failed / unknown_timeout / skipped 诊断状态。

Dashboard 打开业务库必须使用 SQLite `mode=ro`。缺库时显示错误页，不创建数据库；schema 不匹配时显示诊断错误，不自动迁移。

### 5.2 分析库，可写

分析库：

```text
data/dashboard_analysis.sqlite3
```

分析库由 dashboard 管理，可以创建和写入。它与业务库隔离，删除分析库不影响监控历史。

建议表：

```sql
CREATE TABLE IF NOT EXISTS analysis_runs (
    id TEXT PRIMARY KEY,
    question TEXT NOT NULL,
    asset TEXT NOT NULL DEFAULT '',
    window_start TEXT NOT NULL DEFAULT '',
    window_end TEXT NOT NULL DEFAULT '',
    from_item_id TEXT NOT NULL DEFAULT '',
    user_context TEXT NOT NULL DEFAULT '',
    evidence_packet_json TEXT NOT NULL DEFAULT '',
    manual_prompt TEXT NOT NULL DEFAULT '',
    answer_text TEXT NOT NULL DEFAULT '',
    answer_json TEXT NOT NULL DEFAULT '',
    model_label TEXT NOT NULL DEFAULT 'manual_chatgpt_business',
    prompt_version TEXT NOT NULL DEFAULT 'v1',
    evidence_count INTEGER NOT NULL DEFAULT 0,
    judgement TEXT NOT NULL DEFAULT '',
    overall_confidence REAL NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'draft',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS analysis_evidence (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    news_id TEXT NOT NULL,
    rank INTEGER NOT NULL DEFAULT 0,
    relevance_score REAL NOT NULL DEFAULT 0,
    matched_keywords TEXT NOT NULL DEFAULT '',
    selected INTEGER NOT NULL DEFAULT 1,
    llm_confidence REAL NOT NULL DEFAULT 0,
    llm_impact_path TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS screenshots (
    id TEXT PRIMARY KEY,
    file_path TEXT NOT NULL,
    original_filename TEXT NOT NULL DEFAULT '',
    user_description TEXT NOT NULL DEFAULT '',
    uploaded_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
```

### 5.3 Evidence builder 数据边界

Evidence builder 默认只读本地 SQLite：

- 从 `flash_history` 按时间窗口取消息。
- 结合标的关键词、宏观关键词和优先级打分。
- 最多返回有限条数，避免 evidence packet 过大。
- 不主动请求 Jin10 REST。
- 不主动请求任何行情 API。
- 不写 `jin10_history.sqlite3`。

Jin10 REST、行情 REST、链上数据、交易所数据均属于后续增强，不是 Phase 2A 默认数据源。

## 6. 页面设计

### 6.1 `/` 快讯流

用途：

- 查看最近入库快讯。
- 区分 T3 / T2 / T1 / T0。
- 查看来源、发生时间、入库来源和 Telegram 状态。
- 快速跳转到单条详情页。

Phase 1 功能：

- 优先级筛选：全部、T3、T2、T1、T0。
- 关键词搜索：查标题和正文。
- 时间范围：最近 1h / 6h / 24h / 自定义。
- 仅看已推 Telegram。
- 只读展示消息密度。
- 点击消息进入 `/item/{id}`。

数据来源：

- `flash_history`
- `delivery_log`
- `telegram_delivery_status`

禁止行为：

- 不触发补拉。
- 不刷新 Jin10 REST。
- 不发送 Telegram。

### 6.2 `/item/{id}` 消息详情和上下文

用途：

- 查看中心消息详情。
- 查看前后 5/15/30/60 分钟上下文。
- 判断一条消息出现时附近有哪些相关事件。
- 跳转到 `/analyze` 并预填时间窗口。

Phase 1 功能：

- 中心消息高亮。
- 时间线按 `published_at` 正序展示。
- 展示优先级、来源、图片链接、source_url。
- 展示 Telegram 投递状态。
- 折叠展示 `raw_json`。
- 提供“用这段上下文生成证据包”入口，跳转 `/analyze`，但只预填参数。

数据来源：

- `flash_history`
- `telegram_delivery_status`
- `delivery_log`

边界：

- 上下文语义应与 `--context <id>` 保持一致。
- 不写业务库。

### 6.3 `/telegram-status` 投递状态

用途：

- 查看 Telegram 发送、失败、超时未知和跳过状态。
- 诊断失败原因。
- 保护既有去重语义。

Phase 1 功能：

- 统计卡：sent、failed、unknown_timeout、skipped。
- 状态筛选。
- 列表展示消息 ID、状态、mode、detail、更新时间和消息摘要。
- 链接到 `/item/{id}`。
- 明确标注 `unknown_timeout` 不是成功，也不是失败，只是状态未知。

数据来源：

- `telegram_delivery_status`
- `flash_history`

禁止行为：

- 不提供重试按钮。
- 不提供补发按钮。
- 不写 `delivery_log`。
- 不改变“已成功发送过的 Telegram 不重复补发”的语义。

### 6.4 `/system` 系统健康

用途：

- 判断监控进程最近是否还在入库。
- 查看数据库、游标、关键词和投递概况。

Phase 1 功能：

- 最后入库时间和距今分钟数。
- `last_ingested_at`、`last_startup`、`last_catchup_at`。
- 历史库大小和总消息数。
- 今日 T3 / T2 / 已推 / 失败数量。
- KEYWORDS / HIGH_PRIORITY 数量。
- 本地服务绑定地址和端口。

数据来源：

- `runtime_state`
- `flash_history`
- `delivery_log`
- `telegram_delivery_status`
- 本地文件 metadata
- 环境变量中的关键词配置文件路径或已加载关键词列表

边界：

- 不检查公网。
- 不修改 launchd。
- 不重启监控进程。

### 6.5 `/analyze` 分析工作台

用途：

- 生成 evidence packet。
- 让用户检查证据是否正确。
- 复制 prompt 到 ChatGPT Business / Custom GPT。
- 粘贴模型回答并保存。
- 建立“答案 -> evidence -> 原始快讯”的可追溯链路。

Phase 2A 功能：

- 输入问题、标的、时间窗口。
- 可从 `/item/{id}` 预填时间窗口和中心消息。
- 可选上传截图并填写手工描述。
- 生成证据包预览。
- 支持勾选/取消证据。
- 生成手工 prompt。
- 一键复制 prompt 文本。
- 提供粘贴回答输入框。
- 保存分析记录到 `dashboard_analysis.sqlite3`。
- 保存 evidence 引用到 `analysis_evidence`。
- 回答中的 news_id 在页面中渲染为 `/item/{id}` 链接。

Phase 2A 不做：

- 不调用 OpenAI API。
- 不调用 Anthropic API。
- 不调用 Claude Vision。
- 不自动理解截图。
- 不主动请求行情 API。

## 7. AI 分析链路

### 7.1 Phase 2A 手工流

默认 AI 工作流：

1. 用户输入问题、标的和时间窗口。
2. Dashboard 从本地 SQLite 只读构建 evidence packet。
3. 用户预览 evidence，必要时调整时间窗口或取消不相关证据。
4. Dashboard 生成适合复制的 prompt。
5. 用户复制到 ChatGPT Business / Custom GPT。
6. 用户把回答粘贴回 Dashboard。
7. Dashboard 保存回答、证据引用和元信息。
8. 用户可从回答里的引用跳回 `/item/{id}` 查看原始快讯。

这个流程的优点：

- 不需要 API key。
- 不新增外部网络依赖。
- 不把 Claude / Anthropic 作为前置条件。
- 用户可以人工判断 evidence 是否靠谱。
- 先验证分析产品形态，再决定是否自动化。

### 7.2 Evidence packet 格式

建议输出：

```json
{
  "question": "BTC刚才为什么突破106k？",
  "asset": "BTC",
  "window_start": "2026-05-21 21:30:00",
  "window_end": "2026-05-21 22:00:00",
  "query_boundary": {
    "source": "local_sqlite_only",
    "jin10_rest_called": false,
    "market_data_called": false
  },
  "evidence": [
    {
      "news_id": "20260521214702000000",
      "published_at": "2026-05-21 21:47:02",
      "priority_level": "T3_IMPORTANT",
      "title": "消息标题",
      "content": "消息正文",
      "news_source": "金十数据",
      "source_url": "",
      "relevance_score": 0.85,
      "matched_keywords": ["BTC", "美联储"]
    }
  ],
  "missing_by_design": [
    "未接入分钟级价格",
    "未接入成交量",
    "未接入链上数据",
    "未接入资金费率"
  ]
}
```

### 7.3 手工 prompt 要求

Prompt 必须强制模型：

- 只能引用 evidence packet 中的 news_id。
- 不编造不存在的新闻。
- 区分新闻催化、宏观情绪、技术突破和证据不足。
- 每条归因写清楚 `impact_path`，不能只说“利好”或“利空”。
- 明确列出缺失证据。
- 输出可回填的结构化 JSON 或清晰分段文本。

建议回填 JSON：

```json
{
  "summary": "一句话结论",
  "judgement": "news_driven",
  "overall_confidence": 0.72,
  "catalysts": [
    {
      "news_id": "20260521214702000000",
      "impact_path": "具体归因机制",
      "confidence": 0.78,
      "direction": "bullish"
    }
  ],
  "missing_evidence": [
    "BTC/USDT 1分钟成交量",
    "交易所资金费率",
    "链上大额转账"
  ],
  "caveat": "只基于本地金十快讯，未验证价格和成交量。"
}
```

### 7.4 Phase 2B 可插拔 API adapter

只有 Phase 2A 跑通后，才评估 API 自动化。可选 adapter：

- OpenAI adapter。
- Anthropic adapter。
- Ollama / local model adapter。

要求：

- Adapter 不能改变 evidence builder 的只读边界。
- Adapter 不能成为打开 `/analyze` 的前置条件。
- 没有 API key 时，手工复制粘贴流必须继续可用。
- API 结果必须保存到同一套 `analysis_runs` 和 `analysis_evidence`。

## 8. 分阶段开发计划

### Phase 0：文档冻结

交付物：

- `docs/design/002-dashboard-ai-full-spec.md`

验收：

- 明确旧 MVP 原型的保留和停止扩展边界。
- 明确正式 FastAPI/Jinja2 方向。
- 明确 Phase 1 / Phase 2A 不改 `jin10_monitor.py`。
- 明确 Anthropic / Claude API 不作为 P0/P1 前置依赖。
- 明确 evidence builder 默认只读本地 SQLite。
- 明确 Telegram dashboard 链接放到 Phase 3 单独做。

### Phase 1：独立只读 Dashboard

目标：把已验证的只读 MVP 能力迁移为独立 FastAPI/Jinja2 dashboard。

建议小步 commit：

1. 新增 `run_dashboard.py`、`dashboard/__init__.py`、`dashboard/app.py`。
2. 新增 `dashboard/db.py`，封装只读 SQLite 查询。
3. 新增基础模板和导航。
4. 实现 `/` 快讯流。
5. 实现 `/item/{id}`。
6. 实现 `/telegram-status`。
7. 实现 `/system`。
8. 补 README 和依赖说明。

Phase 1 边界：

- 不改 `jin10_monitor.py`。
- 不删除旧 `--dashboard`。
- 不写业务库。
- 不调用 Jin10 REST。
- 不发送 Telegram。
- 不接 AI API。

Phase 1 验收：

- `python run_dashboard.py` 能启动。
- 默认绑定 `127.0.0.1:8765`。
- 缺少历史库时显示错误页，不创建库。
- 访问所有页面后，`jin10_history.sqlite3` 无新增业务行。
- `/item/{id}` 上下文与 `--context` 语义一致。
- Ctrl+C 停 dashboard 不影响 launchd 监控服务。

### Phase 2A：Evidence packet + 手工 AI 回填

目标：先做完整的无 API 分析闭环。

建议小步 commit：

1. 新增 `dashboard/analysis_db.py` 和 `data/dashboard_analysis.sqlite3` 初始化逻辑。
2. 新增 `dashboard/evidence.py`，只读本地 SQLite 构建 evidence packet。
3. 新增 `/analyze` 页面输入和 evidence preview。
4. 新增 prompt 生成和复制视图。
5. 新增回答粘贴、解析和保存。
6. 新增分析详情或历史入口。
7. 补 README。

Phase 2A 边界：

- 不改 `jin10_monitor.py`。
- 不调用 Jin10 REST。
- 不调用 OpenAI / Anthropic / Claude API。
- 不自动理解截图。
- 不接 Telegram 链接。

Phase 2A 验收：

- 能从本地历史库生成 evidence packet。
- Evidence packet 标注 `local_sqlite_only`。
- 能复制 prompt 到 ChatGPT Business / Custom GPT。
- 能粘贴回答并保存到分析库。
- 保存的 evidence 中每个 news_id 都能跳转到 `/item/{id}`。
- 删除分析库不会影响业务库。

### Phase 2B：可选 LLM adapter

目标：在手工流稳定后再决定是否自动调用模型。

可选任务：

- 新增 provider adapter 接口。
- 实现 OpenAI adapter。
- 实现 Anthropic adapter。
- 增加 provider 配置和禁用开关。
- 增加失败降级到手工流。

边界：

- 手工流永远保留。
- 没有 API key 时 dashboard 仍可完整使用 Phase 1 和 Phase 2A。

### Phase 3：增强和跨链路功能

可选任务：

- Telegram 消息附带 dashboard 详情链接，单独 commit。
- `/aggregation` 只读聚合候选报告。
- 分钟级价格数据叠加。
- 截图 Vision 增强。
- 分析历史对比。
- System prompt 版本对比。

Phase 3 中 Telegram dashboard 链接是唯一可能需要改 `jin10_monitor.py` 的功能，必须单独评估、单独 diff、单独 commit，且不得改变 Telegram 去重语义。

## 9. 风险和控制

### 9.1 误写业务库

风险等级：高。

控制：

- 业务库连接必须 `mode=ro`。
- 缺库不创建。
- schema 不匹配不迁移。
- 分析结果只写 `dashboard_analysis.sqlite3`。

### 9.2 干扰实时监控

风险等级：中。

控制：

- 独立手动启动。
- 不接管 launchd。
- 不连接 WebSocket。
- 不触发 REST 补拉。
- 不发送 Telegram。

### 9.3 本地服务误暴露

风险等级：中。

控制：

- 默认只绑定 `127.0.0.1`。
- 不建议 `0.0.0.0`。
- 一旦需要局域网、Tailscale、反向代理或公网访问，必须先补认证和访问控制设计。

### 9.4 AI 误归因

风险等级：中。

控制：

- 先 evidence preview，再手工复制。
- Prompt 强制只引用 evidence 中 news_id。
- 输出必须包含 missing evidence。
- 页面明确说明当前证据不包含价格、成交量、链上和资金费率，除非后续接入。

### 9.5 Telegram 语义破坏

风险等级：高。

控制：

- Phase 1 / 2A 不改 Telegram 推送逻辑。
- `/telegram-status` 只读。
- `delivery_log` 继续作为成功发送去重权威来源。
- Telegram dashboard 链接放到 Phase 3 单独做。

## 10. 当前 MVP 与正式 Dashboard 的关系

| 项目 | 当前 `--dashboard` MVP | 正式 FastAPI Dashboard |
|------|------------------------|-------------------------|
| 入口 | `jin10_monitor.py --dashboard` | `run_dashboard.py` |
| 位置 | `jin10_monitor.py` 内 | `dashboard/` 独立目录 |
| 状态 | 已提交，保留 | 后续新开发 |
| 用途 | 原型、fallback、交互参考 | 正式本地工具 |
| 是否继续扩展 | 否 | 是 |
| 是否写业务库 | 否 | 否 |
| AI 分析 | 无 | Phase 2A 手工流 |

迁移时不急于删除旧入口。只有正式 dashboard 稳定后，再评估是否废弃或保留旧 `--dashboard`。

## 11. 不做清单

明确暂不做：

- 大规模重构 `jin10_monitor.py`。
- 直接开启 AGGREGATION_V2 suppress。
- Telegram callback receiver。
- 公网暴露。
- 用户系统。
- Postgres / VPS 迁移。
- 向量检索 / embedding。
- 自动交易建议。
- 把 Claude / Anthropic API 作为 P0/P1 必需项。

## 12. 后续提交建议

Phase 0 只提交文档：

- `docs/design/002-dashboard-ai-full-spec.md`

如果 `docs/status/033-2026-05-22-dashboard-architecture-reset-handoff.md` 仍为 untracked，建议同一个文档提交中纳入跟踪。原因是它已经是本轮工作的权威入口，记录了架构切换结论；继续 untracked 会让后续每次开工都看到脏状态，也容易丢失上下文。
