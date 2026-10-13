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
import os
import re
import shutil
import subprocess
import sys
import stat
from datetime import datetime, timezone
from pathlib import Path

from factory_plan import parse_plan
from route import load_rules, route

TERMINAL = ("merged", "committed")
VERDICTS = ("PASS", "CHANGES")
STOPWORDS = {"the", "a", "an", "to", "of", "for", "and", "in", "on", "with"}
LITE_MAX_FILES = 3
LITE_MAX_LINES = 30
STALE_MINUTES = 30


def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def jobs_dir(root) -> Path:
    return Path(root) / "factory/jobs"


def read_job(root, job_id: str) -> dict:
    return json.loads((jobs_dir(root) / job_id / "job.json").read_text())


def write_job(root, job: dict) -> None:
    job["updated"] = now()
    (jobs_dir(root) / job["id"] / "job.json").write_text(json.dumps(job, indent=2))
    touch_lock(root, job.get("plan", ""))


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
    touch_lock(root, job["plan"])
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


# ---- run lock: one run per plan, and the plan and its spec read-only while it lasts ----


def lock_path(root, plan_stem: str) -> Path:
    return jobs_dir(root) / "_runs" / f"{plan_stem}.lock"


def read_lock(root, plan_stem: str) -> dict | None:
    p = lock_path(root, plan_stem)
    try:
        return json.loads(p.read_text())
    except (OSError, json.JSONDecodeError):
        return None


def age_minutes(iso: str) -> float:
    t = datetime.strptime(iso, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - t).total_seconds() / 60


def touch_lock(root, plan_stem: str) -> None:
    lock = read_lock(root, plan_stem) if plan_stem else None
    if lock:
        lock["heartbeat"] = now()
        lock_path(root, plan_stem).write_text(json.dumps(lock, indent=2))


def lock_view(lock: dict, stale_minutes: int = STALE_MINUTES) -> dict:
    return {"plan": lock["plan"], "run_id": lock["run_id"], "since": lock["started"], "heartbeat": lock["heartbeat"],
            "stale": age_minutes(lock["heartbeat"]) > stale_minutes, "protect": lock["protect"]}


def lock_acquire(root, plan_file: str, run_id: str, force: bool = False, stale_minutes: int = STALE_MINUTES) -> dict:
    root = Path(root)
    path = Path(plan_file) if Path(plan_file).is_absolute() else root / plan_file
    plan = parse_plan(path.read_text())
    stem = path.stem
    existing = read_lock(root, stem)
    modes: dict[str, int] = {}
    if existing:
        view = lock_view(existing, stale_minutes)
        if existing["run_id"] == run_id:
            touch_lock(root, stem)
            return {"ok": True, "held": True, "reacquired": True}
        if not force:
            return {"ok": False, "held_by": existing["run_id"], "since": existing["started"], "heartbeat": existing["heartbeat"], "stale": view["stale"]}
        modes = existing.get("modes", {})
    protect = [plan_file] + ([plan.spec] if plan.spec else [])
    for rel in protect:
        p = root / rel
        if p.exists():
            modes.setdefault(rel, stat.S_IMODE(p.stat().st_mode))
            p.chmod(modes[rel] & ~0o222)
    lock = {"run_id": run_id, "plan": stem, "path": plan_file, "spec": plan.spec, "protect": protect, "modes": modes,
            "started": now(), "heartbeat": now()}
    lp = lock_path(root, stem)
    lp.parent.mkdir(parents=True, exist_ok=True)
    lp.write_text(json.dumps(lock, indent=2))
    return {"ok": True, "held": True, "reacquired": False}


def lock_release(root, plan_stem: str, run_id: str | None = None, force: bool = False) -> dict:
    root = Path(root)
    lock = read_lock(root, plan_stem)
    if not lock:
        return {"ok": True, "released": False}
    if run_id and lock["run_id"] != run_id and not force:
        return {"ok": False, "released": False, "held_by": lock["run_id"]}
    for rel, mode in lock.get("modes", {}).items():
        p = root / rel
        if p.exists():
            p.chmod(mode)
    lock_path(root, plan_stem).unlink()
    return {"ok": True, "released": True}


def lock_list(root, stale_minutes: int = STALE_MINUTES) -> list[dict]:
    out = []
    for f in sorted((jobs_dir(root) / "_runs").glob("*.lock")):
        lock = read_lock(root, f.stem)
        if lock:
            out.append(lock_view(lock, stale_minutes))
    return out


def tick_plan(root, plan_file: str) -> dict:
    """Tick the open steps of every task a job has landed. Works on a read-only plan and leaves it read-only."""
    root = Path(root)
    path = Path(plan_file) if Path(plan_file).is_absolute() else root / plan_file
    plan = parse_plan(path.read_text())
    landed = set()
    for f in jobs_dir(root).glob("*/job.json"):
        j = json.loads(f.read_text())
        if j.get("plan") == path.stem and j.get("stage") in TERMINAL:
            landed.add(j.get("task"))
    heading = re.compile(r"^#{2,4}\s+(?:Task|Phase|Step|Milestone|Wave)\b[^\n]*?(\d+)", re.I)
    out, current, in_fence, ticked = [], None, False, 0
    for line in path.read_text().splitlines(keepends=True):
        if re.match(r"^\s*(```|~~~)", line):
            in_fence = not in_fence
        elif not in_fence and (m := heading.match(line)):
            current = int(m.group(1))
        elif not in_fence and current in landed and re.match(r"^\s*[-*] \[ \]", line):
            line = line.replace("[ ]", "[x]", 1)
            ticked += 1
        out.append(line)
    text = "".join(out)
    after = parse_plan(text)
    stepped = [t for t in after.tasks if t.steps]
    closed = bool(stepped) and all(t.done for t in stepped) and after.status not in ("completed", "done", "shipped")
    if closed:
        text = close_header(text)
        if RECORD_TITLE not in text:
            text = text.rstrip("\n") + "\n\n" + execution_record(root, path.stem)
    mode = stat.S_IMODE(path.stat().st_mode)
    path.chmod(mode | 0o200)
    try:
        path.write_text(text)
    finally:
        path.chmod(mode)
    return {"ok": True, "ticked": ticked, "closed": closed}


RECORD_TITLE = "## Execution record"


def _plan_jobs(root, plan_stem: str) -> list[dict]:
    jobs = []
    for f in sorted(jobs_dir(root).glob("*/job.json")):
        j = json.loads(f.read_text())
        if j.get("plan") == plan_stem:
            jobs.append(j)
    return jobs


def execution_record(root, plan_stem: str) -> str:
    """What the run did, as a table without checkboxes so plan tools do not read it as work. Kept in the plan, which
    travels with the repo, since the job folders are local and are removed once the plan is closed."""
    rows, tokens, ms = [], 0, 0
    for j in _plan_jobs(root, plan_stem):
        folder = jobs_dir(root) / j["id"]
        agents = j.get("agents", {})
        t = sum(a.get("tokens", 0) for a in agents.values())
        m = sum(a.get("ms", 0) for a in agents.values())
        tokens, ms = tokens + t, ms + m
        verdicts = ", ".join(f"{k} {v}" for k, v in j.get("reviews", {}).items()) or "short path"
        decision = ""
        if (folder / "decision.md").exists():
            decision = (folder / "decision.md").read_text().splitlines()[0].strip()
        notes = []
        if n := len(list(folder.glob("rework-*.md"))):
            notes.append(f"reworked {n}x")
        if n := len(list(folder.glob("answers-*.md"))):
            notes.append(f"{n} answered question(s)")
        models = "/".join(sorted({a.get("model", "") for a in agents.values() if a.get("model")}))
        rows.append(f"| {j.get('task')} | {j.get('tier', '')} | {models} | {j.get('round', 1)} | {verdicts} | {decision} | {'; '.join(notes)} | {t} | {m // 1000}s |")
    head = "| Task | Tier | Models | Rounds | Reviews | Decision | Notes | Tokens | Agent time |\n|---|---|---|---|---|---|---|---|---|\n"
    return f"{RECORD_TITLE}\n\n{head}" + "\n".join(rows) + f"\n\nTotal: {tokens} tokens, {ms // 1000}s of agent time.\n"


def clean_jobs(root, plan_stem: str) -> dict:
    """Remove the local job folders and run state of a finished plan. Refuses while any job of the plan is not landed."""
    jobs = _plan_jobs(root, plan_stem)
    waiting = [j["id"] for j in jobs if j.get("stage") not in TERMINAL]
    if waiting:
        return {"ok": False, "reason": "jobs not landed: " + ", ".join(waiting), "removed": []}
    for j in jobs:
        shutil.rmtree(jobs_dir(root) / j["id"], ignore_errors=True)
    run_path(root, plan_stem).unlink(missing_ok=True)  # the lock is released by `lock release`, which restores the plan's permissions
    return {"ok": True, "removed": [j["id"] for j in jobs]}


def close_header(text: str) -> str:
    """Declare the plan completed in its YAML front matter, creating the block when the plan has none."""
    fields = f"status: completed\nverified_on: {datetime.now(timezone.utc).date().isoformat()}\nverified_by: clay run\n"
    lines = text.splitlines(keepends=True)
    if lines and lines[0].strip() == "---":
        end = next((i for i, l in enumerate(lines[1:], 1) if l.strip() == "---"), None)
        if end is not None:
            kept = [l for l in lines[1:end] if not re.match(r"^(status|verified_on|verified_by):", l)]
            return "".join(["---\n", *kept, fields, *lines[end:]])
    return f"---\n{fields}---\n" + text


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="state.py")
    sub = ap.add_subparsers(dest="cmd", required=True)
    lk = sub.add_parser("lock")
    lk.add_argument("action", choices=("acquire", "release", "status", "list"))
    lk.add_argument("--root", default=".")
    lk.add_argument("--plan-file")
    lk.add_argument("--plan")
    lk.add_argument("--run-id")
    lk.add_argument("--force", action="store_true")
    lk.add_argument("--stale-minutes", type=int, default=STALE_MINUTES)
    tp = sub.add_parser("tick-plan")
    tp.add_argument("--root", default=".")
    tp.add_argument("--plan-file", required=True)
    cl = sub.add_parser("clean")
    cl.add_argument("--root", default=".")
    cl.add_argument("--plan", required=True)
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
    if a.cmd == "clean":
        out = clean_jobs(a.root, a.plan)
        print(json.dumps(out, indent=2))
        return 0 if out["ok"] else 1
    if a.cmd == "tick-plan":
        print(json.dumps(tick_plan(a.root, a.plan_file), indent=2))
        return 0
    if a.cmd == "lock":
        stem = a.plan or (Path(a.plan_file).stem if a.plan_file else "")
        if a.action == "acquire":
            out = lock_acquire(a.root, a.plan_file, a.run_id or "", a.force, a.stale_minutes)
        elif a.action == "release":
            out = lock_release(a.root, stem, a.run_id, a.force)
        elif a.action == "status":
            lock = read_lock(a.root, stem)
            out = {"held": bool(lock), **(lock_view(lock, a.stale_minutes) if lock else {})}
        else:
            out = lock_list(a.root, a.stale_minutes)
        print(json.dumps(out, indent=2))
        return 3 if a.action == "acquire" and not out["ok"] else 0
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
