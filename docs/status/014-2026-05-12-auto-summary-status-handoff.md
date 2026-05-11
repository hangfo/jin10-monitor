# 项目状态摘要 014：自动补拉摘要投递状态记录已完成

更新时间：2026-05-12 凌晨（Asia/Shanghai）

## 1. 这份文档的用途

本文件用于在新 session 中快速续接可靠性修复阶段，不需要回读旧聊天。

这份摘要重点覆盖：

- 自动补拉摘要 Telegram 投递状态记录已经完成什么。
- 当前 Git 状态、文档判断和验证结果。
- 下一步建议优先处理什么。

## 2. 当前仓库状态

- 项目：jin10-monitor
- GitHub 仓库：https://github.com/hangfo/jin10-monitor
- 本地路径：`/Users/rich/jin10-monitor`
- 分支：`main`
- 当前最新功能提交：
  - `06423a2 fix(catchup): record auto summary delivery status`

最近提交：

```text
06423a2 fix(catchup): record auto summary delivery status
e5e6867 docs(status): add telegram status query handoff
3bce008 feat(telegram): add delivery status query
f1a5cfb docs(status): add config tolerance handoff
85cd1b0 fix(config): tolerate invalid numeric env values
b55715e docs(status): add telegram delivery handoff
```

本摘要生成前已确认：

- `06423a2` 已推送到 `origin/main`。
- 功能提交后工作区干净。

新 session 仍必须重新执行本地 Git 检查，不要只凭本文件判断现场状态。

## 3. 本次修复内容

目标：让自动补拉摘要的 Telegram 发送结果可通过现有投递状态查询入口诊断，同时不污染单条消息补拉去重语义。

已完成：

- 自动补拉摘要发送成功、失败、超时未知或保护跳过时，会写入 `telegram_delivery_status`。
- 摘要状态使用独立 key：
  - `catchup_summary:<trigger>:<start>:<end>`
- 摘要状态使用独立 mode：
  - `catchup_summary`
- 状态详情记录轻量摘要：
  - `stored`
  - `push_candidates`
  - `truncated`
  - 失败或跳过详情
- README 已说明自动补拉摘要也会进入 `--telegram-status` 只读视图。
- CHANGELOG 已记录本次用户可见变化。

最重要的保护点：

- 没有把自动补拉摘要写入 `delivery_log`。
- 没有调用 `mark_delivery()`。
- 没有修改手动补拉逐条发送逻辑。
- 没有修改自动补拉是否发送摘要的条件。
- 没有新增重试队列。
- 没有新增 `.env` 字段。
- 没有修改启动命令或后台服务配置。
- 查询和诊断入口仍然只读。
- 手动补拉仍只跳过已成功发送过的单条 Telegram 消息，失败、超时未知、跳过和摘要状态都不会被当成“已发送”。

## 4. 使用方式

查看最近需要关注的 Telegram 投递状态：

```bash
python jin10_monitor.py --telegram-status
```

查看全部状态，包括已发送和自动补拉摘要：

```bash
python jin10_monitor.py --telegram-status all --telegram-status-limit 50
```

自动补拉摘要记录示例：

```text
[skipped catchup_summary] id=catchup_summary:gap:2026-05-12 09:58:00:2026-05-12 10:05:00
  详情：stored=1 push_candidates=1 truncated=False detail=Telegram 未配置
```

## 5. 验证结果

已执行并通过：

```bash
.venv/bin/python -m py_compile jin10_monitor.py
git diff --check
```

临时 SQLite 保护路径验证：

```bash
HISTORY_DB=/private/tmp/jin10_auto_summary_status_test.sqlite3 \
TG_TOKEN= TG_CHAT_ID= \
.venv/bin/python -c '...mock run_auto_catch_up...'
```

验证结果：

- Telegram 未配置时，自动补拉摘要记录为 `skipped`。
- 状态表写入 `message_id=catchup_summary:...`、`mode=catchup_summary`。
- `delivery_log_count=0`，确认没有污染逐条消息去重表。

只读查询验证：

```bash
HISTORY_DB=/private/tmp/jin10_auto_summary_status_test.sqlite3 \
.venv/bin/python jin10_monitor.py --telegram-status all --telegram-status-limit 5
```

确认结果：

- 查询能展示自动补拉摘要状态。
- 查询不会触发补发。

## 6. 文档判断

已更新：

- `README.md`：说明自动补拉摘要也会显示在 Telegram 投递状态只读视图里。
- `CHANGELOG.md`：记录本次用户可见变化。

本次不需要更新：

- `.env.example`：没有新增配置项。
- `docs/operations/001-launchd.md`：没有修改启动方式、后台服务管理方式或 launchd 配置。

## 7. 当前风险判断

风险等级：低。

影响范围：

- WebSocket：未修改。
- REST：未修改。
- Telegram 推送：不改变发送策略，只增加摘要发送结果记录。
- SQLite 历史库：复用现有 `telegram_delivery_status` 表，不改表结构。
- 补拉去重：未修改，仍只通过 `delivery_log` 判断单条消息是否已成功发送。
- 启动方式：未修改。
- 配置字段：未修改。

残余风险：

- 自动补拉摘要状态只保留同一窗口、同一 trigger 的最近一次结果，不是完整投递流水。
- 如果未来需要批量分析摘要历史，可能需要独立审计表；当前阶段不建议为了这个做大改。

## 8. 下一步优先级

建议继续保持小步可靠性修复，不要马上做复杂重试队列。

候选：

1. 数值配置上下限保护。
   - 当前只处理非法格式，不限制极端合法值。
   - 建议逐项评估默认行为和误填风险，避免一次性改太多。
2. Telegram 投递状态查询降级优化。
   - 如果未来需要兼容非常旧的数据库，可以在缺少 `flash_history` 时只显示状态表字段。
   - 当前正常项目库已有 `flash_history`，这个优化不是优先项。
3. 真实运行观察。
   - 观察 launchd 日志里自动补拉摘要是否自然触发。
   - 通过 `--telegram-status` 检查摘要状态是否符合预期。

## 9. 新 session 交接提示词

新开 session 后可以直接贴：

```text
请继续 /Users/rich/jin10-monitor 项目。

先读取：
1. /Users/rich/jin10-monitor/AGENTS.md
2. /Users/rich/jin10-monitor/docs/status/014-2026-05-12-auto-summary-status-handoff.md

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
- .env 数值配置容错已完成，提交 85cd1b0。
- Telegram 投递状态只读查询入口已完成，提交 3bce008。
- 自动补拉摘要投递状态记录已完成，提交 06423a2。
- README.md 和 CHANGELOG.md 已更新。

下一步建议：
优先评估数值配置上下限保护，先给修改计划，等我确认后再改代码。

要求：
- 先基于最新代码给修改计划，并等我确认后再改代码。
- 查询和诊断入口只做只读，不要实现重试队列。
- 优先做最小可靠修复，不要大规模重构模块。
- 继续保护现有补拉去重语义：已成功发送过的 Telegram 不重复补发。
- 如果新增 CLI 用户操作方式，预计需要更新 README.md 和 CHANGELOG.md。
- 修改后给 diff、风险和验证。
- commit/push 前更新 CHANGELOG.md，并等我确认。
```
