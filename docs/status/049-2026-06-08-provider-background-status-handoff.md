更新时间：2026-06-08 01:37（Asia/Shanghai）

# 049 - Provider 后台调用与状态展示交接

## 本次状态

当前分支仍为 `main`。本轮接续 `048`，完成 `/analyze` Provider 后台调用 / 异步状态第一版。

已完成：

- 点击“调用并保存”后不再让页面阻塞等待 GLM / Gemini / 其他 Provider 返回。
- 草稿会先进入 `running` 状态，详情页和历史页展示为 `调用中`。
- 独立分析库 `analysis_runs` 新增并迁移字段：
  - `provider_name`
  - `provider_started_at`
- Provider 开始调用时会记录 Provider、开始时间，并清空上一轮错误与耗时。
- Provider 后台完成后仍沿用原 `save_answer()` 保存路径，状态转为 `done`，保存 judgement、overall confidence、模型标签和耗时。
- Provider 失败或返回不可解析 JSON 时，状态回到 `draft`，保留草稿、错误原因、错误时间和实际耗时，不保存为已完成。
- 详情页在 `running` 状态下显示 Provider、开始时间和“进行中”，并提供刷新入口。
- 历史页增加开始时间列，`running` 状态显示 Provider 和“进行中”耗时占位。
- 重复点击同一草稿时会被拦截，提示 Provider 正在调用中，避免重复打模型。

## 边界

本轮保持：

- 不请求金十 REST。
- 不修改 WebSocket / REST / Telegram 采集或发送逻辑。
- 不写业务历史库。
- 不自动重发 Telegram `unknown_timeout`。
- 不把 GLM、Gemini 或任何 Provider 设为启动必需项。
- 默认无 Provider key 时仍不请求模型 API，手动复制 Prompt / 粘贴 JSON 流程继续可用。
- Provider 调用结果只写 `data/dashboard_analysis.sqlite3` 独立分析库。

## 验证

已执行：

```bash
.venv/bin/python -m py_compile dashboard/app.py dashboard/analysis_db.py
.venv/bin/python -m pytest tests/test_dashboard_analysis.py -q
.venv/bin/python -m pytest -q
git diff --check
临时 `127.0.0.1:8766` 浏览器烟测
```

当前结果：

- `py_compile`：通过
- `tests/test_dashboard_analysis.py`：56 passed
- 全量 pytest：197 passed
- `git diff --check`：通过
- 浏览器烟测：历史页和详情页均为 200，历史页展示“开始 / 耗时”列，详情页展示 Provider / 开始 / 耗时 / 状态，无 500。

## 当前观察

这次实现解决的是用户体验阻塞，不解决 Provider 服务端耗时波动本身。GLM 仍可能几十秒返回；差别是页面不会一直卡在表单提交请求里，用户可以先回到详情页或历史页查看状态。

第一版没有做实时 WebSocket / SSE 推送。当前用刷新查看状态即可，风险更低，也更符合本地 dashboard sidecar 定位。

## 下一步建议

建议下一轮优先做轻量可观测和历史管理，而不是继续调整 GLM token：

1. 历史页增加状态筛选：全部 / 调用中 / 草稿 / 已完成 / 最近失败。
2. 详情页可选轻量自动刷新：仅 `running` 状态每 5-10 秒刷新一次，完成或失败后停止。
3. 草稿清理：支持删除失败草稿，必要时再做批量删除。
4. Provider 调用统计：在 `/system` 展示最近 24h 调用次数、失败次数、平均耗时和最近错误，但只读分析库，不替代官方账单。

推荐模型：

- `GPT-5.5 中`：历史筛选、running 自动刷新、草稿管理、轻量 Provider 统计。
- `GPT-5.5 高`：自动评测框架、embedding / 向量相似度、Vision 自动截图分析、外部源或采集链路逻辑。

## 下一 session 可复制提示词

```text
继续 /Users/rich/jin10-monitor 项目。

先读取：
1. /Users/rich/jin10-monitor/AGENTS.md
2. /Users/rich/jin10-monitor/docs/status/049-2026-06-08-provider-background-status-handoff.md
3. /Users/rich/jin10-monitor/docs/status/048-2026-06-08-glm-provider-ux-handoff.md
4. /Users/rich/jin10-monitor/docs/status/047-2026-06-07-analyze-v3-provider-ux-handoff.md
5. /Users/rich/jin10-monitor/docs/design/007-provider-adapter-and-review-followup-plan.md

先执行：
git branch --show-current
git status
git pull --rebase
git log --oneline -8

当前结论：
- Provider Adapter 第一版已完成，支持 Anthropic、Gemini、OpenAI-compatible、OpenAI；默认无 key 不请求模型 API。
- /analyze Provider 调用已改为后台执行：提交后草稿进入 calling/running 状态，详情页和历史页显示 Provider、开始时间和耗时状态。
- Provider 成功后保存为 done；失败或不可解析 JSON 会回到草稿并保留错误和耗时，不污染已完成分析。
- GLM:glm-4.7-flash 的弱证据约束已生效；不要通过降低 COMPAT_LLM_MAX_TOKENS 到 1400 优化耗时，本地 .env 保持 COMPAT_LLM_MAX_TOKENS=4096。
- Dashboard 仍是本地只读诊断和分析侧车，不作为采集入口。
- 不请求金十 REST，不写业务历史库，不自动重发 Telegram unknown_timeout。

推荐下一步：
优先做 Provider 状态管理的轻量收尾：
1. 历史页增加状态筛选：全部 / 调用中 / 草稿 / 已完成 / 最近失败。
2. 详情页只在 running 状态做轻量自动刷新，完成或失败后停止。
3. 增加失败草稿清理入口，先做单条删除体验，不急着批量。
4. 可选在 /system 增加只读 Provider 调用统计。

推荐模型：
- GPT-5.5 中：历史筛选、running 自动刷新、草稿管理、轻量 Provider 统计。
- GPT-5.5 高：自动评测框架、embedding/向量相似度、Vision 自动截图分析、外部源或采集链路逻辑。
```
