#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_ROOT"

PYTHON_BIN="$PROJECT_ROOT/.venv/bin/python"
PIP_BIN="$PROJECT_ROOT/.venv/bin/pip"
PID_FILE="$PROJECT_ROOT/logs/app.pid"
OUT_LOG="$PROJECT_ROOT/logs/flask.out.log"
ERR_LOG="$PROJECT_ROOT/logs/flask.err.log"
PORT="${PORT:-5000}"

if [[ ! -f ".env" ]]; then
  echo "Missing .env file. Create it from .env.example first."
  exit 1
fi

if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 is required on macOS."
  exit 1
fi

if [[ ! -x "$PYTHON_BIN" ]]; then
  echo "Creating virtual environment..."
  python3 -m venv .venv
fi

mkdir -p logs

"$PIP_BIN" install -r requirements.txt >/dev/null

if lsof -ti tcp:"$PORT" >/dev/null 2>&1; then
  EXISTING_PID="$(lsof -ti tcp:"$PORT" | head -n 1)"
  if [[ -n "$EXISTING_PID" ]]; then
    echo "Stopping existing app process on port $PORT (PID $EXISTING_PID)..."
    kill "$EXISTING_PID" >/dev/null 2>&1 || true
    sleep 2
    kill -9 "$EXISTING_PID" >/dev/null 2>&1 || true
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
