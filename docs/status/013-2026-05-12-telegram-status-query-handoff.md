# 项目状态摘要 013：Telegram 投递状态查询入口已完成

更新时间：2026-05-12 凌晨（Asia/Shanghai）

## 1. 这份文档的用途

本文件用于在新 session 中快速续接可靠性修复阶段，不需要回读旧聊天。

这份摘要重点覆盖：

- Telegram 投递状态只读查询入口已经完成什么。
- 当前 Git 状态、文档更新和验证结果。
- 下一步建议优先处理什么。

## 2. 当前仓库状态

- 项目：jin10-monitor
- GitHub 仓库：https://github.com/hangfo/jin10-monitor
- 本地路径：`/Users/rich/jin10-monitor`
- 分支：`main`
- 当前最新提交：
  - `3bce008 feat(telegram): add delivery status query`

最近提交：

```text
3bce008 feat(telegram): add delivery status query
f1a5cfb docs(status): add config tolerance handoff
85cd1b0 fix(config): tolerate invalid numeric env values
b55715e docs(status): add telegram delivery handoff
a163e2b fix(telegram): record delivery status
341b5c3 docs(status): add pagination reliability handoff
```

本摘要生成前已确认：

- `git status` 干净，`main` 已与 `origin/main` 同步。
- `3bce008` 已推送到 `origin/main`。

新 session 仍必须重新执行本地 Git 检查，不要只凭本文件判断现场状态。

## 3. 本次修复内容

目标：给已经记录的 Telegram 投递状态增加一个安全、只读、低成本的查询入口，便于排查失败、超时未知或保护规则跳过。

已完成：

- 新增 `--telegram-status` CLI。
- 新增 `--telegram-status-limit` CLI。
- 默认查询需要关注的状态：
  - `failed`
  - `unknown_timeout`
  - `skipped`
- 支持按状态查询：
  - `problem`
  - `failed`
  - `unknown_timeout`
  - `skipped`
  - `sent`
  - `all`
- 查询输出包含：
  - 投递状态更新时间
  - 投递状态
  - 投递模式（`realtime` / `catchup`）
  - 金十消息 ID
  - 消息发生时间
  - 标题/正文摘要
  - 投递详情
- README 已新增使用说明。
- CHANGELOG 已记录本次用户可见变化。

最重要的保护点：

- 查询入口只读，不触发补发。
- 查询入口使用 SQLite `mode=ro` 打开历史库。
- 没有调用 `init_history_db()`，避免查询时建表、补字段、打开 WAL 或回填历史数据。
- 没有新增 `.env` 字段。
- 没有修改 `.env.example` 默认值。
- 没有修改启动命令或后台服务配置。
- 没有修改 WebSocket / REST / Telegram 发送核心逻辑。
- 没有改变补拉去重语义：手动补拉仍只跳过已成功发送过的 Telegram，失败、超时未知和跳过记录不会被当成“已发送”。

## 4. 使用方式

查看最近需要关注的 Telegram 投递状态：

```bash
python jin10_monitor.py --telegram-status
```

只看发送失败：

```bash
python jin10_monitor.py --telegram-status failed --telegram-status-limit 20
```

查看全部状态，包括已发送：

```bash
python jin10_monitor.py --telegram-status all --telegram-status-limit 50
```

## 5. 验证结果

已执行并通过：

```bash
.venv/bin/python -m py_compile jin10_monitor.py
git diff --check
```

临时 SQLite 查询验证：

```bash
HISTORY_DB=/private/tmp/jin10_status_query_test_20260512.sqlite3 \
.venv/bin/python jin10_monitor.py --telegram-status

HISTORY_DB=/private/tmp/jin10_status_query_test_20260512.sqlite3 \
.venv/bin/python jin10_monitor.py --telegram-status failed --telegram-status-limit 5

HISTORY_DB=/private/tmp/jin10_status_query_test_20260512.sqlite3 \
.venv/bin/python jin10_monitor.py --telegram-status all --telegram-status-limit 5
```

验证结果：

- 默认 `--telegram-status` 只显示 `failed` 和 `unknown_timeout` 等需关注状态，不显示 `sent`。
- `--telegram-status failed` 只显示失败记录。
- `--telegram-status all` 会显示 `unknown_timeout`、`sent`、`failed`。
- 查询输出能展示消息时间、内容摘要和详情。

缺库路径验证：

```bash
HISTORY_DB=/private/tmp/jin10_status_missing_20260511.sqlite3 \
.venv/bin/python jin10_monitor.py --telegram-status

ls -l /private/tmp/jin10_status_missing_20260511.sqlite3
```

确认结果：

- 缺库时只提示历史库不存在。
- 查询不会创建缺失的 SQLite 文件。

## 6. 当前风险判断

风险等级：低。

影响范围：

- WebSocket：未修改。
- REST：未修改。
- Telegram 推送：未修改发送逻辑。
- SQLite 历史库：新增只读查询入口，不写库。
- 补拉去重：未修改，仍只跳过已成功发送过的 Telegram。
- 启动方式：未修改。
- 配置字段：未修改。

残余风险：

- 如果旧数据库缺少 `flash_history` 表，当前查询会记录 warning，而不是降级只显示状态表；这对正常运行过的项目数据库不构成影响。
- 查询入口只是诊断工具，不会自动重试失败消息。

## 7. 文档判断

已更新：

- `README.md`：新增 `--telegram-status` 使用方式和状态说明。
- `CHANGELOG.md`：记录本次只读查询入口。

本次不需要更新：

- `.env.example`：没有新增配置项。
- `docs/operations/001-launchd.md`：没有修改启动方式或后台服务管理方式。

## 8. 下一步优先级

建议继续保持小步可靠性修复，不要马上做复杂重试队列。

候选：

1. 自动补拉摘要状态记录。
   - 当前自动补拉摘要不是单条金十消息，目前没有写入 `telegram_delivery_status`。
   - 可以评估是否用独立 key 记录摘要发送状态，但要避免污染单条消息的去重语义。
2. 数值配置上下限保护。
   - 当前只处理非法格式，不限制极端合法值。
   - 如要做，建议逐项评估默认行为和误填风险，避免一次性改太多。
3. Telegram 投递状态查询降级优化。
   - 如果未来需要兼容非常旧的数据库，可以在缺少 `flash_history` 时只显示状态表字段。
   - 当前正常项目库已有 `flash_history`，这个优化不是优先项。

## 9. 新 session 交接提示词

新开 session 后可以直接贴：

```text
请继续 /Users/rich/jin10-monitor 项目。

先读取：
1. /Users/rich/jin10-monitor/AGENTS.md
2. /Users/rich/jin10-monitor/docs/status/013-2026-05-12-telegram-status-query-handoff.md

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
- README.md 和 CHANGELOG.md 已更新。

下一步建议：
优先评估自动补拉摘要状态记录，先给修改计划，等我确认后再改代码。

要求：
- 先基于最新代码给修改计划，并等我确认后再改代码。
- 查询和诊断入口只做只读，不要实现重试队列。
- 优先做最小可靠修复，不要大规模重构模块。
- 继续保护现有补拉去重语义：已成功发送过的 Telegram 不重复补发。
- 如果新增 CLI 用户操作方式，预计需要更新 README.md 和 CHANGELOG.md。
- 修改后给 diff、风险和验证。
- commit/push 前更新 CHANGELOG.md，并等我确认。
```
