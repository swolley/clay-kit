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
   Look for work that may already be done: a task that has no job and carries `done_signals` (its planned commit
   is already in the git history, or every file it creates exists) may already be implemented, for instance a plan that
   was carried out by hand and never ticked. Before you start anything, say so and ask with the question tool: skip
   those tasks (and tick their steps), build them anyway, or stop. Never start such a task silently. Modifying a file
   that exists is not a signal, so ordinary tasks are not questioned.
   Only after that decision, ask once if needed: the question is skipped when no task that will actually run has tier `fable`
   (a fable task skipped as already-done is not asked about). Otherwise ask once with the question tool, listing those tasks, with these options:
   `opus` with `xhigh` (recommended) runs them as tier `heavy` (builder opus, effort xhigh, approver opus); `fable` as the plan says
   spawns the builder with model fable and effort high (if the host does not accept fable, `tiers.md` falls back to opus xhigh);
   lower to `careful` runs them as tier `careful` (opus, high; the approver follows the normal risk rule). In every case the models
   recorded in `agents` are the ones actually passed, and the plan file is never edited. The answer holds for the whole run and is
   asked again on a resumed run. `factory-task` with an explicit `tier=fable` is not asked again, the user chose it.
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

`factory-task [tier=<name>] <text>`: run `state.py adhoc --root <repo> --text "<text>"`. It writes a one-task plan to
`factory/jobs/_runs/adhoc-<YYYYMMDD-HHMMSS>-<slug>.md` (title from the first words of the text, tier `medium` unless a leading `tier=<name>` says
`light`, `medium`, `careful`, `heavy` or `fable`, one `Accept` criterion taken from the text) and prints `plan_file`, `plan_stem`, `title` and `tier`; an
unknown tier or an empty text exits 2. The file is local and git ignores it, so it never reaches the repo's plans folder. Use `plan_file` as the plan path
for `run`, `lock`, `new-job` and `begin-job`, and run it through the Job loop and Completion. Completion skips `tick-plan` and the plan commit (there is nothing in the
repo to tick), then releases the lock and runs `clean`, which also deletes the working plan.
