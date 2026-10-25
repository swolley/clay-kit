#!/usr/bin/env python3
"""Which vendor runs an agent when a run may hand agents to the peer vendor's CLI, and how much of the Codex plan is left.

`decide` is pure: state.py gathers the run state and the usage and passes them in. `quota` reads the newest `rate_limits` it can
find, the last peer run's status file or a Codex rollout file.
"""
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

from models import AGENT_DEFAULTS

PEER = {"claude": "codex", "codex": "claude"}
# What `vendor-down --reason limit` without --until records: out for the rest of the run.
END_OF_RUN = "9999-12-31T23:59:59Z"
DEFAULT_THRESHOLD = 80
TAIL_BYTES = 1_000_000  # rollout files grow to many MB; the last rate_limits is near their end
ROLLOUTS_TRIED = 5


def parse_iso(text: str) -> datetime:
    return datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(timezone.utc)


def iso(epoch: float) -> str:
    return datetime.fromtimestamp(epoch, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _find_limits(node):
    """The `rate_limits` object nearest the root of a parsed event, or None."""
    if isinstance(node, dict):
        if isinstance(node.get("rate_limits"), dict):
            return node["rate_limits"]
        children = node.values()
    elif isinstance(node, list):
        children = node
    else:
        return None
    return next((found for found in map(_find_limits, children) if found), None)


def _epoch(value) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return parse_iso(value).timestamp()
        except ValueError:
            return None
    return None


def _reading(limits: dict, now: float) -> tuple[float, str | None] | None:
    """The fullest window of a rate_limits object as (used_percent, resets_at); a window that has reset counts as 0."""
    windows = [limits.get("primary"), limits.get("secondary")] if "used_percent" not in limits else [limits]
    best = None
    for w in windows:
        if not isinstance(w, dict) or isinstance(w.get("used_percent"), bool) or not isinstance(w.get("used_percent"), (int, float)):
            continue
        resets = _epoch(w.get("resets_at"))
        used, until = (0.0, None) if resets is not None and resets <= now else (float(w["used_percent"]), iso(resets) if resets is not None else None)
        if best is None or used > best[0]:
            best = (used, until)
    return best


def _last_reading(path: Path, now: float) -> tuple[float, str | None] | None:
    try:
        with path.open("rb") as f:
            size = f.seek(0, os.SEEK_END)
            f.seek(max(0, size - TAIL_BYTES))
            lines = f.read().decode("utf-8", errors="replace").splitlines()
    except OSError:
        return None
    for line in reversed(lines):
        try:
            event = json.loads(line)
        except ValueError:  # a truncated line, or the partial first line of the tail
            continue
        limits = _find_limits(event)
        if limits and (reading := _reading(limits, now)):
            return reading
    return None


def _newest(paths) -> list[Path]:
    found = []
    for p in paths:
        try:
            found.append((p.stat().st_mtime, p))
        except OSError:
            continue
    return [p for _, p in sorted(found, key=lambda m: m[0], reverse=True)]


def quota(root, vendor: str, codex_home: Path | None = None, now: float | None = None) -> dict:
    """{used_percent, resets_at, source} for a vendor. Only Codex exposes a margin: from the last peer run's status file or, when a
    rollout file is newer, from that. None when there is nothing to read, and always for claude."""
    now = time.time() if now is None else now
    none = {"used_percent": None, "resets_at": None, "source": "none"}
    if vendor != "codex":
        return none
    home = Path(codex_home or os.environ.get("CODEX_HOME") or Path.home() / ".codex")
    status = _newest(Path(root).glob("factory/jobs/*/peer/*.status.json"))
    rollouts = _newest((home / "sessions").glob("**/rollout-*.jsonl"))
    readings = []  # (mtime, source, reading) for the newest file of each kind that holds a rate_limits
    for source, files in (("peer", status), ("sessions", rollouts[:ROLLOUTS_TRIED])):
        for path in files:
            if source == "peer":
                try:
                    reading = _reading(_find_limits(json.loads(path.read_text())) or {}, now)
                except (OSError, ValueError):
                    reading = None
            else:
                reading = _last_reading(path, now)
            if reading:
                readings.append((path.stat().st_mtime, source, reading))
                break
    if not readings:
        return none
    _, source, (used, resets) = max(readings, key=lambda r: r[0])
    return {"used_percent": used, "resets_at": resets, "source": source}


def _unusable(run: dict, vendor: str, now: datetime) -> str | None:
    """Why a vendor cannot take an agent right now: `off` for the run, `exhausted` until a time still ahead, else None."""
    entry = (run.get("vendors") or {}).get(vendor) or {}
    if entry.get("off"):
        return "off"
    until = entry.get("exhausted_until")
    if until:
        try:
            if parse_iso(until) > now:
                return "exhausted"
        except ValueError:
            return "exhausted"  # an unreadable time is not a licence to use the vendor
    return None


def carried_marks(vendors: dict, now: str) -> dict:
    """The vendor-down marks a new run keeps: only a dated exhaustion still ahead. `off` and the end-of-run exhaustion belong to
    the run that recorded them."""
    kept = {}
    for name, entry in vendors.items():
        until = entry.get("exhausted_until")
        if until and until != END_OF_RUN and _unusable({"vendors": {name: {"exhausted_until": until}}}, name, parse_iso(now)):
            kept[name] = {"exhausted_until": until}
    return kept


def decide(job: dict | None, run: dict, agent: str, host: str, usage: dict, now: str) -> dict:
    """The vendor for an agent: {vendor, peer, reason, crossed, cross_on}, `cross_on` being the run state's `cross.on`. `agent` is builder, an agent of models.AGENT_DEFAULTS without
    -risky (then `job` holds the builder's vendor) or reviewer-final (then `job` is None). `usage` maps vendor to used_percent or
    None. vendor is None when neither vendor can take the agent."""
    if agent != "builder" and (agent not in AGENT_DEFAULTS or agent.endswith("-risky")):
        raise ValueError(f"unknown agent {agent!r}")
    cross = run.get("cross") or {}
    if not cross.get("on") or host not in PEER:
        return {"vendor": host, "peer": False, "reason": "session", "crossed": False, "cross_on": bool(cross.get("on"))}
    peer, threshold, at = PEER[host], cross.get("threshold", DEFAULT_THRESHOLD), parse_iso(now)
    down = {v: _unusable(run, v, at) for v in (host, peer)}
    over = {v: usage.get(v) is not None and usage[v] >= threshold for v in (host, peer)}

    def out(vendor, reason, crossed=False):
        return {"vendor": vendor, "peer": vendor not in (None, host), "reason": reason, "crossed": crossed, "cross_on": True}

    if agent == "builder":
        if (job or {}).get("lean"):  # lean jobs are built by the session, whatever the tier or the margin
            return out(host, "session")
        wanted = peer if (job or {}).get("tier") in cross.get("builder_tiers", []) else host
        other = PEER[wanted]
        if down[wanted]:
            if down[other]:
                return out(None, "exhausted")
            return out(other, "session" if down[wanted] == "off" else "exhausted")
        if over[wanted] and not down[other] and not over[other]:
            return out(other, "threshold")
        return out(wanted, "builder_tiers" if wanted == peer else "session")
    # Reviewers and approver: the vendor opposite to the one that built (the host for a lean job and for the final review).
    built = ((job or {}).get("vendors") or {}).get("builder", {}).get("vendor", host)
    if built not in PEER:
        built = host
    opposite = PEER[built]
    if down[opposite] is None and not over[opposite]:
        return out(opposite, "opposite", True)
    if down[built] is None:
        return out(built, "not crossed")
    if down[opposite] is None:  # the builder's vendor is out, so staying on it is not an option
        return out(opposite, "opposite", True)
    return out(None, "exhausted")
