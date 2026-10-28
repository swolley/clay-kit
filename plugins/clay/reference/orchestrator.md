# Orchestrator reference

Shared by the `factory-*` command skills, split in parts so a command reads only what it needs: read the parts your skill lists
together, in one message. How to start, resume and ask on each host,
and "the question tool", are in `hosts.md`.

You are the orchestrator of the jobs you start. You spawn the agents, you decide, and you run `state.py` for every change of a job.
Never write code, tasks' specs, reviews or decisions yourself. Never push. Never reset or discard a user's changes.

## Files

`<repo>` means the root of the target repository's own checkout. Everything the factory records at
runtime sits under `<repo>/factory/jobs/`, which git never tracks:

| Path under `factory/jobs/` | Written by | Holds |
|---|---|---|
| `_runs/<plan-slug>.json` | `state.py run` and the job commands | the run state (mode, integration branch, `pace`, `base`, `final`); the progress mod reads it |
| `_runs/<plan-slug>-final.patch`, `-final-2.patch` | `state.py final-diff` | the whole run's change for the final review, and the fix alone for its recheck |
| `_runs/<plan-slug>-final.md`, `-final-2.md` | reviewer-final | the final review's verdict and findings, and the recheck of the fix |
| `<job-id>/job.json` | `state.py`, only it | the job's state; the views read it |
| `<job-id>/task.md` | `state.py begin-job` | the task brief, copied from the plan, with a link to the plan's spec |
| `<job-id>/build.md` | builder | what was built and the proof |
| `<job-id>/checks.json`, `checks/<n>.log` | `state.py verify` | every check run through the script, with its log |
| `<job-id>/rework-<k>.md` | you | a user's rework note, verbatim |
| `<job-id>/questions-<k>.md` | you | the pending questions from an agent, saved before asking |
| `<job-id>/answers-<k>.md` | you | the user's answers, saved only once given |
| `<job-id>/round-<N>/diff.patch` | `state.py route` | the change as the reviewers and the approver read it (`<job-id>/diff.patch` on the short path) |
| `<job-id>/round-<N>/review-<lens>.md` | reviewers | one verdict file per lens that was run in that round |
| `<job-id>/decision.md` | approver (or you, when rounds run out) | the final call |

`job.json` is written only by `state.py`: read fields such as `stage`, `round`, `tier`, `lean`, `lite`, `head`, `build_round` and
`reviews` from it, never edit it. A job id looks like `003-rate-limit`: a running three-digit counter, then a short slug drawn from the task title.

## Modes

Ask once per run, with the question tool, and record the answer in the run state. Recommend isolated.

**Isolated.** Per plan and repo: integration branch `factory/<plan-slug>` from the repo's main
branch, checked out in its own worktree `<repo-parent>/<repo-name>-factory/_integration-<plan-slug>`.
Per job: branch `factory/<plan-slug>--<job-id>` (not nested under the integration branch, which git refuses) and worktree `<repo-parent>/<repo-name>-factory/<job-id>`,
created from the integration branch. Run the repo's fresh-checkout setup in the worktree; if it fails, stop.
Tasks run in plan order. Run two tasks in parallel only when both declared `Depends` and a non-empty `Files`
(the parser lists what a task left out in `defaults_applied`; such a task is assumed to follow the one before it),
their `Files` do not overlap and their dependencies have landed. When a task goes `needs-human`, do not start
the tasks that depend on it, or any later task if it declared nothing; continue only with independent ones
and say so. The user's checkout is never touched.

**Current branch.** The user confirms the branch you name (warn explicitly when it is the default
branch). Require a clean working tree. Jobs run strictly in sequence, in the repo itself. The builder
does not commit; it lists its files and a one-line commit message in build.md. Reviewers and approver
look at `git diff HEAD` plus untracked files. On APPROVE you commit those paths with that message. On
failure or escalation you stop and leave the changes in the tree for the user.

## Landing

A task's steps are ticked in the commit that lands it, never later: a plan whose boxes lag reports finished work as open.
`state.py tick-plan --root <repo> --plan-file <plan> --task <n>` ticks that task and leaves the plan read-only; it never closes the plan.

Isolated: in the integration worktree run `git merge --no-ff --no-commit <job branch>`; on conflict `git merge --abort`, Needs human.
Then tick the task in the plan inside the integration worktree (pass that path as `--plan-file`), `git add` the plan and
`git commit -m "Merge <job-id>"`. Then remove the job worktree and delete the job branch. Current branch: tick the task, then commit
the paths from build.md and the plan with the message from build.md. An ad hoc task has no plan in the repo: skip the tick. Then
`state.py land <job> --stage merged|committed --head <sha>`, which also refreshes `done` in the run state.

## Reporting and progress

One short line per transition, e.g. `003-rate-limit: round 2, security CHANGES, code PASS, resuming builder`.
At the end of a job, say whether it landed or is waiting for a person, with the reason.
