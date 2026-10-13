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
