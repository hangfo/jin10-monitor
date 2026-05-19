# 项目状态摘要 025：实时处理链路测试收口

更新时间：2026-05-19（Asia/Shanghai）

## 1. 这份文档的用途

本文件用于在新 session 中快速续接，不需要回读旧聊天。

这份摘要重点覆盖：

- `024` 之后新增的 `handle_item` 实时处理链路测试。
- 当前 Git 状态、验证结果、风险判断。
- 下一阶段建议：是否继续 `GPT-5.5 中`，或切 `GPT-5.5 高` 进入 `poll_loop` 主循环 gap 触发测试。

## 2. 当前仓库状态

- 项目：jin10-monitor
- GitHub 仓库：https://github.com/hangfo/jin10-monitor
- 本地路径：`/Users/rich/jin10-monitor`
- 分支：`main`
- 当前最新提交：
  - `5ddf7c7 test(realtime): cover handle item delivery status`

最近提交：

```text
5ddf7c7 test(realtime): cover handle item delivery status
da1c9ea docs(status): add manual catchup wrapper handoff
4e8c37e test(catchup): cover manual catch-up wrapper
35314a6 docs(status): add auto catchup tests handoff
bd2ef94 test(catchup): cover auto seen id handoff
2248691 test(catchup): cover auto skip branches
```

本摘要生成前已确认：

- `main` 已与 `origin/main` 同步。
- 工作区干净。
- 完整 pytest 结果为 `83 passed`。

新 session 仍必须重新执行本地 Git 检查，不要只凭本文件判断现场状态。

## 3. 本阶段完成内容

`024` 后建议继续小步测试，优先保持无真实 Telegram、无真实 REST、临时 SQLite。本阶段已完成并提交：

- `5ddf7c7 test(realtime): cover handle item delivery status`

新增测试全部位于 `tests/test_storage.py`，使用：

- fake `send_telegram`
- 临时 SQLite 历史库

未触发：

- 真实 Telegram
- 真实 REST
- launchd
- WebSocket

## 4. `handle_item` 已覆盖语义

新增 3 个实时链路测试，覆盖：

- 命中关键词且 Telegram 发送成功：
  - 历史入库。
  - 写入 `delivery_log`，`mode="realtime"`。
  - 写入 `telegram_delivery_status` 的 `sent` 状态。
- 命中关键词但 Telegram 发送失败：
  - 历史入库。
  - 写入 `telegram_delivery_status` 的 `failed` 状态。
  - 不写 `delivery_log`。
- 未命中关键词：
  - 历史入库。
  - 不调用 `send_telegram`。
  - 不写 `delivery_log` 或 Telegram 投递状态。

重点保护的既有语义：

- 实时链路和补拉链路一致：只有成功发送才写成功投递去重表。
- 失败、超时未知、保护跳过等非成功状态只进入诊断表，不污染成功投递去重。

## 5. 当前测试覆盖概览

当前 pytest 用例数：

```text
83 passed
```

测试文件：

- `tests/test_pure_functions.py`
  - 45 个用例。
- `tests/test_storage.py`
  - 38 个用例。

最近一次完整验证：

```bash
git diff --check
.venv/bin/python -m pytest tests/test_storage.py
.venv/bin/python -m pytest
```

结果：

```text
tests/test_storage.py: 38 passed
full pytest: 83 passed
```

本摘要生成时再次运行：

```text
.venv/bin/python -m pytest
83 passed
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

## 7. 当前风险判断

整体风险等级：低。

影响范围：

- WebSocket：未修改。
- REST：未触发真实 REST。
- Telegram 推送：未修改发送逻辑；测试 fake `send_telegram`。
- SQLite 历史库：未修改 schema；测试使用临时 SQLite。
- 补拉 / 实时去重：新增测试保护成功发送才写 `delivery_log`。
- 启动方式：未修改。
- 配置字段：未修改。

残余风险：

- 尚未覆盖 `poll_loop` 主循环中 gap 检测触发 `run_auto_catch_up` 的 async 编排。
- 尚未做 SQLite 并发压力测试。
- 尚未做 launchd 实际运行验证。
- 其它 CLI limit 参数尚未统一范围化，但当前不是最高优先级。

## 8. 下一步建议

建议下一阶段进入 `poll_loop` 主循环 gap 触发 `run_auto_catch_up` 的 async 编排测试，并切 `GPT-5.5 高`。

原因：

- 当前轻量功能链路测试已经覆盖到 `handle_item` 和补拉包装层。
- 剩余最高价值风险点是主循环是否在 REST 轮询停顿后正确触发 gap 自愈补拉。
- 该测试需要 mock `poll_once`、`run_auto_catch_up`、`asyncio.sleep`，并设计可控退出，复杂度高于前面的单函数包装层测试。

暂不建议：

- 继续泛化参数 clamp。
- 做 SQLite 并发压力测试。
- 做 launchd 实测。
- 做补拉架构重构。

## 9. 模型建议

下一阶段建议使用 `GPT-5.5 高`。

如果只继续整理文档或加极小无网络边界测试，`GPT-5.5 中` 仍然足够。

如果进入以下任务，应使用 `GPT-5.5 高`：

- `poll_loop` 主循环 gap 触发 async 测试。
- SQLite 并发判断。
- launchd 实际运行验证。
- 较大行为重构或补拉架构调整。

## 10. 新 session 交接提示词

新开 session 后可以直接贴：

```text
请继续 /Users/rich/jin10-monitor 项目。

建议模型：GPT-5.5 高。
本轮建议进入 poll_loop 主循环 gap 触发 run_auto_catch_up 的 async 编排测试。
如果只是继续文档整理或极小无网络边界测试，可用 GPT-5.5 中。

先读取：
1. /Users/rich/jin10-monitor/AGENTS.md
2. /Users/rich/jin10-monitor/docs/status/025-2026-05-19-realtime-handle-item-tests-handoff.md

默认不要回读旧聊天。先执行：
git branch --show-current
git status
git pull --rebase
git log --oneline -6

当前阶段目标：
进入 poll_loop 主循环 gap 触发 run_auto_catch_up 的 async 编排测试。继续保持无真实 Telegram、无真实 REST、临时 SQLite 或 fake helper；不要做 launchd 实测，不要做 SQLite 并发压力测试，不要重构补拉架构。

已完成：
- crawl_window mock REST 边界测试已完成。
- .env 数值配置范围保护已完成。
- 手动补拉 CLI 参数范围保护已完成。
- catch_up_window mock REST 边界测试已完成。
- run_auto_catch_up 未来游标、最大回看窗口、早退分支、gap 摘要冷却、seen_id 交接测试已完成。
- run_catch_up 手动补拉包装层测试已完成：
  - Telegram 关闭不发送。
  - 窗口失败早退。
  - skip guard 只写 skipped 状态，不写 delivery_log。
  - 发送成功才 mark_delivery。
  - 发送失败只写诊断状态，不写成功投递去重。
  - 多条候选逐条处理，send_interval=0 不等待。
- handle_item 实时链路测试已完成：
  - 发送成功写 realtime delivery_log。
  - 发送失败只写 telegram_delivery_status。
  - 未命中关键词只入库不发送。
- 当前 pytest 结果为 83 passed。
- 最新功能测试提交：5ddf7c7。

下一步建议：
先只做 poll_loop gap 触发的一两个关键无网络测试：
- AUTO_CATCHUP 开启且 gap_seconds >= AUTO_CATCHUP_GAP_SECONDS 时调用 run_auto_catch_up(session, now, trigger="gap")。
- AUTO_CATCHUP 关闭或 gap 未达阈值时不调用 run_auto_catch_up。

测试设计建议：
- mock poll_once 返回空列表。
- mock run_auto_catch_up 记录调用。
- mock asyncio.sleep 抛出自定义异常让 poll_loop 可控退出。
- 如需固定时间，优先用小 helper 或 monkeypatch datetime；不要大规模重构生产逻辑。

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
