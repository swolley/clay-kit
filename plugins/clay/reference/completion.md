# Completion

Part of the orchestrator reference (see `orchestrator.md`). `<plugin root>` is the path your skill states. Follow `<plugin root>/STYLE.md`. `<repo>` is the root of the target repository's own checkout.

For an ad hoc plan (`factory/jobs/_runs/adhoc-*.md`, made by `state.py adhoc`) skip the final review, the documentation pass, `close-plan` and the plan
commit, since the plan is local and there is nothing in the repo to close; release the lock and run `clean` as below, which also
deletes the working plan.

When every task is landed, each one is already ticked (Landing, `orchestrator.md`). Then:

1. **Final review.** Each task was reviewed alone; this reads the run's whole branch once, for what only shows across tasks. Skip it
   for a plan of one task, whose only job was already reviewed, and for an ad hoc plan, unless a job of the run was lean: then it
   always runs, for one task and for an ad hoc plan too, since it is the only independent reading a lean job gets (`final-diff` prints
   `lean`, the number of lean jobs). On a resume, `final` in the run state says
   how far it got: `review` recorded skips the first review, `fix_job` recorded goes on from that job, `recheck` recorded ends the
   step. `final-diff` asked again for a span it already wrote returns it unchanged (`reused: true`), so a resume never widens a review.
   - Run `state.py final-diff --root <repo> --plan <plan-stem>`. It writes `_runs/<plan-stem>-final.patch` and prints `patch` and
     `risky`. When it is not ok (a run started before this step existed, or the integration branch is gone), say so in one line with
     its `reason` and go on with step 2.
   - Spawn `reviewer-final` as `hosts.md` says, with the model and effort of `state.py model --host <host> --agent reviewer-final`, adding
     `--risky` when `final-diff` printed `risky: true`, and the prompt `Plugin root: <plugin root>`, then `Code: <tree>` (the integration
     worktree in isolated mode, since the repo's own checkout has none of the run's code; `<repo>` in current-branch mode), `Plan: <plan>`,
     `Jobs: <repo>/factory/jobs`, `Diff: <patch>` and `Output: <repo>/factory/jobs/_runs/<plan-stem>-final.md`, all absolute paths. When it has finished, run `state.py final-verdict --root <repo> --plan <plan-stem> --agent '<usage JSON>'` in its own
     step (the usage as in the Job loop's recording rule). Not ok means the file or its verdict line is missing: the agent gets one more
     try with a reminder to write it; if it still has none, tell the user and go on with step 2.
   - `PASS`: go on with step 2. `CHANGES`: run one ad hoc task through the Job loop, `state.py adhoc --text "tier=medium Fix the final
     review findings in <repo>/factory/jobs/_runs/<plan-stem>-final.md"`, as the documentation pass does (see "Ad hoc tasks inside
     Completion" below). When it lands, run `final-diff --fix`, spawn `reviewer-final` again with `Scope: fix`, `Previous:
     <repo>/factory/jobs/_runs/<plan-stem>-final.md`, the new `Diff:` and `Output: <repo>/factory/jobs/_runs/<plan-stem>-final-2.md`, then
     `final-verdict --fix --fix-job <job-id>`. When `final-diff --fix` is not ok because nothing landed, record no recheck and tell the
     user the findings are still open. The findings the recheck still lists are not fixed again: tell the user, one line per
     finding, and go on. When the fix job goes `needs-human` instead, leave the recheck out: `close-plan` then records the first
     review's findings as open.
2. **Documentation pass.** When two or more tasks named the same document under `Docs`, or a job's `## Deviations` contradicts what a
   document says, run one ad hoc task for it (`state.py adhoc --text "tier=light Reconcile <files> with <what changed>"`) through the
   Job loop, so the reconciliation is reviewed like any other change. Never edit the documentation yourself. Otherwise skip this step.
3. **Close.** `state.py close-plan --root <repo> --plan-file <plan>` (in isolated mode the plan inside the integration worktree) ticks
   what is still open of a landed task and, when every checklist of the plan is resolved, writes `status: completed` and `verified_on`
   in the front matter and appends one `## Delivery status (<date>)` section: `**Documented in:**` with the `Docs` of the tasks,
   `### Divergences` with each job's `## Deviations` and every cancelled step with its reason, `### Final review` when step 1 ran, and `### Execution record` (task, tier,
   models, rounds, reviews, decision, notes, tokens, agent time). Commit it on the branch the jobs landed on, in current-branch mode in
   the repo and in isolated mode in the integration worktree, with the message "Close the plan". `closed: false` means a checklist is
   still open (a skipped task, a section outside the tasks): say which, and leave the plan open.
4. **Check.** Run `python3 <plugin root>/scripts/plan_status.py --root <repo> --all --plan <plan-stem>`. When it reports documentation
   missing for the plan, say so in one line.

**Ad hoc tasks inside Completion.** The documentation pass and the final review's fix run inside this run, not as runs of their
own: the run's mode, branch and lock stay as they are, and the ad hoc plan gets no `run`, `lock` or Completion of its own. In isolated
mode the job's branch and worktree are cut from the plan's integration branch and land on it, as the plan's tasks do; in current-branch
mode the job is committed on the current branch. Once it has landed, `state.py clean --root <repo> --plan <its plan_stem>` removes its job folder and working plan.

The plan is never deleted. It stays as the dated record of what was decided and of what was deliberately not built, and it keeps the
run's history, since the job folders are local; the documentation it names describes the present. A plan is finished when its
checklists are resolved, its front matter says so, its delivery status names its documentation and that documentation exists.

Then release the lock and run `state.py clean --root <repo> --plan <plan-stem>`, which removes the plan's job folders and run state; it
refuses while a job of the plan is not landed, and then you leave everything as it is. It does not remove worktrees. Isolated mode then
ends with the finish step: ask the user, with the question tool, how the integration branch reaches the repo's main branch: merge it,
prepare a pull request without pushing, keep the branch, or discard it. Do only the chosen local action. Current-branch mode has nothing
to merge.
