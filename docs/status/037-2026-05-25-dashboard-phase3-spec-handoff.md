# 037 - Dashboard Phase 3 规格交接

日期：2026-05-25

更新时间：2026-05-31（Asia/Shanghai）

## 当前状态

本交接准备的最新本地提交是：

```text
4726a97 docs(dashboard): define phase 2b and phase 3 plan
```

开始本交接前，最新已推送 dashboard UX 提交是：

```text
7b190c4 feat(dashboard): improve analysis timing and news rendering
```

本交接记录了在审核 `phase 2a function 2&4&5.zip` proposal 后形成的 Phase 2B / Phase 3 规划检查点。

## Zip 审核结果

zip 包含六个文件：

- `manual_ai.py`
- `analyze.html`
- `analyze_run.html`
- `base.html`
- `feed.html`
- `item.html`

当前仓库实现对其中大多数文件已经更完整。直接替换会在多个地方让当前 UX 回退：

- `manual_ai.py`：会把更友好的基于时间戳的新闻链接，回退到 raw `[#news_id]` 风格标签。
- `analyze.html`：会用更多 inline JavaScript 替换更清晰的 `data-minutes` 快速窗口控件。
- `analyze_run.html`：会把 evidence sidebar 从时间 + headline/content + relevance 缩减为更薄的 ID/time 展示。
- `base.html`：会删除或重写现有共享新闻和 datetime 样式。
- `feed.html` 和 `item.html`：消息渲染方案不比当前类金十渲染器更好。

只采用了一个有用行为：

- 如果 `pic_url` 失效或加载失败，图片缩略图会隐藏自身
  (`onerror="this.closest('a').style.display='none'"`)

## 变更内容

### 1. Phase 2B / Phase 3 规格

新增：

```text
docs/design/003-phase2b-phase3-spec.md
```

该规格冻结下一步 dashboard 计划：

1. Phase 3A：通过 `DASHBOARD_URL` 增加 Telegram `/item/{id}` 深链
2. Phase 3B：带安全上限的快讯流无限加载
3. Phase 3C：截图上传与手工图表上下文
4. 置信度 tooltip，说明模型置信度是主观估计
5. Phase 2B provider adapter，用于可选 LLM API
6. provider / API key 可用后再做 Vision recognition
7. item 时间线的 market data overlay

### 2. 图片 fallback

更新：

- `dashboard/templates/feed.html`
- `dashboard/templates/item.html`

如果金十图片 URL 加载失败，隐藏 broken thumbnail link，避免在快讯流或详情页留下破图。

### 3. Changelog

更新：

- `CHANGELOG.md`

Changelog 现在记录了新的 003 spec 及其计划边界。

## 验证

最新验证：

```text
.venv/bin/python -m pytest -q
128 passed

git diff --check
no output

curl -s -o /tmp/jin10_root.html -w "%{http_code}" http://127.0.0.1:8765/
200

curl -s -o /tmp/jin10_analyze.html -w "%{http_code}" http://127.0.0.1:8765/analyze
200
```

## 已保留的边界

- 未修改 `jin10_monitor.py`。
- 未修改 launchd config。
- 未新增依赖。
- 未新增 `python-multipart`。
- 未连接任何模型 API。
- 未调用金十 REST 或 market-data APIs。
- 未发送 Telegram。
- 未写业务历史 DB。
- 分析写入仍隔离在 `data/dashboard_analysis.sqlite3`。

## 下一步建议工作

建议顺序：

1. 如果本地规划提交尚未推送，先推送它。
2. Phase 3A：增加 Telegram `/item/{id}` 深链。
3. Phase 3B：增加快讯流无限加载：
   - 首屏：50 行
   - 每次追加：30 行
   - 自动上限：500 行
4. Phase 3C：增加截图上传和手工图表描述。
5. 给分析结果增加置信度 tooltip。
6. 只有在 API key 可用后再做 Phase 2B provider adapter。

建议模型：

- Phase 3A 会触及 Telegram 消息格式，使用 `GPT-5.5 高`。
- Phase 3A 提交后，快讯流无限加载和置信度 tooltip 用 `GPT-5.5 中` 足够。

## 可直接复制的 next-session prompt

```text
请继续 /Users/rich/jin10-monitor 项目。

建议模型：GPT-5.5 高，如果要做 Phase 3A Telegram /item/{id} 深链；如果只是做快讯流无限加载或置信度 tooltip，用 GPT-5.5 中即可。

先读取：
1. /Users/rich/jin10-monitor/AGENTS.md
2. /Users/rich/jin10-monitor/docs/status/037-2026-05-25-dashboard-phase3-spec-handoff.md
3. /Users/rich/jin10-monitor/docs/design/003-phase2b-phase3-spec.md
4. /Users/rich/jin10-monitor/docs/design/002-dashboard-ai-full-spec.md

先执行：
git branch --show-current
git status
git pull --rebase
git log --oneline -8

当前结论：
- Phase 1 和 Phase 2A Dashboard 已完成。
- 当前正式入口是 run_dashboard.py + dashboard/。
- 不继续扩展旧 jin10_monitor.py 内置 dashboard。
- Phase 2A 手工 AI 分析流已完成：本地 SQLite evidence packet + ChatGPT/Claude 手工复制粘贴 + 独立分析库保存。
- 003 Phase 2B / Phase 3 规格已新增。
- phase 2a function 2&4&5.zip 已评估，除图片死链兜底外，其余实现相对当前 repo 都是回退或低收益替代，未采用。
- 不接模型 API，不请求金十 REST，不写业务历史库。

下一步：
优先做 Phase 3A：Telegram 消息附 /item/{id} 深链。按 003 spec 实现 DASHBOARD_URL 环境变量；为空时 Telegram 文本保持当前行为不变。先给计划，确认后小步修改、测试、更新 CHANGELOG、提交推送。
```
