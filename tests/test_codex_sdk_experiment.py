"""Offline tests: no Codex installation, account, network, or model calls."""
import importlib.util
import json
import subprocess
import sys
import time
import types
from pathlib import Path

import pytest

PATH = Path(__file__).resolve().parent.parent / "experiments/codex-sdk-peer/compare.py"
SPEC = importlib.util.spec_from_file_location("codex_peer_experiment", PATH)
mod = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(mod)


def test_cli_parses_session_usage_and_answer(monkeypatch, tmp_path):
    captured = {}

    def fake_run(cmd, **kwargs):
        captured.update(cmd=cmd, **kwargs)
        return subprocess.CompletedProcess(
            cmd, 0,
            "\n".join([
                json.dumps({"type": "thread.started", "thread_id": "thread-abc"}),
                json.dumps({"type": "item.completed", "item": {"type": "agent_message", "text": "Issue at x.py:3"}}),
                json.dumps({"type": "turn.completed", "usage": {"input_tokens": 14, "output_tokens": 8}}),
            ]), "",
        )

    monkeypatch.setattr(mod.subprocess, "run", fake_run)
    out = mod.cli_turn(tmp_path, "review this", None, None)
    assert captured["input"] == "review this"
    assert captured["cmd"][:7] == ["codex", "exec", "-C", str(tmp_path), "-s", "read-only", "--json"]
    assert out["session_id"] == "thread-abc"
    assert out["response"] == "Issue at x.py:3"
    assert out["usage"]["input_tokens"] == 14
    assert out["status"] == "completed"


def test_cli_resume_uses_the_saved_thread_and_same_sandbox(monkeypatch, tmp_path):
    captured = []

    def fake_run(cmd, **kwargs):
        captured.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, json.dumps(
            {"type": "item.completed", "item": {"type": "agent_message", "text": "same issue"}}
        ), "")

    monkeypatch.setattr(mod.subprocess, "run", fake_run)
    out = mod.cli_turn(tmp_path, "follow up", "thread-abc", "gpt-test")
    assert captured[0] == [
        "codex", "exec", "-C", str(tmp_path), "-s", "read-only", "--json",
        "-m", "gpt-test", "resume", "thread-abc", "-"
    ]
    assert out["session_id"] == "thread-abc"


def test_sdk_starts_and_resumes_without_a_real_runtime(monkeypatch, tmp_path):
    calls = []

    class Sandbox:
        read_only = "readonly"

    class ApprovalMode:
        deny_all = "deny_all"

    class FakeThread:
        id = "sdk-123"

        def run(self, prompt, **kwargs):
            calls.append(("run", prompt, kwargs))
            return types.SimpleNamespace(
                status="completed", error=None, final_response="remembered",
                usage={"input_tokens": 9, "output_tokens": 5},
            )

    class FakeCodex:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            pass

        def thread_start(self, **kwargs):
            calls.append(("start", kwargs))
            return FakeThread()

        def thread_resume(self, identifier, **kwargs):
            calls.append(("resume", identifier, kwargs))
            return FakeThread()

    monkeypatch.setitem(sys.modules, "openai_codex", types.SimpleNamespace(Codex=FakeCodex, Sandbox=Sandbox, ApprovalMode=ApprovalMode))
    first = mod.sdk_turn(tmp_path, "review", None, None)
    second = mod.sdk_turn(tmp_path, "followup", first["session_id"], None)
    assert first["session_id"] == second["session_id"] == "sdk-123"
    assert calls[0][0] == "start"
    assert calls[2] == ("resume", "sdk-123", {"cwd": str(tmp_path), "sandbox": "readonly", "approval_mode": "deny_all"})
    assert all(event[-1]["sandbox"] == "readonly" and event[-1]["approval_mode"] == "deny_all"
               for event in calls if event[0] == "run")


def test_start_then_resume_persists_two_turns_and_rejects_overwrite(monkeypatch, tmp_path, capsys):
    prompt = tmp_path / "prompt.md"
    prompt.write_text("review")
    state = tmp_path / "state.json"
    seen = []

    def fake_sdk(cwd, prompt, thread_id, model):
        seen.append(thread_id)
        return {"session_id": "sdk-1", "status": "completed", "error": None,
                "usage": {"input_tokens": 3}, "response": "result"}

    monkeypatch.setattr(mod, "sdk_turn", fake_sdk)
    args = ["sdk", "start", "--cwd", str(tmp_path), "--prompt-file", str(prompt), "--out", str(state)]
    assert mod.main(args) == 0
    assert mod.main(args[:2] + ["--cwd", str(tmp_path), "--prompt-file", str(prompt), "--out", str(tmp_path / "new.json")]) == 0
    with pytest.raises(SystemExit) as err:
        mod.main(args)
    assert err.value.code == 2
    args[1] = "resume"
    assert mod.main(args) == 0
    saved = json.loads(state.read_text())
    assert seen[-1] == "sdk-1"
    assert [turn["phase"] for turn in saved["turns"]] == ["start", "resume"]
    assert saved["session_id"] == "sdk-1"
    assert all("elapsed_ms" in turn for turn in saved["turns"])


def test_a_hanging_turn_is_aborted_and_leaves_no_state(monkeypatch, tmp_path, capsys):
    prompt = tmp_path / "prompt.md"
    prompt.write_text("review")
    state = tmp_path / "state.json"

    def hangs(cwd, prompt, thread_id, model):
        time.sleep(5)

    monkeypatch.setattr(mod, "sdk_turn", hangs)
    started = time.monotonic()
    code = mod.main(["sdk", "start", "--cwd", str(tmp_path), "--prompt-file", str(prompt),
                     "--out", str(state), "--timeout", "1"])
    assert code == 1
    assert time.monotonic() - started < 4
    assert not state.exists()
    assert "exceeded 1s" in capsys.readouterr().err
