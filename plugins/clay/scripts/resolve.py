#!/usr/bin/env python3
"""Resolve what a command argument means: a job from a short token, or a plan from the plans `plan_status.py` finds.

  resolve.py job [TOKEN] --stages needs-human,waiting-input --root DIR
  resolve.py plans [--unclassified|--audit] --root DIR

Prints JSON. `job` gives {match, candidates, reason}; `plans` lists the plans that still have open steps. Plans are
found where `plan_status.py` finds them, subfolders and nested repositories included; each one carries `root`, the
checkout it belongs to relative to DIR ('' for DIR itself), and `path`, the plan relative to that checkout.
"""
import json
import re
import sys
from pathlib import Path

from factory_plan import done_signals, git_subjects, parse_plan
from plan_status import discover, documents, folders


def load_jobs(root: Path) -> list[dict]:
    jobs = []
    for f in sorted((root / "factory/jobs").glob("*/job.json")):
        try:
            jobs.append(json.loads(f.read_text()))
        except (OSError, json.JSONDecodeError):
            continue
    return jobs


def resolve_job(token: str | None, jobs: list[dict], stages: tuple[str, ...]) -> tuple[dict | None, list[dict], str]:
    """A job from a token: nothing (the only eligible job), a full id, `002`, a task number, or a fragment of the id."""
    eligible = [j for j in jobs if j.get("stage") in stages]
    token = (token or "").strip().lower()
    if not token:
        if len(eligible) == 1:
            return eligible[0], [], "the only job waiting"
        return None, eligible, "no argument and " + ("no job is waiting" if not eligible else "several jobs are waiting")

    if token.isdigit():
        number = int(token)
        by_id = [j for j in eligible if j["id"].startswith(f"{number:03d}-")]
        by_task = [j for j in eligible if j.get("task") == number]
        hits = by_id or by_task
    else:
        hits = [j for j in eligible if j["id"].lower() == token] or [j for j in eligible if token in j["id"].lower()]
    if len(hits) == 1:
        return hits[0], [], "matched " + token
    if hits:
        return None, hits, f"'{token}' matches several jobs"
    anywhere = [j for j in jobs if token in j["id"].lower() or (token.isdigit() and j.get("task") == int(token))]
    reason = f"'{token}' is not a job that is " + "/".join(stages) if anywhere else f"no job matches '{token}'"
    return None, [], reason


def checkout(folder: Path, top: Path) -> Path:
    """The checkout a repository folder belongs to: the nearest folder holding `.git`, from it up to `top`, else the
    folder itself. Its jobs, its git history and its files are that checkout's."""
    for candidate in (folder, *folder.parents):
        if (candidate / ".git").exists():
            return candidate
        if candidate == top:
            break
    return folder


def _scan(root: Path):
    root = Path(root).resolve()
    jobs: dict[Path, list[dict]] = {}
    for _, relative, _, folder in folders(root, discover(root)):
        home = checkout(root / relative, root)
        if home not in jobs:
            jobs[home] = load_jobs(home)
        for f in documents(folder):
            parsed = parse_plan(f.read_text())
            landed = {j.get("task") for j in jobs[home] if j.get("plan") == f.stem and j.get("stage") in ("merged", "committed")}
            where = {"root": "" if home == root else home.relative_to(root).as_posix(), "path": f.relative_to(home).as_posix()}
            yield where, home, parsed, landed


def list_plans(root: Path) -> list[dict]:
    """Plans that still have work. A declared status (completed, shipped, superseded) closes a plan whatever its
    checkboxes say. A task counts as done when its steps are ticked or a job of this plan landed it, since a
    landing can leave the tick uncommitted after a crash; a task with no steps is not work we can run."""
    plans = []
    for where, _, parsed, landed in _scan(root):
        if parsed.state != "open":
            continue
        open_tasks = [t for t in parsed.tasks if t.steps and not t.done and t.number not in landed]
        if open_tasks:
            plans.append({**where, "title": parsed.title, "tasks": len(parsed.tasks), "open": len(open_tasks)})
    return plans


def list_unclassified(root: Path) -> list[dict]:
    """Plans with no steps and no declared status: neither open nor closed, so a person decides."""
    return [{**where, "title": p.title} for where, _, p, _ in _scan(root) if p.state == "unclassified"]


def audit_plans(root: Path) -> list[dict]:
    """Second check, from the repo: a plan declared closed whose planned commits and files are not there, or a plan
    still open whose every task already shows its signals. Only tasks that name a commit or a created file can be judged."""
    subjects: dict[Path, set[str]] = {}
    findings = []
    for where, home, parsed, _ in _scan(root):
        judged = [t for t in parsed.tasks if t.commits or t.files_create]
        if not judged:
            continue
        if home not in subjects:
            subjects[home] = git_subjects(home)
        shown = [bool(done_signals(t, home, subjects[home])) for t in judged]
        if parsed.state == "done" and parsed.status and not any(shown):
            findings.append({**where, "finding": f"declared {parsed.status} but no planned commit or created file is in the repo"})
        elif parsed.state == "open" and all(shown):
            findings.append({**where, "finding": "has open steps but every task already shows its commit or files"})
    return findings


def main(argv: list[str]) -> int:
    if not argv or argv[0] not in ("job", "plans"):
        print(__doc__, file=sys.stderr)
        return 2
    root = Path(argv[argv.index("--root") + 1]) if "--root" in argv else Path(".")
    if argv[0] == "plans":
        pick = list_unclassified if "--unclassified" in argv else audit_plans if "--audit" in argv else list_plans
        print(json.dumps(pick(root), indent=2))
        return 0
    stages = tuple(argv[argv.index("--stages") + 1].split(",")) if "--stages" in argv else ("needs-human",)
    skip = {argv.index(o) + 1 for o in ("--stages", "--root") if o in argv} | {i for i, a in enumerate(argv) if a in ("--stages", "--root")}
    token = next((a for i, a in enumerate(argv[1:], start=1) if i not in skip), None)
    match, candidates, reason = resolve_job(token, load_jobs(root), stages)
    print(json.dumps({"match": match, "candidates": candidates, "reason": reason}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
