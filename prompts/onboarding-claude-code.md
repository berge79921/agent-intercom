# Onboarding: Claude Code

```bash
git clone <intercom-repo> ~/intercom && cd ~/intercom
git checkout intercom
python3 intercom.py inbox <your-role> --open
```

**Give the agent its rules.** Put `core-rules.md` + your role file into the project's
`CLAUDE.md` (or `~/.claude/CLAUDE.md` for all projects), with `<INTERCOM_DIR>` and
`<YOUR_ROLE>` filled in.

**Wake-up loop.** Claude Code can watch a long-running command and be notified on each
line it prints. Ask it to run:

```
python3 ~/intercom/intercom.py watch <your-role>
```

as a background monitor for the session. Each new message becomes a notification.

**Watchdog for absence.** Also run, on a longer interval:

```
python3 ~/intercom/intercom.py due --silence-min 45
```

It prints only when something is overdue or a role went quiet, and exits 1 — so it works
as a monitor condition, a hook, or a cron entry. Without this, an agent waiting for a
partner will wait forever and look busy while doing it.

**Hooks (optional).** A `SessionStart` hook that runs `intercom.py inbox <role> --open`
means the agent always begins by reading what it owes.
