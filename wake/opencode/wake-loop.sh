#!/bin/bash
# Keep-alive loop: one wake.sh pass per minute, plus a tick file whose age shows whether the loop is alive.
# Run this under launchd (KeepAlive) or systemd (Restart=always) - not under an interval timer.
HERE="$(cd "$(dirname "$0")" && pwd)"
TICK="${TICK_FILE:-$HOME/.local/state/intercom-wake/last-tick}"; mkdir -p "$(dirname "$TICK")"
while true; do bash "$HERE/wake.sh"; touch "$TICK"; sleep 60; done
