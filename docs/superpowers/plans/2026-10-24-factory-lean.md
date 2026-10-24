# Factory Lean Tasks Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let simple tasks be built by the session and proved by their own checks, with the final branch review as their independent reading, while every other task keeps the full loop.

**Architecture:** `state.py` decides eligibility (`preflight`), records lean jobs (`begin-job --lean`), gates them (`lean-check`), sends them back to the full loop (`promote`) and shows them in the record; `adhoc` learns `verify=`. A new reference part, `reference/lean.md`, tells the orchestrator how a lean job runs, and the other parts point to it.

**Tech Stack:** Python 3 standard library, pytest, Markdown reference parts and skills.

**Spec:** `docs/superpowers/specs/2026-10-24-factory-lean-design.md`

## Global Constraints

- No emojis and no em-dashes in any file. Code and docs in English. Every skill references `STYLE.md`.
- Python: standard library only. Tests run with `python3 -m pytest tests -q`; `python3 scripts/validate.py` exits 0 after every task; `node --test tests/mod/` stays green.
- Eligible means: tier `light` or `medium`, declared `Files` whose routing selects only `code`, declared `Accept` and `Verify`.
- More than 8 eligible tasks in a plan sets `long: true`.
- A run with at least one lean job always runs the final review, also for one task and for an ad hoc plan.

## Review Focus

- A lean job whose session never ran its `Verify` through `state.py verify`: `lean-check` must not land it (Task 2).
- A lean job whose last check passed but whose code changed afterwards (stale run): `lean-check` must not land it (Task 2).
- A task whose `Files` lists a sensitive path among ordinary ones (`app/util.py`, `app/auth/session.py`): not eligible, reason names `security` (Task 1).
- `verify=` text with a quoted command containing spaces and a following task text: the command is the quoted part only, the rest is the task (Task 3).
- A promoted job: it routes and reviews like any job, and its record says `promoted: <reason>`, never `lean` in Reviews (Task 2).

---

### Task 1: Eligibility in preflight

**Repo:** clay-kit
**Tier:** medium
**Depends:** none
**Files:** `plugins/clay/scripts/state.py`, `tests/test_state.py`
**Docs:** none: read by the orchestrator through reference/lean.md, written in Task 4
**Accept:** 1. `lean_eligibility` returns `(True, "")` for an eligible task and `(False, reason)` otherwise, with the reasons below. 2. `preflight` with a plan adds `lean` and `lean_reason` to each task, and `lean_count` and `long` to the output. 3. Without a plan `preflight` is unchanged.
**Verify:** `python3 -m pytest tests -q && python3 scripts/validate.py`

**Interfaces:**
- Consumes: `route(paths, rules)` and `load_rules(path)` from `route.py`; the routing table chosen as `route_job` chooses it (the repo's `factory/routing.md`, else the plugin's).
- Produces: `lean_eligibility(task, rules) -> tuple[bool, str]` in `state.py`. Reasons, checked in this order: `"tier <tier>"`, `"no Files"` (no declared `Files`, or none that reads as a path: first word, contains a slash), `"Files route to <lens>[, <lens>]"`, `"no Accept"`, `"no Verify"`. `preflight(root, plan_file, repo_name)` output: `plan.tasks[i]["lean"]`, `plan.tasks[i]["lean_reason"]`, `lean_count: int`, `long: bool`. Task 2 and Task 4 rely on these names.

- [ ] **Step 1: Write the failing tests** in `tests/test_state.py`, with a helper that writes a one-task plan from fields:
  - `test_a_light_task_with_files_accept_and_verify_is_eligible`: `light`, Files `` `app/util.py` ``, Accept, Verify `` `pytest -q` `` gives `(True, "")`.
  - `test_eligibility_reasons`: parametrized over `careful` gives `"tier careful"`; no Files gives `"no Files"`; Files `` `app/util.py`, `app/auth/session.py` `` gives `"Files route to security"`; no Accept gives `"no Accept"`; no Verify gives `"no Verify"`.
  - `test_preflight_marks_each_task_and_counts_the_eligible`: on the `repo` fixture plan, task 1 has no `Verify`, so `lean is False` and `lean_reason == "no Verify"`; after adding `**Verify:** \`pytest -q\`` to task 1, `lean is True`, `lean_count == 1`, `long is False`.
  - `test_preflight_flags_a_long_lean_plan`: a plan of 9 eligible tasks gives `lean_count == 9` and `long is True`.
- [ ] **Step 2: Run them.** `python3 -m pytest tests/test_state.py -q`. Expected: FAIL.
- [ ] **Step 3: Implement `lean_eligibility` and the `preflight` additions in `state.py`.** Parse the plan once with `parse_plan` for the `Task` objects; `describe_plan` keeps producing the dicts the fields are added to. Extract the routing-table choice of `route_job` into `_rules(root, table=None)` and use it in both.
- [ ] **Step 4: Run the suite and the validator.** Expected: PASS, exit 0.
- [ ] **Step 5: Commit** `feat: preflight says which tasks can run lean, and why not`.

### Task 2: Lean jobs: record, gate, promote

**Repo:** clay-kit
**Tier:** careful
**Depends:** 1
**Files:** `plugins/clay/scripts/state.py`, `tests/test_state.py`
**Docs:** none: read by the orchestrator through reference/lean.md, written in Task 4
**Accept:** 1. `begin-job --lean` records `lean: true` and `verify`, the task's commands. 2. `lean-check` lands only a code-only, not risky change whose every `Verify` command has a current, passing latest run and fewer than two failed runs. 3. `promote` clears `lean` and records the reason. 4. The execution record shows `lean` for a lean job and `promoted: <reason>` for a promoted one. 5. `final-diff` reports `lean`, the number of lean jobs of the plan.
**Verify:** `python3 -m pytest tests -q && python3 scripts/validate.py`

**Interfaces:**
- Consumes: `_rules`, `lean_eligibility` (Task 1); `read_checks`, `tree_state`, `changed`, `final_diff` (existing).
- Produces in `state.py`:
  - `new_job(..., lean: bool = False)` and `begin_job(..., lean: bool = False)`; `job.json` always gets `verify: list[str]` (the backticked commands of the task's `Verify`, else the whole field, else `[]`) and `lean: bool`. CLI: `begin-job ... --lean`, `new-job ... --lean`.
  - `lean_check(root, job_id: str) -> dict`: `{"land": True}` or `{"land": False, "promote": reason}`. Reasons in this order: `"routes to <lens>[, <lens>]"`, `"risky"`, `"checks failed twice: <cmd>"`, `"no recorded run: <cmd>"`, `"stale run: <cmd>"`, `"failing run: <cmd>"`. CLI `lean-check <job>`, exit 0 either way.
  - `promote(root, job_id: str, reason: str) -> dict`: sets `lean: False`, `promoted: reason`, leaves the stage. CLI `promote <job> --reason TEXT`.
  - `execution_record`: Reviews cell `lean` for a job with `lean`; Notes gains `lean`, or `promoted: <reason>`.
  - `final_diff` output gains `lean: int`.

- [ ] **Step 1: Write the failing tests** in `tests/test_state.py`:
  - `test_begin_job_lean_records_lean_and_the_verify_commands`: task 1 with `**Verify:** \`pytest -q\` and \`ruff check\``; `begin_job(..., lean=True)` gives `job["lean"] is True`, `job["verify"] == ["pytest -q", "ruff check"]`.
  - `test_lean_check_lands_a_clean_code_change_with_a_passing_current_check`: change `app/util.py`, `run_check(..., "true")` with verify `["true"]`; `lean_check == {"land": True}`.
  - `test_lean_check_without_a_recorded_run_does_not_land` and `test_lean_check_on_a_stale_run_does_not_land` (change the file after the run).
  - `test_lean_check_on_a_failing_run_does_not_land` (verify `["false"]`).
  - `test_lean_check_promotes_after_two_failed_runs`: verify `["test -f ok"]`, two runs without the file, then create `ok` (outside the tracked tree) and run again so the last run passes; reason starts with `checks failed twice`.
  - `test_lean_check_promotes_a_change_that_routes_to_security` (change `app/auth/session.py`): reason `routes to security`.
  - `test_promote_clears_lean_and_route_then_reviews_it`: after `promote`, `route_job` gives `reviewers` with `security` and `lite is False`.
  - `test_execution_record_shows_lean_and_promoted_jobs`: one lean job landed, one promoted job landed; their rows show `lean` and `promoted: routes to security`.
  - `test_final_diff_reports_the_lean_jobs`.
  - `test_cli_lean_check_and_promote`.
- [ ] **Step 2: Run them.** Expected: FAIL.
- [ ] **Step 3: Implement** the interfaces above. `lean_check` reads the job's change with `changed` and routes it with `_rules`; a check is current when its `state` equals `tree_state` now; failed runs are counted per command over all records.
- [ ] **Step 4: Run the suite and the validator.** Expected: PASS, exit 0.
- [ ] **Step 5: Commit** `feat: lean jobs land through lean-check, or are promoted to the full loop`.

### Task 3: verify= for ad hoc tasks

**Repo:** clay-kit
**Tier:** light
**Depends:** 2
**Files:** `plugins/clay/scripts/state.py`, `tests/test_state.py`
**Docs:** none: read through start.md and factory-task, written in Task 4
**Accept:** 1. `adhoc --text "tier=light verify=\"pytest -q tests\" Fix the slug"` writes `**Verify:** \`pytest -q tests\`` and the task text `Fix the slug`. 2. `verify=` takes a double-quoted or backticked command, or a single word. 3. `tier=` and `verify=` may come in either order. 4. The output gains `verify` (the command or `""`).
**Verify:** `python3 -m pytest tests -q && python3 scripts/validate.py`

**Interfaces:**
- Produces: `adhoc_plan(root, text) -> dict` with the new key `verify: str`; the plan it writes declares `**Verify:**` when given. Task 4 relies on it.

- [ ] **Step 1: Write the failing tests** `test_adhoc_takes_a_quoted_verify_command`, `test_adhoc_takes_verify_before_or_after_tier`, `test_adhoc_takes_a_one_word_verify`, `test_adhoc_without_verify_declares_none` (no `**Verify:**` line, `verify == ""`).
- [ ] **Step 2: Run them.** Expected: FAIL.
- [ ] **Step 3: Implement** the leading-options loop in `adhoc_plan`: repeat matching `tier=(\S+)` or `verify=("[^"]*"|`[^`]*`|\S+)` at the start of the text.
- [ ] **Step 4: Run the suite and the validator.** Expected: PASS, exit 0.
- [ ] **Step 5: Commit** `feat: an ad hoc task can declare its check with verify=`.

### Task 4: The lean reference and the commands that use it

**Repo:** clay-kit
**Tier:** light
**Depends:** 3
**Files:** `plugins/clay/reference/lean.md`, `plugins/clay/reference/job-loop.md`, `plugins/clay/reference/start.md`, `plugins/clay/reference/completion.md`, `plugins/clay/reference/inline.md`, `plugins/clay/reference/orchestrator.md`, `plugins/clay/skills/factory-run/SKILL.md`, `plugins/clay/skills/factory-task/SKILL.md`, `plugins/clay/README.md`, `tests/test_orchestrator_text.py`
**Docs:** `plugins/clay/README.md`
**Accept:** 1. `reference/lean.md` covers eligibility, the choice at the start, the lean job (build by the session, `lean-check`, `promote`, landing) and how it differs from `inline`. 2. `factory-run` takes `lean` and `full`, `factory-task` takes `lean`; both read `lean.md`. 3. `start.md` adds the lean choice to the mode question, the session-model note and the resume rule. 4. `completion.md` runs the final review whenever a lean job exists, also for one task and ad hoc. 5. The validator passes.
**Verify:** `python3 -m pytest tests -q && python3 scripts/validate.py && node --test tests/mod/`

**Interfaces:**
- Consumes: `preflight` fields (Task 1), `begin-job --lean`, `lean-check`, `promote`, `final-diff` `lean` (Task 2), `adhoc` `verify` (Task 3).

- [ ] **Step 1: Write the failing text tests** in `tests/test_orchestrator_text.py`:
  - `test_lean_reference_names_its_commands`: `read("reference/lean.md")` contains `lean-check`, `promote`, `begin-job`, `--lean`, `lean_reason`, `long`, `session's model`, `inline`.
  - `test_run_and_task_read_the_lean_part`: both SKILL.md files mention `lean.md` and the word `lean` in `argument-hint`; `factory-run` also `full`.
  - `test_completion_reviews_any_run_with_a_lean_job`: `completion.md` contains `lean` within the final review step and says it runs for one task and ad hoc plans then.
  - `test_resume_sends_a_ready_lean_job_to_lean_check`: `start.md` contains `lean-check`.
- [ ] **Step 2: Run them.** Expected: FAIL.
- [ ] **Step 3: Write `reference/lean.md`** from spec sections 1 to 3, and edit the other parts: `job-loop.md` step 2 sends a job with `lean` to `lean.md`; `start.md` mode question and the `lean`/`full` arguments, the line on the session's model, the resume rule; `completion.md` step 1's skip rule; `inline.md` one sentence on the difference; `orchestrator.md` parts table row for `lean.md`; both SKILL.md files read it and take the words; README Workflow paragraph.
- [ ] **Step 4: Run the suite, the validator and the mod tests.** Expected: PASS, exit 0.
- [ ] **Step 5: Commit** `feat: factory-run and factory-task run eligible tasks lean`.
