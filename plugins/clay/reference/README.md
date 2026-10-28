# Reference parts

For whoever maintains the plugin: the parts of the orchestrator reference, what each holds and which commands read it. The
skills name the parts they read; nothing reads this file at runtime.

| Part | Holds | Read by |
|---|---|---|
| `orchestrator.md` | the rules, the files, the modes, landing, reporting | every command except `factory-unlock` |
| `hosts.md` | which host, and what every host shares about starting an agent, its model and effort, asking the user | every command that spawns or asks: run, task, approve, rework, answer, unlock |
| `hosts-claude.md` | how Claude Code starts, resumes and asks | read after `hosts.md` on Claude Code |
| `hosts-codex.md` | how Codex starts, resumes and asks | read after `hosts.md` on Codex |
| `lock.md` | the run lock | run, task, approve, rework, answer, unlock |
| `start.md` | resolving a plan, preconditions, resume, the ad hoc task | run, task |
| `job-loop.md` | the job loop and the pace | run, task, rework, answer |
| `commands.md` | resolving a job, approve, rework, answer, status | approve, rework, answer, status |
| `questions.md` | questions from agents | answer; run, task and rework when an agent asks something |
| `lean.md` | lean tasks, built in the session and gated by their checks | run, task, when a task is lean or the user chose lean |
| `concerns.md` | pending/resolved concern recovery, approver verdict and builder rework | run, task, only after an APPROVE is questioned or when resuming a concern |
| `peer.md` | working with the peer vendor: who runs which agent, running one through the other CLI, falling back | run, task, only when the peer is on |
| `completion.md` | closing a finished plan | run, task, once every task has landed |
