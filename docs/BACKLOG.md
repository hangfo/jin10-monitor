更新时间：2026-06-26 01:24（Asia/Shanghai）

# Backlog

本文记录已识别但暂未进入当前提交范围的事项。优先级会随生产状态、A/B 结果和用户目标调整。

## P0：近期应处理

### Provider A/B 人工 scorecard 落档

- 背景：`exports/provider_ab_after_fix/` 的 3 个样本已完成 Gemini + GLM 真实调用。
- 现状：6/6 JSON 稳定；主要差异集中在 `news_driven` vs `macro_sentiment`、行情方向冲突和 missing evidence 口径。
- 下一步：把人工结论回填到各 `ab_scorecard.md`，或新增一份汇总文档。
- 边界：不重新调用 Provider API。

### 判断是否小改 judgement Prompt

- 背景：ETH 上涨样本中，证据偏美元/加息利空，模型仍给出宏观归因。
- 建议：增加规则：当证据主方向与行情方向明显相反，且缺少直接 ETH/BTC/订单流/成交量证据时，优先 `unclear` 或低置信 `macro_sentiment`，并明确 missing evidence。
- 风险：会影响 Dashboard Provider 输出口径。
- 建议模型：`GPT-5.5 高`。

## P1：体验增强

### `/system` 日志 level 筛选 UI

- 背景：后端 `/api/system/log-events` 已支持 `level=ERROR` / `level=SHELL` 等过滤。
- 下一步：给 `/system` 日志面板增加下拉筛选。
- 边界：只读刷新，不改变日志扫描和缓存语义。

### A/B 离线复盘能力

- 状态：已完成基础能力。
- 用法：`scripts/run_ab_eval.py --rebuild-comparisons --summary-report` 可从已有导出结果补生成 `comparison.md` 并输出 `<output-root>/summary.md`。
- 边界：只读已有结果，不调用 Provider API，不做自动投票，不自动改 Provider 排序。
- 后续：如果样本扩大很多，再考虑把 summary 转成 Dashboard 只读页。

## P2：后续观察

### `/aggregation` AJAX 重绘 SVG 和明细

- 背景：当前只读刷新只更新统计数字。
- 触发条件：用户明确需要图表和明细也无刷新页面更新。
- 风险：会把部分 Jinja 服务端渲染拆到前端，需控制 diff。

### Evidence scoring 小样本校准

- 背景：若人工 scorecard 显示关键新闻经常被默认选择漏掉，再回到 scoring。
- 触发条件：多个样本出现 key catalyst 未进入 selected evidence。
- 边界：先小样本回测，不直接大改 v3 默认选择。

### Provider 原始输出大小提示

- 背景：`raw_output` 不应截断，但可提示文件大小。
- 下一步：如果 raw 文件变大影响复盘，再加大小提示。
- 边界：不删除、不截断原始输出。

## 暂不做

- Canvas。
- Anthropic Provider 默认化。
- Provider 自动并发调用。
- A/B 自动投票或自动保存到 `analysis_runs`。
- WebSocket / REST / Telegram 主链路重构。
- 业务历史库 schema 调整。
