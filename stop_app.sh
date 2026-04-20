#!/usr/bin/env bash
set -u

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_ROOT"

PID_FILE="$PROJECT_ROOT/logs/app.pid"
PORT="${PORT:-8000}"
STOPPED=0

load_port_from_env() {
  local env_port
  env_port="$(grep -E '^PORT=' .env 2>/dev/null | tail -n 1 | cut -d= -f2- | tr -d '[:space:]')"
  if [[ -n "$env_port" ]]; then
    PORT="$env_port"
  fi
}

is_project_process() {
  local pid command cwd
  pid="$1"
  command="$(ps -p "$pid" -o command= 2>/dev/null || true)"
  cwd="$(lsof -a -p "$pid" -d cwd -Fn 2>/dev/null | awk '/^n/ {sub(/^n/, "", $0); print; exit}')"
  [[ "$cwd" == "$PROJECT_ROOT" || "$command" == *"$PROJECT_ROOT"* ]]
}

load_port_from_env

if [[ -f "$PID_FILE" ]]; then
  PID_VALUE="$(head -n 1 "$PID_FILE" 2>/dev/null || true)"
  if [[ -n "$PID_VALUE" ]] && is_project_process "$PID_VALUE"; then
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
    if ! is_project_process "$PID_VALUE"; then
      continue
    fi
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
