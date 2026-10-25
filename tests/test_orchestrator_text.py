from pathlib import Path

PLUGIN = Path(__file__).resolve().parent.parent / "plugins/clay"


def read(rel: str) -> str:
    return (PLUGIN / rel).read_text()


def reference() -> str:
    """The whole orchestrator reference, which is split in parts a command reads as it needs them."""
    return "\n".join(p.read_text() for p in sorted((PLUGIN / "reference").glob("*.md")))


def test_current_branch_routing_uses_diff_not_porcelain():
    t = (PLUGIN / "scripts/state.py").read_text()
    assert "git status --porcelain | " not in reference() and "ls-files" in t and "--exclude-standard" in t


def step_zero() -> str:
    return " ".join(read("reference/job-loop.md").split("0. **Once per run.**")[1].split("\n1. ")[0].split())


def test_jobs_folder_ignores_itself():
    assert "`state.py setup" in step_zero() and "ignored by git" in step_zero()


def test_dashboard_is_copied_next_to_jobs():
    assert "copies the dashboard" in step_zero()


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
    assert "total" in step_zero() and "`done`" in step_zero()
    assert "refreshes `done` in the run state" in read("reference/orchestrator.md").split("## Landing")[1]


def test_progress_mod_is_wired_into_the_plugin():
    import json

    assert json.loads(read("hooks/hooks.json"))["modules"] == ["./register.tsx"]
    assert json.loads(read(".claude-plugin/plugin.json"))["types"] == "./types/index.d.ts"
    reg = read("hooks/register.tsx")
    assert "factory-progress" in reg and "factory-agents" in reg
    assert "factory:progress" not in reg and "factory:agents" not in reg
    assert (PLUGIN / "types/index.d.ts").exists()


def test_orchestrator_records_the_model_and_effort_of_each_agent():
    flat = " ".join(read("reference/hosts.md").split())
    assert "`job.json` `agents` (`after-agent`, `agent`) records what was actually passed" in flat


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


def test_inline_mode_is_gone():
    assert not (PLUGIN / "reference/inline.md").exists()
    assert "inline.md" not in reference() and "# Inline mode" not in reference()
    for skill in ("factory-run", "factory-task"):
        t = read(f"skills/{skill}/SKILL.md")
        assert "[lean|full]" in t or "[lean]" in t, skill
        assert "inline was replaced by lean" in t, skill


def test_brainstorm_has_the_spec_reviewer_and_the_excuses_table():
    t = read("skills/factory-brainstorm/SKILL.md")
    assert "reviewer-spec" in t and "Thoughts that mean stop" in t
    assert "reviewer-spec" in read("tiers.md")
    assert "Write" not in read("agents/reviewer-spec.md").split("---")[1]


def test_completion_records_the_run_in_the_plan_and_cleans_the_local_jobs():
    t = reference()
    assert "Execution record" in t and "state.py clean" in t and "does not remove worktrees" in t


def test_landing_ticks_the_task_in_its_own_commit():
    landing = read("reference/orchestrator.md").split("## Landing")[1]
    assert "--task <n>" in landing and "--no-commit" in landing and "never closes the plan" in landing


def test_completion_closes_the_plan_with_its_documentation_and_never_deletes_it():
    t = read("reference/completion.md")
    assert "state.py close-plan" in t and "Documented in" in t and "Divergences" in t
    assert "The plan is never deleted" in t and "Never edit the documentation yourself" in t


def test_builder_keeps_documentation_and_records_deviations():
    t = read("agents/builder.md")
    assert "## Documentation" in t and "`Docs`" in t and "## Deviations" in t.split("## build.md")[1]


def test_code_review_blocks_stale_documentation():
    t = read("agents/reviewer-code.md")
    assert "Is the documentation still true?" in t and "`Docs: none`" in t and "## Deviations" in t


def test_plan_skill_asks_for_docs_and_keeps_index_without_status():
    t = read("skills/factory-plan/SKILL.md")
    assert "**Docs:**" in t and "none: <reason>" in t and "No status there" in t and "plan_status.py" in t


def parts_read_by(skill: str) -> set[str]:
    import re

    return set(re.findall(r"reference/([\w-]+\.md)", read(f"skills/{skill}/SKILL.md")))


def test_every_part_of_the_reference_is_listed_in_the_core_and_exists():
    import re

    listed = set(re.findall(r"^\| `([\w-]+\.md)` \|", read("reference/README.md"), re.M))
    present = {p.name for p in (PLUGIN / "reference").glob("*.md") if p.name != "README.md"}
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
    assert "questions.md" in t and "completion.md" in t
    for part in ("questions.md", "completion.md"):
        assert part not in "".join(f"reference/{x}" for x in parts_read_by("factory-run")), part


# The host parts are left out of the per-command shares: every command that spawns or asks reads them, and the word budget
# below caps what a run reads at the start, hosts.md and the host part included.
def test_the_small_commands_read_a_fraction_of_the_reference():
    size = {p.name: len(p.read_text()) for p in (PLUGIN / "reference").glob("*.md") if not p.name.startswith("hosts") and p.name != "README.md"}
    total = sum(size.values())
    for skill, limit in (("factory-unlock", 0.1), ("factory-status", 0.4), ("factory-approve", 0.6)):
        assert sum(size[n] for n in parts_read_by(skill) - {"hosts.md"}) < limit * total, skill


def words(rel: str) -> int:
    return len(read(rel).split())


def test_a_run_reads_at_most_4800_words_at_the_start():
    for skill in ("factory-run", "factory-task"):
        for host in ("claude", "codex", "cursor"):
            start = words(f"skills/{skill}/SKILL.md") + sum(words(f"reference/{p}") for p in parts_read_by(skill))
            assert start + words(f"reference/hosts-{host}.md") <= 4800, (skill, host)


def test_parts_have_no_shared_header():
    for p in (PLUGIN / "reference").glob("*.md"):
        assert "Part of the orchestrator reference" not in p.read_text(), p.name
    assert "`<repo>` means" in read("reference/orchestrator.md")
    for skill in ("factory-unlock", "factory-brainstorm", "factory-plan"):
        assert "`<repo>`" in read(f"skills/{skill}/SKILL.md"), skill


def test_job_json_is_written_only_by_the_script():
    t = read("reference/orchestrator.md")
    assert "written only by `state.py`" in t and '"id": "003-rate-limit"' not in t


def test_savvy_progress_is_gone():
    assert "savvy-progress" not in reference() and "savvy-progress" not in read("README.md")


def test_a_job_loop_spawns_only_the_lenses_to_rerun_and_hands_out_the_ready_made_diff():
    t = read("reference/job-loop.md")
    assert "`rerun`" in t and "`carried`" in t and "diff.patch" in t and "`Diff: <path>`" in t
    assert "Spawn the reviewers in `rerun`" in t and "`all_pass` counts the carried verdicts" in t


def test_agents_read_the_diff_file_and_the_recorded_checks():
    for agent in ("reviewer-code", "reviewer-security", "reviewer-interface", "approver"):
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


def test_interface_lenses_get_one_reviewer():
    loop = read("reference/job-loop.md")
    assert "`reviewer-interface`" in loop and "Lenses:" in loop and "role `interface`" in loop and "reviewer-uiux" not in loop
    agent = read("agents/reviewer-interface.md")
    assert "Lenses:" in agent and "review-<lens>.md" in agent and "\n## ux\n" in agent and "\n## ui\n" in agent
    tiers = read("tiers.md")
    assert "reviewer-interface" in tiers and "reviewer-uiux" not in tiers
    for old in ("reviewer-ux", "reviewer-ui", "reviewer-uiux"):
        assert not (PLUGIN / f"agents/{old}.md").exists(), old


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
    assert "close-plan" in skill and "clean" in skill
    for rel in ("reference/start.md", "reference/completion.md"):
        t = read(rel)
        assert "state.py adhoc" in t and "factory/jobs/_runs" in t, rel
    assert "`completion.md`" in read("reference/start.md").split("## Ad hoc task")[1]
    assert "close-plan" in read("reference/completion.md").split("For an ad hoc plan")[1].split("\n\n")[0]


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
    assert "recorded in `agents` are the ones actually passed" in flat
    assert "plan file is never edited" in flat


def test_tiers_say_fable_needs_confirmation():
    t = read("tiers.md")
    assert "never started without" in t and "confirmation" in t and "cost" in t


def test_plan_handover_names_every_fable_task():
    hand = read("skills/factory-plan/SKILL.md").split("## Hand over")[1]
    assert "fable" in hand and "every" in hand


HOST_SECTIONS = ("## Which host", "## Starting an agent", "## Model and effort", "## Asking the user")
HOST_PART_SECTIONS = ("## Starting an agent", "## Model and effort", "## Resuming an agent", "## Asking the user")
HOSTS = ("claude", "codex", "cursor")


def host_part(host: str) -> str:
    return read(f"reference/hosts-{host}.md")


def test_hosts_part_has_sections():
    t = read("reference/hosts.md")
    for heading in HOST_SECTIONS:
        assert f"\n{heading}\n" in t, heading
    assert [h for h in HOST_SECTIONS] == sorted(HOST_SECTIONS, key=t.index)
    assert "Read <plugin root>/agents/<role>.md and follow it as your instructions." in t
    flat = " ".join(t.split())
    assert "end the turn" in flat and "never apply a default" in flat.lower() and "longer than 3" in flat
    assert "state.py model --host <host>" in flat and "frontmatter" in flat
    assert "`hosts-<host>.md`" in flat


def test_each_host_has_its_own_part():
    for host in HOSTS:
        t = host_part(host)
        for heading in HOST_PART_SECTIONS:
            assert f"\n{heading}\n" in t, (host, heading)
    tools = {"claude": ("`Agent`", "`AskUserQuestion`", "`SendMessage`", "`subagent_tokens`"),
             "codex": ("`spawn_agent`", "`request_user_input`", "`send_input`", "`reasoning_effort`"),
             "cursor": ("`Task`", "`fast`", "`inherit`")}
    for host, names in tools.items():
        for name in names:
            assert name in host_part(host), (host, name)


def test_hosts_detection_is_an_ordered_check():
    flat = " ".join(read("reference/hosts.md").split())
    which = flat.split("## Which host")[1].split("##")[0]
    assert which.index("`AskUserQuestion`") < which.index("`spawn_agent`") < which.index("`Task`")
    assert "`Agent` or `AskUserQuestion` is Claude Code" in which
    assert "If none is present, say so in one line and stop" in which
    assert "SendMessage" not in which


def test_hosts_closes_codex_agents():
    flat = " ".join(host_part("codex").split())
    assert "`close_agent`" in flat and "once its file has been read" in flat


def test_hosts_handles_refused_spawn_on_thread_limit():
    flat = " ".join(host_part("codex").split())
    assert "`AgentLimitReached`) is not a failed agent" in flat
    assert "start the reviewers that did not fit and retry the refused spawn" in flat
    # the builder is the last thing closed: running reviewers are waited for first
    assert flat.index("`wait_agent` for the reviewers still running") < flat.index("only if no slot is free yet, close the builder")
    assert "a later round starts a fresh builder" in flat


def test_cursor_starts_a_fresh_builder():
    assert "fresh builder" in host_part("cursor")


def test_claude_part_holds_the_progress_band():
    assert "progress band" in host_part("claude")


def other_parts() -> dict[str, str]:
    texts = {p.name: p.read_text() for p in (PLUGIN / "reference").glob("*.md") if not p.name.startswith("hosts")}
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


def test_short_path_has_no_size_limit_and_the_approver_writes_the_code_review():
    assert "30 lines" not in reference() and "30 lines" not in read("tiers.md")
    lite = read("agents/approver.md").partition("## Lite jobs")[2].partition("\n## ")[0]
    assert "review-code.md" in lite and "CHANGES" in lite


def test_round_three_escalates_to_a_fresh_builder():
    t = reference()
    assert "state.py escalate" in t and "fresh builder" in t
    assert "escalat" in read("tiers.md")


def test_completion_runs_the_final_review_first():
    t = read("reference/completion.md")
    assert t.index("final-diff") < t.index("Documentation pass")
    for word in ("reviewer-final", "final-verdict", "--fix", "Scope: fix", "one task", "ad hoc"):
        assert word in t, word
    assert "-final.md" in read("reference/orchestrator.md")


def test_lean_reference_names_its_commands():
    t = read("reference/lean.md")
    for word in ("lean-check", "promote", "begin-job", "--lean", "lean_reason", "long", "session's model"):
        assert word in t, word


def test_run_and_task_read_the_lean_part():
    run, task = read("skills/factory-run/SKILL.md"), read("skills/factory-task/SKILL.md")
    for t in (run, task):
        hint = next(l for l in t.splitlines() if l.startswith("argument-hint:"))
        assert "lean.md" in t and "lean" in hint
    assert "full" in next(l for l in run.splitlines() if l.startswith("argument-hint:"))


def test_completion_reviews_any_run_with_a_lean_job():
    step = read("reference/completion.md").partition("1. **Final review.**")[2].partition("2. **Documentation pass.**")[0]
    assert "lean" in step and "one task" in step and "ad hoc" in step


def test_resume_sends_a_ready_lean_job_to_lean_check():
    assert "lean-check" in read("reference/start.md")


def test_a_builder_whose_agent_is_gone_is_replaced_on_any_host():
    resume = " ".join(read("reference/start.md").split("## Resume")[1].split("## Ad hoc task")[0].split())
    assert "any builder whose agent is gone, on any host" in resume


def test_the_claude_part_has_no_rule_for_other_hosts():
    assert "elsewhere" not in host_part("claude")


def test_the_job_json_fields_to_read_are_examples_and_name_build_round():
    flat = " ".join(read("reference/orchestrator.md").split())
    assert "fields such as" in flat and "`build_round`" in flat


def test_factory_task_keeps_inline_out_of_the_task_text():
    assert "as with a leading `lean`, which stays out of `--text` too" in read("skills/factory-task/SKILL.md")


def test_the_run_state_row_names_its_fields():
    row = next(l for l in read("reference/orchestrator.md").splitlines() if l.startswith("| `_runs/<plan-slug>.json`"))
    for field in ("mode", "integration branch", "`pace`", "`base`", "`final`"):
        assert field in row, field


def test_auto_pace_points_to_the_lock_release():
    auto = read("reference/job-loop.md").split("**Auto.**")[1].split("\n\n")[0]
    assert "`lock.md`" in auto


def test_readme_says_one_reviewer_judges_either_interface_lens():
    t = " ".join(read("README.md").split())
    assert "one interface reviewer judges ui, ux or both" in t and "combined reviewer" not in t


def test_peer_part_names_its_commands():
    t = read("reference/peer.md")
    for needle in ("state.py vendor", "peer.py start", "peer.py wait", "vendor-down", "--resume", "review not crossed", "vendor: null"):
        assert needle in t, needle


def test_run_skills_read_the_peer_part_only_when_on():
    for skill in ("factory-run", "factory-task"):
        assert "peer.md" in read(f"skills/{skill}/SKILL.md"), skill
        assert "peer.md" not in parts_read_by(skill), skill


def test_loop_asks_the_vendor_when_the_peer_is_on():
    import re

    loop = read("reference/job-loop.md")
    for n in ("2", "4", "6"):
        step = re.split(rf"^{n}\. \*\*", loop, flags=re.M)[1].split("\n" + str(int(n) + 1) + ". **")[0]
        assert "peer.md" in step, n
    done = read("reference/completion.md").split("1. **Final review.**")[1].split("2. **Documentation pass.**")[0]
    assert "peer.md" in done


def test_start_offers_the_peer():
    t = read("reference/start.md")
    assert "--cross" in t and "--host <host>" in t.split("Preconditions (run)")[1].split("2. Tell")[0]


def test_the_peer_is_recorded_per_agent():
    assert "`vendor`" in read("reference/hosts.md") and "`vendor`" in read("reference/job-loop.md")


def test_rework_and_answer_sessions_find_the_peer():
    for skill in ("factory-rework", "factory-answer"):
        assert "peer.md" in read(f"skills/{skill}/SKILL.md"), skill
        assert "peer.md" not in parts_read_by(skill), skill
    flat = " ".join(read("reference/peer.md").split())
    assert "outside the start" in flat.lower() and "peer: true" in flat
    step = " ".join(read("reference/job-loop.md").split("2. **Build.**")[1].split("\n3. **")[0].split())
    assert "outside the start" in step and "state.py vendor" in step
    assert "peer.md" in read("reference/questions.md").split("4. When answers exist")[1]


def test_review_not_crossed_is_only_for_reviews():
    sentence = next(s for s in " ".join(read("reference/peer.md").split()).split("- ") if "review not crossed" in s)
    assert "reviewer" in sentence and "approver" in sentence and "reviewer-final" in sentence
