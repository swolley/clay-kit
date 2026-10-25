---
name: factory-brainstorm
description: Use before creative work such as a new feature, component, behavior change or project. Turns an idea into an approved design through short questions, then hands over to the plan skill. Skip for pure bug fixes with a known cause.
argument-hint: <idea or goal>
---

Plugin root: ${CLAUDE_PLUGIN_ROOT}
If the line above does not show an absolute path, the plugin root is the folder two levels above the folder that holds this SKILL.md (the folder that contains skills/).

# Brainstorm

Turn an idea into a design the user has approved, before any code is written.
Follow `<plugin root>/STYLE.md` for questions, explanations and length. `<repo>` in the parts of `reference/` is the root of the
target repository's own checkout.

Derived from the superpowers `brainstorming` skill (MIT); see NOTICE.md.

## 1. Classify, and say it

Name the path before the first question so the user can override it:

- **Spike**: a feasibility question whose output is an answer, not code to keep.
  State the question and the probe in 2-3 sentences, get a nod, find out as
  cheaply as correctness allows, report a recommendation. Anything built is
  throwaway.
- **Bounded**: a well-scoped change to a flow that already exists in this repo.
  Ask the questions that matter, give a short design in chat, stop. No spec file.
- **Architectural**: a new project or subsystem, or a change to interfaces others
  depend on. Full path below.

When unsure, take the heavier path. Hidden complexity found later moves the path
up, never down: stop and say so.

## 2. Gate

No implementation of any kind (code, scaffolding, dependency installs, external
projects) until the user approves the design of the selected path. A reply
approves only what was actually shown. Reading the project is always allowed.

## 3. Understand

- Read the repo's instructions, recent commits and the files the idea touches.
- Run `python3 <plugin root>/scripts/plan_status.py` from the repo. When plans are still open, name them in one
  line and recommend finishing one before starting new work; when the idea is already planned or specified, say so.
  Go on if the user does.
- When the specs or plans folder holds an `INDEX.md`, read it first and open only the files it points you to.
- If the idea spans several independent subsystems, say so and split it; design
  the first piece only.
- Ask for what is missing, one question at a time (`STYLE.md` rule 1, with the question tool
  `<plugin root>/reference/hosts.md` names for this host): purpose,
  who it is for, constraints, what success looks like. Do not ask what the request
  or the repo already answers.
- Write back your understanding in a few lines, separating what the user said from
  what you assumed, and let them correct it before designing.

## 4. Design

- Propose 2-3 approaches with trade-offs, the recommended one first. Remove anything
  the goal does not need.
- Present the design in sections sized to their difficulty: architecture,
  components and their boundaries, data flow, errors, testing. Ask for approval
  once per decision that is really open, not after every paragraph.
- Prefer small units with one purpose and a clear interface. Follow the patterns
  already in the repo; improve only what the goal touches.

## 5. Write the spec (architectural path only)

- Save to the place the repo's instructions name for specs; default
  `docs/superpowers/specs/YYYY-MM-DD-<topic>-design.md`. When that folder holds an `INDEX.md`, add one line
  for the spec, its file name and what it covers, no status. Commit it. A spec records a decision at a date;
  the behaviour it leads to is described in the repo's documentation once it ships.
- Check it once yourself: no placeholders, no contradictions, one plan's worth of scope,
  no requirement that can be read two ways. Fix inline.
- Spawn the `reviewer-spec` agent as `<plugin root>/reference/hosts.md` says, with the model and effort that
  `python3 <plugin root>/scripts/state.py model --host <host> --agent reviewer-spec --root <repo>` prints (`<repo>` is this
  repository's root), and a prompt of `Plugin root: <plugin root>`, the spec path and the repo. Its reply starts with
  `VERDICT: PASS` or `VERDICT: CHANGES`. Fix every issue it raises in the spec and say what you changed; one
  round is enough, do not loop.
- Ask the user to review the written spec. Wait for approval.

## 6. Hand over

Architectural: invoke the `factory-plan` skill of this tool. Nothing else.
Bounded: after the user says yes, implement through the repo's normal workflow.
Spike: the report is the end.

## Thoughts that mean stop

| Thought | Reality |
|---------|---------|
| "Too simple to need a design" | Pick the path by the repo: a bounded change gets a short design in chat, an architectural one a spec. |
| "I will call it bounded and skip the spec" | Reaching for a label to skip work is itself the doubt: take the heavier path. |
| "The design is obvious, I will start while they read it" | The gate is the approval, not the length. Present, then stop until the user says yes. |
| "I know this kind of app, so it is bounded" | Bounded measures the repo. With no existing flow to change, it is architectural. |
| "The spike works, so I will keep the code" | A spike's output is an answer. Keeping the code is a new request: classify it again. |
| "They approved the idea, so the spec is approved too" | A reply approves only what was shown. Each stage needs its own yes. |
