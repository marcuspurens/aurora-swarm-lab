#!/usr/bin/env bash
set -euo pipefail

LAUNCH_DIR="${HOME}/Library/LaunchAgents"
GUI_DOMAIN="gui/$(id -u)"

disable_agent() {
  local label="$1"
  local plist_path="${LAUNCH_DIR}/${label}.plist"
  launchctl bootout "${GUI_DOMAIN}" "${plist_path}" >/dev/null 2>&1 || true
  rm -f "${plist_path}"
}

disable_agent "com.aurora.workers"
disable_agent "com.aurora.intake-ui"
disable_agent "com.aurora.obsidian-watch"
disable_agent "com.aurora.dropbox-watch"

echo "Removed Aurora autostart agents."
