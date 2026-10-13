import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from validate import validate  # noqa: E402

FM = "---\nname: {name}\ndescription: {desc}\n{extra}---\nSee STYLE.md.\n"


def write(root: Path, rel: str, text: str) -> None:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text)


def skill(name: str, extra: str = "") -> str:
    return FM.format(name=name, desc="d", extra=extra)


def make_scaffold(root: Path) -> None:
    write(root, ".claude-plugin/marketplace.json", json.dumps({"name": "k", "plugins": []}))
    write(root, "plugins/clay/.claude-plugin/plugin.json", json.dumps({"name": "clay"}))
    write(root, "plugins/clay/skills/factory-brainstorm/SKILL.md", skill("factory-brainstorm"))
    write(root, "plugins/clay/skills/factory-plan/SKILL.md", skill("factory-plan"))
    for cmd in ("factory-run", "factory-task", "factory-status", "factory-approve", "factory-rework", "factory-answer", "factory-unlock"):
        write(root, f"plugins/clay/skills/{cmd}/SKILL.md", skill(cmd, "disable-model-invocation: true\n") + "reference/orchestrator.md\n")
    write(root, "plugins/clay/agents/builder.md", skill("builder"))
    write(root, "plugins/clay/reference/orchestrator.md", "core\n")


def test_valid_scaffold_passes(tmp_path):
    make_scaffold(tmp_path)
    assert validate(tmp_path) == []


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
    write(tmp_path, "plugins/clay/agents/builder.md", skill("builder") + "Use superpowers:tdd\n")
    assert any("builder.md" in p and "superpowers:" in p for p in validate(tmp_path))


def test_missing_style_reference_fails(tmp_path):
    make_scaffold(tmp_path)
    write(tmp_path, "plugins/clay/agents/builder.md", "---\nname: builder\ndescription: d\n---\nno ref\n")
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
    write(tmp_path, "plugins/clay/skills/factory-unlock/SKILL.md", skill("factory-unlock", "disable-model-invocation: true\n") + "reference/lock.md\n")
    assert validate(tmp_path) == []
    write(tmp_path, "plugins/clay/skills/factory-unlock/SKILL.md", skill("factory-unlock", "disable-model-invocation: true\n") + "reference/lock.md reference/gone.md\n")
    assert any("factory-unlock/SKILL.md" in p and "gone.md" in p for p in validate(tmp_path))


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
