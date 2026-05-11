# 项目状态摘要 012：.env 数值配置容错已完成

更新时间：2026-05-11 晚（Asia/Shanghai）

## 1. 这份文档的用途

本文件用于在新 session 中快速续接可靠性修复阶段，不需要回读旧聊天。

这份摘要重点覆盖：

- `.env` 数值配置容错已经完成什么。
- 当前 Git 状态、后台服务重载状态和验证结果。
- 下一步建议优先处理什么。

## 2. 当前仓库状态

- 项目：jin10-monitor
- GitHub 仓库：https://github.com/hangfo/jin10-monitor
- 本地路径：`/Users/rich/jin10-monitor`
- 分支：`main`
- 当前最新提交：
  - `85cd1b0 fix(config): tolerate invalid numeric env values`

最近提交：

```text
85cd1b0 fix(config): tolerate invalid numeric env values
b55715e docs(status): add telegram delivery handoff
a163e2b fix(telegram): record delivery status
341b5c3 docs(status): add pagination reliability handoff
fbeb996 fix(catchup): advance duplicate timestamp cursor
71095af docs(status): add reliability p1 handoff
```

本摘要生成前已确认：

- `git status` 干净，`main` 已与 `origin/main` 同步。
- `85cd1b0` 已推送到 `origin/main`。
- 后台 `launchd` 服务已执行 `./scripts/launchd/manage.sh reload`，新代码已运行。

新 session 仍必须重新执行本地 Git 检查，不要只凭本文件判断现场状态。

## 3. 本次修复内容

目标：避免 `.env` 数值配置误填导致进程启动阶段直接崩溃。

已完成：

- 新增 `env_int(name, default)`。
- 新增 `env_float(name, default)`。
- 下列启动期数值配置改为安全解析：
  - `CATCHUP_MAX_HOURS`
  - `CATCHUP_MAX_STORE`
  - `CATCHUP_MAX_SEND`
  - `CATCHUP_SEND_INTERVAL`
  - `AUTO_CATCHUP_GAP_SECONDS`
  - `SHOW_DELAY_IF_SECONDS`
  - `POLL_INTERVAL`
  - `WS_RECONNECT_DELAY`
- 配置值为空或未设置时继续使用原默认值。
- 配置值非法时记录 warning，并使用原默认值继续运行。
- `CHANGELOG.md` 已记录本次修复。

最重要的保护点：

- 没有新增 `.env` 字段。
- 没有修改 `.env.example` 默认值。
- 没有修改启动命令。
- 没有修改 WebSocket / REST / Telegram / SQLite 核心逻辑。
- 没有改变补拉去重语义：已成功发送过的 Telegram 仍不会重复补发。

## 4. 验证结果

已执行并通过：

```bash
.venv/bin/python -m py_compile jin10_monitor.py
git diff --check
```

坏配置验证：

```bash
POLL_INTERVAL=abc WS_RECONNECT_DELAY=oops CATCHUP_MAX_HOURS=bad \
CATCHUP_SEND_INTERVAL=nope SHOW_DELAY_IF_SECONDS=nah \
TG_TOKEN= TG_CHAT_ID= HISTORY_DB=/tmp/jin10_bad_env.sqlite3 \
.venv/bin/python jin10_monitor.py --history --history-limit 1
```

验证结果：

```text
CATCHUP_MAX_HOURS='bad' 不是有效整数，使用默认值 24
CATCHUP_SEND_INTERVAL='nope' 不是有效数字，使用默认值 0.5
SHOW_DELAY_IF_SECONDS='nah' 不是有效整数，使用默认值 60
POLL_INTERVAL='abc' 不是有效数字，使用默认值 3
WS_RECONNECT_DELAY='oops' 不是有效数字，使用默认值 5
历史库暂无匹配记录：(最新)
```

确认结果：

- 非法数值配置不会导致进程启动失败。
- 日志会指出具体坏配置和值。
- 系统会回退到原默认值。

## 5. 后台服务状态

已执行：

```bash
./scripts/launchd/manage.sh reload
./scripts/launchd/manage.sh status
tail -80 logs/jin10-monitor.log
```

确认结果：

- `launchd` 服务状态为 `running`。
- reload 后新 pid 为 `13356`。
- 日志显示 `23:21:45` 新进程启动。
- 启动后自动补拉执行成功：

```text
离线补拉完成：2026-05-11 23:17:00 -> 2026-05-11 23:21:45，入库 0 条，命中 2 条，摘要 未发送
```

- 冷启动预加载完成，已忽略 21 条旧快讯。
- REST 轮询已启动。
- WebSocket 已连接并发送登录包。
- WebSocket 初始历史列表已预热去重 40 条。

## 6. 当前风险判断

风险等级：低。

影响范围：

- 配置解析：数值配置非法时从启动失败改为 warning + 默认值。
- WebSocket：未修改核心逻辑；仅 `WS_RECONNECT_DELAY` 坏值会回默认 `5`。
- REST：未修改核心逻辑；仅 `POLL_INTERVAL` 坏值会回默认 `3`。
- Telegram 推送：未修改。
- SQLite 历史库：未修改。
- 补拉去重：未修改，仍只跳过已成功发送过的 Telegram。
- 启动方式：未修改。

残余风险：

- 如果用户误填配置，进程会继续按默认值运行，可能需要通过 warning 日志发现配置错误。
- 本次没有新增配置健康检查命令，也没有做配置值上下限校验；这是为了保持最小可靠修复。

## 7. 文档判断

本次不需要更新 `README.md` 或 `.env.example`：

- 没有新增配置项。
- 没有删除配置项。
- 没有改变默认值。
- 没有改变启动命令或用户操作方式。
- `CHANGELOG.md` 已记录用户可感知的可靠性变化。

## 8. 下一步优先级

建议继续保持小步可靠性修复，不要马上做复杂重试队列。

候选：

1. Telegram 投递状态查询入口。
   - 可以新增只读 CLI，查询最近 `failed / unknown_timeout / skipped` 状态。
   - 这会新增用户操作方式，通常需要同步更新 `README.md`。
2. 自动补拉摘要状态记录。
   - 当前自动补拉摘要不是单条金十消息，目前没有写入 `telegram_delivery_status`。
   - 可以评估是否用独立 key 记录摘要发送状态，但要避免污染单条消息的去重语义。
3. 数值配置上下限保护。
   - 当前只处理非法格式，不限制极端合法值。
   - 如要做，建议逐项评估默认行为和误填风险，避免一次性改太多。

## 9. 新 session 交接提示词

新开 session 后可以直接贴：

```text
请继续 /Users/rich/jin10-monitor 项目。

先读取：
1. /Users/rich/jin10-monitor/AGENTS.md
2. /Users/rich/jin10-monitor/docs/status/012-2026-05-11-config-tolerance-handoff.md

默认不要回读旧聊天。先执行：
git branch --show-current
git status
git pull --rebase
git log --oneline -6

当前阶段目标：
继续可靠性修复，优先做最小可靠修复，不要大规模重构模块。

已完成：
- P0：last_ingested_at 游标安全修复，提交 5221a88。
- P1：catch_up_window 已放到 asyncio.to_thread，SQLite 已改线程本地连接并开启 WAL / busy_timeout，提交 da08e98。
- P1 后续：补拉重复时间戳翻页 cursor 已修复，提交 fbeb996。
- P2：Telegram delivery status 最小版已完成，提交 a163e2b。
- 交接文档 011 已完成，提交 b55715e。
- .env 数值配置容错已完成，提交 85cd1b0。
- 后台 launchd 服务已 reload，新代码已运行。

下一步建议：
优先评估 Telegram 投递状态查询入口，先给修改计划，等我确认后再改代码。

要求：
- 先基于最新代码给修改计划，并等我确认后再改代码。
- 优先做最小可靠修复，不要大规模重构模块。
- 继续保护现有补拉去重语义：已成功发送过的 Telegram 不重复补发。
- 修改后给 diff、风险和验证。
- commit/push 前更新 CHANGELOG.md，并等我确认。
```
