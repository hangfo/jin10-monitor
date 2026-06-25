# 064 - Replit 355a88d 到 cacbe1d 深度审查跟进

更新时间：2026-06-25 21:44（Asia/Shanghai）

当前分支：`main`

## 背景

本轮复核 Replit 提供的 `355a88d → cacbe1d` 全量改动审查文本。当前仓库已经位于 `2b536dd`，包含 062/063 两轮 Provider A/B hardening 与 review follow-up，因此本轮只采纳仍适用于当前 HEAD 的增量建议。

## 逐项结论

### 已确认已覆盖

1. 心跳 6 小时静默盲区、失败不更新 `last_health_heartbeat_at`、心跳异常不带崩主路。
   - 状态：已在 `9a2bf67` 覆盖。
   - 本轮处理：不重复修改。

2. 日志扫描异常名、Traceback 聚合、TTL 缓存、force 刷新和元信息。
   - 状态：已在 `9a2bf67` 覆盖。
   - 本轮处理：只扩展 level 过滤。

3. Provider A/B 默认 dry-run、`--execute --yes`、批量上限、Provider 归一化、Dashboard 调用语义对齐、结果落盘安全。
   - 状态：已在 `cacbe1d`、`e9b8e75`、`2b536dd` 覆盖。
   - 本轮处理：只增加自动对比。

4. 外部监控文档。
   - 状态：已有 `docs/ops/external-monitoring.md`。
   - 本轮处理：不重复。

### 本轮直接采纳

1. `CHANGELOG.md` 日期分区。
   - 采纳状态：已采纳。
   - 实现：新增空 `## Unreleased`，把已推送的 2026-06-25 条目归入 `## 2026-06-25`。
   - 理由：已发布内容不应继续留在 Unreleased。

2. Provider A/B 自动对比。
   - 采纳状态：已采纳。
   - 实现：`scripts/run_ab_eval.py` 新增 `write_comparison()`；同一 `run_id` 至少有两个 Provider 结果时生成 `comparison.md`。
   - 字段：status、model、judgement、overall_confidence、catalysts 数量、missing_evidence 数量、JSON 稳定、耗时、Token、finish reason、错误。
   - 边界：只汇总客观字段和模型自报结构；关键催化覆盖、重复 `news_id`、缺失证据合理性和 `pass/watch/fail` 仍需人工 scorecard。

3. 日志 API level 过滤。
   - 采纳状态：已采纳。
   - 实现：`/api/system/log-events` 支持 `level=ERROR` / `level=SHELL` 等后端过滤。
   - 边界：不改变日志扫描、TTL 缓存、force 刷新和前端自动刷新逻辑。

### 后续计划

1. `docs/ROADMAP.md`、`docs/DECISIONS.md`、`docs/BACKLOG.md`。
   - 状态：后续独立文档阶段。
   - 理由：方向正确，但属于产品路线和架构决策收口，不应与本轮 review follow-up 代码增强混成一个提交。
   - 建议模型：`GPT-5.5 中`。

2. 更完整的 A/B 汇总报告。
   - 状态：后续等人工 scorecard 后再做。
   - 理由：当前 `comparison.md` 已解决打开多文件对照的痛点；自动结论或投票系统必须等主观字段有稳定口径。

3. 批量进度更细粒度展示。
   - 状态：已部分覆盖。
   - 理由：`e9b8e75` 已加实时 flush，当前会显示每个 `run_id` / Provider 调用进度；是否增加 `idx/total` 只是小体验优化。

### 不优先或不采纳

1. `raw_output` 自动截断。
   - 状态：不采纳。
   - 理由：A/B 评测需要保留 Provider 原始输出用于复盘；更适合后续只增加大小提示，而不是截断原始证据。

2. 自动 Provider 并发。
   - 状态：不采纳。
   - 理由：当前安全边界是串行、可观察、可中断，避免并发放大免费额度/成本消耗。

3. 把 ROADMAP 三件套塞进本轮。
   - 状态：不采纳。
   - 理由：会把产品路线整理和代码 review follow-up 混在一起，不利于审查和提交说明。

## 修改文件

```text
CHANGELOG.md
scripts/run_ab_eval.py
dashboard/app.py
tests/test_run_ab_eval.py
tests/test_dashboard_analysis.py
docs/design/008-provider-ab-evaluation-plan.md
docs/status/064-2026-06-25-replit-review-followup-handoff.md
```

## 边界确认

未改：

- WebSocket 实时主路。
- REST 补拉策略。
- Telegram 发送、健康心跳或 `delivery_log`。
- `data/history.sqlite3` 业务历史库写入逻辑。
- `data/dashboard_analysis.sqlite3` 的 `analysis_runs` 保存逻辑。
- Dashboard Provider 后台保存状态机。
- Provider API 默认启用范围。

本轮新增的 `comparison.md` 只写在 `exports/provider_ab/<run_id>/` 导出目录；日志 level 过滤只读。

## 验证计划

建议验证：

```bash
.venv/bin/python -m py_compile scripts/run_ab_eval.py dashboard/app.py
.venv/bin/python -m pytest tests/test_run_ab_eval.py tests/test_dashboard_analysis.py -q
.venv/bin/python -m pytest -q
git diff --check
```

## 下一步建议

P0：

1. 人工填写 `exports/provider_ab_after_fix/<run_id>/ab_scorecard.md` 主观字段。
2. 用 `comparison.md` + `ab_scorecard.md` 决定是否调整 judgement Prompt。

P1：

1. 独立文档阶段新增 `docs/ROADMAP.md`、`docs/DECISIONS.md`、`docs/BACKLOG.md`。
2. 若需要日志页筛选 UI，再给 `/system` 日志面板加 level 下拉；当前 API 已支持。

P2：

1. 如果 A/B 样本扩大，再做批量汇总 Markdown。
2. 如果 raw 输出文件变得很大，只增加大小提示，不截断原始输出。

## 下一 session 提示词

```text
继续 /Users/rich/jin10-monitor。

先读取 AGENTS.md、CHANGELOG.md、docs/design/008-provider-ab-evaluation-plan.md，以及 docs/status/064-2026-06-25-replit-review-followup-handoff.md。

当前边界：
- 已逐项复核 Replit 355a88d → cacbe1d 深度审查报告。
- 已采纳 CHANGELOG 日期归档、Provider A/B comparison.md、/api/system/log-events level 过滤。
- ROADMAP/DECISIONS/BACKLOG 暂列后续独立文档阶段。
- 不写 analysis_runs、不写业务历史库、不请求金十 REST、不触发 Telegram。
- WebSocket / REST / Telegram / Dashboard Provider 保存逻辑未改。

下一步优先：
1. 跑 targeted + full pytest 和 git diff --check。
2. 需要 closeout 时 commit/push。
3. 后续人工填写 scorecard，再决定是否改 Provider judgement Prompt。

模型建议：
- 测试、文档收口、ROADMAP 三件套：GPT-5.5 中。
- 修改 Provider judgement 口径、evidence scoring 或自动评测框架：GPT-5.5 高。
```
