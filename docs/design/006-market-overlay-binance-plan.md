更新时间：2026-06-01 22:44（Asia/Shanghai）

# 006 - Binance 行情叠加最小实施计划

## 1. 背景

当前 Dashboard 已有 `dashboard/market/` adapter 边界和 `/api/market/klines` 占位端点，但还没有真实行情数据源。

此前 `003`、`004`、`038` 和 `040` 的共同结论是：

- 行情叠加是分析体验增强，不是采集主链路。
- 不从 Dashboard 请求金十 REST。
- 不让 Dashboard 启动依赖外部行情 API。
- 不写业务历史库。
- 不影响 WebSocket、REST、Telegram 推送和去重。
- 不应从首页批量价格请求开始。

现在 WebSocket 实时主路和启动顺序已经稳定，可以推进一个隔离、可关闭、失败可降级的第一版 market overlay。

## 2. 第一版目标

先实现 Binance public REST 的只读行情叠加，用于加密货币交易对。

第一版只解决一个问题：

> 用户打开单条快讯或分析工作台时，能够手动选择交易对，查看该快讯附近的分钟级价格变化。

不做自动交易、不做实时盘口、不做全市场行情服务。

## 3. 数据源边界

第一版数据源：

- Binance public REST。
- 优先使用 `GET /api/v3/klines`。
- 可选使用 `GET /api/v3/ticker/price` 做当前价格轻量查询。

第一版交易对：

- `BTCUSDT`
- `ETHUSDT`
- `SOLUSDT`
- `BNBUSDT`

后续可以扩展，但必须仍走 adapter 白名单，不能把任意用户输入直接拼成外部请求。

## 4. 启用方式

默认不启用。

建议使用环境变量：

```bash
MARKET_ADAPTER=binance
```

未配置时：

- `/api/market/klines` 继续返回 `ok=false`、空 `klines` 和提示。
- 页面显示降级状态，不影响其他 Dashboard 功能。

## 5. 页面展示位置

### P1：`/item/{id}`

优先放在单条快讯详情页。

展示内容：

- symbol 选择器。
- interval 选择器，第一版只开放 `1m`、`5m`。
- 窗口选择，默认围绕快讯时间 `±30m`。
- 价格摘要：新闻前价格、新闻后价格、窗口高低点、涨跌幅。
- 简单分钟级时间线或小型表格。

失败时展示：

- `market data unavailable`
- adapter 名称
- 错误摘要

不阻塞快讯正文和上下文时间线。

### P2：`/analyze`

第二步加入分析工作台。

用途：

- 用户选择 asset、时间窗口和 symbol 后，附加一段可选 market context。
- market context 可以加入 prompt 的“外部行情上下文”段落。
- evidence boundary 必须标明 `market_data_called=true`。

注意：

- 不让行情成为 evidence packet 生成的前置条件。
- 没有行情数据时，手工 AI 分析流程必须继续可用。

### 暂不做：首页 feed

首页不做批量行情请求。

原因：

- 首页是实时快讯流，批量外部请求会拖慢页面。
- 一条新闻未必能稳定映射到交易对。
- 容易让 Dashboard 再次出现“刷新慢”的感知问题。

### 暂不做：`/system` 行情列表

`/system` 只适合展示配置状态和最近错误，不展示行情本身。

## 6. Adapter 设计

新增：

```text
dashboard/market/binance.py
```

保留现有接口：

```python
class BaseMarketAdapter:
    def fetch_klines(self, *, symbol: str, interval: str, start: str, end: str) -> list[Kline]:
        ...
```

建议补充：

- symbol 白名单校验。
- interval 白名单校验。
- start/end 时间解析和窗口上限。
- 2-3 秒请求超时。
- 内存 TTL cache，避免重复打开同一新闻时反复请求。
- 统一把外部错误转成 `MarketAdapterError`。

## 7. 缓存策略

第一版只做进程内内存缓存。

建议 cache key：

```text
adapter:symbol:interval:start:end
```

建议 TTL：

- 历史窗口：5-15 分钟。
- 当前价格：15-30 秒。

除非单独批准，不写 SQLite 业务历史库。

## 8. 风险与降级

### Binance API 不可用

处理：

- `/api/market/klines` 返回 `ok=false`。
- 页面显示降级提示。
- 不影响 Dashboard 其他页面。

### 请求变慢

处理：

- adapter 超时控制在 2-3 秒。
- 前端请求只在用户打开详情页或点击刷新时发生。
- 不在首页自动批量请求。

### symbol 映射错误

处理：

- 第一版以用户手动选择为准。
- 仅轻量推荐，不自动替用户决定。

### 数据语义误读

处理：

- 页面明确显示 symbol、interval、窗口。
- Prompt 中必须注明行情数据来源和窗口。
- 不把价格变化直接判断为新闻因果。

## 9. 验收标准

- 未配置 `MARKET_ADAPTER` 时，Dashboard 正常启动，`/api/market/klines` 返回空降级结果。
- 配置 `MARKET_ADAPTER=binance` 时，`/api/market/klines?symbol=BTCUSDT&interval=1m&...` 返回标准化 `klines`。
- Binance 超时或失败时，API 返回 `market data unavailable`，页面不崩溃。
- `/item/{id}` 能展示一个可选行情上下文面板。
- 首页不发起行情请求。
- 不写 `data/jin10_history.sqlite3`。
- 不改变 Telegram、WebSocket、REST 和补拉逻辑。

## 10. 推荐实施步骤

### Step 1：Adapter 与 API

- 新增 `dashboard/market/binance.py`。
- 完善 `get_market_adapter()`。
- 给 `/api/market/klines` 加参数校验、错误摘要和测试。
- 覆盖未配置、未实现、Binance 成功、Binance 失败。

### Step 2：`/item/{id}` UI

- 增加可折叠的行情上下文面板。
- 默认不自动请求，或只在用户选择 symbol 后请求。
- 展示摘要和小型表格。

### Step 3：`/analyze` 可选上下文

- 允许用户把 market context 加入 prompt。
- evidence boundary 标明行情来源。
- 不改变本地 evidence packet 的必需字段。

## 11. 模型建议

- 写文档、评审边界、拆任务：`GPT-5.5 中`。
- 实现 Binance adapter、缓存、UI、测试和浏览器验证：`GPT-5.5 高`。

