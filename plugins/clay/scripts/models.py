#!/usr/bin/env python3
"""Model and effort per host for a tier or an agent, from the defaults of tiers.md and the optional <root>/factory/models.json.

models.json: {"<host>": {"tiers": {"<tier>": {"model": M, "effort": E}}, "agents": {"<agent>": {"model": M, "effort": E}}}}
Hosts are claude and codex; both keys of an entry are optional and the entry wins over the defaults, per key.
The top-level key `cross` is not a host: {"cross": {"builder_tiers": [tier, ...], "threshold": 1..100}} configures running agents through the peer vendor's CLI (defaults [] and 80): the tiers whose builders go to the peer, and the used_percent at which a vendor counts as over its limit.
Vocabulary: claude takes its model names and efforts; codex accepts any non-empty model and effort value.
"""
import json
from pathlib import Path

from factory_plan import TIERS

HOSTS = ("claude", "codex")

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
    "reviewer-interface": ("sonnet", "medium"),
    "reviewer-security": ("opus", "high"),
    "reviewer-spec": ("sonnet", "medium"),
    "approver": ("sonnet", "high"),
    "approver-risky": ("opus", "high"),
    "reviewer-final": ("sonnet", "high"),
    "reviewer-final-risky": ("opus", "high"),
}
# Agent names of earlier versions, now judged by reviewer-interface; a models.json that still names one is refused.
RENAMED = ("reviewer-ux", "reviewer-ui", "reviewer-uiux")
# The agents whose model depends on whether the job, or the run, is risky; `<agent>-risky` holds the risky choice.
RISKY_AGENTS = ("approver", "reviewer-final")

CLAUDE_MODELS = ("haiku", "sonnet", "opus", "fable", "inherit")
CLAUDE_EFFORTS = ("low", "medium", "high", "xhigh", "max")
FILE = "factory/models.json"
CROSS_DEFAULTS = {"builder_tiers": [], "threshold": 80}


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


def _validate_cross(body) -> None:
    if not isinstance(body, dict):
        raise ModelsError(f"{FILE}: cross must be an object")
    for key, value in body.items():
        where = f"{FILE}: cross.{key}"
        if key not in CROSS_DEFAULTS:
            raise ModelsError(f"{where}: unknown key, expected one of {', '.join(CROSS_DEFAULTS)}")
        if key == "builder_tiers":
            if not isinstance(value, list) or any(not isinstance(t, str) or t not in TIERS for t in value):
                raise ModelsError(f"{where}: {value!r} is not a list of tiers ({', '.join(sorted(TIERS))})")
        elif not isinstance(value, int) or isinstance(value, bool) or not 1 <= value <= 100:
            raise ModelsError(f"{where}: {value!r} is not an integer from 1 to 100")


def _validate(data) -> None:
    if not isinstance(data, dict):
        raise ModelsError(f"{FILE}: the top level must be an object")
    for host, body in data.items():
        if host == "cross":
            _validate_cross(body)
            continue
        if host not in HOSTS:
            raise ModelsError(f"{FILE}: unknown host {host!r}, expected one of {', '.join(HOSTS)}")
        if not isinstance(body, dict):
            raise ModelsError(f"{FILE}: {host} must be an object")
        for group, entries in body.items():
            names = {"tiers": TIERS, "agents": set(AGENT_DEFAULTS)}.get(group)
            if names is None:
                raise ModelsError(f"{FILE}: {host}.{group}: unknown key, expected tiers or agents")
            if not isinstance(entries, dict):
                raise ModelsError(f"{FILE}: {host}.{group} must be an object")
            for name, entry in entries.items():
                where = f"{FILE}: {host}.{group}.{name}"
                if name not in names:
                    hint = f" ({name} is now reviewer-interface)" if name in RENAMED else ""
                    raise ModelsError(f"{where}: unknown {group[:-1]} name{hint}, expected one of {', '.join(sorted(names))}")
                if not isinstance(entry, dict):
                    raise ModelsError(f"{where} must be an object")
                for key, value in entry.items():
                    if key not in ("model", "effort"):
                        raise ModelsError(f"{where}.{key}: unknown key, expected model or effort")
                    _check_value(where, host, key, value)


def load(root) -> dict:
    path = Path(root) / FILE
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text())
    except (OSError, ValueError) as e:  # ValueError covers bad JSON and bytes that are not UTF-8
        raise ModelsError(f"{FILE}: cannot read or parse it as JSON ({e})") from e
    _validate(data)
    return data


def cross_config(root) -> dict:
    """The cross block with its defaults: the tiers whose builders go to the peer vendor, and the used_percent at which a vendor is over its limit."""
    block = {**CROSS_DEFAULTS, **load(root).get("cross", {})}
    return {**block, "builder_tiers": list(block["builder_tiers"])}


def resolve(root, host: str, tier: str | None = None, agent: str | None = None, risky: bool = False) -> dict:
    """The model and effort to pass for a tier or an agent; None means pass nothing. `source` says where they came from."""
    if host not in HOSTS:
        raise ModelsError(f"unknown host {host!r}, expected one of {', '.join(HOSTS)}")
    if (tier is None) == (agent is None):
        raise ModelsError("give exactly one of tier and agent")
    if risky and (tier is not None or agent not in RISKY_AGENTS):
        raise ModelsError("--risky applies only to --agent approver and --agent reviewer-final")
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
        names = [f"{agent}-risky" if risky else agent]
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
