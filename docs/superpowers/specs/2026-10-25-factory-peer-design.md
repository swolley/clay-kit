# Factory peer vendor: design

Date: 2026-10-25. Status: approved in conversation.

## Goal

Let a run use both the Claude and the Codex account: some agents run through the other vendor's CLI, so the usage is split
across two plans and every job is read by a model of a different family than the one that wrote it. Success: with both CLIs
installed, a run on either host spreads its agents over both vendors, every job's reviews and approval come from the vendor that
did not build it (or the record says why not), a vendor that hits its limit hands its work to the other instead of stopping the
run, and the execution record keeps the vendor of every agent so that later runs can be judged on facts.

Out of scope: Cursor sessions (no peer); choosing vendors from past results (the data is recorded now, used later); a usage
source for the Claude plan (none is readable today).

## Approach

The session stays the orchestrator on its host, Claude Code or Codex. The other vendor is the **peer**, reached through its
official CLI run as a detached process by a new script, `scripts/peer.py`, so a long build never hits the host's command timeout.
`state.py` decides which vendor runs each agent and records it; everything else of the Job loop (verdict files, `verdicts`,
landing, the record) is unchanged, whoever ran the agent. The design is symmetric: on Claude Code the peer is `codex exec`, on
Codex it is `claude -p`. Rejected: an MCP server (more infrastructure, and long calls time out the same way); a native subagent
that runs the CLI (the same timeout, and one agent more); vendor strengths written into the rules (they change with every model
release).

## 1. Who runs what

- **When it is on.** Only when the session's host is `claude` or `codex`, the other CLI (`codex` or `claude`) is on `PATH`, and the
  user said yes at the start of the run (section 5). `<peer>` is the other host's name.
- **Builder.** The session's host, unless the task's tier is listed in `builder_tiers` (section 5; empty by default, since where to
  build is the programmer's choice), or the chosen vendor is over its threshold or exhausted (section 3) while the other is not.
  Lean jobs are built by the session as today.
- **Reviewers and approver.** The vendor opposite to the job's builder. When that vendor is over its threshold or exhausted, they
  stay on the builder's vendor and the job records `crossed: false`.
- **Final review.** The vendor opposite to the session's host, with the same exception.
- **Models.** A peer agent takes its model and effort from `state.py model --host <its vendor>`, so `factory/models.json` entries for
  that host apply; without entries a Codex peer passes no model (the user's Codex default) and a Claude peer uses the `tiers.md`
  tables.
- **Escalation and rework.** Round 3's fresh builder and a rework builder decide their vendor again, so they may change vendor.
- **Decision.** `state.py vendor <job> --role <builder|reviewer|approver|reviewer-final> --host <host>` prints
  `{ "vendor", "peer", "model", "effort", "reason", "crossed" }` (`peer` is true when the vendor is not the session's host;
  `reason` is one of `session`, `builder_tiers`, `threshold`, `exhausted`, `opposite`, `not crossed`) and records it in `job.json`
  (for `reviewer-final`, in the run state's `final`). With the peer off it prints the session's host and `reason: "session"`.

## 2. `peer.py`

- **`peer.py start --root <repo> --job <job-id> --role <role> --round <N> --vendor <claude|codex> --cwd <dir> --write <dir>
  [--model <m>] [--effort <e>] [--resume <session-id>] --prompt-file <file>`** starts a detached runner and returns at once with
  `{ "ok": true, "run": "<role>-r<N>" }`. Its files are `<repo>/factory/jobs/<job-id>/peer/<role>-r<N>.{log,status.json}`; the prompt
  file sits next to them. For the final review `--job` is `_runs` and the files go under `_runs/peer/`.
- **The prompt** is the generic agent's message: `Read <plugin root>/agents/<role>.md and follow it as your instructions.`, then
  `<paths>` and the rest of the prompt the calling part gives, exactly as a spawned agent gets them.
- **Codex.** `codex exec -C <cwd> --add-dir <write> -s workspace-write [-m <model>] [-c model_reasoning_effort=<effort>] --json
  -o <last message file> -` with the prompt on stdin; with `--resume`, `codex exec resume <session-id>` with the same options. Never
  a flag that bypasses the sandbox.
- **Claude.** `claude -p [--model <model>] [--effort <effort>] --output-format json --add-dir <write> --allowedTools <the tools of
  the agent file's frontmatter; none when it lists none> --permission-mode acceptEdits`, run with `<cwd>` as working directory and the prompt on stdin; with
  `--resume`, `--resume <session-id>`. Never `--dangerously-skip-permissions`.
- **Directories.** `--cwd` is the job's worktree (the integration worktree or `<repo>` for the final review, as `Code:` says);
  `--write` is the job folder (`_runs/` for the final review), where the agent writes `build.md` or its verdict file.
- **Network.** Codex's `workspace-write` sandbox has no network by default; the worktree's setup is run by the orchestrator before the
  build, as today, so a peer builder needs none. A task that does is a known limit of a Codex peer.
- **Timeouts.** 60 minutes for `builder`, 20 for every other role; past it the runner kills the process group and records
  `timeout`.
- **`peer.py wait --root <repo> --job <job-id> --run <role>-r<N> [--timeout <seconds>]`** (default 300) returns as soon as the run
  ends, or at the timeout with `state: "running"`. The final answer is `{ "state": "done" | "failed", "error": null | "limit" |
  "missing" | "auth" | "timeout" | "exit" | "lost", "session_id", "tokens", "ms", "rate_limits" }`: `tokens` is input plus output as
  the CLI reports them, `ms` is measured by the runner, `rate_limits` is Codex's last `used_percent` and `resets_at` (null for
  Claude). `lost` means the runner is gone without a status file.
- **Errors.** `missing`: the CLI is not on `PATH`. `auth`: the CLI says it is not logged in. `limit`: the CLI says a usage or rate
  limit was reached (`LIMIT_PATTERNS` in `peer.py`, matched case-insensitively on the error output), or Codex reports
  `used_percent` of 100. `exit`: any other non-zero exit.
- **Source of truth.** As today, the agent's file decides: after `done` the orchestrator checks `build.md` or runs `state.py
  verdicts`, and a missing file gets one more run with a reminder, as for a native agent.

## 3. Margin and fallback

- **`state.py quota --vendor codex`** prints `{ "used_percent", "resets_at", "source" }` from the newest `rate_limits` it can read:
  the last peer run's status file, else the newest rollout file under `$CODEX_HOME/sessions` (default `~/.codex`). A window whose
  `resets_at` has passed counts as 0%. No data prints `used_percent: null`. For `claude` it always prints `null`.
- **Threshold.** A vendor whose `used_percent` is at or above `threshold` (default 80) is over it. An unknown margin is never over.
- **`state.py vendor-down --vendor <v> --reason <limit|missing|auth> [--until <iso>]`** records the vendor in the run state's
  `vendors`: `limit` marks it exhausted until `--until` (Codex's `resets_at`) or to the end of the run; `missing` and `auth` turn
  the peer off for the run. The orchestrator says it in one line.
- **On a failed agent.** `limit`: `vendor-down`, then the same agent runs again on the other vendor (a builder starts fresh from the
  branch as it stands). `missing` or `auth`: `vendor-down`, then the agent runs on the session's host. `timeout`, `exit` or `lost`:
  one more run on the same vendor; a second failure sends the job to Needs human with the log path (for the final review:
  tell the user and go on, as `completion.md` says for a missing verdict).
- **Both exhausted.** The run stops as in `auto` pace: the waiting jobs are listed, the lock is released.

## 4. Record

- **`job.json`.** Each role in `agents` gains `vendor` and, for a peer, `session_id`; the job gains `vendor_reason` per role and
  `crossed: false` when a review stayed on the builder's vendor. Peer usage is recorded with `after-agent`, as for any agent.
- **Run state.** `cross: { "on", "peer", "threshold", "builder_tiers" }` and `vendors: { "<v>": { "exhausted_until", "off" } }`.
- **Execution record** (`close-plan`): the models column shows the vendor (`codex:gpt-5.5`, `claude:sonnet`); Notes says
  `review not crossed` for a job with `crossed: false`; a new column, `first round`, gives the first round's verdicts. With the
  builder's vendor, tier and first-round verdict in every row, results per vendor can be counted across closed plans later.

## 5. Turning it on

- **`factory/models.json`** gains a top-level `cross` object: `{ "builder_tiers": ["light"], "threshold": 80 }`, both optional
  (defaults `[]` and `80`). `models.py` validates it (tiers from the tier list, threshold 1 to 100).
- **Start.** `state.py preflight` reports `peer: { "vendor": "<peer>", "found": true|false }`. When found, the mode question adds
  "work with <peer>: yes (recommended) / no"; `state.py run --cross on|off` records it. A resumed run asks again; jobs keep the
  vendors they were given.
- **Reference.** A new part, `reference/peer.md`, holds sections 1 to 3 for the orchestrator and is read only when the peer is
  on; `job-loop.md` steps 2, 4 and 6 and `completion.md` step 1 say in one clause to ask `state.py vendor` first when it is. The
  start's word budget is unchanged.
- **README** gets one paragraph and the `cross` keys.

## Testing

- `tests/test_peer.py`, with fake `codex` and `claude` executables on a test `PATH`: a run that writes its file and ends `done` with
  tokens and session id; `limit`, `auth`, `exit` from the fake's output; `timeout` with a short limit; `missing` without the fake;
  `lost` when the runner dies; `--resume` passes the session id; the argument lists never contain a sandbox-bypass flag.
- `tests/test_state.py`: `vendor` for each role and reason (session, `builder_tiers`, threshold, exhausted, opposite, not
  crossed) with the peer on and off; `quota` from a status file, from a rollout file, with a past `resets_at`, and with no data;
  `vendor-down` for each reason; `run --cross`; `preflight` reports `peer`; the execution record shows vendor, `review not
  crossed` and the first round.
- `tests/test_models.py`: `cross` validation.
- `tests/test_orchestrator_text.py`: `peer.md` names `vendor`, `peer.py start`, `wait`, `vendor-down`; the run skills read it only
  when the peer is on; the word budget holds.
- `scripts/validate.py` passes.
