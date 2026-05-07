# 项目状态摘要 001：离线补拉工作流

更新时间：2026-05-07 00:45 左右（Asia/Shanghai）

## 1. 基本信息

- 项目：jin10-monitor
- GitHub 仓库：https://github.com/hangfo/jin10-monitor
- 本地路径：`/Users/rich/jin10-monitor`
- 当前功能分支：`feat/catchup`
- 当前功能提交：`aa61ce9 feat(catchup): add offline backfill workflow`
- 当前 `main` 基准：`5ad52f1 feat(alerts): separate priority levels and metadata`
- PR 地址：https://github.com/hangfo/jin10-monitor/pull/new/feat/catchup

## 2. 当前目标

本项目用于抓取金十快讯，并通过终端和 Telegram 尽快推送交易相关消息。

核心目标：

- WebSocket 主路实时监听金十快讯。
- REST 轮询作为兜底，降低漏消息风险。
- 按关键词和金十自身重要性做分级推送。
- 保存 SQLite 历史，便于后续查询、复盘和离线补拉。
- 离线期间重新启动后，自动补齐未运行期间的消息。

## 3. 已完成能力

### 3.1 实时抓取

- WebSocket 使用金十私有二进制协议解析。
- REST 轮询保留为双保险。
- `seen_ids` 使用有序去重，避免无序 set 随机淘汰问题。

### 3.2 推送分级

当前分级为稳定字符串，已入库：

- `T3_IMPORTANT`：金十自身标红的重要消息，最高级。
- `T2_HIGH`：命中 `HIGH_PRIORITY` 关键词。
- `T1_NORMAL`：命中普通 `KEYWORDS`。
- `T0_NONE`：不推送，仅入库或冷启动预热。

显示含义：

- `T3_IMPORTANT` 用 `⚡`。
- `T2_HIGH` 用 `🚨`。
- `T1_NORMAL` 用 `📰`。

### 3.3 数据库历史

SQLite 默认路径：

```bash
data/jin10_history.sqlite3
```

已经存储的关键字段包括：

- 金十消息 ID
- 发布时间 `published_at`
- 标题、正文
- 是否重要 `important`
- 是否有标题 `has_title`
- 是否加粗 `has_bold`
- 是否有图 `has_pic`
- 图片链接 `pic_url`
- 正文来源文字 `news_source`
- 外部来源链接 `source_url`
- 推送优先级 `priority_level`
- 采集来源 `source`
- 原始 JSON `raw_json`

### 3.4 离线补拉

已完成 V1：

- 启动时自动读取 `runtime_state.last_ingested_at`。
- 自动补拉窗口为 `(last_ingested_at, startup_at]`。
- 自动补拉只入库，并发送一条 Telegram 摘要。
- 自动补拉不逐条推送历史消息，避免阻塞实时新闻。
- 手动补拉支持指定时间窗口，并可选择是否补发 Telegram。
- 同一金十消息 ID 不重复入库。
- 已经 Telegram 推送过的消息不会被补拉重复发送。

相关表：

- `runtime_state`：记录 `last_ingested_at`、`last_ingested_id`、`last_startup_at`、`last_catchup_at`。
- `delivery_log`：记录 Telegram 已发送消息，区分 `realtime` 和 `catchup`。

### 3.5 临时测试库保护

为了避免测试污染正式 Telegram：

- 当 `HISTORY_DB=/tmp/...`、`/private/tmp/...`、`/var/folders/...` 时，默认跳过真实 Telegram 发送。
- 终端会显示测试确实走到了发送环节，例如：

```text
本次候选发送: 1 条
Telegram 已发送: 0 条
Telegram 已跳过: 1 条
```

如确实需要用临时库真实发送 Telegram，必须显式设置：

```bash
ALLOW_TMP_TELEGRAM=1
```

## 4. 常用命令

进入项目：

```bash
cd /Users/rich/jin10-monitor
source .venv/bin/activate
```

正式常驻运行：

```bash
python jin10_monitor.py
```

一次性抓取测试：

```bash
python jin10_monitor.py --once --limit 5
```

手动补拉但不发 Telegram：

```bash
python jin10_monitor.py \
  --catch-up \
  --from "2026-05-06 23:35" \
  --to "2026-05-06 23:55" \
  --no-catch-up-telegram \
  --catch-up-max-store 80 \
  --catch-up-max-send 10
```

临时库安全测试 Telegram 发送链路：

```bash
HISTORY_DB=/tmp/jin10_tmp_tg_guard.sqlite3 python jin10_monitor.py \
  --catch-up \
  --from "2026-05-06 23:35" \
  --to "2026-05-06 23:55" \
  --catch-up-telegram \
  --catch-up-max-store 80 \
  --catch-up-max-send 1 \
  --catch-up-send-interval 0
```

## 5. 配置项

真实密钥只放 `.env`，禁止提交。

当前关键配置：

- `TG_TOKEN`：Telegram Bot token。
- `TG_CHAT_ID`：Telegram 接收 chat id。
- `HISTORY_DB`：SQLite 历史库路径。
- `AUTO_CATCHUP`：是否启动自动补拉，默认开启。
- `CATCHUP_TELEGRAM`：是否允许补拉相关 Telegram，默认开启。
- `CATCHUP_MAX_HOURS`：自动补拉最多回看小时数，默认 24。
- `CATCHUP_MAX_STORE`：补拉最多入库条数，默认 1000。
- `CATCHUP_MAX_SEND`：手动补拉最多 Telegram 补发条数，默认 120。
- `CATCHUP_SEND_INTERVAL`：手动补发 Telegram 间隔秒数，默认 0.5。
- `ALLOW_TMP_TELEGRAM`：临时库是否允许真实发 Telegram，默认关闭。

## 6. 已验证内容

已执行并通过：

```bash
python3 -m py_compile jin10_monitor.py
git diff --check
```

已验证临时库 Telegram 保护：

- 候选发送能产生。
- 真实 Telegram 不发送。
- 终端显示 `Telegram 已跳过` 和跳过原因。

已验证补拉去重：

- 首次补拉可入库。
- 同窗口再次补拉显示 `入库: 0 条`、`已存在未重复入库: N 条`。

## 7. 当前未完成 / 待观察

- `feat/catchup` 已 push，但尚未 merge 到 `main`。
- 建议先在真实环境运行 30-60 分钟，确认：
  - 启动时只发一条离线补拉摘要。
  - 实时新闻仍能及时推送。
  - 没有重复入库或重复 Telegram。
- 稳定后再 merge 到 `main`。

## 8. 下一步建议优先级

1. 真实试运行 `feat/catchup` 分支。
2. 补 README 和 `.env.example`，写清楚离线补拉和临时库保护配置。
3. 稳定后 merge `feat/catchup` 到 `main`。
4. 增加本地进程守护：
   - macOS 本地优先考虑 `launchd`。
   - VPS 再考虑 `systemd`。
5. V2：实时优先队列。
   - 历史补发如果逐条进行，必须允许实时消息插队。
   - 避免历史消息补发 1 分钟时阻塞最新快讯。
6. Telegram inline 按钮：
   - 回溯前后 15 分钟。
   - 静音同主题。
7. 事件聚合防刷屏：
   - 同主题 2-5 分钟合并。
8. 行情关联：
   - 新闻发生前后抓 ETH/BTC/黄金/美股指数变化，用于复盘。

## 9. 命名和留存规则

建议以后所有项目状态摘要都放在：

```bash
docs/status/
```

命名格式：

```text
NNN-YYYY-MM-DD-topic.md
```

示例：

```text
001-2026-05-07-catchup-workflow.md
002-2026-05-07-merge-main-and-docs.md
003-2026-05-08-launchd-supervisor.md
```

规则：

- 每个大节点生成一份，不需要每次小改都生成。
- 大节点包括：核心功能完成、merge 到 main、部署方式变化、数据库结构变化、Telegram 行为变化。
- 摘要可以同步 GitHub，因为不含密钥，且对迁移环境有帮助。
- `CHANGELOG.md` 记录版本变化；`docs/status/` 记录上下文和交接信息。

## 10. 新 session 交接提示词

如果切换 session，可以直接贴下面这段：

```text
请先读取 /Users/rich/jin10-monitor/AGENTS.md 和 /Users/rich/jin10-monitor/docs/status/001-2026-05-07-catchup-workflow.md。
当前项目是 hangfo/jin10-monitor，功能分支 feat/catchup 已 push，最新提交 aa61ce9。
不要直接用 MCP 写 GitHub，不要未经确认 commit/push。
下一步优先检查 feat/catchup 的真实运行情况，再决定是否 merge main。
```
