# 065 - ROADMAP / DECISIONS / BACKLOG 路线收口

更新时间：2026-06-26 00:57（Asia/Shanghai）

当前分支：`main`

## 背景

本轮接续 `064-2026-06-25-replit-review-followup-handoff.md`，先只读复盘 `exports/provider_ab_after_fix/` 下 3 个 Provider A/B 样本，再按“scorecard 之后再做 ROADMAP / DECISIONS / BACKLOG”的顺序完成文档收口。

本轮不修改 Provider Prompt、不重新调用 Provider API、不触碰采集或投递链路。

## Provider A/B 复盘结论

3 个样本均保持 JSON 稳定：

- `ar_20260606_003632_12fb68`：强非农 / 加息预期导致 ETH 下跌。
  - Gemini：`pass`，`news_driven` 命中主线，未重复 `news_id`。
  - GLM：`watch/pass`，主线正确但更偏 `macro_sentiment`。
- `ar_20260609_222743_1c996d`：CPI / 能源 / 风险偏好导致 ETH 下跌。
  - Gemini：`pass`，`macro_sentiment` 口径合理。
  - GLM：`watch`，部分地缘和原油链条偏弱。
- `ar_20260625_052808_8607df`：ETH 上涨但证据多为美元 / 加息偏利空。
  - Gemini：`watch`，能提示时间和因果不足，但 summary 与上涨方向存在张力。
  - GLM：`watch/fail`，能指出宏观利空与 ETH 上涨不一致，但出现 `[#news_id]` 占位符格式问题。

暂不立即修改 Prompt。真正要改的不是简单扩大 `news_driven` / `macro_sentiment` 定义，而是增加“证据主方向与行情方向明显相反时，优先降级为 `unclear` 或低置信宏观解释，并明确 missing evidence”的规则。

## 本轮新增文档

```text
docs/ROADMAP.md
docs/DECISIONS.md
docs/BACKLOG.md
```

### `docs/ROADMAP.md`

记录当前阶段路线：

- P0：Provider A/B 质量收口。
- P1：Dashboard 只读诊断与复盘体验。
- P2：采集可靠性维护。
- 暂缓：Canvas、Anthropic Provider 默认化、自动并发、embedding、自动投票和大规模 evidence scoring 重写。

### `docs/DECISIONS.md`

记录仍有效的决策：

- Dashboard 采用 `run_dashboard.py` + `dashboard/` 独立服务路线。
- Provider 分析与业务历史库隔离。
- Provider A/B 当前基线为 Gemini + GLM。
- `comparison.md` 只做客观汇总。
- 运行诊断必须只读优先。
- 健康心跳是诊断信号，不写 `delivery_log`。

### `docs/BACKLOG.md`

拆分待办池：

- P0：Provider A/B 人工 scorecard 落档、判断是否小改 judgement Prompt。
- P1：`/system` 日志 level 筛选 UI、A/B 批量汇总 Markdown、旧导出目录补生成 `comparison.md`。
- P2：`/aggregation` AJAX 重绘、evidence scoring 小样本校准、Provider 原始输出大小提示。

## 边界确认

未改：

- WebSocket 实时主路。
- REST 补拉策略。
- Telegram 发送、健康心跳或 `delivery_log`。
- `data/history.sqlite3` 业务历史库。
- `data/dashboard_analysis.sqlite3` 与 `analysis_runs` 保存逻辑。
- Dashboard Provider 后台保存状态机。
- Provider Prompt、adapter、A/B CLI 行为。

未调用：

- Provider API。
- 金十 REST。
- Telegram API。
- 本地 Dashboard 写入端点。

## 验证结果

已运行：

```bash
git diff --check
.venv/bin/python - <<'PY'
from pathlib import Path
for path in [Path('docs/ROADMAP.md'), Path('docs/DECISIONS.md'), Path('docs/BACKLOG.md')]:
    text = path.read_text()
    fences = text.count(chr(96) * 3)
    headings = [line for line in text.splitlines() if line.startswith('#')]
    print(f'{path}: fences={fences} headings={len(headings)} first={headings[0] if headings else "-"}')
    if fences % 2:
        raise SystemExit(f'unclosed fence in {path}')
PY
```

结果：

- `git diff --check`：通过。
- Markdown 结构检查：通过。

本轮为 docs-only，未运行 pytest。

## 下一步建议

P0：

1. 决定是否小改 Provider judgement Prompt。
2. 如果要改，重点增加“证据方向与行情方向冲突时降级”的规则，并补测试保护。
3. 同时修正 GLM 输出占位符 `[#news_id]` 的 Prompt 约束。

P1：

1. 如暂不改 Prompt，先把本轮 A/B 主观结论回填到各 `ab_scorecard.md` 或新增汇总文档。
2. 做 `/system` 日志 level 筛选 UI，复用已存在的后端 API。

模型建议：

- 回填 scorecard、整理 A/B 汇总、`/system` 小 UI：`GPT-5.5 中`。
- 修改 Provider judgement Prompt、evidence scoring 或 Dashboard compare 体验：`GPT-5.5 高`。

## 下一 session 提示词

```text
继续 /Users/rich/jin10-monitor。

先读取：
1. AGENTS.md
2. CHANGELOG.md
3. docs/status/065-2026-06-26-roadmap-decisions-backlog-handoff.md
4. docs/ROADMAP.md
5. docs/DECISIONS.md
6. docs/BACKLOG.md
7. docs/design/008-provider-ab-evaluation-plan.md

当前边界：
- Provider A/B scorecard 已只读复盘：Gemini JSON 稳定且整体优于 GLM；GLM 可作第二意见但有弱链条和 `[#news_id]` 占位符问题。
- ROADMAP / DECISIONS / BACKLOG 三件套已新增。
- 不写 analysis_runs、不写业务历史库、不请求金十 REST、不触发 Telegram。
- WebSocket / REST / Telegram / Dashboard Provider 保存逻辑未改。
- 不要自动调用新的 Provider API，除非我明确要求。

下一步优先：
1. 判断是否小改 Provider judgement Prompt。
2. 如果修改 Prompt，用 GPT-5.5 高，重点处理行情方向与证据方向冲突时降级为 unclear / 低置信 macro_sentiment，并约束 GLM 不得输出 `[#news_id]` 占位符。
3. 如果暂不改 Prompt，用 GPT-5.5 中，先回填 scorecard 或做 `/system` 日志 level 筛选 UI。
```
