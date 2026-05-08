# 项目状态摘要 003：稳定性、关键词配置与当前交接

更新时间：2026-05-09 04:15 左右（Asia/Shanghai）

## 1. 当前仓库状态

- 项目：jin10-monitor
- GitHub 仓库：https://github.com/hangfo/jin10-monitor
- 本地路径：`/Users/rich/jin10-monitor`
- 当前分支：`main`
- 当前最新提交：`f57621b docs(changelog): group entries by date`
- 工作区状态：生成本文件前已确认干净

近期关键提交：

```text
f57621b docs(changelog): group entries by date
eac3f85 feat(config): support keyword files
a056cdf fix(reliability): improve telegram delivery diagnostics
ddc9115 docs(ops): add daily launchd quick reference
99f7c57 docs(status): add launchd handoff summary
```

## 2. 当前运行状态

macOS `launchd` 后台服务正在运行：

```text
Label: com.rich.jin10-monitor
state: running
pid: 15482
program: /Users/rich/jin10-monitor/scripts/run_monitor.sh
stdout/stderr: /Users/rich/jin10-monitor/logs/jin10-monitor.log
last exit code: never exited
```

最近确认的 SQLite 游标：

```text
last_startup_at  = 2026-05-09 00:46:16
last_catchup_at  = 2026-05-09 00:46:16
last_ingested_at = 2026-05-09 04:08:54
last_ingested_id = 20260509040854765800
```

含义：

- 后台服务持续运行。
- WebSocket/REST 入库链路仍在推进。
- `last_ingested_at` 已明显晚于本次启动时间，说明实时消息在持续入库。

## 3. 已完成能力汇总

### 3.1 实时抓取与兜底

- WebSocket 主路接收金十实时快讯。
- REST 轮询作为兜底。
- 冷启动会预加载已有快讯 ID，避免重启后重复推旧消息。

### 3.2 Telegram 推送质量

- 推送分级：
  - `T3_IMPORTANT`：金十自身重要消息，显示为 `⚡`。
  - `T2_HIGH`：命中高优先级关键词，显示为 `🚨`。
  - `T1_NORMAL`：命中普通关键词，显示为 `📰`。
  - `T0_NONE`：不推送，仅入库。
- Telegram 发送失败日志已经增强：
  - 4xx/5xx 会记录 status、attempt、body。
  - 网络异常会记录异常类型和 `repr(error)`。
  - 超时不自动重试，避免消息实际已送达但本地重复发送。
- 对明确临时的 5xx 和网络连接异常有有限退避重试。

### 3.3 离线补拉

- 自动补拉窗口：`(last_ingested_at, startup_at]`。
- 自动补拉只入库并发送摘要，不逐条推送历史消息。
- 手动补拉支持指定时间窗口、入库上限、补发上限和发送间隔。
- `delivery_log` 记录 Telegram 已发送消息，避免补拉重复发送。
- 临时测试库默认不真实发送 Telegram，避免测试污染正式群。

### 3.4 历史留存

SQLite 默认路径：

```bash
data/jin10_history.sqlite3
```

关键表：

- `flash_history`：快讯正文、标题、来源、图片、优先级、原始 JSON。
- `runtime_state`：运行游标，如 `last_ingested_at`。
- `delivery_log`：Telegram 投递记录。

### 3.5 关键词外部配置

已支持不改代码管理关键词：

```bash
KEYWORDS_FILE=config/keywords.txt
HIGH_PRIORITY_FILE=config/high_priority.txt
```

文件格式：

- 一行一个关键词。
- 支持以 `#` 开头的注释。
- 不配置、文件缺失或文件为空时，自动回退内置默认关键词。

示例模板：

```text
config/keywords.example.txt
config/high_priority.example.txt
```

个人文件默认不提交：

```text
config/*.txt
```

但示例模板会提交：

```text
config/*.example.txt
```

## 4. 常用命令

进入项目：

```bash
cd /Users/rich/jin10-monitor
source .venv/bin/activate
```

查看后台状态：

```bash
./scripts/launchd/manage.sh status
```

查看实时日志：

```bash
./scripts/launchd/manage.sh logs
```

重载后台服务：

```bash
./scripts/launchd/manage.sh reload
```

停止后台服务：

```bash
./scripts/launchd/manage.sh stop
```

一次性抓取测试：

```bash
python jin10_monitor.py --once --limit 5
```

历史查询：

```bash
python jin10_monitor.py --history 伊朗 --history-limit 20
```

查看 SQLite 游标：

```bash
sqlite3 data/jin10_history.sqlite3 "select key, value, updated_at from runtime_state order by key;"
```

## 5. 当前观察结论

最近日志显示：

- `launchd` 服务持续运行。
- 消息持续入库和打印。
- `⚡`、`🚨`、`📰` 三类消息均出现。
- reload 后没有离线补拉摘要是正常的：当补拉窗口内 `入库 0 条，命中 0 条` 时不会发 Telegram 摘要，避免刷屏。

## 6. 下一步建议

### P1：启用个人关键词文件

如果想减少误推或聚焦交易相关消息，下一步可以创建：

```bash
cp config/keywords.example.txt config/keywords.txt
cp config/high_priority.example.txt config/high_priority.txt
```

再按你的关注方向调整关键词，并在 `.env` 开启：

```bash
KEYWORDS_FILE=config/keywords.txt
HIGH_PRIORITY_FILE=config/high_priority.txt
```

修改 `.env` 后重载后台服务。

### P2：事件聚合防刷屏 V2

目标：

- 同主题、同来源或相似标题在短时间内合并或降噪。
- T3 重要消息仍优先推送。
- 重复/相似消息继续入库，但 Telegram 减少刷屏。

建议这项单独开设计小版本，先定规则再改代码。

### P3：VPS/systemd

只有准备迁移到 VPS 后再做。需要考虑：

- `.env` 和 SQLite 迁移。
- 时区。
- systemd service。
- 日志轮转。
- 网络连通性。

## 7. 新 session 交接提示词

如果切换 session，可以直接贴：

```text
请先读取 /Users/rich/jin10-monitor/AGENTS.md、
/Users/rich/jin10-monitor/docs/status/003-2026-05-09-config-and-stability.md。

当前项目 hangfo/jin10-monitor 在 main 分支运行。
后台服务 com.rich.jin10-monitor 由 launchd 常驻，日志在 logs/jin10-monitor.log。
最新关键功能包括：离线补拉、Telegram 可靠性增强、关键词外部配置、CHANGELOG 日期分组。
禁止用 MCP API 直接写 GitHub；未经确认不要 commit/push。
下一步优先考虑启用个人关键词文件，或设计事件聚合防刷屏 V2。
```
