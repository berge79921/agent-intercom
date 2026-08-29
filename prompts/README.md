# Role prompts

Copy the file that matches an agent's job into whatever your tool reads at startup —
`CLAUDE.md`, `AGENTS.md`, a system prompt, a `--append-system-prompt` flag.

| File | For |
|---|---|
| `core-rules.md` | **Everyone.** The protocol rules. Include this in every agent. |
| `lead.md` | The coordinating agent: assigns, reviews, merges, keeps scope. |
| `builder.md` | The implementing agent. |
| `verifier.md` | The independent checking agent (different model, different machine). |
| `onboarding-claude-code.md` | Setup steps for Claude Code |
| `onboarding-opencode.md` | Setup steps for OpenCode |
| `onboarding-codex.md` | Setup steps for Codex CLI |

Two agents are enough to start (`lead` + `builder`). Add `verifier` as soon as
something is worth verifying — and make it a different model on a different machine,
otherwise it is not independent.
