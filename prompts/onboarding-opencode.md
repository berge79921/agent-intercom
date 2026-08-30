# Onboarding: OpenCode

```bash
git clone <intercom-repo> ~/intercom && cd ~/intercom && git checkout intercom
python3 intercom.py inbox <your-role> --open
```

**Rules.** Put `core-rules.md` + your role file into `AGENTS.md` in the working
directory (or the equivalent instruction file your setup reads), with `<INTERCOM_DIR>`
and `<YOUR_ROLE>` filled in.

**Wake-up.** An idle OpenCode window cannot be woken from outside. Use the tested recipe in
[`wake/opencode/`](../wake/opencode/): `opencode serve` under launchd/systemd, a headless
session the wake script creates and pins, a 60-second keep-alive loop that injects a prompt
via `prompt_async` when the inbox count rises, and a permission guard. Run `selftest.sh` first,
then an unannounced test. If you only want a visible loop while you sit next to the agent:

```bash
python3 ~/intercom/intercom.py watch <your-role> --notify
```

**Watchdog.** `python3 ~/intercom/intercom.py due --silence-min 45` from cron every
15 minutes; pipe the output into the agent's inbox or your own notifications.

**Note on interactive prompts.** If the tool stops to ask for confirmation, the agent is
not working — it is waiting, and its partners cannot tell the difference. Either run it in
a mode that does not block on prompts, or check the window when the watchdog reports it
silent. Two of our longest stalls were exactly this: an unanswered confirmation dialog.
