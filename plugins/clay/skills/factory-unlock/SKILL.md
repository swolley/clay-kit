---
name: factory-unlock
description: Release the run lock of a plan: use it when a run was closed or crashed, or when you need to edit the plan or its spec. Makes them writable again.
disable-model-invocation: true
argument-hint: <plan> [--force]
---

Plugin root: ${CLAUDE_PLUGIN_ROOT}
If the line above does not show an absolute path, the plugin root is the folder two levels above the folder that holds this SKILL.md (the folder that contains skills/).
Follow <plugin root>/STYLE.md. Read these parts of the shared reference together, in one message: <plugin root>/reference/lock.md, <plugin root>/reference/hosts.md. Use the plugin root above wherever they say `<plugin root>`; `<repo>` is the root of the target repository's own checkout.

Arguments: $ARGUMENTS (a plan, may be empty)
If the Arguments line still shows a placeholder that starts with $, the arguments are the text the user typed after the command name.

1. List the locks: `python3 <plugin root>/scripts/state.py lock list --root <repo>`. With no argument take the only lock, or ask which one with the question tool,
   showing each plan, since when, and whether it is stale.
2. A lock with a recent heartbeat belongs to a run that may still be going in another session. Say so and ask for explicit confirmation before releasing it, because
   that run would go on without its lock.
3. Release it: `state.py lock release --root <repo> --plan <plan> --force`. This restores the permissions of the plan and its spec. Say what was restored.
