# Claude Code

Host part for Claude Code (`<host>` is `claude`), read after `hosts.md`.

## Starting an agent

Start the named agent `clay:<role>` with the `Agent` tool.

## Model and effort

Pass `model` on every spawn; an `inherit`, like a null, passes nothing and the model is recorded empty. Pass `effort` only when the
`Agent` tool shows an `effort` parameter; otherwise pass none, and the `effort:` in the agent file's frontmatter applies (the
builder has none and runs at the session's effort).

When no per-call effort was passed, record the frontmatter `effort:` of the agent file, since that one applied: it equals the
`effort` that `state.py model --host claude --agent <role>` prints. The builder has no such file value: record its effort empty.
The usage is `subagent_tokens`, `tool_uses` and `duration_ms` of the spawn result.

## Resuming an agent

Send the message to the builder's agent id with `SendMessage`.

## Asking the user

The question tool is `AskUserQuestion`: at most 4 options per question and up to 4 questions per call; more go in further calls or
the plain-text form.

## Progress band

The progress band and pane (the mod in `<plugin root>/hooks/`) exist only on Claude Code.
`factory/jobs/dashboard.html` works on every host.
