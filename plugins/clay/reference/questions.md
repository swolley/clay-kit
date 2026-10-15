# Questions from agents

Part of the orchestrator reference (see `orchestrator.md`). `<plugin root>` is the path your skill states. Follow `<plugin root>/STYLE.md`. `<repo>` is the root of the target repository's own checkout.

The source of truth is a file, never the prompt. A subagent cannot ask the user; it ends with
`STATUS: NEEDS_INPUT` and numbered questions in build.md.

1. Copy the questions to `questions-<k>.md` (next unused `k`) and set `stage: "waiting-input"` before asking anything.
2. Ask the user with the question tool (`hosts.md`, "Asking the user"), batching the job's questions, each option labeled and the agent's
   recommended answer first. Write the answers to `answers-<k>.md` only when the user has actually given them.
3. Anything that is not an answer leaves the job waiting: a dismissed prompt, a timeout or auto-continue, or an
   unrelated message from the user. Handle an unrelated message normally, never apply a default or the
   recommended answer, and do not touch the job. Keep working on the other, independent jobs.
4. When answers exist, set `stage: "build"` and start a fresh builder (named `builder-<job-id>`, spawned as in step 2 of `job-loop.md`) that is told to
   read `answers-<k>.md` and update build.md. This does not use up the review resumes.
5. If the user says they do not know, set `needs-human` and quote the open questions.

Say it plainly when a job is waiting: `003-rate-limit: waiting for you, 2 questions (use /factory-answer 003-rate-limit)`.
At the end of a run, and in `status`, list every job that is waiting for you.

