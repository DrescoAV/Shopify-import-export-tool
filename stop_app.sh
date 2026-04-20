#!/usr/bin/env bash
set -u

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_ROOT"

PID_FILE="$PROJECT_ROOT/logs/app.pid"
PORT="${PORT:-5000}"
STOPPED=0

if [[ -f "$PID_FILE" ]]; then
  PID_VALUE="$(head -n 1 "$PID_FILE" 2>/dev/null || true)"
  if [[ -n "$PID_VALUE" ]]; then
    kill "$PID_VALUE" >/dev/null 2>&1 || true
    sleep 1
    kill -9 "$PID_VALUE" >/dev/null 2>&1 || true
    STOPPED=1
  fi
  rm -f "$PID_FILE"
fi

if lsof -ti tcp:"$PORT" >/dev/null 2>&1; then
  while IFS= read -r PID_VALUE; do
    [[ -n "$PID_VALUE" ]] || continue
    kill "$PID_VALUE" >/dev/null 2>&1 || true
    sleep 1
    kill -9 "$PID_VALUE" >/dev/null 2>&1 || true
    STOPPED=1
  done < <(lsof -ti tcp:"$PORT")
fi

if [[ "$STOPPED" -eq 1 ]]; then
  echo "Application stopped."
else
  echo "No running application found."
fi
