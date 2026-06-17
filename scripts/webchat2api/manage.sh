#!/usr/bin/env zsh
set -euo pipefail

PROJECT_DIR="${PROJECT_DIR:-/Users/rich/jin10-monitor}"
WEBCHAT_REPO_URL="${WEBCHAT_REPO_URL:-https://github.com/zqbxdev/webchat2api}"
WEBCHAT_DIR="${WEBCHAT_DIR:-$PROJECT_DIR/.local/webchat2api}"
WEBCHAT_VENV="${WEBCHAT_VENV:-$WEBCHAT_DIR/.venv}"
WEBCHAT_ENV="${WEBCHAT_ENV:-$WEBCHAT_DIR/.jin10.env}"
WEBCHAT_PID_FILE="${WEBCHAT_PID_FILE:-$WEBCHAT_DIR/.jin10.pid}"
WEBCHAT_LOG="${WEBCHAT_LOG:-$WEBCHAT_DIR/.jin10.log}"
WEBCHAT_HOST="${WEBCHAT_HOST:-127.0.0.1}"
WEBCHAT_PORT="${WEBCHAT_PORT:-5083}"
WEBCHAT_LABEL="${WEBCHAT_LABEL:-com.rich.jin10-webchat2api}"
WEBCHAT_PLIST="${WEBCHAT_PLIST:-$WEBCHAT_DIR/$WEBCHAT_LABEL.plist}"
LAUNCHD_DOMAIN="gui/$(id -u)"

usage() {
  cat <<'EOF'
Usage: scripts/webchat2api/manage.sh <command>

Commands:
  setup       Clone/update webchat2api and install Python deps
  setup-ui    Build the optional local web admin UI
  start       Start local webchat2api on 127.0.0.1:5083
  stop        Stop local webchat2api
  restart     Stop then start
  status      Show process and health status
  logs        Tail local webchat2api log
  env         Print dashboard .env snippet
  accounts    List sanitized local proxy accounts
  import-gpt-token <file>
              Import one GPT/ChatGPT access token from a local file
  open        Open local admin UI in the default browser

No ChatGPT account token/cookie is read by this script. Add accounts only in
the local webchat2api admin UI.
EOF
}

ensure_local_dir() {
  mkdir -p "$PROJECT_DIR/.local"
}

ensure_repo() {
  ensure_local_dir
  if [[ -d "$WEBCHAT_DIR/.git" ]]; then
    git -C "$WEBCHAT_DIR" pull --ff-only
  else
    git clone "$WEBCHAT_REPO_URL" "$WEBCHAT_DIR"
  fi
}

generate_secret() {
  python3 - <<'PY'
import secrets
print(secrets.token_urlsafe(48))
PY
}

ensure_env() {
  mkdir -p "$WEBCHAT_DIR"
  if [[ ! -f "$WEBCHAT_ENV" ]]; then
    local secret
    secret="$(generate_secret)"
    cat > "$WEBCHAT_ENV" <<EOF
HOST=$WEBCHAT_HOST
PORT=$WEBCHAT_PORT
LOGIN_SECRET=$secret
WEBCHAT2API_AUTH_KEY=$secret
STORAGE_BACKEND=json
EOF
    chmod 600 "$WEBCHAT_ENV"
  fi
}

load_env() {
  ensure_env
  set -a
  source "$WEBCHAT_ENV"
  set +a
}

xml_escape() {
  python3 - "$1" <<'PY'
import html
import sys
print(html.escape(sys.argv[1], quote=True))
PY
}

write_launchd_plist() {
  load_env
  local py work log host port login auth storage
  py="$(xml_escape "$WEBCHAT_VENV/bin/python")"
  work="$(xml_escape "$WEBCHAT_DIR")"
  log="$(xml_escape "$WEBCHAT_LOG")"
  host="$(xml_escape "${HOST:-$WEBCHAT_HOST}")"
  port="$(xml_escape "${PORT:-$WEBCHAT_PORT}")"
  login="$(xml_escape "$LOGIN_SECRET")"
  auth="$(xml_escape "$WEBCHAT2API_AUTH_KEY")"
  storage="$(xml_escape "${STORAGE_BACKEND:-json}")"
  cat > "$WEBCHAT_PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>$WEBCHAT_LABEL</string>
  <key>WorkingDirectory</key>
  <string>$work</string>
  <key>ProgramArguments</key>
  <array>
    <string>$py</string>
    <string>-u</string>
    <string>main.py</string>
  </array>
  <key>EnvironmentVariables</key>
  <dict>
    <key>HOST</key>
    <string>$host</string>
    <key>PORT</key>
    <string>$port</string>
    <key>LOGIN_SECRET</key>
    <string>$login</string>
    <key>WEBCHAT2API_AUTH_KEY</key>
    <string>$auth</string>
    <key>STORAGE_BACKEND</key>
    <string>$storage</string>
  </dict>
  <key>StandardOutPath</key>
  <string>$log</string>
  <key>StandardErrorPath</key>
  <string>$log</string>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <false/>
</dict>
</plist>
EOF
  chmod 600 "$WEBCHAT_PLIST"
}

ensure_python_runtime() {
  if [[ ! -x "$WEBCHAT_VENV/bin/python" ]]; then
    python3 -m venv "$WEBCHAT_VENV"
  fi
  "$WEBCHAT_VENV/bin/python" -m pip install --upgrade pip
  "$WEBCHAT_VENV/bin/python" -m pip install \
    "curl-cffi>=0.15.0" \
    "fastapi>=0.136.0" \
    "pillow>=12.2.0" \
    "pybase64>=1.4.3" \
    "python-multipart>=0.0.26" \
    "tiktoken>=0.12.0" \
    "uvicorn>=0.44.0" \
    "sqlalchemy>=2.0.0" \
    "psycopg2-binary>=2.9.0" \
    "gitpython>=3.1.0"
}

build_web_ui() {
  if [[ ! -d "$WEBCHAT_DIR/web" ]]; then
    return
  fi
  if [[ ! -d "$WEBCHAT_DIR/web/node_modules" ]]; then
    (cd "$WEBCHAT_DIR/web" && npm ci)
  fi
  (cd "$WEBCHAT_DIR/web" && npm run build)
  rm -rf "$WEBCHAT_DIR/web_dist"
  cp -R "$WEBCHAT_DIR/web/out" "$WEBCHAT_DIR/web_dist"
}

setup() {
  ensure_repo
  ensure_env
  ensure_python_runtime
  echo "webchat2api setup complete: $WEBCHAT_DIR"
  echo "Admin UI has not been built. Run 'scripts/webchat2api/manage.sh setup-ui' when npm install is acceptable."
  env_snippet
}

setup_ui() {
  ensure_repo
  build_web_ui
  echo "webchat2api web UI build complete."
}

is_running() {
  if command -v launchctl >/dev/null 2>&1 && launchctl print "$LAUNCHD_DOMAIN/$WEBCHAT_LABEL" >/dev/null 2>&1; then
    local pid
    pid="$(launchctl print "$LAUNCHD_DOMAIN/$WEBCHAT_LABEL" 2>/dev/null | awk '/^[[:space:]]*pid = / {print $3; exit}')"
    [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null && return 0
  fi
  [[ -f "$WEBCHAT_PID_FILE" ]] || return 1
  local pid
  pid="$(cat "$WEBCHAT_PID_FILE" 2>/dev/null || true)"
  [[ -n "$pid" ]] || return 1
  kill -0 "$pid" 2>/dev/null
}

start() {
  ensure_repo
  ensure_env
  if [[ ! -x "$WEBCHAT_VENV/bin/python" ]]; then
    echo "Python runtime is missing; running setup first."
    setup
  fi
  if is_running; then
    echo "webchat2api already running."
    return
  fi
  if command -v launchctl >/dev/null 2>&1; then
    write_launchd_plist
    launchctl bootout "$LAUNCHD_DOMAIN/$WEBCHAT_LABEL" >/dev/null 2>&1 || true
    launchctl bootstrap "$LAUNCHD_DOMAIN" "$WEBCHAT_PLIST"
    launchctl enable "$LAUNCHD_DOMAIN/$WEBCHAT_LABEL" >/dev/null 2>&1 || true
    launchctl kickstart -k "$LAUNCHD_DOMAIN/$WEBCHAT_LABEL" >/dev/null 2>&1 || true
    sleep 2
    status
    return
  fi
  load_env
  mkdir -p "$(dirname "$WEBCHAT_LOG")"
  (
    cd "$WEBCHAT_DIR"
    nohup "$WEBCHAT_VENV/bin/python" -u main.py </dev/null >> "$WEBCHAT_LOG" 2>&1 &
    local pid=$!
    echo "$pid" > "$WEBCHAT_PID_FILE"
    disown "$pid" 2>/dev/null || true
  )
  sleep 2
  status
}

stop() {
  if command -v launchctl >/dev/null 2>&1; then
    launchctl bootout "$LAUNCHD_DOMAIN/$WEBCHAT_LABEL" >/dev/null 2>&1 || true
  fi
  if ! is_running; then
    rm -f "$WEBCHAT_PID_FILE"
    echo "webchat2api is not running."
    return
  fi
  local pid
  pid="$(cat "$WEBCHAT_PID_FILE")"
  kill "$pid" 2>/dev/null || true
  for _ in {1..20}; do
    if ! kill -0 "$pid" 2>/dev/null; then
      break
    fi
    sleep 0.2
  done
  if kill -0 "$pid" 2>/dev/null; then
    kill -9 "$pid" 2>/dev/null || true
  fi
  rm -f "$WEBCHAT_PID_FILE"
  echo "webchat2api stopped."
}

status() {
  if is_running; then
    local pid
    pid="$(launchctl print "$LAUNCHD_DOMAIN/$WEBCHAT_LABEL" 2>/dev/null | awk '/^[[:space:]]*pid = / {print $3; exit}' || true)"
    echo "process: running${pid:+ (pid $pid)}"
  else
    echo "process: stopped"
  fi
  if curl -sf "http://$WEBCHAT_HOST:$WEBCHAT_PORT/health" >/dev/null 2>&1; then
    echo "health: ok"
  else
    echo "health: unavailable"
  fi
  echo "admin UI: http://$WEBCHAT_HOST:$WEBCHAT_PORT"
}

logs() {
  touch "$WEBCHAT_LOG"
  tail -f "$WEBCHAT_LOG"
}

accounts() {
  load_env
  curl -sf \
    -H "Authorization: Bearer $WEBCHAT2API_AUTH_KEY" \
    "http://$WEBCHAT_HOST:$WEBCHAT_PORT/api/accounts?provider=gpt"
  echo
}

import_gpt_token() {
  local token_file="${1:-}"
  if [[ -z "$token_file" ]]; then
    echo "Usage: scripts/webchat2api/manage.sh import-gpt-token <local-token-file>" >&2
    echo "The file should contain one GPT/ChatGPT access token. It will not be printed." >&2
    return 2
  fi
  if [[ ! -f "$token_file" ]]; then
    echo "token file not found: $token_file" >&2
    return 1
  fi
  load_env
  WEBCHAT_URL="http://$WEBCHAT_HOST:$WEBCHAT_PORT" \
  WEBCHAT_AUTH="$WEBCHAT2API_AUTH_KEY" \
  TOKEN_FILE="$token_file" \
  python3 - <<'PY'
import json
import os
import urllib.error
import urllib.request
from pathlib import Path

token = Path(os.environ["TOKEN_FILE"]).read_text(encoding="utf-8").strip()
if not token:
    raise SystemExit("token file is empty")
body = json.dumps({"provider": "gpt", "tokens": [token]}).encode("utf-8")
request = urllib.request.Request(
    os.environ["WEBCHAT_URL"].rstrip("/") + "/api/accounts",
    data=body,
    headers={
        "Authorization": f"Bearer {os.environ['WEBCHAT_AUTH']}",
        "Content-Type": "application/json",
    },
    method="POST",
)
try:
    with urllib.request.urlopen(request, timeout=120) as response:
        payload = json.loads(response.read().decode("utf-8"))
except urllib.error.HTTPError as exc:
    detail = exc.read().decode("utf-8", errors="replace")
    raise SystemExit(f"import failed: HTTP {exc.code}: {detail}") from exc
print(json.dumps(payload, ensure_ascii=False, indent=2))
PY
}

env_snippet() {
  load_env
  cat <<EOF

Dashboard .env snippet:
CHATGPT_PROXY_LABEL=ChatGPT Proxy
CHATGPT_PROXY_BASE_URL=http://$WEBCHAT_HOST:$WEBCHAT_PORT/v1
CHATGPT_PROXY_API_KEY=$WEBCHAT2API_AUTH_KEY
CHATGPT_PROXY_MODEL=gpt-4o
CHATGPT_PROXY_MAX_TOKENS=1800
CHATGPT_PROXY_TEMPERATURE=0.2

Admin UI: http://$WEBCHAT_HOST:$WEBCHAT_PORT
Admin login key: $LOGIN_SECRET
EOF
}

open_ui() {
  open "http://$WEBCHAT_HOST:$WEBCHAT_PORT"
}

cmd="${1:-}"
case "$cmd" in
  setup) setup ;;
  setup-ui) setup_ui ;;
  start) start ;;
  stop) stop ;;
  restart) stop; start ;;
  status) status ;;
  logs) logs ;;
  env) env_snippet ;;
  accounts) accounts ;;
  import-gpt-token) import_gpt_token "${2:-}" ;;
  open) open_ui ;;
  -h|--help|help|"") usage ;;
  *)
    echo "Unknown command: $cmd" >&2
    usage >&2
    exit 2
    ;;
esac
