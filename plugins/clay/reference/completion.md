# Completion

Part of the orchestrator reference (see `orchestrator.md`). `<plugin root>` is the path your skill states. Follow `<plugin root>/STYLE.md`. `<repo>` is the root of the target repository's own checkout.

For an ad hoc plan (`factory/jobs/_runs/adhoc-*.md`, made by `state.py adhoc`) skip the documentation pass, `close-plan` and the plan
commit, since the plan is local and there is nothing in the repo to close; release the lock and run `clean` as below, which also
deletes the working plan.

When every task is landed, each one is already ticked (Landing, `orchestrator.md`). Then:

1. **Documentation pass.** When two or more tasks named the same document under `Docs`, or a job's `## Deviations` contradicts what a
   document says, run one ad hoc task for it (`state.py adhoc --text "tier=light Reconcile <files> with <what changed>"`) through the
   Job loop, so the reconciliation is reviewed like any other change. Never edit the documentation yourself. Otherwise skip this step.
2. **Close.** `state.py close-plan --root <repo> --plan-file <plan>` (in isolated mode the plan inside the integration worktree) ticks
   what is still open of a landed task and, when every checklist of the plan is resolved, writes `status: completed` and `verified_on`
   in the front matter and appends one `## Delivery status (<date>)` section: `**Documented in:**` with the `Docs` of the tasks,
   `### Divergences` with each job's `## Deviations` and every cancelled step with its reason, and `### Execution record` (task, tier,
   models, rounds, reviews, decision, notes, tokens, agent time). Commit it on the branch the jobs landed on, in current-branch mode in
   the repo and in isolated mode in the integration worktree, with the message "Close the plan". `closed: false` means a checklist is
   still open (a skipped task, a section outside the tasks): say which, and leave the plan open.
3. **Check.** Run `python3 <plugin root>/scripts/plan_status.py --root <repo> --all --plan <plan-stem>`. When it reports documentation
   missing for the plan, say so in one line.

The plan is never deleted. It stays as the dated record of what was decided and of what was deliberately not built, and it keeps the
run's history, since the job folders are local; the documentation it names describes the present. A plan is finished when its
checklists are resolved, its front matter says so, its delivery status names its documentation and that documentation exists.

Then release the lock and run `state.py clean --root <repo> --plan <plan-stem>`, which removes the plan's job folders and run state; it
refuses while a job of the plan is not landed, and then you leave everything as it is. It does not remove worktrees. Isolated mode then
ends with the finish step: ask the user, with the question tool, how the integration branch reaches the repo's main branch: merge it,
prepare a pull request without pushing, keep the branch, or discard it. Do only the chosen local action. Current-branch mode has nothing
to merge.
