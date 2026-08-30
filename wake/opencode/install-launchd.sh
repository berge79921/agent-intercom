#!/bin/bash
# Fill the two plist examples with this machine's paths and load them (macOS). Idempotent.
set -e
HERE="$(cd "$(dirname "$0")" && pwd)"; . "$HERE/wake.conf"
OC="$(command -v opencode)"; LA="$HOME/Library/LaunchAgents"; mkdir -p "$LA" "$HOME/Library/Logs"
for f in serve wake; do
  src="$HERE/$( [ $f = serve ] && echo serve.plist.example || echo launchd.plist.example )"
  dst="$LA/$( [ $f = serve ] && echo opencode-serve || echo intercom-wake ).plist"
  sed -e "s|__HOME__|$HOME|g" -e "s|__PATH__|$(dirname "$OC"):/usr/local/bin:/usr/bin:/bin|g" \
      -e "s|__OPENCODE_BIN__|$OC|g" -e "s|__PROJECT_DIR__|$PROJECT_DIR|g" -e "s|__WAKE_DIR__|$HERE|g" "$src" > "$dst"
  launchctl bootout "gui/$(id -u)/$(basename "$dst" .plist)" 2>/dev/null || true
  launchctl bootstrap "gui/$(id -u)" "$dst"; echo "loaded $dst"
done
