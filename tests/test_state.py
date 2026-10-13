import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugins/clay/scripts"))
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


def test_light_small_change_takes_the_short_path_without_reviewers(repo):
    state.setup(repo, repo)
    j = new(repo, 1)
    (repo / "app/util.py").write_text("x = 2\n")
    out = state.route_job(repo, j["id"])
    assert out["lite"] is True and out["reviewers"] == []
    job = state.read_job(repo, j["id"])
    assert job["stage"] == "approve" and job["lite"] is True and job["reviewers"] == []


def test_light_but_large_change_keeps_its_reviewers(repo):
    state.setup(repo, repo)
    j = new(repo, 1)
    (repo / "app/util.py").write_text("\n".join(f"x{i} = {i}" for i in range(80)) + "\n")
    out = state.route_job(repo, j["id"])
    assert out["lite"] is False and out["reviewers"] == ["code"]


def test_a_non_light_task_never_takes_the_short_path(repo):
    state.setup(repo, repo)
    j = new(repo, 2)
    (repo / "app/util.py").write_text("x = 2\n")
    assert state.route_job(repo, j["id"])["lite"] is False


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


def test_cli_lock_acquire_exits_3_when_another_run_holds_the_plan(locked_repo, capsys):
    assert state.main(["lock", "acquire", "--root", str(locked_repo), "--plan-file", PLAN_FILE, "--run-id", "run-a"]) == 0
    capsys.readouterr()
    assert state.main(["lock", "acquire", "--root", str(locked_repo), "--plan-file", PLAN_FILE, "--run-id", "run-b"]) == 3
    assert json.loads(capsys.readouterr().out)["held_by"] == "run-a"


def test_tick_plan_closes_the_header_when_every_task_is_done(locked_repo):
    for n in (1, 2):
        j = new(locked_repo, n)
        state.land_job(locked_repo, j["id"], "committed", head="abc")
    out = state.tick_plan(locked_repo, PLAN_FILE)
    text = (locked_repo / PLAN_FILE).read_text()
    assert out["closed"] is True
    assert text.startswith("---\nstatus: completed\nverified_on: 20")
    assert text.count("- [ ]") == 0
    assert state.tick_plan(locked_repo, PLAN_FILE)["closed"] is False  # already closed: not written twice
    assert (locked_repo / PLAN_FILE).read_text().count("status:") == 1


def test_tick_plan_replaces_an_existing_status_and_leaves_unfinished_plans_open(locked_repo):
    path = locked_repo / PLAN_FILE
    path.write_text("---\ntitle: x\nstatus: open\n---\n" + path.read_text())
    j = new(locked_repo, 1)
    state.land_job(locked_repo, j["id"], "committed", head="abc")
    assert state.tick_plan(locked_repo, PLAN_FILE)["closed"] is False
    assert "status: open" in path.read_text()
    j = new(locked_repo, 2)
    state.land_job(locked_repo, j["id"], "committed", head="abc")
    assert state.tick_plan(locked_repo, PLAN_FILE)["closed"] is True
    text = path.read_text()
    assert text.count("status:") == 1 and "status: completed" in text and "title: x" in text
