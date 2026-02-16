#!/usr/bin/env bash
set -euo pipefail

cd /Users/mpmac/aurora-swarm-lab
if [ -f .env ]; then
  set -a
  . ./.env
  set +a
fi

exec python -m app.cli.main obsidian-watch
