# Inline mode

Part of the orchestrator reference (see `orchestrator.md`). `<plugin root>` is the path your skill states. Follow `<plugin root>/STYLE.md`. `<repo>` is the root of the target repository's own checkout.

`/factory-run <plan> inline` builds in this session instead of in a `builder` subagent, to save the start-up of one agent per task
(about 12 seconds and 12 thousand tokens). It is allowed only when every runnable task has tier `light`; otherwise say which task
is not and run normally. Do everything of the Job loop (`job-loop.md`) except step 2: make sure the job is in `build`, read
`<plugin root>/agents/builder.md`, and do that agent's work yourself in the job's worktree, writing `build.md` as it says. Record no
`builder` usage, except for an escalated round 3: that builder is a subagent on the higher tier (step 5 of `job-loop.md`) and
its usage is recorded as any builder's. Then go on at step 3: routing decides as usual, so the short path (approver only) applies when `lite` is true, and a
task whose change touches a path another lens watches gets its reviewers after the fact. The `approver` and every reviewer stay subagents: the change must
not be judged by the session that wrote it. In `NEEDS_INPUT` and rework you still own the builder's part. Say at the end that the
run was inline. Lean tasks (`lean.md`) differ: they drop the reviewers and the approver as well.

