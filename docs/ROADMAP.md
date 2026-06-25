更新时间：2026-06-26 01:30（Asia/Shanghai）

# 项目路线图

本文记录 `jin10-monitor` 当前阶段的产品和工程路线，优先服务独立 Dashboard、Provider A/B 复盘、只读运行诊断和采集稳定性维护。

## 当前原则

- 独立 Dashboard 继续走 `run_dashboard.py` + `dashboard/` 路线；旧 `jin10_monitor.py --dashboard` 只作为提示入口和兼容 fallback。
- Provider 分析结果和评测导出保持隔离：Dashboard 保存写 `data/dashboard_analysis.sqlite3`，A/B 评测结果只写 `exports/provider_ab*/<run_id>/`。
- 默认不改 WebSocket、REST、Telegram、业务历史库或生产启动方式，除非任务明确属于运行事故修复。
- Provider A/B 当前基线是 Gemini + GLM/OpenAI-compatible；Anthropic Provider 和 Canvas 继续暂缓。
- A/B 自动脚本只记录客观字段，质量判断仍以人工 scorecard 为准。

## P0：Provider A/B 质量收口

目标：先确认 Gemini 与 GLM 在固定 evidence packet 上的可用边界，再决定是否改 Prompt。

已完成：

- `scripts/run_ab_eval.py` 支持 `.env` 自动加载、实时 flush、`--skip-existing`、`--timeout 1-600`。
- Gemini 默认关闭 thinking 并提高 JSON 输出上限。
- GLM/智谱 compatible 默认关闭 `thinking.type`。
- 同一 `run_id` 多 Provider 结果会生成 `comparison.md`。
- `/api/system/log-events` 支持 level 过滤。
- 已落档 `exports/provider_ab_after_fix/` 的 3 个 Gemini vs GLM 人工 scorecard 汇总。
- 已调整 Provider judgement Prompt：证据方向与行情方向冲突且缺少直接市场证据时，优先 `unclear` 或低置信 `macro_sentiment`。
- 已补 A/B 离线复盘能力：可从已有导出结果重建 `comparison.md` 并生成批量 `summary.md`。

下一步：

- 暂不继续改 Prompt，等待后续新样本观察 `066` 规则是否减少方向冲突场景的强行归因。
- 如果要复测新 Prompt，明确使用 `--execute --yes`，并继续把结果只写到 `exports/provider_ab*/<run_id>/`。
- 如果 A/B 样本显著扩大，再考虑把离线 `summary.md` 做成 Dashboard 只读页；不要做自动投票。

建议模型：

- 只读复盘和文档整理：`GPT-5.5 中`。
- 修改 Provider prompt、evidence scoring 或比较体验：`GPT-5.5 高`。

## P1：Dashboard 只读诊断与复盘体验

目标：让日常观察更快定位问题，但不引入新的写入或外部调用。

候选方向：

- `/system` 日志面板已增加前端 level 下拉，复用 `/api/system/log-events?level=...`。
- Provider A/B 批量汇总 Markdown 和旧导出目录 `comparison.md` 离线重建能力已完成。
- Provider A/B 样本扩大很多后，可考虑把离线 `summary.md` 转成 Dashboard 只读页。
- `/aggregation` 如确实需要更实时，再评估 SVG 和明细表 AJAX 重绘。

边界：

- 不触发金十 REST。
- 不重试 Telegram。
- 不写业务历史库。
- 不把 A/B 结果自动写回 `analysis_runs`。

## P2：采集可靠性维护

目标：保持实时主路可观察、可恢复，并避免诊断逻辑污染业务语义。

候选方向：

- 持续观察健康心跳、REST 403 退避和 WebSocket initial history 状态。
- 需要生产恢复时，优先用现有分窗口补拉和断点续补能力，避免大窗口硬打 REST。
- 若监控进程异常，先检查 launchd 包装脚本、`.env` 加载和最新日志，再评估代码层修复。

边界：

- 健康心跳保持诊断语义，不写 `delivery_log`。
- 补拉历史默认只入库，不补发逐条 Telegram，除非明确要求。

## 暂缓方向

- Canvas 工作流。
- Anthropic Provider 作为默认基线。
- 自动 Provider 并发。
- embedding / 向量相似度。
- 自动投票或自动替代人工 scorecard。
- 大规模重写 evidence scoring。
