# 项目状态摘要 010：补拉重复时间戳翻页修复已完成

更新时间：2026-05-11 晚（Asia/Shanghai）

## 1. 这份文档的用途

本文件用于在新 session 中快速续接可靠性修复阶段，不需要回读旧聊天。

这份摘要重点覆盖：

- 补拉重复时间戳翻页修复已经完成什么。
- 当前 Git 状态、后台服务重载状态和验证结果。
- 下一步建议优先处理什么。

## 2. 当前仓库状态

- 项目：jin10-monitor
- GitHub 仓库：https://github.com/hangfo/jin10-monitor
- 本地路径：`/Users/rich/jin10-monitor`
- 分支：`main`
- 当前最新提交：
  - `fbeb996 fix(catchup): advance duplicate timestamp cursor`

最近提交：

```text
fbeb996 fix(catchup): advance duplicate timestamp cursor
71095af docs(status): add reliability p1 handoff
da08e98 fix(catchup): run catch-up off event loop
f7a63ce docs(status): add reliability p0 handoff
5221a88 fix(catchup): guard ingest cursor time
6d0f5a7 docs(status): add catchup progress handoff
```

本摘要生成前已确认：

- `git status` 干净，`main` 已与 `origin/main` 同步。
- `fbeb996` 已推送到 `origin/main`。
- 后台 `launchd` 服务已执行 `./scripts/launchd/manage.sh reload`，新进程正在运行。

新 session 仍必须重新执行本地 Git 检查，不要只凭本文件判断现场状态。

## 3. 本次修复内容

目标：避免补拉分页在重复时间戳场景下反复请求同一秒，浪费页数并影响窗口覆盖。

已完成：

- 新增 `previous_page_cursor(dated, current_cursor)`。
- `catch_up_window` 的下一页 cursor 从直接复用本页最后一条消息时间：

```python
cursor = dated[-1][0].strftime("%Y-%m-%d %H:%M:%S")
```

改为：

```python
cursor = previous_page_cursor(dated, cursor)
```

- 新 cursor 会取本页最旧消息时间，再向前移动 1 秒。
- 如果接口异常返回不早于当前 cursor 的页面，helper 会基于当前 cursor 再向前移动 1 秒，保证 cursor 不停在原地。
- `CHANGELOG.md` 已记录本次修复。

没有改动：

- 没有修改 `fetch_page_sync` 请求结构。
- 没有修改普通 REST 轮询。
- 没有修改 WebSocket 逻辑。
- 没有修改 Telegram 发送逻辑。
- 没有修改 SQLite 表结构。
- 没有新增 `.env` 配置字段。
- 没有修改启动命令。

## 4. 验证结果

已执行并通过：

```bash
.venv/bin/python -m py_compile jin10_monitor.py
git diff --check
```

旧风险复现：

- mock `fetch_page_sync` 始终返回一页最旧时间为 `2026-05-11 10:00:00` 的消息。
- 旧逻辑会持续请求同一个 cursor，直到 `max_pages=15`。

复现输出：

```text
ok True pages 15 scanned 3
calls ['2026-05-11 10:02:00', '2026-05-11 10:00:00', '2026-05-11 10:00:00', ...] total 15
same_cursor_after_first True
```

修复后重复时间戳边界验证：

```text
ok True pages 2 scanned 3
calls ['2026-05-11 10:02:00', '2026-05-11 09:59:59']
```

异常重复返回同页验证：

```text
ok True pages 15 scanned 3
calls ['2026-05-11 10:02:00', '2026-05-11 09:59:59', '2026-05-11 09:59:58', '2026-05-11 09:59:57', '2026-05-11 09:59:56', '2026-05-11 09:59:55'] total 15
strictly_decreasing_after_first True
```

## 5. 后台服务状态

已执行：

```bash
./scripts/launchd/manage.sh reload
./scripts/launchd/manage.sh status
tail -60 logs/jin10-monitor.log
```

确认结果：

- `launchd` 服务状态为 `running`。
- reload 后新 pid 为 `9251`。
- 日志显示 `22:55:49` 新进程启动。
- 启动后自动补拉执行成功：

```text
离线补拉完成：2026-05-11 22:53:21 -> 2026-05-11 22:55:49，入库 0 条，命中 0 条，摘要 未发送
```

- 冷启动预加载完成。
- REST 轮询已启动。
- WebSocket 已连接并发送登录包。
- WebSocket 初始历史列表已预热去重。

## 6. 当前风险判断

风险等级：中。

影响范围：

- 自动补拉 / 手动补拉：影响 `catch_up_window` 的分页 cursor 推进。
- 普通 REST 轮询：未修改。
- WebSocket：未修改。
- Telegram：未修改。
- SQLite：未修改表结构。
- 配置字段：未新增 `.env` 字段。
- 启动方式：未修改。

残余风险：

- 金十接口当前只看到秒级 `max_time`，没有二级 offset / id cursor。
- 如果同一秒内消息数量超过单页容量，且接口不能用更细粒度方式翻出同秒剩余消息，代码无法保证 100% 取回同秒溢出的全部消息。
- 本次修复解决的是“不要卡在同一秒、不要浪费页数、尽快覆盖更早窗口”，不能凭空补出 API 未暴露的分页能力。

## 7. 文档判断

本次不需要更新 `README.md` 或 `.env.example`：

- 没有新增配置项。
- 没有改变命令用法。
- 没有改变用户需要手动操作的流程。
- `CHANGELOG.md` 已记录用户可感知的可靠性变化。

## 8. 下一步优先级

建议下一步进入 P2：

### P2：Telegram delivery status 最小版设计

建议目标：

- 将 Telegram 发送结果从单一 delivery log 扩展为更可诊断的状态。
- 初始状态建议覆盖：`sent / failed / unknown_timeout / skipped`。
- 先做最小设计，不急着扩大到复杂重试队列。

需要先评估：

- 当前 `delivery_log` 主键是 `(message_id, channel, mode)`。
- 现有 `mark_delivery` 只记录成功发送。
- `send_telegram` 当前返回 bool，内部已有 timeout、网络异常、5xx 重试等逻辑。
- 需要判断是否新增表字段、另建状态表，或保守增加兼容字段。
- 需要避免破坏现有“补拉不重复发送已成功消息”的语义。

后续候选：

1. `.env` 数值配置安全解析。
2. 自动补拉逐条补发配置化，但默认仍不逐条补发，避免刷屏和实时消息混排。
3. 更细的补拉 API 能力探测。如果能确认接口支持毫秒级 / id cursor，再考虑消除同秒溢出的残余风险。

## 9. 新 session 交接提示词

新开 session 后可以直接贴：

```text
请继续 /Users/rich/jin10-monitor 项目。

先读取：
1. /Users/rich/jin10-monitor/AGENTS.md
2. /Users/rich/jin10-monitor/docs/status/010-2026-05-11-reliability-pagination-handoff.md

默认不要回读旧聊天。先执行：
git branch --show-current
git status
git pull --rebase
git log --oneline -6

当前阶段目标：
继续可靠性修复，优先处理 code review 里最紧迫的问题，不继续堆新功能。

已完成：
- P0：last_ingested_at 游标安全修复，提交 5221a88。
- P1：catch_up_window 已放到 asyncio.to_thread，SQLite 已改线程本地连接并开启 WAL / busy_timeout，提交 da08e98。
- P1 后续：补拉重复时间戳翻页 cursor 已修复，提交 fbeb996。
- 后台 launchd 服务已 reload，新代码已运行。

下一步建议：
进入 Telegram delivery status 最小版设计，先评估方案，不要直接大改表结构。

要求：
- 先基于最新代码给修改计划，并等我确认后再改代码。
- 优先做最小可靠修复，不要大规模重构模块。
- 重点保护现有补拉去重语义：已成功发送过的 Telegram 不重复补发。
- 修改后给 diff、风险和验证。
- commit/push 前更新 CHANGELOG.md，并等我确认。
```
