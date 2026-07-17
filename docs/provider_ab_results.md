# Provider A/B Batch Summary

更新时间：2026-07-18 01:30（Asia/Shanghai）

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
- 真实调用发生时源码 HEAD 为 `71e361d`；`attempt_history.jsonl` 可复现性记录在后续 `5e70c0e` 才上线，因此本轮历史调用没有该文件，也不做事后伪造回填。下一轮调用开始才以逐 attempt 的 commit/hash 快照为审计依据。
- 在新自然样本出现前，不据此继续修改 judgement Prompt 或 evidence scoring。

## 2026-07-18 自然样本只读审计

边界：本轮只读检查 2026-07-11 既有手动测试之后保存到 `data/dashboard_analysis.sqlite3` 的自然样本；没有新调用 Provider、没有写 `analysis_runs` 或业务历史库、没有请求金十 REST，也没有触发 Telegram。

- 新增完成态 run：15 个。
- 自然窗口：5 个，每个窗口均包含 Gemini、GLM/compatible 和人工 ChatGPT Business 结果。
- 完整性：15/15 JSON 可解析，15/15 catalyst 只引用已选证据；未发现重复或越界 `news_id`，未发现 `[#news_id]` 字面占位符。

| 窗口 | 场景 | Gemini | GLM/compatible | 人工结果 | 审计结论 |
| --- | --- | --- | --- | --- | --- |
| `2026-07-11 22:20 ~ 23:20` | ETH 上涨，证据主方向偏空/混合 | `macro_sentiment 0.65` | `macro_sentiment 0.55` | `unclear 0.39` | 方向冲突样本，Provider 仍存在偏积极归因，记为 `watch`。 |
| `2026-07-14 20:20 ~ 22:20` | CPI 降温后 ETH 大涨 | `news_driven 0.85` | `macro_sentiment 0.60` | `news_driven 0.87` | 强方向一致样本；新规则没有过度压低 Gemini 的合理归因。 |
| `2026-07-15 20:30 ~ 21:30` | PPI 降温后 ETH 上涨 | `news_driven 0.80` | `macro_sentiment 0.50` | `news_driven 0.88` | 第二个强方向一致样本，但 GLM 继续系统性保守。 |
| `2026-07-16 15:55 ~ 16:55` | ETH 下跌，证据间接且混合 | `macro_sentiment 0.65` | `macro_sentiment 0.55` | `unclear 0.36` | 低证据质量样本，显示置信度与证据强度尚未稳定对齐。 |
| `2026-07-17 20:30 ~ 21:35` | 地缘升级、油价上涨与 ETH 下跌 | `macro_sentiment 0.80` | `macro_sentiment 0.40` | `news_driven 0.86` | 方向一致但 Provider 置信度跨度过大，适合做校准样本。 |

结论：等待的“方向冲突 + 强方向一致”自然样本对已经出现，但现有结果仍受 evidence packet 的消息数量、边缘消息组成和 Provider 风格影响。下一步优先设计确定性 evidence packet、证据集敏感度审计和保存后的置信度校准/质量标签；在这些非 Prompt 层机制能够量化问题前，不立即修改 judgement Prompt 或 evidence scoring。

## 2026-07-18 收敛与稳定性实现验收

边界：没有发起真实 Provider 调用，没有修改 judgement Prompt 或 evidence scoring 权重；只读扫描生产分析库，功能开发和迁移测试均在隔离 worktree / 临时库完成。

- 新建分析保存 evidence packet 与完整 Prompt 的 SHA-256；详情页可克隆冻结输入，对比页只有双指纹一致才认定为严格 A/B。
- 默认核心证据从最多 10 条收敛到最多 8 条，先覆盖不同主题再按原相关度顺序补齐；候选仍保留最多 40 条。
- Provider 原始置信度只作审计；本地证据质量分不读取该字段，方向冲突、内部多空冲突或 `unclear` 最高为 C。
- `/analyze/stability` 与 CLI 沿用保存答案做 Top-4/6/8 和单条剔除重算；它衡量证据依赖性，不等同于模型重新回答。

真实历史库只读结果：

| 范围 | 完成 run | 重复窗口 | 严格同输入窗口 | 稳定 | 需复核 | 脆弱 | 耗时 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 最近 50 条 | 50 | 10 | 0 | 11 | 2 | 37 | 约 0.06s |
| 2026-07-11 后本轮最新 15 条 | 15 | 5 | 0 | 6 | 1 | 8 | 包含在上项 |

解读：旧自然样本有助于发现方向和置信度问题，但没有任何一组同时满足证据与 Prompt 完全一致，不能据此精确归因 Provider。后续测试必须先建立一个冻结源 run，再分别克隆给 Gemini、GLM/compatible 和人工 ChatGPT；若只重新按同一时间窗口构建，晚到消息和人工选择仍会污染对照。
