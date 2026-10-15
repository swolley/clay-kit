---
name: factory-rework
description: Send a job that is waiting for the user back to its builder with feedback.
disable-model-invocation: true
argument-hint: <job id> <note>
---

Plugin root: ${CLAUDE_PLUGIN_ROOT}
If the line above does not show an absolute path, the plugin root is the folder two levels above this SKILL.md.
Follow <plugin root>/STYLE.md. Read these parts of the shared reference together, in one message: <plugin root>/reference/orchestrator.md, <plugin root>/reference/lock.md, <plugin root>/reference/commands.md, <plugin root>/reference/job-loop.md, <plugin root>/reference/hosts.md. Read `questions.md` (same folder) only when an agent asks something. Use the plugin root above wherever they say `<plugin root>`.

Arguments: $ARGUMENTS (first word is the job id, the rest is the note).
If the Arguments line still shows a placeholder that starts with $, the arguments are the text the user typed after the command name.

Resolve the job as in "Resolving a job" in `commands.md`, with stages `needs-human`; the argument may be empty, a number or a fragment.
Respect the run lock (`lock.md`): if another session holds the plan with a recent heartbeat, say so and ask before acting.
Follow "The other commands", rework, in `commands.md`. Store the note verbatim.
