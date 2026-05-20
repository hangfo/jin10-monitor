# 项目状态摘要 030：事件聚合防刷屏 V2 最小版

更新时间：2026-05-20（Asia/Shanghai）

## 1. 这份文档的用途

本文件用于在新 session 中快速续接，不需要回读旧聊天。

这份摘要重点覆盖：

- 事件聚合防刷屏 V2 最小版已经实现到哪里。
- 默认关闭状态、开启方式、观察点和风险。
- 下一步建议，以及每类下一步应使用 `GPT-5.5 中` 还是 `GPT-5.5 高`。

## 2. 当前仓库状态

- 项目：jin10-monitor
- GitHub 仓库：https://github.com/hangfo/jin10-monitor
- 本地路径：`/Users/rich/jin10-monitor`
- 分支：`main`
- 当前最新功能提交：
  - `de29e44 feat(telegram): add aggregation anti-spam v2`

最近提交：

```text
de29e44 feat(telegram): add aggregation anti-spam v2
313554c docs(status): add main startup test assessment
a68980e docs(status): add test stage review
fd68ae9 docs(status): add poll loop tests handoff
6f5c1a6 test(poll): cover REST item handling
25118b8 test(poll): cover auto catch-up exception path
```

本摘要生成前已确认：

- `main` 已与 `origin/main` 同步。
- 工作区开始时干净。
- V2 功能提交前完整 pytest 结果为 `90 passed`。

新 session 仍必须重新执行本地 Git 检查，不要只凭本文件判断现场状态。

## 3. 已完成内容

事件聚合防刷屏 V2 最小版已实现并推送：

- `de29e44 feat(telegram): add aggregation anti-spam v2`

新增配置：

- `AGGREGATION_V2=0`
  - 默认关闭。
- `AGGREGATION_WINDOW_SECONDS=180`
  - 范围 `0-3600`。
  - `0` 表示关闭聚合窗口。
- `AGGREGATION_BYPASS_IMPORTANT=1`
  - T3 金十重要消息绕过聚合，仍然直推。

实现位置：

- `jin10_monitor.py`
  - 新增聚合 key、窗口清理、跳过判断和成功推送后登记 helper。
  - 在 `handle_item` 实时发送 Telegram 前判断是否聚合降噪。
- `.env.example`
  - 新增配置示例。
- `README.md`
  - 新增配置说明。
- `CHANGELOG.md`
  - 按真实日期记录功能变更。
- `tests/test_storage.py`
  - 新增实时聚合和 T3 绕过聚合测试。

## 4. 当前行为

默认状态：

- `AGGREGATION_V2=0`，功能不开启。
- 现有 Telegram 推送行为不变。

开启后：

- 只影响实时 `handle_item` 路径。
- 第一条相似实时消息正常发送 Telegram。
- 发送成功后才登记聚合 key。
- 窗口内相似实时消息：
  - 继续入库。
  - 不发送 Telegram。
  - 写入 `telegram_delivery_status`，状态为 `skipped`。
  - detail 形如 `aggregation_v2 similar_to=<id> at=<time>`。
  - 不写 `delivery_log`。
- T3 金十重要消息默认绕过聚合，仍然直推。

明确未做：

- 不影响自动补拉摘要。
- 不影响手动补拉逐条补发。
- 不修改 SQLite schema。
- 不修改 launchd。
- 不做复杂文本相似度算法。
- 不做聚合摘要消息。

## 5. 关键不变量

必须继续保护：

- 已成功发送过的 Telegram 不重复补发。
- `delivery_log` 仍然只代表真实发送成功。
- `telegram_delivery_status` 是诊断侧表，`skipped` 不等于已发送。
- T3 重要消息默认不被聚合压掉。
- 所有消息仍正常入库，聚合只影响 Telegram 推送。

## 6. 开启方式

如果决定开启，在 `.env` 增加或修改：

```bash
AGGREGATION_V2=1
AGGREGATION_WINDOW_SECONDS=180
AGGREGATION_BYPASS_IMPORTANT=1
```

然后重载后台服务：

```bash
./scripts/launchd/manage.sh reload
```

注意：

- 是否执行 reload 需要用户明确同意。
- 当前文档生成阶段没有做 launchd 实测。

## 7. 开启后观察点

建议观察：

- Telegram 是否明显减少同主题刷屏。
- T3 金十重要消息是否仍然直推。
- `--telegram-status skipped` 是否出现 `aggregation_v2 similar_to=...`。
- 是否误压了本应独立推送的不同事件。

只读诊断命令：

```bash
python jin10_monitor.py --telegram-status skipped --telegram-status-limit 20
python jin10_monitor.py --history --history-limit 20
```

## 8. 风险判断

整体风险：中低。

原因：

- 默认关闭，所以部署后不改变行为。
- 开启后会影响实时 Telegram 推送数量。
- 但 T3 重要消息默认绕过。
- 成功去重表不被 skipped 污染。
- 不改补拉、不改 schema、不改启动方式。

主要残余风险：

- 聚合 key 当前是保守的文本前缀规则，不是语义相似度。
- 同标题但实质不同的连续消息可能被压掉。
- 不同标题但同一事件的消息可能仍然分别发送。

## 9. 下一步建议和模型

### A. 写文档、提交 handoff、只读确认

建议模型：`GPT-5.5 中`。

适用任务：

- 整理 `030` handoff。
- 检查 git 状态。
- 查询只读状态。
- 决定是否开启。

### B. 开启 V2 并 reload 观察

建议模型：`GPT-5.5 中`。

适用任务：

- 用户明确同意后修改本机 `.env`。
- 执行 `./scripts/launchd/manage.sh reload`。
- 使用只读状态命令观察。

注意：

- reload 会影响本机常驻服务，执行前需要明确确认。

### C. 调整聚合规则

建议模型：`GPT-5.5 高`。

适用任务：

- 修改聚合 key。
- 加入关键词主题聚合。
- 默认开启 V2。
- 增加聚合摘要。
- 扩展到补拉路径。
- 排查真实运行中的误压或漏压。

## 10. 新 session 交接提示词

新开 session 后可以直接贴：

```text
请继续 /Users/rich/jin10-monitor 项目。

建议模型：
- 如果只是文档整理、只读状态确认、决定是否开启 V2，用 GPT-5.5 中。
- 如果要调整事件聚合规则、默认开启、扩展到补拉、或排查真实运行误压/漏压，用 GPT-5.5 高。

先读取：
1. /Users/rich/jin10-monitor/AGENTS.md
2. /Users/rich/jin10-monitor/docs/status/030-2026-05-20-aggregation-v2-handoff.md

默认不要回读旧聊天。先执行：
git branch --show-current
git status
git pull --rebase
git log --oneline -6

当前阶段目标：
事件聚合防刷屏 V2 最小版已实现并推送，默认关闭。下一步先决定是否开启并观察；不要继续无目的扩张测试，不要做 launchd 实测，除非用户明确同意 reload。

已完成：
- V2 配置：AGGREGATION_V2、AGGREGATION_WINDOW_SECONDS、AGGREGATION_BYPASS_IMPORTANT。
- 实时 handle_item 发送前聚合判断。
- 被聚合跳过消息写 telegram_delivery_status=skipped，不写 delivery_log。
- T3 重要消息默认绕过聚合。
- README、.env.example、CHANGELOG 已更新。
- 完整 pytest 基线：90 passed。
- 最新功能提交：de29e44。

下一步建议：
如果用户想开启，先说明会修改本机 .env 并 reload 后台服务，等确认后执行：
AGGREGATION_V2=1
AGGREGATION_WINDOW_SECONDS=180
AGGREGATION_BYPASS_IMPORTANT=1
./scripts/launchd/manage.sh reload

要求：
- CHANGELOG.md 必须按真实提交日期写入当天小节，不要把多日改动堆在 Unreleased。
- 查询和诊断入口只做只读，不要实现重试队列。
- 优先做最小可靠修复，不要大规模重构模块。
- 继续保护现有补拉去重语义：已成功发送过的 Telegram 不重复补发。
- 如果新增 CLI 用户操作方式，预计需要更新 README.md 和 CHANGELOG.md。
- 修改后给 diff、风险和验证。
- commit/push 前更新 CHANGELOG.md。
- 每次最终回复都告诉我下一步应该用 GPT-5.5 中还是高。
```
