import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugins/clay/scripts"))
from plan_status import discover, scan_plans, scan_specs, scan_todos  # noqa: E402

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
    _plan(tmp_path / "docs/superpowers/plans/2026-01-01-p.md", "- [x] a", front="superseded")
    assert _one(tmp_path)["inconsistency"] == "front-matter says superseded but every step is flagged"


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
