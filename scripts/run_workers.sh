#!/usr/bin/env bash
set -euo pipefail

PYTHON_BIN="${AURORA_PYTHON_BIN:-python}"

"${PYTHON_BIN}" -m app.cli.main worker --lane io &
"${PYTHON_BIN}" -m app.cli.main worker --lane transcribe &
"${PYTHON_BIN}" -m app.cli.main worker --lane oss20b &
"${PYTHON_BIN}" -m app.cli.main worker --lane nemotron &
wait
