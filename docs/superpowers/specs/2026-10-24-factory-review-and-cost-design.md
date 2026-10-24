# Factory review and cost: design

Date: 2026-10-24. Status: approved in conversation.

## Goal

Close the gaps found by comparing the factory with superpowers 7.0.0 `subagent-driven-development`: no review of the branch as
a whole, a job that fails its rounds goes to a person without a stronger builder ever trying, and the approver is a fixed extra
agent on every job. Success: a run catches problems that only show across tasks, lands more jobs without a person, and spends
one agent less on most ordinary jobs, with the same files and scripts on every host.

Out of scope: aligning `factory-brainstorm` and `factory-plan` with superpowers 7.0.0, which is a separate spec.

## Approach

Three changes to the job loop and its completion, each owned by `state.py` for the bookkeeping and by the reference text for
the orchestrator's steps. The final review is what makes the wider short path safe: a job read by one agent instead of two is
read again, with the others, at the end. Rejected for the approver: landing non-risky jobs without an approver when every lens
passes (moves evidence, conflict and policy checks into code or into the code reviewer), and the approver on `haiku` (smallest
saving, weakest last gate). Rejected for the escalation: an extra fourth round (raises the cost ceiling) and asking the user
(stops `auto` runs for what a stronger model can try).

## 1. Wider short path

- `state.py route` sets `lite` when the job is not risky, its tier is `light` or `medium`, and the routing selects only the
  `code` lens. Size no longer counts: `LITE_MAX_FILES` and `LITE_MAX_LINES` go. Risky keeps its meaning from `tiers.md` (the
  `security` lens selected, or tier `heavy` or `fable`), so a lite job is never risky.
- In a lite round the approver reviews the code first, as the code reviewer would, and writes `round-N/review-code.md` with
  `VERDICT: PASS` or `VERDICT: CHANGES` on line one. On `CHANGES` it stops there and writes no `decision.md`; on `PASS` it goes on to
  its three gates and writes `decision.md`.
- The orchestrator runs `state.py verdicts <job>` after a lite approver too. `route` records `code` as the round's lens for a lite
  job (`reviewers: ["code"]`, `rerun: []`), so `verdicts` reads the approver's file like any review file. `all_pass` with a
  `decision.md` goes on to Land or Needs human as today; `CHANGES` goes back to the builder as in step 5, and the resumes count the same.
- `agents/approver.md` "Lite jobs" says to write the review file and when to stop. `job-loop.md` step 3 and `tiers.md` "Short path"
  state the new rule; `tiers.md` drops the "about 12 seconds" figure tied to the old size limit, keeping the saving of one agent run.

## 2. Model escalation in the last round

- Rounds stay at most three: round 1 builds, round 2 resumes the builder, round 3 is the escalation.
- Before round 3, `state.py escalate <job>` moves the tier one step: `light` to `medium`, `medium` to `careful`, `careful` to
  `heavy`. It writes `tier`, `escalated_from` (the tier before) and prints `{ "tier", "escalated_from", "model", "effort" }` from
  the same table `state.py model` uses. For a job already `heavy` or `fable` it changes nothing and prints `"escalated": false`:
  round 3 is then a resume as today. `fable` is never reached by escalation, since it needs the user's confirmation.
- An escalated round 3 spawns a fresh builder, not a resume, with `<paths> Build round 3. Escalated from <tier>: every round's
  reviews are in round-*/. Read task.md, build.md and them, then continue from the branch as it stands.` It is recorded under
  the role `builder` with its own model.
- Risk is computed from the current tier, so a job escalated to `heavy` gets the approver on `opus`. A job escalated to `careful`
  leaves the short path, so its round 3 is reviewed by the code reviewer.
- `close-plan`'s execution record shows the escalation in the tier column as `light→medium`. `job-loop.md` step 5 and `tiers.md`
  describe it.

## 3. Final review of the branch

- **When.** In `completion.md`, as step 1, before the documentation pass, once every task has landed. Skipped for an ad hoc plan
  (`factory-task`) and for a plan of one task, whose only job was already reviewed.
- **The change.** `state.py final-diff --root <repo> --plan <plan-stem>` writes `factory/jobs/_runs/<plan-stem>-final.patch` (commits,
  file list, diff) and prints its path and the base. Isolated: from the merge base of the integration branch and the repo's main
  branch to the integration branch. Current branch: from `base`, the commit `state.py run` now records in the run state when the
  run starts, to `HEAD`. A run state with no `base` (a run started before this change) skips the final review and says so.
  It records the head it diffed to in the run state under `final.head`. With `--fix` it diffs from that recorded head instead,
  so the second review sees only the fix, and writes `<plan-stem>-final-2.patch`.
- **The agent.** New `agents/reviewer-final.md`, read-only except for its file. It reads the plan, the spec the plan names, each
  job's `build.md` `## Deviations`, and the patch. It looks only for what a per-task review cannot see: tasks that contradict or
  duplicate each other, pieces never wired together, spec criteria no task covers, leftovers (debug code, dead files, TODOs the
  plan did not plan). It writes `factory/jobs/_runs/<plan-stem>-final.md`: line one `VERDICT: PASS` or `VERDICT: CHANGES`, then the
  findings, numbered, each with file and line and why it matters. Model: `opus` with effort `high` when any job of the run was
  risky, `sonnet` with effort `high` otherwise; `state.py model --agent reviewer-final [--risky]` prints it, and `tiers.md` lists it.
- **Findings.** On `CHANGES` the orchestrator runs one ad hoc task through the Job loop, `state.py adhoc --text "tier=medium Fix the
  final review findings in factory/jobs/_runs/<plan-stem>-final.md"`, as the documentation pass does. When it lands, it runs
  `final-diff --fix` and spawns `reviewer-final` once more with `Scope: fix` and the previous findings: it checks each finding
  against the fix only and writes `<plan-stem>-final-2.md`. What that second review still lists is not fixed again: it goes to
  the user in one line per finding.
- **Verdict.** After each review the orchestrator runs `state.py final-verdict --root <repo> --plan <plan-stem> [--fix] --agent
  '<usage JSON>'`. It reads line one of the review file, exits 1 when the file or the verdict line is missing (the agent gets one
  more try with a reminder, as in step 4 of the Job loop), and stores under `final` in the run state the verdict, the number of
  findings, the fix job's id once known, and the agent's model, effort, tokens and time.
- **Record.** `close-plan` reads `final` from the run state and appends `### Final review` to the Delivery status: the verdict of
  the first review, the fix job if any, and the findings the last review left open, or `none`. The execution record gets a row
  for `reviewer-final` with its model, tokens and time.

## Testing

- `tests/test_state.py`: `route` sets `lite` for a medium job of any size with only `code`, and not for `careful` or when
  `security` is selected; `verdicts` reads a lite approver's `review-code.md`; `escalate` moves each tier, stops at `heavy` and
  `fable`, and makes a job risky at `heavy`; `run` records `base`; `final-diff` in both modes and with `--fix`; `final-verdict` stores the verdict and fails on a missing line; `close-plan`
  writes `### Final review` and shows an escalated tier.
- `tests/test_orchestrator_text.py`: the reference text names `escalate`, `final-diff` and `reviewer-final` where the steps use
  them, and no longer names the short path's size limits.
- `scripts/validate.py` covers the new agent file and its frontmatter.
