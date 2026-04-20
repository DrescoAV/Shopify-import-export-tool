#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_ROOT"

PYTHON_BIN="$PROJECT_ROOT/.venv/bin/python"
PIP_BIN="$PROJECT_ROOT/.venv/bin/pip"
PID_FILE="$PROJECT_ROOT/logs/app.pid"
OUT_LOG="$PROJECT_ROOT/logs/flask.out.log"
ERR_LOG="$PROJECT_ROOT/logs/flask.err.log"
PORT="${PORT:-8000}"

load_port_from_env() {
  local env_port
  env_port="$(grep -E '^PORT=' .env 2>/dev/null | tail -n 1 | cut -d= -f2- | tr -d '[:space:]')"
  if [[ -n "$env_port" ]]; then
    PORT="$env_port"
  fi
}

select_system_python() {
  local candidate
  for candidate in python3.12 python3.11 python3; do
    if command -v "$candidate" >/dev/null 2>&1; then
      if "$candidate" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)' >/dev/null 2>&1; then
        command -v "$candidate"
        return 0
      fi
    fi
  done

  return 1
}

is_project_process() {
  local pid command cwd
  pid="$1"
  command="$(ps -p "$pid" -o command= 2>/dev/null || true)"
  cwd="$(lsof -a -p "$pid" -d cwd -Fn 2>/dev/null | awk '/^n/ {sub(/^n/, "", $0); print; exit}')"
  [[ "$cwd" == "$PROJECT_ROOT" || "$command" == *"$PROJECT_ROOT"* ]]
}

if [[ ! -f ".env" ]]; then
  echo "Missing .env file. Create it from .env.example first."
  exit 1
fi

load_port_from_env

SYSTEM_PYTHON="$(select_system_python || true)"
if [[ -z "$SYSTEM_PYTHON" ]]; then
  echo "Python 3.11+ is required on macOS."
  exit 1
fi

if [[ -x "$PYTHON_BIN" ]]; then
  if ! "$PYTHON_BIN" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)' >/dev/null 2>&1; then
    echo "Existing virtual environment uses an unsupported Python version. Recreating..."
    rm -rf .venv
  fi
fi

if [[ ! -x "$PYTHON_BIN" ]]; then
  echo "Creating virtual environment with $SYSTEM_PYTHON..."
  "$SYSTEM_PYTHON" -m venv .venv
fi

mkdir -p logs

"$PIP_BIN" install -r requirements.txt >/dev/null

if lsof -ti tcp:"$PORT" >/dev/null 2>&1; then
  EXISTING_PID="$(lsof -ti tcp:"$PORT" | head -n 1)"
  if [[ -n "$EXISTING_PID" ]]; then
    if is_project_process "$EXISTING_PID"; then
      echo "Stopping existing app process on port $PORT (PID $EXISTING_PID)..."
      kill "$EXISTING_PID" >/dev/null 2>&1 || true
      sleep 2
      kill -9 "$EXISTING_PID" >/dev/null 2>&1 || true
    else
      echo "Port $PORT is already in use by another process (PID $EXISTING_PID)."
      echo "Update PORT in .env or stop the other application first."
      exit 1
    fi
  fi
fi

nohup "$PYTHON_BIN" app.py >"$OUT_LOG" 2>"$ERR_LOG" &
APP_PID=$!
echo "$APP_PID" >"$PID_FILE"

HEALTHY=0
for _ in {1..20}; do
  sleep 0.5
  if curl --silent --fail "http://127.0.0.1:$PORT/health" >/dev/null 2>&1; then
    HEALTHY=1
    break
  fi
done

if [[ "$HEALTHY" -ne 1 ]]; then
  echo "Application did not become ready. Check logs/flask.err.log"
  exit 1
fi

echo "Application started successfully."
echo "URL: http://localhost:$PORT/"
echo "PID: $APP_PID"

open "http://localhost:$PORT/" >/dev/null 2>&1 || true
