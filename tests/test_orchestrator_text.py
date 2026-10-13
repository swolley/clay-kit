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
    assert "Completion" in read("skills/factory-task/SKILL.md")
    assert "Accept" in read("agents/approver.md") and "empty" in read("agents/approver.md")


def test_approve_warns_without_decision_and_points_to_rerun():
    t = read("skills/factory-approve/SKILL.md")
    assert "no decision.md" in t and "rerun" in t


def test_builder_can_ask_through_the_orchestrator():
    t = read("agents/builder.md")
    assert "STATUS: NEEDS_INPUT" in t and "recommended" in t


def test_questions_are_persisted_before_asking():
    t = read("reference/orchestrator.md")
    assert "questions-<k>.md" in t and "answers-<k>.md" in t and "waiting-input" in t


def test_no_answer_is_never_a_default():
    t = read("reference/orchestrator.md")
    assert "never apply a default" in t and "unrelated message" in t


def test_waiting_jobs_are_reasked_on_resume_and_status():
    t = read("reference/orchestrator.md")
    assert "| waiting-input" in t and "waiting for you" in t


def test_answer_command_exists_and_points_to_reference():
    t = read("skills/factory-answer/SKILL.md")
    assert "disable-model-invocation: true" in t and "reference/orchestrator.md" in t


def test_dashboard_marks_waiting_input():
    assert "waiting-input" in read("factory/dashboard.html")


def test_run_state_carries_task_counts_for_the_progress_band():
    t = read("reference/orchestrator.md")
    assert "`total`" in t and "`done`" in t and "each time a job lands" in t


def test_progress_mod_is_wired_into_the_plugin():
    import json

    assert json.loads(read("hooks/hooks.json"))["modules"] == ["./register.tsx"]
    assert json.loads(read(".claude-plugin/plugin.json"))["types"] == "./types/index.d.ts"
    reg = read("hooks/register.tsx")
    assert "factory-progress" in reg and "factory-agents" in reg
    assert "factory:progress" not in reg and "factory:agents" not in reg
    assert (PLUGIN / "types/index.d.ts").exists()


def test_job_state_carries_times_and_run_state_carries_the_task_list():
    t = read("reference/orchestrator.md")
    assert "`started`" in t and "`updated`" in t and "ISO 8601" in t
    assert "`tasks`" in t and "`after`" in t


def test_orchestrator_records_the_model_and_effort_of_each_agent():
    t = read("reference/orchestrator.md")
    assert "`agents` records" in t and "effort` you passed" in t
