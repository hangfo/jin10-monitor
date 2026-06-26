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
