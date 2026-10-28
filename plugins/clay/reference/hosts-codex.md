# Codex

Host part for Codex (`<host>` is `codex`), read after `hosts.md`.

## Starting an agent

Always start a generic agent with `spawn_agent`, with the message `hosts.md` gives. Wait for the agent with `wait_agent` before
reading its file.

## Model and effort

Pass `model` and `reasoning_effort` (the printed `effort`); omit a key that is null, the session's value applies. If the spawn
refuses a `reasoning_effort` value, spawn again without it and record the effort empty. The usage is what the spawn result carries.

## Resuming an agent

Send the message to the builder's agent id with `send_input`. The approver is closed once read, so a concern starts it again. Codex limits the live agent threads (default 6, or 4 including the
root under multi-agent v2; see `docs/hosts.md`), so close each reviewer and the approver with `close_agent` once its file has been
read, and the builder when the job leaves review or lands. A spawn refused for the thread limit (`AgentLimitReached`) is not a
failed agent, and starting a round's reviewers in several messages is allowed then. In this order: close the agents already read;
`wait_agent` for the reviewers still running, read their files and close them; only if no slot is free yet, close the builder (a
later round starts a fresh builder, as `start.md` Resume says); then start the reviewers that did not fit and retry the refused
spawn. If nothing is left to close, `wait_agent` for the running agents and spawn again.

## Asking the user

The question tool is `request_user_input`: 2 to 3 options per question, so a question with 4 goes to the plain-text form, and 1 to
3 questions per call. It works only in Plan mode by default and is refused for subagents.
