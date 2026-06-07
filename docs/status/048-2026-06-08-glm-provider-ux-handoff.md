更新时间：2026-06-08 01:33（Asia/Shanghai）

# 048 - GLM Provider A/B 与分析详情 UX 交接

## 本次状态

当前分支仍为 `main`。本轮工作从 `/analyze` Provider A/B 试跑继续，重点验证 GLM Flash 在同一 evidence packet 下的表现，并收口 Provider 错误诊断、耗时显示、judgement 中文展示和分析详情页可读性。

已完成：

- 接入并验证 `GLM:glm-4.7-flash` 作为 OpenAI-compatible Provider。
- Provider 调用成功和失败都会记录 `provider_elapsed_ms`，详情页和历史页均显示耗时。
- Provider 失败会继续保留草稿，不保存为已完成；错误重定向会保留本次选择的 provider。
- 不可解析 JSON 错误增加模型标签、耗时和原始返回短预览，便于区分 Gemini/GLM 的解析失败。
- 仅对 GLM/OpenAI-compatible 且模型名包含 `glm` 的调用追加弱证据约束，不影响 Gemini、OpenAI、Anthropic 或手动 ChatGPT Prompt。
- GLM 专用约束要求正文使用中文；单条 indirect/mixed 弱证据优先判为 `unclear`，不得高置信强行归因。
- GLM 对单条 mixed 证据给出高置信 `news_driven` 时，详情页显示本地复核提示。
- 详情页、历史页、对比页将 judgement 枚举展示为中文：`新闻驱动`、`宏观情绪`、`技术突破`、`无法确认`。
- 详情页顶部元信息改为紧凑两行摘要，`分析 ID` 降为辅助信息；AI 结论句突出显示为醒目的“结论”块。
- 对比页补充说明：`missing_evidence` 来自各次模型原始输出，同一 Prompt 下差异代表模型复盘侧重点不同，不代表本地 evidence packet 改变。

## GLM A/B 观察

用户用同一 ETH 窗口、同一 evidence packet 连续试跑 GLM 后，最新两次结果符合当前预期：

- judgement 均为 `unclear`，页面展示为 `无法确认`。
- overall confidence 分别约为 `20%` 和 `30%`。
- 未再把单条地缘政治新闻强行判为 `news_driven`。
- 输出理由能指出：地缘冲突与 ETH 上涨方向不完全一致，缺少成交量、资金费率、BTC 联动或订单流等验证。

这说明 GLM 专用弱证据约束已起作用。当前不建议继续大改评分模型。

## GLM 耗时结论

GLM 耗时波动明显：

- 同一 Prompt 约 `2089` 字。
- 相近回答长度约 `515-552` 字。
- 实测耗时可从约 `26.7s` 波动到 `67.4s`。

这更像 GLM 服务端排队或推理波动，不像本地逻辑冲突。

已试过将 `.env` 中 `COMPAT_LLM_MAX_TOKENS` 从 `4096` 降到 `1400`，结果出现：

```text
compatible provider returned an empty response; elapsed=15.0s
```

该记录仍保持草稿，未污染已完成分析。随后已将本地 `.env` 恢复：

```bash
COMPAT_LLM_MAX_TOKENS=4096
COMPAT_LLM_TEMPERATURE=0
PROVIDER_TIMEOUT_SECONDS=90
```

结论：不要用压低 `COMPAT_LLM_MAX_TOKENS` 的方式优化 GLM 耗时；短期优先保持成功率。

## 验证

已执行：

```bash
.venv/bin/python -m pytest tests/test_dashboard_analysis.py -q
.venv/bin/python -m pytest -q
.venv/bin/python -m py_compile dashboard/app.py dashboard/manual_ai.py dashboard/analysis_db.py
git diff --check
```

结果：

- `tests/test_dashboard_analysis.py`：53 passed
- 全量 pytest：194 passed
- `py_compile`：通过
- `git diff --check`：通过

## 明确未做

- 未请求金十 REST。
- 未修改 WebSocket / REST / Telegram 采集或发送逻辑。
- 未写业务历史库。
- 未自动重发 Telegram unknown_timeout。
- 未把 GLM 设为主链路。
- 未引入 embedding、向量检索或自动评测框架。
- 未实现后台 Provider 调用或异步状态。
- 未提交 `exports/` 本地实验输出。

## 下一 session 建议

推荐下一步优先做 Provider 后台调用 / 异步状态，而不是继续调 GLM 参数：

1. Provider 调用提交后立即返回详情页或历史页，不让页面长时间阻塞。
2. 分析草稿增加 `running` 或等价本地状态，历史页显示“调用中”。
3. 前端轻量轮询或手动刷新，完成后展示结果，失败仍保留草稿和错误。
4. 避免后台任务写业务历史库；只写独立分析库。
5. 保持 Dashboard 只读诊断和分析侧车定位，不作为采集入口。

推荐模型：

- `GPT-5.5 中`：后台调用 UX、Provider 状态展示、历史筛选、轻量测试补齐。
- `GPT-5.5 高`：自动评测框架、embedding/向量相似度、深度 Provider/Vision 集成、WebSocket/REST/Telegram/SQLite 游标或外部源逻辑。

## 下一 session 可复制提示词

```text
继续 /Users/rich/jin10-monitor 项目。

先读取：
1. /Users/rich/jin10-monitor/AGENTS.md
2. /Users/rich/jin10-monitor/docs/status/048-2026-06-08-glm-provider-ux-handoff.md
3. /Users/rich/jin10-monitor/docs/status/047-2026-06-07-analyze-v3-provider-ux-handoff.md
4. /Users/rich/jin10-monitor/docs/design/007-provider-adapter-and-review-followup-plan.md
5. /Users/rich/jin10-monitor/docs/design/003-phase2b-phase3-spec.md

先执行：
git branch --show-current
git status
git pull --rebase
git log --oneline -8

当前结论：
- Provider Adapter 第一版已完成，支持 Anthropic、Gemini、OpenAI-compatible、OpenAI；默认无 key 不请求模型 API。
- /analyze 已完成 v3 默认证据选择，最多展示 40 条，默认只选高相关、低重复、非汇总预告证据。
- Provider 失败原因和耗时已持久化到独立分析库草稿；失败不会保存为已完成。
- GLM:glm-4.7-flash 已完成同窗试跑，弱证据约束已生效，单条地缘 mixed 证据会回到“无法确认 / 低置信度”。
- GLM 耗时波动较大，已确认不应通过降低 COMPAT_LLM_MAX_TOKENS 到 1400 优化；本地 .env 已恢复 COMPAT_LLM_MAX_TOKENS=4096。
- 详情页、历史页、对比页已显示中文 judgement，详情页 AI 结论已突出显示。
- Dashboard 仍是本地只读诊断和分析侧车，不作为采集入口。
- 不请求金十 REST，不写业务历史库，不自动重发 Telegram unknown_timeout。

推荐下一步：
优先做 Provider 后台调用 / 异步状态：
1. 点击“调用并保存”后不要阻塞页面等待 GLM/Gemini 返回。
2. 草稿进入“调用中”状态，历史页和详情页显示耗时/开始时间/Provider。
3. 完成后保存结果，失败仍保留草稿和错误。
4. 保持只写独立分析库，不触碰业务历史库和采集链路。
5. 完成后跑 pytest、更新 CHANGELOG 和 handoff，再提交推送。

推荐模型：
- GPT-5.5 中：后台调用 UX、Provider 状态展示、历史筛选、轻量测试。
- GPT-5.5 高：自动评测框架、embedding/向量相似度、深度 Provider/Vision 集成、外部源或采集链路逻辑。
```
