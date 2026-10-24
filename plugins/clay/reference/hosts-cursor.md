# Cursor

Host part for Cursor (`<host>` is `cursor`), read after `hosts.md`.

## Starting an agent

Start the plugin's agent `<role>` with the `Task` tool; when the host does not list it, start a generic agent with the message
`hosts.md` gives.

## Model and effort

Pass `model` only, and only `fast` or `inherit`; there is no effort. `inherit`, like a null, is the model of the user's chat, Auto
included when the user picked Auto. The usage is what the spawn result carries.

## Resuming an agent

No way to resume an agent is documented for Cursor: start a fresh builder, spawned as in step 2 of `job-loop.md`, as `start.md`
Resume says for a builder whose agent is gone.

## Asking the user

The question tool is the ask-question tool. It documents no option limit: use at most 4 options per question. It is reported to be
offered depending on the model, and headless mode to skip it; without it, use the plain-text form.
