# 项目状态摘要 011：Telegram 投递状态最小版已完成

更新时间：2026-05-11 晚（Asia/Shanghai）

## 1. 这份文档的用途

本文件用于在新 session 中快速续接 Telegram 投递可靠性阶段，不需要回读旧聊天。

这份摘要重点覆盖：

- Telegram delivery status 最小版已经完成什么。
- 当前 Git 状态、后台服务重载状态和验证结果。
- 下一步建议优先处理什么。

## 2. 当前仓库状态

- 项目：jin10-monitor
- GitHub 仓库：https://github.com/hangfo/jin10-monitor
- 本地路径：`/Users/rich/jin10-monitor`
- 分支：`main`
- 当前最新提交：
  - `a163e2b fix(telegram): record delivery status`

最近提交：

```text
a163e2b fix(telegram): record delivery status
341b5c3 docs(status): add pagination reliability handoff
fbeb996 fix(catchup): advance duplicate timestamp cursor
71095af docs(status): add reliability p1 handoff
```

本摘要生成前已确认：

- `git status` 干净，`main` 已与 `origin/main` 同步。
- `a163e2b` 已推送到 `origin/main`。
- 后台 `launchd` 服务已执行 `./scripts/launchd/manage.sh reload`，新进程正在运行。

新 session 仍必须重新执行本地 Git 检查，不要只凭本文件判断现场状态。

## 3. 本次修复内容

目标：让 Telegram 投递结果可诊断，同时保护现有补拉去重语义。

已完成：

- 新增 `TelegramSendResult`，让 `send_telegram` 返回明确状态，而不是只返回 `True / False`。
- 新增 Telegram 投递状态：
  - `sent`
  - `failed`
  - `unknown_timeout`
  - `skipped`
- 新增 SQLite 表 `telegram_delivery_status`，记录每条消息最近一次 Telegram 投递状态和简短详情。
- 手动补拉逐条发送会记录 `sent / failed / skipped` 状态。
- 实时推送会记录 `sent / failed / unknown_timeout / skipped` 状态。
- `CHANGELOG.md` 已记录本次修复。

最重要的保护点：

- `delivery_log` 仍然只表示“Telegram 已成功发送过”。
- 成功发送时继续写 `delivery_log`。
- 失败、超时未知、保护规则跳过时只写 `telegram_delivery_status`，不写 `delivery_log`。
- 补拉候选仍通过 `has_any_delivery(..., channel="telegram")` 查看旧成功表，所以已成功发送过的 Telegram 不会重复补发。

没有改动：

- 没有修改 WebSocket 接收、keepalive 或重连逻辑。
- 没有修改 REST 轮询抓取逻辑。
- 没有修改补拉分页 cursor 逻辑。
- 没有修改补拉候选排序和选择策略。
- 没有新增 `.env` 配置字段。
- 没有修改启动命令。
- 没有新增依赖。
- 没有实现复杂重试队列。

## 4. 验证结果

已执行并通过：

```bash
.venv/bin/python -m py_compile jin10_monitor.py
git diff --check
```

临时 SQLite 语义验证：

- `skipped` 不会写入 `delivery_log`。
- `failed` 状态下补拉候选仍可被选中。
- 成功后会写入 `delivery_log`。
- 同一消息成功进入 `delivery_log` 后，补拉候选会跳过。

验证输出：

```text
send_status skipped
has_delivery_after_sent True
status_rows [('m1', 'sent', '')]
```

## 5. 后台服务状态

已执行：

```bash
./scripts/launchd/manage.sh reload
./scripts/launchd/manage.sh status
tail -60 logs/jin10-monitor.log
```

确认结果：

- `launchd` 服务状态为 `running`。
- reload 后新 pid 为 `11482`。
- 日志显示 `23:10:18` 新进程启动。
- 启动后自动补拉执行成功：

```text
离线补拉完成：2026-05-11 23:06:33 -> 2026-05-11 23:10:18，入库 0 条，命中 0 条，摘要 未发送
```

- 冷启动预加载完成，已忽略 21 条旧快讯。
- REST 轮询已启动。
- WebSocket 已连接并发送登录包。
- WebSocket 初始历史列表已预热去重 40 条。

## 6. 当前风险判断

风险等级：中低。

影响范围：

- Telegram 推送：发送结果从布尔值升级为可诊断状态。
- SQLite 历史库：新增 `telegram_delivery_status` 表。
- 补拉去重：旧成功表语义未变，仍只跳过已成功发送过的 Telegram。
- 普通 REST 轮询：未修改。
- WebSocket：未修改。
- 配置字段：未新增 `.env` 字段。
- 启动方式：未修改。

残余风险：

- 新状态表目前只记录最近一次状态，不是完整投递流水。
- 自动补拉摘要不是单条金十消息，目前仍只保留原来的布尔结果，没有写入 `telegram_delivery_status`。
- 目前只提升可诊断性，没有实现失败重试队列；这是有意保持最小可靠修复。

## 7. 文档判断

本次不需要更新 `README.md` 或 `.env.example`：

- 没有新增配置项。
- 没有改变命令用法。
- 没有改变用户需要手动操作的流程。
- `CHANGELOG.md` 已记录用户可感知的可靠性变化。

## 8. 下一步优先级

建议下一步先不要扩大 Telegram 重试功能，优先处理更低风险的可靠性收尾。

候选：

1. `.env` 数值配置安全解析。
   - 当前多个数值配置直接 `int(...)` / `float(...)`，如果环境变量写错，进程会启动失败。
   - 建议做最小 helper，保留默认值并记录 warning。
2. Telegram 投递状态查询入口。
   - 可以考虑新增只读 CLI 查询最近失败/未知投递状态。
   - 需要先评估是否值得修改 README，因为这会改变用户操作方式。
3. 自动补拉逐条补发配置化。
   - 默认仍不逐条补发，避免刷屏和实时消息混排。
   - 不建议马上做复杂重试队列。

## 9. 新 session 交接提示词

新开 session 后可以直接贴：

```text
请继续 /Users/rich/jin10-monitor 项目。

先读取：
1. /Users/rich/jin10-monitor/AGENTS.md
2. /Users/rich/jin10-monitor/docs/status/011-2026-05-11-telegram-delivery-status-handoff.md

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
- 后台 launchd 服务已 reload，新代码已运行。

下一步建议：
优先评估 .env 数值配置安全解析，先给修改计划，等我确认后再改代码。

要求：
- 先基于最新代码给修改计划，并等我确认后再改代码。
- 优先做最小可靠修复，不要大规模重构模块。
- 继续保护现有补拉去重语义：已成功发送过的 Telegram 不重复补发。
- 修改后给 diff、风险和验证。
- commit/push 前更新 CHANGELOG.md，并等我确认。
```
