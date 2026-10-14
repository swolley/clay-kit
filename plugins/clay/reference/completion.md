# Completion

Part of the orchestrator reference (see `orchestrator.md`). `<plugin root>` is the path your skill states. Follow `<plugin root>/STYLE.md`. `<repo>` is the root of the target repository's own checkout.

For an ad hoc plan (`factory/jobs/_runs/adhoc-*.md`, made by `state.py adhoc`) skip `tick-plan` and the plan commit, since the plan is local and there is
nothing in the repo to tick; release the lock and run `clean` as below, which also deletes the working plan.

When every task is landed, tick the steps of each completed task with `state.py tick-plan` (see `lock.md`) and commit that on
the branch the jobs landed on: in current-branch mode in the repo (message "Mark the plan steps done"), in isolated mode in the integration
worktree (pass the plan's path inside that worktree as `--plan-file`). When every task of the plan is done, `tick-plan` also writes
`status: completed` and `verified_on` in the plan's front matter and appends an `## Execution record` table (task, tier, models, rounds,
reviews, decision, notes, tokens, agent time), and the same commit carries both (`closed: true` in its output). The plan then keeps the
history, since the job folders are local. Then release the lock and run `state.py clean --root <repo> --plan <plan-stem>`, which removes the
plan's job folders and run state; it refuses while a job of the plan is not landed, and then you leave everything as it is. It does not
remove worktrees. Isolated mode then ends
with the finish step: ask the user, with the question tool, how the integration branch reaches the repo's
main branch: merge it, prepare a pull request without pushing, keep the branch, or discard it. Do only the
chosen local action. Current-branch mode has nothing to merge.

