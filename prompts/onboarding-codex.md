# Onboarding: Codex CLI

```bash
git clone <intercom-repo> ~/intercom && cd ~/intercom && git checkout intercom
python3 intercom.py inbox <your-role> --open
```

**Rules.** Put `core-rules.md` + your role file into `AGENTS.md` at the repo root, with
`<INTERCOM_DIR>` and `<YOUR_ROLE>` filled in.

**Headless runs.** When running non-interactively, make sure the agent is allowed to run
`git` and `python3` without stopping for approval — an approval prompt in a headless run
looks exactly like silence to everyone else, and the work simply never starts.

**Wake-up loop.** Detach a watcher and let the agent read its output:

```bash
setsid nohup python3 ~/intercom/intercom.py watch <your-role> > ~/intercom-watch.log 2>&1 &
```

**Watchdog.** `python3 ~/intercom/intercom.py due --silence-min 45` on a cron schedule.

**Scope.** Codex is productive and enthusiastic; it will keep improving things nobody asked
for. Always send tasks as a numbered closed list with an explicit "not in scope" line and a
time box, and require a plan message before code. This is the single most effective control
we found.
