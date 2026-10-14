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


def test_commit_messages_are_read_from_inline_and_fenced_commit_steps():
    text = (
        "# P\n\n### Task 1: A\n\n- [ ] **Step 1: Commit** `feat: add parse`\n\n"
        "### Task 2: B\n\n- [ ] **Step 1: Commit**\n\n```bash\ngit add a\ngit commit -m \"fix: handle empty input\"\n```\n"
    )
    plan = parse_plan(text)
    assert plan.tasks[0].commits == ["feat: add parse"]
    assert plan.tasks[1].commits == ["fix: handle empty input"]


def test_create_bullets_are_told_apart_from_modify_bullets():
    text = "# P\n\n### Task 1: A\n\n**Files:**\n- Create: `new.py`\n- Modify: `old.py:10-20`\n- Test: `t.py`\n\n- [ ] **Step 1: do**\n"
    t = parse_plan(text).tasks[0]
    assert t.files == ["new.py", "old.py", "t.py"] and t.files_create == ["new.py", "t.py"]


def _git(root, *args):
    import subprocess

    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *args], cwd=root, check=True, capture_output=True)


def test_done_signals_come_from_commits_and_created_files_only(tmp_path, capsys):
    import json

    from factory_plan import main

    _git(tmp_path, "init", "-q")
    (tmp_path / "old.py").write_text("x")
    (tmp_path / "made.py").write_text("x")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-q", "-m", "feat: add parse")
    plan = tmp_path / "plan.md"
    plan.write_text(
        "# P\n\n"
        "### Task 1: Done by commit\n\n- [ ] **Step 1: Commit** `feat: add parse`\n\n"
        "### Task 2: Done by created file\n\n**Files:**\n- Create: `made.py`\n\n- [ ] **Step 1: do**\n\n"
        "### Task 3: Only modifies an existing file\n\n**Files:** `old.py`\n\n- [ ] **Step 1: do**\n\n"
        "### Task 4: Not done\n\n**Files:**\n- Create: `nope.py`\n\n- [ ] **Step 1: Commit** `feat: other`\n"
    )
    assert main([str(plan), "--root", str(tmp_path)]) == 0
    tasks = json.loads(capsys.readouterr().out)["tasks"]
    assert [bool(t["done_signals"]) for t in tasks] == [True, True, False, False]
    assert "feat: add parse" in tasks[0]["done_signals"][0]


def test_a_commit_message_with_a_longer_subject_still_counts(tmp_path, capsys):
    import json

    from factory_plan import main

    _git(tmp_path, "init", "-q")
    (tmp_path / "f").write_text("x")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-q", "-m", "feat: add dashboard and fixture jobs")
    plan = tmp_path / "plan.md"
    plan.write_text("# P\n\n### Task 1: A\n\n- [ ] **Step 1: Commit** `feat: add dashboard`\n\n### Task 2: B\n\n- [ ] **Step 1: Commit** `feat: add dash`\n")
    main([str(plan), "--root", str(tmp_path)])
    tasks = json.loads(capsys.readouterr().out)["tasks"]
    assert bool(tasks[0]["done_signals"]) is True
    assert bool(tasks[1]["done_signals"]) is True  # prefix match is deliberate; the user is asked, never skipped silently


def test_spec_path_is_read_from_the_plan_header():
    text = "# P\n\n**Goal:** x\n\n**Spec:** `docs/superpowers/specs/2026-01-01-demo-design.md`\n\n### Task 1: A\n\n- [ ] **Step 1: do**\n"
    assert parse_plan(text).spec == "docs/superpowers/specs/2026-01-01-demo-design.md"


def test_a_plan_without_a_real_spec_has_an_empty_spec():
    assert parse_plan("# P\n\n**Spec:** none (fixture)\n\n### Task 1: A\n\n- [ ] **Step 1: do**\n").spec == ""
    assert parse_plan("# P\n\n### Task 1: A\n\n- [ ] **Step 1: do**\n").spec == ""


def test_git_subjects_include_checked_out_submodules(tmp_path):
    import subprocess

    from factory_plan import git_subjects

    def git(cwd, *a):
        subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "-c", "protocol.file.allow=always", *a], cwd=cwd, check=True, capture_output=True)

    sub, main = tmp_path / "sub", tmp_path / "main"
    for d in (sub, main):
        d.mkdir()
        git(d, "init", "-q")
    (sub / "a").write_text("1")
    git(sub, "add", "a")
    git(sub, "commit", "-q", "-m", "feat: inside the submodule")
    (main / "b").write_text("1")
    git(main, "add", "b")
    git(main, "commit", "-q", "-m", "feat: in the root")
    git(main, "submodule", "add", "-q", str(sub), "Modules/X")
    got = git_subjects(main)
    assert {"feat: in the root", "feat: inside the submodule"} <= got


def test_task_counts_open_done_and_cancelled_steps():
    t = parse_plan("# P\n\n### Task 1: A\n\n- [ ] a\n- [x] b\n- [X] c\n- [-] d\n- [ ] e\n").tasks[0]
    assert t.counts() == (2, 2, 1)
    assert parse_plan("# P\n\n### Task 1: A\n").tasks[0].counts() == (0, 0, 0)


def test_task_state_follows_its_steps_and_cancelled_steps_count_as_resolved():
    text = (
        "# P\n\n### Task 1: A\n\n- [-] a\n- [-] b\n\n### Task 2: B\n\n- [x] a\n- [-] b\n\n"
        "### Task 3: C\n\n- [x] a\n- [ ] b\n\n### Task 4: D\n\n- [ ] a\n\n### Task 5: E\n"
    )
    assert [t.state for t in parse_plan(text).tasks] == ["cancelled", "done", "partial", "open", "empty"]


def test_status_banner_is_read_from_the_top_of_the_plan():
    assert parse_plan("# P\n\n> **Status:** completed 2026-10-01\n\n### Task 1: A\n\n- [ ] a\n").banner == "completed 2026-10-01"
    assert parse_plan("# P\n\nStatus: in progress\n\n### Task 1: A\n\n- [ ] a\n").banner == "in progress"
    assert parse_plan("# P\n\n**Status:** draft\n\n### Task 1: A\n\n- [ ] a\n").banner == "draft"


def test_status_banner_is_absent_without_a_banner_line():
    assert parse_plan("---\nstatus: completed\n---\n# P\n\n### Task 1: A\n\n- [ ] a\n").banner == ""
    assert parse_plan("---\nStatus: completed\n---\n# P\n\n### Task 1: A\n\n- [ ] a\n").banner == ""
    assert parse_plan("# P\n\n### Task 1: A\n\nStatus: inside a task\n\n- [ ] a\n").banner == ""
    assert parse_plan("# P\n\n```\nStatus: in a fence\n```\n\n### Task 1: A\n").banner == ""


def test_plan_date_comes_from_the_file_name():
    from factory_plan import plan_date

    assert plan_date("2026-10-13-factory-backlog.md") == "2026-10-13"
    assert plan_date("docs/superpowers/plans/2026-01-02-x.md") == "2026-01-02"
    assert plan_date("factory-backlog-2026-10-13.md") == ""
    assert plan_date("2026-1-3-short.md") == ""


def test_steps_before_the_first_task_form_a_plan_level_block():
    plan = parse_plan("# P\n\n- [x] agree on scope\n- [ ] book the hall\n\n### Task 1: A\n\n- [ ] a\n")
    assert [t.number for t in plan.tasks] == [1]
    assert [(b.kind, b.title, b.counts()) for b in plan.blocks] == [("plan", "(plan level)", (1, 1, 0)), ("task", "A", (1, 0, 0))]
    assert plan.blocks[1] is plan.tasks[0]


def test_a_section_after_the_last_task_does_not_leak_into_it():
    text = "# P\n\n### Task 1: A\n\n- [x] a\n\n## Release gates\n\n- [ ] tag the release\n- [ ] announce it\n"
    plan = parse_plan(text)
    assert plan.tasks[0].counts() == (0, 1, 0) and plan.tasks[0].done is True
    assert [(b.kind, b.title, b.counts()) for b in plan.blocks] == [("task", "A", (0, 1, 0)), ("section", "Release gates", (2, 0, 0))]


def test_a_plan_with_an_open_trailing_section_is_open():
    plan = parse_plan("# P\n\n### Task 1: A\n\n- [x] a\n\n## Release gates\n\n- [ ] publish\n")
    assert plan.state == "open"


def test_a_deeper_heading_inside_a_task_keeps_its_steps_in_the_task():
    plan = parse_plan("# P\n\n## Task 1: A\n\n### Details\n\n- [ ] a\n- [ ] b\n")
    assert plan.tasks[0].counts() == (2, 0, 0) and [b.kind for b in plan.blocks] == ["task"]


def test_blocks_without_steps_are_left_out_but_tasks_without_steps_stay():
    plan = parse_plan("# P\n\nIntro.\n\n## Context\n\nProse.\n\n### Task 1: A\n\n## Notes\n\nMore prose.\n")
    assert [b.kind for b in plan.blocks] == ["task"]


def test_file_lines_are_read_anywhere_in_a_task():
    text = "# P\n\n### Task 1: A\n\nSome prose first.\n\n- Create: `src/lamp.py`\n- Modify: `src/wick.py`\n\n- [ ] do\n"
    t = parse_plan(text).tasks[0]
    assert t.files == ["src/lamp.py", "src/wick.py"] and t.files_create == ["src/lamp.py"]


def test_migrations_and_new_test_files_are_created_files():
    text = (
        "# P\n\n### Task 1: A\n\n**Files:**\n- Migration: `db/0001_lamps.sql`\n- Test: `tests/test_lamp.py`\n"
        "- Test: extend `tests/test_wick.py`\n- Test: `tests/test_oil.py` (existing)\n- File: `docs/lamp.md`\n\n- [ ] do\n"
    )
    t = parse_plan(text).tasks[0]
    assert t.files == ["db/0001_lamps.sql", "tests/test_lamp.py", "tests/test_wick.py", "tests/test_oil.py", "docs/lamp.md"]
    assert t.files_create == ["db/0001_lamps.sql", "tests/test_lamp.py"]


def test_test_files_named_as_extended_or_modified_are_not_created():
    text = (
        "# P\n\n### Task 1: A\n\n**Files:**\n- Test: `tests/test_lamp.py` (extended)\n"
        "- Test: `tests/test_wick.py` (modified)\n- Test: appended to `tests/test_oil.py`\n\n- [ ] do\n"
    )
    assert parse_plan(text).tasks[0].files_create == []


def test_a_new_test_file_whose_path_holds_such_a_word_is_still_created():
    text = "# P\n\n### Task 1: A\n\n**Files:**\n- Test: `tests/existence_test.py`\n\n- [ ] do\n"
    assert parse_plan(text).tasks[0].files_create == ["tests/existence_test.py"]


def test_deleted_files_are_told_apart_from_the_files_a_task_keeps():
    text = "# P\n\n### Task 1: A\n\n**Files:**\n- Modify: `src/lamp.py`\n- Delete: `src/candle.py`\n\n- [ ] do\n"
    t = parse_plan(text).tasks[0]
    assert t.files == ["src/lamp.py", "src/candle.py"] and t.files_delete == ["src/candle.py"]
