---
name: factory-task
description: Run one ad hoc task through the same build, review and approval loop, without a written plan.
disable-model-invocation: true
argument-hint: "<what to do>"
---

Plugin root: ${CLAUDE_PLUGIN_ROOT}
Follow ${CLAUDE_PLUGIN_ROOT}/STYLE.md. Read these parts of the shared reference together, in one message: ${CLAUDE_PLUGIN_ROOT}/reference/orchestrator.md, ${CLAUDE_PLUGIN_ROOT}/reference/lock.md, ${CLAUDE_PLUGIN_ROOT}/reference/start.md, ${CLAUDE_PLUGIN_ROOT}/reference/job-loop.md. Read `questions.md` only when an agent asks something, `inline.md` only with the word `inline`, and `completion.md` once the task has landed (all in the same folder). Use the plugin root above wherever they say `<plugin root>`.

Task text: $ARGUMENTS

Treat the text as a one-task plan named `adhoc` (see "Ad hoc task" in `start.md`) and run the
Preconditions, mode question, Job loop (`job-loop.md`) and Completion (`completion.md`) for it. Do not write a plan file.
