import json
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugins/clay/scripts"))
import models  # noqa: E402
import resolve  # noqa: E402
import state  # noqa: E402

PLAN = """# Demo plan

**Spec:** none

### Task 1: Add slugify helper

**Repo:** demo
**Tier:** light
**Files:** `app/util.py`
**Accept:** 1. Works.

- [ ] **Step 1: Write the failing test**
- [ ] **Step 2: Implement**

### Task 2: Extend the session lifetime

**Tier:** careful
**Depends:** 1
**Files:** `app/auth/session.py`

- [ ] **Step 1: Do it**
"""


def git(root, *args):
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *args], cwd=root, check=True, capture_output=True)


@pytest.fixture
def repo(tmp_path):
    git(tmp_path, "init", "-q", "-b", "main")
    (tmp_path / "app/auth").mkdir(parents=True)
    (tmp_path / "app/util.py").write_text("x = 1\n")
    (tmp_path / "app/auth/session.py").write_text("N = 30\n")
    plans = tmp_path / "docs/superpowers/plans"
    plans.mkdir(parents=True)
    (plans / "2026-01-01-demo.md").write_text(PLAN)
    git(tmp_path, "add", "-A")
    git(tmp_path, "commit", "-q", "-m", "init")
    return tmp_path


def new(repo, task=1):
    return state.new_job(repo, "docs/superpowers/plans/2026-01-01-demo.md", task, repo_name="demo", mode="current-branch", branch="main", worktree=str(repo))


def test_setup_creates_the_state_folder_ignored_by_git(repo, tmp_path):
    plugin = tmp_path / "plugin/factory"
    plugin.mkdir(parents=True)
    (plugin / "dashboard.html").write_text("<html>")
    state.setup(repo, plugin.parent)
    assert (repo / "factory/jobs/.gitignore").read_text().strip() == "*"
    assert (repo / "factory/jobs/dashboard.html").read_text() == "<html>"
    git(repo, "status", "--porcelain")
    out = subprocess.run(["git", "status", "--porcelain"], cwd=repo, capture_output=True, text=True).stdout
    assert "factory" not in out


def test_new_job_claims_the_next_id_and_writes_the_brief(repo):
    state.setup(repo, repo)
    a = new(repo, 1)
    b = new(repo, 2)
    assert (a["id"], b["id"]) == ("001-add-slugify-helper", "002-extend-session-lifetime")
    brief = (repo / "factory/jobs/001-add-slugify-helper/task.md").read_text()
    assert "# Task 1: Add slugify helper" in brief and "**Tier:** light" in brief and "Write the failing test" in brief
    job = json.loads((repo / "factory/jobs/001-add-slugify-helper/job.json").read_text())
    assert job["stage"] == "spec" and job["tier"] == "light" and job["task"] == 1 and job["plan"] == "2026-01-01-demo"
    assert job["base"] == subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True).stdout.strip()


def test_stage_changes_keep_a_phase_log_with_closed_phases(repo):
    state.setup(repo, repo)
    j = new(repo)
    state.set_stage(repo, j["id"], "build")
    state.set_stage(repo, j["id"], "review")
    job = state.read_job(repo, j["id"])
    stages = [p["stage"] for p in job["phases"]]
    assert stages == ["spec", "build", "review"]
    assert job["phases"][0]["end"] and job["phases"][1]["end"] and job["phases"][2]["end"] is None
    state.set_stage(repo, j["id"], "committed")
    assert state.read_job(repo, j["id"])["phases"][-1]["end"]


def test_record_agent_accumulates_tokens_and_time_per_role(repo):
    state.setup(repo, repo)
    j = new(repo)
    state.record_agent(repo, j["id"], "builder", model="opus", effort="", tokens=14000, ms=27000, tools=6)
    state.record_agent(repo, j["id"], "builder", model="opus", effort="", tokens=20000, ms=60000, tools=10)
    a = state.read_job(repo, j["id"])["agents"]["builder"]
    assert (a["tokens"], a["ms"], a["tools"], a["runs"]) == (34000, 87000, 16, 2)


def test_route_uses_the_changed_files_and_sets_up_the_round(repo):
    state.setup(repo, repo)
    j = new(repo, 2)
    (repo / "app/auth/session.py").write_text("N = 60\n")
    out = state.route_job(repo, j["id"])
    assert out["reviewers"] == ["code", "security"] and out["lite"] is False
    job = state.read_job(repo, j["id"])
    assert job["stage"] == "review" and job["round"] == 1 and job["reviews"] == {"code": "pending", "security": "pending"}
    assert (repo / "factory/jobs" / j["id"] / "round-1").is_dir()


def test_a_light_change_of_any_size_takes_the_short_path(repo):
    state.setup(repo, repo)
    j = new(repo, 1)
    (repo / "app/util.py").write_text("\n".join(f"x{i} = {i}" for i in range(80)) + "\n")
    out = state.route_job(repo, j["id"])
    assert out["lite"] is True and out["reviewers"] == ["code"] and out["rerun"] == []
    job = state.read_job(repo, j["id"])
    assert job["stage"] == "approve" and job["lite"] is True and job["round"] == 1 and job["reviews"] == {"code": "pending"}


def test_a_medium_change_takes_the_short_path(repo):
    (repo / PLAN_FILE).write_text(PLAN.replace("**Tier:** light", "**Tier:** medium"))
    git(repo, "commit", "-q", "-am", "medium")
    state.setup(repo, repo)
    j = new(repo, 1)
    (repo / "app/util.py").write_text("x = 2\n")
    assert state.route_job(repo, j["id"])["lite"] is True


def test_careful_and_risky_jobs_keep_their_reviewers(repo):
    state.setup(repo, repo)
    careful = new(repo, 2)
    (repo / "app/util.py").write_text("x = 2\n")
    assert state.route_job(repo, careful["id"])["lite"] is False
    git(repo, "checkout", "--", "app/util.py")
    light = new(repo, 1)
    (repo / "app/auth/session.py").write_text("N = 60\n")
    out = state.route_job(repo, light["id"])
    assert out["lite"] is False and "security" in out["reviewers"]


def test_verdicts_read_the_approvers_code_review_on_the_short_path(repo):
    state.setup(repo, repo)
    j = new(repo, 1)
    (repo / "app/util.py").write_text("x = 2\n")
    state.route_job(repo, j["id"])
    folder = repo / "factory/jobs" / j["id"]
    (folder / "decision.md").write_text("APPROVE\n")
    out = state.check_verdicts(repo, j["id"])
    assert out["ok"] is False and out["missing"] == ["code"]
    (folder / "round-1/review-code.md").write_text("VERDICT: CHANGES\n\n## Issues\n1. x\n")
    out = state.check_verdicts(repo, j["id"])
    assert out["all_pass"] is False and state.read_job(repo, j["id"])["reviews"] == {"code": "CHANGES"}


def test_verdict_check_fails_loudly_when_a_file_is_missing(repo):
    state.setup(repo, repo)
    j = new(repo, 2)
    (repo / "app/auth/session.py").write_text("N = 60\n")
    state.route_job(repo, j["id"])
    rnd = repo / "factory/jobs" / j["id"] / "round-1"
    (rnd / "review-code.md").write_text("VERDICT: PASS\n")
    res = state.check_verdicts(repo, j["id"])
    assert res["ok"] is False and res["missing"] == ["security"]
    assert state.read_job(repo, j["id"])["stage"] == "review"
    (rnd / "review-security.md").write_text("VERDICT: CHANGES\n\n1. x\n")
    res = state.check_verdicts(repo, j["id"])
    assert res["ok"] is True and res["all_pass"] is False
    assert state.read_job(repo, j["id"])["reviews"] == {"code": "PASS", "security": "CHANGES"}


def test_verdict_check_rejects_a_first_line_that_is_not_a_verdict(repo):
    state.setup(repo, repo)
    j = new(repo, 2)
    (repo / "app/auth/session.py").write_text("N = 60\n")
    state.route_job(repo, j["id"])
    rnd = repo / "factory/jobs" / j["id"] / "round-1"
    (rnd / "review-code.md").write_text("Looks fine to me\n")
    (rnd / "review-security.md").write_text("VERDICT: PASS\n")
    res = state.check_verdicts(repo, j["id"])
    assert res["ok"] is False and res["invalid"] == ["code"]


def test_land_sets_the_stage_the_head_and_the_run_counts(repo):
    state.setup(repo, repo)
    state.write_run(repo, "docs/superpowers/plans/2026-01-01-demo.md", mode="current-branch", pace="step")
    run = json.loads((repo / "factory/jobs/_runs/2026-01-01-demo.json").read_text())
    assert (run["total"], run["done"], run["pace"]) == (2, 0, "step") and run["tasks"][1]["after"] == [1]
    j = new(repo, 1)
    state.land_job(repo, j["id"], "committed", head="abc123")
    job = state.read_job(repo, j["id"])
    assert job["stage"] == "committed" and job["head"] == "abc123"
    assert json.loads((repo / "factory/jobs/_runs/2026-01-01-demo.json").read_text())["done"] == 1


def test_cli_prints_json_and_returns_a_failure_code_for_a_failed_check(repo, capsys):
    state.setup(repo, repo)
    j = new(repo, 2)
    (repo / "app/auth/session.py").write_text("N = 60\n")
    assert state.main(["route", j["id"], "--root", str(repo)]) == 0
    assert json.loads(capsys.readouterr().out)["reviewers"] == ["code", "security"]
    assert state.main(["verdicts", j["id"], "--root", str(repo)]) == 1
    assert json.loads(capsys.readouterr().out)["ok"] is False


# ---- run lock and protected files ----

import os  # noqa: E402
import stat  # noqa: E402
from datetime import datetime, timedelta, timezone  # noqa: E402

PLAN_FILE = "docs/superpowers/plans/2026-01-01-demo.md"


def writable(p: Path) -> bool:
    return bool(p.stat().st_mode & stat.S_IWUSR)


@pytest.fixture
def locked_repo(repo):
    spec = repo / "docs/superpowers/specs"
    spec.mkdir(parents=True)
    (spec / "2026-01-01-demo-design.md").write_text("# spec\n")
    plan = repo / PLAN_FILE
    plan.write_text(plan.read_text().replace("**Spec:** none", "**Spec:** `docs/superpowers/specs/2026-01-01-demo-design.md`"))
    state.setup(repo, repo)
    return repo


def test_acquire_takes_the_lock_and_makes_plan_and_spec_read_only(locked_repo):
    r = state.lock_acquire(locked_repo, PLAN_FILE, run_id="run-a")
    assert r["ok"] is True
    assert not writable(locked_repo / PLAN_FILE)
    assert not writable(locked_repo / "docs/superpowers/specs/2026-01-01-demo-design.md")
    lock = json.loads((locked_repo / "factory/jobs/_runs/2026-01-01-demo.lock").read_text())
    assert lock["run_id"] == "run-a" and set(lock["protect"]) == {PLAN_FILE, "docs/superpowers/specs/2026-01-01-demo-design.md"}


def test_a_second_run_is_refused_while_the_first_is_alive(locked_repo):
    state.lock_acquire(locked_repo, PLAN_FILE, run_id="run-a")
    r = state.lock_acquire(locked_repo, PLAN_FILE, run_id="run-b")
    assert r["ok"] is False and r["stale"] is False and r["held_by"] == "run-a"
    assert not writable(locked_repo / PLAN_FILE)


def test_the_same_run_can_take_its_own_lock_again(locked_repo):
    state.lock_acquire(locked_repo, PLAN_FILE, run_id="run-a")
    assert state.lock_acquire(locked_repo, PLAN_FILE, run_id="run-a")["ok"] is True


def test_release_restores_the_original_permissions_and_removes_the_lock(locked_repo):
    before = (locked_repo / PLAN_FILE).stat().st_mode & 0o777
    state.lock_acquire(locked_repo, PLAN_FILE, run_id="run-a")
    r = state.lock_release(locked_repo, "2026-01-01-demo", run_id="run-a")
    assert r["ok"] is True and r["released"] is True
    assert (locked_repo / PLAN_FILE).stat().st_mode & 0o777 == before
    assert not (locked_repo / "factory/jobs/_runs/2026-01-01-demo.lock").exists()


def test_release_by_another_run_is_refused_unless_forced(locked_repo):
    state.lock_acquire(locked_repo, PLAN_FILE, run_id="run-a")
    assert state.lock_release(locked_repo, "2026-01-01-demo", run_id="run-b")["ok"] is False
    assert not writable(locked_repo / PLAN_FILE)
    assert state.lock_release(locked_repo, "2026-01-01-demo", run_id="run-b", force=True)["ok"] is True
    assert writable(locked_repo / PLAN_FILE)


def _age(repo, minutes):
    p = repo / "factory/jobs/_runs/2026-01-01-demo.lock"
    lock = json.loads(p.read_text())
    lock["heartbeat"] = (datetime.now(timezone.utc) - timedelta(minutes=minutes)).strftime("%Y-%m-%dT%H:%M:%SZ")
    p.write_text(json.dumps(lock))


def test_a_lock_without_a_heartbeat_for_long_is_stale_and_needs_an_explicit_takeover(locked_repo):
    before = (locked_repo / PLAN_FILE).stat().st_mode & 0o777
    state.lock_acquire(locked_repo, PLAN_FILE, run_id="run-a")
    _age(locked_repo, 45)
    r = state.lock_acquire(locked_repo, PLAN_FILE, run_id="run-b")
    assert r["ok"] is False and r["stale"] is True
    r = state.lock_acquire(locked_repo, PLAN_FILE, run_id="run-b", force=True)
    assert r["ok"] is True
    state.lock_release(locked_repo, "2026-01-01-demo", run_id="run-b")
    assert (locked_repo / PLAN_FILE).stat().st_mode & 0o777 == before


def test_any_job_change_refreshes_the_heartbeat(locked_repo):
    state.lock_acquire(locked_repo, PLAN_FILE, run_id="run-a")
    _age(locked_repo, 20)
    j = new(locked_repo)
    state.set_stage(locked_repo, j["id"], "build")
    lock = json.loads((locked_repo / "factory/jobs/_runs/2026-01-01-demo.lock").read_text())
    age = datetime.now(timezone.utc) - datetime.strptime(lock["heartbeat"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    assert age < timedelta(minutes=2)


def test_lock_list_reports_each_lock_and_whether_it_is_stale(locked_repo):
    state.lock_acquire(locked_repo, PLAN_FILE, run_id="run-a")
    _age(locked_repo, 45)
    [item] = state.lock_list(locked_repo)
    assert item["plan"] == "2026-01-01-demo" and item["stale"] is True and item["run_id"] == "run-a"


def test_tick_plan_ticks_only_landed_tasks_even_on_a_read_only_plan(locked_repo):
    state.lock_acquire(locked_repo, PLAN_FILE, run_id="run-a")
    j = new(locked_repo, 1)
    state.land_job(locked_repo, j["id"], "committed", head="abc")
    state.tick_plan(locked_repo, PLAN_FILE)
    text = (locked_repo / PLAN_FILE).read_text()
    assert text.count("- [x]") == 2 and text.count("- [ ]") == 1
    assert not writable(locked_repo / PLAN_FILE)


def test_tick_plan_ticks_the_task_being_landed_and_never_closes(locked_repo):
    state.lock_acquire(locked_repo, PLAN_FILE, run_id="run-a")
    j = new(locked_repo, 1)
    state.land_job(locked_repo, j["id"], "committed", head="abc")
    out = state.tick_plan(locked_repo, PLAN_FILE, task=2)  # task 2 has no landed job yet: it lands in the same commit
    text = (locked_repo / PLAN_FILE).read_text()
    assert out["ticked"] == 3 and "- [ ]" not in text
    assert "status:" not in text and "## Delivery status" not in text
    assert not writable(locked_repo / PLAN_FILE)


def test_close_plan_writes_documentation_and_divergences_once(locked_repo):
    path = locked_repo / PLAN_FILE
    text = path.read_text().replace("**Files:** `app/util.py`\n", "**Files:** `app/util.py`\n**Docs:** `docs/util.md`\n")
    path.write_text(text.replace("- [ ] **Step 1: Do it**", "- [ ] **Step 1: Do it**\n- [-] **Step 2: Migrate old sessions** not needed, none exist"))
    for n in (1, 2):
        j = new(locked_repo, n)
        if n == 1:
            (locked_repo / "factory/jobs" / j["id"] / "build.md").write_text(
                "STATUS: READY\n\n## Summary\nx\n\n## Deviations\n- Named it `slug` instead of `slugify`: clashes with a builtin.\n\n## Commit\nfeat: x\n")
        else:
            (locked_repo / "factory/jobs" / j["id"] / "build.md").write_text("STATUS: READY\n\n## Deviations\nNone.\n")
        state.land_job(locked_repo, j["id"], "committed", head="abc")
    out = state.close_plan(locked_repo, PLAN_FILE)
    text = path.read_text()
    assert out["closed"] is True and out["documented_in"] == ["docs/util.md"]
    section = text.split("## Delivery status (")[1]
    assert "**Documented in:** `docs/util.md`" in section
    assert "- Task 1: Named it `slug` instead of `slugify`: clashes with a builtin." in section
    assert "- Task 2: step cancelled: Migrate old sessions not needed, none exist" in section
    assert "None." not in section and "- [" not in section
    assert "### Execution record" in section
    state.close_plan(locked_repo, PLAN_FILE)
    assert path.read_text().count("## Delivery status") == 1


def test_close_plan_says_when_no_task_names_documentation(locked_repo):
    for n in (1, 2):
        j = new(locked_repo, n)
        state.land_job(locked_repo, j["id"], "committed", head="abc")
    state.close_plan(locked_repo, PLAN_FILE)
    text = (locked_repo / PLAN_FILE).read_text()
    assert "**Documented in:** none, no task names documentation" in text and "None recorded." in text


def test_cli_lock_acquire_exits_3_when_another_run_holds_the_plan(locked_repo, capsys):
    assert state.main(["lock", "acquire", "--root", str(locked_repo), "--plan-file", PLAN_FILE, "--run-id", "run-a"]) == 0
    capsys.readouterr()
    assert state.main(["lock", "acquire", "--root", str(locked_repo), "--plan-file", PLAN_FILE, "--run-id", "run-b"]) == 3
    assert json.loads(capsys.readouterr().out)["held_by"] == "run-a"


def test_close_plan_closes_the_header_when_every_task_is_done(locked_repo):
    for n in (1, 2):
        j = new(locked_repo, n)
        state.land_job(locked_repo, j["id"], "committed", head="abc")
    out = state.close_plan(locked_repo, PLAN_FILE)
    text = (locked_repo / PLAN_FILE).read_text()
    assert out["closed"] is True
    assert text.startswith("---\nstatus: completed\nverified_on: 20")
    assert text.count("- [ ]") == 0
    assert state.close_plan(locked_repo, PLAN_FILE)["closed"] is False  # already closed: not written twice
    assert (locked_repo / PLAN_FILE).read_text().count("status:") == 1


def test_close_plan_replaces_an_existing_status_and_leaves_unfinished_plans_open(locked_repo):
    path = locked_repo / PLAN_FILE
    path.write_text("---\ntitle: x\nstatus: open\n---\n" + path.read_text())
    j = new(locked_repo, 1)
    state.land_job(locked_repo, j["id"], "committed", head="abc")
    assert state.close_plan(locked_repo, PLAN_FILE)["closed"] is False
    assert "status: open" in path.read_text()
    j = new(locked_repo, 2)
    state.land_job(locked_repo, j["id"], "committed", head="abc")
    assert state.close_plan(locked_repo, PLAN_FILE)["closed"] is True
    text = path.read_text()
    assert text.count("status:") == 1 and "status: completed" in text and "title: x" in text


def test_close_plan_leaves_a_trailing_section_open_and_the_plan_unclosed(locked_repo):
    path = locked_repo / PLAN_FILE
    path.write_text(path.read_text() + "\n## Release gates\n\n- [ ] publish\n")
    for n in (1, 2):
        j = new(locked_repo, n)
        state.land_job(locked_repo, j["id"], "committed", head="abc")
    out = state.close_plan(locked_repo, PLAN_FILE)
    text = path.read_text()
    assert out["closed"] is False and out["ticked"] == 3
    assert "- [ ] publish" in text and "status: completed" not in text


def test_closing_writes_an_execution_record_without_checkboxes(locked_repo):
    for n in (1, 2):
        j = new(locked_repo, n)
        state.record_agent(locked_repo, j["id"], "builder", model="sonnet", tokens=1000, ms=5000, tools=3)
        if n == 1:
            (locked_repo / "factory/jobs" / j["id"] / "rework-1.md").write_text("again")
        state.land_job(locked_repo, j["id"], "committed", head="abc")
    state.close_plan(locked_repo, PLAN_FILE)
    text = (locked_repo / PLAN_FILE).read_text()
    assert "## Execution record" in text and "| Task | Tier |" in text
    assert "reworked 1x" in text and "Total: 2000 tokens, 10s" in text
    tail = text.split("## Execution record")[1]
    assert "- [ ]" not in tail and "- [x]" not in tail and "### Task" not in tail
    state.close_plan(locked_repo, PLAN_FILE)
    assert (locked_repo / PLAN_FILE).read_text().count("## Execution record") == 1


def test_execution_record_counts_findings_per_round_and_lens(locked_repo):
    a, b = new(locked_repo, 1), new(locked_repo, 2)
    folder = locked_repo / "factory/jobs" / a["id"]
    (folder / "round-1").mkdir()
    (folder / "round-2").mkdir()
    (folder / "round-1/review-code.md").write_text("VERDICT: CHANGES\n\n## Issues\n1. x\n2. y\n")
    (folder / "round-1/review-ui.md").write_text("VERDICT: PASS\n\n## Issues\nNone.\n")
    (folder / "round-2/review-code.md").write_text("VERDICT: PASS\n\n## Issues\nNone.\n")
    for j in (a, b):
        state.land_job(locked_repo, j["id"], "committed", head="abc")
    state.close_plan(locked_repo, PLAN_FILE)
    text = (locked_repo / PLAN_FILE).read_text()
    assert "| Decision | Findings | Notes |" in text
    assert "r1 code 2, r1 ui 0, r2 code 0" in text
    row2 = next(l for l in text.splitlines() if l.startswith("| 2 |"))
    assert row2.split("|")[-5].strip() == "short path"


def test_findings_ignore_numbered_observations_and_mark_reviewed_jobs_without_files(locked_repo):
    a, b = new(locked_repo, 1), new(locked_repo, 2)
    folder = locked_repo / "factory/jobs" / a["id"]
    (folder / "round-1").mkdir()
    (folder / "round-1/review-code.md").write_text("VERDICT: PASS\n\n## Issues\nNone.\n\n## Observations\n1. a\n2. b\n")
    job = state.read_job(locked_repo, b["id"])
    job["reviews"] = {"code": "PASS"}
    state.write_job(locked_repo, job)
    rows = state.execution_record(locked_repo, "2026-01-01-demo").splitlines()
    cells = {l.split("|")[1].strip(): l.split("|")[-5].strip() for l in rows if l.startswith("| 1 |") or l.startswith("| 2 |")}
    assert cells == {"1": "r1 code 0", "2": "-"}


def test_clean_removes_landed_jobs_but_refuses_while_one_is_unfinished(locked_repo):
    a, b = new(locked_repo, 1), new(locked_repo, 2)
    state.land_job(locked_repo, a["id"], "committed", head="abc")
    state.set_stage(locked_repo, b["id"], "needs-human")
    out = state.clean_jobs(locked_repo, "2026-01-01-demo")
    assert out["ok"] is False and (locked_repo / "factory/jobs" / a["id"]).exists()
    state.land_job(locked_repo, b["id"], "merged", head="def")
    out = state.clean_jobs(locked_repo, "2026-01-01-demo")
    assert out["ok"] is True and not (locked_repo / "factory/jobs" / a["id"]).exists()


# ---- partial review rounds, the ready-made diff and recorded checks ----


def review(repo, job_id, rnd, lens, verdict):
    d = repo / "factory/jobs" / job_id / f"round-{rnd}"
    d.mkdir(exist_ok=True)
    (d / f"review-{lens}.md").write_text(f"VERDICT: {verdict}\n\n## Issues\nNone.\n")


def test_a_lens_that_passed_is_not_rerun_while_nothing_it_watches_changed(repo):
    state.setup(repo, repo)
    j = new(repo, 2)
    (repo / "app/auth/session.py").write_text("N = 60\n")
    assert state.route_job(repo, j["id"])["rerun"] == ["code", "security"]
    review(repo, j["id"], 1, "code", "PASS")
    review(repo, j["id"], 1, "security", "CHANGES")
    assert state.check_verdicts(repo, j["id"])["all_pass"] is False
    (repo / "app/auth/session.py").write_text("N = 61\n")
    out = state.route_job(repo, j["id"])
    assert out["rerun"] == ["code", "security"] and out["carried"] == {}
    review(repo, j["id"], 2, "code", "PASS")
    review(repo, j["id"], 2, "security", "PASS")
    assert state.check_verdicts(repo, j["id"])["all_pass"] is True
    (repo / "app/util.py").write_text("x = 2\n")
    out = state.route_job(repo, j["id"])
    assert out["reviewers"] == ["code", "security"] and out["rerun"] == ["code"] and out["carried"] == {"security": 2}
    assert state.read_job(repo, j["id"])["reviews"] == {"code": "pending", "security": "PASS"}


def test_the_round_is_complete_with_the_rerun_lenses_and_the_carried_verdicts(repo):
    state.setup(repo, repo)
    j = new(repo, 2)
    (repo / "app/auth/session.py").write_text("N = 60\n")
    state.route_job(repo, j["id"])
    review(repo, j["id"], 1, "code", "PASS")
    review(repo, j["id"], 1, "security", "PASS")
    state.check_verdicts(repo, j["id"])
    (repo / "app/util.py").write_text("x = 2\n")
    state.route_job(repo, j["id"])
    missing = state.check_verdicts(repo, j["id"])
    assert missing["ok"] is False and missing["missing"] == ["code"]
    review(repo, j["id"], 2, "code", "CHANGES")
    out = state.check_verdicts(repo, j["id"])
    assert out["ok"] is True and out["all_pass"] is False and out["verdicts"] == {"code": "CHANGES"} and out["carried"] == {"security": 1}


def test_a_carried_verdict_keeps_the_round_it_was_given_in(repo):
    state.setup(repo, repo)
    j = new(repo, 2)
    (repo / "app/auth/session.py").write_text("N = 60\n")
    state.route_job(repo, j["id"])
    review(repo, j["id"], 1, "code", "PASS")
    review(repo, j["id"], 1, "security", "PASS")
    state.check_verdicts(repo, j["id"])
    (repo / "app/util.py").write_text("x = 2\n")
    state.route_job(repo, j["id"])
    review(repo, j["id"], 2, "code", "PASS")
    state.check_verdicts(repo, j["id"])
    (repo / "app/util.py").write_text("x = 3\n")
    assert state.route_job(repo, j["id"])["carried"] == {"security": 1}


def test_a_lens_newly_called_for_by_a_changed_path_runs_even_with_nothing_to_carry(repo):
    state.setup(repo, repo)
    j = new(repo, 2)
    (repo / "app/util.py").write_text("x = 2\n")
    assert state.route_job(repo, j["id"])["rerun"] == ["code"]
    review(repo, j["id"], 1, "code", "PASS")
    state.check_verdicts(repo, j["id"])
    (repo / "app/auth/session.py").write_text("N = 60\n")
    out = state.route_job(repo, j["id"])
    assert out["rerun"] == ["code", "security"] and out["carried"] == {}


def test_nothing_changed_since_a_passing_round_means_nothing_to_rerun(repo):
    state.setup(repo, repo)
    j = new(repo, 2)
    (repo / "app/util.py").write_text("x = 2\n")
    state.route_job(repo, j["id"])
    review(repo, j["id"], 1, "code", "PASS")
    state.check_verdicts(repo, j["id"])
    out = state.route_job(repo, j["id"])
    assert out["rerun"] == [] and out["carried"] == {"code": 1}
    assert state.check_verdicts(repo, j["id"])["all_pass"] is True


def test_route_writes_the_diff_with_commits_files_and_what_changed_since_the_last_round(repo):
    state.setup(repo, repo)
    j = new(repo, 2)
    (repo / "app/auth/session.py").write_text("N = 60\n")
    (repo / "app/new.py").write_text("y = 1\n")
    out = state.route_job(repo, j["id"])
    patch = Path(out["diff"])
    assert patch == repo / "factory/jobs" / j["id"] / "round-1/diff.patch"
    text = patch.read_text()
    assert "+N = 60" in text and "+y = 1" in text and "app/new.py" in text and "Changed since" not in text
    (repo / "app/util.py").write_text("x = 2\n")
    text = Path(state.route_job(repo, j["id"])["diff"]).read_text()
    assert "# Changed since the previous round: app/util.py" in text


def test_the_short_path_gets_its_diff_in_its_round_folder(repo):
    state.setup(repo, repo)
    j = new(repo, 1)
    (repo / "app/util.py").write_text("x = 2\n")
    out = state.route_job(repo, j["id"])
    assert out["lite"] is True and out["diff"] == str(repo / "factory/jobs" / j["id"] / "round-1" / "diff.patch")
    assert "+x = 2" in Path(out["diff"]).read_text()


def test_execution_record_notes_the_short_path(locked_repo):
    j = new(locked_repo, 1)
    (locked_repo / "app/util.py").write_text("x = 2\n")
    state.route_job(locked_repo, j["id"])
    state.land_job(locked_repo, j["id"], "committed", head="abc")
    state.land_job(locked_repo, new(locked_repo, 2)["id"], "committed", head="abc")
    state.close_plan(locked_repo, PLAN_FILE)
    row1 = next(l for l in (locked_repo / PLAN_FILE).read_text().splitlines() if l.startswith("| 1 |"))
    assert "short path" in row1.split("|")[-4]


def test_isolated_job_diff_lists_the_commits_and_follows_the_branch(repo):
    state.setup(repo, repo)
    base = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True).stdout.strip()
    git(repo, "checkout", "-q", "-b", "factory/demo/001")
    j = state.new_job(repo, "docs/superpowers/plans/2026-01-01-demo.md", 2, repo_name="demo", mode="isolated", branch="factory/demo/001", worktree=str(repo), base=base)
    (repo / "app/auth/session.py").write_text("N = 60\n")
    git(repo, "commit", "-q", "-am", "raise the lifetime")
    out = state.route_job(repo, j["id"])
    text = Path(out["diff"]).read_text()
    assert out["reviewers"] == ["code", "security"] and "raise the lifetime" in text and "+N = 60" in text
    review(repo, j["id"], 1, "code", "PASS")
    review(repo, j["id"], 1, "security", "PASS")
    state.check_verdicts(repo, j["id"])
    (repo / "app/util.py").write_text("x = 2\n")
    git(repo, "commit", "-q", "-am", "touch util")
    out = state.route_job(repo, j["id"])
    assert out["rerun"] == ["code"] and out["carried"] == {"security": 1}


def test_verify_records_the_run_and_a_reuse_does_not_run_it_again(repo):
    state.setup(repo, repo)
    j = new(repo, 1)
    counter = repo.parent / f"{repo.name}-runs.txt"
    cmd = f"echo x >> {counter}; echo green"
    first = state.run_check(repo, j["id"], cmd)
    assert first["exit"] == 0 and first["reused"] is False and first["tail"] == ["green"] and first["current"] is True
    again = state.run_check(repo, j["id"], cmd, reuse=True)
    assert again["reused"] is True and again["n"] == first["n"] and counter.read_text() == "x\n"
    assert Path(first["log"]).read_text() == "green\n"


def test_verify_reruns_when_the_code_changed_or_the_command_differs(repo):
    state.setup(repo, repo)
    j = new(repo, 1)
    first = state.run_check(repo, j["id"], "true")
    (repo / "app/util.py").write_text("x = 2\n")
    again = state.run_check(repo, j["id"], "true", reuse=True)
    assert again["reused"] is False and again["n"] == first["n"] + 1 and again["state"] != first["state"]
    other = state.run_check(repo, j["id"], "echo other", reuse=True)
    assert other["reused"] is False and other["n"] == again["n"] + 1


def test_a_failed_check_keeps_its_exit_code_and_is_reused_as_failed(repo):
    state.setup(repo, repo)
    j = new(repo, 1)
    bad = state.run_check(repo, j["id"], "echo boom; exit 3")
    assert bad["exit"] == 3 and bad["tail"] == ["boom"]
    again = state.run_check(repo, j["id"], "echo boom; exit 3", reuse=True)
    assert again["reused"] is True and again["exit"] == 3


def test_checks_lists_every_run_and_marks_those_for_the_current_code(repo):
    state.setup(repo, repo)
    j = new(repo, 1)
    state.run_check(repo, j["id"], "true")
    (repo / "app/util.py").write_text("x = 2\n")
    state.run_check(repo, j["id"], "echo two")
    listed = state.list_checks(repo, j["id"])
    assert [(c["cmd"], c["current"]) for c in listed] == [("true", False), ("echo two", True)]


def test_a_check_that_runs_too_long_is_recorded_as_timed_out(repo):
    state.setup(repo, repo)
    j = new(repo, 1)
    out = state.run_check(repo, j["id"], "sleep 5", timeout=1)
    assert out["exit"] == 124 and "timed out" in out["tail"][0]


def test_cli_verify_returns_the_exit_code_of_the_check(repo, capsys):
    state.setup(repo, repo)
    j = new(repo, 1)
    assert state.main(["verify", j["id"], "--cmd", "true", "--root", str(repo)]) == 0
    assert json.loads(capsys.readouterr().out)["exit"] == 0
    assert state.main(["verify", j["id"], "--cmd", "exit 2", "--root", str(repo)]) == 1
    assert json.loads(capsys.readouterr().out)["exit"] == 2
    assert state.main(["checks", j["id"], "--root", str(repo)]) == 0
    assert len(json.loads(capsys.readouterr().out)) == 2


def test_a_check_stays_current_when_the_same_code_is_committed_again(repo):
    state.setup(repo, repo)
    base = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True).stdout.strip()
    git(repo, "checkout", "-q", "-b", "factory/demo/001")
    j = state.new_job(repo, "docs/superpowers/plans/2026-01-01-demo.md", 1, repo_name="demo", mode="isolated", branch="factory/demo/001", worktree=str(repo), base=base)
    (repo / "app/util.py").write_text("x = 2\n")
    git(repo, "commit", "-q", "-am", "change")
    first = state.run_check(repo, j["id"], "true")
    git(repo, "commit", "-q", "--amend", "-m", "same code, new message")
    again = state.run_check(repo, j["id"], "true", reuse=True)
    assert again["reused"] is True and again["n"] == first["n"] and again["current"] is True


# ---- composite commands: fewer round trips for the same bookkeeping ----


def test_begin_job_creates_the_job_and_moves_it_to_build(repo):
    state.setup(repo, repo)
    out = state.begin_job(repo, PLAN_FILE, 1, repo_name="demo", mode="current-branch", branch="main", worktree=str(repo))
    job = state.read_job(repo, out["id"])
    assert out["stage"] == "build" and job["stage"] == "build"
    assert [p["stage"] for p in job["phases"]] == ["spec", "build"] and job["phases"][0]["end"] is not None
    assert (repo / "factory/jobs" / out["id"] / "task.md").exists()
    assert re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", job["started"]) and job["updated"] >= job["started"]


def test_after_agent_records_several_agents_in_one_call(repo):
    state.setup(repo, repo)
    j = new(repo, 2)
    state.record_agents(repo, j["id"], [
        {"role": "code", "model": "sonnet", "effort": "medium", "tokens": 9000, "ms": 20000, "tools": 5},
        {"role": "security", "model": "opus", "tokens": 12000, "ms": 30000, "tools": 7},
    ])
    state.record_agents(repo, j["id"], [{"role": "code", "model": "sonnet", "tokens": 1000, "ms": 2000, "tools": 1}])
    agents = state.read_job(repo, j["id"])["agents"]
    assert (agents["code"]["tokens"], agents["code"]["runs"], agents["security"]["model"]) == (10000, 2, "opus")


def test_preflight_without_a_plan_lists_the_plans_with_open_steps(repo):
    out = state.preflight(repo)
    assert [p["path"] for p in out["plans"]] == [PLAN_FILE] and out["plans"][0]["open"] == 2 and out["unclassified"] == []


def test_preflight_with_a_plan_gives_the_parse_the_jobs_and_the_audit(repo):
    state.setup(repo, repo)
    j = new(repo, 1)
    state.set_stage(repo, j["id"], "build")
    out = state.preflight(repo, PLAN_FILE, "demo")
    assert [t["title"] for t in out["plan"]["tasks"]] == ["Add slugify helper", "Extend the session lifetime"]
    assert out["plan"]["tasks"][1]["defaults_applied"] is not None and "done_signals" in out["plan"]["tasks"][0]
    assert [(x["id"], x["task"], x["stage"]) for x in out["jobs"]] == [(j["id"], 1, "build")]
    assert out["audit"] == []
    assert "plans" not in out


def test_preflight_audit_names_only_the_chosen_plan(repo):
    other = repo / "docs/superpowers/plans/2026-01-02-other.md"
    other.write_text("---\nstatus: completed\n---\n# Other\n\n### Task 1: Create the thing\n\n**Files:**\n- Create: `app/never.py`\n\n- [x] **Step 1: Done**\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "other plan")
    everything = state.preflight(repo, "docs/superpowers/plans/2026-01-02-other.md", "demo")["audit"]
    mine = state.preflight(repo, PLAN_FILE, "demo")["audit"]
    assert mine == [] and all(f["path"].endswith("2026-01-02-other.md") for f in everything)


def test_cli_runs_the_composite_commands(repo, capsys):
    state.setup(repo, repo)
    assert state.main(["preflight", "--root", str(repo), "--plan-file", PLAN_FILE, "--repo-name", "demo"]) == 0
    assert json.loads(capsys.readouterr().out)["plan"]["title"]
    assert state.main(["begin-job", "--root", str(repo), "--plan-file", PLAN_FILE, "--task", "1", "--repo-name", "demo", "--mode", "current-branch", "--branch", "main", "--worktree", str(repo)]) == 0
    began = json.loads(capsys.readouterr().out)
    assert began["stage"] == "build"
    agents = json.dumps([{"role": "builder", "model": "sonnet", "tokens": 5, "ms": 6, "tools": 7}])
    assert state.main(["after-agent", began["id"], "--agents", agents, "--root", str(repo)]) == 0
    assert json.loads(capsys.readouterr().out)["builder"]["tokens"] == 5


# ---- ad hoc working plan ----


def adhoc(root, text):
    return subprocess.run([sys.executable, str(Path(state.__file__)), "adhoc", "--root", str(root), "--text", text], capture_output=True, text=True)


def test_adhoc_writes_a_parsable_plan_under_runs_and_prints_its_facts(tmp_path):
    done = adhoc(tmp_path, "Rename the helper across the demo module and update the callers now")
    assert done.returncode == 0, done.stderr
    out = json.loads(done.stdout)
    path = Path(out["plan_file"])
    assert path.parent == tmp_path / "factory/jobs/_runs" and path.suffix == ".md"
    assert re.fullmatch(r"adhoc-\d{8}-\d{6}-[a-z0-9-]+", out["plan_stem"]) and path.stem == out["plan_stem"]
    assert out["tier"] == "medium" and out["title"] == "Rename the helper across the demo module and"
    assert (tmp_path / "factory/jobs/.gitignore").read_text() == "*\n"
    text = path.read_text()
    assert "### Task 1: Rename the helper across the demo module and" in text
    assert "**Tier:** medium" in text
    assert "**Accept:** 1. Rename the helper across the demo module and update the callers now" in text
    assert "- [ ] **Step 1: Rename the helper across the demo module and update the callers now**" in text
    plan = state.parse_plan(text)
    assert len(plan.tasks) == 1 and plan.tasks[0].tier == "medium" and plan.tasks[0].steps and plan.tasks[0].accept


def test_adhoc_plan_works_with_run_lock_and_new_job_by_its_path(tmp_path):
    git(tmp_path, "init", "-q", "-b", "main")
    out = json.loads(adhoc(tmp_path, "tier=careful Fix the demo parser").stdout)
    assert out["tier"] == "careful"
    assert state.write_run(tmp_path, out["plan_file"], "current-branch")["total"] == 1
    assert state.lock_acquire(tmp_path, out["plan_file"], run_id="r")["ok"] is True
    job = state.new_job(tmp_path, out["plan_file"], 1, repo_name="demo", mode="current-branch", branch="main", worktree=str(tmp_path))
    j = state.read_job(tmp_path, job["id"])
    assert j["tier"] == "careful" and j["plan"] == out["plan_stem"]


def test_adhoc_tier_token_is_removed_from_title_and_accept(tmp_path):
    out = json.loads(adhoc(tmp_path, "tier=light Tidy the demo readme").stdout)
    assert out["tier"] == "light" and out["title"] == "Tidy the demo readme"
    text = Path(out["plan_file"]).read_text()
    assert "tier=" not in text and "**Accept:** 1. Tidy the demo readme" in text


def test_adhoc_title_is_capped_at_60_characters(tmp_path):
    out = json.loads(adhoc(tmp_path, "internationalization " * 6).stdout)
    assert len(out["title"]) <= 60 and out["title"].startswith("internationalization")


@pytest.mark.parametrize("text", ["tier=huge Do a thing", "", "   ", "tier=light"])
def test_adhoc_refuses_an_unknown_tier_or_empty_text_with_exit_2(tmp_path, text):
    done = adhoc(tmp_path, text)
    assert done.returncode == 2
    assert "light, medium, careful, heavy, fable" in done.stderr
    assert not (tmp_path / "factory/jobs/_runs").exists()


def test_clean_deletes_a_read_only_adhoc_plan(tmp_path):
    git(tmp_path, "init", "-q", "-b", "main")
    out = json.loads(adhoc(tmp_path, "Do the demo thing").stdout)
    state.lock_acquire(tmp_path, out["plan_file"], run_id="r")
    assert not writable(Path(out["plan_file"]))
    state.lock_release(tmp_path, out["plan_stem"], run_id="r")
    state.lock_acquire(tmp_path, out["plan_file"], run_id="r")
    assert state.clean_jobs(tmp_path, out["plan_stem"])["ok"] is True
    assert not Path(out["plan_file"]).exists()


def test_md_files_in_runs_are_ignored_by_lock_list_and_resolve_plans(tmp_path):
    out = json.loads(adhoc(tmp_path, "Do the demo thing").stdout)
    assert state.lock_list(tmp_path) == []
    state.lock_acquire(tmp_path, out["plan_file"], run_id="r")
    assert [v["plan"] for v in state.lock_list(tmp_path)] == [out["plan_stem"]]
    assert resolve.list_plans(tmp_path) == [] and resolve.list_unclassified(tmp_path) == []


def test_adhoc_collapses_whitespace_so_a_multiline_text_stays_on_one_line(tmp_path):
    out = json.loads(adhoc(tmp_path, "tier=light Fix the demo\nsecond line:  more\t text").stdout)
    text = Path(out["plan_file"]).read_text()
    assert "**Accept:** 1. Fix the demo second line: more text\n" in text
    assert "- [ ] **Step 1: Fix the demo second line: more text**\n" in text
    assert state.parse_plan(text).tasks[0].accept == ["Fix the demo second line: more text"]


def test_adhoc_same_second_same_text_gets_a_numeric_suffix_even_when_the_first_is_read_only(tmp_path):
    first = json.loads(adhoc(tmp_path, "Do the demo thing").stdout)
    Path(first["plan_file"]).chmod(0o444)
    seen = {first["plan_file"]}
    for _ in range(2):
        done = adhoc(tmp_path, "Do the demo thing")
        assert done.returncode == 0, done.stderr
        seen.add(json.loads(done.stdout)["plan_file"])
    assert len(seen) == 3 and all(Path(p).exists() for p in seen)


def test_adhoc_tier_key_is_case_insensitive(tmp_path):
    out = json.loads(adhoc(tmp_path, "TIER=Careful Do the demo thing").stdout)
    assert out["tier"] == "careful" and out["title"] == "Do the demo thing"


def test_escalate_moves_the_tier_one_step_and_prints_its_model(repo):
    state.setup(repo, repo)
    j = new(repo, 1)
    out = state.escalate(repo, j["id"], "claude")
    assert out == {"escalated": True, "tier": "medium", "escalated_from": "light", "model": "sonnet", "effort": "medium"}
    job = state.read_job(repo, j["id"])
    assert job["tier"] == "medium" and job["escalated_from"] == "light"


def test_escalate_twice_changes_nothing_the_second_time(repo):
    state.setup(repo, repo)
    j = new(repo, 1)
    first = state.escalate(repo, j["id"], "claude")
    before = state.read_job(repo, j["id"])
    assert state.escalate(repo, j["id"], "claude") == first
    assert state.read_job(repo, j["id"]) == before


@pytest.mark.parametrize("tier", ["heavy", "fable"])
def test_heavy_and_fable_are_not_escalated(repo, tier):
    state.setup(repo, repo)
    j = new(repo, 1)
    job = state.read_job(repo, j["id"])
    job["tier"] = tier
    state.write_job(repo, job)
    assert state.escalate(repo, j["id"], "claude") == {"escalated": False, "tier": tier}
    assert "escalated_from" not in state.read_job(repo, j["id"])


def test_an_escalated_job_leaves_the_short_path_at_careful(repo):
    (repo / PLAN_FILE).write_text(PLAN.replace("**Tier:** light", "**Tier:** medium"))
    git(repo, "commit", "-q", "-am", "medium")
    state.setup(repo, repo)
    j = new(repo, 1)
    state.escalate(repo, j["id"], "claude")
    (repo / "app/util.py").write_text("x = 2\n")
    assert state.route_job(repo, j["id"])["lite"] is False


def test_execution_record_shows_the_escalated_tier(locked_repo):
    j = new(locked_repo, 1)
    state.escalate(locked_repo, j["id"], "claude")
    state.land_job(locked_repo, j["id"], "committed", head="abc")
    state.land_job(locked_repo, new(locked_repo, 2)["id"], "committed", head="abc")
    state.close_plan(locked_repo, PLAN_FILE)
    row1 = next(l for l in (locked_repo / PLAN_FILE).read_text().splitlines() if l.startswith("| 1 |"))
    assert row1.split("|")[2].strip() == "light→medium"


def test_cli_escalate(repo, capsys):
    state.setup(repo, repo)
    j = new(repo, 1)
    assert state.main(["escalate", j["id"], "--host", "claude", "--root", str(repo)]) == 0
    assert json.loads(capsys.readouterr().out)["tier"] == "medium"


STEM = "2026-01-01-demo"


def head(repo):
    return subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True).stdout.strip()


def run_state(repo):
    return json.loads(state.run_path(repo, STEM).read_text())


def set_run(repo, **fields):
    run = run_state(repo)
    for k, v in fields.items():
        if v is None:
            run.pop(k, None)
        else:
            run[k] = v
    state.run_path(repo, STEM).write_text(json.dumps(run))


def commit(repo, text, subject):
    (repo / "app/util.py").write_text(text)
    git(repo, "commit", "-q", "-am", subject)


def test_run_records_its_base_once(repo):
    state.setup(repo, repo)
    state.write_run(repo, PLAN_FILE, "current-branch")
    first = head(repo)
    commit(repo, "x = 2\n", "later work")
    state.write_run(repo, PLAN_FILE, "current-branch")
    assert run_state(repo)["base"] == first


def test_final_diff_current_branch_spans_the_run(repo):
    state.setup(repo, repo)
    state.write_run(repo, PLAN_FILE, "current-branch")
    commit(repo, "x = 2\n", "alpha change")
    out = state.final_diff(repo, STEM)
    text = Path(out["patch"]).read_text()
    assert out["ok"] is True and out["commits"] == 1 and out["risky"] is False
    assert "# Plan 2026-01-01-demo, final review" in text and "alpha change" in text and "+x = 2" in text
    assert out["head"] == head(repo) == run_state(repo)["final"]["head"]


def test_final_diff_isolated_spans_the_integration_branch(repo):
    state.setup(repo, repo)
    state.write_run(repo, PLAN_FILE, "isolated")
    set_run(repo, integration="factory/demo")
    git(repo, "checkout", "-q", "-b", "factory/demo")
    commit(repo, "x = 2\n", "on integration")
    git(repo, "checkout", "-q", "main")
    out = state.final_diff(repo, STEM)
    text = Path(out["patch"]).read_text()
    assert out["ok"] is True and "on integration" in text and "+x = 2" in text


def test_final_diff_isolated_without_the_branch_is_not_ok(repo):
    state.setup(repo, repo)
    state.write_run(repo, PLAN_FILE, "isolated")
    set_run(repo, integration="factory/gone")
    out = state.final_diff(repo, STEM)
    assert out["ok"] is False and "factory/gone" in out["reason"]


def test_final_diff_without_base_is_not_ok(repo):
    state.setup(repo, repo)
    state.write_run(repo, PLAN_FILE, "current-branch")
    set_run(repo, base=None)
    assert state.final_diff(repo, STEM)["ok"] is False
    assert state.main(["final-diff", "--root", str(repo), "--plan", STEM]) == 1


def test_final_diff_fix_starts_from_the_recorded_head(repo):
    state.setup(repo, repo)
    state.write_run(repo, PLAN_FILE, "current-branch")
    commit(repo, "x = 2\n", "alpha change")
    state.final_diff(repo, STEM)
    commit(repo, "x = 3\n", "beta fix")
    out = state.final_diff(repo, STEM, fix=True)
    text = Path(out["patch"]).read_text()
    assert out["patch"].endswith(f"{STEM}-final-2.patch") and out["commits"] == 1
    assert "beta fix" in text and "alpha change" not in text and "+x = 3" in text
    assert run_state(repo)["final"]["fix_head"] == head(repo)


def test_final_diff_is_risky_when_any_job_was(repo):
    state.setup(repo, repo)
    state.write_run(repo, PLAN_FILE, "current-branch")
    j = new(repo, 1)
    job = state.read_job(repo, j["id"])
    job["reviewers"] = ["code", "security"]
    state.write_job(repo, job)
    commit(repo, "x = 2\n", "alpha change")
    assert state.final_diff(repo, STEM)["risky"] is True


FINAL = "VERDICT: CHANGES\n\n## Findings\n1. a.py:1: first\n2. b.py:2: second\n\n## Observations\n1. not a finding\n"


def test_final_verdict_stores_the_verdict_and_fails_without_one(repo):
    state.setup(repo, repo)
    state.write_run(repo, PLAN_FILE, "current-branch")
    runs = repo / "factory/jobs/_runs"
    usage = {"model": "opus", "effort": "high", "tokens": 100, "ms": 2000}
    (runs / f"{STEM}-final.md").write_text(FINAL)
    assert state.final_verdict(repo, STEM, False, usage) == {"ok": True, "verdict": "CHANGES", "findings": 2}
    assert run_state(repo)["final"]["review"] == {"verdict": "CHANGES", "findings": 2, "agent": usage}
    (runs / f"{STEM}-final.md").write_text("Looks fine to me.\n")
    assert state.final_verdict(repo, STEM, False, usage)["ok"] is False
    assert state.final_verdict(repo, STEM, True, usage)["ok"] is False
    assert state.main(["final-verdict", "--root", str(repo), "--plan", STEM, "--fix", "--agent", "{}"]) == 1


def test_close_plan_writes_the_final_review(locked_repo):
    state.write_run(locked_repo, PLAN_FILE, "current-branch")
    runs = locked_repo / "factory/jobs/_runs"
    (runs / f"{STEM}-final.md").write_text(FINAL)
    state.final_verdict(locked_repo, STEM, False, {"model": "opus", "tokens": 100, "ms": 2000})
    (runs / f"{STEM}-final-2.md").write_text("VERDICT: CHANGES\n\n## Findings\n2. b.py:2: second, still open\n")
    state.final_verdict(locked_repo, STEM, True, {"model": "opus", "tokens": 50, "ms": 1000}, fix_job="004-fix")
    for n in (1, 2):
        state.land_job(locked_repo, new(locked_repo, n)["id"], "committed", head="abc")
    state.close_plan(locked_repo, PLAN_FILE)
    section = (locked_repo / PLAN_FILE).read_text().split("### Final review")[1]
    assert "First review: CHANGES, 2 finding(s)." in section and "Fix: job 004-fix." in section
    assert "2. b.py:2: second, still open" in section.split("Left open:")[1] and "a.py:1" not in section.split("Left open:")[1]
    row = next(l for l in (locked_repo / PLAN_FILE).read_text().splitlines() if l.startswith("| final |"))
    assert "opus" in row and "150" in row


def test_close_plan_without_a_final_review_writes_no_section(locked_repo):
    state.write_run(locked_repo, PLAN_FILE, "current-branch")
    for n in (1, 2):
        state.land_job(locked_repo, new(locked_repo, n)["id"], "committed", head="abc")
    state.close_plan(locked_repo, PLAN_FILE)
    text = (locked_repo / PLAN_FILE).read_text()
    assert "### Execution record" in text and "### Final review" not in text and "| final |" not in text


def test_rework_starts_a_new_attempt_from_the_current_round(repo):
    state.setup(repo, repo)
    j = new(repo, 1)
    job = state.read_job(repo, j["id"])
    job["round"], job["stage"] = 3, "needs-human"
    state.write_job(repo, job)
    assert state.rework(repo, j["id"]) == {"rework_from": 3}
    job = state.read_job(repo, j["id"])
    assert job["rework_from"] == 3 and job["stage"] == "build"
    assert state.main(["rework", j["id"], "--root", str(repo)]) == 0


def test_a_resumed_run_from_before_the_base_keeps_no_base(repo):
    state.setup(repo, repo)
    state.write_run(repo, PLAN_FILE, "current-branch")
    set_run(repo, base=None)
    commit(repo, "x = 2\n", "work before the resume")
    state.write_run(repo, PLAN_FILE, "current-branch")
    assert "base" not in run_state(repo) or run_state(repo)["base"] is None


def test_final_diff_isolated_starts_where_the_integration_branch_left_main(repo):
    state.setup(repo, repo)
    git(repo, "checkout", "-q", "-b", "feature")
    commit(repo, "x = 9\n", "feature work")
    git(repo, "checkout", "-q", "main")
    (repo / "app/auth/session.py").write_text("N = 45\n")
    git(repo, "commit", "-q", "-am", "main moved on")
    git(repo, "checkout", "-q", "feature")
    state.write_run(repo, PLAN_FILE, "isolated")
    git(repo, "branch", "factory/2026-01-01-demo", "main")
    git(repo, "checkout", "-q", "factory/2026-01-01-demo")
    (repo / "app/auth/session.py").write_text("N = 50\n")
    git(repo, "commit", "-q", "-am", "run work")
    git(repo, "checkout", "-q", "feature")
    out = state.final_diff(repo, STEM)
    text = Path(out["patch"]).read_text()
    assert out["ok"] is True and "run work" in text and "main moved on" not in text and "feature work" not in text


def test_final_diff_fix_with_no_new_commit_is_not_ok(repo):
    state.setup(repo, repo)
    state.write_run(repo, PLAN_FILE, "current-branch")
    commit(repo, "x = 2\n", "alpha change")
    state.final_diff(repo, STEM)
    out = state.final_diff(repo, STEM, fix=True)
    assert out["ok"] is False and "no commit" in out["reason"]


def test_final_diff_again_reuses_the_recorded_review_span(repo):
    state.setup(repo, repo)
    state.write_run(repo, PLAN_FILE, "current-branch")
    commit(repo, "x = 2\n", "alpha change")
    first = state.final_diff(repo, STEM)
    commit(repo, "x = 3\n", "beta fix")
    again = state.final_diff(repo, STEM)
    assert again["reused"] is True and again["head"] == first["head"] and again["patch"] == first["patch"]
    assert run_state(repo)["final"]["head"] == first["head"]
    assert "beta fix" not in Path(again["patch"]).read_text()


def test_escalate_records_the_builder_it_asks_for_and_keeps_the_earlier_model(locked_repo):
    j = new(locked_repo, 1)
    state.record_agent(locked_repo, j["id"], "builder", model="haiku", effort="low", tokens=10)
    state.escalate(locked_repo, j["id"], "claude")
    builder = state.read_job(locked_repo, j["id"])["agents"]["builder"]
    assert (builder["model"], builder["effort"]) == ("sonnet", "medium") and builder["models"] == ["haiku", "sonnet"]
    state.record_agent(locked_repo, j["id"], "builder", model="sonnet", effort="medium", tokens=20)
    state.land_job(locked_repo, j["id"], "committed", head="abc")
    state.land_job(locked_repo, new(locked_repo, 2)["id"], "committed", head="abc")
    state.close_plan(locked_repo, PLAN_FILE)
    row1 = next(l for l in (locked_repo / PLAN_FILE).read_text().splitlines() if l.startswith("| 1 |"))
    assert row1.split("|")[3].strip() == "haiku/sonnet"


def test_final_verdict_with_bad_usage_json_exits_2(repo, capsys):
    state.setup(repo, repo)
    state.write_run(repo, PLAN_FILE, "current-branch")
    assert state.main(["final-verdict", "--root", str(repo), "--plan", STEM, "--agent", "{not json"]) == 2
    assert "error" in json.loads(capsys.readouterr().out)


def test_clean_removes_the_final_review_files(repo):
    state.setup(repo, repo)
    state.write_run(repo, PLAN_FILE, "current-branch")
    runs = repo / "factory/jobs/_runs"
    for name in ("-final.patch", "-final.md", "-final-2.patch", "-final-2.md"):
        (runs / f"{STEM}{name}").write_text("x")
    assert state.clean_jobs(repo, STEM)["ok"] is True
    assert not list(runs.glob(f"{STEM}-final*"))


def test_preflight_audit_finds_a_plan_in_a_subfolder(repo):
    rel = "docs/superpowers/plans/area/2026-01-02-other.md"
    (repo / rel).parent.mkdir()
    (repo / rel).write_text("---\nstatus: completed\n---\n# Other\n\n### Task 1: Create the thing\n\n**Files:**\n- Create: `app/never.py`\n\n- [x] **Step 1: Done**\n")
    assert [f["path"] for f in state.preflight(repo, rel, "demo")["audit"]] == [rel]
    assert state.preflight(repo, PLAN_FILE, "demo")["audit"] == []


def one_task(tier="light", files="`app/util.py`", accept="1. Works.", verify="`pytest -q`") -> str:
    fields = [f"**Tier:** {tier}"]
    fields += [f"**Files:** {files}"] if files else []
    fields += [f"**Accept:** {accept}"] if accept else []
    fields += [f"**Verify:** {verify}"] if verify else []
    return "# P\n\n### Task 1: Do it\n\n" + "\n".join(fields) + "\n\n- [ ] **Step 1: Do**\n"


def eligibility(tmp_path, **fields):
    return state.lean_eligibility(state.parse_plan(one_task(**fields)).tasks[0], state._rules(tmp_path))


def test_a_light_task_with_files_accept_and_verify_is_eligible(tmp_path):
    assert eligibility(tmp_path) == (True, "")


@pytest.mark.parametrize("fields, reason", [
    ({"tier": "careful"}, "tier careful"),
    ({"files": ""}, "no Files"),
    ({"files": "the helpers"}, "no Files"),
    ({"files": "`app/util.py`, `app/auth/session.py`"}, "Files route to security"),
    ({"accept": ""}, "no Accept"),
    ({"verify": ""}, "no Verify"),
])
def test_eligibility_reasons(tmp_path, fields, reason):
    assert eligibility(tmp_path, **fields) == (False, reason)


def test_preflight_marks_each_task_and_counts_the_eligible(repo):
    out = state.preflight(repo, PLAN_FILE, "demo")
    task1 = out["plan"]["tasks"][0]
    assert (task1["lean"], task1["lean_reason"]) == (False, "no Verify") and out["lean_count"] == 0
    (repo / PLAN_FILE).write_text(PLAN.replace("**Accept:** 1. Works.", "**Accept:** 1. Works.\n**Verify:** `pytest -q`"))
    out = state.preflight(repo, PLAN_FILE, "demo")
    assert out["plan"]["tasks"][0]["lean"] is True and out["lean_count"] == 1 and out["long"] is False
    assert out["plan"]["tasks"][1]["lean_reason"] == "tier careful"


def test_preflight_flags_a_long_lean_plan(repo):
    body = one_task().split("### Task 1: Do it")[1]
    text = "# P\n" + "".join(f"\n### Task {n}: Do {n}{body}" for n in range(1, 10))
    (repo / PLAN_FILE).write_text(text)
    out = state.preflight(repo, PLAN_FILE, "demo")
    assert out["lean_count"] == 9 and out["long"] is True


def lean_job(repo, verify="`true`", task=1):
    (repo / PLAN_FILE).write_text(PLAN.replace("**Accept:** 1. Works.", f"**Accept:** 1. Works.\n**Verify:** {verify}"))
    git(repo, "commit", "-q", "-am", "verify")
    state.setup(repo, repo)
    return state.begin_job(repo, PLAN_FILE, task, repo_name="demo", mode="current-branch", branch="main", worktree=str(repo), lean=True)


def test_begin_job_lean_records_lean_and_the_verify_commands(repo):
    j = lean_job(repo, "`pytest -q` and `ruff check`")
    job = state.read_job(repo, j["id"])
    assert job["lean"] is True and job["verify"] == ["pytest -q", "ruff check"] and job["stage"] == "build"


def test_lean_check_lands_a_clean_code_change_with_a_passing_current_check(repo):
    j = lean_job(repo)
    (repo / "app/util.py").write_text("x = 2\n")
    state.run_check(repo, j["id"], "true")
    assert state.lean_check(repo, j["id"]) == {"land": True}


def test_lean_check_without_a_recorded_run_does_not_land(repo):
    j = lean_job(repo)
    (repo / "app/util.py").write_text("x = 2\n")
    assert state.lean_check(repo, j["id"]) == {"land": False, "promote": "no recorded run: true"}


def test_lean_check_on_a_stale_run_does_not_land(repo):
    j = lean_job(repo)
    (repo / "app/util.py").write_text("x = 2\n")
    state.run_check(repo, j["id"], "true")
    (repo / "app/util.py").write_text("x = 3\n")
    assert state.lean_check(repo, j["id"]) == {"land": False, "promote": "stale run: true"}


def test_lean_check_on_a_failing_run_does_not_land(repo):
    j = lean_job(repo, "`false`")
    (repo / "app/util.py").write_text("x = 2\n")
    state.run_check(repo, j["id"], "false")
    assert state.lean_check(repo, j["id"]) == {"land": False, "promote": "failing run: false"}


def test_lean_check_promotes_after_two_failed_runs(repo):
    flag = repo.parent / f"{repo.name}-ok"
    cmd = f"test -f {flag}"
    j = lean_job(repo, f"`{cmd}`")
    (repo / "app/util.py").write_text("x = 2\n")
    state.run_check(repo, j["id"], cmd)
    state.run_check(repo, j["id"], cmd)
    flag.write_text("")
    state.run_check(repo, j["id"], cmd)
    assert state.lean_check(repo, j["id"])["promote"] == f"checks failed twice: {cmd}"


def test_lean_check_promotes_a_change_that_routes_to_security(repo):
    j = lean_job(repo)
    (repo / "app/auth/session.py").write_text("N = 60\n")
    state.run_check(repo, j["id"], "true")
    assert state.lean_check(repo, j["id"]) == {"land": False, "promote": "routes to security"}


def test_promote_clears_lean_and_route_then_reviews_it(repo):
    j = lean_job(repo)
    (repo / "app/auth/session.py").write_text("N = 60\n")
    state.promote(repo, j["id"], "routes to security")
    job = state.read_job(repo, j["id"])
    assert job["lean"] is False and job["promoted"] == "routes to security"
    out = state.route_job(repo, j["id"])
    assert "security" in out["reviewers"] and out["lite"] is False


def test_execution_record_shows_lean_and_promoted_jobs(repo):
    a = lean_job(repo)
    b = state.begin_job(repo, PLAN_FILE, 2, repo_name="demo", mode="current-branch", branch="main", worktree=str(repo), lean=True)
    state.promote(repo, b["id"], "routes to security")
    for j in (a, b):
        state.land_job(repo, j["id"], "committed", head="abc")
    record = state.execution_record(repo, STEM)
    row1 = next(l for l in record.splitlines() if l.startswith("| 1 |")).split("|")
    row2 = next(l for l in record.splitlines() if l.startswith("| 2 |")).split("|")
    assert row1[5].strip() == "lean" and "lean" in row1[8]
    assert row2[5].strip() != "lean" and "promoted: routes to security" in row2[8]


def test_final_diff_reports_the_lean_jobs(repo):
    j = lean_job(repo)
    state.write_run(repo, PLAN_FILE, "current-branch")
    commit(repo, "x = 2\n", "lean work")
    state.land_job(repo, j["id"], "committed", head=head(repo))
    assert state.final_diff(repo, STEM)["lean"] == 1


def test_cli_lean_check_and_promote(repo, capsys):
    j = lean_job(repo)
    assert state.main(["lean-check", j["id"], "--root", str(repo)]) == 0
    assert json.loads(capsys.readouterr().out)["land"] is False
    assert state.main(["promote", j["id"], "--reason", "by hand", "--root", str(repo)]) == 0
    assert state.read_job(repo, j["id"])["promoted"] == "by hand"


def test_adhoc_takes_a_quoted_verify_command(tmp_path):
    out = state.adhoc_plan(tmp_path, 'tier=light verify="pytest -q tests" Fix the slug')
    text = Path(out["plan_file"]).read_text()
    assert out["verify"] == "pytest -q tests" and out["title"] == "Fix the slug"
    assert "**Verify:** `pytest -q tests`\n" in text and "**Accept:** 1. Fix the slug\n" in text


def test_adhoc_takes_verify_before_or_after_tier(tmp_path):
    out = state.adhoc_plan(tmp_path, "verify=`make test` tier=light Fix it")
    assert (out["verify"], out["tier"], out["title"]) == ("make test", "light", "Fix it")


def test_adhoc_takes_a_one_word_verify(tmp_path):
    assert state.adhoc_plan(tmp_path, "verify=pytest Fix it")["verify"] == "pytest"


def test_adhoc_without_verify_declares_none(tmp_path):
    out = state.adhoc_plan(tmp_path, "Fix it")
    assert out["verify"] == "" and "**Verify:**" not in Path(out["plan_file"]).read_text()


def test_an_ad_hoc_task_with_verify_is_eligible_without_files(repo):
    out = state.adhoc_plan(repo, "tier=light verify=true Fix the slug")
    pre = state.preflight(repo, out["plan_file"], "demo")
    assert pre["plan"]["tasks"][0]["lean"] is True and pre["lean_count"] == 1
    plain = state.adhoc_plan(repo, "tier=light Fix the slug again")
    assert state.preflight(repo, plain["plan_file"], "demo")["plan"]["tasks"][0]["lean_reason"] == "no Verify"


@pytest.mark.parametrize("files", ["`app/util.py`, `package.json`", "`app/util.py`, `.env`", "`app/util.py:12-40`, `composer.lock`"])
def test_a_sensitive_root_file_is_not_eligible(tmp_path, files):
    assert eligibility(tmp_path, files=files) == (False, "Files route to security")


def test_lean_check_refuses_a_job_that_is_not_lean_or_not_light_or_medium(repo):
    j = lean_job(repo, task=2)
    (repo / "app/util.py").write_text("x = 2\n")
    state.run_check(repo, j["id"], "true")
    assert state.lean_check(repo, j["id"]) == {"land": False, "promote": "tier careful"}
    state.promote(repo, j["id"], "by hand")
    assert state.lean_check(repo, j["id"]) == {"land": False, "promote": "not a lean job"}


def test_lean_check_does_not_land_an_empty_change(repo):
    j = lean_job(repo)
    state.run_check(repo, j["id"], "true")
    assert state.lean_check(repo, j["id"]) == {"land": False, "promote": "no change"}


def test_lean_check_in_isolated_mode_refuses_uncommitted_files(repo):
    (repo / PLAN_FILE).write_text(PLAN.replace("**Accept:** 1. Works.", "**Accept:** 1. Works.\n**Verify:** `true`"))
    git(repo, "commit", "-q", "-am", "verify")
    state.setup(repo, repo)
    base = head(repo)
    git(repo, "checkout", "-q", "-b", "factory/demo/001")
    j = state.begin_job(repo, PLAN_FILE, 1, repo_name="demo", mode="isolated", branch="factory/demo/001", worktree=str(repo), base=base, lean=True)
    commit(repo, "from app.helper import y\n", "use helper")
    (repo / "app/helper.py").write_text("y = 1\n")
    state.run_check(repo, j["id"], "true")
    assert state.lean_check(repo, j["id"]) == {"land": False, "promote": "uncommitted changes"}
    git(repo, "add", "app/helper.py")
    git(repo, "commit", "-q", "-m", "helper")
    state.run_check(repo, j["id"], "true")
    assert state.lean_check(repo, j["id"]) == {"land": True}


def start_cross(repo, monkeypatch, tmp_path, tiers=None, host="claude"):
    """A run with the peer on, and a Codex home with no rollout files, so no usage is read from the real one."""
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "codex-home"))
    if tiers is not None:
        (repo / "factory").mkdir(exist_ok=True)
        (repo / "factory/models.json").write_text(json.dumps({"cross": {"builder_tiers": tiers}}))
    state.setup(repo, repo)
    state.write_run(repo, PLAN_FILE, "current-branch", cross="on", host=host)


def vendor_cli(repo, capsys, *args):
    assert state.main(["vendor", *args, "--root", str(repo)]) == 0
    return json.loads(capsys.readouterr().out)


def test_vendor_records_the_choice_in_the_job(repo, capsys, monkeypatch, tmp_path):
    start_cross(repo, monkeypatch, tmp_path, tiers=["light"])
    j = new(repo)
    out = vendor_cli(repo, capsys, j["id"], "--agent", "builder", "--host", "claude")
    want = models.resolve(repo, "codex", tier="light")
    assert (out["vendor"], out["peer"], out["reason"], out["crossed"]) == ("codex", True, "builder_tiers", False)
    assert (out["model"], out["effort"]) == (want["model"], want["effort"])
    job = state.read_job(repo, j["id"])
    assert job["vendors"]["builder"] == {"vendor": "codex", "reason": "builder_tiers"}
    assert "crossed" not in job


def test_vendor_review_crosses_and_records_when_it_does_not(repo, capsys, monkeypatch, tmp_path):
    start_cross(repo, monkeypatch, tmp_path, tiers=["light"])
    j = new(repo)
    vendor_cli(repo, capsys, j["id"], "--agent", "builder", "--host", "claude")
    out = vendor_cli(repo, capsys, j["id"], "--agent", "reviewer-code", "--host", "claude")
    assert (out["vendor"], out["reason"], out["crossed"]) == ("claude", "opposite", True)
    assert out["model"] == models.resolve(repo, "claude", agent="reviewer-code")["model"]
    state.vendor_down(repo, STEM, "claude", "limit", "2999-01-01T00:00:00Z")
    out = vendor_cli(repo, capsys, j["id"], "--agent", "approver", "--host", "claude", "--risky")
    assert (out["vendor"], out["reason"], out["crossed"]) == ("codex", "not crossed", False)
    job = state.read_job(repo, j["id"])
    assert job["crossed"] is False
    assert job["vendors"]["approver"] == {"vendor": "codex", "reason": "not crossed"}


def test_vendor_reads_the_usage_of_the_codex_plan(repo, capsys, monkeypatch, tmp_path):
    start_cross(repo, monkeypatch, tmp_path, tiers=["light"])
    folder = tmp_path / "codex-home/sessions/2026/10/25"
    folder.mkdir(parents=True)
    event = {"payload": {"rate_limits": {"primary": {"used_percent": 91.0, "resets_at": time.time() + 3600}}}}
    (folder / "rollout-x.jsonl").write_text(json.dumps(event) + "\n")
    j = new(repo)
    out = vendor_cli(repo, capsys, j["id"], "--agent", "builder", "--host", "claude")
    assert (out["vendor"], out["reason"]) == ("claude", "threshold")


def test_vendor_for_the_final_review_is_kept_in_the_run_state(repo, capsys, monkeypatch, tmp_path):
    start_cross(repo, monkeypatch, tmp_path)
    out = vendor_cli(repo, capsys, "--agent", "reviewer-final", "--host", "claude", "--plan", STEM, "--risky")
    assert (out["vendor"], out["reason"]) == ("codex", "opposite")
    assert out["model"] == models.resolve(repo, "codex", agent="reviewer-final", risky=True)["model"]
    assert run_state(repo)["final"]["vendor"] == {"vendor": "codex", "reason": "opposite"}


def test_vendor_with_the_peer_off_is_the_session(repo, capsys):
    state.setup(repo, repo)
    state.write_run(repo, PLAN_FILE, "current-branch")
    j = new(repo)
    out = vendor_cli(repo, capsys, j["id"], "--agent", "builder", "--host", "claude")
    assert (out["vendor"], out["peer"], out["reason"]) == ("claude", False, "session")
    assert out["model"] == models.resolve(repo, "claude", tier="light")["model"]


def test_vendor_down_marks_the_run(repo, capsys):
    state.setup(repo, repo)
    state.write_run(repo, PLAN_FILE, "current-branch", cross="on", host="claude")
    until = "2026-10-25T18:00:00Z"
    assert state.main(["vendor-down", "--plan", STEM, "--vendor", "codex", "--reason", "limit", "--until", until, "--root", str(repo)]) == 0
    assert run_state(repo)["vendors"]["codex"] == {"exhausted_until": until}
    assert state.main(["vendor-down", "--plan", STEM, "--vendor", "codex", "--reason", "missing", "--root", str(repo)]) == 0
    assert run_state(repo)["vendors"]["codex"] == {"exhausted_until": until, "off": True}
    assert state.main(["vendor-down", "--plan", STEM, "--vendor", "claude", "--reason", "auth", "--root", str(repo)]) == 0
    assert run_state(repo)["vendors"]["claude"] == {"off": True}
    capsys.readouterr()


def test_vendor_down_limit_without_until_lasts_the_run(repo):
    state.setup(repo, repo)
    state.write_run(repo, PLAN_FILE, "current-branch", cross="on", host="claude")
    state.vendor_down(repo, STEM, "codex", "limit")
    assert run_state(repo)["vendors"]["codex"]["exhausted_until"] > "2999"


def test_vendor_down_refuses_a_bad_reason_a_bad_time_and_a_missing_run(repo, capsys):
    state.setup(repo, repo)
    with pytest.raises(ValueError):
        state.vendor_down(repo, STEM, "codex", "limit")
    state.write_run(repo, PLAN_FILE, "current-branch")
    with pytest.raises(ValueError):
        state.vendor_down(repo, STEM, "codex", "tired")
    with pytest.raises(ValueError):
        state.vendor_down(repo, STEM, "codex", "limit", "tomorrow")
    assert state.main(["vendor-down", "--plan", STEM, "--vendor", "codex", "--reason", "tired", "--root", str(repo)]) == 2
    assert "error" in json.loads(capsys.readouterr().out)


def test_run_records_cross(repo):
    state.setup(repo, repo)
    run = state.write_run(repo, PLAN_FILE, "current-branch", cross="on", host="claude")
    assert run["cross"] == {"on": True, "peer": "codex", "threshold": 80, "builder_tiers": []}
    assert run_state(repo)["cross"] == run["cross"]
    state.vendor_down(repo, STEM, "codex", "missing")
    run = state.write_run(repo, PLAN_FILE, "current-branch", cross="off", host="codex")
    assert run["cross"] == {"on": False, "peer": "claude", "threshold": 80, "builder_tiers": []}
    assert run["vendors"] == {"codex": {"off": True}}
    assert state.write_run(repo, PLAN_FILE, "current-branch")["cross"]["on"] is False  # not asked: what was recorded stays


def test_run_cross_takes_the_models_json_block(repo):
    (repo / "factory").mkdir()
    (repo / "factory/models.json").write_text(json.dumps({"cross": {"builder_tiers": ["light"], "threshold": 70}}))
    state.setup(repo, repo)
    assert state.main(["run", "--plan-file", PLAN_FILE, "--mode", "current-branch", "--cross", "on", "--host", "claude", "--root", str(repo)]) == 0
    assert run_state(repo)["cross"] == {"on": True, "peer": "codex", "threshold": 70, "builder_tiers": ["light"]}


def test_run_cross_on_a_host_without_a_peer_is_off(repo):
    state.setup(repo, repo)
    assert state.write_run(repo, PLAN_FILE, "current-branch", cross="on", host="cursor")["cross"]["on"] is False


def test_preflight_reports_the_peer(repo, tmp_path, monkeypatch):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    fake = bin_dir / "codex"
    fake.write_text("#!/bin/sh\n")
    fake.chmod(0o755)
    (bin_dir / "git").symlink_to(shutil.which("git"))  # a PATH that holds only git and the fake codex
    monkeypatch.setenv("PATH", str(bin_dir))
    assert state.preflight(repo, PLAN_FILE, "demo", host="claude")["peer"] == {"vendor": "codex", "found": True}
    assert state.preflight(repo, host="claude")["peer"] == {"vendor": "codex", "found": True}
    assert state.preflight(repo, PLAN_FILE, "demo", host="codex")["peer"] == {"vendor": "claude", "found": False}
    assert "peer" not in state.preflight(repo, PLAN_FILE, "demo", host="cursor")
    assert "peer" not in state.preflight(repo, PLAN_FILE, "demo")
