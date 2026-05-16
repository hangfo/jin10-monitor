# 项目状态摘要 018：开发效用与优先级重新评估

更新时间：2026-05-17（Asia/Shanghai）

## 1. 这份文档的用途

本文件用于记录一次阶段性复盘：对照 `CHANGELOG.md`、历史 handoff 和真实提交，重新评估后续开发效用和优先级。

这份摘要重点回答：

- 哪些已完成工作最有价值。
- 哪些计划与实际完成存在偏离。
- 哪些偏离是合理调整，哪些需要流程修正。
- 下一步优先做什么，哪些暂缓。
- 新 session 应该如何续接。

## 2. 当前仓库状态

- 项目：jin10-monitor
- GitHub 仓库：https://github.com/hangfo/jin10-monitor
- 本地路径：`/Users/rich/jin10-monitor`
- 分支：`main`
- 当前最新提交：
  - `3cfdfb8 docs(changelog): split recent entries by date`

最近提交：

```text
3cfdfb8 docs(changelog): split recent entries by date
e58bf44 docs(status): add catchup tests handoff
c64bbf6 test(catchup): cover summary formatting helpers
198c570 test(catchup): cover window pagination boundaries
96f692a docs(status): add pytest skeleton handoff
3c665dd test(storage): cover sqlite boundary semantics
```

本摘要生成前已确认：

- `3cfdfb8` 已推送到 `origin/main`。
- `main` 已与 `origin/main` 同步。
- 工作区干净。

新 session 仍必须重新执行本地 Git 检查，不要只凭本文件判断现场状态。

## 3. 回溯结论

整体判断：

- 主线没有明显跑偏。
- 从 2026-05-07 到 2026-05-17，实际完成内容基本围绕“稳定运行、补拉可靠性、Telegram 去重/诊断、测试保护”推进。
- 真正需要修正的是流程和记录习惯，而不是技术方向。

发现的出入：

1. `CHANGELOG.md` 日期分组被破坏过
   - 2026-05-09 已有 `docs(changelog): group entries by date`。
   - 2026-05-16 / 2026-05-17 期间曾继续把多日变更堆在 `Unreleased`。
   - 已用 `3cfdfb8 docs(changelog): split recent entries by date` 修正。
   - 后续规则：按真实提交日期写入日期小节；当天无小节就新建。

2. 2026-05-10 的“自动补拉逐条补发配置化”没有继续推进
   - 后续实际转向 P0/P1/P2 可靠性修复。
   - 这是合理调整。
   - 原因：游标安全、补拉线程化、分页完整性和 Telegram 投递诊断优先级更高，且逐条补发会提高刷屏和重复发送风险。

3. 2026-05-12 多次提到“数值配置上下限保护”，实际未做
   - 这是未完成候选，不是当前高优先级缺口。
   - 当前已完成非法数值格式容错。
   - clamp 需要逐项判断默认值和极端合法值风险，不适合顺手批量做。

4. 2026-05-17 pytest 阶段略超出最初计划，但方向一致
   - 原计划先做纯函数和 SQLite 边界。
   - 实际继续补了 `catch_up_window` mock 测试和补拉摘要纯逻辑测试。
   - 这是合理扩展，因为仍然保持小步、无网络、无真实 Telegram、无运行逻辑修改。

## 4. 已完成工作的开发效用排序

### 最高效用

1. 补拉和历史库可靠性修复
   - `last_ingested_at` 游标安全。
   - `catch_up_window` 放到 `asyncio.to_thread`。
   - SQLite 线程本地连接、WAL、busy_timeout。
   - 重复时间戳翻页 cursor。
   - 历史入库 upsert 语义修复。

价值：

- 直接降低漏消息、卡补拉、阻塞实时消息、历史语义污染的风险。
- 这些是监控系统的核心可靠性问题，优先级最高。

2. Telegram 去重和投递状态诊断
   - `delivery_log` 继续只表示成功发送。
   - `telegram_delivery_status` 单独记录 sent / failed / unknown_timeout / skipped。
   - 只读查询入口不触发补发。
   - 自动补拉摘要状态记录不污染逐条消息去重。

价值：

- 保护“已成功发送过的 Telegram 不重复补发”。
- 同时提高故障诊断能力。
- 这是可靠性和可观测性之间的低风险折中。

3. pytest 骨架与边界测试
   - 纯函数测试。
   - SQLite 临时库测试。
   - `catch_up_window` mock REST 测试。
   - 补拉摘要纯逻辑测试。

价值：

- 后续修复有回归保护。
- 测试不访问外网、不发送 Telegram、不碰真实库。
- 非常适合继续扩展。

### 中高效用

4. 自愈补拉摘要降噪
   - gap 自愈摘要增加 30 分钟冷却。

价值：

- 改善 Telegram 群阅读体验。
- 对实时推送和补拉入库影响小。

5. launchd 管理和运维文档
   - `manage.sh` 增强。
   - 运维速查。
   - 状态摘要。

价值：

- 降低日常维护成本。
- 对功能正确性不是最高优先，但对个人长期运行很有用。

### 暂时低效用或高风险

1. 自动补拉逐条补发配置化
   - 当前暂缓。
   - 原因：会改变 Telegram 行为，存在刷屏和重复发送风险。
   - 只有在真实需要补发历史重点消息时再设计。

2. 事件聚合防刷屏 V2
   - 当前暂缓。
   - 原因：需要定义相似度、时间窗、T3 例外、入库与推送差异，容易变成大改。

3. Telegram inline 按钮
   - 当前暂缓。
   - 原因：是体验增强，不是可靠性核心。

4. VPS/systemd
   - 当前暂缓。
   - 原因：本地 launchd 仍是当前运行形态，迁移前再设计。

## 5. 下一步优先级

建议继续使用 `GPT-5.5 中`，走小步测试和文档。

### P0：Telegram 发送结果轻量单测

优先原因：

- 这是 017 handoff 里明确的残余风险。
- 可以先测不联网保护分支，风险低。
- 直接保护 Telegram 发送语义。

建议范围：

- 未配置 `TG_TOKEN` / `TG_CHAT_ID` 时返回 `skipped`。
- `HISTORY_DB` 为临时测试库且未设置 `ALLOW_TMP_TELEGRAM` 时返回 `skipped`。
- `TelegramSendResult.ok` 只在 `sent` 时为真。

暂不建议一开始就做复杂 fake aiohttp session，除非小步测试足够清晰。

### P1：`crawl_window` mock REST 测试

优先原因：

- 回溯查询依赖 REST 翻页和关键词评分。
- 与 `catch_up_window` 类似，可以完全 mock `fetch_page_sync`。

建议范围：

- 窗口过滤。
- 关键词评分。
- 优先级分类。
- 跨页 cursor 推进。

### P2：自动补拉 gap 冷却状态测试

优先原因：

- 已有真实运行观察，但单元测试覆盖不足。

注意：

- 避免真实 Telegram 和 REST。
- 如果测试 `maybe_auto_catchup` 需要大量 mock，就先暂缓，优先找更小 helper 或拆出纯逻辑。

### P3：数值配置上下限保护

状态：

- 保留为候选，不作为立即任务。

建议：

- 先列出每个数值配置的合理上下限和误填风险。
- 不要一次性批量 clamp。

## 6. 流程规则更新

后续执行规则：

1. `CHANGELOG.md`
   - 不把多日改动继续堆在 `Unreleased`。
   - 按真实提交日期写入 `## YYYY-MM-DD`。
   - 如果当天已有小节，追加到当天。
   - 如果当天没有小节，新建当天小节。

2. 计划和实际偏离
   - 如果偏离是因为真实运行风险、code review 风险或用户新指令，允许调整。
   - 调整后要在 handoff 中写清楚为什么没继续原计划。

3. 测试优先级
   - 优先无网络、无真实 Telegram、无真实历史库的测试。
   - 先保护核心语义，再考虑体验增强。

4. 暂缓项
   - 自动逐条补发、事件聚合、inline 按钮、VPS/systemd 不要顺手推进。
   - 这些都需要单独设计和用户确认。

## 7. 新 session 交接提示词

新开 session 后可以直接贴：

```text
请继续 /Users/rich/jin10-monitor 项目。

先读取：
1. /Users/rich/jin10-monitor/AGENTS.md
2. /Users/rich/jin10-monitor/docs/status/018-2026-05-17-priority-reassessment-handoff.md

默认不要回读旧聊天。先执行：
git branch --show-current
git status
git pull --rebase
git log --oneline -6

当前阶段目标：
继续最小 pytest 骨架阶段，但优先按开发效用推进：先保护 Telegram 发送结果和回溯查询 crawl_window 等边界逻辑。继续小步可靠修复，不要大规模重构模块。

已完成：
- 最小 pytest 骨架已完成，提交 591bea8。
- SQLite 边界测试已完成，提交 3c665dd。
- 补拉窗口无网络测试已完成，提交 198c570。
- 补拉摘要纯逻辑测试已完成，提交 c64bbf6。
- 状态摘要 017 已完成，提交 e58bf44。
- CHANGELOG 已按真实提交日期重新分组，提交 3cfdfb8。
- 开发效用与优先级重新评估已记录在状态摘要 018。

下一步建议：
优先做 P0：Telegram 发送结果轻量单测。
先从不联网保护分支开始：
- 未配置 TG_TOKEN / TG_CHAT_ID 时返回 skipped。
- HISTORY_DB 为临时测试库且未设置 ALLOW_TMP_TELEGRAM 时返回 skipped。
- TelegramSendResult.ok 只在 sent 时为真。

然后再考虑：
1. crawl_window mock REST 测试。
2. 自动补拉 gap 冷却状态测试。
3. 数值配置上下限保护评估。

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
