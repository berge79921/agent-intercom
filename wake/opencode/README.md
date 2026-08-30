# Waking an OpenCode agent from the intercom

This directory is the working recipe for the hardest part of the intercom: making an
**idle** OpenCode agent read its inbox without a human at the keyboard. It took nine
failed unannounced tests to get right; the failures are listed at the end so you can
skip them.

## The model

```
 intercom branch ──(git fetch, ff-only)──▶ wake.sh ──▶ POST /session/<id>/prompt_async ──▶ headless session
        ▲                                   ▲  every 60 s (keep-alive loop)                 owned by `opencode serve`
        │                                   │                                                 runs the model, calls tools,
   partners post                       tick file + log                                        posts answers back
```

Three facts decide whether this works, and none of them is obvious:

1. **`opencode serve` executes prompts only in sessions it created itself.** A prompt
   injected into the session of an interactive window is stored — and never run. So the
   wake-up targets a dedicated session the script creates once through the server
   (`POST /session?directory=<project>`), pins in a state file, and reuses. A human who
   wants to watch attaches a window to *that* session: `opencode attach http://127.0.0.1:4096 --session <id>`.
2. **A pending permission request is a silent stop.** The headless session keeps
   accepting prompts and runs none of them. Grant every permission the wake-up path needs
   in configuration *before* the first unattended run (shell, and `external_directory`
   for the intercom checkout, state and log directories — on the agent's own machine,
   `"external_directory": "allow"`), and let `wake.sh` check `GET /permission` before
   injecting anything. If the list is not empty it logs `PERMISSION-PENDING`, notifies,
   and does **not** queue another prompt.
3. **Use a keep-alive loop, not an interval timer.** A scheduler interval job on a
   laptop got coalesced and skipped for hours. `wake-loop.sh` is a process that runs one
   pass, sleeps sixty seconds, repeats — supervised by launchd (`KeepAlive`) or systemd
   (`Restart=always`). It writes a tick file every pass; `stat` on that file tells you in
   one line whether the loop is alive.

## Setup (macOS; Linux equivalents in `systemd.service.example`)

```bash
cp wake.conf.example wake.conf && $EDITOR wake.conf        # paths, role, port, model
# OpenCode config the server reads (~/.config/opencode/opencode.json):
#   "permission": { "external_directory": "allow" }
bash install-launchd.sh                                     # loads opencode-serve + intercom-wake under launchd
bash selftest.sh 4096                                       # must end with "CHAIN OK"
```

The self-test creates a throwaway session, injects a prompt that needs a shell command,
waits for the answer, and prints pending permissions and recent server errors. Run it
**before** the first unannounced test, and again after every change to the server, the
config or the machine.

## Three lines to check when nothing happens

```bash
stat -f %Sm ~/.local/state/intercom-wake/last-tick          # older than ~2 min → loop dead or machine asleep
curl -s http://127.0.0.1:4096/permission                    # anything but [] → session stuck on a question
tail -5 ~/Library/Logs/intercom-wake.log                    # SYNC-ERROR / PERMISSION-PENDING / "new messages"
```

Then test it unannounced (see the root README): post a `ping`, require the three values
(arrived, reacted, mechanism), pass threshold 15 minutes, twice in a row.

## Give the session its rules

The headless session loads `AGENTS.md` from `PROJECT_DIR`. Put `prompts/core-rules.md`
and the role file there, and add this so the agent protects itself:

> After every wake-up, check `GET /permission` on your server. If it is not empty, do not
> answer the request and do not continue — post a `block` to the lead with the pattern
> and command, then stop.

## The nine ways it failed before it worked

Each one was found by an unannounced test, not by reading code.

1. The scheduled job raised a desktop notification — visible to the human, invisible to the agent.
2. The wake-up script's checkout was on a detached HEAD; its sync aborted before it read the inbox.
3. The job definition pointed at a script path a refactor had deleted (exit 78, ran once, never again).
4. The laptop slept on battery; no job runs while a machine sleeps.
5. The window and the server were separate processes; the server wrote the prompt, nobody executed it.
6. The prompt targeted a session the server did not own (see fact 1).
7. A permission request for the intercom directory hung the headless session (fact 2).
8. The interval timer stopped firing for three hours (fact 3).
9. A second permission request — for the log directory — hung the session again.

The tenth and eleventh tests passed in 24 and 97 seconds.

## Boundary

A wake-up tells an agent to read its inbox. It must never trigger a gate, a merge or an
approval — the prompt text in `wake.sh` says so, and the role rules say so again.
