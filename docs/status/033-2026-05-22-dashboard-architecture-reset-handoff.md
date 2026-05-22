# 项目状态摘要 033：Dashboard 原型收尾与正式架构切换

更新时间：2026-05-22（Asia/Shanghai）

## 1. 本摘要用途

本文件用于新 session 继续 Dashboard 工作，不需要回读旧聊天。

当前节点的关键变化是：Dashboard 已经有一个可运行、已提交、已推送的只读 MVP 原型；下一步不应继续扩大旧入口，而应转向正式的 FastAPI/Jinja2 Dashboard 和无 API 的 ChatGPT Business 分析工作流。

## 2. 当前仓库状态

- 项目路径：`/Users/rich/jin10-monitor`
- 当前分支：`main`
- 远端状态：`git pull --rebase` 显示 `Already up to date.`
- 工作区状态：生成本摘要前为干净状态。
- 最新提交：
  - `6330022 feat(dashboard): add readonly local dashboard mvp`
  - `9d0a971 docs(dashboard): add dashboard mvp design`
  - `e5e6aac docs(status): add context and dashboard handoff`
  - `d66bdd6 feat(history): add readonly context lookup`
  - `811256e docs(status): add aggregation v2 handoff`
  - `de29e44 feat(telegram): add aggregation anti-spam v2`

## 3. 最近 commit 是否与新需求冲突

结论：不需要 revert。

`6330022` 的作用是提供一个本地只读 Dashboard MVP 原型，默认通过：

```bash
.venv/bin/python jin10_monitor.py --dashboard
```

访问：

```text
http://127.0.0.1:8765/
```

它已经覆盖：

- 首页最近快讯流。
- 消息详情页和前后上下文。
- Telegram 状态诊断页。
- 聚合报告占位页。
- 首页自动刷新。
- 卡片可点击。
- 已加载条数提示。

它与新需求的关系：

- 产品方向不冲突：仍然是本地、只读、可回看、可诊断的 dashboard。
- 安全边界不冲突：不触发 REST、WebSocket、补拉或 Telegram，不写业务库。
- 架构方向有临时债：当前实现放在 `jin10_monitor.py` 内，而正式方案应迁移到独立 `run_dashboard.py` + `dashboard/`。

因此处理策略是：保留作为已验证原型和 fallback，但后续不要继续往 `jin10_monitor.py` 里堆 dashboard 功能。

## 4. 是否需要新开 branch

结论：暂时不新开 branch。

原因：

- `AGENTS.md` 当前协议要求在 `main` 上工作，并在修改前确认 branch/status/pull/log。
- 当前远端同步正常，工作区干净，没有分叉或冲突。
- 下一步应先做文档冻结和小步迁移，适合继续在 `main` 上按 commit 拆分推进。

后续只有在以下场景再考虑新 branch：

- 要删除或废弃旧 `--dashboard` 入口。
- 要引入新的运行依赖或改启动方式。
- 要做大规模模块迁移，diff 难以一眼解释清楚。
- 用户明确希望走 PR/分支隔离。

## 5. 当前最终方向

采用第二版 Dashboard 主方案，但必须做关键调整：

- 不把 Claude / Anthropic API 作为 P0/P1 前置依赖。
- 当前默认 AI 工作流应是无 API 模式：
  - 生成 evidence packet。
  - 复制到 ChatGPT Business / Custom GPT。
  - 把模型回答粘贴回 Dashboard 保存。
- API 自动调用只作为后续可插拔能力。
- Phase 1 / Phase 2A 不改 `jin10_monitor.py`。
- Telegram dashboard 链接放到后续 Phase 3，单独 commit。
- Evidence builder 默认只读本地 SQLite，不主动调用金十 REST。

## 6. 建议下一步

优先做 Phase 0：冻结最终版需求文档。

建议产物：

```text
docs/design/002-dashboard-ai-full-spec.md
```

文档应明确：

- 页面范围：首页、详情、Telegram 状态、系统健康、分析页。
- 数据来源：业务库只读 `data/jin10_history.sqlite3`，分析库可写 `data/dashboard_analysis.sqlite3`。
- 只读边界：Dashboard 不写业务库，不触发补拉，不发送 Telegram，不接管 launchd。
- 启动方式：正式目标为 `python run_dashboard.py`，默认监听 `127.0.0.1:8765`。
- AI 路线：Phase 2A 手工 ChatGPT Business，Phase 2B 再做 OpenAI/Anthropic/Ollama adapter。
- 当前 `6330022` 原型的定位：保留，不扩展，后续迁移。

完成文档冻结后，再进入 Phase 1：

```text
run_dashboard.py
dashboard/
  app.py
  db.py
  routers/
  templates/
```

## 7. 不要做的事

下一轮不要做：

- 不要 revert `6330022`。
- 不要新开 branch，除非用户明确要求。
- 不要继续把 dashboard 新功能塞进 `jin10_monitor.py`。
- 不要默认接 Claude / Anthropic API。
- 不要改 Telegram 推送格式。
- 不要调用金十 REST 作为 evidence builder 默认数据源。
- 不要公网或局域网暴露 dashboard。

## 8. 新 session 建议模型

建议使用：`GPT-5.5 高`。

原因：下一步要把产品需求、架构边界和迁移路径一次性定稳，涉及历史 commit 判断、旧原型保留策略、FastAPI 结构和无 API AI 工作流。

## 9. 新 session 提示词

```text
请继续 /Users/rich/jin10-monitor 项目。

建议模型：GPT-5.5 高。

先读取：
1. /Users/rich/jin10-monitor/AGENTS.md
2. /Users/rich/jin10-monitor/docs/status/033-2026-05-22-dashboard-architecture-reset-handoff.md

默认不要回读旧聊天。先执行：
git branch --show-current
git status
git pull --rebase
git log --oneline -6

当前结论：
- 最新 commit 6330022 是已提交已推送的只读 Dashboard MVP 原型，不需要 revert。
- 暂时不新开 branch，继续按 AGENTS 协议在 main 上小步推进。
- 旧 dashboard 原型保留，但后续不要继续往 jin10_monitor.py 里扩展 dashboard。
- 正式方向切到 FastAPI/Jinja2 独立 dashboard。
- AI 分析默认不接 Claude / Anthropic API，而是先做 evidence packet + ChatGPT Business/Custom GPT 手工复制粘贴 + 回填保存。

下一步任务：
先做 Phase 0 文档冻结：
1. 结合 /Users/rich/Downloads/002-dashboard-ai-full-spec.md
2. 结合 /Users/rich/Downloads/jin10_dashboard_master_plan.html
3. 结合 /Users/rich/Downloads/jin10_monitor_architecture_and_roadmap.svg
4. 结合当前已提交的 Dashboard MVP 进度

产出最终版：
/Users/rich/jin10-monitor/docs/design/002-dashboard-ai-full-spec.md

要求：
- 以功能实现为主。
- 明确页面、数据来源、只读边界、启动方式、风险和分步开发计划。
- 不要把 Anthropic/Claude API 作为 P0/P1 前置依赖。
- Phase 1/2A 不改 jin10_monitor.py。
- Telegram dashboard 链接放到后续 Phase 3 单独做。
- Evidence builder 默认只读本地 SQLite，不主动请求金十 REST。
- 先给修改计划并等我确认后再改文档。
```
