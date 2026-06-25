更新时间：2026-06-25 21:17（Asia/Shanghai）

# 008 - Provider 同窗 A/B 评测计划

## 1. 目的

本文接续 `047-2026-06-07-analyze-v3-provider-ux-handoff.md`。

当前不继续大改 evidence scoring，而是先用同一批本地证据比较 Gemini、ChatGPT Plus 和 GLM Flash 的输出质量。

评测目标：

- 判断 Provider 是否能稳定生成可解析 JSON。
- 判断 catalysts 是否覆盖关键新闻。
- 判断是否重复拆分同一个 `news_id`。
- 判断 `judgement` 是否和人工直觉一致。
- 判断 `missing_evidence` 是否合理。
- 观察 Prompt 长度、耗时和失败模式。

## 2. 固定变量

每个 A/B 样本必须固定：

- 同一个 `analysis_runs.id`。
- 同一个时间窗口。
- 同一个 `evidence_packet_json`。
- 同一个 evidence 默认选择状态。
- 同一个行情开关状态。
- 同一个 `manual_prompt`。
- 同一个 Prompt 版本。

不同 Provider 之间不得增删证据、改写 Prompt 或临时补充外部新闻。

## 3. 样本选择

第一轮建议选择 3-5 个历史窗口：

- 一个加密资产直接新闻窗口。
- 一个宏观数据或利率/美元驱动窗口。
- 一个地缘或能源风险窗口。
- 一个混合窗口，用来观察模型是否乱归因。
- 一个证据较少或噪声较高窗口，用来观察 `missing_evidence`。

优先使用 `/analyze` v3 默认选择生成的草稿，因为它已经保留了完整 Prompt 和 evidence packet。

## 4. 导出方式

使用只读脚本导出固定实验包：

```bash
.venv/bin/python scripts/export_provider_ab_packet.py ar_xxx
```

默认输出到：

```text
exports/provider_ab/<run_id>/
```

文件：

- `prompt.md`：每个 Provider 使用的固定 Prompt。
- `evidence_packet.json`：固定 evidence reference。
- `ab_scorecard.md`：人工记录表。
- `metadata.json`：窗口、Prompt 版本、证据数和行情状态。

脚本只读 `data/dashboard_analysis.sqlite3`，不请求模型 API，不请求金十 REST，不写业务历史库，不触发 Telegram。

## 5. 受保护的自动评测方式

如果需要批量调用 Gemini / GLM 等 API Provider，可以使用受保护的自动评测脚本：

```bash
# 默认 dry-run：只导出/检查 packet 和 Provider 配置，不调用任何模型 API
.venv/bin/python scripts/run_ab_eval.py ar_xxx

# 批量 dry-run：适合先确认 3-5 个窗口和配置状态
.venv/bin/python scripts/run_ab_eval.py --run-ids ar_1 ar_2 ar_3 --providers gemini compatible

# 真实调用：必须同时提供 --execute 和 --yes
.venv/bin/python scripts/run_ab_eval.py --run-ids ar_1 ar_2 ar_3 --providers gemini compatible --execute --yes

# 断点续跑：跳过已有 done 结果，失败或缺失的 Provider 会重新调用
.venv/bin/python scripts/run_ab_eval.py --run-ids ar_1 ar_2 ar_3 --providers gemini compatible --execute --yes --skip-existing

# 慢模型或长 Prompt：临时覆盖本次 CLI 的 per-provider 超时
.venv/bin/python scripts/run_ab_eval.py ar_xxx --providers gemini compatible --execute --yes --timeout 120
```

安全边界：

- 默认不调用 Provider API；真实外部调用必须显式加 `--execute --yes`。
- CLI 会自动读取仓库 `.env`，与 `run_dashboard.py` 的 Provider 配置口径保持一致；shell 中已导出的环境变量优先级更高。
- 默认 Provider 为 `gemini compatible`，对应当前 Gemini + GLM/OpenAI-compatible 基线；`openai` / `anthropic` 只有显式指定才会尝试。
- 批量真实调用默认最多 5 个 `run_id`，超过需显式提高 `--max-runs`。
- `--skip-existing` 只跳过已有 `<provider>_result.json` 且 `status=done` 的 Provider；失败结果不会跳过，便于中断后续跑。
- `--timeout` 允许 `1-600` 秒，按 Provider 调用临时设置 `PROVIDER_TIMEOUT_SECONDS`，调用后恢复原环境变量。
- 脚本会自动补齐缺失的 `exports/provider_ab/<run_id>/` packet，但真实调用结果只写该导出目录：
  - `<provider>_raw.txt`
  - `<provider>_parsed.json`
  - `<provider>_result.json`
  - `eval_results.json`
  - `ab_scorecard.md` 自动结果区块
- 脚本复用 Dashboard 当前调用语义：`system_prompt = provider_system_prompt(...)`，`user_prompt = prompt.md`，确保结果可与 `/analyze` 后台 Provider 调用对齐。
- 脚本不写 `analysis_runs`，不写业务历史库，不请求金十 REST，不触发 Telegram。

推荐配置：

- Gemini 2.5 Flash 做 JSON A/B 时建议使用 `GEMINI_THINKING_BUDGET=0`，并将 `GEMINI_MAX_TOKENS` 设为 `8192`，降低 `MAX_TOKENS` 截断概率。
- GLM 4.7 / 智谱 compatible 做 JSON A/B 时建议使用 `COMPAT_LLM_THINKING_TYPE=disabled`；否则 `reasoning_content` 可能占满输出预算，导致可见 `content` 为空或 JSON 不完整。

## 6. Provider 执行顺序

建议顺序：

1. Gemini：使用 Dashboard Provider 或手动复制 `prompt.md`，记录 finishReason、耗时和 JSON 稳定性。
2. ChatGPT Plus：手动粘贴同一份 `prompt.md`，保存原始输出。
3. GLM Flash：使用 OpenAI-compatible 配置或手动方式，保存原始输出。

如果某个 Provider 返回不可解析 JSON，不要手工修复后再参与“稳定性”评分；可以另存一份修复版用于后续业务阅读，但评测记录必须保留原始失败。

## 7. 评分口径

每个 Provider 至少记录：

- `key_catalysts_hit`：是否命中关键新闻。
- `duplicate_news_id`：是否把同一个 `news_id` 拆成多个 catalysts。
- `judgement`：`news_driven` / `macro_sentiment` / `technical_breakout` / `unclear`。
- `missing_evidence_reasonable`：是否正确指出证据缺口。
- `json_parse_stable`：原始输出是否可直接解析。
- `prompt_runtime_notes`：Prompt 长度、耗时、MAX_TOKENS、timeout 或限流。

建议人工结论分为：

- `pass`：可直接保存或只需轻微人工复核。
- `watch`：可读但有明显重复、漏因或格式风险。
- `fail`：JSON 不稳定、关键新闻漏掉、或归因明显错误。

自动脚本只填写耗时、Token、finish reason、JSON 稳定性和错误等客观字段；`key_catalysts_hit`、`duplicate_news_id`、`missing_evidence_reasonable` 和最终 `pass/watch/fail` 仍需人工复核。

## 8. 暂不做

本轮暂不做：

- embedding 或向量相似度。
- 自动 Provider 多路并发。
- 自动重写 Prompt。
- 继续扩大 v3 默认选择规则。
- WebSocket / REST / Telegram / SQLite 业务历史库改动。

## 9. 下一步判断

如果 A/B 结果显示 Gemini / GLM 的主要问题是重复 `news_id` 或 JSON 不稳，优先小改 Prompt 和 Provider 错误展示。

如果结果显示关键新闻经常被 v3 默认选择漏掉，再回到 evidence scoring 小样本校准。

如果 ChatGPT Plus 明显优于 API Provider，优先优化手工回填和草稿筛选，不急着扩展自动调用。
