# 项目状态摘要 020：数值配置上下限保护评估清单

更新时间：2026-05-17（Asia/Shanghai）

## 1. 这份文档的用途

本文件只评估数值配置的建议范围和误填风险，不实装批量 clamp。

当前配置读取逻辑：

- `env_int()` / `env_float()` 会在空值或非法字符串时使用默认值。
- 大部分合法但不合理的数值（负数、0、极大值）会原样进入运行逻辑。
- 少数调用点已有局部保护，例如 `SHOW_DELAY_IF_SECONDS = max(0, ...)`、轮询 sleep 使用 `max(1.0, ...)`、自动补拉回看小时数使用 `max(1, CATCHUP_MAX_HOURS)`。

## 2. 建议范围与风险

| 配置 | 当前默认 | 当前保护 | 建议下限 | 建议上限 | 误填风险 |
| --- | ---: | --- | ---: | ---: | --- |
| `POLL_INTERVAL` | `3` 秒 | sleep 时至少 `1.0` 秒 | `1` 秒 | `60` 秒 | 过小会增加 REST 请求频率；过大时 REST 兜底变慢，且 gap 检测只在下一轮 poll loop 开始时判断，发现停顿会更迟。负数目前会被 sleep 下限兜住，但日志仍显示负间隔。 |
| `WS_RECONNECT_DELAY` | `5` 秒 | 无 | `1` 秒 | `300` 秒 | 过小会在 WebSocket 故障时频繁重连；负数会导致 `asyncio.sleep()` 抛错，可能让 WebSocket 循环异常退出。 |
| `CATCHUP_MAX_HOURS` | `24` 小时 | 自动补拉 floor 使用 `max(1, ...)` | `1` 小时 | `168` 小时 | 过小会截断离线窗口；过大会放大 REST 扫描和 SQLite 写入压力。负数在自动补拉中会被当成 1 小时，但摘要仍可能显示原配置值，容易误导排查。 |
| `CATCHUP_MAX_STORE` | `1000` 条 | `catch_up_window()` 内无统一下限 | `20` 条 | `5000` 条 | 过小会导致补拉窗口过早截断；过大会增加 REST 翻页、内存和 SQLite 写入压力。0 或负数会让 max_pages 退化为最小页数，但收集逻辑语义不直观。 |
| `CATCHUP_MAX_SEND` | `120` 条 | `select_catchup_send_candidates()` 对 `<=0` 返回空 | `0` 条 | `300` 条 | 过大时手动补发可能刷屏；0 可作为关闭逐条补发的显式值。负数目前等价于 0，但不够清晰。 |
| `CATCHUP_SEND_INTERVAL` | `0.5` 秒 | 发送循环只在 `>0` 时 sleep | `0` 秒 | `10` 秒 | 过小会密集发送 Telegram；过大时手动补发耗时明显。负数目前等价于 0，但不够清晰。 |
| `AUTO_CATCHUP_GAP_SECONDS` | `300` 秒 | `<=0` 关闭 gap 自愈补拉 | `0` 秒 | `86400` 秒 | 0 可作为关闭开关；过小会让短暂停顿频繁触发补拉摘要；过大会让睡眠或断网后的自愈发现太慢。负数目前等价于关闭。 |
| `SHOW_DELAY_IF_SECONDS` | `60` 秒 | 启动时 `max(0, ...)` | `0` 秒 | `3600` 秒 | 0 可作为关闭延迟提示；过大会隐藏明显延迟；负数已经被压到 0。 |

## 3. 建议推进顺序

优先建议只做两类最小保护：

1. 先保护会直接造成运行异常的字段：
   - `WS_RECONNECT_DELAY`：下限至少 `1`，避免负数传入 `asyncio.sleep()`。
2. 再保护会造成明显资源或刷屏风险的字段：
   - `POLL_INTERVAL`、`CATCHUP_MAX_STORE`、`CATCHUP_MAX_SEND`、`CATCHUP_SEND_INTERVAL`、`AUTO_CATCHUP_GAP_SECONDS`。

暂不建议一次性批量 clamp 所有字段。更稳的做法是先加一个通用但很小的范围读取 helper，并先覆盖 1-2 个高风险字段，配套 pytest 验证 warning、fallback 和边界值。

## 4. 测试建议

如果下一步实装，建议新增纯函数级测试，不启动真实网络：

- 非法字符串继续回默认值。
- 低于下限时返回下限并记录 warning。
- 高于上限时返回上限并记录 warning。
- 明确允许 0 的字段（例如 `AUTO_CATCHUP_GAP_SECONDS`、`SHOW_DELAY_IF_SECONDS`、`CATCHUP_MAX_SEND`、`CATCHUP_SEND_INTERVAL`）不被误改成 1。

## 5. 当前判断

本清单只是评估，不改变运行行为。当前最值得优先实装的是 `WS_RECONNECT_DELAY` 下限保护，因为负数可能直接让 WebSocket 重连 sleep 抛错；其次才是资源型上限保护。
