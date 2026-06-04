更新时间：2026-06-04 20:20（Asia/Shanghai）

# 项目状态摘要 044：Provider Adapter 与 Review 修复收口

日期：2026-06-04

## 1. 本摘要用途

本摘要接续 `043` 运维驾驶舱只读诊断收口之后，记录代码 review 建议的采纳结果、Provider Adapter 第一版落地状态、当前验证结果，以及换 session 后不要遗漏的后续任务。

本轮输入：

- `/Users/rich/Downloads/jin10-monitor-review-042.md`
- 用户明确要求评估 review 建议，能采纳则并入代码。
- 用户要求同时开发 Anthropic Adapter 和可免费/低成本试用的类似 LLM Adapter。

本轮核心结论：

- 可低风险落地的两个真实 Bug 已修复。
- Provider Adapter 第一版已落地。
- 行情面板 Canvas mini 折线图已在本轮追加完成。
- 删除旧 Dashboard 死代码暂不混入本轮，应单独 refactor。

## 2. 当前仓库状态

本摘要生成前 HEAD：

```text
fcfb758 docs(status): add ops diagnostics handoff
```

本轮变更准备提交，涉及：

- Dashboard 搜索准确性修复。
- Binance market adapter 并发缓存去重。
- LLM Provider Adapter。
- `/analyze` 一键调用 Provider 并保存分析结果。
- `.env.example` Provider 配置示例。
- review 后续计划文档 `007`。
- `/item/{id}` 行情面板 Canvas mini 折线图。
- 本项目状态摘要 `044`。

当前正式 Dashboard 入口仍是：

```text
http://127.0.0.1:8765/
```

本轮为验证页面，启动了独立 Dashboard LaunchAgent：

```text
com.rich.jin10-dashboard
```

它只运行 `run_dashboard.py --host 127.0.0.1 --port 8765`，不启动采集、不请求金十 REST、不发送 Telegram。

## 3. 已完成内容

### 3.1 SQL LIKE 通配符修复

已完成。

修复范围：

- `query_recent_items`
- `query_feed_page`
- `query_latest_published_at`
- `query_keyword_heatmap`

行为变化：

- 用户搜索 `%`、`_`、`\` 时按字面量匹配。
- 避免 `BTC_` 匹配 `BTCA`、`50%收益` 匹配 `50X收益`。
- 只影响 Dashboard 只读查询结果准确性，不影响业务库写入。

验证：

- 新增 `test_query_keyword_escapes_sql_like_wildcards`。
- 全量 pytest 已通过。

### 3.2 Binance Adapter 并发缓存穿透修复

已完成。

修复方式：

- 为同一 cache key 增加 in-flight 去重。
- 第一个线程负责真实请求。
- 后续线程等待缓存结果。
- 如果首个请求失败，等待者收到明确 `MarketAdapterError`，不返回假空行情。

边界：

- 不改变 Binance endpoint。
- 不扩大交易对白名单。
- 不让首页自动请求行情。
- 不写业务库。

验证：

- 新增 `test_binance_adapter_deduplicates_concurrent_cache_misses`。
- 全量 pytest 已通过。

### 3.3 Provider Adapter 第一版

已完成。

新增 / 实现：

- `dashboard/providers/http_json.py`
- `dashboard/providers/gemini_provider.py`
- `dashboard/providers/compatible_provider.py`
- `dashboard/providers/anthropic_provider.py`
- `dashboard/providers/openai_provider.py`

支持：

- Anthropic Messages API。
- Gemini API。
- OpenAI-compatible `/chat/completions`，用于 DeepSeek / GLM 等。
- OpenAI 备用 provider。

默认行为：

- 没有 API key 时不发起模型请求。
- `/system` 只显示配置状态。
- `/analyze` 和 `/analyze/{run_id}` 只在存在可用 Provider 时显示“调用并保存”。

写入边界：

- Provider 结果只写 `data/dashboard_analysis.sqlite3`。
- 不写 `data/jin10_history.sqlite3`。
- 不请求金十 REST。
- 不发送、不重试、不补发 Telegram。

验证：

- 新增 provider response parse 单测。
- `/system`、`/analyze`、`/healthz` 在 8765 烟测 200。
- 全量 pytest 已通过。

### 3.4 Canvas mini 折线图

已完成。

完成位置：

- `/item/{id}` 行情上下文面板。

行为：

- 仍然只在用户点击“加载行情”后请求 `/api/market/klines`。
- 成功返回 K 线后展示 close 走势 mini 折线图。
- 按首尾 close 判断涨跌颜色。
- 展示快讯发布时间竖线标记。
- 保留行情摘要和 K 线表格。

边界：

- 不新增后端 API。
- 不首页批量请求行情。
- 不写业务历史库。
- 不影响 `/analyze` Prompt 流程。

验证：

- 模板测试新增 `market-chart` / `drawMarketChart` / `data-news-time` 断言。
- 全量 pytest 已通过。

## 4. 免费 / 低成本 LLM 选型

推荐顺序：

1. Gemini：优先申请和试用。
2. GLM Flash：中文与国内访问备选。
3. DeepSeek：低价 OpenAI-compatible 备选。
4. Anthropic：能力强，但等付费预算明确后再启用。

建议配置：

Gemini：

```bash
GEMINI_API_KEY=...
GEMINI_MODEL=gemini-2.5-flash
```

DeepSeek：

```bash
COMPAT_LLM_LABEL=DeepSeek
COMPAT_LLM_BASE_URL=https://api.deepseek.com
COMPAT_LLM_API_KEY=...
COMPAT_LLM_MODEL=deepseek-v4-flash
```

GLM：

```bash
COMPAT_LLM_LABEL=GLM
COMPAT_LLM_BASE_URL=https://open.bigmodel.cn/api/paas/v4
COMPAT_LLM_API_KEY=...
COMPAT_LLM_MODEL=glm-4.5-flash
```

Anthropic：

```bash
ANTHROPIC_API_KEY=...
ANTHROPIC_MODEL=claude-sonnet-4-6
```

## 5. 本轮明确未做

### 5.1 删除旧版 Dashboard 死代码

未做。

原因：

- `jin10_monitor.py --dashboard` 仍是历史 fallback。
- 删除约 590 行旧 HTTP Dashboard，属于大 refactor。
- 应单独确认后做，避免把大删除混进 Provider / Bugfix。

建议：

- 单独一轮 `refactor(monitor): remove legacy dashboard server`。
- 或先把 `--dashboard` 改为提示使用 `run_dashboard.py`，再删除旧 server。

推荐模型：`GPT-5.5 中`。

### 5.2 `save_history_item` Upsert 拆分

未做。

原因：

- 影响业务历史库写入和 priority/style_flags 覆盖语义。
- 需要先补充优先级升级、不降级、style_flags 保留的回归测试。

推荐模型：`GPT-5.5 高`。

### 5.3 Multipart 上传解析器替换

未做。

原因：

- 影响截图上传路径。
- 应同时加入标准库 multipart 解析、magic bytes MIME 校验和浏览器上传回归。

推荐模型：`GPT-5.5 中` 或 `GPT-5.5 高`。

### 5.4 时区系统性治理

未做。

原因：

- 当前系统大量使用本地时间假设。
- 这是全局行为改动，需单独盘点 SQLite、WebSocket、REST、market adapter 和 Dashboard 展示。

推荐模型：`GPT-5.5 高`。

### 5.5 `/system` 查询性能优化

未做。

原因：

- 当前 P0 是功能和可读性。
- window function / 大表扫描优化应在观察到页面变慢后再做。

推荐模型：`GPT-5.5 中`。

### 5.6 Evidence scoring 归一化

未做。

原因：

- 会影响分析证据排序和 Prompt 输入质量。
- 需要先定义可解释的评分标尺。

推荐模型：`GPT-5.5 中`。

### 5.7 Provider 输出质量 A/B 对比页

未做。

原因：

- 需先有 Gemini / GLM / DeepSeek 的真实样本。
- 可以复用现有 `/analyze/compare`，但需要补 `model_label` 展示和筛选。

推荐模型：`GPT-5.5 中`。

## 6. 验证结果

代码验证：

```text
python -m py_compile ... 通过
git diff --check 通过
PYTHONPATH=. pytest
177 passed
```

页面验证：

```text
GET http://127.0.0.1:8765/system 200
GET http://127.0.0.1:8765/analyze 200
GET http://127.0.0.1:8765/healthz 200
```

`/healthz` 仍显示：

```text
writes_business_db=false
calls_jin10_rest=false
sends_telegram=false
```

## 7. 推荐下一步

### P0：Provider 真实试用

申请 Gemini API key，配置 `.env`，重启 Dashboard 后走一次真实 `/analyze`。

观察：

- 输出是否符合 JSON。
- `parse_answer()` 是否能稳定解析。
- Gemini 对中文宏观/加密新闻的归因质量。

推荐模型：`GPT-5.5 中`。

### P0：分析历史展示 `model_label`

让 `/analyze/history` 和 `/analyze/compare` 展示模型来源，方便后续比较 Gemini / GLM / DeepSeek。

推荐模型：`GPT-5.5 中`。

## 8. 下一 session 建议 Prompt

```text
继续 /Users/rich/jin10-monitor 项目。

先读取：
1. AGENTS.md
2. docs/status/044-2026-06-04-provider-adapter-review-handoff.md
3. docs/design/007-provider-adapter-and-review-followup-plan.md
4. docs/design/006-market-overlay-binance-plan.md
5. docs/design/003-phase2b-phase3-spec.md

先执行：
git branch --show-current
git status
git pull --rebase
git log --oneline -8

当前结论：
- Review 中 SQL LIKE 通配符修复、Binance 并发缓存去重、Provider Adapter 第一版已完成。
- Provider 支持 Anthropic、Gemini、OpenAI-compatible、OpenAI；默认无 key 不请求模型 API。
- Dashboard 仍是本地只读诊断和分析侧车，不作为采集入口。
- 不请求金十 REST，不写业务历史库，不自动重发 Telegram unknown_timeout。
- 行情面板 Canvas mini 折线图已完成，`/item/{id}` 点击加载行情后会展示 close 折线和快讯时间标记。

推荐下一步：
优先做 Provider 真实 key 试用和分析历史 `model_label` 展示：先用 Gemini API key 跑一次 `/analyze`，再让历史和对比页清楚显示 Gemini / GLM / DeepSeek / Anthropic 来源。

推荐模型：
- GPT-5.5 中：Provider 真实试用、Provider 状态展示、分析历史 model_label、Canvas 复用到 `/analyze` preview。
- GPT-5.5 高：save_history_item upsert 拆分、时区系统治理、任何业务写入链路或 Telegram/SQLite 游标改动。
```
