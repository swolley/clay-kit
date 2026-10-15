# Hosts

Part of the orchestrator reference (see `orchestrator.md`). `<plugin root>` is the path your skill states. Follow `<plugin root>/STYLE.md`. `<repo>` is the root of the target repository's own checkout.

The few things that differ between the hosts: starting an agent, its model and effort, resuming it, asking the user. The other
parts say "as `hosts.md` says" and "the question tool" for them; everything else, `inline` mode included, is the same everywhere.

## Which host

The spawn tool your session has names the host: `Agent` is Claude Code, `spawn_agent` is Codex, `Task` is Cursor. There is
nothing to run. `<host>` in the commands is `claude`, `codex` or `cursor` accordingly.

| | Claude Code | Codex | Cursor |
|---|---|---|---|
| Start an agent | the named agent `clay:<role>` | `spawn_agent`, generic message | the plugin's agent `<role>`; generic message if the host does not list it |
| Per call | `model`; `effort` only if the tool shows it | `model`, `reasoning_effort` | `model`, only `fast` or `inherit`; no effort |
| Resume the builder | `SendMessage` to the agent id | `send_input` to the agent id | a fresh builder |
| Ask the user | `AskUserQuestion`, up to 4 options | `request_user_input`, 2 to 3 options | the ask-question tool |

## Starting an agent

`<role>` is the agent file's name: `builder`, `reviewer-<lens>`, `reviewer-uiux`, `reviewer-spec` or `approver`. The prompt is
the one the calling part gives; `<paths>` opens with `Plugin root: <plugin root>`, which is how every agent finds its files.
On Codex always, and on Cursor when the host does not list the plugin's agent, start a generic agent whose message is
`Read <plugin root>/agents/<role>.md and follow it as your instructions.` followed by `<paths>` and the rest of the prompt.
Keep the agent id the spawn returns (on Codex wait for the agent with `wait_agent` before reading its file). Pass only what
the spawn tool takes: a tool that takes no name gets none, and a tool that does not accept an effort gets none.

## Model and effort

Every spawn takes its values from `python3 <plugin root>/scripts/state.py model --host <host> --root <repo> (--tier <tier> | --agent <name> [--risky])`.
It prints `model`, `effort` and `source`; `null` means pass nothing for that key. The defaults are the tables of
`<plugin root>/tiers.md`, and `<repo>/factory/models.json`, when it exists, maps them per host. Exit 2 names the bad key: tell the
user and stop.

- **Claude Code:** pass `model` on every spawn. Pass `effort` only when the Agent tool shows an `effort` parameter; otherwise pass
  none, and the `effort:` in the agent file's frontmatter applies (the builder has none and runs at the session's effort).
- **Codex:** pass `model` and `reasoning_effort` (the printed `effort`); omit a key that is null, the session's value applies.
- **Cursor:** pass `model` only, and only `fast` or `inherit`; there is no effort. `inherit`, like a null, is the model of the
  user's chat, Auto included when the user picked Auto.

**Recording.** `job.json` `agents` (`after-agent`, `agent`) records what was actually passed, never a value that was not applied:
leave `model` empty when none was passed and leave `effort` empty when the host did not accept one. On Claude Code, when no
per-call effort was passed, record the frontmatter `effort:` of the agent file instead, since that one applied (builder: empty).
The usage comes from the spawn result: on Claude Code `subagent_tokens`, `tool_uses` and `duration_ms`; elsewhere what the
result carries, else leave it out.

## Resuming an agent

On Claude Code send the message to the builder's agent id with `SendMessage`, on Codex with `send_input`. Cursor has no way to
resume an agent: start a fresh builder, as when a session lost its builder, spawned as in step 2 of `job-loop.md`; it reads
build.md, the rounds and the branch log. On any host a builder whose agent is gone is replaced the same way.

## Asking the user

"The question tool" in every part is the host's tool in the table. Codex's `request_user_input` works only in Plan mode by
default and is refused for subagents. Cursor's ask-question tool is offered depending on the model, and headless mode skips it.

**Option limit.** At most 4 options per question on Claude Code, and on Cursor, which documents no limit. On Codex the tool takes
2 to 3; a question with 4 goes to the plain-text form.

**Plain-text form.** Use it when there is no question tool or the host refuses it, and on Codex when a list is longer than 3.
Write the question in your reply with numbered options, each with its consequence and the recommended one first, end the turn,
and read the user's next message as the answer. A message that is not an answer leaves the job waiting (`questions.md`); never
apply a default.

## Claude Code only

The progress band and pane (the mod in `<plugin root>/hooks/`) and the `savvy-progress` reporting (`orchestrator.md`) exist only
on Claude Code; elsewhere skip them without a word. `factory/jobs/dashboard.html` works on every host.
