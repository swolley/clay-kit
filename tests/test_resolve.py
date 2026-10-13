import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugins/clay/scripts"))
from resolve import list_plans, main, resolve_job  # noqa: E402

JOBS = [
    {"id": "001-add-slugify-helper", "task": 1, "stage": "committed"},
    {"id": "002-add-greeting-subtitle", "task": 2, "stage": "needs-human"},
    {"id": "003-extend-session-lifetime", "task": 3, "stage": "waiting-input"},
]
HUMAN = ("needs-human",)
BOTH = ("needs-human", "waiting-input")


def test_no_token_picks_the_only_eligible_job():
    match, cands, _ = resolve_job(None, JOBS, HUMAN)
    assert match["id"] == "002-add-greeting-subtitle" and cands == []


def test_no_token_with_several_candidates_returns_them_for_a_question():
    match, cands, _ = resolve_job("", JOBS, BOTH)
    assert match is None and [c["id"] for c in cands] == ["002-add-greeting-subtitle", "003-extend-session-lifetime"]


def test_full_id_three_digits_task_number_and_fragment_all_resolve():
    for token in ("002-add-greeting-subtitle", "002", "2", "subtitle"):
        match, _, _ = resolve_job(token, JOBS, BOTH)
        assert match and match["id"] == "002-add-greeting-subtitle", token


def test_a_job_that_is_not_eligible_is_not_matched():
    match, cands, reason = resolve_job("1", JOBS, HUMAN)
    assert match is None and cands == [] and "not" in reason


def test_ambiguous_fragment_returns_candidates():
    jobs = [{"id": "001-a-fix", "task": 1, "stage": "needs-human"}, {"id": "002-b-fix", "task": 2, "stage": "needs-human"}]
    match, cands, _ = resolve_job("fix", jobs, HUMAN)
    assert match is None and len(cands) == 2


def test_unknown_token_matches_nothing():
    match, cands, reason = resolve_job("zzz", JOBS, BOTH)
    assert match is None and cands == [] and reason


def _plan(root: Path, name: str, steps: str):
    d = root / "docs/superpowers/plans"
    d.mkdir(parents=True, exist_ok=True)
    (d / name).write_text(f"# Plan {name}\n\n### Task 1: A\n\n{steps}\n")


def test_list_plans_keeps_only_plans_with_open_steps(tmp_path):
    _plan(tmp_path, "2026-01-01-open.md", "- [ ] **Step 1: do**")
    _plan(tmp_path, "2026-01-02-done.md", "- [x] **Step 1: do**")
    plans = list_plans(tmp_path)
    assert [p["path"] for p in plans] == ["docs/superpowers/plans/2026-01-01-open.md"]
    assert plans[0]["open"] == 1 and plans[0]["tasks"] == 1


def test_cli_job_and_plans_print_json(tmp_path, capsys):
    base = tmp_path / "factory/jobs/002-x"
    base.mkdir(parents=True)
    (base / "job.json").write_text(json.dumps({"id": "002-x", "task": 2, "stage": "needs-human"}))
    assert main(["job", "2", "--stages", "needs-human", "--root", str(tmp_path)]) == 0
    assert json.loads(capsys.readouterr().out)["match"]["id"] == "002-x"
    _plan(tmp_path, "2026-01-01-open.md", "- [ ] **Step 1: do**")
    assert main(["plans", "--root", str(tmp_path)]) == 0
    assert json.loads(capsys.readouterr().out)[0]["open"] == 1
