# Host notes

What each host documents, with the page it was read from. "Not documented" means
the pages read do not say it; nothing here is inferred. Read on 2026-10-13.

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

## Codex (docs: https://developers.openai.com/codex/ and openai/codex)

| Topic | Fact | Source |
|-------|------|--------|
| Plugin manifest | A root `plugin.json`; `.codex-plugin/plugin.json` is a compatibility fallback. Required fields not documented | codex/plugins/build |
| Marketplace | `.agents/plugins/marketplace.json` with `name`, `plugins[]` entries having `name`, `source {source: local, path}`, `policy`, `category`. Not the Claude Code schema | codex/plugins/build |
| Skills | `skills/<name>/SKILL.md` with `name` and `description`; user invokes with `/skills` or `$name`; the model may pick one by description | learn.chatgpt.com/docs/build-skills |
| User-only skill | `agents/openai.yaml` with `policy.allow_implicit_invocation: false` | learn.chatgpt.com/docs/build-skills |
| Custom agents | TOML files in `.codex/agents/` or `~/.codex/agents/` with `name`, `description`, `developer_instructions`, optional `model`, `model_reasoning_effort`. Marked as possibly changing. Plugin-bundled agents: not documented | learn.chatgpt.com/docs/agent-configuration/subagents |
| Question tool | `request_user_input`: no official page. From issues and PRs: it blocks only in Plan mode; in Default mode it needs an off-by-default feature flag. **Unverified** | github.com/openai/codex/issues/43759, /12694 |
| Shared plugin files from a skill | Not documented. `PLUGIN_ROOT` is documented for hook commands only | codex/plugins/build |

Consequences: Codex support needs a separate manifest, a separate marketplace file, user-only skills through `agents/openai.yaml`, and agents as TOML. Whether a plugin can bundle those agents and read a shared file is not documented, so Codex support is **pending** (see Task 12). Until the question tool is documented, Codex uses the plain-text fallback.
