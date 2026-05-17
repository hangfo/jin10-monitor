# 项目状态摘要 022：手动补拉 CLI 参数范围保护已完成

更新时间：2026-05-17（Asia/Shanghai）

## 1. 这份文档的用途

本文件用于在新 session 中快速续接，不需要回读旧聊天。

这份摘要重点覆盖：

- `.env` 数值配置范围保护已经完成。
- 手动补拉 CLI 参数范围保护已经完成。
- 当前 Git 状态、验证结果、风险判断和下一步建议。

## 2. 当前仓库状态

- 项目：jin10-monitor
- GitHub 仓库：https://github.com/hangfo/jin10-monitor
- 本地路径：`/Users/rich/jin10-monitor`
- 分支：`main`
- 当前最新提交：
  - `62675bd fix(cli): clamp catchup limit arguments`

最近提交：

```text
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

## 3. 本阶段已完成内容

### 3.1 `.env` 数值配置范围保护

已完成并推送：

- `WS_RECONNECT_DELAY >= 1`
- `POLL_INTERVAL = 1..60`
- `CATCHUP_MAX_HOURS = 1..168`
- `CATCHUP_MAX_STORE = 20..5000`
- `CATCHUP_MAX_SEND = 0..300`
- `CATCHUP_SEND_INTERVAL = 0..10`
- `AUTO_CATCHUP_GAP_SECONDS = 0..86400`
- `SHOW_DELAY_IF_SECONDS = 0..3600`

保留的特殊语义：

- `CATCHUP_MAX_SEND=0`：关闭逐条补发。
- `CATCHUP_SEND_INTERVAL=0`：逐条补发不等待。
- `AUTO_CATCHUP_GAP_SECONDS=0`：关闭 gap 自愈补拉。
- `SHOW_DELAY_IF_SECONDS=0`：关闭延迟提示。

相关提交：

```text
d3e0f92 fix(config): clamp websocket reconnect delay
293867a fix(config): clamp poll interval range
e2da331 fix(config): clamp catchup store limit
45232a7 fix(config): clamp catchup send limit
0e2540e fix(config): clamp catchup send interval
df549b3 fix(config): clamp remaining numeric envs
```

### 3.2 手动补拉 CLI 参数范围保护

提交：

- `62675bd fix(cli): clamp catchup limit arguments`

已完成：

- `--catch-up-max-store` 限制为 `20..5000`。
- `--catch-up-max-send` 限制为 `0..300`。
- `--catch-up-send-interval` 限制为 `0..10`。
- 新增 `clamp_int_value()` / `clamp_float_value()`，让 `.env` 与 CLI 共用同一 clamp 行为。
- 新增 `normalized_catchup_limits()`，在进入 `run_catch_up()` 前统一规范化手动补拉参数。
- CLI help 已标明范围。
- README 已补充手动补拉 CLI 参数范围。
- CHANGELOG 已按 `2026-05-17` 小节记录。

保留的特殊语义：

- `--catch-up-max-send 0`：关闭逐条补发。
- `--catch-up-send-interval 0`：逐条补发不等待。

## 4. 当前测试覆盖概览

当前 pytest 用例数：

```text
61 passed
```

测试文件：

- `tests/test_pure_functions.py`
  - 覆盖数值范围 helper、CLI 参数规范化、时间解析、优先级分类、回溯查询、Telegram 格式化和发送结果边界。
- `tests/test_storage.py`
  - 覆盖 SQLite 临时库、历史入库 upsert、游标自提交、未来时间保护、Telegram delivery 去重、补拉窗口、补拉摘要、gap 冷却。

## 5. 验证结果

最近一次完整验证：

```bash
git diff --check
.venv/bin/python -m pytest
```

pytest 结果：

```text
61 passed
```

本阶段还执行过：

```bash
.venv/bin/python jin10_monitor.py --help
```

确认 CLI help 中显示：

```text
--catch-up-max-store ... 范围 20-5000
--catch-up-max-send ... 范围 0-300
--catch-up-send-interval ... 范围 0-10
```

手动补拉坏参数 smoke：

```bash
HISTORY_DB=/tmp/jin10_cli_clamp_smoke.sqlite3 \
.venv/bin/python jin10_monitor.py \
  --catch-up \
  --from "2026-05-06 23:35" \
  --to "2026-05-06 23:35:01" \
  --no-catch-up-telegram \
  --catch-up-max-store 1 \
  --catch-up-max-send 999 \
  --catch-up-send-interval -1
```

结果：

- 三条 clamp warning 正常出现。
- 后续 REST 阶段因当前 DNS / 网络不可用返回 `ok=False`。
- 因使用 `--no-catch-up-telegram`，未触发真实 Telegram。

## 6. 文档判断

已更新：

- `README.md`
  - 记录 `.env` 数值配置范围。
  - 记录手动补拉 CLI 参数范围。
- `.env.example`
  - 标注 `.env` 数值配置范围和 `0` 的特殊语义。
- `CHANGELOG.md`
  - 按真实提交日期写入 `2026-05-17` 小节。
- `docs/status/021-2026-05-17-config-clamp-handoff.md`
  - 记录 `.env` 配置范围保护阶段。
- `docs/status/022-2026-05-17-cli-clamp-handoff.md`
  - 记录 CLI 参数范围保护阶段。

## 7. 当前风险判断

整体风险等级：低。

影响范围：

- WebSocket：只影响重连等待配置读取。
- REST：只影响兜底轮询间隔配置读取；不改变 REST 抓取逻辑本身。
- Telegram 推送：只影响手动补拉逐条补发数量和间隔的配置 / CLI 参数读取；不改变发送逻辑。
- SQLite 历史库：未修改 schema；只通过补拉入库上限间接控制扫描和写入规模。
- 补拉去重：未修改，继续保护“已成功发送过的 Telegram 不重复补发”语义。
- 启动方式：未修改。

残余风险：

- 用户如果有意传入超出范围的 `.env` 或 CLI 值，现在会被 clamp 到边界，并记录 warning。
- CLI 的 `--lookup-max-pages`、`--limit`、`--history-limit`、`--telegram-status-limit` 等仍有自己的局部保护或默认行为，尚未做统一范围化；目前不是最高优先级。

## 8. 下一步优先级

建议继续小步推进，不要大规模重构。

优先候选：

1. 回到 pytest 边界补充
   - 继续补 `crawl_window` / `catch_up_window` mock REST 边界。
   - 例如 REST 异常 fallback、空页、重复 ID、未命中关键词、窗口边界等。

2. 评估其它 CLI limit 参数是否需要范围保护
   - `--limit`
   - `--history-limit`
   - `--telegram-status-limit`
   - `--lookup-max-pages`
   - 建议先做评估，不要直接批量 clamp。

3. 自动补拉主循环 gap 触发条件测试
   - 只有能小步 mock 时再做。
   - 如果需要较多 async orchestration，建议切更高推理档位。

暂缓：

- SQLite 并发压力测试。
- launchd 实际运行验证。
- 自动补拉逐条补发配置化。
- 事件聚合防刷屏 V2。
- Telegram inline 按钮。

## 9. 模型建议

下一阶段继续使用 `GPT-5.5 中`。

理由：

- 如果只是继续小步 pytest、CLI limit 评估、README / CHANGELOG 文档更新，`GPT-5.5 中` 足够。
- 只有进入自动补拉主循环异步测试、SQLite 并发判断、launchd 实际运行验证或更大范围行为重构时，才建议切到 `GPT-5.5 高`。

## 10. 新 session 交接提示词

新开 session 后可以直接贴：

```text
请继续 /Users/rich/jin10-monitor 项目。

建议模型：GPT-5.5 中。
如需进入自动补拉主循环异步测试、SQLite 并发判断、launchd 实际运行验证或较大行为重构，再切 GPT-5.5 高。

先读取：
1. /Users/rich/jin10-monitor/AGENTS.md
2. /Users/rich/jin10-monitor/docs/status/022-2026-05-17-cli-clamp-handoff.md

默认不要回读旧聊天。先执行：
git branch --show-current
git status
git pull --rebase
git log --oneline -6

当前阶段目标：
继续最小 pytest / 可靠性阶段。`.env` 数值配置范围保护和手动补拉 CLI 参数范围保护已完成并推送；README、.env.example、CHANGELOG 和 handoff 文档已同步。下一步优先回到无网络 pytest 边界补充，或先评估其它 CLI limit 参数是否需要范围保护。

已完成：
- `.env` 数值配置范围保护已完成，最新相关提交 df549b3。
- 手动补拉 CLI 参数范围保护已完成，提交 62675bd。
- 当前 pytest 结果为 61 passed。
- 状态摘要 022 已完成。

下一步建议：
优先二选一：
1. 继续补 crawl_window / catch_up_window mock REST 边界，保持无网络测试。
2. 先评估其它 CLI limit 参数范围保护：--limit、--history-limit、--telegram-status-limit、--lookup-max-pages，只评估不要直接批量 clamp。

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
