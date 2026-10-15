---
name: factory-run
description: Run the open tasks of a plan: each task is built, reviewed by the lenses its diff needs, then approved or escalated. Resumes an interrupted run.
disable-model-invocation: true
argument-hint: <plan file> [inline]
---

Plugin root: ${CLAUDE_PLUGIN_ROOT}
If the line above does not show an absolute path, the plugin root is the folder two levels above this SKILL.md.
Follow <plugin root>/STYLE.md. Read these parts of the shared reference together, in one message: <plugin root>/reference/orchestrator.md, <plugin root>/reference/lock.md, <plugin root>/reference/start.md, <plugin root>/reference/job-loop.md, <plugin root>/reference/hosts.md. Read `questions.md` only when an agent asks something, `inline.md` only with the word `inline`, and `completion.md` once every task has landed (all in the same folder). Use the plugin root above wherever they say `<plugin root>`.

Arguments: $ARGUMENTS (a plan, may be empty: see "Resolving a plan" in `start.md`; the word `inline` asks for the mode in `inline.md`)
If the Arguments line still shows a placeholder that starts with $, the arguments are the text the user typed after the command name.

1. Resolve the plan, take the run lock (`lock.md`: stop if another run holds the plan), then Preconditions, Resume and the mode question (`start.md`, `orchestrator.md`). The pace is guided unless the user
   chooses otherwise: see "Pace" in `job-loop.md`.
2. Run the Job loop (`job-loop.md`) for each runnable task, in order, in parallel only where the reference allows.
3. When every task has landed, read `completion.md` and do it.
4. Report one line per transition and a final summary: landed jobs, jobs waiting for the user.
