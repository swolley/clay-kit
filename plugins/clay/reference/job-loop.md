# Job loop and pace

Part of the orchestrator reference (see `orchestrator.md`). `<plugin root>` is the path your skill states. Follow `<plugin root>/STYLE.md`. `<repo>` is the root of the target repository's own checkout.

## Job loop

Do the bookkeeping with `python3 <plugin root>/scripts/state.py` instead of editing files by hand: it writes `job.json`, keeps the
phase log and the times, and does the checks. Every command takes `--root <repo>` and prints JSON.

Open every agent prompt with the job's coordinates (`<paths>` below): its folder `<repo>/factory/jobs/<job-id>/`, the
worktree path, the branch, the mode and the base, then `State: python3 <plugin root>/scripts/state.py`, the job id and the repo root `<repo>`: the agents run
and read checks with them (`verify`, `checks`). A reviewer and the approver also get `Diff: <path>`, the `diff` that `state.py route` printed.

When an agent finishes, the spawn result carries its usage (`subagent_tokens`, `tool_uses`, `duration_ms`). Record it at once:
`state.py agent <job-id> <role> --model <m> --effort <e> --tokens <n> --ms <n> --tools <n>` (roles `builder`, `code`, `security`,
`ux`, `ui`, `approver`; leave `--effort` empty when the host did not accept one). The progress views show who has the job, on which
model, and what it cost in time and tokens. The usage of your own session is not included: it is not reported to you.

0. **Once per run.** Take the run lock (see `lock.md`), then `state.py setup --plugin-root <plugin root>` (creates `factory/jobs/`, ignored by git, and copies the
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
   `questions.md`, `STATUS: BLOCKED` sends the job to step 8.
3. **Route.** `state.py route <job>` takes the changed paths (`git diff --name-only <base>...<branch>`; in current-branch mode
   `git diff --name-only HEAD` plus `git ls-files --others --exclude-standard`), applies the routing table (the repo's `factory/routing.md`
   if that file exists) and sets up the round: it writes `reviewers`, creates `round-N/` with `diff.patch` (commits, file list, what changed since the
   previous round, diff: no agent runs those git commands again) and sets the stage. It prints `reviewers`, `rerun`, `carried`, `lite` and `diff`.
   **Carried lenses.** After round 1 a lens that passed keeps its verdict and is not run again while nothing its rules watch has changed since
   that round: `carried` names the round it was given in. The `code` lens watches every path, so it runs again whenever anything changed, and a
   lens that asked for changes always runs again. `rerun` is the list to spawn; it may be empty when nothing changed.
   **Short path.** When it prints `lite: true` (tier `light`, at most 3 files and 30 lines, only the `code` lens) no reviewer is spawned
   and the job goes straight to approve: the approver reviews the diff itself, so tell it `Lite: yes` in its prompt.
4. **Review round N.** Spawn the reviewers in `rerun` in one message, with the settings from `tiers.md`, prompt `<paths> Review round N.`
   plus `Port: 5101+10n` for ux and `5102+10n` for ui. When they have finished, check the round in its own step: `state.py verdicts <job>`
   reads line one of every file of `rerun`, stores the verdicts in `job.json`, and exits 1 if a file or a verdict line
   is missing; `all_pass` counts the carried verdicts too. A reviewer's chat reply is a claim, not a verdict: only its file counts. A reviewer that wrote no file gets one more time, with a reminder to write it; if it still has no verdict line, stop and tell the user. The builder stays untouched until the whole round is in.
5. **Decide.** `all_pass`: approve. Any CHANGES with resumes left (max 2 after round 1): `state.py stage <job> build`,
   resume the builder with `SendMessage` (or a fresh builder if the session lost it) saying the reviews are in `round-N/` and to
   answer every CHANGES; then check the first line of build.md as in step 2, run step 3 again (the diff may have grown) and start the
   next round. When the resumes are used up, you write `decision.md` yourself: first line `ESCALATE`, then a sentence naming
   the lenses that still ask for changes, and go to step 8.
6. **Approve.** Only after the check in step 4 passed (or in the short path), and never in the same message as that check (a failed
   check must not still start the approver), `state.py stage <job> approve` and spawn the `approver` with `<paths> Final round: N.`
   The approver's model is in `tiers.md` (`opus` when the job is risky, `sonnet` otherwise). Line one of decision.md routes it:
   `APPROVE` goes to step 7, `ESCALATE` to step 8.
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
ready command (`/factory-approve <id>`, `/factory-rework <id> <note>`, `/factory-answer <id>`), and stop.

A prompt that is dismissed counts as stop and leaves every job as it is. Running `factory-run` again starts guided again.

