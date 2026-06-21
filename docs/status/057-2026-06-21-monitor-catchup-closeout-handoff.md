# 057 - Monitor 恢复收口、Dashboard 清理与补拉续跑

更新时间：2026-06-21 17:30（Asia/Shanghai）

当前分支：`main`

当前最新提交：`57ea37f feat(monitor): add resumable catchup checkpoints`

## 背景

本轮从一次真实生产故障继续推进：采集服务曾因本地 `.env` 中 `CHATGPT_PROXY_LABEL=ChatGPT Proxy` 含空格，被旧 `scripts/run_monitor.sh` 的 shell `source .env` 解析打挂，launchd 反复以 `127` 退出，Telegram 推送和业务入库静默中断约 6 天。

恢复过程中还发现两个长期问题：

- 旧内嵌 Dashboard 原型仍留在 `jin10_monitor.py`，和正式 `run_dashboard.py + dashboard/` 架构重复。
- REST 长窗口补拉在 `403` 或网络抖动下容易中断，用户需要手动计算下一次从哪里继续。

## 已完成并推送

### 启动防护

提交：`6320a8c fix(monitor): harden launchd dotenv loading`

- 新增 `scripts/run_monitor.py`，使用 `python-dotenv` 加载 `.env`，避免 shell 解析含空格值。
- `scripts/run_monitor.sh` 不再 `source .env`，只负责进入项目目录、准备日志目录并启动 Python wrapper。
- 保留 `os.execv()` 语义，让 launchd 跟踪真正的 `jin10_monitor.py` 进程。

后续提交：`5b2096c fix(monitor): harden launcher and catchup retries`

- `scripts/run_monitor.py` 不再二次硬编码 `.venv/bin/python`。
- 改用当前运行 wrapper 的 `sys.executable` 接力执行 `jin10_monitor.py`，降低迁移到不同 Python 环境时的路径失配风险。

### Dashboard 死代码清理

提交：`307ffff refactor(dashboard): retire embedded dashboard`

- 删除 `jin10_monitor.py` 旧内嵌 HTTPServer Dashboard 原型和相关 HTML 拼接代码。
- 保留采集、Telegram、历史查询、Dashboard 深链等业务函数。
- `python jin10_monitor.py --dashboard` 不再启动旧页面，改为友好提示使用：

```bash
.venv/bin/python run_dashboard.py --host 127.0.0.1 --port 8765
```

已验证独立 Dashboard `/healthz` 可正常返回，且仍保持只读边界：

- `writes_business_db=false`
- `calls_jin10_rest=false`
- `sends_telegram=false`

### WebSocket initial history 补拉可见性

提交：`4364a35 fix(monitor): restore summary catchup visibility`

- WebSocket 重连收到 initial history 快照时，新入库消息仍只入库，不逐条刷屏。
- 如果有新增内容，会发一条“金十重连补拉完成”摘要，记录 `mode=ws_initial_summary`。
- 单条历史消息不写 `delivery_log`，避免误判为已经逐条推送过。

### 手动补拉分窗口容错

提交：`5b2096c fix(monitor): harden launcher and catchup retries`

- `--catch-up-window-minutes` 分窗口补拉遇到单个子窗口失败后，会继续尝试下一窗口。
- 连续 2 个子窗口失败才停止，减少一次网络抖动跳过全部后续窗口的概率。
- 汇总逻辑会继续统计失败之后的成功窗口，但不会把失败窗口误当成功。

### 手动补拉断点续跑

提交：`57ea37f feat(monitor): add resumable catchup checkpoints`

- 带 `--catch-up-window-minutes` 的手动补拉会在 `runtime_state` 写入断点：
  - `catch_up_checkpoint`
  - `catch_up_checkpoint_original_start`
  - `catch_up_checkpoint_target_end`
  - `catch_up_checkpoint_window_minutes`
- 断点只推进到“从起点开始连续成功”的窗口末尾。
- 如果中间某个窗口失败，即使后续窗口成功，断点也不会越过失败窗口，避免漏补。
- 完整补拉成功后自动清空断点。
- 新增 `--resume`：

```bash
.venv/bin/python jin10_monitor.py --catch-up \
  --resume \
  --no-catch-up-telegram \
  --catch-up-max-send 0
```

`--resume` 默认使用断点里的目标结束时间和窗口分钟数，也可以用 `--to` 覆盖结束时间。

## 当前状态

### Git

- `main` 已推送到 `origin/main`。
- 当前最新提交为 `57ea37f`。
- 上次提交后工作树为干净状态。

### 采集主路

- WebSocket 仍是实时主路。
- REST 仍可能出现 `403 forbidden_backoff`，不能把 REST 失败误判为整体采集中断。
- Telegram 补拉策略保持不变：自动补拉、重连补拉只发摘要，不逐条刷屏。

### 历史缺口

`2026-06-18 11:00:00` 到 `2026-06-18 22:59:59` 仍需补入本地库。之前尝试小窗口补拉时 REST 仍返回 `HTTP 403`，未能补齐。

建议下一轮使用新的断点续跑能力，仍然只入库、不发 Telegram：

```bash
.venv/bin/python jin10_monitor.py --catch-up \
  --from "2026-06-18 11:00:00" \
  --to "2026-06-18 23:00:00" \
  --no-catch-up-telegram \
  --catch-up-max-send 0 \
  --catch-up-window-minutes 30
```

如果失败，等待冷却后再执行：

```bash
.venv/bin/python jin10_monitor.py --catch-up \
  --resume \
  --no-catch-up-telegram \
  --catch-up-max-send 0
```

不要连续硬打 REST，避免加重退避。

## 验证

本轮关键验证已执行过：

```bash
.venv/bin/python -m py_compile jin10_monitor.py
.venv/bin/python -m py_compile scripts/run_monitor.py
.venv/bin/python -m pytest tests/test_storage.py tests/test_dashboard_analysis.py tests/test_pure_functions.py -q
.venv/bin/python -m pytest tests/test_dashboard_db.py -q
.venv/bin/python -m pytest -q
git diff --check
```

结果：

- `tests/test_storage.py tests/test_dashboard_analysis.py tests/test_pure_functions.py`：`175 passed`
- `tests/test_dashboard_db.py`：`24 passed`
- 全量测试：`214 passed`
- `git diff --check`：通过

## 下一步建议

P0：

1. 用新的 `--resume` 机制继续补 `2026-06-18 11:00-23:00` 缺口，只入库、不发 Telegram。
2. 如果 REST 继续 `403`，停止并等待冷却，不要连续硬打。

P1：

1. 实现 Telegram 健康心跳：
   - `HEALTH_HEARTBEAT_INTERVAL_S` 默认 6 小时。
   - 设为 `0` 可关闭。
   - 文案短，例如：

```text
✅ Monitor 在线 · 06-21 17:30
last_ingested_at: 2026-06-21 17:29:xx
```

2. `/system` 增加最近 monitor 错误日志只读诊断：
   - 只读 `logs/jin10-monitor.log` 尾部。
   - 展示最近 `ERROR`、`command not found` 等行。
   - 不调用 `launchctl`，不触发采集、REST 或 Telegram。

P2：

1. 外部监控 `/healthz` 文档化或接入本地/远端监控。
2. Provider A/B 偏好投票、compare 高亮等分析体验项继续暂缓，不要和采集恢复混在一起。

## 下一 session 提示词

```text
继续 /Users/rich/jin10-monitor。

先读取 AGENTS.md、CHANGELOG.md、README.md 的“离线补拉”段，以及 docs/status/057-2026-06-21-monitor-catchup-closeout-handoff.md。
当前 main 最新提交应为：
57ea37f feat(monitor): add resumable catchup checkpoints

当前边界：
- Telegram 补拉策略不变：自动/重连补拉只发摘要，不逐条刷屏。
- WebSocket 实时主路不改。
- Dashboard 已迁移到 run_dashboard.py；jin10_monitor.py 只保留 --dashboard 迁移提示。
- 手动分窗口补拉已有 --resume，断点存在 runtime_state，不新建表。
- REST 仍可能 403，补缺口要保守，不要连续硬打。

下一步优先：
1. 用 --resume 机制尝试补 `2026-06-18 11:00:00` 到 `2026-06-18 23:00:00` 缺口，只入库、不发 Telegram：
   .venv/bin/python jin10_monitor.py --catch-up --from "2026-06-18 11:00:00" --to "2026-06-18 23:00:00" --no-catch-up-telegram --catch-up-max-send 0 --catch-up-window-minutes 30
   如果失败，等待冷却后：
   .venv/bin/python jin10_monitor.py --catch-up --resume --no-catch-up-telegram --catch-up-max-send 0
2. 评估并实现 Telegram 健康心跳：
   - HEALTH_HEARTBEAT_INTERVAL_S 默认 6h。
   - 设为 0 可关闭。
   - 不写单条 delivery_log，不改变新闻推送去重。
3. 评估 /system 最近 monitor 错误日志只读诊断。

验证要求：
- .venv/bin/python -m py_compile jin10_monitor.py
- .venv/bin/python -m pytest tests/test_storage.py tests/test_dashboard_analysis.py tests/test_pure_functions.py -q
- .venv/bin/python -m pytest -q
- git diff --check
- 如果改 dashboard，额外 smoke /healthz。

完成后更新 CHANGELOG.md，按日期分组。
未经确认不要 commit/push；如果我说 commit+push，再按 AGENTS.md commit 格式执行。

模型建议：GPT-5.5 高。
```

