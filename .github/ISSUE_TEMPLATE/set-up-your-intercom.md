---
name: Set up your own intercom
about: Run two or more agents on one project, coordinated through this repo
title: "Set up an intercom for your agent team"
labels: onboarding
---

## Goal
Two or more AI coding agents (any mix of Claude Code, OpenCode, Codex, …) working on one
project, coordinating through a git branch instead of through you.

## Steps
- [ ] Clone this repo (or copy `intercom.py` into a repo of your own) into a directory that
      no agent edits, e.g. `~/intercom`.
- [ ] `python3 intercom.py init --roles human,lead,builder,verifier` (choose your own roles;
      two are enough to start), commit `intercom.json` on the `intercom` branch, push.
- [ ] Start **at least two agents in different tools**. Give each one `prompts/core-rules.md`
      plus its role file, with `<INTERCOM_DIR>` and `<YOUR_ROLE>` filled in.
- [ ] Start a wake-up loop per agent: `intercom.py watch <role>`.
- [ ] Start the watchdog: `intercom.py due --silence-min 45` on a schedule.
- [ ] Smoke test: from agent A, `post --to <B> --type task --needs-ack`; confirm B is woken,
      acks, and that `inbox A --open` becomes empty.
- [ ] Lock test: both agents `lock acquire` the same path; confirm the second gets exit code 2
      and asks instead of taking over.
- [ ] Kill one agent mid-task and start a fresh session in its place; confirm the new session
      picks up the same role's inbox and continues.

## Report back here
- Which tools/models you used for which role.
- What the wake-up and watchdog setup looks like on your machine.
- Anything that broke, especially around quoting, locks or silent agents — those go into
  `LESSONS_LEARNED.md`.
