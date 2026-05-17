# 项目状态摘要 023：自动补拉测试阶段阶段性收口

更新时间：2026-05-18（Asia/Shanghai）

## 1. 这份文档的用途

本文件用于在新 session 中快速续接，不需要回读旧聊天。

这份摘要重点覆盖：

- 本 session 最早目标与当前完成情况的对照。
- 参数范围保护为什么已经收口。
- 自动补拉与补拉窗口功能测试已经补到哪里。
- 当前 Git 状态、验证结果、风险判断和下一步建议。

## 2. 当前仓库状态

- 项目：jin10-monitor
- GitHub 仓库：https://github.com/hangfo/jin10-monitor
- 本地路径：`/Users/rich/jin10-monitor`
- 分支：`main`
- 当前最新提交：
  - `bd2ef94 test(catchup): cover auto seen id handoff`

最近提交：

```text
bd2ef94 test(catchup): cover auto seen id handoff
2248691 test(catchup): cover auto skip branches
47f1b55 test(catchup): cover auto max hours limit
8297c04 test(catchup): cover future auto cursor recovery
7abba04 test(catchup): cover REST window edges
61a9f77 docs(status): add cli clamp handoff
62675bd fix(cli): clamp catchup limit arguments
3975e6b docs(status): add config clamp handoff
df549b3 fix(config): clamp remaining numeric envs
0e2540e fix(config): clamp catchup send interval
45232a7 fix(config): clamp catchup send limit
e2da331 fix(config): clamp catchup store limit
293867a fix(config): clamp poll interval range
d3e0f92 fix(config): clamp websocket reconnect delay
```

本摘要生成前已确认：

- `main` 已与 `origin/main` 同步。
- 工作区干净。

新 session 仍必须重新执行本地 Git 检查，不要只凭本文件判断现场状态。

## 3. 对照本 session 最早提示词

最早目标：

- 继续最小 pytest 骨架阶段。
- P0 Telegram 发送结果、P1 crawl_window 首个 mock REST、P2 gap 摘要冷却已完成。
- 下一步优先二选一：
  1. 继续补 `crawl_window` mock REST 边界。
  2. 做数值配置上下限保护评估清单，不直接批量 clamp。

本 session 实际完成：

- 完成 `crawl_window` mock REST 边界测试：
  - `962717c test(lookup): cover crawl window edges`
- 完成数值配置上下限保护评估清单：
  - `db2ba62 docs(config): assess numeric clamp ranges`
- 完成核心 `.env` 数值配置范围保护：
  - `d3e0f92` 到 `df549b3`
- 完成手动补拉 CLI 参数范围保护：
  - `62675bd fix(cli): clamp catchup limit arguments`
- 完成参数线 handoff：
  - `3975e6b docs(status): add config clamp handoff`
  - `61a9f77 docs(status): add cli clamp handoff`
- 按用户反馈收口参数线，回到功能模块测试。
- 完成 `catch_up_window` 和 `run_auto_catch_up` 多个无网络功能边界测试：
  - `7abba04`
  - `8297c04`
  - `47f1b55`
  - `2248691`
  - `bd2ef94`

未遗漏的要求：

- CHANGELOG 已按真实提交日期分组：`2026-05-17` 与 `2026-05-18`。
- 查询和诊断入口仍只读；没有实现重试队列。
- 没有大规模重构模块。
- 没有改动 Telegram 已成功发送不重复补发语义。
- 新增 / 改变 CLI 行为时已更新 README 和 CHANGELOG。
- 所有改动均提交前验证，并按小步提交推送。

刻意收口不继续的事项：

- 不继续主动扩展参数 clamp / 参数测试。剩余 `--limit`、`--history-limit`、`--telegram-status-limit`、`--lookup-max-pages` 等不是当前最高风险。
- 不在本 session 进入自动补拉主循环 async 编排测试。
- 不在本 session 进入 SQLite 并发或 launchd 实际运行验证。

## 4. 已完成的配置范围保护

`.env` 数值配置：

- `WS_RECONNECT_DELAY >= 1`
- `POLL_INTERVAL = 1..60`
- `CATCHUP_MAX_HOURS = 1..168`
- `CATCHUP_MAX_STORE = 20..5000`
- `CATCHUP_MAX_SEND = 0..300`
- `CATCHUP_SEND_INTERVAL = 0..10`
- `AUTO_CATCHUP_GAP_SECONDS = 0..86400`
- `SHOW_DELAY_IF_SECONDS = 0..3600`

手动补拉 CLI 参数：

- `--catch-up-max-store = 20..5000`
- `--catch-up-max-send = 0..300`
- `--catch-up-send-interval = 0..10`

保留的特殊语义：

- `CATCHUP_MAX_SEND=0` / `--catch-up-max-send 0`：关闭逐条补发。
- `CATCHUP_SEND_INTERVAL=0` / `--catch-up-send-interval 0`：逐条补发不等待。
- `AUTO_CATCHUP_GAP_SECONDS=0`：关闭 gap 自愈补拉。
- `SHOW_DELAY_IF_SECONDS=0`：关闭延迟提示。

## 5. 已完成的功能模块测试

### 5.1 `crawl_window`

已覆盖：

- app_id 失败 fallback。
- 空页停止。
- 重复 ID 去重。
- 未命中关键词仍在 `all_items`，但不进入 `matched_items`。

### 5.2 `catch_up_window`

已覆盖：

- 窗口过滤。
- 已入库统计。
- 已成功投递过的 Telegram 不进入补发候选。
- `max_store` 截断。
- 跨页 cursor 推进。
- app_id 失败 fallback。
- 空页停止。
- 跨页重复 ID 去重。
- 未命中关键词只入库不补发。

### 5.3 `run_auto_catch_up`

已覆盖：

- gap 摘要冷却中不发送。
- gap 摘要冷却后发送并写入状态。
- `last_ingested_at` 跑到未来时，从历史库最新有效游标回退。
- 未来游标但无可恢复历史游标时安全跳过。
- 超过 `CATCHUP_MAX_HOURS` 时截断补拉窗口。
- 缺少 `last_ingested_at` 时早退。
- `last_ingested_at` 格式错误时返回错误。
- 回退缓冲后没有离线窗口时早退。
- 自动补拉成功后，将 `seen_item_ids` 预热到内存去重集合，避免实时链路重复处理。

## 6. 当前测试覆盖概览

当前 pytest 用例数：

```text
72 passed
```

测试文件：

- `tests/test_pure_functions.py`
  - 45 个用例。
- `tests/test_storage.py`
  - 27 个用例。

最近一次完整验证：

```bash
git diff --check
.venv/bin/python -m pytest
```

结果：

```text
72 passed
```

## 7. 当前风险判断

整体风险等级：低。

影响范围：

- WebSocket：未修改生产逻辑。
- REST：未修改真实抓取逻辑；新增 mock REST 测试。
- Telegram 推送：未修改发送逻辑；继续保护已成功发送不重复补发。
- SQLite 历史库：未修改 schema；测试使用临时 SQLite。
- 补拉去重：新增测试保护自动补拉到实时链路的内存去重交接。
- 启动方式：未修改。
- 配置字段：已完成范围保护，当前不建议继续扩展参数线。

残余风险：

- 尚未覆盖 `poll_loop` 主循环里 gap 检测触发 `run_auto_catch_up` 的 async 编排。
- 尚未做 SQLite 并发压力测试。
- 尚未做 launchd 实际运行验证。
- 其它 CLI limit 参数尚未统一范围化，但当前不是最高优先级。

## 8. 下一步建议

建议优先二选一：

1. 继续功能链路测试，使用 `GPT-5.5 中`
   - 补 `run_catch_up` 手动补拉包装层测试。
   - 重点保护 Telegram 保护跳过、发送状态统计、`mark_delivery` 只在发送成功时写入等语义。
   - 保持 fake Telegram / 临时 SQLite，不触发真实 Telegram。

2. 进入 `poll_loop` gap 触发测试，切 `GPT-5.5 高`
   - 需要 mock `poll_once`、`run_auto_catch_up`、`asyncio.sleep` 或设计可控退出。
   - async 编排复杂度更高，建议高推理档位。

暂不建议：

- 继续泛化参数 clamp。
- 做 SQLite 并发压力测试。
- 做 launchd 实测。
- 做补拉架构重构。

## 9. 模型建议

下一阶段默认使用 `GPT-5.5 中`。

如果选择 `run_catch_up` 手动补拉包装层测试，`GPT-5.5 中` 足够。

如果选择 `poll_loop` 主循环 gap 触发测试、SQLite 并发判断、launchd 实际运行验证或较大行为重构，再切 `GPT-5.5 高`。

## 10. 新 session 交接提示词

新开 session 后可以直接贴：

```text
请继续 /Users/rich/jin10-monitor 项目。

建议模型：GPT-5.5 中。
如需进入 poll_loop 主循环 gap 触发 async 测试、SQLite 并发判断、launchd 实际运行验证或较大行为重构，再切 GPT-5.5 高。

先读取：
1. /Users/rich/jin10-monitor/AGENTS.md
2. /Users/rich/jin10-monitor/docs/status/023-2026-05-18-auto-catchup-tests-handoff.md

默认不要回读旧聊天。先执行：
git branch --show-current
git status
git pull --rebase
git log --oneline -6

当前阶段目标：
继续功能链路可靠性测试。参数 clamp 阶段已经收口，不要继续泛化参数测试，除非发现明确运行风险。优先推进 run_catch_up 手动补拉包装层测试，保持无真实 Telegram、无真实 REST、临时 SQLite。

已完成：
- crawl_window mock REST 边界测试已完成。
- .env 数值配置范围保护已完成。
- 手动补拉 CLI 参数范围保护已完成。
- catch_up_window mock REST 边界测试已完成。
- run_auto_catch_up 未来游标、最大回看窗口、早退分支、gap 摘要冷却、seen_id 交接测试已完成。
- 当前 pytest 结果为 72 passed。
- 状态摘要 023 已完成。

下一步建议：
优先做 run_catch_up 手动补拉包装层测试：
- telegram_enabled=False 时不发送 Telegram。
- telegram_skip_reason 命中时记录 skipped 状态但不写 delivery_log。
- send_telegram 成功时 mark_delivery 并增加 telegram_sent。
- send_telegram 失败时只记录状态，不写成功投递去重。

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
