# Style contract

Every skill and agent of this tool follows these rules and points here instead of
restating them. Change a rule here, once.

## 1. Questions to the user

- Ask with the host's structured-question tool, one question at a time, options
  with a one-line consequence each, the recommended option first.
- The tool of each host, its option limit and the plain-text fallback are in
  `reference/hosts.md` ("Asking the user").
- Only skills in the main session ask. Subagents do not use the question tool:
  an agent that needs an answer writes the open question in its own file and stops.

## 2. Explanations

- Default: what changes, why it matters, and a technical term only when needed, with
  one line of context. Never drop the context a decision needs.
- Go deeper only when the user asks ("explain", "in detail").

## 3. Agent output

- First line machine-readable: `STATUS: READY|BLOCKED`, `VERDICT: PASS|CHANGES`,
  or `APPROVE` / `ESCALATE`.
- Then findings only, each as `path:line`, cause, fix. No narration of steps taken.
- A report is a claim, not a fact: whoever reads it checks it against the diff.

## 4. Language

- Chat follows the repo's instructions (`AGENTS.md` or `CLAUDE.md`). Code, comments
  and docs follow the repo's convention. No emojis, no em-dashes.
