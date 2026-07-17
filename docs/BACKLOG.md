更新时间：2026-07-17 22:33（Asia/Shanghai）

# Backlog

本文记录已识别但暂未进入当前提交范围的事项。优先级会随生产状态、A/B 结果和用户目标调整。

## 已完成：离线全量恢复与时间边界

- 启动自动补抓已取消 24 小时截断，改为从上次有效游标完整覆盖离线期，并以独立断点支持失败后下次启动续传。
- 任意时间手动回溯默认分片、幂等、只入库；历史 Telegram 必须显式选择，避免影响当前实时推送。
- Dashboard 分析与行情的全部日期时间输入已统一增加前端即时校验和服务端强制校验。
- 2026-07-16 至 2026-07-17 的生产缺口已补齐；后续仅需观察一次真实长离线重启是否按新断点语义完整收口。

## 已完成：Provider A/B 收口

### Provider A/B 人工 scorecard 落档

- 背景：`exports/provider_ab_after_fix/` 的 3 个样本已完成 Gemini + GLM 真实调用。
- 状态：已在 `docs/status/067-2026-06-26-provider-ab-scorecard-summary.md` 落档人工 scorecard 汇总。
- 结论：6/6 JSON 稳定；主要差异集中在 `news_driven` vs `macro_sentiment`、行情方向冲突和 missing evidence 口径。
- 边界：不重新调用 Provider API。

### 判断是否小改 judgement Prompt

- 背景：ETH 上涨样本中，证据偏美元/加息利空，模型仍给出宏观归因。
- 状态：已在 `bfec2bf` 完成 Prompt 调整。
- 当前观察口径：新样本应检查方向冲突场景是否降级为 `unclear` 或低置信 `macro_sentiment`，并确认 GLM 不再输出 `[#news_id]` 占位符。

## P0：近期应处理

### 新 Prompt 小样本观察

- 背景：`066` 已调整 Provider judgement Prompt，但尚未用新真实样本复测。
- 状态：已用两个方向冲突固定 packet 完成 Gemini + GLM/compatible 小批量真实复测；成功输出均降级为 `unclear` 或低置信 `macro_sentiment`，结构稳定，结果归档在 `docs/provider_ab_results.md`。
- 状态：2026-07-11 至 2026-07-17 已自然产生一个方向冲突样本和多个强方向一致样本；15 个完成态 run 的只读审计已记录在 `docs/provider_ab_results.md`。
- 结论：Gemini 在 CPI/PPI 强一致样本中仍能输出高置信 `news_driven`，没有被新规则过度压低；方向冲突和低质量证据样本仍存在偏积极归因，Provider 间置信度跨度也较大。
- 下一步：先收敛 evidence packet 的确定性、消息数量敏感度和置信度校准，再决定是否修改 Prompt；当前不继续修改 judgement Prompt 或 evidence scoring。
- 边界：真实调用必须显式 `--execute --yes`，结果只写 `exports/provider_ab*/<run_id>/`。
- 建议模型：`GPT-5.5 高`。

### 分析结论收敛与置信度校准

- 背景：同一自然窗口内，消息数量和边缘证据组成会改变结论，Gemini、GLM 与人工结果的置信度跨度可达到 `0.40 ~ 0.86`；单纯输出 `unclear` 不能满足“给出最可能解释并说明反证”的产品需求。
- 下一步设计：固定 evidence packet 的排序与数量，保存 packet 指纹；对同一窗口做 leave-one-out / top-K 敏感度审计；将“方向、证据强度、Provider 一致性、结论稳定性”拆成独立字段，再生成校准后的展示置信度和质量标签。
- 验收标准：相同输入重复构建得到相同 packet；移除低相关边缘消息不改变主结论；置信度能区分方向冲突、强一致和证据不足；结论即使不确定也必须给出主假设、备选假设和最关键缺失证据。
- 边界：先做离线只读回放和纯函数实现，不调用 Provider、不改业务历史库、不自动覆盖已有 `analysis_runs`。

## P1：体验增强

### `/system` 日志 level 筛选 UI

- 背景：后端 `/api/system/log-events` 支持 level 过滤。
- 状态：已完成，页面可选择全部、`ERROR`、`WARNING` 或 `SHELL`；Telegram 等显式 WARNING 不再误标为 SHELL。
- 边界：只读刷新，不改变日志扫描和缓存语义。

### A/B 离线复盘能力

- 状态：已完成基础能力。
- 用法：`scripts/run_ab_eval.py --rebuild-comparisons --summary-report` 可从已有导出结果补生成 `comparison.md` 并输出 `<output-root>/summary.md`。
- tracked 归档：`docs/provider_ab_results.md` 保留当前 `exports/provider_ab_after_fix` 的客观汇总表，原始 `exports/` 仍不进 Git。
- 边界：只读已有结果，不调用 Provider API，不做自动投票，不自动改 Provider 排序。
- 后续：如果样本扩大很多，再考虑把 summary 转成 Dashboard 只读页。

### 方向冲突置信度上限观察

- 背景：当前 Prompt 规则是“证据方向冲突且缺少直接市场证据时”降级。Review 建议进一步要求只要方向冲突，无论是否有市场数据，`overall_confidence` 都不得高于 `0.7`。
- 状态：暂不直接修改 Prompt。
- 理由：如果方向冲突但存在明确 ETF 资金流、订单流或清算证据，低于或等于 `0.7` 的硬上限可能过度压制真实解释；需要新样本证明模型仍过度自信后再改。
- 触发条件：后续 scorecard 中再次出现方向冲突且置信度过高、missing_evidence 不合理或传导链过度确定。

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
