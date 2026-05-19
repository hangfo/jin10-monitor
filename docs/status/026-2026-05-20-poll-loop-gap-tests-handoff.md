# 项目状态摘要 026：REST 轮询主循环 gap 自愈补拉测试

更新时间：2026-05-20（Asia/Shanghai）

## 1. 这份文档的用途

本文件用于在新 session 中快速续接，不需要回读旧聊天。

这份摘要重点覆盖：

- `025` 之后新增的 `poll_loop` 主循环 gap 触发自动补拉编排测试。
- 当前 Git 状态、验证结果、风险判断。
- 下一阶段建议：是否继续 `GPT-5.5 中`，或切 `GPT-5.5 高`。

## 2. 当前仓库状态

- 项目：jin10-monitor
- GitHub 仓库：https://github.com/hangfo/jin10-monitor
- 本地路径：`/Users/rich/jin10-monitor`
- 分支：`main`
- 当前最新功能测试提交：
  - `8d37b2e test(poll): cover gap auto catch-up trigger`

最近提交：

```text
8d37b2e test(poll): cover gap auto catch-up trigger
6b3c71d docs(status): add realtime handle item handoff
5ddf7c7 test(realtime): cover handle item delivery status
da1c9ea docs(status): add manual catchup wrapper handoff
4e8c37e test(catchup): cover manual catch-up wrapper
35314a6 docs(status): add auto catchup tests handoff
```

本摘要生成前已确认：

- `main` 已推送到 `origin/main`。
- 功能测试提交前完整 pytest 结果为 `86 passed`。
- 本摘要文档会作为 docs-only 收尾提交。

新 session 仍必须重新执行本地 Git 检查，不要只凭本文件判断现场状态。

## 3. 本阶段完成内容

`025` 后建议进入 `poll_loop` 主循环 gap 触发 `run_auto_catch_up` 的 async 编排测试。本阶段已完成并提交：

- `8d37b2e test(poll): cover gap auto catch-up trigger`

新增测试位于 `tests/test_storage.py`，使用：

- fake `datetime.now()` 序列固定主循环时间。
- fake `poll_once` 返回空列表，避免真实 REST。
- fake `run_auto_catch_up` 记录调用参数，避免进入真实补拉。
- fake `asyncio.sleep` 抛出自定义异常，让无限循环可控退出。

未触发：

- 真实 Telegram
- 真实 REST
- launchd
- WebSocket
- SQLite 并发压力路径

## 4. `poll_loop` 已覆盖语义

新增 3 个无网络测试，覆盖：

- `AUTO_CATCHUP=True` 且 `gap_seconds >= AUTO_CATCHUP_GAP_SECONDS`：
  - 调用 `run_auto_catch_up(session, now, trigger="gap")`。
  - 补拉检查后仍继续执行本轮 `poll_once`。
- `AUTO_CATCHUP=False`：
  - 即使 gap 达阈值也不调用 `run_auto_catch_up`。
- gap 未达阈值：
  - 不调用 `run_auto_catch_up`。

重点保护的既有语义：

- 主循环只在明确达到 gap 阈值时进入自愈补拉。
- 自愈补拉使用 `trigger="gap"`，从而沿用 gap 摘要冷却等既有保护。
- 测试只验证编排触发条件，不改变补拉去重和 Telegram 投递语义。

## 5. 当前测试覆盖概览

当前 pytest 用例数：

```text
86 passed
```

测试文件：

- `tests/test_pure_functions.py`
  - 45 个用例。
- `tests/test_storage.py`
  - 41 个用例。

最近一次完整验证：

```bash
git diff --check
.venv/bin/python -m pytest tests/test_storage.py -k poll_loop
.venv/bin/python -m pytest tests/test_storage.py
.venv/bin/python -m pytest
```

结果：

```text
poll_loop selected tests: 3 passed
tests/test_storage.py: 41 passed
full pytest: 86 passed
```

## 6. 当前覆盖地图

已完成：

- `crawl_window` mock REST 边界测试。
- `.env` 数值配置范围保护。
- 手动补拉 CLI 参数范围保护。
- `catch_up_window` mock REST 边界测试。
- `run_auto_catch_up`：
  - 未来游标恢复。
  - 最大回看窗口。
  - 早退分支。
  - gap 摘要冷却。
  - `seen_id` 交接。
- `run_catch_up` 手动补拉包装层：
  - Telegram 关闭不发送。
  - 窗口失败早退。
  - skip guard 只写 skipped 状态，不写 `delivery_log`。
  - 成功才 `mark_delivery`。
  - 失败只写诊断状态。
  - 多条候选逐条处理。
  - `send_interval=0` 不等待。
- `handle_item` 实时处理链路：
  - 成功发送写 realtime 去重。
  - 失败只写诊断状态。
  - 未命中关键词只入库不发送。
- `poll_loop` REST 轮询主循环：
  - gap 达阈值触发 `run_auto_catch_up(..., trigger="gap")`。
  - 自动补拉关闭时不触发。
  - gap 未达阈值时不触发。

## 7. 当前风险判断

整体风险等级：低。

影响范围：

- WebSocket：未修改。
- REST：未触发真实 REST；`poll_once` 使用 fake。
- Telegram 推送：未修改发送逻辑；未触发真实 Telegram。
- SQLite 历史库：未修改 schema；本轮测试不依赖真实补拉写库。
- 补拉 / 实时去重：未修改去重逻辑，只新增主循环触发条件测试。
- 启动方式：未修改。
- 配置字段：未修改。

残余风险：

- 尚未覆盖 `poll_loop` 中 `run_auto_catch_up` 抛异常后继续轮询的分支。
- 尚未覆盖 `poll_once` 返回 item 后与 gap 自愈补拉顺序交互的更细路径。
- 尚未做 SQLite 并发压力测试。
- 尚未做 launchd 实际运行验证。
- 其它 CLI limit 参数尚未统一范围化，但当前不是最高优先级。

## 8. 下一步建议

建议下一阶段优先做一个很小的收口分支，而不是马上扩大范围：

- 可选 A：补 `poll_loop` 中 `run_auto_catch_up` 抛异常仍继续进入 `poll_once` 的无网络测试。
- 可选 B：补 `poll_once` 返回新 item 后 `handle_item` 被调用的主循环轻量编排测试。

暂不建议：

- 做 SQLite 并发压力测试。
- 做 launchd 实测。
- 继续泛化参数 clamp。
- 做补拉架构重构。

## 9. 模型建议

下一阶段如果只做 A 或 B 这种 1 到 2 个小型无网络编排测试，建议使用 `GPT-5.5 中`。

如果进入以下任务，应使用 `GPT-5.5 高`：

- 连续 gap、多轮 loop 状态交互。
- SQLite 并发判断。
- launchd 实际运行验证。
- 较大行为重构或补拉架构调整。

## 10. 新 session 交接提示词

新开 session 后可以直接贴：

```text
请继续 /Users/rich/jin10-monitor 项目。

建议模型：GPT-5.5 中。
本轮建议继续一个很小的 poll_loop 无网络编排测试收口；如果进入连续 gap、多轮状态交互、SQLite 并发或 launchd 实测，再切 GPT-5.5 高。

先读取：
1. /Users/rich/jin10-monitor/AGENTS.md
2. /Users/rich/jin10-monitor/docs/status/026-2026-05-20-poll-loop-gap-tests-handoff.md

默认不要回读旧聊天。先执行：
git branch --show-current
git status
git pull --rebase
git log --oneline -6

当前阶段目标：
继续保持无真实 Telegram、无真实 REST、临时 SQLite 或 fake helper；不要做 launchd 实测，不要做 SQLite 并发压力测试，不要重构补拉架构。

已完成：
- crawl_window mock REST 边界测试已完成。
- .env 数值配置范围保护已完成。
- 手动补拉 CLI 参数范围保护已完成。
- catch_up_window mock REST 边界测试已完成。
- run_auto_catch_up 未来游标、最大回看窗口、早退分支、gap 摘要冷却、seen_id 交接测试已完成。
- run_catch_up 手动补拉包装层测试已完成。
- handle_item 实时链路测试已完成。
- poll_loop gap 达阈值触发 run_auto_catch_up(..., trigger="gap") 测试已完成。
- poll_loop 在 AUTO_CATCHUP 关闭或 gap 未达阈值时不触发自动补拉测试已完成。
- 当前 pytest 结果为 86 passed。
- 最新功能测试提交：8d37b2e。

下一步建议：
先只做一个很小的 poll_loop 无网络编排测试：
- run_auto_catch_up 抛异常时，poll_loop 记录 warning 后仍继续本轮 poll_once；或
- poll_once 返回新 item 时，poll_loop 调用 handle_item(session, item, source="rest")。

要求：
- CHANGELOG.md 必须按真实提交日期写入当天小节，不要把多日改动堆在 Unreleased。
- 查询和诊断入口只做只读，不要实现重试队列。
- 优先做最小可靠修复，不要大规模重构模块。
- 继续保护现有补拉去重语义：已成功发送过的 Telegram 不重复补发。
- 如果新增 CLI 用户操作方式，预计需要更新 README.md 和 CHANGELOG.md。
- 修改后给 diff、风险和验证。
- commit/push 前更新 CHANGELOG.md。
- 一般情况直接推进；只有需要重要产品/风险判断时再停下来问我。
```
