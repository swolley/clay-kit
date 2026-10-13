# Tiers

The tier of a task chooses the builder's model and effort. Rule: the cheapest tier
that gets the task right the first time; when unsure, the next one up. `fable` is
reserved: use it only when a task clearly needs it.

| Tier | Use | model | effort |
|------|-----|-------|--------|
| light | mechanical edits, config, running builds and tests | sonnet | low |
| medium | standard feature work with clear requirements | sonnet | medium |
| careful | delicate but understood changes, many edge cases | opus | high |
| heavy | unfamiliar code, unclear root cause | opus | xhigh |
| fable | hardest problems | fable | high |

The model is what makes a tier real: some hosts' spawn tool accepts a model but no effort, and then the effort column is a
recommendation, not a guarantee. That is why `light` and `medium` use the faster model and `careful` and `heavy` the stronger
one; with one model for every tier the tier would change nothing. The orchestrator passes `model` when it spawns the builder, and
`effort` too when the host accepts a per-call value; otherwise the agent file's frontmatter default applies.

Fallback: if the host does not accept `fable`, use `opus` with `xhigh`.

## The other agents

| Agent | model | effort |
|-------|-------|--------|
| reviewer-code | sonnet | medium |
| reviewer-ui | sonnet | medium |
| reviewer-ux | sonnet | medium |
| reviewer-security | opus | high |
| reviewer-spec | sonnet | medium |
| approver | sonnet or opus, see below | high |

The approver decides whether a change lands without anyone looking, so it uses `opus` when the job is risky and `sonnet`
otherwise. A job is risky when the routing selected the `security` reviewer (a sensitive path was touched) or its tier is
`careful`, `heavy` or `fable`. In the short path (below) the approver also does the code review.

## Short path

A task of tier `light` whose change touches at most 3 files and 30 lines, and whose routing selects only the `code`
reviewer, takes the short path: no separate reviewer, and the approver reviews the diff itself. It saves one agent run
(about 12 seconds and 12 thousand tokens in the first real run). Anything else keeps its reviewers.
