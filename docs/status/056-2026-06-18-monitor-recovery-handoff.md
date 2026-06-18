# 056 - Monitor 恢复、补拉与启动防护

更新时间：2026-06-18 07:18（Asia/Shanghai）

当前分支：`main`

## 背景

用户反馈 Telegram 推送停在 `2026-06-12`，Dashboard 快讯流最近 24h 为空。排查发现 Dashboard 仍在运行，但采集主服务 `com.rich.jin10-monitor` 反复退出：

- `launchctl`：`last exit code = 127`
- 日志：`.env:38: command not found: Proxy`
- 本地业务库最新游标：`2026-06-12 00:51:18`

根因是本地 `.env` 中 `CHATGPT_PROXY_LABEL=ChatGPT Proxy` 含空格，旧 `scripts/run_monitor.sh` 使用 shell `source .env`，导致 shell 把 `Proxy` 当成命令执行。该配置属于本地实验项，不进入 Git；代码侧需要避免未来任何带空格 env 值再次打挂采集服务。

## 已处理

### 启动防护

- 新增 `scripts/run_monitor.py`：
  - 使用 `python-dotenv` 加载 `.env`。
  - `override=True` 保持旧 `source .env` 的覆盖语义。
  - 加载后 `os.execv()` 启动 `.venv/bin/python jin10_monitor.py`。
- 修改 `scripts/run_monitor.sh`：
  - 不再 `source .env`。
  - 只负责进入项目目录、确保 `logs/` 存在，并执行 `scripts/run_monitor.py`。
- 增加测试保护：`test_run_monitor_loads_dotenv_without_shell_source()`。

### 历史恢复

已手动补拉并只写本地业务库，不补发历史 Telegram：

- 从原最新游标 `2026-06-12 00:51:18` 开始补拉。
- 本地库从 `30592` 条恢复到 `35880+` 条。
- `2026-06-12` 到 `2026-06-17 18:00`、以及 `2026-06-18 00:00` 后窗口已有补入。
- 实时 WebSocket 恢复后，最新快讯继续入库并实时推送 Telegram。

### 实时恢复

`com.rich.jin10-monitor` 已恢复运行，日志显示：

- WebSocket 已连接。
- WebSocket initial history 已新入库。
- 实时消息已继续入库。
- Telegram 实时发送恢复。

## 当前残留

### REST 403 退避

金十 REST 目前仍可能返回 `403`，`runtime_state.rest_status=forbidden_backoff`。这不会阻塞 WebSocket 实时主路，但会影响历史补拉和 REST 兜底。

### 明确缺口

`2026-06-17 18:00:00` 到 `2026-06-18 00:00:00` 仍未补入，原因是两个 `app_id` 在冷却后小窗口补拉仍返回 `HTTP 403`。

建议不要连续硬打接口。等待 REST 恢复或冷却更久后，再按 30 分钟或 1 小时窗口执行：

```bash
.venv/bin/python jin10_monitor.py --catch-up \
  --from "2026-06-17 18:00:00" \
  --to "2026-06-17 19:00:00" \
  --no-catch-up-telegram \
  --catch-up-max-store 1000 \
  --catch-up-max-send 0
```

失败两轮后停止，避免加重退避。

## 验证

已执行：

```bash
zsh -n scripts/run_monitor.sh
.venv/bin/python -m py_compile scripts/run_monitor.py
.venv/bin/python -m pytest tests/test_dashboard_analysis.py -q
.venv/bin/python -m pytest -q
git diff --check
curl -s http://127.0.0.1:8765/api/feed/latest-ts
```

结果：

- `tests/test_dashboard_analysis.py`：`68 passed`
- 全量测试：`210 passed`
- `git diff --check`：通过
- launchd kickstart 后 monitor 通过新 wrapper 启动，无新增 `.env:38` 报错。
- WebSocket 已连接，`/api/feed/latest-ts` 已推进到 `2026-06-18 07:16:38`。

## 下一步建议

P0：

1. 保持 WebSocket 实时主路在线。
2. 不补发历史 Telegram。
3. 等 REST 403 冷却后补 `2026-06-17 18:00-24:00`。

P1：

1. 如大窗口补拉继续不稳，单独设计 `catch_up_window` 的断点续补 / 自动切小窗口，不和本次启动修复混在一个 commit。
2. `/system` 可考虑增加“launchd 上次退出码 / 最近启动失败原因”只读诊断，降低类似问题的发现成本。

暂缓：

- webchat2api / ChatGPT proxy 继续留在实验边界，不进入 `main`。
- Anthropic Provider、公共 ChatGPT proxy 继续暂缓。
