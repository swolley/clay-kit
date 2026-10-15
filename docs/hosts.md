# Host notes

What each host documents, with the page it was read from. "Not documented" means
the pages read do not say it; nothing here is inferred. Claude Code read on 2026-10-13,
Codex and Cursor on 2026-10-15.

## Claude Code (docs: https://code.claude.com/docs/en/)

| Topic | Fact | Source |
|-------|------|--------|
| Command spelling | A plugin skill `skills/<name>/SKILL.md` is `/<plugin>:<name>`; frontmatter `name` sets the last segment; the bare `/<name>` also works unless another command uses it | skills.md |
| Autocomplete | The `name` is shown in the `/` menu; one entry per skill is implied, not stated. Sub-arguments are not documented as listed | skills.md |
| `argument-hint` | Hint shown during autocomplete, e.g. `[plan-file]`; does not change argument passing | skills.md |
| `disable-model-invocation: true` | The model cannot load the skill on its own; the user can run it; the skill is also not preloaded into subagents | skills.md |
| `user-invocable: false` | Hidden from the menu, model only | skills.md |
| Default invocation | The model may start a skill from its `description` | skills.md |
| Shared plugin files | `${CLAUDE_PLUGIN_ROOT}` is substituted in plugin skill, command and agent markdown, not in the Bash tool environment | skills.md, plugins/manifest-reference.md |
| Subagent fields | `name`, `description` required; `tools`, `model`, `effort`, `skills`, `isolation` and more. In plugin agents `hooks`, `mcpServers`, `permissionMode` are ignored | sub-agents.md |
| Subagent `model` | `sonnet`, `opus`, `haiku`, `fable`, a full model id, or `inherit`; the Agent call can pass `model` per invocation | sub-agents.md |
| Subagent `effort` | `low`, `medium`, `high`, `xhigh`, `max` (levels depend on the model); a per-invocation `effort` exists from v2.1.292 | sub-agents.md |
| Question tool | `AskUserQuestion`, multiple choice with an "Other" free-text row. **Not available inside subagents** | tools-reference.md, sub-agents.md |
| Manifest | `plugin.json`: only `name` required. `marketplace.json`: `name`, `owner.name`, `plugins[]` with `name` and `source`; `category` is free-form | plugins/manifest-reference.md, plugins/marketplace-reference.md |

Command names: skills are named `factory-<verb>` so they are typed `/factory-<verb>` (the bare form of a skill name is documented to work when no other command uses it; the namespaced `/clay:factory-<verb>` also works), and the mod commands are `factory-progress` and `factory-agents`, because a mod command name may only hold letters, digits, `_` and `-` (verified live on 2026-10-13).

Observed in a real run (Claude Code desktop, 2.1.293, 2026-10-13): the Agent tool of the orchestrating session accepted a `model` but no `effort` and no `name` for the agent. Tiers therefore apply the model only, and a resumed agent is addressed by the id the spawn returns.

Consequences for this tool:
- Any question to the user is asked by a skill in the main session. Agents never ask; they write open questions into their own file and the orchestrator asks.
- Shared logic is read from the parts in `${CLAUDE_PLUGIN_ROOT}/reference/` (each command skill names the ones it needs), and helper scripts live in `plugins/clay/scripts/`, so an installed plugin never reads outside its folder.
- `${CLAUDE_PLUGIN_ROOT}` is substituted in skill and agent text, not in files read later, so each command skill states the plugin root at its top and the files of `reference/` refer to `<plugin root>`. The validator enforces both.
- Tiers pass `model` at spawn, and `effort` when the host accepts it; otherwise the agent's frontmatter default applies.

## Codex (source: openai/codex at `bb64b89`, 2026-10-15)

The proxy of the research session blocked developers.openai.com and learn.chatgpt.com, so this section is read from the
source code of the CLI. `GH:` stands for `https://github.com/openai/codex/blob/bb64b89/codex-rs/`. Rows marked **(S)** come
from a search engine's excerpt of the official page, not from reading it: confirm them in a browser.

| Topic | Fact | Source |
|-------|------|--------|
| Plugin manifest | Searched in order: `.codex-plugin/plugin.json`, `.claude-plugin/plugin.json`, `.cursor-plugin/plugin.json`. **A Claude Code manifest is read as it is** | GH:exec-server-protocol/src/protocol.rs |
| Manifest fields | `name`, `version`, `description`, `keywords`, `skills`, `mcpServers`, `apps`, `hooks`, `commands`, `interface {displayName, shortDescription, longDescription, developerName, category, ...}`. Paths start with `./`. Defaults: `skills/`, `hooks/hooks.json`, `.mcp.json`, `.app.json` | GH:core-plugins/src/manifest.rs, loader.rs |
| Plugin agents | **No agents field.** Custom agents load only from the `agents/` folder of a config layer (`~/.codex/agents/`, `.codex/agents/`), never from a plugin | GH:agent-roles/src/loader.rs |
| Commands | `commands/*.md` of a plugin are converted to skills at install; `$ARGUMENTS` is detected | GH:core-plugins/src/command_migration/plugin.rs |
| Marketplace | Searched in order, first wins: `.agents/plugins/marketplace.json`, `.agents/plugins/api_marketplace.json`, `.claude-plugin/marketplace.json`, `.cursor-plugin/marketplace.json`. An entry `source` may be `"./path"` | GH:core-plugins/src/marketplace.rs |
| Install | `codex plugin marketplace add <owner/repo[@ref]>`, then `codex plugin add <plugin>@<marketplace>`; `/plugins` in the TUI **(S)** | GH:cli/src/marketplace_cmd.rs, plugin_cmd.rs; developers.openai.com/codex/plugins/build (S) |
| On disk | `$CODEX_HOME/plugins/cache/<marketplace>/<plugin>/<version>` (`local` without a version) | GH:core-plugin-common/src/installed.rs |
| Skill frontmatter | Parsed: `name` (max 64), `description`, `metadata.short-description`. `argument-hint` and `disable-model-invocation` are ignored | GH:skills/src/parser.rs |
| User-only skill | `agents/openai.yaml` beside SKILL.md with `policy: { allow_implicit_invocation: false }` (default true) | GH:skills/src/metadata.rs |
| Invocation | `$<skill>` in the composer or the `/skills` picker; plugin skills are namespaced `<plugin>:<skill>` | GH:ext/skills/src/catalog_prompt.rs, loader/namespace.rs |
| Arguments | No mechanism: text after the mention is ordinary prompt text | GH:ext/skills/src/fragments.rs |
| Shared plugin files | No variable for the plugin root in skill text. The model gets the absolute path of SKILL.md and is told to resolve relative paths "relative to the directory containing that expanded `SKILL.md` first" | GH:ext/skills/src/catalog_prompt.rs |
| Custom agents | TOML: `name`, `description` required, plus any config key: `developer_instructions`, `model`, `model_reasoning_effort`, `sandbox_mode`, ... | GH:agent-roles/src/agent_role_config.rs |
| Spawn tool | `spawn_agent` with `message`, `agent_type`, and per call `model` and `reasoning_effort` (shown when `expose_spawn_agent_model_overrides`, default true in config). Also `wait_agent`, `send_input`, `resume_agent`, `close_agent`. `multi_agent` is on by default | GH:core/src/tools/handlers/multi_agents_spec.rs, core/src/config/mod.rs |
| Live agent threads | Capped by `agents.max_concurrent_threads_per_session` (formerly `agents.max_threads`, an alias). Default 6 with `multi_agent` (`DEFAULT_AGENT_MAX_THREADS = Some(6)`, `core/src/config/mod.rs:255`); with multi-agent v2 the default is 4 per session counting the root, so 3 subagents (`mod.rs:256`, `effective_agent_max_threads` at `mod.rs:1666`). Hitting it returns `AgentLimitReached`; `close_agent` frees a thread | GH:core/src/config/mod.rs, protocol/src/error.rs |
| Effort values | `none`, `minimal`, `low`, `medium`, `high`, `xhigh`, `max`, ... (accepted values depend on the model) | GH:protocol/src/openai_models.rs |
| Question tool | `request_user_input`: 1 to 3 questions, 2 to 3 options each, "Other" added. Plan mode only unless `[features] default_mode_request_user_input = true` (under development, off). **Refused in subagents** ("root thread" only) | GH:core/src/tools/handlers/request_user_input.rs, tools/src/tool_config.rs |
| Hooks | Plugins ship hooks; their commands get `PLUGIN_ROOT` and `CLAUDE_PLUGIN_ROOT` in the environment. Hooks must be trusted before they run **(S)** | GH:hooks/src/engine/discovery.rs; developers.openai.com/codex/hooks (S) |
| Agent shell env | No variable points to the plugin folder in commands the agent runs | GH: no match outside hooks and MCP |
| Custom prompts | `~/.codex/prompts` is deprecated in favour of skills **(S)** | developers.openai.com/codex/custom-prompts (S) |

## Cursor (docs: https://cursor.com/docs/ and github.com/cursor/plugins)

cursor.com could not be opened from the research session (DNS failure, proxy 403). Rows marked **(S)** come from a search
engine's excerpt of the cited page; rows marked **(F)** were read in full on GitHub. "Forum" is a user report, not the docs.

| Topic | Fact | Source |
|-------|------|--------|
| Plugin manifest | `.cursor-plugin/plugin.json`; only `name` required (kebab-case), no extra keys allowed. Components: `skills`, `agents`, `commands`, `rules` (path, glob or list), `hooks`, `mcpServers` **(F)** | github.com/cursor/plugins/blob/main/schemas/plugin.schema.json |
| Default discovery | `skills/<x>/SKILL.md`, `agents/`, `commands/`, `rules/`, `hooks/hooks.json`, `mcp.json` **(F)** | github.com/cursor/plugin-template/blob/main/docs/add-a-plugin.md |
| Marketplace | `.cursor-plugin/marketplace.json`: `name`, `plugins[]` with `name` and `source` (relative path or URL) **(F)**. Cursor's own repo holds it beside `.claude-plugin/marketplace.json` **(F)** | github.com/cursor/plugins (schemas/marketplace.schema.json) |
| Install | Admins add a repo via Dashboard -> Plugins & MCPs -> Import from Repo; users install from Customize (project or user scope) **(S)**. In the CLI `/plugin marketplace add <git URL>` **(S)** | cursor.com/docs/plugins, cursor.com/docs/cli/changelog (S) |
| Claude Code plugins | "Plugins imported from Claude Code appear alongside native ones", under the setting "Include Third-Party Plugins, Skills, and Other Configs" (on by default) **(S)**. Which parts are imported: not documented | cursor.com/docs/cli/changelog, cursor.com/docs/reference/third-party-hooks (S) |
| Skills | Read from `.cursor/skills`, `.agents/skills`, `~/.cursor/skills`, and for compatibility `.claude/skills`, `.codex/skills` **(S)** | cursor.com/docs/skills (S) |
| Skill frontmatter | `name` (matches the folder), `description`, `paths`, `disable-model-invocation`, `metadata`. `argument-hint`: not documented **(S)** | cursor.com/docs/skills (S) |
| User-only skill | `disable-model-invocation: true`: loaded only when the user types `/<skill>` **(S)**. Forum: such plugin skills were hidden from the `/` menu | cursor.com/docs/skills (S); forum.cursor.com/t/155748 |
| Shared plugin files | Skills reference files "using relative paths from the skill root" **(S)**. `${CURSOR_PLUGIN_ROOT}` and `${CLAUDE_PLUGIN_ROOT}` are expanded in MCP `command`, `args`, `env`, `cwd` only; in skill or agent text: not documented | cursor.com/docs/skills, cursor.com/docs/reference/plugins (S) |
| Arguments | `$ARGUMENTS`: not documented | |
| Subagents | `.cursor/agents/`, `~/.cursor/agents/`, and for compatibility `.claude/agents/`, `.codex/agents/` **(S)**. Fields: `name`, `description`, `model` (`inherit` or a model id), `readonly`, `is_background`. `tools`, `effort`: not documented | cursor.com/docs/subagents (S) |
| Spawn tool | The Task tool; a subagent cannot start another **(S)**. Forum: the per-call `model` accepts only `fast` | cursor.com/docs/subagents (S); forum.cursor.com/t/156736 |
| Question tool | The ask-question tool works in any conversation, and subagents and skills may use it when told to **(S)**. Forum (reported): offered depending on the model; skipped in headless `cursor-agent -p` | cursor.com/changelog/2-4 (S); forum.cursor.com/t/165280, /173657 |
| Hooks | `{"version":1,"hooks":{<event>:[{command,...}]}}`; plugins ship `hooks/hooks.json` **(F)**. Claude Code hooks are mapped to Cursor events **(S)** | github.com/cursor/plugin-template (starter-advanced); cursor.com/docs/hooks (S) |
| Rules | `.cursor/rules/*.mdc` and `AGENTS.md` **(S)** | cursor.com/docs/rules (S) |
| On disk | Local plugins in `~/.cursor/plugins/local/<name>` **(S)**; the install cache is not documented | cursor.com/docs/plugins (S) |

## What the three hosts share and where they differ

| Need of this tool | Claude Code | Codex | Cursor |
|---|---|---|---|
| Find the plugin | `.claude-plugin/` | `.codex-plugin/plugin.json` first; `.claude-plugin/` files only for the marketplace | `.cursor-plugin/`; may import a Claude Code plugin |
| Shared files from a skill | `${CLAUDE_PLUGIN_ROOT}` substituted | path relative to SKILL.md | path relative to the skill root |
| Bundled agents | `agents/*.md` | not possible from a plugin | `agents/*.md` |
| Per-call model | yes (`model`) | yes (`model`, `reasoning_effort`) | only `fast` (forum) |
| Model names | `haiku`, `sonnet`, `opus`, `fable` | OpenAI model ids | Cursor model ids or `inherit` |
| User-only command | `disable-model-invocation` | `agents/openai.yaml` policy | `disable-model-invocation` |
| Arguments | `$ARGUMENTS` | the message text | not documented |
| Question tool | `AskUserQuestion`, main session | `request_user_input`, Plan mode only by default | ask-question tool, model dependent |
| Progress mod | yes | no | no |

Consequences, as built (design: `docs/superpowers/specs/2026-10-15-codex-cursor-design.md`; the host-by-host instructions
the orchestrator follows are in `plugins/clay/reference/hosts.md`):
- Every skill opens with `Plugin root: ${CLAUDE_PLUGIN_ROOT}` and a fallback line saying the root is the folder two levels
  above the folder that holds its `SKILL.md`. Claude Code substitutes the variable; Codex and Cursor use the fallback, which follows their documented
  rule of paths relative to the skill. The rest of the text says `<plugin root>`. Agents never use the variable: they read the
  `Plugin root:` line of their prompt, which the orchestrator adds on every host.
- Codex cannot install agents with the plugin, so there the orchestrator spawns a generic subagent told to read
  `<plugin root>/agents/<role>.md`. Cursor starts the plugin's own agent and falls back to the same generic message when the
  host does not list it. No TOML installer was written.
- Tiers name Claude models only in the defaults of `tiers.md` (mirrored in `scripts/models.py`). Other hosts map them with the
  optional `factory/models.json`, resolved by `state.py model`; without an entry Codex passes no model and keeps the tier's
  effort, and Cursor passes nothing. The values each host accepts are checked when the file is read.
- Every question has a plain-text fallback: numbered options in the reply, then wait for the user's answer. Codex's
  `request_user_input` is used in Plan mode, and a list longer than 3 options goes to plain text.
- The progress band and pane stay Claude Code only; `factory/jobs/dashboard.html` works on every host.
- Our `hooks/hooks.json` holds a Claude Code mod (`{"modules": [...]}`) and Codex and Cursor load that path by default, so
  both manifests declare hooks inline and empty (`"hooks": {"hooks": {}}` for Codex, `"hooks": {"version": 1, "hooks": {}}` for
  Cursor). The Codex loader skips an empty inline object without reading the default path (`core-plugins/src/loader.rs`).
- Codex needs `agents/openai.yaml` with `allow_implicit_invocation: false` for each user-only skill; Cursor uses the existing
  `disable-model-invocation: true`.

Still untested (in `tests/e2e/CHECKLIST.md`, sections K and L): that Cursor finds the plugin's `agents/` and `skills/` by
default with no key in its manifest; how Cursor imports a Claude Code plugin; what `inherit` does as a per-call model (reported
ignored in some versions); the Cursor install routes and the `/` menu for user-only skills; that Codex does not read our
`hooks/hooks.json`, which is read from source only; that an inline `hooks` object in the Cursor manifest stops Cursor loading the
default `hooks/hooks.json` is not documented.
