---
name: factory-rework
description: Send a job that is waiting for the user back to its builder with feedback.
disable-model-invocation: true
argument-hint: <job id> <note>
---

Plugin root: ${CLAUDE_PLUGIN_ROOT}
Follow ${CLAUDE_PLUGIN_ROOT}/STYLE.md. Read ${CLAUDE_PLUGIN_ROOT}/reference/orchestrator.md first: it holds the
shared rules (files, modes, resume, job loop, completion). Use the plugin root above wherever it says `<plugin root>`.

Arguments: $ARGUMENTS (first word is the job id, the rest is the note).

Follow "The other commands", rework, in the reference. Store the note verbatim.
