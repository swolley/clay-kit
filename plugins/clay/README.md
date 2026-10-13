# clay

The plugin is called `clay`; the workflow it contains is the *factory*: brainstorm, plan, run.

Take an idea to reviewed, merged code. You design and plan with the model in a conversation, then
run the plan: each task is built, reviewed by the lenses its change needs, and approved or handed back to you.

## Commands

Every command is a skill named `factory-<verb>`, so it is typed `/factory-run` and listed together in the autocomplete under `/factory-`. The namespaced form `/clay:factory-run` also works. The exact spelling per host is in [docs/hosts.md](https://github.com/swolley/clay-kit/blob/master/docs/hosts.md).

| Command | Started by | What it does |
|---------|-----------|--------------|
| `/factory-brainstorm` | you, or the model when you describe new work | idea to approved design (spec for big work, short chat design for small work) |
| `/factory-plan` | you, or the model after an approved design | design to a plan of tasks and steps |
| `/factory-run [plan]` | you only | runs the plan's open tasks, asking after each task what to do next; takes the only plan with open steps when you give none |
| `/factory-task "<text>"` | you only | one ad hoc task, no plan file |
| `/factory-status` | you only | jobs, stages, verdicts, what waits for you |
| `/factory-approve [job]` | you only | lands a job that was waiting for you |
| `/factory-rework [job] <note>` | you only | sends a waiting job back to its builder |
| `/factory-answer [job] [text]` | you only | answers the questions a job is waiting on, now or later |
| `/factory-unlock [plan]` | you only | releases the run lock of a plan, for a crashed run or to edit it |

`[job]` may be left out when only one job waits, and may be the id, `002`, the task number or a piece of the id.

## Workflow

1. `/factory-brainstorm`: questions, approaches, design. You approve it.
2. `/factory-plan`: a plan with tasks, tiers and acceptance criteria. You review it.
3. `/factory-run`: for each task a builder works at the task's tier, up to four reviewers check the real diff
   (code always; ui, ux and security only when the changed paths call for them, see `routing.md`), then an
   approver lands it or escalates it. Reviewer findings are checked, not applied blindly; a builder is
   resumed at most twice. A small `light` task takes a short path with no separate reviewer.
4. When all tasks have landed, you choose how the work reaches your main branch. Nothing is ever pushed.

**Pace.** The run is guided: after each task it asks whether to go on, stop, or run the rest without asking. When a task needs a decision
(an escalation) it puts the question to you in the same prompt, so you approve, rework with a note, skip or stop without typing another command.
After "run the rest without asking" a task that needs you stops the run and lists the commands to continue.

**Models.** The task's tier picks the builder's model: `light` and `medium` the faster one, `careful` and `heavy` the stronger one (see `tiers.md`).
Some hosts cannot pass an effort, so the model is what the tier really changes.

**Isolation.** `/factory-run` recommends a development branch per plan with one worktree per job, so your checkout
is untouched and different plans can run at once in different sessions. You can instead confirm working on the current branch; jobs then
run one at a time and are committed after approval.

**One run per plan.** A run takes a lock on its plan: a second run on the same plan from another chat is refused, and the plan file and the spec
it names are read-only while it lasts (the plugin also refuses edits with an explanation). The steps are ticked at the end. `/factory-unlock`
releases a lock by hand.

## Progress in the terminal (Claude Code)

The plugin includes a mod that shows progress inside the interface, with no setup: a band above the prompt
(tasks done over total, running phases, the jobs that wait for you), a toast when a job needs you,
and a pane for whoever follows the work: one sentence of the situation, and per plan a table with a row per task in plan order
(status, a progress bar colored by tier, who is in charge and on which model, elapsed time, tokens and agent time, reviewer verdicts).
Rows that need you have buttons that write the ready command into the prompt, and the plan shows its lock.
`/factory-progress` shows or hides the band and `/factory-agents` opens the pane. They use a hyphen because Claude Code
refuses a colon in a mod command name. The mod only reads the files in `factory/jobs/`, so it costs no tokens.

State lives in `factory/jobs/` (ignored by git). A static dashboard shows it, with selectable text, copy buttons and the usage of each agent:
`/factory-run` copies the page to `factory/jobs/dashboard.html`; serve that folder with
`cd factory/jobs && python3 -m http.server` and open `/dashboard.html`.

## Plan format and why it follows superpowers

Plans live in `docs/superpowers/plans/YYYY-MM-DD-<feature>.md` and specs in `docs/superpowers/specs/`, with
`### Task N:` headings and `- [ ]` steps. This matches the superpowers conventions on purpose, for compatibility
with projects already built with that tool: their plans run here without migration. Per-task fields
(`Repo`, `Tier`, `Depends`, `Files`, `Constraints`, `Accept`, `Verify`) are optional; missing ones get defaults
and `/factory-run` tells you which. You do not have to design with this plugin: brainstorm and plan with superpowers or by
hand, and use `/factory-run` only to execute.

## Requirements

Claude Code, `git`, and `python3` (standard library only) for the plan parser, the reviewer routing and the run bookkeeping (`scripts/state.py`).
The target repo's own `AGENTS.md` or `CLAUDE.md` must say how to set up a checkout and run its tests.
Optional: with the `savvy-progress` mod installed, `/factory-run` also reports progress to its bar; nothing depends on it.

## Hosts

Claude Code is supported. Codex is **pending**: whether a Codex plugin can bundle custom agents and read
shared files is not documented, and its question tool is unverified (see [docs/hosts.md](https://github.com/swolley/clay-kit/blob/master/docs/hosts.md)).

## Credits

Derived from [obra/superpowers](https://github.com/obra/superpowers) (MIT) and
[JohnnyVizz/claude-kit](https://github.com/JohnnyVizz/claude-kit) (MIT); see [NOTICE.md](NOTICE.md).
The idea of a spec, build, review and approve loop was inspired by zazencodes
`software-factory-claude-code`, which publishes no license; none of its content is used here.
