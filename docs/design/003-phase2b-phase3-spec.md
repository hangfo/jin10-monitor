# Dashboard Phase 2B / Phase 3 规格

日期：2026-05-25

更新时间：2026-05-31（Asia/Shanghai）

## 1. 目的

本文冻结 Phase 2A 之后的下一阶段 Dashboard 开发边界。
它是在 `002-dashboard-ai-full-spec.md` 基础上的延伸，不替代原文档。

Phase 2A 已完成：

- 独立 FastAPI/Jinja2 dashboard
- 本地只读 evidence packet 构建器
- 手工 ChatGPT Business / Custom GPT prompt 流程
- 独立 `data/dashboard_analysis.sqlite3`
- 分析历史和可追溯的 `/item/{id}` 链接

下一阶段必须继续保持相同安全姿态：

- dashboard 仍是本地 sidecar 工具
- 业务历史库仍保持只读
- 手工 AI 流程仍保持可用
- 模型 API 只是可选 adapter，不是启动要求
- Telegram 语义必须受保护

## 2. 全局边界

始终保持：

- dashboard 代码不写业务历史库
- dashboard 不触发金十 REST 补拉
- dashboard 不触发 WebSocket 连接
- dashboard 不触发 Telegram 重发或重试
- 打开 dashboard 页面不要求 provider API key
- 不删除或削弱手工复制粘贴分析流程

如果某个功能需要改 `jin10_monitor.py`，必须放在独立 commit 中，并且包含变更前后默认行为不变的测试。

## 3. Phase 3A - Telegram Dashboard 深链

### 目标

每条 Telegram 推送可以可选地附带一个本地 dashboard 链接，指回原始快讯详情页：

```text
http://127.0.0.1:8765/item/{news_id}
```

### 配置

新增可选环境变量：

```text
DASHBOARD_URL=http://127.0.0.1:8765
```

规则：

- `DASHBOARD_URL` 为空或未设置时，Telegram 消息文本必须保持不变
- 设置 `DASHBOARD_URL` 时，在消息中追加 dashboard 链接
- 追加 `/item/{id}` 前先去掉尾部斜杠
- 不改变 Telegram 去重 key
- 不改变 `delivery_log`
- 不新增 callback receiver 或 inbound Telegram 处理

### 实现范围

可能涉及文件：

- `jin10_monitor.py`
- `.env.example`
- `README.md`
- 覆盖 `format_message()` 的测试

### 验收

- 测试证明未设置 `DASHBOARD_URL` 时默认格式化消息不变
- 测试证明配置 URL 后只追加一个 `/item/{id}` 链接
- 不改变发送、重试、补发行为

## 4. Phase 3B - 快讯流无限加载

### 目标

快讯流首屏应快速加载，并且可以在不手动刷新页面的情况下继续阅读更多历史。

这是单列时间线 / 无限加载功能，不是多列 masonry 布局。

### 推荐 UX

- 首屏：50 条
- 自动追加：每次请求 30 条
- 自动上限：500 条可见消息
- 达到上限后：显示手动“load more”操作，或用清晰标签停止继续加载
- 保留当前筛选：priority、keyword、hours、仅 Telegram 已发送、status

### 后端

新增只读端点：

```text
GET /api/feed/page?offset=N&limit=30&...
```

可选方案：

- 返回由小型 row partial 渲染的 HTML 片段
- 或返回 JSON 并在客户端渲染

如果 HTML partial 能保持 Jinja 模板样式一致，并避免在 JavaScript 中重复渲染规则，则优先使用 HTML partial。

### 负载与压力

预期压力较低：

- 只读 SQLite
- 有界 `LIMIT/OFFSET`
- 本地 dashboard

缓解措施：

- 将 `limit` 上限限制为 50
- 将自动加载总行数限制为 500
- 复用现有筛选归一化逻辑
- 避免轮询和无限加载互相打架；分页请求进行中时 auto-refresh 不应 reload

### 验收

- 初始页面在没有 JavaScript 时仍可工作
- 滚动会追加更多行
- 筛选条件保持不变
- 不写业务 DB
- 除本地 dashboard 外不发生网络调用

## 5. Phase 3C - 截图上传与手工描述

### 目标

允许用户给分析记录附加一张图表截图，并手工描述图表内容。

这个阶段不需要模型 API。

### 当前资产

分析数据库已经有：

```text
screenshots(id, file_path, original_filename, user_description, uploaded_at)
```

以及保存截图的辅助代码。

### 推荐 UX

在 `/analyze` 中：

- 图片文件选择器
- 小预览图
- 手工描述文本框
- 描述追加到 `user_context`
- 保存后的截图可以从分析记录链接访问

### 边界

- 文件存储在 `data/screenshots/`
- 只接受图片 MIME 类型
- 强制大小上限，建议 8 MB
- Phase 3C 不把图片发送到任何外部 API
- 在 Vision 出现前，手工描述是权威图表上下文

### 验收

- 无 API key 也能上传成功
- 截图保存在业务历史 DB 之外
- 删除分析历史不会删除业务快讯
- prompt 包含用户提供的图表描述

## 6. 置信度说明

### 目标

明确说明模型置信度是主观估计，不是交易信号或统计概率。

### 建议 UI 文案

```text
置信度是模型基于证据充分度、时间吻合度和因果链条清晰度给出的主观估计，不是交易信号。
≥75% 较可信；50-75% 仅供参考；<50% 证据不足。
```

### 放置位置

- `/analyze/{run_id}` 的整体置信度旁边
- catalyst 级别置信度 hover/help 文本
- 可选：`/analyze/history` 列头

### 验收

- 用户不用离开分析页面即可看到说明
- 不改 schema
- 不依赖 provider

## 7. Phase 2B - LLM Provider Adapter

### 目标

在永久保留手工复制粘贴流程作为 fallback 的同时，新增可选自动模型调用。

### Provider 接口

建议结构：

```text
dashboard/providers/
├── __init__.py
├── base.py
├── openai_provider.py
└── anthropic_provider.py
```

基础接口：

```python
class AnalysisProvider:
    name: str

    def available(self) -> bool:
        ...

    async def analyze(self, prompt: str, *, attachments: list[Path] | None = None) -> ProviderResult:
        ...
```

Provider 结果：

```python
@dataclass
class ProviderResult:
    model_label: str
    raw_text: str
    usage: dict[str, object]
```

### 规则

- 没有 API key 时：provider 不可用，手工流程仍可工作
- provider 失败时：显示错误，并保留已生成的 prompt
- provider 结果通过同一个 `save_answer()` 路径保存
- `analysis_runs.model_label` 记录实际模型
- 不改变 evidence builder 边界
- 除非所选 provider 明确支持 Vision 且用户主动选择，否则不发送截图

### 验收

- 没有 provider package 或 key 时，手工流程仍可工作
- 自动路径可以禁用
- provider 错误不会丢失 prompt 或 evidence packet
- 测试覆盖 provider 不可用时的 fallback

## 8. Vision 识别

### 目标

当 Vision provider 可用时，自动解释上传的图表截图。

### 要求

可靠的图表解释需要具备视觉能力的模型。仅靠本地 OCR 不足以完成：

- symbol 识别
- 时间轴解释
- 价格轴解释
- K 线走势
- 时间周期和交易所上下文

### 输出

Vision 应返回结构化图表上下文：

```json
{
  "symbol": "ETH/USDT",
  "timeframe": "1h",
  "approx_window": "2026-05-24 21:30 - 22:00",
  "price_move": "2480 -> 2515",
  "trend": "up",
  "uncertainties": ["exchange not visible"]
}
```

识别出的文字应进入 `user_context`，不能覆盖用户输入。

## 9. Market Data Overlay

### 目标

在 `/item/{id}` 上、后续也在 evidence packet 中，展示新闻上下文旁边的分钟级行情上下文。

### 候选来源

- Binance public REST，用于加密货币交易对
- 其他 market API，后续按需加入

### 边界

- 行情数据只读
- 本地或内存缓存响应，避免重复调用
- market API 不可用时 dashboard 仍应工作
- 行情数据不能成为 evidence packet 生成的前置条件

### 验收

- `/item/{id}` 可以展示一段小型邻近价格时间线
- 失败时降级为“market data unavailable”
- 除非单独批准缓存设计，否则不写业务 DB

## 10. 推荐顺序

1. Phase 3A：Telegram dashboard 深链
2. Phase 3B：快讯流无限加载
3. Phase 3C：截图上传与手工描述
4. 置信度说明
5. Phase 2B provider adapter
6. Vision 识别
7. Market data overlay

理由：

- Telegram 链接日常价值最高，但会触及 Telegram 格式，因此需要 `GPT-5.5 高`。
- 无限加载和截图上传是本地 dashboard 功能，没有 API 依赖。
- 置信度说明很小，可以和分析 UI polish 合并。
- Provider 和 Vision 工作应等 API key 与 provider 偏好明确后再做。
- Market data overlay 有用，但会引入外部数据可靠性和缓存问题。

## 11. 测试策略

每个阶段必须包含：

- 尽可能使用 focused no-network unit tests
- 对变更的 dashboard 页面做 browser smoke
- `git diff --check`
- commit 前跑完整 `pytest`

对于 Telegram 变更，特别需要：

- 测试默认无 `DASHBOARD_URL` 的格式化
- 测试配置 dashboard 链接的情况
- 测试中不发送 Telegram
- 不改变 delivery dedupe 语义
