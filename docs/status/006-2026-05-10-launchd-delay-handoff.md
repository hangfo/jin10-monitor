# 项目状态摘要 006：launchd 自恢复与延迟提示已落地

更新时间：2026-05-10 晚（Asia/Shanghai）

## 1. 这份文档的用途

本文件用于在新 session 中快速续接当前项目状态，避免回读长对话。

适用场景：

- 需要知道最近两次小版本交付已经做了什么。
- 需要确认后台服务当前是否已经加载新代码。
- 需要决定下一步优先继续做哪个观察性/稳定性任务。

## 2. 当前仓库状态

- 项目：jin10-monitor
- GitHub 仓库：https://github.com/hangfo/jin10-monitor
- 本地路径：`/Users/rich/jin10-monitor`
- 分支：`main`
- 当前已知最新提交：
  - `c933b90 feat(delay): show stale message latency`
  - `f465d5b fix(launchd): harden reload and install flow`

最近已完成能力：

- `scripts/launchd/manage.sh` 的 `install/reload` 现在会自动执行 `launchctl enable`。
- `launchd` 在 `bootstrap` 失败时会输出更明确的下一步排查命令。
- README、运维文档和 CHANGELOG 已同步说明新的 `launchd` 恢复路径。
- 新增 `SHOW_DELAY_IF_SECONDS` 配置。
- 当消息发生时间落后当前时间超过阈值时，Telegram 和终端都会显示 `延迟：Xs`。

切换 session 后仍然必须重新执行本地 Git 和服务检查，不要只凭本文件判断现场状态。

## 3. 本轮核心结论

### 3.1 launchd 自恢复问题已收口

之前的现象是：

- 服务被 disable 或 bootout 后，`manage.sh reload` 可能报 `Bootstrap failed: 5`。
- 需要手动执行 `launchctl enable gui/$(id -u)/com.rich.jin10-monitor` 才能恢复。

现在脚本内已经内建恢复路径：

- `install` / `reload` 先执行 `launchctl enable`
- 如果服务已加载，先 `bootout`
- 再 `bootstrap`
- 如果失败，输出 `print-disabled` / `print` / `tail` 等排查命令

结论：

- 这类恢复不再依赖人工记忆命令。
- Codex 沙箱里仍可能看到 `Bootstrap failed: 5`，但真实 macOS 环境重载已验证成功。

### 3.2 延迟提示 P1 已完成

目标是先补显示层，不做统一延迟框架。

当前行为：

- 新配置：`SHOW_DELAY_IF_SECONDS=60`
- 当 `当前时间 - 消息发生时间 >= 阈值` 时：

```text
延迟：123s
```

- 同时显示在：
  - Telegram 消息
  - 终端日志输出

当前未做：

- 不区分 WS / REST / 补拉 的不同延迟语义。
- 不把延迟写入 SQLite。
- 不改补拉摘要统计和发送策略。

## 4. 本轮验证结果

### 4.1 代码与格式化验证

已验证：

- `.venv/bin/python -m py_compile jin10_monitor.py`
- 本地格式化测试：
  - 阈值内不显示延迟
  - 阈值外显示 `延迟：125s`
  - Telegram/终端两条显示路径都带上延迟文本

### 4.2 launchd 与后台服务验证

已验证：

- `./scripts/launchd/manage.sh reload`
- `./scripts/launchd/manage.sh status`

结果：

- 后台服务成功重载。
- `launchctl status` 显示 `state = running`
- 日志显示进程已重启并重新连接 WebSocket / REST。

说明：

- 重载后的真实日志里，尚未自然遇到一条超过 60 秒阈值的新消息，所以还没有“真实运行中出现延迟行”的现场样本。
- 但显示函数的本地验证已经通过，且后台已加载新代码。

## 5. 当前建议的下一步优先级

### P1：catch-up 进度日志

建议优先做这个，而不是立刻扩成统一延迟框架或自动补发策略。

目标：

- 补拉多页时输出轻量进度，便于知道：
  - 扫到第几页
  - 累计入库多少
  - 已存在多少
  - 是否接近 `max_store`

建议日志形态：

```text
catchup page=1 stored=20 existing=5
catchup page=2 stored=43 existing=18
```

优先原因：

- 开发成本低
- 对后续排障收益高
- 风险低于“自动补拉逐条补发配置化”
- 能为后面进一步调整补拉策略提供更好的观察面

### P2：自动补拉逐条补发配置化

建议保守设计，默认仍不逐条补发，避免刷屏和实时消息混排。

### P2/P3：统一延迟框架或事件聚合 V2

这两项都更适合在已有更多真实运行反馈后再做，避免过早抽象。

## 6. 模型与推理建议

当前判断：

- 文档、CHANGELOG、commit/push：`5.4` 中推理足够
- `launchd` 脚本、小型显示层特性、补拉进度日志：`5.4` 中到高推理通常足够
- 下面这些任务更适合考虑 `5.5` 高推理：
  - 自动补拉逐条补发配置化
  - 统一延迟框架
  - 事件聚合防刷屏 V2
  - WS / REST / SQLite / Telegram 多链路一致性排障

当前不建议仅为下一步 `catch-up` 进度日志切换到 `5.5` 高推理。

## 7. 新 session 交接提示词

新开 session 后可以直接贴：

```text
请继续 /Users/rich/jin10-monitor 项目。
先读取：
1. /Users/rich/jin10-monitor/AGENTS.md
2. /Users/rich/jin10-monitor/docs/status/006-2026-05-10-launchd-delay-handoff.md

默认不要回读旧聊天。先执行：
git branch --show-current
git status
git pull --rebase
git log --oneline -5

当前优先任务：
给 catch-up 增加轻量进度日志，便于观察多页补拉时的扫描/入库进度。

要求：
- 不降低代码、debug 和架构设计质量。
- 代码修改前给计划。
- 修改后给 diff、风险和验证。
- commit/push 前更新 CHANGELOG.md，并等我确认。
```
