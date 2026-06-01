更新时间：2026-06-01 00:15（Asia/Shanghai）

# REST 长期 403 下的补拉替代设计评估

## 1. 当前结论

当前不要立刻把外部源接入运行链路。

推荐顺序：

1. 先强化现有 WebSocket initial history / reconnect 的短缺口恢复能力。
2. 同步把补拉能力设计成 adapter 边界，但首版只做设计和只读 probe。
3. 用更强运行告警覆盖 REST 长期 403 的可见性。
4. 金十 REST 请求策略只作为受控实验，不作为主线修复。

原因：

- WebSocket 实时主路当前正常，Telegram realtime 最近持续有 `sent`。
- REST 已经验证为反复 `forbidden_backoff`，继续堆 header / app id 容易变成脆弱的私有接口对抗。
- Dashboard 必须继续保持本地只读诊断和分析侧车，不应成为采集入口。
- 外部新闻源的 ID、时间、字段、版权和覆盖范围都不同，不能直接混入现有 Telegram 去重和业务历史语义。

## 2. 只读运行证据

只读检查时间约为 `2026-06-01 00:04（Asia/Shanghai）`。

仓库状态：

```text
main...origin/main
HEAD=35032e9 docs(dashboard): localize mid-phase handoffs
工作区干净
```

运行状态：

```text
launchd: com.rich.jin10-monitor running, pid=49084
rest_status=forbidden_backoff
rest_forbidden_streak=7
rest_last_error=HTTP 403 4/4 entries; backoff 900s
rest_last_ok_at=2026-05-31 22:50:31
rest_backoff_until=2026-06-01 00:06:05
```

24h 入库来源：

```text
ws|2026-05-31 23:57:59|64
ws_initial|2026-06-01 00:01:30|21
rest|2026-05-31 22:30:12|47
catchup_auto|2026-05-31 22:26:51|115
```

Telegram 状态：

```text
sent|48|2026-05-31 15:58:01
unknown_timeout|44|2026-05-31 14:31:59
failed|3|2026-05-31 09:27:01
```

判断：

- WebSocket 主路可用。
- `ws_initial` 已经能在 reconnect 后保存比 `last_ingested_at` 更新的历史快照。
- REST 最近仍不可依赖。
- catch-up 仍绑定金十 REST，因此 REST 403 会让自动补拉退化。
- Telegram 最近成功发送，不应因为旧 `unknown_timeout` 自动重发。

## 3. 外部来源评估

### 3.1 Glanceway 的金十源示例

来源：

- https://glanceway.app/source/codytseng/jin10/

它的作用：

- 证明社区示例仍在使用当前仓库类似的非官方金十快讯接口：
  `https://flash-api.jin10.com/get_flash_list?channel=-8200&vip=1`
- 示例只带 `x-app-id=bVBF4FyRTn5NJF5n` 和 `x-version=1.0.0`。

对当前项目的价值：

- 有用，但只适合作为对照样本。
- 它说明我们当前策略没有明显少掉一个公开参数；也反过来说明 403 更可能来自访问策略、地域、频率、服务端规则或非官方接口收紧。

不能怎么用：

- 不能直接复制到生产链路，因为当前本机已经对同类请求出现连续 403。
- 不能把它当成稳定补拉源；它和现有 REST 是同源接口，失败相关性很高。

安全用法：

- 只放进离线 probe 文档或受控 probe 脚本。
- probe 输出只写终端或独立诊断 JSON，不写 `flash_history`、`delivery_log`、`telegram_delivery_status`。

### 3.2 金十官方 API / 开放平台

来源：

- https://flash.jin10.com/detail/20230609193240074100
- https://www.jin10.com/about/index.html
- https://www.jin10.com/example/websiteiframe.html

它的作用：

- 官方曾宣传金十开放平台 API，覆盖 7x24 快讯、财经日历、行情数据、深度分析文章等。
- 金十关于我们页面明确其内容和服务归广州金十信息科技有限公司运营。
- 免费引用页协议明确禁止抓取、索引、缓存后再加工；页面还显示免费引用页及关联接口已于 `2025-12-01` 停止服务。

对当前项目的价值：

- 这是长期最干净的金十补拉方案。
- 如果用户愿意申请或购买 token，它可以作为 `jin10_official` adapter，而不是继续依赖私有 web/app 接口。

不能怎么用：

- 不能在没有授权、token、调用条款和速率限制说明的情况下假装它已经可接入。
- 不能从 Dashboard 页面直接请求官方 API。

安全用法：

- 先只设计 adapter 接口和配置位。
- 等 token 和条款明确后，在采集进程里接，不在 Dashboard 接。
- 默认不开启；失败时不影响 WebSocket。

### 3.3 WallstreetCN 7x24 示例

来源：

- https://glanceway.app/fr/source/codytseng/wallstreetcn/

它的作用：

- 示例使用 `https://api-one.wallstcn.com/apiv1/content/lives?channel=...&limit=200`。
- 支持 `global-channel`、A 股、美股、外汇、商品、港股等频道。

对当前项目的价值：

- 可作为“替代补拉源”的候选，但它不是金十。
- 更适合作为跨源对照、缺口提示、或者分析侧证据补充。

风险：

- 内容覆盖和金十不一致，不能保证补齐金十漏掉的同一条消息。
- ID namespace 不同，直接入 `flash_history.id` 会污染现有去重语义。
- 文章来源、版权和转发边界需要单独确认。

安全用法：

- 首版只做 `external_probe` 或独立 `source_candidate` 输出。
- 如后续入库，必须使用独立 ID namespace，例如 `wallstreetcn:{id}`，并明确 `source='external_wallstreetcn'`。
- 默认不发 Telegram；最多在 Dashboard 系统页提示“外部源有相邻时间新闻，可人工核对”。

### 3.4 CoinGlass newsflash API

来源：

- https://docs.coinglass.com/v4.0-zh/reference/newsflash-list

它的作用：

- 官方文档提供 `GET https://open-api-v4.coinglass.com/api/newsflash/list`。
- 参数支持 `start_time`、`end_time`、`language`、`page`、`per_page`。
- 需要 `CG-API-KEY`。

对当前项目的价值：

- 对加密货币相关快讯和行情背景有价值。
- 不适合作为金十宏观快讯的通用替代补拉源。

风险：

- 需要 API key 和费用/额度边界。
- 覆盖范围偏 crypto，不适合补齐全部宏观、央行、地缘、商品快讯。
- 时间字段和内容结构需要归一化。

安全用法：

- 放在未来 market / crypto context adapter，而不是核心 catch-up。
- 只在用户主动分析 crypto 标的或打开相关分析时读取。
- 不写业务历史库；最多写独立分析库或内存缓存。

## 4. 方案对比

| 方案 | 推荐级别 | 解决什么 | 成本 | 主要风险 | 对 Telegram / SQLite / Dashboard 边界 |
| --- | --- | --- | --- | --- | --- |
| 强化 WebSocket initial history / reconnect | P0 | REST 403 时的短缺口恢复 | 低-中 | initial history 深度有限 | 不改 Telegram 去重；仍写业务历史；Dashboard 只读 |
| 补拉 adapter 边界 | P1 | 为官方 API 或外部源预留隔离层 | 中 | 抽象过早或边界不清 | 必须保留 source/id namespace；不从 Dashboard 调用 |
| 运行告警增强 | P1 | 让 REST 长期退化和补拉停摆更早可见 | 低 | 只告警不恢复 | 只读诊断；不发/不重发 Telegram |
| 金十 REST 请求策略修复 | P2 | 尝试恢复当前非官方 REST | 中 | 继续 403、规则漂移、对抗性维护 | 只允许受控 probe；不应默认接生产 |
| WallstreetCN 替代源 | P2 | 非金十新闻对照 | 中 | 内容不等价、版权和去重污染 | 首版不入业务库、不发 Telegram |
| CoinGlass newsflash | P3 | crypto 快讯/分析上下文 | 中 | 范围偏窄、需要 key | 不作为核心补拉源；放分析侧 |
| 金十官方 API | P1/P2 | 长期稳定金十补拉 | 中-高 | 需要授权、费用、条款 | 最干净，但必须等 token 和条款明确 |

## 5. 推荐实现路线

### Step 1：只读设计与状态指标

本阶段只改文档和可选只读诊断，不改采集行为。

建议新增指标：

- `last_ws_initial_at`
- `last_ws_initial_newest_published_at`
- `last_ws_initial_count`
- `last_ws_initial_saved_count`
- `rest_degraded_since`
- `catchup_source_status`

边界：

- 不发 Telegram。
- 不写 `delivery_log`。
- 不从 Dashboard 请求外部 API。

### Step 2：WebSocket initial history 短缺口恢复

目标：

- reconnect 后 initial list 中如发现比当前 `last_ingested_at` 更新、且符合推送条件的消息，先只记录诊断。
- 第二阶段再决定是否允许摘要式告警，而不是逐条补发。

建议默认行为：

- `ws_initial` 继续入 `flash_history`。
- 不推进或谨慎推进 `last_ingested_at`，需要先确认不会让真实 `ws` 实时游标被历史快照提前覆盖。
- 不自动 Telegram 补发。

### Step 3：补拉 source adapter

建议接口：

```text
BackfillSource.fetch_window(start_dt, end_dt) -> BackfillPageResult
```

首批 adapter：

- `jin10_legacy_rest`：当前 `fetch_page_sync()` 的封装。
- `jin10_official`：仅占位，等授权 token。
- `wallstreetcn_probe`：只读对照，不写业务库。
- `coinglass_probe`：crypto 分析上下文，不进核心 catch-up。

### Step 4：受控 probe

probe 输出只允许：

- 终端表格
- 独立 `data/source_probe/*.json`
- Dashboard 只读展示

probe 禁止：

- 写 `flash_history`
- 写 `delivery_log`
- 写 `telegram_delivery_status`
- 调用 Telegram
- 从 Dashboard 发起采集请求

## 6. 明确不做

- 不把 WallstreetCN 或 CoinGlass 直接混入现有金十业务历史库。
- 不用外部源消息替代金十消息 ID。
- 不自动重发 `unknown_timeout`。
- 不让 Dashboard 成为采集入口。
- 不继续扩展旧 `jin10_monitor.py --dashboard` 原型。
- 不把 Glanceway 示例当作可长期依赖的生产接口。
- 不在没有金十官方授权的情况下接入所谓官方 API。

## 7. 下一步建议

建议下一步先做 Step 1：

1. 在 `jin10_monitor.py` 中只增加 WebSocket initial history 诊断状态写入。
2. 在 `/system` 增加只读展示。
3. 增加 no-network tests 覆盖状态写入和 Dashboard 查询。
4. 不改变推送、不改变补拉、不改外部源。

这一步建议使用 `GPT-5.5 高`，因为虽然改动可以很小，但涉及 WebSocket、runtime_state、补拉游标和 Telegram 去重边界。
