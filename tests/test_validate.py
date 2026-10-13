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
    write(root, "plugins/factory/.claude-plugin/plugin.json", json.dumps({"name": "factory"}))
    write(root, "plugins/factory/skills/brainstorm/SKILL.md", skill("brainstorm"))
    write(root, "plugins/factory/skills/plan/SKILL.md", skill("plan"))
    for cmd in ("run", "task", "status", "approve", "rework"):
        write(root, f"plugins/factory/skills/{cmd}/SKILL.md", skill(cmd, "disable-model-invocation: true\n"))
    write(root, "plugins/factory/agents/builder.md", skill("builder"))


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
    write(tmp_path, "plugins/factory/skills/plan/SKILL.md", "---\nname: plan\n---\nSTYLE.md\n")
    assert any("plan/SKILL.md" in p and "description" in p for p in validate(tmp_path))


def test_superpowers_reference_fails(tmp_path):
    make_scaffold(tmp_path)
    write(tmp_path, "plugins/factory/agents/builder.md", skill("builder") + "Use superpowers:tdd\n")
    assert any("builder.md" in p and "superpowers:" in p for p in validate(tmp_path))


def test_missing_style_reference_fails(tmp_path):
    make_scaffold(tmp_path)
    write(tmp_path, "plugins/factory/agents/builder.md", "---\nname: builder\ndescription: d\n---\nno ref\n")
    assert any("builder.md" in p and "STYLE.md" in p for p in validate(tmp_path))


def test_command_skills_must_disable_model_invocation(tmp_path):
    make_scaffold(tmp_path)
    write(tmp_path, "plugins/factory/skills/run/SKILL.md", skill("run"))
    assert any("run/SKILL.md" in p and "disable-model-invocation" in p for p in validate(tmp_path))


def test_brainstorm_and_plan_must_allow_model_invocation(tmp_path):
    make_scaffold(tmp_path)
    write(tmp_path, "plugins/factory/skills/plan/SKILL.md", skill("plan", "disable-model-invocation: true\n"))
    assert any("plan/SKILL.md" in p and "disable-model-invocation" in p for p in validate(tmp_path))
