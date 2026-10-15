import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
SCRIPTS = HERE.parent / "plugins/clay/scripts"
sys.path.insert(0, str(SCRIPTS))
from models import AGENT_DEFAULTS, HOSTS, TIER_DEFAULTS, ModelsError, resolve  # noqa: E402


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


def test_uiux_is_ux(tmp_path):
    for host in HOSTS:
        assert resolve(tmp_path, host, agent="reviewer-uiux") == resolve(tmp_path, host, agent="reviewer-ux")
    write_models(tmp_path, {"claude": {"agents": {"reviewer-ux": {"model": "opus"}}}, "codex": {"agents": {"reviewer-ux": {"model": "m"}}}})
    for host in HOSTS:
        assert resolve(tmp_path, host, agent="reviewer-uiux") == resolve(tmp_path, host, agent="reviewer-ux")
    assert resolve(tmp_path, "codex", agent="reviewer-uiux")["model"] == "m"


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
        ({"cursor": {"tiers": {"light": {"effort": "low"}}}}, "cursor", {"tier": "light"}, "effort"),
        ({"codex": {"tiers": {"light": {"model": ""}}}}, "codex", {"tier": "light"}, "codex.tiers.light.model"),
        (None, "claude", {"tier": "light", "agent": "approver"}, "tier"),
        (None, "claude", {}, "tier"),
        (None, "claude", {"tier": "hevy"}, "hevy"),
        (None, "claude", {"agent": "reviewer-cod"}, "reviewer-cod"),
        (None, "gemini", {"tier": "light"}, "gemini"),
    ],
)
def test_bad_input_raises(tmp_path, data, host, kwargs, needle):
    if data is not None:
        write_models(tmp_path, data)
    with pytest.raises(ModelsError, match=re.escape(needle)):
        resolve(tmp_path, host, **kwargs)


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
    others = {k: v for k, v in AGENT_DEFAULTS.items() if k not in ("approver", "approver-risky")}
    assert {k: v for k, v in agents.items() if k != "approver"} == others
    assert AGENT_DEFAULTS["approver"] == ("sonnet", "high")
    assert AGENT_DEFAULTS["approver-risky"] == ("opus", "high")


def run_cli(*args):
    return subprocess.run([sys.executable, str(SCRIPTS / "state.py"), "model", *args], capture_output=True, text=True)


def test_cli_exit_codes(tmp_path):
    ok = run_cli("--host", "codex", "--tier", "light", "--root", str(tmp_path))
    assert ok.returncode == 0
    assert json.loads(ok.stdout) == {"model": None, "effort": "low", "source": "session"}
    bad = run_cli("--host", "codex", "--tier", "nope", "--root", str(tmp_path))
    assert bad.returncode == 2
    assert "nope" in json.loads(bad.stdout)["error"]


def test_non_utf8_file_is_a_models_error(tmp_path):
    (tmp_path / "factory").mkdir()
    (tmp_path / "factory/models.json").write_bytes(b"\xff\xfe")
    with pytest.raises(ModelsError, match=re.escape("models.json")):
        resolve(tmp_path, "claude", tier="light")
    done = run_cli("--host", "claude", "--tier", "light", "--root", str(tmp_path))
    assert done.returncode == 2
    assert "models.json" in json.loads(done.stdout)["error"]
