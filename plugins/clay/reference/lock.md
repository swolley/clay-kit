# Run lock

Part of the orchestrator reference (see `orchestrator.md`). `<plugin root>` is the path your skill states. Follow `<plugin root>/STYLE.md`. `<repo>` is the root of the target repository's own checkout.

One run at a time per plan, and the plan and its spec cannot be edited while it lasts. The run takes a lock at the start with
`python3 <plugin root>/scripts/state.py lock acquire --root <repo> --plan-file <plan> --run-id <id>`, where `<id>` is a fresh unique id you
remember for the whole run. The lock is the file `factory/jobs/_runs/<plan>.lock`; it records the run id, when it started, and a heartbeat that
every `state.py` change of a job refreshes. It also makes the plan file and the spec its header names (`**Spec:**`) read-only, and remembers their
original permissions.

- The command exits 3 when another run holds the plan, and prints who, since when and the last heartbeat. If that heartbeat is recent (30 minutes),
  tell the user the plan is being run by another session, that it must be stopped there first or released with `/factory-unlock`, and stop.
- If the other run is `stale` (no heartbeat for over 30 minutes: its session was closed or crashed), say so and ask with the question tool whether to
  take over; take over with `--force`, which keeps the original permissions.
- Release it with `state.py lock release --root <repo> --plan <plan-stem> --run-id <id>` when the run completes, when the user stops it, and when the
  run ends because a job needs a person in `auto` pace. A run that goes on after a decision in guided pace keeps the lock.
- The plan's steps are ticked at the end with `state.py tick-plan --root <repo> --plan-file <plan>`, which works on the read-only file and leaves it
  read-only. Never edit the plan or the spec yourself while the lock is held, and tell the builders not to.
- A command that acts on a job (`approve`, `rework`, `answer`) from a session that does not hold the lock, on a plan with a recent heartbeat, asks the
  user to confirm before acting, because the session that runs the plan may be acting on the same job.

