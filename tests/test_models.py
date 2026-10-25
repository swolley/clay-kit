import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
SCRIPTS = HERE.parent / "plugins/clay/scripts"
sys.path.insert(0, str(SCRIPTS))
import factory_plan  # noqa: E402
from models import AGENT_DEFAULTS, HOSTS, TIER_DEFAULTS, ModelsError, cross_config, resolve  # noqa: E402


def write_models(root: Path, data) -> None:
    (root / "factory").mkdir(exist_ok=True)
    text = data if isinstance(data, str) else json.dumps(data)
    (root / "factory/models.json").write_text(text)


def test_claude_defaults(tmp_path):
    assert resolve(tmp_path, "claude", tier="careful") == {"model": "opus", "effort": "high", "source": "tiers.md"}
    assert resolve(tmp_path, "claude", agent="reviewer-security") == {"model": "opus", "effort": "high", "source": "tiers.md"}
    assert resolve(tmp_path, "claude", agent="approver") == {"model": "sonnet", "effort": "high", "source": "tiers.md"}
    assert resolve(tmp_path, "claude", agent="approver", risky=True) == {"model": "opus", "effort": "high", "source": "tiers.md"}


def test_codex_without_file(tmp_path):
    assert resolve(tmp_path, "codex", tier="heavy") == {"model": None, "effort": "xhigh", "source": "session"}


def test_cursor_without_file(tmp_path):
    assert resolve(tmp_path, "cursor", tier="light") == {"model": None, "effort": None, "source": "session"}


def test_fable_off_claude_is_heavy(tmp_path):
    for host in ("codex", "cursor"):
        assert resolve(tmp_path, host, tier="fable") == resolve(tmp_path, host, tier="heavy")
    write_models(tmp_path, {"codex": {"tiers": {"fable": {"model": "x"}}}})
    assert resolve(tmp_path, "codex", tier="fable")["model"] == "x"
    assert resolve(tmp_path, "claude", tier="fable") == {"model": "fable", "effort": "high", "source": "tiers.md"}


def test_interface_reviewer_resolves_on_every_host(tmp_path):
    assert resolve(tmp_path, "claude", agent="reviewer-interface") == {"model": "sonnet", "effort": "medium", "source": "tiers.md"}
    for host in HOSTS:
        assert set(resolve(tmp_path, host, agent="reviewer-interface")) == {"model", "effort", "source"}
    write_models(tmp_path, {"codex": {"agents": {"reviewer-interface": {"model": "m"}}}})
    assert resolve(tmp_path, "codex", agent="reviewer-interface")["model"] == "m"


def test_partial_fable_entry_takes_effort_from_heavy(tmp_path):
    write_models(tmp_path, {"codex": {"tiers": {"fable": {"model": "x"}}}})
    assert resolve(tmp_path, "codex", tier="fable") == {"model": "x", "effort": "xhigh", "source": "models.json"}
    write_models(tmp_path, {"codex": {"tiers": {"fable": {"model": "x"}, "heavy": {"effort": "max"}}}})
    assert resolve(tmp_path, "codex", tier="fable") == {"model": "x", "effort": "max", "source": "models.json"}


def test_mapping_wins_per_key(tmp_path):
    write_models(tmp_path, {"codex": {"tiers": {"light": {"model": "m1"}}}})
    assert resolve(tmp_path, "codex", tier="light") == {"model": "m1", "effort": "low", "source": "models.json"}


def test_risky_approver_mapping(tmp_path):
    write_models(tmp_path, {"codex": {"agents": {"approver-risky": {"model": "big"}}}})
    assert resolve(tmp_path, "codex", agent="approver", risky=True)["model"] == "big"
    assert resolve(tmp_path, "codex", agent="approver")["model"] is None


@pytest.mark.parametrize(
    "data, host, kwargs, needle",
    [
        ("{not json", "claude", {"tier": "light"}, "models.json"),
        ({"curosr": {}}, "claude", {"tier": "light"}, "curosr"),
        ({"codex": {"tiers": {"hevy": {"model": "x"}}}}, "codex", {"tier": "light"}, "hevy"),
        ({"codex": {"agents": {"reviewer-cod": {"model": "x"}}}}, "codex", {"tier": "light"}, "reviewer-cod"),
        ({"claude": {"tiers": {"light": {"model": "gpt-x"}}}}, "claude", {"tier": "light"}, "gpt-x"),
        ({"claude": {"tiers": {"light": {"effort": "huge"}}}}, "claude", {"tier": "light"}, "huge"),
        ({"cursor": {"tiers": {"light": {"model": "auto"}}}}, "cursor", {"tier": "light"}, "auto"),
        ({"cursor": {"tiers": {"light": {"effort": "low"}}}}, "cursor", {"tier": "light"}, "cursor.tiers.light.effort"),
        ({"codex": {"tiers": {"light": {"model": ""}}}}, "codex", {"tier": "light"}, "codex.tiers.light.model"),
        ("", "claude", {"tier": "light"}, "models.json"),
        ([], "claude", {"tier": "light"}, "top level"),
        ("null", "claude", {"tier": "light"}, "top level"),
        ("3", "claude", {"tier": "light"}, "top level"),
        ({"claude": {"tiers": {"light": {"model": None}}}}, "claude", {"tier": "light"}, "claude.tiers.light.model"),
        ({"claude": {"tiers": {"light": {"model": 3}}}}, "claude", {"tier": "light"}, "claude.tiers.light.model"),
        ({"codex": {"tiers": {"light": {"effort": 3}}}}, "codex", {"tier": "light"}, "codex.tiers.light.effort"),
        ({"codex": {"tiers": {"light": {"modle": "x"}}}}, "codex", {"tier": "light"}, "modle"),
        ({"codex": {"agents": {"reviewer-ux": {"model": "x"}}}}, "codex", {"tier": "light"}, "reviewer-ux is now reviewer-interface"),
        ({"codex": {"agents": {"reviewer-ui": {"model": "x"}}}}, "codex", {"tier": "light"}, "reviewer-ui is now reviewer-interface"),
        ({"codex": {"agents": {"reviewer-uiux": {"model": "x"}}}}, "codex", {"tier": "light"}, "reviewer-uiux is now reviewer-interface"),
        ({"cross": {"builder_tiers": ["hevy"]}}, "claude", {"tier": "light"}, "cross.builder_tiers"),
        ({"cross": {"builder_tiers": [["light"]]}}, "claude", {"tier": "light"}, "cross.builder_tiers"),
        ({"cross": {"threshold": 0}}, "claude", {"tier": "light"}, "cross.threshold"),
        ({"cross": {"threshold": 101}}, "claude", {"tier": "light"}, "cross.threshold"),
        ({"cross": {"tiers": []}}, "claude", {"tier": "light"}, "cross.tiers"),
        (None, "claude", {"tier": "light", "agent": "approver"}, "tier"),
        (None, "claude", {}, "tier"),
        (None, "claude", {"tier": "hevy"}, "hevy"),
        (None, "claude", {"agent": "reviewer-cod"}, "reviewer-cod"),
        (None, "gemini", {"tier": "light"}, "gemini"),
        (None, "claude", {"tier": "light", "risky": True}, "--risky"),
        (None, "claude", {"agent": "reviewer-code", "risky": True}, "--risky"),
        (None, "codex", {"agent": "reviewer-interface", "risky": True}, "--risky"),
        (None, "claude", {"agent": "reviewer-spec", "risky": True}, "reviewer-final"),
    ],
)
def test_bad_input_raises(tmp_path, data, host, kwargs, needle):
    if data is not None:
        write_models(tmp_path, data)
    with pytest.raises(ModelsError, match=re.escape(needle)):
        resolve(tmp_path, host, **kwargs)


def test_cross_defaults(tmp_path):
    assert cross_config(tmp_path) == {"builder_tiers": [], "threshold": 80}


def test_cross_reads_the_block(tmp_path):
    write_models(tmp_path, {"cross": {"builder_tiers": ["light"], "threshold": 70}})
    assert cross_config(tmp_path) == {"builder_tiers": ["light"], "threshold": 70}
    assert resolve(tmp_path, "claude", tier="light")["model"] == "haiku"


def test_empty_object_is_a_no_op(tmp_path):
    before = resolve(tmp_path, "codex", tier="light")
    write_models(tmp_path, {})
    assert resolve(tmp_path, "codex", tier="light") == before


def test_effort_only_entry_keeps_effort_and_falls_back_for_model(tmp_path):
    write_models(tmp_path, {"claude": {"tiers": {"light": {"effort": "max"}}}, "codex": {"tiers": {"light": {"effort": "max"}}}})
    assert resolve(tmp_path, "claude", tier="light") == {"model": "haiku", "effort": "max", "source": "models.json"}
    assert resolve(tmp_path, "codex", tier="light") == {"model": None, "effort": "max", "source": "models.json"}


def parse_tables() -> tuple[dict, dict]:
    tiers, agents, section = {}, {}, None
    for line in (SCRIPTS.parent / "tiers.md").read_text().splitlines():
        if line.startswith("| Tier "):
            section = tiers
        elif line.startswith("| Agent "):
            section = agents
        elif not line.startswith("|"):
            section = None
        elif section is not None and not line.startswith("|--"):
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if section is tiers:
                section[cells[0]] = (cells[2], cells[3])
            else:
                section[cells[0]] = (cells[1], cells[2])
    return tiers, agents


def test_tiers_md_parity():
    tiers, agents = parse_tables()
    assert tiers and agents
    assert tiers == TIER_DEFAULTS
    assert set(TIER_DEFAULTS) == set(factory_plan.TIERS)
    split = ("approver", "approver-risky", "reviewer-final", "reviewer-final-risky")
    others = {k: v for k, v in AGENT_DEFAULTS.items() if k not in split}
    assert {k: v for k, v in agents.items() if k not in split} == others
    assert agents["reviewer-final"] == ("sonnet or opus, see below", "high")
    assert AGENT_DEFAULTS["approver"] == ("sonnet", "high")
    assert AGENT_DEFAULTS["approver-risky"] == ("opus", "high")


def run_cli(*args):
    return subprocess.run([sys.executable, str(SCRIPTS / "state.py"), "model", *args], capture_output=True, text=True)


def test_cli_risky_only_with_approver(tmp_path):
    for args in (("--tier", "light"), ("--agent", "reviewer-code")):
        bad = run_cli("--host", "claude", *args, "--risky", "--root", str(tmp_path))
        assert bad.returncode == 2 and "--risky" in json.loads(bad.stdout)["error"]
    ok = run_cli("--host", "claude", "--agent", "approver", "--risky", "--root", str(tmp_path))
    assert ok.returncode == 0 and json.loads(ok.stdout)["model"] == "opus"


def test_cli_exit_codes(tmp_path):
    ok = run_cli("--host", "codex", "--tier", "light", "--root", str(tmp_path))
    assert ok.returncode == 0
    assert json.loads(ok.stdout) == {"model": None, "effort": "low", "source": "session"}
    bad = run_cli("--host", "codex", "--tier", "nope", "--root", str(tmp_path))
    assert bad.returncode == 2
    assert "nope" in json.loads(bad.stdout)["error"]


def test_cli_typo_in_models_json_exits_2_and_names_the_key(tmp_path):
    write_models(tmp_path, {"codex": {"tiers": {"light": {"modle": "x"}}}})
    bad = run_cli("--host", "codex", "--tier", "light", "--root", str(tmp_path))
    assert bad.returncode == 2
    assert "codex.tiers.light.modle" in json.loads(bad.stdout)["error"]


def test_non_utf8_file_is_a_models_error(tmp_path):
    (tmp_path / "factory").mkdir()
    (tmp_path / "factory/models.json").write_bytes(b"\xff\xfe")
    with pytest.raises(ModelsError, match=re.escape("models.json")):
        resolve(tmp_path, "claude", tier="light")
    done = run_cli("--host", "claude", "--tier", "light", "--root", str(tmp_path))
    assert done.returncode == 2
    assert "models.json" in json.loads(done.stdout)["error"]


def test_agent_frontmatter_effort():
    agents = HERE.parent / "plugins/clay/agents"
    checked = []
    for name, (_model, effort) in AGENT_DEFAULTS.items():
        if name.endswith("-risky"):  # a variant of an agent, not an agent file
            continue
        fm = re.match(r"---\n(.*?)\n---\n", (agents / f"{name}.md").read_text(), re.S).group(1)
        assert re.search(rf"^effort: {effort}$", fm, re.M), name
        checked.append(name)
    assert sorted(checked) == sorted(["reviewer-code", "reviewer-interface", "reviewer-spec", "reviewer-security", "approver", "reviewer-final"])
    builder = (agents / "builder.md").read_text()
    assert "effort:" not in re.match(r"---\n(.*?)\n---\n", builder, re.S).group(1)


def test_final_reviewer_defaults(tmp_path):
    assert resolve(tmp_path, "claude", agent="reviewer-final") == {"model": "sonnet", "effort": "high", "source": "tiers.md"}
    assert resolve(tmp_path, "claude", agent="reviewer-final", risky=True) == {"model": "opus", "effort": "high", "source": "tiers.md"}


def test_final_reviewer_risky_mapping(tmp_path):
    write_models(tmp_path, {"codex": {"agents": {"reviewer-final-risky": {"model": "gpt-x"}}}})
    assert resolve(tmp_path, "codex", agent="reviewer-final", risky=True)["model"] == "gpt-x"
