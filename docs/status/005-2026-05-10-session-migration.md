# 项目状态摘要 005：低额度迁移与当前优先任务

更新时间：2026-05-10 下午（Asia/Shanghai）

## 1. 这份文档的用途

本文件用于切换新 session 时快速接上当前项目，不需要回读完整长对话。

原则：

- 省额度不能降低代码、排障和架构交付质量。
- 普通文档、commit/push、简单配置使用较低成本模式。
- WebSocket、REST、Telegram、SQLite、补拉去重和进程守护等核心链路仍按高质量排障标准执行。

## 2. 当前仓库状态

- 项目：jin10-monitor
- GitHub 仓库：https://github.com/hangfo/jin10-monitor
- 本地路径：`/Users/rich/jin10-monitor`
- 分支：`main`
- 当前已知最新提交：`8af5791 docs(status): add gap recovery handoff`
- 最近已完成能力：
  - 统一快讯时间显示。
  - 启动离线补拉。
  - 长停顿/睡眠恢复后自愈补拉摘要。
  - 补拉摘要列出最多 10 条 T3/T2 重点标题。
  - 关键词外部配置。
  - Telegram 网络异常日志与有限重试。

切换 session 后必须重新执行本地检查确认最新状态，不要只凭本文件判断。

## 3. 最近一次排障结论

用户反馈：MacBook 凌晨合盖离线，开盖后没有看到离线补拉统计推送。

排障结论：

- 不是最新补拉逻辑已经证明有 bug。
- 主要原因是后台 `launchd` 当时仍运行旧进程，旧进程启动时间早于后续补拉增强提交，所以没有“自愈补拉摘要”能力。
- SQLite 实际仍有入库记录，说明不是完全漏抓。
- 日志里同时出现 Telegram `TimeoutError` 和 `Connection reset by peer`，说明 Telegram API 或网络也曾不稳定。

恢复动作：

- `manage.sh reload` 遇到 `Bootstrap failed: 5`。
- 手动执行 `launchctl enable` 后重新 bootstrap 成功。
- 新进程启动后，日志出现“离线补拉完成 ... 摘要 已发送”，证明最新补拉逻辑已加载。

## 4. 当前最优先任务

### P0/P1：修复 `manage.sh reload/install` 的 launchd 启动健壮性

目标：

- 把这次手动恢复用到的 `launchctl enable` 写入脚本流程。
- 避免服务被 disabled 或 bootout 后，`reload/install` 报 `Bootstrap failed: 5` 需要用户手动救。
- 保持脚本输出对新手友好，失败时提示下一步检查命令。

建议修改范围：

- `scripts/launchd/manage.sh`
- `README.md` 或相关 launchd 文档
- `CHANGELOG.md`

建议验证：

```bash
./scripts/launchd/manage.sh check
./scripts/launchd/manage.sh status
./scripts/launchd/manage.sh reload
./scripts/launchd/manage.sh status
./scripts/launchd/manage.sh logs
```

如涉及真实后台服务，执行前要说明会重载服务。

## 5. 后续任务优先级

### P1：延迟提示

当推送延迟超过阈值时，在 Telegram/终端显示：

```text
延迟：123s
```

建议配置：

```bash
SHOW_DELAY_IF_SECONDS=60
```

### P2：自动补拉逐条补发配置化

默认仍不逐条补发，避免刷屏和实时消息混乱。

可预留配置：

```bash
AUTO_CATCHUP_SEND_LEVELS=T3_IMPORTANT,T2_HIGH
AUTO_CATCHUP_MAX_SEND=0
```

只有用户手动改成大于 0 时才补发。

### P2：catch-up 进度日志

补拉多页时增加轻量进度日志，例如：

```text
catchup page=1 stored=20 existing=5
catchup page=2 stored=43 existing=18
```

### P3：事件聚合防刷屏 V2

目标：

- 同主题、同来源或相似标题短时间内合并。
- T3 重要消息保持独立优先。
- 完整入库，Telegram 减少重复信息。

### P4：VPS/systemd

本地稳定后再迁移，避免把本地还没稳定的问题带到服务器。

## 6. 省额度协作建议

这部分是协作方式，不是降低质量标准。

推荐：

- 简单文档、commit/push、README、CHANGELOG：用较低成本模型/中推理。
- 小 bug、小配置、局部脚本：用中推理。
- WebSocket 协议、REST 补拉、SQLite 去重、Telegram delivery、launchd/systemd 守护、交易级推送可靠性：必要时用更强模型或高推理。
- 尽量复制关键日志文本，不发整屏长截图。
- 每次只发最关键截图，其他用文字描述。
- 阶段完成后写 `docs/status/00x-...md`，新 session 先读摘要再继续。

不建议：

- 为了省额度跳过本地验证。
- 为了省额度不读相关代码就改核心链路。
- 为了省额度把不确定的排障结论说成确定。

## 7. 新 session 交接提示词

新开 session 后可以直接贴：

```text
请继续 /Users/rich/jin10-monitor 项目。
先读取：
1. /Users/rich/jin10-monitor/AGENTS.md
2. /Users/rich/jin10-monitor/docs/status/005-2026-05-10-session-migration.md

默认不要回读旧聊天。先执行：
git branch --show-current
git status
git pull --rebase
git log --oneline -5

当前优先任务：
修复 scripts/launchd/manage.sh 的 reload/install 健壮性，把 launchctl enable 纳入流程，避免 Bootstrap failed: 5 后需要手动恢复。

要求：
- 不降低代码、debug 和架构设计质量。
- 代码修改前给计划。
- 修改后给 diff、风险和验证。
- commit/push 前更新 CHANGELOG.md，并等我确认。
```
