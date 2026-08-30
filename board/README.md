# Board

`board.sh` = agenttrail (MIT) + this repo's skin. It shows the intercom as a live map: roles as
stations, open messages as task capsules, blockers in red, dashed tubes between stations, the
mascot in the corner (it cheers when a run is active).

```bash
bash board/board.sh <intercom-dir> [port]      # default port 5340, binds to 127.0.0.1 only
```

What feeds it: `PLAN.md`, written by `python3 intercom.py render` (which runs on every post,
ack and sync). Roles come from `intercom.json`; `project` there sets the title. Nothing in the
board is edited by hand — change the messages, not the plan.

Upstream is cloned into `~/.cache/agent-intercom/agenttrail` (override with `AGENTTRAIL_HOME`,
pin a ref with `AGENTTRAIL_REF`). The skin (`skin.css`) is injected into a copy of the board's
`index.html`; the mascot frames live in `docs/mascot/`.
