# End-to-end checklist

Needs a Claude Code session with the swolley-kit marketplace and the `factory` plugin installed.

Setup, once per scenario (use a fresh directory each time):

```bash
tests/e2e/make_fixture.sh /tmp/factory-fixture
cd /tmp/factory-fixture   # open Claude Code here
```

Tick each line with what you observed. Failures become fixes in the file that owns the behavior.

## A. Routing and escalation (`/factory:run docs/superpowers/plans/2026-10-13-fixture-plan.md`)

- [ ] The run states which defaults it applied (task 1 has no `Depends`) and asks for the mode; isolated is recommended.
- [ ] Choose isolated. A worktree folder `<name>-factory/_integration-...` and job worktrees appear next to the repo; the checkout of `main` is untouched.
- [ ] Job 1 (backend) selects reviewers `["code"]` only, in `factory/jobs/001-*/job.json`.
- [ ] Job 2 (`ui/Greeting.vue`) selects `code`, `ux`, `ui`; no `security`.
- [ ] Job 3 (`app/auth/session.py`) selects `code`, `security`, and the approver writes `ESCALATE`; the job ends `needs-human`.
- [ ] Jobs 1 and 2 are merged into the integration branch; each has `decision.md` starting `APPROVE`.
- [ ] Nothing was pushed (`git remote -v` is empty).
- [ ] The dashboard (`cd factory/jobs && python3 -m http.server`, open `/dashboard.html`) shows the three jobs grouped under the plan, with only the selected reviewers, and job 3 highlighted.
- [ ] `/factory:status` lists the same states.
- [ ] `/factory:approve 003-...` lands job 3 in the integration branch; the run's Completion step then asks how the integration branch reaches `main`, and does only that local action.

## B. Resume (fresh fixture, isolated mode)

For each stage, stop the session at that point, reopen it, and rerun `/factory:run <plan>`:

- [ ] While the builder runs: the same job is resumed, no second branch or worktree for that task.
- [ ] With one reviewer done and others missing: only the missing reviewers rerun.
- [ ] After the approver, before landing: the approver is not rerun if `decision.md` exists; the job lands.
- [ ] A `needs-human` job is listed and left alone.
- [ ] Delete a job's worktree by hand, rerun: that job becomes `needs-human` with a reason; no branch is recreated.

## C. Legacy plan

- [ ] `/factory:run docs/superpowers/plans/2026-10-13-fixture-legacy.md` runs and reports the defaults (tier `medium`, accept taken from steps).

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
- [ ] `/factory:status` and the end of the run list the job as waiting for you.
- [ ] `/factory:answer <job-id>` asks the same questions again; answering writes `answers-1.md` and a fresh builder continues without using a review resume.
- [ ] Answering "I do not know" moves the job to `needs-human`.
