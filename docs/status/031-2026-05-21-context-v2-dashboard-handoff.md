# 项目状态摘要 031：上下文查询收口与 Dashboard 下一步

更新时间：2026-05-21（Asia/Shanghai）

## 1. 这份文档的用途

本文件用于在新 session 中快速续接，不需要回读旧聊天。

这份摘要重点覆盖：

- `--context` 只读上下文查询已完成。
- 事件聚合防刷屏 V2 的当前真实判断：代码保留、运行关闭、作为技术债后续完善。
- Telegram inline / callback 暂缓原因。
- Dashboard 的实际意义、未来设计方向和下一步模型建议。

## 2. 当前仓库状态

- 项目：jin10-monitor
- GitHub 仓库：https://github.com/hangfo/jin10-monitor
- 本地路径：`/Users/rich/jin10-monitor`
- 分支：`main`
- 当前最新功能提交：
  - `d66bdd6 feat(history): add readonly context lookup`

最近提交：

```text
d66bdd6 feat(history): add readonly context lookup
811256e docs(status): add aggregation v2 handoff
de29e44 feat(telegram): add aggregation anti-spam v2
313554c docs(status): add main startup test assessment
a68980e docs(status): add test stage review
fd68ae9 docs(status): add poll loop tests handoff
```

本摘要生成前已确认：

- `main` 已与 `origin/main` 同步。
- 工作区开始时干净。
- `--context` 功能提交前完整 pytest 结果为 `92 passed`。

新 session 仍必须重新执行本地 Git 检查，不要只凭本文件判断现场状态。

## 3. 已完成：只读上下文查询

已完成并推送：

- `d66bdd6 feat(history): add readonly context lookup`

新增命令：

```bash
.venv/bin/python jin10_monitor.py --context <消息ID> --context-minutes 15
```

行为：

- 只读打开 SQLite。
- 按消息 ID 找中心快讯。
- 查询前后 N 分钟本地历史。
- 按时间顺序输出。
- 中心消息用 `>>` 标记。
- 不触发 REST。
- 不触发 Telegram。
- 不触发补拉。
- 不创建或初始化数据库。

验证过的真实库示例：

```bash
.venv/bin/python jin10_monitor.py --context 20260520235247799800 --context-minutes 15
```

结果正常输出 6 条上下文，中心消息被 `>>` 标记。

## 4. V2 聚合当前判断

事件聚合防刷屏 V2 最小版已实现：

- `de29e44 feat(telegram): add aggregation anti-spam v2`

但当前运行中应保持关闭：

```bash
AGGREGATION_V2=0
```

原因：

- 历史回测显示当前 48 字标题前缀规则在 1437 条历史实时 Telegram 发送中触发 0 次。
- 32 字前缀仍触发 0 次。
- 24 字前缀才少量触发。
- 16 字前缀触发更多，但会误压真实不同消息，例如 USDA 小麦、玉米、豆粕、棉花等同批数据。

结论：

- V2 不是完全伪需求，但当前 suppress 规则太保守，开启后几乎不会生效。
- 直接放宽规则会有误压真实消息队列的风险。
- 因此 V2 暂列技术债，不继续直接上线 suppress。

后续如果恢复 V2，应先做：

```text
--aggregation-report
```

只读回测候选规则，展示会压掉哪些消息、命中数量和疑似误压样本；确认后再考虑真正 suppress。

## 5. Telegram inline / callback 当前判断

暂不做 Telegram inline callback。

原因：

- Telegram callback button 不是只加按钮，还需要 bot 监听 updates。
- 点击 callback 后需要及时响应 callback query，否则客户端会一直 loading。
- 这会新增一条 Telegram inbound 链路，并要和现有 Jin10 WebSocket / REST 常驻任务共存。
- 当前项目还没有本地 Web 服务或 callback receiver。

当前策略：

- 不直接做 Telegram callback。
- 先把本地只读能力做好。
- `--context` 是未来 Telegram 按钮、dashboard 详情页、命令行查询的共同底座。

## 6. Dashboard 的实际意义

Dashboard 不应该复刻金十网站。

如果只是做一个类似金十的新闻流，意义不大，因为金十已经有公共网站。

真正有意义的 dashboard 应该是个人交易信息控制台：

- 最近快讯流。
- 点击快讯查看前后 15 分钟上下文。
- Telegram 投递状态：sent / failed / unknown_timeout / skipped。
- T3 / T2 / T1 筛选。
- 自动补拉摘要与补拉窗口记录。
- V2 聚合候选报告。
- 关键词命中质量和噪音分析。

也就是说，dashboard 的价值不是“看新闻”，而是：

- 复盘 Telegram 推送为什么出现。
- 看哪些消息只入库没推。
- 快速理解一条 Telegram 前后发生了什么。
- 为未来 Telegram inline / callback 提供可打开的详情入口。

## 7. 建议的未来功能路线

### P0：已完成

- `--context <消息ID>` 只读上下文查询。

### P1：Dashboard MVP 设计

先设计，不急着写代码。

需要明确：

- 页面有哪些。
- 数据来源是什么。
- 是否只读。
- 如何启动。
- 是否需要认证或只绑定 localhost。
- 如何避免影响现有 launchd 监控服务。

建议 MVP 页面：

- `/`：最近快讯流。
- `/item/<id>`：单条快讯详情 + 前后上下文。
- `/telegram-status`：投递状态列表。
- `/aggregation-report`：V2 聚合候选报告。

### P2：`--aggregation-report`

只读 CLI，回测聚合规则。

用途：

- 判断 V2 suppress 是否值得重新开启。
- 避免误压真实消息队列。

### P3：Dashboard MVP 实现

只读本地服务。

建议边界：

- 只绑定 `127.0.0.1`。
- 只读 SQLite。
- 不接管 Jin10 监控进程。
- 不发送 Telegram。
- 不触发 REST。

### P4：Telegram inline / callback

等 dashboard / context / report 稳定后再做。

可能方式：

- Telegram 消息里放 dashboard 本地详情链接。
- 或新增 callback receiver。

但 callback receiver 属于新运行链路，届时应单独设计。

## 8. 下一步建议和模型

建议下一步：

- 做 Dashboard MVP 设计文档。
- 只设计页面、数据、边界、启动方式和风险。
- 不马上写前端或服务代码。

模型建议：

- Dashboard MVP 设计：`GPT-5.5 高`。
- 文档整理、handoff、只读 git 状态确认：`GPT-5.5 中`。
- 未来 dashboard 实现：`GPT-5.5 高`。
- 未来 Telegram callback / inline：`GPT-5.5 高`。
- 未来 V2 聚合规则调整或 `--aggregation-report` 策略设计：`GPT-5.5 高`。

## 9. 新 session 交接提示词

新开 session 后可以直接贴：

```text
请继续 /Users/rich/jin10-monitor 项目。

建议模型：GPT-5.5 高。
本轮建议做 Dashboard MVP 设计文档，只设计页面、数据来源、只读边界、启动方式和风险，不急着写前端或服务代码。

先读取：
1. /Users/rich/jin10-monitor/AGENTS.md
2. /Users/rich/jin10-monitor/docs/status/031-2026-05-21-context-v2-dashboard-handoff.md

默认不要回读旧聊天。先执行：
git branch --show-current
git status
git pull --rebase
git log --oneline -6

当前阶段判断：
- --context 只读上下文查询已完成并推送，最新功能提交 d66bdd6。
- 事件聚合防刷屏 V2 代码已实现但运行中关闭，暂列技术债；不要直接放宽 suppress 规则，后续应先做只读 --aggregation-report。
- Telegram inline / callback 暂不做，因为需要新增 bot update receiver，新链路较重。
- Dashboard 不应复刻金十网站，而应作为个人交易信息控制台。

下一步具体任务：
写 Dashboard MVP 设计文档，明确：
- 页面结构：最近快讯流、单条详情+上下文、Telegram 状态、聚合候选报告。
- 数据来源：SQLite 只读。
- 运行方式：本地 localhost，只读服务，不接管现有 launchd 监控。
- 安全边界：不发送 Telegram、不触发 REST、不写数据库、不暴露公网。
- 后续如何和 Telegram inline / callback 连接。
- 风险和阶段拆分。

要求：
- 不要继续无目的扩张测试。
- 不要做 launchd 实测，除非我明确同意。
- 不要做 SQLite 并发压力测试。
- 不要重构补拉架构。
- 继续保护现有补拉去重语义：已成功发送过的 Telegram 不重复补发。
- CHANGELOG.md 必须按真实提交日期写入当天小节。
- 每次最终回复都告诉我下一步应该用 GPT-5.5 中还是高。
```
