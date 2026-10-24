# Factory slim reference: design

Date: 2026-10-24. Status: approved in conversation, from the analysis of the reference parts.

> **Amended 2026-10-25:** the word cap is 4,800, not 4,400: the spec's cuts reached about 4,600, and compressing real rules further was ruled out by the user.

## Goal

Cut what `factory-run` and `factory-task` read before their first step, without losing a rule. Today `factory-run` reads its
SKILL, `orchestrator.md`, `lock.md`, `start.md`, `job-loop.md` and `hosts.md`: about 6,000 words, of which about 2,000 are
duplicates, descriptions of what `state.py` already does, or rows for hosts the session is not on. Success: `factory-run` reads at
most 4,400 words at the start on every host (its SKILL, the parts its first read lists and the host part; `lean.md`,
`questions.md` and `completion.md` are read on condition and not counted), a test keeps it there, and every rule removed is either
kept in one other place or done by a script.

## Approach

Structural cuts, not a terser style. Every sentence that goes is one of: a rule stated in another part (it stays there), a
description of what a script does (the script stays the authority), text for a host the session is not on (it moves to that
host's part), or a feature removed on purpose (`inline`, the separate UI reviewers, `savvy-progress`). The rest of the wording is
untouched. Rejected: a telegraphic "caveman" style (the parts are full of conditions and order of steps, and dropping articles
and connectives makes them ambiguous; a misread rule costs a round, far more than the words saved, and the parts are read from
the prompt cache anyway); moving the reference into the agents' prompts (the orchestrator still needs it).

## 1. Hosts, split per host

- `reference/hosts.md` keeps only what every host shares: "Which host" (the detection order and `<host>`), the generic
  start-up message for a host without the named agent, `state.py model` and its exit 2, the recording rule's common part
  (record what was passed, never a value that was not applied), the plain-text form, and one line: "Then read
  `hosts-<host>.md` in the same folder: it is your host part."
- New `reference/hosts-claude.md`, `hosts-codex.md`, `hosts-cursor.md`, each with that host's row of today's table (start an
  agent, per-call keys, resume, question tool and its option and per-call limits), its "Model and effort" bullet, its usage
  fields, and its own notes: the Codex thread limit and `close_agent` order go to `hosts-codex.md`, the fresh builder for want of
  a resume and the ask-question caveats to `hosts-cursor.md`, the progress band and pane to `hosts-claude.md`.
- The other parts keep saying "as `hosts.md` says" and "the question tool"; `hosts.md` defines both as what the host part says.
- Every skill that reads `hosts.md` today (run, task, approve, rework, answer, unlock, brainstorm, plan) reads it the same way;
  the host part is read in the next message, once the host is known.

## 2. `orchestrator.md`

- **Files.** The table of paths under `factory/jobs/` stays, with the `_runs/<plan-slug>.json` row cut to what the orchestrator
  uses (mode, integration branch, pace, `base`, `final`). The `job.json` example, its field list, the id reservation with
  `mkdir`, the `.gitignore` and dashboard copy (lines 45-69 today) go: `begin-job`, `after-agent`, `setup` and the other
  `state.py` commands write all of it. One sentence replaces them: `job.json` is written only by `state.py`; read `stage`,
  `round`, `tier`, `lean`, `lite`, `head` and `reviews` from it, never edit it.
- **Role.** "You write `job.json`" becomes "you run `state.py` for every change of a job", which ends the contradiction with the
  Job loop.
- **Dashboard.** The `python3 -m http.server` line goes; the README already gives it.
- **Parts table.** It moves to a new `reference/README.md`, for whoever maintains the plugin; the skills already list what each
  reads. The opening paragraph keeps the instruction to read the listed parts in one message.
- **`savvy-progress`.** The reporting paragraph goes, with its mention in `hosts.md` and the README: the plugin's own progress
  band and pane (`hooks/`) show the same, and the mod is not installed.

## 3. Headers

The line "Part of the orchestrator reference ... `<plugin root>` ... STYLE.md ... `<repo>`" at the top of every part goes.
Each skill already states the plugin root and STYLE.md before listing its parts; `orchestrator.md` keeps the one definition of
`<repo>` under Files, and a skill that reads a part using `<repo>` without reading `orchestrator.md` (`factory-unlock`,
`factory-brainstorm`, `factory-plan`) states it in its SKILL.

## 4. `start.md`

- **Resolving a plan.** The internals of the audit and of `unclassified` (which script prints them, with which flags) go; it
  keeps: show `unclassified` as a count, and when the audit names the chosen plan, say so in one line and ask before running.
  The paragraph that runs `plan_status.py` before choosing goes: `preflight` has already listed the plans.
- **Fable question.** The sentence that copies the default models per host goes; the options are labelled with what
  `state.py model --host <host> --tier <tier>` prints, as now.
- **Resume.** "A named builder does not survive its session ..." stays here and goes from `hosts.md`.
- **Ad hoc task.** What Completion skips for an ad hoc plan is said only in `completion.md`; here one clause points to it.

## 5. `lock.md`

- The tick and close of the read-only plan stay in Landing (`orchestrator.md`) and Completion; `lock.md` keeps "never edit the
  plan or the spec while the lock is held, and tell the builders not to".
- The bullet on `approve`, `rework` and `answer` from another session goes: those three skills already say it.
- The release when a job needs a person in `auto` pace stays here and goes from the Pace section of `job-loop.md`, which points
  to it.

## 6. `job-loop.md`

- The recording paragraph keeps the `after-agent` command and its roles; what each field holds and where the usage comes from is
  in the host part.
- Step 5 loses the `inline` sentence (section 8).
- Step 4 spawns one interface reviewer (section 9) instead of choosing among three.

## 7. `completion.md`

When the final review runs is said once, in step 1 (skipped for a plan of one task and for an ad hoc plan, unless a job of the
run was lean); the opening paragraph on ad hoc plans lists the other skipped steps and points to step 1 for the final review.

## 8. Inline mode removed

Lean covers what inline was for (`light` tasks built in the session) and more. `reference/inline.md` goes, with the `inline`
argument of `factory-run` and `factory-task` (argument hint `[lean|full]`), the inline sentence in step 5 of `job-loop.md`, the
"Lean and inline" section of `lean.md`, the README sentence and the tests that assert inline text. A user who still types
`inline` gets one line, "inline was replaced by lean", and the run goes on as with `lean`.

## 9. One interface reviewer

`reviewer-ux`, `reviewer-ui` and `reviewer-uiux` share their whole frame (inputs, diff, dev server, output format) and differ
only in the questions they ask. They become one agent, `agents/reviewer-interface.md`: its prompt names the lenses to judge
(`Lenses: ux`, `Lenses: ui` or `Lenses: ux ui`), it writes `round-<N>/review-<lens>.md` for each lens named, each with its own
verdict, and it keeps both question lists under their lens.

- The routing lenses stay `ux` and `ui`: `routing.md`, carried lenses and `verdicts` are unchanged.
- Step 4 of the Job loop: when `rerun` holds `ux`, `ui` or both, spawn one `reviewer-interface` with those lenses and
  `Port: 5101+10n`; its usage is recorded under the role `interface`.
- `models.py` and `tiers.md`: one entry, `reviewer-interface` (sonnet, medium), replaces the three. A `factory/models.json` that
  still names `reviewer-ux`, `reviewer-ui` or `reviewer-uiux` exits 2 naming the key and saying it is now `reviewer-interface`.
- The progress mod (`hooks/model.ts`) keeps showing the pending lenses (`ux, ui`) and finds their model under the role
  `interface`, and still under `uiux`, `ux` and `ui` in the jobs of a run started before the change.

## Testing

- `tests/test_orchestrator_text.py`:
  - a word budget: for each host, the SKILL of `factory-run` plus every part it reads at the start plus `hosts-<host>.md` is at
    most 4,400 words; the same for `factory-task`. It replaces the 18% cap on `hosts.md`;
  - the parts table is read from `reference/README.md`, and every part on disk is listed there;
  - no part opens with the old header line; `orchestrator.md` defines `<repo>`;
  - nothing names `inline.md`, `reviewer-uiux`, `reviewer-ux`, `reviewer-ui` or `savvy-progress`;
  - the interface reviewer: step 4 names `reviewer-interface`, `Lenses:` and the role `interface`;
  - the host parts hold the Codex thread limit, the Cursor fresh builder and each host's question tool, and `hosts.md` points to
    them.
- `tests/test_models.py`: `reviewer-interface` resolves on every host; the three old keys in `models.json` exit 2 with the hint.
- `tests/mod/model.test.ts`: a job with role `interface` and an old job with `uiux` both show their reviewer's model.
- `scripts/validate.py`: the three host parts exist; a skill that lists `reference/hosts.md` passes as today; the agent file
  `reviewer-interface.md` and its frontmatter are checked like the others.
