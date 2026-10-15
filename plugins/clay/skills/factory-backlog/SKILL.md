---
name: factory-backlog
description: Show the open work of a repository or workspace: plans with steps left, specs without a plan and, on request, code markers. Read-only.
disable-model-invocation: true
argument-hint: [--all] [--repo <name>] [--kind plans,specs,todos] [--stale] [--format table|json|html]
---

Plugin root: ${CLAUDE_PLUGIN_ROOT}
If the line above does not show an absolute path, the plugin root is the folder two levels above this SKILL.md.
Follow <plugin root>/STYLE.md. Read <plugin root>/reference/orchestrator.md first: it holds the
shared rules (files, modes, resume, job loop, completion). Use the plugin root above wherever it says `<plugin root>`.

Arguments: $ARGUMENTS (may be empty)
If the Arguments line still shows a placeholder that starts with $, the arguments are the text the user typed after the command name.

1. Run `python3 <plugin root>/scripts/plan_status.py <arguments>`, where `<arguments>` is the Arguments line above, from the repository (or workspace) the user is working in.
   With no arguments it lists the open work only; `--all` adds finished and superseded plans and planned specs.
2. Report the result in the language of the chat: what is open per repository, which specs have no plan, and what to do first.
   Keep the tool's numbers and file names as printed. If it fails, show its message and stop.
3. Do not edit any plan or spec, and do not start a run.
