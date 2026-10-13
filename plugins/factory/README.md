# factory

Take an idea to reviewed, merged code. You design and plan with the model in a conversation, then
run the plan: each task is built, reviewed by the lenses its change needs, and approved or handed back to you.

## Commands

Every command is a skill named `factory-<verb>`, so it is typed `/factory-run` and listed together in the autocomplete under `/factory-`. The namespaced form `/factory:factory-run` also works. The exact spelling per host is in [docs/hosts.md](../../docs/hosts.md).

| Command | Started by | What it does |
|---------|-----------|--------------|
| `/factory-brainstorm` | you, or the model when you describe new work | idea to approved design (spec for big work, short chat design for small work) |
| `/factory-plan` | you, or the model after an approved design | design to a plan of tasks and steps |
| `/factory-run <plan>` | you only | runs the plan's open tasks; resumes an interrupted run |
| `/factory-task "<text>"` | you only | one ad hoc task, no plan file |
| `/factory-status` | you only | jobs, stages, verdicts, what waits for you |
| `/factory-approve <job>` | you only | lands a job that was waiting for you |
| `/factory-rework <job> <note>` | you only | sends a waiting job back to its builder |
| `/factory-answer <job> [text]` | you only | answers the questions a job is waiting on, now or later |

## Workflow

1. `/factory-brainstorm`: questions, approaches, design. You approve it.
2. `/factory-plan`: a plan with tasks, tiers and acceptance criteria. You review it.
3. `/factory-run <plan>`: for each task a builder works at the task's tier, up to four reviewers check the real diff
   (code always; ui, ux and security only when the changed paths call for them, see `routing.md`), then an
   approver lands it or escalates it. Reviewer findings are checked, not applied blindly; a builder is
   resumed at most twice.
4. When all tasks have landed, you choose how the work reaches your main branch. Nothing is ever pushed.

Isolation: `/factory-run` recommends a development branch per plan with one worktree per job, so your checkout
is untouched. You can instead confirm working on the current branch; jobs then run one at a time and are
committed after approval.

## Progress in the terminal (Claude Code)

The plugin includes a mod that shows progress inside the interface, with no setup: a band above the prompt
(tasks done over total, running phases, the jobs that wait for you), a toast when a job needs you,
and a pane with the jobs by section: waiting for you, running, finished and planned, each job with its tier color,
a phase track, elapsed time and reviewer verdicts. `/factory-progress` shows or hides the band and `/factory-agents` opens the pane. They use a hyphen because Claude Code
refuses a colon in a mod command name (the skills are named the same way, so everything sits under `/factory-`). It only reads the
files in `factory/jobs/`.

State lives in `factory/jobs/` (add it to `.gitignore`). A static dashboard shows it:
`/factory-run` copies the page to `factory/jobs/dashboard.html`; serve that folder with
`cd factory/jobs && python3 -m http.server` and open `/dashboard.html`.

## Plan format and why it follows superpowers

Plans live in `docs/superpowers/plans/YYYY-MM-DD-<feature>.md` and specs in `docs/superpowers/specs/`, with
`### Task N:` headings and `- [ ]` steps. This matches the superpowers conventions on purpose, for compatibility
with projects already built with that tool: their plans run here without migration. Per-task fields
(`Repo`, `Tier`, `Depends`, `Files`, `Constraints`, `Accept`, `Verify`) are optional; missing ones get defaults
and `/factory-run` tells you which.

## Requirements

Claude Code, `git`, and `python3` (standard library only) for the plan parser and reviewer routing.
The target repo's own `AGENTS.md` or `CLAUDE.md` must say how to set up a checkout and run its tests.
Optional: with the `savvy-progress` mod installed, `/factory-run` also reports progress to its bar; nothing depends on it.

## Hosts

Claude Code is supported. Codex is **pending**: whether a Codex plugin can bundle custom agents and read
shared files is not documented, and its question tool is unverified (see [docs/hosts.md](../../docs/hosts.md)).

## Credits

Derived from [obra/superpowers](https://github.com/obra/superpowers) (MIT) and
[JohnnyVizz/claude-kit](https://github.com/JohnnyVizz/claude-kit) (MIT); see [NOTICE.md](NOTICE.md).
The idea of a spec, build, review and approve loop was inspired by zazencodes
`software-factory-claude-code`, which publishes no license; none of its content is used here.
