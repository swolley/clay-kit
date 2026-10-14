---
name: factory-approve
description: Land a job that is waiting for the user: merge it into the integration branch, or commit it in current-branch mode.
disable-model-invocation: true
argument-hint: <job id>
---

Plugin root: ${CLAUDE_PLUGIN_ROOT}
Follow ${CLAUDE_PLUGIN_ROOT}/STYLE.md. Read these parts of the shared reference together, in one message: ${CLAUDE_PLUGIN_ROOT}/reference/orchestrator.md, ${CLAUDE_PLUGIN_ROOT}/reference/lock.md, ${CLAUDE_PLUGIN_ROOT}/reference/commands.md. Use the plugin root above wherever they say `<plugin root>`.

Job: $ARGUMENTS

Resolve the job as in "Resolving a job" in `commands.md`, with stages `needs-human`; the argument may be empty, a number or a fragment.
Respect the run lock (`lock.md`): if another session holds the plan with a recent heartbeat, say so and ask before acting.
Follow "The other commands", approve, in `commands.md`. Read the job's decision.md and tell the user in two lines what is being approved before landing it. If the job has
no decision.md (for example a blocked build with no reviews), say so and ask for explicit confirmation first.
After landing, tell the user to rerun `/factory-run <plan>` so the steps are ticked and the finish step runs.
