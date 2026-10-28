# Codex peer experiment: Python SDK vs CLI

This is a **manual, opt-in experiment**, not a clay integration. It changes
neither `plugins/clay/scripts/peer.py` nor the routing rules. Run it from a
Claude Code host machine with access to the Codex account.

## Purpose

Measure whether the Python SDK offers a tangible benefit over `codex exec`
for a peer review: initial turn, restarting the Python process, resuming the
same conversation, response continuity, tokens and wall time.

The two transports use **separate sessions**, **the same prompts**, the
**same working directory and model**, and a **read-only sandbox**. Neither
should change files in the target checkout. This is a test of delegated
review, not of mid-turn `steer()` or interactive collaboration.

## Requirements

- Python 3.10+.
- A Codex account already signed in locally. The SDK reuses existing
  authentication and packages its own matching runtime; the CLI comparison
  requires an independently installed `codex` in PATH.
- To install the Python SDK in an isolated virtual environment:

```bash
python3 -m venv .venv-codex-peer
.venv-codex-peer/bin/python -m pip install openai-codex
```

Do not pass credentials to the script. It does not perform login or use
OpenAI API keys, although the local Codex configuration determines billing
and usage limits. This experiment **does invoke the model** and consumes
the quota of the configured account.

## Run

Use a **disposable clone** or a checkout with no uncommitted work. Choose a
real diff and fill two prompts (examples below). The second prompt should
refer to a detail stated only in the first turn's reply, to test continuity
without supplying that detail again.

```bash
PY=.venv-codex-peer/bin/python
REPO=/absolute/path/to/disposable/checkout

$PY experiments/codex-sdk-peer/compare.py sdk start \
  --cwd "$REPO" --prompt-file experiments/codex-sdk-peer/prompts/review.md \
  --out /tmp/clay-codex-sdk-review.json

$PY experiments/codex-sdk-peer/compare.py cli start \
  --cwd "$REPO" --prompt-file experiments/codex-sdk-peer/prompts/review.md \
  --out /tmp/clay-codex-cli-review.json

# Close the Python process (each command exits), then resume by ID:
$PY experiments/codex-sdk-peer/compare.py sdk resume \
  --cwd "$REPO" --prompt-file experiments/codex-sdk-peer/prompts/follow-up.md \
  --out /tmp/clay-codex-sdk-review.json

$PY experiments/codex-sdk-peer/compare.py cli resume \
  --cwd "$REPO" --prompt-file experiments/codex-sdk-peer/prompts/follow-up.md \
  --out /tmp/clay-codex-cli-review.json
```

The state files record the `session_id`, elapsed milliseconds, whatever token
counters the transport exposes, status, error, and raw final response per
turn. They may contain repository details: keep them out of Git. Do not share
them without inspecting their contents.

A turn error is recorded in the state file for diagnosis. A failed first
turn should be retried with a **new output path**. `resume` refuses a changed
working directory, transport, model or more than one existing turn.

## What counts as evidence

- Does each fresh process successfully resume its own thread?
- Does the follow-up correctly recall a nontrivial point from the first turn?
- Does one method lose context or require additional instructions?
- Compare per-turn wall time and available token counters; the SDK and CLI
  may expose counters with different meanings. Do not infer API billing or
  cache savings from these values alone.
- Compare findings against the diff manually or with an independent hidden
  check. Fluent output is not a quality metric.

Repeat across several reviews, alternate execution order, and record the
runtime/SDK versions and model. Keep the existing clay benchmarks unchanged.

## Scope and safety

The experiment deliberately uses read-only mode for both transports. It
does not ask the model to edit code, start services or access the network.
Normal repository instructions can still influence the agent; use a trusted
disposable checkout. Avoid executing prompts from untrusted sources.

SDK docs: https://github.com/openai/codex/blob/main/sdk/python/docs/getting-started.md
API reference: https://github.com/openai/codex/blob/main/sdk/python/docs/api-reference.md
