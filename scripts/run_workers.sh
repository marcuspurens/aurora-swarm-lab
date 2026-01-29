#!/usr/bin/env bash
set -euo pipefail

python -m app.cli.main worker --lane io &
python -m app.cli.main worker --lane transcribe &
python -m app.cli.main worker --lane oss20b &
python -m app.cli.main worker --lane nemotron &
wait
