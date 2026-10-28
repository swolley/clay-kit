# Starting a run

## Resolving a plan

For `factory-run` without a plan, run `python3 <plugin root>/scripts/state.py preflight --root <repo>` (it lists `plans`, the plans with open steps, and `unclassified`;
`resolve.py plans` is the script behind it): one plan with open steps is the plan; none, point to `factory-brainstorm` and `factory-plan`. Several: list up to 4 plans, the most
recent (by the date in the file name), which on Codex goes to the plain-text form (`hosts.md`), as path and open over total tasks, say how many more
there are, and accept a fragment of a name typed by the user (match it the same way as a job token).
Plans are found where `plan_status.py` finds them, subfolders and nested repositories included. Each one carries `root`, the
checkout it belongs to relative to `<repo>`, and `path`, the plan relative to that checkout: when `root` is not empty, show the plan as
`<root>/<path>` and, once it is chosen, `<repo>/<root>` is `<repo>` for the rest of the run.

A plan whose front matter declares it closed is never offered, and a task with no steps is not runnable. `unclassified` lists
plans with no steps and no declared status: they are never offered to run; tell the user how many there are. The preflight with a
plan returns its `audit` (a plan declared closed whose work is not in the repo, or an open plan whose work all is): if it names that
plan, tell the user in one line and ask before running.

## Preconditions (run)

1. The plan file exists. One call gathers what the start needs: `python3 <plugin root>/scripts/state.py preflight --root <repo> --plan-file <plan> --repo-name <name> --host <host>`.
   It returns `plan` (as `factory_plan.py <plan> --repo <name> --root <repo>` prints it), `jobs` (for Resume), `audit`, `unclassified`, `peer` and `git_identity`. If there are no tasks, point to the `factory-brainstorm` and `factory-plan` skills and stop.
   If `git_identity.ok` is false, give its `reason` and stop: no job could commit.
2. Tell the user which defaults the parser applied (`defaults_applied`) and any `warnings`, in one line per task.
   Look for work that may already be done: a task that has no job and carries `done_signals` (its planned commit
   is already in the git history, or every file it creates exists) may already be implemented, for instance a plan that
   was carried out by hand and never ticked. Before you start anything, say so and ask with the question tool: skip
   those tasks (and tick their steps), build them anyway, or stop. Never start such a task silently. Modifying a file
   that exists is not a signal, so ordinary tasks are not questioned.
   Only after that decision, ask once if needed: the question is skipped when no task that will actually run has tier `fable`
   (a fable task skipped as already-done is not asked about). Otherwise ask once with the question tool, on every host (it is about cost), listing those tasks, with these options:
   `heavy` (recommended) runs them as tier `heavy` (approver on its risky model); `fable` as the plan says runs them as tier `fable`;
   lower to `careful` runs them as tier `careful` (the approver follows the normal risk rule). Label each option with the builder's
   model and effort that `state.py model --host <host> --tier <tier>` prints for it (a null model is the session's). In every case the models
   recorded in `agents` are the ones actually passed, and the plan file is never edited. The answer holds for the whole run and is
   asked again on a resumed run. `factory-task` with an explicit `tier=fable` is not asked again, the user chose it.
3. Lean: `preflight` also gives each task `lean` and `lean_reason`, and `lean_count` and `long`; with `lean_count` above 0 the
   mode question adds the lean choice and the start message the note on the session's model (`lean.md`).
4. The target repo is a git repo. Isolated mode needs a clean main checkout only for the final merge.
5. Resume (below), then mode choice, then start. When `peer.found`, the mode question adds "work with <peer>: yes (recommended) / no", asked again on a resumed run;
   `state.py run` gets `--cross on|off --host <host>`, and with yes read `peer.md`.

## Resume

`run` is idempotent. Take the plan and the `jobs` from the preflight, then classify each task:

| State | Found | Action |
|-------|-------|--------|
| done | all non-cancelled steps checked | skip |
| landed, not ticked | stage `merged` or `committed` | tick its steps (`state.py tick-plan`), commit the plan, skip |
| interrupted | stage `spec`, `build`, `review` or `approve` | resume from that stage; a `concern_status` follows `concerns.md` first |
| needs-human | stage `needs-human` | do not touch; list it |
| waiting-input | stage `waiting-input` | read the pending `questions-<k>.md` and ask again; see `questions.md` |
| not started | no job | start |

Resuming: keep the worktree and branch, never recreate. If they are missing, or the branch no
longer points at the `head` in `job.json`, set `needs-human` and say why. `build` with a build.md for the recorded `build_round` and `STATUS: READY`: go straight to Route (step 3), or to `lean-check` for a job
with `lean` (`lean.md`).
`build` without build.md: start a fresh
builder with the task and the commits already on the branch; for a job with `lean`, go on building in the session (`lean.md`). Round partly done: keep finished
review files, rerun only the missing reviewers. `approve` without decision.md: rerun the approver. `approve` on a short-path job (`lite` in `job.json`): run `state.py verdicts` first, since a
decision.md may be left from an earlier round; `CHANGES` or a missing review goes back to step 5 or reruns the approver, and only `all_pass` lets decision.md count.
A named builder does not survive its session; a resumed builder, like any builder whose agent is gone, on any host, is a new agent that reads build.md,
the rounds and the branch log. In current-branch mode show leftover changes and ask whether to
continue from them, stash them or stop. Before continuing, say in one line per job what you found.

## Ad hoc task

`factory-task [tier=<name>] <text>`: run `state.py adhoc --root <repo> --text "<text>"`. It writes a one-task plan to
`factory/jobs/_runs/adhoc-<YYYYMMDD-HHMMSS>-<slug>.md` (title from the first words of the text, tier `medium` unless a leading `tier=<name>` says
`light`, `medium`, `careful`, `heavy` or `fable`, one `Accept` criterion taken from the text) and prints `plan_file`, `plan_stem`, `title` and `tier`; an
unknown tier or an empty text exits 2. The file is local and git ignores it, so it never reaches the repo's plans folder. Use `plan_file` as the plan path
for `run`, `lock` and `open-job`, and run it through the Job loop and Completion. Landing skips the tick (there is nothing in the repo to tick), and Completion does what `completion.md` says for an ad hoc plan.
