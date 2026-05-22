# 项目状态摘要 032：Dashboard MVP 可运行原型与收尾

更新时间：2026-05-22（Asia/Shanghai）

## 1. 本摘要用途

本文件用于后续 session 快速接上 Dashboard MVP 工作，不需要回读旧聊天。

本轮目标从“只做设计文档”推进到“尽快看到前端界面”。当前已经有可运行的本地只读 Dashboard 原型，但仍应视为 MVP 原型，不是最终完成版。

## 2. 当前仓库状态

- 项目：`/Users/rich/jin10-monitor`
- 分支：`main`
- 本轮开始前已同步远端，工作区从干净状态开始。
- 上一个已推送提交：
  - `9d0a971 docs(dashboard): add dashboard mvp design`
- 当前本轮变更尚未提交。

变更文件：

- `jin10_monitor.py`
- `README.md`
- `CHANGELOG.md`
- `tests/test_storage.py`
- `docs/status/032-2026-05-22-dashboard-mvp-handoff.md`

## 3. 已完成内容

新增本地只读 Dashboard MVP：

```bash
.venv/bin/python jin10_monitor.py --dashboard
```

默认地址：

```text
http://127.0.0.1:8765/
```

已实现页面：

- `/`：最近快讯流。
- `/item/<id>`：单条消息详情 + 前后上下文。
- `/telegram-status`：Telegram 投递状态诊断列表。
- `/aggregation-report`：聚合候选报告占位页。

已修正第一版原型暴露出的关键 UX 问题：

- 首页增加 15 秒自动刷新。
- 首页显示“已加载 N 条”，避免误以为只有几条。
- 窄窗口下整张消息卡片可点击。
- 卡片上增加“查看上下文”提示。
- 详情页可展示前后 15 分钟上下文，中心消息有高亮。
- Telegram 状态页在窄窗口下也用可点击卡片展示。

## 4. 只读边界

Dashboard 当前保持旁路诊断工具定位：

- 只绑定 `127.0.0.1` / `localhost`。
- 只读打开 SQLite：复用 `open_readonly_history_db()`。
- 不触发 Jin10 REST。
- 不连接 Jin10 WebSocket。
- 不触发补拉。
- 不发送 Telegram。
- 不写 `delivery_log`。
- 不写 `telegram_delivery_status`。
- 不接管现有 launchd 常驻监控进程。

`delivery_log` 仍是已成功 Telegram 发送的补拉去重权威表；`telegram_delivery_status` 仍只是诊断状态表。

## 5. 验证结果

已执行：

```bash
.venv/bin/python -m py_compile jin10_monitor.py
.venv/bin/python -m pytest -q
git diff --check
curl -I http://127.0.0.1:8765/
curl -I http://127.0.0.1:8765/item/20260522204219999800
```

结果：

- `py_compile` 通过。
- `pytest`：`95 passed`。
- `git diff --check` 通过。
- Dashboard 首页返回 `200 OK`。
- Dashboard 详情页返回 `200 OK`。

本地实际运行时，首页已能展示 2026-05-22 晚间实时入库数据，并显示已加载 80 条。

## 6. 真实进度判断

这轮不是“最终 dashboard 完成”，而是“可运行 MVP 原型完成”。

已满足：

- 能打开本地页面。
- 能看最近快讯。
- 能点消息看上下文。
- 能看 Telegram 投递状态。
- 基本通路测试通过。

仍未满足：

- UI 还需要继续打磨。
- 信息密度和筛选交互还比较粗糙。
- 聚合报告仍只是占位。
- 没有搜索。
- 没有更细的状态解释或问题分组。
- 没有前端组件化，HTML/CSS 仍在 `jin10_monitor.py` 中。

## 7. 风险评估

### 7.1 代码体量风险

风险等级：中。

原因：

- 本轮为了尽快看到前端界面，把标准库 HTTP 服务、HTML、CSS 和查询逻辑都放进了 `jin10_monitor.py`。
- diff 较大，后续如果继续扩展 dashboard，建议考虑拆分模块。

### 7.2 核心链路风险

风险等级：低。

原因：

- 未改 WebSocket / REST / Telegram 发送 / 补拉主逻辑。
- Dashboard 只读查询，不写业务库。
- 已补缺库不创建文件的测试。

### 7.3 运行方式风险

风险等级：低到中。

原因：

- 新增 `--dashboard` CLI 启动方式。
- 默认只监听 `127.0.0.1`。
- 不随 launchd 启动。
- 不接管现有后台监控。

## 8. 建议收尾方式

建议本轮先作为一个 feature commit 收尾：

```text
feat(dashboard): add readonly local dashboard mvp
```

提交前应再次确认：

```bash
.venv/bin/python -m py_compile jin10_monitor.py
.venv/bin/python -m pytest -q
git diff --check
```

建议提交后再单独评估下一轮是否做 UI 精修。

## 9. 下一步建议

下一轮优先级：

1. UI 精修：筛选区、卡片密度、详情页返回、状态解释。
2. 搜索：按关键词 / 消息 ID 查找。
3. 聚合报告：先做只读 `--aggregation-report` CLI，再接入 dashboard。
4. 模块拆分：如果 dashboard 继续扩张，把 HTML / HTTP handler 从 `jin10_monitor.py` 拆出去。

模型建议：

- UI 精修：`GPT-5.5 中` 即可。
- 聚合报告策略、模块拆分或 dashboard 继续扩大：`GPT-5.5 高`。

## 10. 新 session 提示词

```text
请继续 /Users/rich/jin10-monitor 项目。

先读取：
1. /Users/rich/jin10-monitor/AGENTS.md
2. /Users/rich/jin10-monitor/docs/status/032-2026-05-22-dashboard-mvp-handoff.md

先执行：
git branch --show-current
git status
git pull --rebase
git log --oneline -6

当前阶段：
- 本地只读 Dashboard MVP 原型已实现但尚未提交。
- Dashboard 默认 http://127.0.0.1:8765/
- 已能展示最近快讯、点击消息查看上下文、查看 Telegram 投递状态、展示聚合报告占位。
- 已修复第一版原型的明显问题：自动刷新、卡片可点击、已加载条数、查看上下文提示。
- 当前仍不是最终版，UI 还需要后续精修。

要求：
- 继续保护只读边界：不触发 REST、WebSocket、补拉或 Telegram。
- 不接管 launchd。
- 不要暴露公网或局域网。
- 先检查当前未提交 diff、验证结果和风险，再决定是否 commit/push。
```
