# 项目状态摘要 015：自愈摘要降噪与历史入库语义修复已完成

更新时间：2026-05-16 晚间（Asia/Shanghai）

## 1. 这份文档的用途

本文件用于在新 session 中快速续接可靠性修复阶段，不需要回读旧聊天。

这份摘要重点覆盖：

- 自愈补拉摘要频繁夹在实时消息中的问题如何处理。
- `save_history_item` 重复入库覆盖首次来源和优先级的问题如何修复。
- 当前 Git 状态、后台服务 reload 状态和验证结果。
- 下一步建议优先处理什么。

## 2. 当前仓库状态

- 项目：jin10-monitor
- GitHub 仓库：https://github.com/hangfo/jin10-monitor
- 本地路径：`/Users/rich/jin10-monitor`
- 分支：`main`
- 当前最新提交：
  - `8a59f86 fix(storage): preserve first ingest semantics`

最近提交：

```text
8a59f86 fix(storage): preserve first ingest semantics
15d8ff2 fix(catchup): throttle gap summary telegram
3f8d5b9 docs(status): add auto summary status handoff
06423a2 fix(catchup): record auto summary delivery status
e5e6867 docs(status): add telegram status query handoff
3bce008 feat(telegram): add delivery status query
```

本摘要生成前已确认：

- `8a59f86` 已推送到 `origin/main`。
- `main` 已与 `origin/main` 同步。
- 工作区干净。

新 session 仍必须重新执行本地 Git 检查，不要只凭本文件判断现场状态。

## 3. 本次修复内容

### 3.1 自愈补拉摘要降噪

问题：

- 常驻进程检测到 REST 轮询停顿超过 `AUTO_CATCHUP_GAP_SECONDS=300` 秒时，会触发自愈补拉摘要。
- 在网络或系统持续不稳定时，摘要可能每十几分钟夹在实时快讯之间，影响 Telegram 群阅读流。

已完成：

- 为 `trigger="gap"` 的自愈补拉摘要增加 30 分钟发送冷却。
- 新增运行状态 key：
  - `last_gap_summary_telegram_at`
- 冷却只影响 gap 自愈摘要。
- 启动离线补拉摘要不受影响。
- 补拉入库、实时消息推送和投递状态记录不受影响。

验证到的真实运行表现：

- 20:12 触发自愈补拉但 `入库 0 条，命中 0 条，摘要 未发送`。
- 20:29 发送一条自愈摘要。
- 21:01 再发送一条自愈摘要。
- 两条摘要间隔约 32 分钟，符合 30 分钟冷却。
- 21:01 摘要后，21:08、21:13、21:16、21:18、21:25 的实时消息继续正常发送。

### 3.2 历史入库 upsert 语义修复

问题：

- `save_history_item()` 原来使用 `INSERT OR IGNORE` 后再无条件 `UPDATE`。
- 同一条消息如果先由 WS 入库，后续又被 REST 或补拉遇到，后来的路径会覆盖首次 `source`、`hit`、`high` 和 `priority_level`。
- 这会污染历史数据语义，尤其是首次来源和优先级分析。

已完成：

- 改为明确的 `INSERT ... ON CONFLICT(id) DO UPDATE`。
- 重复 id 时：
  - 保留首次 `source`。
  - 保留 `created_at`。
  - `hit` / `high` / `important` / `has_bold` 使用 OR 语义，正向标记不丢。
  - `priority_level` 只升级不降级。
  - 降级场景保留旧 `style_flags`。
  - `title` / `content` / `raw_json` / `pic_url` / `news_source` / `source_url` 仍可更新。
- `update_ingest_cursor()` 在真正更新游标后自行 `commit()`，减少未来调用踩隐式事务依赖的风险。

最重要的保护点：

- 没有修改 WebSocket 接收逻辑。
- 没有修改 REST 拉取逻辑。
- 没有修改 Telegram 发送逻辑。
- 没有修改 `delivery_log` 去重语义。
- 没有新增 `.env` 字段。
- 没有修改启动命令或 launchd 配置。

## 4. 验证结果

已执行并通过：

```bash
.venv/bin/python -m py_compile jin10_monitor.py
git diff --check
```

临时 SQLite 验证：

1. WS 高优先级先入库、REST 低优先级后入库：

```text
('ws', 1, 1, 'T2_HIGH', '普通后续文本', 'rest-src', 'https://example.com/p.png')
```

确认：

- `source=ws` 保留。
- `hit/high/priority_level` 未降级。
- 展示元数据可更新。

2. REST 低优先级先入库、WS 重要消息后入库：

```text
('rest', 1, 1, 1, 'T3_IMPORTANT', '重要后续文本')
```

确认：

- 首次来源保留。
- 优先级可升级。

3. 单独调用 `update_ingest_cursor()` 后重开连接读取：

```text
{'last_ingested_at': '2026-05-16 10:02:00', 'last_ingested_id': 'phase0-cursor-1'}
```

确认：

- cursor 已独立提交。

## 5. 后台服务状态

已执行：

```bash
./scripts/launchd/manage.sh reload
./scripts/launchd/manage.sh status
```

确认结果：

- launchd 服务为 `running`。
- reload 后新 PID 为 `10716`。
- reload 后日志显示：
  - `=== 金十快讯监控启动 ===`
  - `离线补拉完成 ... 入库 0 条，命中 2 条，摘要 未发送`
  - `WebSocket 已连接`

## 6. 文档判断

已更新：

- `CHANGELOG.md`：记录自愈摘要降噪、历史入库 upsert 语义修复和本状态摘要。
- `docs/status/015-2026-05-16-gap-throttle-and-upsert-handoff.md`：新增本摘要。

本次不需要更新：

- `.env.example`：没有新增配置项。
- `README.md`：没有新增用户命令或配置方式。
- `docs/operations/001-launchd.md`：没有修改启动方式、后台服务管理方式或 launchd 配置。

## 7. 当前风险判断

风险等级：中低。

影响范围：

- WebSocket：未修改接收逻辑。
- REST：未修改拉取逻辑。
- Telegram 推送：未修改实时消息发送逻辑。
- SQLite 历史库：修改 `flash_history` 重复 id upsert 语义，并新增/使用 `last_gap_summary_telegram_at` 运行状态 key。
- 补拉去重：未修改，仍只通过 `delivery_log` 判断单条消息是否已成功发送。
- 自愈摘要：gap 摘要最多约 30 分钟发一次；启动离线摘要不受影响。
- 启动方式：未修改。
- 配置字段：未修改。

残余风险：

- 自愈摘要 30 分钟冷却是否足够，需要继续观察真实 Telegram 群体验。如果仍然嫌多，可以改为 60 分钟，或再加 `stored/push_candidates` 门槛。
- Telegram 发送仍可能因为网络超时出现 `unknown_timeout`，当前策略仍是避免自动重试以降低重复发送风险。
- 还没有正式 pytest 骨架，当前依赖临时 SQLite 验证和真实运行观察。

## 8. 下一步优先级

建议下一步进入最小 pytest 骨架，不要马上大规模拆模块。

优先测试纯函数和边界逻辑：

1. `item_datetime`
   - WS / REST 时间统一是补拉、延迟判断、游标推进的基础。
2. `classify_priority`
   - 直接影响 Telegram 是否推送和优先级。
3. `previous_page_cursor`
   - 补拉分页边界最容易出问题。
4. `format_message`
   - 影响 Telegram 展示、HTML escape、延迟显示。
5. `item_text` / `indicator_item_text`
   - 金十不同数据包结构会影响命中和展示。

建议先做 15 到 20 个关键用例，不要一次追求 50 个。

暂缓：

- 大规模模块拆分。
- Telegram inline 按钮。
- 配置 clamp。
- `Accept-Encoding: br`。

## 9. 新 session 交接提示词

新开 session 后可以直接贴：

```text
请继续 /Users/rich/jin10-monitor 项目。

先读取：
1. /Users/rich/jin10-monitor/AGENTS.md
2. /Users/rich/jin10-monitor/docs/status/015-2026-05-16-gap-throttle-and-upsert-handoff.md

默认不要回读旧聊天。先执行：
git branch --show-current
git status
git pull --rebase
git log --oneline -6

当前阶段目标：
进入最小 pytest 骨架阶段，优先保护纯函数和边界逻辑。继续小步可靠修复，不要大规模重构模块。

已完成：
- P0：last_ingested_at 游标安全修复，提交 5221a88。
- P1：catch_up_window 已放到 asyncio.to_thread，SQLite 已改线程本地连接并开启 WAL / busy_timeout，提交 da08e98。
- P1 后续：补拉重复时间戳翻页 cursor 已修复，提交 fbeb996。
- P2：Telegram delivery status 最小版已完成，提交 a163e2b。
- .env 数值配置容错已完成，提交 85cd1b0。
- Telegram 投递状态只读查询入口已完成，提交 3bce008。
- 自动补拉摘要投递状态记录已完成，提交 06423a2。
- 自愈补拉摘要 30 分钟冷却已完成，提交 15d8ff2。
- 历史入库 upsert 语义修复和 cursor 自提交已完成，提交 8a59f86。
- README.md 和 CHANGELOG.md 已更新。

下一步建议：
先给最小 pytest 骨架修改计划，等我确认后再改代码。优先覆盖 item_datetime、classify_priority、previous_page_cursor、format_message、item_text / indicator_item_text，先做 15 到 20 个关键用例即可。

要求：
- 先基于最新代码给修改计划，并等我确认后再改代码。
- 查询和诊断入口只做只读，不要实现重试队列。
- 优先做最小可靠修复，不要大规模重构模块。
- 继续保护现有补拉去重语义：已成功发送过的 Telegram 不重复补发。
- 如果新增 CLI 用户操作方式，预计需要更新 README.md 和 CHANGELOG.md。
- 修改后给 diff、风险和验证。
- commit/push 前更新 CHANGELOG.md，并等我确认。
```
