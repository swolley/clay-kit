# Factory backlog Implementation Plan

> **For agentic workers:** run with `/factory-run`; steps use checkbox syntax.

**Goal:** a Python port of laraplate's `plan-status` shipped in the clay plugin as `/factory-backlog` and as a standalone script, using one plan parser.

**Architecture:** `plugins/clay/scripts/plan_status.py` holds discovery, scanners and renderers; `factory_plan.py` stays the only plan parser and gains what the backlog needs.

**Tech Stack:** Python 3 standard library, pytest, the clay mod in TypeScript for the pane line.

**Spec:** `docs/superpowers/specs/2026-10-13-factory-backlog-design.md`

## Global Constraints

- Source of behaviour: `/home/swolley/Scaricati/marco/laraplate-stack/laraplate/scripts/plan-status.php` and its test `scripts/tests/plan-status-test.sh`. Read them; do not modify them.
- Standard library only; Python 3.10 syntax; no import from the plugin other than `factory_plan`.
- Default output is open work only; `--all` shows the rest.
- Option names exactly as in the spec.
- Nothing laraplate-specific in names, paths or tests (use invented fixtures); the laraplate parity run is a separate, skippable test.

## Review Focus

- A plan with front matter `status: completed` and unchecked boxes is reported as an inconsistency and counted done.
- A plan with no checkboxes and no status is `NO BOXES`, never open, never an inconsistency.
- A task whose steps are all cancelled reads as cancelled, and cancelled steps count as resolved.
- Two repositories under one root, one nested inside the other, are each reported once with their own plans.
- `--root` pointing at a folder without any plan or spec prints a clear message and exits 0.

---

### Task 1: Parser additions

**Repo:** swolley-kit
**Tier:** careful
**Files:**
- Modify: `plugins/clay/scripts/factory_plan.py`
- Test: `tests/test_factory_plan.py`
**Constraints:** existing callers (`resolve.py`, `state.py`) keep working; no behaviour change for them
**Accept:** 1. `Plan` exposes per-task counts of open, done and cancelled steps. 2. A task whose steps are all cancelled has state `cancelled`. 3. The status banner line (`> **Status:** ...` or `Status: ...` near the top) is exposed as `Plan.banner`. 4. The plan date comes from the file name when it starts with `YYYY-MM-DD`.
**Verify:** `.venv/bin/python -m pytest tests -q`

- [ ] **Step 1: Write failing tests** for counts, all-cancelled state, banner and date in `tests/test_factory_plan.py`
- [ ] **Step 2: Run them; expect failure** on the missing attributes
- [ ] **Step 3: Implement `Task.counts() -> tuple[int, int, int]`, `Task.state`, `Plan.banner`, `plan_date(name: str) -> str`** in `factory_plan.py`
- [ ] **Step 4: Run the whole suite; expect pass**
- [ ] **Step 5: Commit** `feat: parser exposes step counts, cancelled state, banner and plan date`

### Task 2: Discovery and plan scan

**Repo:** swolley-kit
**Tier:** careful
**Depends:** 1
**Files:**
- Create: `plugins/clay/scripts/plan_status.py`
- Create: `tests/test_plan_status.py`
**Constraints:** port `Workspace` and `PlanParser` of the PHP tool, using `factory_plan.parse_plan`
**Accept:** 1. `discover(root) -> dict[str, str]` maps repository name to relative path ('' for the root). 2. `scan_plans(root, repos, evidence=True) -> list[dict]` returns, per plan, the keys `repo, file, path, date, title, front_matter_status, status_banner, tasks, total_steps, checked_steps, state, inconsistency`. 3. State and inconsistency follow the spec.
**Verify:** `.venv/bin/python -m pytest tests/test_plan_status.py -q`

- [ ] **Step 1: Write failing tests** for nested repositories, status precedence, `NO BOXES`, inconsistency and cancelled tasks, with invented fixtures
- [ ] **Step 2: Run them; expect failure**
- [ ] **Step 3: Implement `discover` and `scan_plans`** in `plan_status.py`
- [ ] **Step 4: Run them; expect pass**
- [ ] **Step 5: Commit** `feat: backlog discovers repositories and scans plans`

### Task 3: Spec and TODO scanners

**Repo:** swolley-kit
**Tier:** medium
**Depends:** 2
**Files:**
- Modify: `plugins/clay/scripts/plan_status.py`
- Test: `tests/test_plan_status.py`
**Accept:** 1. `scan_specs(root, repos, plans) -> list[dict]` gives each spec a state `planned`, `plan_uncited`, `unplanned` or `reference`. 2. `scan_todos(root, repos, limit) -> list[dict]` finds `TODO|FIXME|XXX|@todo` markers in code comments only and honors the exclusions of the PHP tool.
**Verify:** `.venv/bin/python -m pytest tests/test_plan_status.py -q`

- [ ] **Step 1: Write failing tests** for the four spec states and for markers inside strings that must not count
- [ ] **Step 2: Run them; expect failure**
- [ ] **Step 3: Implement `scan_specs` and `scan_todos`** porting `SpecScanner` and `TodoScanner`
- [ ] **Step 4: Run them; expect pass**
- [ ] **Step 5: Commit** `feat: backlog scans specs and code markers`

### Task 4: Renderers and command line

**Repo:** swolley-kit
**Tier:** medium
**Depends:** 3
**Files:**
- Modify: `plugins/clay/scripts/plan_status.py`
- Test: `tests/test_plan_status.py`
**Constraints:** default is open work only; `--all` adds the rest; table width must not break on a narrow terminal
**Accept:** 1. `render_table`, `render_json` and `render_html` take the scan result and the options. 2. `main(argv) -> int` accepts every option of the spec. 3. A root with nothing to scan prints a message and exits 0.
**Verify:** `.venv/bin/python -m pytest tests/test_plan_status.py -q`

- [ ] **Step 1: Write failing tests** for the default open-only table, `--all`, `--format json` keys, `--repos`, `--summary` and the empty root
- [ ] **Step 2: Run them; expect failure**
- [ ] **Step 3: Implement the three renderers and `main`**
- [ ] **Step 4: Run them; expect pass**
- [ ] **Step 5: Commit** `feat: backlog renderers and command line`

### Task 5: Parity with the PHP tool

**Repo:** swolley-kit
**Tier:** careful
**Depends:** 4
**Files:**
- Create: `tests/test_plan_status_parity.py`
**Constraints:** skipped when the laraplate checkout is not at `PLAN_STATUS_PARITY_ROOT`; compares `--format json --no-evidence` of both tools
**Accept:** 1. Every plan has the same state and the same step counts in both tools, or is listed in an explicit, commented allow-list of decided differences. 2. The test prints the differences it finds when it fails.
**Verify:** `PLAN_STATUS_PARITY_ROOT=/home/swolley/Scaricati/marco/laraplate-stack/laraplate .venv/bin/python -m pytest tests/test_plan_status_parity.py -q`

- [ ] **Step 1: Write the parity test** with the skip and the allow-list mechanism, empty allow-list
- [ ] **Step 2: Run it; expect failures listing each difference**
- [ ] **Step 3: For each difference decide, with the user if unclear, whether the port or the allow-list changes**, and fix `plan_status.py` or `factory_plan.py` accordingly
- [ ] **Step 4: Run it; expect pass**
- [ ] **Step 5: Commit** `test: backlog parity with the PHP plan-status`

### Task 6: Command, orchestrator, pane and docs

**Repo:** swolley-kit
**Tier:** medium
**Depends:** 5
**Files:**
- Create: `plugins/clay/skills/factory-backlog/SKILL.md`
- Modify: `plugins/clay/reference/orchestrator.md`, `plugins/clay/hooks/register.tsx`, `plugins/clay/hooks/model.ts`, `plugins/clay/README.md`, `plugins/clay/NOTICE.md`, `scripts/validate.py`
- Test: `tests/test_validate.py`, `tests/mod/model.test.ts`
**Accept:** 1. `/factory-backlog` is manual only and passes `validate.py` and `claude plugin validate`. 2. The orchestrator tells agents to run it before choosing work. 3. The pane shows the open-plan and unplanned-spec counts. 4. `NOTICE.md` records the origin of the port. 5. The README explains how to use `plan_status.py` outside the plugin.
**Verify:** `.venv/bin/python -m pytest tests -q && node --test tests/mod/ && bash scripts/typecheck-mod.sh`

- [ ] **Step 1: Write failing tests** for the new skill's manual-only rule and for the pane count in `model.ts`
- [ ] **Step 2: Run them; expect failure**
- [ ] **Step 3: Add the skill, the orchestrator paragraph, the pane line, the NOTICE row and the README section**
- [ ] **Step 4: Run the whole verification; expect pass**
- [ ] **Step 5: Commit** `feat: factory-backlog command, pane line and docs`
