#!/usr/bin/env python3
"""Development backlog of a repository, or of a whole workspace: plans, specs and code markers.

Repositories are discovered, not declared: every directory under the root that holds plans or specs is one, the root
included. A plan's state comes from its front matter `status:` when present, otherwise from its checkboxes; a
disagreement between the two is reported as an inconsistency. The tool never edits a plan.

Ported from laraplate's `scripts/plan-status.php`; plans are read through `factory_plan.parse_plan`, so the backlog and
the factory runner give a plan the same meaning. Standard library only.
"""
import argparse
import glob
import html
import json
import os
import re
import shutil
import subprocess
import sys
import textwrap
from dataclasses import dataclass
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
# The line and the lines that continue it, up to the first blank line.
DOCUMENTED_PATTERN = re.compile(r"^\s*(?:[-*]\s+)?\*\*Documented in:\*\*[ \t]*((?:.+\n?)*)", re.IGNORECASE | re.MULTILINE)
DOC_PATH = re.compile(r"`([^`\s]+)`|([\w./-]+/[\w./-]+\.(?:md|mdx|rst|adoc|txt))\b")
DOC_LIKE = re.compile(r"^[\w./-]+$")
DELIVERY_PATTERN = re.compile(r"^## Delivery status", re.MULTILINE)


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


def folders(root: Path, repos: dict[str, str], dirs: tuple[str, ...] = PLAN_DIRS):
    """Each existing folder of plans (or of specs, given `SPEC_DIRS`) of every repository in `repos`, with the
    repository's name, its path relative to `root` and the pattern the folder matched."""
    for repo, relative in repos.items():
        for pattern in dirs:
            for d in sorted(glob.glob(os.path.join(glob.escape(str(Path(root) / relative)), pattern))):
                if os.path.isdir(d):
                    yield repo, relative, pattern, Path(d)


def documents(folder: Path) -> list[Path]:
    """The Markdown files of a plans or specs folder and of its subfolders, without index and readme files."""
    found = (folder / name for name in sorted(glob.glob("**/*.md", root_dir=folder, recursive=True)))
    return [f for f in found if f.name not in SKIPPED and f.is_file()]


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
    # A superseded plan resolves its steps too, cancelled or done: that is its normal end.
    if declared is not None and effective not in ("done", "superseded") and checkbox_state == "done":
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


class LastChange:
    """When each file of a folder was last changed: the date of the last commit that touched it, or the file's
    modification date when the working copy differs from that commit or git does not know the file. Never the
    modification date alone, since a fresh clone gives every file the same one. In a shallow clone the files
    unchanged since its oldest commit get that commit's date. Each folder costs three git calls, made once."""

    def __init__(self) -> None:
        self._folders: dict[Path, tuple[dict[str, str], set[str]] | None] = {}

    @staticmethod
    def _git(folder: Path, *args: str) -> str | None:
        try:
            done = subprocess.run(["git", "-C", str(folder), *args], capture_output=True, text=True)
        except OSError:
            return None
        return done.stdout if done.returncode == 0 else None

    def _folder(self, folder: Path) -> tuple[dict[str, str], set[str]] | None:
        if folder not in self._folders:
            log = self._git(folder, "log", "--format=%x00%cs", "--name-only", "--relative", "--", ".")
            if log is None:
                self._folders[folder] = None
            else:
                dates: dict[str, str] = {}
                day = ""
                for line in log.splitlines():
                    if line.startswith("\x00"):
                        day = line[1:]
                    elif line and "/" not in line:
                        dates.setdefault(line, day)  # newest first: the first commit seen is the last change
                changed = (self._git(folder, "diff", "HEAD", "--name-only", "--relative", "--", ".") or "").splitlines()
                changed += (self._git(folder, "ls-files", "--others", "--exclude-standard", "--", ".") or "").splitlines()
                self._folders[folder] = (dates, {c for c in changed if "/" not in c})
        return self._folders[folder]

    def of(self, file: Path) -> tuple[str, str]:
        """The date and where it comes from: `git` (last commit), `worktree` (uncommitted change, modification
        date) or `mtime` (a file git does not track, modification date)."""
        known = self._folder(file.parent)
        if known is not None and file.name not in known[1] and file.name in known[0]:
            return known[0][file.name], "git"
        try:
            day = datetime.fromtimestamp(file.stat().st_mtime).strftime("%Y-%m-%d")
        except OSError:
            day = "0000-00-00"
        return day, "worktree" if known is not None and file.name in known[1] else "mtime"


def _without_fences(text: str) -> str:
    """The text without its fenced blocks, where a plan may quote a closing section as an example."""
    return re.sub(r"^```.*?^```", "", text, flags=re.M | re.S)


def documentation(text: str, root: Path, relative: str) -> tuple[list[str], str | None]:
    """The documents a closed plan names on its `**Documented in:**` line, and what is wrong with that: no such line,
    or a named document that does not exist. `none` on the line is an explicit answer and is accepted."""
    match = DOCUMENTED_PATTERN.search(_without_fences(text))
    if match is None:
        return [], "closed but names no documentation (no Documented in line)"
    value = match.group(1).strip()
    # A backticked word is a document only when it reads as a path: a variable or a command named next to it is not.
    found = (a or b for a, b in DOC_PATH.findall(value))
    paths = list(dict.fromkeys(f for f in found if DOC_LIKE.match(f) and ("/" in f or re.search(r"\.(md|mdx|rst|adoc|txt)$", f))))
    if not paths:
        return [], None if re.match(r"none\b", value, re.I) else "Documented in names no document"
    missing = [d for d in paths if not ((root / relative / d).exists() or (root / d).exists())]
    return paths, f"documentation not found: {', '.join(missing)}" if missing else None


def _scan_plan(file: Path, root: Path, repo: str, relative: str, plan_dir: str, evidence: bool,
               last_change: LastChange | None = None, folder: Path | None = None) -> dict:
    text = file.read_text(errors="replace")
    plan = parse_plan(text)
    tasks = []
    total = checked = 0
    # Every checklist counts, including the steps above the first task and those under a section that is not a task.
    for t in plan.blocks:
        if not t.steps:
            continue
        open_, done, cancelled = t.counts()
        # A file the task deletes is gone once it ran, so its absence is no sign that the task is still to do.
        files = [f for f in dict.fromkeys(_paths(t.files)) if f not in t.files_delete]
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
    updated, updated_source = (last_change or LastChange()).of(file)
    state = effective_state(declared, checkbox_state)
    documented_in, docs_issue = documentation(text, root, relative) if state == "done" else ([], None)
    disagreement = inconsistency(declared, banner, checkbox_state, checked, total)
    if disagreement is None and state not in ("done", "superseded") and DELIVERY_PATTERN.search(_without_fences(text)):
        disagreement = f"delivery status written but the plan reads {state} ({checked}/{total} steps flagged)"
    return {
        "kind": "plan",
        "repo": repo,
        "source": plan_dir,
        "file": file.relative_to(folder or file.parent).as_posix(),
        "date": date,
        "date_source": date_source,
        "updated": updated,
        "updated_source": updated_source,
        "path": file.relative_to(root).as_posix(),
        "title": plan.title or file.name.removesuffix(".md"),
        "front_matter_status": declared,
        "status_banner": banner,
        "tasks": tasks,
        "total_steps": total,
        "checked_steps": checked,
        "checkbox_state": checkbox_state,
        "state": state,
        "inconsistency": disagreement,
        "documented_in": documented_in,
        "docs_issue": docs_issue,
    }


def scan_plans(root: Path | str, repos: dict[str, str], evidence: bool = True) -> list[dict]:
    """Every plan of every repository in `repos`, broken down per task with step counts, state and file evidence."""
    root = Path(root).resolve()
    plans = []
    last_change = LastChange()
    for repo, relative, plan_dir, folder in folders(root, repos):
        for file in documents(folder):
            plans.append(_scan_plan(file, root, repo, relative, plan_dir, evidence, last_change, folder))
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
        plan_names[Path(plan["file"]).name] = plan["path"]
    specs = []
    last_change = LastChange()
    for repo, _, _, folder in folders(root, repos, SPEC_DIRS):
        for file in documents(folder):
            cited = file.name in blob
            sibling = None if cited else _sibling_plan(file.name, plan_names)
            if any(REFERENCE_PATTERN.match(line) for line in _head(file, 30)):
                state = "reference"
            elif cited:
                state = "planned"
            else:
                state = "plan_uncited" if sibling else "unplanned"
            updated, updated_source = last_change.of(file)
            specs.append({
                "kind": "spec",
                "repo": repo,
                "file": file.relative_to(folder).as_posix(),
                "path": file.relative_to(root).as_posix(),
                "title": _spec_title(file),
                "updated": updated,
                "updated_source": updated_source,
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


def scan_todos(root: Path | str, repos: dict[str, str], limit: int, only: str | None = None) -> list[dict]:
    """Markers (`TODO`, `FIXME`, `XXX`, `@todo`) in the comments of source files, at most `limit`. The root repository
    does not walk into the repositories nested under it, so a marker is reported once. `only` reports one repository
    but still knows about the others, so the root does not walk into them."""
    root = Path(root).resolve()
    todos: list[dict] = []
    for repo, relative in repos.items():
        base = root / relative
        if (only is not None and repo != only) or not base.is_dir():
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


# ---- report, renderers and command line

LABEL = {"done": "DONE", "partial": "PARTIAL", "open": "OPEN", "superseded": "SUPERSED", "cancelled": "CANCELLED",
         "empty": "NO BOXES", "planned": "PLANNED", "unplanned": "NO PLAN", "plan_uncited": "UNCITED",
         "reference": "REFERENCE"}
COLOR = {"done": "\033[32m", "partial": "\033[33m", "open": "\033[31m", "superseded": "\033[90m",
         "cancelled": "\033[90m", "empty": "\033[90m", "planned": "\033[90m", "unplanned": "\033[35m",
         "plan_uncited": "\033[33m", "reference": "\033[90m"}
ICON = {"done": "✓", "partial": "~", "cancelled": "✗", "empty": "–"}
BOX = {"done": "x", "partial": "~", "cancelled": "-", "empty": "-"}
OPEN_PLAN_STATES = {"open", "partial", "empty"}
OPEN_SPEC_STATES = {"unplanned", "plan_uncited"}
KINDS = ("plans", "specs", "todos")
SORTS = ("date", "repo", "progress", "updated")
STALE_HINT = "  << every declared file exists"
ANSI = re.compile(r"\033\[[0-9;]*m")
MAX_WIDTH = 120


@dataclass
class Options:
    """What the report holds (`all`, `kinds`, `repo`, `plan`, `sort`, `stale`, `evidence`, `todo_limit`) and how it is
    drawn (`summary`, `style`, `colors`, `width`; no width means the terminal's)."""
    all: bool = False
    kinds: tuple[str, ...] = ("plans", "specs")
    repo: str | None = None
    plan: str | None = None
    sort: str = "date"
    stale: bool = False
    evidence: bool = True
    todo_limit: int = 200
    summary: bool = False
    style: str = "icon"
    colors: bool = False
    width: int | None = None


def resolve_repo(name: str, repos: dict[str, str]) -> str:
    """An exact repository name wins; failing that a single substring match is enough."""
    if name in repos:
        return name
    matches = [r for r in repos if name in r]
    if len(matches) == 1:
        return matches[0]
    known = ", ".join(repos)
    raise ValueError(f"Unknown --repo={name}. Found: {known}." if not matches
                     else f"Ambiguous --repo={name}: matches {', '.join(matches)}.")


def _sort_plans(plans: list[dict], by: str) -> list[dict]:
    if by == "repo":
        return sorted(plans, key=lambda p: (p["repo"], p["file"]))
    if by == "progress":
        return sorted(plans, key=lambda p: (p["checked_steps"] / p["total_steps"] if p["total_steps"] else 1.0,
                                            p["date"]))
    if by == "updated":
        return sorted(plans, key=lambda p: (p["updated"], p["repo"], p["file"]), reverse=True)
    return sorted(plans, key=lambda p: (p["date"], p["repo"], p["file"]))


def _totals(plans: list[dict], specs: list[dict], todos: list[dict]) -> dict:
    tasks = [t for p in plans for t in p["tasks"]]
    plan_count = lambda state: sum(p["state"] == state for p in plans)  # noqa: E731
    spec_count = lambda state: sum(s["state"] == state for s in specs)  # noqa: E731
    return {
        "plans": len(plans),
        "plans_done": plan_count("done"),
        "plans_partial": plan_count("partial"),
        "plans_open": plan_count("open"),
        "plans_superseded": plan_count("superseded"),
        "tasks_done": sum(t["state"] == "done" for t in tasks),
        "tasks_partial": sum(t["state"] == "partial" for t in tasks),
        "tasks_open": sum(t["state"] not in ("done", "partial", "cancelled") for t in tasks),
        "tasks_cancelled": sum(t["state"] == "cancelled" for t in tasks),
        "stale_tasks": sum(t["stale"] for t in tasks),
        "inconsistent_plans": sum(p["inconsistency"] is not None for p in plans),
        "undocumented_plans": sum(p["docs_issue"] is not None for p in plans),
        "specs_unplanned": spec_count("unplanned"),
        "specs_reference": spec_count("reference"),
        "specs_plan_uncited": spec_count("plan_uncited"),
        "todos": len(todos),
    }


def build_report(root: Path | str, opts: Options) -> dict:
    """Scan `root` and keep what `opts` selects. The totals describe everything selected by `repo`, `plan` and `kinds`,
    before the open-work filter, so a short list still says how much exists. Raises ValueError on an unknown repo."""
    root = Path(root).resolve()
    repos = discover(root)
    repo = resolve_repo(opts.repo, repos) if opts.repo is not None else None
    every_plan = scan_plans(root, repos, opts.evidence)
    plans = [p for p in every_plan
             if "plans" in opts.kinds and (repo is None or p["repo"] == repo)
             and (opts.plan is None or opts.plan in p["file"])]
    plans = _sort_plans(plans, opts.sort)
    # Whether a plan names a spec is answered against every plan, never against the filtered ones.
    specs = [s for s in scan_specs(root, repos, every_plan) if repo is None or s["repo"] == repo] \
        if "specs" in opts.kinds else []
    todos = scan_todos(root, repos, max(1, opts.todo_limit), only=repo) if "todos" in opts.kinds else []
    totals = _totals(plans, specs, todos)
    if not opts.all or opts.stale:
        plans = [{**p, "tasks": [t for t in p["tasks"] if t["state"] not in ("done", "cancelled")
                                 and (t["stale"] or not opts.stale)]}
                 for p in plans if opts.all or p["state"] in OPEN_PLAN_STATES]
        if opts.stale:
            plans = [p for p in plans if p["tasks"]]
    if not opts.all:
        specs = [s for s in specs if s["state"] in OPEN_SPEC_STATES]
    if opts.stale:
        specs, todos = [], []
    return {"generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "scope": "all" if opts.all else "open", "totals": totals, "plans": plans, "specs": specs, "todos": todos}


def _width(opts: Options) -> int:
    return max(20, min(opts.width or shutil.get_terminal_size((100, 24)).columns, MAX_WIDTH))


def _shorten(text: str, limit: int) -> str:
    text = re.sub(r"\*\*|`", "", text).strip()
    return text if len(text) <= limit else text[:max(limit - 1, 0)] + "…"


def _shorten_left(text: str, limit: int) -> str:
    return text if len(text) <= limit else "…" + text[len(text) - max(limit - 1, 0):]


def _clip(line: str, width: int) -> str:
    """A line that still overflows is cut to the width; its colour codes go with it."""
    plain = ANSI.sub("", line)
    return line if len(plain) <= width else plain[:width - 1] + "…"


def _paint(state: str, opts: Options) -> str:
    label = LABEL.get(state, state)
    return f"{COLOR.get(state, '')}{label}\033[0m" if opts.colors else label


def _mark(state: str, opts: Options) -> str:
    """Always three visible characters, so callers pad around it rather than through it."""
    if opts.style == "icon":
        glyph, tail = ICON.get(state, "○"), "  "
    else:
        glyph, tail = BOX.get(state, " "), ""
    if opts.colors:
        glyph = f"{COLOR.get(state, '')}{glyph}\033[0m"
    return glyph + tail if opts.style == "icon" else f"[{glyph}]"


def _rule(title: str, width: int) -> list[str]:
    return ["", title, "-" * min(len(title), width)]


def _plan_header(plan: dict, opts: Options, width: int) -> list[str]:
    declared = f"  status: {plan['front_matter_status']}" if plan["front_matter_status"] else ""
    date = f"~{plan['date']}  " if plan["date_source"] == "mtime" else ""
    tail = f"  {_updated(plan)}  [{plan['repo']}]  {plan['checked_steps']}/{plan['total_steps']} steps  "
    visible_tail = len(tail) + len(LABEL.get(plan["state"], plan["state"])) + len(declared)
    room = width - len(date) - visible_tail
    if room >= 16:
        return [date + _shorten(plan["file"], room) + tail + _paint(plan["state"], opts) + declared]
    return [date + _shorten(plan["file"], width - len(date)),
            f"    {_paint(plan['state'], opts)}  {plan['checked_steps']}/{plan['total_steps']} steps  "
            f"{_updated(plan)}  [{plan['repo']}]{declared}"]


def _updated(item: dict) -> str:
    """The last change, marked `~` when only the file's modification date was there to go by."""
    return ("~" if item["updated_source"] == "mtime" else "") + f"upd {item['updated']}"


def _task_line(task: dict, opts: Options, width: int) -> str:
    """Names are padded to one column; on a narrow terminal the evidence and the stale hint shrink first."""
    evidence = f"  files {task['files_found']}/{task['files_total']}" if task["files_total"] else ""
    stale = STALE_HINT if task["stale"] else ""
    room = width - 8 - 6  # mark and indent, counts
    for ev, st in ((evidence, stale), (evidence, "  <<" if stale else ""), ("", "  <<" if stale else ""), ("", "")):
        # Reserve the longest tail on wide terminals so that the counts line up from one task to the next.
        reserve = 13 + len(STALE_HINT) if (ev, st) == (evidence, stale) else len(ev) + len(st)
        if room - reserve >= 16:
            break
    name_width = min(52, room - reserve)
    name = _shorten(task["name"], name_width).ljust(name_width)
    return f"    {_mark(task['state'], opts)} {name} {task['checked']:2d}/{task['total']:<2d}{ev}{st}"


def render_table(report: dict, opts: Options) -> str:
    width = _width(opts)
    out: list[str] = []
    if report["plans"]:
        out += _rule("PLANS", width)
        for plan in report["plans"]:
            out += _plan_header(plan, opts, width)
            if plan["inconsistency"]:
                out.append("    ! " + _shorten(plan["inconsistency"], width - 6))
            if plan["docs_issue"]:
                out.append("    ! " + _shorten(plan["docs_issue"], width - 6))
            if not opts.summary:
                out += [_task_line(task, opts, width) for task in plan["tasks"]]
                out.append("")

    def specs_of(state: str) -> list[dict]:
        return [s for s in report["specs"] if s["state"] == state]

    def spec_block(title: str, state: str, extra) -> None:
        if not (found := specs_of(state)):
            return
        out.extend(_rule(title, width))
        for spec in found:
            head = f"    {LABEL[state]:<8} {_updated(spec)}  [{spec['repo']}] "
            out.append(head + _shorten(spec["title"], width - len(head)))
            out.extend("             " + _shorten_left(line, width - 13) for line in extra(spec))
        out.append("")

    spec_block("SPECS WITH AN UNCITED PLAN", "plan_uncited",
               lambda s: [f"spec: {s['path']}", f"plan: {s['sibling_plan']}"])
    spec_block("SPECS WITH NO PLAN", "unplanned", lambda s: [s["path"]])
    spec_block("SPECS WITH A PLAN", "planned", lambda s: [s["path"]])
    spec_block("SPECS THAT NEED NO PLAN", "reference", lambda s: [s["path"]])

    if report["todos"]:
        out += _rule("CODE MARKERS", width)
        for todo in report["todos"]:
            head = f"    {todo['marker']:<6} "
            where = _shorten_left(f"{todo['path']}:{todo['line']}", max(10, width - len(head) - 12))
            out.append(head + where + "  " + _shorten(todo["text"], max(0, width - len(head) - len(where) - 2)))
        out.append("")

    t = report["totals"]
    if not (report["plans"] or report["specs"] or report["todos"]):
        out += ["", "Nothing open." if report["scope"] == "open" else "Nothing found."]
    out += ["", *textwrap_line(
        f"Plans {t['plans']} ({t['plans_done']} done, {t['plans_partial']} partial, {t['plans_open']} open, "
        f"{t['plans_superseded']} superseded) | tasks {t['tasks_done']} done, {t['tasks_partial']} partial, "
        f"{t['tasks_open']} open, {t['tasks_cancelled']} cancelled | specs: {t['specs_unplanned']} with no plan, "
        f"{t['specs_plan_uncited']} with an uncited plan | code markers {t['todos']}", width)]
    if t["stale_tasks"]:
        out += textwrap_line(f"{t['stale_tasks']} unflagged task(s) have every declared file on disk: verify "
                             "them, then flag or explain.", width)
    if t["inconsistent_plans"]:
        out += textwrap_line(f"{t['inconsistent_plans']} plan(s) disagree with their own declared status: "
                             "reconcile the front-matter.", width)
    if t["undocumented_plans"]:
        out += textwrap_line(f"{t['undocumented_plans']} finished plan(s) do not point at existing documentation: "
                             "add a Documented in line naming the documents that describe the work now.", width)
    lines = []
    for line in out:
        if line or (lines and lines[-1]):
            lines.append(_clip(line.rstrip(), width))
    return "\n".join(lines) + "\n"


def textwrap_line(text: str, width: int) -> list[str]:
    return textwrap.wrap(text, width, break_long_words=True)


def render_json(report: dict, opts: Options) -> str:
    return json.dumps(report, indent=4, ensure_ascii=False) + "\n"


SVG = '<svg class="ico" viewBox="0 0 16 16" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="2" ' \
      'stroke-linecap="round" stroke-linejoin="round">{}</svg>'
SVG_DEFAULT = '<circle cx="8" cy="8" r="5.6"/>'
SVG_PATH = {
    "done": '<polyline points="3.5,8.5 6.8,11.8 12.5,4.8"/>',
    "partial": '<path d="M3.5 9.2c1.2-2.6 2.5-2.6 3.7 0s2.5 2.6 3.7 0"/><circle cx="8" cy="8" r="6.2" opacity=".35"/>',
    "empty": '<path d="M4 8h8" opacity=".6"/>',
    "cancelled": '<path d="M4.5 4.5l7 7M11.5 4.5l-7 7" opacity=".6"/>',
}
HTML_HEAD = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Backlog</title>
<style>
:root { color-scheme: light dark; --bg:#fff; --fg:#14161a; --muted:#6b7280; --line:#e5e7eb; --chip:#f3f4f6;
        --done:#0a7f3f; --partial:#9a6700; --open:#b42318; --other:#6b21a8; }
@media (prefers-color-scheme: dark) { :root { --bg:#14161a; --fg:#e8e8e8; --muted:#9aa0a6; --line:#2a2d33; --chip:#22252b;
        --done:#43c06f; --partial:#e3b341; --open:#ff7b72; --other:#d8b4fe; } }
body { margin:0; padding:24px; background:var(--bg); color:var(--fg);
       font:14px/1.5 ui-sans-serif,system-ui,-apple-system,"Segoe UI",sans-serif; }
h1 { font-size:18px; margin:0 0 4px; } p.sub { color:var(--muted); margin:0 0 16px; font-size:13px; }
.controls { display:flex; gap:8px; flex-wrap:wrap; margin-bottom:14px; }
button { font:inherit; font-size:13px; padding:5px 12px; border:1px solid var(--line); border-radius:999px;
         background:var(--chip); color:var(--fg); cursor:pointer; }
button[aria-pressed="true"] { border-color:currentColor; font-weight:600; }
.wrap { overflow-x:auto; } table { border-collapse:collapse; width:100%; min-width:760px; }
td { padding:6px 10px; border-bottom:1px solid var(--line); vertical-align:top; }
tr.group td { background:var(--chip); border-top:2px solid var(--line); }
td.dim { color:var(--muted); font-size:12px; white-space:nowrap; }
td.num { text-align:right; white-space:nowrap; font-variant-numeric:tabular-nums; }
.pill { font-size:11px; letter-spacing:.04em; padding:2px 8px; border-radius:999px; border:1px solid currentColor; white-space:nowrap; }
.done .pill{color:var(--done)} .partial .pill{color:var(--partial)} .open .pill{color:var(--open)}
.box { display:inline-flex; align-items:center; }
.ico { width:16px; height:16px; display:block; }
.done .ico{color:var(--done)} .partial .ico{color:var(--partial)} .open .ico{color:var(--open)} .empty .ico,.cancelled .ico{color:var(--muted)}
.unplanned .pill,.superseded .pill{color:var(--other)}
.warn { color:var(--partial); font-size:12px; }
[hidden]{display:none!important}
</style></head><body>
<h1>Backlog</h1>
<p class="sub">__SUMMARY__</p>
<div class="controls">
  <button data-f="all" aria-pressed="true">All</button>
  <button data-f="open" aria-pressed="false">Open</button>
  <button data-f="partial" aria-pressed="false">Partial</button>
  <button data-f="done" aria-pressed="false">Done</button>
  <button data-k="plan" aria-pressed="false">Plans only</button>
  <button data-k="spec" aria-pressed="false">Specs only</button>
  <button data-k="todo" aria-pressed="false">Markers only</button>
</div>
<div class="wrap"><table>__BODY__</table></div>
<script>
var state = { f: 'all', k: 'all' };
function apply() {
  document.querySelectorAll('tr.row').forEach(function (row) {
    var okF = state.f === 'all' || row.classList.contains(state.f);
    var okK = state.k === 'all' || row.dataset.kind === state.k;
    row.hidden = !(okF && okK);
  });
  document.querySelectorAll('tr.group').forEach(function (row) {
    var next = row.nextElementSibling, visible = false;
    while (next && next.classList.contains('row')) {
      if (!next.hidden) { visible = true; break; }
      next = next.nextElementSibling;
    }
    row.hidden = !(visible || (state.f === 'all' && state.k === 'all'));
  });
}
document.querySelectorAll('button[data-f]').forEach(function (b) {
  b.addEventListener('click', function () {
    state.f = b.dataset.f;
    document.querySelectorAll('button[data-f]').forEach(function (o) { o.setAttribute('aria-pressed', String(o === b)); });
    apply();
  });
});
document.querySelectorAll('button[data-k]').forEach(function (b) {
  b.addEventListener('click', function () {
    state.k = state.k === b.dataset.k ? 'all' : b.dataset.k;
    document.querySelectorAll('button[data-k]').forEach(function (o) {
      o.setAttribute('aria-pressed', String(o === b && state.k !== 'all'));
    });
    apply();
  });
});
</script>
</body></html>
"""


def render_html(report: dict, opts: Options) -> str:
    e = lambda text: html.escape(str(text), quote=True)  # noqa: E731
    rows = []
    for plan in report["plans"]:
        state = plan["state"]
        warning = plan["inconsistency"] or plan["docs_issue"]
        note = f'<span class="warn">{e(warning)}</span>' if warning else e(plan["front_matter_status"] or "")
        rows.append(f'<tr class="group plan {state}" data-kind="plan"><td>{e(plan["repo"])}</td>'
                    f'<td><strong>{e(plan["title"])}</strong></td>'
                    f'<td class="num">{plan["checked_steps"]}/{plan["total_steps"]}</td>'
                    f'<td><span class="pill {state}">{e(LABEL.get(state, state))}</span></td><td>{note}</td>'
                    f'<td class="dim">{e(_updated(plan))}</td></tr>')
        for task in plan["tasks"]:
            ts = task["state"]
            evidence = f"{task['files_found']}/{task['files_total']} files" if task["files_total"] else ""
            hint = ' <span class="warn">all files exist</span>' if task["stale"] else ""
            rows.append(f'<tr class="row {ts}" data-kind="plan"><td class="dim">{e(plan["file"])}</td>'
                        f'<td>{e(task["name"])}</td><td class="num">{task["checked"]}/{task["total"]}</td>'
                        f'<td><span class="box" title="{e(LABEL.get(ts, ts))}">{SVG.format(SVG_PATH.get(ts, SVG_DEFAULT))}</span></td>'
                        f'<td>{e(evidence)}{hint}</td><td></td></tr>')
    for spec in report["specs"]:
        state = spec["state"]
        if state == "reference":
            continue
        rows.append(f'<tr class="row {state}" data-kind="spec"><td class="dim">{e(spec["repo"])}</td>'
                    f'<td>{e(spec["title"])}</td><td class="num"></td>'
                    f'<td><span class="pill {state}">{e(LABEL.get(state, ""))}</span></td>'
                    f'<td class="dim">{e(spec["sibling_plan"] or spec["path"])}</td>'
                    f'<td class="dim">{e(_updated(spec))}</td></tr>')
    for todo in report["todos"]:
        rows.append(f'<tr class="row open" data-kind="todo"><td class="dim">{e(todo["repo"])}</td>'
                    f'<td>{e(todo["text"])}</td><td class="num"></td>'
                    f'<td><span class="pill open">{e(todo["marker"])}</span></td>'
                    f'<td class="dim">{e(todo["path"])}:{todo["line"]}</td><td></td></tr>')
    t = report["totals"]
    scope = "open work only" if report["scope"] == "open" else "everything"
    summary = (f"{t['plans']} plans · {t['tasks_open']} tasks open · {t['specs_unplanned']} specs without a plan · "
               f"{t['todos']} code markers · {scope} · generated {report['generated_at']}")
    return HTML_HEAD.replace("__SUMMARY__", e(summary)).replace("__BODY__", "\n".join(rows))


USAGE = """Development backlog of a repository, or of a whole workspace: plans, specs and code markers.

Shows the open work (open and partial plans, plans with no boxes, specs without a plan); --all adds the rest.
Repositories are discovered: every directory under the root holding plans or specs is one. A plan's front matter
`status:` overrides its checkbox counts. Steps are `- [ ]` open, `- [x]` done, `- [-]` cancelled. Each plan and spec
shows its last change (`upd`): the last commit that touched it, or the file's modification date when it has uncommitted
changes or is not in git (`~`). A finished plan must name existing documentation on a `**Documented in:**` line. The
tool never edits a plan."""


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="plan_status.py", description=USAGE,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--root", default=".", help="where to scan from (default: the current directory)")
    p.add_argument("--format", choices=("table", "json", "html"), default="table", help="output format")
    p.add_argument("--kind", default="plans,specs", help="sources to scan: plans,specs,todos (default: plans,specs)")
    p.add_argument("--all", action="store_true", help="also finished and superseded plans and planned specs")
    p.add_argument("--open", action="store_true", help="only open work; this is the default")
    p.add_argument("--stale", action="store_true", help="only unflagged tasks that create files, all of which exist")
    p.add_argument("--plan", help="filter plans by file name substring")
    p.add_argument("--repo", help="limit to one repository; a unique substring is enough")
    p.add_argument("--sort", choices=SORTS, default="date", help="order plans: oldest first, by repo, least advanced, or last changed first")
    p.add_argument("--style", choices=("icon", "box"), default="icon", help="task marks as icons or ASCII checkboxes")
    p.add_argument("--summary", action="store_true", help="one line per plan, no task detail")
    p.add_argument("--todo-limit", type=int, default=200, help="cap code markers (default: 200)")
    p.add_argument("--out", help="write to a file instead of stdout")
    p.add_argument("--no-evidence", action="store_true", help="skip filesystem checks")
    p.add_argument("--repos", action="store_true", help="list the repositories found under the root and exit")
    return p


def main(argv: list[str] | None = None) -> int:
    try:
        args = _parser().parse_args(argv)
    except SystemExit as stop:
        return stop.code if isinstance(stop.code, int) else 1
    root = Path(args.root).resolve()
    if not root.is_dir():
        print(f"Invalid --root={args.root}: not a directory.", file=sys.stderr)
        return 1
    kinds = tuple(k.strip() for k in args.kind.split(",") if k.strip())
    if bad := [k for k in kinds if k not in KINDS]:
        print(f"Invalid --kind {','.join(bad)}. Use plans, specs or todos.", file=sys.stderr)
        return 2
    repos = discover(root)
    if not repos:
        print(f"No plans or specs found under {root}.")
        return 0
    if args.repos:
        for name, relative in repos.items():
            print(f"{name:<24} {relative or '.'}")
        return 0
    opts = Options(all=args.all, kinds=kinds, repo=args.repo, plan=args.plan, sort=args.sort, stale=args.stale,
                   evidence=not args.no_evidence, todo_limit=args.todo_limit, summary=args.summary, style=args.style,
                   colors=args.out is None and args.format == "table" and sys.stdout.isatty())
    try:
        report = build_report(root, opts)
    except ValueError as error:
        print(error, file=sys.stderr)
        return 1
    output = {"json": render_json, "html": render_html}.get(args.format, render_table)(report, opts)
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(output)
        print(f"Written: {args.out}")
    else:
        sys.stdout.write(output)
    return 0


if __name__ == "__main__":
    sys.exit(main())
