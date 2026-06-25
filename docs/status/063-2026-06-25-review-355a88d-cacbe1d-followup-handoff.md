# 063 - 355a88d 到 cacbe1d 深度 Review 后续收口

更新时间：2026-06-25 21:17（Asia/Shanghai）

当前分支：`main`

## 背景

本轮复核 `/Users/rich/Downloads/jin10-monitor 深度 Review 完整改动文档(355a88d → cacbe1d).zip` 与用户补充说明。

zip 内包含 6 个候选成品文件：

```text
run_ab_eval.py
dashboard_app.py
template_aggregation.html
test_run_ab_eval.py
test_dashboard_analysis.py
CHANGELOG.md
```

当前仓库基线已经是 `e9b8e75 fix(dashboard): harden provider ab eval calls`，比 review 目标 `cacbe1d` 多了 Provider A/B hardening，因此本轮没有整文件覆盖，而是逐项复用仍有价值的建议。

## 逐项评估

### 已由此前提交解决，不重复采纳

1. `run_ab_eval.py` 双重执行保护 `--execute --yes`。
   - 状态：已存在。
   - 理由：当前 CLI 已拒绝缺少 `--yes` 的真实调用。

2. 调用语义对齐 Dashboard Provider。
   - 状态：已存在。
   - 理由：当前脚本使用 `provider_system_prompt(provider_key, provider.name)` + `prompt.md`，没有把 `evidence_packet.json` 另塞进 user prompt。

3. `safe_filename()` 与 stale `_parsed.json` 清理。
   - 状态：已存在。
   - 理由：当前测试已覆盖 provider 文件名和失败时清理旧 parsed JSON。

4. 上轮 `asyncio.gather(return_exceptions=True)` 不采纳判断。
   - 状态：维持不采纳。
   - 理由：heartbeat 无限循环 task 不会返回，`return_exceptions=True` 无法及时暴露异常；当前做法是在 heartbeat loop 内部消化异常，避免影响主路。

### 本轮直接采纳并修正实现

1. `--skip-existing` 断点续跑。
   - 采纳状态：已采纳。
   - 实现：`scripts/run_ab_eval.py` 新增 `--skip-existing`；只跳过已有 `<provider>_result.json` 且 `status=done` 的 Provider。
   - 细节：`status=failed` 或缺失结果不会跳过，方便中断后只补失败项。
   - 理由：真实 Provider 调用即使免费也有额度和时间成本，断点续跑能避免重复消耗。

2. `--timeout` per-provider 超时覆盖。
   - 采纳状态：已采纳，但修正了候选实现。
   - 候选问题：候选代码在 provider 实例创建后才写 `PROVIDER_TIMEOUT_SECONDS`，而真实 Gemini/GLM adapter 在 `__init__` 中读取 timeout，因此可能不生效。
   - 实现：新增 `temporary_provider_timeout()`，在 `get_provider()` / `provider_factory()` 创建实例之前临时设置环境变量，Provider 调用结束后恢复。
   - 校验：`validate_args()` 限制 `--timeout` 必须在 `1-600` 秒。

3. 空 provider 和仅 `manual` 的友好错误。
   - 采纳状态：已采纳。
   - 实现：`validate_args()` 对空字符串 provider 提前报错；如果 provider 被过滤后为空，提示可用 provider，并说明 `manual` 不是 CLI 可调用 Provider。
   - 理由：原先 `normalize_provider_keys()` 会静默丢弃空字符串和 `manual`，错误不够可操作。

4. `GET /api/aggregation/stats`。
   - 采纳状态：已采纳。
   - 实现：`dashboard/app.py` 新增只读 JSON 端点；历史库不可用时返回 `503` 和 `{ok:false,error}`。
   - 边界：只调用 `history_health()` 和 `query_aggregation_report()`，不触发聚合、不写库、不请求外部源。

5. `/aggregation` AJAX 刷新统计。
   - 采纳状态：已采纳，但调整了前端实现风格。
   - 候选问题：候选模板使用较多内联样式和 emoji 文案，且只适合直接整文件覆盖。
   - 实现：保留现有页面结构，新增“刷新统计”按钮和 `refreshAggregationStats()`；只更新 `skipped_24h`、`skipped_7d` 与状态文字，不重绘 SVG 或明细表。
   - 理由：SVG 和明细仍由服务端渲染，局部刷新只做轻量观测即可。

### 后续计划，不在本轮扩张

1. `ab_scorecard.md` 自动加入 baseline vs after-fix 对照。
   - 状态：暂缓。
   - 理由：当前 A/B 工具定位是记录客观运行结果，质量判断仍需人工；复杂对照容易变成半自动评分系统。

2. `/aggregation` AJAX 重绘 SVG 与明细表。
   - 状态：暂缓。
   - 理由：当前收益不如只刷新数字，且会把 Jinja 服务端渲染拆成前端模板逻辑。

3. 真实 Provider 优先级写入生产配置。
   - 状态：等 scorecard 人工打分后再做。
   - 理由：目前只确认 JSON 稳定性和耗时，`judgement`、关键催化覆盖、缺失证据合理性还需要人工复核。

### 不采纳或不按候选方式采纳

1. 整文件覆盖 zip 中的 `run_ab_eval.py`。
   - 理由：会回退 `e9b8e75` 已完成的 `.env` 自动加载和实时 flush，也没有包含 Gemini/GLM hardening 后的上下文。

2. 候选 `--timeout` 的 provider 创建后注入方式。
   - 理由：真实 adapter timeout 在 `__init__` 读取，必须在 provider factory 之前注入。

3. 候选 `aggregation.html` 的完整样式覆盖。
   - 理由：会引入不必要的页面结构和样式变化；当前页面只需轻量按钮。

4. 自动 Provider 多路并发。
   - 理由：仍不符合 008 设计文档，本轮继续保持串行、可观察、可中断。

## 修改文件

```text
scripts/run_ab_eval.py
dashboard/app.py
dashboard/templates/aggregation.html
tests/test_run_ab_eval.py
tests/test_dashboard_analysis.py
docs/design/008-provider-ab-evaluation-plan.md
CHANGELOG.md
docs/status/063-2026-06-25-review-355a88d-cacbe1d-followup-handoff.md
```

## 边界确认

未改：

- WebSocket 实时主路。
- REST 补拉策略。
- Telegram 发送、健康心跳或 `delivery_log`。
- `data/history.sqlite3` 业务历史库写入逻辑。
- `data/dashboard_analysis.sqlite3` 的 `analysis_runs` 保存逻辑。
- Dashboard Provider 后台保存状态机。
- Provider API 默认启用范围；OpenAI / Anthropic 仍不默认跑。

本轮新增的 `/api/aggregation/stats` 是只读端点，只返回聚合诊断 JSON。

## 验证计划

建议验证：

```bash
.venv/bin/python -m py_compile scripts/run_ab_eval.py dashboard/app.py
.venv/bin/python -m pytest tests/test_run_ab_eval.py tests/test_dashboard_analysis.py -q
.venv/bin/python -m pytest -q
git diff --check
```

如需真实 A/B 续跑，可使用：

```bash
.venv/bin/python scripts/run_ab_eval.py --run-ids ar_1 ar_2 ar_3 \
  --providers gemini compatible \
  --execute --yes \
  --skip-existing \
  --timeout 120
```

## 下一步建议

P0：

1. 人工填写 `exports/provider_ab_after_fix/<run_id>/ab_scorecard.md` 主观字段。
2. 用 scorecard 决定是否要小改 `news_driven` vs `macro_sentiment` Prompt 口径。

P1：

1. 服务重启后观察 60 秒内 Telegram `🟢 [启动]` 心跳，确认 monitor heartbeat 端到端仍正常。
2. 需要长批 A/B 时优先使用 `--skip-existing --timeout 120`，避免重复消耗免费额度。

P2：

1. 如果 aggregation 页面需要更实时的图表，再单独评估 SVG/明细 AJAX 重绘。
2. 如果 Provider A/B 样本扩大到 5 个以上，再考虑生成一个汇总 Markdown，不做自动投票。

## 下一 session 提示词

```text
继续 /Users/rich/jin10-monitor。

先读取 AGENTS.md、CHANGELOG.md、docs/design/008-provider-ab-evaluation-plan.md，以及 docs/status/063-2026-06-25-review-355a88d-cacbe1d-followup-handoff.md。

当前边界：
- 本轮已逐项复核 355a88d → cacbe1d 深度 review zip。
- 已采纳 run_ab_eval.py --skip-existing、--timeout 1-600、空 provider 友好错误。
- 已采纳 /api/aggregation/stats 只读 JSON 端点和 /aggregation 页面轻量刷新按钮。
- 未整文件覆盖 zip 候选，保留 e9b8e75 的 .env 自动加载、实时 flush、Gemini/GLM hardening。
- 不写 analysis_runs、不写业务历史库、不请求金十 REST、不触发 Telegram。
- WebSocket / REST / Telegram / Dashboard Provider 保存逻辑未改。

下一步优先：
1. 跑 targeted + full pytest 和 git diff --check。
2. 需要 closeout 时 commit/push。
3. 后续根据 scorecard 决定是否小改 Provider judgement Prompt。

模型建议：
- 测试和 closeout：GPT-5.5 中。
- 修改 Provider judgement 口径或扩展 A/B 汇总能力：GPT-5.5 高。
```
