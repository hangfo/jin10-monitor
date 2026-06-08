更新时间：2026-06-09 02:45（Asia/Shanghai）

# 052 - 历史管理与 Provider 统计收口交接

## 本次状态

本轮接续 `047`、`048`、`049`、`050` 与设计文档 `007`、`008`，先完成上一轮 `043` review 跟进提交：

- commit：`ec370a2 fix(dashboard): clarify ops cockpit timeout diagnostics`
- push：已推送到 `origin/main`

随后收口 `047-050` 中仍适合本轮一次性完成的低风险遗留项。

已完成：

- 历史分析页新增状态筛选：
  - 全部
  - 调用中
  - 草稿
  - 已完成
  - 最近失败
- “最近失败”筛选只展示带 `provider_error` 的草稿，便于清理 Gemini / GLM 超时、空响应或不可解析 JSON 留下的失败草稿。
- 草稿删除策略已明确并落地：
  - 只允许删除 `draft` 记录。
  - `done` 记录保留用于复盘、Provider A/B 对比和后续质量评估。
  - `running` 记录不允许手动删除，避免后台任务完成时状态语义混乱。
- 详情页只有草稿显示删除按钮；直接 POST 删除已完成或调用中记录会被拦截并回到详情页提示原因。
- `/system` 增加只读 Provider 调用统计：
  - 最近 24h 调用数
  - 成功数
  - 失败数
  - 调用中数
  - 分 Provider 的 P50 / 平均 / 最大耗时
  - 最近错误与错误时间
- Provider 统计只读 `data/dashboard_analysis.sqlite3` 独立分析库，不请求模型 API，不请求金十 REST，不写业务历史库，不替代官方账单。

## 对 047-050 与 007/008 遗留项的处理

已完成 / 本轮收口：

1. Provider 后台调用 / running 状态：已在 `049` 完成，并在 `050` 增加重启孤儿清理、状态闸门和 running 自动刷新。
2. GLM 弱证据约束与失败 UX：已在 `048` / `050` 完成。
3. 历史状态筛选：本轮完成。
4. 草稿删除策略：本轮完成，策略为“只删草稿，不删 done / running”。
5. `/system` Provider 24h 只读统计：本轮完成。
6. Provider A/B 固定实验包：已在 `008` 设计，并由 `scripts/export_provider_ab_packet.py` 支持；本轮不自动调用模型。

继续暂缓 / 不混入本轮：

- Canvas mini K 线图：继续暂缓。当前 `/item/{id}` 已有基于 Lightweight Charts 的交互 K 线图，能覆盖币安行情查看需求；再做 Canvas mini 图属于可视化增强，不是历史管理或 Provider 状态收口。
- Anthropic Provider 真实试用：继续暂缓。当前已经先实现并验证免费 / 低成本优先的 Gemini 与 GLM 路线；Anthropic 属于付费能力扩展，不和本轮历史管理收口混在一起。
- GLM Prompt 结构重构：继续暂缓，除非先固定 3-5 个 evidence packet 做 A/B。
- 自动评测框架、embedding / 向量相似度、Vision 自动截图分析：继续暂缓，属于高复杂度质量评估或外部源能力扩展。
- 外部源 / 采集链路逻辑：继续暂缓，本轮不改变 Dashboard sidecar 边界。

## 边界

本轮保持：

- 不请求金十 REST。
- 不修改 WebSocket / REST / Telegram 采集或发送逻辑。
- 不写业务历史库。
- 不自动重发 Telegram `unknown_timeout`。
- 不自动调用 Provider。
- 不把 Dashboard 变成采集入口。
- 只写独立分析库中的分析记录状态；`/system` Provider 统计是只读查询。

## 验证

已执行：

```bash
git branch --show-current
git status --short --branch
git pull --rebase
git log --oneline -8
.venv/bin/python -m py_compile dashboard/app.py dashboard/analysis_db.py
.venv/bin/python -m pytest tests/test_dashboard_analysis.py -q
.venv/bin/python -m pytest -q
git diff --check
临时 `127.0.0.1:8766` 浏览器烟测
```

当前结果：

- 分支：`main`
- `git pull --rebase`：`Current branch main is up to date.`
- `047-050` 前置提交：`ec370a2` 已 push 到 `origin/main`
- `py_compile`：通过
- `tests/test_dashboard_analysis.py`：67 passed
- 全量 pytest：209 passed
- `git diff --check`：通过
- 临时 `127.0.0.1:8766` 浏览器烟测：
  - `/analyze/history?status=recent_failed`：200，状态筛选存在并选中 `recent_failed`。
  - `/system`：200，Provider 调用统计和“不代表官方账单”说明可见。

## 下一步建议

P0 / 做下一步：

1. 运行全量 pytest、`git diff --check` 和浏览器烟测。
2. 提交并推送本轮历史管理与 Provider 统计收口。
3. 用真实历史记录打开 `/analyze/history?status=recent_failed`，人工确认失败草稿是否容易定位。

P1 / 可做但不急：

1. `/system/ws-initial` 顶部行动指南。
2. 未确认 `unknown_timeout` 的 `ops_notes` 独立分析库备注设计。
3. Provider A/B 小样本人工记录，不自动化。

P2 / 继续暂缓：

1. GLM Prompt 结构重构。
2. Anthropic Provider 真实试用。
3. Canvas mini K 线图。
4. SSE 流式 Provider。
5. embedding、Vision、自动评测框架或外部源 / 采集链路扩展。

推荐模型：

- `GPT-5.5 中`：历史筛选、草稿管理、Provider 只读统计、`/system/ws-initial` 行动指南、ops_notes 设计。
- `GPT-5.5 高`：GLM Prompt 结构重构、自动评测框架、embedding / 向量相似度、Vision、SSE、Anthropic 深度集成或外部源 / 采集链路逻辑。

## 下一 session 可复制提示词

```text
继续 /Users/rich/jin10-monitor 项目。

先读取：
1. /Users/rich/jin10-monitor/AGENTS.md
2. /Users/rich/jin10-monitor/docs/status/052-2026-06-09-history-provider-stats-closeout-handoff.md
3. /Users/rich/jin10-monitor/docs/status/051-2026-06-08-review-043-ops-cockpit-followup-handoff.md
4. /Users/rich/jin10-monitor/docs/status/050-2026-06-08-review-047-049-followup-handoff.md
5. /Users/rich/jin10-monitor/docs/design/008-provider-ab-evaluation-plan.md

先执行：
git branch --show-current
git status
git pull --rebase
git log --oneline -8

当前结论：
- 047-050 遗留的历史管理收口已完成：历史页支持全部 / 调用中 / 草稿 / 已完成 / 最近失败筛选。
- 草稿删除策略已明确：只允许删除 draft；done 保留用于复盘和 A/B，对 running 不提供手动删除。
- /system 已增加最近 24h Provider 只读统计：调用、成功、失败、调用中、P50/平均/最大耗时和最近错误。
- Canvas mini K 线图继续暂缓，因为 /item/{id} 已有 Lightweight Charts 交互 K 线图。
- Anthropic Provider 继续暂缓；当前先用免费/低成本 Gemini 与 GLM 路线。
- Dashboard 仍是本地只读诊断和分析侧车，不作为采集入口。
- 不请求金十 REST，不写业务历史库，不自动重发 Telegram unknown_timeout。

推荐下一步：
1. 优先做 /system/ws-initial 顶部行动指南或 unknown_timeout ops_notes 设计。
2. 如果要比较 Provider 质量，用 008 的固定 packet 手工 A/B，不先做自动评测框架。
3. GLM Prompt 重构、Anthropic、Canvas mini 图、SSE、Vision、embedding 和外部源继续暂缓。

推荐模型：
- GPT-5.5 中：驾驶舱只读统计、ws_initial 行动指南、ops_notes、Provider A/B 手工整理。
- GPT-5.5 高：GLM Prompt 结构重构、自动评测框架、embedding/Vision、SSE、外部源或采集链路逻辑。
```
