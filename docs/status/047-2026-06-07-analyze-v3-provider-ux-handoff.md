更新时间：2026-06-07 11:36（Asia/Shanghai）

# 047 - Analyze V3 默认选择与 Provider UX 交接

## 本次状态

当前分支仍为 `main`。本轮工作聚焦 Dashboard `/analyze` 的证据默认选择、Provider 失败复盘、Gemini 调用体验、草稿展示和行情上下文开关。

已完成：

- `/analyze` evidence 默认选择升级为 v3。
- Provider 调用失败原因持久化到独立分析库草稿。
- Gemini `MAX_TOKENS`、不可解析 JSON、Provider 不可用等错误不再保存为 done。
- 草稿详情页和历史页不再把未完成记录显示为 `manual_chatgpt_business`，改为“待调用 / 待回填”。
- 草稿详情页提供完整 Prompt 复制、Provider 重试和手动 JSON 粘贴入口。
- Prompt 增加长度与已选证据数分级提示。
- Prompt 约束同一个 `news_id` 只能输出一个 catalyst，减少 Gemini 重复拆分同一新闻。
- `/analyze` 步骤导航支持已到达步骤回退和回填区域锚点跳转，未到达步骤保持锁定。
- 结构化行情上下文改为醒目的“加入行情摘要”开关卡片，默认不请求 market adapter。

## v3 默认选择策略

v3 仍是可解释规则，不是黑箱模型训练。

核心策略：

- 候选证据最多展示 40 条。
- 默认最多选 10 条进入 Prompt。
- 默认优先选择相关度不低于 `0.35` 的证据。
- 默认至少尝试保留 4 条较相关证据。
- 汇总、预告、夜盘要闻、整理类内容默认不选，除非分数非常高。
- 明显噪声、广告、过短或低相关内容默认不选。
- 每条候选显示 `selection_note`，解释为什么默认选中或默认不选。

这解决了用户试用中 `19 / 19` 全部进入 Prompt 后 Gemini 变慢、`MAX_TOKENS` 或过度压缩 catalysts 的问题。

## Provider 错误持久化

独立分析库 `analysis_runs` 新增字段：

- `provider_error`
- `provider_error_at`

行为：

- Provider 失败时只更新草稿，不改为 done。
- 失败错误会在详情页展示，刷新后仍可见。
- 成功保存分析时自动清空错误。
- `MAX_TOKENS` 使用中文可行动提示：减少证据数量或调高 `GEMINI_MAX_TOKENS`。

已覆盖错误：

- Gemini 非 `STOP` finishReason。
- 模型返回不可解析 JSON。
- Provider 不可用。
- Prompt 为空。
- 已完成记录再次调用 Provider。

## 行情上下文开关

当前最佳方案是默认不请求行情，避免浪费资源。

行为：

- 页面自动按标的匹配交易对：`BTC -> BTCUSDT`、`ETH -> ETHUSDT`、`SOL -> SOLUSDT`、`BNB -> BNBUSDT`。
- “加入行情摘要”默认关闭。
- 只有用户手动打开，才会在证据预览阶段请求 market adapter。
- 如需配置级默认开启，需要同时满足：

```bash
MARKET_CONTEXT_DEFAULT_ENABLED=1
MARKET_ADAPTER=binance
```

未配置或未手动开启时，不请求 Binance，不影响 Prompt 生成。

## 验证

已执行：

```bash
.venv/bin/python -m pytest tests/test_dashboard_analysis.py -q
.venv/bin/python -m pytest -q
.venv/bin/python -m py_compile dashboard/app.py dashboard/evidence.py dashboard/analysis_db.py dashboard/manual_ai.py
git diff --check
git fetch origin main
```

结果：

- `tests/test_dashboard_analysis.py`：47 passed
- 全量 pytest：188 passed
- `py_compile`：通过
- `git diff --check`：通过
- `HEAD` 与 `origin/main` 在提交前一致

## 明确未做

- 未请求金十 REST。
- 未修改 WebSocket / REST / Telegram 采集或发送逻辑。
- 未写业务历史库。
- 未自动重发 Telegram unknown_timeout。
- 未接 GLM Flash 做真实 A/B。
- 未引入 embedding、向量检索或机器学习训练。
- 未删除旧 Dashboard fallback 代码。

## 当前遗留问题

建议下一步按优先级处理：

1. Gemini / ChatGPT Plus / GLM 同窗 A/B：固定同一个 evidence packet、时间窗口、行情开关状态和 Prompt 版本，对比 catalysts 覆盖、judgement、置信度和 JSON 稳定性。
2. v3 选择策略继续小样本校准：重点观察默认 4-8 条是否漏掉关键新闻，尤其是宏观数据和地缘消息混合窗口。
3. 历史草稿管理：试用会留下失败或未回填草稿，可增加历史页草稿筛选、批量删除或只显示最近失败原因。
4. Provider 限额与用量可视化：Gemini 免费/付费限额可能因模型和账户不同变化，后续可在 `/system` 增加本地调用次数和最近失败统计，但不要代替官方账单。
5. 真正第 4 步独立页面：当前“4 回填答案”是锚点跳转；如后续手动回填流程变复杂，可拆成独立 step/route。

## 下一 session 建议

推荐先做 P0：

- 做一次严格的同窗 A/B 设计，不急着再改评分模型。
- 选 3-5 个历史窗口，每个窗口固定 evidence packet，分别跑 Gemini、ChatGPT Plus 手动、GLM Flash。
- 用人工表格记录：是否命中关键新闻、是否重复同一 `news_id`、judgement 是否一致、missing_evidence 是否合理、JSON 是否稳定。

推荐模型：

- `GPT-5.5 中`：同窗 A/B 设计、草稿筛选、Provider 状态展示、v3 小幅校准。
- `GPT-5.5 高`：embedding/向量相似度、评测框架、Provider/Vision 深度集成、任何 WebSocket/REST/Telegram/SQLite 游标或外部源逻辑。
