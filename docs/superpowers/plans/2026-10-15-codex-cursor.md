# Codex and Cursor Support Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the clay plugin installable and runnable from Codex and Cursor, with Claude Code behaving exactly as today.

**Architecture:** One host-neutral source. Thin manifests per host, a plugin root that skills find without `${CLAUDE_PLUGIN_ROOT}`, a model and effort resolver in Python (`models.py`, exposed as `state.py model`), and one reference part (`reference/hosts.md`) that tells the orchestrator how each host spawns, resumes and asks.

**Tech Stack:** Markdown skills and agents, JSON and YAML manifests, Python 3 standard library, pytest.

**Spec:** `docs/superpowers/specs/2026-10-15-codex-cursor-design.md` (facts in `docs/hosts.md`)

## Global Constraints

- Claude Code keeps working unchanged: `.claude-plugin/marketplace.json` and `plugins/clay/.claude-plugin/plugin.json` are not edited, and `/factory-<verb>` still works.
- No emojis and no em-dashes in any file. Code and docs in English. Every skill and agent references `STYLE.md`.
- No hard dependency on another plugin; nothing under `plugins/clay/` reads outside its folder.
- `${CLAUDE_PLUGIN_ROOT}` appears once per SKILL.md, in its first body line, and never in `agents/` or `reference/`.
- No fixed OpenAI or Cursor model id anywhere in the plugin.
- Python: standard library only; tests run with `.venv/bin/python -m pytest tests -q`; `python3 scripts/validate.py` exits 0 after every task.

## Review Focus

- `factory/models.json` missing, empty or not valid JSON: missing means defaults; invalid exits 2 with the file name, never a traceback.
- A typo in `models.json` (host `curosr`, tier `hevy`, agent `reviewer-cod`): exit 2 naming the key, not a silent fallback.
- A partial entry (`model` without `effort`): the missing key falls back on its own, the given one is kept.
- A skill invoked with no arguments on Claude Code: `$ARGUMENTS` becomes empty and the fallback sentence must not misfire; the sentence never spells `$ARGUMENTS`.
- A Cursor manifest key outside the Cursor schema: Cursor rejects the whole manifest (`additionalProperties: false`); the validator must catch it first.

---

### Task 1: Model and effort resolver

**Repo:** clay-kit
**Tier:** medium
**Depends:** none
**Files:** `plugins/clay/scripts/models.py`, `plugins/clay/scripts/state.py`, `tests/test_models.py`
**Accept:** 1. `state.py model` resolves every rule of the spec's "Model mapping" section. 2. Bad input exits 2 with a message naming the key. 3. A test fails if `tiers.md` and the script disagree.
**Verify:** `.venv/bin/python -m pytest tests/test_models.py -q`

**Interfaces:**
- Produces: `resolve(root: Path, host: str, tier: str | None = None, agent: str | None = None, risky: bool = False) -> dict` returning `{"model": str | None, "effort": str | None, "source": "models.json" | "tiers.md" | "session"}`; raises `ModelsError(str)` on bad input. Constants `HOSTS = ("claude", "codex", "cursor")`, `TIER_DEFAULTS: dict[str, tuple[str, str]]`, `AGENT_DEFAULTS: dict[str, tuple[str, str]]`.
- Produces: CLI `state.py model --root DIR --host H (--tier T | --agent A) [--risky]`, prints the dict as JSON, exit 2 on `ModelsError`.
- Consumes: `TIERS` from `factory_plan.py` for the tier names.

- [ ] **Step 1: Write the failing tests** in `tests/test_models.py` (import as the other tests do, `sys.path` to `plugins/clay/scripts`):
  - `test_claude_defaults`: `resolve(tmp, "claude", tier="careful") == {"model": "opus", "effort": "high", "source": "tiers.md"}`; `agent="reviewer-security"` gives `opus`/`high`; `agent="approver"` gives `sonnet`/`high`; with `risky=True` gives `opus`/`high`.
  - `test_codex_without_file`: `tier="heavy"` gives `{"model": None, "effort": "xhigh", "source": "session"}`.
  - `test_cursor_without_file`: `tier="light"` gives `{"model": None, "effort": None, "source": "session"}`.
  - `test_fable_off_claude_is_heavy`: codex `tier="fable"` with no entry equals codex `tier="heavy"`; with `{"codex": {"tiers": {"fable": {"model": "x"}}}}` the model is `x`.
  - `test_uiux_is_ux`: `agent="reviewer-uiux"` equals `agent="reviewer-ux"` on every host, including a `models.json` entry for `reviewer-ux` only.
  - `test_mapping_wins_per_key`: `{"codex": {"tiers": {"light": {"model": "m1"}}}}` gives `model "m1"`, `effort "low"`, `source "models.json"`.
  - `test_risky_approver_mapping`: `{"codex": {"agents": {"approver-risky": {"model": "big"}}}}` with `risky=True` gives `big`; without `risky` gives `None`.
  - `test_bad_input_raises` (parametrized): invalid JSON; top-level key `curosr`; tier `hevy`; agent `reviewer-cod`; claude model `gpt-x`; claude effort `huge`; cursor model `auto`; any cursor `effort`; empty codex model; both or neither of `tier` and `agent`; host `gemini`. Each raises `ModelsError` whose text names the bad key or value.
  - `test_tiers_md_parity`: parse the two tables of `plugins/clay/tiers.md` (rows `| name | ... | model | effort |`); every tier row equals `TIER_DEFAULTS`, every agent row except `approver` equals `AGENT_DEFAULTS`, and `AGENT_DEFAULTS` holds `approver` `("sonnet", "high")` and `approver-risky` `("opus", "high")`.
  - `test_cli_exit_codes`: `subprocess` run of `state.py model --host codex --tier light --root <tmp>` exits 0 and prints JSON; with `--tier nope` exits 2.
- [ ] **Step 2: Run them.** Expected: FAIL, `ModuleNotFoundError: models`.
- [ ] **Step 3: Implement `models.py`.** Read `<root>/factory/models.json` only if it exists. Validate the whole file before resolving (host keys, `tiers`/`agents` keys, then per-host vocabulary from the spec table). Resolution order exactly as the spec, per key. `reviewer-uiux` maps to `reviewer-ux` before lookup; `risky` maps `approver` to `approver-risky`. Module docstring states the file format in three lines.
- [ ] **Step 4: Add the `model` subcommand to `state.py`** (`main`, beside `adhoc`, plus a usage line in the docstring). On `ModelsError` print `{"error": "<text>"}` and return 2.
- [ ] **Step 5: Run the tests.** Expected: PASS. Then the whole suite and `python3 scripts/validate.py`.
- [ ] **Step 6: Commit** `feat: resolve model and effort per host from tiers and factory/models.json`.

### Task 2: Host-neutral agents with frontmatter effort

**Repo:** clay-kit
**Tier:** light
**Depends:** 1
**Files:** `plugins/clay/agents/*.md`, `scripts/validate.py`, `tests/test_validate.py`, `tests/test_models.py`
**Accept:** 1. No agent contains `CLAUDE_PLUGIN_ROOT`; each says its plugin root is the `Plugin root:` line of its prompt. 2. The seven fixed-effort agents carry `effort:` equal to `AGENT_DEFAULTS`; `builder` has none. 3. The validator enforces 1.
**Verify:** `.venv/bin/python -m pytest tests -q && python3 scripts/validate.py`

**Interfaces:**
- Consumes: `AGENT_DEFAULTS` (Task 1).
- Produces: the sentence every agent carries, exactly: ``Your plugin root is the `Plugin root:` line of your prompt; paths below written `<plugin root>/...` start there.`` Task 5 relies on it.

- [ ] **Step 1: Write the failing tests.** `test_validate.py`: `test_agent_with_plugin_root_variable_fails` (an agent body containing `${CLAUDE_PLUGIN_ROOT}/STYLE.md` yields a problem naming the file) and `test_agent_without_root_sentence_fails`. Update `make_scaffold` so its agent carries the sentence. `test_models.py`: `test_agent_frontmatter_effort` reads each `plugins/clay/agents/<name>.md` frontmatter: for every key of `AGENT_DEFAULTS` that is a file name, `effort` equals the default; `builder.md` has no `effort`.
- [ ] **Step 2: Run them.** Expected: FAIL.
- [ ] **Step 3: Edit the agents.** Replace every `${CLAUDE_PLUGIN_ROOT}` with `<plugin root>`, add the sentence after the first paragraph, add `effort:` to the frontmatter of `reviewer-code`, `reviewer-ui`, `reviewer-ux`, `reviewer-uiux`, `reviewer-spec` (`medium`), `reviewer-security`, `approver` (`high`).
- [ ] **Step 4: Add the two agent rules to `validate.py`.**
- [ ] **Step 5: Run the suite and the validator.** Expected: PASS, exit 0.
- [ ] **Step 6: Commit** `feat: agents read the plugin root from their prompt and carry their fixed effort`.

### Task 3: Skills find the plugin root and arguments on every host

**Repo:** clay-kit
**Tier:** light
**Depends:** none
**Files:** `plugins/clay/skills/*/SKILL.md`, `scripts/validate.py`, `tests/test_validate.py`
**Accept:** 1. Every SKILL.md body starts with the two plugin-root lines of the spec. 2. `CLAUDE_PLUGIN_ROOT` occurs once per skill; other paths say `<plugin root>/`. 3. Each skill with `$ARGUMENTS` carries the fallback sentence, and `$ARGUMENTS` occurs at most once. 4. The validator enforces 1 to 3.
**Verify:** `.venv/bin/python -m pytest tests -q && python3 scripts/validate.py`

**Interfaces:**
- Produces: exact lines, as constants in `validate.py` (`ROOT_LINE`, `ROOT_FALLBACK`, `ARGS_FALLBACK`):
  - `Plugin root: ${CLAUDE_PLUGIN_ROOT}`
  - `If the line above does not show an absolute path, the plugin root is the folder two levels above this SKILL.md.`
  - `If the Arguments line still shows a placeholder that starts with $, the arguments are the text the user typed after the command name.`

- [ ] **Step 1: Write the failing tests** in `test_validate.py`, with `make_scaffold` updated to the new lines: `test_skill_without_root_lines_fails`, `test_skill_with_second_plugin_root_fails`, `test_skill_with_two_arguments_placeholders_fails`, `test_skill_with_arguments_but_no_fallback_fails`. Each asserts a problem naming the SKILL.md.
- [ ] **Step 2: Run them.** Expected: FAIL.
- [ ] **Step 3: Edit the 10 skills.** Put the two root lines first in the body (brainstorm and plan gain them), turn every other `${CLAUDE_PLUGIN_ROOT}` into `<plugin root>`, keep `Use the plugin root above wherever they say <plugin root>`, and add `ARGS_FALLBACK` right after the line that carries `$ARGUMENTS`. Three skills label that line differently (`Job:` in approve, `Task text:` in task, `Plan:` in unlock): relabel each to `Arguments: $ARGUMENTS (...)` keeping its meaning in the parenthesis, so the fallback sentence is true everywhere. `factory-backlog` uses `$ARGUMENTS` a second time inside its command: write that command as `python3 <plugin root>/scripts/plan_status.py <arguments>`, where `<arguments>` is the Arguments line.
- [ ] **Step 4: Add the rules to `validate.py`.**
- [ ] **Step 5: Run the suite and the validator.** Expected: PASS, exit 0.
- [ ] **Step 6: Commit** `feat: skills find the plugin root and their arguments without host substitution`.

### Task 4: Codex and Cursor manifests and user-only skills

**Repo:** clay-kit
**Tier:** medium
**Depends:** none
**Files:** `plugins/clay/.codex-plugin/plugin.json`, `plugins/clay/.cursor-plugin/plugin.json`, `.cursor-plugin/marketplace.json`, `plugins/clay/skills/<manual>/agents/openai.yaml` (8 files), `scripts/validate.py`, `tests/test_validate.py`
**Accept:** 1. The files hold what the spec's section 1 table says, with the inline empty hooks of the spec. 2. `name`, `version`, `description` match `.claude-plugin/plugin.json`; the Cursor marketplace lists the same plugin names and sources as the Claude one. 3. Each `MANUAL_ONLY` skill has `agents/openai.yaml` with `allow_implicit_invocation: false`; `AUTO_ALLOWED` skills have none. 4. Cursor manifests use only schema keys. 5. The validator enforces 2 to 4.
**Verify:** `.venv/bin/python -m pytest tests -q && python3 scripts/validate.py`

**Interfaces:**
- Produces in `validate.py`: `CURSOR_PLUGIN_KEYS` = the 21 property names of `github.com/cursor/plugins` `schemas/plugin.schema.json` (`name`, `displayName`, `description`, `version`, `minClientVersions`, `author`, `publisher`, `homepage`, `repository`, `license`, `logo`, `keywords`, `category`, `tags`, `commands`, `agents`, `skills`, `rules`, `hooks`, `variables`, `mcpServers`); `CURSOR_MARKETPLACE_KEYS = {"name", "owner", "metadata", "plugins"}`.
- Values: Codex `"skills": "./skills/"`, `"hooks": {"hooks": {}}`, `interface.displayName "Clay"`, `interface.developerName "swolley"`, `interface.category` equal to the Claude marketplace entry `category`. Cursor declares no `skills` and no `agents` key (default discovery of `skills/` and `agents/`, as the `cursor/plugin-template` starter does; a directory is not a documented value for those keys) and sets `"hooks": {"version": 1, "hooks": {}}`. `openai.yaml` body: `policy:\n  allow_implicit_invocation: false\n`.

- [ ] **Step 1: Write the failing tests** in `test_validate.py`, `make_scaffold` extended with valid copies of the new files: `test_missing_codex_manifest_fails`, `test_version_mismatch_fails` (Cursor `version` differs, the problem names both files), `test_cursor_unknown_key_fails` (`"types"` in the Cursor plugin.json), `test_cursor_marketplace_source_mismatch_fails`, `test_hooks_not_empty_inline_fails` (Codex `"hooks": "./hooks/hooks.json"`), `test_manual_skill_without_openai_yaml_fails`, `test_auto_skill_with_openai_yaml_fails`.
- [ ] **Step 2: Run them.** Expected: FAIL.
- [ ] **Step 3: Write the three manifests and the 8 `openai.yaml` files** with the values above. Codex `description` and Cursor `description` copy the Claude plugin.json description verbatim.
- [ ] **Step 4: Add the rules to `validate.py`.** `openai.yaml` is checked by text (`allow_implicit_invocation: false` present), no YAML parser.
- [ ] **Step 5: Run the suite and the validator.** Expected: PASS, exit 0.
- [ ] **Step 6: Commit** `feat: Codex and Cursor manifests, user-only skills on Codex`.

### Task 5: Orchestration per host

**Repo:** clay-kit
**Tier:** careful
**Depends:** 1, 2, 3
**Files:** `plugins/clay/reference/hosts.md`, `plugins/clay/reference/job-loop.md`, `plugins/clay/reference/questions.md`, `plugins/clay/reference/start.md`, `plugins/clay/reference/orchestrator.md`, `plugins/clay/STYLE.md`, `plugins/clay/tiers.md`, `plugins/clay/skills/{factory-run,factory-task,factory-approve,factory-rework,factory-answer,factory-unlock,factory-brainstorm,factory-plan}/SKILL.md`, `scripts/validate.py`, `tests/test_validate.py`, `tests/test_orchestrator_text.py`
**Accept:** 1. `reference/hosts.md` holds the spec's section 3 table, the generic spawn message, the plain-text fallback, the option limits and the effort recording rule. 2. Every spawn in the reference takes model and effort from `state.py model --host <host>`. 3. `<paths>` opens with `Plugin root: <plugin root>`. 4. No reference file says "at most 4 options" or names `SendMessage` outside `hosts.md`. 5. The six skills that spawn or ask list `reference/hosts.md`; brainstorm and plan point to it for `reviewer-spec` and questions. 6. Claude Code reads the same instructions it reads today when its tools are present.
**Verify:** `.venv/bin/python -m pytest tests -q && python3 scripts/validate.py`

**Interfaces:**
- Consumes: `state.py model` (Task 1), the agent sentence (Task 2), the skill root lines (Task 3).
- Produces: `reference/hosts.md` sections, by heading: `## Which host`, `## Starting an agent`, `## Model and effort`, `## Resuming an agent`, `## Asking the user`, `## Claude Code only`. Generic spawn message, exactly: `Read <plugin root>/agents/<role>.md and follow it as your instructions.` followed by `<paths>`.

- [ ] **Step 1: Write the failing tests** in `test_orchestrator_text.py` (it already reads the reference as text): `test_hosts_part_has_sections` (the six headings), `test_no_fixed_option_limit_outside_hosts` (`at most 4` absent from every other reference part and from STYLE.md), `test_sendmessage_only_in_hosts`, `test_spawns_use_model_resolver` (`job-loop.md` contains `state.py model --host`), `test_paths_carry_plugin_root` (`job-loop.md` contains `Plugin root: <plugin root>`). In `test_validate.py`: `test_spawning_skill_without_hosts_part_fails` for `factory-run`.
- [ ] **Step 2: Run them.** Expected: FAIL.
- [ ] **Step 3: Write `reference/hosts.md`** from the spec's section 3 and the Effort subsection, in the style of the other parts (header line pointing to `orchestrator.md`, `<plugin root>` and STYLE.md).
- [ ] **Step 4: Edit the reference parts.** `job-loop.md`: `<paths>` gains `Plugin root:` first; steps 2, 4, 5, 6 spawn and resume "as `hosts.md` says", with `state.py model --host <host> --tier <tier>` for the builder, `--agent reviewer-<lens>` for reviewers, `--agent approver [--risky]`; the `after-agent` paragraph points to the recording rule. `start.md`: "the question tool shows at most 4 options" becomes the host's limit from `hosts.md`. `questions.md` and `orchestrator.md`: add `hosts.md` to the parts table and to "Ask the user". `tiers.md`: the "model is what makes a tier real" paragraph says the values come from `state.py model`, the frontmatter carries the fixed efforts, and `factory/models.json` maps other hosts. `STYLE.md` section 1: the host names and the fallback move to `reference/hosts.md`, STYLE keeps the rule and points there.
- [ ] **Step 5: Edit the skills.** Add `<plugin root>/reference/hosts.md` to the read list of run, task, approve, rework, answer, unlock; brainstorm and plan say to spawn `reviewer-spec` and ask questions as `<plugin root>/reference/hosts.md` says. Add the rule (those six list `reference/hosts.md`) to `validate.py`.
- [ ] **Step 6: Run the suite and the validator.** Expected: PASS, exit 0.
- [ ] **Step 7: Commit** `feat: one host reference for spawning, models, resuming and questions`.

### Task 6: Documentation and manual checks

**Repo:** clay-kit
**Tier:** light
**Depends:** 4, 5
**Files:** `README.md`, `plugins/clay/README.md`, `docs/hosts.md`, `tests/e2e/CHECKLIST.md`
**Accept:** 1. Root README: install on Claude Code, Codex (`codex plugin marketplace add swolley/clay-kit`, then `codex plugin add clay@clay-kit`) and Cursor (`/plugin marketplace add https://github.com/swolley/clay-kit` in the CLI, or Dashboard import). 2. Tool README: the "Hosts" section replaces "pending" with the per-host table, how to invoke, `factory/models.json` with one example per host, and the known limits (no progress mod off Claude Code; Codex questions need Plan mode or fall back to text; Cursor per-call model only `fast`/`inherit`, no effort, `inherit` reported ignored in some versions, user-only plugin skills reported hidden from `/`). 3. `CHECKLIST.md` gains sections for Codex and Cursor: install, `factory-status`, a one-task `factory-task`, a question answered through the fallback, the model and effort recorded in `job.json`, and the hooks file not loaded. 4. `docs/hosts.md` consequences point to the spec and drop "to be tested" for what Tasks 4 and 5 settled.
**Verify:** `python3 scripts/validate.py`; read both READMEs top to bottom on GitHub rendering.

- [ ] **Step 1: Write the two README sections and the checklist sections** with the content of Accept 1 to 3. The install commands are the ones in `docs/hosts.md`; the CLI marketplace argument form is the one each host documents, nothing else.
- [ ] **Step 2: Update `docs/hosts.md` consequences.**
- [ ] **Step 3: Check** `grep -rnP "\x{2014}" README.md plugins/clay/README.md docs/hosts.md tests/e2e/CHECKLIST.md` prints nothing (no em-dash), and the validator exits 0.
- [ ] **Step 4: Commit** `docs: install and limits for Codex and Cursor, manual checks`.
