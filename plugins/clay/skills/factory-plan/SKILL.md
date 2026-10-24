---
name: factory-plan
description: Use when a design or spec is approved and the work has several steps, before touching code. Writes an implementation plan of tasks and steps that the run command can execute.
argument-hint: <spec path>
---

Plugin root: ${CLAUDE_PLUGIN_ROOT}
If the line above does not show an absolute path, the plugin root is the folder two levels above the folder that holds this SKILL.md (the folder that contains skills/).

# Plan

Turn an approved spec into a plan of small tasks that someone who has not seen this
conversation can execute. Follow `<plugin root>/STYLE.md`. `<repo>` in the parts of `reference/` is the root of the target
repository's own checkout.

Derived from the superpowers `writing-plans` skill (MIT); see NOTICE.md.

## Before writing

- Run `python3 <plugin root>/scripts/plan_status.py` from the repo. When plans are still open, name them in
  one line and recommend finishing one before starting another; then go on if the user does.
- When the plans or specs folder holds an `INDEX.md`, read it first and open only the files it points you to.
- Find where the repo keeps its documentation in its instructions (`AGENTS.md` or `CLAUDE.md`). When they do
  not say, ask the user once (`STYLE.md` rule 1) and suggest recording the answer in those instructions.

## Where and what format

Save to `docs/superpowers/plans/YYYY-MM-DD-<feature>.md` of the repo that owns the work.
The folders, the file names and the syntax below match superpowers on purpose: projects
built with that tool keep working here without migration, and the reverse.

- Header: `# <Feature> Plan`, then `Goal`, `Architecture`, `Tech Stack` and `Spec` lines,
  then `Global Constraints` (project-wide rules from the spec, exact values) and
  `Review Focus` (failure modes the spec implies but no task tests, most likely first).
- One `### Task N: <title>` per task, with `- [ ]` steps under it. Checkbox states are
  `[ ]` open, `[x]` done, `[-]` cancelled. A cancelled step carries its reason on the same line;
  dropped work is never left `[ ]`, or the plan reads as open forever.
- Per-task fields are plain lines, never checkboxes, so progress tools do not count them.
- When the plans folder holds an `INDEX.md`, add one line for the plan: its file name and what it covers.
  No status there: `plan_status.py` reads it from the plan, and a second copy drifts.

A plan is a dated record of what was decided, not documentation: it stays true about one moment, while the
documentation describes the present. Nothing ships described only in a plan. While a run holds the plan it
is read-only and what the run does differently is recorded in its jobs; outside a run, update the plan when
a decision, the scope or the order changes.

## Task template

```markdown
### Task 1: Component name

**Repo:** my-repo
**Tier:** careful
**Depends:** 1
**Files:** `src/thing.py`, `tests/test_thing.py`
**Docs:** `docs/thing.md`
**Constraints:** keep the public signature stable
**Accept:** 1. Returns the parsed value. 2. Rejects empty input.
**Verify:** `pytest tests/test_thing.py -v`

- [ ] **Step 1: Write the failing test** `test_rejects_empty_input` asserting `ValueError`
- [ ] **Step 2: Run it; expect failure** with "parse not defined"
- [ ] **Step 3: Implement `parse(text: str) -> int`** in `src/thing.py`
- [ ] **Step 4: Run it; expect pass**
- [ ] **Step 5: Commit** `feat: add parse`
```

All fields are optional. Give each task a Commit step with its message (`**Step N: Commit** `feat: ...``) and mark the files it creates with `Create:` when you list them as bullets: the run command uses both to notice work that is already done. When missing, the runner applies defaults and says so:
`Tier` medium, `Repo` the repo holding the plan, no `Depends`, `Accept` taken from the steps, no `Docs`
(said for every tier but `light`).

## Documentation

Every task that changes behaviour keeps the documentation that describes it true, in the same task:
the next agent reads it instead of working the behaviour out from the code.

- `Docs` names the files the task updates or creates, in the place the repo's instructions give.
- Document what the code cannot say on its own: contracts, invariants, decisions and their reasons,
  extension points, limits, permissions, configuration options and environment variables added, removed
  or renamed. Never restate the code (lists of methods, fields or files): that is stale at the next change.
- A task that changes no observable behaviour writes `**Docs:** none: <reason>` (a typo, formatting,
  a narrow test fix, an internal refactor). A `light` task with no `Docs` line declares the same.

## How to size and word tasks

- A task is the smallest unit with its own test cycle that a reviewer could reject
  without rejecting its neighbor. Fold setup, config and docs into the task that needs them.
- `Tier` is the cheapest level that gets the task right the first time: light for mechanical work, medium for standard
  features and for fixes whose diagnosis is complete, careful only for writes into user files or shared state, behaviour
  derived from a comparison or ambiguous spec, or security; heavy for unfamiliar code or unknown cause. Size alone never
  decides. Fable only when clearly needed. Details in `tiers.md`.
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
6. Every task that changes behaviour names its `Docs`, or says `none` and why.

## Hand over

Save, commit, and ask the user to review the plan (`STYLE.md` rule 1, with the question tool
`<plugin root>/reference/hosts.md` names for this host). Execution is the
`/factory-run` command of this tool; do not pick an execution method for the user.
Name every fable task in the handover, with its title, so the user sees at plan review which tasks `run` will ask about.
