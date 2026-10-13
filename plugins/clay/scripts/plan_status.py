#!/usr/bin/env python3
"""Development backlog of a repository, or of a whole workspace: plans, specs and code markers.

Repositories are discovered, not declared: every directory under the root that holds plans or specs is one, the root
included. A plan's state comes from its front matter `status:` when present, otherwise from its checkboxes; a
disagreement between the two is reported as an inconsistency. The tool never edits a plan.

Ported from laraplate's `scripts/plan-status.php`; plans are read through `factory_plan.parse_plan`, so the backlog and
the factory runner give a plan the same meaning. Standard library only.
"""
import glob
import os
from datetime import datetime
from pathlib import Path

from factory_plan import parse_plan, plan_date

PLAN_DIRS = ("docs/superpowers/plans", ".cursor/plans", "Modules/*/docs/plans")
SPEC_DIRS = ("docs/superpowers/specs", ".cursor/specs")
SKIPPED = {"INDEX.md", "README.md"}


def discover(root: Path | str) -> dict[str, str]:
    """Repository name to path relative to `root` ('' for the root itself): any directory holding plans or specs,
    the root first since it reads as the heading of the repositories nested in it. Only direct children are looked at."""
    root = Path(root).resolve()
    root_holds_work = False
    children: set[str] = set()
    for d in PLAN_DIRS + SPEC_DIRS:
        if any(Path(root, hit).is_dir() for hit in glob.glob(d, root_dir=root)):
            root_holds_work = True
        for hit in glob.glob(f"*/{d}", root_dir=root):
            if Path(root, hit).is_dir():
                children.add(hit.split("/")[0])
    repos = {root.name: ""} if root_holds_work else {}
    for name in sorted(children):
        repos[name] = name
    return repos


def _paths(files: list[str]) -> list[str]:
    """The declared files that look like paths, as the PHP tool reads them: first word, with a slash, no `::` or call."""
    out = []
    for f in files:
        candidate = f.strip().split(" ")[0].strip().rstrip(",;")
        if "/" in candidate and "::" not in candidate and "(" not in candidate:
            out.append(candidate)
    return out


def _evidence(paths: list[str], root: Path, relative: str) -> tuple[int, list[str]]:
    """How many of `paths` exist, looked up from the root and from the repository; the missing ones."""
    found, missing = 0, []
    for p in paths:
        candidates = [root / p, root / relative / p]
        if any(c.exists() or ("*" in str(c) and glob.glob(str(c))) for c in candidates):
            found += 1
        else:
            missing.append(p)
    return found, missing


def _checkbox_state(checked: int, total: int) -> str:
    if total == 0:
        return "empty"
    return "done" if checked == total else ("open" if checked == 0 else "partial")


def effective_state(declared: str | None, checkbox_state: str) -> str:
    """The front matter status wins over the checkboxes; an unknown or missing status leaves them in charge."""
    match (declared or "").lower():
        case "completed" | "done" | "shipped":
            return "done"
        case "superseded" | "abandoned" | "cancelled":
            return "superseded"
        case "in-progress" | "in_progress" | "partial":
            return "partial"
        case "open" | "draft" | "planned":
            return "partial" if checkbox_state == "done" else "open"
    return checkbox_state


def inconsistency(declared: str | None, banner: str | None, checkbox_state: str, checked: int, total: int) -> str | None:
    """A disagreement between the declared status and the checkboxes. A plan with no checkboxes cannot disagree:
    retrospective records are written that way on purpose."""
    if total == 0:
        return None
    effective = effective_state(declared, checkbox_state)
    if declared is None and banner is not None and banner.lower().startswith("complet") and checkbox_state != "done":
        return f"banner says completed but {checked}/{total} steps are flagged"
    if declared is not None and effective == "done" and checkbox_state != "done":
        return f"front-matter says {declared} but {checked}/{total} steps are flagged"
    if declared is not None and effective != "done" and checkbox_state == "done":
        return f"front-matter says {declared} but every step is flagged"
    return None


def _date_of(file: Path) -> tuple[str, str]:
    """The plan's own date from its file name; otherwise the file's modification date, and says so."""
    if date := plan_date(file.name):
        return date, "filename"
    try:
        return datetime.fromtimestamp(file.stat().st_mtime).strftime("%Y-%m-%d"), "mtime"
    except OSError:
        return "0000-00-00", "mtime"


def _scan_plan(file: Path, root: Path, repo: str, relative: str, plan_dir: str, evidence: bool) -> dict:
    plan = parse_plan(file.read_text(errors="replace"))
    tasks = []
    total = checked = 0
    for t in plan.tasks:
        if not t.steps:
            continue
        open_, done, cancelled = t.counts()
        files = list(dict.fromkeys(_paths(t.files)))
        created = len(_paths(t.files_create))
        found, missing = _evidence(files, root, relative) if evidence else (0, [])
        state = t.state
        tasks.append({
            "number": t.number,
            "name": t.title,
            "checked": done + cancelled,
            "cancelled": cancelled,
            "total": len(t.steps),
            "state": state,
            "files": files,
            "files_found": found,
            "files_total": len(files),
            "files_missing": missing,
            "stale": state != "done" and len(files) > 0 and created > 0 and found == len(files),
        })
        total += len(t.steps)
        checked += done + cancelled
    declared = plan.status or None
    banner = plan.banner or None
    checkbox_state = _checkbox_state(checked, total)
    date, date_source = _date_of(file)
    return {
        "kind": "plan",
        "repo": repo,
        "source": plan_dir,
        "file": file.name,
        "date": date,
        "date_source": date_source,
        "path": file.relative_to(root).as_posix(),
        "title": plan.title or file.name.removesuffix(".md"),
        "front_matter_status": declared,
        "status_banner": banner,
        "tasks": tasks,
        "total_steps": total,
        "checked_steps": checked,
        "checkbox_state": checkbox_state,
        "state": effective_state(declared, checkbox_state),
        "inconsistency": inconsistency(declared, banner, checkbox_state, checked, total),
    }


def scan_plans(root: Path | str, repos: dict[str, str], evidence: bool = True) -> list[dict]:
    """Every plan of every repository in `repos`, broken down per task with step counts, state and file evidence."""
    root = Path(root).resolve()
    plans = []
    for repo, relative in repos.items():
        base = root / relative
        for plan_dir in PLAN_DIRS:
            for d in sorted(glob.glob(os.path.join(glob.escape(str(base)), plan_dir))):
                if not os.path.isdir(d):
                    continue
                for file in (Path(d, name) for name in sorted(glob.glob("*.md", root_dir=d))):
                    if file.name in SKIPPED or not file.is_file():
                        continue
                    plans.append(_scan_plan(file, root, repo, relative, plan_dir, evidence))
    return plans
