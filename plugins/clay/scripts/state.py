#!/usr/bin/env python3
"""The mechanical bookkeeping of a factory run, so the orchestrator does not redo it by hand at every step.

Each command prints JSON. `verdicts` exits 1 when the round is not complete and valid.

  state.py setup --root DIR --plugin-root DIR
  state.py adhoc --root DIR --text "[tier=NAME] TEXT"
  state.py model --root DIR --host claude|codex (--tier T | --agent A) [--risky]
  state.py run --root DIR --plan-file P --mode M --pace step|auto [--cross on|off --host H]
  state.py preflight --root DIR [--plan-file P --repo-name R] [--host H]
  state.py new-job --root DIR --plan-file P --task N --repo-name R --mode M --branch B --worktree W [--lean]
  state.py begin-job --root DIR --plan-file P --task N --repo-name R --mode M --branch B --worktree W [--lean]
  state.py stage JOB STAGE --root DIR
  state.py agent JOB ROLE --model M --effort E --tokens N --ms N --tools N [--vendor V --session-id ID] --root DIR
  state.py after-agent JOB --agents JSON --root DIR
  state.py route JOB --root DIR [--table FILE]
  state.py verdicts JOB --root DIR
  state.py verify JOB --cmd COMMAND [--reuse] [--timeout S] --root DIR
  state.py checks JOB --root DIR
  state.py concern JOB --root DIR
  state.py resolve-concern JOB --root DIR
  state.py land JOB --stage committed|merged --head SHA --root DIR
  state.py tick-plan --plan-file P [--task N] --root DIR
  state.py close-plan --plan-file P --root DIR
  state.py vendor [JOB] --agent A --host H [--plan STEM] [--risky] --root DIR
  state.py quota --vendor claude|codex --root DIR
  state.py vendor-down --plan STEM --vendor V --reason limit|missing|auth [--until ISO|EPOCH] --root DIR
  state.py escalate JOB --host H --root DIR
  state.py rework JOB --root DIR
  state.py lean-check JOB --root DIR
  state.py promote JOB --reason TEXT --root DIR
  state.py final-diff --plan STEM [--fix] --root DIR
  state.py final-verdict --plan STEM [--fix] [--fix-job ID] --agent JSON --root DIR
"""
import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import stat
import time
from datetime import datetime, timezone
from glob import escape as glob_escape
from pathlib import Path

from factory_plan import CLOSED, SECTION, TIERS, TASK_HEADING, describe_plan, parse_plan
from models import RISKY_AGENTS, ModelsError, cross_config, resolve as resolve_model
from resolve import audit_plans, list_plans, list_unclassified, load_jobs
from route import load_rules, route
from vendors import END_OF_RUN, PEER, carried_marks, decide, iso, parse_iso, quota as read_quota

TERMINAL = ("merged", "committed")
VERDICTS = ("PASS", "CHANGES")
STOPWORDS = {"the", "a", "an", "to", "of", "for", "and", "in", "on", "with"}
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


def git(cwd, *args: str, ok: tuple[int, ...] = (0,)) -> str:
    done = subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True)
    return done.stdout if done.returncode in ok else ""


def setup(root, plugin_root) -> None:
    d = jobs_dir(root)
    (d / "_runs").mkdir(parents=True, exist_ok=True)
    (d / ".gitignore").write_text("*\n")
    src = Path(plugin_root) / "factory" / "dashboard.html"
    if src.exists():
        shutil.copy(src, d / "dashboard.html")


def adhoc_plan(root, text: str) -> dict:
    """Write the one-task working plan of an ad hoc task under factory/jobs/_runs, which git never sees."""
    valid = "light, medium, careful, heavy, fable"
    tier, verify, body = "medium", "", text.strip()
    # Leading options, in any order: `tier=<name>` and `verify=<command>` ("quoted", `backticked` or one word).
    while m := re.match(r'(tier|verify)=("[^"]*"|`[^`]*`|\S*)\s*', body, re.I):
        value = m.group(2)
        if m.group(1).lower() == "tier":
            tier = value.lower()
        else:
            verify = value[1:-1] if value[:1] in ('"', "`") and len(value) > 1 else value
        body = body[m.end():]
    body = " ".join(body.split())
    if tier not in TIERS or not body:
        raise ValueError(f"an ad hoc task needs a text and a tier that is one of: {valid}")
    title = " ".join(body.split()[:8])[:60].rstrip()
    base = f"adhoc-{datetime.now().strftime('%Y%m%d-%H%M%S')}-{slugify(title)}"
    d = jobs_dir(Path(root).resolve())
    (d / "_runs").mkdir(parents=True, exist_ok=True)
    (d / ".gitignore").write_text("*\n")
    n, stem = 1, base
    while (d / "_runs" / f"{stem}.md").exists():  # same second, same text: never overwrite (or trip on) the first plan
        n += 1
        stem = f"{base}-{n}"
    path = d / "_runs" / f"{stem}.md"
    path.write_text(
        f"# Ad hoc: {title}\n\n**Spec:** none\n\n### Task 1: {title}\n\n**Tier:** {tier}\n**Accept:** 1. {body}\n"
        + (f"**Verify:** `{verify}`\n" if verify else "") + "\n"
        f"- [ ] **Step 1: {body}**\n"
    )
    return {"plan_file": str(path), "plan_stem": stem, "title": title, "tier": tier, "verify": verify}


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
    if task.docs:
        lines.append("**Docs:** " + ", ".join(f"`{d}`" for d in task.docs))
    elif task.docs_none:
        lines.append(f"**Docs:** none: {task.docs_none}")
    if task.constraints:
        lines.append(f"**Constraints:** {task.constraints}")
    if task.accept:
        lines.append("**Accept:** " + " ".join(f"{i}. {a}" for i, a in enumerate(task.accept, 1)))
    if task.verify:
        lines.append(f"**Verify:** {task.verify}")
    lines.append("")
    lines += [f"- [ ] {s.text}" for s in task.steps if s.state != "cancelled"]
    return "\n".join(lines) + "\n"


def _verify_commands(task) -> list[str]:
    """The commands of a task's `Verify`: its backticked parts, else the whole field; none when the plan declares none."""
    if "verify" in task.defaults_applied or not task.verify.strip():
        return []
    return re.findall(r"`([^`]+)`", task.verify) or [task.verify.strip()]


def new_job(root, plan_file: str, task_number: int, repo_name: str, mode: str, branch: str, worktree: str, base: str | None = None,
            lean: bool = False, job_id: str | None = None) -> dict:
    root = Path(root)
    path = Path(plan_file) if Path(plan_file).is_absolute() else root / plan_file
    plan = parse_plan(path.read_text(), default_repo=repo_name)
    task = next(t for t in plan.tasks if t.number == task_number)
    job_id = job_id or claim_id(root, slugify(task.title))
    folder = jobs_dir(root) / job_id
    (folder / "task.md").write_text(render_brief(plan_file, task, repo_name))
    head = base or git(worktree, "rev-parse", "HEAD").strip()
    t = now()
    job = {
        "id": job_id, "plan": path.stem, "task": task.number, "repo": task.repo or repo_name, "mode": mode, "tier": task.tier,
        "branch": branch, "worktree": worktree, "agents": {}, "stage": "spec", "round": 0, "started": t, "updated": t,
        "reviewers": [], "reviews": {}, "head": head, "base": head, "build_round": 0, "lite": False,
        "lean": lean, "verify": _verify_commands(task),
        "phases": [{"stage": "spec", "start": t, "end": None}],
    }
    (folder / "job.json").write_text(json.dumps(job, indent=2))
    touch_lock(root, job["plan"])
    return {"id": job_id, "folder": str(folder)}


def begin_job(root, plan_file: str, task_number: int, repo_name: str, mode: str, branch: str, worktree: str, base: str | None = None,
              lean: bool = False, job_id: str | None = None) -> dict:
    """new_job and the move to the build stage in one step."""
    out = new_job(root, plan_file, task_number, repo_name, mode, branch, worktree, base, lean, job_id)
    set_stage(root, out["id"], "build")
    return {**out, "stage": "build"}


def factory_dir(root) -> Path:
    """Where the worktrees of isolated runs live: next to the repo, never inside it."""
    root = Path(root).resolve()
    return root.parent / f"{root.name}-factory"


def _git_run(cwd, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True)


def open_job(root, plan_file: str, task_number: int, repo_name: str, mode: str, lean: bool = False) -> dict:
    """Claim a job and begin it. Isolated: the plan's integration branch `factory/<plan>` and its worktree
    `<repo-parent>/<repo-name>-factory/_integration-<plan>` are created the first time, from the repo's main branch; the job gets
    `factory/<plan>--<job-id>` (a branch cannot nest under another one) in `.../<job-id>`, cut from the integration branch, and only
    then its job.json, so a failure leaves at most an abandoned claim. Current branch: the job runs in the repo on its branch."""
    root = Path(root)
    if mode != "isolated":
        return {"ok": True, **begin_job(root, plan_file, task_number, repo_name, mode,
                                        git(root, "branch", "--show-current").strip(), str(root), lean=lean)}
    path = _plan_path(root, plan_file)
    task = next(t for t in parse_plan(path.read_text(), default_repo=repo_name).tasks if t.number == task_number)
    integration, base_dir = f"factory/{path.stem}", factory_dir(root)
    iwt = base_dir / f"_integration-{path.stem}"
    if not iwt.exists():
        if _commit(root, integration):
            done = _git_run(root, "worktree", "add", str(iwt), integration)
        elif main := _main_branch(root):
            done = _git_run(root, "worktree", "add", "-b", integration, str(iwt), main)
        else:
            return {"ok": False, "reason": "no main branch to start the integration branch from"}
        if done.returncode:
            return {"ok": False, "reason": done.stderr.strip()}
    job_id = claim_id(root, slugify(task.title))
    branch, wt = f"{integration}--{job_id}", base_dir / job_id
    done = _git_run(root, "worktree", "add", "-b", branch, str(wt), integration)
    if done.returncode:
        return {"ok": False, "reason": done.stderr.strip(), "id": job_id}
    out = begin_job(root, plan_file, task_number, repo_name, mode, branch, str(wt), lean=lean, job_id=job_id)
    rp = run_path(root, path.stem)
    if rp.exists():
        run = json.loads(rp.read_text())
        run.update(integration=integration, integration_worktree=str(iwt))
        rp.write_text(json.dumps(run, indent=2))
    return {"ok": True, **out, "branch": branch, "worktree": str(wt), "integration": integration, "integration_worktree": str(iwt)}


def concern(root, job_id: str) -> dict:
    """Open or recover the one concern per job.

    Create its file before recording the pending state. If interrupted between those writes,
    a second call recovers the existing file instead of spending a second concern.
    Only the approver can decide whether the concern is upheld.
    """
    job = read_job(root, job_id)
    path = jobs_dir(root) / job_id / "concern-1.md"
    record = job.get("concern", {})
    if record.get("status") == "resolved":
        return {"ok": False, "reason": "this job already had its one resolved concern; follow the approver's verdict"}
    if record and record.get("status") != "pending":
        return {"ok": False, "reason": "unrecognized concern status"}
    resumed = record.get("status") == "pending" or job.get("concerns", 0) >= 1 or path.exists()
    if not path.exists():
        # The orchestrator fills in numbered points before sending this file to the approver.
        path.write_text("# Concern 1\n\n## Points\n\n", encoding="utf-8")
    job["concerns"] = 1
    job["concern"] = {"status": "pending", "file": path.name}
    write_job(root, job)
    return {"ok": True, "file": str(path), "status": "pending", "resumed": resumed}


def resolve_concern(root, job_id: str) -> dict:
    """Record the approver's answer to a pending concern; reject stale verdict files.

    APPROVE needs a Concerns section and CHANGES needs an Issues section, so the
    original, pre-concern APPROVE cannot be mistaken for the new answer on resume.
    """
    job = read_job(root, job_id)
    record = job.get("concern", {})
    if record.get("status") != "pending":
        return {"ok": False, "reason": "no pending concern to resolve"}
    path = jobs_dir(root) / job_id / "concern-1.md"
    if not path.is_file() or not re.search(r"(?m)^1\.\s+\S", path.read_text(encoding="utf-8")):
        return {"ok": False, "reason": "concern file needs numbered points before the approver can answer"}
    decision_path = jobs_dir(root) / job_id / "decision.md"
    if not decision_path.is_file():
        return {"ok": False, "reason": "approver decision.md is missing"}
    decision = decision_path.read_text(encoding="utf-8")
    verdict = decision.splitlines()[0].strip() if decision.splitlines() else ""
    section = {"APPROVE": "Concerns", "CHANGES": "Issues"}.get(verdict)
    if section is None:
        return {"ok": False, "reason": "concern verdict must be APPROVE or CHANGES"}
    m = re.search(r"(?ms)^## " + section + r"\s*\n(.*?)(?=^## |\Z)", decision)
    if not m or not m.group(1).strip():
        return {"ok": False, "reason": "the approver must answer the concern in ## " + section}
    record.update(status="resolved", verdict=verdict, round=job.get("round", 0))
    job["concern"] = record
    write_job(root, job)
    return {"ok": True, "file": str(path), "status": "resolved", "verdict": verdict}


def _landing_concern_problem(root, job: dict) -> str | None:
    """A concern must be settled, and upheld CHANGES must get a fresh approved round."""
    record = job.get("concern", {})
    if record.get("status") == "pending" or (job.get("concerns") and record.get("status") != "resolved"):
        return "pending concern must be resolved before landing"
    if record.get("verdict") == "CHANGES":
        if job.get("round", 0) <= record.get("round", job.get("round", 0)):
            return "upheld concern requires a new review round before landing"
        decision = jobs_dir(root) / job["id"] / "decision.md"
        if not decision.is_file() or not decision.read_text(encoding="utf-8").startswith("APPROVE\n"):
            return "upheld concern requires a fresh APPROVE after rework"
    return None


def merge_job(root, job_id: str) -> dict:
    """Isolated landing in one step: merge the job branch into the integration worktree, tick the task in the plan there (not for
    an ad hoc plan, which is not in the repo), commit "Merge <job-id>", remove the job worktree, delete the job branch where it was
    merged (`-d` checks against the HEAD it runs in) and record the job as merged. A conflict aborts the merge and lands nothing."""
    root = Path(root)
    job = read_job(root, job_id)
    if reason := _landing_concern_problem(root, job):
        return {"ok": False, "reason": reason}
    run = read_run(root, job["plan"])
    iwt = Path(run.get("integration_worktree") or factory_dir(root) / f"_integration-{job['plan']}")
    merge = _git_run(iwt, "merge", "--no-ff", "--no-commit", job["branch"])
    if merge.returncode:
        _git_run(iwt, "merge", "--abort")
        return {"ok": False, "reason": "conflict: " + (merge.stdout + merge.stderr).strip()[-400:]}
    plan = Path(run.get("path") or "")
    if plan.parts and "_runs" not in plan.parts:
        rel = plan.relative_to(root.resolve()) if plan.is_absolute() else plan
        tick_plan(root, str(iwt / rel), job["task"])
        _git_run(iwt, "add", str(rel))
    done = _git_run(iwt, "commit", "-m", f"Merge {job_id}")
    if done.returncode:
        _git_run(iwt, "merge", "--abort")
        return {"ok": False, "reason": "commit failed: " + done.stderr.strip()[-400:]}
    head = git(iwt, "rev-parse", "HEAD").strip()
    removed = _git_run(root, "worktree", "remove", job["worktree"]).returncode == 0
    deleted = _git_run(iwt, "branch", "-d", job["branch"]).returncode == 0
    land_job(root, job_id, "merged", head)
    return {"ok": True, "head": head, "worktree_removed": removed, "branch_deleted": deleted}


def git_identity(root) -> dict:
    """Whether git can commit in the repo: with no author or committer identity every job would fail at its first commit."""
    for ident in ("GIT_AUTHOR_IDENT", "GIT_COMMITTER_IDENT"):
        done = subprocess.run(["git", "-C", str(root), "var", ident], capture_output=True, text=True)
        if done.returncode != 0:
            return {"ok": False, "reason": "git has no commit identity: set user.name and user.email (for this repo or globally)"}
    return {"ok": True, "reason": None}


def preflight(root, plan_file: str | None = None, repo_name: str = "", host: str | None = None) -> dict:
    """What a run needs to know before it starts, in one call. Without a plan: the plans with open steps and the unclassified ones.
    With a plan: the plan as parsed (defaults, warnings, signs of work already done), the jobs it already has, what the audit says about it
    and whether git can commit. With a host that has a peer vendor (claude, codex): whether the peer's CLI is on PATH."""
    root = Path(root)
    out: dict = {"unclassified": list_unclassified(root)}
    if host in PEER:
        out["peer"] = {"vendor": PEER[host], "found": shutil.which(PEER[host]) is not None}
    if not plan_file:
        out["plans"] = list_plans(root)
        return out
    path = Path(plan_file) if Path(plan_file).is_absolute() else root / plan_file
    text = path.read_text()
    out["plan"] = describe_plan(text, repo_name, root)
    rules = _rules(root)
    for task, view in zip(parse_plan(text, default_repo=repo_name).tasks, out["plan"]["tasks"]):
        view["lean"], view["lean_reason"] = lean_eligibility(task, rules, adhoc=path.parent.name == "_runs")
    out["lean_count"] = sum(1 for t in out["plan"]["tasks"] if t["lean"])
    out["long"] = out["lean_count"] > LONG_LEAN
    out["jobs"] = []
    for j in load_jobs(root):
        if j.get("plan") != path.stem:
            continue
        view = {k: j.get(k) for k in ("id", "task", "stage", "round", "build_round", "head", "branch", "worktree")}
        status = j.get("concern", {}).get("status")
        if status is None and (j.get("concerns") or (jobs_dir(root) / j["id"] / "concern-1.md").is_file()):
            status = "pending"  # recovers a crash between writing the concern file and job.json
        if status:
            view["concern_status"] = status
        out["jobs"].append(view)
    out["audit"] = [f for f in audit_plans(root) if (root.resolve() / f["root"] / f["path"]) == path.resolve()]
    out["git_identity"] = git_identity(root)
    return out


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


def record_agent(root, job_id: str, role: str, model: str = "", effort: str = "", tokens: int = 0, ms: int = 0, tools: int = 0,
                 vendor: str = "", session_id: str = "") -> dict:
    job = read_job(root, job_id)
    a = job["agents"].get(role, {})
    job["agents"][role] = {
        "model": model or a.get("model", ""), "effort": effort,
        "tokens": a.get("tokens", 0) + tokens, "ms": a.get("ms", 0) + ms, "tools": a.get("tools", 0) + tools, "runs": a.get("runs", 0) + 1,
    }
    if seen := _models(a, model):
        job["agents"][role]["models"] = seen
    for key, value in (("vendor", vendor), ("session_id", session_id)):
        if value or a.get(key):
            job["agents"][role][key] = value or a[key]
    write_job(root, job)
    return job["agents"][role]


def _models(agent: dict, model: str) -> list[str]:
    """Every model a role ran on, when there was more than one (an escalated builder); empty otherwise."""
    seen = sorted(set(agent.get("models", [])) | {m for m in (agent.get("model", ""), model) if m})
    return seen if len(seen) > 1 else []


def record_agents(root, job_id: str, agents: list[dict]) -> dict:
    """The usage of several agents that finished together, each as record_agent takes it."""
    return {a["role"]: record_agent(root, job_id, a["role"], a.get("model", ""), a.get("effort", ""), int(a.get("tokens", 0)), int(a.get("ms", 0)),
                                    int(a.get("tools", 0)), a.get("vendor", ""), a.get("session_id", "")) for a in agents}


def rework(root, job_id: str) -> dict:
    """A person sent the job back with a note: a new attempt starts, and the rounds of step 5 count from here."""
    job = read_job(root, job_id)
    job["rework_from"] = job["round"]
    write_job(root, job)
    set_stage(root, job_id, "build")
    return {"rework_from": job["round"]}


ESCALATION = {"light": "medium", "medium": "careful", "careful": "heavy"}


def escalate(root, job_id: str, host: str) -> dict:
    """Move the job one tier up for its last round, so a fresh, stronger builder tries before a person is asked. `heavy` and
    `fable` stay as they are (`fable` needs the user's confirmation). A job already escalated is left as it is, so a resumed
    run spawns the same builder."""
    job = read_job(root, job_id)
    if "escalated_from" not in job:
        if job["tier"] not in ESCALATION:
            return {"escalated": False, "tier": job["tier"]}
        chosen = resolve_model(root, host, tier=ESCALATION[job["tier"]])
        job["escalated_from"], job["tier"] = job["tier"], ESCALATION[job["tier"]]
        # The builder about to be spawned is the one the progress views should show, and the record keeps the earlier model.
        builder = job["agents"].get("builder", {})
        if seen := _models(builder, chosen["model"] or ""):
            builder["models"] = seen
        builder.update(model=chosen["model"] or builder.get("model", ""), effort=chosen["effort"] or "")
        job["agents"]["builder"] = builder
        write_job(root, job)
    chosen = resolve_model(root, host, tier=job["tier"])
    return {"escalated": True, "tier": job["tier"], "escalated_from": job["escalated_from"], "model": chosen["model"], "effort": chosen["effort"]}


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
            lines += 1
    return sorted(set(names)), lines


def fingerprints(job: dict, root) -> dict[str, str]:
    """Path to a short identity of its content, for every file the job's change touches."""
    cwd = job.get("worktree") or str(root)
    out: dict[str, str] = {}
    if job["mode"] == "current-branch":
        names = git(cwd, "diff", "--name-only", "-z", "--no-renames", "HEAD").split("\0") + git(cwd, "ls-files", "--others", "--exclude-standard", "-z").split("\0")
        for name in filter(None, names):
            f = Path(cwd) / name
            out[name] = hashlib.sha1(f.read_bytes()).hexdigest() if f.is_file() else "gone"
        return out
    raw = git(cwd, "diff", "--raw", "-z", "--no-abbrev", "--no-renames", f"{job['base']}...{job['branch']}").split("\0")
    for meta, name in zip(raw[0::2], raw[1::2]):
        out[name] = meta.split()[3]
    return out


def tree_state(job: dict, root) -> str:
    """Identity of the code a check runs against: the tree of HEAD plus anything uncommitted, so a new commit of the same code keeps it."""
    cwd = job.get("worktree") or str(root)
    parts = [git(cwd, "rev-parse", "HEAD^{tree}").strip(), git(cwd, "status", "--porcelain"), git(cwd, "diff", "HEAD"), json.dumps(sorted(fingerprints(job, root).items()))]
    return hashlib.sha1("\0".join(parts).encode()).hexdigest()[:16]


def build_patch(job: dict, root, paths: list[str], round_no: int, delta: set[str] | None) -> str:
    """The change as a reviewer reads it: commits, file list and diff in one file, so no agent runs the same git commands again."""
    cwd = job.get("worktree") or str(root)
    head = [f"# Job {job['id']}, round {round_no}", f"# Base {job['base']}, branch {job['branch']}, mode {job['mode']}"]
    if job["mode"] == "current-branch":
        diff = git(cwd, "diff", "HEAD")
        numstat = git(cwd, "diff", "--numstat", "HEAD")
        for extra in git(cwd, "ls-files", "--others", "--exclude-standard").split():
            diff += git(cwd, "diff", "--no-index", "--", "/dev/null", extra, ok=(0, 1))
            numstat += f"new\t-\t{extra}\n"
    else:
        span = f"{job['base']}...{job['branch']}"
        head.append("# Commits:")
        head += [f"#   {ln}" for ln in git(cwd, "log", "--oneline", f"{job['base']}..{job['branch']}").splitlines()]
        diff = git(cwd, "diff", span)
        numstat = git(cwd, "diff", "--numstat", span)
    head.append("# Files (added, removed, path):")
    head += [f"#   {ln.replace(chr(9), ' ')}" for ln in numstat.splitlines()]
    if delta is not None:
        head.append("# Changed since the previous round: " + (", ".join(sorted(delta)) or "nothing"))
    return "\n".join(head) + "\n\n" + diff


def _rules(root, table: str | None = None):
    """The routing table: the one given, else the repo's own `factory/routing.md`, else the plugin's."""
    default = Path(__file__).resolve().parent.parent / "routing.md"
    own = jobs_dir(root).parent / "routing.md"
    return load_rules(Path(table) if table else own if own.exists() else default)


LEAN_TIERS = ("light", "medium")
LONG_LEAN = 8


def _declared_paths(files: list[str]) -> list[str]:
    """The declared files that read as paths: the first word of each entry (the parser has dropped its backticks), when it has a
    slash or the shape of a file name (`package.json`, `.env`); a line range such as `:12-40` is dropped."""
    out = []
    for f in files:
        word = re.sub(r":\d+(-\d+)?$", "", f.strip().strip("`").split(" ")[0].strip("`,;"))
        if "/" in word or re.fullmatch(r"[\w.-]*\.[\w-]+", word):
            out.append(word)
    return out


def lean_eligibility(task, rules, adhoc: bool = False) -> tuple[bool, str]:
    """Whether the session may build the task itself, proved by its own checks, and if not, why. An ad hoc task declares no
    files, so for it only `lean-check`, on the real diff, judges the paths."""
    if task.tier not in LEAN_TIERS:
        return False, f"tier {task.tier}"
    paths = [] if "files" in task.defaults_applied else _declared_paths(task.files)
    if not paths and not adhoc:
        return False, "no Files"
    lenses = [lens for lens in route(paths, rules) if lens != "code"]
    if lenses:
        return False, "Files route to " + ", ".join(lenses)
    if "accept" in task.defaults_applied or not task.accept:
        return False, "no Accept"
    if "verify" in task.defaults_applied or not task.verify.strip():
        return False, "no Verify"
    return True, ""


def lean_check(root, job_id: str) -> dict:
    """The gate of a lean job, in place of review and approval: it lands when its change still needs only the code lens, it is
    not risky, and every Verify command's latest run is current and passed, with fewer than two failed runs. Otherwise the
    reason it goes to the full loop."""
    job = read_job(root, job_id)
    if not job.get("lean"):
        return {"land": False, "promote": "not a lean job"}
    if job["tier"] not in LEAN_TIERS:
        return {"land": False, "promote": f"tier {job['tier']}"}
    paths, _ = changed(job, root)
    if not paths:
        return {"land": False, "promote": "no change"}
    lenses = [lens for lens in route(paths, _rules(root)) if lens != "code"]
    if lenses:
        return {"land": False, "promote": "routes to " + ", ".join(lenses)}
    # Isolated mode lands the branch, so a check that passed on files left out of it proves nothing.
    if job["mode"] != "current-branch" and git(job.get("worktree") or str(root), "status", "--porcelain").strip():
        return {"land": False, "promote": "uncommitted changes"}
    commands = job.get("verify", [])
    if not commands:
        return {"land": False, "promote": "no Verify"}
    records = read_checks(root, job_id)
    runs = {cmd: [r for r in records if r["cmd"] == cmd] for cmd in commands}
    current = tree_state(job, root)
    for reason, failed in (
        ("checks failed twice", lambda rs: sum(1 for r in rs if r["exit"] != 0) >= 2),
        ("no recorded run", lambda rs: not rs),
        ("stale run", lambda rs: rs[-1]["state"] != current),
        ("failing run", lambda rs: rs[-1]["exit"] != 0),
    ):
        if cmd := next((c for c in commands if failed(runs[c])), None):
            return {"land": False, "promote": f"{reason}: {cmd}"}
    return {"land": True}


def promote(root, job_id: str, reason: str) -> dict:
    """A lean job goes to the full loop: it is routed, reviewed and approved as any job, the session's build included."""
    job = read_job(root, job_id)
    job.update(lean=False, promoted=reason)
    write_job(root, job)
    return {"id": job_id, "promoted": reason}


def route_job(root, job_id: str, table: str | None = None) -> dict:
    job = read_job(root, job_id)
    paths, lines = changed(job, root)
    prints = fingerprints(job, root)
    previous = job.get("fingerprints")
    delta = None if previous is None else {p for p in set(previous) | set(prints) if previous.get(p) != prints.get(p)}
    rules = _rules(root, table)
    reviewers = route(paths, rules)
    # The short path: the approver reviews the code itself, so one agent fewer. Never for a risky job.
    risky = "security" in reviewers or job["tier"] in ("heavy", "fable")
    lite = not risky and job["tier"] in ("light", "medium") and reviewers == ["code"]
    folder = jobs_dir(root) / job_id
    if lite:
        job["round"] += 1
        job.update(reviewers=["code"], reviews={"code": "pending"}, rerun=[], carried={}, lite=True, build_round=job["round"], fingerprints=prints)
        write_job(root, job)
        rnd = folder / f"round-{job['round']}"
        rnd.mkdir(exist_ok=True)
        patch = rnd / "diff.patch"
        patch.write_text(build_patch(job, root, paths, job["round"], delta))
        set_stage(root, job_id, "approve")
        return {"reviewers": ["code"], "rerun": [], "carried": {}, "lite": True, "paths": paths, "files": len(paths), "lines": lines, "diff": str(patch)}
    # A lens that passed keeps its verdict while nothing its rules watch has changed since that round. The code lens
    # watches every path, so it runs again whenever anything changed; a lens that asked for changes always runs again.
    touched = set(route(sorted(delta), rules)) if delta else set()
    carried = {
        lens: job.get("carried", {}).get(lens, job["round"])
        for lens in reviewers
        if previous is not None and job.get("reviews", {}).get(lens) == "PASS" and lens not in touched
    }
    rerun = [lens for lens in reviewers if lens not in carried]
    job["round"] += 1
    job.update(
        reviewers=reviewers, rerun=rerun, carried=carried, lite=False, build_round=job["round"], fingerprints=prints,
        reviews={lens: "PASS" if lens in carried else "pending" for lens in reviewers},
    )
    write_job(root, job)
    rnd = folder / f"round-{job['round']}"
    rnd.mkdir(exist_ok=True)
    patch = rnd / "diff.patch"
    patch.write_text(build_patch(job, root, paths, job["round"], delta))
    set_stage(root, job_id, "review")
    return {"reviewers": reviewers, "rerun": rerun, "carried": carried, "lite": False, "paths": paths, "files": len(paths), "lines": lines, "diff": str(patch)}


def check_verdicts(root, job_id: str) -> dict:
    job = read_job(root, job_id)
    rnd = jobs_dir(root) / job_id / f"round-{job['round']}"
    verdicts: dict[str, str] = {}
    missing: list[str] = []
    invalid: list[str] = []
    # On the short path the approver writes the code review, so it is read although no reviewer was spawned.
    for r in ["code"] if job.get("lite") else job.get("rerun", job["reviewers"]):
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
    all_pass = ok and all(job["reviews"].get(r) == "PASS" for r in job["reviewers"])
    return {"ok": ok, "verdicts": verdicts, "carried": job.get("carried", {}), "missing": missing, "invalid": invalid, "all_pass": all_pass}


# ---- checks: a command run once per tree state, so the reviewers and the approver read the result instead of running it again ----

TAIL_LINES = 30


def read_checks(root, job_id: str) -> list[dict]:
    try:
        return json.loads((jobs_dir(root) / job_id / "checks.json").read_text())
    except (OSError, json.JSONDecodeError):
        return []


def check_view(record: dict, current: str, reused: bool = False) -> dict:
    log = Path(record["log"])
    tail = log.read_text().splitlines()[-TAIL_LINES:] if log.exists() else []
    return {"n": record["n"], "cmd": record["cmd"], "exit": record["exit"], "state": record["state"], "current": record["state"] == current,
            "reused": reused, "at": record["at"], "ms": record["ms"], "log": record["log"], "tail": tail}


def run_check(root, job_id: str, cmd: str, reuse: bool = False, timeout: int = 1800) -> dict:
    """Run a command in the job's checkout and record its exit code, log and the tree state it ran against. With `reuse`, a
    record of the same command for the same tree state is returned instead of running it again."""
    job = read_job(root, job_id)
    state_now = tree_state(job, root)
    records = read_checks(root, job_id)
    if reuse:
        for r in reversed(records):
            if r["cmd"] == cmd and r["state"] == state_now:
                return check_view(r, state_now, reused=True)
    n = len(records) + 1
    folder = jobs_dir(root) / job_id / "checks"
    folder.mkdir(exist_ok=True)
    started = time.monotonic()
    try:
        done = subprocess.run(cmd, shell=True, cwd=job.get("worktree") or str(root), capture_output=True, text=True, timeout=timeout)
        code, out = done.returncode, done.stdout + done.stderr
    except subprocess.TimeoutExpired as e:
        code, out = 124, f"timed out after {timeout}s\n" + "".join(x if isinstance(x, str) else x.decode(errors="replace") for x in (e.stdout, e.stderr) if x)
    log = folder / f"{n}.log"
    log.write_text(out)
    record = {"n": n, "cmd": cmd, "exit": code, "state": state_now, "at": now(), "ms": int((time.monotonic() - started) * 1000), "log": str(log)}
    (jobs_dir(root) / job_id / "checks.json").write_text(json.dumps([*records, record], indent=2))
    touch_lock(root, job.get("plan", ""))
    return check_view(record, state_now)


def list_checks(root, job_id: str) -> list[dict]:
    job = read_job(root, job_id)
    state_now = tree_state(job, root)
    return [check_view(r, state_now) for r in read_checks(root, job_id)]


def run_path(root, plan_stem: str) -> Path:
    return jobs_dir(root) / "_runs" / f"{plan_stem}.json"


def landed_count(root, plan_stem: str) -> int:
    done = set()
    for f in jobs_dir(root).glob("*/job.json"):
        j = json.loads(f.read_text())
        if j.get("plan") == plan_stem and j.get("stage") in TERMINAL:
            done.add(j.get("task"))
    return len(done)


def write_run(root, plan_file: str, mode: str, pace: str = "step", cross: str | None = None, host: str | None = None) -> dict:
    """The run state. `cross` ("on" or "off", asked at the start) records whether agents may go to the host's peer vendor, with the
    settings of models.json, and drops the vendor-down marks that lasted the run (`off`, exhausted to the end of the run) or have
    passed; without it what an earlier start recorded stays, `vendors` included."""
    root = Path(root)
    path = Path(plan_file) if Path(plan_file).is_absolute() else root / plan_file
    plan = parse_plan(path.read_text())
    rp = run_path(root, path.stem)
    existed = rp.exists()
    run = json.loads(rp.read_text()) if existed else {}
    run.update(
        plan=path.stem, path=plan_file, mode=mode, pace=pace, integration=run.get("integration"), total=len(plan.tasks),
        # Only a new run records where it starts: a run resumed from before `base` existed would get a later commit.
        base=run.get("base") if existed else git(root, "rev-parse", "HEAD").strip() or None,
        done=landed_count(root, path.stem),
        tasks=[{"n": t.number, "title": t.title, "tier": t.tier, "after": t.depends} for t in plan.tasks],
    )
    if cross is not None:
        if cross not in ("on", "off"):
            raise ValueError(f"cross is on or off, not {cross!r}")
        if not host:
            raise ValueError("--cross needs --host")
        run["cross"] = {"on": cross == "on" and host in PEER, "peer": PEER.get(host), **cross_config(root)}
        run["vendors"] = carried_marks(run.get("vendors") or {}, now())
    rp.parent.mkdir(parents=True, exist_ok=True)
    rp.write_text(json.dumps(run, indent=2))
    return run


FINDING = re.compile(r"^\s*\d+[.)]\s", re.M)


def _section(text: str, title: str) -> str:
    """The body of a `## <title>` section, up to the next `## ` heading."""
    return re.split(r"^## ", text.partition(f"## {title}")[2], maxsplit=1, flags=re.M)[0]


def _commit(root, ref: str) -> str:
    return git(root, "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}", ok=(0, 1)).strip()


def _main_branch(root) -> str:
    """The repo's main branch, which an integration branch is created from: the remote's default, else `main` or `master`."""
    remote = git(root, "symbolic-ref", "--quiet", "--short", "refs/remotes/origin/HEAD", ok=(0, 1)).strip()
    for ref in (remote.removeprefix("origin/"), remote, "main", "master"):
        if ref and _commit(root, ref):
            return ref
    return ""


def final_diff(root, plan_stem: str, fix: bool = False) -> dict:
    """The change of the whole run as the final reviewer reads it, in one file. Isolated: from where the integration branch
    left the repo to its tip; current branch: from the commit the run started on to HEAD. With `fix`, from the head the first
    review read, so the second sees only the fix. `risky` says whether any job of the run was."""
    root = Path(root)
    rp = run_path(root, plan_stem)
    if not rp.exists():
        return {"ok": False, "reason": f"no run state for {plan_stem}"}
    run = json.loads(rp.read_text())
    if not run.get("base"):
        return {"ok": False, "reason": "the run state has no base: the run started before the final review existed"}
    final = run.get("final", {})
    key = "fix_" if fix else ""
    patch = rp.parent / f"{plan_stem}-final{'-2' if fix else ''}.patch"
    jobs = _plan_jobs(root, plan_stem)
    risky = any("security" in j.get("reviewers", []) or j.get("tier") in ("heavy", "fable") for j in jobs)
    lean = sum(1 for j in jobs if j.get("lean"))
    # A resumed completion asks again: the span the review was given stays the one on record.
    if final.get(f"{key}head") and patch.exists():
        return {"ok": True, "patch": str(patch), "base": final.get(f"{key}base"), "head": final[f"{key}head"],
                "commits": final.get(f"{key}commits", 0), "risky": risky, "reused": True, "lean": lean}
    if run.get("mode") == "isolated":
        branch = run.get("integration") or f"factory/{plan_stem}"
        tip = _commit(root, branch)
        if not tip:
            return {"ok": False, "reason": f"integration branch {branch} not found"}
        start = git(root, "merge-base", tip, _main_branch(root) or run["base"]).strip()
        if not start:
            return {"ok": False, "reason": f"integration branch {branch} shares no history with the main branch"}
    else:
        tip, start = git(root, "rev-parse", "HEAD").strip(), run["base"]
    if fix:
        if not final.get("head"):
            return {"ok": False, "reason": "no first final review to start the fix from"}
        start = final["head"]
    span = f"{start}..{tip}"
    commits = git(root, "log", "--oneline", span).splitlines()
    if fix and not commits:
        return {"ok": False, "reason": "no commit since the first final review: the fix has not landed on the run's branch"}
    numstat = git(root, "diff", "--numstat", span)
    lines = [f"# Plan {plan_stem}, final review" + (" of the fix" if fix else ""), f"# Base {start}, head {tip}, mode {run.get('mode')}", "# Commits:"]
    lines += [f"#   {c}" for c in commits]
    lines.append("# Files (added, removed, path):")
    lines += [f"#   {ln.replace(chr(9), ' ')}" for ln in numstat.splitlines()]
    patch.write_text("\n".join(lines) + "\n\n" + git(root, "diff", span))
    final.update({f"{key}head": tip, f"{key}base": start, f"{key}commits": len(commits)})
    run["final"] = final
    rp.write_text(json.dumps(run, indent=2))
    return {"ok": True, "patch": str(patch), "base": start, "head": tip, "commits": len(commits), "risky": risky, "reused": False, "lean": lean}


def final_verdict(root, plan_stem: str, fix: bool, agent: dict, fix_job: str | None = None) -> dict:
    """Read the verdict of a final review and keep it in the run state with its findings count and the agent's usage."""
    rp = run_path(root, plan_stem)
    f = rp.parent / f"{plan_stem}-final{'-2' if fix else ''}.md"
    if not rp.exists() or not f.exists():
        return {"ok": False, "reason": f"{f.name} is missing"}
    text = f.read_text()
    first = (text.splitlines() or [""])[0].strip()
    verdict = first.removeprefix("VERDICT: ") if first.startswith("VERDICT: ") else ""
    if verdict not in VERDICTS:
        return {"ok": False, "reason": f"{f.name} has no verdict line"}
    findings = len(FINDING.findall(_section(text, "Findings")))
    run = json.loads(rp.read_text())
    final = run.setdefault("final", {})
    final["recheck" if fix else "review"] = {"verdict": verdict, "findings": findings, "agent": agent}
    if fix_job:
        final["fix_job"] = fix_job
    rp.write_text(json.dumps(run, indent=2))
    return {"ok": True, "verdict": verdict, "findings": findings}


def read_run(root, plan_stem: str) -> dict:
    try:
        return json.loads(run_path(root, plan_stem).read_text())
    except (OSError, json.JSONDecodeError):
        return {}


def vendor(root, job_id: str | None, agent: str, host: str, plan_stem: str | None = None, risky: bool = False) -> dict:
    """Which vendor runs an agent, with the model and effort to pass it, recorded where the execution record reads it: the job
    (`vendors[agent]`, and `crossed: false` when a review stayed on the builder's vendor) or, for reviewer-final, the run state."""
    try:
        job = read_job(root, job_id) if job_id else None
    except (OSError, ValueError) as e:
        raise ValueError(f"no readable job {job_id}") from e
    stem = job["plan"] if job else plan_stem
    if agent == "builder" and not job:
        raise ValueError("the builder needs a job")
    if agent == "reviewer-final" and not stem:
        raise ValueError("reviewer-final needs --plan")
    run = read_run(root, stem) if stem else {}
    cross = run.get("cross") or {}
    usage = {v: read_quota(root, v)["used_percent"] for v in (host, PEER.get(host)) if v in PEER} if cross.get("on") else {}
    out = decide(job, run, agent, host, usage, now())
    if out["vendor"] is None:
        return {**out, "model": None, "effort": None}
    chosen = resolve_model(root, out["vendor"], tier=job["tier"]) if agent == "builder" else resolve_model(
        root, out["vendor"], agent=agent, risky=risky and agent in RISKY_AGENTS)
    record = {"vendor": out["vendor"], "reason": out["reason"]}
    if agent == "reviewer-final":
        final = run.setdefault("final", {})
        final["vendor"] = record
        if not out["crossed"] and cross.get("on"):
            final["crossed"] = False
        run_path(root, stem).write_text(json.dumps(run, indent=2))
    elif job:
        job.setdefault("vendors", {})[agent] = record
        if out["reason"] == "not crossed":
            job["crossed"] = False
        write_job(root, job)
    return {**out, "model": chosen["model"], "effort": chosen["effort"]}


def vendor_down(root, plan_stem: str, vendor: str, reason: str, until: str | None = None) -> dict:
    """Record in the run state that a vendor cannot take agents: `limit` until `until` (ISO, or epoch seconds as Codex's
    `resets_at`; to the end of the run without it), `missing` and `auth` for the rest of the run."""
    if reason not in ("limit", "missing", "auth"):
        raise ValueError(f"reason is limit, missing or auth, not {reason!r}")
    if vendor not in PEER:
        raise ValueError(f"vendor is claude or codex, not {vendor!r}")
    rp = run_path(root, plan_stem)
    if not rp.exists():
        raise ValueError(f"no run state for {plan_stem}")
    if until is not None:
        try:
            until = iso(float(until)) if re.fullmatch(r"\d+(\.\d+)?", str(until)) else parse_iso(until).strftime("%Y-%m-%dT%H:%M:%SZ")
        except (ValueError, OverflowError, OSError) as e:
            raise ValueError(f"--until {until!r} is not an ISO 8601 time or an epoch") from e
    run = json.loads(rp.read_text())
    entry = run.setdefault("vendors", {}).setdefault(vendor, {})
    if reason == "limit":
        entry["exhausted_until"] = until or END_OF_RUN
    else:
        entry["off"] = True
    rp.write_text(json.dumps(run, indent=2))
    return {"vendor": vendor, **entry}


def land_job(root, job_id: str, stage: str, head: str) -> dict:
    before = read_job(root, job_id)
    if reason := _landing_concern_problem(root, before):
        raise ValueError(reason)
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
    """Best effort: an agent that may not write `_runs` (a Codex peer in its sandbox) still records its checks and its job."""
    lock = read_lock(root, plan_stem) if plan_stem else None
    if lock:
        lock["heartbeat"] = now()
        try:
            lock_path(root, plan_stem).write_text(json.dumps(lock, indent=2))
        except OSError:
            pass


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


def _plan_path(root, plan_file: str) -> Path:
    return Path(plan_file) if Path(plan_file).is_absolute() else Path(root) / plan_file


def _write_plan(path: Path, text: str) -> None:
    """Write a plan that the run lock keeps read-only, and leave it read-only."""
    mode = stat.S_IMODE(path.stat().st_mode)
    path.chmod(mode | 0o200)
    try:
        path.write_text(text)
    finally:
        path.chmod(mode)


def tick_plan(root, plan_file: str, task: int | None = None) -> dict:
    """Tick the open steps of every task a job has landed, and of `task` when given, so that the tick can travel in the
    commit that lands the task. Never closes the plan: that is `close_plan`. Works on a read-only plan and leaves it
    read-only."""
    root = Path(root)
    path = _plan_path(root, plan_file)
    landed = set() if task is None else {task}
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
        elif not in_fence and not TASK_HEADING.match(line) and SECTION.match(line):
            current = None  # a `##` section that is not a task is no task's work, so its boxes are never ticked
        elif not in_fence and current in landed and re.match(r"^\s*[-*] \[ \]", line):
            line = line.replace("[ ]", "[x]", 1)
            ticked += 1
        out.append(line)
    if ticked:
        _write_plan(path, "".join(out))
    return {"ok": True, "ticked": ticked}


def close_plan(root, plan_file: str) -> dict:
    """Tick what has landed, then, when every checklist of the plan is resolved, declare it completed in the front
    matter and append one `## Delivery status` section: the documentation that describes the work now, the divergences
    from the plan, and the execution record. Closing twice writes nothing the second time."""
    ticked = tick_plan(root, plan_file)["ticked"]
    path = _plan_path(root, plan_file)
    text = path.read_text()
    plan = parse_plan(text)
    stepped = [b for b in plan.blocks if b.steps]
    if not stepped or not all(b.done for b in stepped) or plan.status in CLOSED:
        return {"ok": True, "ticked": ticked, "closed": False}
    text = close_header(text)
    docs = list(dict.fromkeys(d for t in plan.tasks for d in t.docs))
    if DELIVERY_TITLE not in text and RECORD_TITLE not in text:
        text = text.rstrip("\n") + "\n\n" + delivery_status(root, path.stem, plan, docs)
    _write_plan(path, text)
    return {"ok": True, "ticked": ticked, "closed": True, "documented_in": docs}


DELIVERY_TITLE = "## Delivery status"
RECORD_TITLE = "### Execution record"  # older plans carry it as a `##` section, which this also matches


def _plan_jobs(root, plan_stem: str) -> list[dict]:
    jobs = []
    for f in sorted(jobs_dir(root).glob("*/job.json")):
        j = json.loads(f.read_text())
        if j.get("plan") == plan_stem:
            jobs.append(j)
    return jobs


def _findings(folder: Path, reviewed: bool) -> str:
    """Numbered items under `## Issues` per round and lens, e.g. `r1 code 2, r1 ui 0, r2 code 0`; `short path` when the job had no reviewers, `-` when it had but left no files."""
    found = []
    for f in folder.glob("round-*/review-*.md"):
        n, lens = int(f.parent.name.split("-", 1)[1]), f.stem.removeprefix("review-")
        body = re.split(r"^## ", f.read_text().partition("## Issues")[2], maxsplit=1, flags=re.M)[0]
        found.append((n, lens, len(re.findall(r"^\s*\d+[.)]\s", body, re.M))))
    return ", ".join(f"r{n} {lens} {c}" for n, lens, c in sorted(found)) or ("-" if reviewed else "short path")


def _first_round(folder: Path) -> str:
    """The verdicts the first round's reviews opened with, like `code CHANGES, ui PASS`; empty for a job without them."""
    found = []
    for f in sorted(folder.glob("round-1/review-*.md")):
        first = (f.read_text().splitlines() or [""])[0].strip()
        if first.startswith("VERDICT: ") and first.removeprefix("VERDICT: ") in VERDICTS:
            found.append(f"{f.stem.removeprefix('review-')} {first.removeprefix('VERDICT: ')}")
    return ", ".join(found)


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
        verdicts = ", ".join(f"{k} {v}" for k, v in j.get("reviews", {}).items()) or ("lean" if j.get("lean") else "short path")
        decision = ""
        if (folder / "decision.md").exists():
            decision = (folder / "decision.md").read_text().splitlines()[0].strip()
        notes = ["short path"] if j.get("lite") else []
        if j.get("lean"):
            notes.append("lean")
        if j.get("promoted"):
            notes.append(f"promoted: {j['promoted']}")
        if n := len(list(folder.glob("rework-*.md"))):
            notes.append(f"reworked {n}x")
        if n := len(list(folder.glob("answers-*.md"))):
            notes.append(f"{n} answered question(s)")
        findings = _findings(folder, bool(j.get("reviews")))
        models = "/".join(sorted({f"{a['vendor']}:{m}" if a.get("vendor") else m for a in agents.values() for m in [a.get("model", ""), *a.get("models", [])] if m}))
        if j.get("crossed") is False:
            notes.append("review not crossed")
        tier = f"{j['escalated_from']}→{j.get('tier', '')}" if j.get("escalated_from") else j.get("tier", "")
        rows.append(f"| {j.get('task')} | {tier} | {models} | {j.get('round', 1)} | {_first_round(folder)} | {verdicts} | {decision} | {findings} | {'; '.join(notes)} | {t} | {m // 1000}s |")
    final = _final_run(root, plan_stem)
    reviews = [final[k] for k in ("review", "recheck") if k in final]
    if reviews:
        usage = [r.get("agent", {}) for r in reviews]
        t, m = sum(int(a.get("tokens", 0)) for a in usage), sum(int(a.get("ms", 0)) for a in usage)
        tokens, ms = tokens + t, ms + m
        prefix = f"{v}:" if (v := (final.get("vendor") or {}).get("vendor")) else ""
        models = "/".join(sorted({prefix + a["model"] for a in usage if a.get("model")}))
        notes = "review not crossed" if final.get("crossed") is False else ""
        rows.append(f"| final | | {models} | {len(reviews)} | | {', '.join(r['verdict'] for r in reviews)} | | | {notes} | {t} | {m // 1000}s |")
    head = "| Task | Tier | Models | Rounds | First round | Reviews | Decision | Findings | Notes | Tokens | Agent time |\n|---|---|---|---|---|---|---|---|---|---|---|\n"
    return f"{RECORD_TITLE}\n\n{head}" + "\n".join(rows) + f"\n\nTotal: {tokens} tokens, {ms // 1000}s of agent time.\n"


def _final_run(root, plan_stem: str) -> dict:
    """The final review part of the run state, empty when the run had none."""
    try:
        return json.loads(run_path(root, plan_stem).read_text()).get("final", {})
    except (OSError, json.JSONDecodeError):
        return {}


def final_section(root, plan_stem: str) -> str:
    """`### Final review` of the Delivery status: the first verdict, the fix job, and what the last review left open. Empty
    when the run had no final review."""
    final = _final_run(root, plan_stem)
    if "review" not in final:
        return ""
    first = final["review"]
    lines = [f"First review: {first['verdict']}, {first['findings']} finding(s)."]
    if final.get("fix_job"):
        lines.append(f"Fix: job {final['fix_job']}.")
    last, name = (final["recheck"], f"{plan_stem}-final-2.md") if "recheck" in final else (first, f"{plan_stem}-final.md")
    open_items = []
    if last["verdict"] == "CHANGES":
        try:
            body = _section((run_path(root, plan_stem).parent / name).read_text(), "Findings")
            open_items = [ln.strip() for ln in body.splitlines() if FINDING.match(ln)]
        except OSError:
            open_items = [f"{last['findings']} finding(s), file {name} not found"]
    left = "\n\nLeft open:\n\n" + "\n".join(open_items) if open_items else "\n\nLeft open: none."
    return "### Final review\n\n" + "\n".join(lines) + left + "\n"


def _deviations(build: Path) -> list[str]:
    """The items of the `## Deviations` section of a build.md, one line each; `None.` and blank lines are no items.
    Checkbox marks are dropped, so plan tools never count a divergence as a step."""
    if not build.exists():
        return []
    body = re.split(r"^## ", build.read_text().partition("\n## Deviations")[2], maxsplit=1, flags=re.M)[0]
    items = []
    for line in body.splitlines()[1:]:  # the first line is the rest of the heading
        item = re.sub(r"^\s*(?:[-*]|\d+[.)])\s+(?:\[[ xX-]\]\s*)?", "", line).strip()
        if item and not re.fullmatch(r"none\.?", item, re.I):
            items.append(item)
    return items


def divergences(root, plan_stem: str, plan) -> list[str]:
    """What the run did differently from the plan: each landed job's `## Deviations`, then every cancelled step with
    the reason written next to it."""
    found = []
    for j in _plan_jobs(root, plan_stem):
        if j.get("stage") in TERMINAL:
            found += [f"Task {j.get('task')}: {item}" for item in _deviations(jobs_dir(root) / j["id"] / "build.md")]
    for t in plan.tasks:
        found += [f"Task {t.number}: step cancelled: {s.text}" for s in t.steps if s.state == "cancelled"]
    return found


def delivery_status(root, plan_stem: str, plan, docs: list[str]) -> str:
    """The closing section of a plan, written once by `close_plan`. Without checkboxes, so plan tools do not read it
    as work. `Documented in` names the documentation the tasks declared, which is where the behaviour lives now: the
    plan stays as the dated record of what was decided and what was deliberately not built."""
    day = datetime.now(timezone.utc).date().isoformat()
    documented = ", ".join(f"`{d}`" for d in docs) if docs else "none, no task names documentation"
    items = divergences(root, plan_stem, plan)
    listed = "\n".join(f"- {i}" for i in items) if items else "None recorded."
    final = final_section(root, plan_stem)
    return (f"{DELIVERY_TITLE} ({day}): delivered by clay run\n\n**Documented in:** {documented}\n\n"
            f"### Divergences\n\n{listed}\n\n" + (f"{final}\n" if final else "") + execution_record(root, plan_stem))


def clean_jobs(root, plan_stem: str) -> dict:
    """Remove the local job folders and run state of a finished plan. Refuses while any job of the plan is not landed."""
    jobs = _plan_jobs(root, plan_stem)
    waiting = [j["id"] for j in jobs if j.get("stage") not in TERMINAL]
    if waiting:
        return {"ok": False, "reason": "jobs not landed: " + ", ".join(waiting), "removed": []}
    for j in jobs:
        shutil.rmtree(jobs_dir(root) / j["id"], ignore_errors=True)
    (jobs_dir(root) / "_runs" / f"{plan_stem}.md").unlink(missing_ok=True)  # the working plan of an ad hoc task; unlinking needs no write permission on the file
    for f in (jobs_dir(root) / "_runs").glob(f"{glob_escape(plan_stem)}-final*"):
        f.unlink(missing_ok=True)
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
    tp.add_argument("--task", type=int)
    cp = sub.add_parser("close-plan")
    cp.add_argument("--root", default=".")
    cp.add_argument("--plan-file", required=True)
    ah = sub.add_parser("adhoc")
    ah.add_argument("--root", default=".")
    ah.add_argument("--text", required=True)
    md = sub.add_parser("model")
    md.add_argument("--root", default=".")
    md.add_argument("--host", required=True)
    md.add_argument("--tier")
    md.add_argument("--agent")
    md.add_argument("--risky", action="store_true")
    vd = sub.add_parser("vendor")
    vd.add_argument("job", nargs="?")
    vd.add_argument("--root", default=".")
    vd.add_argument("--agent", required=True)
    vd.add_argument("--host", required=True)
    vd.add_argument("--plan")
    vd.add_argument("--risky", action="store_true")
    qt = sub.add_parser("quota")
    qt.add_argument("--root", default=".")
    qt.add_argument("--vendor", required=True, choices=sorted(PEER))
    vn = sub.add_parser("vendor-down")
    vn.add_argument("--root", default=".")
    vn.add_argument("--plan", required=True)
    vn.add_argument("--vendor", required=True)
    vn.add_argument("--reason", required=True)
    vn.add_argument("--until")
    es = sub.add_parser("escalate")
    es.add_argument("job")
    es.add_argument("--root", default=".")
    es.add_argument("--host", required=True)
    fd = sub.add_parser("final-diff")
    fd.add_argument("--root", default=".")
    fd.add_argument("--plan", required=True)
    fd.add_argument("--fix", action="store_true")
    fv = sub.add_parser("final-verdict")
    fv.add_argument("--root", default=".")
    fv.add_argument("--plan", required=True)
    fv.add_argument("--fix", action="store_true")
    fv.add_argument("--fix-job")
    fv.add_argument("--agent", required=True, help='JSON {"model","effort","tokens","ms","tools"}')
    cl = sub.add_parser("clean")
    cl.add_argument("--root", default=".")
    cl.add_argument("--plan", required=True)
    oj = sub.add_parser("open-job")
    oj.add_argument("--root", default=".")
    for opt in ("--plan-file", "--repo-name", "--mode"):
        oj.add_argument(opt, required=True)
    oj.add_argument("--task", type=int, required=True)
    oj.add_argument("--lean", action="store_true")
    mj = sub.add_parser("merge-job")
    mj.add_argument("--root", default=".")
    mj.add_argument("job")
    for action in ("concern", "resolve-concern"):
        cn = sub.add_parser(action)
        cn.add_argument("--root", default=".")
        cn.add_argument("job")
    for name in ("setup", "run", "preflight", "new-job", "begin-job", "stage", "agent", "after-agent", "route", "verdicts", "land", "verify", "checks", "rework", "lean-check", "promote"):
        sp = sub.add_parser(name)
        sp.add_argument("--root", default=".")
        if name in ("stage", "agent", "after-agent", "route", "verdicts", "land", "verify", "checks", "rework", "lean-check", "promote"):
            sp.add_argument("job")
        if name == "promote":
            sp.add_argument("--reason", required=True)
        if name == "after-agent":
            sp.add_argument("--agents", required=True, help='JSON list of {"role","model","effort","tokens","ms","tools","vendor","session_id"}')
        if name == "preflight":
            sp.add_argument("--plan-file")
            sp.add_argument("--repo-name", default="")
            sp.add_argument("--host")
        if name == "verify":
            sp.add_argument("--cmd", dest="check_cmd", required=True)
            sp.add_argument("--reuse", action="store_true")
            sp.add_argument("--timeout", type=int, default=1800)
        if name == "setup":
            sp.add_argument("--plugin-root", required=True)
        if name in ("run", "new-job", "begin-job"):
            sp.add_argument("--plan-file", required=True)
            sp.add_argument("--mode", required=True)
        if name == "run":
            sp.add_argument("--pace", default="step")
            sp.add_argument("--cross", choices=("on", "off"))
            sp.add_argument("--host")
        if name in ("new-job", "begin-job"):
            sp.add_argument("--task", type=int, required=True)
            sp.add_argument("--repo-name", required=True)
            sp.add_argument("--branch", required=True)
            sp.add_argument("--worktree", required=True)
            sp.add_argument("--base")
            sp.add_argument("--lean", action="store_true")
        if name == "stage":
            sp.add_argument("stage_name")
        if name == "agent":
            sp.add_argument("role")
            for opt in ("--model", "--effort", "--vendor", "--session-id"):
                sp.add_argument(opt, default="")
            for opt in ("--tokens", "--ms", "--tools"):
                sp.add_argument(opt, type=int, default=0)
        if name == "route":
            sp.add_argument("--table")
        if name == "land":
            sp.add_argument("--stage", dest="to_stage", default="committed")
            sp.add_argument("--head", required=True)
    a = ap.parse_args(argv)
    if a.cmd in ("open-job", "merge-job", "concern", "resolve-concern"):
        if a.cmd == "open-job":
            out = open_job(a.root, a.plan_file, a.task, a.repo_name, a.mode, a.lean)
        elif a.cmd == "merge-job":
            out = merge_job(a.root, a.job)
        elif a.cmd == "concern":
            out = concern(a.root, a.job)
        else:
            out = resolve_concern(a.root, a.job)
        print(json.dumps(out, indent=2))
        return 0 if out["ok"] else 1
    if a.cmd == "clean":
        out = clean_jobs(a.root, a.plan)
        print(json.dumps(out, indent=2))
        return 0 if out["ok"] else 1
    if a.cmd == "adhoc":
        try:
            print(json.dumps(adhoc_plan(a.root, a.text), indent=2))
        except ValueError as e:
            print(f"state.py adhoc: {e}", file=sys.stderr)
            return 2
        return 0
    if a.cmd == "model":
        try:
            print(json.dumps(resolve_model(a.root, a.host, a.tier, a.agent, a.risky), indent=2))
        except ModelsError as e:
            print(json.dumps({"error": str(e)}))
            return 2
        return 0
    if a.cmd in ("final-diff", "final-verdict"):
        if a.cmd == "final-diff":
            out = final_diff(a.root, a.plan, a.fix)
        else:
            try:
                usage = json.loads(a.agent)
            except ValueError as e:
                print(json.dumps({"error": f"--agent is not valid JSON ({e})"}))
                return 2
            out = final_verdict(a.root, a.plan, a.fix, usage, a.fix_job)
        print(json.dumps(out, indent=2))
        return 0 if out["ok"] else 1
    if a.cmd in ("vendor", "vendor-down", "quota"):
        try:
            if a.cmd == "vendor":
                out = vendor(a.root, a.job, a.agent, a.host, a.plan, a.risky)
            elif a.cmd == "vendor-down":
                out = vendor_down(a.root, a.plan, a.vendor, a.reason, a.until)
            else:
                out = read_quota(a.root, a.vendor)
        except (ValueError, ModelsError) as e:
            print(json.dumps({"error": str(e)}))
            return 2
        print(json.dumps(out, indent=2))
        return 0
    if a.cmd == "escalate":
        try:
            print(json.dumps(escalate(a.root, a.job, a.host), indent=2))
        except ModelsError as e:
            print(json.dumps({"error": str(e)}))
            return 2
        return 0
    if a.cmd == "tick-plan":
        print(json.dumps(tick_plan(a.root, a.plan_file, a.task), indent=2))
        return 0
    if a.cmd == "close-plan":
        print(json.dumps(close_plan(a.root, a.plan_file), indent=2))
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
        try:
            out = write_run(a.root, a.plan_file, a.mode, a.pace, a.cross, a.host)
        except (ValueError, ModelsError) as e:
            print(json.dumps({"error": str(e)}))
            return 2
    elif a.cmd == "preflight":
        out = preflight(a.root, a.plan_file, a.repo_name, a.host)
    elif a.cmd == "new-job":
        out = new_job(a.root, a.plan_file, a.task, a.repo_name, a.mode, a.branch, a.worktree, a.base, a.lean)
    elif a.cmd == "begin-job":
        out = begin_job(a.root, a.plan_file, a.task, a.repo_name, a.mode, a.branch, a.worktree, a.base, a.lean)
    elif a.cmd == "lean-check":
        out = lean_check(a.root, a.job)
    elif a.cmd == "promote":
        out = promote(a.root, a.job, a.reason)
    elif a.cmd == "rework":
        out = rework(a.root, a.job)
    elif a.cmd == "after-agent":
        out = record_agents(a.root, a.job, json.loads(a.agents))
    elif a.cmd == "stage":
        out = {"id": a.job, "stage": set_stage(a.root, a.job, a.stage_name)["stage"]}
    elif a.cmd == "agent":
        out = record_agent(a.root, a.job, a.role, a.model, a.effort, a.tokens, a.ms, a.tools, a.vendor, a.session_id)
    elif a.cmd == "route":
        out = route_job(a.root, a.job, a.table)
    elif a.cmd == "verdicts":
        out = check_verdicts(a.root, a.job)
    elif a.cmd == "verify":
        out = run_check(a.root, a.job, a.check_cmd, a.reuse, a.timeout)
    elif a.cmd == "checks":
        out = list_checks(a.root, a.job)
    else:
        try:
            out = {"id": a.job, "stage": land_job(a.root, a.job, a.to_stage, a.head)["stage"]}
        except ValueError as e:
            print(json.dumps({"ok": False, "reason": str(e)}))
            return 1
    print(json.dumps(out, indent=2))
    if a.cmd == "verdicts" and not out["ok"]:
        return 1
    return 1 if a.cmd == "verify" and out["exit"] != 0 else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
