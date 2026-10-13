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
| `_runs/<plan-slug>.json` | you | the mode chosen for the run, the integration branch, the plan path, the run `pace`, the task counts `total` and `done` (set at the start, `done` raised each time a job lands), and `tasks`, the planned tasks as `{ "n", "title", "tier", "after" }` written at the start (`after` lists the task numbers it waits for); the progress mod reads them |
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
  "agents": { "builder": { "model": "opus", "effort": "high" }, "code": { "model": "sonnet", "effort": "medium" } }, "stage": "review", "round": 2, "started": "2026-10-13T10:00:00Z", "updated": "2026-10-13T10:12:30Z", "reviewers": ["code", "security"],
  "reviews": { "code": "PASS", "security": "pending" } }
```

`agents` records, per role (`builder`, `code`, `security`, `ux`, `ui`, `approver`), the `model` and `effort` you passed when
you spawned that agent; write it right after each spawn. The progress mod shows who has the job and on which model.
`head` is the commit the job branch pointed at after the last build, and `build_round` the round that build was for; a
resume uses them. `started` and `updated` are ISO 8601 UTC timestamps: set `started` when the job is created and refresh `updated`
on every change (the progress mod shows elapsed time from them).
`stage` is `spec`, `build`, `waiting-input`, `review`, `approve`, `merged`, `committed` or `needs-human`. Replace
the file as a whole each time it changes. `reviews` holds the current round; earlier rounds stay in their folders.
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

## Run lock

One run at a time per plan, and the plan and its spec cannot be edited while it lasts. The run takes a lock at the start with
`python3 <plugin root>/scripts/state.py lock acquire --root <repo> --plan-file <plan> --run-id <id>`, where `<id>` is a fresh unique id you
remember for the whole run. The lock is the file `factory/jobs/_runs/<plan>.lock`; it records the run id, when it started, and a heartbeat that
every `state.py` change of a job refreshes. It also makes the plan file and the spec its header names (`**Spec:**`) read-only, and remembers their
original permissions.

- The command exits 3 when another run holds the plan, and prints who, since when and the last heartbeat. If that heartbeat is recent (30 minutes),
  tell the user the plan is being run by another session, that it must be stopped there first or released with `/factory-unlock`, and stop.
- If the other run is `stale` (no heartbeat for over 30 minutes: its session was closed or crashed), say so and ask with the question tool whether to
  take over; take over with `--force`, which keeps the original permissions.
- Release it with `state.py lock release --root <repo> --plan <plan-stem> --run-id <id>` when the run completes, when the user stops it, and when the
  run ends because a job needs a person in `auto` pace. A run that goes on after a decision in guided pace keeps the lock.
- The plan's steps are ticked at the end with `state.py tick-plan --root <repo> --plan-file <plan>`, which works on the read-only file and leaves it
  read-only. Never edit the plan or the spec yourself while the lock is held, and tell the builders not to.
- A command that acts on a job (`approve`, `rework`, `answer`) from a session that does not hold the lock, on a plan with a recent heartbeat, asks the
  user to confirm before acting, because the session that runs the plan may be acting on the same job.

## Preconditions (run)

1. The plan file exists. Parse it: `python3 <plugin root>/scripts/factory_plan.py <plan> --repo <name> --root <repo>`.
   If there are no tasks, point to the `factory-brainstorm` and `factory-plan` skills and stop.
2. Tell the user which defaults the parser applied (`defaults_applied`) and any `warnings`, in one line per task.
   Then look for work that may already be done: a task that has no job and carries `done_signals` (its planned commit
   is already in the git history, or every file it creates exists) may already be implemented, for instance a plan that
   was carried out by hand and never ticked. Before you start anything, say so and ask with the question tool: skip
   those tasks (and tick their steps), build them anyway, or stop. Never start such a task silently. Modifying a file
   that exists is not a signal, so ordinary tasks are not questioned.
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

Resuming: keep the worktree and branch, never recreate. If they are missing, or the branch no
longer points at the `head` in `job.json`, set `needs-human` and say why. `build` with a build.md for the recorded `build_round` and `STATUS: READY`: go straight to Route (step 3).
`build` without build.md: start a fresh
builder with the task and the commits already on the branch. Round partly done: keep finished
review files, rerun only the missing reviewers. `approve` without decision.md: rerun the approver.
A named builder does not survive its session; a resumed builder is a new agent that reads build.md,
the rounds and the branch log. In current-branch mode show leftover changes and ask whether to
continue from them, stash them or stop. Before continuing, say in one line per job what you found.

## Job loop

Do the bookkeeping with `python3 <plugin root>/scripts/state.py` instead of editing files by hand: it writes `job.json`, keeps the
phase log and the times, and does the checks. Every command takes `--root <repo>` and prints JSON.

Open every agent prompt with the job's coordinates (`<paths>` below): its folder `<repo>/factory/jobs/<job-id>/`, the
worktree path, the branch, the mode and the base.

When an agent finishes, the spawn result carries its usage (`subagent_tokens`, `tool_uses`, `duration_ms`). Record it at once:
`state.py agent <job-id> <role> --model <m> --effort <e> --tokens <n> --ms <n> --tools <n>` (roles `builder`, `code`, `security`,
`ux`, `ui`, `approver`; leave `--effort` empty when the host did not accept one). The progress views show who has the job, on which
model, and what it cost in time and tokens. The usage of your own session is not included: it is not reported to you.

0. **Once per run.** Take the run lock (see Run lock), then `state.py setup --plugin-root <plugin root>` (creates `factory/jobs/`, ignored by git, and copies the
   dashboard) and `state.py run --plan-file <plan> --mode <mode> --pace <pace>` (writes the run state: total, tasks, and `done`
   counted from the landed jobs).
1. **Create** the job. In isolated mode create the branch and worktree first, and only then write `job.json`:
   `state.py new-job --plan-file <plan> --task <n> --repo-name <name> --mode <mode> --branch <b> --worktree <w>` claims the next job
   id, writes `task.md` and `job.json` and prints the id, so a crash never leaves a job without its worktree. A job folder that has
   no `job.json` is an abandoned claim: start the task fresh.
2. **Build.** `state.py stage <job> build`. Spawn the `builder` with the model and effort of the task's tier in `<plugin root>/tiers.md`,
   prompt `<paths> Build round 1.` plus `Port: <5100+10n>` (n = job number), and name it `builder-<job-id>` where the host allows it.
   Some hosts' spawn tool takes the model but does not accept an effort or a name: pass what it accepts, and in `agents` record
   the model and leave `effort` empty, never one that was not applied. Keep the agent id the spawn returns; it replaces the name
   when you resume the builder (`SendMessage` to that id).
   The first line of build.md decides what happens next: `STATUS: READY` moves on, `STATUS: NEEDS_INPUT` goes to
   Questions from agents, `STATUS: BLOCKED` sends the job to step 8.
3. **Route.** `state.py route <job>` takes the changed paths (`git diff --name-only <base>...<branch>`; in current-branch mode
   `git diff --name-only HEAD` plus `git ls-files --others --exclude-standard`), applies the routing table (the repo's `factory/routing.md`
   if that file exists) and sets up the round: it writes `reviewers`, creates `round-N/` and sets the stage. It prints `reviewers` and `lite`.
   **Short path.** When it prints `lite: true` (tier `light`, at most 3 files and 30 lines, only the `code` lens) no reviewer is spawned
   and the job goes straight to approve: the approver reviews the diff itself, so tell it `Lite: yes` in its prompt.
4. **Review round N.** Spawn all selected reviewers in one message, with the settings from `tiers.md`, prompt `<paths> Review round N.`
   plus `Port: 5101+10n` for ux and `5102+10n` for ui. When they have finished, check the round in its own step: `state.py verdicts <job>`
   reads line one of every selected file (`PASS` or `CHANGES`), stores the verdicts in `job.json`, and exits 1 if a file or a verdict line
   is missing. A reviewer's chat reply is a claim, not a verdict: only its file counts. A reviewer that wrote no file gets one more time, with a reminder to write it; if it still has no verdict line, stop and tell the user. The builder stays untouched until the whole round is in.
5. **Decide.** `all_pass`: approve. Any CHANGES with resumes left (max 2 after round 1): `state.py stage <job> build`,
   resume the builder with `SendMessage` (or a fresh builder if the session lost it) saying the reviews are in `round-N/` and to
   answer every CHANGES; then check the first line of build.md as in step 2, run step 3 again (the diff may have grown) and start the
   next round. When the resumes are used up, you write `decision.md` yourself: first line `ESCALATE`, then a sentence naming
   the lenses that still ask for changes, and go to step 8.
6. **Approve.** Only after the check in step 4 passed (or in the short path), and never in the same message as that check (a failed
   check must not still start the approver), `state.py stage <job> approve` and spawn the `approver` with `<paths> Final round: N.`
   The approver's model is in `tiers.md` (`opus` when the job is risky, `sonnet` otherwise). Line one of decision.md routes it:
   `APPROVE` goes to step 7, `ESCALATE` to step 8.
7. **Land.** Isolated: in the integration worktree run `git merge --no-ff <job branch> -m "Merge <job-id>"`; on
   conflict `git merge --abort`, Needs human. Then remove the job worktree and delete the job branch. Current
   branch: commit the paths and message from build.md. Then `state.py land <job> --stage merged|committed --head <sha>`, which
   also refreshes `done` in the run state.
8. **Needs human.** `state.py stage <job> needs-human`; keep the branch and worktree; name the waiting job for the user, give its
   worktree path, and quote either decision.md or the reason given for BLOCKED.

## Pace

Recorded in the run state as `pace`: `step` (the default) or `auto`.

**Guided (`step`).** When a job ends, ask with the question tool what to do next, and do it without making the user
type another command.
- A job landed and tasks are left: continue with the next task (recommended), stop here, or
  run the rest without asking (sets `pace: auto`). After the last task, go to Completion.
- A job needs a person (`needs-human`): quote in two lines the question in the `## Handoff to the human` of its
  decision.md, or the BLOCKED reason, then offer: approve as it stands (Land), rework with a note (take the note as
  free text), skip this task and go on, or stop. Apply the answer and continue the loop. In current-branch mode
  skip is not offered: the changes are in the tree and the next task must not start on top of them. In isolated mode a skipped job
  stays `needs-human`, and the tasks that depend on it are not started.
- An agent asked a question: handle it in place, as in Questions from agents.

**Auto.** No question between tasks. A job that needs a person stops the run: list the waiting jobs, each with the
ready command (`/factory-approve <id>`, `/factory-rework <id> <note>`, `/factory-answer <id>`), and stop.

A prompt that is dismissed counts as stop and leaves every job as it is. Running `factory-run` again starts guided again.

## Resolving arguments

A command may get a short token or nothing. Resolve a job with
`python3 <plugin root>/scripts/resolve.py job "<token>" --stages <stages> --root <repo>`: the stages are `needs-human`
for approve and rework, `waiting-input` for answer. A `match` is the job. `candidates` mean you ask which one with the
question tool, listing each as its id and stage. With no match, say the `reason` and list what is eligible. A token can be
nothing (the only eligible job), the full id, `002`, a task number, or a fragment of the id.

For `factory-run` without a plan, run `python3 <plugin root>/scripts/resolve.py plans --root <repo>`: one plan with open
steps is the plan; several, ask with the question tool, each as its path and open over total tasks; none, point to
`factory-brainstorm` and `factory-plan`.

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

When every task is landed, tick the steps of each completed task with `state.py tick-plan` (see Run lock) and commit that on
the branch the jobs landed on: in current-branch mode in the repo (message "Mark the plan steps done"), in isolated mode in the integration
worktree (pass the plan's path inside that worktree as `--plan-file`). Then release the lock. Isolated mode then ends
with the finish step: ask the user, with the question tool, how the integration branch reaches the repo's
main branch: merge it, prepare a pull request without pushing, keep the branch, or discard it. Do only the
chosen local action. Current-branch mode has nothing to merge.

## The other commands

- **approve `<job-id>`**: only valid on a job in `needs-human`. Isolated: check the integration worktree is clean, then
  Land. Current branch: Land (commit).
- **rework `<job-id>` `<note>`**: only valid on a job in `needs-human`. Write the note verbatim to `rework-<k>.md`
  (next unused k), set `stage: "build"`, spawn a fresh `builder-<job-id>` told to read that file and update
  build.md; a rework gets a fresh budget of 2 resumes. Continue from the check of build.md in step 2 of the Job loop.
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
