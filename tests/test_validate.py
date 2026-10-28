import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from validate import validate  # noqa: E402

ROOT_SENTENCE = "Your plugin root is the `Plugin root:` line of your prompt; paths below written `<plugin root>/...` start there. If your prompt has no such line, say so in your reply and stop without doing the task."
ROOT_LINE = "Plugin root: ${CLAUDE_PLUGIN_ROOT}"
ROOT_FALLBACK = "If the line above does not show an absolute path, the plugin root is the folder two levels above the folder that holds this SKILL.md (the folder that contains skills/)."
ARGS_FALLBACK = "If the Arguments line still shows a placeholder that starts with $, the arguments are the text the user typed after the command name."
FM = "---\nname: {name}\ndescription: {desc}\n{extra}---\n"


def write(root: Path, rel: str, text: str) -> None:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text)


def agent(name: str) -> str:
    return FM.format(name=name, desc="d", extra="") + "See STYLE.md.\n"


def skill(name: str, extra: str = "", body: str = "") -> str:
    return FM.format(name=name, desc="d", extra=extra) + ROOT_LINE + "\n" + ROOT_FALLBACK + "\nSee STYLE.md.\n" + body


DESC = "d"
MANUAL = ("factory-run", "factory-task", "factory-status", "factory-approve", "factory-rework", "factory-answer", "factory-unlock")
OPENAI_YAML = "policy:\n  allow_implicit_invocation: false\n"
SPAWNING = ("factory-run", "factory-task", "factory-approve", "factory-rework", "factory-answer", "factory-unlock")


def put_json(root: Path, rel: str, data: dict) -> None:
    write(root, rel, json.dumps(data))


def make_scaffold(root: Path) -> None:
    put_json(root, ".claude-plugin/marketplace.json", {"name": "k", "plugins": [{"name": "clay", "source": "./plugins/clay", "description": DESC, "version": "0.1.0", "category": "skill"}]})
    put_json(root, "plugins/clay/.claude-plugin/plugin.json", {"name": "clay", "version": "0.1.0", "description": DESC})
    put_json(root, "plugins/clay/.codex-plugin/plugin.json", {"name": "clay", "version": "0.1.0", "description": DESC, "skills": "./skills/", "hooks": {"hooks": {}}, "interface": {"displayName": "Clay", "category": "skill"}})
    write(root, "plugins/clay/skills/factory-brainstorm/SKILL.md", skill("factory-brainstorm"))
    write(root, "plugins/clay/skills/factory-plan/SKILL.md", skill("factory-plan"))
    for cmd in MANUAL:
        hosts = "reference/hosts.md\n" if cmd in SPAWNING else ""
        write(root, f"plugins/clay/skills/{cmd}/SKILL.md", skill(cmd, "disable-model-invocation: true\n") + "reference/orchestrator.md\n" + hosts)
        write(root, f"plugins/clay/skills/{cmd}/agents/openai.yaml", OPENAI_YAML)
    write(root, "plugins/clay/agents/builder.md", agent("builder") + ROOT_SENTENCE + "\n")
    write(root, "plugins/clay/reference/orchestrator.md", "core\n")
    write(root, "plugins/clay/reference/hosts.md", "hosts\n")
    for host in ("claude", "codex"):
        write(root, f"plugins/clay/reference/hosts-{host}.md", f"{host}\n")


def test_valid_scaffold_passes(tmp_path):
    make_scaffold(tmp_path)
    assert validate(tmp_path) == []


def test_a_missing_host_part_fails(tmp_path):
    make_scaffold(tmp_path)
    (tmp_path / "plugins/clay/reference/hosts-codex.md").unlink()
    assert any("reference/hosts-codex.md" in p for p in validate(tmp_path))


def test_bad_json_fails_and_names_file(tmp_path):
    make_scaffold(tmp_path)
    write(tmp_path, ".claude-plugin/marketplace.json", "{nope")
    problems = validate(tmp_path)
    assert any(p.startswith(".claude-plugin/marketplace.json:") for p in problems)


def test_skill_without_description_fails(tmp_path):
    make_scaffold(tmp_path)
    write(tmp_path, "plugins/clay/skills/factory-plan/SKILL.md", "---\nname: plan\n---\nSTYLE.md\n")
    assert any("factory-plan/SKILL.md" in p and "description" in p for p in validate(tmp_path))


def test_superpowers_reference_fails(tmp_path):
    make_scaffold(tmp_path)
    write(tmp_path, "plugins/clay/agents/builder.md", agent("builder") + ROOT_SENTENCE + "\nUse superpowers:tdd\n")
    assert any("builder.md" in p and "superpowers:" in p for p in validate(tmp_path))


def test_missing_style_reference_fails(tmp_path):
    make_scaffold(tmp_path)
    write(tmp_path, "plugins/clay/agents/builder.md", "---\nname: builder\ndescription: d\n---\n" + ROOT_SENTENCE + "\n")
    assert any("builder.md" in p and "STYLE.md" in p for p in validate(tmp_path))


def test_command_skills_must_disable_model_invocation(tmp_path):
    make_scaffold(tmp_path)
    write(tmp_path, "plugins/clay/skills/factory-run/SKILL.md", skill("factory-run"))
    assert any("factory-run/SKILL.md" in p and "disable-model-invocation" in p for p in validate(tmp_path))


def test_brainstorm_and_plan_must_allow_model_invocation(tmp_path):
    make_scaffold(tmp_path)
    write(tmp_path, "plugins/clay/skills/factory-plan/SKILL.md", skill("factory-plan", "disable-model-invocation: true\n"))
    assert any("factory-plan/SKILL.md" in p and "disable-model-invocation" in p for p in validate(tmp_path))


def test_command_skill_must_read_orchestrator_reference(tmp_path):
    make_scaffold(tmp_path)
    write(tmp_path, "plugins/clay/skills/factory-run/SKILL.md", skill("factory-run", "disable-model-invocation: true\n"))
    assert any("factory-run/SKILL.md" in p and "reference/" in p for p in validate(tmp_path))


def test_orchestrator_reference_must_not_use_plugin_root_variable(tmp_path):
    make_scaffold(tmp_path)
    write(tmp_path, "plugins/clay/reference/orchestrator.md", "uses ${CLAUDE_PLUGIN_ROOT}/x\n")
    assert any("orchestrator.md" in p and "CLAUDE_PLUGIN_ROOT" in p for p in validate(tmp_path))
    write(tmp_path, "plugins/clay/reference/orchestrator.md", "core\n")
    write(tmp_path, "plugins/clay/reference/lock.md", "uses ${CLAUDE_PLUGIN_ROOT}/x\n")
    assert any("lock.md" in p and "CLAUDE_PLUGIN_ROOT" in p for p in validate(tmp_path))


def test_a_command_skill_may_read_several_parts_but_each_must_exist(tmp_path):
    make_scaffold(tmp_path)
    write(tmp_path, "plugins/clay/reference/lock.md", "lock\n")
    write(tmp_path, "plugins/clay/skills/factory-unlock/SKILL.md", skill("factory-unlock", "disable-model-invocation: true\n") + "reference/lock.md reference/hosts.md\n")
    assert validate(tmp_path) == []
    write(tmp_path, "plugins/clay/skills/factory-unlock/SKILL.md", skill("factory-unlock", "disable-model-invocation: true\n") + "reference/lock.md reference/hosts.md reference/gone.md\n")
    assert any("factory-unlock/SKILL.md" in p and "gone.md" in p for p in validate(tmp_path))


def test_manual_skill_pointing_to_a_missing_part_with_the_plugin_root_form_fails(tmp_path):
    make_scaffold(tmp_path)
    write(tmp_path, "plugins/clay/skills/factory-status/SKILL.md", skill("factory-status", "disable-model-invocation: true\n") + "Read <plugin root>/reference/orchestrator.md and <plugin root>/reference/gone.md\n")
    assert any("factory-status/SKILL.md" in p and "gone.md" in p for p in validate(tmp_path))
    write(tmp_path, "plugins/clay/skills/factory-status/SKILL.md", skill("factory-status", "disable-model-invocation: true\n") + "Read <plugin root>/reference/orchestrator.md\n")
    assert validate(tmp_path) == []


def test_spawning_skill_without_hosts_part_fails(tmp_path):
    make_scaffold(tmp_path)
    write(tmp_path, "plugins/clay/skills/factory-run/SKILL.md", skill("factory-run", "disable-model-invocation: true\n") + "reference/orchestrator.md\n")
    assert any(p.startswith("plugins/clay/skills/factory-run/SKILL.md:") and "reference/hosts.md" in p for p in validate(tmp_path))
    # a command that neither spawns nor asks needs no host part
    assert not any("factory-status" in p for p in validate(tmp_path))


def test_notice_requires_shipped_license_texts(tmp_path):
    make_scaffold(tmp_path)
    write(tmp_path, "plugins/clay/NOTICE.md", "derived")
    assert any("NOTICE.md" in p and "licenses" in p for p in validate(tmp_path))


def test_answer_skill_must_disable_model_invocation(tmp_path):
    make_scaffold(tmp_path)
    write(tmp_path, "plugins/clay/skills/factory-answer/SKILL.md", skill("factory-answer") + "reference/orchestrator.md\n")
    assert any("factory-answer/SKILL.md" in p and "disable-model-invocation" in p for p in validate(tmp_path))


def test_skill_name_must_match_its_folder(tmp_path):
    make_scaffold(tmp_path)
    write(tmp_path, "plugins/clay/skills/factory-plan/SKILL.md", skill("plan"))
    assert any("factory-plan/SKILL.md" in p and "name" in p and "folder" in p for p in validate(tmp_path))


def test_unlock_skill_must_disable_model_invocation(tmp_path):
    make_scaffold(tmp_path)
    write(tmp_path, "plugins/clay/skills/factory-unlock/SKILL.md", skill("factory-unlock") + "reference/orchestrator.md\n")
    assert any("factory-unlock/SKILL.md" in p and "disable-model-invocation" in p for p in validate(tmp_path))


def test_backlog_skill_must_disable_model_invocation(tmp_path):
    make_scaffold(tmp_path)
    write(tmp_path, "plugins/clay/skills/factory-backlog/SKILL.md", skill("factory-backlog") + "reference/orchestrator.md\n")
    assert any("factory-backlog/SKILL.md" in p and "disable-model-invocation" in p for p in validate(tmp_path))


def test_agent_with_plugin_root_variable_fails(tmp_path):
    make_scaffold(tmp_path)
    write(tmp_path, "plugins/clay/agents/builder.md", agent("builder") + ROOT_SENTENCE + "\n${CLAUDE_PLUGIN_ROOT}/STYLE.md\n")
    assert any(p.startswith("plugins/clay/agents/builder.md:") and "CLAUDE_PLUGIN_ROOT" in p for p in validate(tmp_path))


def test_agent_without_root_sentence_fails(tmp_path):
    make_scaffold(tmp_path)
    write(tmp_path, "plugins/clay/agents/builder.md", agent("builder"))
    assert any(p.startswith("plugins/clay/agents/builder.md:") and "Plugin root:" in p for p in validate(tmp_path))


def test_agent_root_sentence_after_first_heading_fails(tmp_path):
    make_scaffold(tmp_path)
    write(tmp_path, "plugins/clay/agents/builder.md", agent("builder") + "## What you are given\n" + ROOT_SENTENCE + "\n")
    assert any(p.startswith("plugins/clay/agents/builder.md:") and "before the first" in p for p in validate(tmp_path))
    write(tmp_path, "plugins/clay/agents/builder.md", agent("builder") + ROOT_SENTENCE + "\n## What you are given\nx\n")
    assert validate(tmp_path) == []


def test_agent_with_the_old_root_sentence_fails(tmp_path):
    make_scaffold(tmp_path)
    old = ROOT_SENTENCE.split(" If your prompt")[0]
    write(tmp_path, "plugins/clay/agents/builder.md", agent("builder") + old + "\n")
    assert any(p.startswith("plugins/clay/agents/builder.md:") and "Plugin root:" in p for p in validate(tmp_path))


def test_skill_without_root_lines_fails(tmp_path):
    make_scaffold(tmp_path)
    write(tmp_path, "plugins/clay/skills/factory-plan/SKILL.md", FM.format(name="factory-plan", desc="d", extra="") + "See STYLE.md.\n")
    assert any(p.startswith("plugins/clay/skills/factory-plan/SKILL.md:") and "Plugin root:" in p for p in validate(tmp_path))
    write(tmp_path, "plugins/clay/skills/factory-plan/SKILL.md", FM.format(name="factory-plan", desc="d", extra="") + ROOT_LINE + "\nSee STYLE.md.\n")
    assert any(p.startswith("plugins/clay/skills/factory-plan/SKILL.md:") and "Plugin root:" in p for p in validate(tmp_path))


def test_skill_with_second_plugin_root_fails(tmp_path):
    make_scaffold(tmp_path)
    write(tmp_path, "plugins/clay/skills/factory-plan/SKILL.md", skill("factory-plan", body="Follow ${CLAUDE_PLUGIN_ROOT}/STYLE.md.\n"))
    assert any(p.startswith("plugins/clay/skills/factory-plan/SKILL.md:") and "CLAUDE_PLUGIN_ROOT" in p for p in validate(tmp_path))


def test_skill_with_two_arguments_placeholders_fails(tmp_path):
    make_scaffold(tmp_path)
    body = "Arguments: $ARGUMENTS\n" + ARGS_FALLBACK + "\nRun x $ARGUMENTS\n"
    write(tmp_path, "plugins/clay/skills/factory-plan/SKILL.md", skill("factory-plan", body=body))
    assert any(p.startswith("plugins/clay/skills/factory-plan/SKILL.md:") and "$ARGUMENTS" in p for p in validate(tmp_path))


def test_skill_with_arguments_but_no_fallback_fails(tmp_path):
    make_scaffold(tmp_path)
    write(tmp_path, "plugins/clay/skills/factory-plan/SKILL.md", skill("factory-plan", body="Arguments: $ARGUMENTS\n"))
    assert any(p.startswith("plugins/clay/skills/factory-plan/SKILL.md:") and "Arguments line" in p for p in validate(tmp_path))
    write(tmp_path, "plugins/clay/skills/factory-plan/SKILL.md", skill("factory-plan", body="Arguments: $ARGUMENTS\n" + ARGS_FALLBACK + "\n"))
    assert validate(tmp_path) == []


def test_arguments_fallback_must_be_the_next_line_after_the_placeholder(tmp_path):
    make_scaffold(tmp_path)
    path = "plugins/clay/skills/factory-plan/SKILL.md"
    for body in (
        ARGS_FALLBACK + "\nArguments: $ARGUMENTS\n",
        "Arguments: $ARGUMENTS\nOther text.\n" + ARGS_FALLBACK + "\n",
        "Arguments: $ARGUMENTS\n" + "Other text. " + ARGS_FALLBACK + "\n",
    ):
        write(tmp_path, path, skill("factory-plan", body=body))
        assert any(p.startswith(path + ":") and "Arguments line" in p for p in validate(tmp_path)), body
    write(tmp_path, path, skill("factory-plan", body="Arguments: $ARGUMENTS\n\n" + ARGS_FALLBACK + "\n"))
    assert validate(tmp_path) == []


def test_skill_with_other_dollar_brace_variable_fails(tmp_path):
    make_scaffold(tmp_path)
    path = "plugins/clay/skills/factory-plan/SKILL.md"
    write(tmp_path, path, skill("factory-plan", body="Read ${CLAUDE_SKILL_DIR}/x.md\n"))
    assert any(p.startswith(path + ":") and "${" in p for p in validate(tmp_path))
    write(tmp_path, path, skill("factory-plan", body="Home is ${HOME}\n"))
    assert any(p.startswith(path + ":") and "${" in p for p in validate(tmp_path))


def test_skill_with_positional_argument_leftover_fails(tmp_path):
    make_scaffold(tmp_path)
    path = "plugins/clay/skills/factory-plan/SKILL.md"
    for body in ("The id is $1\n", "Text $9 here\n", "All: $ARGUMENTS[0]\n"):
        write(tmp_path, path, skill("factory-plan", body=body))
        assert any(p.startswith(path + ":") and ("$1" in p or "$ARGUMENTS[" in p) for p in validate(tmp_path)), body


def edit_json(root: Path, rel: str, **changes) -> None:
    data = json.loads((root / rel).read_text())
    data.update(changes)
    put_json(root, rel, data)


def test_missing_codex_manifest_fails(tmp_path):
    make_scaffold(tmp_path)
    (tmp_path / "plugins/clay/.codex-plugin/plugin.json").unlink()
    assert any(p.startswith("plugins/clay/.codex-plugin/plugin.json:") and "missing" in p for p in validate(tmp_path))



def test_version_mismatch_fails(tmp_path):
    make_scaffold(tmp_path)
    edit_json(tmp_path, "plugins/clay/.cursor-plugin/plugin.json", version="0.2.0")
    assert any("plugins/clay/.cursor-plugin/plugin.json" in p and "plugins/clay/.claude-plugin/plugin.json" in p and "version" in p for p in validate(tmp_path))


def test_codex_description_mismatch_fails(tmp_path):
    make_scaffold(tmp_path)
    edit_json(tmp_path, "plugins/clay/.codex-plugin/plugin.json", description="other")
    assert any("plugins/clay/.codex-plugin/plugin.json" in p and "description" in p for p in validate(tmp_path))






def test_codex_hooks_not_empty_inline_fails(tmp_path):
    make_scaffold(tmp_path)
    edit_json(tmp_path, "plugins/clay/.codex-plugin/plugin.json", hooks="./hooks/hooks.json")
    assert any(p.startswith("plugins/clay/.codex-plugin/plugin.json:") and "hooks" in p for p in validate(tmp_path))



def test_codex_path_without_dot_slash_fails(tmp_path):
    make_scaffold(tmp_path)
    edit_json(tmp_path, "plugins/clay/.codex-plugin/plugin.json", skills="skills/")
    assert any(p.startswith("plugins/clay/.codex-plugin/plugin.json:") and "./" in p for p in validate(tmp_path))


def test_codex_bare_dot_slash_path_fails(tmp_path):
    make_scaffold(tmp_path)
    edit_json(tmp_path, "plugins/clay/.codex-plugin/plugin.json", skills="./")
    assert any(p.startswith("plugins/clay/.codex-plugin/plugin.json:") and "./" in p for p in validate(tmp_path))


def test_codex_path_list_is_checked_entry_by_entry(tmp_path):
    make_scaffold(tmp_path)
    edit_json(tmp_path, "plugins/clay/.codex-plugin/plugin.json", skills=["./skills/", "more/"])
    assert any(p.startswith("plugins/clay/.codex-plugin/plugin.json:") and "./" in p for p in validate(tmp_path))
    edit_json(tmp_path, "plugins/clay/.codex-plugin/plugin.json", skills=["./skills/", "./"])
    assert any(p.startswith("plugins/clay/.codex-plugin/plugin.json:") and "./" in p for p in validate(tmp_path))
    edit_json(tmp_path, "plugins/clay/.codex-plugin/plugin.json", skills=["./skills/", "./more/"])
    assert validate(tmp_path) == []



def test_claude_marketplace_version_must_match_plugin_version(tmp_path):
    make_scaffold(tmp_path)
    edit_json(tmp_path, ".claude-plugin/marketplace.json", plugins=[{"name": "clay", "source": "./plugins/clay", "description": DESC, "version": "0.2.0", "category": "skill"}])
    assert any(p.startswith(".claude-plugin/marketplace.json:") and "version" in p and "0.2.0" in p for p in validate(tmp_path))


def test_codex_category_must_match_marketplace_entry(tmp_path):
    make_scaffold(tmp_path)
    edit_json(tmp_path, "plugins/clay/.codex-plugin/plugin.json", interface={"displayName": "Clay", "category": "other"})
    assert any(p.startswith("plugins/clay/.codex-plugin/plugin.json:") and "category" in p for p in validate(tmp_path))


def test_manual_skill_without_openai_yaml_fails(tmp_path):
    make_scaffold(tmp_path)
    (tmp_path / "plugins/clay/skills/factory-run/agents/openai.yaml").unlink()
    assert any("factory-run/agents/openai.yaml" in p and "missing" in p for p in validate(tmp_path))


def test_manual_skill_openai_yaml_must_disable_implicit_invocation(tmp_path):
    make_scaffold(tmp_path)
    write(tmp_path, "plugins/clay/skills/factory-run/agents/openai.yaml", "policy:\n  allow_implicit_invocation: true\n")
    assert any("factory-run/agents/openai.yaml" in p and "allow_implicit_invocation: false" in p for p in validate(tmp_path))


def test_openai_yaml_policy_line_must_be_a_real_line_under_policy(tmp_path):
    make_scaffold(tmp_path)
    path = "plugins/clay/skills/factory-run/agents/openai.yaml"
    for text in (
        "policy:\n  # allow_implicit_invocation: false\n",
        "# allow_implicit_invocation: false\n",
        "policy:\n  allow_implicit_invocation: true\n# allow_implicit_invocation: false\n",
        "allow_implicit_invocation: false\n",
        "policy:\nother:\n  allow_implicit_invocation: false\n",
        "policy:\n  note: allow_implicit_invocation: false\n",
        "policy:\n  other:\n    allow_implicit_invocation: false\n",
        "policy:\n  nested: x\n    allow_implicit_invocation: false\n",
        "policy: {allow_implicit_invocation: true}\n",
    ):
        write(tmp_path, path, text)
        assert any("factory-run/agents/openai.yaml" in p and "allow_implicit_invocation: false" in p for p in validate(tmp_path)), text
    for text in (
        OPENAI_YAML,
        "interface:\n  x: y\npolicy:\n  allow_implicit_invocation: false\n",
        "policy:\n    allow_implicit_invocation: false\n",
        "policy:\n  allow_implicit_invocation: false  # user only\n",
        "policy: {allow_implicit_invocation: false}\n",
    ):
        write(tmp_path, path, text)
        assert validate(tmp_path) == [], text


def test_auto_skill_with_openai_yaml_fails(tmp_path):
    make_scaffold(tmp_path)
    write(tmp_path, "plugins/clay/skills/factory-plan/agents/openai.yaml", OPENAI_YAML)
    assert any("factory-plan/agents/openai.yaml" in p for p in validate(tmp_path))
