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
one; with one model for every tier the tier would change nothing. The orchestrator takes what it passes from
`scripts/state.py model`, whose Claude Code defaults are the two tables here; `factory/models.json` in the target repo maps the
tiers and agents for the other hosts (and may override them on Claude Code). The fixed effort of every agent except the builder
is also in the `effort:` of its agent file's frontmatter, which Claude Code applies when no per-call effort is passed.
`reference/hosts.md` says what each host can take.

Fallback: on Claude Code, if the session does not accept `fable`, use `opus` with `xhigh`; on the other hosts `state.py model`
resolves `fable` as `heavy` unless `factory/models.json` gives it an entry.

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

A job of tier `light` or `medium` that is not risky and whose routing selects only the `code` reviewer takes the short path,
whatever the size of its change: no separate reviewer, and the approver writes the code review itself before its gates. When that
review asks for changes, the builder gets the job back as after any review. It saves one agent run per round. Anything else keeps its
reviewers. A short-path job is read by one agent instead of two; the final review of the plan's branch reads it again with the others.
