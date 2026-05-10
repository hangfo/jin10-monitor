# 项目状态摘要 007：补拉进度日志已落地

更新时间：2026-05-10 晚（Asia/Shanghai）

## 1. 这份文档的用途

本文件用于在新 session 中快速续接当前项目状态，不需要回读完整长对话。

这份摘要重点覆盖：

- 最近三个连续小版本交付已经完成了什么。
- 后台服务是否已经加载最新代码。
- 当前最适合继续推进的下一优先项。

## 2. 当前仓库状态

- 项目：jin10-monitor
- GitHub 仓库：https://github.com/hangfo/jin10-monitor
- 本地路径：`/Users/rich/jin10-monitor`
- 分支：`main`
- 当前已知最新提交：
  - `5520f1e feat(catchup): add progress logging`
  - `1732902 docs(status): add launchd and delay handoff`
  - `c933b90 feat(delay): show stale message latency`
  - `f465d5b fix(launchd): harden reload and install flow`

最近已完成能力：

- `launchd` 的 `install/reload` 现在会自动执行 `launchctl enable`，并提供失败排查提示。
- 新增 `SHOW_DELAY_IF_SECONDS` 配置，消息延迟超过阈值时会显示 `延迟：Xs`。
- 补拉跨多页时，终端会输出 `catch-up page=...` 进度日志，便于观察扫描和入库推进。

切换 session 后仍然必须重新执行本地 Git、日志和服务检查，不要只凭本文件判断现场状态。

## 3. 本轮核心结论

### 3.1 launchd 自恢复已经稳定落地

当前 `scripts/launchd/manage.sh` 行为：

- `install` / `reload` 会先执行 `launchctl enable`
- 服务已加载时会先 `bootout`
- 然后再 `bootstrap`
- 失败时会提示 `print-disabled` / `print` / `tail` 等排查命令

结论：

- “服务被 disable 后 reload 需要人工补 `launchctl enable`”这个问题已经被脚本吸收。
- Codex 沙箱里仍可能看到 `Bootstrap failed: 5`，但真实 macOS 环境重载已验证成功。

### 3.2 延迟提示 P1 已完成

当前行为：

- 配置项：`SHOW_DELAY_IF_SECONDS=60`
- 当 `当前时间 - 消息发生时间 >= 阈值` 时：

```text
延迟：123s
```

- 同时显示在：
  - Telegram 消息
  - 终端日志输出

当前仍未扩展成统一延迟框架：

- 不区分 WS / REST / 补拉 的不同延迟语义
- 不把延迟写入 SQLite
- 不改补拉摘要统计或发送策略

### 3.3 补拉进度日志 P1 已完成

目标是增强补拉可观测性，不改补拉语义。

当前行为：

- 补拉跨多页时，终端会输出轻量进度日志，例如：

```text
catch-up page=1 source=catchup_auto window_hits=20 collected=20 existing=5
catch-up page=2 source=catchup_auto window_hits=23 collected=43 existing=18
```

字段含义：

- `page`：当前扫到第几页
- `source`：本次补拉来源，例如 `catchup_auto` / `catchup_manual`
- `window_hits`：这一页落在目标时间窗口内的条数
- `collected`：累计已收集到的窗口内条数
- `existing`：累计其中已有历史记录的条数

结论：

- 现在可以更快判断补拉是否在推进、窗口里到底扫到了多少条、历史库重复占比大概是多少。
- 这对后续调试“大窗口补拉”“补拉慢”“为什么最终 stored 很少”都有帮助。

## 4. 本轮验证结果

### 4.1 延迟提示验证

已验证：

- `.venv/bin/python -m py_compile jin10_monitor.py`
- 本地格式化测试：
  - 阈值内不显示延迟
  - 阈值外显示 `延迟：125s`
  - Telegram/终端两条显示路径都带上延迟文本

### 4.2 补拉进度日志验证

已验证：

- `.venv/bin/python -m py_compile jin10_monitor.py`
- 本地模拟多页补拉测试

实际输出过：

```text
catch-up page=1 source=catchup_auto app_id=... window_hits=2 collected=2 existing=1
catch-up page=2 source=catchup_auto app_id=... window_hits=1 collected=3 existing=1
```

说明进度日志已经在真实补拉函数路径里生效，不只是文案拼接。

### 4.3 launchd 与后台服务验证

已验证：

- `./scripts/launchd/manage.sh reload`
- `./scripts/launchd/manage.sh status`

结果：

- 后台服务成功重载
- `launchctl status` 显示 `state = running`
- 日志显示进程已重新连接 WebSocket / REST

说明：

- 当前后台已经加载最新代码。
- 重载后的真实日志里是否出现某条“延迟提示”或“多页补拉进度日志”，仍取决于现场是否自然触发对应场景。

## 5. 说明文档与配置文档状态

已同步更新：

- `README.md`
  - `SHOW_DELAY_IF_SECONDS` 配置说明
  - 补拉多页进度日志示例
- `.env.example`
  - `SHOW_DELAY_IF_SECONDS=60`
- `docs/operations/001-launchd.md`
  - `launchctl enable` 已纳入手动/脚本流程说明
- `CHANGELOG.md`
  - 已记录 launchd 自恢复、延迟提示、补拉进度日志

当前不需要再额外补新的“配置文档”：

- 用户会实际修改的配置入口已经被 README 和 `.env.example` 覆盖
- `docs/status/*` 更适合做交接摘要，不适合作为长期配置主文档重复维护

## 6. 当前建议的下一步优先级

### P2：自动补拉逐条补发配置化

这是现在最适合继续推进的下一项。

建议方向：

- 默认仍不逐条补发，避免刷屏和实时消息混排
- 预留显式配置，例如：

```bash
AUTO_CATCHUP_SEND_LEVELS=T3_IMPORTANT,T2_HIGH
AUTO_CATCHUP_MAX_SEND=0
```

只有用户主动改成大于 `0` 时才补发。

为什么现在适合做它：

- 补拉可观测性已经提升，下一步更适合开始做补发策略开关
- 这项会动到 Telegram 行为，但还没有上升到“统一延迟框架”那种抽象复杂度

### P2/P3：统一延迟框架

现在还不急着做。

原因：

- 目前已经有可见的延迟提示
- 但 WS / REST / 补拉 的延迟语义是否统一，仍然需要更多真实运行反馈来决定

### P3：事件聚合防刷屏 V2

适合在补发配置化之后再做，否则变量会有点太多。

## 7. 模型与推理建议

当前判断：

- 文档、README、CHANGELOG、commit/push：`5.4` 中推理足够
- `launchd` 脚本、小型显示层功能、补拉进度日志：`5.4` 中到高推理足够
- 下面这些任务更适合考虑 `5.5` 高推理：
  - 自动补拉逐条补发配置化
  - 统一延迟框架
  - 事件聚合防刷屏 V2
  - WS / REST / SQLite / Telegram 多链路一致性排障

如果下一步真开始做“自动补拉逐条补发配置化”，建议先提醒用户评估是否切到 `5.5` 高推理。

## 8. 新 session 交接提示词

新开 session 后可以直接贴：

```text
请继续 /Users/rich/jin10-monitor 项目。
先读取：
1. /Users/rich/jin10-monitor/AGENTS.md
2. /Users/rich/jin10-monitor/docs/status/007-2026-05-10-catchup-progress-handoff.md

默认不要回读旧聊天。先执行：
git branch --show-current
git status
git pull --rebase
git log --oneline -5

当前优先任务：
做自动补拉逐条补发配置化，但默认仍不逐条补发，避免刷屏和实时消息混排。

要求：
- 不降低代码、debug 和架构设计质量。
- 代码修改前给计划。
- 修改后给 diff、风险和验证。
- commit/push 前更新 CHANGELOG.md，并等我确认。
```
