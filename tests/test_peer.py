import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugins/clay/scripts"))
import peer  # noqa: E402
from peer import agent_tools, build_command, start, wait  # noqa: E402

# One fake for both CLIs: it reads the prompt from stdin, writes the file named after `WRITE `, records how it was called, and
# prints what FAKE_MODE asks for.
FAKE = f"""#!{sys.executable}
import json, os, subprocess, sys, time
prompt = sys.stdin.read()
for line in prompt.splitlines():
    if line.startswith("WRITE "):
        with open(line[6:], "w") as f:
            f.write("done\\n")
with open(os.environ["FAKE_CALLS"], "a") as f:
    f.write(json.dumps({{"argv": sys.argv, "cwd": os.getcwd()}}) + "\\n")
mode = os.environ.get("FAKE_MODE", "ok")
name = os.path.basename(sys.argv[0])
if mode == "ok" and name == "codex":
    print(json.dumps({{"type": "thread.started", "thread_id": "T1"}}))
    print(json.dumps({{"type": "event_msg", "payload": {{"type": "token_count", "rate_limits": {{"primary": {{"used_percent": 42.0, "resets_at": 1900000000}}}}}}}}))
    print(json.dumps({{"type": "turn.completed", "usage": {{"input_tokens": 100, "cached_input_tokens": 30, "output_tokens": 20}}}}))
elif mode == "ok":
    print(json.dumps({{"session_id": "S1", "is_error": False, "result": "fine", "usage": {{"input_tokens": 50, "output_tokens": 5, "cache_read_input_tokens": 400, "cache_creation_input_tokens": 30}}, "duration_ms": 9}}))
elif mode == "full":
    print(json.dumps({{"type": "thread.started", "thread_id": "T2"}}))
    print(json.dumps({{"type": "token_count", "rate_limits": {{"primary": {{"used_percent": 100.0, "resets_at": 1900000000}}}}}}))
    sys.exit(1)
elif mode in ("limit", "auth", "boom"):
    sys.stderr.write({{"limit": "You've hit your usage limit.", "auth": "Not logged in. Please run /login.", "boom": "boom"}}[mode] + "\\n")
    sys.exit(1)
elif mode == "spawn":
    child = subprocess.Popen(["sleep", "60"])
    with open(os.environ["FAKE_PIDFILE"], "w") as f:
        f.write(str(child.pid))
    time.sleep(60)
elif mode == "sleep":
    time.sleep(5)
"""


@pytest.fixture
def env(tmp_path, monkeypatch):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for name in ("codex", "claude"):
        (bin_dir / name).write_text(FAKE)
        (bin_dir / name).chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setenv("FAKE_CALLS", str(tmp_path / "calls.jsonl"))
    monkeypatch.setattr(peer, "POLL_SECONDS", 0.05)
    root, cwd, write = tmp_path / "repo", tmp_path / "wt", tmp_path / "repo/factory/jobs/J1"
    for d in (cwd, write):
        d.mkdir(parents=True)
    prompt = tmp_path / "prompt.md"
    prompt.write_text(f"Read the agent file.\nWRITE {write}/build.md\n")
    yield {"root": root, "cwd": cwd, "write": write, "prompt": prompt, "tmp": tmp_path}
    # No runner or CLI outlives its test: each status names the runner and, once the CLI runs, its process group.
    for path in (write / "peer").glob("*.status.json"):
        status = json.loads(path.read_text())
        for pgid in (status.get("pgid"), status.get("pid")):
            if isinstance(pgid, int) and pgid > 0:
                try:
                    os.killpg(pgid, signal.SIGKILL)
                except (ProcessLookupError, PermissionError):
                    pass
        if isinstance(status.get("pid"), int):
            try:
                os.waitpid(status["pid"], 0)
            except ChildProcessError:
                pass


def run(env, vendor="codex", role="builder", wait_s=10, **kw):
    out = start(env["root"], "J1", role, 1, vendor, str(env["cwd"]), str(env["write"]), str(env["prompt"]), **kw)
    assert out == {"ok": True, "run": f"{role}-r1"}
    return wait(env["root"], "J1", out["run"], timeout=wait_s)


def calls(env):
    return [json.loads(line) for line in (env["tmp"] / "calls.jsonl").read_text().splitlines()]


def alive(pid: int) -> bool:
    try:
        with open(f"/proc/{pid}/stat") as f:
            return f.read().rsplit(")", 1)[1].split()[0] != "Z"
    except FileNotFoundError:
        return False


def test_codex_run_is_done_with_usage(env):
    out = run(env, "codex")
    assert out["state"] == "done" and out["error"] is None
    assert out["session_id"] == "T1"
    assert out["tokens"] == 120
    assert out["rate_limits"]["used_percent"] == 42.0 and out["rate_limits"]["resets_at"] == 1900000000
    assert out["ms"] > 0
    assert (env["write"] / "build.md").read_text() == "done\n"
    peer_dir = env["write"] / "peer"
    assert json.loads((peer_dir / "builder-r1.status.json").read_text())["state"] == "done"
    assert "thread.started" in (peer_dir / "builder-r1.log").read_text()
    assert calls(env)[0]["cwd"] == str(env["cwd"])


def test_claude_run_is_done_with_usage(env):
    out = run(env, "claude", role="reviewer-code", resume="S0")
    assert out["state"] == "done" and out["error"] is None
    assert out["session_id"] == "S1"
    assert out["tokens"] == 485  # input, output and both cache counts
    assert out["rate_limits"] is None
    call = calls(env)[0]
    assert call["cwd"] == str(env["cwd"])
    assert call["argv"][call["argv"].index("--resume") + 1] == "S0"


@pytest.mark.parametrize("vendor,mode,error", [
    ("codex", "limit", "limit"),
    ("claude", "limit", "limit"),
    ("claude", "auth", "auth"),
    ("codex", "auth", "auth"),
    ("codex", "boom", "exit"),
    ("codex", "full", "limit"),
])
def test_errors_are_classified(env, monkeypatch, vendor, mode, error):
    monkeypatch.setenv("FAKE_MODE", mode)
    out = run(env, vendor)
    assert (out["state"], out["error"]) == ("failed", error)
    if mode == "full":
        assert out["rate_limits"]["used_percent"] == 100.0 and out["session_id"] == "T2"


def test_missing_cli(env, monkeypatch):
    empty = env["tmp"] / "empty"
    empty.mkdir()
    monkeypatch.setenv("PATH", str(empty))
    out = run(env, "codex")
    assert (out["state"], out["error"]) == ("failed", "missing")


def test_timeout_kills_the_process_group(env, monkeypatch):
    pidfile = env["tmp"] / "child.pid"
    monkeypatch.setenv("FAKE_MODE", "spawn")
    monkeypatch.setenv("FAKE_PIDFILE", str(pidfile))
    out = run(env, "codex", limit_seconds=1)
    assert (out["state"], out["error"]) == ("failed", "timeout")
    child = int(pidfile.read_text())
    deadline = time.time() + 3
    while alive(child) and time.time() < deadline:
        time.sleep(0.05)
    assert not alive(child)


def test_lost_runner(env):
    dead = subprocess.Popen(["true"])
    dead.wait()
    peer_dir = env["write"] / "peer"
    peer_dir.mkdir()
    (peer_dir / "builder-r1.status.json").write_text(json.dumps({"state": "running", "pid": dead.pid}))
    out = wait(env["root"], "J1", "builder-r1", timeout=5)
    assert (out["state"], out["error"]) == ("failed", "lost")


def test_wait_returns_running_at_its_timeout(env, monkeypatch):
    monkeypatch.setenv("FAKE_MODE", "sleep")
    began = time.monotonic()
    out = start(env["root"], "J1", "builder", 1, "codex", str(env["cwd"]), str(env["write"]), str(env["prompt"]))
    assert time.monotonic() - began < 1
    status = json.loads((env["write"] / "peer/builder-r1.status.json").read_text())
    assert status["state"] == "running" and status["pid"] > 0
    assert wait(env["root"], "J1", out["run"], timeout=1)["state"] == "running"
    status = json.loads((env["write"] / "peer/builder-r1.status.json").read_text())
    assert status["pid"] > 0 and status["pgid"] > 0 and alive(status["pgid"])  # the runner records the CLI's group


def test_lost_runner_takes_its_cli_with_it(env):
    dead = subprocess.Popen(["true"])
    dead.wait()
    orphan = subprocess.Popen(["sleep", "60"], start_new_session=True)
    peer_dir = env["write"] / "peer"
    peer_dir.mkdir()
    (peer_dir / "builder-r1.status.json").write_text(json.dumps({"state": "running", "pid": dead.pid, "pgid": orphan.pid}))
    out = wait(env["root"], "J1", "builder-r1", timeout=5)
    assert (out["state"], out["error"]) == ("failed", "lost")
    assert orphan.wait(timeout=3) == -signal.SIGKILL


def test_start_refuses_a_run_that_is_still_running(env):
    live = subprocess.Popen(["sleep", "60"])
    try:
        peer_dir = env["write"] / "peer"
        peer_dir.mkdir()
        (peer_dir / "builder-r1.status.json").write_text(json.dumps({"state": "running", "pid": live.pid}))
        with pytest.raises(peer.RunActive):
            start(env["root"], "J1", "builder", 1, "codex", str(env["cwd"]), str(env["write"]), str(env["prompt"]))
        args = ["start", "--root", str(env["root"]), "--job", "J1", "--role", "builder", "--round", "1", "--vendor", "codex",
                "--cwd", str(env["cwd"]), "--write", str(env["write"]), "--prompt-file", str(env["prompt"])]
        done = subprocess.run([sys.executable, peer.__file__, *args], capture_output=True, text=True)
        assert done.returncode == 2 and "error" in json.loads(done.stdout)
    finally:
        live.kill()
        live.wait()
    assert run(env, "codex")["state"] == "done"  # a dead runner's status is no obstacle


def test_wait_on_an_unknown_run_is_an_error(env):
    with pytest.raises(ValueError):
        wait(env["root"], "J1", "builder-r9", timeout=1)
    done = subprocess.run([sys.executable, peer.__file__, "wait", "--root", str(env["root"]), "--job", "J1", "--run", "builder-r9",
                           "--timeout", "1"], capture_output=True, text=True)
    assert done.returncode == 2 and "error" in json.loads(done.stdout)


def test_cli_start_and_wait(env, monkeypatch):
    script = Path(peer.__file__)
    base = ["--root", str(env["root"]), "--job", "J1"]
    started = subprocess.run([sys.executable, script, "start", *base, "--role", "approver", "--round", "2", "--vendor", "claude",
                              "--cwd", str(env["cwd"]), "--write", str(env["write"]), "--prompt-file", str(env["prompt"])],
                             capture_output=True, text=True, check=True)
    assert json.loads(started.stdout) == {"ok": True, "run": "approver-r2"}
    waited = subprocess.run([sys.executable, script, "wait", *base, "--run", "approver-r2", "--timeout", "10"],
                            capture_output=True, text=True, check=True)
    assert json.loads(waited.stdout)["state"] == "done"


def test_commands():
    codex = build_command("codex", "/wt", "/job", "gpt-5.5", "high", None, [], "/job/peer/last.md")
    for part in ("exec", "-C", "--add-dir", "-s", "workspace-write", "--json", "-o"):
        assert part in codex
    assert codex[-1] == "-"
    assert codex[codex.index("-m") + 1] == "gpt-5.5" and "model_reasoning_effort=high" in codex
    resumed = build_command("codex", "/wt", "/job", None, None, "T1", [], "/job/peer/last.md")
    assert "resume" in resumed and "T1" in resumed and "-m" not in resumed and resumed[-1] == "-"
    claude = build_command("claude", "/wt", "/job", "sonnet", "medium", None, ["Read", "Bash"], "/job/peer/last.md")
    for part in ("-p", "--output-format", "json", "--add-dir", "--allowedTools", "Read,Bash", "--permission-mode", "acceptEdits"):
        assert part in claude
    assert "--resume" not in claude
    assert "--allowedTools" not in build_command("claude", "/wt", "/job", None, None, "S1", [], "/x")
    for vendor in ("claude", "codex"):  # `inherit` is the session's model, which a CLI started on its own does not have
        cmd = build_command(vendor, "/wt", "/job", "inherit", None, None, [], "/x")
        assert "inherit" not in cmd and "--model" not in cmd and "-m" not in cmd
    for cmd in (codex, resumed, claude, build_command("claude", "/wt", "/job", None, None, "S1", ["Read"], "/x")):
        assert not any("dangerously" in part for part in cmd)


def test_builder_tools_include_bash():
    assert "Bash" in agent_tools("builder")
    assert agent_tools("no-such-agent") == []
