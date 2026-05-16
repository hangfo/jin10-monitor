# 项目状态摘要 016：最小 pytest 骨架和 SQLite 边界测试已完成

更新时间：2026-05-17（Asia/Shanghai）

## 1. 这份文档的用途

本文件用于在新 session 中快速续接测试骨架阶段，不需要回读旧聊天。

这份摘要重点覆盖：

- 最小 pytest 骨架已经如何落地。
- 目前已覆盖哪些纯函数和 SQLite 边界语义。
- 当前 Git 状态和验证结果。
- 下一步建议优先处理什么。

## 2. 当前仓库状态

- 项目：jin10-monitor
- GitHub 仓库：https://github.com/hangfo/jin10-monitor
- 本地路径：`/Users/rich/jin10-monitor`
- 分支：`main`
- 当前最新提交：
  - `3c665dd test(storage): cover sqlite boundary semantics`

最近提交：

```text
3c665dd test(storage): cover sqlite boundary semantics
591bea8 test(core): add minimal pytest skeleton
4309c11 docs(status): add gap throttle and upsert handoff
8a59f86 fix(storage): preserve first ingest semantics
15d8ff2 fix(catchup): throttle gap summary telegram
3f8d5b9 docs(status): add auto summary status handoff
```

本摘要生成前已确认：

- `3c665dd` 已推送到 `origin/main`。
- `main` 已与 `origin/main` 同步。
- 工作区干净。

新 session 仍必须重新执行本地 Git 检查，不要只凭本文件判断现场状态。

## 3. 本阶段已完成内容

### 3.1 最小 pytest 骨架

提交：

- `591bea8 test(core): add minimal pytest skeleton`

已完成：

- 新增 `requirements-dev.txt`。
- README 新增“本地测试”小节：
  - `pip install -r requirements-dev.txt`
  - `pytest`
- 新增 `tests/test_pure_functions.py`。
- 初始覆盖 19 个纯函数和边界用例。

覆盖范围：

- `item_datetime`
  - unix 秒级时间戳。
  - unix 毫秒时间戳。
  - REST 完整时间字符串。
  - REST 分钟级时间字符串。
  - 空值和非法值。
- `classify_priority`
  - important 优先。
  - high 优先于普通命中。
  - 普通命中。
  - 未命中。
- `previous_page_cursor`
  - 正常回退到本页最旧消息前 1 秒。
  - 重复 cursor 时间不向前推进。
  - 分钟级 cursor。
- `item_text` / `indicator_item_text`
  - 标准 title/content。
  - HTML 清理。
  - 从 `【标题】正文` 拆标题。
  - 指标包标题和数值正文。
  - 未知包返回空。
- `format_message`
  - HTML escape。
  - 补拉标记。
  - 来源链接和图片链接。
  - 无标题但 HTML bold content 的展示。

### 3.2 SQLite 边界测试

提交：

- `3c665dd test(storage): cover sqlite boundary semantics`

已完成：

- 新增 `tests/test_storage.py`。
- 使用 pytest `tmp_path` 创建临时 SQLite。
- 测试中临时替换 `jm.HISTORY_DB`。
- 每个测试结束关闭线程本地连接，避免测试间串库。

覆盖范围：

- `save_history_item`
  - WS 高优先级先入库、REST 普通重复入库时：
    - 保留首次 `source=ws`。
    - `hit/high/has_bold/priority_level` 不降级。
    - 展示元数据仍可更新。
  - REST 普通先入库、WS 重要消息重复入库时：
    - 保留首次 `source=rest`。
    - `important/high/priority_level` 可升级。
- `update_ingest_cursor`
  - 游标更新后重开连接仍可读取，确认函数会自行 commit。
  - 远未来时间消息不会推进 `last_ingested_at`。
- Telegram 去重语义
  - `mark_delivery` 写入 `delivery_log` 后，`has_any_delivery` 可识别已成功发送。
  - `record_telegram_delivery_status` 只写诊断状态，不写 `delivery_log`，不会污染补拉去重判断。
- `select_catchup_send_candidates`
  - 会跳过 `already_delivered=True` 的候选。

## 4. 验证结果

已执行并通过：

```bash
.venv/bin/python -m py_compile jin10_monitor.py tests/test_pure_functions.py tests/test_storage.py
git diff --check
.venv/bin/python -m pytest
```

pytest 结果：

```text
26 passed
```

## 5. 文档判断

已更新：

- `README.md`：新增本地测试入口。
- `CHANGELOG.md`：记录最小 pytest 骨架和 SQLite 边界回归测试。
- `docs/status/016-2026-05-17-pytest-skeleton-handoff.md`：新增本摘要。

本阶段不需要更新：

- `.env.example`：没有新增配置项。
- `docs/operations/001-launchd.md`：没有修改启动方式、后台服务管理方式或 launchd 配置。
- README CLI 模式说明：没有新增业务 CLI。

## 6. 当前风险判断

风险等级：低。

影响范围：

- WebSocket：未修改。
- REST：未修改。
- Telegram 推送：未修改，测试不发送真实 Telegram。
- SQLite 历史库：未修改运行逻辑；测试只操作临时库。
- 补拉去重：未修改运行逻辑；新增测试保护“已成功发送过的 Telegram 不重复补发”。
- 启动方式：未修改。
- 配置字段：未修改。

残余风险：

- `catch_up_window` 仍缺少 mock REST 页面的单元测试。
- 自动补拉摘要冷却仍主要依赖真实运行观察和已有逻辑验证。
- Telegram 网络异常路径仍没有完整单元测试，当前策略仍是避免对未知超时自动重试，以降低重复发送风险。

## 7. 下一步优先级

建议下一步继续做小步测试，不要大规模拆模块。

优先：

1. `catch_up_window` 无网络单元测试
   - mock `fetch_page_sync`。
   - 覆盖窗口过滤。
   - 覆盖已入库统计。
   - 覆盖已投递跳过。
   - 覆盖 `max_store` 截断。
   - 覆盖翻页 cursor 推进。

2. 自动补拉摘要相关纯逻辑
   - `build_catchup_summary_message`。
   - `catchup_summary_status_id`。
   - `catchup_summary_delivery_detail`。

暂缓：

- 大规模模块拆分。
- Telegram inline 按钮。
- 配置 clamp。
- `Accept-Encoding: br`。
- 真正联网的 Telegram/REST 集成测试。

## 8. 模型建议

下一阶段可以默认使用 `GPT-5.5 中`。

理由：

- 当前代码和测试骨架已经清楚。
- 下一步主要是 mock 测试和文档收束。
- 只有再次进入 SQLite 并发、Telegram 去重实装、线上异常复盘时，才建议切回 `GPT-5.5 高`。

## 9. 新 session 交接提示词

新开 session 后可以直接贴：

```text
请继续 /Users/rich/jin10-monitor 项目。

先读取：
1. /Users/rich/jin10-monitor/AGENTS.md
2. /Users/rich/jin10-monitor/docs/status/016-2026-05-17-pytest-skeleton-handoff.md

默认不要回读旧聊天。先执行：
git branch --show-current
git status
git pull --rebase
git log --oneline -6

当前阶段目标：
继续最小 pytest 骨架阶段，优先保护补拉窗口和摘要相关边界逻辑。继续小步可靠修复，不要大规模重构模块。

已完成：
- 最小 pytest 骨架已完成，提交 591bea8。
- SQLite 边界测试已完成，提交 3c665dd。
- README.md 和 CHANGELOG.md 已更新。

下一步建议：
先给 catch_up_window 无网络单元测试修改计划，等我确认后再改代码。优先 mock fetch_page_sync，覆盖窗口过滤、已入库统计、已投递跳过、max_store 截断和翻页 cursor 推进。

要求：
- 先基于最新代码给修改计划，并等我确认后再改代码。
- 查询和诊断入口只做只读，不要实现重试队列。
- 优先做最小可靠修复，不要大规模重构模块。
- 继续保护现有补拉去重语义：已成功发送过的 Telegram 不重复补发。
- 如果新增 CLI 用户操作方式，预计需要更新 README.md 和 CHANGELOG.md。
- 修改后给 diff、风险和验证。
- commit/push 前更新 CHANGELOG.md，并等我确认。
```
