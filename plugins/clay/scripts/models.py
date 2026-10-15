#!/usr/bin/env python3
"""Model and effort per host for a tier or an agent, from the defaults of tiers.md and the optional <root>/factory/models.json.

models.json: {"<host>": {"tiers": {"<tier>": {"model": M, "effort": E}}, "agents": {"<agent>": {"model": M, "effort": E}}}}
Hosts are claude, codex and cursor; both keys of an entry are optional and the entry wins over the defaults, per key.
Vocabulary: claude takes its model names and efforts, codex any non-empty text, cursor `fast` or `inherit` and no effort.
"""
import json
from pathlib import Path

from factory_plan import TIERS

HOSTS = ("claude", "codex", "cursor")

# Mirrors the two tables of tiers.md; tests/test_models.py fails when they disagree.
TIER_DEFAULTS: dict[str, tuple[str, str]] = {
    "light": ("haiku", "low"),
    "medium": ("sonnet", "medium"),
    "careful": ("opus", "high"),
    "heavy": ("opus", "xhigh"),
    "fable": ("fable", "high"),
}
AGENT_DEFAULTS: dict[str, tuple[str, str]] = {
    "reviewer-code": ("sonnet", "medium"),
    "reviewer-ui": ("sonnet", "medium"),
    "reviewer-ux": ("sonnet", "medium"),
    "reviewer-uiux": ("sonnet", "medium"),
    "reviewer-security": ("opus", "high"),
    "reviewer-spec": ("sonnet", "medium"),
    "approver": ("sonnet", "high"),
    "approver-risky": ("opus", "high"),
}

CLAUDE_MODELS = ("haiku", "sonnet", "opus", "fable", "inherit")
CLAUDE_EFFORTS = ("low", "medium", "high", "xhigh", "max")
CURSOR_MODELS = ("fast", "inherit")
FILE = "factory/models.json"


class ModelsError(Exception):
    pass


def _check_value(where: str, host: str, key: str, value) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ModelsError(f"{where}.{key}: {value!r} is not a non-empty string")
    if host == "claude":
        if key == "model" and value not in CLAUDE_MODELS and not value.startswith("claude-"):
            raise ModelsError(f"{where}.model: {value!r} is not one of {', '.join(CLAUDE_MODELS)} or a claude- id")
        if key == "effort" and value not in CLAUDE_EFFORTS:
            raise ModelsError(f"{where}.effort: {value!r} is not one of {', '.join(CLAUDE_EFFORTS)}")
    elif host == "cursor" and key == "model" and value not in CURSOR_MODELS:
        raise ModelsError(f"{where}.model: {value!r} is not one of {', '.join(CURSOR_MODELS)}")


def _validate(data) -> None:
    if not isinstance(data, dict):
        raise ModelsError(f"{FILE}: the top level must be an object")
    for host, body in data.items():
        if host not in HOSTS:
            raise ModelsError(f"{FILE}: unknown host {host!r}, expected one of {', '.join(HOSTS)}")
        if not isinstance(body, dict):
            raise ModelsError(f"{FILE}: {host} must be an object")
        for group, entries in body.items():
            names = {"tiers": TIERS, "agents": set(AGENT_DEFAULTS) - {"reviewer-uiux"}}.get(group)
            if names is None:
                raise ModelsError(f"{FILE}: {host}.{group}: unknown key, expected tiers or agents")
            if not isinstance(entries, dict):
                raise ModelsError(f"{FILE}: {host}.{group} must be an object")
            for name, entry in entries.items():
                where = f"{FILE}: {host}.{group}.{name}"
                if name not in names:
                    hint = " (reviewer-uiux is configured as reviewer-ux)" if name == "reviewer-uiux" else ""
                    raise ModelsError(f"{where}: unknown {group[:-1]} name{hint}, expected one of {', '.join(sorted(names))}")
                if not isinstance(entry, dict):
                    raise ModelsError(f"{where} must be an object")
                for key, value in entry.items():
                    if key not in ("model", "effort"):
                        raise ModelsError(f"{where}.{key}: unknown key, expected model or effort")
                    if host == "cursor" and key == "effort":
                        raise ModelsError(f"{where}.effort: cursor has no per-call effort")
                    _check_value(where, host, key, value)


def load(root) -> dict:
    path = Path(root) / FILE
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as e:
        raise ModelsError(f"{FILE}: cannot read it as JSON ({e})") from e
    _validate(data)
    return data


def resolve(root, host: str, tier: str | None = None, agent: str | None = None, risky: bool = False) -> dict:
    """The model and effort to pass for a tier or an agent; None means pass nothing. `source` says where they came from."""
    if host not in HOSTS:
        raise ModelsError(f"unknown host {host!r}, expected one of {', '.join(HOSTS)}")
    if (tier is None) == (agent is None):
        raise ModelsError("give exactly one of tier and agent")
    if tier is not None:
        if tier not in TIERS:
            raise ModelsError(f"unknown tier {tier!r}, expected one of {', '.join(sorted(TIERS))}")
        group, names = "tiers", [tier]
        if tier == "fable" and host != "claude":
            names.append("heavy")
    else:
        if agent not in AGENT_DEFAULTS:
            raise ModelsError(f"unknown agent {agent!r}, expected one of {', '.join(sorted(AGENT_DEFAULTS))}")
        group = "agents"
        name = "reviewer-ux" if agent == "reviewer-uiux" else agent
        names = ["approver-risky" if name == "approver" and risky else name]
    entries = load(root).get(host, {}).get(group, {})
    default_model, default_effort = (TIER_DEFAULTS if group == "tiers" else AGENT_DEFAULTS)[names[-1]]
    out: dict = {}
    from_file = False
    for key, default in (("model", default_model), ("effort", default_effort)):
        value = next((entries[n][key] for n in names if key in entries.get(n, {})), None)
        from_file = from_file or value is not None
        if value is None and (host == "claude" or (host == "codex" and key == "effort")):
            value = default
        out[key] = value
    source = "models.json" if from_file else "tiers.md" if host == "claude" else "session"
    return {**out, "source": source}
