#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_DIR="${ROOT_DIR}/logs"

HIGHLIGHT_SERVICE_DIR="${ROOT_DIR}/apps/highlight-service"
CONSOLE_WEB_DIR="${ROOT_DIR}/apps/highlight-cutter/frontend"
SOCIAL_AUTO_UPLOAD_DIR="${ROOT_DIR}/apps/social-auto-upload"

HIGHLIGHT_PORT="${HIGHLIGHT_PORT:-8765}"
SOCIAL_PORT="${SOCIAL_PORT:-5409}"
CONSOLE_PORT="${CONSOLE_PORT:-8001}"

PIDS=()
NAMES=()
PORTS=()

mkdir -p "${LOG_DIR}"

print_section() {
  printf '\n==> %s\n' "$1"
}

require_command() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Missing required command: $1" >&2
    exit 1
  fi
}

check_port_free() {
  local port="$1"
  if lsof -nP -iTCP:"${port}" -sTCP:LISTEN >/tmp/highlight-port-"${port}".txt 2>/dev/null; then
    echo "Port ${port} is already in use:" >&2
    cat /tmp/highlight-port-"${port}".txt >&2
    echo "Stop that process first, or override the port with HIGHLIGHT_PORT / SOCIAL_PORT / CONSOLE_PORT." >&2
    exit 1
  fi
}

wait_for_port() {
  local name="$1"
  local port="$2"
  local timeout="${3:-45}"
  local waited=0

  while ! lsof -nP -iTCP:"${port}" -sTCP:LISTEN >/dev/null 2>&1; do
    sleep 1
    waited=$((waited + 1))
    if [ "${waited}" -ge "${timeout}" ]; then
      echo "${name} did not open port ${port} within ${timeout}s. Check logs in ${LOG_DIR}." >&2
      return 1
    fi
  done
}

start_service() {
  local name="$1"
  local cwd="$2"
  local log_file="$3"
  local port="$4"
  shift 4

  print_section "Starting ${name}"
  echo "cwd: ${cwd}"
  echo "log: ${log_file}"

  (
    cd "${cwd}"
    exec "$@"
  ) >"${log_file}" 2>&1 &

  PIDS+=("$!")
  NAMES+=("${name}")
  PORTS+=("${port}")
}

cleanup() {
  if [ "${#PIDS[@]}" -eq 0 ]; then
    return
  fi

  print_section "Stopping services"
  for i in "${!PIDS[@]}"; do
    local pid="${PIDS[$i]}"
    local name="${NAMES[$i]}"
    if kill -0 "${pid}" >/dev/null 2>&1; then
      echo "Stopping ${name} (${pid})"
      pkill -TERM -P "${pid}" >/dev/null 2>&1 || true
      kill "${pid}" >/dev/null 2>&1 || true
    fi
  done
}

trap cleanup INT TERM EXIT

require_command lsof
require_command pnpm

check_port_free "${HIGHLIGHT_PORT}"
check_port_free "${SOCIAL_PORT}"
check_port_free "${CONSOLE_PORT}"

if [ -x "${HIGHLIGHT_SERVICE_DIR}/.venv/bin/uvicorn" ]; then
  HIGHLIGHT_RUNNER="${HIGHLIGHT_SERVICE_DIR}/.venv/bin/uvicorn"
else
  require_command python3
  HIGHLIGHT_RUNNER="python3 -m uvicorn"
fi

if [ -x "${SOCIAL_AUTO_UPLOAD_DIR}/.venv/bin/python" ]; then
  SOCIAL_PYTHON="${SOCIAL_AUTO_UPLOAD_DIR}/.venv/bin/python"
else
  require_command python3
  SOCIAL_PYTHON="python3"
fi

if ! bash -lc "${SOCIAL_PYTHON} - <<'PY'
import flask
import flask_cors
import playwright
import schedule
import xhs
PY" >/dev/null 2>&1; then
  cat >&2 <<EOF
social-auto-upload backend dependencies are missing.

Install them first:
  cd ${SOCIAL_AUTO_UPLOAD_DIR}
  ${SOCIAL_PYTHON} -m pip install -e '.[web]' playwright==1.52.0 schedule==1.2.2

EOF
  exit 1
fi

start_service \
  "highlight-service" \
  "${HIGHLIGHT_SERVICE_DIR}" \
  "${LOG_DIR}/highlight-service.log" \
  "${HIGHLIGHT_PORT}" \
  bash -lc "${HIGHLIGHT_RUNNER} app.main:app --host 127.0.0.1 --port ${HIGHLIGHT_PORT}"

wait_for_port "highlight-service" "${HIGHLIGHT_PORT}" 45

start_service \
  "social-auto-upload backend" \
  "${SOCIAL_AUTO_UPLOAD_DIR}" \
  "${LOG_DIR}/social-auto-upload.log" \
  "${SOCIAL_PORT}" \
  bash -lc "${SOCIAL_PYTHON} sau_backend.py"

wait_for_port "social-auto-upload backend" "${SOCIAL_PORT}" 45

start_service \
  "highlight console web" \
  "${CONSOLE_WEB_DIR}" \
  "${LOG_DIR}/highlight-console.log" \
  "${CONSOLE_PORT}" \
  env \
    HOST=127.0.0.1 \
    PORT="${CONSOLE_PORT}" \
    HIGHLIGHT_SERVICE_URL="http://127.0.0.1:${HIGHLIGHT_PORT}" \
    PUBLISH_SERVICE_URL="http://127.0.0.1:${SOCIAL_PORT}" \
    pnpm dev

wait_for_port "highlight console web" "${CONSOLE_PORT}" 60

cat <<EOF

All services are running.

Highlight API:        http://127.0.0.1:${HIGHLIGHT_PORT}
Social upload API:   http://127.0.0.1:${SOCIAL_PORT}
Console web:         http://127.0.0.1:${CONSOLE_PORT}

Logs:
  ${LOG_DIR}/highlight-service.log
  ${LOG_DIR}/social-auto-upload.log
  ${LOG_DIR}/highlight-console.log

Press Ctrl+C to stop all services.
EOF

while true; do
  for i in "${!PIDS[@]}"; do
    name="${NAMES[$i]}"
    port="${PORTS[$i]}"
    if ! lsof -nP -iTCP:"${port}" -sTCP:LISTEN >/dev/null 2>&1; then
      echo "${name} is no longer listening on port ${port}. Check logs in ${LOG_DIR}." >&2
      exit 1
    fi
  done
  sleep 2
done
