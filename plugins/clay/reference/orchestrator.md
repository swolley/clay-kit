# Orchestrator reference

Shared by the `factory-*` command skills, split in parts so a command reads only what it needs. The skill that sent you here states `<plugin root>` and
lists the parts it needs: read them together, in one message. Follow `<plugin root>/STYLE.md`. These files are read as plain text:
the plugin-root variable is not substituted in them. How to start, resume and ask on each host, and "the question tool", are in `hosts.md`.

You are the orchestrator of the jobs you start. You spawn the agents, you decide, you write
`job.json` and nothing else of the job's content. Never write code, tasks' specs, reviews or
decisions yourself. Never push. Never reset or discard a user's changes.

| Part | Holds | Read by |
|---|---|---|
| `orchestrator.md` | the rules, the files, the modes, landing, reporting | every command except `factory-unlock` |
| `hosts.md` | starting an agent, its model and effort, resuming it, asking the user, per host | every command that spawns or asks: run, task, approve, rework, answer, unlock |
| `lock.md` | the run lock | run, task, approve, rework, answer, unlock |
| `start.md` | resolving a plan, preconditions, resume, the ad hoc task | run, task |
| `job-loop.md` | the job loop and the pace | run, task, rework, answer |
| `commands.md` | resolving a job, approve, rework, answer, status | approve, rework, answer, status |
| `questions.md` | questions from agents | answer; run, task and rework when an agent asks something |
| `inline.md` | building in the session | run, task, only with `inline` |
| `completion.md` | closing a finished plan | run, task, once every task has landed |

## Files

`<repo>` means the root of the target repository's own checkout. Everything the factory records at
runtime sits under `<repo>/factory/jobs/`, which git never tracks:

| Path under `factory/jobs/` | Written by | Holds |
|---|---|---|
| `_runs/<plan-slug>.json` | you | the mode chosen for the run, the integration branch, the plan path, the run `pace`, the task counts `total` and `done` (set at the start, `done` raised each time a job lands), and `tasks`, the planned tasks as `{ "n", "title", "tier", "after" }` written at the start (`after` lists the task numbers it waits for); the progress mod reads them |
| `<job-id>/job.json` | you, only you | the job's state; the dashboard reads it |
| `<job-id>/task.md` | you | the task brief, copied from the plan |
| `<job-id>/build.md` | builder | what was built and the proof |
| `<job-id>/checks.json`, `checks/<n>.log` | `state.py verify` | every check run through the script: command, exit code, the tree state it ran against, the log |
| `<job-id>/rework-<k>.md` | you | a user's rework note, verbatim |
| `<job-id>/questions-<k>.md` | you | the pending questions from an agent, saved before asking |
| `<job-id>/answers-<k>.md` | you | the user's answers, saved only once given |
| `<job-id>/round-<N>/diff.patch` | `state.py route` | the change as the reviewers and the approver read it: commits, file list, what changed since the previous round, diff (a short-path job has it as `<job-id>/diff.patch`) |
| `<job-id>/round-<N>/review-<lens>.md` | reviewers | one verdict file per lens that was run in that round |
| `<job-id>/decision.md` | approver (or you, when rounds run out) | the final call |

A job id looks like `003-rate-limit`: a running three-digit counter, then a short hyphenated slug drawn from
the task title. Reserve the id by creating its folder with plain `mkdir` (no `-p`); if that fails, a parallel
session got there first, so try the next counter value. `job.json`:

```json
{ "id": "003-rate-limit", "plan": "2026-10-13-x", "task": 3, "repo": "api", "mode": "isolated",
  "tier": "careful", "branch": "factory/x/003-rate-limit", "worktree": "/abs/path",
  "agents": { "builder": { "model": "opus", "effort": "high" }, "code": { "model": "sonnet", "effort": "medium" } }, "stage": "review", "round": 2, "started": "2026-10-13T10:00:00Z", "updated": "2026-10-13T10:12:30Z", "reviewers": ["code", "security"],
  "reviews": { "code": "PASS", "security": "pending" } }
```

`agents` records, per role (`builder`, `code`, `security`, `ux`, `ui`, `uiux`, `approver`), the `model` and `effort` you passed when
you spawned that agent, as the recording rule in `hosts.md` says; write it right after each spawn. The progress mod shows who has the job and on which model.
`head` is the commit the job branch pointed at after the last build, and `build_round` the round that build was for; a
resume uses them. `started` and `updated` are ISO 8601 UTC timestamps: set `started` when the job is created and refresh `updated`
on every change (the progress mod shows elapsed time from them).
`stage` is `spec`, `build`, `waiting-input`, `review`, `approve`, `merged`, `committed` or `needs-human`. Replace
the file as a whole each time it changes. `reviews` holds the current round; earlier rounds stay in their folders. `reviewers` is every lens of the round, `rerun` the ones that are run in it and
`carried` the ones that keep a passing verdict from an earlier round (lens to the round it was given in); `fingerprints` is what `route` compares the next round against.
`state.py setup` (step 0 of the Job loop) creates `factory/jobs/` with a `factory/jobs/.gitignore` containing `*` (it ignores itself, so job
state never dirties the repo) and copies `<plugin root>/factory/dashboard.html` to `factory/jobs/dashboard.html` at the start of every
run, so the page is never older than the plugin. `agents` also keeps `tokens`, `ms`, `tools` and `runs` per role, and `phases` a log of
the stages with their start and end, which is what the views show.
The user serves that folder with `cd factory/jobs && python3 -m http.server` and opens `/dashboard.html`.
`task.md` holds the task's title, fields, steps and a link to the spec named in the plan header.

## Modes

Ask once per run, with the question tool, and record the answer in the run state. Recommend isolated.

**Isolated.** Per plan and repo: integration branch `factory/<plan-slug>` from the repo's main
branch, checked out in its own worktree `<repo-parent>/<repo-name>-factory/_integration-<plan-slug>`.
Per job: branch `factory/<plan-slug>/<job-id>` and worktree `<repo-parent>/<repo-name>-factory/<job-id>`,
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

If the tools `mcp__savvy-progress__progress` and `mcp__savvy-progress__step` exist, report the plan, the
phase and accepted tasks to them, using each task title as the Agent `description`. Skip silently if absent.
