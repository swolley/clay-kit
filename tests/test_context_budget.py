"""Tests for the static context inventory (no host required)."""
import importlib.util
from pathlib import Path

MODULE = Path(__file__).resolve().parents[1] / "scripts/context_budget.py"
spec = importlib.util.spec_from_file_location("context_budget", MODULE)
context_budget = importlib.util.module_from_spec(spec)
spec.loader.exec_module(context_budget)


def test_inventory_separates_required_and_conditional(tmp_path):
    plugin = tmp_path / "clay"
    (plugin / "skills/factory-run").mkdir(parents=True)
    (plugin / "reference").mkdir()
    (plugin / "skills/factory-run/SKILL.md").write_text(
        "Read these parts: <plugin root>/reference/hosts.md, "
        "<plugin root>/reference/job-loop.md. "
        "Read `lean.md` only when needed."
    )
    for name in ("hosts.md", "job-loop.md", "lean.md", "hosts-claude.md", "hosts-codex.md", "hosts-cursor.md"):
        (plugin / "reference" / name).write_text("one two three")
    result = context_budget.inventory(plugin)["factory-run"]
    assert set(result["required"]) == {"hosts.md", "job-loop.md"}
    assert result["conditional"] == {"lean.md": 3}
    assert result["host_startup_words"]["claude"] == result["startup_words"] + 3


def test_inventory_is_read_only(tmp_path):
    plugin = tmp_path / "clay"
    (plugin / "skills/hello").mkdir(parents=True)
    (plugin / "skills/hello/SKILL.md").write_text("Hello world")
    before = sorted(str(p) for p in plugin.rglob("*"))
    result = context_budget.inventory(plugin)
    assert result["hello"]["startup_words"] == 2
    assert before == sorted(str(p) for p in plugin.rglob("*"))
