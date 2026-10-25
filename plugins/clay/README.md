# clay

The plugin is called `clay`; the workflow it contains is the *factory*: brainstorm, plan, run.

Take an idea to reviewed, merged code. You design and plan with the model in a conversation, then
run the plan: each task is built, reviewed by the lenses its change needs, and approved or handed back to you.

## Commands

Every command is a skill named `factory-<verb>`, so on Claude Code it is typed `/factory-run` and listed together in the autocomplete under `/factory-`. The namespaced form `/clay:factory-run` also works. On Codex the same skill is `$factory-run` and on Cursor `/factory-run`; see [Hosts](#hosts). The tables below write the Claude Code and Cursor form. The exact spelling per host is in [docs/hosts.md](https://github.com/swolley/clay-kit/blob/master/docs/hosts.md).

| Command | Started by | What it does |
|---------|-----------|--------------|
| `/factory-brainstorm` | you, or the model when you describe new work | idea to approved design (spec for big work, checked by an independent spec reviewer; short chat design for small work) |
| `/factory-plan` | you, or the model after an approved design | design to a plan of tasks and steps |
| `/factory-run [plan]` | you only | runs the plan's open tasks, asking after each task what to do next; takes the only plan with open steps when you give none |
| `/factory-task [tier=<name>] "<text>"` | you only | one ad hoc task from a working plan the command writes itself under `factory/jobs/`; `/factory-task tier=careful <text>` sets the tier |
| `/factory-status` | you only | jobs, stages, verdicts, what waits for you |
| `/factory-approve [job]` | you only | lands a job that was waiting for you |
| `/factory-rework [job] <note>` | you only | sends a waiting job back to its builder |
| `/factory-answer [job] [text]` | you only | answers the questions a job is waiting on, now or later |
| `/factory-backlog [options]` | you only | open plans, specs without a plan and, on request, code markers; read-only |
| `/factory-unlock [plan]` | you only | releases the run lock of a plan, for a crashed run or to edit it |

`[job]` may be left out when only one job waits, and may be the id, `002`, the task number or a piece of the id.

## Workflow

1. `/factory-brainstorm`: questions, approaches, design. You approve it.
2. `/factory-plan`: a plan with tasks, tiers and acceptance criteria. You review it.
3. `/factory-run`: for each task a builder works at the task's tier, up to four reviewers check the real diff
   (code always; ui, ux and security only when the changed paths call for them, see `routing.md`); one interface reviewer judges ui, ux or both and writes a verdict per lens, then an
   approver lands it or escalates it. Reviewer findings are checked, not applied blindly; a job has
   at most three rounds. A `light` or `medium` task that only the code reviewer would read takes a short path: the approver writes the code review itself. When a second round still asks for changes, the third is built by a fresh builder one tier up. After a rework round only the reviewers that asked for changes, or whose paths changed, run again; a lens that passed keeps its verdict. Reviewers and the approver read one ready-made `diff.patch` per round, and the builder's checks are recorded by `state.py verify` once per state of the code, so the suite is not run again by every agent. Each task's steps are ticked in the commit that lands it. A builder keeps the documentation the task names under `Docs` true in the same change and records under `## Deviations` what it did differently from the plan; the code reviewer blocks a stale document. When every task has landed a final reviewer reads the plan's whole branch for what only shows across tasks; its findings get one fix task and a recheck of that fix, and what is still open is reported to you. When a plan is finished its header says `status: completed` and one `## Delivery status` section names the documentation that describes the work now (`Documented in`), lists the divergences and keeps the run's history in an execution record; the plan is never deleted, and the local job folders are then removed.
   `/factory-run <plan> lean` goes further for simple tasks (light or medium, files that only the code reviewer would read, declared
   `Accept` and `Verify`): the session builds them and their own checks gate them, with no reviewer or approver per task, and the
   final review of the branch reads them all; a task whose diff or checks say otherwise goes back to the full loop. Without the word the
   run proposes it when some tasks qualify, `full` turns it off, and `/factory-task lean verify="<command>" <text>` does the same for one task.
4. When all tasks have landed, you choose how the work reaches your main branch. Nothing is ever pushed.

**Pace.** The run is guided: after each task it asks whether to go on, stop, or run the rest without asking. When a task needs a decision
(an escalation) it puts the question to you in the same prompt, so you approve, rework with a note, skip or stop without typing another command.
After "run the rest without asking" a task that needs you stops the run and lists the commands to continue.

**Models.** The task's tier picks the builder's model: `light` and `medium` the faster one, `careful` and `heavy` the stronger one (see `tiers.md`).
Some hosts cannot pass an effort, so the model is what the tier really changes. Model names differ per host: [Model mapping](#model-mapping-factorymodelsjson) says how to set them.
`light` runs on `haiku` as a trial; the execution record has a Findings column (review issues per round and lens) to show whether to go back to `sonnet`.

**Isolation.** `/factory-run` recommends a development branch per plan with one worktree per job, so your checkout
is untouched and different plans can run at once in different sessions. You can instead confirm working on the current branch; jobs then
run one at a time and are committed after approval.

**One run per plan.** A run takes a lock on its plan: a second run on the same plan from another chat is refused, and the plan file and the spec
it names are read-only while it lasts (the plugin also refuses edits with an explanation). The steps of a task are ticked as it lands. `/factory-unlock`
releases a lock by hand.

## Progress in the terminal (Claude Code only)

The plugin includes a mod that shows progress inside the interface, with no setup: a band above the prompt
(tasks done over total, running phases, the jobs that wait for you), a toast when a job needs you,
and a pane for whoever follows the work: one sentence of the situation, and per plan a table with a row per task in plan order
(status, a progress bar colored by tier, who is in charge and on which model, elapsed time, tokens and agent time, reviewer verdicts).
Rows that need you have buttons that write the ready command into the prompt, and the plan shows its lock.
`/factory-progress` shows or hides the band and `/factory-agents` opens the pane. They use a hyphen because Claude Code
refuses a colon in a mod command name. The mod only reads the files in `factory/jobs/`, so it costs no tokens.
Codex and Cursor have no band or pane; the static dashboard below works on every host.

State lives in `factory/jobs/` (ignored by git). A static dashboard shows it, with selectable text, copy buttons and the usage of each agent:
`/factory-run` copies the page to `factory/jobs/dashboard.html`; serve that folder with
`cd factory/jobs && python3 -m http.server` and open `/dashboard.html`.

## Plan format and why it follows superpowers

Plans live in `docs/superpowers/plans/YYYY-MM-DD-<feature>.md` and specs in `docs/superpowers/specs/`, with
`### Task N:` headings and `- [ ]` steps. This matches the superpowers conventions on purpose, for compatibility
with projects already built with that tool: their plans run here without migration. Per-task fields
(`Repo`, `Tier`, `Depends`, `Files`, `Docs`, `Constraints`, `Accept`, `Verify`) are optional; missing ones get defaults
and `/factory-run` tells you which. `Docs` names the documentation a task keeps true, or says `none: <reason>` for a change
with no observable behaviour; a `light` task without it declares none. A cancelled step `- [-]` carries its reason on the
same line. An `INDEX.md` next to the plans or specs lists each file with what it covers and no status, which the plans hold. You do not have to design with this plugin: brainstorm and plan with superpowers or by
hand, and use `/factory-run` only to execute.

## Backlog outside the plugin

`scripts/plan_status.py` works on its own, with no agent host: copy `plan_status.py` and `factory_plan.py` together into one
folder (the first imports the second) and run it with Python 3; only the standard library is used.

```
python3 plan_status.py                  # open work under the current folder
python3 plan_status.py --root ~/work    # a whole workspace: every folder holding plans or specs is a repository
python3 plan_status.py --all --format html --out backlog.html
```

It reads `docs/superpowers/plans/` and `docs/superpowers/specs/` (also `.cursor/plans/`, `.cursor/specs/` and
`Modules/*/docs/plans/`), subfolders included, in the root and in each folder one level below it; `/factory-run`
and the pane look in the same places. It never edits anything, and `--help` lists every option.
Each plan and spec shows its last change (`upd`), the date of the last commit that touched it; a file with uncommitted
changes shows its modification date, and one git does not track shows it marked `~`. Nobody writes that date into the
plan: it is read from git, so it cannot drift. `--sort updated` lists the most recently changed plans first. A finished plan
that does not name existing documentation on a `**Documented in:**` line is reported.

## Requirements

A host that runs plugins: Claude Code, Codex or Cursor (see [Hosts](#hosts)), plus `git` and `python3` (standard library only) for the plan parser, the reviewer routing and the run bookkeeping (`scripts/state.py`).
The target repo's own `AGENTS.md` or `CLAUDE.md` must say how to set up a checkout and run its tests, and should say where its documentation lives; `/factory-plan` asks once when it does not.

## Hosts

The marketplace is `clay-kit` and the plugin `clay`. The same files serve all three hosts, with one manifest each; the host
differences the run has to handle are written in [reference/hosts.md](reference/hosts.md) and one part per host
(`reference/hosts-<host>.md`), and the facts behind them, with
their sources, in [docs/hosts.md](https://github.com/swolley/clay-kit/blob/master/docs/hosts.md).

| | Claude Code | Codex | Cursor |
|---|---|---|---|
| Install | `/plugin marketplace add swolley/clay-kit`, then `/plugin install clay@clay-kit` | `codex plugin marketplace add swolley/clay-kit`, then `codex plugin add clay@clay-kit` | CLI `/plugin marketplace add https://github.com/swolley/clay-kit`, or a team admin imports the repo in the Dashboard (Plugins & MCPs, Import from Repo), and users install from Customize. As documented by Cursor, not yet tried by us |
| Manifest read | `.claude-plugin/` | `.codex-plugin/`, and `.claude-plugin/` for the marketplace | `.cursor-plugin/` |
| Invoke | `/factory-run` (or `/clay:factory-run`) | `$factory-run`, or the `/skills` picker (`clay:factory-run`) | `/factory-run` |
| Agents | the plugin's `clay:<role>` agents | generic subagents told to read the agent file | the plugin's agents, generic ones if the host does not list them |
| Model per call | `model`, and `effort` only if the Agent tool shows it | `model` and `reasoning_effort` | reported to take only `fast` or `inherit`, no effort |
| Questions | `AskUserQuestion`, up to 4 options | `request_user_input`, 2 to 3 options, in Plan mode, else plain text | the ask-question tool (reported to depend on the model, and to be skipped in headless mode, `cursor-agent -p`) |
| Resume the builder | `SendMessage` | `send_input` | a fresh builder |
| Progress band and pane | yes | no | no |
| `factory/jobs/dashboard.html` | yes | yes | yes |

Where the host does not substitute the plugin root, a skill finds the plugin's shared files from the folder of its own `SKILL.md`
(each skill states its plugin root on its first two lines of the body).

### Model mapping (`factory/models.json`)

Model names differ per host, and the plugin fixes no OpenAI or Cursor model id. `factory/models.json` in the target repository,
beside `factory/routing.md`, is optional and maps tiers and agents to the host's own names. It has one entry per host, with
`tiers` and `agents` inside; every entry may give `model`, `effort` or both.

```json
{
  "claude": {
    "tiers": { "light": { "model": "sonnet", "effort": "low" } },
    "agents": {
      "approver": { "model": "opus", "effort": "max" },
      "approver-risky": { "model": "opus", "effort": "max" }
    }
  },
  "codex": {
    "tiers": {
      "light": { "model": "<your model id>", "effort": "low" },
      "heavy": { "model": "<your model id>", "effort": "xhigh" }
    },
    "agents": {
      "reviewer-code": { "model": "<your model id>", "effort": "medium" },
      "approver": { "model": "<your model id>" },
      "approver-risky": { "model": "<your model id>" }
    }
  },
  "cursor": {
    "tiers": { "light": { "model": "fast" }, "heavy": { "model": "inherit" } }
  }
}
```

(Replace each `<your model id>` with a model id your Codex accepts; the file is read as JSON, so no comments.)

| Host | `model` | `effort` |
|------|---------|----------|
| `claude` | `haiku`, `sonnet`, `opus`, `fable`, `inherit`, or an id starting with `claude-` | `low`, `medium`, `high`, `xhigh`, `max` |
| `codex` | any non-empty text, the id Codex knows | any non-empty text, as Codex accepts for that model |
| `cursor` | `fast` or `inherit` | not allowed: Cursor has no per-call effort |

Tiers are `light`, `medium`, `careful`, `heavy`, `fable`. Agents are `reviewer-code`, `reviewer-interface`,
`reviewer-security`, `reviewer-spec`, `approver`, `approver-risky` (the approver of a risky job), `reviewer-final` (the review of a
finished plan's branch) and `reviewer-final-risky` (the same, when any job of the run was risky). The names
`reviewer-ux`, `reviewer-ui` and `reviewer-uiux` of earlier versions are refused: use `reviewer-interface`. A `-risky` entry does not inherit from its agent: to change the agent of risky work, give the
`-risky` name its own entry.

**Resolution order**, for each of `model` and `effort` separately:

1. The entry in `factory/models.json` for the host.
2. On Claude Code, the defaults of [tiers.md](tiers.md).
3. Otherwise the session's own model: on Codex the model is not passed but the effort of `tiers.md` is kept; on Cursor nothing is passed.

On a host other than Claude Code, tier `fable` with no entry of its own is resolved as `heavy`. To check what a run will pass:

```
python3 <plugin root>/scripts/state.py model --host <host> --tier <tier>
python3 <plugin root>/scripts/state.py model --host <host> --agent <agent> [--risky]
```

Add `--root <repo>` when you do not run it from the repository. It prints the `model`, the `effort` and the `source`
(`models.json`, `tiers.md` or `session`); `null` means that key is not passed. A mistake in the file (bad JSON, an unknown host,
tier or agent, a value the host cannot take) stops the run with a message that names the key. On Codex and Cursor `source` is
`session` when the model is the session's, even when the Codex effort comes from `tiers.md`.

### Working with the other vendor (Claude Code and Codex)

With both the `claude` and the `codex` CLI on `PATH`, a run on either host asks at the start "work with <the other one>: yes (recommended) / no". On yes, the
session stays the orchestrator and some agents run through the other vendor's CLI (`scripts/peer.py`, detached, so a long build never hits a command timeout):
the builder stays on your host, and each job's reviewers and approver, and the final review, come from the vendor that did not write the code, or the record says
`review not crossed`. A vendor that hits its limit hands its agents to the other instead of stopping the run, and the execution record keeps each agent's vendor.
Cursor sessions have no peer. The optional `cross` key of `factory/models.json` sets which builders go to the peer and when a vendor counts as over its limit:

```json
{ "cross": { "builder_tiers": ["light"], "threshold": 80 } }
```

`builder_tiers` (default `[]`) lists the tiers whose builders go to the peer; `threshold` (default `80`, 1 to 100) is the Codex `used_percent` at or above
which new agents go to the other vendor. A Codex peer runs in its `workspace-write` sandbox, which has no network.

### Known limits on Codex and Cursor

- The progress band and pane exist only on Claude Code. `factory/jobs/dashboard.html` works everywhere.
- **Codex questions.** `request_user_input` works only in Plan mode by default and is refused for subagents. Outside it the run
  asks in plain text: numbered options in the reply, then it waits for your next message. A list longer than 3 options also goes
  to plain text.
- **Codex agents.** A Codex plugin cannot install agents, so each role runs as a generic subagent that is told to read the plugin's
  agent file.
- **Cursor model and effort.** The per-call model is reported to accept only `fast` or `inherit` (a forum report), and there is no effort. `inherit` is reported
  ignored in some versions of Cursor. The model of your chat applies when nothing is passed, Auto included.
- **Cursor menu.** Plugin skills marked user-only were reported hidden from the `/` menu. Type the command by name.
- **Cursor, untested.** Whether Cursor finds the plugin's agents by default, and how it imports a Claude Code plugin, are not
  tested yet; the install route above comes from Cursor's documentation, not from our own run.
- Model names differ per host, so a repository that runs on Codex or Cursor needs a `factory/models.json` to choose models per
  tier; without one Codex uses the session's model with the effort of `tiers.md`, and Cursor the model of your chat.
- **Codex reviewers.** Codex runs them as generic subagents, which ignore the `tools:` frontmatter of the agent files, so reviewers
  and the approver keep their no-code-change promise by instruction only.
- A Cursor builder cannot be resumed: a rework starts a fresh builder that reads `build.md`, the rounds and the branch log.
- The Claude Code progress mod in `hooks/` is meant to stay unloaded on Codex and Cursor: their manifests declare empty hooks.

### Manual checks on Codex and Cursor

The Codex and Cursor sections of [tests/e2e/CHECKLIST.md](https://github.com/swolley/clay-kit/blob/master/tests/e2e/CHECKLIST.md)
need the real host and cannot run in CI. Record here which were run and when.

| Host | Host version | Date | Sections run | Result |
|------|--------------|------|--------------|--------|
| Codex | | | | |
| Cursor | | | | |

## Credits

Derived from [obra/superpowers](https://github.com/obra/superpowers) (MIT) and
[JohnnyVizz/claude-kit](https://github.com/JohnnyVizz/claude-kit) (MIT); see [NOTICE.md](NOTICE.md).
The idea of a spec, build, review and approve loop was inspired by zazencodes
`software-factory-claude-code`, which publishes no license; none of its content is used here.
