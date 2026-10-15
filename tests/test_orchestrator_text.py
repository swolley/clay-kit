from pathlib import Path

PLUGIN = Path(__file__).resolve().parent.parent / "plugins/clay"


def read(rel: str) -> str:
    return (PLUGIN / rel).read_text()


def reference() -> str:
    """The whole orchestrator reference, which is split in parts a command reads as it needs them."""
    return "\n".join(p.read_text() for p in sorted((PLUGIN / "reference").glob("*.md")))


def test_current_branch_routing_uses_diff_not_porcelain():
    t = reference()
    assert "git status --porcelain | " not in t and "git ls-files --others --exclude-standard" in t


def test_jobs_folder_ignores_itself():
    assert "factory/jobs/.gitignore" in reference()


def test_dashboard_is_copied_next_to_jobs():
    t = reference()
    assert "copy" in t.lower() and "factory/jobs/dashboard.html" in t


def test_parallel_only_when_declared():
    t = reference()
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
    t = reference()
    assert "questions-<k>.md" in t and "answers-<k>.md" in t and "waiting-input" in t


def test_no_answer_is_never_a_default():
    t = reference()
    assert "never apply a default" in t and "unrelated message" in t


def test_waiting_jobs_are_reasked_on_resume_and_status():
    t = reference()
    assert "| waiting-input" in t and "waiting for you" in t


def test_answer_command_exists_and_points_to_reference():
    t = read("skills/factory-answer/SKILL.md")
    assert "disable-model-invocation: true" in t and "reference/" in t


def test_dashboard_marks_waiting_input():
    assert "waiting-input" in read("factory/dashboard.html")


def test_run_state_carries_task_counts_for_the_progress_band():
    t = reference()
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
    t = reference()
    assert "`started`" in t and "`updated`" in t and "ISO 8601" in t
    assert "`tasks`" in t and "`after`" in t


def test_orchestrator_records_the_model_and_effort_of_each_agent():
    t = reference()
    assert "`agents` records" in t and "effort` you passed" in t


def test_run_warns_about_tasks_that_may_already_be_implemented():
    t = reference()
    assert "--root" in t and "done_signals" in t and "already be implemented" in t


def test_no_undefined_build_check_step():
    assert "Build check" not in reference()


def test_job_json_is_written_after_the_worktree_exists():
    assert "before writing `job.json`" in reference() or "only then write `job.json`" in reference()


def test_job_records_head_and_build_round_for_resume():
    t = reference()
    assert "`head`" in t and "`build_round`" in t


def test_style_contract_does_not_point_outside_the_plugin():
    assert "docs/hosts.md" not in read("STYLE.md")


def test_spec_says_the_orchestrator_lands_the_job():
    spec = (PLUGIN.parent.parent / "docs/superpowers/specs/2026-10-13-factory-design.md").read_text()
    assert "clears a job to land" in spec and "**Approver** merges" not in spec


def test_arguments_are_resolved_with_the_helper_script():
    t = reference()
    assert "## Resolving a plan" in t and "## Resolving a job" in t and "resolve.py job" in t and "resolve.py plans" in t


def test_command_skills_resolve_their_argument():
    for skill in ("factory-approve", "factory-rework", "factory-answer"):
        assert "Resolving a job" in read(f"skills/{skill}/SKILL.md"), skill
    assert "Resolving a plan" in read("skills/factory-run/SKILL.md")


def test_run_is_guided_by_default_and_can_switch_to_auto():
    t = reference()
    assert "## Pace" in t and "`pace`" in t and "run the rest without asking" in t
    assert "approve as it stands" in t and "rework with a note" in t


def test_auto_pace_stops_with_the_ready_command():
    t = reference()
    assert "stops the run" in t and "/factory-approve <id>" in t


def test_skip_is_not_offered_in_current_branch_mode():
    assert "skip is not offered" in reference()


def test_verdicts_are_checked_in_their_own_step_before_the_next_agent():
    t = reference()
    assert "own step" in t and "never in the same message" in t


def test_a_reviewer_that_wrote_no_file_gets_one_more_try():
    t = reference()
    assert "wrote no file" in t and "one more time" in t


def test_spawn_limits_of_the_host_are_stated():
    t = reference()
    assert "does not accept an effort" in t and "leave `effort` empty" in t
    assert "agent id" in t


def test_light_and_medium_tiers_run_on_the_faster_model():
    t = read("tiers.md")
    assert "| light |" in t and "| medium |" in t
    rows = {line.split("|")[1].strip(): line for line in t.splitlines() if line.startswith("| ") and "|" in line[2:]}
    assert "haiku" in rows["light"] and "sonnet" in rows["medium"]
    assert "opus" in rows["careful"] and "opus" in rows["heavy"]


def test_approver_model_depends_on_risk():
    t = read("tiers.md")
    assert "approver" in t and "sensitive" in t


def test_run_uses_the_state_script_for_bookkeeping():
    t = reference()
    for cmd in ("state.py begin-job", "state.py route", "state.py verdicts", "state.py after-agent", "state.py land", "state.py stage"):
        assert cmd in t, cmd


def test_short_path_is_described_for_light_tasks():
    t = reference()
    assert "short path" in t and "`lite`" in t
    assert "Lite" in read("agents/approver.md")


def test_agent_usage_is_recorded_after_every_spawn():
    t = reference()
    assert "subagent_tokens" in t or "usage" in t
    assert "state.py agent" in t


def test_run_takes_a_lock_and_refuses_a_second_run_on_the_same_plan():
    t = reference()
    assert "# Run lock" in t and "state.py lock acquire" in t and "state.py lock release" in t
    assert "another run" in t and "stale" in t and "read-only" in t


def test_the_plan_is_ticked_by_the_script_after_the_lock_is_released_or_while_held():
    t = reference()
    assert "state.py tick-plan" in t


def test_commands_that_act_on_jobs_respect_the_lock():
    for skill in ("factory-approve", "factory-rework", "factory-answer"):
        assert "lock" in read(f"skills/{skill}/SKILL.md"), skill


def test_unlock_command_exists_and_is_manual_only():
    t = read("skills/factory-unlock/SKILL.md")
    assert "disable-model-invocation: true" in t and "reference/" in t and "state.py lock" in t


def test_inline_mode_keeps_approver_and_reviewers_as_subagents():
    t = reference()
    assert "# Inline mode" in t and "tier `light`" in t and "stay subagents" in t
    assert "inline" in read("skills/factory-run/SKILL.md")


def test_brainstorm_has_the_spec_reviewer_and_the_excuses_table():
    t = read("skills/factory-brainstorm/SKILL.md")
    assert "reviewer-spec" in t and "Thoughts that mean stop" in t
    assert "reviewer-spec" in read("tiers.md")
    assert "Write" not in read("agents/reviewer-spec.md").split("---")[1]


def test_completion_records_the_run_in_the_plan_and_cleans_the_local_jobs():
    t = reference()
    assert "Execution record" in t and "state.py clean" in t and "does not\nremove worktrees" in t


def parts_read_by(skill: str) -> set[str]:
    import re

    return set(re.findall(r"reference/([\w-]+\.md)", read(f"skills/{skill}/SKILL.md")))


def test_every_part_of_the_reference_is_listed_in_the_core_and_exists():
    import re

    listed = set(re.findall(r"^\| `([\w-]+\.md)` \|", read("reference/orchestrator.md"), re.M))
    present = {p.name for p in (PLUGIN / "reference").glob("*.md")}
    assert listed == present and len(present) > 1


def test_each_command_reads_only_the_parts_it_needs():
    assert parts_read_by("factory-unlock") == {"lock.md", "hosts.md"}
    assert parts_read_by("factory-status") == {"orchestrator.md", "commands.md"}
    assert parts_read_by("factory-approve") == {"orchestrator.md", "lock.md", "commands.md", "hosts.md"}
    assert {"job-loop.md", "start.md", "lock.md", "orchestrator.md"} <= parts_read_by("factory-run")
    assert {"job-loop.md", "start.md", "lock.md", "orchestrator.md"} <= parts_read_by("factory-task")
    assert {"job-loop.md", "commands.md", "lock.md", "questions.md"} <= parts_read_by("factory-answer")
    assert {"job-loop.md", "commands.md", "lock.md"} <= parts_read_by("factory-rework")


def test_the_parts_a_run_needs_only_sometimes_are_read_when_needed():
    t = read("skills/factory-run/SKILL.md")
    assert "questions.md" in t and "inline.md" in t and "completion.md" in t
    for part in ("questions.md", "inline.md", "completion.md"):
        assert part not in "".join(f"reference/{x}" for x in parts_read_by("factory-run")), part


# hosts.md is left out of the per-command shares: unlock reads it only to ask a question, and every command that spawns
# or asks needs it. So that it cannot grow unnoticed, the last assert caps hosts.md itself at 16% of the whole reference
# (about 13.8% when the cap was set, plus about 15% headroom).
def test_the_small_commands_read_a_fraction_of_the_reference():
    size = {p.name: len(p.read_text()) for p in (PLUGIN / "reference").glob("*.md") if p.name != "hosts.md"}
    total = sum(size.values())
    for skill, limit in (("factory-unlock", 0.1), ("factory-status", 0.4), ("factory-approve", 0.6)):
        assert sum(size[n] for n in parts_read_by(skill) - {"hosts.md"}) < limit * total, skill
    hosts = len(read("reference/hosts.md"))
    assert hosts < 0.16 * (total + hosts), "hosts.md grew past its cap"


def test_a_job_loop_spawns_only_the_lenses_to_rerun_and_hands_out_the_ready_made_diff():
    t = read("reference/job-loop.md")
    assert "`rerun`" in t and "`carried`" in t and "diff.patch" in t and "`Diff: <path>`" in t
    assert "Spawn the reviewers in `rerun`" in t and "`all_pass` counts the carried verdicts" in t


def test_agents_read_the_diff_file_and_the_recorded_checks():
    for agent in ("reviewer-code", "reviewer-security", "reviewer-ui", "reviewer-ux", "approver"):
        assert "`Diff:`" in read(f"agents/{agent}.md"), agent
    for agent in ("builder", "reviewer-code", "approver"):
        assert "<State command>" in read(f"agents/{agent}.md"), agent
    assert "verify" in read("agents/builder.md") and "--reuse" in read("agents/reviewer-code.md")
    approver = read("agents/approver.md")
    assert "current: true" in approver and "without `--reuse`" in approver and "carried" in approver


def test_the_composite_commands_replace_the_step_by_step_calls_in_the_loop():
    loop, start = read("reference/job-loop.md"), read("reference/start.md")
    assert "state.py begin-job" in loop and "state.py after-agent" in loop and "in one call" in loop
    assert "state.py preflight" in start and "`jobs`" in start and "`audit`" in start
    assert "state.py new-job" not in start and "factory_plan.py <plan> --repo <name> --root <repo>` prints it" in start


def test_a_round_that_needs_both_interface_lenses_spawns_one_combined_reviewer():
    loop = read("reference/job-loop.md")
    assert "`reviewer-uiux`" in loop and "`review-ux.md` and `review-ui.md`" in loop and "role `uiux`" in loop
    agent = read("agents/reviewer-uiux.md")
    assert "review-ux.md" in agent and "review-ui.md" in agent and "reviewer-ux.md" in agent and "reviewer-ui.md" in agent
    assert "reviewer-uiux" in read("tiers.md")


def test_tier_guidance_and_approver_rule():
    t = read("tiers.md")
    assert "## Choosing a tier" in t and "size alone never decides" in t.lower()
    rows = {line.split("|")[1].strip(): line for line in t.splitlines() if line.startswith("| ") and "|" in line[2:]}
    assert "haiku" in rows["light"] and "trial" in rows["light"] and "Findings" in t
    assert "`heavy` or `fable`" in t and "`careful`, `heavy` or `fable`" not in t
    assert "tiers.md" in reference()


def test_plan_skill_tier_bullet_points_to_tiers():
    t = read("skills/factory-plan/SKILL.md")
    assert "tiers.md" in t and "size alone" in t.lower()


def test_readme_mentions_haiku_trial_and_findings():
    t = read("README.md")
    assert "haiku" in t and "Findings" in t


def test_adhoc_task_makes_its_working_plan_with_state_adhoc():
    skill = read("skills/factory-task/SKILL.md")
    assert "Do not write a plan file" not in skill and "state.py adhoc" in skill
    assert "tier=" in skill.split("---")[1]
    assert "tick-plan" in skill and "clean" in skill
    for rel in ("reference/start.md", "reference/completion.md"):
        t = read(rel)
        assert "state.py adhoc" in t and "factory/jobs/_runs" in t, rel
    assert "tick-plan" in read("reference/start.md").split("## Ad hoc task")[1]


def test_readme_shows_the_tier_option_of_factory_task():
    assert "/factory-task tier=careful <text>" in read("README.md")


def test_run_asks_once_before_starting_fable_tasks():
    pre = read("reference/start.md").split("## Preconditions (run)")[1].split("## Resume")[0]
    flat = " ".join(pre.split())
    assert "question tool" in flat and "once" in flat and "resumed" in flat
    assert "`tier=fable`" in flat and "not asked again" in flat
    assert "${CLAUDE_PLUGIN_ROOT}" not in read("reference/start.md")
    # ordering: after the defaults line and after the already-done decision
    assert flat.index("defaults") < flat.index("already be done") < flat.index("fable")
    # skip rule
    assert "no task that will actually run has tier `fable`" in flat and "skipped" in flat
    assert "already-done" in flat and "is not asked about" in flat
    # the mapping of each option to a tier, labelled with what the model resolver prints on this host
    assert "on every host (it is about cost)" in flat
    assert "`heavy` (recommended) runs them as tier `heavy` (approver on its risky model)" in flat
    assert "`fable` as the plan says runs them as tier `fable`" in flat
    assert "lower to `careful` runs them as tier `careful` (the approver follows the normal risk rule)" in flat
    assert "`state.py model --host <host> --tier <tier>`" in flat
    assert "On Claude Code, with no `factory/models.json`, that reads `opus` with `xhigh`, `fable` with `high`" in flat and "`opus` with `high`" in flat
    assert "recorded in `agents` are the ones actually passed" in flat
    assert "plan file is never edited" in flat


def test_tiers_say_fable_needs_confirmation():
    t = read("tiers.md")
    assert "never started without" in t and "confirmation" in t and "cost" in t


def test_plan_handover_names_every_fable_task():
    hand = read("skills/factory-plan/SKILL.md").split("## Hand over")[1]
    assert "fable" in hand and "every" in hand


HOST_SECTIONS = ("## Which host", "## Starting an agent", "## Model and effort", "## Resuming an agent", "## Asking the user", "## Claude Code only")


def test_hosts_part_has_sections():
    t = read("reference/hosts.md")
    for heading in HOST_SECTIONS:
        assert f"\n{heading}\n" in t, heading
    assert [h for h in HOST_SECTIONS] == sorted(HOST_SECTIONS, key=t.index)
    assert "Read <plugin root>/agents/<role>.md and follow it as your instructions." in t
    for tool in ("`Agent`", "`spawn_agent`", "`Task`", "`AskUserQuestion`", "`request_user_input`", "`send_input`", "`SendMessage`"):
        assert tool in t, tool
    flat = " ".join(t.split())
    assert "end the turn" in flat and "never apply a default" in flat.lower() and "longer than 3" in flat
    assert "state.py model --host <host>" in flat and "frontmatter" in flat


def test_hosts_detection_is_an_ordered_check():
    flat = " ".join(read("reference/hosts.md").split())
    which = flat.split("## Which host")[1].split("| |")[0]
    assert which.index("`AskUserQuestion`") < which.index("`spawn_agent`") < which.index("`Task`")
    assert "`Agent` or `AskUserQuestion` is Claude Code" in which
    assert "If none is present, say so in one line and stop" in which
    assert "SendMessage" not in which


def test_hosts_closes_codex_agents():
    flat = " ".join(read("reference/hosts.md").split())
    assert "`close_agent`" in flat and "once its file has been read" in flat


def other_parts() -> dict[str, str]:
    texts = {p.name: p.read_text() for p in (PLUGIN / "reference").glob("*.md") if p.name != "hosts.md"}
    texts["STYLE.md"] = read("STYLE.md")
    return texts


def test_no_fixed_option_limit_outside_hosts():
    for name, text in other_parts().items():
        assert "at most 4" not in " ".join(text.split()), name


def test_sendmessage_only_in_hosts():
    for name, text in other_parts().items():
        assert "SendMessage" not in text, name
    for skill in (PLUGIN / "skills").glob("*/SKILL.md"):
        assert "SendMessage" not in skill.read_text(), skill.parent.name


def test_spawns_use_model_resolver():
    flat = " ".join(read("reference/job-loop.md").split())
    assert "state.py model --host <host>" in flat
    assert "--tier <tier>" in flat and "--agent reviewer-<lens>" in flat and "--agent approver" in flat and "--risky" in flat
    assert "with the model and effort of the task's tier in" not in flat and "The approver's model is in `tiers.md`" not in flat


def test_paths_carry_plugin_root():
    assert "Plugin root: <plugin root>" in read("reference/job-loop.md")
