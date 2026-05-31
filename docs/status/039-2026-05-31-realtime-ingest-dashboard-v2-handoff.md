# 039 - 实时入库恢复和 Dashboard V2 交接

日期：2026-05-31

更新时间：2026-05-31（Asia/Shanghai）

## 当前状态

最新已推送提交：

```text
26b7d7e feat(dashboard): add compare analysis and resilient realtime ingest
```

推送后的分支状态：

```text
main...origin/main
```

独立 Dashboard 入口仍是：

```text
run_dashboard.py + dashboard/
```

不要通过扩展旧 `jin10_monitor.py --dashboard`
原型来继续工作。

## 本 session 已完成内容

本 session 完成了两条线：

1. Dashboard V2 第二轮功能
2. 实时入库 / Telegram 事故诊断与加固

代码已提交并推送为：

```text
26b7d7e feat(dashboard): add compare analysis and resilient realtime ingest
```

## Dashboard V2 新增内容

新增分析对比：

- `GET /analyze/compare`
- `dashboard/templates/analyze_compare.html`
- `analysis_db.get_runs_for_compare()`
- history page 支持 checkbox 选择两条 run
- run detail 中的重新分析和对比快捷入口

新增 adapter 边界：

- `dashboard/providers/`，用于未来 Phase 2B LLM providers
- OpenAI 和 Anthropic provider stubs，目前只检查 env configuration
- `dashboard/market/`，用于未来 price overlay adapters
- `GET /api/market/klines` 占位端点；未配置 market adapter 时返回空 fallback

新增 UI / status polish：

- system page provider 状态面板
- 补齐 `.pill.normal`、`tr.row-normal` 和 `tr.row-none` CSS
- 增加 comparison 导航链接

## 事故诊断

观察到的用户症状：

- Telegram 在此前成功发送后停止推送。
- Dashboard 显示重复 Telegram timeout 状态。
- Dashboard 最新快讯落后于金十网站。
- 金十网站已有最新的真主党消息，但 dashboard 在 monitor 重启前没有显示。

发现：

- Telegram bot token 和 chat id 有效。
- Telegram API 可达：
  - `getMe`：HTTP 200
  - `getChat`：HTTP 200
  - `sendChatAction`：HTTP 200
  - live diagnostic `sendMessage`：`sent`
- 金十 REST endpoint 对所有已配置 app ids 和 modes 持续返回 403：
  - channel + app id 1：403
  - channel + app id 2：403
  - legacy + app id 1：403
  - legacy + app id 2：403
- 金十 WebSocket 可达，但运行中的 monitor 进入了疑似 half-open connection 状态：进程仍存活，REST 仍在循环，但 WebSocket 没有产生新的历史行。

结论：

- Telegram 不是被 dashboard 代码破坏的。
- REST 403 是外部 access-policy / endpoint-compatibility 问题。
- Dashboard 落后是由 REST 被阻断，加上 WebSocket 闲置或 half-open 后没有重连导致。

## 已合并实时加固

`jin10_monitor.py` 变更：

- 新增 `WS_IDLE_TIMEOUT`
- WebSocket receive loop 现在使用应用层 idle timeout，在配置窗口内没有消息时重连
- 新增 `REST_FORBIDDEN_BACKOFF_SECONDS`
- `poll_once()` 现在会在所有 REST entries 返回 403 后退避
- 重复 403 日志改为摘要输出，而不是每几秒刷一条
- REST 被阻断时，WebSocket 仍是 realtime primary path

测试：

- 新增 `test_poll_once_backs_off_after_all_rest_entries_return_403`

运行操作：

- 代码变更后已 reload launchd service
- dashboard server 仍可通过 `http://127.0.0.1:8765` 访问

## 当前运行证据

reload 后，WebSocket 入库恢复：

```text
2026-05-31 13:31:34 | ws | 据韩联社：韩国与日本在国防会谈中讨论双边军事后勤支持协议。
2026-05-31 13:36:05 | ws | 国家数据局局长刘烈宏：高质量数据集是人工智能发展的核心基础
```

Telegram realtime delivery 也恢复：

```text
20260531133134591800 | realtime | sent
20260531133605275800 | realtime | sent
```

此前缺失的网站消息已通过 WebSocket initial history 恢复：

```text
2026-05-31 13:08:16 | ws_initial | 黎真主党称对以军发起多轮打击
```

REST 仍被阻断：

```text
REST 连续被 403 拒绝：4/4 个入口不可用，暂停 REST ...
```

这表示 realtime WebSocket 正常、Telegram 正常，但基于 REST 的 catch-up 在选择新的 REST-compatible source 或 request strategy 之前仍处于降级状态。

## 验证

自动验证：

```text
.venv/bin/python -m pytest -q
145 passed in 0.79s

git diff --check
no output
```

浏览器验证：

- dashboard feed 可在 `http://127.0.0.1:8765/` 加载
- 刷新后，真主党消息出现在 feed 中
- commit 前已对 `/analyze/history`、`/analyze/compare`、`/system` 和
  `/api/market/klines` 做 smoke test

Git 验证：

```text
git status --short --branch
## main...origin/main

git rev-parse HEAD
26b7d7ee9ad8c78e73df358dd1dc6a157ea10eaa

git rev-parse origin/main
26b7d7ee9ad8c78e73df358dd1dc6a157ea10eaa
```

## 重要边界

继续保持这些边界：

- 不继续扩展旧 `jin10_monitor.py --dashboard` 原型。
- 不从 dashboard 页面请求金十 REST。
- 不把分析输出写入业务历史 DB。
- 不自动重试 Telegram `unknown_timeout` 行；保留 success-only dedupe 语义。
- 不让 dashboard 启动依赖 OpenAI、Anthropic、market data 或任何外部 API。

## 建议的下一步顺序

建议下一步：在新增功能前先做 runtime diagnostics panel。

原因：

- 最近的问题不是缺少 UI 功能，而是可观测性不足。
- 系统已有诊断所需数据，但需要 shell / log / SQL inspection。
- system page panel 可以让下一次事故立即可见：
  - 最新 `ws` / `ws_initial` / `rest` row time
  - 最新 `last_ingested_at`
  - 最新 Telegram `sent`、`unknown_timeout` 和 `failed`
  - REST 403 backoff state，如果已持久化或可从最近 logs / status 推断
  - catch-up health 和最近 summary status

建议实现形态：

1. 为 runtime health 增加只读 dashboard DB helper(s)。
2. 增加紧凑的 `/system` "Realtime pipeline" panel。
3. 保持本地化，并从 SQLite / log 派生。
4. 暂不增加主动 retry 按钮。
5. 为 helper output 增加聚焦测试。

之后：

1. 如果 REST 仍是 403，评估 catch-up source replacement。
2. 然后继续可选 market overlay UI / adapter work。
3. Provider Adapter 应等 runtime health 更清楚后再做，因为手工分析流已经可用，而 provider calls 会增加 credentials、cost、timeout 和 error boundaries。

## 建议模型

- `GPT-5.5 中`：system status panel、handoff docs、小型 dashboard UI、comparison polish、只读 diagnostics。
- `GPT-5.5 高`：REST replacement research、provider streaming、credential/error boundaries，或复杂 market-data normalization / caching。

## 可直接复制的 next-session prompt

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
