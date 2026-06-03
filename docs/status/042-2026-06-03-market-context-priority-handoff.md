更新时间：2026-06-03 20:26（Asia/Shanghai）

# 项目状态摘要 042：行情上下文收口与后续优先级编排

日期：2026-06-03

## 1. 本摘要用途

本摘要用于接续 `041` 之后的 Dashboard 行情叠加阶段，并为下一 session 排定优先级。

本阶段已经完成：

- Binance market adapter 第一版。
- `/item/{id}` 用户触发的行情上下文面板。
- `/analyze` 可选结构化行情上下文进入 Prompt。
- `run_dashboard.py` 启动时加载 `.env`。
- `CHANGELOG.md` 重新按日期分组。
- 最新代码已提交并推送到 `origin/main`。

当前最新提交：

```text
243e0c8 feat(dashboard): add analyze market context
```

## 2. 当前仓库状态

只读检查时间：

```text
2026-06-03 20:26（Asia/Shanghai）
```

分支与远端：

```text
main...origin/main
```

最近提交：

```text
243e0c8 feat(dashboard): add analyze market context
377714d feat(dashboard): load market adapter config
f077ccd feat(dashboard): add item market overlay
8f5de91 feat(dashboard): add binance market adapter
5a81bca docs(dashboard): plan binance market overlay
0af26b3 fix(runtime): start websocket before rest startup work
8498a04 fix(dashboard): reduce feed refresh latency
ca42086 feat(dashboard): clarify degraded runtime notices
```

本摘要生成前工作树干净。本摘要生成后会新增：

```text
docs/status/042-2026-06-03-market-context-priority-handoff.md
```

并更新：

```text
CHANGELOG.md
```

## 3. 本阶段已完成内容

### 3.1 Binance market adapter

相关提交：

```text
8f5de91 feat(dashboard): add binance market adapter
377714d feat(dashboard): load market adapter config
```

完成内容：

- 新增 Binance Spot public REST adapter。
- 支持 `GET /api/market/klines`。
- 支持 `BTCUSDT`、`ETHUSDT`、`SOLUSDT`、`BNBUSDT` 白名单交易对。
- 支持 `1m`、`5m` 周期。
- 增加 symbol / interval 校验、请求超时、错误降级和进程内 TTL cache。
- `run_dashboard.py` 启动时加载 `.env`，使正式 8765 dashboard 能读取 `MARKET_ADAPTER=binance`。

边界：

- 默认未配置时不请求外部行情 API。
- 不写业务历史库。
- 不影响 WebSocket / REST / Telegram。
- Binance 失败时 dashboard 继续可用。

### 3.2 `/item/{id}` 行情上下文面板

相关提交：

```text
f077ccd feat(dashboard): add item market overlay
```

完成内容：

- 在单条快讯详情页加入用户触发的行情上下文面板。
- 支持选择交易对、周期和快讯邻近窗口。
- 展示价格摘要和小型 K 线表格。
- 仅点击加载时请求 market adapter。

边界：

- 首页不批量请求行情。
- `/system` 不展示行情列表。
- 打开 `/item/{id}` 默认不自动请求 Binance。

### 3.3 `/analyze` 可选结构化行情上下文

相关提交：

```text
243e0c8 feat(dashboard): add analyze market context
```

完成内容：

- `/analyze` 输入页新增“结构化行情上下文（可选）”。
- 用户勾选后，使用分析时间窗口请求 market adapter。
- 预览页展示 Binance 行情摘要。
- 生成 Prompt 时写入独立的“结构化行情上下文”区块。
- 行情不可用时 Prompt 明确提示“不要把缺失行情数据当作价格没有波动”。
- hidden JSON 已做 HTML attribute 转义，避免表单传递被双引号截断。

边界：

- 未勾选时不请求 market adapter。
- 行情不是 evidence packet 的前置条件。
- 不接模型 API。
- 不写业务历史库。
- 不改变 Telegram 去重或推送语义。

### 3.4 `CHANGELOG.md` 日期分组规则

已修正：

- `Unreleased` 只放当前未提交或待发布条目。
- 已提交内容按实际日期归入 `## YYYY-MM-DD`。
- 当前已新增 `## 2026-06-03`，记录 `/analyze` 行情上下文。

后续规则：

- 新增未提交变更先放 `Unreleased`。
- commit / push 收口时，把已提交条目归入当天日期段。
- 文档更新时间继续精确到分钟。

## 4. 当前真实运行状态

只读读取 `runtime_state`：

```text
last_startup_at|2026-06-02 19:31:52
last_ingested_at|2026-06-03 20:26:41
last_ingested_id|20260603202641873800
last_catchup_at|2026-06-03 20:10:19

last_ws_initial_at|2026-06-03 20:12:40
last_ws_initial_count|40
last_ws_initial_saved_count|6
last_ws_initial_oldest_published_at|2026-06-03 19:51:50
last_ws_initial_newest_published_at|2026-06-03 20:11:23

rest_status|forbidden_backoff
rest_forbidden_streak|3
rest_last_ok_at|2026-06-03 20:11:27
rest_last_error_at|2026-06-03 20:20:58
rest_last_error|HTTP 403 4/4 entries; backoff 540s
rest_backoff_until|2026-06-03 20:29:58
```

24h 入库来源：

```text
catchup_auto|2026-06-03 20:10:06|973
rest|2026-06-03 20:11:21|118
ws|2026-06-03 20:26:41|369
ws_initial|2026-06-03 20:11:23|265
```

Telegram 24h 状态：

```text
failed|26|2026-06-03 08:39:58
sent|31|2026-06-03 12:26:41
unknown_timeout|61|2026-06-03 12:15:22
```

判断：

- WebSocket 主路仍在推进 `last_ingested_at`。
- REST 仍反复进入 `forbidden_backoff`，但 `rest_last_ok_at=2026-06-03 20:11:27` 说明它仍是间歇恢复，不是彻底断开。
- `last_ws_initial_saved_count=6` 说明 WebSocket initial history 已经真实补入过新消息。
- Telegram 仍有 `sent`，但 `unknown_timeout` 和 `failed` 数量仍值得观察。
- 目前不应自动重发 `unknown_timeout`，成功去重仍以 `delivery_log` 为准。

## 5. 当前设计完成度对照

### 已完成或基本完成

- `002`：独立 FastAPI/Jinja2 dashboard 方向已经落地，正式入口仍是 `run_dashboard.py + dashboard/`。
- `003` Phase 3A：Telegram dashboard 深链已完成。
- `003` Phase 3B：快讯流分页 / 加载能力已完成。
- `003` Phase 3C：截图上传、预览、手工描述已完成。
- `003` 置信度说明已完成。
- `004`：分析对比、重新分析入口、provider stub、market stub 已完成。
- `006` Step 1：Binance adapter 与 API 已完成。
- `006` Step 2：`/item/{id}` 行情面板已完成。
- `006` Step 3：`/analyze` 可选行情上下文已完成。

### 尚未完成但仍在路线内

- Phase 2B Provider Adapter：目前只有 OpenAI / Anthropic stub，没有真实 API 调用。
- Vision 识别：当前截图仍是手工描述，没有自动图表理解。
- REST 长期 403 后的补拉 source adapter：目前只有设计评估，没有接入官方 API 或外部源 probe。
- WebSocket initial history 短缺口恢复策略：目前只读诊断已经证明 `saved_count` 可大于 0，但还没有摘要式告警或恢复策略。
- `/system` 更强告警：目前有只读诊断，但还可以把 REST 间歇恢复、initial history 新入库、Telegram timeout 增长做成更清晰的运行提醒。

## 6. 摘要后优先级建议

### P0：先做只读运行告警增强

推荐优先级最高。

原因：

- REST 仍反复 403。
- `ws_initial_saved_count=6` 已经证明 initial history 有实际补入价值。
- Telegram `unknown_timeout` 仍存在。
- 这一项能提高观察和判断质量，但不改变采集、补拉、推送和去重语义。

建议范围：

- `/system` 明确展示 REST 是“间歇恢复后当前退避”，不是整体采集中断。
- 当 `last_ws_initial_saved_count > 0` 时，用只读提示说明 initial history 已有新入库。
- 当 `unknown_timeout` 在 24h 内持续增长时，用只读提示建议人工核对，不自动重发。
- 保留 Dashboard 只读边界。

模型建议：

```text
GPT-5.5 中
```

### P1：Provider Adapter 真实 API 接入设计，不建议立刻实装

设计文档里 Phase 2B 是下一大阶段，但当前还缺三个前置决定：

- 用 OpenAI 还是 Anthropic，或两者都保留。
- API key、费用、超时、失败降级和模型选择。
- 是否允许 provider 接收截图；如果允许，Vision 边界要一起设计。

建议下一步只先写设计细化或最小实现计划：

- 继续保留手工复制粘贴为默认路径。
- 自动 provider 只写 `dashboard_analysis.sqlite3`。
- provider 失败时保留 prompt 和 evidence。
- 首版不自动发送截图。

模型建议：

```text
GPT-5.5 高（如果要写实现）
GPT-5.5 中（如果只写设计）
```

### P2：Vision / 截图自动分析暂缓

当前截图上传的意义仍然成立：

- 保存截图与分析记录关联。
- 把用户手工描述稳定写入 Prompt。
- 方便历史复盘和证据追溯。

但自动 Vision 需要真实 provider 能力，且会引入：

- 图片发送到外部模型的隐私和成本问题。
- 多图上传顺序和引用问题。
- 识别错误不能覆盖用户描述的 UI 设计。

建议等 Provider Adapter 稳定后再做。

模型建议：

```text
GPT-5.5 高
```

### P3：WebSocket initial history 短缺口恢复策略，先设计后实现

这项重要，但风险高于只读告警。

原因：

- `last_ws_initial_saved_count=6` 说明它可能补到短缺口。
- 但一旦让它参与游标推进或 Telegram 补发，就会触碰 `delivery_log` 去重、`last_ingested_at` 语义和补拉边界。

建议先做设计文档或只读模拟：

- 列出 initial history 新入库项。
- 只生成“摘要式人工核对提示”，不逐条补发。
- 不推进实时游标，除非证明不会覆盖真实 WebSocket。

模型建议：

```text
GPT-5.5 高
```

### P4：REST 补拉 source adapter / 外部源 probe 暂缓

`005` 的结论仍然成立：

- Glanceway 金十示例只适合对照，不能解决同源 REST 403。
- 金十官方 API 是长期最干净方案，但要等授权和 token。
- WallstreetCN / CoinGlass 不能直接混入金十业务历史库。

建议暂缓接入运行链路。

可以保留为未来只读 probe：

- 输出到终端或独立 `data/source_probe/*.json`。
- 不写 `flash_history`。
- 不发 Telegram。
- 不从 Dashboard 触发采集。

模型建议：

```text
GPT-5.5 高
```

### P5：行情功能继续扩展可以搁置

当前 Binance 行情叠加已经完成 `006` 的三步目标。

暂时不建议继续扩：

- 首页 feed 不做批量行情请求。
- `/system` 不展示行情列表。
- 暂不做更多交易对、更多周期或小图表。

原因：

- 当前已经足够支持单条复盘和手工分析。
- 继续扩会增加外部 API 依赖和 UI 复杂度。
- 当前更高价值是运行告警和 Provider/Vision 边界决策。

模型建议：

```text
GPT-5.5 中（小 UI polish）
GPT-5.5 高（复杂图表或多源行情）
```

## 7. 推荐下一步

建议新 session 的第一步做：

```text
P0：/system 只读运行告警增强
```

具体目标：

1. 不改采集链路。
2. 不改 Telegram 发送或去重。
3. 不接外部源。
4. 在 `/system` 更清楚展示：
   - REST 当前退避但曾间歇恢复。
   - WebSocket 主路是否仍新鲜。
   - WebSocket initial history 是否已有新入库。
   - Telegram unknown_timeout 是否需要人工观察。

理由：

- 这是风险最低、收益最高的下一步。
- 能直接服务当前运行问题。
- 不偏离 `002` / `003` / `004` 的 dashboard 只读诊断定位。

## 8. 可以搁置的事项

短期可以搁置：

- 外部新闻源接入运行链路。
- 金十 REST 私有接口对抗式修复。
- Telegram callback receiver。
- 自动重发 `unknown_timeout`。
- 首页行情批量请求。
- Vision 自动截图分析。
- 多图上传和自动传图到模型窗口。
- 事件聚合 V2 默认开启。

搁置不是废弃，而是因为它们要么风险高、要么依赖未决、要么会触碰采集/推送语义。

## 9. 验证记录

本阶段代码提交前已验证：

```text
git diff --check
无输出

.venv/bin/python -m pytest tests/test_dashboard_analysis.py tests/test_market_adapter.py -q
48 passed

.venv/bin/python -m pytest -q
171 passed

Browser smoke:
http://127.0.0.1:8765/analyze 显示“结构化行情上下文（可选）”
```

本摘要生成前只读检查：

```text
git branch --show-current
main

git status --short --branch
## main...origin/main

git pull --rebase
Already up to date.

git log --oneline -8
243e0c8 feat(dashboard): add analyze market context
377714d feat(dashboard): load market adapter config
f077ccd feat(dashboard): add item market overlay
8f5de91 feat(dashboard): add binance market adapter
5a81bca docs(dashboard): plan binance market overlay
0af26b3 fix(runtime): start websocket before rest startup work
8498a04 fix(dashboard): reduce feed refresh latency
ca42086 feat(dashboard): clarify degraded runtime notices
```

## 10. 可直接复制的 next-session prompt

```text
请继续 /Users/rich/jin10-monitor 项目。

建议模型：
- GPT-5.5 中：如果先做 /system 只读运行告警增强、文档收口、CHANGELOG 或只读诊断。
- GPT-5.5 高：如果要实现 Provider Adapter、Vision、WebSocket initial history 短缺口恢复、REST source adapter 或任何涉及 Telegram 去重 / SQLite 游标 / 外部源的逻辑。

先读取：
1. /Users/rich/jin10-monitor/AGENTS.md
2. /Users/rich/jin10-monitor/docs/status/042-2026-06-03-market-context-priority-handoff.md
3. /Users/rich/jin10-monitor/docs/design/004-dashboard-v2-plan.md
4. /Users/rich/jin10-monitor/docs/design/006-market-overlay-binance-plan.md
5. /Users/rich/jin10-monitor/docs/design/005-rest-backfill-alternatives.md
6. /Users/rich/jin10-monitor/docs/design/003-phase2b-phase3-spec.md

先执行：
git branch --show-current
git status
git pull --rebase
git log --oneline -8

当前结论：
- 最新已推送提交：243e0c8 feat(dashboard): add analyze market context。
- Binance 行情叠加三步已完成：adapter/API、/item 用户触发面板、/analyze 可选行情上下文进入 Prompt。
- run_dashboard.py 已加载 .env，8765 可启用 MARKET_ADAPTER=binance。
- CHANGELOG.md 规则已调整：未提交变更放 Unreleased，已提交内容按 ## YYYY-MM-DD 日期分组。
- Dashboard 仍是本地只读诊断和分析侧车，不作为采集入口。
- 不接模型 API，不请求金十 REST from dashboard，不写业务历史库，不自动重发 Telegram unknown_timeout。
- 当前只读运行状态显示 WebSocket 主路仍推进 last_ingested_at，REST 仍 forbidden_backoff 但会间歇恢复，last_ws_initial_saved_count 已出现大于 0。

推荐下一步：
优先做 /system 只读运行告警增强：更清楚展示 REST 间歇恢复/当前退避、WebSocket 主路新鲜度、WebSocket initial history 新入库、Telegram unknown_timeout 人工观察提示。不要改采集链路，不改 Telegram 去重，不接外部源。

暂缓：
Provider Adapter 真实 API、Vision 自动截图分析、REST source adapter、外部新闻源 probe、首页行情批量请求。
```
