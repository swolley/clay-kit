# Lean tasks

A lean task is built by a `builder` agent on its tier's model and proved by its own checks, with no reviewer or approver of its own;
the final review of the branch (`completion.md`) is its independent reading. The session only orchestrates, so the code never grows
its context. Every other task of the same run keeps the full Job loop.

## Which tasks

`state.py preflight --plan-file <plan>` marks each task with `lean` and `lean_reason`, and counts `lean_count`. A task is eligible
when its tier is `light` or `medium`, it declares `Files` whose routing (`routing.md`) selects only the `code` lens, and it declares
`Accept` and `Verify`. `lean_reason` says why not (`tier careful`, `no Files`, `Files route to security`, `no Accept`, `no Verify`).
`long: true` means more than 8 eligible tasks: say that the last ones will run on a long or compacted context.

## Choosing

- `factory-run <plan> lean` runs every eligible task lean, `factory-run <plan> full` none. Without either word, add one question to
  the mode question: "lean where possible (N of M tasks)", recommended when N > 0, or "all full". The choice holds for the run; a
  resumed run asks again, and jobs already started keep the `lean` they were created with.
- `factory-task lean <text>` runs the ad hoc task lean when it is eligible. Its `Verify` comes from `verify=<command>` in the text
  (`adhoc` prints `verify`); without it the task is not eligible (`no Verify`), so say why and run it full. An ad hoc task
  declares no `Files`: `lean-check` judges its paths on the real diff.

## The lean job

1. **Create.** `state.py open-job ... --lean`, in the run's mode: isolated mode still cuts the job's branch and worktree from the
   integration branch. `job.json` records `lean: true` and `verify`, the task's commands.
2. **Build.** Spawn the `builder` as step 2 of the Job loop says (its model from `state.py model --tier <tier>`), with the prompt
   `<paths> Build round 1.` and the line `Lean: yes`, which turns on its file's lean rules. Record its usage. Its first line of
   build.md routes the job as in the Job loop: `NEEDS_INPUT` goes to `questions.md`, `BLOCKED` to Needs human.
3. **Gate.** `state.py lean-check <job>`. `land: true` goes to Landing (`orchestrator.md`), as any approved job. Otherwise it prints
   `promote` with the reason: the job is not lean or its tier is no longer light or medium, it changed nothing, the change routes to
   another lens, isolated mode left files uncommitted, a check failed twice, or a `Verify` command has no
   run, a stale run (the code changed after it) or a failing one.
4. **Promote.** `state.py promote <job> --reason "<reason>"`, then continue at step 3 (Route) of the Job loop with the build as it
   stands: reviewers and approver read it as any builder's, at the task's tier, and a resume or rework spawns the `builder` agent.
   Say so in one line.

A lean job shows `lean` in the execution record, a promoted one `promoted: <reason>`.
