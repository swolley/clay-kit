# Factory tool: design (swolley-kit)

Status: draft for review. Tool name: `factory` (placeholder, see Open items), first package of a personal multi-tool repository (section 7).

## 1. Purpose

One plugin that covers the whole path from an idea to merged code, for Claude Code and Codex:

1. **Design phase (interactive):** brainstorming and planning with human gates.
2. **Execution phase (autonomous):** each task of the approved plan runs as an isolated job that is built, reviewed from several angles and approved or escalated.

It replaces the use of the `superpowers` plugin alongside a factory.

### Sources and licensing

Checked on 2026-10-13. What may be reused depends on each source's license.

| Source | License (verified) | What we may do | What we take |
|--------|--------------------|----------------|--------------|
| [obra/superpowers](https://github.com/obra/superpowers) v6.4.2 | MIT, Copyright (c) 2025 Jesse Vincent | Derive and adapt text, keeping the copyright and permission notice | Skill wording of `brainstorming` and `writing-plans` as a base, then rewritten |
| [JohnnyVizz/claude-kit](https://github.com/JohnnyVizz/claude-kit) (`savvy-flow`, `savvy-progress`), commit `272a877` | MIT, Copyright (c) 2026 johnnyvizz | Derive and adapt text, keeping the notice | Tier model, self-contained briefs, `filemap.md` idea; progress tool names for the optional integration |
| [zazencodes/zazencodes-season-3](https://github.com/zazencodes/zazencodes-season-3/tree/main/src/software-factory-claude-code) `software-factory-claude-code` | **No license** (GitHub reports none; no LICENSE file in the repo). All rights reserved by default | **Ideas only.** Do not copy or closely paraphrase its files (skill, agents, dashboard, README, BUILD_PROMPT) | The general pattern: orchestrator plus agents, file-based hand-off, parallel reviewers, escalate-or-merge. Patterns and ideas are not protected; its expression is |

Rules that follow:
- Everything derived from the zazencodes factory is written from scratch from the pattern above. No text, prompt wording, code or HTML is carried over, and the dashboard is original code.
- MIT-derived files carry the original copyright and permission notice in the tool's `NOTICE.md`, naming the source and version.
- The zazencodes project is credited in the README as inspiration only, with no claim of derivation, and that wording avoids implying a license.
- `scripts/check_overlap.py` reports the 6-word sequences the plugin shares with a checkout of another project; run it against the zazencodes folder before publishing. On 2026-10-13 the first agent drafts shared 347 sequences with it and were rewritten from the spec alone; the result is 65, which are file names, the verdict first-line contract, HTML boilerplate and frontmatter tool lists.
- Before publishing the repository, re-check each source's license, and ask the zazencodes author for permission if any of their content is ever wanted verbatim.

### Success criteria

- A user can go from `brainstorm` to a merged integration branch with one approval for the design and one for the plan, and no further prompts unless a job escalates.
- No agent or skill output is longer than the task needs. Explanations are understandable without being stripped of technical context.
- Questions to the user use the host's native structured-question tool; plain text is only a fallback.
- Only the agents a job needs are run.
- The plugin has no hard dependency on `superpowers`, `savvy-progress` or any other plugin.

### Non-goals

- Not a CI system. Build, test and lint commands come from the target repo's own instructions (`AGENTS.md` or `CLAUDE.md`).
- No push to remotes, ever.
- No project-specific rules in the plugin. Everything repo-specific is read from the repo.

## 2. Shared style contract (`STYLE.md`)

Every skill and agent file references `STYLE.md` instead of restating it, so a style change is made in one place.

1. **Questions.** Ask through the host's structured-question tool. One question at a time, options with a one-line consequence each, a recommended option first. Fall back to numbered options in plain text only when the host has no such tool. A table in `STYLE.md` maps host to tool name; entries are verified at implementation time, not assumed.
2. **Explanations.** Default level: what changes, why it matters, and the technical term only when needed with one line of context. Never drop the context needed to decide. A deeper explanation is given only when the user asks for it ("explain", `--deep`).
3. **Agent output.** First line machine-readable (`VERDICT:`, `STATUS:`, `APPROVE`/`ESCALATE`). Then only findings as `path:line`, cause, fix. No narration of steps taken.
4. **Chat language** follows the repo's instructions; code, comments and docs content follow the repo's convention.

## 3. Design phase

### 3.1 `brainstorm`

Derived from superpowers `brainstorming`, kept: path classification (spike, bounded, architectural), hard gate before implementation, written spec for architectural work.

Changed:
- Questions use the native tool (section 2).
- Spec and self-review are proportional: bounded work gets a short chat design, no file.
- No mandatory restatement of the request, no per-section approvals unless the design has more than one real decision.
- Spec location follows the repo's own convention (read from `AGENTS.md`), defaulting to `docs/superpowers/specs/`.

### 3.2 `plan` and the plan format

**Why superpowers conventions are kept.** The folder layout (`docs/superpowers/{specs,plans}/`), the file name patterns and the plan syntax deliberately match those of superpowers. The reason is compatibility: projects already built with superpowers keep their specs and plans where tools expect them, can be executed by the factory without migration, and can still be read by superpowers or by tooling written for it. A change to these conventions is a compatibility break and must be recorded in this spec.

Plans live in `docs/superpowers/plans/YYYY-MM-DD-<feature>.md` of the repo that owns the work (the same place and name pattern as superpowers). The format is a **compatible superset** of the superpowers plan format, so existing plans, and tooling that reads them such as a `plan-status` script, keep working.

Kept from the superpowers format: the `# Title` heading, `Goal`, `Architecture`, `Spec` header lines, a `### Task N: <title>` heading per task, and `- [ ]` / `- [x]` / `- [-]` (open, done, cancelled) checkbox steps under each task. Tooling in the user's workspace treats a heading starting with Task, Phase, Step, Milestone or Wave as a task and each checkbox under it as a step, so the factory keeps exactly that structure.

Added, per task, as plain (non-checkbox) lines directly under the task heading, all optional:

```markdown
### Task 3: <title>

**Repo:** laraplate | laraplate-ui | ...
**Tier:** light | medium | careful | heavy | fable
**Depends:** 1, 2
**Files:** <paths expected to change>
**Constraints:** <what must hold; repo rules that matter>
**Accept:** <numbered, verifiable criteria>
**Verify:** <exact commands>

- [ ] Step: write the failing test ...
- [ ] Step: implement ...
```

Rules:
- The field lines contain no checkbox, so a checkbox-counting tool never mistakes them for steps.
- Defaults when a field is missing, which is how an older superpowers plan runs: `Tier` medium, `Repo` the repo holding the plan, `Depends` none, `Accept` derived from the task's steps, `Verify` taken from the repo's own instructions. The orchestrator tells the user which defaults it applied.
- Each task is a self-sufficient brief, because workers do not see the conversation. `Repo` is required in multi-repo workspaces. `Files` is a hint, not a contract: reviewer routing uses the real diff.
- A task is done when all its non-cancelled steps are checked. The factory ticks the steps it completed and never edits cancelled ones.
- The superpowers header line pointing to `subagent-driven-development` or `executing-plans` is not written: execution is `/factory:run`.

### 3.3 Gates

Two human gates only: design (spec or short chat design) and plan. After the plan is approved, `/factory:run` runs without further prompts.

## 4. Execution phase

### 4.0 Skills, names and invocation

Every command is its own skill, so each one appears in the host's command autocompletion and nothing has to be remembered. Names read as one pipeline: `brainstorm` (idea to design), `plan` (design to plan), `run` (plan to code).

| Skill | Started by | Why |
|-------|-----------|-----|
| `brainstorm` | the user, or the model on its own when the user describes new work | conversational, ends at the user's approval gate |
| `plan` | the user, or the model on its own after an approved design | conversational, ends at the user's review of the plan |
| `run`, `task`, `approve`, `rework`, `answer` | the user only (model invocation disabled) | start autonomous work that spends tokens, creates branches and worktrees and can merge |
| `status` | the user only | read-only, but kept explicit so it is never run by surprise |

Model invocation is controlled per skill. The orchestration logic shared by `run`, `task`, `approve`, `rework` and `status` (job loop, modes, resume, state) lives in one reference file of the plugin, which these skills read; how a skill points at a shared file is recorded in `docs/hosts.md`. Commands are namespaced by the plugin (`/factory:run`); the exact spelling per host is also in `docs/hosts.md`. The autocompletion behavior (one entry per skill, no sub-arguments) is observed from installed plugins, not yet tested for this tool.

### 4.1 Commands

```
/factory:run <plan-file>         run the plan's open tasks
/factory:task "<text>"           run one ad hoc task without a plan
/factory:status                  list jobs and their stage
/factory:approve <job-id>        merge a needs-human job into the integration branch
/factory:rework <job-id> <note>  send a needs-human job back to its builder
/factory:answer <job-id> [text]  answer the questions a job is waiting on (or see them again)
```

`/factory:task` is for small work that does not need a plan. Each command is a separate skill, so free text never collides with a command name.

### 4.2 Preconditions

At start the orchestrator checks that the plan exists and has checkbox tasks with the fields above. If not, it stops and points to `brainstorm` and `plan`. It checks that the target repo is a git repository with a clean main checkout.

### 4.3 Isolation mode: branches and worktrees

At the start of `/factory:run` the orchestrator proposes a mode through the native question tool, with isolation as the recommended option, and records the choice in the plan's run state.

**Isolated (recommended, default).**
- One integration branch per plan and repo: `factory/<plan-slug>`, created from the repo's main branch.
- One worktree and one branch per job: `factory/<plan-slug>/<task-id>`, created from the integration branch. Worktrees live next to the repo.
- Tasks run in sequence by default. Tasks whose `depends` are satisfied and whose `files` do not overlap may run in parallel.
- The user's checkout is never touched except by the final merge the user chooses.

**Current branch (user opt-in).**
- The user confirms working directly on the branch they are on. No integration branch, no worktrees, no merge step: each approved job is committed on the current branch.
- Jobs run strictly in sequence, since they share one working tree. Parallel execution is disabled in this mode.
- Preconditions: clean working tree at start, and the orchestrator names the branch it will commit to and waits for confirmation. If the branch is `main` or the repo's default branch, the confirmation says so explicitly.
- A job that fails review or escalates stops the run, leaving earlier approved jobs committed and the failing job's changes in the working tree for the user to inspect, with no automatic reset.
- The user can keep working in other worktrees of the same repo in parallel; the factory only owns the checkout it was started in.

The mode applies per run. `job.json` records it (`mode: "isolated" | "current-branch"`).

### 4.4 Job loop

```
task -> builder -> [routed reviewers] -> WAIT FOR ALL
              ^                              |
              +-- any CHANGES: resume -------+  (max 2 resumes)
                                             v all PASS
                                         approver -> APPROVE: merge into integration branch
                                                  -> ESCALATE: needs-human
```

- **Spec of the job** is the task brief plus a link to the design spec. There is no separate `spec-writer` agent.
- **Builder** runs at the task's tier. It carries, as short sections of its own prompt, test-first development, systematic debugging, and verification before claiming done (commands run, results recorded). It updates `filemap.md` when it adds or moves files.
- **Reviewer routing** is decided after the build from the real diff, using `routing.md` (path pattern to reviewer). `reviewer-code` and `approver` always run. `reviewer-ui`, `reviewer-ux`, `reviewer-security` run only when a changed path matches. The routing result is written to `job.json` and the round waits only for the selected reviewers.
- **Reviews are adversarial:** the builder's report is a claim to verify against the diff, not a fact.
- **Approver** merges (isolated mode) or commits (current-branch mode) only when all acceptance criteria are met with evidence, all selected reviews pass, and there are no conflicts. It escalates on: licensing or ownership boundaries stated in the repo's instructions, money, auth or permissions, migrations, CI or deploy config, new dependencies, and spec assumptions that are product decisions.

### 4.5 Tiers

| Tier | Intended use | Default model / effort |
|------|--------------|------------------------|
| light | mechanical edits, config, running builds and tests | opus / low |
| medium | standard feature work with clear requirements | opus / medium |
| careful | delicate but understood changes, many edge cases | opus / high |
| heavy | unfamiliar code, unclear root cause | opus / xhigh |
| fable | hardest problems; reserved | fable / high |

Rule: the cheapest tier that gets the task right the first time; when unsure, the next one up, except `fable`, which is chosen only when clearly needed. Models and efforts are configuration in `tiers.md`, so a host without the `fable` model maps it to another model. The tier is applied by spawning the builder with the matching model and effort.

### 4.6 Completion

When every task is done, the orchestrator ticks the steps of each completed task in the plan (so any plan-status tooling stays accurate). In isolated mode it then hands over to the finish step: the user chooses how the integration branch reaches main. In current-branch mode the commits are already on the branch and there is nothing to merge. The plugin never pushes.

### 4.7 State

Runtime state in `factory/jobs/<job-id>/` of the main checkout, gitignored: `job.json` (written only by the orchestrator), `build.md`, `round-N/review-*.md`, `decision.md`, `rework-K.md`. `job.json` fields: `id`, `plan`, `task`, `repo`, `mode`, `tier`, `branch`, `worktree`, `stage`, `round`, `reviewers`, `reviews`.

### 4.7a Questions from agents

A subagent cannot use the question tool, so it ends with `STATUS: NEEDS_INPUT` and numbered questions (options and a
recommended answer) in `build.md`. The orchestrator saves them to `questions-<k>.md` and sets stage `waiting-input`
before it asks, because the source of truth is a file and not the prompt. It asks through the native question tool,
batching them, and writes `answers-<k>.md` only when answers were actually given. A dismissed prompt, a timeout or
auto-continue, or an unrelated user message leaves the job waiting: no default and no recommended answer is ever applied,
and independent jobs continue. `/factory:answer <job-id> [text]` asks the pending questions again, or takes written
answers, at any later time, also from another session; resuming `run` re-asks them too. With answers the builder is
restarted without using a review resume. "I do not know" moves the job to `needs-human`. `BLOCKED` is kept for faults no
answer can fix.

### 4.8 Resuming an interrupted run

There is no separate resume command: `/factory:run <plan>` is idempotent and resumes by itself.

At start the orchestrator reads the plan and `factory/jobs/` and classifies each task:

| Task state | Found | Action |
|------------|-------|--------|
| Done | all non-cancelled steps checked | skip |
| Merged but not ticked | `job.json` stage `merged` (or committed, in current-branch mode) | tick the steps, then skip |
| Interrupted | `job.json` with stage `spec`, `build`, `review` or `approve` | resume from the recorded stage |
| `needs-human` | `job.json` stage `needs-human` | do not touch; list it and wait for `/factory:approve` or `/factory:rework` |
| `waiting-input` | `job.json` stage `waiting-input` | ask the pending questions again from `questions-<k>.md` |
| Not started | no job | start normally |

Resuming a stage:
- `spec` or `build` with no `build.md`: keep the worktree and branch, start a fresh builder with the task brief and the commits already on the branch.
- `build` with `build.md`, or `review` with some `review-*.md` present: keep the finished files, rerun only the missing parts of the current round. A reviewer that did not finish is rerun.
- A named builder does not survive its session. A resumed builder is a new agent that reads `build.md`, the round folders and the git log of the job branch, as in a rework.
- `approve` with no `decision.md`: rerun the approver.

Safety:
- The worktree and branch of a job are reused, never recreated. If they are missing or the branch has diverged from what `job.json` records, the job goes to `needs-human` with the reason.
- Current-branch mode: a job interrupted mid-build leaves uncommitted changes. The orchestrator shows them and asks whether to continue from them, stash them or stop. It never resets them on its own.
- `job.json` is rewritten only by the orchestrator on each transition, so after a crash it is at worst one transition behind. A step that is repeated must therefore be safe to repeat; the orchestrator checks for existing output before redoing it.
- The orchestrator reports what it found and what it will resume, in one line per job, before it continues.

## 5. Dashboard

Single static `dashboard.html`, no build step, served by a plain static server, polling `job.json` files. Groups jobs by plan and repo, shows tier and only the selected reviewers per job, highlights `needs-human`. Same approach as the original factory.

## 6. Progress in the terminal

### 6.1 Progress mod (Claude Code only, part of the factory plugin)

A Claude Code mod in `plugins/factory/hooks/` draws the progress inside the interface. It depends on nothing but the
files the run command already writes: every few seconds it reads `factory/jobs/*/job.json` and `factory/jobs/_runs/*.json`
in the working folder and one level below it (a workspace root with several repos).

- **Band above the prompt** while any job is running or waiting: a bar of tasks done over total for the active plan,
  its name, the phases of the running jobs (`build`, `review r1 2/3`, `approve`) and, highlighted, how many jobs
  are waiting for the user. A Hide button, and the `factory-progress` command, toggle it.
- **Toast** when a job starts waiting for the user (`needs-human` or `waiting-input`), and once at start-up if
  some already are.
- **Pane** with the plans, their jobs and each job's reviewer verdicts, opened by the `factory-agents` command.
- Commands are `factory-progress` and `factory-agents`. A mod command name may only hold letters, digits, `_` and `-`:
  the engine refused `factory:progress` in a live session (verified 2026-10-13), so the colon form that skills get from
  their plugin namespace is not available to mod commands.
- The run file carries `total` and `done` so the mod never parses plans. The pure logic (parsing, summary, bar,
  scan of the folders with an injected file system) is in `hooks/model.ts` and tested with Node's runner.
- Hosts without mods ignore the folder; nothing else depends on it.

### 6.2 Optional savvy-progress hook

If the tools `mcp__savvy-progress__progress` and `mcp__savvy-progress__step` exist, the orchestrator also reports to them
(task titles identical to the Agent `description`). Only the orchestrator does; builders do not. Skipped silently if
absent. With the mod above this is redundant, and kept only for people who run that plugin.

## 7. Repository and plugin layout

The repository is a personal toolkit that will hold several installable tools (plugins, skills, mods) for IDEs
and agent hosts, not only this one. It follows the marketplace layout used by claude-kit: a manifest at the
root and one folder per tool under `plugins/`. The factory is the first tool, `plugins/factory/`.

```
.claude-plugin/marketplace.json     name, owner, plugins[] (name, source, version, category)
plugins/
  factory/                          this spec
    .claude-plugin/plugin.json
    .codex-plugin/plugin.json
    skills/{brainstorm,plan,run,task,status,approve,rework}/SKILL.md
    reference/orchestrator.md       shared logic read by run, task, status, approve, rework
    scripts/{factory_plan,route}.py plan parser and reviewer routing (stdlib only)
    hooks/{hooks.json,register.tsx,model.ts}  progress mod (Claude Code); types/index.d.ts is its state contract
    agents/{builder,reviewer-code,reviewer-ui,reviewer-ux,reviewer-security,approver}.md
    factory/dashboard.html
    STYLE.md  routing.md  tiers.md
    NOTICE.md                       MIT notices for superpowers and claude-kit (zazencodes: credit only, see Sources and licensing)
  <future tools>/
scripts/validate.py                 repo-level validator (development only, not installed)
shared/                             optional: content reused by several tools (for example STYLE.md)
docs/superpowers/specs/             design record for the whole repo
LICENSE                             MIT (own work), covers the repo; per-tool NOTICE.md for MIT-derived work
```

Rules for the toolkit:
- Each tool is self-contained and installable on its own; no tool requires another.
- Shared content (the style contract) is either copied at build time into each tool or lives in `shared/` with a documented sync step, so an installed tool never depends on a path outside its folder. The choice is an open item.
- `category` in the manifest distinguishes kinds of tool (`skill`, `mod`, and so on).
- Derived work keeps its original copyright notice in the tool's `NOTICE.md`.

No session-start hook in the factory. Skills trigger by `description`. If a hook proves necessary, it stays under a few lines.

## 8. Verification

- **Skills:** run each skill against a throwaway repo with scripted prompts; check the gate holds, questions use the native tool, and output length stays within the style contract.
- **Factory:** a fixture repo with a three-task plan covering a backend-only task, a UI task and a task that must escalate. Expected: backend task runs no ui/ux reviewer; UI task runs them; escalation lands in `needs-human`.
- **Routing:** unit-level check that `routing.md` patterns select the expected reviewers for sample diffs.
- **Resume:** kill a run at each stage (`spec`, `build`, `review` with one reviewer done, `approve`) and in current-branch mode with uncommitted changes; rerun `/factory:run` and check that merged tasks are skipped, the interrupted job is resumed without a duplicate branch, and `needs-human` jobs are left alone.

## 9. Open items

1. Plugin name (`factory` is a placeholder).
2. Native question tool name per host (Codex and others): verify from each host's documentation before writing `STYLE.md`.
3. Whether `fable` maps to a real model on the user's setup; otherwise `tiers.md` points it elsewhere.
4. Parallel tasks: confirm the file-overlap rule is enough or whether the plan should mark parallel groups explicitly.
5. Codex support for subagents with per-agent model and effort: verify before promising tiers on Codex.
6. How shared content (`STYLE.md`) is distributed to installed tools: copy at build time or `shared/` with a sync step.
7. Marketplace manifest fields for Codex and other hosts: verify each host's format before writing it; only the Claude Code format has been checked (against claude-kit).
