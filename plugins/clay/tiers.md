# Tiers

The tier of a task chooses the builder's model and effort. Rule: the cheapest tier
that gets the task right the first time; when unsure, the next one up. `fable` is
reserved: use it only when a task clearly needs it.

| Tier | Use | model | effort |
|------|-----|-------|--------|
| light | mechanical edits, config, running builds and tests (trial, see below) | haiku | low |
| medium | standard feature work with clear requirements | sonnet | medium |
| careful | delicate but understood changes, many edge cases | opus | high |
| heavy | unfamiliar code, unclear root cause | opus | xhigh |
| fable | hardest problems | fable | high |

`light` on `haiku` is a trial. Go back to `sonnet` if the Findings column of the execution record shows light jobs needing a
second round more often than not over their first five jobs.

## Choosing a tier

- `careful` only when the change writes into a user's files or shared state, or its behaviour must be derived from a comparison
  or an ambiguous spec, or it touches security.
- When the diagnosis is already complete down to the line, the tier is `medium`.
- Size alone never decides the tier.
- `heavy` is for unfamiliar code or an unknown cause.

The model is what makes a tier real: some hosts' spawn tool accepts a model but no effort, and then the effort column is a
recommendation, not a guarantee. That is why `light` and `medium` use the faster models and `careful` and `heavy` the stronger
one; with one model for every tier the tier would change nothing. The orchestrator passes `model` when it spawns the builder, and
`effort` too when the host accepts a per-call value; otherwise the agent file's frontmatter default applies.

Fallback: if the host does not accept `fable`, use `opus` with `xhigh`.

`fable` is never started without the user's confirmation: it is the most costly tier, so a plan that names it does not decide
alone. `run` asks once before it starts such tasks (see `reference/start.md`); only an explicit `tier=fable` on `factory-task` skips the question.

## The other agents

| Agent | model | effort |
|-------|-------|--------|
| reviewer-code | sonnet | medium |
| reviewer-ui | sonnet | medium |
| reviewer-ux | sonnet | medium |
| reviewer-uiux | sonnet | medium |
| reviewer-security | opus | high |
| reviewer-spec | sonnet | medium |
| approver | sonnet or opus, see below | high |

The approver decides whether a change lands without anyone looking, so it uses `opus` when the job is risky and `sonnet`
otherwise. A job is risky when the routing selected the `security` reviewer (a sensitive path was touched) or its tier is
`heavy` or `fable`; `careful` alone does not make a job risky. In the short path (below) the approver also does the code review.

`reviewer-uiux` is `reviewer-ux` and `reviewer-ui` in one run. The run command spawns it instead of the two when a round needs both lenses, so the change is
read once; it still writes one verdict file per lens.

## Short path

A task of tier `light` whose change touches at most 3 files and 30 lines, and whose routing selects only the `code`
reviewer, takes the short path: no separate reviewer, and the approver reviews the diff itself. It saves one agent run
(about 12 seconds and 12 thousand tokens in the first real run). Anything else keeps its reviewers.
