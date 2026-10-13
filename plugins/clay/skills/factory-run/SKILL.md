---
name: factory-run
description: Run the open tasks of a plan: each task is built, reviewed by the lenses its diff needs, then approved or escalated. Resumes an interrupted run.
disable-model-invocation: true
argument-hint: <plan file>
---

Plugin root: ${CLAUDE_PLUGIN_ROOT}
Follow ${CLAUDE_PLUGIN_ROOT}/STYLE.md. Read ${CLAUDE_PLUGIN_ROOT}/reference/orchestrator.md first: it holds the
shared rules (files, modes, resume, job loop, completion). Use the plugin root above wherever it says `<plugin root>`.

Plan file: $ARGUMENTS (may be empty: see "Resolving arguments" in the reference)

1. Resolve the plan, then Preconditions, Resume and the mode question (orchestrator reference). The pace is guided unless the user
   chooses otherwise: see "Pace".
2. Run the Job loop for each runnable task, in order, in parallel only where the reference allows.
3. When every task has landed, do Completion.
4. Report one line per transition and a final summary: landed jobs, jobs waiting for the user.
