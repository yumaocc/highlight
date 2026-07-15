#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_DIR="${ROOT_DIR}/logs"
RUN_DIR="${ROOT_DIR}/.run"

HIGHLIGHT_SERVICE_DIR="${ROOT_DIR}/apps/highlight-service"
CONSOLE_WEB_DIR="${ROOT_DIR}/apps/highlight-cutter/frontend"
SOCIAL_AUTO_UPLOAD_DIR="${ROOT_DIR}/apps/social-auto-upload"

HIGHLIGHT_PORT="${HIGHLIGHT_PORT:-8765}"
SOCIAL_PORT="${SOCIAL_PORT:-5409}"
CONSOLE_PORT="${CONSOLE_PORT:-8001}"
WORKER_INTERVAL="${WORKER_INTERVAL:-2}"
WORKER_ID="${WORKER_ID:-local-worker}"

PIDS=()
NAMES=()
PORTS=()

mkdir -p "${LOG_DIR}" "${RUN_DIR}"

print_section() {
  printf '\n==> %s\n' "$1"
}

require_command() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Missing required command: $1" >&2
    exit 1
  fi
}

pid_is_running() {
  local pid="$1"
  [ -n "${pid}" ] && kill -0 "${pid}" >/dev/null 2>&1
}

stop_pid() {
  local pid="$1"
  local name="$2"
  if ! pid_is_running "${pid}"; then
    return
  fi

  echo "Stopping ${name} (${pid})"
  pkill -TERM -P "${pid}" >/dev/null 2>&1 || true
  kill -TERM "${pid}" >/dev/null 2>&1 || true

  for _ in $(seq 1 20); do
    if ! pid_is_running "${pid}"; then
      return
    fi
    sleep 0.25
  done

  echo "Force stopping ${name} (${pid})"
  pkill -KILL -P "${pid}" >/dev/null 2>&1 || true
  kill -KILL "${pid}" >/dev/null 2>&1 || true
}

stop_pid_file() {
  local file="$1"
  local name="$2"
  if [ ! -f "${file}" ]; then
    return
  fi
  local pid
  pid="$(cat "${file}" 2>/dev/null || true)"
  if [ -n "${pid}" ]; then
    stop_pid "${pid}" "${name}"
  fi
  rm -f "${file}"
}

stop_port() {
  local port="$1"
  local name="$2"
  local pids
  pids="$(lsof -tiTCP:"${port}" -sTCP:LISTEN 2>/dev/null || true)"
  if [ -z "${pids}" ]; then
    return
  fi
  for pid in ${pids}; do
    stop_pid "${pid}" "${name} on port ${port}"
  done
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

check_port_free() {
  local port="$1"
  local name="$2"
  if lsof -nP -iTCP:"${port}" -sTCP:LISTEN >/tmp/highlight-restart-port-"${port}".txt 2>/dev/null; then
    echo "${name} port ${port} is still in use after stop attempt:" >&2
    cat /tmp/highlight-restart-port-"${port}".txt >&2
    echo "Restart aborted so an old service is not mistaken for a fresh one." >&2
    exit 1
  fi
}

start_service() {
  local name="$1"
  local cwd="$2"
  local log_file="$3"
  local pid_file="$4"
  local port="$5"
  shift 5

  print_section "Starting ${name}"
  echo "cwd: ${cwd}"
  echo "log: ${log_file}"

  local pid
  pid="$(python3 - "${cwd}" "${log_file}" "$@" <<'PY'
import subprocess
import sys

cwd, log_file, *command = sys.argv[1:]
with open(log_file, "wb") as output:
    process = subprocess.Popen(
        command,
        cwd=cwd,
        stdin=subprocess.DEVNULL,
        stdout=output,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
print(process.pid)
PY
)"
  echo "${pid}" >"${pid_file}"
  PIDS+=("${pid}")
  NAMES+=("${name}")
  PORTS+=("${port}")
}

cleanup() {
  if [ "${#PIDS[@]}" -eq 0 ]; then
    return
  fi

  print_section "Stopping services"
  for i in "${!PIDS[@]}"; do
    stop_pid "${PIDS[$i]}" "${NAMES[$i]}"
  done
}

trap cleanup INT TERM EXIT

require_command lsof
require_command corepack
require_command python3

print_section "Stopping old services"
stop_pid_file "${RUN_DIR}/highlight-worker.pid" "highlight worker"
stop_pid_file "${RUN_DIR}/highlight-console.pid" "highlight console web"
stop_pid_file "${RUN_DIR}/social-auto-upload.pid" "social-auto-upload backend"
stop_pid_file "${RUN_DIR}/highlight-service.pid" "highlight-service"
stop_port "${CONSOLE_PORT}" "highlight console web"
stop_port "${SOCIAL_PORT}" "social-auto-upload backend"
stop_port "${HIGHLIGHT_PORT}" "highlight-service"
check_port_free "${CONSOLE_PORT}" "highlight console web"
check_port_free "${SOCIAL_PORT}" "social-auto-upload backend"
check_port_free "${HIGHLIGHT_PORT}" "highlight-service"

if [ -x "${HIGHLIGHT_SERVICE_DIR}/.venv/bin/uvicorn" ]; then
  HIGHLIGHT_RUNNER="${HIGHLIGHT_SERVICE_DIR}/.venv/bin/uvicorn"
else
  require_command python3
  HIGHLIGHT_RUNNER="python3 -m uvicorn"
fi

if [ -x "${HIGHLIGHT_SERVICE_DIR}/.venv/bin/python" ]; then
  HIGHLIGHT_PYTHON="${HIGHLIGHT_SERVICE_DIR}/.venv/bin/python"
else
  require_command python3
  HIGHLIGHT_PYTHON="python3"
fi

if [ -x "${SOCIAL_AUTO_UPLOAD_DIR}/.venv/bin/python" ]; then
  SOCIAL_PYTHON="${SOCIAL_AUTO_UPLOAD_DIR}/.venv/bin/python"
else
  require_command python3
  SOCIAL_PYTHON="python3"
fi

if ! bash -lc "${SOCIAL_PYTHON} -c 'import flask, flask_cors, playwright, schedule, xhs'" >/dev/null 2>&1; then
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
  "${RUN_DIR}/highlight-service.pid" \
  "${HIGHLIGHT_PORT}" \
  bash -lc "${HIGHLIGHT_RUNNER} app.main:app --host 127.0.0.1 --port ${HIGHLIGHT_PORT}"
wait_for_port "highlight-service" "${HIGHLIGHT_PORT}" 45

start_service \
  "social-auto-upload backend" \
  "${SOCIAL_AUTO_UPLOAD_DIR}" \
  "${LOG_DIR}/social-auto-upload.log" \
  "${RUN_DIR}/social-auto-upload.pid" \
  "${SOCIAL_PORT}" \
  bash -lc "${SOCIAL_PYTHON} sau_backend.py"
wait_for_port "social-auto-upload backend" "${SOCIAL_PORT}" 45

start_service \
  "highlight console web" \
  "${CONSOLE_WEB_DIR}" \
  "${LOG_DIR}/highlight-console.log" \
  "${RUN_DIR}/highlight-console.pid" \
  "${CONSOLE_PORT}" \
  env \
    CI=true \
    HOST=127.0.0.1 \
    PORT="${CONSOLE_PORT}" \
    HIGHLIGHT_SERVICE_URL="http://127.0.0.1:${HIGHLIGHT_PORT}" \
    PUBLISH_SERVICE_URL="http://127.0.0.1:${SOCIAL_PORT}" \
    corepack pnpm dev
wait_for_port "highlight console web" "${CONSOLE_PORT}" 60

start_service \
  "highlight pipeline worker" \
  "${HIGHLIGHT_SERVICE_DIR}" \
  "${LOG_DIR}/highlight-worker.log" \
  "${RUN_DIR}/highlight-worker.pid" \
  "" \
  bash -lc "${HIGHLIGHT_PYTHON} -m app.worker --interval ${WORKER_INTERVAL} --worker-id ${WORKER_ID}"

# Services are intentionally detached after a successful restart. Keep the
# EXIT cleanup active only while startup is in progress.
trap - EXIT

cat <<EOF

All services restarted.

Highlight API:        http://127.0.0.1:${HIGHLIGHT_PORT}
Social upload API:   http://127.0.0.1:${SOCIAL_PORT}
Console web:         http://127.0.0.1:${CONSOLE_PORT}
Pipeline worker:     pid $(cat "${RUN_DIR}/highlight-worker.pid")

Logs:
  ${LOG_DIR}/highlight-service.log
  ${LOG_DIR}/social-auto-upload.log
  ${LOG_DIR}/highlight-console.log
  ${LOG_DIR}/highlight-worker.log

PID files:
  ${RUN_DIR}
EOF

exit 0

while true; do
  for i in "${!PIDS[@]}"; do
    name="${NAMES[$i]}"
    pid="${PIDS[$i]}"
    port="${PORTS[$i]}"
    if ! pid_is_running "${pid}"; then
      echo "${name} process ${pid} exited. Check logs in ${LOG_DIR}." >&2
      exit 1
    fi
    if [ -n "${port}" ] && ! lsof -nP -iTCP:"${port}" -sTCP:LISTEN >/dev/null 2>&1; then
      echo "${name} is no longer listening on port ${port}. Check logs in ${LOG_DIR}." >&2
      exit 1
    fi
  done
  sleep 2
done
