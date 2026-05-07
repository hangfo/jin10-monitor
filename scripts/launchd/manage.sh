#!/bin/zsh
# Small helper for the macOS launchd service.
# It keeps the exact launchctl commands in one place so installs and reloads are easy to repeat.

set -eu

PROJECT_DIR="/Users/rich/jin10-monitor"
LABEL="com.rich.jin10-monitor"
DOMAIN="gui/$(id -u)"
SOURCE_PLIST="$PROJECT_DIR/scripts/launchd/$LABEL.plist"
TARGET_PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
LOG_FILE="$PROJECT_DIR/logs/jin10-monitor.log"

usage() {
  cat <<EOF
Usage: $0 <command>

Commands:
  check      Validate plist and scripts without changing the service
  install    Copy plist and start service for the first time
  reload     Replace plist and restart service
  status     Show launchd service status
  logs       Follow the unified service log
  stop       Stop service but keep plist installed
  uninstall  Stop service and remove plist from LaunchAgents

EOF
}

is_loaded() {
  launchctl print "$DOMAIN/$LABEL" >/dev/null 2>&1
}

check() {
  echo "1/3 Checking run wrapper syntax ..."
  zsh -n "$PROJECT_DIR/scripts/run_monitor.sh"
  echo "2/3 Checking launchd plist ..."
  plutil -lint "$SOURCE_PLIST"
  echo "3/3 Checking required local files ..."
  test -f "$PROJECT_DIR/.env"
  test -x "$PROJECT_DIR/.venv/bin/python"
  echo "OK: launchd files look ready."
}

install() {
  check
  if is_loaded; then
    echo "Service is already loaded. Use reload instead:"
    echo "  $0 reload"
    exit 1
  fi
  mkdir -p "$HOME/Library/LaunchAgents" "$PROJECT_DIR/logs"
  cp "$SOURCE_PLIST" "$TARGET_PLIST"
  launchctl bootstrap "$DOMAIN" "$TARGET_PLIST"
  echo "OK: service installed and started."
  echo "Next: $0 logs"
}

reload() {
  check
  mkdir -p "$HOME/Library/LaunchAgents" "$PROJECT_DIR/logs"
  if is_loaded; then
    launchctl bootout "$DOMAIN" "$TARGET_PLIST"
  fi
  cp "$SOURCE_PLIST" "$TARGET_PLIST"
  launchctl bootstrap "$DOMAIN" "$TARGET_PLIST"
  echo "OK: service reloaded with latest plist."
  echo "Next: $0 logs"
}

status() {
  launchctl print "$DOMAIN/$LABEL"
}

logs() {
  mkdir -p "$PROJECT_DIR/logs"
  touch "$LOG_FILE"
  tail -f "$LOG_FILE"
}

stop_service() {
  if is_loaded; then
    launchctl bootout "$DOMAIN" "$TARGET_PLIST"
    echo "OK: service stopped."
  else
    echo "Service is not loaded."
  fi
}

uninstall() {
  stop_service
  rm -f "$TARGET_PLIST"
  echo "OK: plist removed from LaunchAgents."
}

command="${1:-}"
case "$command" in
  check) check ;;
  install) install ;;
  reload) reload ;;
  status) status ;;
  logs) logs ;;
  stop) stop_service ;;
  uninstall) uninstall ;;
  *) usage; exit 1 ;;
esac
