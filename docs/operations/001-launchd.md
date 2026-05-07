# 运维说明 001：macOS launchd 进程守护

更新时间：2026-05-07

## 1. 目标

让 `jin10_monitor.py` 在 macOS 本地后台常驻运行，并在异常退出后自动重启。

本方案只提供文件和命令，不自动安装系统服务。这样便于审查、回滚和迁移。

## 0. 最简操作

以后优先使用管理脚本，不需要手记复杂 `launchctl` 命令。

先进入项目：

```bash
cd /Users/rich/jin10-monitor
```

检查配置是否可用：

```bash
./scripts/launchd/manage.sh check
```

首次安装并启动：

```bash
./scripts/launchd/manage.sh install
```

更新代码或修改 plist 后重载：

```bash
./scripts/launchd/manage.sh reload
```

查看状态：

```bash
./scripts/launchd/manage.sh status
```

查看日志：

```bash
./scripts/launchd/manage.sh logs
```

停止服务：

```bash
./scripts/launchd/manage.sh stop
```

彻底卸载服务：

```bash
./scripts/launchd/manage.sh uninstall
```

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
  - stdout 和 stderr 都写入 `logs/jin10-monitor.log`，避免查看错文件。

- `scripts/launchd/manage.sh`
  - 管理脚本，封装安装、重载、停止、查看日志等命令。
  - 迁移路径后，主要改这个文件和 plist 里的项目路径。

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
chmod +x scripts/launchd/manage.sh
```

## 4. 安装到 launchd

推荐使用：

```bash
./scripts/launchd/manage.sh install
```

下面是手动命令，只有排查时才需要逐条执行。

复制 plist 到用户级 LaunchAgents：

```bash
mkdir -p ~/Library/LaunchAgents
cp scripts/launchd/com.rich.jin10-monitor.plist ~/Library/LaunchAgents/
```

加载服务：

```bash
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.rich.jin10-monitor.plist
```

首次安装时只执行 `bootstrap`。因为 plist 里已经设置了 `RunAtLoad=true`，`bootstrap` 会自动启动服务。`kickstart -k` 只用于后续重启，首次安装时不要紧跟着执行，避免刚启动又被重启一次。

查看状态：

```bash
./scripts/launchd/manage.sh status
```

## 5. 查看日志

实时查看日志：

```bash
./scripts/launchd/manage.sh logs
```

如果服务没有启动，优先看这个日志文件。

## 6. 停止和卸载

停止并卸载 launchd 服务：

```bash
./scripts/launchd/manage.sh stop
```

删除 LaunchAgents 中的副本：

```bash
./scripts/launchd/manage.sh uninstall
```

这不会删除项目代码、SQLite 历史库或 `.env`。

## 7. 更新代码后的重启

拉取或修改代码后，重启服务：

```bash
./scripts/launchd/manage.sh reload
```

重启后检查：

```bash
tail -n 80 logs/jin10-monitor.log
sqlite3 /Users/rich/jin10-monitor/data/jin10_history.sqlite3 "select key, value, updated_at from runtime_state order by key;"
```

## 8. 迁移到其他路径或机器

如果项目路径不是 `/Users/rich/jin10-monitor`，需要同步改三处：

1. `scripts/run_monitor.sh` 里的 `PROJECT_DIR`。
2. `scripts/launchd/manage.sh` 里的 `PROJECT_DIR`。
3. `scripts/launchd/com.rich.jin10-monitor.plist` 里的 `ProgramArguments`。
4. `scripts/launchd/com.rich.jin10-monitor.plist` 里的日志路径和 `WorkingDirectory`。

改完后重新复制 plist 到 `~/Library/LaunchAgents/`。

## 9. 排查顺序

1. 先手动运行 `python jin10_monitor.py --once --limit 3`。
2. 再看 `logs/jin10-monitor.log`。
3. 再看 `launchctl print gui/$(id -u)/com.rich.jin10-monitor`。
4. 最后检查 `.env`、`.venv`、路径是否迁移后未更新。
