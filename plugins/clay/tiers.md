# Tiers

The tier of a task chooses the builder's model and effort. Rule: the cheapest tier
that gets the task right the first time; when unsure, the next one up. `fable` is
reserved: use it only when a task clearly needs it.

| Tier | Use | model | effort |
|------|-----|-------|--------|
| light | mechanical edits, config, running builds and tests | opus | low |
| medium | standard feature work with clear requirements | opus | medium |
| careful | delicate but understood changes, many edge cases | opus | high |
| heavy | unfamiliar code, unclear root cause | opus | xhigh |
| fable | hardest problems | fable | high |

Applying a tier (Claude Code): where the spawn tool accepts no effort, only the model of the tier is applied and the effort column is a
recommendation, not a guarantee.

Applying a tier (Claude Code): the orchestrator passes `model` when it spawns the
builder, and `effort` too when the host accepts a per-call value; otherwise the
agent file's frontmatter default applies.

Fallback: if the host does not accept `fable`, use `opus` with `xhigh`.

## Fixed settings for the other agents

| Agent | model | effort |
|-------|-------|--------|
| reviewer-code | sonnet | medium |
| reviewer-ui | sonnet | medium |
| reviewer-ux | sonnet | medium |
| reviewer-security | opus | high |
| approver | opus | high |
