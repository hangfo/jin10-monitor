# 059 - /system 最近 monitor 错误日志诊断与心跳上线观察

更新时间：2026-06-22 00:20（Asia/Shanghai）

当前分支：`main`

## 背景

本轮从 `058-2026-06-22-monitor-heartbeat-review-closeout.md` 继续，边界保持不变：

- WebSocket 实时主路不改。
- 自动补拉和 WebSocket initial history 只发摘要，不逐条刷屏。
- Telegram 健康心跳默认 `HEALTH_HEARTBEAT_INTERVAL_S=21600`，设为 `0` 可关闭。
- 心跳只记录 `mode=health_heartbeat` 和 `last_health_heartbeat_at`，不写 `delivery_log`。
- 手动分窗口补拉继续使用 `--resume` 与终端进度提示。
- REST 仍可能 403，补缺口保持保守，不连续硬打。

## 本轮完成

### 生产心跳观察

- 当前 `main` 已确认在 `49555f8 feat(monitor): add health heartbeat`。
- 已执行 `./scripts/launchd/manage.sh reload`，让生产 launchd 进程加载当前代码。
- `./scripts/launchd/manage.sh status` 显示服务 `running`，新 pid 为 `32214`。
- 日志确认心跳任务已经启动：

```text
00:18:19 [INFO] health_heartbeat: 每 6.0h 发送一次心跳
```

心跳循环当前设计是启动后先 `sleep(HEALTH_HEARTBEAT_INTERVAL_S)`，所以 reload 后不会立刻发 Telegram。按 `2026-06-22 00:18:19` 启动时间估算，下一条真实健康心跳应在 `2026-06-22 06:18` 左右出现，仍需继续观察 Telegram 和 `telegram_delivery_status(mode='health_heartbeat')`。

### 6 月 18 日缺口补拉

已执行：

```bash
.venv/bin/python jin10_monitor.py --catch-up \
  --from "2026-06-18 11:00:00" \
  --to "2026-06-18 23:00:00" \
  --no-catch-up-telegram \
  --catch-up-max-send 0 \
  --catch-up-window-minutes 30
```

结果：

- REST 仍返回 `HTTPError: HTTP Error 403: Forbidden`。
- 连续 2 个 30 分钟子窗口失败后停止后续窗口。
- 入库 `0` 条，候选发送 `0` 条，没有 Telegram 发送。
- 断点仍保留在 `2026-06-18 11:00:00`，目标结束时间为 `2026-06-18 23:00:00`，窗口为 `30` 分钟。

当前断点：

```text
catch_up_checkpoint=2026-06-18 11:00:00
catch_up_checkpoint_original_start=2026-06-18 11:00:00
catch_up_checkpoint_target_end=2026-06-18 23:00:00
catch_up_checkpoint_window_minutes=30
```

### /system 最近 monitor 错误日志

已在 Dashboard `/system` 增加“最近 monitor 错误日志”只读面板：

- 只读取本地 `logs/jin10-monitor.log` 尾部。
- 只筛选最近 `ERROR`、`command not found`、`Traceback`、`Exception` 行。
- 日志缺失时显示空状态，不影响 `/system` 页面渲染。
- 不触发补拉、不请求金十 REST、不写 SQLite、不发送 Telegram。

真实库 smoke 结果显示当前可见的最近错误主要是 Telegram `TimeoutError()` 与 `ClientConnectorError`，这能帮助快速区分本地 monitor 运行、REST 403 与 Telegram 网络问题。

## 验证

```bash
.venv/bin/python -m py_compile jin10_monitor.py
.venv/bin/python -m pytest tests/test_dashboard_db.py::test_query_recent_monitor_log_events_reads_error_tail tests/test_dashboard_db.py::test_query_recent_monitor_log_events_handles_missing_file tests/test_dashboard_analysis.py::test_analyze_templates_show_selection_hints_and_asset_market_sync -q
.venv/bin/python -m pytest tests/test_storage.py tests/test_dashboard_analysis.py tests/test_pure_functions.py -q
.venv/bin/python -m pytest -q
git diff --check
```

结果：

- 针对性测试：`3 passed`
- 核心测试集：`178 passed`
- 全量测试：`219 passed`
- `git diff --check`：通过

额外 smoke：

```bash
.venv/bin/python run_dashboard.py --host 127.0.0.1 --port 8766
curl -s http://127.0.0.1:8766/healthz
curl -v --max-time 10 http://127.0.0.1:8766/system
```

结果：

- `/healthz` 返回 `status=ok`，且保持 `writes_business_db=false`、`calls_jin10_rest=false`、`sends_telegram=false`。
- `/system` 返回 `200 OK`，页面包含“最近 monitor 错误日志”和真实 Telegram timeout 错误行。
- 8766 临时服务已停止，正式 8765 dashboard 进程未在本轮重启。

## 当前边界

- WebSocket 实时主路未修改。
- `jin10_monitor.py` 采集、补拉和 Telegram 投递语义未修改。
- `/system` 新增能力是只读日志展示，不会请求外部源或写业务库。
- 健康心跳已在生产进程启动，但真实 Telegram 心跳还需等默认 6 小时间隔后观察。
- REST 仍处于可能 403 的状态，缺口补拉继续使用 `--resume` 保守续跑。

## 下一步建议

P0：

1. 在 `2026-06-22 06:18` 后检查 Telegram 是否出现健康心跳，并查询：

```bash
sqlite3 data/jin10_history.sqlite3 "select message_id, mode, status, detail, updated_at from telegram_delivery_status where mode='health_heartbeat' order by updated_at desc limit 5;"
sqlite3 data/jin10_history.sqlite3 "select key, value, updated_at from runtime_state where key='last_health_heartbeat_at';"
```

2. REST 冷却后再用断点续补：

```bash
.venv/bin/python jin10_monitor.py --catch-up \
  --resume \
  --no-catch-up-telegram \
  --catch-up-max-send 0
```

P1：

1. 观察 `/system` 最近 monitor 错误日志是否能帮助区分 Telegram 网络超时、REST 403 和本地启动错误；如果错误行太多，再考虑加状态分类或时间列解析。
2. 如果正式 8765 dashboard 需要立即展示新面板，单独 reload dashboard 进程；本轮只用 8766 临时 smoke，未重启 8765。

P2：

1. 外部 `/healthz` 监控或本地提醒方案文档化，作为 Telegram 心跳之外的第二层告警。
2. 心跳和缺口补拉稳定后，再回到第一轮 Provider A/B 实验。

## 下一 session 提示词

```text
继续 /Users/rich/jin10-monitor。

先读取 AGENTS.md、CHANGELOG.md、README.md 的“离线补拉”段，以及 docs/status/059-2026-06-22-system-monitor-log-diagnostics-handoff.md。
当前 main 最新提交应包含 /system 最近 monitor 错误日志只读诊断。

当前边界：
- WebSocket 实时主路不改。
- 自动补拉和 WebSocket initial history 只发摘要，不逐条刷屏。
- Telegram 健康心跳已在生产进程启动，默认 HEALTH_HEARTBEAT_INTERVAL_S=21600，启动后先等 6 小时再发。
- 心跳只记录 mode=health_heartbeat 和 last_health_heartbeat_at，不写 delivery_log。
- 手动分窗口补拉已有 --resume 和终端进度提示。
- REST 仍可能 403，补缺口要保守，不要连续硬打。
- /system 最近 monitor 错误日志只读扫描 logs/jin10-monitor.log 尾部，不触发 REST/Telegram/写库。

下一步优先：
1. 在 2026-06-22 06:18 后验证生产 Telegram 健康心跳是否出现，并检查 telegram_delivery_status(mode='health_heartbeat') 与 last_health_heartbeat_at。
2. 继续尝试补 2026-06-18 11:00:00 到 2026-06-18 23:00:00 缺口，只入库、不发 Telegram：
   .venv/bin/python jin10_monitor.py --catch-up --resume --no-catch-up-telegram --catch-up-max-send 0
3. 如果要让正式 8765 dashboard 立刻显示 /system 新日志面板，单独 reload dashboard；否则等下次自然重启也可以。

验证要求：
- .venv/bin/python -m py_compile jin10_monitor.py
- .venv/bin/python -m pytest tests/test_storage.py tests/test_dashboard_analysis.py tests/test_pure_functions.py -q
- .venv/bin/python -m pytest -q
- git diff --check

模型建议：GPT-5.5 中。若同时改采集/Telegram 投递语义，再用 GPT-5.5 高。
```
