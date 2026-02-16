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

USER_ID="${AURORA_MOBILE_USER_ID:-mobile-user}"
PROJECT_ID="${AURORA_MOBILE_PROJECT_ID:-personal}"
SESSION_ID="${AURORA_MOBILE_SESSION_ID:-mobile-chat}"
TODO_LIMIT="${AURORA_MOBILE_TODO_LIMIT:-12}"

COMMAND="${1:-}"
shift || true
TEXT="${*:-}"

usage() {
  cat <<'EOF'
Usage:
  scripts/mobile_aurora.sh ask "<question>"
  scripts/mobile_aurora.sh remember "<text>"
  scripts/mobile_aurora.sh todo-add "<task>"
  scripts/mobile_aurora.sh todo-list
  scripts/mobile_aurora.sh handoff

Scope defaults can be overridden in env:
  AURORA_MOBILE_USER_ID
  AURORA_MOBILE_PROJECT_ID
  AURORA_MOBILE_SESSION_ID
  AURORA_MOBILE_TODO_LIMIT
EOF
}

if [ -z "${COMMAND}" ]; then
  usage
  exit 1
fi

case "${COMMAND}" in
  ask)
    if [ -z "${TEXT}" ]; then
      echo "Missing question."
      usage
      exit 1
    fi
    exec python -m app.cli.main ask "${TEXT}" \
      --user-id "${USER_ID}" \
      --project-id "${PROJECT_ID}" \
      --session-id "${SESSION_ID}"
    ;;
  remember)
    if [ -z "${TEXT}" ]; then
      echo "Missing text to remember."
      usage
      exit 1
    fi
    exec python -m app.cli.main ask "kom ihåg detta: ${TEXT}" \
      --user-id "${USER_ID}" \
      --project-id "${PROJECT_ID}" \
      --session-id "${SESSION_ID}"
    ;;
  todo-add)
    if [ -z "${TEXT}" ]; then
      echo "Missing TODO text."
      usage
      exit 1
    fi
    exec python -m app.cli.main memory-write \
      --type working \
      --text "TODO: ${TEXT}" \
      --topic todo \
      --topic mobile \
      --importance 0.9 \
      --confidence 0.9 \
      --source-refs '{"kind":"mobile_todo"}' \
      --user-id "${USER_ID}" \
      --project-id "${PROJECT_ID}" \
      --session-id "${SESSION_ID}"
    ;;
  todo-list)
    python -m app.cli.main memory-recall \
      --query "TODO" \
      --type working \
      --limit "${TODO_LIMIT}" \
      --user-id "${USER_ID}" \
      --project-id "${PROJECT_ID}" \
      --session-id "${SESSION_ID}" | awk 'BEGIN {count=0} /TODO:/ {print; count++} END {if (count==0) print "No TODO items found."}'
    ;;
  handoff)
    exec python -m app.cli.main context-handoff
    ;;
  *)
    echo "Unknown command: ${COMMAND}"
    usage
    exit 1
    ;;
esac

