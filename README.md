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
- `python jin10_monitor.py`：常驻运行，WebSocket + REST 双路。

## 配置

- `KEYWORDS`：命中后才推送。空列表表示全部推送。
- `HIGH_PRIORITY`：命中后使用高优先级标头。
- `POLL_INTERVAL`：REST 兜底轮询间隔，默认 3 秒。
- `WS_RECONNECT_DELAY`：WebSocket 断线重连间隔，默认 5 秒。
- `WS_URLS`：WebSocket 地址列表，逗号分隔。默认使用本机已验证可解析的 `wss://wss-flash-2.jin10.com/`。
- `HISTORY_DB`：本地历史库路径，默认 `data/jin10_history.sqlite3`。

## 历史留存

脚本会把冷启动、REST、WebSocket 收到的快讯写入 SQLite，本地数据库默认不提交到 Git。字段包括快讯 ID、发布时间、标题、正文、关键词命中、高优先级标记、来源和原始 JSON。

## 说明

本项目只访问公开接口，不包含绕过登录、验证码、付费墙或其他访问控制的逻辑。实时消息可以辅助观察市场，但不构成交易建议；正式交易前建议结合行情源、风控和延迟监控一起使用。
