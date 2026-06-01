更新时间：2026-06-01 20:34（Asia/Shanghai）

# 项目状态摘要 041：WebSocket initial history 诊断增强收口

日期：2026-06-01

## 1. 本摘要用途

本摘要用于接续 `040` 之后的 REST 长期 403 补拉替代评估和 WebSocket initial history 诊断增强阶段。

当前已经完成：

- REST 长期 403 下的补拉替代设计评估。
- WebSocket initial history 运行诊断状态持久化。
- Dashboard `/system` 只读展示 WebSocket 初始历史快照状态。
- launchd 常驻监控进程 reload，并确认新状态真实写入 `runtime_state`。
- 代码已提交并推送到 `origin/main`。

## 2. 当前仓库状态

当前最新提交：

```text
e56248e feat(runtime): expose websocket initial diagnostics
```

最近提交：

```text
e56248e feat(runtime): expose websocket initial diagnostics
35032e9 docs(dashboard): localize mid-phase handoffs
8c4c66f docs(status): add rest diagnostics handoff
8ae7bd9 feat(runtime): persist rest backoff status
cf361d1 feat(dashboard): enhance system diagnostics panel
```

分支状态：

```text
main...origin/main
```

`HEAD` 与 `origin/main` 一致：

```text
e56248e07aca5776979ae129f2634be1bb913875
```

## 3. 已完成内容

### 3.1 REST 长期 403 补拉替代设计评估

新增文档：

```text
docs/design/005-rest-backfill-alternatives.md
```

核心结论：

- 当前不要立刻把外部源接入运行链路。
- Glanceway 金十源示例只适合作为对照样本，不能解决当前同源 REST 403。
- 金十官方 API 是长期最干净方案，但必须等授权、token、调用条款和限速明确。
- WallstreetCN 7x24 可以作为外部对照或缺口提示，但不是金十补拉替代，不能直接混入现有 `flash_history.id`。
- CoinGlass newsflash 更适合作为 crypto 分析上下文，不适合作为宏观快讯通用补拉源。
- 推荐先强化 WebSocket initial history / reconnect 诊断，再考虑补拉 adapter 边界。

明确隔离规则：

- 外部源首版只能做受控 probe。
- probe 不写 `flash_history`。
- probe 不写 `delivery_log`。
- probe 不写 `telegram_delivery_status`。
- probe 不调用 Telegram。
- Dashboard 不作为采集入口。

### 3.2 WebSocket initial history 状态持久化

提交：

```text
e56248e feat(runtime): expose websocket initial diagnostics
```

完成内容：

- WebSocket reconnect 收到 initial history list 时写入 `runtime_state`：
  - `last_ws_initial_at`
  - `last_ws_initial_count`
  - `last_ws_initial_saved_count`
  - `last_ws_initial_newest_published_at`
  - `last_ws_initial_oldest_published_at`
- 日志从原来的：

```text
WebSocket 初始历史列表已预热去重：40 条
```

扩展为：

```text
WebSocket 初始历史列表已预热去重：40 条，新入库 0 条
```

边界：

- 不推进 `last_ingested_at`。
- 不发送 Telegram。
- 不重发 `unknown_timeout`。
- 不改变 `delivery_log` 去重语义。
- 不改变 REST 请求策略。
- 不改变补拉执行逻辑。
- 只新增 `runtime_state` 诊断键和 Dashboard 只读展示。

### 3.3 Dashboard `/system` 只读展示

完成内容：

- `/system` 的实时链路诊断区继续展示 `ws`、`ws_initial`、`rest`、`catchup_auto`、`catchup_manual` 24h 入库状态。
- 如果存在 `last_ws_initial_*` 状态，则额外展示：
  - 最近快照时间
  - initial list 条数
  - 新入库条数
  - 覆盖的最早 / 最新消息时间

页面仍明确只读：

```text
不会触发补拉、REST 请求、Telegram 重试或发送
```

## 4. 验证记录

代码验证：

```text
.venv/bin/python -m py_compile jin10_monitor.py dashboard/db.py
通过

.venv/bin/python -m pytest -q
149 passed

git diff --check
无输出
```

launchd reload：

```text
scripts/launchd/manage.sh reload
OK: service reloaded with latest plist.
```

reload 后服务状态：

```text
state = running
pid = 8600
```

Browser smoke：

```text
GET http://127.0.0.1:8765/system
200
```

页面确认：

- 显示“系统健康”。
- 显示只读提示。
- 显示 WebSocket 初始历史块。
- 显示“最近快照 / 新入库 / 覆盖”。
- 无 `Internal Server Error`。

## 5. 当前真实运行状态

只读检查时间约为：

```text
2026-06-01 20:34（Asia/Shanghai）
```

launchd：

```text
com.rich.jin10-monitor running
pid=8600
```

`runtime_state` 关键状态：

```text
last_startup_at|2026-06-01 20:29:44
last_ingested_at|2026-06-01 20:33:45
last_ingested_id|20260601203345608800
last_catchup_at|2026-06-01 20:29:45

last_ws_initial_at|2026-06-01 20:29:46
last_ws_initial_count|40
last_ws_initial_saved_count|0
last_ws_initial_oldest_published_at|2026-06-01 20:02:44
last_ws_initial_newest_published_at|2026-06-01 20:29:28
```

REST 状态：

```text
rest_status|forbidden_backoff
rest_forbidden_streak|2
rest_last_ok_at|2026-06-01 20:31:02
rest_last_error_at|2026-06-01 20:34:16
rest_last_error|HTTP 403 4/4 entries; backoff 360s
rest_backoff_until|2026-06-01 20:40:16
```

判断：

- reload 后 REST 曾恢复 `ok`，但随后再次进入 `forbidden_backoff`。
- 这说明 REST 是间歇恢复，不是稳定修复。
- WebSocket 主路仍在推进 `last_ingested_at`。
- WebSocket initial history 状态已经真实写入。

24h 来源：

```text
catchup_auto|2026-06-01 07:03:34|77
rest|2026-06-01 20:20:44|9
ws|2026-06-01 20:33:45|74
ws_initial|2026-06-01 20:21:43|40
```

Telegram 24h 状态：

```text
failed|1|2026-05-31 23:39:27
sent|12|2026-06-01 12:31:45
unknown_timeout|13|2026-06-01 12:31:40
```

最近 Telegram 状态：

```text
20260601203137202800|realtime|sent|2026-06-01 12:31:45
20260601203128103800|realtime|unknown_timeout|2026-06-01 12:31:40|TimeoutError()
20260601203053067800|realtime|sent|2026-06-01 12:30:54
```

判断：

- Telegram realtime 仍有成功 `sent`。
- 仍出现单条 `unknown_timeout`，但不自动重发是正确边界。
- 成功去重仍以 `delivery_log` 为准。

## 6. 重要边界

继续保持：

- Dashboard 不请求金十 REST。
- Dashboard 不触发补拉。
- Dashboard 不发送、不重试 Telegram。
- 不自动重发 `unknown_timeout`。
- 成功去重仍以 `delivery_log` 为准。
- 不把 WallstreetCN、CoinGlass 或其它外部源混入业务历史库。
- 不用外部源消息替代金十消息 ID。
- 不继续扩展旧 `jin10_monitor.py --dashboard` 原型。
- 正式 Dashboard 入口仍是 `run_dashboard.py + dashboard/`。
- 手工 AI 分析流仍是默认路径，不接模型 API。

## 7. 下一步建议

### P0：观察 WebSocket initial history 诊断和 REST 波动

先观察一段真实运行：

- `/system` 是否持续显示新的 `last_ws_initial_at`。
- `last_ws_initial_saved_count` 是否偶尔大于 0。
- REST 是否继续在 `ok` 和 `forbidden_backoff` 之间波动。
- Telegram 是否继续出现新的 `unknown_timeout`，以及是否有后续 `sent`。

建议先不要急着让 `ws_initial` 参与补发或游标推进。

### P1：只读告警增强

如果 REST 继续长期 `forbidden_backoff`，下一步优先做更强告警，而不是接外部源：

- `/system` 明确展示“REST 间歇恢复 / 当前退避”。
- 当 `last_ws_initial_newest_published_at` 明显晚于 `last_ingested_at` 时标记为“initial history 可能覆盖短缺口”。
- 当 `last_ws_initial_saved_count > 0` 时在 `/system` 提醒“initial history 新入库”。

边界：

- 仍只读。
- 不发 Telegram。
- 不推进游标。

### P2：WebSocket initial history 短缺口恢复策略设计

只有在真实观察证明 initial history 能稳定补到缺口后，再评估：

- 是否允许 initial history 生成摘要式告警。
- 是否需要独立记录 initial history 新入库项。
- 是否可以在严格条件下辅助恢复短缺口。

这一步涉及游标、Telegram 去重和补拉语义，建议使用 `GPT-5.5 高`。

### P3：补拉 source adapter

等 P0/P1/P2 更清楚后，再考虑：

- `jin10_legacy_rest`
- `jin10_official`
- `wallstreetcn_probe`
- `coinglass_probe`

首版只能做受控 probe，不进入业务链路。

## 8. 模型建议

- `GPT-5.5 中`：041 handoff、CHANGELOG、只读观察、文档收口、小型 `/system` 文案展示。
- `GPT-5.5 高`：让 `ws_initial` 参与短缺口恢复判断、设计摘要式告警、补拉 source adapter、外部源 probe、任何涉及 Telegram 去重或 SQLite 游标的逻辑变化。

## 9. 可直接复制的 next-session prompt

```text
请继续 /Users/rich/jin10-monitor 项目。

建议模型：
- GPT-5.5 中：如果只是观察运行状态、补 handoff、微调 /system 只读诊断文案。
- GPT-5.5 高：如果要设计或实现 WebSocket initial history 短缺口恢复、摘要式告警、补拉 source adapter 或外部源 probe。

先读取：
1. /Users/rich/jin10-monitor/AGENTS.md
2. /Users/rich/jin10-monitor/docs/status/041-2026-06-01-ws-initial-diagnostics-handoff.md
3. /Users/rich/jin10-monitor/docs/design/005-rest-backfill-alternatives.md
4. /Users/rich/jin10-monitor/docs/status/040-2026-05-31-rest-status-dashboard-handoff.md
5. /Users/rich/jin10-monitor/docs/design/004-dashboard-v2-plan.md

先执行：
git branch --show-current
git status
git pull --rebase
git log --oneline -8

当前结论：
- 最新提交 e56248e feat(runtime): expose websocket initial diagnostics 已推送到 origin/main。
- launchd 已 reload，当前服务 running，PID 8600。
- /system 已能只读展示 WebSocket initial history 最近快照、列表条数、新入库条数和覆盖时间范围。
- reload 后已确认 runtime_state 真实写入 last_ws_initial_*：
  last_ws_initial_at=2026-06-01 20:29:46
  last_ws_initial_count=40
  last_ws_initial_saved_count=0
  last_ws_initial_oldest_published_at=2026-06-01 20:02:44
  last_ws_initial_newest_published_at=2026-06-01 20:29:28
- REST reload 后曾恢复 ok，但到 2026-06-01 20:34:16 又进入 forbidden_backoff，说明 REST 是间歇恢复，不是稳定修复。
- WebSocket 主路仍正常推进 last_ingested_at，Telegram realtime 最近仍有 sent，也有单条 unknown_timeout。
- 不接模型 API，不从 Dashboard 请求金十 REST，不写外部源到业务历史库，不自动重发 Telegram unknown_timeout。

下一步建议：
先观察 /system 的 WebSocket initial history 诊断与 REST 波动；如果只做只读展示增强，用 GPT-5.5 中。如果要让 ws_initial 参与短缺口恢复判断或摘要式告警，用 GPT-5.5 高，并先给设计计划再改代码。
```
