# Jin10 Monitor

金十快讯实时监控脚本：WebSocket 主路接收实时消息，REST 每隔数秒轮询兜底，命中关键词后推送到 Telegram。

## 快速启动

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python jin10_monitor.py --once --limit 20
python jin10_monitor.py --history 伊朗 --history-limit 20
python jin10_monitor.py --lookup-date 2026-05-02 --lookup-start 20:05 --lookup-end 20:20
python jin10_monitor.py --catch-up --from "2026-05-06 23:35" --to "2026-05-06 23:55" --no-catch-up-telegram
python jin10_monitor.py
```

在 `.env` 里填入：

```bash
TG_TOKEN=你的 Telegram Bot Token
TG_CHAT_ID=你的 Telegram chat_id
```

如果没有配置 Telegram，脚本会把命中的消息打印到控制台，适合先做本地验证。

## 模式

- `python jin10_monitor.py --once --limit 20`：一次性抓取最近快讯，用于验证接口、关键词和 Telegram 推送。
- `python jin10_monitor.py --history 伊朗 --history-limit 20`：查询本地历史库。
- `python jin10_monitor.py --history --history-high`：查看最近高优先级记录。
- `python jin10_monitor.py --lookup-date 2026-05-02 --lookup-start 20:05 --lookup-end 20:20`：直接从金十 REST 回溯指定时间窗口。
- `python jin10_monitor.py --catch-up --from "2026-05-06 23:35" --to "2026-05-06 23:55" --no-catch-up-telegram`：手动补拉指定离线窗口，只入库不发 Telegram。
- `python jin10_monitor.py --catch-up --from "2026-05-06 23:35" --to "2026-05-06 23:55" --catch-up-telegram --catch-up-max-send 10`：手动补拉并最多补发 10 条 Telegram。
- `python jin10_monitor.py`：常驻运行，WebSocket + REST 双路。

## 配置

- `KEYWORDS`：命中后才推送。空列表表示全部推送。
- `HIGH_PRIORITY`：命中后使用高优先级标头。
- `KEYWORDS_FILE`：可选，普通推送关键词文件路径，一行一个关键词，支持 `#` 注释。未配置、文件不存在或文件为空时使用内置默认关键词。
- `HIGH_PRIORITY_FILE`：可选，高优先级关键词文件路径，一行一个关键词，支持 `#` 注释。未配置、文件不存在或文件为空时使用内置默认关键词。
- `POLL_INTERVAL`：REST 兜底轮询间隔，默认 3 秒。
- `WS_RECONNECT_DELAY`：WebSocket 断线重连间隔，默认 5 秒。
- `WS_URLS`：WebSocket 地址列表，逗号分隔。默认使用本机已验证可解析的 `wss://wss-flash-2.jin10.com/`。
- `HISTORY_DB`：本地历史库路径，默认 `data/jin10_history.sqlite3`。
- `JIN10_APP_IDS`：REST 请求头 app id 列表，逗号分隔。默认先用当前页面常见 app id，再自动降级到旧 app id。
- `PUSH_IMPORTANT`：是否直接推送金十红色重要消息，默认 `1`。设为 `0` 时只按关键词推送。
- `AUTO_CATCHUP`：启动时是否自动补拉离线窗口，默认 `1`。
- `CATCHUP_TELEGRAM`：补拉是否允许发送 Telegram，默认 `1`。自动补拉只发送一条摘要，不逐条发送历史消息。
- `CATCHUP_MAX_HOURS`：自动补拉最多回看小时数，默认 24。
- `CATCHUP_MAX_STORE`：补拉最多入库条数，默认 1000。
- `CATCHUP_MAX_SEND`：手动补拉最多补发 Telegram 条数，默认 120。
- `CATCHUP_SEND_INTERVAL`：手动补发 Telegram 的发送间隔，默认 0.5 秒。
- `AUTO_CATCHUP_GAP_SECONDS`：常驻进程检测到 REST 轮询停顿超过该秒数后，会自动补拉一次摘要，默认 300；设为 `0` 可关闭。
- `SHOW_DELAY_IF_SECONDS`：消息发生时间距当前超过该秒数时，在 Telegram 和终端显示 `延迟：Xs`，默认 60；设为 `0` 可关闭。
- `ALLOW_TMP_TELEGRAM`：临时测试库是否允许真实发送 Telegram，默认 `0`。当 `HISTORY_DB=/tmp/...` 时，脚本会跳过真实 Telegram 发送并在终端显示跳过原因。

### 关键词文件

如果想在不改代码的情况下调整关键词，可以复制示例文件：

```bash
cp config/keywords.example.txt config/keywords.txt
cp config/high_priority.example.txt config/high_priority.txt
```

然后在 `.env` 里启用：

```bash
KEYWORDS_FILE=config/keywords.txt
HIGH_PRIORITY_FILE=config/high_priority.txt
```

`config/*.txt` 默认不提交到 Git，适合保存个人关键词；`config/*.example.txt` 会留在仓库里作为模板。后台服务修改关键词后需要重载：

```bash
./scripts/launchd/manage.sh reload
```

## 历史留存

脚本会把冷启动、REST、WebSocket 收到的快讯写入 SQLite，本地数据库默认不提交到 Git。字段包括快讯 ID、发布时间、标题、正文、关键词命中、高优先级标记、金十重要标记、HTML 加粗标记、来源和原始 JSON。

## 离线补拉

脚本会在 SQLite 的 `runtime_state` 表里维护游标：

- `last_ingested_at`：最新已入库消息的金十发生时间。
- `last_ingested_id`：对应的金十消息 ID。
- `last_startup_at`：本次启动时间。
- `last_catchup_at`：最近一次补拉执行时间。

自动补拉窗口为：

```text
(last_ingested_at, 本次启动时间]
```

也就是从上次已入库消息之后开始，到本次启动那一刻为止。自动补拉只入库并发送一条 Telegram 摘要，不逐条推送历史消息，避免补拉期间堵住实时新闻。

常驻运行时，如果 Mac 睡眠、网络长时间断开或进程被系统暂停，脚本会检测 REST 轮询是否停顿超过 `AUTO_CATCHUP_GAP_SECONDS`。恢复后会用同样的规则从 `last_ingested_at` 补到恢复时刻，并只发送一条“自愈补拉”摘要。摘要会列出最多 10 条 T3/T2 重点标题，方便快速判断是否需要手动逐条补发。

补拉跨多页时，终端会输出轻量进度日志，例如：

```text
catch-up page=1 source=catchup_auto window_hits=20 collected=20 existing=5
catch-up page=2 source=catchup_auto window_hits=23 collected=43 existing=18
```

查看游标是否正常推进：

```bash
sqlite3 data/jin10_history.sqlite3 "select key, value, updated_at from runtime_state order by key;"
sqlite3 data/jin10_history.sqlite3 "select id,published_at,source,priority_level,title from flash_history order by published_at desc limit 5;"
```

正常情况下，`last_ingested_at` 应该接近或等于 `flash_history` 最新记录的 `published_at`。

## 安全测试

为了避免测试污染正式 Telegram，临时 SQLite 库默认不真实发送 Telegram：

```bash
HISTORY_DB=/tmp/jin10_tmp_tg_guard.sqlite3 python jin10_monitor.py \
  --catch-up \
  --from "2026-05-06 23:35" \
  --to "2026-05-06 23:55" \
  --catch-up-telegram \
  --catch-up-max-send 1
```

这类测试会在终端显示：

```text
本次候选发送: 1 条
Telegram 已发送: 0 条
Telegram 已跳过: 1 条
```

如果确实要用临时库测试真实 Telegram 发送，需要显式设置：

```bash
ALLOW_TMP_TELEGRAM=1
```

## 后台常驻

macOS 本地后台常驻推荐使用 `launchd`。本仓库提供模板，但不会自动安装服务：

- 启动脚本：`scripts/run_monitor.sh`
- launchd 模板：`scripts/launchd/com.rich.jin10-monitor.plist`
- 管理脚本：`scripts/launchd/manage.sh`
- 操作文档：`docs/operations/001-launchd.md`

先确认脚本能手动运行，再按文档复制 plist 到 `~/Library/LaunchAgents/`：

```bash
chmod +x scripts/run_monitor.sh
chmod +x scripts/launchd/manage.sh
./scripts/launchd/manage.sh check
open docs/operations/001-launchd.md
```

日志默认写入：

```text
logs/jin10-monitor.log
```

### 日常运维速查

```bash
cd /Users/rich/jin10-monitor
./scripts/launchd/manage.sh status   # 看后台是否在运行
./scripts/launchd/manage.sh logs     # 看实时日志，Ctrl+C 只退出看日志
./scripts/launchd/manage.sh reload   # 更新代码或配置后重启后台服务
./scripts/launchd/manage.sh stop     # 临时停止后台服务
./scripts/launchd/manage.sh install  # 首次安装后台服务
./scripts/launchd/manage.sh uninstall # 停止并取消后台自启
```

`install` 和 `reload` 会自动执行 `launchctl enable`，用于恢复之前被标记为 disabled 的服务，减少 `Bootstrap failed: 5` 后还要手工补救的情况。

## 说明

本项目只访问公开接口，不包含绕过登录、验证码、付费墙或其他访问控制的逻辑。实时消息可以辅助观察市场，但不构成交易建议；正式交易前建议结合行情源、风控和延迟监控一起使用。
