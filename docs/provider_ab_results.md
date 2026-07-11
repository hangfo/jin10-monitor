# Provider A/B Batch Summary

更新时间：2026-06-26 21:19:01

- 扫描 run 数：3
- Provider 结果数：6
- 边界：只汇总已有导出文件，不调用 Provider API，不写 analysis_runs，不请求金十 REST，不触发 Telegram。

| run_id | asset | provider | model | status | judgement | confidence | catalysts | missing | duplicate_news_id | JSON | elapsed | tokens | comparison | error |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ar_20260606_003632_12fb68 | ETH | gemini | gemini:gemini-2.5-flash | done | news_driven | 0.9 | 5 | 0 | - | yes | 6.74 | in=6805 out=1221 | yes | - |
| ar_20260606_003632_12fb68 | ETH | compatible | GLM:glm-4.7-flash | done | macro_sentiment | 0.8 | 3 | 3 | - | yes | 66.98 | in=5929 out=492 | yes | - |
| ar_20260609_222743_1c996d | ETH | gemini | gemini:gemini-2.5-flash | done | macro_sentiment | 0.78 | 2 | 0 | - | yes | 3.48 | in=2160 out=542 | yes | - |
| ar_20260609_222743_1c996d | ETH | compatible | GLM:glm-4.7-flash | done | macro_sentiment | 0.55 | 4 | 3 | - | yes | 48.61 | in=1999 out=628 | yes | - |
| ar_20260625_052808_8607df | ETH | gemini | gemini:gemini-2.5-flash | done | macro_sentiment | 0.7 | 5 | 0 | - | yes | 6.0 | in=2806 out=1087 | yes | - |
| ar_20260625_052808_8607df | ETH | compatible | GLM:glm-4.7-flash | done | macro_sentiment | 0.55 | 5 | 4 | - | yes | 84.2 | in=2546 out=795 | yes | - |

## Run 摘要

| run_id | question | providers | comparison.md |
| --- | --- | --- | --- |
| ar_20260606_003632_12fb68 | ETH刚才为什么跌了 | gemini, compatible | yes |
| ar_20260609_222743_1c996d | ETH刚才为什么跌了 | gemini, compatible | yes |
| ar_20260625_052808_8607df | ETH刚才为什么涨了 | gemini, compatible | yes |

> 自动汇总只记录客观字段和模型自报结构；关键催化覆盖、缺失证据是否合理、最终 pass/watch/fail 仍需人工复核。

## 2026-07-11 新 Prompt 方向冲突复测

边界：本轮使用当前 `provider_system_prompt(...)` 对两个固定 packet 执行 Gemini + GLM/compatible 同窗复测；共发起 5 次免费 API 请求，其中 4 次得到成功输出，另有 1 次 GLM 读取超时后仅重跑该失败项。结果只写 ignored 的 `exports/provider_ab_prompt_retest_20260711/`，没有写 `analysis_runs`、业务历史库，没有请求金十 REST 或触发 Telegram。

| run_id | 场景 | Provider | model | 初次结果 | 最终结果 | judgement | confidence | JSON | 人工结论 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `ar_20260607_091419_4d265c` | ETH 上涨，证据为霍尔木兹冲突/无人机风险 | Gemini | `gemini:gemini-2.5-flash` | done / 5.0s | done | `unclear` | 0.4 | yes | `watch`：分类正确，但 summary 的“主要受……影响”仍带确定性因果色彩。 |
| `ar_20260607_091419_4d265c` | 同上 | compatible | `GLM:glm-4.7-flash` | done / 5.0s | done | `unclear` | 0.4 | yes | `pass/watch`：缺失证据合理，内部口径一致。 |
| `ar_20260711_192040_1ecbdd` | ETH 上涨，证据主要为地缘紧张与加息分歧 | Gemini | `gemini:gemini-2.5-flash` | done / 6.2s | done | `unclear` | 0.2 | yes | `pass`：没有强行解释上涨，直接指出行情证据缺口。 |
| `ar_20260711_192040_1ecbdd` | 同上 | compatible | `GLM:glm-4.7-flash` | failed / 121.5s timeout | retry done / 6.5s | `macro_sentiment` | 0.4 | yes after retry | `watch`：内容合格，无 `[#news_id]` 占位符；继续观察偶发超时。 |

对抗性检查：

- 成功输出均可直接解析为 JSON。
- catalyst 只引用已选证据，没有重复或越界 `news_id`。
- GLM 使用真实消息 ID，没有输出 `[#news_id]` 字面占位符。
- 两个 Provider 都列出了成交量、订单流、清算、资金费率或 BTC/ETH 联动等缺失市场证据。

归因限制：

- 本轮证明的是“当前 Prompt 下的新执行能够在方向冲突时降级”，不是旧 Prompt 与新 Prompt 的同 packet 因果对照。
- 两个样本都是方向冲突场景，尚缺强方向一致样本来验证新规则不会过度压低合理的 `news_driven`。
- `ar_20260711_192040_1ecbdd` 的结构化行情上下文因 Binance `HTTP 451` 不可用，不能把模型结论视为结合完整价格/成交量数据后的判断。
- 在新自然样本出现前，不据此继续修改 judgement Prompt 或 evidence scoring。
