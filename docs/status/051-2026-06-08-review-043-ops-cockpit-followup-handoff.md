更新时间：2026-06-08 21:31（Asia/Shanghai）

# 051 - 043 运维驾驶舱 Review 跟进交接

## 本次状态

本轮根据 `/Users/rich/Downloads/jin10-review-043-diff.md` 复核 `92973a1 → bf4a9b4` 的 `/system` 运维驾驶舱、`/telegram-status` unknown_timeout 核对和 `/system/ws-initial` 只读诊断变更。

已接纳并实现：

- P0：修复 `unknown_timeout_confirmed` 未进入 `/system` 驾驶舱的信息断层。
  - `query_system_health()` 现在计算：
    - `unknown_timeout`
    - `unknown_timeout_confirmed`
    - `unknown_timeout_unconfirmed`
  - `build_ops_overview()` 只用 `unknown_timeout_unconfirmed` 和 `failed` 触发 Telegram 降级。
  - 已在 `delivery_log` 确认的 `unknown_timeout` 不再让 Hero 进入“降级运行”。
- P1：REST 泳道 headline 本地化。
  - `forbidden_backoff` 显示为 `403 退避中`。
  - `ok`、`error`、`recent`、`no_recent_success` 显示为中文。
- P1：`ws_initial` 下钻记录优先排序。
  - `newer_than_cursor=True` 的记录排在前面，同组内仍按发布时间新到旧。
- P1：`info` pill 映射为绿色。
  - 此项已在 `050` 跟进中完成，本轮保留测试覆盖。
- P2：Initial History 泳道口径更清楚。
  - `新入库 N 条` 改为 `最近快照新增 N 条`。
  - detail 补充最近快照时间，并说明这是重连快照新增计数，不是 24h 累计。
- UX：Hero 区增加状态参考起点和持续时长。
  - REST 退避时优先使用 `rest_last_ok_at` 作为参考起点。
  - 主路 warn/error 时使用 `last_ingested_at` 作为参考起点。

## 暂缓项与理由

- 暂缓：Anthropic Provider 真实接入。
  - 理由：当前 Provider Adapter 已有多 Provider 接入，`043` review 的 Anthropic/SSE 建议属于主线功能扩展，不应和 `/system` 只读诊断修复混在一个变更里。
  - 建议模型：`GPT-5.5 高`，如果只做非流式 Anthropic Provider 小步接入可用 `GPT-5.5 中`。
- 暂缓：SSE 流式分析。
  - 理由：当前 Provider 调用已改为后台状态 UX；SSE 会改变调用交互模型、错误恢复和保存时机，需要单独设计。
  - 建议模型：`GPT-5.5 高`。
- 暂缓：行情面板 Canvas mini 折线图。
  - 理由：这是 `/item` 行情可视化增强，不属于 043 驾驶舱 bug 修复；且需要浏览器截图验证不同窗口/无行情数据状态。
  - 建议模型：`GPT-5.5 中`。
- 暂缓：Telegram unknown_timeout 人工备注 / 只读处置表。
  - 理由：需要新增独立分析库表和处置状态语义，必须先明确“人工确认”是否影响驾驶舱降级判断；本轮只修复 delivery_log 已确认的假阳性。
  - 建议模型：`GPT-5.5 中`。
- 暂缓：`/system/ws-initial` 顶部动态行动指南。
  - 理由：排序已经让关键记录优先出现；行动指南属于页面信息架构增强，可和人工处置流程一起做。
  - 建议模型：`GPT-5.5 中`。
- 暂缓：Hero actions 区域 `max-height`。
  - 理由：目前没有实际溢出证据，先保留为低优先级 UI polish。
  - 建议模型：`GPT-5.5 中`。

## 边界

本轮保持：

- 不请求金十 REST。
- 不修改 WebSocket / REST / Telegram 采集或发送逻辑。
- 不写业务历史库。
- 不自动重发 Telegram `unknown_timeout`。
- 不自动把 `unknown_timeout` 改写为 `sent`。
- `/system`、`/telegram-status`、`/system/ws-initial` 仍是只读诊断页面。

## 验证

已执行：

```bash
.venv/bin/python -m pytest tests/test_dashboard_db.py -q
.venv/bin/python -m py_compile dashboard/db.py dashboard/app.py
.venv/bin/python -m pytest tests/test_dashboard_db.py tests/test_dashboard_analysis.py -q
.venv/bin/python -m pytest -q
git diff --check
```

当前结果：

- `tests/test_dashboard_db.py`：24 passed
- `py_compile`：通过
- 聚焦测试：88 passed
- 全量测试：206 passed
- `git diff --check`：通过
- 浏览器烟测：
  - `/system`：Telegram 条形图下方显示已确认 / 仍需核对；REST 泳道为中文 headline；Hero 显示状态参考起点。
  - `/system/ws-initial`：首屏可见晚于游标记录，无 Internal Server Error。

## 下一步建议

推荐下一轮做 `/system` 运维诊断收口：

1. `/system` 增加 Provider 24h 只读统计，可和 `050` 的 Provider 状态数据合并设计。
2. `/system/ws-initial` 顶部增加按 `newer_than_cursor` 动态生成的行动指南。
3. 设计独立分析库 `ops_notes`，允许对未确认 `unknown_timeout` 做只读人工备注，但不触碰 `delivery_log`。
4. Anthropic/SSE/mini K 线图另开主线功能阶段，不混入运维驾驶舱修复。

推荐模型：

- `GPT-5.5 中`：驾驶舱筛选/统计、ws_initial 行动指南、ops_notes 设计、mini K 线图小步实现。
- `GPT-5.5 高`：SSE 流式 Provider、Provider 调用状态机重构、自动评测框架、涉及外部源或采集链路的逻辑。

## 下一 session 可复制提示词

```text
继续 /Users/rich/jin10-monitor 项目。

先读取：
1. /Users/rich/jin10-monitor/AGENTS.md
2. /Users/rich/jin10-monitor/docs/status/051-2026-06-08-review-043-ops-cockpit-followup-handoff.md
3. /Users/rich/jin10-monitor/docs/status/050-2026-06-08-review-047-049-followup-handoff.md
4. /Users/rich/jin10-monitor/docs/status/043-2026-06-04-ops-cockpit-readonly-diagnostics-handoff.md
5. /Users/rich/jin10-monitor/docs/design/003-phase2b-phase3-spec.md

先执行：
git branch --show-current
git status
git pull --rebase
git log --oneline -8

当前结论：
- 043 review 的 P0 已接纳：/system 区分 unknown_timeout 已在 delivery_log 确认和仍需人工核对，只有未确认 timeout 或 failed 才触发 Telegram 降级。
- REST 泳道 headline 已中文化，Initial History 泳道已明确“最近快照新增”口径，ws_initial 下钻优先显示晚于游标记录。
- Hero 区已显示状态参考起点和持续时长。
- Dashboard 仍是本地只读诊断和分析侧车，不作为采集入口。
- 不请求金十 REST，不写业务历史库，不自动重发 Telegram unknown_timeout。

推荐下一步：
优先做 /system 运维诊断收口：
1. /system 增加 Provider 24h 只读统计。
2. /system/ws-initial 顶部增加行动指南。
3. 设计 ops_notes，只写独立分析库，用于人工备注 unknown_timeout。
4. Anthropic/SSE/mini K 线图另开功能阶段。

推荐模型：
- GPT-5.5 中：驾驶舱筛选/统计、ws_initial 行动指南、ops_notes、mini K 线图小步实现。
- GPT-5.5 高：SSE 流式 Provider、Provider 状态机重构、自动评测框架、外部源/采集链路逻辑。
```
