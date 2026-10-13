#!/usr/bin/env python3
"""The mechanical bookkeeping of a factory run, so the orchestrator does not redo it by hand at every step.

Each command prints JSON. `verdicts` exits 1 when the round is not complete and valid.

  state.py setup --root DIR --plugin-root DIR
  state.py run --root DIR --plan-file P --mode M --pace step|auto
  state.py new-job --root DIR --plan-file P --task N --repo-name R --mode M --branch B --worktree W
  state.py stage JOB STAGE --root DIR
  state.py agent JOB ROLE --model M --effort E --tokens N --ms N --tools N --root DIR
  state.py route JOB --root DIR [--table FILE]
  state.py verdicts JOB --root DIR
  state.py land JOB --stage committed|merged --head SHA --root DIR
"""
import argparse
import json
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from factory_plan import parse_plan
from route import load_rules, route

TERMINAL = ("merged", "committed")
VERDICTS = ("PASS", "CHANGES")
STOPWORDS = {"the", "a", "an", "to", "of", "for", "and", "in", "on", "with"}
LITE_MAX_FILES = 3
LITE_MAX_LINES = 30


def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def jobs_dir(root) -> Path:
    return Path(root) / "factory/jobs"


def read_job(root, job_id: str) -> dict:
    return json.loads((jobs_dir(root) / job_id / "job.json").read_text())


def write_job(root, job: dict) -> None:
    job["updated"] = now()
    (jobs_dir(root) / job["id"] / "job.json").write_text(json.dumps(job, indent=2))


def git(cwd, *args: str) -> str:
    done = subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True)
    return done.stdout if done.returncode == 0 else ""


def setup(root, plugin_root) -> None:
    d = jobs_dir(root)
    (d / "_runs").mkdir(parents=True, exist_ok=True)
    (d / ".gitignore").write_text("*\n")
    src = Path(plugin_root) / "factory" / "dashboard.html"
    if src.exists():
        shutil.copy(src, d / "dashboard.html")


def slugify(title: str) -> str:
    words = [w for w in re.findall(r"[a-z0-9]+", title.lower()) if w not in STOPWORDS]
    return "-".join(words[:4]) or "task"


def claim_id(root, slug: str) -> str:
    d = jobs_dir(root)
    d.mkdir(parents=True, exist_ok=True)
    numbers = [int(m.group(1)) for p in d.iterdir() if (m := re.match(r"(\d{3})-", p.name))]
    n = max(numbers, default=0) + 1
    while True:
        job_id = f"{n:03d}-{slug}"
        try:
            (d / job_id).mkdir()
            return job_id
        except FileExistsError:
            n += 1


def render_brief(plan_file: str, task, default_repo: str) -> str:
    lines = [f"# Task {task.number}: {task.title}", "", f"Plan: {plan_file}", ""]
    lines.append(f"**Repo:** {task.repo or default_repo}")
    lines.append(f"**Tier:** {task.tier}")
    if task.depends:
        lines.append("**Depends:** " + ", ".join(map(str, task.depends)))
    if task.files:
        lines.append("**Files:** " + ", ".join(f"`{f}`" for f in task.files))
    if task.constraints:
        lines.append(f"**Constraints:** {task.constraints}")
    if task.accept:
        lines.append("**Accept:** " + " ".join(f"{i}. {a}" for i, a in enumerate(task.accept, 1)))
    if task.verify:
        lines.append(f"**Verify:** {task.verify}")
    lines.append("")
    lines += [f"- [ ] {s.text}" for s in task.steps if s.state != "cancelled"]
    return "\n".join(lines) + "\n"


def new_job(root, plan_file: str, task_number: int, repo_name: str, mode: str, branch: str, worktree: str, base: str | None = None) -> dict:
    root = Path(root)
    path = Path(plan_file) if Path(plan_file).is_absolute() else root / plan_file
    plan = parse_plan(path.read_text(), default_repo=repo_name)
    task = next(t for t in plan.tasks if t.number == task_number)
    job_id = claim_id(root, slugify(task.title))
    folder = jobs_dir(root) / job_id
    (folder / "task.md").write_text(render_brief(plan_file, task, repo_name))
    head = base or git(worktree, "rev-parse", "HEAD").strip()
    t = now()
    job = {
        "id": job_id, "plan": path.stem, "task": task.number, "repo": task.repo or repo_name, "mode": mode, "tier": task.tier,
        "branch": branch, "worktree": worktree, "agents": {}, "stage": "spec", "round": 0, "started": t, "updated": t,
        "reviewers": [], "reviews": {}, "head": head, "base": head, "build_round": 0, "lite": False,
        "phases": [{"stage": "spec", "start": t, "end": None}],
    }
    (folder / "job.json").write_text(json.dumps(job, indent=2))
    return {"id": job_id, "folder": str(folder)}


def set_stage(root, job_id: str, stage: str) -> dict:
    job = read_job(root, job_id)
    t = now()
    phases = job.setdefault("phases", [])
    if phases and phases[-1]["end"] is None:
        phases[-1]["end"] = t
    if stage not in TERMINAL:
        phases.append({"stage": stage, "start": t, "end": None})
    job["stage"] = stage
    write_job(root, job)
    return job


def record_agent(root, job_id: str, role: str, model: str = "", effort: str = "", tokens: int = 0, ms: int = 0, tools: int = 0) -> dict:
    job = read_job(root, job_id)
    a = job["agents"].get(role, {})
    job["agents"][role] = {
        "model": model or a.get("model", ""), "effort": effort,
        "tokens": a.get("tokens", 0) + tokens, "ms": a.get("ms", 0) + ms, "tools": a.get("tools", 0) + tools, "runs": a.get("runs", 0) + 1,
    }
    write_job(root, job)
    return job["agents"][role]


def changed(job: dict, root) -> tuple[list[str], int]:
    """The files the job's change touches and how many lines it adds or removes."""
    cwd = job.get("worktree") or str(root)
    if job["mode"] == "current-branch":
        names = git(cwd, "diff", "--name-only", "HEAD").split() + git(cwd, "ls-files", "--others", "--exclude-standard").split()
        stat = git(cwd, "diff", "--numstat", "HEAD")
    else:
        span = f"{job['base']}...{job['branch']}"
        names = git(cwd, "diff", "--name-only", span).split()
        stat = git(cwd, "diff", "--numstat", span)
    lines = sum(int(a) + int(b) for a, b, *_ in (ln.split("\t") for ln in stat.splitlines()) if a.isdigit() and b.isdigit())
    for extra in git(cwd, "ls-files", "--others", "--exclude-standard").split() if job["mode"] == "current-branch" else []:
        try:
            lines += len((Path(cwd) / extra).read_text().splitlines())
        except (OSError, UnicodeDecodeError):
            lines += LITE_MAX_LINES + 1
    return sorted(set(names)), lines


def route_job(root, job_id: str, table: str | None = None) -> dict:
    job = read_job(root, job_id)
    paths, lines = changed(job, root)
    default = Path(__file__).resolve().parent.parent / "routing.md"
    own = jobs_dir(root).parent / "routing.md"
    rules = load_rules(Path(table) if table else own if own.exists() else default)
    reviewers = route(paths, rules)
    lite = job["tier"] == "light" and reviewers == ["code"] and len(paths) <= LITE_MAX_FILES and lines <= LITE_MAX_LINES
    if lite:
        job.update(reviewers=[], reviews={}, lite=True)
        write_job(root, job)
        set_stage(root, job_id, "approve")
    else:
        job["round"] += 1
        job.update(reviewers=reviewers, reviews={r: "pending" for r in reviewers}, lite=False, build_round=job["round"])
        write_job(root, job)
        (jobs_dir(root) / job_id / f"round-{job['round']}").mkdir(exist_ok=True)
        set_stage(root, job_id, "review")
    return {"reviewers": [] if lite else reviewers, "lite": lite, "paths": paths, "files": len(paths), "lines": lines}


def check_verdicts(root, job_id: str) -> dict:
    job = read_job(root, job_id)
    rnd = jobs_dir(root) / job_id / f"round-{job['round']}"
    verdicts: dict[str, str] = {}
    missing: list[str] = []
    invalid: list[str] = []
    for r in job["reviewers"]:
        f = rnd / f"review-{r}.md"
        if not f.exists():
            missing.append(r)
            continue
        first = (f.read_text().splitlines() or [""])[0].strip()
        value = first.removeprefix("VERDICT: ") if first.startswith("VERDICT: ") else ""
        if value in VERDICTS:
            verdicts[r] = value
        else:
            invalid.append(r)
    if verdicts:
        job["reviews"].update(verdicts)
        write_job(root, job)
    ok = not missing and not invalid
    return {"ok": ok, "verdicts": verdicts, "missing": missing, "invalid": invalid, "all_pass": ok and all(v == "PASS" for v in verdicts.values())}


def run_path(root, plan_stem: str) -> Path:
    return jobs_dir(root) / "_runs" / f"{plan_stem}.json"


def landed_count(root, plan_stem: str) -> int:
    done = set()
    for f in jobs_dir(root).glob("*/job.json"):
        j = json.loads(f.read_text())
        if j.get("plan") == plan_stem and j.get("stage") in TERMINAL:
            done.add(j.get("task"))
    return len(done)


def write_run(root, plan_file: str, mode: str, pace: str = "step") -> dict:
    root = Path(root)
    path = Path(plan_file) if Path(plan_file).is_absolute() else root / plan_file
    plan = parse_plan(path.read_text())
    rp = run_path(root, path.stem)
    run = json.loads(rp.read_text()) if rp.exists() else {}
    run.update(
        plan=path.stem, path=plan_file, mode=mode, pace=pace, integration=run.get("integration"), total=len(plan.tasks),
        done=landed_count(root, path.stem),
        tasks=[{"n": t.number, "title": t.title, "tier": t.tier, "after": t.depends} for t in plan.tasks],
    )
    rp.parent.mkdir(parents=True, exist_ok=True)
    rp.write_text(json.dumps(run, indent=2))
    return run


def land_job(root, job_id: str, stage: str, head: str) -> dict:
    job = set_stage(root, job_id, stage)
    job["head"] = head
    write_job(root, job)
    rp = run_path(root, job["plan"])
    if rp.exists():
        run = json.loads(rp.read_text())
        run["done"] = landed_count(root, job["plan"])
        rp.write_text(json.dumps(run, indent=2))
    return job


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="state.py")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("setup", "run", "new-job", "stage", "agent", "route", "verdicts", "land"):
        sp = sub.add_parser(name)
        sp.add_argument("--root", default=".")
        if name in ("stage", "agent", "route", "verdicts", "land"):
            sp.add_argument("job")
        if name == "setup":
            sp.add_argument("--plugin-root", required=True)
        if name in ("run", "new-job"):
            sp.add_argument("--plan-file", required=True)
            sp.add_argument("--mode", required=True)
        if name == "run":
            sp.add_argument("--pace", default="step")
        if name == "new-job":
            sp.add_argument("--task", type=int, required=True)
            sp.add_argument("--repo-name", required=True)
            sp.add_argument("--branch", required=True)
            sp.add_argument("--worktree", required=True)
            sp.add_argument("--base")
        if name == "stage":
            sp.add_argument("stage_name")
        if name == "agent":
            sp.add_argument("role")
            for opt in ("--model", "--effort"):
                sp.add_argument(opt, default="")
            for opt in ("--tokens", "--ms", "--tools"):
                sp.add_argument(opt, type=int, default=0)
        if name == "route":
            sp.add_argument("--table")
        if name == "land":
            sp.add_argument("--stage", dest="to_stage", default="committed")
            sp.add_argument("--head", required=True)
    a = ap.parse_args(argv)
    if a.cmd == "setup":
        setup(a.root, a.plugin_root)
        out: dict = {"ok": True}
    elif a.cmd == "run":
        out = write_run(a.root, a.plan_file, a.mode, a.pace)
    elif a.cmd == "new-job":
        out = new_job(a.root, a.plan_file, a.task, a.repo_name, a.mode, a.branch, a.worktree, a.base)
    elif a.cmd == "stage":
        out = {"id": a.job, "stage": set_stage(a.root, a.job, a.stage_name)["stage"]}
    elif a.cmd == "agent":
        out = record_agent(a.root, a.job, a.role, a.model, a.effort, a.tokens, a.ms, a.tools)
    elif a.cmd == "route":
        out = route_job(a.root, a.job, a.table)
    elif a.cmd == "verdicts":
        out = check_verdicts(a.root, a.job)
    else:
        out = {"id": a.job, "stage": land_job(a.root, a.job, a.to_stage, a.head)["stage"]}
    print(json.dumps(out, indent=2))
    return 1 if a.cmd == "verdicts" and not out["ok"] else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
