更新时间：2026-06-08 21:15（Asia/Shanghai）

# Changelog

## Unreleased

## 2026-06-08

- 接纳 `047-049` 深度 review 的稳定性修复：Dashboard 启动时自动恢复因服务重启遗留的 `running` 分析草稿；Provider 后台完成只能从 `running` 写入，手动回填只能从 `draft` 写入，避免后台结果覆写人工结果；running 详情页显示已等待秒数和同 Provider 历史 P50 预计耗时并自动刷新；统一 GLM Provider 检测、过滤 Gemini thinking part、修复 `/system` 中 `info` 状态 pill 颜色，并将 Binance K 线时间链路固定为北京墙上时间与 UTC epoch 的显式转换。
- 改进 Provider 失败后的草稿续跑体验：失败详情页不再继续显示“已开始后台调用”，会明确提示草稿已保留、可切换 Gemini/GLM 重新调用或手动粘贴严格 JSON；手工回答文本框固定浅色可输入样式并说明用途；历史草稿缺失 Prompt 时，重试 Provider 会尝试用已保存的问题、窗口和证据列表重新生成并写回 Prompt。
- 增强 `/analyze` Provider 结果复核与失败体验：对单条低相关、非标的直接证据的高置信 `news_driven` 输出进行本地降级，避免 GLM/Gemini 把弱证据保存成 70% 高置信结论；手动回填空回答不再保存为已完成；失败草稿优先显示实际模型名；OpenAI-compatible 空响应错误增加模型、finish reason、message keys 和 token usage 摘要。
- 将 `/analyze` Provider 调用改为后台执行：点击“调用并保存”后立即回到详情页，草稿进入 `调用中` 状态并记录 Provider、开始时间和耗时占位；后台完成后保存结果，失败则回到草稿并保留错误与实际耗时。该状态只写独立分析库，不触碰业务历史库、采集链路或 Telegram。
- 增强 GLM Provider 弱证据保护与耗时可见性：仅对 GLM/OpenAI-compatible 调用追加专用 system 约束，要求正文使用中文、单条 indirect/mixed 证据优先判为 `unclear` 且不得高置信强行归因；Provider 成功或失败都会记录耗时，分析详情页和历史页可直接看到本次调用耗时；GLM 对单条 mixed 证据给出高置信 `news_driven` 时，详情页显示本地复核提示；详情、历史和对比页将 judgement 枚举展示为中文。

## 2026-06-07

- 增强 `/analyze` Provider 失败诊断：Provider 调用重定向会保留本次选择的 provider，下次回到草稿页时对应下拉项仍被选中；模型返回不可解析 JSON 时，错误详情会记录实际模型标签和原始返回短预览，便于区分 GLM/Gemini 解析失败、超时和模型输出格式问题。
- 新增 Provider 同窗 A/B 评测计划和只读导出脚本：可将指定 `analysis_runs.id` 导出为固定实验包，包含 `prompt.md`、`evidence_packet.json`、`ab_scorecard.md` 和 `metadata.json`，便于用同一 evidence packet 对比 Gemini、ChatGPT Plus 与 GLM Flash；脚本只读独立分析库，不请求模型 API、不请求金十 REST、不写业务历史库、不触发 Telegram。
- 将 `/analyze` 证据默认选择升级为 v3：候选仍最多展示 40 条，但默认只选高相关、低重复、非汇总预告的证据；低相关、汇总、预告和噪声消息仍可见并可手动勾选，减少 Gemini 因 Prompt 过长而超时或压缩结论。
- 持久化 Provider 调用失败原因：Gemini `MAX_TOKENS`、不可解析 JSON、Provider 不可用等错误会写入独立分析库草稿并在详情页展示；成功保存后自动清空错误，避免失败草稿看起来像已完成分析。
- 优化 `/analyze` Provider 与手动回填体验：草稿记录在详情页和历史页显示为“待调用 / 待回填”，详情页提供复制完整 Prompt、重试 Provider 或粘贴 ChatGPT JSON 的入口；Provider 提交按钮仍会立即显示“调用中”并禁用。
- 改进 `/analyze` 工作台交互：步骤导航支持已到达步骤回退和回填区域锚点跳转，未到达步骤保持锁定；Prompt 页按已选证据数和长度给出分级风险提示，并限制同一 `news_id` 只输出一个 catalyst。
- 将结构化行情上下文改为醒目的“加入行情摘要”开关卡片：默认不请求行情数据、不消耗 Binance/market adapter 资源；用户手动开启后才请求所选交易对 K 线摘要，仍保留 BTC/ETH/SOL/BNB 到 USDT 交易对的自动匹配。
- 新增项目状态摘要 047：记录 v3 选择策略、Provider 错误持久化、行情开关 UX、当前验证结果、遗留问题和下一步 A/B 测试建议。

## 2026-06-06

- 将 `/analyze` 证据相关度升级为 v2 多因子评分：综合标的命中、利率/美元/流动性、地缘/能源风险、因果语言、数据/预期差、时间贴近和优先级，并对汇总、预告、整理、广告和同主题重复内容降权；候选证据上限从 25 条扩展到 40 条，但默认仍只勾选前 10 条以控制 Prompt 长度。
- 在证据预览、分析详情和 Prompt 中展示 v2 评分理由，帮助区分“本地相关度”与“模型置信度”；新增只读 `scripts/backtest_evidence_scoring.py` 回测脚本，用历史 LLM 单条证据置信度评估 v1/v2 top-k 排序效果。
- 优化 Provider 调用错误提示与 Gemini prompt 口径：Provider 错误改为中文可行动提示；Prompt 明确 `news_driven`、`macro_sentiment`、`technical_breakout`、`unclear` 判定标准，并要求证据充分时优先输出 4-8 条不同传导链 catalysts。
- 修复历史分析页右上角“对比”按钮裸跳空对比页的问题：顶部按钮现在与底部浮动栏一致，只有选满两条记录才可用，并携带选中 ids 进入 `/analyze/compare`。
- 新增项目状态摘要 046：记录 v2 评分模型、回测结果、Provider/Gemini 观察、当前未提交外部链路边界，以及下一步建议。

## 2026-06-05

- 修复 Dashboard Provider 调用体验和失败保护：`/analyze` 调用按钮提交后立即显示“调用中”并禁用，Gemini 返回 `MAX_TOKENS` 等非正常 `finishReason` 或不可解析 JSON 时保留草稿并显示错误，不再保存为伪“已完成”；Gemini 请求增加 JSON 输出约束，并补充 `GEMINI_THINKING_BUDGET` 示例配置。
- 优化 `/analyze` 证据与行情选择：证据预览默认只勾选前 10 条最高相关度候选，并显示已选条数、建议上限和“本地相关度不是模型置信度”的说明；Prompt 页显示已选证据数和 Prompt 长度提示；分析标的 BTC/ETH/SOL/BNB 会自动匹配对应 USDT 交易对，非加密标的会禁用 Binance 行情摘要，避免 ETH 问题误带 BTCUSDT 行情。
- 在分析详情、历史分析和对比分析页展示 `model_label`，便于区分手工 ChatGPT、Gemini、GLM、DeepSeek 等不同来源的分析结果。
- 修复 `/item/{id}` 交互 K 线图的时间对齐问题：秒级快讯窗口会扩展到完整 K 线边界，避免 `±15m`、`±60m` 或自定义窗口少算首尾蜡烛；快讯竖线改为锚定到快讯发生时刻所在的 K 线，随拖动和缩放同步移动；横轴刻度改为自适应 `HH:mm`，时间输入改用更宽的 `datetime-local` 控件。
- 修复 `/item/{id}` K 线图显示细节：快讯竖线在移出当前可视时间范围后隐藏，底部按成交量 0 轴动态截断且不穿过时间轴；成交量改为独立 pane 和独立右侧刻度，隐藏 TradingView attribution logo，并用自定义分割线避免遮挡右侧价格轴。
- 新增项目状态摘要 045：记录交互 K 线图体验收口、当前验证结果、未做事项，以及换新 session 后的下一步建议和 GPT-5.5 模型档位。

## 2026-06-04

- 将 `/item/{id}` 行情上下文面板升级为交互 K 线图：引入本地 vendored TradingView Lightweight Charts，自动加载当前详情窗口行情，展示蜡烛图、成交量、hover OHLCV、拖动缩放和快讯时间竖线；K 线明细表默认折叠，仍保持只读、无首页批量行情请求。
- 优化 `/item/{id}` 交互 K 线体验：将 `±5m/±15m/±30m/±60m` 窗口切换移到行情图上方并定位回行情面板；图表时间轴和 hover 提示统一显示北京时间，提示文案中文化，关闭默认横向价格虚线并保留随缩放移动的快讯时间竖线；摘要卡片改为快讯前收盘、快讯后涨跌、成交量合计等更有用指标。
- 修复 Dashboard 搜索关键字中的 SQLite `LIKE` 通配符误匹配：`%`、`_` 和反斜杠会按字面量搜索，避免快讯筛选、分页和最新时间判断失准。
- 增强 Binance market adapter 缓存并发保护：同一 symbol / interval / window 同时未命中缓存时只发起一次 public REST 请求，等待者复用缓存结果或收到明确降级错误。
- 实现 Dashboard LLM Provider Adapter 第一版：支持 Anthropic Messages API、Gemini API、OpenAI-compatible API（DeepSeek / GLM 等）和 OpenAI 备用 provider；`/analyze` Prompt 草稿可显式调用已配置 Provider 并保存到独立分析库，默认无 key 时不请求模型 API。
- 新增 Provider Adapter 与 review 后续计划 007：记录本轮采纳项、暂缓删除旧 Dashboard 的边界、Gemini / GLM / DeepSeek / Anthropic 试用顺序和后续 P0/P1/P2 排期。
- 新增项目状态摘要 044：记录 review 修复和 Provider Adapter 第一版收口、当前验证结果、明确未做事项，并给出下一 session 继续 Canvas mini 折线图的复制提示。

- 新增项目状态摘要 043：记录 `/system` 运维驾驶舱、`/telegram-status` unknown_timeout 核对、`/system/ws-initial` 下钻三个 P0 只读诊断闭环的完成状态、当前运行证据、后续 Provider Adapter 设计优先级和模型档位建议。

## 2026-06-03

- 新增 Dashboard `/system/ws-initial` 只读下钻：列出最近 `source='ws_initial'` 新入库快讯，标记是否晚于当前 `last_ingested_at` 游标，并展示 Telegram 最新状态和 `delivery_log` 确认状态；用于人工判断 WebSocket 重连快照是否覆盖短缺口，不推进游标、不补发 Telegram。
- 增强 Dashboard `/telegram-status` unknown_timeout 只读核对：状态明细新增 `delivery_log` 确认列，汇总区拆分 24h unknown_timeout、已确认和仍需人工核对数量，帮助判断“超时未知但可能已成功”的投递记录；页面不重试、不补发、不写去重表。
- 将 Dashboard `/system` 升级为运维驾驶舱：新增顶部总判断、人工动作建议、WebSocket / REST / WebSocket initial history / Telegram 四条链路卡、24h 入库来源与 Telegram 状态条形图；保留原始诊断表供开发排查，页面仍只读且不触发采集、REST 请求或 Telegram 发送。
- 增强 Dashboard `/system` 只读运行告警：24h Telegram 卡片新增 `unknown_timeout` 数量；当 REST 曾间歇恢复后再次退避时明确提示不要误判为整体采集中断；当 24h 内存在 `unknown_timeout` 时提示人工核对但不自动重发，成功去重仍以 `delivery_log` 为准。
- 新增项目状态摘要 042：记录 Binance 行情叠加三步完成、`CHANGELOG.md` 按日期分组规则、当前 WebSocket / REST / Telegram 运行状态，以及下一阶段 Provider、Vision、REST 补拉替代和告警增强的优先级编排。
- 在 `/analyze` 手工分析流中加入可选结构化行情上下文：用户勾选后使用分析时间窗口请求 market adapter，预览页展示 Binance 行情摘要，并在生成 Prompt 时独立写入“结构化行情上下文”区块；未勾选或行情失败时手工分析流程继续可用。

## 2026-06-02

- 让 `run_dashboard.py` 启动时加载 `.env`，并在 `.env.example` 增加 `MARKET_ADAPTER=binance` 等行情叠加示例配置；Dashboard 正式 8765 启动后可通过环境变量启用 Binance adapter，而默认仍不请求外部行情 API。
- 在 `/item/{id}` 增加用户触发的行情上下文面板：支持选择 Binance 白名单交易对、`1m/5m` 周期和快讯邻近窗口，点击后调用 `/api/market/klines` 展示价格摘要与 K 线表格；默认不自动请求，不影响首页刷新和实时采集链路。
- 实现 Dashboard Binance market adapter 的第一步：`MARKET_ADAPTER=binance` 时 `/api/market/klines` 可通过 Binance public REST 读取白名单加密交易对 K 线，并带有 symbol/interval 校验、请求超时、进程内 TTL 缓存和失败降级；默认未配置时仍不请求外部行情 API。

## 2026-06-01

- 新增 Binance 行情叠加最小实施计划 006：确认第一版只做可关闭、只读、用户触发的加密交易对 market overlay，优先放在 `/item/{id}`，后续再进入 `/analyze`，不首页批量请求、不写业务历史库、不影响 WebSocket / REST / Telegram。
- 修复启动链路在 REST/DNS 慢或 403 时拖慢实时主路的问题：WebSocket 现在启动后立即作为实时主路连接，REST 冷启动预加载与离线补拉改为后台执行；后台补拉使用启动瞬间的 `last_ingested_at` 快照，避免被新 WebSocket 消息推进游标后误判“没有离线窗口”。
- 降低 Dashboard 快讯流感知延迟：首页自动检查新消息间隔从 20 秒降到 3 秒，并在打开页面后立即检查一次；快讯流和详情页时间显示到秒，首页 Telegram 状态补充本地投递时间，便于与金十官网逐秒对比。
- 增强 Dashboard `/system` 只读告警：当 REST 退避但 WebSocket 主路仍新鲜时明确提示“不是整体采集中断”，当 WebSocket 初始历史新入库或最新时间晚于游标时提示人工核对短缺口；不推进游标、不补发 Telegram、不请求外部源。
- 新增项目状态摘要 041：记录 WebSocket initial history 诊断增强、REST 补拉替代设计评估、launchd reload 后 `last_ws_initial_*` 真实写入、REST 间歇恢复后再次进入 `forbidden_backoff`，以及下一步观察 / 只读告警 / 短缺口恢复策略建议。
- 新增 REST 长期 403 下的补拉替代设计评估：明确 Glanceway 金十示例、金十官方 API、WallstreetCN 7x24 与 CoinGlass newsflash 的用途、风险和隔离用法，推荐先强化 WebSocket initial history / reconnect 诊断，再考虑补拉 adapter 边界。
- 增强 WebSocket initial history 运行诊断：WebSocket 重连收到初始历史列表时写入 `last_ws_initial_*` 状态，记录快照时间、列表条数、新入库条数和覆盖时间范围，并在 Dashboard `/system` 只读展示；不改变 Telegram 去重、补拉或发送语义。

## 2026-05-31

- 中文化中期 Dashboard 设计与交接文档：将 `docs/design/003-phase2b-phase3-spec.md` 和 `docs/status/034` 至 `039` 中的大段英文正文统一改为中文，并补充本次文档更新时间；保留文件名、命令、路由、环境变量、commit hash、代码块和技术标识不变。
- 新增项目状态摘要 040：记录 `/system` 诊断面板和 REST 状态持久化收口、launchd reload 后的真实运行证据、当前 REST 仍反复 403 但 WebSocket 与 Telegram realtime 正常，以及下一步文档中文化建议。
- 持久化 REST 运行状态：REST 轮询成功、连续 403 退避或其它异常时写入 `runtime_state`，`/system` 可直接显示 `ok`、`forbidden_backoff`、`error`、连续 403 轮数、退避截止时间、最近错误和最近恢复时间；仅增强诊断，不改变 REST 请求、补拉或 Telegram 发送语义。
- 增强 Dashboard `/system` 只读运行诊断面板：展示最近 WebSocket、REST、自动补拉、手动补拉入库时间和 24h 数量，补充 `last_ingested_id`、缺口摘要时间、Telegram 最新 sent/unknown_timeout/failed 与补拉摘要状态；页面明确不触发补拉、REST 请求、Telegram 重试或发送。
- 修复实时采集韧性：WebSocket 主连接增加空闲超时主动重连，避免半开连接长时间不入库；REST 轮询在金十接口连续 403 时改为退避和汇总告警，减少日志刷屏与 dashboard “超时/补拉”噪声，并补充无网络单测保护。
- 新增 Dashboard V2 第二轮能力：分析历史支持勾选两条记录进入 `/analyze/compare` 双栏对比，分析详情和历史页新增“重新分析”入口；新增 `dashboard/providers/` Provider Adapter 骨架、`dashboard/market/` 行情 adapter 边界和 `/api/market/klines` 占位端点；系统页展示 Provider 配置状态，并补齐 `.pill.normal`、`row-normal`、`row-none` 样式。

## 2026-05-29

- 新增项目状态摘要 038：记录 Dashboard v1/v2 补丁包评估、`304929a` V2 bugfix 基线、003 与 004 计划差异、下一步分析对比 / 行情 adapter / Provider Adapter 的推荐编排。
- 修复 Dashboard 快讯流与分析页细节：不再展示 `style_flags` 内部调试字段，隐藏空内容快讯，避免正文重复显示，时间列统一到分钟，补拉消息显示“补拉”标签，Telegram 状态和 AI 方向标签中文化为催化语义；同时加固截图上传（读入前 `Content-Length` 预检、限定 png/jpeg/webp/gif、500 错误脱敏），并将同秒消息排序 tie-breaker 改为金十消息 `id`。
- 新增 Dashboard V2 开发计划定稿 004：对照 v1/v2 两版补丁包和当前 repo，确认 v2 为修复基线、保留 v1 路线图价值但不接入 HTML 页面，冻结后续分析对比、可选行情叠加、Phase 2B Provider Adapter 和 Vision 识别边界。

## 2026-05-25

- 完成 Dashboard Phase 3A/3B/3C 增强：Telegram 消息支持通过可选 `DASHBOARD_URL` 追加本地 `/item/{id}` 详情链接，未配置时 Telegram 文本保持原样；快讯流首屏默认 50 条并支持滚动分页加载；分析页支持本地截图上传、预览、手工截图描述和分析记录截图关联；置信度展示增加“主观估计、非交易信号”的悬停说明。
- 新增项目状态摘要 037：记录 `phase 2a function 2&4&5.zip` 评估结论、仅采用图片死链兜底的原因、003 Phase 2B / Phase 3 规格落地情况和下一步 Phase 3A Telegram 深链计划。
- 新增 Dashboard Phase 2B / Phase 3 规格文档：明确 Telegram `/item/{id}` 深链、快讯流无限加载、截图上传、置信度说明、LLM provider adapter、Vision 识别和行情叠加的实现边界与推荐顺序。

## 2026-05-24

- 增强独立 Dashboard 体验：分析页改用原生日期时间选择器并提供 5/15/30 分钟、1 小时、4 小时快捷窗口，快讯流和详情页按金十消息样式渲染重要、标题、加粗、图片和来源链接，分析详情页催化因素与证据列表改为优先显示时间和标题并弱化内部 news_id。
- 修复独立 Dashboard 模板细节：`/item/{id}` 时间显示统一到分钟，分析相关导航高亮避免 `/analyze/history` 与分析页双高亮，并将分析记录状态展示为中文草稿/已完成。
- 修复独立 Dashboard Phase 2A 细节：禁用默认 `/docs`、`/redoc` 与 `/openapi.json`，补齐分析历史和聚合报告导航，证据边界改为结构化字段，快讯流自动刷新改为保留当前筛选条件的最新时间戳智能轮询，并新增只读聚合报告基础页。
- 新增独立 Dashboard Phase 2A 手工 AI 分析流：支持从本地只读 SQLite 构建 evidence packet、生成 ChatGPT Business/Custom GPT 复制用 Prompt、回填并解析答案、保存到独立 `data/dashboard_analysis.sqlite3`，并提供分析详情与历史记录页面；快讯流增加安全自动刷新，关键词热力改用真实监控关键词；不接模型 API、不请求金十 REST、不写业务历史库。

## 2026-05-23

- 扩展独立 Dashboard Phase 1 页面：新增共享导航模板、Telegram 投递状态页、系统健康页和分析占位页，并增强首页关键词、时间范围和“仅已推 Telegram”筛选；已确认发送语义改用 `delivery_log`。
- 新增独立 Dashboard 单条详情页雏形：支持从首页点击快讯进入 `/item/{id}`，只读展示中心消息、Telegram 状态和前后时间窗口上下文。
- 增强独立 Dashboard 首页快讯筛选：支持通过 URL query 选择优先级、返回条数和只看有 Telegram 状态的消息，并对参数做白名单和范围保护。
- 新增独立 Dashboard 首页快讯流雏形：`run_dashboard.py` 首页读取只读 SQLite 最近快讯，展示时间、优先级、内容摘要、来源和 Telegram 状态，继续保持不写业务库、不触发金十 REST、不发送 Telegram。
- 新增独立 Dashboard 只读 SQLite 查询层：封装 `HISTORY_DB` 路径解析、`mode=ro` + `query_only` 连接、schema 健康检查和最近快讯查询，并用临时 SQLite 测试保护缺库不创建、只读连接拒绝写入和 Telegram 状态联查。

## 2026-05-22

- 新增独立 Dashboard 骨架入口：`run_dashboard.py` 启动 FastAPI/Jinja2 服务，默认监听 `127.0.0.1:8765`，先提供最小健康页和 `/healthz`，不写业务库、不触发金十 REST、不发送 Telegram。
- 新增 Dashboard + AI 分析最终规格：冻结正式 FastAPI/Jinja2 独立 dashboard 方向，明确旧 `--dashboard` 原型保留但不继续扩展，AI 分析先采用 evidence packet + ChatGPT Business/Custom GPT 手工复制粘贴 + 回填保存。
- 新增项目状态摘要 033：记录 Dashboard 原型已提交已推送、无需 revert，后续切到独立 dashboard 架构，且 Anthropic/Claude API 不作为 P0/P1 前置依赖。
- 新增本地只读 Dashboard MVP：支持 `--dashboard` 打开最近快讯、单条上下文、Telegram 投递状态和聚合报告占位页面，默认仅监听 `127.0.0.1` 且不触发 REST、WebSocket、补拉或 Telegram 发送。

## 2026-05-21

- 新增 Dashboard MVP 设计文档：明确本地只读页面结构、SQLite 数据来源、localhost 启动方式、安全边界、与 Telegram inline / callback 的后续关系，以及实现前的风险控制。
- 新增项目状态摘要 031：记录只读上下文查询已完成、事件聚合 V2 暂列技术债、Telegram inline 暂缓，以及下一阶段 dashboard MVP 设计方向和模型建议。

## 2026-05-20

- 新增只读上下文查询入口：`--context <消息ID>` 支持查看某条快讯前后指定分钟数的本地历史，便于在 Telegram 消息后快速复盘背景且不触发 REST、Telegram 或补拉。
- 新增项目状态摘要 030：记录事件聚合防刷屏 V2 最小版的默认关闭状态、开启方式、观察点、风险和后续模型建议。
- 新增事件聚合防刷屏 V2 最小版：默认关闭，开启后相似实时快讯在窗口内只推第一条，后续消息继续入库并写入 Telegram skipped 诊断状态；T3 金十重要消息默认绕过聚合直推。
- 新增项目状态摘要 029：完成 `main()` 启动编排测试方案评估，明确直接强测 `main()` 成本偏高，若后续覆盖应优先抽小型启动 helper 并使用更高推理强度。
- 新增项目状态摘要 028：完成测试阶段复盘，确认 `poll_loop` 不再继续扩张低价值测试，下一阶段优先评估 `main()` / `ws_loop` 顶层 async 编排是否值得覆盖。
- 新增项目状态摘要 027：记录 `poll_loop` 主循环无网络编排测试收口、当前验证结果、风险判断和下一阶段建议。
- 增强 REST 轮询主循环新消息处理测试：覆盖 `poll_once` 返回新快讯时，`poll_loop` 会以 `source="rest"` 调用 `handle_item` 并写入内存去重集合。
- 增强 REST 轮询主循环异常保护测试：覆盖 `poll_loop` 中 gap 自愈补拉抛异常后记录 warning 并继续进入本轮 `poll_once`，避免补拉异常阻断实时轮询兜底。
- 新增项目状态摘要 026：记录 REST 轮询主循环 gap 触发自动补拉测试覆盖、验证结果、风险判断和下一阶段建议。
- 增强 REST 轮询主循环自愈补拉编排测试：覆盖 `poll_loop` 在停顿达到 `AUTO_CATCHUP_GAP_SECONDS` 时以 `trigger="gap"` 调用自动补拉，以及关闭自动补拉或停顿未达阈值时不调用补拉，继续保持无真实 REST、无真实 Telegram 验证。

## 2026-05-19

- 新增项目状态摘要 025：记录实时处理链路测试覆盖、验证结果、风险判断、后续模型建议和 poll_loop gap 测试新 session 交接提示词。
- 增强实时处理链路测试：覆盖 `handle_item` 命中关键词发送成功写入实时去重、发送失败只写诊断状态，以及未命中关键词只入库不发送，继续保持无真实 Telegram 和临时 SQLite 验证。

## 2026-05-18

- 新增项目状态摘要 024：记录手动补拉包装层测试覆盖、验证结果、风险判断、后续模型建议和新 session 交接提示词。
- 增强手动补拉包装层测试：覆盖手动窗口参数传递、窗口失败早退、关闭 Telegram、保护规则跳过、发送成功写入去重记录、发送失败只写诊断状态，以及多条候选逐条发送与 `send_interval=0` 不等待语义，继续保持无真实 Telegram、无真实 REST 和临时 SQLite 验证。
- 新增项目状态摘要 023：对照本 session 最早目标，记录参数线收口、自动补拉测试覆盖、剩余风险、模型建议和新 session 交接提示词。
- 增强自动补拉与实时去重交接测试：覆盖自动补拉成功后将 `seen_item_ids` 预热到内存去重集合，避免补拉刚处理过的消息又被实时链路当成新消息。
- 增强自动补拉早退分支测试：覆盖缺少 `last_ingested_at`、游标格式错误和回退缓冲后没有离线窗口时不进入补拉扫描。
- 增强自动补拉最大回看窗口测试：覆盖离线窗口超过 `CATCHUP_MAX_HOURS` 时截断到允许范围，并确认自动补拉不逐条发送历史消息。
- 增强自动补拉未来游标回归测试：覆盖 `last_ingested_at` 跑到未来时从历史库最新有效游标回退，以及无可恢复历史游标时安全跳过。

## 2026-05-17

- 增强补拉窗口 mock REST 边界测试：覆盖 app_id fallback、空页停止、跨页重复 ID 去重和未命中关键词只入库不补发，继续保持无网络和无真实 Telegram 验证。
- 新增项目状态摘要 022：记录手动补拉 CLI 参数范围保护、验证结果、风险判断、后续 pytest 边界和其它 CLI limit 参数评估方向，便于换 session 续接。
- 增强手动补拉 CLI 参数范围保护：`--catch-up-max-store`、`--catch-up-max-send`、`--catch-up-send-interval` 与 `.env` 配置使用同一范围，并在 README 和 CLI help 中标明边界。
- 新增项目状态摘要 021：记录数值配置范围保护、README / `.env.example` 文档同步、验证结果、风险判断和后续 CLI 参数 clamp 评估方向，便于换 session 续接。
- 补齐剩余数值配置范围保护与文档：`CATCHUP_MAX_HOURS`、`AUTO_CATCHUP_GAP_SECONDS`、`SHOW_DELAY_IF_SECONDS` 增加上下限保护，并在 README 与 `.env.example` 标明配置范围。
- 增强补拉 Telegram 补发间隔配置保护：`CATCHUP_SEND_INTERVAL` 限制在 0 到 10 秒之间，保留 0 作为不等待的语义，同时避免误填负数或极大值导致补发节奏异常。
- 增强补拉 Telegram 补发上限配置保护：`CATCHUP_MAX_SEND` 限制在 0 到 300 条之间，保留 0 作为关闭逐条补发的语义，同时避免误填极大值导致补发刷屏。
- 增强补拉入库上限配置保护：`CATCHUP_MAX_STORE` 限制在 20 到 5000 条之间，避免误填 0、负数或极大值导致补拉窗口语义不清或扫描写入压力过大。
- 增强 REST 轮询间隔配置保护：`POLL_INTERVAL` 限制在 1 到 60 秒之间，避免误填负数或极大值导致日志误导、请求过密或轮询兜底明显变慢。
- 增强 WebSocket 重连配置保护：`WS_RECONNECT_DELAY` 低于 1 秒时自动使用 1 秒下限并记录 warning，避免负数配置导致重连 sleep 异常退出。
- 新增数值配置上下限保护评估清单：梳理轮询、WebSocket 重连、补拉窗口、补发间隔、gap 自愈和延迟提示等配置的建议范围与误填风险，暂不实装批量 clamp。
- 扩展回溯查询 mock REST 边界测试：覆盖 app_id 失败 fallback、空页停止、重复 ID 去重和未命中关键词只保留在全部结果中，继续保持无网络验证。
- 新增项目状态摘要 019：记录 Telegram 发送结果测试、回溯查询 cursor 修复与 mock REST 测试、自动补拉 gap 摘要冷却测试、验证结果和后续优先级，便于换 session 续接。
- 增强自愈补拉摘要冷却回归测试：用临时历史库和 fake Telegram 覆盖 gap 摘要冷却中不发送、冷却后发送并写入投递状态，避免真实 REST 和真实 Telegram。
- 修复回溯查询翻页 cursor 边界：`crawl_window` 复用补拉窗口的上一页 cursor 计算，避免重复时间戳导致下一页重复扫描；新增无网络 mock REST 测试覆盖窗口过滤、关键词评分、高优先级分类和跨页 cursor。
- 扩展 Telegram 发送结果 fake session 测试：覆盖 200 成功、500 失败和 timeout 送达未知分支，继续保持不联网、不触碰真实 Telegram。
- 增强 Telegram 发送结果轻量回归测试：覆盖未配置凭据、临时测试库保护跳过和 `TelegramSendResult.ok` 判定，确保无真实网络和无真实 Telegram 即可保护发送结果边界。
- 新增项目状态摘要 018：记录开发效用重新评估、计划与实际偏离判断、后续优先级和 CHANGELOG 日期分组规则，便于后续按效用续接。
- 整理 CHANGELOG：按真实提交日期拆分近期变更，避免多日改动继续堆在 `Unreleased`。
- 新增项目状态摘要 017：记录补拉窗口无网络测试、补拉摘要纯逻辑测试、验证结果、模型建议和下一步 Telegram/crawl_window/gap 冷却测试方向，便于换 session 续接。
- 增强补拉摘要回归测试：覆盖重点摘要条目排序、摘要投递状态 ID、摘要投递详情和自愈补拉摘要消息 escape / 截断提示等纯逻辑。
- 增强补拉窗口回归测试：mock REST 页面覆盖窗口过滤、已入库统计、已投递跳过、`max_store` 截断和跨页 cursor 推进，避免依赖外部网络即可验证补拉边界语义。
- 新增项目状态摘要 016：记录最小 pytest 骨架、SQLite 边界测试、验证结果、模型建议和下一步 catch_up_window 无网络测试计划，便于换 session 续接。

## 2026-05-16

- 增强 SQLite 边界回归测试：用临时历史库覆盖历史入库 upsert、游标自提交、未来时间保护、Telegram 投递去重和投递状态诊断不污染去重表等关键语义。
- 新增最小 pytest 骨架：加入开发依赖入口，并覆盖时间解析、优先级分类、补拉翻页游标、消息文本提取和 Telegram 格式化等纯函数边界逻辑。
- 修复历史入库 upsert 语义：重复消息再次入库时保留首次来源和入库时间，优先级只升级不降级，并让游标更新函数自行提交状态，降低后续调用踩隐式事务依赖的风险。
- 降低自愈补拉摘要打扰：常驻进程触发的 gap 自愈摘要增加 30 分钟发送冷却，避免网络或系统短暂停顿时多条摘要频繁夹在实时快讯中；启动离线补拉摘要不受影响。
- 新增项目状态摘要 015：记录自愈补拉摘要降噪、历史入库 upsert 语义修复、验证结果、后台服务 reload 状态和下一步 pytest 骨架建议，便于换 session 续接。

## 2026-05-12

- 增强自动补拉摘要诊断：摘要 Telegram 发送成功、失败、超时未知或保护跳过时会写入投递状态查询视图，但不会写入逐条消息去重表，避免影响手动补拉补发判断。
- 新增项目状态摘要 014：记录自动补拉摘要投递状态修复、验证结果、文档判断和下一步可靠性修复建议，便于换 session 续接。
- 新增 Telegram 投递状态只读查询入口：支持查看最近失败、超时未知、保护规则跳过或全部投递记录，便于诊断 Telegram 发送状态且不会触发补发。

## 2026-05-11

- 增强 `.env` 数值配置容错：轮询间隔、补拉上限、延迟阈值等字段写错时不再导致进程启动失败，系统会记录警告并使用默认值继续运行。
- 增强 Telegram 投递状态诊断：新增独立状态记录，区分已发送、发送失败、超时未知和保护规则跳过；已成功发送记录仍保持原语义，避免补拉重复发送已成功推送过的消息。
- 修复补拉翻页游标推进：下一页从本页最旧消息时间再往前 1 秒开始，避免重复时间戳导致补拉反复请求同一秒、浪费页数并影响窗口覆盖。
- 提升补拉可靠性：手动补拉和自动补拉改为后台线程执行，SQLite 改为线程本地连接并开启 WAL 与 5 秒锁等待，降低补拉阻塞实时监控和并发写入锁冲突的风险。
- 修复补拉游标安全：`last_ingested_at` 改用解析后的时间比较，跳过未来时间消息推进游标，并让自动补拉起点回退 120 秒，降低乱序和异常时间导致漏补拉的风险。

## 2026-05-10

- 增强补拉可观测性：补拉跨多页时会输出 `catch-up page=...` 进度日志，便于观察扫描页数、命中窗口条数、累计入库候选和已存在条数。
- 新增延迟提示配置：`SHOW_DELAY_IF_SECONDS` 支持在消息发生时间落后当前时间超过阈值时，在 Telegram 和终端显示 `延迟：Xs`，默认 60 秒，便于快速识别推送是否变慢。
- 增强 `launchd` 管理脚本健壮性：`install` 和 `reload` 现在会自动执行 `launchctl enable`，并在 `bootstrap` 失败时提示下一步排查命令，减少 `Bootstrap failed: 5` 后需要手工恢复的情况。
- 补充 `launchd` 运维文档：手动安装流程加入 `launchctl enable`，并说明 `reload` 的实际重载步骤与 disabled 状态排查方法。
- 新增项目状态摘要 005：记录额度友好的迁移方式、当前运行状态判断和下一步优先任务，便于切换新 session 后低成本续接。
- 新增长时间停顿自愈补拉：常驻进程从睡眠或长时间断网恢复后，会自动补齐停顿窗口并发送一条摘要。
- 增强补拉摘要：自动补拉摘要列出最多 10 条 T3/T2 重点标题，便于快速判断是否需要手动补发。
- 统一快讯时间显示：Telegram、终端和补拉解析统一使用完整发生时间，避免 WebSocket 与 REST 消息显示格式不一致。

## 2026-05-09

- 新增项目状态摘要 003：记录当前稳定性、关键词配置、后台运行状态和后续交接信息。
- 新增关键词外部配置：支持通过 `KEYWORDS_FILE` 和 `HIGH_PRIORITY_FILE` 加载一行一个关键词的本地配置文件，并提供示例模板。
- 增强 Telegram 推送可靠性：记录可诊断的异常类型与错误内容，对明确临时的网络/5xx 失败做有限重试，并补充 WebSocket 登录包与历史元数据回填的防御性修正。
- 补充 README 日常运维速查：集中列出后台状态、日志、重载、停止、安装和卸载命令。

## 2026-05-07

- 修复数据类消息空推送：为财报/指标类 WebSocket 消息生成可读标题和数值正文，并跳过无法显示内容的未知消息。
- 新增 `scripts/launchd/manage.sh`：封装检查、安装、重载、状态、日志、停止和卸载命令，降低手动操作难度。
- 调整 `launchd` 日志说明：stdout/stderr 合并到 `logs/jin10-monitor.log`，首次安装只执行 `bootstrap`。
- 新增 macOS `launchd` 运维模板：提供后台常驻启动脚本、plist 模板、日志目录和迁移/排查文档。
- 补充 README 与 `.env.example`：记录离线补拉配置、手动补拉命令、SQLite 游标检查和临时库 Telegram 保护。
- 新增临时测试库保护：`HISTORY_DB=/tmp/...` 默认跳过真实 Telegram 发送，并在终端记录跳过原因。
- 新增补拉去重与发送记录：同一金十消息 ID 不重复入库，已推送过的 Telegram 消息不重复补发。
- 新增手动补拉命令：支持指定时间窗口补拉、限制入库数量、限制 Telegram 补发数量和发送间隔。
- 新增离线补拉：启动时自动补齐上次入库到本次启动之间的消息，只入库并发送一条 Telegram 摘要。

## 2026-05-04

- 分离 Telegram/终端推送优先级：`T3_IMPORTANT`、`T2_HIGH`、`T1_NORMAL`、`T0_NONE`。
- 补齐历史库消息元数据：标题、图片、新闻来源、来源链接和优先级字段。
- 统一终端、Telegram、历史查询和回溯查询的优先级与来源展示。
