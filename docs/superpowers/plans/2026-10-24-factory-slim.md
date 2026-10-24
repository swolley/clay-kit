# Factory Slim Reference Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Cut what `factory-run` and `factory-task` read before their first step to at most 4,400 words on every host, without losing a rule.

**Architecture:** Four structural cuts to the Markdown reference and the agents: one interface reviewer instead of three, inline mode removed, `hosts.md` split into a shared part and one part per host, and the trim of what other parts or `state.py` already say. A text test caps the words read at the start.

**Tech Stack:** Markdown reference parts, skills and agents; Python 3 standard library (`models.py`, `validate.py`), pytest; TypeScript mod (`hooks/model.ts`) with `node --test`.

**Spec:** `docs/superpowers/specs/2026-10-24-factory-slim-design.md`

> **Amended 2026-10-25:** the word cap is 4,800, not 4,400: the spec's cuts reached about 4,600, and compressing real rules further was ruled out by the user.

## Global Constraints

- No emojis and no em-dashes in any file. Code and docs in English. Every skill references `STYLE.md`.
- Wording that is not cut stays as it is: no terse "caveman" rewrite.
- Every sentence removed is either stated in one other place (name it in the commit body) or done by a script.
- `factory-run` and `factory-task` read at most 4,400 words at the start on every host: their SKILL, the parts their first read lists (`reference/<part>.md`) and `hosts-<host>.md`.
- After every task: `python3 -m pytest tests -q` passes, `python3 scripts/validate.py` exits 0, `node --test tests/mod/` passes.

## Review Focus

- A Codex run that reads `hosts.md` but never the host part loses the thread-limit rule: `hosts.md` must say to read `hosts-<host>.md` right after detecting the host (Task 3).
- A `factory/models.json` that still names `reviewer-ux`, `reviewer-ui` or `reviewer-uiux` must exit 2 with a hint naming `reviewer-interface`, not run on defaults (Task 1).
- A run resumed from before the change has `agents.uiux` (or `ux`, `ui`) in `job.json`: the mod must still show the reviewer's model (Task 1).
- A round whose `rerun` holds only `ui`: one `reviewer-interface` with `Lenses: ui`, which writes only `review-ui.md` (Task 1).
- A user who types `factory-run <plan> inline`: one line saying lean replaced it, then the run goes on as with `lean` (Task 2).

---

### Task 1: One interface reviewer

**Repo:** clay-kit
**Tier:** medium
**Depends:** none
**Files:** `plugins/clay/agents/reviewer-interface.md`, `plugins/clay/agents/reviewer-ux.md`, `plugins/clay/agents/reviewer-ui.md`, `plugins/clay/agents/reviewer-uiux.md`, `plugins/clay/scripts/models.py`, `plugins/clay/tiers.md`, `plugins/clay/reference/job-loop.md`, `plugins/clay/reference/orchestrator.md`, `plugins/clay/reference/hosts.md`, `plugins/clay/hooks/model.ts`, `plugins/clay/README.md`, `tests/test_models.py`, `tests/test_orchestrator_text.py`, `tests/mod/model.test.ts`
**Docs:** `plugins/clay/README.md` (the agents list and the models.json paragraph), `plugins/clay/tiers.md`
**Accept:** 1. `agents/reviewer-interface.md` judges the lenses named on its `Lenses:` line and writes `round-<N>/review-<lens>.md` for each, with its own verdict; the three old agent files are gone. 2. `models.py` knows `reviewer-interface` (sonnet, medium) and rejects the three old keys with a hint. 3. Step 4 of the Job loop spawns one `reviewer-interface` for `ux`, `ui` or both, role `interface`. 4. The mod finds the model under `interface`, then `uiux`.
**Verify:** `python3 -m pytest tests -q && python3 scripts/validate.py && node --test tests/mod/`

**Interfaces:**
- Produces: agent `reviewer-interface` (frontmatter `effort: medium`, tools `Read, Grep, Glob, Bash, Write`); prompt line `Lenses: ux`, `Lenses: ui` or `Lenses: ux ui`; role `interface` in `job.json` `agents`. `AGENT_DEFAULTS["reviewer-interface"] = ("sonnet", "medium")`. Task 3 and Task 4 rely on the name `reviewer-interface` in `hosts.md` and `job-loop.md`.

- [ ] **Step 1: Write the failing tests.**
  - `tests/test_models.py`: replace `test_uiux_is_ux` with `test_interface_reviewer_resolves_on_every_host` (`resolve(tmp_path, host, agent="reviewer-interface")` is `{"model": "sonnet", "effort": "medium", "source": "tiers.md"}` on claude). In `test_bad_input_raises` replace the two `reviewer-uiux` rows with three rows, one per old key, e.g. `({"codex": {"agents": {"reviewer-ux": {"model": "x"}}}}, "codex", {"tier": "light"}, "reviewer-ux is now reviewer-interface")`, and `(None, "codex", {"agent": "reviewer-interface", "risky": True}, "--risky")`. `test_agent_frontmatter_effort` expects `["reviewer-code", "reviewer-interface", "reviewer-spec", "reviewer-security", "approver", "reviewer-final"]`.
  - `tests/test_orchestrator_text.py`: replace `test_a_round_that_needs_both_interface_lenses_spawns_one_combined_reviewer` with `test_interface_lenses_get_one_reviewer`: `job-loop.md` contains `` `reviewer-interface` ``, `Lenses:` and ``role `interface` ``, and no `reviewer-uiux`; the agent file contains `Lenses:`, `review-<lens>.md`, `## ux` and `## ui`; `tiers.md` contains `reviewer-interface` and not `reviewer-uiux`. In `test_agents_read_the_diff_file_and_the_recorded_checks` the agent list is `("reviewer-code", "reviewer-security", "reviewer-interface", "approver")`.
  - `tests/mod/model.test.ts`: `workingNow finds the interface reviewer for either pending lens`: a job with `agents: { interface: { model: 'sonnet', effort: 'medium' } }` and pending `ux`, `ui` gives `'ux, ui · sonnet medium'`; keep the `uiux` test as the old-job case; `roleOf('clay:reviewer-interface')` is `'interface'`.
- [ ] **Step 2: Run them.** `python3 -m pytest tests/test_models.py tests/test_orchestrator_text.py -q && node --test tests/mod/`. Expected: FAIL.
- [ ] **Step 3: Write `agents/reviewer-interface.md`** from the shared frame of `reviewer-ux.md` and `reviewer-ui.md` (inputs, `Diff:`, dev server on the given port, output format), one `## ux` and one `## ui` section holding each file's "What to judge" list verbatim, and the rule: judge only the lenses on the `Lenses:` line, one file per lens, each its own verdict; a prompt without `Lenses:` is answered in the reply and stopped, as a missing `Plugin root:` is. Delete the three old agent files.
- [ ] **Step 4: Update `models.py`:** one `reviewer-interface` entry replaces the three; drop the uiux alias in `resolve`; `_validate` raises `"<where>: unknown agent name (<key> is now reviewer-interface), expected one of ..."` for `reviewer-ux`, `reviewer-ui`, `reviewer-uiux`.
- [ ] **Step 5: Update the text:** `tiers.md` (one row, the uiux paragraph becomes one sentence on `Lenses:`), `job-loop.md` step 4 (when `rerun` holds `ux`, `ui` or both, spawn one `reviewer-interface` with `--agent reviewer-interface`, `Lenses:` and `Port: 5101+10n`, role `interface`; the ui port `5102+10n` goes), the role lists in `job-loop.md` and `orchestrator.md`, `hosts.md` `<role>` list, the README agents list and models.json sentence.
- [ ] **Step 6: Update `hooks/model.ts` `workingNow`:** for role `ui` or `ux`, look up `agents.interface ?? agents.uiux` (and the same in `observed`).
- [ ] **Step 7: Run the suite, the validator and the mod tests.** Expected: PASS, exit 0.
- [ ] **Step 8: Commit** `feat: one interface reviewer judges the ux and ui lenses`.

### Task 2: Remove inline mode

**Repo:** clay-kit
**Tier:** light
**Depends:** 1
**Files:** `plugins/clay/reference/inline.md`, `plugins/clay/reference/orchestrator.md`, `plugins/clay/reference/job-loop.md`, `plugins/clay/reference/lean.md`, `plugins/clay/reference/hosts.md`, `plugins/clay/skills/factory-run/SKILL.md`, `plugins/clay/skills/factory-task/SKILL.md`, `plugins/clay/README.md`, `tests/test_orchestrator_text.py`
**Docs:** `plugins/clay/README.md` (the Workflow paragraph)
**Accept:** 1. `reference/inline.md` is gone and nothing in the plugin names it or `inline` mode. 2. Both skills take `[lean|full]`, and the word `inline` gets one line, "inline was replaced by lean", and runs as `lean`.
**Verify:** `python3 -m pytest tests -q && python3 scripts/validate.py`

- [ ] **Step 1: Write the failing tests** in `tests/test_orchestrator_text.py`: replace `test_inline_mode_keeps_approver_and_reviewers_as_subagents` with `test_inline_mode_is_gone`: `reference/inline.md` does not exist, `"inline.md"` and `"# Inline mode"` are not in `reference()`, and both skills contain `[lean|full]` and `inline was replaced by lean`. In `test_the_parts_a_run_needs_only_sometimes_are_read_when_needed` and `test_lean_reference_names_its_commands`, drop `inline.md` and `"inline"`.
- [ ] **Step 2: Run them.** Expected: FAIL.
- [ ] **Step 3: Remove inline:** delete `reference/inline.md`; its row in the parts table of `orchestrator.md`; the inline sentence of step 5 in `job-loop.md`; "Lean and inline" in `lean.md`; "`inline` mode included" in `hosts.md`; the inline clause of the README Workflow paragraph; in both skills the read of `inline.md`, the argument hint and the Arguments line, plus the sentence for a user who still types `inline`.
- [ ] **Step 4: Run the suite and the validator.** Expected: PASS, exit 0.
- [ ] **Step 5: Commit** `feat: remove inline mode, which lean replaces`.

### Task 3: Hosts, split per host

**Repo:** clay-kit
**Tier:** medium
**Depends:** 2
**Files:** `plugins/clay/reference/hosts.md`, `plugins/clay/reference/hosts-claude.md`, `plugins/clay/reference/hosts-codex.md`, `plugins/clay/reference/hosts-cursor.md`, `plugins/clay/reference/orchestrator.md`, `plugins/clay/reference/start.md`, `plugins/clay/README.md`, `scripts/validate.py`, `tests/test_orchestrator_text.py`, `tests/test_validate.py`, `docs/hosts.md`
**Docs:** `docs/hosts.md` (it points to the part that holds the differences), `plugins/clay/README.md` (same pointer)
**Accept:** 1. `hosts.md` holds only what every host shares and tells the reader to read `hosts-<host>.md` next. 2. Each host part holds that host's start, per-call keys, resume, question tool and limits, recording details and its own notes. 3. `validate.py` fails when a host part is missing. 4. No rule of today's `hosts.md` is lost.
**Verify:** `python3 -m pytest tests -q && python3 scripts/validate.py`

**Interfaces:**
- Produces: `reference/hosts-claude.md`, `hosts-codex.md`, `hosts-cursor.md`, each with the headings `## Starting an agent`, `## Model and effort`, `## Resuming an agent`, `## Asking the user`. `hosts.md` keeps `## Which host`, `## Starting an agent`, `## Model and effort`, `## Asking the user`. Task 4 counts `hosts-<host>.md` in the word budget.

- [ ] **Step 1: Write the failing tests** in `tests/test_orchestrator_text.py`, with `def host_part(h): return read(f"reference/hosts-{h}.md")`:
  - `HOST_SECTIONS` becomes the four shared headings; `test_hosts_part_has_sections` keeps the generic-agent sentence, `end the turn`, `never apply a default`, `longer than 3`, `state.py model --host <host>` and `frontmatter` in `hosts.md`, and asserts `` `hosts-<host>.md` `` in it; each tool name is asserted in its own host part (`Agent`, `AskUserQuestion`, `SendMessage` in claude; `spawn_agent`, `request_user_input`, `send_input` in codex; `Task` in cursor and in `hosts.md`'s detection).
  - `test_hosts_closes_codex_agents` and `test_hosts_handles_refused_spawn_on_thread_limit` read `host_part("codex")`, with the same sentences.
  - New `test_cursor_starts_a_fresh_builder` (`host_part("cursor")` contains `fresh builder`) and `test_claude_part_holds_the_progress_band` (`host_part("claude")` contains `progress band`).
  - `other_parts()` leaves out every `hosts*.md`.
  - `tests/test_validate.py`: a plugin tree without `reference/hosts-codex.md` reports `reference/hosts-codex.md`.
- [ ] **Step 2: Run them.** Expected: FAIL.
- [ ] **Step 3: Split `hosts.md`** as the spec's section 1 says. The table goes; each row moves to its host part as prose. The "a named builder does not survive its session" sentence stays in `start.md` Resume only; `hosts-cursor.md` says to start a fresh builder as `start.md` Resume says. The `savvy-progress` clause of "Claude Code only" goes (Task 4 removes the rest).
- [ ] **Step 4: Add the parts to the parts table** in `orchestrator.md`, and in `validate.py` check that `reference/hosts-claude.md`, `hosts-codex.md` and `hosts-cursor.md` exist whenever `reference/hosts.md` does. Point `docs/hosts.md` and the README to `hosts.md` and the host parts.
- [ ] **Step 5: Run the suite and the validator.** Expected: PASS, exit 0.
- [ ] **Step 6: Commit** `feat: hosts.md keeps what every host shares, each host has its own part`.

### Task 4: Trim the parts and cap the start

**Repo:** clay-kit
**Tier:** medium
**Depends:** 3
**Files:** `plugins/clay/reference/orchestrator.md`, `plugins/clay/reference/README.md`, `plugins/clay/reference/start.md`, `plugins/clay/reference/lock.md`, `plugins/clay/reference/job-loop.md`, `plugins/clay/reference/completion.md`, `plugins/clay/reference/commands.md`, `plugins/clay/reference/questions.md`, `plugins/clay/reference/lean.md`, `plugins/clay/reference/hosts.md`, `plugins/clay/skills/factory-unlock/SKILL.md`, `plugins/clay/skills/factory-brainstorm/SKILL.md`, `plugins/clay/skills/factory-plan/SKILL.md`, `plugins/clay/README.md`, `tests/test_orchestrator_text.py`
**Docs:** `plugins/clay/README.md` (the `savvy-progress` line goes), `plugins/clay/reference/README.md` (new: the parts table)
**Accept:** 1. Sections 2 to 7 of the spec are applied. 2. `factory-run` and `factory-task` read at most 4,400 words at the start on each host. 3. Every rule removed is kept in one other place or done by a script, and the commit body lists where.
**Verify:** `python3 -m pytest tests -q && python3 scripts/validate.py`

- [ ] **Step 1: Write the failing tests** in `tests/test_orchestrator_text.py`:
  - `test_a_run_reads_at_most_4400_words_at_the_start`: for `skill` in `factory-run`, `factory-task` and `host` in `claude`, `codex`, `cursor`, `words(f"skills/{skill}/SKILL.md") + sum(words(f"reference/{p}") for p in parts_read_by(skill)) + words(f"reference/hosts-{host}.md") <= 4400`, with `words = lambda rel: len(read(rel).split())`.
  - `test_parts_have_no_shared_header`: no file in `reference/` contains `Part of the orchestrator reference`; `orchestrator.md` contains `` `<repo>` means ``; `factory-unlock`, `factory-brainstorm` and `factory-plan` SKILLs contain `` `<repo>` ``.
  - `test_job_json_is_written_only_by_the_script`: `orchestrator.md` contains `written only by \`state.py\`` and not `"id": "003-rate-limit"`.
  - `test_savvy_progress_is_gone`: `savvy-progress` is not in `reference()` nor in `plugins/clay/README.md`.
  - `test_every_part_of_the_reference_is_listed_in_the_core_and_exists` reads the table from `reference/README.md` and compares it with every `reference/*.md` except `README.md`; `test_the_small_commands_read_a_fraction_of_the_reference` leaves out `README.md` and every `hosts*.md`, and drops the 18% cap on `hosts.md`, which the word budget replaces.
  - Rewrite to where the rule now lives: `test_jobs_folder_ignores_itself` and `test_dashboard_is_copied_next_to_jobs` assert `state.py setup`, `ignored by git` and `copies the dashboard` in step 0 of `job-loop.md`; the fable test drops the `On Claude Code, with no \`factory/models.json\`` assert and keeps the rest.
- [ ] **Step 2: Run them.** Expected: FAIL.
- [ ] **Step 3: Apply the spec, section by section:** 2 (`orchestrator.md`: Files, role, dashboard, parts table to `reference/README.md`, `savvy-progress` also out of the README), 3 (headers, and `<repo>` in the three skills), 4 (`start.md`), 5 (`lock.md`), 6 (`job-loop.md`: recording details live in the host parts; the Pace section points to `lock.md` for the release), 7 (`completion.md`). Keep the parts' remaining wording as it is.
- [ ] **Step 4: Run the suite and the validator.** Expected: PASS, exit 0. If the budget test fails, report the word counts; do not cut further than the spec without asking.
- [ ] **Step 5: Commit** `feat: the reference says each rule once and leaves the bookkeeping to state.py`, body: one line per removed rule naming where it lives now.
