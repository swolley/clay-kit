# Commands that act on a job

Part of the orchestrator reference (see `orchestrator.md`). `<plugin root>` is the path your skill states. Follow `<plugin root>/STYLE.md`. `<repo>` is the root of the target repository's own checkout.

## Resolving a job

A command may get a short token or nothing. Resolve a job with
`python3 <plugin root>/scripts/resolve.py job "<token>" --stages <stages> --root <repo>`: the stages are `needs-human`
for approve and rework, `waiting-input` for answer. A `match` is the job. `candidates` mean you ask which one with the
question tool, listing each as its id and stage. With no match, say the `reason` and list what is eligible. A token can be
nothing (the only eligible job), the full id, `002`, a task number, or a fragment of the id.

## The other commands

- **approve `<job-id>`**: only valid on a job in `needs-human`. Isolated: check the integration worktree is clean, then
  Land. Current branch: Land (commit). See Landing in `orchestrator.md`.
- **rework `<job-id>` `<note>`**: only valid on a job in `needs-human`. Write the note verbatim to `rework-<k>.md`
  (next unused k), set `stage: "build"`, spawn a fresh `builder-<job-id>` with the model and effort of the task's tier as in step 2 of `job-loop.md`, told to read that file and update
  build.md; a rework gets a fresh budget of 2 resumes. Continue from the check of build.md in step 2 of the Job loop (`job-loop.md`).
- **answer `<job-id>` `[text]`**: only valid on a job in `waiting-input`. Without text, ask the pending questions again
  from the file. With text, treat it as the answers, check it covers every question (ask again for what is missing), save
  it to `answers-<k>.md` and continue from step 4 of `questions.md`.
- **status**: list jobs from `job.json` files: id, plan, stage, round, reviewers with verdicts; say which
  wait for the user. Read-only.
