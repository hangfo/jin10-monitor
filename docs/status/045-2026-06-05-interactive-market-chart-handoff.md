更新时间：2026-06-05 22:12（Asia/Shanghai）

# 项目状态摘要 045：交互 K 线图体验收口

日期：2026-06-05

## 1. 本摘要用途

本摘要接续 `044` Provider Adapter 与 review 修复收口，记录 `/item/{id}` 行情上下文面板从 mini 折线图升级到交互 K 线图后的体验修复、验证结果和下一 session 入口。

本轮目标：

- 让小白能直观看懂快讯前后价格变化。
- 让开发能通过同一面板看到 K 线数量、窗口边界、成交量和明细。
- 保持 Dashboard 只读侧车边界，不影响采集、Telegram、REST 或业务历史库。

## 2. 当前仓库状态

本摘要生成前 HEAD：

```text
37480bf feat(dashboard): add interactive market chart
```

本轮变更准备提交，涉及：

- `/item/{id}` 行情窗口分钟边界对齐。
- `/item/{id}` 交互 K 线图 UI 修复。
- Binance market adapter 秒级窗口扩展。
- 图表相关回归测试。
- `CHANGELOG.md`、`docs/design/007` 和本摘要。

当前正式 Dashboard 入口仍是：

```text
http://127.0.0.1:8765/
```

## 3. 已完成内容

### 3.1 K 线窗口数量修复

已完成。

行为：

- 秒级开始时间向下取整到 K 线边界。
- 秒级结束时间向上取整到 K 线边界。
- `±15m` 对秒级快讯窗口返回 32 根 1m K 线。
- `±60m` 对秒级快讯窗口返回 122 根 1m K 线。

原因：

- 快讯时间通常带秒，Binance K 线以分钟开盘时间为边界。
- 如果直接用秒级 start/end，请求会漏掉首尾所在分钟。

### 3.2 快讯时间竖线修复

已完成。

行为：

- 快讯竖线锚定到“快讯发生时刻所在 K 线”。
- 竖线随左右拖动和缩放移动。
- 竖线移出当前可视时间范围后隐藏，避免溢出到横轴外。
- 竖线底部按成交量 0 轴动态截断，不穿过时间轴。

### 3.3 价格 / 成交量分区修复

已完成。

行为：

- 上方 pane 展示价格 K 线。
- 下方 pane 展示成交量。
- 成交量有独立右侧刻度。
- 隐藏 TradingView attribution logo。
- 使用自定义分割线区分价格区和成交量区，避免库内置 separator 越过右侧轴或遮挡价格。

### 3.4 输入和摘要体验

已完成。

行为：

- `±5m/±15m/±30m/±60m` 按钮位于行情面板顶部。
- 点击窗口按钮后定位回 `#market-panel`。
- 开始 / 结束时间使用原生 `datetime-local` 控件。
- 横轴刻度自适应显示 `HH:mm`。
- hover 提示保留完整北京时间和中文 OHLCV 文案。
- 摘要卡片展示快讯前收盘、末根收盘、快讯后涨跌、窗口高低、成交量合计、最大单根成交量、K 线数量。

## 4. 验证结果

已执行：

```bash
.venv/bin/python -m pytest tests/test_dashboard_analysis.py tests/test_market_adapter.py
.venv/bin/python -m pytest
git diff --check
.venv/bin/python -m py_compile dashboard/app.py dashboard/market/binance.py
launchctl kickstart -k gui/$(id -u)/com.rich.jin10-dashboard
curl -sS -o /tmp/jin10_item.html -w '%{http_code}' 'http://127.0.0.1:8765/item/20260604214010904800?minutes=30#market-panel'
curl -sS 'http://127.0.0.1:8765/api/market/klines?symbol=BTCUSDT&interval=1m&start=2026-06-04%2021:25:10&end=2026-06-04%2021:55:10'
```

结果：

- 全量 pytest：`179 passed`
- 页面 smoke：`200`
- 行情 API：`True 32 2026-06-04 21:25:00 2026-06-04 21:56:00`
- `git diff --check`：通过
- `py_compile`：通过

## 5. 边界保持

未改变：

- 不改 WebSocket 采集链路。
- 不改 REST 采集链路。
- 不改 Telegram 去重或发送逻辑。
- 不写业务历史库。
- 不从首页批量请求行情。
- Dashboard 仍是本地只读诊断和分析侧车。

## 6. 未做事项

仍未做：

- 删除 `jin10_monitor.py` 内旧版 Dashboard 死代码。
- Provider 真实 key 试用。
- 分析历史和对比页展示 `model_label`。
- 把交互 K 线图复用到 `/analyze` preview。
- Vision 自动截图分析。
- WebSocket initial history 自动短缺口恢复。
- REST source adapter 或外部新闻源 probe。

## 7. 下一步建议

推荐优先级：

1. Provider 真实 key 试用和 `model_label` 展示。
   - 用 Gemini 免费层或 GLM Flash 先跑一次 `/analyze`。
   - 在分析历史、分析详情、对比页显示 Gemini / GLM / DeepSeek / Anthropic 来源。
   - 推荐模型：GPT-5.5 中。

2. 将交互 K 线图复用到 `/analyze` preview。
   - 让证据包预览也能直接看到行情。
   - 不新增采集链路，不写业务库。
   - 推荐模型：GPT-5.5 中。

3. 删除旧版 Dashboard 死代码。
   - 单独做一轮，不混入功能开发。
   - 先确认 `jin10_monitor.py --dashboard` fallback 处理方式。
   - 推荐模型：GPT-5.5 高。

4. Provider / Vision / 外部源扩展。
   - 只在需要真实自动分析能力时推进。
   - 涉及外部 API、费用、稳定性和边界管理。
   - 推荐模型：GPT-5.5 高。

## 8. 下一 session 复制提示词

```text
继续 /Users/rich/jin10-monitor 项目。

先读取：
1. /Users/rich/jin10-monitor/AGENTS.md
2. /Users/rich/jin10-monitor/docs/status/045-2026-06-05-interactive-market-chart-handoff.md
3. /Users/rich/jin10-monitor/docs/status/044-2026-06-04-provider-adapter-review-handoff.md
4. /Users/rich/jin10-monitor/docs/design/007-provider-adapter-and-review-followup-plan.md
5. /Users/rich/jin10-monitor/docs/design/003-phase2b-phase3-spec.md

先执行：
git branch --show-current
git status
git pull --rebase
git log --oneline -8

当前结论：
- Provider Adapter 第一版已完成，支持 Anthropic、Gemini、OpenAI-compatible、OpenAI；默认无 key 不请求模型 API。
- `/item/{id}` 行情上下文面板已升级成交互 K 线图，支持自动加载、拖动缩放、hover OHLCV、快讯时间竖线、价格/成交量独立 pane。
- K 线窗口已按分钟边界对齐，秒级快讯不会漏掉首尾 K 线。
- Dashboard 仍是本地只读诊断和分析侧车，不作为采集入口。
- 不请求金十 REST，不写业务历史库，不自动重发 Telegram unknown_timeout。

推荐下一步：
优先做 Provider 真实 key 试用和分析历史 model_label 展示：先用 Gemini 或 GLM Flash 跑一次 /analyze，再让历史、详情和对比页清楚显示模型来源。

推荐模型：
- GPT-5.5 中：Provider 真实试用、Provider 状态展示、分析历史 model_label、交互 K 线图复用到 /analyze preview。
- GPT-5.5 高：删除旧 Dashboard 死代码、Provider/Vision 深度集成、WebSocket initial history 自动短缺口恢复、任何 Telegram/SQLite 游标或外部源逻辑。
```
