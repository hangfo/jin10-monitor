更新时间：2026-06-06 16:37（Asia/Shanghai）

# 046 - Evidence Scoring V2 与 Provider 分析体验交接

## 本次状态

当前分支仍为 `main`。本轮工作聚焦 Dashboard `/analyze` 的本地证据相关度评分、Provider 调用错误提示、Gemini prompt 口径和历史分析对比入口。

已完成：

- `/analyze` evidence scoring 从 v1 关键词/优先级粗打分升级为 v2 多因子规则评分。
- 候选证据上限从 25 条扩展到 40 条，但默认仍只勾选前 10 条。
- 证据预览、分析详情侧栏和 Prompt 中都展示或携带 v2 评分理由。
- Provider 错误提示改为中文可行动文案。
- Gemini/Provider prompt 明确 `news_driven`、`macro_sentiment`、`technical_breakout`、`unclear` 的判定标准。
- Prompt 要求证据充分时优先输出 4-8 条不同传导链 catalysts，减少 Gemini Flash 过度压缩。
- 历史分析页右上角“对比”按钮改为跟随勾选状态，选满两条才可用，并携带 ids 进入 `/analyze/compare`。
- 新增只读回测脚本 `scripts/backtest_evidence_scoring.py`。

## v2 评分模型

当前 v2 使用可解释规则，不是黑箱训练模型。

主要加分因子：

- `direct_asset`：直接命中分析标的。
- `macro_liquidity`：美联储、利率、美元、收益率、非农、就业、通胀、流动性等。
- `geo_energy`：伊朗、以色列、霍尔木兹、制裁、战争、油价、能源等。
- `causal_language`：预期、概率、远超预期、风险偏好、避险、走强、下跌等因果词。
- `event_quality`：公布、录得、强于预期、低于预期、概率等数据或预期差信号。
- `time_proximity`：只在已有实质命中时增强贴近窗口的新闻，不让纯时间接近的无关消息入选。
- `priority`：保留 T3/T2 权重，但不能单独把分数顶满。

主要降权因子：

- 汇总、预告、每日、一览、夜盘要闻等设置更重降权和分数上限。
- “整理”类轻度降权。
- 广告、开户、直播、订阅等噪声降权。
- 信息量过短降权。
- 同主题重复新闻在排序前做轻微降权。

显示分数使用 `SCORE_SCALE = 120` 做降温，避免大量 `1.00` 造成“满分泛滥”误解。

## 回测结果

回测脚本：

```bash
.venv/bin/python scripts/backtest_evidence_scoring.py
.venv/bin/python scripts/backtest_evidence_scoring.py --top-k 5 --threshold 0.7
.venv/bin/python scripts/backtest_evidence_scoring.py --top-k 8 --threshold 0.7
.venv/bin/python scripts/backtest_evidence_scoring.py --top-k 10 --threshold 0.8
```

最近一次 `top-k=10, threshold=0.7`：

- eligible runs：14
- v1 precision：0.264
- v1 recall：0.787
- v1 hits：2.64
- v2 precision：0.300
- v2 recall：0.890
- v2 hits：3.00

结论：

- v2 在历史 LLM 高置信证据召回上明显优于 v1。
- v2 仍是弱标签回测，标签来自过往模型回答，不应当视为真实市场因果真值。
- 样本量仍偏小，后续应继续积累 Gemini / ChatGPT / GLM 对同一窗口的对比样本。

## Provider 与 Gemini 观察

用户真实试用中观察到：

- Gemini 2.5 Flash 能成功生成结构化 JSON。
- Gemini Flash 倾向压缩 catalysts 数量，常只输出 3-4 条；已通过 prompt 要求证据充分时输出 4-8 条不同传导链。
- Gemini 与手工 ChatGPT Plus 可能对 `news_driven` / `macro_sentiment` 判定不同；已将判定标准写入 prompt。
- Provider 失败时现在保留草稿，不保存为 done。

已确认一个失败草稿：

- `ar_20260606_155201_94705f`
- 状态：`draft`
- 证据：`10 / 16`
- Prompt 长度：约 4542 字
- answer_text：空

当前 provider 错误只通过 URL query 临时展示，没有持久化到 `dashboard_analysis.sqlite3`。如果要复盘失败原因，下一步可以考虑给分析库加 `provider_error` / `provider_error_at` 字段。

## 验证

已执行：

```bash
.venv/bin/python -m pytest tests/test_dashboard_analysis.py -q
.venv/bin/python scripts/backtest_evidence_scoring.py --top-k 10 --threshold 0.7
.venv/bin/python -m pytest -q
git diff --check
.venv/bin/python -m py_compile dashboard/evidence.py dashboard/manual_ai.py dashboard/analysis_db.py dashboard/app.py scripts/backtest_evidence_scoring.py
```

结果：

- `tests/test_dashboard_analysis.py`：44 passed
- 全量 pytest：185 passed
- `git diff --check`：通过
- `py_compile`：通过
- 临时 `8766` smoke test：证据预览 40 条候选正常渲染，历史页顶部对比按钮不再裸跳空页。

## 明确未做

- 未请求金十 REST。
- 未修改 WebSocket / REST / Telegram 采集和发送逻辑。
- 未写业务历史库。
- 未自动重发 Telegram unknown_timeout。
- 未引入 embedding、向量检索或真实机器学习训练。
- 未持久化 provider 调用失败原因。
- 未接 GLM Flash 做真实 A/B。

## 当前遗留问题

建议下一步按优先级处理：

1. Provider 失败原因持久化：把 `finishReason`、invalid JSON、timeout、max length 等错误写入分析库，详情页可见，方便复盘。
2. Gemini / ChatGPT / GLM 同窗 A/B：同一 evidence packet 分别跑不同 provider，对比 catalysts 覆盖、judgement、置信度和 JSON 稳定性。
3. v2 评分继续校准：随着新样本增加，定期跑 `scripts/backtest_evidence_scoring.py`，观察 top5/top8/top10 的召回和误排。
4. `/analyze` Prompt 长度守卫：当已选证据或 prompt 长度接近 provider 限制时，页面给出更强提醒或自动建议减少证据。
5. 分析库草稿清理：用户试用中会留下失败/未回填草稿，可增加只读筛选或显式删除。

## 下一 session 建议

推荐先做 P0：

- Provider 失败原因持久化。
- `/analyze` Prompt 长度与 selected evidence 风险提示增强。

推荐模型：

- `GPT-5.5 中`：Provider 失败原因持久化、Prompt 长度守卫、v2 评分小幅校准、GLM Flash 最小接入试用。
- `GPT-5.5 高`：embedding/向量相似度、历史样本评测框架、Provider/Vision 深度集成、任何 WebSocket/REST/Telegram/SQLite 游标逻辑。

