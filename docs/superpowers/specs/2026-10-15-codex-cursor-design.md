# Codex and Cursor support: design

Date: 2026-10-15. Status: approved in conversation.

## Goal

Make the clay suite usable from Codex and Cursor, not only Claude Code, with the limits those hosts impose stated plainly.
Success: a user installs the plugin from this repo on either host, types the factory commands, and a run builds, reviews and
approves tasks with the same files and the same scripts as on Claude Code. Claude Code keeps working exactly as today.

The facts behind every choice are in `docs/hosts.md` (Codex read from its source at `bb64b89`, Cursor from its plugin schemas
and docs excerpts). Where a fact is marked unverified there, the design names the check that settles it.

## Approach

One source, written to hold on every host, plus a thin manifest per host. No build step and no per-host copies. A new
reference part, `reference/hosts.md`, tells the orchestrator how to do the few things that differ: start an agent, pick its
model, resume it, ask the user. Rejected: a generator that writes `dist/codex` and `dist/cursor` (duplicates every file and
must be rerun on each change), and documentation only (leaves the hosts unusable).

## 1. Packaging and install

| File | Host | Content |
|------|------|---------|
| `.claude-plugin/marketplace.json`, `plugins/clay/.claude-plugin/plugin.json` | Claude Code; Codex reads them too | unchanged |
| `plugins/clay/.codex-plugin/plugin.json` | Codex (searched first) | `name`, `version`, `description`, `skills: "./skills"`, an empty inline `hooks`, `interface { displayName, shortDescription, developerName, category }` |
| `.cursor-plugin/marketplace.json` | Cursor | `name`, `owner`, `plugins: [{ name: "clay", source: "./plugins/clay", description }]` |
| `plugins/clay/.cursor-plugin/plugin.json` | Cursor | `name`, `version`, `description`, an empty inline `hooks`; no `skills` or `agents` key, because Cursor finds `skills/` and `agents/` by default |

- `hooks/hooks.json` holds the Claude Code mod (`{"modules": [...]}`). Codex and Cursor load `hooks/hooks.json` by default, so
  both manifests declare hooks inline and empty. Codex: `"hooks": {"hooks": {}}` (an inline object with no events is skipped and
  the default path is not read: `core-plugins/src/loader.rs`, `load_plugin_hooks`). Cursor: `"hooks": {"version": 1, "hooks": {}}`
  (the schema takes a path or an inline object).
- Codex gets no `.agents/plugins/marketplace.json`: it reads `.claude-plugin/marketplace.json`, and its parser keeps unknown keys
  such as `version` instead of rejecting them (`core-plugins/src/marketplace.rs`, `RawMarketplaceManifestPlugin`).
- The Cursor manifests allow no keys outside their schema (`additionalProperties: false`); the validator holds the list.
- Name, version and description agree across the four manifests; the validator enforces it.
- **User-only commands.** The 8 manual skills (`MANUAL_ONLY` in the validator) each get `agents/openai.yaml` with
  `policy: { allow_implicit_invocation: false }`. Cursor honours the existing `disable-model-invocation: true`. A forum report
  says Cursor hid such plugin skills from the `/` menu; the README lists it as a known limit.

Invocation per host: Claude Code `/factory-run`; Codex `$factory-run` or the `/skills` picker (namespaced `clay:factory-run`);
Cursor `/factory-run`.

## 2. Plugin root and arguments

- Every skill opens with two lines:
  `Plugin root: ${CLAUDE_PLUGIN_ROOT}` and
  `If the line above does not show an absolute path, the plugin root is the folder two levels above this SKILL.md.`
  Claude Code substitutes the variable. Codex tells the model the absolute path of SKILL.md and to resolve relative paths from
  its folder, so the fallback holds there. Cursor documents paths relative to the skill root, so it holds there too.
- The rest of each skill says `<plugin root>/...` instead of `${CLAUDE_PLUGIN_ROOT}/...`, as the reference files already do. The
  variable appears once per skill, in the first line, so an unsubstituted copy can never sit in the middle of an instruction.
- **Agents** stop using `${CLAUDE_PLUGIN_ROOT}`. A generic agent on Codex reads the agent file as plain text, where nothing is
  substituted. Each agent says its plugin root is the `Plugin root:` line of its prompt, and the orchestrator adds that line to
  `<paths>` (job-loop.md) on every host.
- `Arguments: $ARGUMENTS` stays, followed by: `If the Arguments line still shows a placeholder that starts with $, the arguments
  are the text the user typed after the command name.` The sentence never spells the placeholder, because Claude Code would
  substitute it there too.
- The validator checks the two plugin-root lines in every skill, one `CLAUDE_PLUGIN_ROOT` and at most one `$ARGUMENTS` per skill,
  and the absence of `CLAUDE_PLUGIN_ROOT` in `agents/`.

## 3. Orchestration per host

`reference/hosts.md` (plugin) is read by every command that spawns an agent or asks a question. The host is known from the
spawn tool the session has: `Agent` is Claude Code, `spawn_agent` is Codex, `Task` is Cursor. No detection script.

| | Claude Code | Codex | Cursor |
|---|---|---|---|
| Start an agent | named agent `clay:<role>` | `spawn_agent`, generic; message opens with `Read <plugin root>/agents/<role>.md and follow it.` then `<paths>` | the plugin's agent `<role>`; if the host does not list it, generic as on Codex |
| Model and effort | `state.py model` (defaults from `tiers.md`) | `state.py model`; `model` and `reasoning_effort` passed when it gives them | `state.py model`; only `fast` or `inherit` can be passed per call |
| Resume the builder | `SendMessage` to the agent id | `send_input` to the agent id | a fresh builder (the rule that already exists for a lost session) |
| Ask the user | `AskUserQuestion`, up to 4 options | `request_user_input`, 2 to 3 options; refused outside Plan mode by default | the ask-question tool |
| Usage for `after-agent` | from the spawn result | what the result carries, else empty | what the result carries, else empty |

- **Plain-text fallback.** When there is no question tool, or the host refuses it: write the question with numbered options
  in the reply, end the turn, and read the user's next message as the answer. A message that is not an answer leaves the job
  waiting, as `questions.md` already says. Never apply a default.
- Every place that says "at most 4 options" says "the host's limit (see `hosts.md`)". On Codex a list longer than 3 goes to
  the plain-text form.
- `inline` mode works the same everywhere: the builder's work happens in the session.

### Model mapping

`<repo>/factory/models.json` is optional and lives beside the existing `factory/routing.md`:

```json
{
  "codex": {
    "tiers":  { "light": { "model": "<id>", "effort": "low" }, "heavy": { "model": "<id>", "effort": "xhigh" } },
    "agents": { "reviewer-code": { "model": "<id>", "effort": "medium" }, "approver": { "model": "<id>" }, "approver-risky": { "model": "<id>" } }
  },
  "cursor": { "tiers": { "light": { "model": "fast" } } }
}
```

`python3 <plugin root>/scripts/state.py model --root <repo> --host claude|codex|cursor (--tier <t> | --agent <name> [--risky])`
prints `{ "model", "effort", "source" }`:

1. The host's entry in `models.json` wins, per key (`model` and `effort` separately).
2. Otherwise, on `claude`, the defaults of `tiers.md`.
3. Otherwise, on `codex`, `model: null` (the session's model) and the effort of `tiers.md` (Codex uses the same names).
4. Otherwise, on `cursor`, `model: null` and `effort: null` (no per-call effort).
5. Tier `fable` with no entry on a host other than `claude` resolves as `heavy`. `reviewer-uiux` resolves as `reviewer-ux`.
   `--risky` picks `approver-risky`, then the `tiers.md` rule.

Each host has its own vocabulary, checked when `models.json` is read (a bad value exits 2 and names the key):

| Host | `model` | `effort` |
|------|---------|----------|
| `claude` | `haiku`, `sonnet`, `opus`, `fable`, `inherit`, or an id starting with `claude-` | `low`, `medium`, `high`, `xhigh`, `max` |
| `codex` | any non-empty id (OpenAI ids change too often to list) | any non-empty value (Codex accepts model-defined values) |
| `cursor` | `fast` or `inherit` (the only values the Task tool takes per call) | not allowed (Cursor has no effort) |

An unknown host key, tier or agent name in the file also exits 2, so a typo does not silently fall back to the defaults.

On Cursor, `inherit` (and no entry at all) means the model of the user's chat, including Auto when the user picked Auto in the
model picker. A plugin cannot set Auto itself: `auto` is not a documented subagent value, and the agent files are shared with
Claude Code, where it would be invalid.

`source` is `models.json`, `tiers.md` or `session`. `null` means pass nothing. An unknown host, tier or agent exits 2. The
defaults of `tiers.md` move into the script; a test checks that the table in `tiers.md` and the script agree. `job.json`
`agents` records what was actually passed, so the progress views and the dashboard stay honest.

The `fable` question at the start of a run is asked on every host: it is about cost, not about Claude.

### Effort

Today `tiers.md` holds an effort per tier and per agent, and the orchestrator passes it only when the spawn tool takes one. The
Claude Code run of 2026-10-13 showed the Agent tool taking a model but no effort, so in practice no effort is applied. The plan:

| | Builder (effort depends on the tier) | Every other agent (fixed effort) |
|---|---|---|
| Claude Code | per call when the Agent tool shows an `effort` parameter; else the session's effort, recorded empty | `effort:` in the agent's frontmatter (documented for plugin agents), so it applies even without a per-call value |
| Codex | `reasoning_effort` per call | `reasoning_effort` per call |
| Cursor | none; recorded empty | none; recorded empty |

Frontmatter efforts, from `tiers.md`: `reviewer-code`, `reviewer-ui`, `reviewer-ux`, `reviewer-uiux`, `reviewer-spec` `medium`;
`reviewer-security`, `approver` `high`. A test keeps them equal to `tiers.md`. On Claude Code, when no per-call effort was
passed, `agents` records the frontmatter value, because that is the one applied.

### What stays Claude Code only

The progress band and pane (the mod) and the `savvy-progress` reporting. `factory/jobs/dashboard.html` works on every host.

## 4. Testing and documentation

- Unit tests: `state.py model` (every rule above, bad input exits 2), parity of `tiers.md` with the script, the new validator
  rules (plugin-root lines, no variable in agents, `openai.yaml` for each manual skill and none for the others, the four
  manifests valid and in agreement).
- `tests/e2e/CHECKLIST.md` gets a Codex section and a Cursor section: install from the marketplace, run `factory-status`, run a
  one-task plan with `factory-task`, answer a question through the fallback. They cannot run in CI; the README says which
  were run and when.
- Root README: install steps per host. Tool README: the host table, the model mapping, and the known limits.
- `docs/hosts.md` stays the record of facts; this spec does not repeat them.

## Out of scope

- A Codex TOML agent installer (rejected in conversation; generic agents cover it).
- Fixed OpenAI or Cursor model ids in the plugin.
- A progress view inside Codex or Cursor.
