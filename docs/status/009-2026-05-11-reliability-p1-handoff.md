# 项目状态摘要 009：可靠性 P1 补拉线程化已完成

更新时间：2026-05-11 晚（Asia/Shanghai）

## 1. 这份文档的用途

本文件用于在新 session 中快速续接可靠性修复阶段，不需要回读旧聊天。

这份摘要重点覆盖：

- P1 `catch_up_window` 线程化和 SQLite WAL / busy_timeout 已完成什么。
- 当前 Git 状态、后台服务重载状态和验证结果。
- 下一步最优先处理的可靠性问题。

## 2. 当前仓库状态

- 项目：jin10-monitor
- GitHub 仓库：https://github.com/hangfo/jin10-monitor
- 本地路径：`/Users/rich/jin10-monitor`
- 分支：`main`
- 当前最新提交：
  - `da08e98 fix(catchup): run catch-up off event loop`

最近提交：

```text
da08e98 fix(catchup): run catch-up off event loop
f7a63ce docs(status): add reliability p0 handoff
5221a88 fix(catchup): guard ingest cursor time
6d0f5a7 docs(status): add catchup progress handoff
5520f1e feat(catchup): add progress logging
1732902 docs(status): add launchd and delay handoff
```

本摘要生成前已确认：

- `git status` 干净，`main` 已与 `origin/main` 同步。
- `da08e98` 已推送到 `origin/main`。
- 后台 `launchd` 服务已执行 `./scripts/launchd/manage.sh reload`，新进程正在运行。

新 session 仍必须重新执行本地 Git 检查，不要只凭本文件判断现场状态。

## 3. P1 已完成内容

目标：让补拉不再阻塞 asyncio event loop，并降低线程化补拉后的 SQLite 锁冲突和跨线程连接风险。

已完成：

- `run_catch_up` 手动补拉改为通过 `await asyncio.to_thread(catch_up_window, ...)` 执行。
- `run_auto_catch_up` 自动补拉 / 自愈补拉改为通过 `await asyncio.to_thread(catch_up_window, ...)` 执行。
- SQLite 连接从单个全局 `_db_conn` 改为线程本地 `_db_local = threading.local()`。
- 移除 `check_same_thread=False`，避免误把同一个 SQLite connection 跨线程复用。
- 新增 `configure_db_connection`，每个新连接创建后统一设置：
  - `PRAGMA busy_timeout = 5000`
  - `PRAGMA journal_mode = WAL`
- 新增 `SQLITE_BUSY_TIMEOUT_MS = 5000` 常量。
- `CHANGELOG.md` 已记录本次 P1 修复。

没有改动：

- 没有修改补拉翻页游标算法。
- 没有修改消息过滤和优先级规则。
- 没有修改 Telegram 发送逻辑。
- 没有新增 `.env` 配置字段。
- 没有修改启动命令。

## 4. P1 验证结果

已执行并通过：

```bash
.venv/bin/python -m py_compile jin10_monitor.py
git diff --check
```

已用临时 SQLite 库验证：

```text
journal_mode wal
busy_timeout 5000
```

已用 monkeypatch 验证：

- `run_catch_up` 会在非主线程调用 `catch_up_window`。
- `run_auto_catch_up` 会在非主线程调用 `catch_up_window`。
- 补拉线程不会复用主线程 SQLite connection。
- 补拉期间 event loop 仍能 tick。

验证输出：

```text
manual_ok True
auto_ok True trigger verify
ticks_while_manual 5
call {'source': 'catchup_manual', 'thread_changed': True, 'shared_main_conn': False, 'busy_timeout': 5000, 'journal_mode': 'wal'}
call {'source': 'catchup_auto', 'thread_changed': True, 'shared_main_conn': False, 'busy_timeout': 5000, 'journal_mode': 'wal'}
```

已用临时库验证历史查询入口：

```bash
HISTORY_DB=/tmp/jin10_p1_history_verify.sqlite3 .venv/bin/python jin10_monitor.py --history 巴菲特 --history-limit 5
```

输出：

```text
[INFO] 历史库暂无匹配记录：巴菲特
```

## 5. 后台服务状态

已执行：

```bash
./scripts/launchd/manage.sh reload
./scripts/launchd/manage.sh status
tail -80 logs/jin10-monitor.log
```

确认结果：

- `launchd` 服务状态为 `running`。
- reload 后新 pid 为 `7498`。
- 日志显示 `22:44:10` 新进程启动。
- 启动后自动补拉执行成功：

```text
离线补拉完成：2026-05-11 22:39:01 -> 2026-05-11 22:44:10，入库 0 条，命中 3 条，摘要 未发送
```

- 冷启动预加载完成。
- REST 轮询已启动。
- WebSocket 已连接并发送登录包。
- WebSocket 初始历史列表已预热去重。

## 6. 当前风险判断

P1 风险等级：中。

影响范围：

- SQLite：连接策略改为每线程一个 connection，并开启 WAL / busy_timeout。
- 自动补拉 / 手动补拉：同步 `catch_up_window` 改为后台线程执行。
- WebSocket / REST：实时路径仍按原逻辑运行，但会使用主线程自己的 SQLite connection。
- Telegram：未修改发送逻辑。
- 配置字段：未新增 `.env` 字段。
- 启动方式：未修改。

注意：

- WAL 模式会正常产生 SQLite `-wal` / `-shm` sidecar 文件。
- 如果某些文件系统不支持 WAL，连接初始化可能报错；当前本机验证正常。
- 5 秒 `busy_timeout` 能降低锁冲突失败概率，但不能消除长期写锁导致的失败。
- 本次修复没有解决补拉翻页重复时间戳可能卡页或漏页的问题。
- 本次修复没有实现 Telegram delivery status。

## 7. 下一步优先级

### P1 后续：修复 `catch_up_window` 翻页游标在重复时间戳下可能卡页或漏页的问题

建议作为下一步第一优先级。

原因：

- 这是补拉完整性问题，优先级高于 Telegram delivery status。
- 当前补拉分页使用最后一条消息时间作为下一页 cursor。
- 如果同一秒内有多条消息，且分页边界刚好落在重复时间戳中间，可能出现重复扫描、卡页或漏掉同一秒剩余消息的风险。
- P0 已保证 `last_ingested_at` 游标安全，P1 已降低补拉阻塞和 SQLite 并发风险；下一步应继续补齐补拉窗口完整性。

建议先评估再改：

- 先阅读 `fetch_page_sync` 返回排序和 `catch_up_window` 当前分页逻辑。
- 用 mock page 构造同一时间戳跨页场景，复现风险后再改。
- 优先做最小可靠修复，不大规模重构。
- 改动后要验证：
  - 重复时间戳跨页不会漏消息。
  - 分页 cursor 能前进或安全停止，不会无限重复。
  - 现有 `max_pages` / `max_store` 截断语义不被破坏。
  - 去重仍依赖消息 ID。

### 后续 P2

完成翻页游标修复后，再考虑：

1. Telegram `delivery_status` 最小版设计：`sent / failed / unknown_timeout / skipped`。
2. `.env` 数值配置安全解析。
3. 自动补拉逐条补发配置化，但默认仍不逐条补发，避免刷屏和实时消息混排。

## 8. 新 session 交接提示词

新开 session 后可以直接贴：

```text
请继续 /Users/rich/jin10-monitor 项目。

先读取：
1. /Users/rich/jin10-monitor/AGENTS.md
2. /Users/rich/jin10-monitor/docs/status/009-2026-05-11-reliability-p1-handoff.md

默认不要回读旧聊天。先执行：
git branch --show-current
git status
git pull --rebase
git log --oneline -6

当前阶段目标：
继续可靠性修复，优先处理 code review 里最紧迫的问题，不继续堆新功能。

已完成：
- P0：last_ingested_at 游标安全修复，提交 5221a88。
- P1：catch_up_window 已放到 asyncio.to_thread，SQLite 已改线程本地连接并开启 WAL / busy_timeout，提交 da08e98。
- 后台 launchd 服务已 reload，新代码已运行。

下一步先做：
修复 catch_up_window 翻页游标在重复时间戳下可能卡页或漏页的问题。

要求：
- 先基于最新代码给修改计划，并等我确认后再改代码。
- 优先做最小可靠修复，不要大规模重构模块。
- 先用 mock page 复现同一时间戳跨页风险，再改。
- 修改后给 diff、风险和验证。
- commit/push 前更新 CHANGELOG.md，并等我确认。
```
