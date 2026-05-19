# 项目状态摘要 028：测试阶段复盘与下一步判断

更新时间：2026-05-20（Asia/Shanghai）

## 1. 这份文档的用途

本文件用于在新 session 中快速续接，不需要回读旧聊天。

这份摘要重点覆盖：

- `027` 之后对当前测试覆盖的阶段复盘。
- 是否继续扩张 `poll_loop` / 无网络边界测试的判断。
- 下一阶段建议和模型选择。

## 2. 当前仓库状态

- 项目：jin10-monitor
- GitHub 仓库：https://github.com/hangfo/jin10-monitor
- 本地路径：`/Users/rich/jin10-monitor`
- 分支：`main`
- 当前最新提交：
  - `fd68ae9 docs(status): add poll loop tests handoff`

最近提交：

```text
fd68ae9 docs(status): add poll loop tests handoff
6f5c1a6 test(poll): cover REST item handling
25118b8 test(poll): cover auto catch-up exception path
2b771cb docs(status): add poll loop gap handoff
8d37b2e test(poll): cover gap auto catch-up trigger
6b3c71d docs(status): add realtime handle item handoff
```

本摘要生成前已确认：

- `main` 已与 `origin/main` 同步。
- 工作区开始时干净。
- 完整 pytest 结果为 `88 passed`。

新 session 仍必须重新执行本地 Git 检查，不要只凭本文件判断现场状态。

## 3. 当前测试覆盖复盘

当前测试总数：

```text
88 passed
```

测试分布：

- `tests/test_pure_functions.py`
  - 45 个用例。
- `tests/test_storage.py`
  - 43 个用例。

已经覆盖的高价值无网络区域：

- 数值配置解析与范围保护。
- 手动补拉 CLI 参数范围归一化。
- Telegram 发送结果边界。
- REST 回溯查询 `crawl_window` mock 边界。
- 补拉窗口 `catch_up_window` mock 边界。
- SQLite 历史库、游标、投递去重和诊断状态边界。
- `run_auto_catch_up` 早退、未来游标、最大回看、gap 摘要冷却、`seen_ids` 交接。
- `run_catch_up` 手动包装层发送、跳过、失败、间隔和去重语义。
- `handle_item` 实时处理链路。
- `poll_loop` REST 轮询主循环的 gap、自愈异常和新消息处理编排。

## 4. 阶段判断

结论：不建议继续在 `poll_loop` 里扩张更多低价值测试。

原因：

- `poll_loop` 的核心行为已经被 5 个无网络场景覆盖。
- 继续增加多轮 loop、连续 gap 或日志细节测试，容易变成对实现细节的重复绑定。
- 真正剩余的风险已经不在单个 `poll_loop` 分支，而在更上层的 `main()` / `ws_loop` async 编排。
- `main()` / `ws_loop` 的测试会更接近任务调度和连接生命周期，需要先评估收益与维护成本。

## 5. 当前仍有价值但不应直接开做的方向

### A. `main()` 启动编排评估

潜在覆盖点：

- 启动时 `AUTO_CATCHUP=True` 会先执行 `run_auto_catch_up`。
- `run_auto_catch_up` 异常后仍继续冷启动预加载。
- 冷启动 `poll_once` 中旧消息只预热 `seen_ids` 和入库，不推送。
- 冷启动期间新于 `startup_at` 的消息进入 `handle_item(..., source="rest")`。

风险：

- 需要 fake `aiohttp.ClientSession` 或抽出更小的 helper。
- 如果直接测试 `main()`，容易碰到 `asyncio.gather(ws_loop, poll_loop)` 无限任务。
- 若为了测试而拆生产函数，已经不是纯测试小步，需要更谨慎。

建议：

- 先只做评估，不直接改。
- 如果决定覆盖，优先抽一个很小的纯编排 helper，而不是强测整个 `main()`。

### B. `ws_loop` 编排评估

潜在覆盖点：

- 初始历史列表只预热去重并入库，不推送。
- 后续实时 WS 列表或单条消息调用 `handle_item(..., source="ws")`。
- 心跳 code `1201` 回复空包。

风险：

- 需要 fake WebSocket async iterator 和协议包。
- 当前 WS 解析包含二进制包、登录 secret、xor 解包，测试搭建成本较高。
- 容易把测试写成协议细节复刻，而不是保护业务语义。

建议：

- 暂不做，除非近期出现 WS 相关 bug 或需要改 WS 逻辑。

### C. SQLite 并发 / launchd 实测

现阶段不建议主动进入。

原因：

- SQLite 并发压力测试属于更重的可靠性验证，应该使用 `GPT-5.5 高`，并明确测试边界。
- launchd 实测会触及本机常驻服务状态，不应在没有明确授权时执行。

## 6. 下一步建议

建议下一阶段先停止测试扩张，做一个短决策：

- 如果目标是继续低风险推进：整理一个 `main()` 启动编排测试设计草案，只列方案和风险，不改代码。
- 如果目标是尽快回到运行稳定性：只做只读状态确认，不做 launchd reload / install / 实测。
- 如果目标是收尾当前测试阶段：可以暂时不新增测试，保留当前 `88 passed` 作为阶段基线。

我建议的默认下一步：

1. 不再继续加 `poll_loop` 测试。
2. 先做 `main()` 启动编排测试的方案评估。
3. 评估后再决定是否值得抽 helper 或直接停止。

## 7. 模型建议

下一阶段如果只是做方案评估、阶段复盘、文档整理或只读状态确认，建议使用 `GPT-5.5 中`。

如果进入以下任务，应使用 `GPT-5.5 高`：

- 抽 helper 覆盖 `main()` 启动编排。
- 设计 `ws_loop` fake WebSocket 测试。
- 连续多轮 async 状态交互。
- SQLite 并发判断。
- launchd 实际运行验证。
- 较大行为重构或补拉架构调整。

## 8. 新 session 交接提示词

新开 session 后可以直接贴：

```text
请继续 /Users/rich/jin10-monitor 项目。

建议模型：GPT-5.5 中。
本轮建议先做 main() 启动编排测试方案评估，只列方案、收益、风险，不急着改代码；如果决定抽 helper 或测试 main()/ws_loop 顶层 async 编排，再切 GPT-5.5 高。

先读取：
1. /Users/rich/jin10-monitor/AGENTS.md
2. /Users/rich/jin10-monitor/docs/status/028-2026-05-20-test-stage-review.md

默认不要回读旧聊天。先执行：
git branch --show-current
git status
git pull --rebase
git log --oneline -6

当前阶段目标：
不要继续扩张 poll_loop 低价值测试。先评估 main() 启动编排是否值得覆盖，继续保持无真实 Telegram、无真实 REST、临时 SQLite 或 fake helper；不要做 launchd 实测，不要做 SQLite 并发压力测试，不要重构补拉架构。

已完成：
- crawl_window mock REST 边界测试已完成。
- .env 数值配置范围保护已完成。
- 手动补拉 CLI 参数范围保护已完成。
- catch_up_window mock REST 边界测试已完成。
- run_auto_catch_up 未来游标、最大回看窗口、早退分支、gap 摘要冷却、seen_id 交接测试已完成。
- run_catch_up 手动补拉包装层测试已完成。
- handle_item 实时链路测试已完成。
- poll_loop 主循环 5 个无网络场景已完成。
- 当前 pytest 结果为 88 passed。
- 最新测试阶段复盘文档：028。

下一步建议：
只做 main() 启动编排测试设计评估：
- 可覆盖什么。
- 需要 fake 什么。
- 是否需要抽 helper。
- 风险是否值得。
不要直接进入 launchd 实测、SQLite 并发压力测试或补拉架构重构。

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
