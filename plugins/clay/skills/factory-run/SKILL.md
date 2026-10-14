---
name: factory-run
description: Run the open tasks of a plan: each task is built, reviewed by the lenses its diff needs, then approved or escalated. Resumes an interrupted run.
disable-model-invocation: true
argument-hint: <plan file> [inline]
---

Plugin root: ${CLAUDE_PLUGIN_ROOT}
Follow ${CLAUDE_PLUGIN_ROOT}/STYLE.md. Read these parts of the shared reference together, in one message: ${CLAUDE_PLUGIN_ROOT}/reference/orchestrator.md, ${CLAUDE_PLUGIN_ROOT}/reference/lock.md, ${CLAUDE_PLUGIN_ROOT}/reference/start.md, ${CLAUDE_PLUGIN_ROOT}/reference/job-loop.md. Read `questions.md` only when an agent asks something, `inline.md` only with the word `inline`, and `completion.md` once every task has landed (all in the same folder). Use the plugin root above wherever they say `<plugin root>`.

Arguments: $ARGUMENTS (a plan, may be empty: see "Resolving a plan" in `start.md`; the word `inline` asks for the mode in `inline.md`)

1. Resolve the plan, take the run lock (`lock.md`: stop if another run holds the plan), then Preconditions, Resume and the mode question (`start.md`, `orchestrator.md`). The pace is guided unless the user
   chooses otherwise: see "Pace" in `job-loop.md`.
2. Run the Job loop (`job-loop.md`) for each runnable task, in order, in parallel only where the reference allows.
3. When every task has landed, read `completion.md` and do it.
4. Report one line per transition and a final summary: landed jobs, jobs waiting for the user.
