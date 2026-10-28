# Host capability contract (design baseline)

This is a declarative checklist, not a new execution abstraction. Keep the
workflow and persistent job state independent of the host. Host-specific tool
calls belong at the agent execution boundary.

| Capability | Claude Code | Codex |
|---|---|---|
| Spawn role | Named plugin agent | Generic subagent + role file |
| Resume live builder | SendMessage | send_input |
| Per-call model | Supported | Supported |
| Per-call effort | Conditional on Agent tool | reasoning_effort; retry without on rejection |
| User questions | AskUserQuestion | request_user_input in Plan mode; text fallback |
| Usage metadata | subagent_tokens/tool_uses/duration_ms | Spawn result, when available |
| Progress mod | Available | Unavailable |
| Cross-vendor peer | Codex CLI | Claude CLI |

The entries summarize current behavior described by `reference/hosts-*.md`.
Reported or untested capabilities are **not** guarantees.

## Invariants

1. State transitions, reviewer lenses, security gates, and verdict formats
   must not depend on the host.
2. An unavailable host capability must use a documented fallback or stop
   with an explicit error. Do not silently claim a model/effort override.
3. The execution record must distinguish requested settings from observed
   settings when the host provides enough evidence; otherwise record unknown.
4. Agent role files and shared task artifacts remain the portable contract.
5. Do not introduce a class hierarchy or new adapter layer until concrete
   duplicated host branches justify it.

## Smoke-test matrix

On each supported host, check: spawn and record a builder; complete a review;
rework after a CHANGES verdict; recover after interrupted execution; ask for
user input; apply or decline an unsupported model/effort override; land only
after required gates. Run cross-vendor checks separately on Claude/Codex.

This document records the boundary to test. It does not assert these checks
have passed.
