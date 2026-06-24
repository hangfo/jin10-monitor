# 061 - Provider A/B 批量评测工具收口

更新时间：2026-06-25 05:08（Asia/Shanghai）

当前分支：`main`

## 背景

本轮接续 `060-2026-06-25-review-4981335-355a88d-followup-handoff.md` 的 P2：单独评估并落地 `scripts/run_ab_eval.py` 自动 Provider A/B 调用器。

目标不是替代人工质量判断，而是把固定 evidence packet 的 API 调用、耗时、Token、finish reason、JSON 稳定性和原始输出落盘标准化，减少手工复制统计的重复劳动。

## 已完成

### 受保护的 CLI

新增：

```bash
scripts/run_ab_eval.py
```

默认行为：

```bash
.venv/bin/python scripts/run_ab_eval.py ar_xxx
```

- 默认 dry-run，不调用任何 Provider API。
- 自动补齐缺失的 `exports/provider_ab/<run_id>/` packet。
- 检查 Provider 配置状态。
- 写入 `eval_plan.json` 作为预演记录。

真实调用必须显式确认：

```bash
.venv/bin/python scripts/run_ab_eval.py ar_xxx --providers gemini compatible --execute --yes
```

批量模式：

```bash
.venv/bin/python scripts/run_ab_eval.py --run-ids ar_1 ar_2 ar_3 --providers gemini compatible
.venv/bin/python scripts/run_ab_eval.py --run-ids ar_1 ar_2 ar_3 --providers gemini compatible --execute --yes
```

安全保护：

- `--execute` 没有 `--yes` 会直接拒绝。
- 批量真实调用默认最多 5 个 `run_id`；超过需显式提高 `--max-runs`。
- 默认 Provider 为 `gemini compatible`，对应当前 Gemini + GLM/OpenAI-compatible 基线。
- `openai` / `anthropic` 只有显式指定才会尝试，不进入默认批量。
- `manual` 会被过滤，因为它不是可自动调用 Provider。

### 输出文件

真实调用结果只写入导出目录：

```text
exports/provider_ab/<run_id>/
```

新增或更新文件：

- `eval_plan.json`：dry-run 计划和配置状态。
- `<provider>_raw.txt`：Provider 原始输出或错误。
- `<provider>_parsed.json`：可解析 JSON 的规范化结果。
- `<provider>_result.json`：单 Provider 客观运行元信息。
- `eval_results.json`：本次 run 的结构化汇总。
- `ab_scorecard.md`：追加“自动 Provider A/B 结果”区块。

脚本不写 `analysis_runs`，不写业务历史库，不请求金十 REST，不触发 Telegram。

### 调用语义

脚本复用 Dashboard 当前 Provider 语义：

- `system_prompt = provider_system_prompt(provider_key, provider.name)`
- `user_prompt = prompt.md`

没有采用候选脚本里“把整份 `prompt.md` 放到 system，再把 `evidence_packet.json` 塞进 user”的做法。这样自动 A/B 结果能和 `/analyze/{run_id}/run-provider` 后台调用保持可比。

### 测试覆盖

新增：

```bash
tests/test_run_ab_eval.py
```

覆盖：

- 必须提供 `run_id` 或 `--run-ids`。
- `--execute` 必须搭配 `--yes`。
- 批量真实调用超过 `--max-runs` 会拒绝。
- Provider 名称归一化：`glm` 归到 `compatible`，`manual` 不自动调用。
- fenced JSON / 嵌入 JSON 解析。
- dry-run 会导出 packet 和 `eval_plan.json`，但不会调用 fake provider。
- execute 会写 raw / parsed / result / eval_results / scorecard。
- Provider 异常会记录为失败并落盘。
- `main()` dry-run 可返回 0。
- 批量 dry-run 汇总输出。
- Provider 文件名按 key 固定，避免模型名中的 `/`、`:` 污染路径。

## 边界确认

未改：

- WebSocket 实时主路。
- REST 补拉策略。
- Telegram 发送或健康心跳。
- `data/history.sqlite3` 业务历史库。
- Dashboard `/analyze` 页面和后台 Provider 保存逻辑。
- Provider adapter 网络实现。

本轮只新增离线 CLI、测试和文档。

## 使用建议

第一轮建议：

1. 从 `/analyze/history` 选 3 个代表性草稿或已完成 run。
2. 先 dry-run：

```bash
.venv/bin/python scripts/run_ab_eval.py --run-ids ar_1 ar_2 ar_3 --providers gemini compatible
```

3. 确认 `eval_plan.json`、packet、Provider 配置和 Prompt 长度。
4. 再真实调用：

```bash
.venv/bin/python scripts/run_ab_eval.py --run-ids ar_1 ar_2 ar_3 --providers gemini compatible --execute --yes
```

5. 人工打开每个 `ab_scorecard.md`，只对自动脚本无法判断的字段打分：
   - key catalysts 是否命中。
   - 是否重复拆分同一个 `news_id`。
   - `judgement` 是否合理。
   - `missing_evidence` 是否合理。
   - 最终 pass / watch / fail。

## 验证结果

本轮已运行：

```bash
.venv/bin/python -m py_compile scripts/run_ab_eval.py
.venv/bin/python -m pytest tests/test_run_ab_eval.py -q
.venv/bin/python -m pytest tests/test_dashboard_analysis.py tests/test_run_ab_eval.py -q
.venv/bin/python -m pytest -q
git diff --check
```

结果：

- `tests/test_dashboard_analysis.py tests/test_run_ab_eval.py`：`84 passed`
- 全量 pytest：`247 passed`
- `git diff --check`：通过

## 下一步建议

P0：

1. 挑 3 个固定 packet 做 dry-run，确认 Gemini / compatible 配置状态。
2. 小批量真实执行 `--execute --yes`，只跑 3 个窗口。
3. 人工填写 `ab_scorecard.md` 的主观字段。

P1：

1. 汇总 Gemini vs GLM 的 JSON 稳定性、耗时和重复 `news_id` 模式。
2. 若 GLM 仍明显过度归因，再小改 `provider_system_prompt()` 的 GLM 专用约束。
3. 若关键新闻漏选明显，再回到 evidence scoring 小样本校准。

P2：

1. 考虑给 `/analyze/history` 加“导出 A/B packet”按钮。
2. 考虑给 `/analyze/compare` 增加自动结果字段高亮，但不要先做复杂投票系统。

## 下一 session 提示词

```text
继续 /Users/rich/jin10-monitor。

先读取 AGENTS.md、CHANGELOG.md、docs/design/008-provider-ab-evaluation-plan.md，以及 docs/status/061-2026-06-25-provider-ab-eval-tool-handoff.md。

当前边界：
- scripts/run_ab_eval.py 已实现，默认 dry-run。
- 真实 Provider 调用必须 --execute --yes。
- 默认 Provider 为 gemini compatible；openai/anthropic 不默认跑。
- 结果只写 exports/provider_ab/<run_id>/，不写 analysis_runs、不写业务历史库、不请求金十 REST、不触发 Telegram。
- WebSocket / REST / Telegram / Dashboard 保存逻辑未改。

下一步优先：
1. 挑 3 个代表性 analysis run，先执行 dry-run。
2. 确认配置和 packet 后，小批量真实跑 gemini + compatible。
3. 人工填写 scorecard 主观字段，判断是否需要改 GLM prompt 或 evidence scoring。

模型建议：
- 执行 dry-run、整理 scorecard：GPT-5.5 中。
- 根据真实 A/B 结果修改 Provider prompt、evidence scoring 或 Dashboard 比较体验：GPT-5.5 高。
```
