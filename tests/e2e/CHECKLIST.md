# End-to-end checklist

Sections A to J run in a Claude Code session with the clay-kit marketplace and the `clay` plugin installed; section G is Claude Code only.
Sections K (Codex) and L (Cursor) run in that host with the same marketplace. They need the real host and a person, so they cannot
run in CI. The "Manual checks on Codex and Cursor" table in `plugins/clay/README.md` records which were run and when; it is empty
until someone runs them.

Setup, once per scenario (use a fresh directory each time):

```bash
tests/e2e/make_fixture.sh /tmp/factory-fixture
cd /tmp/factory-fixture   # open Claude Code here
```

Tick each line with what you observed. Failures become fixes in the file that owns the behavior.

## A. Routing and escalation (`/factory-run docs/superpowers/plans/2026-10-13-fixture-plan.md`)

- [ ] The run states which defaults it applied (task 1 has no `Depends`) and asks for the mode; isolated is recommended.
- [ ] Choose isolated. A worktree folder `<name>-factory/_integration-...` and job worktrees appear next to the repo; the checkout of `main` is untouched.
- [ ] Job 1 (backend) selects reviewers `["code"]` only, in `factory/jobs/001-*/job.json`.
- [ ] Job 2 (`ui/Greeting.vue`) selects `code`, `ux`, `ui`; no `security`.
- [ ] Job 3 (`app/auth/session.py`) selects `code`, `security`, and the approver writes `ESCALATE`; the job ends `needs-human`.
- [ ] Jobs 1 and 2 are merged into the integration branch; each has `decision.md` starting `APPROVE`.
- [ ] Nothing was pushed (`git remote -v` is empty).
- [ ] The dashboard (`cd factory/jobs && python3 -m http.server`, open `/dashboard.html`) shows the three jobs grouped under the plan, with only the selected reviewers, and job 3 highlighted.
- [ ] `/factory-status` lists the same states.
- [ ] `/factory-approve 003-...` lands job 3 in the integration branch; the run's Completion step then asks how the integration branch reaches `main`, and does only that local action.

## B. Resume (fresh fixture, isolated mode)

For each stage, stop the session at that point, reopen it, and rerun `/factory-run <plan>`:

- [ ] While the builder runs: the same job is resumed, no second branch or worktree for that task.
- [ ] With one reviewer done and others missing: only the missing reviewers rerun.
- [ ] After a round where only `ux` asked for changes and the builder touched no `auth` path, round 2 runs `code` and `ux` and `security` keeps its PASS: `job.json` shows `carried: {"security": 1}`, no `round-2/review-security.md` exists, and the approver counts the carried PASS.
- [ ] `round-1/diff.patch` exists and holds the commits, the file list and the diff; `state.py checks <job>` lists the builder's runs, and the reviewers and the approver did not run the suite again (their runs, if any, are single targeted checks).
- [ ] After the approver, before landing: the approver is not rerun if `decision.md` exists; the job lands.
- [ ] A `needs-human` job is listed and left alone.
- [ ] Delete a job's worktree by hand, rerun: that job becomes `needs-human` with a reason; no branch is recreated.

## C. Legacy plan

- [ ] `/factory-run docs/superpowers/plans/2026-10-13-fixture-legacy.md` runs and reports the defaults (tier `medium`, accept taken from steps).

## D. Current-branch mode (fresh fixture)

- [ ] The run names the branch and warns because it is `main`; it requires a clean tree and waits for confirmation.
- [ ] Jobs run one at a time in the fixture directory itself; no integration branch or worktrees are created.
- [ ] The builder leaves changes uncommitted; after APPROVE the orchestrator commits with the message from `build.md`.
- [ ] An escalated job stops the run and leaves its changes in the working tree, with no reset.

## E. Style

- [ ] Questions were asked with the question tool, one at a time, with a recommended option first.
- [ ] Agent files start with their machine-readable first line and contain only findings, no narration.

## F. Questions from agents

Use a task whose brief leaves a real choice open (for example "add a cache" with no store named).

- [ ] The builder ends with `STATUS: NEEDS_INPUT` and numbered questions with a recommended answer; the job shows `waiting-input`.
- [ ] `questions-1.md` exists before the question is asked, and the dashboard shows the job as waiting for you.
- [ ] Dismiss the prompt or type an unrelated message: the job stays `waiting-input`, no `answers-1.md` is written, other jobs continue.
- [ ] `/factory-status` and the end of the run list the job as waiting for you.
- [ ] `/factory-answer <job-id>` asks the same questions again; answering writes `answers-1.md` and a fresh builder continues without using a review resume.
- [ ] Answering "I do not know" moves the job to `needs-human`.

## H. Pace and short arguments

- [ ] `/factory-run` without an argument takes the only plan with open steps, or asks which one.
- [ ] After a landed task it asks: continue, stop, or run the rest without asking.
- [ ] After an escalated task it quotes the question and offers approve, rework with a note, skip (isolated mode only) and stop; the answer is applied and the run goes on without a new command.
- [ ] Choosing "run the rest without asking" stops asking; an escalation then stops the run and lists the ready commands.
- [ ] `/factory-approve`, `/factory-rework` and `/factory-answer` work with no argument (one candidate), with `2`, with `002` and with a fragment of the id.
- [ ] The pane buttons (`approve`, `rework`, `answer`, `run`) write the right command in the prompt.
- [ ] In the dashboard the ids and commands can be selected and copied, and a selection survives the refresh.

## I. Speed and usage

- [ ] A `light` task with a small change takes the short path: no reviewer runs, `reviewers` is empty, and the approver's decision mentions it reviewed the diff.
- [ ] Builders of `light` and `medium` tasks run on the faster model, `careful` and `heavy` on the stronger one (`agents` in `job.json`).
- [ ] After each agent, `job.json` has its `tokens`, `ms`, `tools` and `runs`; the pane shows `<tokens> tok · <time> working` on the task line and totals on the plan.
- [ ] The dashboard detail of a job lists each agent with model, tokens, time and runs, and the time spent in each phase.

## J. Run lock and protected files

- [ ] While a run is going, the plan file and the spec its header names are read-only (`ls -l`), and trying to edit them fails.
- [ ] In a second chat, `/factory-run` on the same plan is refused with who holds it and since when; a different plan runs.
- [ ] The plan editing attempt through Claude Code's `Edit` or `Write` is refused by the plugin with the explanation, before the permission error.
- [ ] After the run completes the lock is gone, the permissions are back, and the plan steps were ticked and committed.
- [ ] Closing the session mid-run and starting `/factory-run` again after 30 minutes offers to take over the stale lock; `/factory-unlock` releases it and restores the files.
- [ ] The pane and the dashboard show the lock on the plan and the command to release it.

## G. Progress mod (Claude Code)

- [ ] With the plugin loaded and jobs present, the band above the prompt shows the plan, the bar and the running phases.
- [ ] `/factory-progress` hides and shows the band.
- [ ] `/factory-agents` opens the pane with the jobs and their reviewer verdicts.
- [ ] A job moving to `needs-human` or `waiting-input` raises a toast and the band shows "waiting for you".
- [ ] With no `factory/jobs` folder, nothing is drawn and no error appears in the transcript.
- [ ] Started from a workspace root with the jobs in `<repo>/factory/jobs`, the band still appears.

## K. Codex

Fresh fixture, opened in Codex. The commands are `$factory-<verb>` or the `/skills` picker.

- [ ] `codex plugin marketplace add swolley/clay-kit`, then `codex plugin add clay@clay-kit`, both succeed.
- [ ] The `/skills` picker lists the ten factory skills (namespaced `clay:factory-*`).
- [ ] `$factory-status` runs and reports no jobs.
- [ ] A one-task run: `$factory-task "<a trivial change in the fixture>"` builds, reviews and lands the change; the job folder has `build.md` and `decision.md` starting `APPROVE`, and the review files unless the task took the short path.
- [ ] One agent question is answered through the plain-text fallback: outside Plan mode the run asks in the reply with numbered options and waits; your next message is read as the answer, and an unrelated message leaves the job waiting.
- [ ] In Plan mode the same question uses `request_user_input` (2 to 3 options).
- [ ] `factory/jobs/<job>/job.json` `agents` records the model and effort actually passed (from `python3 <plugin root>/scripts/state.py model --host codex ...`); a key that was not passed is empty.
- [ ] With a `factory/models.json` that names a model for `light`, the builder is started with it and `job.json` shows it.
- [ ] The agents run as generic subagents that read the plugin's agent file (the spawn message starts with `Read <plugin root>/agents/`).
- [ ] The plugin root the session worked out is an absolute path that contains `skills/`; state what the session printed.
- [ ] A two-task run (`$factory-run` on a plan with two tasks): the second task starts without hitting a thread limit, because each reviewer and the approver were closed with `close_agent` after their files were read.
- [ ] A CHANGES round resumes the builder through `send_input` (no fresh builder), and the builder is closed when the job lands.
- [ ] Force the thread limit (set `agents.max_concurrent_threads_per_session` to 3, or use a task that routes four reviewers): a refused spawn is retried after a slot frees, the reviewers that did not fit run afterwards, and no job goes `needs-human` because of it.
- [ ] The Claude Code mod hooks file (`hooks/hooks.json`) is not loaded: no hook trust prompt, no band or pane, no error about it.

## L. Cursor

Fresh fixture, opened in Cursor. The commands are `/factory-<verb>`. The install route is Cursor's documented one (CLI
`/plugin marketplace add https://github.com/swolley/clay-kit`, or Dashboard, Plugins & MCPs, Import from Repo, then Customize for users) and has not been tried yet. The menu names come from a search excerpt of Cursor's page and may differ; correct them here if they do.

- [ ] The plugin installs from the marketplace by one of the two routes; note which one.
- [ ] The `factory-*` skills appear in the `/` menu or can be typed by name; note which of the user-only ones are hidden.
- [ ] `/factory-status` runs and reports no jobs.
- [ ] A one-task run: `/factory-task "<a trivial change in the fixture>"` builds, reviews and lands the change; the job folder has `build.md` and `decision.md` starting `APPROVE`, and the review files unless the task took the short path.
- [ ] One agent question is answered through the plain-text fallback (numbered options in the reply, the next message read as the answer), or through the ask-question tool if the host offers it.
- [ ] `factory/jobs/<job>/job.json` `agents` records the model actually passed (`fast`, `inherit` or empty) and an empty effort for every agent.
- [ ] The session reports itself as Cursor (`--host cursor` in the model calls), not Claude Code.
- [ ] The plugin root the session worked out is an absolute path that contains `skills/`; state what the session printed.
- [ ] The plugin's agents are found without a `skills` or `agents` key in `.cursor-plugin/plugin.json`: the builder starts as the plugin's `builder` agent, not as a generic one.
- [ ] User-only skills (`factory-run`, `factory-approve`, ...) are not started by the model on its own; they run only when typed.
- [ ] `inherit` behaviour: with `{"cursor": {"tiers": {"light": {"model": "inherit"}}}}` in `factory/models.json`, note whether the subagent runs on the model of the chat or on another; `inherit` is reported ignored in some versions.
- [ ] After a rework, a fresh builder is started and reads `build.md`, the rounds and the branch log.
- [ ] The Claude Code mod hooks file (`hooks/hooks.json`) is not loaded: no band or pane, no error about it.
