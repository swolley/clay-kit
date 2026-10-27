#!/usr/bin/env python3
"""Capture reproducible clay run snapshots without changing the workflow.

Examples:
  python3 scripts/benchmark.py start --root . --name simple-01 --host claude --mode full
  python3 scripts/benchmark.py finish --root . --name simple-01 --session-cost-before 0 --session-cost-after 0.42
  python3 scripts/benchmark.py report --root . --name simple-01

Run finish BEFORE clay's final cleanup when possible. Costs are optional,
manually supplied session-level USD values; never infer token counts from USD.
"""
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def safe_name(value):
    if not value or any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_" for c in value):
        raise ValueError("name must contain only letters, digits, hyphen and underscore")
    return value


def destination(root, name):
    return Path(root).resolve() / "factory" / "benchmarks" / (safe_name(name) + ".json")


def job_snapshot(root):
    base = Path(root).resolve() / "factory" / "jobs"
    result = []
    if not base.exists():
        return result
    for path in sorted(base.glob("*/job.json")):
        try:
            obj = json.loads(path.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            continue
        result.append({
            "id": obj.get("id"), "plan": obj.get("plan"),
            "tier": obj.get("tier"), "stage": obj.get("stage"),
            "agents": obj.get("agents", []),
            "phases": obj.get("phases", []),
            "build_round": obj.get("build_round"),
        })
    return result


def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def run(args):
    path = destination(args.root, args.name)
    if args.action == "start":
        if path.exists():
            raise ValueError(f"benchmark already exists: {path}")
        data = {"schema": 1, "name": args.name, "host": args.host,
                "mode": args.mode, "started_at": utc_now(),
                "baseline_jobs": job_snapshot(args.root), "status": "running"}
        write(path, data)
    else:
        if not path.exists():
            raise ValueError(f"benchmark not found: {path}")
        data = json.loads(path.read_text(encoding="utf-8"))
        if args.action == "finish":
            if data["status"] != "running":
                raise ValueError("benchmark already finished")
            before, after = args.session_cost_before, args.session_cost_after
            if (before is None) != (after is None):
                raise ValueError("provide both session cost values or neither")
            if before is not None and (before < 0 or after < before):
                raise ValueError("session costs must be nonnegative and increasing")
            data["finished_at"] = utc_now()
            data["status"] = "finished"
            data["jobs_at_finish"] = job_snapshot(args.root)
            data["session_cost_usd"] = {
                "before": before, "after": after,
                "delta": round(after - before, 6) if before is not None else None,
                "scope": "entire host session; may include non-clay activity",
            }
            write(path, data)
    print(json.dumps({"file": str(path), "status": data["status"],
                      "jobs_captured": len(data.get("jobs_at_finish", [])),
                      "session_cost_usd": data.get("session_cost_usd")}, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    for action in ("start", "finish", "report"):
        p = sub.add_parser(action)
        p.add_argument("--root", type=Path, default=Path("."))
        p.add_argument("--name", required=True)
        if action == "start":
            p.add_argument("--host", choices=("claude", "codex", "cursor"), required=True)
            p.add_argument("--mode", choices=("full", "lean"), required=True)
        if action == "finish":
            p.add_argument("--session-cost-before", type=float)
            p.add_argument("--session-cost-after", type=float)
    args = parser.parse_args()
    try:
        run(args)
    except (ValueError, OSError) as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
