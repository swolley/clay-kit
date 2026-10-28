# Host notes

What each host documents, with the page it was read from. "Not documented" means
the pages read do not say it; nothing here is inferred. Claude Code read on 2026-10-13,
Codex on 2026-10-15.

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

## Supported-host comparison

| Capability | Claude Code | Codex |
|---|---|---|
| Plugin discovery | `.claude-plugin/` | `.codex-plugin/`, Claude marketplace compatibility |
| Bundled agent roles | Named plugin agents | Generic subagents reading the role file |
| Model override | `model` | `model` |
| Effort override | When Agent supports it | `reasoning_effort` |
| Questions | `AskUserQuestion` | `request_user_input` in Plan mode; text fallback |
| Resume | `SendMessage` | `send_input` |
| Progress mod | Available | Unavailable |
| External peer | Codex CLI | Claude CLI |

The supported host instructions live in `plugins/clay/reference/hosts.md`,
`hosts-claude.md`, and `hosts-codex.md`. Older design plans are preserved
as historical records and do not define supported integrations.

The host detection policy requires `Agent` or `AskUserQuestion` for Claude,
then `spawn_agent` for Codex. Without either tool the run stops rather than
silently selecting an unsupported host.
