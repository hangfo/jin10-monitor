更新时间：2026-06-11 20:04（Asia/Shanghai）

# 053 - 052 Review 跟进与下一阶段路线交接

## 本次状态

本轮对照两份截至 `bab6c66` 的 review：

- `/Users/rich/Downloads/jin10-review-052-diff.md`
- `/Users/rich/.codex/attachments/512bab78-09bd-4ffe-a27f-280f461f410a/pasted-text.txt`

已接纳并实现：

- P1：running 详情页前端计时时区修复。
  - `provider_started_at` 是北京时间字符串。
  - 前端现在用 `new Date(startedAt.replace(" ", "T") + "+08:00")` 解析。
  - 避免 UTC 浏览器把已等待时间多算 8 小时，导致页面刚打开就误报长等待。
- P1：Provider 统计 `model_label` 保留最新活动记录。
  - `query_provider_call_stats()` 的 rows 已按活动时间 DESC 排序。
  - 分 Provider 聚合时不再用后续旧记录覆盖 `setdefault()` 初始化的最新 `model_label`。
  - 避免 GLM/Gemini 升级模型后 `/system` 仍显示旧版本名称。
- P2：running 页面自动刷新更温和。
  - 仍保留 6 秒自动刷新。
  - 如果标签页不可见或用户正在选中文本，延后 2 秒再检查。
  - 避免阅读证据、复制文本时被 reload 打断。
- P2：Provider 统计增加未归类计数。
  - 对 `status=draft`、`provider_name` 非空但 `provider_error` 为空的旧/异常记录，单独计入 `uncounted_count`。
  - 不把这类记录伪装成成功、失败或 running。
- 巧思增强：`/system` Provider 统计增加最近调用时间线。
  - 最近最多 50 个 Provider 调用以小圆点展示。
  - 成功、失败、调用中、未归类分别用不同颜色。
  - 点击可跳到对应 `/analyze/{run_id}`。
  - 仍只读独立分析库，不请求模型 API，不写业务库。

- commit：`b5c7536 fix(dashboard): address provider stats review`
- push：已推送到 `origin/main`

## 未立即实现与理由

- 暂缓：`docs/ROADMAP.md` / `docs/DECISIONS.md` / `docs/BACKLOG.md` 三件套。
  - 理由：这是正确方向，但属于产品架构收口，不应和本轮 052 review bugfix 混成一个 commit。
  - 建议下一轮作为 P0 文档阶段独立做。
  - 推荐模型：`GPT-5.5 中`。
- 暂缓：Provider Tournament 面板。
  - 理由：当前已具备固定 packet 导出、历史筛选和 `/analyze/compare`；下一步应先跑 3-5 个真实 Gemini/GLM 小样本，再决定面板字段。
  - 推荐模型：`GPT-5.5 中` 起步；如果要自动评分和评测表结构，使用 `GPT-5.5 高`。
- 暂缓：Market Confirmation Engine。
  - 理由：交易价值高，但会新增 market reaction 数据模型和多窗口行情计算，应该先独立设计 `market_reactions` 表与回填策略。
  - 推荐模型：`GPT-5.5 高`。
- 暂缓：NewsLiquid 整合。
  - 理由：必须作为语义层写入独立分析库，不能污染 `flash_history` 原始事件流；需要先完成路线图和 market confirmation 边界。
  - 推荐模型：`GPT-5.5 高`。
- 暂缓：Missed Alpha Digest。
  - 理由：这是长期闭环功能，依赖 Provider A/B 与 Market Confirmation 的真实数据。
  - 推荐模型：`GPT-5.5 高`。
- 暂缓：Anthropic Provider 真实试用、SSE、Vision、embedding。
  - 理由：当前主线仍是免费/低成本 Gemini + GLM 的质量校准；这些是能力扩展，不是当前缺陷修复。
  - 推荐模型：`GPT-5.5 高`。

## 当前边界

本轮保持：

- 不请求金十 REST。
- 不修改 WebSocket / REST / Telegram 采集或发送逻辑。
- 不写业务历史库。
- 不自动重发 Telegram `unknown_timeout`。
- 不自动调用 Provider。
- 不引入新外部源。
- `/system` Provider 统计继续只读 `data/dashboard_analysis.sqlite3`。

## 验证

已执行：

```bash
git branch --show-current
git status --short --branch
git pull --rebase
git log --oneline -8
.venv/bin/python -m py_compile dashboard/analysis_db.py dashboard/app.py
.venv/bin/python -m pytest tests/test_dashboard_analysis.py -q
.venv/bin/python -m pytest -q
git diff --check
临时 `127.0.0.1:8766` curl 烟测
正式 `127.0.0.1:8765` reload 后 curl 烟测
```

当前结果：

- 分支：`main`
- `git pull --rebase`：`Current branch main is up to date.`
- `py_compile`：通过
- `tests/test_dashboard_analysis.py`：67 passed
- 全量 pytest：209 passed
- `git diff --check`：通过
- 临时 `127.0.0.1:8766`：
  - `/system`：200，Provider 调用统计和最近调用时间线可见。
  - `/analyze/history?status=recent_failed`：200，状态筛选正常。
- 正式 `127.0.0.1:8765`：
  - 已执行 `launchctl kickstart -k gui/$(id -u)/com.rich.jin10-dashboard`。
  - `/system`：200，Provider 调用统计和最近调用时间线可见。
  - `/analyze/history?status=recent_failed`：200，状态筛选正常。

## 推荐下一阶段

P0 / 立即做：

1. 用 `scripts/export_provider_ab_packet.py` 固定 3-5 个 evidence packet。
2. 每个 packet 分别跑 Gemini 和 GLM。
3. 用 `/analyze/compare` 人工比较：
   - 机制驱动是否说清楚。
   - 方向是否符合行情。
   - 是否过度归因。
   - JSON 是否稳定。
4. 把真实观察写进新的 Provider A/B handoff，再决定是否重构 GLM Prompt。

P1 / 紧随其后：

1. 新增 `docs/ROADMAP.md`、`docs/DECISIONS.md`、`docs/BACKLOG.md`。
2. `/system/ws-initial` 顶部行动指南。
3. `ops_notes` 独立分析库备注设计，用于人工记录 unknown_timeout / ws_initial / rest_status 处置结论。

P2 / 设计后再动代码：

1. Provider Tournament 面板。
2. Market Confirmation Engine。
3. NewsLiquid 语义层。
4. Missed Alpha Digest。
5. Anthropic / SSE / Vision / embedding。

推荐模型：

- `GPT-5.5 中`：当前这类 review follow-up、小型 dashboard 修复、Roadmap/DECISIONS/BACKLOG、Provider 小样本手工 A/B、ws_initial 行动指南。
- `GPT-5.5 高`：Market Confirmation Engine、NewsLiquid 语义层、自动评测框架、GLM Prompt 结构重构、SSE/Vision/embedding 或任何采集链路逻辑。

## 下一 session 可复制提示词

```text
继续 /Users/rich/jin10-monitor 项目。

先读取：
1. /Users/rich/jin10-monitor/AGENTS.md
2. /Users/rich/jin10-monitor/docs/status/053-2026-06-11-review-052-followup-handoff.md
3. /Users/rich/jin10-monitor/docs/status/052-2026-06-09-history-provider-stats-closeout-handoff.md
4. /Users/rich/jin10-monitor/docs/design/008-provider-ab-evaluation-plan.md
5. /Users/rich/jin10-monitor/docs/design/007-provider-adapter-and-review-followup-plan.md

先执行：
git branch --show-current
git status
git pull --rebase
git log --oneline -8

当前结论：
- 052 review 的 P1/P2 低风险缺陷已接纳：running 前端计时按 +08:00 解析；Provider 统计不再被旧 model_label 覆盖；running 自动刷新避开选中文本和后台标签页；/system Provider 统计增加未归类计数和最近调用时间线。
- Dashboard 仍是本地只读诊断和分析侧车，不作为采集入口。
- 不请求金十 REST，不写业务历史库，不自动重发 Telegram unknown_timeout。

推荐下一步：
1. 优先跑 Gemini vs GLM 小样本 A/B：固定 3-5 个 evidence packet，每个分别跑 Gemini 和 GLM，用 /analyze/compare 人工评机制驱动、方向准确和过度归因。
2. 另开文档阶段新增 docs/ROADMAP.md、docs/DECISIONS.md、docs/BACKLOG.md，把当前 053 个 handoff 的有效路线收口。
3. 再做 /system/ws-initial 行动指南和 ops_notes 设计。
4. Market Confirmation、NewsLiquid、Missed Alpha Digest、Anthropic/SSE/Vision/embedding 继续暂缓到设计后。

推荐模型：
- GPT-5.5 中：Provider 小样本 A/B、Roadmap/DECISIONS/BACKLOG、ws_initial 行动指南、ops_notes。
- GPT-5.5 高：Market Confirmation、NewsLiquid、自动评测、GLM Prompt 结构重构、SSE/Vision/embedding、采集链路逻辑。
```
