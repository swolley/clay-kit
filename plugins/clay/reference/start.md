# Starting a run

Part of the orchestrator reference (see `orchestrator.md`). `<plugin root>` is the path your skill states. Follow `<plugin root>/STYLE.md`. `<repo>` is the root of the target repository's own checkout.

## Resolving a plan

For `factory-run` without a plan, run `python3 <plugin root>/scripts/state.py preflight --root <repo>` (it lists `plans`, the plans with open steps, and `unclassified`;
`resolve.py plans` is the script behind it): one plan with open steps is the plan; none, point to `factory-brainstorm` and `factory-plan`. Several: the question tool shows at most 4
options, so list the 4 most recent (by the date in the file name) as path and open over total tasks, say how many more
there are, and accept a fragment of a name typed by the user (match it the same way as a job token).

A plan's declared `status:` (completed, done, shipped, superseded) closes it whatever its checkboxes say (the convention of
plan tools that keep a front matter status); a task with no steps is not runnable. Two more checks guard the lists, both part of the preflight:
`unclassified` lists plans with no steps and no declared status (never offered to run; tell the user how
many there are), and `audit` is the second check (`resolve.py plans --unclassified` and `--audit` print them alone): a plan declared closed whose planned commits and created
files are not in the repo, or an open plan whose tasks all show them. The preflight with a plan returns the audit for that plan only: if it names
that plan, tell the user in one line and ask before running.

Before choosing what to work on, see what is already open: run `python3 <plugin root>/scripts/plan_status.py` from the repository
(the user's `/factory-backlog` does the same). It lists plans with steps left and specs that have no plan, so you do not start
work that exists, or plan work that is already planned. It only reads; never edit a plan or spec because of its output.

## Preconditions (run)

1. The plan file exists. One call gathers what the start needs: `python3 <plugin root>/scripts/state.py preflight --root <repo> --plan-file <plan> --repo-name <name>`.
   It returns `plan` (the plan parsed, as `factory_plan.py <plan> --repo <name> --root <repo>` prints it), `jobs` (the jobs the plan already has, for Resume), `audit` (what
   the audit says about this plan) and `unclassified`. If there are no tasks, point to the `factory-brainstorm` and `factory-plan` skills and stop.
2. Tell the user which defaults the parser applied (`defaults_applied`) and any `warnings`, in one line per task.
   Then look for work that may already be done: a task that has no job and carries `done_signals` (its planned commit
   is already in the git history, or every file it creates exists) may already be implemented, for instance a plan that
   was carried out by hand and never ticked. Before you start anything, say so and ask with the question tool: skip
   those tasks (and tick their steps), build them anyway, or stop. Never start such a task silently. Modifying a file
   that exists is not a signal, so ordinary tasks are not questioned.
3. The target repo is a git repo. Isolated mode needs a clean main checkout only for the final merge.
4. Resume (below), then mode choice, then start.

## Resume

`run` is idempotent. Take the plan and the `jobs` from the preflight, then classify each task:

| State | Found | Action |
|-------|-------|--------|
| done | all non-cancelled steps checked | skip |
| landed, not ticked | stage `merged` or `committed` | tick its steps, skip |
| interrupted | stage `spec`, `build`, `review` or `approve` | resume from that stage |
| needs-human | stage `needs-human` | do not touch; list it |
| waiting-input | stage `waiting-input` | read the pending `questions-<k>.md` and ask again; see `questions.md` |
| not started | no job | start |

Resuming: keep the worktree and branch, never recreate. If they are missing, or the branch no
longer points at the `head` in `job.json`, set `needs-human` and say why. `build` with a build.md for the recorded `build_round` and `STATUS: READY`: go straight to Route (step 3).
`build` without build.md: start a fresh
builder with the task and the commits already on the branch. Round partly done: keep finished
review files, rerun only the missing reviewers. `approve` without decision.md: rerun the approver.
A named builder does not survive its session; a resumed builder is a new agent that reads build.md,
the rounds and the branch log. In current-branch mode show leftover changes and ask whether to
continue from them, stash them or stop. Before continuing, say in one line per job what you found.

## Ad hoc task

`factory-task <text>`: build a one-task plan in memory (title from the text, tier medium, one `Accept`
criterion taken from the text) and run it through the Job loop and Completion with plan name `adhoc`.
