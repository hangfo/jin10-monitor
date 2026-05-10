#!/bin/zsh
# Small helper for the macOS launchd service.
# It keeps the exact launchctl commands in one place so installs and reloads are easy to repeat.

set -eu

PROJECT_DIR="/Users/rich/jin10-monitor"
LABEL="com.rich.jin10-monitor"
DOMAIN="gui/$(id -u)"
SERVICE_TARGET="$DOMAIN/$LABEL"
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
  launchctl print "$SERVICE_TARGET" >/dev/null 2>&1
}

is_disabled() {
  launchctl print-disabled "$DOMAIN" 2>/dev/null | grep -F "\"$LABEL\" => disabled" >/dev/null 2>&1
}

print_recovery_hint() {
  echo "Next checks:"
  echo "  launchctl print-disabled $DOMAIN"
  echo "  launchctl print $SERVICE_TARGET"
  echo "  tail -n 80 $LOG_FILE"
}

prepare_files() {
  mkdir -p "$HOME/Library/LaunchAgents" "$PROJECT_DIR/logs"
  cp "$SOURCE_PLIST" "$TARGET_PLIST"
}

enable_service() {
  if is_disabled; then
    echo "Service was disabled in launchd. Re-enabling ..."
  else
    echo "Ensuring launchd service is enabled ..."
  fi
  launchctl enable "$SERVICE_TARGET"
}

bootstrap_service() {
  local output
  if ! output=$(launchctl bootstrap "$DOMAIN" "$TARGET_PLIST" 2>&1); then
    echo "ERROR: launchctl bootstrap failed."
    echo "$output"
    if is_disabled; then
      echo "Service still appears disabled after enable attempt."
    fi
    print_recovery_hint
    exit 1
  fi
}

bootout_service() {
  local output
  if ! output=$(launchctl bootout "$DOMAIN" "$TARGET_PLIST" 2>&1); then
    echo "WARN: launchctl bootout did not complete cleanly."
    echo "$output"
    echo "Continuing with plist refresh and bootstrap ..."
  fi
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
  prepare_files
  enable_service
  bootstrap_service
  echo "OK: service installed and started."
  echo "Next: $0 logs"
}

reload() {
  check
  prepare_files
  enable_service
  if is_loaded; then
    bootout_service
  fi
  bootstrap_service
  echo "OK: service reloaded with latest plist."
  echo "Next: $0 logs"
}

status() {
  launchctl print "$SERVICE_TARGET"
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
