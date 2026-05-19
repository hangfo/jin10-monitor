# 项目状态摘要 029：main 启动编排测试方案评估

更新时间：2026-05-20（Asia/Shanghai）

## 1. 这份文档的用途

本文件用于在新 session 中快速续接，不需要回读旧聊天。

这份摘要重点覆盖：

- `028` 之后对 `main()` 启动编排测试的方案评估。
- 可覆盖点、需要 fake 的依赖、是否需要抽 helper。
- 是否值得立即进入实现，以及下一阶段模型建议。

## 2. 当前仓库状态

- 项目：jin10-monitor
- GitHub 仓库：https://github.com/hangfo/jin10-monitor
- 本地路径：`/Users/rich/jin10-monitor`
- 分支：`main`
- 当前最新提交：
  - `a68980e docs(status): add test stage review`

最近提交：

```text
a68980e docs(status): add test stage review
fd68ae9 docs(status): add poll loop tests handoff
6f5c1a6 test(poll): cover REST item handling
25118b8 test(poll): cover auto catch-up exception path
2b771cb docs(status): add poll loop gap handoff
8d37b2e test(poll): cover gap auto catch-up trigger
```

本摘要生成前已确认：

- `main` 已与 `origin/main` 同步。
- 工作区开始时干净。
- 最近完整 pytest 基线为 `88 passed`。

新 session 仍必须重新执行本地 Git 检查，不要只凭本文件判断现场状态。

## 3. `main()` 当前启动编排

当前 `main()` 的关键流程：

1. 初始化历史库。
2. 记录启动时间 `startup_at`。
3. 创建 `aiohttp.ClientSession`。
4. 如果 `AUTO_CATCHUP=True`：
   - 调用 `run_auto_catch_up(session, startup_at)`。
   - 成功、跳过、失败或异常都只记录日志，然后继续启动。
5. 冷启动预加载：
   - 调用 `poll_once(session)`。
   - 旧消息写入 `seen_ids`，并以 `source="cold_start"` 入库。
   - 发生时间晚于 `startup_at` 的消息进入 `pending_realtime`。
   - `pending_realtime` 中仍然新的消息会调用 `handle_item(session, item, source="rest")`。
6. 最后并发运行：
   - `ws_loop(session)`
   - `poll_loop(session)`

## 4. 值得覆盖的业务语义

如果后续要测试 `main()` 启动编排，最高价值场景是：

- 启动补拉异常不阻断冷启动预加载。
- `AUTO_CATCHUP=False` 时跳过启动补拉。
- 冷启动旧消息只预热去重和入库，不推送 Telegram。
- 冷启动期间新于 `startup_at` 的消息进入实时处理链路。
- 进入常驻阶段前，确实会安排 `ws_loop` 和 `poll_loop`。

这些场景保护的是启动期“不漏、不刷屏、不被补拉异常卡死”的业务语义。

## 5. 方案 A：直接测试 `main()`

做法：

- monkeypatch `aiohttp.ClientSession` 为 fake async context manager。
- monkeypatch `run_auto_catch_up`、`poll_once`、`handle_item`。
- monkeypatch `asyncio.gather`，让它记录 `ws_loop(session)` 和 `poll_loop(session)` 后可控退出。
- monkeypatch `datetime.now()` 固定 `startup_at`。

优点：

- 不改生产代码。
- 覆盖最接近真实入口的执行顺序。

问题：

- fake 面较大，包括 `ClientSession`、`asyncio.gather`、时间、多个 async 函数。
- `asyncio.gather` 的 coroutine 处理容易产生未 await 噪音，测试会偏脆。
- 一条测试会绑定 `main()` 内部实现顺序，后续轻微整理也可能误伤测试。

判断：

- 不建议作为下一步默认实现。
- 只有当不愿意抽 helper 且只做 1 条 smoke 式测试时才考虑。

## 6. 方案 B：抽小型启动 helper 后测试

做法：

- 从 `main()` 中抽出一个小型 helper，例如：
  - `async def run_startup_sequence(session, startup_at) -> None`
- helper 只负责：
  - 启动自动补拉。
  - 冷启动预加载。
  - 处理 `pending_realtime`。
- `main()` 保留：
  - 初始化数据库。
  - 创建 `ClientSession`。
  - 调用 helper。
  - `asyncio.gather(ws_loop, poll_loop)`。

优点：

- 测试不需要 fake `ClientSession` 或 `asyncio.gather`。
- 可以直接复用现有 fake async helper 风格。
- 覆盖的业务语义更清晰：启动补拉、冷启动预热、冷启动期间新消息处理。

问题：

- 需要修改生产代码结构。
- 虽然是小 helper，但仍属于启动路径重组，需要更谨慎。
- 需要确认 `main()` 中日志和顺序不被意外改变。

建议测试切片：

- 第一条：`run_auto_catch_up` 抛异常后仍调用 `poll_once` 做冷启动预加载。
- 第二条：旧消息只 `save_history_item(..., source="cold_start")` 和 `remember_seen_id`，不调用 `handle_item`。
- 第三条：新于 `startup_at` 的消息调用 `handle_item(..., source="rest")`。

判断：

- 如果决定继续覆盖 `main()` 启动编排，这是最推荐方案。
- 因为会抽 helper，建议使用 `GPT-5.5 高`，并先给修改计划等确认。

## 7. 方案 C：暂不实现

做法：

- 保留当前 `88 passed` 作为阶段基线。
- 不继续扩张测试。
- 只在未来改动启动逻辑、冷启动逻辑或出现相关 bug 时再补测试。

优点：

- 零运行风险。
- 避免为了覆盖率而绑定实现细节。
- 当前高价值底层和中层逻辑已经有较多无网络保护。

问题：

- `main()` 启动顺序仍主要靠代码阅读和人工判断。
- 如果未来改冷启动逻辑，缺少启动级回归测试提醒。

判断：

- 如果当前目标是稳定收口，这是合理选择。
- 如果还要继续小步提高保护，优先选方案 B。

## 8. 最终建议

默认建议：暂不直接实现 `main()` 测试。

如果用户希望继续推进测试，建议进入方案 B：

- 使用 `GPT-5.5 高`。
- 先给小型生产改动计划。
- 只抽一个 `run_startup_sequence(session, startup_at)` helper。
- 第一轮只补 1 到 2 条测试，不碰 `ws_loop`、不碰 launchd、不碰 SQLite 并发。

不建议：

- 直接测试完整 `main()` 并 fake `asyncio.gather`。
- 现在测试 `ws_loop`。
- 做 launchd 实测。
- 做 SQLite 并发压力测试。
- 重构补拉架构。

## 9. 下一步模型建议

- 如果只是阅读本评估、做文档整理或决定是否继续：`GPT-5.5 中`。
- 如果要抽 `run_startup_sequence` helper 并写启动编排测试：`GPT-5.5 高`。
- 如果要测试 `ws_loop`、连续多轮 async 状态、SQLite 并发或 launchd 实测：`GPT-5.5 高`。

## 10. 新 session 交接提示词

新开 session 后可以直接贴：

```text
请继续 /Users/rich/jin10-monitor 项目。

建议模型：GPT-5.5 高，如果决定抽 run_startup_sequence helper 并写 main() 启动编排测试；如果只是继续评估或文档整理，用 GPT-5.5 中。

先读取：
1. /Users/rich/jin10-monitor/AGENTS.md
2. /Users/rich/jin10-monitor/docs/status/029-2026-05-20-main-startup-test-assessment.md

默认不要回读旧聊天。先执行：
git branch --show-current
git status
git pull --rebase
git log --oneline -6

当前阶段目标：
不要继续扩张 poll_loop 低价值测试。若继续测试，优先按评估方案 B：小步抽 run_startup_sequence(session, startup_at) helper，再补 1 到 2 条 main() 启动编排无网络测试。继续保持无真实 Telegram、无真实 REST、临时 SQLite 或 fake helper；不要做 launchd 实测，不要做 SQLite 并发压力测试，不要重构补拉架构。

已完成：
- crawl_window mock REST 边界测试已完成。
- .env 数值配置范围保护已完成。
- 手动补拉 CLI 参数范围保护已完成。
- catch_up_window mock REST 边界测试已完成。
- run_auto_catch_up 未来游标、最大回看窗口、早退分支、gap 摘要冷却、seen_id 交接测试已完成。
- run_catch_up 手动补拉包装层测试已完成。
- handle_item 实时链路测试已完成。
- poll_loop 主循环 5 个无网络场景已完成。
- main() 启动编排测试方案评估已完成。
- 当前 pytest 基线为 88 passed。

下一步建议：
如果继续写代码，先给修改计划并等确认：
- 抽 run_startup_sequence(session, startup_at) helper。
- main() 调用 helper 后再 asyncio.gather(ws_loop, poll_loop)。
- 第一轮只测 run_auto_catch_up 异常后仍继续冷启动预加载，或冷启动期间新消息进入 handle_item(..., source="rest")。

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
