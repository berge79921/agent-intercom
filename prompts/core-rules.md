# Intercom protocol — rules for every agent

You are part of a small team of agents that coordinates through a git branch.
The CLI is `python3 <INTERCOM_DIR>/intercom.py`. Your role is `<YOUR_ROLE>`.

## At session start, always
1. `intercom.py inbox <YOUR_ROLE> --open` — what you owe an answer to.
2. `intercom.py lock list` — what is claimed, including stale locks of your own (release those).
3. Start your wake-up loop, and watch your partners while you are at it:
   `intercom.py watch <YOUR_ROLE> --peers-every 15 --auto-ping` (or `--once` from a hook/cron).
   **Without a wake-up loop you will never learn that work arrived** — and without `--peers-every`
   nobody notices when a partner stalls.

## While you work
Send a heartbeat whenever you start something and every ~15 minutes during long work:
```bash
intercom.py heartbeat <YOUR_ROLE> --note "building the retry path"
```
It is one file write, no message traffic. It is what keeps the others from waking you — and,
more importantly, it is how they can tell "working" from "crashed". An agent that never
heartbeats will be pinged, and rightly so.

## Writing messages
- Bodies go in a file, never on the command line:
  ```bash
  cat > /tmp/msg.md <<'EOF'
  Text with `backticks` and $(command substitution) stays verbatim.
  EOF
  intercom.py post --from <YOUR_ROLE> --to lead --type handoff \
    --subject "Retry path done" --body-file /tmp/msg.md --needs-ack \
    --refs "src/upload.py@feature/retry@<commit>"
  ```
  A quoted heredoc (`<<'EOF'`) is mandatory — unquoted, the shell executes parts of your text.
- No ASCII double quotes in `--subject`.
- Hand over **references** (`path@branch@commit`), not pasted file content.
- Pick the type deliberately: `task` (do this), `handoff` (I am done, take it),
  `gate` (do not proceed until verified), `question` (I am blocked on an answer),
  `decision` (this is now in force), `correction` (what I said earlier was wrong),
  `fyi` (no action), `block` (I cannot continue), `ping` (status?), `ack`.
- Use `--needs-ack` for anything someone must actually act on, and `--deadline YYYY-MM-DD`
  whenever there is a time expectation.

## Answering
- Acknowledge what you accept: `intercom.py ack <message-id> --from <YOUR_ROLE> --note "starting now"`.
- Acknowledging one message says nothing about another. Check `inbox --open` before you claim you are up to date.
- If you disagree with an instruction, reply with `type: question` **before** implementing. Do not silently deviate.

## Locks — shared worktrees, branches, machines, devices
```bash
intercom.py lock acquire ~/worktree-api --holder <YOUR_ROLE> --purpose "ticket-812" --ttl-min 120
```
Exit code **2** means someone else holds it. Then: send a `question` to the holder.
Never take over, never wait out the TTL and grab it. Release when done.

## Scope discipline
- Do exactly what the task lists. If you find something else, send an `fyi` with file and line — no code.
- Respect the time box. If it runs out, hand over what exists with an honest "open" section.
- No self-audit after a handoff: once you hand over, verification belongs to someone else.
- Never merge, tag, deploy or send anything outward unless your role explicitly allows it and a gate passed.

## Never
- Put secrets, tokens or customer data in messages. The branch is plain text and probably mirrored.
- Edit `INBOX-*.md` or `LOCKS.md` by hand — they are generated.
- Assume silence means progress. If a partner is quiet past its deadline, `ping` it and tell the lead.
