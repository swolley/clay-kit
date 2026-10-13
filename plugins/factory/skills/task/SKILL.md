---
name: task
description: Run one ad hoc task through the same build, review and approval loop, without a written plan.
disable-model-invocation: true
argument-hint: "<what to do>"
---

Plugin root: ${CLAUDE_PLUGIN_ROOT}
Follow ${CLAUDE_PLUGIN_ROOT}/STYLE.md. Read ${CLAUDE_PLUGIN_ROOT}/reference/orchestrator.md first: it holds the
shared rules (files, modes, resume, job loop, completion). Use the plugin root above wherever it says `<plugin root>`.

Task text: $ARGUMENTS

Treat the text as a one-task plan named `adhoc` (see "The other commands" in the reference) and run the
Preconditions, mode question, Job loop and Completion for it. Do not write a plan file.
