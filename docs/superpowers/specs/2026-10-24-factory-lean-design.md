# Factory lean tasks: design

Date: 2026-10-24. Status: approved in conversation. Builds on `2026-10-24-factory-review-and-cost-design.md` (the final review).

## Goal

Let simple tasks run the way superpowers `executing-plans` does: the session implements them one after another, proved by their
own checks, with one review of the whole branch at the end instead of a reviewer and an approver per task. Success: a plan of
light and medium tasks with declared files and checks runs with one or two agents in all instead of about three per task, keeps
clay's bookkeeping (lock, ticks, close, execution record), and a task that turns out not to be simple still gets the full loop.

## Approach

The choice is per task, not per run. `state.py preflight` marks each task eligible or not with a reason; the run proposes lean
where possible and the user confirms, or forces it with an argument. A lean task is still a job (`job.json`, branch and worktree
by the run's mode, landing, tick), so every view and record keeps working; it skips Route, Review and Approve. The final review of
the branch becomes mandatory for any run with a lean task. Rejected: a run-wide lean mode (one sensitive task would force the
whole plan back, or slip through), and choosing by the session's model (not known reliably on every host).

## 1. Eligibility

A task is eligible when all hold, all read from the plan:

- tier `light` or `medium`;
- it declares `Files`, and the routing table applied to those paths selects only `code` (the same table and globs as `route`;
  a file entry is the first backticked or slash-bearing word, as `plan_status` reads it);
- it declares `Accept` and `Verify`.

`preflight` without a plan file is unchanged; with a plan file its `plan.tasks[*]` gain `lean`
(`true`/`false`) and `lean_reason` (`"tier careful"`, `"no Files"`, `"Files route to security"`, `"no Verify"`, ...), and the
output gains `lean_count`. A plan with more than 8 eligible tasks gets the warning `long: true`: the last tasks would run on a
long or compacted context.

## 2. Choosing at the start

- `factory-run <plan> lean` runs every eligible task lean; `factory-run <plan> full` runs none. Without either, the run asks
  once, with the mode question: "lean where possible (N of M tasks)" recommended when N > 0, or "all full". The answer is
  recorded in the run state as `lean: "auto" | "off"`.
- The start message says once that lean tasks run on the session's model, so a session on a cheaper model makes them cheaper.
- `factory-task lean <text>` runs the ad hoc task lean when it is eligible (its tier from `tier=`, `Accept` from the text,
  `Verify` required in the text as `verify=<command>`; without it the task runs full and says why).

## 3. The lean job

- `state.py begin-job` takes `--lean`, which records `lean: true` in `job.json`. Branch and worktree follow the run's mode.
- **Build.** The session does the builder's work itself, as `reference/inline.md` already describes: it reads
  `agents/builder.md`, works in the job's worktree with TDD, runs the task's `Verify` through `state.py verify` and writes
  `build.md`. No builder usage is recorded.
- **Gate.** `state.py lean-check <job>` replaces Route, Review and Approve. It reads the change as `route` does and answers
  `{"land": true}` when the routing of the real diff selects only `code`, the job is not risky, and the latest recorded run of
  each `Verify` command is current and exited 0. Otherwise it answers `{"land": false, "promote": "<reason>"}`.
- **Promote.** On `promote`, or when the task's own checks failed twice (two failed records of a `Verify` command), the job
  becomes full: `state.py promote <job>` sets `lean: false` and the job continues at step 3 (Route) of the Job loop, with its
  reviewers and approver, at its declared tier. The session's build stays; a reviewer reads it as any builder's.
- **Land.** As every job (`orchestrator.md`, Landing): tick in the same commit, `state.py land`.
- **Record.** The execution record shows `lean` in Reviews and Notes for a lean job, and `promoted: <reason>` in Notes for one
  that became full.

## 4. Final review

- A run with at least one lean job always runs the final review, also for a plan of one task and for an ad hoc plan: it is the
  only independent reading those tasks get. `final-diff` reports `lean: <count>` so the orchestrator can tell.
- Nothing else about the final review changes: one fix task (lean when eligible), one recheck of the fix.

## 5. Documentation

- New part `reference/lean.md`: eligibility, the choice, the lean job, promotion. Read by `factory-run` and `factory-task`.
- `job-loop.md` points lean jobs to it at step 2; `completion.md` states the mandatory final review; `start.md` adds the lean
  question to the mode question and the resume rule (a lean job in `build` with a ready build.md goes to `lean-check`).
- `inline.md` stays for full jobs built in the session; `lean.md` says how the two differ (inline keeps reviewers and approver).
- README Workflow gets one paragraph.

## Testing

- `tests/test_state.py`: eligibility for each reason; `preflight` with a plan adds `lean`, `lean_reason`, `lean_count`, `long`;
  `begin-job --lean`; `lean-check` lands a clean code-only change with a passing current check, and promotes on a security path,
  on a failing check, on a stale check, and on two failed checks; `promote` clears `lean`; the execution record notes `lean` and
  `promoted`; `final-diff` reports `lean`.
- `tests/test_orchestrator_text.py`: `factory-run` and `factory-task` read `reference/lean.md`; `completion.md` runs the final
  review whenever a lean job exists.
- `scripts/validate.py`: the skills that read `lean.md` exist and point to it.
