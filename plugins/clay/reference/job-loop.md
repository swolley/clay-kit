# Job loop and pace

## Job loop

`state.py` is `python3 <plugin root>/scripts/state.py`; every command takes `--root <repo>` and prints JSON.

Start every agent as `hosts.md` says, with a prompt that opens with the job's coordinates (`<paths>` below): first
`Plugin root: <plugin root>`, then its folder `<repo>/factory/jobs/<job-id>/`, the worktree path, the branch, the mode and the base, then `State: python3 <plugin root>/scripts/state.py`, the job id and the repo root `<repo>`: the agents run
and read checks with them (`verify`, `checks`). A reviewer and the approver also get `Diff: <path>`, the `diff` that `state.py route` printed.

When an agent finishes, record its model, effort and usage at once, with all the agents that finished together in one call:
`state.py after-agent <job-id> --agents '[{"role":"code","model":"sonnet","effort":"medium","tokens":9000,"ms":20000,"tools":5}]'` (roles `builder`, `code`,
`security`, `interface`, `approver`; the fields follow the recording rule in `hosts.md`, plus `vendor` and `session_id` with the peer on; `state.py agent <job-id> <role>` with the same
fields as options records one agent). The usage of your own session is not reported to you.

0. **Once per run.** Take the run lock (see `lock.md`), then `state.py setup --plugin-root <plugin root>` (creates `factory/jobs/`, ignored by git, and copies the
   dashboard) and `state.py run --plan-file <plan> --mode <mode> --pace <pace> [--cross on|off --host <host>]` (writes the run state: total, tasks, and `done`
   counted from the landed jobs).
1. **Create** the job. In isolated mode create the branch and worktree first, and only then write `job.json`:
   `state.py begin-job --plan-file <plan> --task <n> --repo-name <name> --mode <mode> --branch <b> --worktree <w>` claims the next job
   id, writes `task.md` and `job.json`, moves the job to `build` and prints the id, so a crash never leaves a job without its worktree
   (`new-job` does the same without the move). A job folder that has
   no `job.json` is an abandoned claim: start the task fresh.
2. **Build.** A job with `lean` in `job.json` follows `lean.md` from here instead of steps 2 to 6. The job is in `build` already; on a resume or a rework set it with `state.py stage <job> build`. With the peer on, who builds is decided as `peer.md` says (outside the start, run `state.py vendor` first: `peer: true` means follow `peer.md`). Spawn the `builder` as `hosts.md` says, with the model and effort
   `state.py model --host <host> --tier <tier>` prints for the task's tier (after the `fable` answer in `start.md`),
   prompt `<paths> Build round 1.` plus `Port: <5100+10n>` (n = job number), and name it `builder-<job-id>` where the host allows it.
   Keep the agent id the spawn returns; it replaces the name when you resume the builder.
   The first line of build.md decides what happens next: `STATUS: READY` moves on, `STATUS: NEEDS_INPUT` goes to
   `questions.md`, `STATUS: BLOCKED` sends the job to step 8.
3. **Route.** `state.py route <job>` routes the change through the routing table (the repo's `factory/routing.md` if that file
   exists) and sets up the round with its `round-N/diff.patch`, which every agent reads instead of running git. It prints `reviewers`, `rerun`, `carried`, `lite` and `diff`.
   **Carried lenses.** After round 1 a lens that passed keeps its verdict and is not run again while nothing its rules watch has changed since
   that round: `carried` names the round it was given in. The `code` lens watches every path, so it runs again whenever anything changed, and a
   lens that asked for changes always runs again. `rerun` is the list to spawn; it may be empty when nothing changed.
   **Short path.** When it prints `lite: true` (tier `light` or `medium`, not risky, only the `code` lens, any size) no reviewer is spawned
   and the job goes straight to approve: the approver writes the code review itself, so tell it `Lite: yes` in its prompt. The round is set
   up as any other (`round-N/` with its `diff.patch`), with `code` as its only lens.
4. **Review round N.** Spawn the reviewers in `rerun` in one message, as `hosts.md` says (with the peer on, `peer.md` decides each one's vendor), each with the model and effort of
   `state.py model --host <host> --agent reviewer-<lens>`, prompt `<paths> Review round N.` The `ux` and `ui` lenses have one
   reviewer: when `rerun` holds either or both, spawn one `reviewer-interface` (`--agent reviewer-interface`) with `Lenses:` and those
   lenses and `Port: 5101+10n`; it writes `review-<lens>.md` for each, and its usage is recorded under the role `interface`. When they have finished, check the round in its own step: `state.py verdicts <job>`
   reads line one of every file of `rerun`, stores the verdicts in `job.json`, and exits 1 if a file or a verdict line
   is missing; `all_pass` counts the carried verdicts too. A reviewer's chat reply is a claim, not a verdict: only its file counts. A reviewer that wrote no file gets one more time, with a reminder to write it; if it still has no verdict line, stop and tell the user. The builder stays untouched until the whole round is in.
5. **Decide.** `all_pass`: approve. An attempt has at most three rounds, counted from the start of the job or, after a rework, from the
   `rework_from` round in `job.json` (round 4 of a job reworked at round 3 is that attempt's round 1). Any CHANGES after round 1: `state.py stage <job> build`,
   resume the builder as `hosts.md` says, saying the reviews are in `round-N/` and to
   answer every CHANGES; then check the first line of build.md as in step 2, run step 3 again (the diff may have grown) and start the
   next round. Any CHANGES after round 2: `state.py stage <job> build`, then `state.py escalate <job> --host <host>`. With
   `escalated: true` it has moved the task one tier up: spawn a fresh builder (not a resume) with the model and effort it printed and
   the prompt `<paths> Build round 3. Escalated from <tier>: every round's reviews are in round-*/. Read task.md, build.md and them,
   then continue from the branch as it stands.`, and record it under `builder`. With `escalated: false` (the task was `heavy` or `fable`) resume the builder as after round 1.
   Any CHANGES after round 3: you write `decision.md` yourself: first line `ESCALATE`, then a sentence naming the lenses that still ask
   for changes, and go to step 8.
6. **Approve.** Only after the check in step 4 passed (or in the short path), and never in the same message as that check (a failed
   check must not still start the approver), `state.py stage <job> approve` and spawn the `approver` as `hosts.md` says (with the peer on, as `peer.md` says) with `<paths> Final round: N.`, its model and effort
   from `state.py model --host <host> --agent approver`, adding `--risky` when the job is risky (the rule is in `tiers.md`). In the short path, when
   the approver has finished, run `state.py verdicts <job>` in its own step, as in step 4: `CHANGES` goes to step 5 like any review, and
   `all_pass` goes on to decision.md. Line one of decision.md routes it: `APPROVE` goes to step 7, `ESCALATE` to step 8.
7. **Land.** As in Landing (`orchestrator.md`).
8. **Needs human.** `state.py stage <job> needs-human`; keep the branch and worktree; name the waiting job for the user, give its
   worktree path, and quote either decision.md or the reason given for BLOCKED.

## Pace

Recorded in the run state as `pace`: `step` (the default) or `auto`.

**Guided (`step`).** When a job ends, ask with the question tool what to do next, and do it without making the user
type another command.
- A job landed and tasks are left: continue with the next task (recommended), stop here, or
  run the rest without asking (sets `pace: auto`). After the last task, read `completion.md`.
- A job needs a person (`needs-human`): quote in two lines the question in the `## Handoff to the human` of its
  decision.md, or the BLOCKED reason, then offer: approve as it stands (Land), rework with a note (take the note as
  free text), skip this task and go on, or stop. Apply the answer and continue the loop. In current-branch mode
  skip is not offered: the changes are in the tree and the next task must not start on top of them. In isolated mode a skipped job
  stays `needs-human`, and the tasks that depend on it are not started.
- An agent asked a question: handle it in place, as in `questions.md`.

**Auto.** No question between tasks. A job that needs a person stops the run: list the waiting jobs, each with the
ready command (`/factory-approve <id>`, `/factory-rework <id> <note>`, `/factory-answer <id>`), release the lock as `lock.md` says, and stop.

A prompt that is dismissed counts as stop and leaves every job as it is. Running `factory-run` again starts guided again.

