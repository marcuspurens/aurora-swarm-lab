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

_candidate_bins=()
if [ -x "${REPO_DIR}/.venv/bin/python" ]; then
  _candidate_bins+=("${REPO_DIR}/.venv/bin/python")
fi
if command -v python3 >/dev/null 2>&1; then
  _candidate_bins+=("$(command -v python3)")
fi
if command -v python >/dev/null 2>&1; then
  _candidate_bins+=("$(command -v python)")
fi
if [ "${#_candidate_bins[@]}" -eq 0 ]; then
  echo "No Python interpreter found in PATH." >&2
  exit 1
fi

_has_transcribe_backend() {
  local bin="$1"
  "${bin}" - <<'PY' >/dev/null 2>&1
import importlib.util
import os
import shutil

whisper_cmd = str(os.getenv("WHISPER_CLI_CMD", "whisper") or "whisper")
has_cli = bool(shutil.which(whisper_cmd))
has_faster = bool(importlib.util.find_spec("faster_whisper"))
raise SystemExit(0 if (has_cli or has_faster) else 1)
PY
}

PYTHON_BIN=""
for candidate in "${_candidate_bins[@]}"; do
  if _has_transcribe_backend "${candidate}"; then
    PYTHON_BIN="${candidate}"
    break
  fi
done

if [ -z "${PYTHON_BIN}" ]; then
  PYTHON_BIN="${_candidate_bins[0]}"
  echo "Warning: no whisper backend detected for any Python interpreter; using ${PYTHON_BIN} anyway." >&2
fi

export AURORA_PYTHON_BIN="${PYTHON_BIN}"
export PYTHONPATH="${REPO_DIR}${PYTHONPATH:+:${PYTHONPATH}}"

exec "${REPO_DIR}/scripts/run_workers.sh"
