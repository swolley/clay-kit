---
name: plan
description: Use when a design or spec is approved and the work has several steps, before touching code. Writes an implementation plan of tasks and steps that the run command can execute.
argument-hint: <spec path>
---

# Plan

Turn an approved spec into a plan of small tasks that someone who has not seen this
conversation can execute. Follow `${CLAUDE_PLUGIN_ROOT}/STYLE.md`.

Derived from the superpowers `writing-plans` skill (MIT); see NOTICE.md.

## Where and what format

Save to `docs/superpowers/plans/YYYY-MM-DD-<feature>.md` of the repo that owns the work.
The folders, the file names and the syntax below match superpowers on purpose: projects
built with that tool keep working here without migration, and the reverse.

- Header: `# <Feature> Plan`, then `Goal`, `Architecture`, `Tech Stack` and `Spec` lines,
  then `Global Constraints` (project-wide rules from the spec, exact values) and
  `Review Focus` (failure modes the spec implies but no task tests, most likely first).
- One `### Task N: <title>` per task, with `- [ ]` steps under it. Checkbox states are
  `[ ]` open, `[x]` done, `[-]` cancelled.
- Per-task fields are plain lines, never checkboxes, so progress tools do not count them.

## Task template

```markdown
### Task 1: Component name

**Repo:** my-repo
**Tier:** careful
**Depends:** 1
**Files:** `src/thing.py`, `tests/test_thing.py`
**Constraints:** keep the public signature stable
**Accept:** 1. Returns the parsed value. 2. Rejects empty input.
**Verify:** `pytest tests/test_thing.py -v`

- [ ] **Step 1: Write the failing test** `test_rejects_empty_input` asserting `ValueError`
- [ ] **Step 2: Run it; expect failure** with "parse not defined"
- [ ] **Step 3: Implement `parse(text: str) -> int`** in `src/thing.py`
- [ ] **Step 4: Run it; expect pass**
- [ ] **Step 5: Commit** `feat: add parse`
```

All fields are optional. When missing, the runner applies defaults and says so:
`Tier` medium, `Repo` the repo holding the plan, no `Depends`, `Accept` taken from the steps.

## How to size and word tasks

- A task is the smallest unit with its own test cycle that a reviewer could reject
  without rejecting its neighbor. Fold setup, config and docs into the task that needs them.
- `Tier` is the cheapest level that gets the task right the first time: light for
  mechanical work, medium for standard features, careful for delicate changes, heavy for
  unfamiliar code. Use fable only when clearly needed.
- A step is one action with a checkable result. A test step names the test and its
  assertions; a code step gives the exact signature and file and lets the implementer
  write the body; a verification step gives the command and the output that means pass.
- Decide only what the implementer cannot: files, names, signatures, values the spec
  pins, which test proves what. A plan longer than the code it describes has written the
  code instead.
- Each task states what it consumes from earlier tasks and what it produces, with exact names.

## Check before handing over

1. Every spec requirement has a task.
2. Every step lets the implementer do exactly one reasonable thing.
3. Names and signatures agree across tasks.
4. The Review Focus failure modes each have a test in the task that owns the code.
5. The plan is not several times longer than the spec.

## Hand over

Save, commit, and ask the user to review the plan (`STYLE.md` rule 1). Execution is the
`run` command of this tool; do not pick an execution method for the user.
