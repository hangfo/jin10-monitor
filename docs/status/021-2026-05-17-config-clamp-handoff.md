# 项目状态摘要 021：数值配置范围保护已完成

更新时间：2026-05-17（Asia/Shanghai）

## 1. 这份文档的用途

本文件用于在新 session 中快速续接配置范围保护阶段，不需要回读旧聊天。

这份摘要重点覆盖：

- `.env` 数值配置上下限保护已经如何落地。
- README 与 `.env.example` 已经如何同步。
- 当前验证结果、风险判断和下一步建议。

## 2. 当前仓库状态

- 项目：jin10-monitor
- GitHub 仓库：https://github.com/hangfo/jin10-monitor
- 本地路径：`/Users/rich/jin10-monitor`
- 分支：`main`
- 当前最新提交：
  - `df549b3 fix(config): clamp remaining numeric envs`

最近配置范围保护提交：

```text
df549b3 fix(config): clamp remaining numeric envs
0e2540e fix(config): clamp catchup send interval
45232a7 fix(config): clamp catchup send limit
e2da331 fix(config): clamp catchup store limit
293867a fix(config): clamp poll interval range
d3e0f92 fix(config): clamp websocket reconnect delay
db2ba62 docs(config): assess numeric clamp ranges
```

新 session 仍必须重新执行本地 Git 检查，不要只凭本文件判断现场状态。

## 3. 本阶段已完成内容

### 3.1 配置范围 helper

已新增或复用：

- `env_min_float(name, default, minimum)`
- `env_range_float(name, default, minimum, maximum)`
- `env_range_int(name, default, minimum, maximum)`

这些 helper 继续保留原有容错语义：

- 空值使用默认值。
- 非法字符串使用默认值并记录 warning。
- 合法但低于下限或高于上限的值会被 clamp，并记录 warning。

### 3.2 已保护的 `.env` 数值配置

| 配置 | 默认值 | 当前范围 | 说明 |
| --- | ---: | ---: | --- |
| `WS_RECONNECT_DELAY` | `5` | `>=1` | 避免负数传入 WebSocket 重连 sleep。 |
| `POLL_INTERVAL` | `3` | `1-60` | 避免 REST 轮询过密或兜底明显变慢。 |
| `CATCHUP_MAX_HOURS` | `24` | `1-168` | 限制自动补拉最大回看窗口。 |
| `CATCHUP_MAX_STORE` | `1000` | `20-5000` | 控制补拉扫描、内存和 SQLite 写入压力。 |
| `CATCHUP_MAX_SEND` | `120` | `0-300` | `0` 保留为关闭逐条补发。 |
| `CATCHUP_SEND_INTERVAL` | `0.5` | `0-10` | `0` 保留为不等待。 |
| `AUTO_CATCHUP_GAP_SECONDS` | `300` | `0-86400` | `0` 保留为关闭 gap 自愈补拉。 |
| `SHOW_DELAY_IF_SECONDS` | `60` | `0-3600` | `0` 保留为关闭延迟提示。 |

## 4. 文档更新

已更新：

- `README.md`
  - 在配置说明中标明数值配置范围。
  - 明确 `CATCHUP_MAX_SEND=0`、`CATCHUP_SEND_INTERVAL=0`、`AUTO_CATCHUP_GAP_SECONDS=0`、`SHOW_DELAY_IF_SECONDS=0` 的语义。
- `.env.example`
  - 在相关配置行旁标注范围。
- `CHANGELOG.md`
  - 所有配置范围保护按 `2026-05-17` 小节记录。

## 5. 验证结果

最近一次完整验证：

```bash
git diff --check
.venv/bin/python -m pytest
```

pytest 结果：

```text
59 passed
```

已做过的坏配置导入检查包括：

```bash
WS_RECONNECT_DELAY=-2
POLL_INTERVAL=-2
POLL_INTERVAL=120
CATCHUP_MAX_STORE=0
CATCHUP_MAX_STORE=999999
CATCHUP_MAX_SEND=-1
CATCHUP_MAX_SEND=0
CATCHUP_MAX_SEND=999
CATCHUP_SEND_INTERVAL=-1
CATCHUP_SEND_INTERVAL=0
CATCHUP_SEND_INTERVAL=99
CATCHUP_MAX_HOURS=0
CATCHUP_MAX_HOURS=999
AUTO_CATCHUP_GAP_SECONDS=0
AUTO_CATCHUP_GAP_SECONDS=999999
SHOW_DELAY_IF_SECONDS=9999
```

## 6. 当前风险判断

整体风险等级：低。

影响范围：

- WebSocket：只影响断线重连等待配置读取。
- REST：只影响兜底轮询间隔配置读取。
- Telegram 推送：只影响手动补拉逐条补发数量和间隔的默认配置读取。
- SQLite 历史库：未修改 schema；只间接限制补拉最大入库条数。
- 补拉去重：未修改，继续保护“已成功发送过的 Telegram 不重复补发”语义。
- 启动方式：未修改。
- CLI 参数：未修改。

残余风险：

- 如果用户以前故意设置超出范围的 `.env` 值，现在会被 clamp 到边界，并记录 warning。
- CLI 参数仍可能传入超大或负数值，例如 `--catch-up-max-store`、`--catch-up-max-send`、`--catch-up-send-interval`。这属于显式命令输入，尚未处理。

## 7. 下一步优先级

建议继续小步推进，不要大规模重构。

优先候选：

1. 评估并决定是否 clamp CLI 参数
   - `--catch-up-max-store`
   - `--catch-up-max-send`
   - `--catch-up-send-interval`
   - 建议先评估行为，再决定是否沿用同一范围。

2. 继续补 `crawl_window` 或补拉相关 mock REST 边界
   - 可继续保持无网络 pytest。
   - 避免真实 Telegram 和真实 REST。

3. 自动补拉主循环 gap 触发条件测试
   - 只有能小步 mock 时再做。
   - 如果需要较多 async orchestration，建议切更高推理档位。

暂缓：

- SQLite 并发压力测试。
- launchd 实际运行验证。
- 自动补拉逐条补发配置化。
- 事件聚合防刷屏 V2。

## 8. 模型建议

下一阶段继续使用 `GPT-5.5 中`。

理由：

- 如果只是 CLI 参数 clamp 评估、文档更新或小范围 pytest，`GPT-5.5 中` 足够。
- 只有进入自动补拉主循环异步测试、SQLite 并发判断、launchd 实际运行验证或更大范围行为重构时，才建议切到 `GPT-5.5 高`。

## 9. 新 session 交接提示词

新开 session 后可以直接贴：

```text
请继续 /Users/rich/jin10-monitor 项目。

建议模型：GPT-5.5 中。
如需进入自动补拉主循环异步测试、SQLite 并发判断、launchd 实际运行验证或较大行为重构，再切 GPT-5.5 高。

先读取：
1. /Users/rich/jin10-monitor/AGENTS.md
2. /Users/rich/jin10-monitor/docs/status/021-2026-05-17-config-clamp-handoff.md

默认不要回读旧聊天。先执行：
git branch --show-current
git status
git pull --rebase
git log --oneline -6

当前阶段目标：
继续最小 pytest / 配置可靠性阶段。`.env` 数值配置范围保护已完成并推送，README 和 .env.example 已同步。下一步优先评估是否对 CLI 参数做同样 clamp，尤其是 --catch-up-max-store、--catch-up-max-send、--catch-up-send-interval。

要求：
- CHANGELOG.md 必须按真实提交日期写入当天小节，不要把多日改动堆在 Unreleased。
- 查询和诊断入口只做只读，不要实现重试队列。
- 优先做最小可靠修复，不要大规模重构模块。
- 继续保护现有补拉去重语义：已成功发送过的 Telegram 不重复补发。
- 如果新增 CLI 用户操作方式，预计需要更新 README.md 和 CHANGELOG.md。
- 修改后给 diff、风险和验证。
- commit/push 前更新 CHANGELOG.md。
- 一般情况直接推进；只有需要重要产品/风险判断时再停下来问我。
```
