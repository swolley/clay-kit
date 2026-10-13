# swolley-kit

Personal marketplace of plugins, skills and tools for Claude Code, Codex and other agent hosts.

| Tool | What it does |
|------|--------------|
| [factory](plugins/factory) | From an idea to merged code: `brainstorm`, `plan`, then `run`, with routed review and approval. |

## Install (Claude Code)

In Claude Code:

```
/plugin marketplace add swolley/swolley-kit
/plugin install factory@swolley-kit
```

Restart the session afterwards. Commands are namespaced by the plugin, for example `/factory:run`.

## Development

```bash
python3 -m venv .venv && .venv/bin/pip install pytest
.venv/bin/python -m pytest tests -q
.venv/bin/python scripts/validate.py
```

`scripts/validate.py` checks manifests, skill and agent frontmatter, and the rules of the tool
(no dependency on other plugins, one style contract, invocation policy of each command).

## Layout and licenses

- `plugins/<tool>/`: one self-contained tool per folder.
- `docs/superpowers/specs/` and `plans/`: the design record, in the superpowers layout so projects built with that tool stay compatible.
- `LICENSE`: MIT, for this repository's own work. `licenses/`: texts and index of the third-party licenses; derived files are listed in each tool's `NOTICE.md`.
