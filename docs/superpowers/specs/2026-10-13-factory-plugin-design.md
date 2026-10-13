# Factory plugin: design

Status: draft for review. Working name: `factory` (placeholder, see Open items).

## 1. Purpose

One plugin that covers the whole path from an idea to merged code, for Claude Code and Codex:

1. **Design phase (interactive):** brainstorming and planning with human gates.
2. **Execution phase (autonomous):** each task of the approved plan runs as an isolated job that is built, reviewed from several angles and approved or escalated.

It replaces the use of the `superpowers` plugin alongside a factory. It is a derivative of
[obra/superpowers](https://github.com/obra/superpowers) (MIT) and of the structure of
[zazencodes software-factory-claude-code](https://github.com/zazencodes/zazencodes-season-3/tree/main/src/software-factory-claude-code).
Tiering ideas come from `savvy-flow`. Attribution and the MIT notice are kept in `LICENSE` and `NOTICE.md`.

### Success criteria

- A user can go from `brainstorming` to a merged integration branch with one approval for the design and one for the plan, and no further prompts unless a job escalates.
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

### 3.1 `brainstorming`

Derived from superpowers `brainstorming`, kept: path classification (spike, bounded, architectural), hard gate before implementation, written spec for architectural work.

Changed:
- Questions use the native tool (section 2).
- Spec and self-review are proportional: bounded work gets a short chat design, no file.
- No mandatory restatement of the request, no per-section approvals unless the design has more than one real decision.
- Spec location follows the repo's own convention (read from `AGENTS.md`), defaulting to `docs/superpowers/specs/`.

### 3.2 `writing-plans`

Output: a plan file with one checkbox per task. Each task is a self-sufficient brief, because workers do not see the conversation:

```markdown
- [ ] 3. <title>
  - repo: laraplate | laraplate-ui | ...
  - tier: light | medium | careful | heavy | fable
  - depends: 1, 2
  - files: <paths expected to change>
  - constraints: <what must hold; repo rules that matter>
  - accept: <numbered, verifiable criteria>
  - verify: <exact commands>
```

`repo` is required in multi-repo workspaces. `files` is a hint, not a contract: reviewer routing uses the real diff.

### 3.3 Gates

Two human gates only: design (spec or short chat design) and plan. After the plan is approved, `/factory plan` runs without further prompts.

## 4. Execution phase

### 4.1 Commands

```
/factory plan <plan-file>        run the plan's open tasks
/factory status                  list jobs and their stage
/factory approve <job-id>        merge a needs-human job into the integration branch
/factory rework <job-id> <note>  send a needs-human job back to its builder
```

`/factory <free text>` runs a single ad hoc task without a plan, for small work.

### 4.2 Preconditions

At start the orchestrator checks that the plan exists and has checkbox tasks with the fields above. If not, it stops and points to `brainstorming` and `writing-plans`. It checks that the target repo is a git repository with a clean main checkout.

### 4.3 Branches and worktrees

- One integration branch per plan and repo: `factory/<plan-slug>`, created from the repo's main branch.
- One worktree and one branch per job: `factory/<plan-slug>/<task-id>`, created from the integration branch. Worktrees live next to the repo, as in the original factory.
- Tasks run in sequence by default. Tasks whose `depends` are satisfied and whose `files` do not overlap may run in parallel.
- The main checkout is never touched except by the final merge the user chooses.

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
- **Approver** merges only when all acceptance criteria are met with evidence, all selected reviews pass, and there are no conflicts. It escalates on: licensing or ownership boundaries stated in the repo's instructions, money, auth or permissions, migrations, CI or deploy config, new dependencies, and spec assumptions that are product decisions.

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

When every task is merged, the orchestrator ticks the plan's checkboxes (so any plan-status tooling stays accurate), then hands over to the finish step: the user chooses how the integration branch reaches main. The plugin never pushes.

### 4.7 State

Runtime state in `factory/jobs/<job-id>/` of the main checkout, gitignored: `job.json` (written only by the orchestrator), `build.md`, `round-N/review-*.md`, `decision.md`, `rework-K.md`. `job.json` fields: `id`, `plan`, `task`, `repo`, `tier`, `branch`, `worktree`, `stage`, `round`, `reviewers`, `reviews`.

## 5. Dashboard

Single static `dashboard.html`, no build step, served by a plain static server, polling `job.json` files. Groups jobs by plan and repo, shows tier and only the selected reviewers per job, highlights `needs-human`. Same approach as the original factory.

## 6. Optional progress bar

If the tools `mcp__savvy-progress__progress` and `mcp__savvy-progress__step` are available, the orchestrator and builders call them (task titles identical to the Agent `description`, as that plugin requires). If absent, calls are skipped silently. No dependency.

## 7. Plugin layout

```
.claude-plugin/plugin.json
.codex-plugin/plugin.json
skills/brainstorming/SKILL.md
skills/writing-plans/SKILL.md
skills/factory/SKILL.md
agents/builder.md
agents/reviewer-code.md
agents/reviewer-ui.md
agents/reviewer-ux.md
agents/reviewer-security.md
agents/approver.md
factory/dashboard.html
STYLE.md
routing.md
tiers.md
LICENSE
NOTICE.md
docs/superpowers/specs/
```

No session-start hook. Skills trigger by `description`. If a hook proves necessary, it stays under a few lines.

## 8. Verification

- **Skills:** run each skill against a throwaway repo with scripted prompts; check the gate holds, questions use the native tool, and output length stays within the style contract.
- **Factory:** a fixture repo with a three-task plan covering a backend-only task, a UI task and a task that must escalate. Expected: backend task runs no ui/ux reviewer; UI task runs them; escalation lands in `needs-human`.
- **Routing:** unit-level check that `routing.md` patterns select the expected reviewers for sample diffs.
- **Idempotence:** rerunning `/factory plan` skips tasks already merged.

## 9. Open items

1. Plugin name (`factory` is a placeholder).
2. Native question tool name per host (Codex and others): verify from each host's documentation before writing `STYLE.md`.
3. Whether `fable` maps to a real model on the user's setup; otherwise `tiers.md` points it elsewhere.
4. Parallel tasks: confirm the file-overlap rule is enough or whether the plan should mark parallel groups explicitly.
5. Codex support for subagents with per-agent model and effort: verify before promising tiers on Codex.
