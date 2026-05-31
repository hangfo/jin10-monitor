# 034 - Dashboard Phase 1 交接

日期：2026-05-23

更新时间：2026-05-31（Asia/Shanghai）

## 当前状态

独立 FastAPI/Jinja2 dashboard 的 Phase 1 已在 `main` 上实现、提交并推送。

最新提交：

```text
2a555b3 feat(dashboard): complete phase 1 pages
```

推送后工作区是干净的。

## 已完成内容

- 保留旧的 `6330022` 只读 `jin10_monitor.py --dashboard` MVP 作为 fallback。
- 正式 dashboard 方向只继续放在独立文件中：
  - `run_dashboard.py`
  - `dashboard/app.py`
  - `dashboard/db.py`
  - `dashboard/templates/*`
- 未继续扩展 `jin10_monitor.py`。
- 新增共享 Jinja2 layout：
  - `dashboard/templates/base.html`
- 替换旧 standalone 首页模板：
  - 移除 `dashboard/templates/index.html`
  - 新增 `dashboard/templates/feed.html`
- 新增 Phase 1 页面：
  - `/`
  - `/item/{message_id}`
  - `/telegram-status`
  - `/system`
  - `/analyze`，作为 Phase 2A 占位页
- 扩展快讯流筛选：
  - priority
  - keyword
  - recent hours
  - limit
  - 仅确认 Telegram 已发送
- 修正 Telegram 已发送语义：
  - `tg_sent_only` 使用 `delivery_log`
  - `telegram_delivery_status` 仍仅作为诊断状态
- 新增详情页增强：
  - 上下文时间线
  - 最新 Telegram 状态
  - 可用时展示 raw JSON 折叠区
  - 预填 `/analyze` 链接，带 `from_item_id`、`window_start` 和 `window_end`
- 新增只读 dashboard DB helper：
  - `query_feed_density`
  - `query_keyword_heatmap`
  - `query_item`
  - `query_tg_status_for_item`
  - `query_tg_deliveries`
  - `query_tg_summary`
  - `query_system_health`
  - `query_nav_summary`
- 更新 `README.md` 和 `CHANGELOG.md`。

## 验证

最后一次本地测试：

```text
.venv/bin/python -m pytest -q
107 passed
```

以下浏览器 smoke checks 通过：

- `http://127.0.0.1:8765/`
- `http://127.0.0.1:8765/item/{message_id}`
- `http://127.0.0.1:8765/telegram-status`
- `http://127.0.0.1:8765/system`
- `http://127.0.0.1:8765/analyze`
- `http://127.0.0.1:8765/healthz`

验证期间截取的截图：

```text
/private/tmp/jin10-dashboard-phase1-merge-fixed.png
```

## 已保留的边界

- Phase 1 未修改 `jin10_monitor.py`。
- Dashboard 使用 `mode=ro` 和 `PRAGMA query_only = ON` 打开业务 SQLite。
- 业务历史 DB 缺失时，Dashboard 不创建它。
- Dashboard 不调用金十 REST。
- Dashboard 不打开 WebSocket。
- Dashboard 不发送 Telegram。
- Dashboard 不实现 retry、resend 或 backfill 操作。
- `delivery_log` 仍是成功 Telegram 去重的唯一权威。
- `telegram_delivery_status` 仍仅用于诊断。

## 已知取舍

- `query_keyword_heatmap` 当前使用一组小型固定 dashboard keyword list。后续可以改为复用配置关键词，但 Phase 1 不需要。
- `/analyze` 只是占位页。它接受预填查询参数，但不构建 evidence packet、不写分析数据，也不调用任何 AI API。
- 系统页通过 `runtime_state.last_ingested_at` 推断监控新鲜度；这是只读健康提示，不是进程监管。

## 下一阶段建议

开始 Phase 2A：手工 AI 分析循环。

建议顺序：

1. 新增 `dashboard/analysis_db.py`。
2. 创建独立 `data/dashboard_analysis.sqlite3` 数据库结构。
3. 增加测试，证明分析 DB 写入与业务历史 DB 隔离。
4. 新增 `dashboard/evidence.py`，只从本地 SQLite 构建 evidence packet。
5. 新增 `dashboard/manual_ai.py`，用于 prompt 生成和宽松答案解析。
6. 将 `/analyze` 占位页替换为手工流程：
   - 选择问题 / symbol / 时间窗口
   - 预览 evidence packet
   - 复制 prompt
   - 粘贴 ChatGPT Business / Custom GPT 答案
   - 本地保存答案和 references

Phase 2A 重要默认值：

- 不依赖 Anthropic / Claude API。
- 不依赖自动模型 API。
- Evidence builder 只读本地 SQLite。
- Evidence builder 不调用金十 REST。
- 分析只写 `data/dashboard_analysis.sqlite3`。
- 业务历史 DB 保持只读。

## 模型建议

下一次 Phase 2A session 建议使用 `GPT-5.5 高`，因为会触及 schema 设计、evidence 边界、手工解析和 UI 工作流。
