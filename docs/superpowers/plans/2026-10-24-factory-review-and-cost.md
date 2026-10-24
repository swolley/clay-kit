# Factory Review and Cost Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the factory review a plan's branch as a whole, try a stronger builder before handing a job to a person, and spend one agent less on ordinary jobs.

**Architecture:** `state.py` owns every new piece of bookkeeping (`route` for the wider short path, `escalate`, `final-diff`, `final-verdict`, the Final review section of `close-plan`); `models.py` owns the new agent's model; the reference parts and agent files tell the orchestrator and the agents what to do with them.

**Tech Stack:** Python 3 standard library, pytest, Markdown agents and reference parts.

**Spec:** `docs/superpowers/specs/2026-10-24-factory-review-and-cost-design.md`

## Global Constraints

- No emojis and no em-dashes in any file. Code and docs in English. Every agent references `STYLE.md` and carries the plugin root sentence before its first `##` heading.
- Python: standard library only. Tests run with `.venv/bin/python -m pytest tests -q`; `python3 scripts/validate.py` exits 0 after every task.
- Rounds stay at most three per job. `fable` is never reached by escalation.
- Risky means: the routing selected the `security` lens, or the job's current tier is `heavy` or `fable`.
- The tier arrow in the execution record is written `light→medium`.

## Review Focus

- A lite job whose approver wrote `decision.md` but no `review-code.md`: `verdicts` must report `code` missing, never pass the round (Task 1).
- `escalate` run twice for the same job (a resumed run): the second call changes nothing and prints the same tier (Task 2).
- `final-diff` on a run state written before this change (no `base`): `ok: false` with a reason, exit 1, no traceback (Task 4).
- `final-diff` in isolated mode when the integration branch no longer exists: `ok: false` naming the branch (Task 4).
- `close-plan` on a run that had no final review (one task, or skipped): no `### Final review` section, and the rest of the Delivery status unchanged (Task 4).

---

### Task 1: Wider short path

**Repo:** clay-kit
**Tier:** medium
**Depends:** none
**Files:** `plugins/clay/scripts/state.py`, `plugins/clay/agents/approver.md`, `plugins/clay/reference/job-loop.md`, `plugins/clay/reference/inline.md`, `plugins/clay/tiers.md`, `tests/test_state.py`, `tests/test_orchestrator_text.py`
**Docs:** `plugins/clay/tiers.md`
**Accept:** 1. `route` sets `lite` for a non-risky `light` or `medium` job whose routing selects only `code`, whatever its size, and never for `careful`, `heavy`, `fable` or a job with any other lens. 2. A lite round has its own `round-N/` folder and `diff.patch`, `reviewers: ["code"]`, `rerun: []`, and the stage `approve`. 3. `verdicts` on a lite job reads `round-N/review-code.md`. 4. The approver of a lite job writes `review-code.md` first and stops on `CHANGES`. 5. The execution record notes `short path` for a lite job.
**Verify:** `.venv/bin/python -m pytest tests -q && python3 scripts/validate.py`

**Interfaces:**
- Produces: `route_job(root, job_id, table=None) -> dict` keeps its keys; for a lite job `reviewers == ["code"]`, `rerun == []`, `lite is True`, `diff` is `<job folder>/round-<N>/diff.patch`. `job.json` of a lite job holds `lite: true`, `reviews: {"code": "pending"}`. Task 2 relies on `route_job` reading the job's current `tier`.

- [ ] **Step 1: Write the failing tests** in `tests/test_state.py`. Replace `test_light_small_change_takes_the_short_path_without_reviewers` and `test_light_but_large_change_keeps_its_reviewers` with:
  - `test_a_light_change_of_any_size_takes_the_short_path`: task 1 (light), 80 lines in `app/util.py`; `out["lite"] is True`, `out["reviewers"] == ["code"]`, `out["rerun"] == []`; `job["stage"] == "approve"`, `job["round"] == 1`, `job["reviews"] == {"code": "pending"}`.
  - `test_a_medium_change_takes_the_short_path`: write `**Tier:** medium` into task 1 of the plan before `new`; `lite is True`.
  - `test_careful_and_risky_jobs_keep_their_reviewers`: task 2 (careful) touching `app/util.py` gives `lite is False`; task 1 touching `app/auth/session.py` gives `lite is False` and `"security" in out["reviewers"]`.
  - `test_verdicts_read_the_approvers_code_review_on_the_short_path`: after a lite route, no file: `check_verdicts` gives `ok False`, `missing == ["code"]`, even with a `decision.md` present; with `round-1/review-code.md` = `VERDICT: CHANGES`: `all_pass False`, `job["reviews"] == {"code": "CHANGES"}`.
  - Update `test_the_short_path_gets_its_diff_in_the_job_folder` (rename `..._in_its_round_folder`): `out["diff"] == str(<job folder>/"round-1"/"diff.patch")`.
  - `test_execution_record_notes_the_short_path`: a lite job landed and closed shows `short path` in its Notes cell.
- [ ] **Step 2: Run them.** `.venv/bin/python -m pytest tests/test_state.py -q`. Expected: the new tests FAIL.
- [ ] **Step 3: Change `route_job` and `check_verdicts` in `state.py`.** `lite = not risky and job["tier"] in ("light", "medium") and reviewers == ["code"]` with `risky = "security" in reviewers or job["tier"] in ("heavy", "fable")`. The lite branch raises `round`, sets `build_round`, writes `round-N/diff.patch` like the review branch, then sets stage `approve`. Remove `LITE_MAX_FILES` and `LITE_MAX_LINES`; in `changed`, an unreadable untracked file counts as one line. `check_verdicts` reads `["code"]` when `job.get("lite")`, else `rerun` as today. In `execution_record`, append `short path` to the notes of a job with `lite`.
- [ ] **Step 4: Run the tests.** Expected: PASS, including the existing `_findings` test whose job 2 has no reviews.
- [ ] **Step 5: Write the failing text test** in `tests/test_orchestrator_text.py`: `test_short_path_has_no_size_limit_and_the_approver_writes_the_code_review`: `"30 lines"` not in `reference()` nor in `read("tiers.md")`; `"review-code.md"` and `"CHANGES"` in the `## Lite jobs` part of `read("agents/approver.md")`.
- [ ] **Step 6: Edit the text.** `agents/approver.md` "Lite jobs": the job is light or medium and not risky; write `<job folder>/round-<N>/review-code.md` (N is the final round in the prompt) with `VERDICT: PASS` or `VERDICT: CHANGES` on line one and `## Issues` numbered, as the code reviewer does; on `CHANGES` stop without `decision.md`. `job-loop.md` step 3 states the new rule; step 6 says that after a lite approver the orchestrator runs `state.py verdicts` in its own step: `all_pass` reads `decision.md` as today, `CHANGES` goes to step 5. `tiers.md` "Short path": new rule, saving one agent run, no size limit, no seconds figure. `inline.md`: the short path wording matches.
- [ ] **Step 7: Run the suite and the validator.** Expected: PASS, exit 0.
- [ ] **Step 8: Commit** `feat: the short path covers light and medium code-only jobs, and its approver can ask for changes`.

### Task 2: Model escalation in the last round

**Repo:** clay-kit
**Tier:** medium
**Depends:** 1
**Files:** `plugins/clay/scripts/state.py`, `plugins/clay/reference/job-loop.md`, `plugins/clay/tiers.md`, `tests/test_state.py`, `tests/test_orchestrator_text.py`
**Docs:** `plugins/clay/tiers.md`
**Accept:** 1. `escalate` moves `light` to `medium`, `medium` to `careful`, `careful` to `heavy`, records `escalated_from` and prints the new tier's model and effort for the host. 2. `heavy` and `fable` are left as they are. 3. A second call changes nothing. 4. The execution record shows `light→medium`. 5. Step 5 of the job loop spawns a fresh builder for an escalated round 3.
**Verify:** `.venv/bin/python -m pytest tests -q && python3 scripts/validate.py`

**Interfaces:**
- Consumes: `route_job` reads `job["tier"]` (Task 1); `models.resolve(root, host, tier=...)`.
- Produces: `ESCALATION = {"light": "medium", "medium": "careful", "careful": "heavy"}` and `escalate(root, job_id: str, host: str) -> dict` in `state.py`, returning `{"escalated": True, "tier", "escalated_from", "model", "effort"}` or `{"escalated": False, "tier"}`. CLI: `state.py escalate <job> --host <host> --root <repo>`, exit 0, exit 2 with `{"error"}` on a `ModelsError`.

- [ ] **Step 1: Write the failing tests** in `tests/test_state.py`:
  - `test_escalate_moves_the_tier_one_step_and_prints_its_model`: task 1 (light): `escalate(repo, id, "claude") == {"escalated": True, "tier": "medium", "escalated_from": "light", "model": "sonnet", "effort": "medium"}`; `job["tier"] == "medium"`, `job["escalated_from"] == "light"`.
  - `test_escalate_twice_changes_nothing_the_second_time`: second call returns `escalated: True`, same `tier` `medium`, and the job is unchanged.
  - `test_heavy_and_fable_are_not_escalated`: a job with `tier` set to `heavy` (write it into `job.json`) gives `{"escalated": False, "tier": "heavy"}`; the same for `fable`.
  - `test_an_escalated_job_leaves_the_short_path_at_careful`: medium task 1 escalated to `careful`, then `route_job` gives `lite is False`.
  - `test_execution_record_shows_the_escalated_tier`: a landed job escalated from `light` shows `light→medium` in the Tier cell.
  - `test_cli_escalate`: `state.main(["escalate", id, "--host", "claude", "--root", str(repo)]) == 0` and the JSON has `tier`.
- [ ] **Step 2: Run them.** Expected: FAIL.
- [ ] **Step 3: Implement `escalate` and its subcommand in `state.py`.** An already escalated job (`escalated_from` present) returns its current tier, model and effort with `escalated: True` and writes nothing. In `execution_record`, the Tier cell is `f"{escalated_from}→{tier}"` when the job has `escalated_from`.
- [ ] **Step 4: Run the tests.** Expected: PASS.
- [ ] **Step 5: Write the failing text test** `test_round_three_escalates_to_a_fresh_builder`: `reference()` contains `state.py escalate` and `fresh builder`; `read("tiers.md")` contains `escalat`.
- [ ] **Step 6: Edit `job-loop.md` step 5 and `tiers.md`.** Step 5: CHANGES after round 1 resumes the builder; CHANGES after round 2 runs `state.py escalate <job> --host <host>`: `escalated: true` spawns a fresh builder with the printed model and effort and the prompt `<paths> Build round 3. Escalated from <tier>: every round's reviews are in round-*/. Read task.md, build.md and them, then continue from the branch as it stands.`, recorded under `builder`; `escalated: false` resumes as today. CHANGES after round 3 writes `decision.md` `ESCALATE` as today. `tiers.md`: a short section on escalation and that risk follows the current tier.
- [ ] **Step 7: Run the suite and the validator.** Expected: PASS, exit 0.
- [ ] **Step 8: Commit** `feat: round three is built by a fresh builder one tier up`.

### Task 3: The final reviewer agent and its model

**Repo:** clay-kit
**Tier:** light
**Depends:** 2
**Files:** `plugins/clay/agents/reviewer-final.md`, `plugins/clay/scripts/models.py`, `plugins/clay/tiers.md`, `plugins/clay/reference/hosts.md`, `plugins/clay/README.md`, `tests/test_models.py`
**Docs:** `plugins/clay/tiers.md`, `plugins/clay/README.md`
**Accept:** 1. `state.py model --host claude --agent reviewer-final` prints `sonnet`/`high`, with `--risky` `opus`/`high`. 2. `models.json` may map `reviewer-final` and `reviewer-final-risky`. 3. The agent file passes `validate.py` and has `effort: high`. 4. `tiers.md` lists both rows and `test_models` still finds its table equal to `AGENT_DEFAULTS`.
**Verify:** `.venv/bin/python -m pytest tests -q && python3 scripts/validate.py`

**Interfaces:**
- Produces: `AGENT_DEFAULTS["reviewer-final"] == ("sonnet", "high")`, `AGENT_DEFAULTS["reviewer-final-risky"] == ("opus", "high")`; `resolve(..., agent="reviewer-final", risky=True)` allowed. The agent writes `factory/jobs/_runs/<plan-stem>-final.md`, or `-final-2.md` when its prompt says `Scope: fix`, line one `VERDICT: PASS` or `VERDICT: CHANGES`, then `## Findings` numbered, each with `file:line` and why it matters. Tasks 4 and 5 rely on these file names and on the verdict line.

- [ ] **Step 1: Write the failing tests** in `tests/test_models.py`: `test_final_reviewer_defaults` asserts both resolutions above; extend the bad-input case so `risky=True` with `agent="reviewer-code"` still raises.
- [ ] **Step 2: Run them.** Expected: FAIL.
- [ ] **Step 3: Add the two entries to `AGENT_DEFAULTS` and let `risky` apply to `approver` and `reviewer-final`** (`"<agent>-risky"`), with the error text naming both.
- [ ] **Step 4: Write `agents/reviewer-final.md`.** Frontmatter `name: reviewer-final`, a one-line `description`, `tools: Read, Grep, Glob, Bash, Write`, `effort: high`. Body: the plugin root sentence, STYLE.md, what the prompt gives (plan path, spec path, the patch path, the job folders, `Scope: fix` with the previous findings file on a recheck), what to read, what to look for (from spec section 3, and nothing a per-task review already covers), the file it writes and its format; on `Scope: fix` it judges each previous finding against the fix only and lists the ones still open.
- [ ] **Step 5: Update `tiers.md`** (both rows in "The other agents", and that the risky choice follows any risky job of the run), `hosts.md` line 23 role list, and the README agent list.
- [ ] **Step 6: Run the suite and the validator.** Expected: PASS, exit 0.
- [ ] **Step 7: Commit** `feat: a final reviewer agent with its own model`.

### Task 4: Final diff, final verdict and the Final review record

**Repo:** clay-kit
**Tier:** careful
**Depends:** 3
**Files:** `plugins/clay/scripts/state.py`, `tests/test_state.py`
**Docs:** none: script bookkeeping, described in the reference parts by Task 5
**Accept:** 1. `state.py run` records `base` once. 2. `final-diff` writes the patch for both modes and, with `--fix`, from the recorded head. 3. `final-diff` reports `risky`. 4. `final-verdict` stores verdict, findings, fix job and agent usage, and fails on a missing file or verdict line. 5. `close-plan` writes `### Final review` and a final review row in the execution record only when the run has one.
**Verify:** `.venv/bin/python -m pytest tests -q && python3 scripts/validate.py`

**Interfaces:**
- Consumes: the file names and verdict line of Task 3.
- Produces in `state.py`:
  - `write_run` keeps an existing `base` and otherwise sets it to `git rev-parse HEAD` of `root`.
  - `final_diff(root, plan_stem: str, fix: bool = False) -> dict`: `{"ok": True, "patch", "base", "head", "commits", "risky"}` or `{"ok": False, "reason"}`. Isolated: from `git merge-base <integration> <base>` to `<integration>`, git run in `root`. Current branch: from `base` to `HEAD`. `fix`: from `final.head` to the current head, patch `<stem>-final-2.patch`, head stored as `final.fix_head`; otherwise `<stem>-final.patch` and `final.head`. `risky` is true when any job of the plan had `security` in `reviewers` or a tier `heavy` or `fable`. The patch starts with `# Plan <stem>, final review`, `# Base <sha>, head <sha>, mode <mode>`, `# Commits:`, `# Files (added, removed, path):`, then the diff.
  - `final_verdict(root, plan_stem: str, fix: bool, agent: dict, fix_job: str | None = None) -> dict`: reads `<stem>-final.md` or `-final-2.md`; `{"ok", "verdict", "findings"}`; stores under `run["final"]["review"]` or `["recheck"]` `{"verdict", "findings", "agent"}`, and `fix_job` under `run["final"]["fix_job"]` when given. `ok` is false when the file or a `VERDICT: PASS|CHANGES` first line is missing.
  - CLI: `final-diff --root --plan [--fix]` and `final-verdict --root --plan [--fix] [--fix-job ID] --agent JSON`; both exit 1 when `ok` is false.
  - `delivery_status` appends `### Final review` after Divergences when `run.get("final", {}).get("review")`: the first verdict with its count, `Fix: job <id>` when present, then `Left open:` with the numbered findings of the last review if its verdict is `CHANGES`, else `none`. `execution_record` adds a row `| final | | <model> | <reviews run> | <verdict(s)> | | | | <tokens> | <s> |` and counts it in the totals.

- [ ] **Step 1: Write the failing tests** in `tests/test_state.py` (current-branch `repo` fixture plus one isolated case built with `git branch` and `git commit` on an integration branch):
  - `test_run_records_its_base_once`: `write_run` twice; `base` equals the first HEAD after a new commit.
  - `test_final_diff_current_branch_spans_the_run`: commit a change after `write_run`; patch contains `# Plan`, the commit subject and the diff line; `ok`, `head` recorded under `final.head`.
  - `test_final_diff_isolated_spans_the_integration_branch` and `test_final_diff_isolated_without_the_branch_is_not_ok` (reason names the branch).
  - `test_final_diff_without_base_is_not_ok`: a run state with no `base`; `ok False`; CLI exit 1.
  - `test_final_diff_fix_starts_from_the_recorded_head`: second patch holds only the later commit, file `-final-2.patch`.
  - `test_final_diff_is_risky_when_any_job_was`: a job with `reviewers` containing `security`.
  - `test_final_verdict_stores_the_verdict_and_fails_without_one`: `VERDICT: CHANGES` with two numbered findings gives `findings 2`; a file whose first line is prose gives `ok False`; a missing file gives `ok False`.
  - `test_close_plan_writes_the_final_review`: review `CHANGES` with findings, fix job `004-fix`, recheck `CHANGES` with one finding: section has `Fix: job 004-fix` and that finding under `Left open:`; the execution record has a `| final |` row.
  - `test_close_plan_without_a_final_review_writes_no_section`.
- [ ] **Step 2: Run them.** Expected: FAIL.
- [ ] **Step 3: Implement `write_run`'s `base`, `final_diff`, `final_verdict`, the two subcommands, and the record changes in `delivery_status` and `execution_record`.** Reuse `git()` and `run_path()`; numbered findings are counted with the regex `_findings` uses.
- [ ] **Step 4: Run the suite and the validator.** Expected: PASS, exit 0.
- [ ] **Step 5: Commit** `feat: final-diff and final-verdict, and the plan records the final review`.

### Task 5: Completion runs the final review

**Repo:** clay-kit
**Tier:** light
**Depends:** 4
**Files:** `plugins/clay/reference/completion.md`, `plugins/clay/reference/orchestrator.md`, `plugins/clay/README.md`, `tests/test_orchestrator_text.py`
**Docs:** `plugins/clay/README.md`
**Accept:** 1. `completion.md` starts with the final review: when it is skipped, `final-diff`, `reviewer-final` with `--risky` when `final-diff` printed `risky: true`, `final-verdict`, the one fix job and the recheck, and what goes to the user. 2. The documentation pass, close and check follow, renumbered. 3. `orchestrator.md`'s files table lists the `_runs/<plan>-final*` files.
**Verify:** `.venv/bin/python -m pytest tests -q && python3 scripts/validate.py`

**Interfaces:**
- Consumes: `final-diff`, `final-verdict` (Task 4); the agent and its files (Task 3).

- [ ] **Step 1: Write the failing text test** `test_completion_runs_the_final_review_first`: in `read("reference/completion.md")`, `final-diff` appears before `Documentation pass`; the text contains `reviewer-final`, `final-verdict`, `--fix`, `Scope: fix`, `one task` and `ad hoc`.
- [ ] **Step 2: Run it.** Expected: FAIL.
- [ ] **Step 3: Write the step in `completion.md`** following spec section 3: skip for an ad hoc plan and a plan of one task, and say so when `final-diff` is not ok; spawn as `hosts.md` says with the model from `state.py model --agent reviewer-final [--risky]`; `CHANGES` runs `state.py adhoc --text "tier=medium Fix the final review findings in factory/jobs/_runs/<plan-stem>-final.md"` through the Job loop, then `final-diff --fix`, the recheck with `Scope: fix`, `final-verdict --fix --fix-job <id>`; what the recheck lists goes to the user, one line per finding. Add the files to the `orchestrator.md` table and one sentence to the README run section.
- [ ] **Step 4: Run the suite and the validator.** Expected: PASS, exit 0.
- [ ] **Step 5: Commit** `feat: a finished plan gets a review of its whole branch before it closes`.
