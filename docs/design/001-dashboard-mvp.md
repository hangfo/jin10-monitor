# Dashboard MVP 设计文档

更新时间：2026-05-21（Asia/Shanghai）

## 1. 目标

Dashboard MVP 的目标是做一个本地只读的个人交易信息控制台，而不是复刻金十网站。

它应该回答这些问题：

- 最近有哪些入库快讯。
- 某一条 Telegram 推送前后 15 分钟发生了什么。
- 一条消息为什么推送、为什么失败、为什么跳过或为什么只入库。
- 自动补拉是否发生过，补拉窗口大致覆盖了什么。
- 事件聚合 V2 如果未来开启，候选规则可能压掉哪些消息。

核心价值是复盘和诊断，不是替代金十新闻流。

## 2. 非目标

MVP 阶段不做：

- 不做公网服务。
- 不做用户系统。
- 不做 Telegram callback receiver。
- 不做 Telegram 消息发送或补发入口。
- 不做 REST 主动补拉按钮。
- 不接管现有 launchd 常驻监控进程。
- 不直接开启或放宽事件聚合 V2 suppress 规则。

## 3. 页面结构

### 3.1 `/` 最近快讯流

用途：

- 查看最近入库的快讯。
- 快速区分 T3 / T2 / T1。
- 看消息来源、发生时间、入库时间和是否命中关键词。

建议字段：

- 消息 ID。
- 发生时间。
- 标题或正文摘要。
- 优先级。
- 来源：`ws` / `rest` / `catch_up` 等现有来源字段。
- 是否有 Telegram 投递状态。
- 详情页链接。

MVP 交互：

- 支持按优先级筛选。
- 支持只看有 Telegram 状态的消息。
- 默认按发生时间倒序。

### 3.2 `/item/<id>` 单条详情和上下文

用途：

- 围绕一条消息查看前后上下文。
- 复用当前已完成的 `--context <消息ID>` 只读能力。
- 解释一条 Telegram 推送出现时，市场新闻背景是什么。

建议字段：

- 中心消息详情。
- 前后 15 分钟上下文消息，按时间正序。
- 中心消息高亮。
- Telegram 投递状态。
- 关键词命中信息。
- 图片、来源链接等已有元数据，如果本地库中存在则展示。

默认窗口：

- 默认前后 15 分钟。
- 后续可增加 5 / 15 / 30 分钟切换，但 MVP 不必复杂化。

### 3.3 `/telegram-status` 投递状态列表

用途：

- 查看 Telegram 投递诊断状态。
- 区分 `sent`、`failed`、`unknown_timeout`、`skipped`。
- 保护既有语义：已成功发送过的消息仍以 `delivery_log` 作为补拉去重依据。

建议字段：

- 消息 ID。
- 投递状态。
- 投递来源或触发场景。
- 错误摘要。
- 更新时间。
- 对应消息标题。
- 详情页链接。

MVP 筛选：

- 全部。
- failed。
- unknown_timeout。
- skipped。
- sent。

只读边界：

- 只展示状态。
- 不提供重试。
- 不提供补发。
- 不写入 `delivery_log` 或 `telegram_delivery_status`。

### 3.4 `/aggregation-report` 聚合候选报告

用途：

- 为事件聚合 V2 的后续判断提供只读回测入口。
- 先看候选规则会压掉哪些消息，再决定是否开启或调整 suppress。

MVP 阶段建议先保留页面占位，等待后续 `--aggregation-report` CLI 落地后接入。

建议字段：

- 规则参数。
- 候选组数量。
- 每组第一条消息。
- 每组可能被 suppress 的消息。
- 疑似误压样本。
- 按优先级、关键词、来源拆分的统计。

边界：

- 只读展示回测结果。
- 不在页面上直接修改聚合配置。
- 不在页面上开启 `AGGREGATION_V2`。

## 4. 数据来源

Dashboard MVP 的数据来源应全部来自本地 SQLite，只读打开。

优先复用现有数据：

- 历史消息表：最近快讯流、单条详情、上下文。
- `delivery_log`：已成功 Telegram 发送记录，继续作为补拉去重的权威来源。
- `telegram_delivery_status`：诊断状态列表，展示 sent / failed / unknown_timeout / skipped。
- 已有上下文查询逻辑：`--context` 的只读查询语义可作为详情页的数据模型参考。

后续新增数据：

- `--aggregation-report` 先作为 CLI 只读回测能力。
- Dashboard 后续只读取 report 输出或复用同一只读计算函数。

禁止的数据行为：

- 不调用 Jin10 REST。
- 不连接 Jin10 WebSocket。
- 不触发补拉。
- 不发送 Telegram。
- 不初始化或迁移数据库。
- 不因为打开页面写入访问日志到业务 SQLite。

## 5. 只读边界

Dashboard 服务必须是旁路诊断工具。

硬边界：

- SQLite 使用只读连接，例如 `mode=ro`。
- 缺少数据库时返回明确错误页面，不自动创建库。
- 数据库 schema 不匹配时返回诊断错误，不自动迁移。
- 页面操作不写业务库。
- 页面操作不触发网络请求到 Jin10 或 Telegram。
- 页面操作不修改 `.env`、launchd plist 或运行中监控进程。

这条边界的原因是：现有监控服务承担实时入库、补拉和 Telegram 推送，dashboard 只负责解释已有事实。

## 6. 启动方式

MVP 建议采用手动启动：

```bash
.venv/bin/python jin10_monitor.py --dashboard --dashboard-host 127.0.0.1 --dashboard-port 8765
```

设计含义：

- 默认绑定 `127.0.0.1`。
- 默认只读打开当前 `HISTORY_DB`。
- 默认不随 launchd 启动。
- 默认不接管或重启现有监控进程。
- 如果端口被占用，启动失败并提示换端口。

不建议 MVP 阶段加入 launchd：

- launchd 已用于常驻监控服务。
- dashboard 是本地诊断入口，生命周期和监控进程不同。
- 过早放进 launchd 会增加端口、权限、日志和安全边界的复杂度。

后续如果需要常驻 dashboard，应单独设计 plist，不复用监控服务 plist。

## 7. 安全边界

MVP 默认安全策略：

- 只绑定 `127.0.0.1`。
- 不监听 `0.0.0.0`。
- 不暴露公网。
- 不提供写操作。
- 不展示 Telegram token、chat_id、API key、cookie 等真实密钥。
- 错误页不打印完整环境变量。

认证判断：

- MVP 如果严格 localhost-only，可以暂不做登录。
- 一旦允许局域网访问、反向代理或公网访问，必须先做认证和访问控制设计。
- 不建议在 MVP 中加入简易密码参数，避免产生“好像安全了”的错觉。

## 8. 和 Telegram inline / callback 的关系

Dashboard 先作为未来 Telegram 入口的落点，而不是立刻做 callback。

可选后续方式：

- Telegram 消息里附带本地详情链接：`http://127.0.0.1:8765/item/<id>`。
- 如果未来需要手机上打开，需要重新设计网络暴露、认证和设备访问方式。
- Telegram callback receiver 需要新增 bot inbound 链路，应单独设计，不并入 MVP。

当前顺序：

1. 先稳定只读 dashboard。
2. 再稳定 `--aggregation-report`。
3. 再评估 Telegram 消息链接。
4. 最后才评估 callback receiver。

## 9. 阶段拆分

### P1：Dashboard MVP 设计

当前阶段。

交付物：

- 本设计文档。
- 不写前端或服务代码。

### P2：`--aggregation-report`

交付物：

- 只读 CLI。
- 回测聚合候选规则。
- 展示命中数量和疑似误压样本。

### P3：Dashboard MVP 实现

交付物：

- 本地只读 Web 服务。
- 最近快讯流。
- 单条详情和上下文。
- Telegram 状态列表。
- 聚合报告占位或只读接入。

### P4：Telegram 入口

交付物根据后续选择拆分：

- 详情链接。
- 或 callback receiver。

callback receiver 属于新运行链路，需要单独评估。

## 10. 风险评估

### 10.1 误写业务库

风险等级：高。

控制方式：

- 强制只读 SQLite 连接。
- 缺库不创建。
- schema 不匹配不迁移。
- 页面不提供任何写操作。

### 10.2 干扰现有监控服务

风险等级：中。

控制方式：

- 独立手动启动。
- 不接管 launchd。
- 不连接 WebSocket。
- 不触发 REST。
- 不发送 Telegram。

### 10.3 本地服务被误暴露

风险等级：中。

控制方式：

- 默认绑定 `127.0.0.1`。
- 文档明确不建议 `0.0.0.0`。
- 任何公网或局域网访问都必须先补认证设计。

### 10.4 V2 聚合误压真实消息

风险等级：中。

控制方式：

- `/aggregation-report` 只展示候选。
- 不允许页面直接开启 suppress。
- 先做回测和误压样本展示。

### 10.5 误导性诊断

风险等级：低到中。

控制方式：

- 明确区分 `delivery_log` 和 `telegram_delivery_status`。
- 页面标注状态含义。
- `unknown_timeout` 不等同于失败，也不等同于成功。

## 11. MVP 验收标准

后续实现 dashboard 时，MVP 应满足：

- 启动后只监听 `127.0.0.1`。
- 删除或改名历史库后，页面报错但不创建新库。
- 打开所有页面不会新增 SQLite 行。
- 打开所有页面不会产生 Telegram 请求。
- 打开所有页面不会产生 Jin10 REST 请求。
- `/item/<id>` 的上下文结果与 `--context <id>` 语义一致。
- `/telegram-status` 不改变补拉去重语义。
- 退出 dashboard 不影响 launchd 监控服务。
