# clay-kit

Personal marketplace of plugins, skills and tools for Claude Code, Codex and other agent hosts.

| Tool | What it does |
|------|--------------|
| [clay](plugins/clay) | From an idea to merged code: `/factory-brainstorm`, `/factory-plan`, then `/factory-run`, with routed review and approval. |

## Install (Claude Code)

In Claude Code:

```
/plugin marketplace add swolley/clay-kit
/plugin install clay@clay-kit
```

Restart the session afterwards. Commands are named `factory-<verb>`, for example `/factory-run`; the namespaced form `/clay:factory-run` also works.

## Development

```bash
python3 -m venv .venv && .venv/bin/pip install pytest
.venv/bin/python -m pytest tests -q
.venv/bin/python scripts/validate.py
```

`scripts/typecheck-mod.sh <loaded copy of the mod>` type-checks the progress mod against the engine's own types (a missing
identifier in a render hook makes the engine skip the whole hook and draw nothing, and the static validation does not see it).
`node --test tests/mod/` runs the pure logic of the mod.
`python3 scripts/check_overlap.py --zazencodes` downloads the one folder of the project the factory was inspired by (it publishes no license)
and reports how many 6-word sequences the plugin shares with it; run it before publishing.

`scripts/validate.py` checks manifests, skill and agent frontmatter, and the rules of the tool
(no dependency on other plugins, one style contract, invocation policy of each command).

## Layout and licenses

- `plugins/<tool>/`: one self-contained tool per folder.
- `docs/superpowers/specs/` and `plans/`: the design record, in the superpowers layout so projects built with that tool stay compatible.
- `LICENSE`: MIT, for this repository's own work. `licenses/`: texts and index of the third-party licenses; derived files are listed in each tool's `NOTICE.md`.
