# Working with the peer vendor

Read this only when the peer is on: the start's `preflight` printed `peer: {"vendor": "<peer>", "found": true}` and the user said yes
(`run --cross on`). Outside the start (rework, answer, a resumed session) run `state.py vendor <job> --agent builder --host <host> --probe` first
(`--agent reviewer-final --plan <plan-stem> --probe` when only the final review is left): it reads the run state's `cross` and
records nothing, and `cross_on: true` means follow this part. Otherwise every agent runs on your host as `hosts.md` says and none of this applies. `<peer>` is the other host
(`codex` on Claude Code, `claude` on Codex); a native agent is one that runs on your host. `peer.py` is `python3 <plugin root>/scripts/peer.py`.

## Decide

Before every agent the Job loop starts (and `reviewer-final`), ask `state.py vendor <job> --agent <role> --host <host> [--risky]`, with
`--agent` one of `builder`, `reviewer-code`, `reviewer-security`, `reviewer-interface`, `approver`; for the final review
`state.py vendor --agent reviewer-final --plan <plan-stem> --host <host> [--risky]`. It prints `vendor`, `peer`, `model`,
`effort`, `reason`, `crossed` and `cross_on`, and records the choice. Its `model` and `effort` replace those of `state.py model`.
- A lean job's builder is native; its final review goes to the peer.
- Round 3's escalated builder and a rework builder ask again, so they may change vendor.
- `crossed: false` for a reviewer, the approver or `reviewer-final` (never the builder): say `review not crossed` in one line (the vendor opposite to the builder is over its threshold or exhausted).
- `vendor: null`: both vendors are unusable. Stop as in `auto` pace: list the waiting jobs and release the lock (`job-loop.md`, `lock.md`).

`peer: false` runs as `hosts.md` says, with the printed model and effort. `peer: true` runs as below.

## Run a peer agent

1. Write `<repo>/factory/jobs/<job-id>/peer/<role>-r<N>.prompt` (`_runs` for the final review): `Read <plugin root>/agents/<role>.md and
   follow it as your instructions.` followed by `<paths>` and the rest of the prompt the calling part gives, as for a spawned agent.
   `<role>` is the agent file's name, `N` the round (the build round for the builder, 1 for the final review, `--round 2` for its
   `Scope: fix` recheck, so the first run's files stay). A Codex peer gets the lines of "Codex sandbox" below.
2. `peer.py start --root <repo> --job <job-id> --role <role> --round <N> --vendor <peer> --cwd <dir> --write <dir> --prompt-file <file>`,
   adding `--model` and `--effort` when printed non-null (`peer.py` drops `inherit`). `--cwd` is the job's worktree (for the final review the `Code:` tree);
   `--write` is `<repo>/factory/jobs/<job-id>` (`<repo>/factory/jobs/_runs`). It returns at once with `{"ok": true, "run": "<role>-r<N>"}`.
   Start every peer agent of a round first, then the native ones, so they run together. On Codex, `peer.py start` runs `claude -p`,
   which needs the network and writes `~/.claude`: run the start command outside the session's sandbox, with the host's approval.
3. `peer.py wait --root <repo> --job <job-id> --run <role>-r<N> --timeout 100` (under your shell tool's limit): while it prints `running`,
   call it again. It ends `done` or `failed` with `error`, `session_id`, `tokens`, `ms` and `rate_limits`.
4. On `done`, record it with `state.py after-agent`, `vendor` set for every agent of the run, the native ones included, and `session_id`
   for a peer one. Then check as for a native agent: the file decides (`build.md`, `state.py verdicts`, `final-verdict`), and a missing
   one gets one more run with a reminder.
5. Resume a peer builder (a CHANGES round, step 5) with `peer.py start ... --round <N> --resume <session_id>` and the reviews prompt;
   without a `session_id`, or when its vendor went down, start a fresh builder and ask `state.py vendor` again. A fresh builder (here, or
   after `limit`, `timeout` or `lost`) continues from the tree as it stands, uncommitted edits of the stopped run included, and its
   prompt says so. No reset.

## Codex sandbox

A Codex peer runs in `workspace-write`: it writes only its worktree, the job folder and `/tmp`, opens no network socket (localhost
included) and cannot write `~/.cache` or other caches in the home folder. A Claude peer runs in Claude Code's sandbox (`peer.py` passes
the settings): its shell writes only its worktree, the job folder and a temp folder, with no network and no retry outside the sandbox,
but it can commit. So:
- A Codex builder in isolated mode cannot commit (the gitdir stays read-only): its prompt adds `Commit: by the orchestrator`. When `wait`
  returns `done`, commit the paths under its `## Commit` in build.md in the job's worktree with that message, then go on as for any build.
  A Claude builder commits as any builder does.
- A peer reviewer, approver or `reviewer-final` gets the line `Sandbox: no network, no home caches. Rely on the recorded checks
  (verify --reuse) and say in your file which check you could not run again.` A peer `reviewer-interface` gets no `Port:`, so it works
  from the code, as its file allows.

## When a run fails

- `limit`: `state.py vendor-down --plan <plan-stem> --vendor <peer> --reason limit [--until <rate_limits.resets_at>]` (epoch or ISO),
  and say it in one line.
- `missing` or `auth`: `vendor-down ... --reason missing|auth`.
- `sandbox`: Claude Code's sandbox could not start (on Linux it needs `bubblewrap` and `socat`): `vendor-down ... --reason missing`,
  and say why in one line.
- After any `vendor-down`, ask `state.py vendor` again for that agent and run it on the vendor it prints, peer or native (a builder
  starts fresh, as step 5 says).
- `timeout`, `exit` or `lost`: one more run on the same vendor. A second failure sends the job to Needs human with the log,
  `<repo>/factory/jobs/<job-id>/peer/<run>.log`; for the final review tell the user and go on, as `completion.md` says for a missing verdict.
