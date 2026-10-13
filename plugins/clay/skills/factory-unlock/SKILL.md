---
name: factory-unlock
description: Release the run lock of a plan: use it when a run was closed or crashed, or when you need to edit the plan or its spec. Makes them writable again.
disable-model-invocation: true
argument-hint: <plan> [--force]
---

Plugin root: ${CLAUDE_PLUGIN_ROOT}
Follow ${CLAUDE_PLUGIN_ROOT}/STYLE.md. Read these parts of the shared reference together, in one message: ${CLAUDE_PLUGIN_ROOT}/reference/lock.md. Use the plugin root above wherever they say `<plugin root>`.

Plan: $ARGUMENTS (may be empty)

1. List the locks: `python3 <plugin root>/scripts/state.py lock list --root <repo>`. With no argument take the only lock, or ask which one with the question tool,
   showing each plan, since when, and whether it is stale.
2. A lock with a recent heartbeat belongs to a run that may still be going in another session. Say so and ask for explicit confirmation before releasing it, because
   that run would go on without its lock.
3. Release it: `state.py lock release --root <repo> --plan <plan> --force`. This restores the permissions of the plan and its spec. Say what was restored.
