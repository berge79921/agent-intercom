# Agent Intercom — a two-page note on coordinating AI agents

## The problem appears at the second agent

A single coding agent needs no coordination. You talk to it, it works, you read the diff. The moment a second agent joins — a builder and a reviewer, two specialists, one agent per machine — three costs appear that no model quality fixes:

**Collision.** Two agents edit the same worktree. One rebases what the other is mid-way through. The damage is silent and shows up as a mysterious test failure an hour later.

**Amnesia.** A decision made in one agent's context does not exist for the other. The second agent re-derives it, differently. Now you have two defensible answers and no record of which one is in force.

**Silence.** Agent A hands work to agent B and stops. B never learns that something arrived. Both are technically "running". The human discovers the standstill hours later — usually by asking "what is everyone doing?"

The instinct is to solve this with a smarter orchestrator. In practice the expensive failures are not orchestration failures; they are bookkeeping failures. Who said what, who owes an answer, who holds the keys, and who fell asleep.

## The model: a git branch as the bus

Agent Intercom keeps one branch (`intercom`) whose only content is messages, locks and generated inboxes. Every message is a markdown file with front matter: `from`, `to`, `type`, `subject`, `needs_ack`, `deadline`, `refs`, plus a body. Agents post with one command; the tool renders inboxes, commits and pushes.

Three properties follow from choosing git, and they are the whole argument:

- **Auditable by construction.** The history *is* the record. Every instruction, hand-off and approval is a commit with an author and a timestamp. When a review later asks "who authorised this merge", the answer is a file, not a memory.
- **No infrastructure.** No server to run, no key to rotate, no vendor to trust. If your agents can already push to a repository, they can already use the bus. It also works offline; the next push carries the backlog.
- **Tool-agnostic.** Anything that runs `python3 intercom.py` participates. Mixing vendors is a feature, not a workaround: an independent verifier is only meaningfully independent if it is a *different* model on a *different* machine.

### Roles, not identities

Messages are addressed to roles (`lead`, `builder`, `verifier`, `human`), never to sessions. Sessions crash, get restarted, get replaced by a different model mid-project. The role survives, the mail arrives, the new session reads the branch and knows where it stands. This one indirection removes an entire class of "the agent that had that context is gone".

### Types carry the expectation

A closed list — `task, handoff, gate, decision, question, answer, correction, plan, ping, ack, fyi, block` — tells the receiver what is expected without prose. `handoff` means "I am done, take it". `gate` means "do not proceed until someone verified this". `correction` means "what I told you earlier was wrong, here is the fix". Agents comply with a typed instruction far more reliably than with a paragraph that has to be interpreted first.

### Locks make the collision impossible, not unlikely

`lock acquire <resource> --holder <role>` writes a lock file on the branch. A conflicting acquire exits with code 2 and prints who holds it. The rule that matters is social and must be in every agent's prompt: **exit 2 means ask the holder, never take over.** Automatic takeover after a timeout sounds convenient and is how you lose an hour of another agent's work.

### The watchdog is not optional

`due` reports three things: messages whose deadline passed, messages that have gone unanswered too long, and roles that have not spoken in N minutes. It exits 1 when anything needs attention, so it drops straight into a cron entry, a git hook, or an agent's own monitoring loop.

This exists because of the failure that cost us the most: an event-driven agent is only awake when an event arrives. If a partner goes quiet, *no event arrives* — and the waiting agent interprets silence as "work in progress" indefinitely. A watchdog that fires on **absence** rather than on activity is the difference between a team that notices a stall in five minutes and one that notices it in five hours. Build it in from day one.

## What it deliberately does not do

It does not schedule, spawn, or supervise agents; each keeps its own runtime and permissions. It does not replace your issue tracker — issues hold the backlog, the intercom holds the traffic. It does not carry secrets: messages are plain text in a repository, so credentials, tokens and customer data have no business in them. And it does not decide anything: the tool records that a decision was made and by whom, which is exactly the part humans and agents both forget.

## When it pays off

Two or more agents, running longer than a single sitting, on work where a wrong merge is expensive. Typical shapes: a builder plus an independent verifier that must not share context; a long-running refactor split across machines; a human who wants to step away and still be able to reconstruct what happened at 3 a.m.

For a single agent on a single task it is overhead. Be honest about that; add it when the second agent arrives, not before.

## Getting started

`README.md` has the five-minute setup. `prompts/` has ready-made role instructions for Claude Code, OpenCode and Codex. `LESSONS_LEARNED.md` has the mistakes — read that one before you design your own protocol, because most of it was learned the expensive way.
