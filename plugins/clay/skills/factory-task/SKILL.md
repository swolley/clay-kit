---
name: factory-task
description: Run one ad hoc task through the same build, review and approval loop, from a working plan the command writes itself.
disable-model-invocation: true
argument-hint: "[lean] [tier=light|medium|careful|heavy|fable] [verify=<command>] <what to do>"
---

Plugin root: ${CLAUDE_PLUGIN_ROOT}
If the line above does not show an absolute path, the plugin root is the folder two levels above the folder that holds this SKILL.md (the folder that contains skills/).
Follow <plugin root>/STYLE.md. Read these parts of the shared reference together, in one message: <plugin root>/reference/orchestrator.md, <plugin root>/reference/lock.md, <plugin root>/reference/job-loop.md, <plugin root>/reference/hosts.md. Read `questions.md` only when an agent asks something, `peer.md` only when the user chose to work with the peer, `lean.md` only with the word `lean`, and `completion.md` only when the job ran lean (all in the same folder). This command needs only the steps below, not the run setup of `factory-run`. Use the plugin root above wherever they say `<plugin root>`.

Arguments: $ARGUMENTS (the task text, which may start with `lean`, `tier=<name>` and `verify=<command>`)
If the Arguments line still shows a placeholder that starts with $, the arguments are the text the user typed after the command name.
The word `inline` of earlier versions: say in one line "inline was replaced by lean" and go on as with a leading `lean`, which stays out of `--text` too.

1. **Plan.** `python3 <plugin root>/scripts/state.py adhoc --root <repo> --text "<the task text>"`, without a leading `lean`, which only asks
   to run the task lean when it is eligible (`lean.md`). It writes the working plan under `factory/jobs/_runs/` (git ignores it) and prints
   `plan_file`, `plan_stem`, `title` and `tier`: a leading `tier=<name>` sets the tier (default `medium`); an unknown tier or an empty text
   exits 2, which you report. Use `plan_file` unchanged as the plan.
2. **Check.** `state.py preflight --root <repo> --plan-file <plan> --repo-name <name> --host <host>`. `git_identity.ok` false: give its
   `reason` and stop. Say in one line which defaults the parser applied and any warnings. `done_signals` on the task: it may already be
   done, so ask before building it. An explicit `tier=fable` is the user's choice and is not asked about again.
3. **Start.** Ask once with the question tool: the mode (isolated, recommended, or the current branch, which needs a clean tree; name it
   and warn when it is the default branch), adding "work with <peer>: yes (recommended) / no" when `peer.found` (with yes read `peer.md`).
   Then run the Job loop (`job-loop.md`) from step 0 for task 1, with `--cross on|off --host <host>` on `state.py run`.
4. **Finish.** A job that ran lean: read `completion.md`, which runs its final review. Otherwise there is no final review, no
   documentation pass and no `close-plan` (the plan is not in the repo): release the lock, run `state.py clean --root <repo> --plan <plan_stem>`,
   which also deletes the working plan, and in isolated mode ask with the question tool how the integration branch reaches the main
   branch: merge it, prepare a pull request without pushing, keep the branch, or discard it. Do only the chosen local action.
