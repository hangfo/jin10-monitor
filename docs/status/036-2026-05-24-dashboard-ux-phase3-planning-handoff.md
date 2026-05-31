# 036 - Dashboard UX polish 和 Phase 3 规划交接

日期：2026-05-24

更新时间：2026-05-31（Asia/Shanghai）

## 当前状态

本交接前最新已推送提交是：

```text
7c39fc8 fix(dashboard): polish analyze and item templates
```

本交接记录了为以下提交准备的下一批 dashboard UX：

```text
feat(dashboard): improve analysis timing and news rendering
```

这批改动继续沿用 Phase 1 / 2A 的独立 dashboard 架构：

- `run_dashboard.py` 仍是 dashboard 入口。
- 不修改 `jin10_monitor.py`。
- 业务历史 DB 保持只读。
- 不引入模型 API、金十 REST、WebSocket、Telegram send、retry、resend 或 backfill 操作。

## 已实现内容

### 1. 分析时间窗口 UX

`/analyze` 输入表单现在使用浏览器原生 `datetime-local` 控件填写
`window_start` 和 `window_end`。

新增快速时间窗口按钮：

- 过去 5 分钟
- 过去 15 分钟
- 过去 30 分钟
- 过去 1 小时
- 过去 4 小时

当 `/analyze` 在没有预填 item window 的情况下打开时，表单默认使用过去 30 分钟。从 `/item/{id}` 打开时，保留已有预填窗口。

后端归一化会把浏览器值，例如：

```text
2026-05-24T21:30
```

转换为现有 dashboard 格式：

```text
2026-05-24 21:30:00
```

### 2. 类金十快讯渲染

快讯流和详情页现在使用 `flash_history` 中已经存储的样式信号渲染本地新闻行：

- `important`
- `has_title`
- `has_bold`
- `has_pic`
- `pic_url`
- `source_url`
- `style_flags`

重要新闻渲染为红色，有标题的新闻使用更强的标题样式，`has_bold` 控制正文字重，图片以 lazy-loaded thumbnails 渲染，source links 保持可点击。

保留对旧历史 DB schema 的兼容：`has_title` 和 `style_flags` 通过现有 optional-column helper 选择，缺失时回退为空值。

### 3. 分析结果可读性

分析详情渲染现在减少 raw `news_id` 噪音：

- catalyst 条目显示类似 `05-23 09:30` 的时间标签
- `[#news_id]` 链接渲染为更友好的 `[↗ 05-23 09:30]` 标签
- 完整 `news_id` 保留在链接目标和 hover title 中
- evidence sidebar 优先显示时间 + headline/content summary，并在下方弱化展示 raw ID

`analysis_db.get_run()` 会从已保存的 evidence packet 丰富 evidence rows，让模板可以显示 `published_at`、title/content、priority 和 source，而不查询或写入业务 DB。

### 4. Draft 状态样式

共享 CSS 新增 `.pill.none`，让 draft analysis records 有样式，而不是显示成普通白色 pill。

## 功能评估

### 快讯流无限加载

可行且压力较低。正确理解不是 masonry layout，而是单列无限加载。安全实现方式是新增只读 JSON 或 HTML-fragment 端点，使用 `LIMIT/OFFSET`。

推荐限制：

- 首屏：50
- 每次加载：30
- 自动上限：500
- 超过 500 后：显示手动“load more”操作，而不是继续自动触发

这应作为 Phase 3B，放在当前 UX 批次提交之后。

### 截图识别

两步路径：

- 无 API：上传截图，让用户提供手工上下文；本地保存截图，并把文字描述加入 prompt
- 有 API：通过 provider adapter 增加 Vision 识别

可靠自动识别图表 symbol、时间轴、价格轴和 K 线结构，需要具备 vision-capable 的模型。仅靠本地 OCR 对这个用例不够可靠。

推荐位置：截图上传可以作为 Phase 3C；自动识别应放在 Phase 2B provider adapter 之后。

### 置信度说明

置信度是模型自我评估，不是统计概率。

后续小补丁建议 UI 文案：

```text
置信度是模型基于证据充分度、时间吻合度和因果链条清晰度给出的主观估计，不是交易信号。
≥75% 较可信；50-75% 仅供参考；<50% 证据不足。
```

## 验证

交接前最新验证：

```text
.venv/bin/python -m pytest tests/test_dashboard_db.py tests/test_dashboard_analysis.py -q
33 passed

.venv/bin/python -m pytest -q
128 passed

git diff --check
no output
```

以下浏览器 smoke checks 通过：

- `/analyze`
- `/`
- `/item/{id}`
- `/analyze/history`

## 已保留的边界

- 未修改 `jin10_monitor.py`。
- 未修改 launchd config。
- 未新增依赖。
- 未新增 `python-multipart`。
- 未连接任何模型 API。
- 未调用金十 REST 或 market-data APIs。
- 未发送 Telegram。
- 未写业务历史 DB。
- 分析写入仍隔离在 `data/dashboard_analysis.sqlite3`。

## 剩余工作

建议顺序：

1. 提交并推送这批 UX 改动：

```text
feat(dashboard): improve analysis timing and news rendering
```

2. 编写 `docs/design/003-phase2b-phase3-spec.md`，冻结：
   - Telegram `/item/{id}` deep links
   - screenshot upload boundaries
   - market data overlay 边界
   - LLM provider adapter 接口

3. Phase 3A：Telegram 消息 deep link，使用 `DASHBOARD_URL`；未设置时，Telegram 消息文本必须与当前输出逐字节等价。

4. Phase 3B：带安全上限的快讯流无限加载。

5. Phase 3C：截图上传 + 手工图表描述。

6. Phase 2B：在 API key 可用后再做 provider adapter 和可选 Vision recognition。

## 可直接复制的 next-session prompt

```text
请继续 /Users/rich/jin10-monitor 项目。

建议模型：GPT-5.5 高，如果要改 Telegram 消息格式或写 003 spec；如果只是提交当前 dashboard UX 批次，用 GPT-5.5 中也可以。

先读取：
1. /Users/rich/jin10-monitor/AGENTS.md
2. /Users/rich/jin10-monitor/docs/status/036-2026-05-24-dashboard-ux-phase3-planning-handoff.md
3. /Users/rich/jin10-monitor/docs/design/002-dashboard-ai-full-spec.md

先执行：
git branch --show-current
git status
git pull --rebase
git log --oneline -8

当前结论：
- Phase 2A 已完成并推送。
- 当前 UX 批次实现了 /analyze 时间选择器、金十样式消息渲染、分析详情时间戳和 news_id 降噪。
- 仍不修改 jin10_monitor.py。
- 不接模型 API。
- 不写业务历史库。

下一步：
若当前 UX 批次已提交推送，优先写 003 Phase 2B/Phase 3 spec；若还未提交，先复查 diff、跑测试、浏览器 smoke，再提交推送。
```
