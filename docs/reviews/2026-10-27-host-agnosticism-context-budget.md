# Architecture review: host independence and context budget

Status: recommendations only; no runtime behavior changed.

## Summary

The workflow is already mostly host-neutral: plan parsing, state transitions, path-based review routing, and model policy live in Python and shared artifacts. Host-specific behavior remains partly encoded as instructions that the orchestrating model interprets. Multi-host support adds complexity, but the larger cost comes from the workflow matrix (lean/full, short path, peer vendors, escalation, retries, resume, final review).

Do not rewrite the engine or introduce an adapter framework yet. Stabilize boundaries and measure actual prompt cost first.

## Findings and recommendations

### P1 — Host execution contract is implicit

The shared workflow relies on `reference/hosts.md`, per-host references, and model instructions to translate actions into host tools. This can diverge across Claude, Codex and Cursor.

**Proposal:** Document a minimal host capability contract: spawn, resume, question, model/effort override, sandbox, artifact read/write, and progress UI. For each capability distinguish supported, unavailable, and unverified. Keep the contract declarative initially; add executable adapters only where a repeated host-specific branch has been demonstrated.

**Acceptance:** An unsupported capability has a deterministic fallback or fails explicitly. Cross-host behavior is covered by contract tests without relying solely on wording checks.

### P1 — Context budget measures only the startup path

The existing factory-slim plan proposes a 4,400-word startup ceiling, but repeated agent invocations, reference loading, rework rounds and diff duplication can dominate total context use.

**Proposal:** Add a read-only budget report per command and per agent role: required instructions, conditional references, role prompt, task payload, diff size and repeated inputs. Track measured input tokens where the host exposes usage; report unknown rather than estimate as fact.

**Acceptance:** CI checks startup instructions; execution records distinguish model input tokens, output tokens and unmeasured invocations. No claim of total savings without a before/after workload comparison.

### P1 — Host-specific model defaults must not imply equivalent behavior

`models.py` resolves `model` and `effort` by host; unsupported or untested host controls can make identical tiers behave differently.

**Proposal:** Separate *requested* policy from *applied* capabilities in the execution record. Keep per-host overrides in `factory/models.json`, and surface an explicit warning when effort/model selection is unavailable or unverified.

**Acceptance:** Reports do not imply a setting was applied when the host ignored it.

### P2 — Review routing is intentionally deterministic: preserve it

`route.py` selects review lenses from actual changed paths. `state.py` reuses passing lenses when relevant fingerprints are unchanged. This is preferable to calling a classifier for every diff.

**Proposal:** Keep file-path routing as the baseline. If Jev is evaluated, run it only for ambiguous task-tier classification or after a failed round, initially in shadow mode. It may recommend stricter review, never suppress security review or bypass mandatory gates.

**Acceptance:** Default runs make no Jev calls; shadow suggestions are logged separately and do not change decisions.

### P2 — Complexity should be measured by execution paths, not LOC alone

The combination of lean/full, lite/standard, crossed/local, isolated/current, escalation and final review creates the test surface. Adding hosts multiplies this surface if every workflow branch must know host-specific behavior.

**Proposal:** Maintain a decision matrix for high-value combinations and use pairwise coverage plus critical end-to-end paths. Keep host details at the execution boundary, not in the state machine.

**Acceptance:** Every critical transition has a host-neutral test, and each host has a small real-host smoke checklist.

## Suggested incremental PR sequence

1. **Observability:** report context and usage by role; no behavior changes.
2. **Capability contract:** document host features and test fallback decisions.
3. **Small boundary cleanup:** move only demonstrated duplicated host decisions out of orchestrator instructions.
4. **Optional Jev experiment:** shadow-mode tier suggestions and outcome comparison.

## Explicit non-goals

- No new framework or abstract class hierarchy.
- No replacement of the existing `state.py` workflow.
- No unconditional model-based router.
- No mandatory Jev dependency.
- No automatic changes to security gates, review approvals or vendor policy.

## Validation plan

Run `python3 -m pytest tests -q`, `python3 scripts/validate.py`, and `node --test tests/mod/` for each implementation PR. Test actual Claude/Codex/Cursor behavior separately: text-level tests cannot prove host API compatibility.
