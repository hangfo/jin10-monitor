# 外部与本地健康监控接入说明

更新时间：2026-06-25 04:28（Asia/Shanghai）

本文说明如何把 Dashboard `/healthz` 和 Telegram 健康心跳组合成第二层监控。默认边界保持不变：Dashboard 只允许绑定 `127.0.0.1` / `localhost`，不建议直接暴露到公网或局域网。

## `/healthz` 端点

```text
GET http://127.0.0.1:8765/healthz
```

正常响应：

```json
{
  "status": "ok",
  "history_db": "data/jin10_history.sqlite3",
  "history_db_exists": true,
  "read_boundary": "local_sqlite_readonly",
  "writes_business_db": false,
  "calls_jin10_rest": false,
  "sends_telegram": false,
  "missing_tables": []
}
```

`/healthz` 只验证 Dashboard 能否只读打开历史库和必要表是否齐全。它不验证 `jin10_monitor.py` 主进程是否仍在入库，也不验证 Telegram 是否能成功发送；主进程和 Telegram 通道仍以健康心跳为准。

## 推荐监控层次

| 层级 | 监控对象 | 建议方式 |
|---|---|---|
| 主进程与 Telegram | `jin10_monitor.py` 存活、Telegram 通道可用、`last_ingested_at` 新鲜度 | `HEALTH_HEARTBEAT_INTERVAL_S` 健康心跳 |
| Dashboard 与历史库 | Dashboard 进程可访问、SQLite schema 可读 | 本机 cron 或内网探针对 `/healthz` 执行 HTTP 检查 |
| 近期异常 | Telegram timeout、REST 403、Traceback、本地启动错误 | `/system` 最近 monitor 错误日志面板 |

## 本机 cron 检查

适合当前默认 localhost 部署，不需要开放端口。

```bash
*/5 * * * * cd /Users/rich/jin10-monitor && \
  STATUS=$(curl -sf -o /dev/null -w "%{http_code}" http://127.0.0.1:8765/healthz) && \
  [ "$STATUS" = "200" ] || \
  .venv/bin/python - <<'PY'
import os
import urllib.parse
import urllib.request

token = os.getenv("TG_TOKEN", "")
chat_id = os.getenv("TG_CHAT_ID", "")
if token and chat_id:
    text = "Dashboard /healthz 异常，请检查 127.0.0.1:8765/system"
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    data = urllib.parse.urlencode({"chat_id": chat_id, "text": text}).encode()
    urllib.request.urlopen(url, data=data, timeout=10)
PY
```

如果 `.env` 中有真实 Telegram 凭据，cron 脚本应先安全加载环境变量；不要把 token 或 chat_id 写入仓库。

## 内网或外部服务检查

如果确实需要 UptimeRobot、Better Uptime、Checkly 等外部服务检查 `/healthz`，不要把 FastAPI dashboard 直接改为 `0.0.0.0` 暴露。推荐顺序：

1. 通过 Tailscale、WireGuard、SSH tunnel 等私有通道访问 `127.0.0.1:8765`。
2. 或使用 Nginx / Caddy 反向代理，仅暴露 `/healthz`，并限制来源 IP 或加 Basic Auth。
3. 外部监控只断言 HTTP `200` 和 JSON 中 `"status":"ok"`。

示例 Checkly 断言：

```javascript
const response = await fetch("https://example.com/healthz");
const body = await response.json();

assert.equal(response.status, 200);
assert.equal(body.status, "ok");
assert.deepEqual(body.missing_tables, []);
```

## 注意事项

- `/healthz` 是只读检查，不触发金十 REST、不写 SQLite、不发送 Telegram。
- 不要把 `/system` 暴露到公网；它会显示本地日志路径、运行状态和近期错误摘要。
- 外部监控只能证明 Dashboard 和历史库可读，不能替代 Telegram 健康心跳。
