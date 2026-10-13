#!/usr/bin/env python3
"""Parse a plan in the superpowers-compatible superset format into tasks and steps."""
import json
import re
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

TASK_HEADING = re.compile(r"^#{2,4}\s+((?:Task|Phase|Step|Milestone|Wave)\b[^\n]*)$", re.I)
FIELD = re.compile(r"^\s*\*\*(Repo|Tier|Depends|Files|Constraints|Accept|Verify):\*\*\s*(.*)$")
TIERS = {"light", "medium", "careful", "heavy", "fable"}
STEP = re.compile(r"^\s*[-*] \[([ xX-])\]\s*(.*)$")
STATES = {" ": "open", "x": "done", "X": "done", "-": "cancelled"}


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
    constraints: str = ""
    accept: list[str] = field(default_factory=list)
    verify: str = ""
    commits: list[str] = field(default_factory=list)
    files_create: list[str] = field(default_factory=list)
    steps: list[Step] = field(default_factory=list)
    defaults_applied: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    fields_seen: set[str] = field(default_factory=set, repr=False)

    @property
    def done(self) -> bool:
        states = [s.state for s in self.steps]
        return bool(states) and "open" not in states


@dataclass
class Plan:
    title: str
    tasks: list[Task]


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
    elif key == "constraints":
        task.constraints = value
    elif key == "accept":
        task.accept = _numbered(value)
    elif key == "verify":
        task.verify = value


def parse_plan(text: str, default_repo: str = "") -> Plan:
    title = ""
    tasks: list[Task] = []
    current: Task | None = None
    in_fence = False
    last_field = ""
    for line in text.splitlines():
        if re.match(r"^\s*(```|~~~)", line):
            in_fence = not in_fence
            continue
        if in_fence:
            # A commit step often shows its message in a fenced `git commit -m "..."`.
            if current is not None and (c := re.search(r"git commit(?: -\w+)* -m\s+[\"'](.+?)[\"']", line)):
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
            last_field = ""
            continue
        if current is None:
            continue
        if m := FIELD.match(line):
            _apply_field(current, m.group(1), m.group(2).strip())
            last_field = m.group(1).lower()
        elif last_field == "files" and (m := re.match(r"^\s*[-*]\s+(?!\[[ xX-]\])(.*)$", line)):
            paths = [re.sub(r":\d+(?:-\d+)?$", "", p) for p in re.findall(r"`([^`]+)`", m.group(1))]
            current.files += paths
            if re.match(r"\s*Create\b", m.group(1), re.I):
                current.files_create += paths
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
        if "repo" not in t.fields_seen:
            t.repo = default_repo
        if "accept" not in t.fields_seen:
            t.accept = [s.text for s in t.steps if s.state != "cancelled"]
    return Plan(title=title, tasks=tasks)


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


def git_subjects(root: Path) -> set[str]:
    done = subprocess.run(["git", "-C", str(root), "log", "--format=%s"], capture_output=True, text=True)
    return set(done.stdout.splitlines()) if done.returncode == 0 else set()


def main(argv: list[str]) -> int:
    if not argv:
        print("usage: factory_plan.py <plan.md> [--repo NAME] [--root DIR]", file=sys.stderr)
        return 2
    repo = argv[argv.index("--repo") + 1] if "--repo" in argv else ""
    root = Path(argv[argv.index("--root") + 1]) if "--root" in argv else None
    plan = parse_plan(Path(argv[0]).read_text(), default_repo=repo)
    subjects = git_subjects(root) if root is not None else set()
    out = {"title": plan.title, "tasks": []}
    for t in plan.tasks:
        d = asdict(t)
        d.pop("fields_seen")
        d["done"] = t.done
        if root is not None:
            d["files_present"], d["files_missing"] = check_files(t.files, root)
            d["done_signals"] = done_signals(t, root, subjects)
        out["tasks"].append(d)
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
