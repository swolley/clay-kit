import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugins/clay/scripts"))
import json  # noqa: E402

from plan_status import (Options, build_report, discover, main, render_html, render_json,  # noqa: E402
                         render_table, scan_plans, scan_specs, scan_todos)

KEYS = {"repo", "file", "path", "date", "title", "front_matter_status", "status_banner", "tasks", "total_steps",
        "checked_steps", "state", "inconsistency"}


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path


def _plan(path: Path, steps: str, front: str = "", head: str = "") -> Path:
    fm = f"---\nstatus: {front}\n---\n" if front else ""
    return _write(path, f"{fm}# Lantern plan\n{head}\n## Task 1: light the lantern\n\n{steps}\n")


def _one(root: Path) -> dict:
    plans = scan_plans(root, discover(root))
    assert len(plans) == 1
    return plans[0]


def _workspace(root: Path) -> None:
    _plan(root / "docs/superpowers/plans/2026-01-01-root-plan.md", "- [ ] a")
    _plan(root / "orchard/docs/superpowers/plans/2026-01-02-orchard-plan.md", "- [ ] a")
    _plan(root / "quarry/.cursor/plans/quarry.plan.md", "- [ ] a")
    _write(root / "meadow/README.md", "nothing to see\n")


def test_discover_maps_the_root_first_then_each_nested_repository(tmp_path):
    _workspace(tmp_path)
    assert list(discover(tmp_path).items()) == [(tmp_path.name, ""), ("orchard", "orchard"), ("quarry", "quarry")]


def test_discover_finds_specs_and_module_plans_and_skips_the_root_without_work(tmp_path):
    _write(tmp_path / "harbor/Modules/Tide/docs/plans/2026-01-03-tide.md", "# Tide\n")
    _write(tmp_path / "dune/docs/superpowers/specs/2026-01-03-dune-design.md", "# Dune\n")
    assert discover(tmp_path) == {"dune": "dune", "harbor": "harbor"}


def test_discover_on_an_empty_root_finds_nothing(tmp_path):
    assert discover(tmp_path) == {}


def test_nested_repositories_each_report_their_own_plans_once(tmp_path):
    _workspace(tmp_path)
    plans = scan_plans(tmp_path, discover(tmp_path))
    got = sorted((p["repo"], p["path"]) for p in plans)
    assert got == [
        ("orchard", "orchard/docs/superpowers/plans/2026-01-02-orchard-plan.md"),
        ("quarry", "quarry/.cursor/plans/quarry.plan.md"),
        (tmp_path.name, "docs/superpowers/plans/2026-01-01-root-plan.md"),
    ]


def test_a_plan_has_every_documented_key_and_its_date_and_title(tmp_path):
    _plan(tmp_path / "docs/superpowers/plans/2026-03-04-lantern.md", "- [x] a\n- [ ] b")
    _write(tmp_path / "docs/superpowers/plans/README.md", "# not a plan\n- [ ] x\n")
    plan = _one(tmp_path)
    assert KEYS <= plan.keys()
    assert (plan["file"], plan["date"], plan["title"]) == ("2026-03-04-lantern.md", "2026-03-04", "Lantern plan")
    assert (plan["total_steps"], plan["checked_steps"], plan["state"]) == (2, 1, "partial")
    assert plan["front_matter_status"] is None and plan["status_banner"] is None and plan["inconsistency"] is None


def test_the_front_matter_status_wins_over_the_checkboxes(tmp_path):
    cases = [
        ("completed", "- [ ] a", "done"),
        ("shipped", "- [ ] a", "done"),
        ("abandoned", "- [x] a", "superseded"),
        ("in-progress", "- [ ] a", "partial"),
        ("draft", "- [ ] a", "open"),
        ("planned", "- [x] a", "partial"),
        ("whatever", "- [x] a", "done"),
    ]
    for status, steps, expected in cases:
        path = _plan(tmp_path / "docs/superpowers/plans/2026-01-01-p.md", steps, front=status)
        plan = _one(tmp_path)
        assert (plan["front_matter_status"], plan["state"]) == (status, expected), status
        path.unlink()


def test_a_completed_plan_with_open_boxes_is_done_and_inconsistent(tmp_path):
    _plan(tmp_path / "docs/superpowers/plans/2026-01-01-p.md", "- [x] a\n- [ ] b", front="completed")
    plan = _one(tmp_path)
    assert plan["state"] == "done"
    assert plan["inconsistency"] == "front-matter says completed but 1/2 steps are flagged"


def test_an_open_plan_with_every_box_flagged_is_inconsistent(tmp_path):
    _plan(tmp_path / "docs/superpowers/plans/2026-01-01-p.md", "- [x] a", front="open")
    assert _one(tmp_path)["inconsistency"] == "front-matter says open but every step is flagged"


def test_a_completed_banner_without_front_matter_disagreeing_is_inconsistent(tmp_path):
    _plan(tmp_path / "docs/superpowers/plans/2026-01-01-p.md", "- [ ] a\n- [ ] b", head="\n**Status:** Completed 2026-01-05\n")
    plan = _one(tmp_path)
    assert plan["status_banner"] == "Completed 2026-01-05" and plan["state"] == "open"
    assert plan["inconsistency"] == "banner says completed but 0/2 steps are flagged"


def test_a_plan_without_boxes_or_status_has_no_boxes_and_no_inconsistency(tmp_path):
    _plan(tmp_path / "docs/superpowers/plans/2026-01-01-p.md", "Written after the fact.")
    plan = _one(tmp_path)
    assert (plan["state"], plan["total_steps"], plan["tasks"], plan["inconsistency"]) == ("empty", 0, [], None)


def test_a_plan_without_boxes_never_reports_an_inconsistency(tmp_path):
    _plan(tmp_path / "docs/superpowers/plans/2026-01-01-p.md", "Written after the fact.", front="draft",
          head="\n**Status:** Completed\n")
    plan = _one(tmp_path)
    assert plan["state"] == "open" and plan["inconsistency"] is None


def test_cancelled_steps_count_as_resolved_and_an_all_cancelled_task_is_cancelled(tmp_path):
    _write(tmp_path / "docs/superpowers/plans/2026-01-01-p.md", "# Kiln\n\n## Task 1: fire\n\n- [x] a\n- [-] b\n\n"
           "## Task 2: glaze\n\n- [-] a\n- [-] b\n\n## Task 3: cool\n\n- [ ] a\n- [-] b\n")
    plan = _one(tmp_path)
    assert [(t["name"], t["state"], t["checked"], t["cancelled"], t["total"]) for t in plan["tasks"]] == [
        ("fire", "done", 2, 1, 2), ("glaze", "cancelled", 2, 2, 2), ("cool", "partial", 1, 1, 2)]
    assert (plan["total_steps"], plan["checked_steps"], plan["state"]) == (6, 5, "partial")


def test_a_plan_whose_steps_are_all_cancelled_is_done(tmp_path):
    _plan(tmp_path / "docs/superpowers/plans/2026-01-01-p.md", "- [-] a")
    assert _one(tmp_path)["state"] == "done"


def test_a_plan_without_a_date_in_its_name_takes_its_modification_date(tmp_path):
    _plan(tmp_path / ".cursor/plans/kiln.plan.md", "- [ ] a")
    plan = _one(tmp_path)
    assert plan["date_source"] == "mtime" and len(plan["date"]) == 10


def test_evidence_counts_the_declared_files_that_exist(tmp_path):
    _write(tmp_path / "orchard/src/apple.py", "")
    _write(tmp_path / "orchard/docs/superpowers/plans/2026-01-01-p.md",
           "# Orchard\n\n## Task 1: pick\n\n**Files:**\n- Create: `src/apple.py`\n- Create: `src/pear.py`\n\n- [ ] a\n\n"
           "## Task 2: press\n\n**Files:**\n- Create: `src/apple.py`\n\n- [ ] a\n")
    pick, press = _one(tmp_path)["tasks"]
    assert (pick["files_found"], pick["files_total"], pick["files_missing"], pick["stale"]) == (1, 2, ["src/pear.py"], False)
    assert (press["files_found"], press["stale"]) == (1, True)
    plain = scan_plans(tmp_path, discover(tmp_path), evidence=False)[0]["tasks"][0]
    assert (plain["files_found"], plain["files_missing"]) == (0, [])



def test_a_file_the_task_deletes_is_not_evidence(tmp_path):
    _write(tmp_path / "orchard/src/apple.py", "")
    _write(tmp_path / "orchard/docs/superpowers/plans/2026-01-01-p.md",
           "# Orchard\n\n## Task 1: replant\n\n**Files:**\n- Create: `src/apple.py`\n- Delete: `src/stump.py`\n\n- [ ] a\n")
    task = _one(tmp_path)["tasks"][0]
    assert (task["files"], task["files_found"], task["stale"]) == (["src/apple.py"], 1, True)


def _specs(root: Path) -> list[dict]:
    repos = discover(root)
    return scan_specs(root, repos, scan_plans(root, repos, evidence=False))


def test_specs_take_one_of_four_states(tmp_path):
    specs = tmp_path / "docs/superpowers/specs"
    plans = tmp_path / "docs/superpowers/plans"
    _write(specs / "2026-01-01-kiln-design.md", "# Kiln\n")
    _write(specs / "2026-01-02-glaze-design.md", "# Glaze\n")
    _write(specs / "2026-01-03-clay.md", "# Clay notes\n\n**Plan:** not required\n")
    _write(specs / "2026-01-04-wheel.md", "# Wheel\n")
    _write(specs / "INDEX.md", "# Index\n")
    _plan(plans / "2026-01-01-kiln.md", "- [ ] a")
    _plan(plans / "2026-01-02-glaze-work.md", "- [ ] a\n\nSee 2026-01-02-glaze-design.md")
    found = {s["file"]: s for s in _specs(tmp_path)}
    assert {f: s["state"] for f, s in found.items()} == {
        "2026-01-01-kiln-design.md": "plan_uncited", "2026-01-02-glaze-design.md": "planned",
        "2026-01-03-clay.md": "reference", "2026-01-04-wheel.md": "unplanned"}
    kiln = found["2026-01-01-kiln-design.md"]
    assert kiln["sibling_plan"] == "docs/superpowers/plans/2026-01-01-kiln.md" and kiln["has_plan"] is True
    assert (found["2026-01-04-wheel.md"]["has_plan"], found["2026-01-03-clay.md"]["has_plan"]) == (False, False)
    assert (kiln["kind"], kiln["repo"], kiln["title"], kiln["path"]) == (
        "spec", tmp_path.name, "Kiln", "docs/superpowers/specs/2026-01-01-kiln-design.md")


def test_a_reference_marker_may_be_a_bullet_without_bold(tmp_path):
    _write(tmp_path / "docs/superpowers/specs/a.md", "# A\n- Plan: not required\n")
    assert _specs(tmp_path)[0]["state"] == "reference"


def test_a_spec_without_a_heading_is_titled_by_its_name(tmp_path):
    _write(tmp_path / "docs/superpowers/specs/a.md", "text\n")
    assert _specs(tmp_path)[0]["title"] == "a"


def _todos(root: Path, limit: int = 100) -> list[dict]:
    return scan_todos(root, discover(root), limit)


def test_markers_count_only_in_comments(tmp_path):
    _write(tmp_path / "docs/superpowers/plans/x.md", "- [ ] a")
    _write(tmp_path / "app.ts", "\n".join([
        "// TODO: sand the rim",
        "const a = 1; /* FIXME glaze runs */",
        "const s = 'see // TODO later';",
        'const t = "# XXX not work";',
        "const todo = 3; // todo lowercase prose",
        " * @todo document the kiln",
        "const label = `<!-- TODO in a template`;",
        "# XXX shell style",
    ]))
    got = [(t["line"], t["marker"], t["text"]) for t in _todos(tmp_path)]
    assert got == [(1, "TODO", "sand the rim"), (2, "FIXME", "glaze runs */"), (6, "@TODO", "document the kiln"),
                   (8, "XXX", "shell style")]
    assert _todos(tmp_path)[0].keys() >= {"kind", "repo", "marker", "path", "line", "text", "state"}


def test_excluded_directories_hidden_ones_nested_repos_and_other_extensions_are_skipped(tmp_path):
    _write(tmp_path / "docs/superpowers/plans/x.md", "- [ ] a")
    _write(tmp_path / "orchard/docs/superpowers/plans/y.md", "- [ ] a")
    for d in ("vendor", "node_modules", "dist", "public/build", "bootstrap/cache", ".hidden"):
        _write(tmp_path / d / "a.js", "// TODO skipped")
    _write(tmp_path / "other/bootstrap/cache/a.js", "// TODO kept: only the root level is excluded by path")
    _write(tmp_path / "notes.md", "<!-- TODO not source -->")
    _write(tmp_path / "scripts/plan-status.php", "// TODO the scanner itself")
    _write(tmp_path / "orchard/tree.vue", "<!-- TODO prune -->")
    _write(tmp_path / "root.sh", "# FIXME root")
    got = sorted((t["repo"], t["path"]) for t in _todos(tmp_path))
    assert got == sorted([(tmp_path.name, "other/bootstrap/cache/a.js"), (tmp_path.name, "root.sh"),
                          ("orchard", "orchard/tree.vue")])


def test_the_limit_stops_the_scan(tmp_path):
    _write(tmp_path / "docs/superpowers/plans/x.md", "- [ ] a")
    _write(tmp_path / "a.js", "// TODO 1\n// TODO 2\n// TODO 3\n")
    assert len(_todos(tmp_path, 2)) == 2


def test_markers_are_found_in_python_comments_but_not_in_python_strings(tmp_path):
    _write(tmp_path / "docs/superpowers/plans/x.md", "- [ ] a")
    _write(tmp_path / "a.py", '# TODO x\ns = "# TODO"\n')
    assert [(t["path"], t["line"], t["text"]) for t in _todos(tmp_path)] == [("a.py", 1, "x")]


def test_scan_todos_can_report_one_repository_without_walking_into_the_nested_ones(tmp_path):
    _workspace(tmp_path)
    _write(tmp_path / "root.sh", "# TODO root")
    _write(tmp_path / "orchard/o.sh", "# TODO orchard")
    repos = discover(tmp_path)
    assert [t["path"] for t in scan_todos(tmp_path, repos, 10, only=tmp_path.name)] == ["root.sh"]
    assert [t["path"] for t in scan_todos(tmp_path, repos, 10, only="orchard")] == ["orchard/o.sh"]


# ---- renderers and command line

def _backlog(root: Path) -> None:
    """One plan of every state, specs of every state and a marker, in two repositories."""
    _plan(root / "docs/superpowers/plans/2026-01-01-open-plan.md", "- [ ] a")
    _plan(root / "docs/superpowers/plans/2026-01-02-partial-plan.md", "- [x] a\n- [ ] b")
    _plan(root / "docs/superpowers/plans/2026-01-03-done-plan.md", "- [x] a",
          head="Spec: docs/superpowers/specs/2026-01-01-kiln-design.md")
    _plan(root / "docs/superpowers/plans/2026-01-04-old-plan.md", "- [ ] a", front="superseded")
    _write(root / "docs/superpowers/plans/2026-01-05-bare-plan.md", "# Bare plan\nno boxes here\n")
    _write(root / "docs/superpowers/specs/2026-01-01-kiln-design.md", "# Kiln\n")
    _write(root / "docs/superpowers/specs/2026-01-02-glaze.md", "# Glaze\n")
    _write(root / "docs/superpowers/specs/2026-01-03-ref.md", "# Ref\n**Plan: not required**\n")
    _write(root / "docs/superpowers/specs/2026-01-04-lathe-design.md", "# Lathe\n")
    _plan(root / "docs/superpowers/plans/2026-01-04-lathe.md", "- [ ] a")
    _plan(root / "orchard/docs/superpowers/plans/2026-02-01-orchard-plan.md", "- [ ] a\n- [ ] b")
    _write(root / "orchard/tree.ts", "// TODO prune the tree\n")


def _report(root: Path, **kw):
    return build_report(root, Options(**kw))


def _run(capsys, *argv) -> tuple[int, str, str]:
    code = main([str(a) for a in argv])
    out = capsys.readouterr()
    return code, out.out, out.err


def test_the_default_table_shows_only_open_work(tmp_path, capsys):
    _backlog(tmp_path)
    code, out, _ = _run(capsys, "--root", tmp_path)
    assert code == 0
    for shown in ("open-plan.md", "partial-plan.md", "bare-plan.md", "orchard-plan.md", "NO BOXES", "NO PLAN",
                  "2026-01-02-glaze.md"):
        assert shown in out
    for hidden in ("done-plan.md", "old-plan.md", "kiln-design.md", "ref.md", "SUPERSED", "DONE "):
        assert hidden not in out
    assert "Plans 7 (1 done, 1 partial, 3 open, 1 superseded)" in out
    assert "TODO" not in out


def test_the_default_narrows_a_plan_to_its_unfinished_tasks(tmp_path, capsys):
    _write(tmp_path / "docs/superpowers/plans/2026-01-01-two.md",
           "# Two\n## Task 1: first\n- [x] a\n## Task 2: second\n- [ ] b\n")
    _, out, _ = _run(capsys, "--root", tmp_path)
    assert "second" in out and "first" not in out
    _, out, _ = _run(capsys, "--root", tmp_path, "--all")
    assert "second" in out and "first" in out


def test_all_adds_finished_and_superseded_plans_and_planned_specs(tmp_path, capsys):
    _backlog(tmp_path)
    _, out, _ = _run(capsys, "--root", tmp_path, "--all")
    for shown in ("done-plan.md", "old-plan.md", "DONE", "SUPERSED", "open-plan.md", "bare-plan.md"):
        assert shown in out
    report = _report(tmp_path, all=True)
    assert {s["state"] for s in report["specs"]} == {"planned", "plan_uncited", "unplanned", "reference"}
    assert "kiln-design.md" in out and "SPECS WITH A PLAN" in out


def test_open_is_accepted_and_is_the_default(tmp_path, capsys):
    _backlog(tmp_path)
    _, default, _ = _run(capsys, "--root", tmp_path)
    code, explicit, _ = _run(capsys, "--root", tmp_path, "--open")
    assert code == 0 and explicit == default


def test_the_build_report_filters_plans_and_specs_by_default(tmp_path):
    _backlog(tmp_path)
    report = _report(tmp_path)
    assert sorted(p["state"] for p in report["plans"]) == ["empty", "open", "open", "open", "partial"]
    assert sorted(s["state"] for s in report["specs"]) == ["plan_uncited", "unplanned"]
    assert {s["state"] for s in report["specs"]} <= {"unplanned", "plan_uncited"}
    assert report["totals"]["plans"] == 7


def test_json_has_the_keys_of_the_php_report(tmp_path, capsys):
    _backlog(tmp_path)
    code, out, _ = _run(capsys, "--root", tmp_path, "--format", "json", "--kind", "plans,specs,todos")
    data = json.loads(out)
    assert code == 0
    assert data.keys() >= {"generated_at", "totals", "plans", "specs", "todos", "scope"}
    assert data["scope"] == "open"
    assert data["totals"].keys() >= {"plans", "plans_done", "plans_partial", "plans_open", "plans_superseded",
                                     "tasks_done", "tasks_partial", "tasks_open", "tasks_cancelled", "stale_tasks",
                                     "inconsistent_plans", "specs_unplanned", "specs_reference", "specs_plan_uncited",
                                     "todos"}
    assert KEYS <= data["plans"][0].keys()
    assert [t["text"] for t in data["todos"]] == ["prune the tree"]
    assert json.loads(render_json(_report(tmp_path), Options()))["scope"] == "open"
    all_data = json.loads(_run(capsys, "--root", tmp_path, "--format=json", "--all")[1])
    assert all_data["scope"] == "all" and len(all_data["plans"]) == 7


def test_repos_lists_each_repository_and_exits(tmp_path, capsys):
    _workspace(tmp_path)
    code, out, _ = _run(capsys, "--root", tmp_path, "--repos")
    assert code == 0
    assert out.splitlines() == [f"{tmp_path.name:<24} .", f"{'orchard':<24} orchard", f"{'quarry':<24} quarry"]


def test_summary_prints_one_line_per_plan_without_tasks(tmp_path, capsys):
    _backlog(tmp_path)
    _, full, _ = _run(capsys, "--root", tmp_path)
    _, short, _ = _run(capsys, "--root", tmp_path, "--summary")
    assert "light the lantern" in full and "light the lantern" not in short
    assert "open-plan.md" in short


def test_a_root_with_nothing_to_scan_prints_a_message_and_exits_zero(tmp_path, capsys):
    code, out, err = _run(capsys, "--root", tmp_path)
    assert code == 0 and "No plans or specs found" in out and err == ""
    assert _run(capsys, "--root", tmp_path, "--repos")[0] == 0
    assert _run(capsys, "--root", tmp_path, "--format", "json")[0] == 0


def test_an_invalid_root_fails(tmp_path, capsys):
    code, _, err = _run(capsys, "--root", tmp_path / "missing")
    assert code == 1 and "not a directory" in err


def test_bad_option_values_fail_with_a_message(tmp_path, capsys):
    _backlog(tmp_path)
    assert _run(capsys, "--root", tmp_path, "--format", "xml")[0] == 2
    assert _run(capsys, "--root", tmp_path, "--sort", "size")[0] == 2
    code, _, err = _run(capsys, "--root", tmp_path, "--repo", "nothing")
    assert code == 1 and "Unknown --repo=nothing" in err and "orchard" in err


def test_repo_filter_takes_a_unique_substring_and_keeps_the_specs_honest(tmp_path, capsys):
    _backlog(tmp_path)
    _plan(tmp_path / "orchard/docs/superpowers/plans/2026-02-02-cites.md", "- [ ] a",
          head="Spec: docs/superpowers/specs/x.md")
    _, out, _ = _run(capsys, "--root", tmp_path, "--repo", "orch", "--kind", "plans,todos")
    assert "orchard-plan.md" in out and "open-plan.md" not in out.replace("orchard-plan.md", "")
    assert "tree.ts" in out
    _, out, _ = _run(capsys, "--root", tmp_path, "--repo", "orchard", "--kind", "todos")
    assert "tree.ts" in out
    root_only = json.loads(_run(capsys, "--root", tmp_path, "--repo", tmp_path.name, "--kind", "todos",
                                "--format", "json")[1])
    assert root_only["todos"] == []


def test_plan_filters_by_file_name(tmp_path, capsys):
    _backlog(tmp_path)
    _, out, _ = _run(capsys, "--root", tmp_path, "--plan", "partial", "--kind", "plans")
    assert "partial-plan.md" in out and "open-plan.md" not in out


def test_kind_selects_the_sources(tmp_path):
    _backlog(tmp_path)
    report = build_report(tmp_path, Options(kinds=("plans",)))
    assert report["plans"] and report["specs"] == [] and report["todos"] == []
    report = build_report(tmp_path, Options(kinds=("todos",)))
    assert report["plans"] == [] and report["todos"]


def test_sort_orders_plans(tmp_path):
    _backlog(tmp_path)
    by = lambda s: [p["file"] for p in build_report(tmp_path, Options(sort=s))["plans"]]  # noqa: E731
    assert by("date")[0] == "2026-01-01-open-plan.md" and by("date")[-1] == "2026-02-01-orchard-plan.md"
    assert by("progress")[-1] == "2026-01-05-bare-plan.md" and by("progress")[-2] == "2026-01-02-partial-plan.md"
    assert by("repo")[0] == "2026-02-01-orchard-plan.md"


def test_stale_keeps_only_unflagged_tasks_whose_files_all_exist(tmp_path, capsys):
    _write(tmp_path / "src/kiln.py", "x")
    _write(tmp_path / "docs/superpowers/plans/2026-01-01-a.md",
           "# A\n## Task 1: built\n**Files:**\n- Create: `src/kiln.py`\n- [ ] a\n## Task 2: not built\n"
           "**Files:**\n- Create: `src/lathe.py`\n- [ ] b\n")
    _write(tmp_path / "docs/superpowers/specs/s.md", "# S\n")
    report = build_report(tmp_path, Options(stale=True))
    assert [t["name"] for p in report["plans"] for t in p["tasks"]] == ["built"]
    assert report["specs"] == [] and report["todos"] == []
    assert report["totals"]["stale_tasks"] == 1
    _, out, _ = _run(capsys, "--root", tmp_path, "--stale")
    assert "every declared file exists" in out and "unflagged task(s)" in out


def test_no_evidence_skips_the_filesystem_checks(tmp_path):
    _write(tmp_path / "src/kiln.py", "x")
    _write(tmp_path / "docs/superpowers/plans/2026-01-01-a.md",
           "# A\n## Task 1: built\n**Files:**\n- Create: `src/kiln.py`\n- [ ] a\n")
    task = build_report(tmp_path, Options(evidence=False))["plans"][0]["tasks"][0]
    assert task["files_found"] == 0 and task["stale"] is False


def test_inconsistencies_are_reported_in_the_table(tmp_path, capsys):
    _plan(tmp_path / "docs/superpowers/plans/2026-01-01-a.md", "- [ ] a\n- [x] b", front="completed")
    _plan(tmp_path / "docs/superpowers/plans/2026-01-02-b.md", "- [ ] a", front="in-progress")
    _, out, _ = _run(capsys, "--root", tmp_path, "--all")
    assert "status: completed" in out and "! front-matter says completed but 1/2 steps are flagged" in out
    assert "1 plan(s) disagree" in out


def test_todos_are_listed_only_when_asked(tmp_path, capsys):
    _backlog(tmp_path)
    _, out, _ = _run(capsys, "--root", tmp_path, "--kind", "todos", "--todo-limit", "5")
    assert "CODE MARKERS" in out and "orchard/tree.ts:1" in out


def test_style_box_uses_ascii_checkboxes_and_icon_uses_marks(tmp_path):
    _backlog(tmp_path)
    box = render_table(_report(tmp_path), Options(style="box"))
    icon = render_table(_report(tmp_path), Options(style="icon"))
    assert "[ ]" in box and "○" not in box
    assert "○" in icon and "[ ]" not in icon


def test_colors_wrap_the_state_labels_in_ansi_codes(tmp_path):
    _backlog(tmp_path)
    assert "\033[31mOPEN\033[0m" in render_table(_report(tmp_path), Options(colors=True))
    assert "\033" not in render_table(_report(tmp_path), Options(colors=False))


def test_the_table_never_exceeds_a_narrow_terminal(tmp_path):
    long = "a very long name for a task that goes on and on and on and on"
    _write(tmp_path / ("docs/superpowers/plans/2026-01-01-" + "long-" * 10 + "plan.md"),
           f"---\nstatus: in-progress\n---\n# T\n## Task 1: {long}\n**Files:**\n- Create: `a/b.py`\n- [ ] a\n")
    _write(tmp_path / ("docs/superpowers/specs/2026-01-01-" + "spec-" * 20 + ".md"), "# " + long + "\n")
    _write(tmp_path / "src.ts", "// TODO " + long * 2)
    for width in (30, 40, 60, 120):
        out = render_table(build_report(tmp_path, Options(kinds=("plans", "specs", "todos"), width=width)),
                           Options(width=width))
        assert max(len(line) for line in out.splitlines()) <= width, (width, out)
        assert "OPEN" in out or "PARTIAL" in out


def test_the_table_of_an_empty_selection_still_prints_the_totals(tmp_path, capsys):
    _plan(tmp_path / "docs/superpowers/plans/2026-01-01-a.md", "- [x] a")
    code, out, _ = _run(capsys, "--root", tmp_path)
    assert code == 0 and "Plans 1 (1 done" in out and "Nothing open" in out


def test_html_is_one_self_contained_page_with_escaped_text(tmp_path, capsys):
    _backlog(tmp_path)
    _write(tmp_path / "docs/superpowers/specs/2026-01-09-x.md", "# <script>alert(1)</script>\n")
    page = render_html(_report(tmp_path), Options())
    assert page.startswith("<!doctype html>") and "<script>alert(1)</script>" not in page
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in page
    assert "http://" not in page and "https://" not in page
    assert "open-plan.md" in page and "done-plan.md" not in page
    assert 'data-kind="spec"' in page and "NO BOXES" in page
    _, out, _ = _run(capsys, "--root", tmp_path, "--format", "html")
    assert out.startswith("<!doctype html>")


def test_out_writes_a_file_instead_of_stdout(tmp_path, capsys):
    _backlog(tmp_path)
    target = tmp_path / "out" / "backlog.json"
    code, out, _ = _run(capsys, "--root", tmp_path, "--format", "json", "--out", target)
    assert code == 0 and out == f"Written: {target}\n"
    assert json.loads(target.read_text())["totals"]["plans"] == 7


# ---- last change and documentation of finished plans


def _git(root: Path, *args: str, date: str = "2026-03-04T10:00:00") -> None:
    import os
    import subprocess

    env = {**os.environ, "GIT_AUTHOR_DATE": date, "GIT_COMMITTER_DATE": date}
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *args], cwd=root, env=env, check=True,
                   capture_output=True)


def test_last_change_is_the_last_commit_not_the_checkout_time(tmp_path):
    _git(tmp_path, "init", "-q")
    plan = _plan(tmp_path / "docs/superpowers/plans/2026-01-01-p.md", "- [ ] a")
    spec = _write(tmp_path / "docs/superpowers/specs/2026-01-01-s-design.md", "# S\n")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-q", "-m", "one", date="2026-03-04T10:00:00")
    plan.write_text(plan.read_text() + "- [ ] b\n")
    _git(tmp_path, "commit", "-q", "-am", "two", date="2026-05-06T10:00:00")
    report = build_report(tmp_path, Options(all=True))
    [p], [s] = report["plans"], report["specs"]
    assert (p["updated"], p["updated_source"]) == ("2026-05-06", "git")
    assert (s["updated"], s["updated_source"]) == ("2026-03-04", "git")


def test_an_uncommitted_or_untracked_file_takes_its_modification_date(tmp_path):
    from datetime import date

    _git(tmp_path, "init", "-q")
    plan = _plan(tmp_path / "docs/superpowers/plans/2026-01-01-p.md", "- [ ] a")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-q", "-m", "one")
    plan.write_text(plan.read_text() + "- [ ] b\n")
    _plan(tmp_path / "docs/superpowers/plans/2026-01-02-new.md", "- [ ] a")
    sources = {p["file"]: (p["updated"], p["updated_source"]) for p in scan_plans(tmp_path, discover(tmp_path))}
    today = date.today().isoformat()
    assert sources == {"2026-01-01-p.md": (today, "worktree"), "2026-01-02-new.md": (today, "worktree")}


def test_outside_git_the_last_change_is_the_modification_date_marked_as_such(tmp_path, capsys):
    _plan(tmp_path / "docs/superpowers/plans/2026-01-01-p.md", "- [ ] a")
    assert _one(tmp_path)["updated_source"] == "mtime"
    _, out, _ = _run(capsys, "--root", tmp_path)
    assert "~upd " in out


def test_sort_by_last_change_puts_the_most_recent_first(tmp_path):
    _git(tmp_path, "init", "-q")
    _plan(tmp_path / "docs/superpowers/plans/2026-01-01-old.md", "- [ ] a")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-q", "-m", "one", date="2026-03-04T10:00:00")
    old = tmp_path / "docs/superpowers/plans/2026-01-01-old.md"
    old.write_text(old.read_text() + "- [ ] b\n")
    _plan(tmp_path / "docs/superpowers/plans/2026-02-01-new.md", "- [ ] a")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-q", "-m", "two", date="2026-05-06T10:00:00")
    _plan(tmp_path / "docs/superpowers/plans/2026-03-01-untouched.md", "- [ ] a")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-q", "-m", "three", date="2026-04-01T10:00:00")
    files = [p["file"] for p in build_report(tmp_path, Options(sort="updated"))["plans"]]
    assert files[-1] == "2026-03-01-untouched.md" and set(files[:2]) == {"2026-01-01-old.md", "2026-02-01-new.md"}


def test_a_finished_plan_must_name_documentation_that_exists(tmp_path):
    _write(tmp_path / "docs/guide.md", "# Guide\n")
    plans = tmp_path / "docs/superpowers/plans"
    _plan(plans / "2026-01-01-named.md", "- [x] a", head="\n**Documented in:** `docs/guide.md`\n")
    _plan(plans / "2026-01-02-bare.md", "- [x] a")
    _plan(plans / "2026-01-03-broken.md", "- [x] a", head="\n**Documented in:** `docs/gone.md`, docs/guide.md\n")
    _plan(plans / "2026-01-04-none.md", "- [x] a", head="\n**Documented in:** none, internal refactor\n")
    _plan(plans / "2026-01-05-example.md", "- [x] a", head="\n```\n**Documented in:** `docs/guide.md`\n```\n")
    _plan(plans / "2026-01-06-open.md", "- [ ] a")
    found = {p["file"]: (p["documented_in"], p["docs_issue"]) for p in scan_plans(tmp_path, discover(tmp_path))}
    assert found["2026-01-01-named.md"] == (["docs/guide.md"], None)
    assert "no Documented in line" in found["2026-01-02-bare.md"][1]
    assert found["2026-01-03-broken.md"] == (["docs/gone.md", "docs/guide.md"], "documentation not found: docs/gone.md")
    assert found["2026-01-04-none.md"] == ([], None)
    assert "no Documented in line" in found["2026-01-05-example.md"][1]
    assert found["2026-01-06-open.md"] == ([], None)
    report = build_report(tmp_path, Options(all=True))
    assert report["totals"]["undocumented_plans"] == 3
    table = render_table(report, Options(all=True, width=120))
    assert "documentation not found: docs/gone.md" in table and "3 finished plan(s) do not point" in table
    assert "documentation not found" in render_html(report, Options(all=True))


def test_only_paths_on_the_documented_in_line_are_documents(tmp_path):
    _write(tmp_path / "Modules/Core/README.md", "# Core\n")
    _write(tmp_path / "Modules/Core/docs/rag/MODULE.md", "# Module\n")
    _plan(tmp_path / "docs/superpowers/plans/2026-01-01-p.md", "- [x] a",
          head="\n**Documented in:** `Modules/Core/README.md` (`AI_INDEX`, `meta['tuning']`, `ai:tune`), and\n"
               "`Modules/Core/docs/rag/MODULE.md` (*Search*).\n\nNext paragraph `docs/not-a-doc.md`.\n")
    plan = _one(tmp_path)
    assert plan["documented_in"] == ["Modules/Core/README.md", "Modules/Core/docs/rag/MODULE.md"]
    assert plan["docs_issue"] is None


def test_a_delivery_status_on_a_plan_that_is_not_closed_is_an_inconsistency(tmp_path):
    _plan(tmp_path / "docs/superpowers/plans/2026-01-01-p.md", "- [x] a\n- [ ] b\n\n## Delivery status (2026-01-02): built\n")
    _plan(tmp_path / "docs/superpowers/plans/2026-01-02-q.md", "- [ ] a\n\n```\n## Delivery status (date): example\n```\n")
    found = {p["file"]: p["inconsistency"] for p in scan_plans(tmp_path, discover(tmp_path))}
    assert found["2026-01-01-p.md"] == "delivery status written but the plan reads partial (1/2 steps flagged)"
    assert found["2026-01-02-q.md"] is None


def test_a_superseded_plan_with_every_step_resolved_is_consistent(tmp_path):
    _plan(tmp_path / "docs/superpowers/plans/2026-01-01-p.md", "- [x] a\n- [-] b (superseded)\n\n## Delivery status (2026-01-02): superseded\n",
          front="superseded")
    plan = _one(tmp_path)
    assert plan["state"] == "superseded" and plan["inconsistency"] is None


def test_plans_and_specs_in_subfolders_are_read_and_named_from_their_folder(tmp_path):
    _plan(tmp_path / "docs/superpowers/plans/lantern/2026-01-01-wick.md", "- [ ] a")
    _write(tmp_path / "docs/superpowers/plans/lantern/INDEX.md", "# index\n- [ ] not a plan\n")
    _write(tmp_path / "docs/superpowers/specs/lantern/2026-01-01-wick-design.md", "# Wick\n")
    _write(tmp_path / "docs/superpowers/specs/lantern/deep/2026-01-02-oil-design.md", "# Oil\n")
    plan = _one(tmp_path)
    assert (plan["file"], plan["path"]) == ("lantern/2026-01-01-wick.md", "docs/superpowers/plans/lantern/2026-01-01-wick.md")
    specs = scan_specs(tmp_path, discover(tmp_path), [plan])
    assert [(s["file"], s["state"]) for s in specs] == [
        ("lantern/2026-01-01-wick-design.md", "plan_uncited"),
        ("lantern/deep/2026-01-02-oil-design.md", "unplanned"),
    ]
