#!/bin/bash
# Live board for an intercom checkout: runs agenttrail (MIT, github.com/sodiumsun/agenttrail) on the
# intercom directory with this repo's skin (factory palette + mascot) injected. PLAN.md is written by
# `intercom.py render` on every post/ack/sync. Usage: bash board/board.sh [intercom-dir] [port]
set -e
HERE="$(cd "$(dirname "$0")" && pwd)"; DIR="$(cd "${1:-$HERE/..}" && pwd)"; PORT="${2:-5340}"
CACHE="${AGENTTRAIL_HOME:-$HOME/.cache/agent-intercom/agenttrail}"; PIN="${AGENTTRAIL_REF:-main}"
command -v node >/dev/null || { echo "node >= 20 required"; exit 1; }
if [ ! -d "$CACHE/.git" ]; then git clone -q --depth 1 https://github.com/sodiumsun/agenttrail "$CACHE"; fi
git -C "$CACHE" fetch -q --depth 1 origin "$PIN" && git -C "$CACHE" checkout -q FETCH_HEAD
# build the skinned index.html next to the original (never edit upstream's file in place)
B64() { base64 < "$1" | tr -d '\n'; }
IDLE="data:image/png;base64,$(B64 "$HERE/../docs/mascot/idle.png")"; CHEER="data:image/png;base64,$(B64 "$HERE/../docs/mascot/cheer.png")"
CSS=$(sed -e "s|__MASCOT_IDLE__|$IDLE|" -e "s|__MASCOT_CHEER__|$CHEER|" "$HERE/skin.css")
python3 - "$CACHE/public/index.html" "$CACHE/public/index.skinned.html" "$CSS" <<'PY'
import sys
src,dst,css=sys.argv[1],sys.argv[2],sys.argv[3]
html=open(src,encoding='utf-8').read()
html=html.replace('</head>','<style id="intercom-skin">'+css+'</style>\n</head>',1).replace('<title>agenttrail</title>','<title>intercom board</title>',1)
open(dst,'w',encoding='utf-8').write(html)
PY
cp "$CACHE/public/index.html" "$CACHE/public/index.upstream.html"; cp "$CACHE/public/index.skinned.html" "$CACHE/public/index.html"
[ -f "$DIR/PLAN.md" ] || (cd "$DIR" && python3 intercom.py render >/dev/null 2>&1 || true)
echo "board: http://127.0.0.1:$PORT  (repo: $DIR)"
exec node "$CACHE/bin/agenttrail.mjs" "$DIR" --port "$PORT" --no-open
