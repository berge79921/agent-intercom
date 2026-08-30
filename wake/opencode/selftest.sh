#!/bin/bash
# Measures the wake-up chain on this machine without any window: server -> session -> prompt_async
# (with a shell command) -> answer. Usage: bash selftest.sh [port]  (default 4096). Creates one test session.
PORT=${1:-4096}; B=http://127.0.0.1:$PORT; PY=python3
echo "== 1. who listens on port $PORT =="; L=$(lsof -nP -iTCP:$PORT -sTCP:LISTEN 2>/dev/null | tail -n +2); [ -n "$L" ] && echo "$L" | awk '{print "   "$1" pid "$2}' || echo "   NOBODY - no server on $PORT"
echo "== 2. health =="; H=$(curl -s -m 5 $B/global/health); echo "   ${H:-NO ANSWER}"; [ -z "$H" ] && { echo "ABORT: server not answering"; exit 1; }
echo "== 3. sessions the server owns =="; curl -s -m 5 $B/session | $PY -c "import sys,json;ss=json.load(sys.stdin);print('   count:',len(ss));[print('   ',s['id'],'|',(s.get('title') or '')[:40]) for s in ss[:5]]"
echo "== 4. test session + wake-up WITH a shell command =="; SID=$(curl -s -m 10 -X POST $B/session -H 'Content-Type: application/json' -d '{"title":"wake-selftest"}' | $PY -c "import sys,json;print(json.load(sys.stdin)['id'])"); echo "   sid=$SID"
T0=$(date +%s); CODE=$(curl -s -o /dev/null -w '%{http_code}' -m 10 -X POST "$B/session/$SID/prompt_async" -H 'Content-Type: application/json' -d '{"parts":[{"type":"text","text":"Run in the shell: echo AWAKE-TOOL. Reply with the output only."}]}'); echo "   prompt_async HTTP $CODE ($(date '+%H:%M:%S'))"
echo "== 5. waiting for the answer (max 90 s) =="; for i in $(seq 1 30); do sleep 3; S=$(curl -s -m 5 "$B/session/$SID/message" | $PY -c "
import sys,json
ms=json.load(sys.stdin); a=[m for m in ms if m.get('info',{}).get('role')=='assistant']
if not a: print('no assistant message yet'); sys.exit()
m=a[-1]; i=m['info']; tools=[(p.get('tool'),p.get('state',{}).get('status')) for p in m.get('parts',[]) if p.get('type')=='tool']
txt=' '.join(p.get('text','') for p in m.get('parts',[]) if p.get('type')=='text')
print('model=',i.get('providerID'),'/',i.get('modelID'),'| tools=',tools,'| text=',txt[:60].replace(chr(10),' '),'|','DONE' if i.get('time',{}).get('completed') else 'running','| ERROR='+str(i.get('error'))[:160] if i.get('error') else '')"); echo "   $(( $(date +%s)-T0 ))s $S"; echo "$S" | grep -q "DONE\|ERROR" && break; done
echo "== 6. pending permission requests (must be []) =="; echo "   $(curl -s -m 5 $B/permission 2>/dev/null | cut -c1-300)"
echo "== 7. last server log lines mentioning error/permission =="; LOG=$(ls -t ~/.local/share/opencode/log/*.log 2>/dev/null | head -1); [ -n "$LOG" ] && grep -iE "error|permission" "$LOG" | tail -5 | cut -c1-200 | sed 's/^/   /'
echo "== VERDICT =="; echo "$S" | grep -q "text= AWAKE-TOOL.*DONE" && echo "   CHAIN OK: the injected prompt ran a shell command and answered without any window." || echo "   CHAIN BROKEN - see 5./6./7."
