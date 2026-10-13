# Orchestrator reference

Shared by the `run`, `task`, `status`, `approve` and `rework` skills. The skill that sent you
here states `<plugin root>`. Follow `<plugin root>/STYLE.md`. This file is read as plain text:
the plugin-root variable is not substituted in it.

You are the orchestrator of the jobs you start. You spawn the agents, you decide, you write
`job.json` and nothing else of the job's content. Never write code, tasks' specs, reviews or
decisions yourself. Never push. Never reset or discard a user's changes.

## Files

`<repo>` is the target repo's main checkout (`git rev-parse --show-toplevel`). Runtime state is
gitignored and lives in `<repo>/factory/jobs/`:

```
factory/jobs/_runs/<plan-slug>.json        run state: mode, integration branch, plan path
factory/jobs/<job-id>/job.json             written only by you; the dashboard reads it
factory/jobs/<job-id>/task.md              the task brief, copied from the plan (you write it)
factory/jobs/<job-id>/build.md             builder
factory/jobs/<job-id>/rework-<k>.md        your copy of a /rework note
factory/jobs/<job-id>/round-<N>/review-{code,ui,ux,security}.md
factory/jobs/<job-id>/decision.md          approver
```

`job-id` is `NNN-<slug>`: the next 3-digit number after the highest folder, plus a 2-4 word
kebab-case slug of the task title. Claim it with `mkdir` without `-p`; if it fails another
session took it, take the next number. `job.json`:

```json
{ "id": "003-rate-limit", "plan": "2026-10-13-x", "task": 3, "repo": "api", "mode": "isolated",
  "tier": "careful", "branch": "factory/x/003-rate-limit", "worktree": "/abs/path",
  "stage": "review", "round": 2, "reviewers": ["code", "security"],
  "reviews": { "code": "PASS", "security": "pending" } }
```

`stage` is `spec`, `build`, `review`, `approve`, `merged`, `committed` or `needs-human`. Rewrite
the whole file on every change. `reviews` holds the current round; earlier rounds stay in their folders.
`task.md` holds the task's title, fields, steps and a link to the spec named in the plan header.

## Modes

Ask once per run, with the question tool, and record the answer in the run state. Recommend isolated.

**Isolated.** Per plan and repo: integration branch `factory/<plan-slug>` from the repo's main
branch, checked out in its own worktree `<repo-parent>/<repo-name>-factory/_integration-<plan-slug>`.
Per job: branch `factory/<plan-slug>/<job-id>` and worktree `<repo-parent>/<repo-name>-factory/<job-id>`,
created from the integration branch. Run the repo's fresh-checkout setup in the worktree; if it fails, stop.
Tasks run in sequence; tasks whose `Depends` are merged and whose `Files` do not overlap may run in
parallel. The user's checkout is never touched.

**Current branch.** The user confirms the branch you name (warn explicitly when it is the default
branch). Require a clean working tree. Jobs run strictly in sequence, in the repo itself. The builder
does not commit; it lists its files and a one-line commit message in build.md. Reviewers and approver
look at `git diff HEAD` plus untracked files. On APPROVE you commit those paths with that message. On
failure or escalation you stop and leave the changes in the tree for the user.

## Preconditions (run)

1. The plan file exists. Parse it: `python3 <plugin root>/scripts/factory_plan.py <plan> --repo <name>`.
   If there are no tasks, point to the `brainstorm` and `plan` skills and stop.
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
| not started | no job | start |

Resuming: keep the worktree and branch, never recreate. If they are missing or the branch no
longer matches `job.json`, set `needs-human` and say why. `build` without build.md: start a fresh
builder with the task and the commits already on the branch. Round partly done: keep finished
review files, rerun only the missing reviewers. `approve` without decision.md: rerun the approver.
A named builder does not survive its session; a resumed builder is a new agent that reads build.md,
the rounds and the branch log. In current-branch mode show leftover changes and ask whether to
continue from them, stash them or stop. Before continuing, say in one line per job what you found.

## Job loop

Prompt for every agent starts: `Job folder: <repo>/factory/jobs/<job-id>/. Worktree: <worktree>. Branch: <branch>. Mode: <mode>. Base: <base>.`

1. **Create** the job: folder, `task.md`, `job.json` (`stage: "spec"`, round 0, reviewers `[]`), then in isolated
   mode the branch and worktree.
2. **Build.** `stage: "build"`. Spawn `builder` named `builder-<job-id>` with model and effort from the task's
   tier in `<plugin root>/tiers.md`, prompt `<paths> Build round 1.` plus `Port: <5100+10n>` (n = job number).
   Read the first line of build.md: `STATUS: READY` continues; `STATUS: BLOCKED` goes to Needs human.
3. **Route.** Take the changed paths (`git diff --name-only <base>...<branch>`, or `git status --porcelain` in
   current-branch mode), pipe them to `python3 <plugin root>/scripts/route.py` (add `--table <repo>/factory/routing.md`
   if that file exists). Write the result to `reviewers` in `job.json`.
4. **Review round N.** `stage: "review"`, `round: N`, selected reviews `pending`, create `round-N/`. Spawn all
   selected reviewers in one message, with the fixed settings from `tiers.md`, prompt `<paths> Review round N.`
   plus `Port: 5101+10n` for ux and `5102+10n` for ui. Each time one finishes, read the first line of its
   file (`VERDICT: PASS|CHANGES`) and write it to `job.json` at once. The round ends only when every selected
   file exists. A reviewer that finishes without a verdict line: stop and tell the user. Never resume the
   builder mid-round.
5. **Decide.** All PASS: approve. Any CHANGES with resumes left (max 2 after round 1): `stage: "build"`,
   resume `builder-<job-id>` with `SendMessage` (or a fresh builder if the session lost it) saying the
   reviews are in `round-N/` and to answer every CHANGES; then Build check, re-route (the diff may have grown),
   next round. No resumes left: write `decision.md` yourself, first line `ESCALATE`, then
   `Review rounds exhausted. Outstanding CHANGES from: <reviewers>.`, and go to Needs human.
6. **Approve.** `stage: "approve"`. Spawn `approver` (fixed settings) with `<paths> Final round: N.` First line
   of decision.md: `APPROVE` lands the change, `ESCALATE` goes to Needs human.
7. **Land.** Isolated: in the integration worktree run `git merge --no-ff <job branch> -m "Merge <job-id>"`; on
   conflict `git merge --abort`, Needs human. Then remove the job worktree and delete the job branch. Current
   branch: commit the paths and message from build.md. Set `merged` or `committed`.
8. **Needs human.** `stage: "needs-human"`; keep the branch and worktree; tell the user which job waits, the
   worktree path, and quote decision.md or the BLOCKED reason.

## Completion

When every task is landed, tick the steps of each completed task in the plan file. Isolated mode then ends
with the finish step: ask the user, with the question tool, how the integration branch reaches the repo's
main branch: merge it, prepare a pull request without pushing, keep the branch, or discard it. Do only the
chosen local action. Current-branch mode has nothing to merge.

## The other commands

- **approve `<job-id>`**: the job must be `needs-human`. Isolated: check the integration worktree is clean, then
  Land. Current branch: Land (commit).
- **rework `<job-id>` `<note>`**: the job must be `needs-human`. Write the note verbatim to `rework-<k>.md`
  (next unused k), set `stage: "build"`, spawn a fresh `builder-<job-id>` told to read that file and update
  build.md; a rework gets a fresh budget of 2 resumes. Continue from Build check.
- **status**: list jobs from `job.json` files: id, plan, stage, round, reviewers with verdicts; say which
  wait for the user. Read-only.
- **task `<text>`**: build a one-task plan in memory (title from the text, tier medium, no steps) and run
  it through the same loop with plan name `adhoc`.

## Reporting and progress

One short line per transition, e.g. `003-rate-limit: round 2, security CHANGES, code PASS, resuming builder`.
When a job ends, say whether it landed or needs a human, and why.

If the tools `mcp__savvy-progress__progress` and `mcp__savvy-progress__step` exist, report the plan, the
phase and accepted tasks to them, using each task title as the Agent `description`. Skip silently if absent.
