# 项目状态摘要 019：Telegram、回溯查询与 gap 冷却测试已完成

更新时间：2026-05-17（Asia/Shanghai）

## 1. 这份文档的用途

本文件用于在新 session 中快速续接 pytest 骨架阶段，不需要回读旧聊天。

这份摘要重点覆盖：

- Telegram 发送结果边界测试已经如何落地。
- `crawl_window` 回溯查询 mock REST 测试和 cursor 修复已经如何落地。
- 自动补拉 gap 摘要冷却测试已经如何落地。
- 当前 Git 状态、验证结果和下一步建议。

## 2. 当前仓库状态

- 项目：jin10-monitor
- GitHub 仓库：https://github.com/hangfo/jin10-monitor
- 本地路径：`/Users/rich/jin10-monitor`
- 分支：`main`
- 当前最新提交：
  - `5e87629 test(catchup): cover gap summary cooldown`

最近提交：

```text
5e87629 test(catchup): cover gap summary cooldown
edda6d4 fix(lookup): advance crawl cursor safely
c719ea7 test(telegram): cover fake send responses
9dc66f2 test(telegram): cover send result boundaries
c048b57 docs(status): add priority reassessment handoff
3cfdfb8 docs(changelog): split recent entries by date
e58bf44 docs(status): add catchup tests handoff
c64bbf6 test(catchup): cover summary formatting helpers
```

本摘要生成前已确认：

- `5e87629` 已推送到 `origin/main`。
- `main` 已与 `origin/main` 同步。
- 工作区在新增本摘要前是干净的。

新 session 仍必须重新执行本地 Git 检查，不要只凭本文件判断现场状态。

## 3. 本阶段已完成内容

### 3.1 Telegram 发送结果边界测试

提交：

- `9dc66f2 test(telegram): cover send result boundaries`
- `c719ea7 test(telegram): cover fake send responses`

已完成：

- 在 `tests/test_pure_functions.py` 中新增 Telegram 发送结果测试。
- 使用 `NoNetworkSession` 和轻量 fake session，不引入复杂 mock 框架。
- 不访问真实网络、不发送真实 Telegram、不使用真实历史库。

覆盖范围：

- 未配置 `TG_TOKEN` / `TG_CHAT_ID` 时，`send_telegram` 返回 `skipped`。
- `HISTORY_DB` 为临时测试库且未设置 `ALLOW_TMP_TELEGRAM` 时，`send_telegram` 返回 `skipped`。
- `TelegramSendResult.ok` 只在 `sent` 时为 `True`。
- Telegram 返回 200 时结果为 `sent`。
- Telegram 返回 500 时结果为 `failed`。
- Telegram timeout 时结果为 `unknown_timeout`，不自动重试，避免重复发送风险。

### 3.2 回溯查询 mock REST 测试和 cursor 修复

提交：

- `edda6d4 fix(lookup): advance crawl cursor safely`

已完成：

- `crawl_window` 的下一页 cursor 改为复用 `previous_page_cursor(dated, cursor)`。
- 新增无网络 mock REST 测试，覆盖窗口过滤、关键词评分、高优先级分类和跨页 cursor。

修复原因：

- 原逻辑直接使用本页最后一条消息时间作为下一页 cursor。
- 遇到重复时间戳时，下一页可能重复扫描同一秒边界。
- 新逻辑从本页最旧消息时间再回退 1 秒，与补拉窗口 `catch_up_window` 的 cursor 行为保持一致。

影响范围：

- 只影响 `--lookup-*` 回溯查询的 REST 翻页边界。
- 不影响 WebSocket、Telegram 发送、SQLite 历史库、启动方式或配置字段。

### 3.3 自动补拉 gap 摘要冷却测试

提交：

- `5e87629 test(catchup): cover gap summary cooldown`

已完成：

- 在 `tests/test_storage.py` 中新增 `run_auto_catch_up` gap 冷却测试。
- 使用临时 SQLite、fake `catch_up_window` 和 fake `send_telegram`。
- 不访问真实 REST，不发送真实 Telegram。

覆盖范围：

- 冷却期内：
  - 不发送自愈补拉摘要。
  - 不更新 `last_gap_summary_telegram_at`。
- 冷却期外：
  - 发送一条自愈补拉摘要。
  - 更新 `last_gap_summary_telegram_at`。
  - 写入 `telegram_delivery_status`，但不写入逐条消息去重表。

## 4. 当前测试覆盖概览

当前 pytest 用例数：

```text
42 passed
```

测试文件：

- `tests/test_pure_functions.py`
  - 26 个用例。
  - 覆盖时间解析、优先级分类、翻页 cursor、消息文本提取、Telegram 格式化、Telegram 发送结果、`crawl_window` mock REST。
- `tests/test_storage.py`
  - 16 个用例。
  - 覆盖 SQLite 临时库、历史入库 upsert、游标自提交、未来时间保护、Telegram delivery 去重、补拉窗口、补拉摘要、gap 冷却。

## 5. 验证结果

本阶段各小步提交前均已执行并通过相关验证。最近一次完整验证：

```bash
git diff --check
.venv/bin/python -m pytest tests/test_storage.py
.venv/bin/python -m pytest
```

pytest 结果：

```text
42 passed
```

本摘要新增后已重新执行：

```bash
git diff --check
.venv/bin/python -m pytest
```

## 6. 文档判断

已更新：

- `CHANGELOG.md`：按真实提交日期写入 `2026-05-17` 小节。
- `docs/status/019-2026-05-17-telegram-lookup-gap-tests-handoff.md`：新增本摘要。

本阶段不需要更新：

- `README.md`：没有新增 CLI 用户操作方式。
- `.env.example`：没有新增配置项。
- `docs/operations/001-launchd.md`：没有修改启动方式、后台服务管理方式或 launchd 配置。

## 7. 当前风险判断

整体风险等级：低。

影响范围：

- WebSocket：未修改。
- REST：`crawl_window` lookup cursor 有 1 行逻辑修复；补拉 REST 逻辑未修改。
- Telegram 推送：未修改真实发送逻辑；新增测试覆盖发送结果和摘要冷却边界。
- SQLite 历史库：未修改 schema；测试只操作临时库。
- 补拉去重：继续保护“已成功发送过的 Telegram 不重复补发”语义。
- 启动方式：未修改。
- 配置字段：未修改。

残余风险：

- `crawl_window` 目前只覆盖了一个成功翻页场景，后续可以继续补失败 app_id fallback、空页、重复 ID 等边界。
- 自动补拉 gap 测试覆盖了摘要冷却状态，但没有覆盖主循环里 gap 检测触发条件。
- 数值配置上下限保护仍只是候选项，不建议直接批量 clamp。

## 8. 下一步优先级

建议继续小步测试或先做风险清单，不要大规模拆模块。

优先候选：

1. 继续补 `crawl_window` mock REST 边界
   - app_id 失败后 fallback 到下一个 app_id。
   - 空页提前结束。
   - 重复 ID 只输出一次。
   - 无关键词命中仍保留在 `all_items`，但不进入 `matched_items`。

2. 自动补拉主循环 gap 触发条件测试
   - 仅在能小步 mock 的情况下推进。
   - 避免真实 Telegram 和 REST。
   - 如果需要大量 async orchestration，暂缓。

3. 数值配置上下限保护评估
   - 先列 `POLL_INTERVAL`、`WS_RECONNECT_DELAY`、`CATCHUP_MAX_HOURS`、`CATCHUP_MAX_STORE`、`CATCHUP_MAX_SEND`、`CATCHUP_SEND_INTERVAL`、`AUTO_CATCHUP_GAP_SECONDS`、`SHOW_DELAY_IF_SECONDS` 的范围和误填风险。
   - 不要一次性批量 clamp。

暂缓：

- 自动补拉逐条补发配置化。
- 事件聚合防刷屏 V2。
- Telegram inline 按钮。
- VPS/systemd 迁移。
- 真正联网的 Telegram/REST 集成测试。

## 9. 模型建议

下一阶段继续使用 `GPT-5.5 中`。

理由：

- 当前主要是小步 mock 测试和文档清单。
- 已有测试骨架和 helper 足够支撑。
- 只有进入自动补拉主循环大范围异步测试、SQLite 并发或运行形态迁移时，才建议切到 `GPT-5.5 高`。

## 10. 新 session 交接提示词

新开 session 后可以直接贴：

```text
请继续 /Users/rich/jin10-monitor 项目。

建议模型：GPT-5.5 中。

先读取：
1. /Users/rich/jin10-monitor/AGENTS.md
2. /Users/rich/jin10-monitor/docs/status/019-2026-05-17-telegram-lookup-gap-tests-handoff.md

默认不要回读旧聊天。先执行：
git branch --show-current
git status
git pull --rebase
git log --oneline -6

当前阶段目标：
继续最小 pytest 骨架阶段，按开发效用优先推进。P0 Telegram 发送结果测试、P1 crawl_window 首个 mock REST 测试、P2 自动补拉 gap 摘要冷却测试已完成。继续小步可靠修复，不要大规模重构模块。

已完成：
- Telegram 发送结果边界测试已完成，提交 9dc66f2。
- Telegram fake session 200 / 500 / timeout 测试已完成，提交 c719ea7。
- crawl_window cursor 修复和 mock REST 测试已完成，提交 edda6d4。
- 自动补拉 gap 摘要冷却测试已完成，提交 5e87629。
- 状态摘要 019 已完成。

下一步建议：
优先二选一：
1. 继续补 crawl_window mock REST 边界：app_id fallback、空页、重复 ID、未命中关键词。
2. 先做数值配置上下限保护评估清单：只列范围和风险，不要直接批量 clamp。

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
