# Lessons learned

Everything here was paid for once. It comes from running a lead agent, a builder agent and an independent verifier agent across two machines and three vendors, day and night, on work where a wrong merge was expensive. The ordering is by how much each mistake cost.

---

## 1. An event-driven agent sleeps through silence

**What happened.** The lead agent had a watcher that woke it on *incoming messages*. A partner agent went quiet for four and a half hours with two deliverables blocked behind it. No message arrived, so nothing woke the lead, so nobody noticed. From the outside both agents looked busy. The human found the stall, not the system.

**Why it is structural.** Waiting for a message is waiting for an event that, in exactly the failure case you care about, never happens. Absence produces no event.

**The rule.** Every agent team needs a watchdog that fires on **absence**: deadline passed, message unanswered for N minutes, role silent for N minutes. `intercom.py due` does this and exits 1 when something needs attention — put it in cron, a git hook, or your agent's own monitor loop. Also give every delegated task an explicit deadline and check it; a time box nobody watches is a wish.

**Two refinements we had to add afterwards, both from the same night:**

- **Watching the message channel is not watching the agent.** Our partner agent was quiet for hours — and had been working the whole time, pushing commits to its own branch without writing a single message. A watchdog that only reads the channel reports that agent as dead; one that also checks the branches it moves reports the truth. Hence `activity_sources`: a role counts as alive if it sent a heartbeat, posted a message, **or** moved a git ref you told the tool to track.
- **One watchdog on the coordinator is not enough.** The lead is exactly the agent that will be deep in something else when a partner stalls. Every agent's wake-up loop should watch the others (`watch <role> --peers-every 15 --auto-ping`) and send the wake-up itself. Cheap insurance: a `heartbeat` is one file write, and the auto-ping has a cooldown so a silent role gets one message per episode, not a storm.

**And the correction we needed within the hour:** the first version of the mutual watchdog woke an agent we had dismissed hours earlier, and a verifier that was mid-run. A watchdog that cries wolf is worse than none — people mute it. So: park roles that have no running assignment (`standby <role>`), never auto-ping humans, and set the threshold to the longest *legitimate* quiet stretch of the slowest role (45 minutes for a verifier running a full suite, not 20). Alarm fatigue is a design failure, not a user failure.

**Corollary.** Do not poll a partner's output file every few seconds either. That burns context for nothing. Wake on notification, or on a watchdog interval that matches the work — minutes for a build, not seconds.

---

## 2. Never put message text on the command line

**What happened.** Three separate messages arrived mangled or partially *executed*, because bodies were passed as shell strings. Backticks and `$(...)` in a normal sentence are command substitution. A message explaining a shell fix ran part of that fix.

**The rule.** Compose bodies in a file with a **quoted** heredoc, then `--body-file`:

```bash
cat > /tmp/msg.md <<'EOF'
Use `git rebase -i` and $(whoami) — both survive verbatim here.
EOF
python3 intercom.py post --from lead --to builder --type task --subject "Rebase policy" --body-file /tmp/msg.md
```

The quoted delimiter (`<<'EOF'`) is what makes it safe. Also keep ASCII double quotes out of `--subject`; they break the invocation in ways that are tedious to debug at 3 a.m.

---

## 3. An acknowledgement is not proof that the *other* message was read

**What happened.** A builder acknowledged one message, kept working, and looked responsive — while an assignment sent forty minutes earlier had never been read. It surfaced only because the human noticed the branch was untouched and asked.

**The rule.** Mark real assignments `--needs-ack`, and treat "no ack within ten minutes" as a signal, not as patience. `intercom.py inbox <role> --open` shows exactly what a role still owes. Do not infer "they got it" from unrelated activity.

---

## 4. Address roles, never sessions

**What happened.** A session restart killed every subagent it owned. Work in flight was fine — because the branch held the state, and the successor session read the same inbox and continued.

**The rule.** `to: builder`, never `to: that-session-from-this-morning`. Sessions crash, get restarted, get swapped for a different model mid-project. Roles survive. This one indirection removes a whole class of "the agent that knew that is gone".

---

## 5. `BUSY` means ask, never take over

Locks only work if the social rule is in every agent's prompt. `lock acquire` exits **2** when someone else holds the resource; the correct response is a `question` message to the holder, not a takeover and not a wait for the TTL. Automatic takeover after a timeout sounds convenient and is how an hour of someone else's work disappears. Before acquiring, list your own stale locks and release them — the most common blocker is your own forgotten lock.

---

## 6. Give closed lists and time boxes, or you get infinite iteration

**What happened.** An unconstrained builder will keep finding things to improve, forever, and each round is honest work you did not ask for.

**The rule.** Every task message carries: a numbered list of exactly what is in scope, an explicit "not in scope" line, a time box, and a push cadence ("push work-in-progress every 30 minutes"). When something new turns up mid-task, the builder sends an `fyi` with file and line — and does not touch it. The lead decides whether it becomes a follow-up. In practice we ran a standing rule: *no self-audit after handoff* — once you hand over, verification belongs to someone else.

**Corollary.** When an agent reports "idle, what next?", answer it. An idle agent left to invent its own work will invent scope you then have to review and usually reject.

---

## 7. The verifier must be genuinely independent

Different model, different machine, its own clone, and — importantly — it must *execute*, not read. Our most valuable findings came from a verifier that ran the tests and mutated the code, not from one that reviewed a diff. Independence is not a formality: an agent that reviews its own output tends to confirm its own summary. The lead's job is to make the verifier's life easy (exact commit, evidence paths, closed question list) and then to believe the measurement over the story.

---

## 8. A test that cannot fail proves nothing

Two failure shapes hit us repeatedly:

- **Regex tests over behaviour.** A test asserted that a source file *contains* a certain call. The call was there — and unreachable. The guarded path had never executed once. Test across the real boundary (write to a store, read it back), not against the text of the file.
- **Surviving mutants.** We mutated the code deliberately — removed a guard condition, widened a comparison, deleted an error path — and checked that the suite *died*. Several mutants survived a fully green suite. Every one of them was a hole a future change would fall into. If you claim a rule is enforced, prove it by breaking it and watching a test fail.

---

## 9. Measure the failure mode before you design around it

**What happened.** A probe expected a certain error code to mean "protection is working". It actually meant "item not found" — and something earlier in the sequence had made the item invisible. Days of fixes were built on that misreading, each one plausible, none of them touching the cause.

**The rule.** When behaviour surprises you, stop fixing and build a **measurement pass**: run every plausible variant once, record the raw result of each, decide afterwards. Ours became a diagnostic mode that dumped a JSON of every variant it tried. It replaced a week of guessing with twenty minutes of data — and explained, retroactively, every earlier failure. A number you have not verified is a claim, not a fact.

---

## 10. Hand over references, not content

Messages carry `refs: path@branch@commit`. The receiver reads the repository. Pasting file content into messages produces stale copies, giant diffs in the message history, and disagreements about which version was meant. The one exception is a short, exact error string — that belongs inline, because it is the thing being discussed.

---

## 11. Keep the channel clean

- **Declare superseded work explicitly.** When a hand-off is replaced by a newer one, say so in one message listing what is now dead. Otherwise the next agent works from the wrong artefact.
- **Prune the inbox out loud.** Ours grew a tail of long-answered items that still showed as "open". A single message ("these are closed, here is what actually remains, in this order") saved the verifier an hour of triage.
- **One decision, one message, typed `decision`.** If a decision lives in a paragraph inside a status update, it will be re-litigated.

---

## 12. Small operational things that saved time

- **Local time in output, UTC in files.** IDs stay sortable; humans read local time. Both matter.
- **Idempotent renders.** Inboxes and lock lists are generated files; never hand-edit them.
- **Push after every message.** A message that exists only locally has not been sent.
- **No secrets, ever.** The branch is plain text and probably mirrored. Credentials, tokens, customer data: out.
- **Two remotes.** `extra_remotes` mirrors the branch to a second location. Cheap insurance for the one artefact that records who approved what.

---

## The short version

Wake on absence, not just on arrival. Never let a message body touch the shell. Address roles, not sessions. Ask before taking a lock someone else holds. Give closed lists with deadlines. Let an independent agent execute the verification. Break your own tests to prove they work. Measure before you redesign. Send references, not copies.
