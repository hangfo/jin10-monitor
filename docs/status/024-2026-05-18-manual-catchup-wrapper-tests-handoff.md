# 项目状态摘要 024：手动补拉包装层测试收口

更新时间：2026-05-18（Asia/Shanghai）

## 1. 这份文档的用途

本文件用于在新 session 中快速续接，不需要回读旧聊天。

这份摘要重点覆盖：

- `023` 后续建议中的 `run_catch_up` 手动补拉包装层测试完成情况。
- 当前 Git 状态、验证结果、风险判断。
- 下一阶段是否继续使用 `GPT-5.5 中`，以及何时切到 `GPT-5.5 高`。

## 2. 当前仓库状态

- 项目：jin10-monitor
- GitHub 仓库：https://github.com/hangfo/jin10-monitor
- 本地路径：`/Users/rich/jin10-monitor`
- 分支：`main`
- 当前最新提交：
  - `4e8c37e test(catchup): cover manual catch-up wrapper`

最近提交：

```text
4e8c37e test(catchup): cover manual catch-up wrapper
35314a6 docs(status): add auto catchup tests handoff
bd2ef94 test(catchup): cover auto seen id handoff
2248691 test(catchup): cover auto skip branches
47f1b55 test(catchup): cover auto max hours limit
8297c04 test(catchup): cover future auto cursor recovery
```

本摘要生成前已确认：

- `main` 已与 `origin/main` 同步。
- 工作区干净。

新 session 仍必须重新执行本地 Git 检查，不要只凭本文件判断现场状态。

## 3. 本阶段完成内容

`023` 的下一步建议是优先补 `run_catch_up` 手动补拉包装层测试。本阶段已完成并提交：

- `4e8c37e test(catchup): cover manual catch-up wrapper`

新增测试全部位于 `tests/test_storage.py`，使用：

- fake `catch_up_window`
- fake `send_telegram`
- fake `asyncio.sleep`
- 临时 SQLite 历史库

未触发：

- 真实 Telegram
- 真实 REST
- launchd
- WebSocket

## 4. `run_catch_up` 已覆盖语义

新增 8 个包装层测试，覆盖：

- `telegram_enabled=False` 时不发送 Telegram，不写投递状态。
- 手动补拉窗口参数正确传给 `catch_up_window`：
  - `source="catchup_manual"`
  - `max_store`
  - `max_send`
- `catch_up_window` 返回 `ok=False` 时早退，不进入 Telegram 发送。
- `telegram_skip_reason` 命中时：
  - 记录 `telegram_skipped`
  - 写入 `telegram_delivery_status` 的 `skipped` 状态
  - 不写 `delivery_log`
- `send_telegram` 成功时：
  - 调用 `mark_delivery`
  - 增加 `telegram_sent`
  - 写入 `telegram_delivery_status` 的 `sent` 状态
- `send_telegram` 失败时：
  - 增加 `telegram_failed`
  - 写入 `telegram_delivery_status` 的 `failed` 状态
  - 不写 `delivery_log`
- 多条补发候选逐条处理，成功和失败可以混合记录。
- `send_interval > 0` 时按候选等待；`send_interval=0` 时不等待。

重点保护的既有语义：

- 已成功发送过的 Telegram 仍以 `delivery_log` 作为去重依据。
- 失败、超时未知、保护跳过只进入诊断状态表，不污染成功投递去重表。

## 5. 当前测试覆盖概览

当前 pytest 用例数：

```text
80 passed
```

测试文件：

- `tests/test_pure_functions.py`
  - 45 个用例。
- `tests/test_storage.py`
  - 35 个用例。

最近一次完整验证：

```bash
git diff --check
.venv/bin/python -m pytest tests/test_storage.py
.venv/bin/python -m pytest
```

结果：

```text
tests/test_storage.py: 35 passed
full pytest: 80 passed
```

## 6. 当前风险判断

整体风险等级：低。

影响范围：

- WebSocket：未修改。
- REST：未修改真实抓取逻辑；测试 fake `catch_up_window`。
- Telegram 推送：未修改发送逻辑；测试 fake `send_telegram`。
- SQLite 历史库：未修改 schema；测试使用临时 SQLite。
- 补拉去重：新增测试保护成功发送才写 `delivery_log`。
- 启动方式：未修改。
- 配置字段：未修改。

残余风险：

- 尚未覆盖 `poll_loop` 主循环中 gap 检测触发 `run_auto_catch_up` 的 async 编排。
- 尚未做 SQLite 并发压力测试。
- 尚未做 launchd 实际运行验证。
- 其它 CLI limit 参数尚未统一范围化，但当前不是最高优先级。

## 7. 下一步建议

建议优先：

1. 使用 `GPT-5.5 中` 继续做轻量功能链路测试或整理阶段性文档。
   - 可考虑为已覆盖的补拉链路做少量可读性整理，但不要重构生产逻辑。
   - 若继续加测试，优先选择无真实网络、临时 SQLite、fake helper 的小边界。

2. 如果要进入 `poll_loop` gap 触发 async 编排测试，建议切 `GPT-5.5 高`。
   - 这需要 mock `poll_once`、`run_auto_catch_up`、`asyncio.sleep` 或设计可控退出。
   - 该测试更接近主循环调度行为，复杂度高于当前包装层测试。

暂不建议：

- 继续泛化参数 clamp。
- 做 SQLite 并发压力测试。
- 做 launchd 实测。
- 做补拉架构重构。

## 8. 模型建议

下一阶段默认使用 `GPT-5.5 中`。

如果进入以下任务，再切 `GPT-5.5 高`：

- `poll_loop` 主循环 gap 触发 async 测试。
- SQLite 并发判断。
- launchd 实际运行验证。
- 较大行为重构或补拉架构调整。

## 9. 新 session 交接提示词

新开 session 后可以直接贴：

```text
请继续 /Users/rich/jin10-monitor 项目。

建议模型：GPT-5.5 中。
如需进入 poll_loop 主循环 gap 触发 async 测试、SQLite 并发判断、launchd 实际运行验证或较大行为重构，再切 GPT-5.5 高。

先读取：
1. /Users/rich/jin10-monitor/AGENTS.md
2. /Users/rich/jin10-monitor/docs/status/024-2026-05-18-manual-catchup-wrapper-tests-handoff.md

默认不要回读旧聊天。先执行：
git branch --show-current
git status
git pull --rebase
git log --oneline -6

当前阶段目标：
继续功能链路可靠性测试。参数 clamp 阶段已经收口，不要继续泛化参数测试，除非发现明确运行风险。

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
- 当前 pytest 结果为 80 passed。
- 最新功能测试提交：4e8c37e。

下一步建议：
如果继续小步测试，优先保持无真实 Telegram、无真实 REST、临时 SQLite。若要进入 poll_loop 主循环 gap 触发 async 编排测试，建议切 GPT-5.5 高。

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
