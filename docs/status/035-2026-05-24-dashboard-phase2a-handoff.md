# 035 - Dashboard Phase 2A 交接

日期：2026-05-24

更新时间：2026-05-31（Asia/Shanghai）

## 当前状态

独立 FastAPI/Jinja2 dashboard 的 Phase 2A 已提交并推送为
`bd303ae feat(dashboard): add manual analysis workflow`。

本交接也记录了后续准备给
`fix(dashboard): polish phase 2a dashboard`
的 dashboard polish / bugfix 补丁。

当前分支：

```text
main
```

后续补丁范围：

- `CHANGELOG.md`
- `dashboard/app.py`
- `dashboard/db.py`
- `dashboard/evidence.py`
- `dashboard/templates/feed.html`
- `dashboard/templates/analyze.html`
- `dashboard/templates/base.html`
- `dashboard/templates/system.html`
- `dashboard/templates/aggregation.html`
- `docs/status/035-2026-05-24-dashboard-phase2a-handoff.md`
- `tests/test_dashboard_analysis.py`
- `tests/test_dashboard_db.py`

Dashboard dev server 当前运行在：

```text
http://127.0.0.1:8765/
```

## 已完成内容

- 将 Phase 1 的 `/analyze` 占位页替换为 Phase 2A 手工分析流程：
  - 输入 question、asset、time window、可选 source item、可选 context
  - 预览本地 evidence packet
  - 选择 evidence rows
  - 为 ChatGPT Business 或 Custom GPT 生成复制粘贴 prompt
  - 将答案粘贴回 dashboard
  - 保存并查看分析历史 / 详情
- 新增独立分析数据库层：
  - 写入 `data/dashboard_analysis.sqlite3`
  - 创建 `analysis_runs`、`analysis_evidence` 和 `screenshots`
  - 启用 WAL 和 foreign-key 级联删除
  - 保持与 `data/jin10_history.sqlite3` 分离
- 新增本地-only evidence builder：
  - 通过现有只读 dashboard connection 读取 `flash_history`
  - 按资产关键词、高优先级关键词、宏观关键词、priority、important 和 bold flags 计分
  - 增加 `news_id`，保证后续 prompt / database / template 一致
  - 将 packet size 限制为 25 条
- 新增手工 AI helper：
  - prompt 生成，要求严格基于 evidence-only JSON
  - 宽松答案解析，支持 fenced JSON、bare JSON 或 best-effort JSON block extraction
  - 将 `[#news_id]` 渲染为指向 `/item/{id}` 的答案链接
- 新增分析模板：
  - `analyze.html`
  - `analyze_run.html`
  - `analyze_history.html`
- 改进快讯流页面：
  - keyword heatmap 现在使用 `jin10_monitor.py` 中真实配置的 `KEYWORDS` 和 `HIGH_PRIORITY` 列表
  - 高优先级 heatmap 关键词会高亮
  - 快讯流每 20 秒轮询 `/api/feed/latest-ts`，仅在检测到更新的 `published_at` 时刷新；页面隐藏时停止轮询，用户编辑筛选输入时跳过刷新
  - 轮询端点保留当前 feed filters，所以 keyword / priority 页面不会被无关新消息刷新
- 新增 Phase 2A polish / fix 项：
  - 禁用默认 FastAPI `/docs`、`/redoc` 和 `/openapi.json`
  - 新增分析历史和聚合报告导航链接
  - 将 evidence boundary 从普通字符串改为结构化对象，包含 `source`、`jin10_rest_called` 和 `market_data_called`
  - 新增只读 `/aggregation` 基础页，基于 skipped `telegram_delivery_status` 诊断
  - 改进 `/system` 监控状态，使用彩色中文状态标签
- 新增聚焦测试：
  - analysis DB roundtrip
  - cascade delete
  - analysis DB 与业务历史 DB 隔离
  - evidence scoring 和 `news_id` 标注
  - 答案解析和链接渲染
  - `/analyze/history` route 排序在 `/analyze/{run_id}` 之前
  - configured keyword heatmap 行为
  - disabled docs routes
  - 聚合报告只读 helper
- 更新 `CHANGELOG.md`。

## 代码导入说明

上传的 `phase 2a.zip` 有参考价值，但不能直接覆盖应用。

合并期间修复的问题：

- 上传版 `app.py` 注册了两次 `GET /analyze`，旧占位 route 会继续生效。
- 上传版 route 顺序把 `/analyze/{run_id}` 放在 `/analyze/history` 前面，会把 `history` 当成 run id。
- 上传版 evidence 路径查询 `id`，但下游代码期待 `news_id`。
- 上传版 `save_answer()` 更新路径存在 selected-count 参数顺序风险。
- 上传版 `db.py` 和 `base.html` 与已验证的 Phase 1 行为冲突，所以没有整体采用。
- 未新增 `python-multipart` 依赖；表单解析使用轻量 URL-encoded body parsing，避免让 Phase 2A 启动依赖新 package。
- 上传的 `phase 2a update.zip` 增加了一些有用想法，但同样不适合整体采用。已合并的部分包括 configured keyword heatmap、更多 Phase 2A 测试、可兼容的 analyze templates，以及 feed auto-refresh 行为。它的 `app.py` 没有采用，因为会重新引入 `Form(...)` / `python-multipart` 作为硬启动依赖。
- 上传的 `phase 2a bug fix.zip` 已审核并选择性合并：
  - 采用：禁用 docs/openapi、analysis history 和 aggregation nav、彩色 `/system` monitor status、结构化 evidence boundary、只读 `/aggregation`、用于 feed refresh 的 timestamp polling
  - 适配：`/api/feed/latest-ts` 现在保留当前 feed filters；aggregation env parsing 做了 clamp 且能容忍无效值；测试使用动态 timestamp，而不是固定 current-date fixture
  - 未原样采用：整体 `app.py`、`db.py` 和 templates，因为它们会覆盖已验证的 Phase 2A 行为，或降低与现有设计系统的兼容性

## 验证

最近一次本地测试：

```text
.venv/bin/python -m pytest -q
125 passed in 0.75s
```

Route count 检查：

```text
14 dashboard routes:
/
/item/{message_id}
/telegram-status
/system
/analyze
/analyze/preview
/analyze/generate-prompt
/analyze/save-answer
/analyze/history
/analyze/{run_id}
/analyze/{run_id}/delete
/api/feed/latest-ts
/aggregation
/healthz
```

以下浏览器 smoke checks 通过：

- `http://127.0.0.1:8765/`
- `http://127.0.0.1:8765/?keyword=美元&hours=24`
- `/aggregation`
- `/system`
- `/analyze`
- `/analyze/preview`
- `/analyze/generate-prompt`
- `/analyze/history`
- feed auto-refresh script 存在，且当前 filtered feed 可加载
- `/api/feed/latest-ts`，包括带关键词筛选的请求
- `/docs` 和 `/openapi.json` 返回 404

Smoke-test analysis run 在验证后已删除，之后 `analysis_runs` 为空。

## 已保留的边界

- 未修改 `jin10_monitor.py`。
- 未继续扩展旧 `6330022` in-file dashboard fallback。
- 未连接 OpenAI、Anthropic、Claude 或任何模型 API。
- 未新增自动模型 API 依赖。
- Evidence builder 只读本地 SQLite。
- Evidence builder 不调用金十 REST。
- Dashboard 不打开 WebSocket。
- Dashboard 不发送 Telegram。
- Dashboard 不实现 retry、resend 或 backfill 操作。
- 业务历史 DB 继续通过 `mode=ro` 和 `query_only` 保持只读。
- 分析结果只写 `data/dashboard_analysis.sqlite3`。
- `delivery_log` 仍是成功 Telegram 去重的唯一权威。
- `telegram_delivery_status` 仍仅用于诊断。

## 已知取舍

- 分析流程当前只接受 URL-encoded forms。Phase 2A 足够使用，并且避免新增 `python-multipart` 依赖。
- 虽然分析 DB schema 已包含 `screenshots` 表和 helper，但截图上传 route 还没有接入。
- Prompt 生成仅支持手工复制粘贴；没有 streaming UI，也没有 provider adapter。
- Evidence scoring 是启发式且仅本地化的。它可能错过本地历史 DB 中不存在的 market-moving context。
- `/analyze/preview` 不创建分析 DB；DB 会在 prompt generation、answer save、history、detail 或 delete 时创建。
- Feed auto-refresh 使用轻量 timestamp polling，而不是 HTMX/SSE。它保留当前 query string，并且只有在本地 SQLite 出现更新的匹配项时才 reload。

## 下一步建议

建议的下一步功能选择：

- 小型 polish，用 `GPT-5.5 中`：
  - 改进 `/analyze` 空状态 / 错误状态
  - 增加更清晰的 prompt-copy affordance
  - 给 README 增加截图
  - 在 `/system` 增加只读 analysis DB health row
- 更重的下一阶段，用 `GPT-5.5 高`：
  - Phase 2B provider adapter 设计
  - 截图上传和 attachment workflow
  - 更丰富的 evidence packet，加入 price / market overlays
  - 分析结果编辑 / versioning

## 可直接复制的 next-session prompt

```text
请继续 /Users/rich/jin10-monitor 项目。

建议模型：GPT-5.5 中，除非要做 Phase 2B provider adapter 或截图/行情增强，再用 GPT-5.5 高。

先读取：
1. /Users/rich/jin10-monitor/AGENTS.md
2. /Users/rich/jin10-monitor/docs/status/035-2026-05-24-dashboard-phase2a-handoff.md
3. /Users/rich/jin10-monitor/docs/design/002-dashboard-ai-full-spec.md

先执行：
git branch --show-current
git status
git pull --rebase
git log --oneline -8

当前结论：
- Phase 2A 手工 AI 分析流已在 bd303ae commit/push。
- Phase 2A follow-up polish/bugfix 已完成，最新 commit 应包含 `fix(dashboard): polish phase 2a dashboard`。
- 不修改 jin10_monitor.py。
- 不继续扩展旧 6330022 in-file dashboard。
- 不接 Claude / Anthropic / OpenAI 等模型 API 作为 Phase 2A 前置依赖。
- Evidence builder 默认只读本地 SQLite，不请求金十 REST。
- 分析结果只写 data/dashboard_analysis.sqlite3，不写业务历史库。

下一步：
先确认 `git status` 干净、`git pull --rebase` 无新冲突，再按需要选择下一阶段。
```
