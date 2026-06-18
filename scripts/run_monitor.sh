#!/bin/zsh
# Launch wrapper for jin10_monitor.py.
# Keep this file small and explicit so launchd never parses .env with shell syntax.

set -eu

PROJECT_DIR="/Users/rich/jin10-monitor"
PYTHON_BIN="$PROJECT_DIR/.venv/bin/python"
LAUNCH_FILE="$PROJECT_DIR/scripts/run_monitor.py"

cd "$PROJECT_DIR"
mkdir -p "$PROJECT_DIR/logs"

exec "$PYTHON_BIN" "$LAUNCH_FILE"
