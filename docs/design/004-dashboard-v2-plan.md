# Dashboard V2 开发计划定稿

日期：2026-05-29

本文基于当前 `main`、`003-phase2b-phase3-spec.md`、`037` handoff，以及两版补丁包
`phase 2a:b:c bug fix和dashaboard v2计划（v1).zip`、`phase 2a:b:c bug fix（v2).zip`
对照后定稿。结论是：v2 代码作为修复基线更好；v1 的 HTML 计划不进入应用路由，但吸收其路线图内容并改写为本设计文档。

## 当前基线

- 正式入口仍是 `run_dashboard.py` + `dashboard/`，不继续扩展旧 `jin10_monitor.py --dashboard` 原型。
- Dashboard 业务库访问保持只读：`mode=ro` + `PRAGMA query_only`。
- Dashboard 不调用金十 REST，不发送、不补发、不重试 Telegram。
- 分析结果和截图只写独立 `data/dashboard_analysis.sqlite3` 与 `data/screenshots/`。
- Phase 1、Phase 2A、Phase 3A/3B/3C 已完成：只读页面、手工 AI 分析流、Telegram `/item/{id}` 深链、快讯流分页加载、截图上传、置信度说明。

## 本轮修复定稿

### 采用 v2 方案

1. 方向标签使用催化语义：`▲ 偏利多`、`▼ 偏利空`、`◆ 多空混合`。
   这比 v1 的“看多/看空”更准确，避免被误读成交易预测。
2. 全局加入 `box-sizing: border-box`，再对分析页网格补 `min-width: 0`。
   这比只修单页输入框更稳。
3. 同秒消息排序使用金十消息 `id` 作为 tie-breaker。
   `created_at` 受补拉入库时间影响，可能让同一秒内的历史顺序倒置。
4. 截图上传加固：
   先检查 `Content-Length`，再读取 body；MIME 限定为 `png/jpeg/webp/gif`；500 错误不回显原始异常。

### 采用 v1 方案

1. 快讯流不再展示 `style_flags`。
   这是监控进程内部调试字段，不能出现在用户界面。
2. 快讯流隐藏 `title` 和 `content` 都为空的消息。
   空消息仍保留在历史库，详情页仍可通过 `/item/{id}` 访问；不改监控入库链路。
3. `has_title=0` 时只渲染一次正文，避免标题/正文判断异常导致重复显示。
4. 补拉消息在来源列显示“补拉”标签，帮助解释旧消息出现在时间线中的原因。

### 优于两版补丁的调整

- 文本去重判断不放在 Jinja 字符串拼接里，而是在 `dashboard/app.py` 提供 `normalize_news_text()`，统一折叠空白和不可见间隔。
- 不整文件覆盖当前 repo。两版补丁都是候选实现，最终只做最小定向合并，保留当前 HEAD 已完成的 Phase 3 能力。
- 不在监控进程层过滤空消息。展示层过滤已解决 UI 问题，入库层改动会影响历史完整性和实时/补拉链路。

## V2 路线图

### 0. 稳定化收口

- 完成本轮 UI bug、排序稳定性和上传安全修复。
- 用 pytest、浏览器 smoke、`/api/feed/page` 检查确认首屏和分页渲染一致。
- 提交前更新 `CHANGELOG.md`，保持 handoff 与规格文档一致。

### 1. 近期无大模型 API 项

- 分析对比：在 `/analyze/history` 选择两条同标的分析记录，对比 judgement、confidence、主要催化新闻和缺失证据。
- 可选行情叠加：设计为独立 market adapter，仅在用户主动打开单条详情或分析页面时请求；默认不作为 dashboard 启动依赖。
- 行情叠加不得调用金十 REST，不写业务历史库；可先用本地缓存或用户明确选择的数据源，避免把 Dashboard 变成外部行情服务。

### 2. Phase 2B：LLM Provider Adapter

- 新建 `dashboard/providers/`，先定义统一接口，再接 OpenAI 或 Anthropic。
- 手工复制粘贴流永久保留为默认降级路径。
- Provider 调用只写独立分析库，不写业务历史库，不改变 Telegram 发送语义。
- 首版无需改 evidence packet 核心结构；如果后续需要记录 provider metadata，优先复用现有 `model_label`。

### 3. Vision 识别

- 等 Provider Adapter 稳定且 API key 明确后再做。
- 截图 Vision 只用于生成结构化 `user_context` 建议，不自动覆盖用户描述。
- 支持失败降级：Vision 失败时继续保留截图上传 + 手工描述流程。

### 4. Phase 4 候选

- 多标的联合分析。
- 自动识别价格异动后推荐证据窗口。
- 多新闻源融合，但必须另写规格确认数据边界和调用成本。

## 明确不做

- 不做 Telegram callback receiver。
- 不做公网暴露、登录系统或多用户权限。
- 不默认开启事件聚合 V2。
- 不把截图上传扩展为任意文件上传。
- 不把 V1 HTML 计划页作为 Dashboard 路由上线。
