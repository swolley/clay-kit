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
import re
from datetime import datetime
from pathlib import Path

from factory_plan import parse_plan, plan_date

PLAN_DIRS = ("docs/superpowers/plans", ".cursor/plans", "Modules/*/docs/plans")
SPEC_DIRS = ("docs/superpowers/specs", ".cursor/specs")
SKIPPED = {"INDEX.md", "README.md"}
TODO_EXTENSIONS = {"php", "ts", "tsx", "js", "mjs", "vue", "sh", "py"}
TODO_EXCLUDED = {"vendor", "node_modules", ".git", "storage", "dist", "build", "coverage", ".pnpm-store",
                 "public/build", "bootstrap/cache", ".nuxt", ".output"}
# The scanner and its test mention the markers as data; they are not work left.
TODO_SELF = ("scripts/plan-status.php", "scripts/tests/plan-status-test.sh")
# A marker counts only in its conventional spelling (upper case, or a `@todo` tag) and only as the first word of a
# comment (`//`, `#`, `/*`, a docblock `*`, `<!--`, `{{--`).
TODO_PATTERN = re.compile(r"(?://|#|/\*+|^\s*\*|<!--|\{\{--)\s*(TODO|FIXME|XXX|@todo)\b:?\s*")
REFERENCE_PATTERN = re.compile(r"^\s*(?:[-*]\s+)?(?:\*\*)?Plan:?(?:\*\*)?:?\s*not required\b", re.IGNORECASE)


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


def _head(file: Path, lines: int) -> list[str]:
    try:
        with file.open(errors="replace") as handle:
            return [line for _, line in zip(range(lines), handle)]
    except OSError:
        return []


def _spec_title(file: Path) -> str:
    for line in _head(file, 20):
        if m := re.match(r"#\s+(.+)$", line.strip()):
            return m.group(1).strip()
    return file.name.removesuffix(".md")


def _sibling_plan(spec_file: str, plan_names: dict[str, str]) -> str | None:
    """A plan for the same subject, found by stripping the spec's trailing marker: `x-design.md` -> `x.md`."""
    stem = re.sub(r"-(design|review|gate|spec)\.md$", ".md", spec_file)
    return None if stem == spec_file else plan_names.get(stem)


def scan_specs(root: Path | str, repos: dict[str, str], plans: list[dict]) -> list[dict]:
    """Every spec with one of four states: `reference` (declares `Plan: not required` in its first lines), `planned`
    (a plan's text names the file), `plan_uncited` (a plan with the same subject exists but never names it) or
    `unplanned`. `plans` is the result of `scan_plans`."""
    root = Path(root).resolve()
    blob = ""
    plan_names = {}
    for plan in plans:
        try:
            blob += (root / plan["path"]).read_text(errors="replace")
        except OSError:
            pass
        plan_names[plan["file"]] = plan["path"]
    specs = []
    for repo, relative in repos.items():
        for spec_dir in SPEC_DIRS:
            d = os.path.join(glob.escape(str(root / relative)), spec_dir)
            for file in (Path(d, name) for name in sorted(glob.glob("*.md", root_dir=d))) if os.path.isdir(d) else []:
                if file.name in SKIPPED or not file.is_file():
                    continue
                cited = file.name in blob
                sibling = None if cited else _sibling_plan(file.name, plan_names)
                if any(REFERENCE_PATTERN.match(line) for line in _head(file, 30)):
                    state = "reference"
                elif cited:
                    state = "planned"
                else:
                    state = "plan_uncited" if sibling else "unplanned"
                specs.append({
                    "kind": "spec",
                    "repo": repo,
                    "file": file.name,
                    "path": file.relative_to(root).as_posix(),
                    "title": _spec_title(file),
                    "has_plan": state not in ("unplanned", "reference"),
                    "sibling_plan": sibling,
                    "state": state,
                })
    return sorted(specs, key=lambda s: (s["repo"], s["file"]))


def _in_string(prefix: str) -> bool:
    """Whether the end of `prefix` falls inside a quoted string: an odd number of unescaped quotes of one kind."""
    return any(len(re.findall(rf"(?<!\\){q}", prefix)) % 2 for q in ("'", '"', "`"))


def _marker(line: str) -> tuple[str, str] | None:
    """The marker and its text when `line` carries one in a comment, not inside a string."""
    for m in TODO_PATTERN.finditer(line):
        if not _in_string(line[:m.start()]):
            return m.group(1).upper(), line[m.end():].strip()[:120].strip()
    return None


def _source_files(base: Path, nested: list[Path]):
    """Source files under `base`, pruning excluded, hidden and nested-repository directories before descending.
    Entries with a slash are matched against the path from `base`, the others against the directory name."""
    for current, dirs, names in os.walk(base):
        here = Path(current)
        dirs[:] = sorted(
            d for d in dirs
            if here / d not in nested and not d.startswith(".")
            and d not in TODO_EXCLUDED and (here / d).relative_to(base).as_posix() not in TODO_EXCLUDED)
        for name in sorted(names):
            if name.rpartition(".")[2].lower() in TODO_EXTENSIONS and "." in name:
                yield here / name


def scan_todos(root: Path | str, repos: dict[str, str], limit: int) -> list[dict]:
    """Markers (`TODO`, `FIXME`, `XXX`, `@todo`) in the comments of source files, at most `limit`. The root repository
    does not walk into the repositories nested under it, so a marker is reported once."""
    root = Path(root).resolve()
    todos: list[dict] = []
    for repo, relative in repos.items():
        base = root / relative
        if not base.is_dir():
            continue
        nested = [root / other for name, other in repos.items() if name != repo and other]
        for file in _source_files(base, nested):
            path = file.relative_to(root).as_posix()
            if any(path.endswith("/" + s) or path == s for s in TODO_SELF):
                continue
            try:
                lines = file.read_text(errors="replace").splitlines()
            except OSError:
                continue
            for number, line in enumerate(lines, 1):
                if found := _marker(line):
                    todos.append({"kind": "todo", "repo": repo, "marker": found[0], "path": path, "line": number,
                                  "text": found[1], "state": "open"})
                    if len(todos) >= limit:
                        return todos
    return todos
