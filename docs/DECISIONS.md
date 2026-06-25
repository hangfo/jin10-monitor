更新时间：2026-06-26 00:54（Asia/Shanghai）

# 项目决策记录

本文记录当前仍有效的架构和产品决策。新决策应追加到对应主题下，保留背景、结论和影响范围。

## 1. Dashboard 采用独立服务路线

结论：

- 正式 Dashboard 继续使用 `run_dashboard.py` + `dashboard/`。
- `jin10_monitor.py --dashboard` 不继续扩展，仅保留为引导用户使用独立 Dashboard 的 fallback。

原因：

- 采集主路和本地观察工具职责不同，拆开后更容易保证 WebSocket、REST、Telegram 主路稳定。
- Dashboard 可独立做只读查询、AI 分析草稿、Provider 调用状态和系统诊断，而不牵动采集进程。

影响范围：

- 新 Dashboard 功能优先落在 `dashboard/`。
- 除非任务明确是采集事故修复，不应修改 WebSocket、REST 或 Telegram 主链路。

## 2. Provider 分析与业务历史库隔离

结论：

- `/analyze` 的 Provider 保存状态写 `data/dashboard_analysis.sqlite3`。
- Provider A/B CLI 的结果只写 `exports/provider_ab*/<run_id>/`。
- A/B 结果不自动写回 `analysis_runs`，也不写 `data/history.sqlite3`。

原因：

- A/B 评测是模型质量复盘，不应污染业务历史库或已完成分析记录。
- 保持导出目录可删除、可重跑、可人工检查，风险更低。

影响范围：

- `scripts/run_ab_eval.py` 不请求金十 REST，不触发 Telegram。
- 自动脚本只记录运行客观字段，人工质量判断留在 `ab_scorecard.md`。

## 3. Provider A/B 当前基线为 Gemini + GLM

结论：

- 当前自动 A/B 默认 Provider 是 `gemini compatible`。
- Gemini 默认关闭 thinking，并提高 JSON 输出上限。
- GLM/智谱 OpenAI-compatible 默认关闭 `thinking.type`。
- Anthropic Provider 暂不作为当前基线。

原因：

- 真实复测显示 Gemini 与 GLM 在修复后都能稳定输出可解析 JSON。
- 当前主要问题已从 JSON 稳定性转为 judgement 口径和证据归因质量。

影响范围：

- 后续比较优先围绕 Gemini vs GLM 的人工 scorecard。
- 如要改 judgement Prompt，应小步修改并补测试。

## 4. `comparison.md` 只做客观汇总

结论：

- 同一 `run_id` 至少有两个 Provider 结果时，A/B CLI 可生成 `comparison.md`。
- `comparison.md` 只汇总 status、model、judgement、confidence、catalysts/missing 数量、JSON 稳定性、耗时、Token、finish reason 和错误。
- `pass` / `watch` / `fail` 仍由人工 scorecard 决定。

原因：

- 自动汇总可以降低打开多个 JSON 文件的成本。
- 关键催化是否命中、缺失证据是否合理、行情方向是否一致，仍需要人工判断。

影响范围：

- 暂不做自动投票系统。
- 暂不根据 A/B 输出自动改 Provider 优先级。

## 5. 运行诊断必须只读优先

结论：

- `/system`、`/api/system/log-events`、`/api/aggregation/stats` 等诊断能力默认只读。
- 日志 level 过滤只筛选本地日志扫描结果，不改变缓存、刷新或采集逻辑。
- 聚合统计刷新只读业务库，不触发聚合、不写库。

原因：

- 运维页面的职责是定位问题，不应制造新的外部请求或副作用。
- 只读诊断更适合在生产状态不明时使用。

影响范围：

- 新诊断功能必须明确是否读取历史库、分析库、日志文件或 runtime state。
- 涉及 REST、Telegram 或补拉动作的功能必须单独设计和确认。

## 6. 健康心跳是诊断信号

结论：

- 健康心跳用于确认常驻进程在线，不代表新闻投递。
- 心跳状态不能写入 `delivery_log`。
- Telegram 逐条投递真相仍以 `delivery_log` 为准。

原因：

- 把诊断消息混入新闻投递语义会误导 `/system` 和人工排障。

影响范围：

- `/system` 判断 Telegram 健康时，需要区分 confirmed 与 unconfirmed timeout。
- 后续健康检查增强不得污染实时新闻去重或投递记录。

