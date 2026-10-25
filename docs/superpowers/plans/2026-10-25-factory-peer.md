# Factory Peer Vendor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a run hand some agents to the other vendor's CLI, so usage is split across the Claude and Codex accounts and every job is read by a model of the other family.

**Architecture:** `models.py` reads a new `cross` block; a new `vendors.py` holds the pure vendor decision and the Codex quota reader; `state.py` exposes them (`vendor`, `quota`, `vendor-down`, `run --cross`, `preflight --host`) and records the vendor; a new `peer.py` runs `codex exec` or `claude -p` as a detached process with `start` and `wait`. A new reference part, `peer.md`, tells the orchestrator when to use them.

**Tech Stack:** Python 3 standard library (`subprocess`, `json`, `shutil`, `signal`), pytest with fake CLI executables, Markdown reference parts.

**Spec:** `docs/superpowers/specs/2026-10-25-factory-peer-design.md`

## Global Constraints

- No emojis and no em-dashes in any file. Code and docs in English. Python standard library only.
- After every task: `python3 -m pytest tests -q` passes, `python3 scripts/validate.py` exits 0, `node --test tests/mod/` passes.
- Hosts with a peer: `claude` (peer `codex`) and `codex` (peer `claude`); `cursor` never has one.
- Never pass a sandbox or permission bypass: no `--dangerously-bypass-approvals-and-sandbox`, no `--dangerously-skip-permissions`.
- Timeouts: 60 minutes for `builder`, 20 for every other role. `wait` defaults to 300 seconds.
- Threshold default 80, `builder_tiers` default `[]`. An unknown margin is never over the threshold.
- The start's word budget test (4,800 words) keeps passing.

## Review Focus

- A peer killed at its timeout that left a dev server running: the whole process group is gone after `timeout` (Task 3).
- A rollout file with a truncated last line or no `rate_limits` at all: `quota` skips the bad line and prints `null`, never a traceback (Task 2).
- Both vendors exhausted: `vendor` prints `vendor: null`, `reason: "exhausted"`, and `peer.md` says the run stops (Task 2, Task 5).
- `wait` on a run whose runner died before writing its status: `state: "failed"`, `error: "lost"` (Task 3).
- The Claude command for the builder carries the builder's frontmatter tools, including `Bash`, as `--allowedTools` (Task 3).

---

### Task 1: The `cross` block of models.json

**Repo:** clay-kit
**Tier:** light
**Depends:** none
**Files:** `plugins/clay/scripts/models.py`, `tests/test_models.py`
**Docs:** none: documented in the README in Task 5
**Accept:** 1. `cross_config(root)` returns `{"builder_tiers": [...], "threshold": int}` with defaults `[]` and `80`. 2. A `cross` block with an unknown key, an unknown tier or a threshold outside 1 to 100 raises `ModelsError` naming `cross.<key>`. 3. Host entries validate as before.
**Verify:** `python3 -m pytest tests -q && python3 scripts/validate.py`

**Interfaces:**
- Produces: `cross_config(root) -> dict` in `models.py`; Task 2 reads it.

- [ ] **Step 1: Write the failing tests** in `tests/test_models.py`: `test_cross_defaults` (no file gives `{"builder_tiers": [], "threshold": 80}`), `test_cross_reads_the_block` (`{"cross": {"builder_tiers": ["light"], "threshold": 70}}` gives those values, and `resolve(..., tier="light")` still works), and rows in `test_bad_input_raises` for `{"cross": {"builder_tiers": ["hevy"]}}` (`cross.builder_tiers`), `{"cross": {"threshold": 0}}` and `{"cross": {"threshold": 101}}` (`cross.threshold`), `{"cross": {"tiers": []}}` (`cross.tiers`).
- [ ] **Step 2: Run them.** `python3 -m pytest tests/test_models.py -q`. Expected: FAIL.
- [ ] **Step 3: Implement** `cross_config` and the `cross` branch of `_validate` (a top-level key `cross` is not a host).
- [ ] **Step 4: Run the suite and the validator.** Expected: PASS, exit 0.
- [ ] **Step 5: Commit** `feat: models.json takes a cross block for the peer vendor`.

### Task 2: Vendor decision, quota and the run's peer state

**Repo:** clay-kit
**Tier:** careful
**Depends:** 1
**Files:** `plugins/clay/scripts/vendors.py`, `plugins/clay/scripts/state.py`, `tests/test_vendors.py`, `tests/test_state.py`
**Docs:** none: read through reference/peer.md, written in Task 5
**Accept:** 1. `decide` follows spec section 1 for every role and reason. 2. `quota` follows spec section 3. 3. `state.py vendor`, `quota`, `vendor-down`, `run --cross --host` and `preflight --host` work and record what the spec names.
**Verify:** `python3 -m pytest tests -q && python3 scripts/validate.py`

**Interfaces:**
- Consumes: `cross_config(root)` (Task 1); `models.resolve(root, host, tier=..., agent=..., risky=...)`.
- Produces, in `vendors.py`:
  - `PEER = {"claude": "codex", "codex": "claude"}`.
  - `quota(root, vendor: str, codex_home: Path | None = None, now: float | None = None) -> dict` with `used_percent: float | None`, `resets_at: str | None` (ISO 8601 UTC), `source: str` (`"peer"`, `"sessions"` or `"none"`).
  - `decide(job: dict | None, run: dict, agent: str, host: str, usage: dict[str, float | None], now: str) -> dict` with `vendor: str | None`, `peer: bool`, `reason: str`, `crossed: bool`. `agent` is `builder`, an agent name from `models.AGENT_DEFAULTS` without `-risky`, or `reviewer-final` (then `job` is None).
- Produces, in `state.py`: `vendor(root, job_id: str | None, agent: str, host: str, plan_stem: str | None = None, risky: bool = False) -> dict` (the decision plus `model`, `effort`; records `job["vendors"][agent] = {"vendor", "reason"}` and `job["crossed"] = False` when not crossed, or the run state's `final["vendor"]` for `reviewer-final`); `vendor_down(root, plan_stem: str, vendor: str, reason: str, until: str | None = None) -> dict`; `write_run(..., cross: str | None = None, host: str | None = None)` storing `run["cross"] = {"on", "peer", "threshold", "builder_tiers"}` and keeping `run["vendors"]`; `preflight(..., host: str | None = None)` adding `peer: {"vendor", "found"}` for `claude` and `codex` hosts (`shutil.which`). CLI: `vendor [job] --agent <a> --host <h> [--plan <stem>] [--risky]`, `quota --vendor <v>`, `vendor-down --plan <stem> --vendor <v> --reason <limit|missing|auth> [--until <iso>]`, `run ... --cross on|off --host <h>`, `preflight ... --host <h>`. Task 4 and Task 5 rely on these names.

- [ ] **Step 1: Write the failing tests** in `tests/test_vendors.py` for `decide` (pure, no repo), one test per row:
  - peer off (`run["cross"]["on"]` false or no `cross`): every agent gets the host, `reason == "session"`;
  - builder on a tier in `builder_tiers`: `vendor == "codex"` for host `claude`, `reason == "builder_tiers"`, `peer is True`;
  - builder whose chosen vendor has `usage >= threshold` while the other is under or unknown: the other vendor, `reason == "threshold"`;
  - builder whose chosen vendor has `run["vendors"][v]["exhausted_until"]` in the future: the other, `reason == "exhausted"`; one in the past does not count;
  - reviewer of a job whose `vendors.builder.vendor` is `codex`: `claude`, `reason == "opposite"`, `crossed is True`; with `claude` exhausted: `codex`, `reason == "not crossed"`, `crossed is False`;
  - a lean job (no `vendors.builder`): the builder is the host, so its reviewer would be the peer;
  - `reviewer-final` with host `claude`: `codex`, `reason == "opposite"`;
  - both vendors exhausted: `vendor is None`, `reason == "exhausted"`;
  - a peer turned off by `vendors[v]["off"]`: treated as unavailable, never chosen.
  And for `quota`: from a rollout file in a temporary `codex_home` (`sessions/2026/10/25/rollout-x.jsonl` whose last event holds `"rate_limits": {"primary": {"used_percent": 42.0, "resets_at": <future epoch>}}`) gives `42.0` and `source == "sessions"`; a past `resets_at` gives `0.0`; a truncated last line is skipped; no file gives `None` and `source == "none"`; `quota(root, "claude")["used_percent"] is None`; a status file under `factory/jobs/*/peer/*.status.json` newer than the rollout wins with `source == "peer"`.
  In `tests/test_state.py`: `test_vendor_records_the_choice_in_the_job` (peer on, builder on `light` with `builder_tiers: ["light"]`: `job["vendors"]["builder"] == {"vendor": "codex", "reason": "builder_tiers"}` and the printed `model`/`effort` equal `models.resolve(repo, "codex", tier="light")`); `test_vendor_down_marks_the_run` (`limit` with `--until` sets `exhausted_until`, `missing` sets `off: true`); `test_run_records_cross` (`write_run(..., cross="on", host="claude")["cross"] == {"on": True, "peer": "codex", "threshold": 80, "builder_tiers": []}`); `test_preflight_reports_the_peer` (with a fake `codex` on `PATH` via `monkeypatch.setenv`, `preflight(..., host="claude")["peer"] == {"vendor": "codex", "found": True}`; host `cursor` has no `peer`).
- [ ] **Step 2: Run them.** `python3 -m pytest tests/test_vendors.py tests/test_state.py -q`. Expected: FAIL.
- [ ] **Step 3: Implement `vendors.py`** (`decide` takes `usage` so it stays pure; `state.vendor` gathers `usage` with `quota` and reads `run`) **and the `state.py` additions and subcommands.** `decide` for a builder: candidate is the peer when the job's tier is in `builder_tiers`, else the host; it moves to the other vendor when the candidate is exhausted, off, or at or over the threshold while the other is none of these; when neither is usable, `vendor` is None. Codex `resets_at` (epoch seconds) is stored as ISO 8601 UTC.
- [ ] **Step 4: Run the suite and the validator.** Expected: PASS, exit 0.
- [ ] **Step 5: Commit** `feat: state.py decides which vendor runs each agent, and reads the Codex margin`.

### Task 3: The peer runner

**Repo:** clay-kit
**Tier:** careful
**Depends:** none
**Files:** `plugins/clay/scripts/peer.py`, `tests/test_peer.py`
**Docs:** none: read through reference/peer.md, written in Task 5
**Accept:** 1. `start` returns at once and the runner writes `<role>-r<N>.status.json` when the CLI ends. 2. `wait` reports `done` or `failed` with the errors of spec section 2, tokens, ms, session id and Codex rate limits. 3. Commands match spec section 2 and never carry a bypass flag.
**Verify:** `python3 -m pytest tests -q && python3 scripts/validate.py`

**Interfaces:**
- Produces, in `peer.py`:
  - `LIMIT_PATTERNS = ("usage limit", "rate limit", "limit reached", "quota")`, `AUTH_PATTERNS = ("not logged in", "please log in", "unauthorized", "authentication")`, `TIMEOUTS = {"builder": 3600}`, `DEFAULT_TIMEOUT = 1200`.
  - `agent_tools(role: str) -> list[str]`: the `tools:` of `<plugin root>/agents/<role>.md` frontmatter (plugin root is the folder above `scripts/`), `[]` when there is none.
  - `build_command(vendor: str, cwd: str, write: str, model: str | None, effort: str | None, resume: str | None, tools: list[str], last_message: str) -> list[str]`.
  - `classify(vendor: str, returncode: int, output: str, rate_limits: dict | None) -> str | None`.
  - `parse_output(vendor: str, output: str) -> dict` with `session_id`, `tokens`, `rate_limits`.
  - `start(root, job: str, role: str, round_no: int, vendor: str, cwd: str, write: str, prompt_file: str, model=None, effort=None, resume=None, limit_seconds: int | None = None) -> dict` and `wait(root, job: str, run: str, timeout: int = 300) -> dict`.
  - CLI: `peer.py start ... [--limit-seconds <n>]` and `peer.py wait ...` as in spec section 2; `_run` is the internal runner subcommand. Task 5 names these commands.

- [ ] **Step 1: Write the failing tests** in `tests/test_peer.py`, with a fixture that writes fake `codex` and `claude` executables (small Python scripts) into a `tmp_path/bin` put first on `PATH` with `monkeypatch.setenv`; each fake reads its prompt from stdin, writes the file the prompt names, and prints what its mode env var asks for:
  - `test_codex_run_is_done_with_usage`: the fake prints JSONL with `{"type": "thread.started", "thread_id": "T1"}`, a `turn.completed` with `usage` `{"input_tokens": 100, "output_tokens": 20}` and a `rate_limits` event at 42%; `wait` gives `state == "done"`, `session_id == "T1"`, `tokens == 120`, `rate_limits["used_percent"] == 42.0`, `ms > 0`.
  - `test_claude_run_is_done_with_usage`: the fake prints `{"session_id": "S1", "is_error": false, "usage": {"input_tokens": 50, "output_tokens": 5}}`; `tokens == 55`, `rate_limits is None`.
  - `test_errors_are_classified`: parametrized: a fake that exits 1 with "You've hit your usage limit" gives `limit`; with "Not logged in" gives `auth`; with "boom" gives `exit`; a Codex `used_percent` of 100 with exit 1 gives `limit`.
  - `test_missing_cli`: no fake on `PATH` gives `failed`, `missing`.
  - `test_timeout_kills_the_process_group`: a fake that starts a `sleep 60` child and sleeps; `limit_seconds=1` gives `timeout`, and the child's pid (written by the fake to a file) no longer exists.
  - `test_lost_runner`: a status-less run whose recorded pid is dead gives `failed`, `lost`.
  - `test_wait_returns_running_at_its_timeout`: a fake that sleeps 5 s, `wait(timeout=1)` gives `state == "running"`.
  - `test_commands`: `build_command("codex", ...)` contains `exec`, `-C`, `--add-dir`, `-s`, `workspace-write`, `--json`, `-o` and ends with `-`; with `resume="T1"` it contains `resume` and `T1`; `build_command("claude", ..., tools=["Read", "Bash"])` contains `-p`, `--output-format`, `json`, `--add-dir`, `--allowedTools`, `Read,Bash` and `--permission-mode`, `acceptEdits`; no command contains `dangerously`.
  - `test_builder_tools_include_bash`: `"Bash" in agent_tools("builder")`.
- [ ] **Step 2: Run them.** `python3 -m pytest tests/test_peer.py -q`. Expected: FAIL.
- [ ] **Step 3: Implement `peer.py`.** `start` spawns `python3 peer.py _run ...` with `start_new_session=True` and records its pid in `<run>.status.json` as `{"state": "running", "pid"}`; `_run` runs the CLI in its own process group with the prompt on stdin, kills the group (`os.killpg`) at the limit, writes the CLI output to `<run>.log` and the final status. `wait` polls the status file every second.
- [ ] **Step 4: Run the suite and the validator.** Expected: PASS, exit 0.
- [ ] **Step 5: Commit** `feat: peer.py runs an agent through the other vendor's CLI`.

### Task 4: The vendor in the record

**Repo:** clay-kit
**Tier:** medium
**Depends:** 2
**Files:** `plugins/clay/scripts/state.py`, `tests/test_state.py`
**Docs:** none: the record documents itself in the plan
**Accept:** 1. `after-agent` and `agent` take `vendor` and `session_id` and store them on the role. 2. The execution record shows `vendor:model`, `review not crossed` and a `First round` column.
**Verify:** `python3 -m pytest tests -q && python3 scripts/validate.py`

**Interfaces:**
- Consumes: `job["vendors"]`, `job["crossed"]` (Task 2).
- Produces: `record_agent(..., vendor: str = "", session_id: str = "")`; the record header `| Task | Tier | Models | Rounds | First round | Reviews | Decision | Findings | Notes | Tokens | Agent time |`.

- [ ] **Step 1: Write the failing tests** in `tests/test_state.py`: `test_after_agent_records_the_vendor` (`record_agents` with `{"role": "builder", "model": "gpt-5.5", "vendor": "codex", "session_id": "T1", ...}` stores both on `agents.builder`); `test_execution_record_shows_vendor_crossing_and_first_round` (a job with `agents.builder` on `codex:gpt-5.5`, `agents.code` on `claude:sonnet`, `crossed: false`, and `round-1/review-code.md` starting `VERDICT: CHANGES`: the row contains `claude:sonnet/codex:gpt-5.5`, `review not crossed` and `code CHANGES`; a job without vendors shows bare model names as today). Update the tests that match the old header.
- [ ] **Step 2: Run them.** Expected: FAIL.
- [ ] **Step 3: Implement** the two fields in `record_agent`/`record_agents` and the record changes; `First round` reads line one of every `round-1/review-*.md`, empty for a lean or short-path job without them.
- [ ] **Step 4: Run the suite and the validator.** Expected: PASS, exit 0.
- [ ] **Step 5: Commit** `feat: the execution record keeps each agent's vendor and the first round`.

### Task 5: The peer part of the reference

**Repo:** clay-kit
**Tier:** medium
**Depends:** 2, 3, 4
**Files:** `plugins/clay/reference/peer.md`, `plugins/clay/reference/README.md`, `plugins/clay/reference/start.md`, `plugins/clay/reference/job-loop.md`, `plugins/clay/reference/completion.md`, `plugins/clay/skills/factory-run/SKILL.md`, `plugins/clay/skills/factory-task/SKILL.md`, `plugins/clay/README.md`, `tests/test_orchestrator_text.py`
**Docs:** `plugins/clay/README.md` (one paragraph and the `cross` keys), `plugins/clay/reference/peer.md` (new)
**Accept:** 1. `peer.md` tells the orchestrator spec sections 1 to 3 in steps: decide, start, wait, record, fail over, stop. 2. The run skills read it only when the peer is on. 3. The start's word budget still holds.
**Verify:** `python3 -m pytest tests -q && python3 scripts/validate.py`

- [ ] **Step 1: Write the failing tests** in `tests/test_orchestrator_text.py`: `test_peer_part_names_its_commands` (`peer.md` contains `state.py vendor`, `peer.py start`, `peer.py wait`, `vendor-down`, `--resume`, `review not crossed` and `vendor: null`); `test_run_skills_read_the_peer_part_only_when_on` (both SKILLs name `peer.md` and do not list `reference/peer.md` among their first reads); `test_loop_asks_the_vendor_when_the_peer_is_on` (`job-loop.md` steps 2, 4 and 6 and `completion.md` step 1 each contain `peer.md`); `test_start_offers_the_peer` (`start.md` contains `--cross` and `--host <host>` on the preflight); `test_every_part_of_the_reference_is_listed_in_the_core_and_exists` covers `peer.md` once it is in `reference/README.md`.
- [ ] **Step 2: Run them.** Expected: FAIL.
- [ ] **Step 3: Write `peer.md`** (decide with `state.py vendor`; a peer agent: write the prompt file, `peer.py start`, `peer.py wait` until it ends, then `after-agent` with `vendor` and `session_id`, then the same checks as a native agent; resume a peer builder with `--resume <session_id>`, else start a fresh one; round 3's escalated builder and a rework builder ask `state.py vendor` again; errors as spec section 3; `vendor: null` stops the run as `auto` pace does), add its row to `reference/README.md`, the preflight `--host` and the mode question's peer choice to `start.md`, one clause each in `job-loop.md` steps 2, 4, 6 and `completion.md` step 1, the conditional read in both SKILLs, and the README paragraph.
- [ ] **Step 4: Run the suite and the validator.** Expected: PASS, exit 0, the word budget included.
- [ ] **Step 5: Commit** `feat: the reference tells the run how to work with the peer vendor`.
