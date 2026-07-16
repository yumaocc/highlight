#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HIGHLIGHT_SERVICE_DIR="${ROOT_DIR}/apps/highlight-service"
SOCIAL_AUTO_UPLOAD_DIR="${ROOT_DIR}/apps/social-auto-upload"
FRONTEND_DIR="${ROOT_DIR}/apps/highlight-cutter/frontend"

print_section() {
  printf '\n==> %s\n' "$1"
}

require_command() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Missing required command: $1" >&2
    exit 1
  fi
}

create_venv() {
  local directory="$1"

  if [ ! -x "${directory}/.venv/bin/python" ]; then
    python3 -m venv "${directory}/.venv"
  fi
}

require_command python3
require_command corepack

if ! python3 -c 'import sys; raise SystemExit(not ((3, 10) <= sys.version_info[:2] < (3, 13)))'; then
  echo "Python 3.10, 3.11, or 3.12 is required (found $(python3 --version 2>&1))." >&2
  exit 1
fi

print_section "Installing highlight-service dependencies"
create_venv "${HIGHLIGHT_SERVICE_DIR}"
"${HIGHLIGHT_SERVICE_DIR}/.venv/bin/python" -m pip install --upgrade pip
"${HIGHLIGHT_SERVICE_DIR}/.venv/bin/python" -m pip install \
  -r "${HIGHLIGHT_SERVICE_DIR}/requirements.txt"

print_section "Installing social-auto-upload dependencies"
create_venv "${SOCIAL_AUTO_UPLOAD_DIR}"
"${SOCIAL_AUTO_UPLOAD_DIR}/.venv/bin/python" -m pip install --upgrade pip
"${SOCIAL_AUTO_UPLOAD_DIR}/.venv/bin/python" -m pip install \
  -e "${SOCIAL_AUTO_UPLOAD_DIR}[web]" \
  playwright==1.52.0 \
  schedule==1.2.2 \
  xhs==0.2.13

print_section "Installing frontend dependencies"
(
  cd "${FRONTEND_DIR}"
  corepack pnpm install --frozen-lockfile
)

printf '\nDependencies installed successfully. Start the project with:\n  %s/restart-all.sh\n' "${ROOT_DIR}"
