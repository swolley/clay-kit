---
name: factory-task
description: Run one ad hoc task through the same build, review and approval loop, from a working plan the command writes itself.
disable-model-invocation: true
argument-hint: "[lean] [tier=light|medium|careful|heavy|fable] [verify=<command>] <what to do>"
---

Plugin root: ${CLAUDE_PLUGIN_ROOT}
If the line above does not show an absolute path, the plugin root is the folder two levels above the folder that holds this SKILL.md (the folder that contains skills/).
Follow <plugin root>/STYLE.md. Read these parts of the shared reference together, in one message: <plugin root>/reference/orchestrator.md, <plugin root>/reference/lock.md, <plugin root>/reference/start.md, <plugin root>/reference/job-loop.md, <plugin root>/reference/hosts.md. Read `questions.md` only when an agent asks something, `lean.md` only with the word `lean`, and `completion.md` once the task has landed (all in the same folder). Use the plugin root above wherever they say `<plugin root>`.

Arguments: $ARGUMENTS (the task text, which may start with `lean`, `tier=<name>` and `verify=<command>`)
If the Arguments line still shows a placeholder that starts with $, the arguments are the text the user typed after the command name.
The word `inline` of earlier versions: say in one line "inline was replaced by lean" and go on as with a leading `lean`, which stays out of `--text` too.

Call `python3 <plugin root>/scripts/state.py adhoc --root <repo> --text "<the task text>"` (see "Ad hoc task" in `start.md`), without a leading
`lean`, which only asks to run the task lean when it is eligible (`lean.md`; then Completion runs the final review).
It writes the working plan under `factory/jobs/_runs/` and prints `plan_file`, `plan_stem`, `title` and `tier`; a leading `tier=<name>` in the text sets the tier
(default `medium`), and an unknown tier or an empty text exits 2, which you report to the user. Use the printed `plan_file` as the plan, unchanged, and run the
Preconditions, mode question, Job loop (`job-loop.md`) and Completion (`completion.md`) for it. Landing skips the tick and Completion for an ad hoc plan
skips `close-plan` and the plan commit (there is nothing in the repo to tick), then releases the lock and runs `state.py clean`, which also deletes the working plan.
