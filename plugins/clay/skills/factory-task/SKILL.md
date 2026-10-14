---
name: factory-task
description: Run one ad hoc task through the same build, review and approval loop, from a working plan the command writes itself.
disable-model-invocation: true
argument-hint: "[tier=light|medium|careful|heavy|fable] <what to do>"
---

Plugin root: ${CLAUDE_PLUGIN_ROOT}
Follow ${CLAUDE_PLUGIN_ROOT}/STYLE.md. Read these parts of the shared reference together, in one message: ${CLAUDE_PLUGIN_ROOT}/reference/orchestrator.md, ${CLAUDE_PLUGIN_ROOT}/reference/lock.md, ${CLAUDE_PLUGIN_ROOT}/reference/start.md, ${CLAUDE_PLUGIN_ROOT}/reference/job-loop.md. Read `questions.md` only when an agent asks something, `inline.md` only with the word `inline`, and `completion.md` once the task has landed (all in the same folder). Use the plugin root above wherever they say `<plugin root>`.

Task text: $ARGUMENTS

Call `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/state.py adhoc --root <repo> --text "<the task text>"` (see "Ad hoc task" in `start.md`).
It writes the working plan under `factory/jobs/_runs/` and prints `plan_file`, `plan_stem`, `title` and `tier`; a leading `tier=<name>` in the text sets the tier
(default `medium`), and an unknown tier or an empty text exits 2, which you report to the user. Use the printed `plan_file` as the plan, unchanged, and run the
Preconditions, mode question, Job loop (`job-loop.md`) and Completion (`completion.md`) for it. Completion for an ad hoc plan skips `tick-plan` and the plan commit
(there is nothing in the repo to tick), then releases the lock and runs `state.py clean`, which also deletes the working plan.
