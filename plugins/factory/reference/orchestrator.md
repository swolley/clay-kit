# Orchestrator reference

Shared by the `factory-run`, `factory-task`, `factory-status`, `factory-approve`, `factory-rework` and `factory-answer` skills. The skill that sent you
here states `<plugin root>`. Follow `<plugin root>/STYLE.md`. This file is read as plain text:
the plugin-root variable is not substituted in it.

You are the orchestrator of the jobs you start. You spawn the agents, you decide, you write
`job.json` and nothing else of the job's content. Never write code, tasks' specs, reviews or
decisions yourself. Never push. Never reset or discard a user's changes.

## Files

`<repo>` means the root of the target repository's own checkout. Everything the factory records at
runtime sits under `<repo>/factory/jobs/`, which git never tracks:

| Path under `factory/jobs/` | Written by | Holds |
|---|---|---|
| `_runs/<plan-slug>.json` | you | the mode chosen for the run, the integration branch, the plan path, and the task counts `total` and `done` (set at the start, `done` raised each time a job lands); the progress band reads them |
| `<job-id>/job.json` | you, only you | the job's state; the dashboard reads it |
| `<job-id>/task.md` | you | the task brief, copied from the plan |
| `<job-id>/build.md` | builder | what was built and the proof |
| `<job-id>/rework-<k>.md` | you | a user's rework note, verbatim |
| `<job-id>/questions-<k>.md` | you | the pending questions from an agent, saved before asking |
| `<job-id>/answers-<k>.md` | you | the user's answers, saved only once given |
| `<job-id>/round-<N>/review-<lens>.md` | reviewers | one verdict file per selected lens |
| `<job-id>/decision.md` | approver (or you, when rounds run out) | the final call |

A job id looks like `003-rate-limit`: a running three-digit counter, then a short hyphenated slug drawn from
the task title. Reserve the id by creating its folder with plain `mkdir` (no `-p`); if that fails, a parallel
session got there first, so try the next counter value. `job.json`:

```json
{ "id": "003-rate-limit", "plan": "2026-10-13-x", "task": 3, "repo": "api", "mode": "isolated",
  "tier": "careful", "branch": "factory/x/003-rate-limit", "worktree": "/abs/path",
  "stage": "review", "round": 2, "reviewers": ["code", "security"],
  "reviews": { "code": "PASS", "security": "pending" } }
```

`stage` is `spec`, `build`, `waiting-input`, `review`, `approve`, `merged`, `committed` or `needs-human`. Replace
the file as a whole each time it changes. `reviews` holds the current round; earlier rounds stay in their folders.
Before the first job, create `factory/jobs/` with a `factory/jobs/.gitignore` containing `*` (it ignores itself, so
job state never dirties the repo) and copy `<plugin root>/factory/dashboard.html` to `factory/jobs/dashboard.html`.
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

## Preconditions (run)

1. The plan file exists. Parse it: `python3 <plugin root>/scripts/factory_plan.py <plan> --repo <name>`.
   If there are no tasks, point to the `factory-brainstorm` and `factory-plan` skills and stop.
2. Tell the user which defaults the parser applied (`defaults_applied`), in one line per task.
3. The target repo is a git repo. Isolated mode needs a clean main checkout only for the final merge.
4. Resume (below), then mode choice, then start.

## Resume

`run` is idempotent. Read the plan and `factory/jobs/`, then classify each task:

| State | Found | Action |
|-------|-------|--------|
| done | all non-cancelled steps checked | skip |
| landed, not ticked | stage `merged` or `committed` | tick its steps, skip |
| interrupted | stage `spec`, `build`, `review` or `approve` | resume from that stage |
| needs-human | stage `needs-human` | do not touch; list it |
| waiting-input | stage `waiting-input` | read the pending `questions-<k>.md` and ask again; see Questions from agents |
| not started | no job | start |

Resuming: keep the worktree and branch, never recreate. If they are missing or the branch no
longer matches `job.json`, set `needs-human` and say why. `build` without build.md: start a fresh
builder with the task and the commits already on the branch. Round partly done: keep finished
review files, rerun only the missing reviewers. `approve` without decision.md: rerun the approver.
A named builder does not survive its session; a resumed builder is a new agent that reads build.md,
the rounds and the branch log. In current-branch mode show leftover changes and ask whether to
continue from them, stash them or stop. Before continuing, say in one line per job what you found.

## Job loop

Open every agent prompt with the job's coordinates (`<paths>` below): its folder `<repo>/factory/jobs/<job-id>/`, the
worktree path, the branch, the mode and the base.

1. **Create** the job: folder, `task.md`, `job.json` (`stage: "spec"`, round 0, reviewers `[]`), then in isolated
   mode the branch and worktree.
2. **Build.** `stage: "build"`. Spawn the `builder` under the name `builder-<job-id>` with model and effort from the task's
   tier in `<plugin root>/tiers.md`, prompt `<paths> Build round 1.` plus `Port: <5100+10n>` (n = job number).
   The first line of build.md decides what happens next: `STATUS: READY` moves on, `STATUS: NEEDS_INPUT` goes to
   Questions from agents, `STATUS: BLOCKED` sends the job to step 8.
3. **Route.** Take the changed paths (`git diff --name-only <base>...<branch>`; in current-branch
   mode `git diff --name-only HEAD` plus `git ls-files --others --exclude-standard`), pipe them to `python3 <plugin root>/scripts/route.py` (add `--table <repo>/factory/routing.md`
   if that file exists). Write the result to `reviewers` in `job.json`.
4. **Review round N.** `stage: "review"`, `round: N`, selected reviews `pending`, create `round-N/`. Spawn all
   selected reviewers in one message, with the fixed settings from `tiers.md`, prompt `<paths> Review round N.`
   plus `Port: 5101+10n` for ux and `5102+10n` for ui. As each reviewer finishes, take the verdict from line one of its file (`PASS` or `CHANGES`) and store it in
   `job.json` straight away. The round ends only when every selected
   file exists. A reviewer that finishes without a verdict line: stop and tell the user. The builder stays
   untouched until the whole round is in.
5. **Decide.** All PASS: approve. Any CHANGES with resumes left (max 2 after round 1): `stage: "build"`,
   resume `builder-<job-id>` with `SendMessage` (or a fresh builder if the session lost it) saying the
   reviews are in `round-N/` and to answer every CHANGES; then Build check, re-route (the diff may have grown),
   next round. When the resumes are used up, you write `decision.md` yourself: first line `ESCALATE`, then a sentence naming
   the lenses that still ask for changes, and go to step 8.
6. **Approve.** `stage: "approve"`. Spawn `approver` (fixed settings) with `<paths> Final round: N.` Line one
   of decision.md routes it: `APPROVE` goes to step 7, `ESCALATE` to step 8.
7. **Land.** Isolated: in the integration worktree run `git merge --no-ff <job branch> -m "Merge <job-id>"`; on
   conflict `git merge --abort`, Needs human. Then remove the job worktree and delete the job branch. Current
   branch: commit the paths and message from build.md. Set `merged` or `committed`.
8. **Needs human.** `stage: "needs-human"`; keep the branch and worktree; name the waiting job for the user, give its worktree path, and quote either decision.md or the
   reason given for BLOCKED.

## Questions from agents

The source of truth is a file, never the prompt. A subagent cannot ask the user; it ends with
`STATUS: NEEDS_INPUT` and numbered questions in build.md.

1. Copy the questions to `questions-<k>.md` (next unused `k`) and set `stage: "waiting-input"` before asking anything.
2. Ask the user with the question tool, batching the job's questions, each option labeled and the agent's
   recommended answer first. Write the answers to `answers-<k>.md` only when the user has actually given them.
3. Anything that is not an answer leaves the job waiting: a dismissed prompt, a timeout or auto-continue, or an
   unrelated message from the user. Handle an unrelated message normally, never apply a default or the
   recommended answer, and do not touch the job. Keep working on the other, independent jobs.
4. When answers exist, set `stage: "build"` and start a fresh builder (named `builder-<job-id>`) that is told to
   read `answers-<k>.md` and update build.md. This does not use up the review resumes.
5. If the user says they do not know, set `needs-human` and quote the open questions.

Say it plainly when a job is waiting: `003-rate-limit: waiting for you, 2 questions (use /factory-answer 003-rate-limit)`.
At the end of a run, and in `status`, list every job that is waiting for you.

## Completion

When every task is landed, tick the steps of each completed task in the plan file. Isolated mode then ends
with the finish step: ask the user, with the question tool, how the integration branch reaches the repo's
main branch: merge it, prepare a pull request without pushing, keep the branch, or discard it. Do only the
chosen local action. Current-branch mode has nothing to merge.

## The other commands

- **approve `<job-id>`**: only valid on a job in `needs-human`. Isolated: check the integration worktree is clean, then
  Land. Current branch: Land (commit).
- **rework `<job-id>` `<note>`**: only valid on a job in `needs-human`. Write the note verbatim to `rework-<k>.md`
  (next unused k), set `stage: "build"`, spawn a fresh `builder-<job-id>` told to read that file and update
  build.md; a rework gets a fresh budget of 2 resumes. Continue from Build check.
- **answer `<job-id>` `[text]`**: only valid on a job in `waiting-input`. Without text, ask the pending questions again
  from the file. With text, treat it as the answers, check it covers every question (ask again for what is missing), save
  it to `answers-<k>.md` and continue from step 4 of Questions from agents.
- **status**: list jobs from `job.json` files: id, plan, stage, round, reviewers with verdicts; say which
  wait for the user. Read-only.
- **task `<text>`**: build a one-task plan in memory (title from the text, tier medium, one `Accept`
  criterion taken from the text) and run it through the Job loop and Completion with plan name `adhoc`.

## Reporting and progress

One short line per transition, e.g. `003-rate-limit: round 2, security CHANGES, code PASS, resuming builder`.
At the end of a job, say whether it landed or is waiting for a person, with the reason.

If the tools `mcp__savvy-progress__progress` and `mcp__savvy-progress__step` exist, report the plan, the
phase and accepted tasks to them, using each task title as the Agent `description`. Skip silently if absent.
