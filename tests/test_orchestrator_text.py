from pathlib import Path

PLUGIN = Path(__file__).resolve().parent.parent / "plugins/factory"


def read(rel: str) -> str:
    return (PLUGIN / rel).read_text()


def test_current_branch_routing_uses_diff_not_porcelain():
    t = read("reference/orchestrator.md")
    assert "git status --porcelain | " not in t and "git ls-files --others --exclude-standard" in t


def test_jobs_folder_ignores_itself():
    assert "factory/jobs/.gitignore" in read("reference/orchestrator.md")


def test_dashboard_is_copied_next_to_jobs():
    t = read("reference/orchestrator.md")
    assert "copy" in t.lower() and "factory/jobs/dashboard.html" in t


def test_parallel_only_when_declared():
    t = read("reference/orchestrator.md")
    assert "declared" in t and "plan order" in t


def test_adhoc_task_gets_completion_and_criterion():
    assert "Completion" in read("skills/task/SKILL.md")
    assert "Accept" in read("agents/approver.md") and "empty" in read("agents/approver.md")


def test_approve_warns_without_decision_and_points_to_rerun():
    t = read("skills/approve/SKILL.md")
    assert "no decision.md" in t and "rerun" in t
