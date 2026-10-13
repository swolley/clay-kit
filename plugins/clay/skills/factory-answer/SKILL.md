---
name: factory-answer
description: Answer the questions a job is waiting on, now or later: asks them again from the saved file, or takes your written answers.
disable-model-invocation: true
argument-hint: <job id> [your answers]
---

Plugin root: ${CLAUDE_PLUGIN_ROOT}
Follow ${CLAUDE_PLUGIN_ROOT}/STYLE.md. Read ${CLAUDE_PLUGIN_ROOT}/reference/orchestrator.md first: it holds the
shared rules (files, modes, resume, job loop, completion). Use the plugin root above wherever it says `<plugin root>`.

Arguments: $ARGUMENTS (first word is the job id, anything after it is the answers).

Resolve the job as in "Resolving arguments" (stages `waiting-input`); the argument may be empty, a number or a fragment.
Follow "The other commands", answer, and "Questions from agents" in the reference. If the job is not waiting for
input, say so and show its stage.
