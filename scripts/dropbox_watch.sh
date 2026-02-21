#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="${AURORA_REPO_DIR:-$(cd "${SCRIPT_DIR}/.." && pwd)}"

cd "${REPO_DIR}"
if [ -f .env ]; then
  set -a
  . ./.env
  set +a
fi

if [ -x "${REPO_DIR}/.venv/bin/python" ]; then
  PYTHON_BIN="${REPO_DIR}/.venv/bin/python"
elif command -v python3 >/dev/null 2>&1; then
  PYTHON_BIN="$(command -v python3)"
elif command -v python >/dev/null 2>&1; then
  PYTHON_BIN="$(command -v python)"
else
  echo "No Python interpreter found in PATH." >&2
  exit 1
fi

export PYTHONPATH="${REPO_DIR}${PYTHONPATH:+:${PYTHONPATH}}"
exec "${PYTHON_BIN}" -m app.cli.main dropbox-watch
