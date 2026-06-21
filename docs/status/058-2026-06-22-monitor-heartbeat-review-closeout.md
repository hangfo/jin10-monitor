# 058 - Review 057 采纳、健康心跳与补拉进度收口

更新时间：2026-06-22 00:12（Asia/Shanghai）

当前分支：`main`

## 背景

本轮从 `/Users/rich/Downloads/jin10-review-057-diff.md` 继续。该 review 覆盖 `4364a35` 到 `4981335` 的 3 个提交，核心结论是：

- `sys.executable`、`consecutive_errors` 和 `--resume` 断点续补已经落地。
- checkpoint 系统的“宽容执行、保守记录”设计正确。
- 仍需补齐 Telegram 主动健康心跳，避免再次出现服务静默停摆多天才被发现。
- 分窗口补拉的终端反馈和 `merge_catchup_results` 注释可以小修。

## Review 057 逐项处理结论

### 已采纳

- **Telegram 差异化健康心跳**：已实现 `HEALTH_HEARTBEAT_INTERVAL_S`，默认 6 小时，范围 `0-604800`，设为 `0` 可关闭。心跳按 `last_ingested_at` 新鲜度区分：
  - 5 分钟内：`✅ Monitor 正常`
  - 5 到 30 分钟：`⚠️ Monitor 已 N 分钟无入库`
  - 超过 30 分钟：`🚨 Monitor 已 N 分钟无入库，请检查`
  - 无游标：`🚨 Monitor 无入库游标`
- **心跳不污染新闻投递语义**：心跳只记录 `telegram_delivery_status` 的 `mode=health_heartbeat` 和 `runtime_state.last_health_heartbeat_at`，不写 `delivery_log`。
- **补拉断点进度**：`print_catchup_summary` 会基于 `original_start` / `target_end` / `next_start` 显示整体进度，例如 `进度: 50.0%（已完成 360/720 分钟）`。
- **失败窗口聚合注释**：`merge_catchup_results` 中 `ok=False` 子窗口会跳过聚合，并补充注释说明失败窗口没有可靠入库/候选发送数据，后续成功窗口仍可继续聚合。
- **去重文案**：终端输出从“已存在未重复入库”改为“去重跳过（已存在）”。

### 暂缓

- **`delete_state` 独立测试**：当前已有 `clear_catchup_checkpoint` 集成覆盖，`DELETE` 不存在键为 SQLite no-op，风险低；不为一行 wrapper 单独扩大本轮 runtime 变更。
- **`/system` 最近错误日志诊断**：仍有价值，但属于 Dashboard 只读诊断增强，适合下一轮单独做，避免和常驻心跳改动混在一起。
- **compare 偏好投票 / news_id 交叉高亮**：属于 Provider A/B 体验增强，不应插入本轮监控可靠性修复。
- **第一轮 Provider A/B 实验**：不需要代码改动，建议在补齐 6 月 18 日缺口和心跳上线后再执行。

### Review 文档中的小误差

`057-diff.md` 的 `CATCHUP_CHECKPOINT_KEYS` 示例把 `next_start` 写成 `catch_up_checkpoint_next_start`。当前代码实际把 `next_start` 存在 `catch_up_checkpoint`，其余 `original_start`、`target_end`、`window_minutes` 为独立键。该误差不影响 review 的主要判断。

## 已完成

- 新增 `format_health_heartbeat_message()` 和 `health_heartbeat_loop()`。
- `main()` 在 WebSocket、REST 预加载/轮询和启动补拉任务之后追加 `health_heartbeat` 后台任务，不改变实时主路优先启动顺序。
- `.env.example` 和 `README.md` 补充 `HEALTH_HEARTBEAT_INTERVAL_S`。
- `CHANGELOG.md` 增加 2026-06-22 记录。
- 测试新增：
  - 心跳文案分级。
  - 心跳发送状态记录但不写 `delivery_log`。
  - 补拉断点进度计算。
  - `main()` 启动任务顺序包含 `health_heartbeat` 且位于已有任务之后。

## 验证

```bash
.venv/bin/python -m py_compile jin10_monitor.py
.venv/bin/python -m pytest tests/test_pure_functions.py::test_format_health_heartbeat_message_levels_by_staleness tests/test_pure_functions.py::test_catchup_checkpoint_progress_text_uses_original_window tests/test_storage.py::test_health_heartbeat_loop_records_status_without_delivery_log tests/test_storage.py::test_main_schedules_websocket_before_rest_startup_tasks -q
.venv/bin/python -m pytest tests/test_storage.py tests/test_dashboard_analysis.py tests/test_pure_functions.py -q
.venv/bin/python -m pytest -q
git diff --check
```

结果：

- 针对性测试：`4 passed`
- 核心测试集：`178 passed`
- 全量测试：`217 passed`
- `git diff --check`：通过

## 当前边界

- WebSocket 实时主路不改。
- REST `403` 仍按既有退避语义处理，不把 REST 失败误判为整体采集中断。
- 自动补拉和 WebSocket initial history 仍只发摘要，不逐条刷屏。
- 心跳是运行状态消息，不是新闻消息，不进入 `delivery_log`。
- Dashboard 仍由 `run_dashboard.py + dashboard/` 负责，旧 `jin10_monitor.py --dashboard` 只保留迁移提示。

## 下一步建议

P0：

1. 部署后观察下一条 Telegram 健康心跳是否按预期出现。
2. 继续尝试补 `2026-06-18 11:00:00` 到 `2026-06-18 23:00:00` 的历史缺口，只入库、不发 Telegram；如果 REST 继续 `403`，等待冷却后用 `--resume` 续跑。

P1：

1. 做 `/system` 最近 monitor 错误日志只读诊断，展示最近 `ERROR`、`command not found` 等行。
2. 将外部 `/healthz` 监控或本地提醒方案文档化，作为 Telegram 心跳之外的第二层告警。

P2：

1. 执行第一轮 Provider A/B 实验。
2. 继续 compare 偏好投票和 `news_id` 交叉高亮。

## 下一 session 提示词

```text
继续 /Users/rich/jin10-monitor。

先读取 AGENTS.md、CHANGELOG.md、README.md 的“离线补拉”段，以及 docs/status/058-2026-06-22-monitor-heartbeat-review-closeout.md。

当前边界：
- WebSocket 实时主路不改。
- 自动补拉和 WebSocket initial history 只发摘要，不逐条刷屏。
- Telegram 健康心跳已实现，默认 HEALTH_HEARTBEAT_INTERVAL_S=21600，设为 0 可关闭。
- 心跳只记录 mode=health_heartbeat 和 last_health_heartbeat_at，不写 delivery_log。
- 手动分窗口补拉已有 --resume 和终端进度提示。
- REST 仍可能 403，补缺口要保守，不要连续硬打。

下一步优先：
1. 观察/验证生产 Telegram 健康心跳是否按预期出现。
2. 继续尝试补 `2026-06-18 11:00:00` 到 `2026-06-18 23:00:00` 缺口，只入库、不发 Telegram：
   .venv/bin/python jin10_monitor.py --catch-up --from "2026-06-18 11:00:00" --to "2026-06-18 23:00:00" --no-catch-up-telegram --catch-up-max-send 0 --catch-up-window-minutes 30
   如果失败，等待冷却后：
   .venv/bin/python jin10_monitor.py --catch-up --resume --no-catch-up-telegram --catch-up-max-send 0
3. 评估并实现 /system 最近 monitor 错误日志只读诊断。

验证要求：
- .venv/bin/python -m py_compile jin10_monitor.py
- .venv/bin/python -m pytest tests/test_storage.py tests/test_dashboard_analysis.py tests/test_pure_functions.py -q
- .venv/bin/python -m pytest -q
- git diff --check
- 如果改 dashboard，额外 smoke /healthz。

完成后更新 CHANGELOG.md，按日期分组；如果我说 commit+push，再提交推送。

模型建议：GPT-5.5 中。若要同时改采集/Telegram 投递语义和 Dashboard 诊断，再用 GPT-5.5 高。
```
