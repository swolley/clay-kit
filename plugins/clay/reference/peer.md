# Working with the peer vendor

Read this only when the peer is on: the start's `preflight` printed `peer: {"vendor": "<peer>", "found": true}` and the user said yes
(`run --cross on`). Otherwise every agent runs on your host as `hosts.md` says and none of this applies. `<peer>` is the other host
(`codex` on Claude Code, `claude` on Codex); a native agent is one that runs on your host. `peer.py` is `python3 <plugin root>/scripts/peer.py`.

## Decide

Before every agent the Job loop starts (and `reviewer-final`), ask `state.py vendor <job> --agent <role> --host <host> [--risky]`, with
`--agent` one of `builder`, `reviewer-code`, `reviewer-security`, `reviewer-interface`, `approver`; for the final review
`state.py vendor --agent reviewer-final --plan <plan-stem> --host <host> [--risky]`. It prints `vendor`, `peer`, `model`,
`effort`, `reason` and `crossed`, and records the choice. Its `model` and `effort` replace those of `state.py model`.
- A lean job is built by the session; its final review goes to the peer.
- Round 3's escalated builder and a rework builder ask again, so they may change vendor.
- `crossed: false`: say `review not crossed` in one line (the vendor opposite to the builder is over its threshold or exhausted).
- `vendor: null`: both vendors are unusable. Stop as in `auto` pace: list the waiting jobs and release the lock (`job-loop.md`, `lock.md`).

`peer: false` runs as `hosts.md` says, with the printed model and effort. `peer: true` runs as below.

## Run a peer agent

1. Write `<repo>/factory/jobs/<job-id>/peer/<role>-r<N>.prompt` (`_runs` for the final review): `Read <plugin root>/agents/<role>.md and
   follow it as your instructions.` followed by `<paths>` and the rest of the prompt the calling part gives, as for a spawned agent.
   `<role>` is the agent file's name, `N` the round (the build round for the builder, 1 for the final review).
2. `peer.py start --root <repo> --job <job-id> --role <role> --round <N> --vendor <peer> --cwd <dir> --write <dir> --prompt-file <file>`,
   adding `--model` and `--effort` when printed non-null. `--cwd` is the job's worktree (for the final review the `Code:` tree);
   `--write` is `<repo>/factory/jobs/<job-id>` (`<repo>/factory/jobs/_runs`). It returns at once with `{"ok": true, "run": "<role>-r<N>"}`.
   Start every peer agent of a round first, then the native ones, so they run together.
3. `peer.py wait --root <repo> --job <job-id> --run <role>-r<N>`: `state: "running"` at its timeout, call it again. It ends `done` or
   `failed` with `error`, `session_id`, `tokens`, `ms` and `rate_limits`.
4. On `done`, record it with `state.py after-agent`, `vendor` set for every agent of the run, the native ones included, and `session_id`
   for a peer one. Then check as for a native agent: the file decides (`build.md`, `state.py verdicts`, `final-verdict`), and a missing
   one gets one more run with a reminder.
5. Resume a peer builder (a CHANGES round, step 5) with `peer.py start ... --round <N> --resume <session_id>` and the reviews prompt;
   without a `session_id`, or when its vendor went down, start a fresh builder from the branch as it stands and ask `state.py vendor` again.

## When a run fails

- `limit`: `state.py vendor-down --plan <plan-stem> --vendor <peer> --reason limit [--until <rate_limits.resets_at as ISO>]`, say it in
  one line, ask `state.py vendor` again and run the same agent on the vendor it prints (a builder starts fresh from the branch).
- `missing` or `auth`: `vendor-down ... --reason missing|auth`, then the agent runs on your host as `hosts.md` says.
- `timeout`, `exit` or `lost`: one more run on the same vendor. A second failure sends the job to Needs human with the log,
  `<repo>/factory/jobs/<job-id>/peer/<run>.log`; for the final review tell the user and go on, as `completion.md` says for a missing verdict.
