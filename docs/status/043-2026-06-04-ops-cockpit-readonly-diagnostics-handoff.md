更新时间：2026-06-04 05:22（Asia/Shanghai）

# 项目状态摘要 043：运维驾驶舱与只读诊断收口

日期：2026-06-04

## 1. 本摘要用途

本摘要接续 `042` 之后的 P0 只读运行告警增强阶段。

本阶段已经完成：

- `/system` 运维驾驶舱。
- `/telegram-status` unknown_timeout 只读核对。
- `/system/ws-initial` WebSocket initial history 下钻。
- `CHANGELOG.md` 已按规则把已提交条目归入 `## 2026-06-03`。

当前最新提交：

```text
bf4a9b4 feat(dashboard): add websocket initial review
```

## 2. 当前仓库状态

只读检查时间：

```text
2026-06-04 05:22（Asia/Shanghai）
```

分支与远端：

```text
main...origin/main
```

最近提交：

```text
bf4a9b4 feat(dashboard): add websocket initial review
b339126 feat(dashboard): add timeout delivery review
3255141 feat(dashboard): add system operations cockpit
92973a1 feat(dashboard): clarify system runtime alerts
e6b411c docs(status): add market context handoff
243e0c8 feat(dashboard): add analyze market context
377714d feat(dashboard): load market adapter config
f077ccd feat(dashboard): add item market overlay
```

本摘要生成前工作树干净。本摘要生成后会新增：

```text
docs/status/043-2026-06-04-ops-cockpit-readonly-diagnostics-handoff.md
```

并更新：

```text
CHANGELOG.md
```

## 3. 本阶段已完成内容

### 3.1 `/system` 运维驾驶舱

相关提交：

```text
92973a1 feat(dashboard): clarify system runtime alerts
3255141 feat(dashboard): add system operations cockpit
```

完成内容：

- `/system` 第一屏新增总判断，例如“运行正常 / 降级运行 / 需要关注 / 需要立即排查”。
- 新增人工动作建议，把 REST 退避、Telegram unknown_timeout、WebSocket initial history 新入库翻译成可执行的观察事项。
- 新增四条链路卡：
  - WebSocket 主路
  - REST 轮询
  - WebSocket initial history
  - Telegram 投递
- 新增 24h 入库来源条形图。
- 新增 24h Telegram sent / unknown_timeout / failed 条形图。
- 保留原始诊断表，供开发排查 `runtime_state`、REST 状态、initial history 覆盖窗口、Telegram 最近状态和 Provider 状态。
- 修复移动端横向溢出。

边界：

- 只读读取本地 SQLite。
- 不触发 WebSocket。
- 不触发金十 REST。
- 不触发补拉。
- 不发送、不重试、不补发 Telegram。
- 不写 `delivery_log` 或业务历史库。

### 3.2 unknown_timeout 只读核对

相关提交：

```text
b339126 feat(dashboard): add timeout delivery review
```

完成内容：

- `/telegram-status?status=unknown_timeout` 新增 `delivery_log` 确认列。
- 每条投递状态可展示：
  - Telegram 最新状态
  - mode
  - updated_at
  - message_id
  - 是否已在 `delivery_log` 确认
  - `confirmed_sent_at`
- 汇总区拆分：
  - 24h unknown_timeout
  - 已在 `delivery_log` 确认
  - 仍需人工核对
- 页面明确 unknown_timeout 只表示请求发出后未拿到确认，不等同失败。

边界：

- 不自动重发 unknown_timeout。
- 不写 `delivery_log`。
- 不修改 Telegram 去重语义。

### 3.3 WebSocket initial history 下钻

相关提交：

```text
bf4a9b4 feat(dashboard): add websocket initial review
```

完成内容：

- 新增 `GET /system/ws-initial`。
- 列出最近 `source='ws_initial'` 的新入库快讯。
- 展示 initial history 运行状态：
  - `last_ws_initial_at`
  - `last_ws_initial_count`
  - `last_ws_initial_saved_count`
  - 覆盖窗口
  - 当前 `last_ingested_at`
  - 当前 `last_ingested_id`
- 每条 ws_initial 记录展示：
  - published_at
  - 是否晚于当前 `last_ingested_at`
  - priority
  - 内容摘要
  - Telegram 最新状态
  - `delivery_log` 确认状态
- `/system` Initial History 链路卡和详细说明区新增下钻入口。

边界：

- 只读审计。
- 不推进 `last_ingested_at`。
- 不推进 `last_ingested_id`。
- 不补发 Telegram。
- 不生成摘要式 Telegram 提醒。

## 4. 当前真实运行状态

只读读取 `runtime_state`：

```text
last_startup_at|2026-06-02 19:31:52
last_ingested_at|2026-06-04 05:24:21
last_ingested_id|20260604052421958800
last_catchup_at|2026-06-04 05:13:53

last_ws_initial_at|2026-06-04 05:19:04
last_ws_initial_count|40
last_ws_initial_saved_count|1
last_ws_initial_oldest_published_at|2026-06-04 04:26:32
last_ws_initial_newest_published_at|2026-06-04 05:18:28

rest_status|ok
rest_forbidden_streak|0
rest_last_ok_at|2026-06-04 05:24:25
rest_last_error_at|2026-06-03 23:31:12
rest_last_error|
rest_backoff_until|
```

24h 入库来源：

```text
catchup_auto|2026-06-04 05:11:28|1008
ws|2026-06-04 05:24:21|420
ws_initial|2026-06-04 05:18:28|243
rest|2026-06-04 05:17:49|123
```

Telegram 24h 状态：

```text
failed|12|2026-06-03 15:13:33
sent|265|2026-06-03 15:24:06
unknown_timeout|71|2026-06-03 21:20:23
```

ws_initial 晚于当前游标数量：

```text
0
```

判断：

- WebSocket 主路仍新鲜，`last_ingested_at` 正在推进。
- REST 当前为 `ok`，较 `042` 的反复 `forbidden_backoff` 状态更好，但仍需继续观察。
- WebSocket initial history 最近仍有快照和少量新入库，但当前没有晚于 `last_ingested_at` 的 ws_initial 记录。
- Telegram `unknown_timeout` 仍存在，当前更适合继续只读核对，不应自动重发。

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
- `043`：P0 只读运行诊断闭环已完成，包括运维驾驶舱、unknown_timeout 核对、ws_initial 下钻。

### 尚未完成但仍在路线内

- Phase 2B Provider Adapter：目前只有 OpenAI / Anthropic stub，没有真实 API 调用。
- Vision 识别：当前截图仍是手工描述，没有自动图表理解。
- REST 长期 403 后的补拉 source adapter：目前只有设计评估，没有接入官方 API 或外部源 probe。
- WebSocket initial history 短缺口恢复策略：当前只有只读审计，没有摘要式告警或恢复策略。
- Telegram unknown_timeout 的人工处置流程：当前只有只读核对，没有人工标记、备注或受控重发。

## 6. 下一步优先级建议

### P0：继续观察只读驾驶舱，不立刻改采集链路

推荐先观察一段时间。

原因：

- REST 当前已经恢复为 `ok`。
- WebSocket 主路仍新鲜。
- ws_initial 当前没有晚于游标的记录。
- 继续动采集链路、补发、游标推进会明显提高风险。

建议动作：

- 继续使用 `/system` 看总判断。
- 使用 `/telegram-status?status=unknown_timeout` 核对 Telegram 未确认项。
- 使用 `/system/ws-initial` 观察 ws_initial 是否再次出现晚于游标的记录。

模型建议：

```text
GPT-5.5 中
```

### P1：Telegram unknown_timeout 人工备注 / 只读处置设计

建议先写设计，不建议立刻实现重发。

可设计内容：

- 是否允许独立分析库记录人工核对备注。
- 是否记录“已人工确认无需处理”。
- 是否需要一个只写 `dashboard_analysis.sqlite3` 的运维备注表。
- 是否永远禁止写 `delivery_log`，除非真实发送成功。

不建议马上做：

- 自动重发。
- 自动把 unknown_timeout 标为 sent。
- 改 Telegram 去重。

模型建议：

```text
GPT-5.5 中（只写设计）
GPT-5.5 高（如果要实现任何写入或重发相关流程）
```

### P1：Provider Adapter 真实 API 接入设计

这是下一条产品能力主线，但需要先做设计选择。

前置决定：

- 用 OpenAI 还是 Anthropic，或两者都保留。
- 模型、费用、超时、失败降级。
- provider 是否接收截图。
- Vision 是否与 Provider Adapter 同阶段设计。

建议第一步：

- 写 `007-provider-adapter-implementation-plan.md`。
- 不直接接 API。
- 保留手工复制粘贴为默认路径。

模型建议：

```text
GPT-5.5 中（设计）
GPT-5.5 高（真实 API 实现）
```

### P2：WebSocket initial history 摘要式人工提醒设计

这项暂不建议立即实现。

原因：

- 当前 `ws_initial` 晚于游标数量为 `0`。
- 如果未来要提醒，应该是摘要式、人工核对型，而不是逐条 Telegram 补发。
- 会触碰消息去重、游标语义和告警噪音。

模型建议：

```text
GPT-5.5 高
```

### P2：REST source adapter / 外部源 probe

继续暂缓接入运行链路。

当前更合理的状态：

- 保留 `005-rest-backfill-alternatives.md` 的设计结论。
- 金十官方 API 等授权和 token。
- 外部源 probe 不写 `flash_history`、不发 Telegram。

模型建议：

```text
GPT-5.5 高
```

## 7. 推荐下一步

建议新 session 第一件事做：

```text
只读观察与决策：确认 `/system`、`/telegram-status?status=unknown_timeout`、`/system/ws-initial` 三个页面在 8765 上的运行信号，然后决定是否进入 Provider Adapter 设计。
```

如果要继续做功能，推荐优先：

```text
P1：Provider Adapter 真实 API 接入设计文档
```

原因：

- P0 运行诊断已经完成闭环。
- 当前 REST / WebSocket 状态不需要立刻高风险修采集。
- Provider Adapter 是当前 Dashboard 产品路线中下一个明确主线。

模型建议：

```text
GPT-5.5 中：写 Provider Adapter 设计、只读观察、文档收口。
GPT-5.5 高：实现真实 OpenAI / Anthropic API、Vision、任何 Telegram 写入/重发/去重、任何采集链路或 SQLite 游标改动。
```

## 8. 可以继续搁置的事项

短期继续搁置：

- 自动重发 `unknown_timeout`。
- 自动把 unknown_timeout 改写成 sent。
- WebSocket initial history 自动推进游标。
- WebSocket initial history 逐条补发 Telegram。
- 外部新闻源接入运行链路。
- 金十 REST 私有接口对抗式修复。
- 首页行情批量请求。
- Vision 自动截图分析。

搁置原因：

- 当前只读诊断已经足够定位主要运行状态。
- 上述项目会触碰采集、推送、去重或外部 API 成本边界。

## 9. 验证记录

本阶段代码提交前已验证：

```text
git diff --check
无输出

.venv/bin/python -m py_compile dashboard/db.py dashboard/app.py
通过

.venv/bin/python -m pytest tests/test_dashboard_db.py -q
22 passed

.venv/bin/python -m pytest -q
173 passed

Browser smoke:
http://127.0.0.1:8765/system
http://127.0.0.1:8765/telegram-status?status=unknown_timeout
http://127.0.0.1:8765/system/ws-initial
```

本摘要生成前只读检查：

```text
git branch --show-current
main

git status --short --branch
## main...origin/main

git log --oneline -8
bf4a9b4 feat(dashboard): add websocket initial review
b339126 feat(dashboard): add timeout delivery review
3255141 feat(dashboard): add system operations cockpit
92973a1 feat(dashboard): clarify system runtime alerts
e6b411c docs(status): add market context handoff
243e0c8 feat(dashboard): add analyze market context
377714d feat(dashboard): load market adapter config
f077ccd feat(dashboard): add item market overlay
```

## 10. 可直接复制的 next-session prompt

```text
请继续 /Users/rich/jin10-monitor 项目。

建议模型：
- GPT-5.5 中：只读观察、文档收口、Provider Adapter 设计、CHANGELOG、Dashboard 只读诊断。
- GPT-5.5 高：真实 Provider API、Vision、Telegram 写入/重发/去重、SQLite 游标、采集链路、REST source adapter 或外部源。

先读取：
1. /Users/rich/jin10-monitor/AGENTS.md
2. /Users/rich/jin10-monitor/docs/status/043-2026-06-04-ops-cockpit-readonly-diagnostics-handoff.md
3. /Users/rich/jin10-monitor/docs/status/042-2026-06-03-market-context-priority-handoff.md
4. /Users/rich/jin10-monitor/docs/design/004-dashboard-v2-plan.md
5. /Users/rich/jin10-monitor/docs/design/006-market-overlay-binance-plan.md
6. /Users/rich/jin10-monitor/docs/design/005-rest-backfill-alternatives.md
7. /Users/rich/jin10-monitor/docs/design/003-phase2b-phase3-spec.md

先执行：
git branch --show-current
git status
git pull --rebase
git log --oneline -8

当前结论：
- 最新已推送提交：bf4a9b4 feat(dashboard): add websocket initial review。
- P0 只读运行诊断闭环已完成：/system 运维驾驶舱、/telegram-status unknown_timeout 核对、/system/ws-initial 下钻。
- Dashboard 仍是本地只读诊断和分析侧车，不作为采集入口。
- 不接模型 API，不请求金十 REST from dashboard，不写业务历史库，不自动重发 Telegram unknown_timeout，不推进 WebSocket initial history 游标。
- 当前只读运行状态显示 WebSocket 主路新鲜，REST 当前 ok，ws_initial 最近有快照但没有晚于游标的记录，Telegram unknown_timeout 仍需观察。

推荐下一步：
先只读确认 8765 上三个诊断页：/system、/telegram-status?status=unknown_timeout、/system/ws-initial。
如果继续做功能，优先写 Provider Adapter 真实 API 接入设计文档，不要直接接 API。

暂缓：
Vision 自动截图分析、Telegram unknown_timeout 自动重发、WebSocket initial history 自动推进游标或补发、REST source adapter、外部新闻源 probe、首页行情批量请求。
```
