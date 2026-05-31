# 项目状态摘要 040：REST 状态持久化与 Dashboard 诊断收口

日期：2026-05-31

## 1. 本摘要用途

本摘要用于接续 `039` 之后的 Dashboard 可观测性收口阶段。

当前已经完成：

- `/system` 只读运行诊断面板增强。
- REST 403 / 恢复 / 异常状态持久化。
- launchd 常驻监控进程 reload，并已确认新状态真实写入 `runtime_state`。

下一步建议先做文档语言统一：把 `docs/status` 和 `docs/design` 中从中期开始出现的英文正文统一改成中文；文件名、代码块、命令、路由、环境变量、commit hash 保留英文。

## 2. 当前仓库状态

当前最新提交：

```text
8ae7bd9 feat(runtime): persist rest backoff status
```

最近提交：

```text
8ae7bd9 feat(runtime): persist rest backoff status
cf361d1 feat(dashboard): enhance system diagnostics panel
9bd350f docs(status): add realtime ingest handoff
26b7d7e feat(dashboard): add compare analysis and resilient realtime ingest
54bf1f8 docs(dashboard): add v2 bugfix handoff
```

分支状态：

```text
main...origin/main
```

工作区在生成本摘要前是干净的。本摘要生成后会新增：

```text
docs/status/040-2026-05-31-rest-status-dashboard-handoff.md
```

## 3. 已完成内容

### 3.1 `/system` 只读运行诊断面板增强

提交：

```text
cf361d1 feat(dashboard): enhance system diagnostics panel
```

完成内容：

- `/system` 展示最近 WebSocket、WebSocket 初始历史、REST、自动补拉、手动补拉入库时间和 24h 数量。
- 展示 `last_ingested_id`、最后缺口摘要时间。
- 展示 Telegram 最新 `sent`、`unknown_timeout`、`failed` 和最近补拉摘要状态。
- 页面明确标注只读：不触发补拉、REST 请求、Telegram 重试或发送。

验证：

```text
.venv/bin/python -m pytest -q
146 passed

git diff --check
无输出

GET /system
200
```

### 3.2 REST 状态持久化

提交：

```text
8ae7bd9 feat(runtime): persist rest backoff status
```

完成内容：

- REST 轮询成功时写入：
  - `rest_status=ok`
  - `rest_forbidden_streak=0`
  - `rest_last_ok_at`
- REST 全入口 403 时写入：
  - `rest_status=forbidden_backoff`
  - `rest_forbidden_streak`
  - `rest_backoff_until`
  - `rest_last_error`
  - `rest_last_error_at`
- REST 其它异常时写入：
  - `rest_status=error`
  - `rest_last_error`
  - `rest_last_error_at`
- `/system` 优先展示持久化 REST 状态，而不是只靠最近 REST 入库推断。

边界：

- 不改变 REST 请求方式。
- 不改变退避算法。
- 不触发补拉。
- 不发送或重试 Telegram。
- 不写业务快讯内容。
- REST 状态写入失败只打 debug，不阻断轮询。

验证：

```text
.venv/bin/python -m pytest -q
148 passed

git diff --check
无输出

GET /system
200
```

### 3.3 launchd reload 与真实运行确认

已执行：

```text
scripts/launchd/manage.sh reload
```

reload 后确认：

- launchd 服务状态：running
- 新进程 PID：`49084`
- 常驻监控已加载 `8ae7bd9`
- `/system` 能显示 `403 退避中` 和 `REST 状态`

真实 `runtime_state` 证据：

```text
rest_status|forbidden_backoff
rest_forbidden_streak|4
rest_last_error|HTTP 403 4/4 entries; backoff 720s
rest_last_error_at|2026-05-31 23:08:54
rest_backoff_until|2026-05-31 23:20:54
rest_last_ok_at|2026-05-31 22:50:31
```

这说明 REST 并非从未恢复：`2026-05-31 22:50:31` 曾恢复过一次，之后又进入 403 退避。

## 4. 当前运行状态判断

截至本摘要生成前的只读检查：

```text
last_ingested_at|2026-05-31 23:13:04
last_ingested_id|20260531231304165800
last_startup_at|2026-05-31 19:53:51
last_catchup_at|2026-05-31 22:47:48
last_gap_summary_telegram_at|2026-05-31 22:28:23
```

24h 入库来源概况：

```text
catchup_auto|2026-05-31 22:26:51|115
rest|2026-05-31 22:30:12|47
ws|2026-05-31 23:13:04|55
ws_initial|2026-05-31 21:32:31|13
```

判断：

- WebSocket 实时主路正常。
- Telegram realtime 最近有多条 `sent`，发送链路不是全局坏掉。
- REST 仍反复 403，但状态已经可视化、可追踪。
- 自动补拉仍依赖 REST，因此在 REST 403 时会降级或失败。
- 当前不应再继续打磨 `/system`，可以进入下一阶段。

## 5. 重要边界

继续保持：

- 不继续扩展旧 `jin10_monitor.py --dashboard` 原型。
- 正式 Dashboard 入口仍是 `run_dashboard.py + dashboard/`。
- Dashboard 不请求金十 REST。
- Dashboard 不触发补拉。
- Dashboard 不发送、不重试 Telegram。
- 不自动重发 `unknown_timeout`。
- 成功去重仍以 `delivery_log` 为准。
- 不写业务历史库。
- 不接模型 API。

## 6. 下一步建议

### P0：文档英文正文统一改中文

目标：

- 把 `docs/status` 和 `docs/design` 中英文正文统一改为中文。
- 文件名保留英文。
- 代码块、命令、路由、环境变量、类名、函数名、commit hash 保留英文。
- 已经是中文的正文不改。
- 不改代码。
- 不改历史事实。

优先处理明显英文文档：

```text
docs/design/003-phase2b-phase3-spec.md
docs/status/034-2026-05-23-dashboard-phase1-handoff.md
docs/status/035-2026-05-24-dashboard-phase2a-handoff.md
docs/status/036-2026-05-24-dashboard-ux-phase3-planning-handoff.md
docs/status/037-2026-05-25-dashboard-phase3-spec-handoff.md
docs/status/038-2026-05-29-dashboard-v2-bugfix-plan-handoff.md
docs/status/039-2026-05-31-realtime-ingest-dashboard-v2-handoff.md
```

建议做法：

1. 先只读统计英文正文范围，给修改计划。
2. 等确认后分批翻译，不要一次改太多。
3. 每批只做 Markdown 翻译，不碰代码。
4. 翻译后用 `git diff --check` 验证。
5. 可用人工抽查重点边界段落：不做什么、验证结果、下一步建议。

### P1：替代补拉源设计评估

等文档中文化完成后，再评估 REST 长期 403 下的替代补拉源。

原则：

- 先设计，不急着实现。
- 不从 Dashboard 请求金十 REST。
- 不让 Dashboard 成为采集入口。
- 不破坏 WebSocket 实时主路。
- 不改 Telegram 去重语义。

### P2：行情叠加 / 币安价格 API

暂缓。

原因：

- 行情叠加能改善分析体验，但不能解决当前 REST 补拉退化。
- 当前最大风险是补拉源不稳定，而不是缺少价格图。
- 行情 adapter 已有边界，可以等补拉问题更清楚后再推进。

## 7. 模型建议

### 文档中文化能否用 GPT-5.5 低？

结论：可以用于小批量机械翻译初稿，但不建议全程只用 GPT-5.5 低。

原因：

- 这批文档包含很多项目边界：不请求 REST、不写业务库、不重发 Telegram、Provider Adapter 边界、Phase 计划。
- 翻译不是文学润色，而是项目交接事实迁移；如果低档模型漏掉否定词、边界词或时间线，会影响后续开发判断。
- 需要保留命令、路由、env var、commit hash 和代码块不变，这类“半翻译半保留”的任务比纯翻译更容易出错。

推荐：

- 如果只翻译 1 个短文档：GPT-5.5 低可以尝试，但必须人工或 GPT-5.5 中复核 diff。
- 如果批量翻译上述 7 个文档：建议 GPT-5.5 中。
- 如果同时要重整路线图、合并矛盾、判断哪些旧文档过时：用 GPT-5.5 高。

本项目下一步“只翻译英文正文、中文不变、文件名保留英文”的任务，推荐用：

```text
GPT-5.5 中
```

## 8. 下一 session 提示词

```text
请继续 /Users/rich/jin10-monitor 项目。

建议模型：GPT-5.5 中。下一步是文档中文化：把 docs/status 和 docs/design 中从中期开始出现的英文正文统一改成中文；文件名、代码块、命令、路由、环境变量、commit hash 保留英文；已经是中文的正文不改。不要改代码，不要改历史事实。

先读取：
1. /Users/rich/jin10-monitor/AGENTS.md
2. /Users/rich/jin10-monitor/docs/status/040-2026-05-31-rest-status-dashboard-handoff.md
3. /Users/rich/jin10-monitor/docs/status/039-2026-05-31-realtime-ingest-dashboard-v2-handoff.md
4. /Users/rich/jin10-monitor/docs/design/004-dashboard-v2-plan.md
5. /Users/rich/jin10-monitor/docs/design/003-phase2b-phase3-spec.md

先执行：
git branch --show-current
git status
git pull --rebase
git log --oneline -8

当前结论：
- 最新提交是 8ae7bd9 feat(runtime): persist rest backoff status。
- /system 只读运行诊断面板已完成并推送。
- REST 状态持久化已完成并推送。
- launchd 已 reload，常驻监控已加载 8ae7bd9。
- REST 当前仍是 forbidden_backoff，连续 403 会写入 runtime_state 并显示到 /system。
- WebSocket 实时主路正常，Telegram realtime 最近有 sent。
- 不接模型 API，不请求金十 REST from dashboard，不写业务历史库，不自动重发 Telegram unknown_timeout。

下一步：
先只读统计 docs/status 和 docs/design 中英文正文范围，给修改计划并等确认；确认后分批把英文正文翻译成中文，中文正文不变。
```
