#!/bin/bash
# Wake an OpenCode agent when new intercom messages arrive: sync the bus, count open messages,
# and if the count rose, inject a prompt into a SERVER-OWNED headless session via prompt_async.
# One pass per call; run it from wake-loop.sh. Read the README in this directory first.
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
CONF="${WAKE_CONF:-$HERE/wake.conf}"
[ -f "$CONF" ] || { echo "no $CONF (copy wake.conf.example)"; exit 2; }
# shellcheck disable=SC1090
. "$CONF"
mkdir -p "$STATE_DIR" "$(dirname "$LOG")"
SID_FILE="$STATE_DIR/session-id"; COUNT_FILE="$STATE_DIR/last-count"; ERR="$STATE_DIR/sync-err.txt"
log() { echo "$(date '+%Y-%m-%d %H:%M:%S') $*" >> "$LOG"; }
notify() { command -v osascript >/dev/null && osascript -e "display notification \"$1\" with title \"Intercom wake\"" >/dev/null 2>&1; command -v notify-send >/dev/null && notify-send "Intercom wake" "$1" >/dev/null 2>&1; true; }

# The session must belong to the server that receives the prompt. Create it once, pin the ID.
get_sid() {
  local sid=""
  if [ -s "$SID_FILE" ]; then
    sid=$(tr -d '[:space:]' < "$SID_FILE")
    curl -s -m 3 "$SERVE/session/$sid" >/dev/null 2>&1 && { echo "$sid"; return 0; }
    log "  session $sid unknown to server - creating a new one"
  fi
  local resp
  resp=$(curl -s -m 10 -X POST "$SERVE/session?directory=$PROJECT_DIR" -H 'Content-Type: application/json' \
    -d "{\"title\":\"$ROLE-wake\"}")
  sid=$(printf '%s' "$resp" | python3 -c "import sys,json;print(json.load(sys.stdin).get('id',''))" 2>/dev/null)
  [ -n "$sid" ] && { echo "$sid" > "$SID_FILE"; log "  session created: $sid (directory=$PROJECT_DIR)"; echo "$sid"; return 0; }
  log "  POST /session failed: $(printf '%s' "$resp" | cut -c1-160)"; echo ""; return 1
}

# Inject a prompt. A pending permission request means the session is stuck: alarm, do not queue.
wake() {
  local sid="$1" text="$2" pend
  pend=$(curl -s -m 5 "$SERVE/permission" 2>/dev/null)
  if [ -n "$pend" ] && [ "$pend" != "[]" ]; then
    log "PERMISSION-PENDING: $(printf '%s' "$pend" | cut -c1-200) - not injecting"
    notify "wake-up blocked: a permission request is pending"; return 1
  fi
  local body
  body=$(python3 -c 'import json,sys;print(json.dumps({"model":{"providerID":sys.argv[1],"modelID":sys.argv[2]},"parts":[{"type":"text","text":sys.argv[3]}]}))' "$MODEL_PROVIDER" "$MODEL_ID" "$text")
  curl -s -m 15 -X POST "$SERVE/session/$sid/prompt_async" -H 'Content-Type: application/json' -d "$body" >> "$LOG" 2>&1
  log "  prompt_async sent to $sid (model=$MODEL_PROVIDER/$MODEL_ID)"
}

sync_fail() {  # a failed sync is itself a reason to wake the agent - never fail silently
  log "SYNC-ERROR: $1"; local sid; sid=$(get_sid)
  [ -n "$sid" ] && wake "$sid" "Intercom sync failed: $1. Check the checkout manually, then read the inbox."
  notify "intercom sync error: $1"
}

# 1. read-only precheck: right branch, clean worktree. No checkout, no reset, no stash.
cd "$INTERCOM_DIR" || { sync_fail "checkout missing at $INTERCOM_DIR"; exit 1; }
[ "$(git symbolic-ref -q HEAD)" = "refs/heads/$INTERCOM_BRANCH" ] || { sync_fail "not on branch $INTERCOM_BRANCH"; exit 1; }
[ -z "$(git status --porcelain)" ] || { sync_fail "worktree dirty: $(git status --porcelain | head -1)"; exit 1; }
# 2. sync: fetch + fast-forward only
git fetch -q "$INTERCOM_REMOTE" "$INTERCOM_BRANCH" 2>"$ERR" || { sync_fail "$(head -1 "$ERR" | cut -c1-200)"; exit 1; }
if [ "$(git rev-list --count "HEAD..$INTERCOM_REMOTE/$INTERCOM_BRANCH")" -gt 0 ]; then
  git merge -q --ff-only "$INTERCOM_REMOTE/$INTERCOM_BRANCH" 2>"$ERR" || { sync_fail "ff-only merge: $(head -1 "$ERR" | cut -c1-200)"; exit 1; }
fi
# 3. count open messages; wake only when the number ROSE (a falling number means answers went out)
COUNT=$(python3 intercom.py inbox "$ROLE" --open 2>/dev/null | grep -c "OPEN\|OFFEN"); COUNT=${COUNT:-0}
PREV=$(cat "$COUNT_FILE" 2>/dev/null || echo 0); case "$PREV" in ''|*[!0-9]*) PREV=0;; esac
if [ "$COUNT" -gt "$PREV" ]; then
  log "new messages: $COUNT open (was $PREV)"
  sid=$(get_sid) && [ -n "$sid" ] && wake "$sid" "New intercom messages. Run: python3 $INTERCOM_DIR/intercom.py inbox $ROLE --open - then acknowledge, handle the top message, answer via the intercom, send a heartbeat. No gate, no merge, no approval."
  notify "intercom: $COUNT open messages for $ROLE"
fi
echo "$COUNT" > "$COUNT_FILE"
