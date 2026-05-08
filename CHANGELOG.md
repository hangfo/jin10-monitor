# Changelog

## Unreleased

- 分离 Telegram/终端推送优先级：`T3_IMPORTANT`、`T2_HIGH`、`T1_NORMAL`、`T0_NONE`。
- 补齐历史库消息元数据：标题、图片、新闻来源、来源链接和优先级字段。
- 统一终端、Telegram、历史查询和回溯查询的优先级与来源展示。
- 新增离线补拉：启动时自动补齐上次入库到本次启动之间的消息，只入库并发送一条 Telegram 摘要。
- 新增手动补拉命令：支持指定时间窗口补拉、限制入库数量、限制 Telegram 补发数量和发送间隔。
- 新增补拉去重与发送记录：同一金十消息 ID 不重复入库，已推送过的 Telegram 消息不重复补发。
- 新增临时测试库保护：`HISTORY_DB=/tmp/...` 默认跳过真实 Telegram 发送，并在终端记录跳过原因。
- 补充 README 与 `.env.example`：记录离线补拉配置、手动补拉命令、SQLite 游标检查和临时库 Telegram 保护。
- 新增 macOS `launchd` 运维模板：提供后台常驻启动脚本、plist 模板、日志目录和迁移/排查文档。
- 调整 `launchd` 日志说明：stdout/stderr 合并到 `logs/jin10-monitor.log`，首次安装只执行 `bootstrap`。
- 新增 `scripts/launchd/manage.sh`：封装检查、安装、重载、状态、日志、停止和卸载命令，降低手动操作难度。
- 修复数据类消息空推送：为财报/指标类 WebSocket 消息生成可读标题和数值正文，并跳过无法显示内容的未知消息。
- 补充 README 日常运维速查：集中列出后台状态、日志、重载、停止、安装和卸载命令。
- 增强 Telegram 推送可靠性：记录可诊断的异常类型与错误内容，对明确临时的网络/5xx 失败做有限重试，并补充 WebSocket 登录包与历史元数据回填的防御性修正。
- 新增关键词外部配置：支持通过 `KEYWORDS_FILE` 和 `HIGH_PRIORITY_FILE` 加载一行一个关键词的本地配置文件，并提供示例模板。
