# 068 - Provider A/B 与只读诊断阶段收口

更新时间：2026-06-26 01:30（Asia/Shanghai）

当前分支：`main`

## 背景

本轮对 `065` 至 `067` 之后的连续改动做阶段性复盘验收，确认 Provider A/B、Prompt 口径、只读日志筛选和离线汇总能力已经形成一个可交接的小阶段。

本轮不新增运行时代码能力，不调用 Provider API，不请求金十 REST，不触发 Telegram。

## 已完成事项

### Provider A/B 质量闭环

- 已复盘 `exports/provider_ab_after_fix/` 下 3 个 Gemini vs GLM 样本。
- 已生成 `docs/status/067-2026-06-26-provider-ab-scorecard-summary.md`，将人工 `pass` / `watch` / `fail` 结论落档到 Git。
- 当前结论：
  - Gemini：当前首选 Provider，前两个样本 `pass`，方向冲突样本 `watch`。
  - GLM / compatible：可作第二意见，但需观察弱链条、方向冲突和引用格式。
  - 3 个样本均 JSON 稳定，未发现重复 `news_id`。

### Provider judgement Prompt

- 已在 `bfec2bf` 调整 Prompt：
  - 当新闻证据方向与行情方向明显冲突，且缺少成交量、订单流、清算、资金费率或 BTC/ETH 联动等直接市场证据时，优先输出 `unclear` 或低置信 `macro_sentiment`。
  - `missing_evidence` 必须写明缺口。
  - GLM 不得输出 `[#news_id]` 字面占位符，必须使用真实消息 ID。
- 已补测试保护 Prompt 文案。

### `/system` 只读日志筛选

- 已在 `/system` 最近 monitor 错误日志面板增加 level 下拉：
  - 全部
  - `ERROR`
  - `SHELL`
- 前端复用既有 `/api/system/log-events?level=...`。
- 边界仍为只读刷新，不触发补拉、REST、Telegram 或业务库写入。

### A/B 离线复盘工具

- `scripts/run_ab_eval.py` 已新增：
  - `--rebuild-comparisons`
  - `--summary-report [PATH]`
- 已实际生成 ignored 导出文件：
  - `exports/provider_ab/*/comparison.md`
  - `exports/provider_ab/summary.md`
  - `exports/provider_ab_after_fix/*/comparison.md`
  - `exports/provider_ab_after_fix/summary.md`
  - `exports/provider_ab_gemini8192_thinking0/summary.md`
- 这些文件在 `.gitignore` 的 `exports/` 下，不进入 Git。

### 文档收口

- `CHANGELOG.md` 已把 2026-06-26 已提交内容从 `Unreleased` 归档到 `## 2026-06-26`。
- `docs/ROADMAP.md` 已更新 P0/P1 完成状态和下一步观察口径。
- `docs/BACKLOG.md` 已把已完成项移出近期待办，并保留后续观察项。

## 当前边界

未改：

- WebSocket 实时主路。
- REST 补拉策略。
- Telegram 发送、健康心跳或 `delivery_log`。
- `data/history.sqlite3` 业务历史库。
- `data/dashboard_analysis.sqlite3` 与 `analysis_runs` 保存逻辑。
- Dashboard Provider 后台保存状态机。
- Provider adapter 默认参数。

未调用：

- Provider API。
- 金十 REST。
- Telegram API。
- 本地 Dashboard 写入端点。

## 验收清单

已验证：

- `scripts/run_ab_eval.py --rebuild-comparisons --summary-report` 可离线补 `comparison.md` 与 `summary.md`。
- 单 Provider 导出目录会跳过 `comparison.md`，但仍可生成 `summary.md`。
- `/system` 页面可以渲染 level 下拉，`level=ERROR` API 只返回 ERROR。
- 全量测试在最近提交中通过：
  - `pytest tests/test_dashboard_analysis.py -q`
  - `pytest tests/test_run_ab_eval.py -q`
  - `pytest -q`
  - `git diff --check`

本次收口后还需重新跑一次 docs 结构验证和 `git diff --check`。

## handoff 频率策略

后续不再每个小改都生成 `docs/status/*`。

建议规则：

- 小改动只更新 `CHANGELOG.md`，不单独生成 handoff。
  - 例：文案、轻量 UI、单个只读筛选、小测试补充。
- 多个相关小改形成阶段后，再生成一个 handoff。
  - 例：Provider A/B 一组 CLI + Prompt + scorecard + 复盘工具。
- 必须生成 handoff 的情况：
  - Provider Prompt / evidence scoring / 保存状态机改动。
  - WebSocket / REST / Telegram / 启动方式 / 业务历史库边界改动。
  - 生产恢复、事故诊断、阶段性 closeout。
  - 用户明确要求交接或 commit+push closeout。
- `CHANGELOG.md` 继续每次用户可见变更都更新；`Unreleased` 只放尚未提交内容，提交后按日期归档。

## 下一步建议

P0：

1. 暂停继续改 Prompt。
2. 如果愿意消耗 Provider API，再用 2-3 个方向冲突样本复测 `066` Prompt 效果。
3. 如果不想消耗 API，继续只读观察后续自然产生的 Provider 输出。

P1：

1. 如果 A/B 样本扩大很多，把离线 `summary.md` 转成 Dashboard 只读页。
2. 如用户需要，评估 `/aggregation` SVG 和明细 AJAX 重绘。

模型建议：

- 只读观察、文档收口、小 UI：`GPT-5.5 中`。
- 真实 Provider 复测后的 Prompt / evidence scoring 继续调整：`GPT-5.5 高`。

## 下一 session 提示词

```text
继续 /Users/rich/jin10-monitor。

先读取：
1. AGENTS.md
2. CHANGELOG.md
3. docs/status/068-2026-06-26-provider-ab-phase-closeout.md
4. docs/ROADMAP.md
5. docs/BACKLOG.md
6. docs/design/008-provider-ab-evaluation-plan.md

当前边界：
- Provider A/B scorecard、Prompt 方向冲突规则、/system 日志 level 筛选、A/B 离线 comparison/summary 能力已完成阶段收口。
- 不写 analysis_runs、不写业务历史库、不请求金十 REST、不触发 Telegram。
- WebSocket / REST / Telegram / Dashboard Provider 保存逻辑未改。
- handoff 频率已收敛：小改只更新 CHANGELOG，多个相关小改形成阶段后再写 status。

下一步优先：
1. 若要真实复测新 Prompt，用 GPT-5.5 高，并明确允许 Provider API 调用。
2. 若继续只读观察或做小 UI，用 GPT-5.5 中。
3. 暂不继续改 evidence scoring，除非新 scorecard 证明关键新闻经常漏选。
```
