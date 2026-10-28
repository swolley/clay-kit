# Orchestrator concerns

Read this part only if the orchestrator sees an explicit task requirement missing after an approver's APPROVE, or if a resumed job has a pending or resolved concern in job.json. The orchestrator is not a reviewer: the approver decides.

## Open or resume

1. Run `state.py concern <job>`. It creates `concern-1.md` before recording `concern.status: pending`. If an interruption left the file or state behind, the same command returns the original file with `resumed: true`; it does not spend another concern. Do not overwrite existing numbered points on resume.
2. Fill `## Points` in that file with numbered findings. Every finding must quote the missing requirement from task.md and identify relevant code at `file:line`. An empty skeleton must never be sent to the approver.
3. Read decision.md. If it already has a fresh `## Concerns` answer under `APPROVE`, or `## Issues` under `CHANGES`, go directly to resolution. Otherwise send the original approver back with the file path. Claude resumes it with SendMessage; Codex restarts a new approver with `Concerns: <absolute file>` and the usual job coordinates. The approver rewrites decision.md after comparing the findings with task.md and the diff. It must reject interpretations the task leaves open.

## Resolve and route

4. Run `state.py resolve-concern <job>` after the approver has written its decision; the command requires numbered points and a nonempty answer section, and marks `concern.status: resolved` with `verdict: APPROVE|CHANGES`. If it returns `ok: false`, do not land: correct the missing artifact or ask the approver to write its answer, then retry. On resume with `resolved`, use the recorded verdict without reopening the concern.
5. `APPROVE`: follow Landing. `CHANGES`: the approver upheld the concern; this is ordinary rework, **not** a user question. When the current review round is 1 or 2, follow step 5 of job-loop.md for that round's normal resume/escalation rule. Set the stage to build, and give the builder the absolute paths to both `decision.md` (the upheld `## Issues`) and `concern-1.md` (the source points). Tell it to read both and reply to each issue in build.md, then route the changed code with `state.py route <job>` for the next review round. The landing commands refuse an upheld concern until this subsequent review round produces a fresh `APPROVE`. After round 3, use step 5's human escalation; do not start a fourth automatic round.
6. There is only one concern per job. A resolved concern is not reopened after rework, even if the orchestrator still disagrees: follow the approver's subsequent normal verdict, or report the remaining disagreement without vetoing the landing.

An interrupted job with `concern.status: pending` is never ready to land. Resolve it first; the original APPROVE in decision.md is not a fresh answer.
