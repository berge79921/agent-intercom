#!/bin/bash
# Live board for an intercom checkout: agenttrail (MIT, github.com/sodiumsun/agenttrail) on the intercom
# directory with this repo's skin (paper/ink/clay palette, mascot) injected, plus a Timeline view on port+1.
# PLAN.md and TIMELINE.md are written by `intercom.py render` on every post/ack/sync.
# Usage: bash board/board.sh [intercom-dir] [port]     (default: this repo, 5340; binds 127.0.0.1 only)
set -e
HERE="$(cd "$(dirname "$0")" && pwd)"; DIR="$(cd "${1:-$HERE/..}" && pwd)"; PORT="${2:-5340}"; TLPORT=$((PORT+1))
CACHE="${AGENTTRAIL_HOME:-$HOME/.cache/agent-intercom/agenttrail}"; PIN="${AGENTTRAIL_REF:-main}"
MASCOT_DIR="${MASCOT_DIR:-$HERE/../docs/mascot}"
command -v node >/dev/null || { echo "node >= 20 required"; exit 1; }
if [ ! -d "$CACHE/.git" ]; then git clone -q --depth 1 https://github.com/sodiumsun/agenttrail "$CACHE"; fi
git -C "$CACHE" fetch -q --depth 1 origin "$PIN" && git -C "$CACHE" checkout -q FETCH_HEAD
[ -f "$CACHE/public/index.upstream.html" ] || cp "$CACHE/public/index.html" "$CACHE/public/index.upstream.html"
B64() { base64 < "$1" | tr -d '\n'; }
IDLE="data:image/png;base64,$(B64 "$MASCOT_DIR/idle.png")"; CHEER="data:image/png;base64,$(B64 "$MASCOT_DIR/cheer.png")"
CSS=$(sed -e "s|__MASCOT_IDLE__|$IDLE|" -e "s|__MASCOT_CHEER__|$CHEER|" "$HERE/skin.css")
python3 - "$CACHE/public/index.upstream.html" "$CACHE/public/index.html" "$CSS" "http://127.0.0.1:$TLPORT/" <<'PY'
import sys
src,dst,css,tl=sys.argv[1:5]
html=open(src,encoding='utf-8').read()
inject=('<style id="intercom-skin">'+css+'</style>\n'
        '<script>(function(){var q=new URLSearchParams(location.search).get("theme");if(q)try{localStorage.setItem("agenttrail-theme",q);document.documentElement.setAttribute("data-theme",q)}catch(e){}'
        'addEventListener("DOMContentLoaded",function(){var s=document.querySelector(".status");if(s){var a=document.createElement("a");a.className="tab timeline";a.href="'+tl+'";a.target="_blank";a.rel="noopener";a.textContent="Timeline";s.insertBefore(a,s.firstChild)}})})();</script>\n</head>')
html=html.replace('</head>',inject,1).replace('<title>agenttrail</title>','<title>intercom board</title>',1)
open(dst,'w',encoding='utf-8').write(html)
PY
[ -f "$DIR/PLAN.md" ] || (cd "$DIR" && python3 intercom.py render >/dev/null 2>&1 || true)
python3 "$HERE/timeline_server.py" "$DIR" "$TLPORT" & TLPID=$!
trap 'kill $TLPID 2>/dev/null' EXIT
echo "board: http://127.0.0.1:$PORT   timeline: http://127.0.0.1:$TLPORT   (repo: $DIR)"
node "$CACHE/bin/agenttrail.mjs" "$DIR" --port "$PORT" --no-open
