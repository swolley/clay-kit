---
name: factory-answer
description: Answer the questions a job is waiting on, now or later: asks them again from the saved file, or takes your written answers.
disable-model-invocation: true
argument-hint: <job id> [your answers]
---

Plugin root: ${CLAUDE_PLUGIN_ROOT}
If the line above does not show an absolute path, the plugin root is the folder two levels above the folder that holds this SKILL.md (the folder that contains skills/).
Follow <plugin root>/STYLE.md. Read these parts of the shared reference together, in one message: <plugin root>/reference/orchestrator.md, <plugin root>/reference/lock.md, <plugin root>/reference/commands.md, <plugin root>/reference/questions.md, <plugin root>/reference/job-loop.md, <plugin root>/reference/hosts.md. Use the plugin root above wherever they say `<plugin root>`.

Arguments: $ARGUMENTS (first word is the job id, anything after it is the answers).
If the Arguments line still shows a placeholder that starts with $, the arguments are the text the user typed after the command name.

Resolve the job as in "Resolving a job" in `commands.md`, with stages `waiting-input`; the argument may be empty, a number or a fragment.
Respect the run lock (`lock.md`): if another session holds the plan with a recent heartbeat, say so and ask before acting.
Follow "The other commands", answer, in `commands.md` and `questions.md`. If the job is not waiting for
input, say so and show its stage.
