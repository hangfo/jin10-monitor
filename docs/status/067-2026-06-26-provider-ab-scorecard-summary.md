# 067 - Provider A/B scorecard 汇总

更新时间：2026-06-26 01:08（Asia/Shanghai）

当前分支：`main`

## 背景

本轮只读整理 `exports/provider_ab_after_fix/` 下 3 个 Provider A/B 样本，目标是把 Gemini vs GLM 的人工 scorecard 结论落到 Git 可追踪文档中。

重要边界：

- 本轮没有重新调用 Provider API。
- 没有修改 `exports/` 下的原始导出文件，因为 `exports/` 被 `.gitignore` 忽略。
- 没有写 `analysis_runs`，没有写业务历史库，没有请求金十 REST，没有触发 Telegram。
- 本文复盘的是 `bfec2bf` Prompt 调整前已经生成的结果；不能直接视为新 Prompt 复测结论。

## 总体结论

3 个样本中，Gemini 与 GLM/compatible 均保持 JSON 可解析，未发现重复 `news_id`。

人工质量判断：

| run_id | 场景 | Gemini | GLM / compatible | 结论 |
| --- | --- | --- | --- | --- |
| `ar_20260606_003632_12fb68` | ETH 下跌，强非农 / 加息预期 | `pass` | `watch/pass` | Gemini 对强单一宏观数据更完整，GLM 主线正确但更保守。 |
| `ar_20260609_222743_1c996d` | ETH 下跌，CPI / 能源 / 风险偏好 | `pass` | `watch` | Gemini 聚焦 CPI 主线更干净；GLM 扩展到油价和伊朗谈判，部分链条偏弱。 |
| `ar_20260625_052808_8607df` | ETH 上涨，但证据多为美元 / 加息偏利空 | `watch` | `watch/fail` | 两者都暴露“证据方向与行情方向冲突”问题；GLM 另有 `[#news_id]` 占位符风险。 |

当前排序建议：

1. Gemini：作为当前首选 Provider，速度快，JSON 稳定，前两个样本质量较好。
2. GLM / compatible：适合作第二意见 Provider，但需要重点观察弱链条、方向冲突和引用格式。
3. ChatGPT Plus：本轮未重新纳入 API A/B；如果人工粘贴对比明显优于 API Provider，再考虑强化手工回填体验。

## 单样本复盘

### `ar_20260606_003632_12fb68`

固定输入：

- 问题：`ETH刚才为什么跌了`
- 窗口：`2026-06-05 20:35:00` - `2026-06-06 00:35:00`
- 证据：`25/25` selected
- 场景：美国 5 月非农大超预期，加息概率上升，美元走强，ETH 下跌。

Gemini：

- judgement：`news_driven`
- overall_confidence：`0.9`
- catalysts：5 条
- duplicate `news_id`：无
- missing_evidence：空
- 人工结论：`pass`

理由：

- 命中非农超预期、加息概率上升、美元走强和黄金下跌这些关键传导。
- `news_driven` 合理，因为一组高度同源的强宏观数据足以解释主要波动。
- missing_evidence 为空可接受；该样本新闻证据本身已经足够强。

GLM / compatible：

- judgement：`macro_sentiment`
- overall_confidence：`0.8`
- catalysts：3 条
- duplicate `news_id`：无
- missing_evidence：`ETHUSDT 1分钟成交量数据`、`ETH资金费率变化`、`BTC与ETH的联动性分析`
- 人工结论：`watch/pass`

理由：

- 主线正确，但覆盖少于 Gemini。
- missing_evidence 合理；不过在该强新闻样本中，GLM 略偏保守。

### `ar_20260609_222743_1c996d`

固定输入：

- 问题：`ETH刚才为什么跌了`
- 窗口：`2026-06-09 22:12:00` - `2026-06-09 22:27:00`
- 证据：`7/38` selected
- 场景：CPI 预期、能源通胀和风险偏好压制，ETH 下跌。

Gemini：

- judgement：`macro_sentiment`
- overall_confidence：`0.78`
- catalysts：2 条
- duplicate `news_id`：无
- missing_evidence：空
- 人工结论：`pass`

理由：

- 聚焦 CPI 高企和美联储紧缩预期，传导链干净。
- `macro_sentiment` 合理，因为主要不是单条 ETH 直接新闻，而是宏观风险偏好共同传导。

GLM / compatible：

- judgement：`macro_sentiment`
- overall_confidence：`0.55`
- catalysts：4 条
- duplicate `news_id`：无
- missing_evidence：`ETHUSDT 1分钟成交量数据`、`ETH资金费率变化`、`BTC与ETH的联动性数据`
- 人工结论：`watch`

理由：

- CPI 主线合理，missing_evidence 也合理。
- 但把原油下跌、伊朗谈判缓和也直接解释为 ETH 下跌，链条偏弱，适合作第二意见而不是直接保存。

### `ar_20260625_052808_8607df`

固定输入：

- 问题：`ETH刚才为什么涨了`
- 窗口：`2026-06-24 19:03:00` - `2026-06-24 20:03:00`
- 证据：`10/40` selected
- 场景：ETH 上涨，但所选证据多为美元 / 加息 / 贵金属偏利空。

Gemini：

- judgement：`macro_sentiment`
- overall_confidence：`0.7`
- catalysts：5 条
- duplicate `news_id`：无
- missing_evidence：空
- 人工结论：`watch`

理由：

- 能覆盖主要宏观证据，但 summary 出现方向张力：一边说 ETH 上涨，一边说加息和美元走强对风险资产构成压力。
- missing_evidence 为空不理想；更合理的输出应提示缺少 ETH/BTC 联动、成交量、订单流、清算或资金费率数据。
- 该样本正是 `066` Prompt 调整要解决的目标场景。

GLM / compatible：

- judgement：`macro_sentiment`
- overall_confidence：`0.55`
- catalysts：5 条
- duplicate `news_id`：无
- missing_evidence：`ETHUSDT 1分钟成交量数据`、`ETH资金费率变化`、`BTC与ETH的同步联动性`、`ETH大额订单流数据`
- 人工结论：`watch/fail`

理由：

- GLM 能指出宏观利空与 ETH 上涨不一致，并补出更合理的 missing_evidence。
- 但部分 catalyst 把宏观压力和 ETH 逆势上涨混在同一条链上，解释不够稳。
- 原始输出中曾出现 `[#news_id]` 字面占位符风险，已在 `066` Prompt 中补约束。

## 对 `066` Prompt 调整的观察口径

后续如果复测新 Prompt，应重点观察：

1. 方向冲突样本是否从偏确定的 `macro_sentiment` 降为 `unclear` 或低置信 `macro_sentiment`。
2. `missing_evidence` 是否明确写出成交量、订单流、清算、资金费率和 BTC/ETH 联动缺口。
3. GLM 的 `impact_path` 是否使用真实 `[#<news_id>]`，不再输出 `[#news_id]`。
4. Gemini 是否仍能在强非农样本中保留合理的 `news_driven`，不要被新规则过度压成 `unclear`。

## 下一步建议

P0：

1. 暂不继续修改 Prompt。
2. 先用后续真实样本观察 `066` Prompt 是否改善方向冲突场景。
3. 如果不想消耗 Provider API，可以先做旧导出目录的 `comparison.md` 补生成或 A/B 批量汇总 Markdown。

P1：

1. 做 `/system` 日志 level 筛选 UI，复用现有 `/api/system/log-events?level=...`。
2. 如果 A/B 样本扩大到 5 个以上，再做批量总览，而不是自动投票。

模型建议：

- 只读汇总、scorecard 整理、`/system` 小 UI：`GPT-5.5 中`。
- 再次修改 Provider Prompt、evidence scoring 或 Dashboard compare 体验：`GPT-5.5 高`。

