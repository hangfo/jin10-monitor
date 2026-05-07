#!/bin/zsh
# Launch wrapper for jin10_monitor.py.
# Keep this file small and explicit so the service can be migrated by changing PROJECT_DIR only.

set -eu

PROJECT_DIR="/Users/rich/jin10-monitor"
PYTHON_BIN="$PROJECT_DIR/.venv/bin/python"
APP_FILE="$PROJECT_DIR/jin10_monitor.py"
ENV_FILE="$PROJECT_DIR/.env"

cd "$PROJECT_DIR"
mkdir -p "$PROJECT_DIR/logs"

if [[ -f "$ENV_FILE" ]]; then
  # Export .env values for launchd, which does not inherit your interactive shell environment.
  set -a
  source "$ENV_FILE"
  set +a
fi

exec "$PYTHON_BIN" "$APP_FILE"
