# 项目状态摘要 002：后台常驻与推送质量

更新时间：2026-05-07 23:15 左右（Asia/Shanghai）

## 1. 当前仓库状态

- 项目：jin10-monitor
- GitHub 仓库：https://github.com/hangfo/jin10-monitor
- 本地路径：`/Users/rich/jin10-monitor`
- 当前分支：`main`
- 当前最新提交：`f856360 fix(alerts): format indicator messages`
- 工作区状态：干净

近期关键提交：

```text
f856360 fix(alerts): format indicator messages
4762122 docs(ops): simplify launchd management
580de03 docs(ops): add launchd supervisor template
fdb1949 docs: document catchup workflow
759625a docs(status): add catchup workflow handoff
```

## 2. 当前运行状态

macOS `launchd` 后台服务已启用：

```text
Label: com.rich.jin10-monitor
state: running
active count: 1
program: /Users/rich/jin10-monitor/scripts/run_monitor.sh
stdout/stderr: /Users/rich/jin10-monitor/logs/jin10-monitor.log
```

最近确认的 SQLite 游标：

```text
last_ingested_at = 2026-05-07 23:11:54
last_ingested_id = 20260507231154492800
last_startup_at = 2026-05-07 22:45:30
```

含义：

- 后台服务正在运行。
- 日志已统一到 `logs/jin10-monitor.log`。
- 最新入库时间持续推进，说明 WebSocket/REST 入库链路正常。

## 3. 已完成的大节点

### 3.1 离线补拉进入 main

- 自动补拉窗口：`(last_ingested_at, startup_at]`。
- 自动补拉只入库，并发送一条 Telegram 摘要。
- 手动补拉支持指定窗口、限制入库数量、限制补发数量。
- 同一金十消息 ID 不重复入库。
- Telegram 已发送消息会记录到 `delivery_log`，避免补拉重复发送。

### 3.2 launchd 后台常驻

已新增：

- `scripts/run_monitor.sh`
- `scripts/launchd/com.rich.jin10-monitor.plist`
- `scripts/launchd/manage.sh`
- `docs/operations/001-launchd.md`
- `logs/.gitkeep`

`manage.sh` 是后续推荐入口，避免手记复杂命令。

### 3.3 日志统一

旧日志：

```text
logs/jin10-monitor.out.log
logs/jin10-monitor.err.log
```

新日志：

```text
logs/jin10-monitor.log
```

当前已重载服务，新日志路径生效。

### 3.4 空消息修复

问题：

- 金十 WebSocket 会推送 `type=1` 的财报/指标类消息。
- 这类消息没有普通新闻的 `title/content`。
- 旧逻辑会把重要数据推成 Telegram 空消息。

修复：

- 为 `type=1` 指标消息生成可读标题和正文。
- 示例：

```text
纽约联储1年通胀预期 4月
公布值：3.64%
预期：3.5%
前值：3.42%
市场：美国
```

- 对仍然没有可显示内容的未知消息：只入库，不推 Telegram。

验证：

- 已用 2026-05-07 21:28 的壳牌净利润/EPS 两条原始 JSON 回归。
- 已在实时日志中看到 23:00 的纽约联储通胀预期数据类消息被正常格式化。

## 4. 日常运维命令

进入项目：

```bash
cd /Users/rich/jin10-monitor
```

检查配置：

```bash
./scripts/launchd/manage.sh check
```

查看后台状态：

```bash
./scripts/launchd/manage.sh status
```

查看实时日志：

```bash
./scripts/launchd/manage.sh logs
```

重载服务：

```bash
./scripts/launchd/manage.sh reload
```

停止服务：

```bash
./scripts/launchd/manage.sh stop
```

彻底卸载服务：

```bash
./scripts/launchd/manage.sh uninstall
```

查看 SQLite 游标：

```bash
sqlite3 data/jin10_history.sqlite3 "select key, value, updated_at from runtime_state order by key;"
```

## 5. 当前已知现象

### 5.1 终端不会自动同步显示

后台运行后，原终端不会再自动滚动显示消息。

正确查看方式：

```bash
./scripts/launchd/manage.sh logs
```

按 `Ctrl+C` 只会退出看日志，不会停止后台服务。

### 5.2 Codex 工具里 reload 可能遇到 Bootstrap failed: 5

在 Codex 工具环境里执行 `manage.sh reload`，可能遇到：

```text
Bootstrap failed: 5: Input/output error
```

这通常是工具环境权限限制，不是 plist 损坏。用户在自己的终端里执行通常更顺。

如果发生：

```bash
launchctl print gui/$(id -u)/com.rich.jin10-monitor
./scripts/launchd/manage.sh status
```

确认服务状态后再决定是否重新 `bootstrap`。

## 6. 下一步优先级

### P0：继续观察

观察 1-2 小时或到次日：

- 是否还有 Telegram 空消息。
- 是否有重复刷屏。
- `last_ingested_at` 是否继续推进。
- launchd 是否持续 running。

### P1：README 日常速查

README 可再补一个极短的“日常运维速查”区块，方便不记命令时复制。

### P2：事件去重 / 聚合防刷屏

下一项最值得做的新功能：

- 10-30 秒内同指标/同标题相似消息不重复推。
- T3 重要消息仍保留。
- 重复项入库但不 Telegram。
- 终端日志显示“已降噪”。

背景例子：

- 数据类指标消息和文字快讯可能先后描述同一事件。
- 这类不是抓取 bug，但会降低 Telegram 信号质量。

### P3：VPS systemd

只有决定迁移到 VPS 后再做。需要额外考虑：

- `.env` 和 SQLite 迁移。
- 时区。
- systemd service。
- 日志轮转。
- 金十/Telegram 网络连通性。

## 7. 新 session 交接提示词

如果切换 session，可以直接贴：

```text
请先读取 /Users/rich/jin10-monitor/AGENTS.md、
/Users/rich/jin10-monitor/docs/status/001-2026-05-07-catchup-workflow.md、
/Users/rich/jin10-monitor/docs/status/002-2026-05-07-launchd-and-alert-quality.md。

当前项目 hangfo/jin10-monitor 已在 main 上运行。
launchd 后台服务 com.rich.jin10-monitor 已启用，日志在 logs/jin10-monitor.log。
最新关键提交是 f856360，已修复 type=1 数据类消息空推送。
不要直接用 MCP 写 GitHub，不要未经确认 commit/push。
下一步优先观察稳定性，然后做 README 日常速查或事件去重/聚合防刷屏。
```
