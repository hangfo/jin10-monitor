# 066 - Provider judgement Prompt 口径调整

更新时间：2026-06-26 01:03（Asia/Shanghai）

当前分支：`main`

## 背景

本轮接续 `065-2026-06-26-roadmap-decisions-backlog-handoff.md` 的 P0 建议，处理 Provider A/B scorecard 暴露出的两个问题：

- ETH 上涨样本中，证据主要是美元 / 加息偏利空，Provider 仍容易给出偏确定的宏观归因。
- GLM/compatible 输出中曾出现 `[#news_id]` 字面占位符，而不是实际消息 ID。

本轮只调整 Prompt 约束和测试，不重新调用 Provider API，不写 `analysis_runs`，不触碰采集或投递链路。

## 修改内容

### 固定分析 Prompt

`dashboard/manual_ai.py` 的 `SYSTEM_INSTRUCTION` 增加规则：

- 当新闻证据主方向与价格涨跌方向明显相反；
- 且缺少成交量、订单流、清算、资金费率或 BTC/ETH 联动等直接市场证据；
- 必须优先判为 `unclear` 或低置信 `macro_sentiment`；
- 并在 `missing_evidence` 写明缺口；
- 不得强行解释为确定性上涨 / 下跌原因。

### Provider wrapper Prompt

`dashboard/app.py` 的 `provider_system_prompt()` 增加同类约束，使 Dashboard 后台 Provider 调用与手工 Prompt 口径一致。

GLM 专用补充约束新增：

- `impact_path` 末尾必须使用真实消息 ID，例如 `[#20260624195807735800]`。
- 不得输出 `[#news_id]` 字面占位符。

### 测试

`tests/test_dashboard_analysis.py` 增加断言，保护：

- 手工 Prompt 包含“证据方向与价格方向冲突时降级”的规则。
- Provider wrapper Prompt 包含 `unclear` / 低置信 `macro_sentiment` 规则。
- GLM 专用 Prompt 包含禁止 `[#news_id]` 占位符的约束。

## 边界确认

未改：

- WebSocket 实时主路。
- REST 补拉策略。
- Telegram 发送、健康心跳或 `delivery_log`。
- `data/history.sqlite3` 业务历史库。
- `data/dashboard_analysis.sqlite3` 与 `analysis_runs` 保存逻辑。
- Dashboard Provider 后台保存状态机。
- Provider adapter 默认参数。
- A/B CLI 行为。

未调用：

- Provider API。
- 金十 REST。
- Telegram API。
- 本地 Dashboard 写入端点。

## 验证结果

已运行：

```bash
.venv/bin/python -m py_compile dashboard/app.py dashboard/manual_ai.py
.venv/bin/python -m pytest tests/test_dashboard_analysis.py -q
.venv/bin/python -m pytest -q
git diff --check
```

结果：

- `tests/test_dashboard_analysis.py`：`74 passed`
- 全量 pytest：`265 passed`
- `git diff --check`：通过

## 风险评估

风险等级：中。

原因：

- 本轮不影响采集、投递、历史库或启动方式。
- 但会影响 Provider 输出 judgement 口径，尤其是行情方向与新闻方向冲突时，模型更可能输出 `unclear` 或低置信 `macro_sentiment`。

预期收益：

- 减少“新闻证据偏利空但 ETH 上涨”这类样本中的强行归因。
- 让 `missing_evidence` 更明确暴露成交量、订单流、清算、资金费率和联动数据缺口。
- 降低 GLM 输出 `[#news_id]` 占位符导致链接不可用的概率。

## 下一步建议

P0：

1. 用后续真实 Provider A/B 样本观察新 Prompt 是否减少方向冲突场景的强归因。
2. 如果暂不想消耗 Provider API，先回填 `exports/provider_ab_after_fix/` 的人工 scorecard，总结为 Markdown。

P1：

1. 做 `/system` 日志 level 筛选 UI，复用已存在的 `/api/system/log-events?level=...`。
2. 给早期导出目录补生成 `comparison.md`，前提是不重新调用 Provider API。

模型建议：

- 观察 / 回填 scorecard / 做只读汇总：`GPT-5.5 中`。
- 再次修改 Provider Prompt、evidence scoring 或 Dashboard compare 体验：`GPT-5.5 高`。

## 下一 session 提示词

```text
继续 /Users/rich/jin10-monitor。

先读取：
1. AGENTS.md
2. CHANGELOG.md
3. docs/status/066-2026-06-26-provider-judgement-prompt-handoff.md
4. docs/status/065-2026-06-26-roadmap-decisions-backlog-handoff.md
5. docs/ROADMAP.md
6. docs/DECISIONS.md
7. docs/BACKLOG.md
8. docs/design/008-provider-ab-evaluation-plan.md

当前边界：
- Provider judgement Prompt 已调整：证据方向与行情方向明显冲突且缺少直接市场证据时，优先 unclear / 低置信 macro_sentiment，并写 missing_evidence。
- GLM 专用 Prompt 已约束不得输出 `[#news_id]` 字面占位符。
- 不写 analysis_runs、不写业务历史库、不请求金十 REST、不触发 Telegram。
- WebSocket / REST / Telegram / Dashboard Provider 保存逻辑未改。
- 不要自动调用新的 Provider API，除非我明确要求。

下一步优先：
1. 若要继续验证质量，用 GPT-5.5 中整理 scorecard 或只读汇总。
2. 若要再次修改 Provider Prompt、evidence scoring 或 Dashboard compare 体验，用 GPT-5.5 高。
3. 可选做 `/system` 日志 level 筛选 UI，属于 GPT-5.5 中。
```
