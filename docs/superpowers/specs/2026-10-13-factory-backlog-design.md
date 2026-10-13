# Factory backlog: design

Date: 2026-10-13. Status: approved in conversation.

## Goal

Give the clay suite one tool that answers "what is left to do?" for any project that keeps plans and specs in the superpowers layout:
`/factory-backlog` for people and agents inside Claude Code, and a standalone `plan_status.py` for everyone else (Cursor, Codex, CI, contributors
without the plugin). It replaces the second plan parser that lives in `laraplate/scripts/plan-status.php`, so a plan has one meaning everywhere.

## Origin and licence

The behaviour is ported from `plan-status.php` (laraplate, AGPL). The author of both is the same person, who is the sole copyright holder, so the Python
port ships under the plugin's MIT licence. `NOTICE.md` records the origin. The PHP script is not touched by this work.

## Behaviour

Same three kinds of work item as the PHP tool, read from the same places:

- **plans**: `docs/superpowers/plans`, `.cursor/plans`, `Modules/*/docs/plans`, broken down per task with step counts (`- [ ]` open, `- [x]` done,
  `- [-]` cancelled and resolved), progress, a state per task, and evidence from the filesystem (files a task creates that exist).
- **specs**: `docs/superpowers/specs`, `.cursor/specs`, each flagged `planned`, `plan_uncited`, `unplanned` or `reference`; `INDEX.md` and `README.md` skipped.
- **todos**: `TODO`, `FIXME`, `XXX`, `@todo` markers in source files, off by default.
- **Repositories are discovered**, not declared: every directory under `--root` holding plans or specs is one, the root included.
- **State of a plan**: the front matter `status:` wins (`completed`/`done`/`shipped` done; `superseded`/`abandoned`/`cancelled` superseded;
  `in-progress`/`partial` partial; `open`/`draft`/`planned` open); otherwise the checkboxes. A plan with no checkboxes and no status is `NO BOXES`.
  Disagreement between status and checkboxes is reported as an inconsistency, except for plans with no checkboxes.
- **Default output is the open work only**: plans that are open or partial, specs without a plan, plans with no boxes. `--all` adds finished and
  superseded plans and planned specs. This is the one deliberate difference from the PHP tool, whose default shows everything and whose `--open` narrows it.
- Formats: `table` (default), `json`, `html` (one self-contained page). The tool never edits a plan.

Options keep the PHP names: `--root`, `--format`, `--kind`, `--plan`, `--repo`, `--sort date|repo|progress`, `--style icon|box`, `--summary`,
`--todo-limit`, `--out`, `--no-evidence`, `--repos`, `--stale`, plus `--all`. `--open` is accepted and is the default.

## One parser

`factory_plan.py` is the only plan parser. The backlog reads plans through it, and `resolve.py plans` reads them through the same code, so the two
cannot disagree. Parser additions needed by the backlog (cancelled steps counted as resolved, a status banner, per-task `Create:` evidence, the plan date
from the file name) go there and are covered by its tests.

## Command and views

- `skills/factory-backlog/SKILL.md`, manual only: runs the script with the user's arguments and reports the result in the chat language.
- The orchestrator reference tells agents to use it to choose work before starting a run.
- The pane shows a one-line backlog count (open plans, specs without a plan) next to the run list.
- `plan_status.py` runs with the Python standard library only and has no dependency on the rest of the plugin except `factory_plan.py`, which it
  imports from its own folder; the README says how to copy both files for use outside the plugin.

## Parity

The port is accepted when, on the real laraplate plans, every plan gets the same state, step counts and task states as the PHP tool, and any
remaining difference is listed and decided one by one. The cases of `scripts/tests/plan-status-test.sh` are ported as tests.

## Out of scope

Editing plans, writing back status, replacing the PHP script in laraplate, a web server.
