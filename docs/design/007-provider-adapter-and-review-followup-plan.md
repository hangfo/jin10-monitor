更新时间：2026-06-05 22:12（Asia/Shanghai）

# 007 - Provider Adapter 与 Review 后续计划

## 1. 背景

本计划接续 `042` 和 `043`，同时吸收 `/Users/rich/Downloads/jin10-monitor-review-042.md` 的代码 review 建议。

本阶段目标不是扩展采集链路，而是把 Dashboard 从“手工复制 Prompt”推进到“可配置 Provider 一键分析”的第一版，同时修复 review 中两个可低风险落地的真实 Bug。

继续保持边界：

- Dashboard 不作为采集入口。
- 不从 Dashboard 请求金十 REST。
- 不写业务历史库。
- 不发送、不重试、不补发 Telegram。
- Provider 调用只写独立 `data/dashboard_analysis.sqlite3`。

## 2. 本轮采纳

### P0：SQL LIKE 通配符转义

采纳。

原因：

- `keyword` 来自用户输入，包含 `%` 或 `_` 时会被 SQLite `LIKE` 当作通配符。
- 这会让搜索、分页和最新时间查询结果失准。

实施：

- 新增 `escape_like()`。
- 所有关键字 `LIKE` 查询统一追加 `ESCAPE '\\'`。
- 关键词热力图也统一转义，避免后续内置关键词包含特殊字符时行为漂移。

### P0：Binance Adapter 并发缓存穿透

采纳。

原因：

- `/analyze/preview` 可能通过 `asyncio.to_thread` 触发多个同窗口行情请求。
- 多个请求同时未命中缓存时，会并发打到 Binance public REST。

实施：

- 为同一 cache key 增加 in-flight 去重。
- 第一个线程负责请求，后续线程等待缓存结果。
- 如果首个请求失败，等待者得到明确 adapter 错误，不返回假空行情。

### Provider Adapter 第一版

采纳，但按“显式配置、显式点击、失败可降级”落地。

实施：

- `AnthropicProvider`：直连 Anthropic Messages API。
- `GeminiProvider`：直连 Gemini API，作为免费优先试用项。
- `OpenAICompatibleProvider`：支持 DeepSeek / GLM 等兼容 `/chat/completions` 的厂商。
- `OpenAIProvider`：保留为备用直连 provider。
- `/analyze` 生成 Prompt 后，如果存在可用 Provider，显示“调用并保存”。
- `/analyze/{run_id}` 草稿页同样支持显式调用。
- 自动调用结果只写分析库，并保存 `model_label`。

### 交互 K 线图

采纳。

实施：

- 第一版放在 `/item/{id}` 行情上下文面板。
- 使用本地 vendored `lightweight-charts@5.2.0`。
- 页面打开后自动加载当前详情窗口行情。
- 展示蜡烛图、成交量、hover OHLCV、拖动缩放和快讯时间竖线。
- `±5m/±15m/±30m/±60m` 窗口按钮放在行情图上方，点击后定位回行情面板。
- 图表横轴自适应显示 `HH:mm`，hover 提示保留完整北京时间。
- 秒级快讯窗口扩展到完整 K 线边界，避免预设和自定义窗口少算首尾蜡烛。
- 快讯时间竖线锚定到快讯所在 K 线，随拖动和缩放移动；移出当前可视时间范围后隐藏，底部按成交量 0 轴动态截断且不穿过时间轴。
- 成交量使用独立 pane、独立右侧刻度和自定义价格/成交量分割线，隐藏 TradingView attribution logo，避免分割线遮挡右侧价格轴。
- 开始 / 结束时间改用原生 `datetime-local` 控件。
- 摘要指标聚焦快讯前后变化和成交量，而不是重复展示数据来源。
- K 线明细表默认折叠。
- 不新增后端 API，不首页批量请求行情。

## 3. 免费 / 低成本模型选择

### 推荐试用顺序

1. Gemini API：优先申请。
2. GLM Flash：国内备选，尤其适合中文和低成本试验。
3. DeepSeek：极低价 API 备选，但不是稳定免费层。
4. Anthropic：能力强，等确认付费预算后再启用。

### 依据

- Google Gemini API pricing 页面显示 `gemini-2.5-flash` 和 `gemini-2.5-flash-lite` 仍有 Free Tier，适合先试一键分析效果。
- DeepSeek 官方文档显示 `deepseek-v4-flash` 使用 OpenAI-compatible base URL `https://api.deepseek.com`，价格极低，但按 tokens 计费，不应视为免费。
- 智谱 GLM 文档显示 GLM-4.5-Flash 标注为“免费 高效 多功能”，并支持 OpenAI-compatible `https://open.bigmodel.cn/api/paas/v4/chat/completions`。
- Anthropic Sonnet 4.6 能力强，但官方价格仍是按 token 付费。

### 推荐环境变量

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

## 4. 本轮暂不采纳

### 删除旧版 Dashboard 死代码

暂不直接删除。

原因：

- 删除范围约 590 行，且 `jin10_monitor.py --dashboard` 仍是历史 fallback 参数。
- 这属于大 refactor，应单独建一轮变更：先确认 fallback 是否废弃，再删除入口、旧 handler、旧 HTML，并跑主链路回归。

建议下一轮：

1. 搜索 `--dashboard`、旧 HTTP server、旧 dashboard handler 全部引用。
2. 明确替代方案：只保留 `run_dashboard.py`，或 `--dashboard` 改为提示用户启动独立 Dashboard。
3. 单独提交 `refactor(monitor): remove legacy dashboard server`。

### `save_history_item` Upsert 拆分

暂不直接改。

原因：

- 这是业务写入链路，影响 SQLite 历史库和优先级覆盖语义。
- 虽然 review 指出的参数人工对齐风险成立，但需要先补针对优先级升级 / 不降级的回归测试。

建议作为 P1 单独处理，使用 `GPT-5.5 高`。

### Multipart 解析器替换

暂不直接改。

原因：

- 影响截图上传路径和已存图片体验。
- 需要同时补文件头 magic bytes 检测、multipart 边界测试和浏览器上传回归。

建议作为 P1 安全加固，使用 `GPT-5.5 中` 或 `GPT-5.5 高`。

## 5. 后续优先级

### P0 / 下一步

1. 验证 Gemini API 真实 key 的一键分析效果。
2. 给分析历史页展示 `model_label`，便于比较 Gemini / GLM / DeepSeek 输出质量。
3. 给 Provider 调用增加更友好的失败展示：HTTP 状态、厂商、模型、耗时。

推荐模型：`GPT-5.5 中`。

### P1

1. 将交互 K 线图复用到 `/analyze` preview。
2. Multipart 上传安全加固。
3. `save_history_item` upsert 拆分和优先级回归测试。

推荐模型：`GPT-5.5 高`，其中 mini chart 可用 `GPT-5.5 中`。

### P2

1. 旧 Dashboard 死代码删除。
2. Provider 输出质量 A/B 对比页。
3. Vision 自动截图分析。

推荐模型：删除旧代码用 `GPT-5.5 中`，Vision 用 `GPT-5.5 高`。
