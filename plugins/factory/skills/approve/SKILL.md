---
name: approve
description: Land a job that is waiting for the user: merge it into the integration branch, or commit it in current-branch mode.
disable-model-invocation: true
argument-hint: <job id>
---

Plugin root: ${CLAUDE_PLUGIN_ROOT}
Follow ${CLAUDE_PLUGIN_ROOT}/STYLE.md. Read ${CLAUDE_PLUGIN_ROOT}/reference/orchestrator.md first: it holds the
shared rules (files, modes, resume, job loop, completion). Use the plugin root above wherever it says `<plugin root>`.

Job: $ARGUMENTS

Follow "The other commands", approve, in the reference. Read the job's decision.md and tell the user in two lines what is being approved before landing it.
