# 运维说明 001：macOS launchd 进程守护

更新时间：2026-05-07

## 1. 目标

让 `jin10_monitor.py` 在 macOS 本地后台常驻运行，并在异常退出后自动重启。

本方案只提供文件和命令，不自动安装系统服务。这样便于审查、回滚和迁移。

## 2. 文件说明

- `scripts/run_monitor.sh`
  - 进入项目目录。
  - 加载 `.env`，因为 launchd 不会继承终端里的环境变量。
  - 使用项目虚拟环境 `.venv/bin/python` 启动 `jin10_monitor.py`。
  - 迁移到其他机器时，主要改这个文件里的 `PROJECT_DIR`。

- `scripts/launchd/com.rich.jin10-monitor.plist`
  - macOS launchd 服务模板。
  - `RunAtLoad=true`：加载后立即启动。
  - `KeepAlive=true`：进程退出后自动重启。
  - stdout 写入 `logs/jin10-monitor.out.log`。
  - stderr 写入 `logs/jin10-monitor.err.log`。

- `logs/.gitkeep`
  - 只用于保留日志目录。
  - 真实 `.log` 文件不提交到 Git。

## 3. 安装前检查

确认项目能手动运行：

```bash
cd /Users/rich/jin10-monitor
source .venv/bin/activate
python jin10_monitor.py --once --limit 3
```

确认 `.env` 已配置真实 Telegram 参数：

```bash
test -f .env
```

确认启动脚本可执行：

```bash
chmod +x scripts/run_monitor.sh
```

## 4. 安装到 launchd

复制 plist 到用户级 LaunchAgents：

```bash
mkdir -p ~/Library/LaunchAgents
cp scripts/launchd/com.rich.jin10-monitor.plist ~/Library/LaunchAgents/
```

加载服务：

```bash
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.rich.jin10-monitor.plist
launchctl kickstart -k gui/$(id -u)/com.rich.jin10-monitor
```

查看状态：

```bash
launchctl print gui/$(id -u)/com.rich.jin10-monitor
```

## 5. 查看日志

实时查看普通日志：

```bash
tail -f /Users/rich/jin10-monitor/logs/jin10-monitor.out.log
```

实时查看错误日志：

```bash
tail -f /Users/rich/jin10-monitor/logs/jin10-monitor.err.log
```

如果服务没有启动，优先看错误日志。

## 6. 停止和卸载

停止并卸载 launchd 服务：

```bash
launchctl bootout gui/$(id -u) ~/Library/LaunchAgents/com.rich.jin10-monitor.plist
```

删除 LaunchAgents 中的副本：

```bash
rm ~/Library/LaunchAgents/com.rich.jin10-monitor.plist
```

这不会删除项目代码、SQLite 历史库或 `.env`。

## 7. 更新代码后的重启

拉取或修改代码后，重启服务：

```bash
launchctl kickstart -k gui/$(id -u)/com.rich.jin10-monitor
```

重启后检查：

```bash
tail -n 80 /Users/rich/jin10-monitor/logs/jin10-monitor.out.log
sqlite3 /Users/rich/jin10-monitor/data/jin10_history.sqlite3 "select key, value, updated_at from runtime_state order by key;"
```

## 8. 迁移到其他路径或机器

如果项目路径不是 `/Users/rich/jin10-monitor`，需要同步改三处：

1. `scripts/run_monitor.sh` 里的 `PROJECT_DIR`。
2. `scripts/launchd/com.rich.jin10-monitor.plist` 里的 `ProgramArguments`。
3. `scripts/launchd/com.rich.jin10-monitor.plist` 里的日志路径和 `WorkingDirectory`。

改完后重新复制 plist 到 `~/Library/LaunchAgents/`。

## 9. 排查顺序

1. 先手动运行 `python jin10_monitor.py --once --limit 3`。
2. 再看 `logs/jin10-monitor.err.log`。
3. 再看 `launchctl print gui/$(id -u)/com.rich.jin10-monitor`。
4. 最后检查 `.env`、`.venv`、路径是否迁移后未更新。
