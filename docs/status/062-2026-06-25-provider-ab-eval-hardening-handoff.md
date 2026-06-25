# 062 - Provider A/B 真实调用收口与稳定性修复

更新时间：2026-06-25 06:10（Asia/Shanghai）

当前分支：`main`

## 背景

本轮接续 `061-2026-06-25-provider-ab-eval-tool-handoff.md`，先用 `scripts/run_ab_eval.py` 对固定 evidence packet 做 Gemini + GLM 小批量真实 A/B 调用，再根据真实失败模式收稳 Provider 配置和 Prompt 边界。

目标仍不是自动替代人工质量判断，而是让 A/B 工具更可靠地完成客观字段记录：耗时、Token、finish reason、JSON 稳定性、原始输出和错误。

## 真实 A/B 发现

使用当前 `.env` 中已配置的 Gemini 与 GLM/智谱 compatible Provider，第一轮跑了 5 个 `analysis_runs.id`：

```text
ar_20260625_052808_8607df
ar_20260609_030615_d385f2
ar_20260523_173838_6267c8
ar_20260609_222743_1c996d
ar_20260606_003632_12fb68
```

发现的问题：

- `scripts/run_ab_eval.py` 直接运行时没有自动加载仓库 `.env`，dry-run 会误判 Provider 未配置。
- Gemini 2.5 Flash 在中长 Prompt 上出现 `finishReason=MAX_TOKENS`。
- GLM 4.7 Flash 有一次输出打满 `4096` completion tokens，但 `content` 为空，错误摘要显示 `reasoning_content` 占用了输出。
- GLM 另一次 raw 输出接近 JSON，但 `caveat` 字段写成裸中文文本，导致 JSON 不可解析。
- 未发现重复 `news_id`。

## 已修复

### A/B CLI

`scripts/run_ab_eval.py` 现在会自动读取仓库 `.env`，与 `run_dashboard.py` 的 Provider 配置口径一致；shell 中已导出的环境变量仍优先。

CLI 进度输出增加实时 flush，真实调用时可以看到当前跑到哪个 `run_id` / Provider，避免长批次看起来像卡死。

### Gemini

`dashboard/providers/gemini_provider.py` 默认：

```text
GEMINI_MAX_TOKENS=8192
GEMINI_THINKING_BUDGET=0
```

如果用户在 `.env` 或 shell 中显式设置，仍以用户配置为准。

这次复测中，之前 `MAX_TOKENS` 的两个样本均恢复为稳定 JSON：

- `ar_20260625_052808_8607df`：Gemini `6.0s json=yes`
- `ar_20260606_003632_12fb68`：Gemini `6.7s json=yes`

### GLM / OpenAI-compatible

`dashboard/providers/compatible_provider.py` 对 GLM/智谱 compatible 自动增加：

```json
{"thinking": {"type": "disabled"}}
```

该参数只在模型名、base URL 或 label 看起来是 GLM/智谱时添加，避免影响 DeepSeek 或其它 OpenAI-compatible Provider。

GLM 默认 max tokens 对 GLM/智谱模型提高到 `8192`；用户显式配置 `COMPAT_LLM_MAX_TOKENS` 时仍以用户配置为准。

### Provider system prompt

`dashboard/app.py` 的 `provider_system_prompt()` 增强：

- 所有 Provider 都明确“只输出一个合法 JSON object”。
- 明确禁止前言、解释、Markdown 代码块和思考过程。
- 明确所有字符串值必须用双引号，特别是 `caveat`。
- GLM 专用约束补充“不要输出 `reasoning_content` / `<think>`”，并强调 `caveat` 必须是 JSON 字符串。

## 复测结果

修复后用 3 个最容易暴露问题的样本做真实复测：

```bash
.venv/bin/python scripts/run_ab_eval.py \
  --run-ids ar_20260625_052808_8607df ar_20260609_222743_1c996d ar_20260606_003632_12fb68 \
  --providers gemini compatible \
  --output-root exports/provider_ab_after_fix \
  --execute --yes
```

结果：

```text
ar_20260625_052808_8607df  gemini ok 6.0s json=Y      compatible ok 84.2s json=Y
ar_20260609_222743_1c996d  gemini ok 3.5s json=Y      compatible ok 48.6s json=Y
ar_20260606_003632_12fb68  gemini ok 6.7s json=Y      compatible ok 67.0s json=Y
```

质量观察：

- 修复后 6/6 真实调用均成功生成可解析 JSON。
- GLM output token 明显下降，之前容易打满输出的问题被缓解。
- 3 个样本均未发现重复 `news_id`。
- Gemini 仍比 GLM 快很多。
- Gemini 在强非农样本上更倾向 `news_driven`，GLM 更倾向 `macro_sentiment`；是否调整 judgement 口径仍需人工结合行情图和 scorecard 判断。

## 边界确认

未改：

- WebSocket 实时主路。
- REST 补拉策略。
- Telegram 发送或健康心跳。
- `data/history.sqlite3` 业务历史库。
- `data/dashboard_analysis.sqlite3` 的 `analysis_runs` 保存逻辑。
- Dashboard `/analyze` 页面交互和后台保存状态机。
- OpenAI / Anthropic 默认启用策略。

本轮只修改 Provider A/B CLI、Provider adapter 默认参数、Provider system prompt、示例配置、设计文档和测试。

## 验证结果

已运行：

```bash
.venv/bin/python -m py_compile scripts/run_ab_eval.py dashboard/app.py dashboard/providers/gemini_provider.py dashboard/providers/compatible_provider.py
.venv/bin/python -m pytest tests/test_run_ab_eval.py -q
.venv/bin/python -m pytest tests/test_dashboard_analysis.py -q
.venv/bin/python -m pytest tests/test_run_ab_eval.py tests/test_dashboard_analysis.py -q
.venv/bin/python -m pytest -q
git diff --check
```

结果：

- `tests/test_run_ab_eval.py`：`16 passed`
- `tests/test_dashboard_analysis.py`：`70 passed`
- 合并 targeted：`86 passed`
- 全量 pytest：`249 passed`
- `git diff --check`：通过

## 下一步建议

P0：

1. 人工打开 `exports/provider_ab_after_fix/<run_id>/ab_scorecard.md`，补 `key_catalysts_hit`、`duplicate_news_id`、`missing_evidence_reasonable` 和最终 `pass/watch/fail`。
2. 用这 3 个修复后样本判断 Gemini vs GLM 的 judgement 口径差异是否需要 Prompt 微调。

P1：

1. 如果人工确认 Gemini 对强宏观样本过度 `news_driven`，再小改 Prompt 中 `news_driven` vs `macro_sentiment` 的判定口径。
2. 如果 GLM 仍偏保守但 JSON 稳定，可以先保留为第二意见 Provider，不急着扩 scoring。

P2：

1. 考虑给 `scripts/run_ab_eval.py` 增加 `--skip-existing`，避免复测时重复调用已经成功的 Provider。
2. 考虑在 `ab_scorecard.md` 自动区块加入 baseline vs after-fix 的简短对照，但不要做复杂投票系统。

## 下一 session 提示词

```text
继续 /Users/rich/jin10-monitor。

先读取 AGENTS.md、CHANGELOG.md、docs/design/008-provider-ab-evaluation-plan.md，以及 docs/status/062-2026-06-25-provider-ab-eval-hardening-handoff.md。

当前边界：
- Provider A/B CLI 已会自动读取 .env，真实调用仍必须 --execute --yes。
- Gemini 默认关闭 thinking，并提高 JSON 输出上限；GLM/智谱 compatible 默认 thinking.type=disabled。
- 修复后 exports/provider_ab_after_fix/ 中 3 个问题样本 Gemini + GLM 共 6 次真实调用均 json=yes。
- 结果只写 exports/provider_ab*/<run_id>/，不写 analysis_runs、不写业务历史库、不请求金十 REST、不触发 Telegram。
- WebSocket / REST / Telegram / Dashboard 保存逻辑未改。

下一步优先：
1. 人工填写 exports/provider_ab_after_fix/<run_id>/ab_scorecard.md 的主观字段。
2. 判断 Gemini vs GLM 的 judgement 差异是否需要小改 Prompt。
3. 如果要继续代码优化，优先考虑 scripts/run_ab_eval.py --skip-existing，避免复测重复消耗免费额度。

模型建议：
- 只整理 scorecard 和写结论：GPT-5.5 中。
- 修改 Provider prompt、judgement 口径或 A/B CLI 行为：GPT-5.5 高。
```
