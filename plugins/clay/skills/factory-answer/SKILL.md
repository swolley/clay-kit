---
name: factory-answer
description: Answer the questions a job is waiting on, now or later: asks them again from the saved file, or takes your written answers.
disable-model-invocation: true
argument-hint: <job id> [your answers]
---

Plugin root: ${CLAUDE_PLUGIN_ROOT}
Follow ${CLAUDE_PLUGIN_ROOT}/STYLE.md. Read these parts of the shared reference together, in one message: ${CLAUDE_PLUGIN_ROOT}/reference/orchestrator.md, ${CLAUDE_PLUGIN_ROOT}/reference/lock.md, ${CLAUDE_PLUGIN_ROOT}/reference/commands.md, ${CLAUDE_PLUGIN_ROOT}/reference/questions.md, ${CLAUDE_PLUGIN_ROOT}/reference/job-loop.md. Use the plugin root above wherever they say `<plugin root>`.

Arguments: $ARGUMENTS (first word is the job id, anything after it is the answers).

Resolve the job as in "Resolving a job" in `commands.md`, with stages `waiting-input`; the argument may be empty, a number or a fragment.
Respect the run lock (`lock.md`): if another session holds the plan with a recent heartbeat, say so and ask before acting.
Follow "The other commands", answer, in `commands.md` and `questions.md`. If the job is not waiting for
input, say so and show its stage.
