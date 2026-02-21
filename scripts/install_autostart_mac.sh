#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="${AURORA_REPO_DIR:-$(cd "${SCRIPT_DIR}/.." && pwd)}"
LAUNCH_DIR="${HOME}/Library/LaunchAgents"
LOG_DIR="${HOME}/Library/Logs"
GUI_DOMAIN="gui/$(id -u)"

mkdir -p "${LAUNCH_DIR}" "${LOG_DIR}"

if [ -f "${REPO_DIR}/.env" ]; then
  set -a
  . "${REPO_DIR}/.env"
  set +a
fi

write_plist() {
  local label="$1"
  local script_path="$2"
  local log_path="$3"
  local plist_path="${LAUNCH_DIR}/${label}.plist"

  cat >"${plist_path}" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>${label}</string>
  <key>ProgramArguments</key>
  <array>
    <string>${script_path}</string>
  </array>
  <key>WorkingDirectory</key>
  <string>${REPO_DIR}</string>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <true/>
  <key>StandardOutPath</key>
  <string>${log_path}</string>
  <key>StandardErrorPath</key>
  <string>${log_path}</string>
</dict>
</plist>
EOF
}

enable_agent() {
  local label="$1"
  local plist_path="${LAUNCH_DIR}/${label}.plist"
  launchctl bootout "${GUI_DOMAIN}" "${plist_path}" >/dev/null 2>&1 || true
  launchctl bootstrap "${GUI_DOMAIN}" "${plist_path}"
  launchctl kickstart -k "${GUI_DOMAIN}/${label}" >/dev/null 2>&1 || true
}

disable_agent() {
  local label="$1"
  local plist_path="${LAUNCH_DIR}/${label}.plist"
  launchctl bootout "${GUI_DOMAIN}" "${plist_path}" >/dev/null 2>&1 || true
  rm -f "${plist_path}"
}

write_plist "com.aurora.workers" "${REPO_DIR}/scripts/aurora_workers.sh" "${LOG_DIR}/aurora-workers.log"
enable_agent "com.aurora.workers"

write_plist "com.aurora.intake-ui" "${REPO_DIR}/scripts/intake_ui_server.sh" "${LOG_DIR}/aurora-intake-ui.log"
enable_agent "com.aurora.intake-ui"

if [ -n "${OBSIDIAN_VAULT_PATH:-}" ]; then
  write_plist "com.aurora.obsidian-watch" "${REPO_DIR}/scripts/obsidian_watch.sh" "${LOG_DIR}/aurora-obsidian-watch.log"
  enable_agent "com.aurora.obsidian-watch"
else
  disable_agent "com.aurora.obsidian-watch"
fi

if [ -n "${AURORA_DROPBOX_PATHS:-}" ]; then
  write_plist "com.aurora.dropbox-watch" "${REPO_DIR}/scripts/dropbox_watch.sh" "${LOG_DIR}/aurora-dropbox-watch.log"
  enable_agent "com.aurora.dropbox-watch"
else
  disable_agent "com.aurora.dropbox-watch"
fi

echo "Installed autostart agents."
echo "Workers: com.aurora.workers"
echo "Intake UI: com.aurora.intake-ui (http://127.0.0.1:8765)"
if [ -n "${OBSIDIAN_VAULT_PATH:-}" ]; then
  echo "Obsidian watcher: com.aurora.obsidian-watch"
else
  echo "Obsidian watcher skipped (set OBSIDIAN_VAULT_PATH in .env)."
fi
if [ -n "${AURORA_DROPBOX_PATHS:-}" ]; then
  echo "Dropbox watcher: com.aurora.dropbox-watch"
else
  echo "Dropbox watcher skipped (set AURORA_DROPBOX_PATHS in .env)."
fi
