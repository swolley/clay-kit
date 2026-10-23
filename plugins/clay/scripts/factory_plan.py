#!/usr/bin/env python3
"""Parse a plan in the superpowers-compatible superset format into tasks and steps."""
import json
import re
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

TASK_HEADING = re.compile(r"^#{2,4}\s+((?:Task|Phase|Step|Milestone|Wave)\b[^\n]*)$", re.I)
FIELD = re.compile(r"^\s*\*\*(Repo|Tier|Depends|Files|Docs|Constraints|Accept|Verify):\*\*\s*(.*)$")
TIERS = {"light", "medium", "careful", "heavy", "fable"}
STEP = re.compile(r"^\s*[-*] \[([ xX-])\]\s*(.*)$")
STATES = {" ": "open", "x": "done", "X": "done", "-": "cancelled"}
BANNER = re.compile(r"^(?:>\s*)?(?:\*\*Status:\*\*|Status:)\s*(.+)$")
SECTION = re.compile(r"^##\s+(.+)$")
FILE_LINE = re.compile(r"^\s*[-*] (Create|Modify|Test|Migration|File):\s*(.+)$", re.I)
PLAN_LEVEL = "(plan level)"


@dataclass
class Step:
    state: str
    text: str


@dataclass
class Task:
    number: int
    title: str
    repo: str = ""
    tier: str = "medium"
    depends: list[int] = field(default_factory=list)
    files: list[str] = field(default_factory=list)
    docs: list[str] = field(default_factory=list)  # the documentation the task keeps true, from `**Docs:**`
    docs_none: str = ""  # why the task changes no documentation, from `**Docs:** none: <reason>`
    constraints: str = ""
    accept: list[str] = field(default_factory=list)
    verify: str = ""
    commits: list[str] = field(default_factory=list)
    files_create: list[str] = field(default_factory=list)
    files_delete: list[str] = field(default_factory=list)
    steps: list[Step] = field(default_factory=list)
    kind: str = "task"  # task, or a checklist outside the tasks: plan (above the first task) or section (a `##` heading)
    defaults_applied: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    fields_seen: set[str] = field(default_factory=set, repr=False)

    @property
    def done(self) -> bool:
        states = [s.state for s in self.steps]
        return bool(states) and "open" not in states

    def counts(self) -> tuple[int, int, int]:
        """Open, done and cancelled steps."""
        states = [s.state for s in self.steps]
        return states.count("open"), states.count("done"), states.count("cancelled")

    @property
    def state(self) -> str:
        """empty, cancelled, done, partial or open. Cancelled steps count as resolved; a task whose steps are
        all cancelled is cancelled rather than done."""
        open_, done, cancelled = self.counts()
        if not self.steps:
            return "empty"
        if cancelled == len(self.steps):
            return "cancelled"
        if open_ == 0:
            return "done"
        return "open" if done + cancelled == 0 else "partial"


CLOSED = {"completed", "done", "shipped"}
DROPPED = {"superseded", "abandoned", "cancelled"}


@dataclass
class Plan:
    title: str
    tasks: list[Task]
    spec: str = ""
    status: str = ""  # the `status:` of the YAML front matter, lowercased; empty when absent
    banner: str = ""  # a `**Status:** ...` or `Status: ...` line above the first task; empty when absent
    blocks: list[Task] = field(default_factory=list)  # every task, and every other checklist, in document order

    @property
    def state(self) -> str:
        """done, dropped, open or unclassified. A declared status wins over the checkboxes, since plans are
        often closed in their header only; a plan with no steps and no declared status cannot be told apart, so it is unclassified."""
        if self.status in CLOSED:
            return "done"
        if self.status in DROPPED:
            return "dropped"
        stepped = [b for b in self.blocks if b.steps]
        if not stepped:
            return "unclassified"
        return "open" if any(not t.done for t in stepped) else "done"


def _clean(text: str) -> str:
    return re.sub(r"\*\*", "", text).strip().rstrip(":").strip()


def _numbered(value: str) -> list[str]:
    """Split "1. a 2. b" at sequential markers only, so "200. " inside an item stays."""
    starts, pos, n = [], 0, 1
    while (m := re.compile(rf"(?:^|\s){n}\.\s+").search(value, pos)):
        starts.append((m.start(), m.end()))
        pos, n = m.end(), n + 1
    if not starts:
        return [value.strip()] if value.strip() else []
    return [value[e:(starts[i + 1][0] if i + 1 < len(starts) else len(value))].strip() for i, (_, e) in enumerate(starts)]


def _apply_field(task: Task, name: str, value: str) -> None:
    key = name.lower()
    task.fields_seen.add(key)
    if key == "repo":
        task.repo = value
    elif key == "tier":
        task.tier = value.lower()
    elif key == "depends":
        task.depends = [int(n) for n in re.findall(r"\d+", value)]
    elif key == "files":
        task.files = re.findall(r"`([^`]+)`", value) or [v.strip() for v in value.split(",") if v.strip()]
    elif key == "docs":
        if m := re.match(r"none\b[\s:,.-]*(.*)$", value, re.I):
            task.docs, task.docs_none = [], m.group(1).strip() or "none"
        else:
            task.docs = re.findall(r"`([^`]+)`", value) or [v.strip() for v in value.split(",") if v.strip()]
    elif key == "constraints":
        task.constraints = value
    elif key == "accept":
        task.accept = _numbered(value)
    elif key == "verify":
        task.verify = value


def _declare(task: Task, item: str, creates: bool = False, deletes: bool = False) -> None:
    """Record the backticked paths of a file line, without a trailing `:line` or `:from-to` range."""
    paths = [re.sub(r":\d+(?:-\d+)?$", "", p) for p in re.findall(r"`([^`]+)`", item)]
    task.files += paths
    if creates:
        task.files_create += paths
    if deletes:
        task.files_delete += paths


def _creates(kind: str, item: str) -> bool:
    """Whether a file line names a file the task brings into existence; a test file it extends existed before. Only the
    words outside the backticked paths are read, so "extended" or "modified" count and a path never does."""
    kind = kind.lower()
    words = re.sub(r"`[^`]*`", "", item)
    return kind in ("create", "migration") or (kind == "test" and not re.search(r"\b(append|extend|modif|exist)\w*", words, re.I))


def front_status(text: str) -> str:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return ""
    for line in lines[1:]:
        if line.strip() == "---":
            break
        if m := re.match(r"^status:\s*(.+)$", line, re.I):
            return m.group(1).strip().strip("\"'").lower()
    return ""


def _front_matter_end(lines: list[str]) -> int:
    """Index of the first line after the YAML front matter; 0 when there is none."""
    if not lines or lines[0].strip() != "---":
        return 0
    return next((i + 1 for i, line in enumerate(lines[1:], 1) if line.strip() == "---"), 0)


def plan_date(name: str) -> str:
    """The YYYY-MM-DD a plan's file name starts with; empty when it has none."""
    m = re.match(r"\d{4}-\d{2}-\d{2}", Path(name).name)
    return m.group() if m else ""


def parse_plan(text: str, default_repo: str = "") -> Plan:
    status = front_status(text)
    title = ""
    tasks: list[Task] = []
    # Steps above the first task, or under a `##` section that is not a task, are a checklist of their own: they
    # count for the plan but belong to no task.
    current = Task(number=0, title=PLAN_LEVEL, kind="plan")
    blocks = [current]
    in_fence = False
    spec = ""
    banner = ""
    last_field = ""
    lines = text.splitlines()
    body = _front_matter_end(lines)
    for i, line in enumerate(lines):
        if re.match(r"^\s*(```|~~~)", line):
            in_fence = not in_fence
            continue
        if in_fence:
            # A commit step often shows its message in a fenced `git commit -m "..."`.
            if c := re.search(r"git commit(?: -\w+)* -m\s+[\"'](.+?)[\"']", line):
                current.commits.append(c.group(1))
            continue
        if not title and (m := re.match(r"^#\s+(.+)$", line)):
            title = m.group(1).strip()
            continue
        if m := TASK_HEADING.match(line):
            heading = m.group(1)
            num = re.search(r"\d+", heading)
            number = int(num.group()) if num else len(tasks) + 1
            name = _clean(heading.split(":", 1)[1] if ":" in heading else heading)
            current = Task(number=number, title=name)
            tasks.append(current)
            blocks.append(current)
            last_field = ""
            continue
        if m := SECTION.match(line):
            current = Task(number=0, title=_clean(m.group(1)), kind="section")
            blocks.append(current)
            last_field = ""
            continue
        if not tasks:
            if m := re.match(r"^\*\*Spec:\*\*\s*(.*)$", line):
                found = re.search(r"`([^`]+)`", m.group(1))
                spec = found.group(1) if found else ""
            elif not banner and i >= body and (m := BANNER.match(line)):
                banner = m.group(1).strip()
        if current.kind == "task" and (m := FIELD.match(line)):
            _apply_field(current, m.group(1), m.group(2).strip())
            last_field = m.group(1).lower()
        elif m := FILE_LINE.match(line):
            _declare(current, m.group(2), creates=_creates(m.group(1), m.group(2)))
        elif last_field == "files" and (m := re.match(r"^\s*[-*]\s+(?!\[[ xX-]\])(.*)$", line)):
            item = m.group(1)
            _declare(current, item, creates=bool(re.match(r"\s*Create\b", item, re.I)),
                     deletes=bool(re.match(r"\s*Delete\b", item, re.I)))
        elif m := STEP.match(line):
            last_field = ""
            text = _clean(re.sub(r"^Step \d+:\s*", "", _clean(m.group(2))))
            current.steps.append(Step(STATES[m.group(1)], text))
            if c := re.match(r"Commit\b.*?`([^`]+)`", text):
                current.commits.append(c.group(1))
    for t in tasks:
        if t.tier not in TIERS:
            t.warnings.append(f"unknown tier '{t.tier}', using medium")
            t.tier = "medium"
        for name in ("tier", "repo", "depends", "files", "accept", "verify"):
            if name not in t.fields_seen:
                t.defaults_applied.append(name)
        # A light task that names no documentation declares that it changes none; any other tier is told so.
        if "docs" not in t.fields_seen and t.tier != "light":
            t.defaults_applied.append("docs")
        if "repo" not in t.fields_seen:
            t.repo = default_repo
        if "accept" not in t.fields_seen:
            t.accept = [s.text for s in t.steps if s.state != "cancelled"]
    blocks = [b for b in blocks if b.kind == "task" or b.steps]
    return Plan(title=title, tasks=tasks, spec=spec, status=status, banner=banner, blocks=blocks)


def check_files(files: list[str], root: Path) -> tuple[list[str], list[str]]:
    """Which of a task's declared files already exist under `root`. Patterns and brace lists are skipped."""
    present: list[str] = []
    missing: list[str] = []
    for f in files:
        if any(c in f for c in "*?{}"):
            continue
        (present if (root / f).exists() else missing).append(f)
    return present, missing


def done_signals(task: Task, root: Path, subjects: set[str]) -> list[str]:
    """Hints that a task was already carried out: its planned commit is in the history, or every file it
    creates exists. Modifying a file that exists is not a signal, since almost every task does that."""
    signals = [f"commit already in history: {c}" for c in task.commits if any(s == c or s.startswith(c) for s in subjects)]
    if task.files_create and all((root / f).exists() for f in task.files_create):
        signals.append("all files it creates already exist")
    return signals


def _log_subjects(repo: Path) -> set[str]:
    done = subprocess.run(["git", "-C", str(repo), "log", "--format=%s"], capture_output=True, text=True)
    return set(done.stdout.splitlines()) if done.returncode == 0 else set()


def git_subjects(root: Path) -> set[str]:
    """Commit subjects of the repo and of its checked-out submodules, since a plan's commits often land in a submodule."""
    subjects = _log_subjects(root)
    listed = subprocess.run(["git", "-C", str(root), "submodule", "status"], capture_output=True, text=True)
    if listed.returncode == 0:
        for line in listed.stdout.splitlines():
            parts = line.split()
            # A leading "-" marks a submodule that is not checked out: nothing to read there.
            if len(parts) >= 2 and not line.startswith("-"):
                subjects |= _log_subjects(root / parts[1])
    return subjects


def describe_plan(text: str, repo: str = "", root: Path | None = None) -> dict:
    """The plan as the run reads it: its tasks with defaults, warnings and, given the repo, the signs that a task is already done."""
    plan = parse_plan(text, default_repo=repo)
    subjects = git_subjects(root) if root is not None else set()
    out = {"title": plan.title, "status": plan.status, "state": plan.state, "tasks": []}
    for t in plan.tasks:
        d = asdict(t)
        d.pop("fields_seen")
        d["done"] = t.done
        if root is not None:
            d["files_present"], d["files_missing"] = check_files(t.files, root)
            d["done_signals"] = done_signals(t, root, subjects)
        out["tasks"].append(d)
    return out


def main(argv: list[str]) -> int:
    if not argv:
        print("usage: factory_plan.py <plan.md> [--repo NAME] [--root DIR]", file=sys.stderr)
        return 2
    repo = argv[argv.index("--repo") + 1] if "--repo" in argv else ""
    root = Path(argv[argv.index("--root") + 1]) if "--root" in argv else None
    print(json.dumps(describe_plan(Path(argv[0]).read_text(), repo, root), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
