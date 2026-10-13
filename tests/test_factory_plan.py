import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "plugins/clay/scripts"))
from factory_plan import parse_plan  # noqa: E402


def load(name: str, repo: str = ""):
    return parse_plan((HERE / "fixtures" / name).read_text(), default_repo=repo)


def test_superset_fields_parsed():
    t = load("plan-superset.md").tasks[0]
    assert (t.number, t.title, t.repo, t.tier) == (1, "Backend endpoint", "api", "careful")
    assert t.depends == [] and t.files == ["app/Http/Foo.php", "tests/FooTest.php"]
    assert t.accept == ["Returns 200.", "Rejects bad input."]
    assert t.verify == "`php artisan test`"
    assert t.defaults_applied == []


def test_field_lines_not_steps():
    t = load("plan-superset.md").tasks[0]
    assert len(t.steps) == 3


def test_cancelled_step_not_open():
    t = load("plan-superset.md").tasks[0]
    assert [s.state for s in t.steps] == ["done", "done", "cancelled"]
    assert t.done is True


def test_task_without_steps_is_not_done():
    t = load("plan-superset.md").tasks[2]
    assert t.steps == [] and t.done is False


def test_legacy_plan_gets_defaults():
    t = load("plan-legacy.md", repo="myrepo").tasks[0]
    assert t.tier == "medium" and t.repo == "myrepo" and t.depends == []
    assert "tier" in t.defaults_applied and "accept" in t.defaults_applied
    assert t.accept == ["Write the failing test", "Implement"]


def test_checkbox_in_code_fence_ignored():
    t = load("plan-superset.md").tasks[1]
    assert [s.state for s in t.steps] == ["done", "open"] and t.done is False


def test_phase_headings_are_tasks():
    plan = load("plan-legacy.md")
    assert [t.number for t in plan.tasks] == [1, 2] and plan.tasks[1].done is True


def test_plan_skill_template_parses():
    import re

    skill = (HERE.parent / "plugins/clay/skills/factory-plan/SKILL.md").read_text()
    m = re.search(r"## Task template\n+```markdown\n(.*?)\n```", skill, re.S)
    assert m, "plan skill must contain a '## Task template' markdown block"
    plan = parse_plan(m.group(1), default_repo="x")
    t = plan.tasks[0]
    assert t.defaults_applied == [] and t.tier == "careful" and t.depends == [1]
    assert len(t.steps) >= 2 and all(s.state == "open" for s in t.steps)


def test_superpowers_files_bullets_parsed():
    text = "# P\n\n### Task 1: A\n\n**Files:**\n- Create: `a/b.py`\n- Modify: `c.py:12-30`\n- Test: `t/test_b.py`\n\n- [ ] **Step 1: do**\n"
    t = parse_plan(text).tasks[0]
    assert t.files == ["a/b.py", "c.py", "t/test_b.py"] and len(t.steps) == 1


def test_files_listed_in_defaults_when_absent():
    t = parse_plan("# P\n\n### Task 1: A\n\n- [ ] **Step 1: do**\n").tasks[0]
    assert "files" in t.defaults_applied


def test_all_cancelled_task_is_done():
    t = parse_plan("# P\n\n### Task 1: A\n\n- [-] **Step 1: dropped**\n").tasks[0]
    assert t.done is True


def test_check_files_splits_present_missing_and_skips_patterns(tmp_path):
    from factory_plan import check_files

    (tmp_path / "a.py").write_text("x")
    present, missing = check_files(["a.py", "b.py", "skills/{run,task}/SKILL.md", "src/*.ts"], tmp_path)
    assert (present, missing) == (["a.py"], ["b.py"])


def test_cli_reports_existing_files_for_a_root(tmp_path, capsys):
    import json

    from factory_plan import main

    (tmp_path / "a.py").write_text("x")
    plan = tmp_path / "plan.md"
    plan.write_text("# P\n\n### Task 1: A\n\n**Files:** `a.py`\n\n- [ ] **Step 1: do**\n\n### Task 2: B\n\n**Files:** `b.py`\n\n- [ ] **Step 1: do**\n")
    assert main([str(plan), "--root", str(tmp_path)]) == 0
    tasks = json.loads(capsys.readouterr().out)["tasks"]
    assert (tasks[0]["files_present"], tasks[0]["files_missing"]) == (["a.py"], [])
    assert (tasks[1]["files_present"], tasks[1]["files_missing"]) == ([], ["b.py"])


def test_indented_field_lines_are_still_fields():
    t = parse_plan("# P\n\n### Task 1: A\n\n  **Tier:** heavy\n\n- [ ] **Step 1: do**\n").tasks[0]
    assert t.tier == "heavy" and "tier" not in t.defaults_applied


def test_unknown_tier_falls_back_to_medium_with_a_warning():
    t = parse_plan("# P\n\n### Task 1: A\n\n**Tier:** high\n\n- [ ] **Step 1: do**\n").tasks[0]
    assert t.tier == "medium" and any("high" in w for w in t.warnings)
