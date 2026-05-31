# 038 - Dashboard V2 bugfix 和计划交接

日期：2026-05-29

更新时间：2026-05-31（Asia/Shanghai）

## 当前状态

最新已推送提交：

```text
304929a fix(dashboard): polish feed bugs and v2 plan
```

推送后的分支状态：

```text
main...origin/main
```

独立 Dashboard 入口仍是：

```text
run_dashboard.py + dashboard/
```

不要通过扩展旧 `jin10_monitor.py --dashboard` 原型来继续工作。

## 本 session 已完成内容

审核了两个 proposal bundles：

- `phase 2a:b:c bug fix和dashaboard v2计划（v1).zip`
- `phase 2a:b:c bug fix（v2).zip`

最终结论：

- v2 是更好的代码基线。
- v1 的独特价值是 Dashboard V2 planning HTML。
- HTML plan 未作为 app route 加入，因为它会产生第二个维护面，并且包含过时表述。
- 其中有用的路线图内容已提炼到：

```text
docs/design/004-dashboard-v2-plan.md
```

## 已合并 bugfix

Dashboard 快讯流和分析 UI：

- 从 feed rendering 中移除 `style_flags`
- 隐藏 `title` 和 `content` 都为空的消息
- 修复 `has_title=0` 时正文重复渲染
- 将 feed timestamps 截断到分钟精度
- 给 `catchup_auto` / `catchup_manual` 增加可见的 `补拉` 标签
- 将 feed 中的 Telegram status labels 中文化
- 将 LLM direction labels 本地化为催化语义：
  - `▲ 偏利多`
  - `▼ 偏利空`
  - `◆ 多空混合`
- 增加全局 `box-sizing: border-box`
- 用 `min-width: 0` 修复分析表单 grid overflow

排序和上传安全：

- 将同秒 feed 和 context 的 tie-breaker 从 `created_at` 改为金十 message `id`
- 新增 `normalize_news_text()`，用于稳定的、不受空白影响的 title/content 对比
- screenshot upload 会尽可能在读取 body 前检查 `Content-Length`
- screenshot MIME 限制为 `png/jpeg/webp/gif`
- screenshot upload 的 500 错误不再回显 raw exception text

## commit 304929a 修改的文件

- `CHANGELOG.md`
- `dashboard/app.py`
- `dashboard/db.py`
- `dashboard/manual_ai.py`
- `dashboard/templates/_feed_rows.html`
- `dashboard/templates/analyze.html`
- `dashboard/templates/analyze_run.html`
- `dashboard/templates/base.html`
- `tests/test_dashboard_analysis.py`
- `tests/test_dashboard_db.py`
- `docs/design/004-dashboard-v2-plan.md`

## 验证

自动验证：

```text
.venv/bin/python -m pytest -q
139 passed in 0.55s

git diff --check
no output
```

浏览器 / 本地 server smoke：

- server 已在 `http://127.0.0.1:8765` 重启
- `/` 渲染时没有可见 `style_flags`
- feed status labels 以中文渲染
- feed timestamp 长度为 16 个字符（`YYYY-MM-DD HH:MM`）
- `#feed-sentinel` 存在，用于无限加载
- `/api/feed/page?offset=50&limit=2` 返回行且 `has_more=true`
- `/analyze` 渲染 screenshot upload 控件
- analysis grid 不再溢出容器
- SVG screenshot upload 被拒绝
- oversized `Content-Length` 会在读取 body 前被拒绝

## 003 和 004 的关系

`003-phase2b-phase3-spec.md` 是原始 Phase 2B / Phase 3 规格。
它定义了下一步要构建的内容：

- Phase 3A Telegram `/item/{id}` 链接
- Phase 3B 快讯流无限加载
- Phase 3C 截图上传
- confidence tooltip
- 后续 Provider Adapter
- 后续 Vision
- 后续 market overlay

`004-dashboard-v2-plan.md` 不替代 `003`；它是在 Phase 3A/3B/3C 完成、并审核 v1/v2 bugfix bundles 后，对路线图的更新。
主要差异：

- `004` 记录哪些 v1/v2 bundle 思路被接受或拒绝。
- `004` 将 Phase 3 视为已完成，并把项目推进到 V2 规划。
- `004` 明确了 `003` 未覆盖的 bugfix 决策：
  - 只在 dashboard rendering 中隐藏空消息，不改 monitor ingestion
  - 使用金十 `id`，而不是 `created_at`，作为同秒 tie-breaker
  - 使用 catalyst direction wording，而不是 prediction wording
  - 加固 screenshot upload 的 MIME 和大小处理
- `004` 将 market overlay 计划从具体 Binance-first feature 放宽为可选 market adapter boundary，因为 dashboard 启动不应依赖任何外部 market-data API。
- `004` 让下一步顺序更清晰：
  - 稳定化和 summary
  - analysis comparison
  - 可选 market overlay
  - Phase 2B Provider Adapter
  - 只在 provider / API 设置稳定后再做 Vision

## 建议的下一步顺序

推荐顺序：

1. 稳定化收口
   - 保留当前 `304929a` 作为 Phase 3 + V2 bugfix baseline
   - 本地 dashboard server 只用于手工检查
   - 在选择下一范围前避免新增 feature code

2. 分析对比，无外部 API
   - 新增 `/analyze/compare` 或 history page 对比模式
   - 选择两条现有 analysis runs
   - 对比 judgement、confidence、selected catalysts、missing evidence 和 referenced news
   - 仅使用 `dashboard_analysis.sqlite3`

3. Market overlay adapter，可选且有界
   - 选择数据源前先定义小型 `dashboard/market/` interface
   - 仅在用户打开相关 item 或明确请求时 fetch
   - 不调用金十 REST
   - 不让 dashboard 启动依赖网络访问

4. Phase 2B Provider Adapter
   - 定义 `dashboard/providers/`
   - 保持手工复制粘贴流程作为默认 fallback
   - 打开 dashboard 页面不应要求 provider key
   - provider 结果只写独立 analysis DB

5. Vision recognition
   - 只在 Provider Adapter 稳定且 API key 选择明确后进行
   - 用 Vision 建议结构化 `user_context`
   - 永远不自动覆盖用户的手工截图描述

## Adapter 与 market overlay 建议

推荐下一功能：先做分析对比，再做 market overlay，最后做 Provider Adapter。

如果必须在 Provider Adapter 和 market overlay 之间二选一，优先做 market overlay。

理由：

- Provider Adapter 会引入外部模型凭证、provider-specific errors、成本 / 限流行为，以及 streaming 或 timeout 设计。这是更大的架构边界。
- 当前手工 ChatGPT / Claude 流程已经可用，并且对用户工作流仍可接受，所以 Provider Adapter 不阻塞价值。
- Market overlay 可以做成只读、可选、用户触发的 adapter，在不改变 AI 流程的情况下改善 evidence interpretation。
- 设计良好的 market adapter 也会让后续 Provider Adapter 和 Vision 受益，因为价格上下文可以成为另一类 evidence input。

不要从硬编码 Binance 的 market overlay 开始。先冻结本地 interface 和 fallback behavior，再谨慎选择第一个数据源。

## 建议模型

- `GPT-5.5 中`：summary docs、diff review、analysis comparison、小型 dashboard UI 改进。
- `GPT-5.5 高`：Provider Adapter、streaming model calls、credential/error boundary，或扩展成 multi-source caching 和 normalization 的 market adapter。

## 可直接复制的 next-session prompt

```text
请继续 /Users/rich/jin10-monitor 项目。

建议模型：GPT-5.5 中，如果先做分析对比或小型 Dashboard V2 UI；GPT-5.5 高，如果要做 Phase 2B Provider Adapter、外部模型调用边界，或复杂行情 adapter。

先读取：
1. /Users/rich/jin10-monitor/AGENTS.md
2. /Users/rich/jin10-monitor/docs/status/038-2026-05-29-dashboard-v2-bugfix-plan-handoff.md
3. /Users/rich/jin10-monitor/docs/design/004-dashboard-v2-plan.md
4. /Users/rich/jin10-monitor/docs/design/003-phase2b-phase3-spec.md
5. /Users/rich/jin10-monitor/docs/design/002-dashboard-ai-full-spec.md

先执行：
git branch --show-current
git status
git pull --rebase
git log --oneline -8

当前结论：
- Phase 1、Phase 2A、Phase 3A/3B/3C 已完成并推送。
- 当前正式入口是 run_dashboard.py + dashboard/。
- 不继续扩展旧 jin10_monitor.py 内置 dashboard。
- 最新提交是 304929a fix(dashboard): polish feed bugs and v2 plan。
- 004 Dashboard V2 计划已新增：v2 补丁作为修复基线，v1 HTML 计划仅吸收为 Markdown 设计文档。
- 已修复 style_flags 外露、空消息纯数字行、正文重复、同秒排序、截图上传安全、方向标签语义、分析页溢出。
- 不接模型 API，不请求金十 REST，不写业务历史库，不触发 Telegram 重发。

下一步建议：
先做无外部 API 的分析对比功能，或先设计 market adapter 的最小边界；如果必须在 Provider Adapter 和行情叠加二选一，优先做行情叠加的 adapter 边界，不要先硬编码 Binance，也不要让 dashboard 启动依赖网络。
```
