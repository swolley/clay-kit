# Factory Tool Implementation Plan

**Goal:** Build `plugins/factory/` in the swolley-kit marketplace: design skills, a plan-to-merge orchestrator with routed reviewers, tiers, isolation modes, resume and a dashboard.

**Architecture:** Prompts (skills and agents) hold the behavior; three small Python helpers hold the parts that must be deterministic and testable (plan parsing, reviewer routing, repository validation). Hand-off between agents is through files, as in the spec.

**Tech Stack:** Markdown skills and agents, Python 3 (standard library, pytest for tests), static HTML/JS dashboard, git worktrees.

**Spec:** `docs/superpowers/specs/2026-10-13-factory-design.md`

**Compatibility note.** Spec and plan locations (`docs/superpowers/{specs,plans}/`), file name patterns (`YYYY-MM-DD-<topic>...md`) and the plan syntax (`### Task N:` headings, `- [ ]` / `- [x]` / `- [-]` steps) deliberately follow superpowers. This is for compatibility with projects built with that tool, so their specs and plans keep working with this tool unchanged. Do not rename these conventions without recording the break in the spec.

## Global Constraints

- Licenses: repo is MIT, `Copyright (c) 2026 swolley`; derived MIT text keeps the source notice in `plugins/factory/NOTICE.md`; nothing from `zazencodes` is copied, closely paraphrased or reused as HTML or code.
- No hard dependency on `superpowers`, `savvy-progress` or any other plugin; no file under `plugins/factory/` may invoke a `superpowers:` skill.
- Every skill and agent file references `STYLE.md` and does not restate it.
- Agent output: first line machine-readable (`VERDICT: PASS|CHANGES`, `STATUS: READY|BLOCKED`, `APPROVE|ESCALATE`).
- No emojis and no em-dashes in any file. Code and docs in English.
- The tool never pushes to a remote.
- A tool installed on its own must not read paths outside its folder.

## Review Focus

- A plan with no `Tier`/`Repo` fields (a plain superpowers plan) must parse and run with defaults, not fail.
- A cancelled step `- [-]` must not make a task look open.
- Plan field lines must never be counted as steps by the parser.
- A diff touching only docs or config must select only `code` and no UI/UX/security reviewer.
- A path matching several routing rules must yield each reviewer once.
- Resuming with a missing worktree must end in `needs-human`, not in a recreated branch.

---

### Task 1: Repository scaffold and validator

**Repo:** swolley-kit
**Tier:** light
**Depends:** none
**Files:** `.claude-plugin/marketplace.json`, `plugins/factory/.claude-plugin/plugin.json`, `.gitignore`, `README.md`, `plugins/factory/NOTICE.md`, `scripts/validate.py`, `tests/test_validate.py`
**Accept:** 1. `python3 scripts/validate.py` exits 0 on the scaffold. 2. It exits 1 and names the file when a skill lacks `name`/`description` frontmatter, a manifest is invalid JSON, a plugin file references `superpowers:`, or a plugin file lacks a `STYLE.md` reference (skills and agents only). 3. `.gitignore` ignores `factory/jobs/`. 4. It fails if any of `run`, `task`, `status`, `approve`, `rework` lacks `disable-model-invocation: true` or if `brainstorm` or `plan` sets it.
**Verify:** `python3 -m pytest tests/test_validate.py -v`

- [ ] **Step 1: Write failing tests** in `tests/test_validate.py` using `tmp_path` fixtures: `test_valid_scaffold_passes`, `test_bad_json_fails_and_names_file`, `test_skill_without_description_fails`, `test_superpowers_reference_fails`, `test_missing_style_reference_fails`, `test_command_skills_must_disable_model_invocation`, `test_brainstorm_and_plan_must_allow_model_invocation`.
- [ ] **Step 2: Run the tests; expect failure** (`scripts/validate.py` missing).
- [ ] **Step 3: Implement `validate(root: Path) -> list[str]` and a `main()` returning 0/1** in `scripts/validate.py`; each returned string is `<relative path>: <problem>`.
- [ ] **Step 4: Create the scaffold files.** `marketplace.json` follows the claude-kit shape (`name: swolley-kit`, `owner`, `metadata.description`, `plugins[]` with `name`, `source: ./plugins/factory`, `description`, `version: 0.1.0`, `category: skill`). `plugin.json` has name, description, version, author, license MIT. `NOTICE.md` lists superpowers and claude-kit (files added later) and states zazencodes is inspiration only, linking `licenses/README.md`.
- [ ] **Step 5: Run tests and `python3 scripts/validate.py`; expect pass.**
- [ ] **Step 6: Commit** `feat: scaffold marketplace and validator`.

### Task 2: Plan parser

**Repo:** swolley-kit
**Tier:** medium
**Depends:** 1
**Files:** `plugins/factory/scripts/factory_plan.py`, `tests/test_factory_plan.py`, `tests/fixtures/plan-superset.md`, `tests/fixtures/plan-legacy.md`
**Accept:** 1. `parse_plan(text) -> Plan` returns tasks from `### Task N:` headings (also Phase, Step, Milestone, Wave, as the user's `plan-status` does). 2. Field lines (`**Tier:**` and the rest) are never steps. 3. `- [x]` done, `- [ ]` open, `- [-]` cancelled; a task is done when it has at least one step and no open step. 4. Missing fields get defaults (`tier: medium`, `repo` from an argument, `depends: []`, `accept` from step texts) and are listed in `defaults_applied`. 5. Lines inside code fences are ignored. 6. CLI `python3 plugins/factory/scripts/factory_plan.py <file> [--repo NAME]` prints JSON.
**Verify:** `python3 -m pytest tests/test_factory_plan.py -v`; then run the CLI on `/home/swolley/Scaricati/marco/laraplate-stack/docs/superpowers/plans/2026-06-17-ai-assist.md` and read the output.

**Interfaces:**
- Produces: `Step(state: Literal["open","done","cancelled"], text: str)`; `Task(number: int, title: str, repo: str, tier: str, depends: list[int], files: list[str], constraints: str, accept: list[str], verify: str, steps: list[Step], defaults_applied: list[str])` with property `done: bool`; `Plan(title: str, tasks: list[Task])`; `parse_plan(text: str, default_repo: str = "") -> Plan`.

- [ ] **Step 1: Write failing tests**: `test_superset_fields_parsed`, `test_field_lines_not_steps` (a task with 3 fields and 2 steps has `len(steps) == 2`), `test_cancelled_step_not_open`, `test_task_without_steps_is_not_done`, `test_legacy_plan_gets_defaults` (asserts `tier == "medium"` and `"tier" in defaults_applied`), `test_checkbox_in_code_fence_ignored`.
- [ ] **Step 2: Run; expect failure.**
- [ ] **Step 3: Implement `parse_plan`** line by line with a fence toggle; field lines matched by `^\*\*(Repo|Tier|Depends|Files|Constraints|Accept|Verify):\*\*\s*(.*)$`.
- [ ] **Step 4: Run tests; expect pass.**
- [ ] **Step 5: Run the CLI on the real plan** named in Verify and confirm the open/done counts agree with `bash /home/swolley/Scaricati/marco/laraplate-stack/plan-status` for that plan; note any divergence in the commit message.
- [ ] **Step 6: Commit** `feat: add superset plan parser`.

### Task 3: Reviewer routing

**Repo:** swolley-kit
**Tier:** medium
**Depends:** 1
**Files:** `plugins/factory/routing.md`, `plugins/factory/scripts/route.py`, `tests/test_route.py`
**Accept:** 1. `routing.md` is a markdown table `| glob | reviewer |` with reviewers among `ui`, `ux`, `security`. 2. `route(paths, rules)` always includes `code`, includes each other reviewer once if any path matches, and returns them in fixed order `code, security, ux, ui`. 3. Docs-only and config-only diffs return `["code"]`. 4. CLI reads paths from stdin and prints a JSON list.
**Verify:** `python3 -m pytest tests/test_route.py -v`

**Interfaces:**
- Produces: `Rule(glob: str, reviewer: str)`; `load_rules(path: Path) -> list[Rule]`; `route(paths: list[str], rules: list[Rule]) -> list[str]`.

- [ ] **Step 1: Write failing tests**: `test_docs_only_returns_code`, `test_vue_file_adds_ui_and_ux`, `test_auth_path_adds_security`, `test_multiple_matches_deduplicated`, `test_order_is_fixed`, `test_load_rules_ignores_header_and_blank_lines`.
- [ ] **Step 2: Run; expect failure.**
- [ ] **Step 3: Implement** with `fnmatch` on forward-slash paths; `**` handled by translating to a regex.
- [ ] **Step 4: Write `routing.md`** with generic defaults (frontend extensions and `components/`, `views/`, `pages/` for ui and ux; `auth`, `middleware`, `policies`, `routes`, `migrations`, lockfiles and manifests for security) and a note that repos override it by adding `factory/routing.md`.
- [ ] **Step 5: Run tests; expect pass.**
- [ ] **Step 6: Commit** `feat: add reviewer routing`.

### Task 4: Shared contracts (STYLE, tiers) and host research

**Repo:** swolley-kit
**Tier:** careful
**Depends:** 1
**Files:** `plugins/factory/STYLE.md`, `plugins/factory/tiers.md`, `docs/hosts.md`
**Accept:** 1. `STYLE.md` states the four rules of spec section 2 in under 60 lines. 2. `docs/hosts.md` lists, for Claude Code and Codex, the structured-question tool name, how subagent model and effort are set, and plugin manifest format, each with the documentation URL it was read from; anything not found is marked `unverified`. 3. `docs/hosts.md` also records how each host spells a plugin skill command and the flag that disables model invocation. 4. `tiers.md` maps the five tiers to model and effort and explains the `fable` fallback. 5. `STYLE.md` names the question tool for each host only where `docs/hosts.md` has it verified.
**Verify:** `python3 scripts/validate.py`; read both files for length and for unverified claims.

- [ ] **Step 1: Research each host's documentation** for the facts above (including the command spelling and the invocation flag); record URLs and exact names. Do not infer a name that is not documented.
- [ ] **Step 2: Write `docs/hosts.md`.**
- [ ] **Step 3: Write `STYLE.md`** (questions via native tool with numbered-text fallback; default plain-language explanation with deeper mode on request; compact agent output with machine-readable first line; chat language from repo instructions).
- [ ] **Step 4: Write `tiers.md`** as a table `tier | use | model | effort` plus the selection rule (cheapest that works first time; next up when unsure; `fable` only when clearly needed).
- [ ] **Step 5: Run the validator; expect pass.**
- [ ] **Step 6: Commit** `docs: add style contract, tiers and host notes`.

### Task 5: Skill `brainstorm`

**Repo:** swolley-kit
**Tier:** careful
**Depends:** 4
**Files:** `plugins/factory/skills/brainstorm/SKILL.md`, `plugins/factory/NOTICE.md`
**Accept:** 1. Keeps the spike, bounded and architectural paths and the hard gate before implementation. 2. Questions go through the native tool per `STYLE.md`, one at a time, recommended option first. 3. Bounded work produces a short chat design and no file. 4. Spec location follows the repo's own instructions and defaults to `docs/superpowers/specs/YYYY-MM-DD-<topic>-design.md`. 5. No instruction to invoke any `superpowers:` skill; the terminal state is "invoke `plan` of this tool". 6. `NOTICE.md` records that the text derives from superpowers `brainstorming` v6.4.2 (MIT, Jesse Vincent), with the file path.
**Verify:** `python3 scripts/validate.py`; run the skill by hand in a scratch repo with one bounded and one architectural request and check the gate and the question tool behavior.

- [ ] **Step 1: Write the skill** starting from the superpowers text as a base and rewriting it to be shorter and to follow `STYLE.md`. Remove the visual companion and the process-flow digraph unless the skill is unclear without them.
- [ ] **Step 2: Update `NOTICE.md`.**
- [ ] **Step 3: Run the validator; expect pass.**
- [ ] **Step 4: Manual run** as described in Verify; record the outcome in the commit body.
- [ ] **Step 5: Commit** `feat: add brainstorm skill`.

### Task 6: Skill `plan`

**Repo:** swolley-kit
**Tier:** careful
**Depends:** 2, 4
**Files:** `plugins/factory/skills/plan/SKILL.md`, `plugins/factory/NOTICE.md`
**Accept:** 1. Instructs writing plans to `docs/superpowers/plans/YYYY-MM-DD-<feature>.md` in the superset format of spec section 3.2, including the compatibility reason in one sentence. 2. Includes the per-task fields and defaults rule. 3. Ends by asking the user to review the plan, never by choosing an execution method of another tool; execution is `/factory run`. 4. A plan the skill produces for a sample spec passes `factory_plan.py` with no `defaults_applied` other than intentional ones. 5. `description` lets the model start it after an approved design (model invocation enabled). 6. `NOTICE.md` records derivation from superpowers `writing-plans`.
**Verify:** `python3 scripts/validate.py`; generate a plan from `docs/superpowers/specs/2026-10-13-factory-design.md` section 4.8 and run `python3 plugins/factory/scripts/factory_plan.py` on it.

- [ ] **Step 1: Write the skill** (task right-sizing, step granularity, self-review kept; rest shortened).
- [ ] **Step 2: Update `NOTICE.md`.**
- [ ] **Step 3: Run the validator; expect pass.**
- [ ] **Step 4: Generate and parse a sample plan** as in Verify; fix the skill text if the parser reports unexpected defaults.
- [ ] **Step 5: Commit** `feat: add plan skill`.

### Task 7: Agents `builder`, `reviewer-code`, `approver`

**Repo:** swolley-kit
**Tier:** careful
**Depends:** 4
**Files:** `plugins/factory/agents/builder.md`, `plugins/factory/agents/reviewer-code.md`, `plugins/factory/agents/approver.md`
**Accept:** 1. Each file has frontmatter `name`, `description`, `tools`, and references `STYLE.md`. 2. `builder` writes only `build.md` plus commits; first line `STATUS: READY|BLOCKED`; contains short sections for test-first work, systematic debugging and verification before claiming done; updates `filemap.md` when files move. 3. `reviewer-code` first line `VERDICT:`; treats the builder report as a claim to verify against the diff. 4. `builder` treats reviewer findings as claims to verify before acting (fix what is confirmed, answer in `build.md` with evidence what is not), never as orders to apply blindly. 5. `approver` first line `APPROVE` or `ESCALATE`; escalation list matches spec 4.4, including repo-declared licensing and ownership boundaries. 6. No agent file names a model; the orchestrator sets model and effort from the task tier, and the reviewers and approver use fixed settings read from `tiers.md`.
**Verify:** `python3 scripts/validate.py`; read each file for the three first-line contracts.

- [ ] **Step 1: Write `builder.md`** with the job-folder and worktree path convention, branch check, acceptance-criteria evidence in `build.md`, commit rules (explicit paths, one-line messages), rework and resume inputs.
- [ ] **Step 2: Write `reviewer-code.md`** (correctness, reuse, conventions of the repo, tests present and meaningful).
- [ ] **Step 3: Write `approver.md`** (reads everything in the job folder and the diff, spot-checks one criterion, checks merge conflicts with `git merge-tree --write-tree`).
- [ ] **Step 4: Run the validator; expect pass.**
- [ ] **Step 5: Commit** `feat: add builder, code reviewer and approver`.

### Task 8: Agents `reviewer-ui`, `reviewer-ux`, `reviewer-security`

**Repo:** swolley-kit
**Tier:** medium
**Depends:** 7
**Files:** `plugins/factory/agents/reviewer-ui.md`, `plugins/factory/agents/reviewer-ux.md`, `plugins/factory/agents/reviewer-security.md`
**Accept:** 1. Same frontmatter and first-line contract as `reviewer-code`. 2. `reviewer-ui` and `reviewer-ux` look at the running app only when the repo's instructions give a dev-server command, and otherwise review the diff; neither requires a specific browser tool. 3. `reviewer-security` covers access control, input, XSS, data exposure, secrets, abuse and dependencies, blocking only on problems the change introduces.
**Verify:** `python3 scripts/validate.py`

- [ ] **Step 1: Write the three files**, each at most 50 lines, each with its Findings format `path:line`, cause, fix.
- [ ] **Step 2: Run the validator; expect pass.**
- [ ] **Step 3: Commit** `feat: add ui, ux and security reviewers`.

### Task 9: Command skills and orchestrator reference

**Repo:** swolley-kit
**Tier:** heavy
**Depends:** 2, 3, 7, 8
**Files:** `plugins/factory/reference/orchestrator.md`, `plugins/factory/skills/{run,task,status,approve,rework}/SKILL.md`
**Accept:** 1. Five skills, one per command, each with `disable-model-invocation: true`, an `argument-hint`, and a body of at most 30 lines that reads `reference/orchestrator.md` for the shared logic. 2. Preconditions of spec 4.2, mode choice of 4.3 through the native question tool, job loop of 4.4 including routing through `plugins/factory/scripts/route.py`, tiers of 4.5, completion of 4.6, state of 4.7. 3. Resume table of 4.8 implemented as written, using `scripts/factory_plan.py` for task state. 4. The orchestrator is the only writer of `job.json`. 5. Optional progress calls to `mcp__savvy-progress__progress` and `step` guarded by "if the tool exists", skipped silently otherwise. 6. Never pushes; never resets user changes. 7. Defines the finish step: when all tasks are done, in isolated mode it asks the user (native question tool) how the integration branch reaches main (merge, pull request prepared but not pushed, keep the branch, discard) and performs only the chosen local action.
**Verify:** `python3 scripts/validate.py`; Task 11 exercises it end to end.

**Interfaces:**
- Consumes: `factory_plan.parse_plan` and `route.route` through their CLIs; agent first-line contracts from Tasks 7 and 8.
- Produces: `factory/jobs/<job-id>/job.json` with the fields listed in spec 4.7, read by the dashboard.

- [ ] **Step 1: Write `reference/orchestrator.md`** in the order of the spec sections, with the job-id pattern `NNN-<slug>` and the prompt convention `Job folder: ... Worktree: ... Branch: ...` for every agent.
- [ ] **Step 2: Add the resume procedure** as a numbered list mirroring the table, including the `needs-human` outcomes for missing or diverged worktree.
- [ ] **Step 3: Add the current-branch mode rules** (clean tree, branch confirmation, `main` warning, sequential only, stop on failure without reset).
- [ ] **Step 4: Add the progress integration paragraph.**
- [ ] **Step 5: Write the five thin command skills.**
- [ ] **Step 6: Run the validator; expect pass.**
- [ ] **Step 7: Commit** `feat: add command skills and orchestrator reference`.

### Task 10: Dashboard

**Repo:** swolley-kit
**Tier:** medium
**Depends:** 9
**Files:** `plugins/factory/factory/dashboard.html`, `tests/fixtures/jobs/` (sample `job.json` files)
**Accept:** 1. Original code, single file, no build step, no external requests. 2. Groups jobs by plan then repo; shows stage, tier, round and only the job's selected reviewers. 3. `needs-human` jobs are visually distinct. 4. Reads `jobs/<id>/job.json` by polling every 2 seconds; renders the markdown files of a job on click as plain preformatted text. 5. Works served by `python3 -m http.server` from `factory/`.
**Verify:** serve `tests/fixtures/jobs` copied under a temp `factory/jobs/`, open the page and check each point; no console errors.

- [ ] **Step 1: Create fixture jobs**: one `build`, one `review` with two reviewers selected, one `needs-human`, one `merged`, across two plans.
- [ ] **Step 2: Implement the page**; discover jobs from the directory listing of `jobs/`, as the static server provides it.
- [ ] **Step 3: Open it in the built-in browser; verify grouping, reviewer chips and the `needs-human` highlight.**
- [ ] **Step 4: Commit** `feat: add dashboard`.

### Task 11: End-to-end verification on a fixture repo

**Repo:** swolley-kit
**Tier:** heavy
**Depends:** 9, 10
**Files:** `tests/e2e/make_fixture.sh`, `tests/e2e/CHECKLIST.md`
**Accept:** 1. `make_fixture.sh <dir>` creates a git repo with an `AGENTS.md` (setup, test and lint commands), a tiny app with a backend file and a UI file, and a three-task plan: backend-only, UI, and one touching auth that must escalate. 2. Running `/factory run` on it in a Claude Code session satisfies `CHECKLIST.md`: backend job has no ui/ux reviewer, UI job has them, auth job ends `needs-human`, nothing is pushed. 3. Killing the run at each stage and rerunning resumes without a duplicate branch. 4. A plain superpowers plan (`plan-legacy.md`) runs with reported defaults. 5. Current-branch mode runs sequentially and commits on the confirmed branch.
**Verify:** follow `tests/e2e/CHECKLIST.md` and tick each line with the observed result.

- [ ] **Step 1: Write `make_fixture.sh` and run it into the scratch directory;** verify the repo's own test command passes before any job runs.
- [ ] **Step 2: Write `CHECKLIST.md`**: scenarios (routing, escalation, resume at each stage, legacy plan, current-branch mode), with the expected observation per line.
- [ ] **Step 3: Execute the checklist** in a real session; record failures as follow-up fixes in the owning task's files and rerun.
- [ ] **Step 4: Commit** `test: add end-to-end fixture and checklist`.

### Task 12: Codex manifest and README

**Repo:** swolley-kit
**Tier:** medium
**Depends:** 4, 11
**Files:** `plugins/factory/.codex-plugin/plugin.json` (only if verified), `README.md`, `plugins/factory/README.md`
**Accept:** 1. The Codex manifest is added only if `docs/hosts.md` has a verified format and per-agent model and effort support; otherwise the README says Codex support is pending and why. 2. Root README: purpose, install steps for the marketplace, tool list, license and credits (inspiration-only wording for zazencodes). 3. Tool README: commands, workflow, modes, plan format and the compatibility reason, requirements.
**Verify:** `python3 scripts/validate.py`; follow the README install steps in a clean Claude Code profile.

- [ ] **Step 1: Decide Codex support** from `docs/hosts.md`; write the manifest or the pending note.
- [ ] **Step 2: Write both READMEs.**
- [ ] **Step 3: Re-check the three source licenses** against `licenses/README.md` and update the date if unchanged.
- [ ] **Step 4: Run the validator and the install check; expect pass.**
- [ ] **Step 5: Commit** `docs: add readmes and host support note`.
