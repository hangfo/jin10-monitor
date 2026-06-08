更新时间：2026-06-08 21:15（Asia/Shanghai）

# 050 - 047-049 深度 Review 跟进交接

## 本次状态

本轮根据 `/Users/rich/Downloads/jin10-review-047-049-diff.md` 对 `bf4a9b4 → de4dc32` 的 review 建议进行取舍和实现。

已接纳并实现：

- P0：服务重启后的 `running` 孤儿清理。
  - Dashboard 启动时会把遗留 `running` 分析恢复为 `draft`。
  - 草稿保留错误：`服务重启，后台任务已中断，可重新调用。`
- P0：`save_answer()` 增加 `expected_status` 状态闸门。
  - Provider 后台完成只允许 `running -> done`。
  - 手动回填只允许 `draft -> done`。
  - 如果用户或后台状态已变化，后到的写入会被跳过，避免覆盖人工结果。
- P1：`/system` 中 `info` 状态 pill 改为绿色 `sent` 样式。
  - `ws_initial` 的“补到新消息”不再显示为橙色警告。
- P1：统一 GLM Provider 检测。
  - `glm-4.7-flash`、`GLM:...`、`zhipu...` 都按 GLM 系列处理。
- P1：Binance K 线时间链路改为显式北京时间 / UTC epoch 转换。
  - Binance UTC 毫秒统一转为北京墙上时间展示。
  - 前端把北京字符串减 8 小时转成 chart UTC timestamp，显示时再加 8 小时。
- P2：过滤 Gemini thinking part。
  - `thought=true` 的 part 不再拼进最终 JSON 文本。
- UX：`running` 详情页显示已等待秒数、同 Provider 历史 P50 预计耗时，并每 6 秒自动刷新。
  - 不设置短软上限，不主动取消 GLM，继续优先保证成功率。
- UX：Provider 失败后的草稿续跑说明。
  - 失败草稿不再继续显示“Provider 已开始后台调用”。
  - 页面明确提示草稿已保留，可切换 Gemini/GLM 重新调用，也可手动粘贴严格 JSON。
  - 手工回答文本框固定浅色可输入样式，并用 placeholder 说明它不是 Prompt 输入框。
  - 历史草稿缺失 `manual_prompt` 时，Provider 重试会尝试从已保存的问题、窗口、证据列表重新生成 Prompt 并写回草稿。

## 暂缓项与理由

- 暂缓：强制重置 `running` 按钮。
  - 理由：当前启动清孤儿已解决最危险的永久卡死；手动重置按钮会引入“后台线程仍可能完成但记录已被用户重置”的并发交互，需要单独设计状态语义。
  - 建议模型：`GPT-5.5 中`。
- 暂缓：历史页状态筛选。
  - 理由：这是管理体验功能，不是本轮 P0/P1 稳定性修复；可以与草稿清理一起做，避免筛选、删除、对比入口互相打架。
  - 建议模型：`GPT-5.5 中`。
- 暂缓：Provider 24h 调用统计进入 `/system`。
  - 理由：需要定义统计口径（失败草稿、手动回填、旧记录 `provider_name` 为空怎么归类），适合单独做只读统计小阶段。
  - 建议模型：`GPT-5.5 中`。
- 暂缓：`diversity_key` 短内容 hash。
  - 理由：review 评估为影响有限；当前 v2/v3 默认选择的主要风险仍是 Provider 输出和状态管理，不急于调整证据排序。
  - 建议模型：`GPT-5.5 中`。
- 暂缓：GLM 双重指令重构。
  - 理由：本轮已通过本地 guard 和统一 GLM 检测降低风险；改变 system/user prompt 拼接方式会影响 A/B 可比性，应配合固定 packet 评测单独做。
  - 建议模型：`GPT-5.5 高`。

## 边界

本轮保持：

- 不请求金十 REST。
- 不修改 WebSocket / REST / Telegram 采集或发送逻辑。
- 不写业务历史库。
- 不自动重发 Telegram `unknown_timeout`。
- 不降低 `PROVIDER_TIMEOUT_SECONDS`，不增加 GLM 短软上限。
- 只写独立分析库 `data/dashboard_analysis.sqlite3` 的分析记录状态。

## 验证

已执行：

```bash
.venv/bin/python -m py_compile dashboard/app.py dashboard/analysis_db.py dashboard/providers/gemini_provider.py dashboard/market/binance.py
.venv/bin/python -m pytest tests/test_dashboard_analysis.py tests/test_market_adapter.py -q
.venv/bin/python -m pytest tests/test_dashboard_analysis.py -q
```

当前结果：

- `py_compile`：通过
- 聚焦测试：78 passed
- Provider 失败草稿 UX 聚焦测试：64 passed

全量 pytest、`git diff --check` 和浏览器烟测将在提交前执行。

## 下一步建议

推荐下一轮做历史管理收口：

1. 历史页状态筛选：全部 / 调用中 / 草稿 / 已完成 / 最近失败。
2. 草稿删除策略：先明确是否只允许删除 `draft`，还是继续允许删除所有分析记录。
3. `/system` Provider 统计：最近 24h 调用次数、失败次数、平均 / P50 / 最大耗时、最近错误。
4. 如果继续做 GLM Prompt 重构，必须先固定 3-5 个 evidence packet 做 A/B，避免模型漂移被误认为工程改动效果。

推荐模型：

- `GPT-5.5 中`：历史状态筛选、草稿管理、Provider 只读统计、running UI 小修。
- `GPT-5.5 高`：GLM Prompt 结构重构、自动评测框架、embedding / 向量相似度、Vision 或任何外部源 / 采集链路逻辑。

## 下一 session 可复制提示词

```text
继续 /Users/rich/jin10-monitor 项目。

先读取：
1. /Users/rich/jin10-monitor/AGENTS.md
2. /Users/rich/jin10-monitor/docs/status/050-2026-06-08-review-047-049-followup-handoff.md
3. /Users/rich/jin10-monitor/docs/status/049-2026-06-08-provider-background-status-handoff.md
4. /Users/rich/jin10-monitor/docs/status/048-2026-06-08-glm-provider-ux-handoff.md
5. /Users/rich/jin10-monitor/docs/design/007-provider-adapter-and-review-followup-plan.md

先执行：
git branch --show-current
git status
git pull --rebase
git log --oneline -8

当前结论：
- 047-049 review 的 P0 已接纳：服务启动清理 running 孤儿，save_answer 增加 expected_status，避免后台结果覆盖人工结果。
- running 页面已显示已等待时间、历史 P50 估算，并自动刷新；未增加 GLM 软上限，继续优先保证成功率。
- Provider 失败草稿页已明确提示可换 Gemini/GLM 重试或粘贴 JSON；失败后不再显示“后台调用已开始”；历史草稿缺 Prompt 时会尝试重建并写回。
- 已接纳 pill info 绿色、GLM 检测统一、Gemini thought 过滤、Binance 北京时间/UTC 显式转换。
- Dashboard 仍是本地只读诊断和分析侧车，不作为采集入口。
- 不请求金十 REST，不写业务历史库，不自动重发 Telegram unknown_timeout。

推荐下一步：
优先做历史管理收口：
1. 历史页状态筛选：全部 / 调用中 / 草稿 / 已完成 / 最近失败。
2. 明确草稿删除策略，再决定是否限制删除 done 记录。
3. /system 增加只读 Provider 调用统计。
4. GLM Prompt 结构重构先暂缓，除非配套固定 packet A/B。

推荐模型：
- GPT-5.5 中：历史筛选、草稿管理、Provider 只读统计、running UI 小修。
- GPT-5.5 高：GLM Prompt 结构重构、自动评测框架、embedding/向量相似度、Vision 或外部源/采集链路逻辑。
```
