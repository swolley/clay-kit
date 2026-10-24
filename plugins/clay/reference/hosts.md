# Hosts

Part of the orchestrator reference (see `orchestrator.md`). `<plugin root>` is the path your skill states. Follow `<plugin root>/STYLE.md`. `<repo>` is the root of the target repository's own checkout.

The few things that differ between the hosts: starting an agent, its model and effort, resuming it, asking the user. The other
parts say "as `hosts.md` says" and "the question tool" for them: both mean this file and your host part. Everything else is the
same everywhere.

## Which host

The tools your session has name the host. Check in this order and stop at the first match: `Agent` or `AskUserQuestion` is
Claude Code; else `spawn_agent` is Codex; else `Task` is Cursor. If none is present, say so in one line and stop. There is
nothing to run. `<host>` in the commands is `claude`, `codex` or `cursor` accordingly.

Then read your host part, `hosts-<host>.md` in this folder (`hosts-claude.md`, `hosts-codex.md` or `hosts-cursor.md`), before you
start an agent or ask anything. It says how that host starts, resumes and asks.

## Starting an agent

`<role>` is the agent file's name: `builder`, `reviewer-code`, `reviewer-security`, `reviewer-interface`, `reviewer-spec`, `approver` or `reviewer-final`. The prompt is
the one the calling part gives; `<paths>` opens with `Plugin root: <plugin root>`, which is how every agent finds its files.
Where your host part says to start a generic agent, its message is
`Read <plugin root>/agents/<role>.md and follow it as your instructions.` followed by `<paths>` and the rest of the prompt.
Keep the agent id the spawn returns. Pass only what the spawn tool takes: a tool that takes no name gets none, and a tool that
does not accept an effort gets none.

## Model and effort

Every spawn takes its values from `python3 <plugin root>/scripts/state.py model --host <host> --root <repo> (--tier <tier> | --agent <name> [--risky])`.
It prints `model`, `effort` and `source`; `null` means pass nothing for that key. The defaults are the tables of
`<plugin root>/tiers.md`, and `<repo>/factory/models.json`, when it exists, maps them per host. Exit 2 names the bad key: tell the
user and stop. Your host part says which keys the spawn takes.

**Recording.** `job.json` `agents` (`after-agent`, `agent`) records what was actually passed, never a value that was not applied:
leave `model` empty when none was passed and leave `effort` empty when the host did not accept one. When the effort that applied
came from the agent file's frontmatter, your host part says so. The usage comes from the spawn result, with the fields your host
part names; when the result carries none, leave it out.

## Asking the user

"The question tool" in every part is the tool your host part names, with its limits on options and questions per call.

**Plain-text form.** Use it when there is no question tool or the host refuses it, and on Codex when a list is longer than 3.
Write the question in your reply with numbered options, each with its consequence and the recommended one first, end the turn,
and read the user's next message as the answer. A message that is not an answer leaves the job waiting (`questions.md`); never
apply a default.
