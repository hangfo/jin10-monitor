# 项目状态摘要 008：可靠性 P0 游标安全已完成

更新时间：2026-05-11 晚（Asia/Shanghai）

## 1. 这份文档的用途

本文件用于在新 session 中快速续接可靠性修复阶段，不需要回读旧聊天。

这份摘要重点覆盖：

- P0 `last_ingested_at` 游标安全修复已经完成了什么。
- 当前 Git 状态和最新提交。
- 下一步 P1 应该优先做什么，以及建议使用的模型/推理强度。

## 2. 当前仓库状态

- 项目：jin10-monitor
- GitHub 仓库：https://github.com/hangfo/jin10-monitor
- 本地路径：`/Users/rich/jin10-monitor`
- 分支：`main`
- 当前最新提交：
  - `5221a88 fix(catchup): guard ingest cursor time`

最近提交：

```text
5221a88 fix(catchup): guard ingest cursor time
6d0f5a7 docs(status): add catchup progress handoff
5520f1e feat(catchup): add progress logging
1732902 docs(status): add launchd and delay handoff
c933b90 feat(delay): show stale message latency
f465d5b fix(launchd): harden reload and install flow
```

本摘要生成前已确认：

- `git status --short` 无输出，工作区干净。
- `main` 已推送到 `origin/main`。

新 session 仍必须重新执行本地 Git 检查，不要只凭本文件判断现场状态。

## 3. P0 已完成内容

目标：修复 `last_ingested_at` 游标被未来时间或乱序消息推进后，导致后续自动补拉窗口漏掉真实消息的风险。

已完成：

- 新增游标保护常量：
  - `CURSOR_FUTURE_GRACE_SECONDS = 120`
  - `AUTO_CATCHUP_START_BUFFER_SECONDS = 120`
- 新增游标时间工具：
  - `format_cursor_datetime`
  - `parse_cursor_datetime`
- `update_ingest_cursor` 改为先把消息时间和当前游标解析为 `datetime` 后比较。
- 消息发生时间超过当前时间 `now + 120s` 时，仍可正常入库，但不推进 `last_ingested_at`。
- 乱序旧消息不会把 `last_ingested_at` 往回拉。
- 如果当前 `last_ingested_at` 格式坏掉或已经位于未来保护阈值之后，下一条有效消息会修复游标。
- `latest_history_cursor` 从历史库恢复启动游标时，会解析时间并忽略未来时间记录。
- `run_auto_catch_up` 遇到未来 `last_ingested_at` 时，会回退到历史库最新有效游标。
- 自动补拉窗口起点额外回退 120 秒 buffer，依赖现有消息 ID 去重避免重复入库。
- `CHANGELOG.md` 已记录本次 P0 修复。

## 4. P0 验证结果

已执行并通过：

```bash
.venv/bin/python -m py_compile jin10_monitor.py
git diff --check
```

已用临时 SQLite 库验证：

- 未来消息不会推进 `last_ingested_at`。
- 乱序旧消息不会把游标回退。
- 已有未来游标会被下一条有效消息修复。
- `bootstrap_runtime_state` 会忽略未来历史记录。
- 自动补拉起点会回退 120 秒。
- 自动补拉遇到未来游标会回退到历史库最新有效游标。

验证命令使用的是临时库，例如：

```bash
HISTORY_DB=/tmp/jin10_p0_cursor_verify_final.sqlite3 .venv/bin/python -c '...'
```

## 5. 当前风险判断

P0 风险等级：低到中。

影响范围：

- SQLite：会影响 `runtime_state.last_ingested_at` 和 `last_ingested_id` 的推进规则。
- 自动补拉：窗口起点会多回看 120 秒。
- WebSocket / REST：消息仍按原路径入库，只有游标推进更谨慎。
- Telegram：未修改发送逻辑。
- 配置字段：未新增 `.env` 字段。
- 启动方式：未修改。

注意：

- 本次修复没有解决 `catch_up_window` 同步阻塞 event loop 的问题。
- 本次修复没有开启 SQLite WAL / busy_timeout。
- 本次修复没有解决补拉翻页重复时间戳可能卡页或漏页的问题。
- 本次修复没有改 Telegram delivery status。

这些都留给后续 P1/P2。

## 6. 下一步优先级

### P1：把 `catch_up_window` 放到 `asyncio.to_thread`，并给 SQLite 开 WAL + busy_timeout

建议作为下一步第一优先级。

目标：

- 自动补拉和手动补拉不要在同步 REST 翻页期间阻塞 asyncio event loop。
- SQLite 在实时写入、补拉写入、后续线程化补拉之间更稳，减少 `database is locked` 风险。

建议先评估再改：

- 当前全局 `_db_conn` 是 `sqlite3.connect(..., check_same_thread=False)`，P1 需要谨慎处理线程间共用连接风险。
- 优先考虑线程本地 connection 或明确的连接获取策略，不要为了 `to_thread` 简单共用同一个 connection。
- WAL 和 `busy_timeout` 应该在连接创建后设置。
- 保持最小可靠修复，不要顺手大规模重构模块。

建议验证：

- `py_compile`
- 临时 SQLite 库初始化后检查 `PRAGMA journal_mode`
- 临时 SQLite 库检查 `PRAGMA busy_timeout`
- mock / monkeypatch `catch_up_window` 或补拉路径，确认 `run_auto_catch_up` / `run_catch_up` 通过 `asyncio.to_thread` 调用
- 尽量做一个补拉期间 event loop 仍能 tick 的轻量验证

### 后续 P1/P2

完成上述 P1 后，再继续：

1. 修复 `catch_up_window` 翻页游标在重复时间戳下可能卡页/漏页的问题。
2. 做 Telegram `delivery_status` 最小版设计：`sent / failed / unknown_timeout / skipped`。
3. 评估是否顺手做 `.env` 数值配置安全解析。

## 7. 模型与推理建议

下一步 P1 建议使用：

- 模型：`5.5`
- 推理：高推理

原因：

- P1 会涉及 asyncio、线程、SQLite connection 生命周期和锁等待策略。
- 这类改动容易出现“测试能过但长期运行偶发卡住”的边界问题。
- 需要优先保证稳定性，而不是快速堆功能。

P0 这种局部游标修复不必须使用 5.5，但 P1 建议切换。

## 8. 新 session 交接提示词

新开 session 后可以直接贴：

```text
请继续 /Users/rich/jin10-monitor 项目。

先读取：
1. /Users/rich/jin10-monitor/AGENTS.md
2. /Users/rich/jin10-monitor/docs/status/008-2026-05-11-reliability-p0-handoff.md

默认不要回读旧聊天。先执行：
git branch --show-current
git status
git pull --rebase
git log --oneline -6

当前阶段目标：
进入可靠性修复 P1，优先处理 code review 里最紧迫的问题，不继续堆新功能。

已完成：
- P0：`last_ingested_at` 游标安全修复已提交并推送，最新提交 `5221a88 fix(catchup): guard ingest cursor time`。

下一步先做：
P1：把 `catch_up_window` 放到 `asyncio.to_thread`，并给 SQLite 开 WAL + busy_timeout。

要求：
- 建议使用 5.5 高推理。
- 不降低代码、debug 和架构设计质量。
- 先基于最新代码给修改计划，并等我确认后再改代码。
- 优先做最小可靠修复，不要一上来大规模重构模块。
- 重点评估 SQLite connection 在线程化后的安全性，不要简单共用不安全连接。
- 修改后给 diff、风险和验证。
- commit/push 前更新 CHANGELOG.md，并等我确认。
```
