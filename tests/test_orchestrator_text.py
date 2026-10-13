from pathlib import Path

PLUGIN = Path(__file__).resolve().parent.parent / "plugins/clay"


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


def test_run_warns_about_tasks_that_may_already_be_implemented():
    t = read("reference/orchestrator.md")
    assert "--root" in t and "done_signals" in t and "already be implemented" in t


def test_no_undefined_build_check_step():
    assert "Build check" not in read("reference/orchestrator.md")


def test_job_json_is_written_after_the_worktree_exists():
    assert "before writing `job.json`" in read("reference/orchestrator.md") or "only then write `job.json`" in read("reference/orchestrator.md")


def test_job_records_head_and_build_round_for_resume():
    t = read("reference/orchestrator.md")
    assert "`head`" in t and "`build_round`" in t


def test_style_contract_does_not_point_outside_the_plugin():
    assert "docs/hosts.md" not in read("STYLE.md")


def test_spec_says_the_orchestrator_lands_the_job():
    spec = (PLUGIN.parent.parent / "docs/superpowers/specs/2026-10-13-factory-design.md").read_text()
    assert "clears a job to land" in spec and "**Approver** merges" not in spec


def test_arguments_are_resolved_with_the_helper_script():
    t = read("reference/orchestrator.md")
    assert "## Resolving arguments" in t and "resolve.py job" in t and "resolve.py plans" in t


def test_command_skills_resolve_their_argument():
    for skill in ("factory-approve", "factory-rework", "factory-answer", "factory-run"):
        assert "Resolving arguments" in read(f"skills/{skill}/SKILL.md"), skill


def test_run_is_guided_by_default_and_can_switch_to_auto():
    t = read("reference/orchestrator.md")
    assert "## Pace" in t and "`pace`" in t and "run the rest without asking" in t
    assert "approve as it stands" in t and "rework with a note" in t


def test_auto_pace_stops_with_the_ready_command():
    t = read("reference/orchestrator.md")
    assert "stops the run" in t and "/factory-approve <id>" in t


def test_skip_is_not_offered_in_current_branch_mode():
    assert "skip is not offered" in read("reference/orchestrator.md")


def test_verdicts_are_checked_in_their_own_step_before_the_next_agent():
    t = read("reference/orchestrator.md")
    assert "own step" in t and "never in the same message" in t


def test_a_reviewer_that_wrote_no_file_gets_one_more_try():
    t = read("reference/orchestrator.md")
    assert "wrote no file" in t and "one more time" in t


def test_spawn_limits_of_the_host_are_stated():
    t = read("reference/orchestrator.md")
    assert "does not accept an effort" in t and "leave `effort` empty" in t
    assert "agent id" in t


def test_light_and_medium_tiers_run_on_the_faster_model():
    t = read("tiers.md")
    assert "| light |" in t and "| medium |" in t
    rows = {line.split("|")[1].strip(): line for line in t.splitlines() if line.startswith("| ") and "|" in line[2:]}
    assert "sonnet" in rows["light"] and "sonnet" in rows["medium"]
    assert "opus" in rows["careful"] and "opus" in rows["heavy"]


def test_approver_model_depends_on_risk():
    t = read("tiers.md")
    assert "approver" in t and "sensitive" in t


def test_run_uses_the_state_script_for_bookkeeping():
    t = read("reference/orchestrator.md")
    for cmd in ("state.py new-job", "state.py route", "state.py verdicts", "state.py agent", "state.py land", "state.py stage"):
        assert cmd in t, cmd


def test_short_path_is_described_for_light_tasks():
    t = read("reference/orchestrator.md")
    assert "short path" in t and "`lite`" in t
    assert "Lite" in read("agents/approver.md")


def test_agent_usage_is_recorded_after_every_spawn():
    t = read("reference/orchestrator.md")
    assert "subagent_tokens" in t or "usage" in t
    assert "state.py agent" in t


def test_run_takes_a_lock_and_refuses_a_second_run_on_the_same_plan():
    t = read("reference/orchestrator.md")
    assert "## Run lock" in t and "state.py lock acquire" in t and "state.py lock release" in t
    assert "another run" in t and "stale" in t and "read-only" in t


def test_the_plan_is_ticked_by_the_script_after_the_lock_is_released_or_while_held():
    t = read("reference/orchestrator.md")
    assert "state.py tick-plan" in t


def test_commands_that_act_on_jobs_respect_the_lock():
    for skill in ("factory-approve", "factory-rework", "factory-answer"):
        assert "lock" in read(f"skills/{skill}/SKILL.md"), skill


def test_unlock_command_exists_and_is_manual_only():
    t = read("skills/factory-unlock/SKILL.md")
    assert "disable-model-invocation: true" in t and "reference/orchestrator.md" in t and "state.py lock" in t


def test_inline_mode_keeps_approver_and_reviewers_as_subagents():
    t = read("reference/orchestrator.md")
    assert "## Inline" in t and "tier `light`" in t and "stay subagents" in t
    assert "inline" in read("skills/factory-run/SKILL.md")


def test_brainstorm_has_the_spec_reviewer_and_the_excuses_table():
    t = read("skills/factory-brainstorm/SKILL.md")
    assert "reviewer-spec" in t and "Thoughts that mean stop" in t
    assert "reviewer-spec" in read("tiers.md")
    assert "Write" not in read("agents/reviewer-spec.md").split("---")[1]


def test_completion_records_the_run_in_the_plan_and_cleans_the_local_jobs():
    t = read("reference/orchestrator.md")
    assert "Execution record" in t and "state.py clean" in t and "does not\nremove worktrees" in t
