#!/usr/bin/env python3
"""Standalone Codex Python SDK vs CLI comparison. Never called by clay's production runner.

Both transports run a read-only review. Sessions are kept separately to compare
a fresh second process resuming exactly the same first-turn conversation.
No automatic login, no API key handling, and no changes to the target repository.
"""
import argparse
import contextlib
import json
import signal
import subprocess
import sys
import time
from pathlib import Path


def _usage(value):
    """Preserve provider token counters without inventing equivalent costs."""
    if value is None:
        return None
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if hasattr(value, "__dataclass_fields__"):
        from dataclasses import asdict
        return asdict(value)
    if isinstance(value, dict):
        return value
    return {"reported": str(value)}


def sdk_turn(cwd: Path, prompt: str, thread_id: str | None, model: str | None):
    try:
        from openai_codex import ApprovalMode, Codex, Sandbox
    except ImportError as exc:
        raise RuntimeError("Missing openai-codex: install it in a dedicated venv") from exc

    with Codex() as client:
        # `codex exec` never asks for approval; deny_all gives the SDK the same behavior.
        kwargs = {"cwd": str(cwd), "sandbox": Sandbox.read_only, "approval_mode": ApprovalMode.deny_all}
        if model:
            kwargs["model"] = model
        thread = client.thread_resume(thread_id, **kwargs) if thread_id else client.thread_start(**kwargs)
        result = thread.run(prompt, sandbox=Sandbox.read_only, approval_mode=ApprovalMode.deny_all)
        status = getattr(result, "status", None)
        if hasattr(status, "value"):
            status = status.value
        return {
            "session_id": thread.id,
            "status": str(status) if status is not None else "unknown",
            "response": result.final_response,
            "usage": _usage(result.usage),
            "error": str(result.error) if result.error is not None else None,
        }


def cli_turn(cwd: Path, prompt: str, thread_id: str | None, model: str | None):
    # Keep the CLI sandbox equivalent to the SDK's read_only.
    cmd = ["codex", "exec", "-C", str(cwd), "-s", "read-only", "--json"]
    if model:
        cmd += ["-m", model]
    if thread_id:
        cmd += ["resume", thread_id]
    cmd += ["-"]
    try:
        proc = subprocess.run(cmd, input=prompt, capture_output=True, text=True, check=False)
    except FileNotFoundError as exc:
        raise RuntimeError("Codex CLI is missing from PATH") from exc
    session_id, usage, response, error = thread_id, None, None, None
    for line in proc.stdout.splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event.get("type") == "thread.started":
            session_id = event.get("thread_id") or session_id
        elif event.get("type") == "turn.completed":
            usage = event.get("usage")
        elif event.get("type") == "turn.failed":
            error = str(event.get("error"))
        elif event.get("type") == "item.completed":
            item = event.get("item") or {}
            if item.get("type") == "agent_message":
                response = item.get("text")
    if proc.returncode:
        error = error or (proc.stderr.strip()[-2000:] or "codex exec failed")
    return {
        "session_id": session_id, "status": "completed" if proc.returncode == 0 else "failed",
        "response": response, "usage": usage, "error": error, "exit_code": proc.returncode,
    }


@contextlib.contextmanager
def _deadline(seconds: int | None):
    """Abort a turn that hangs, for example when the network is down and the runtime retries forever."""
    if not seconds or not hasattr(signal, "SIGALRM"):
        yield
        return

    def expired(_signum, _frame):
        raise TimeoutError(f"turn exceeded {seconds}s")

    previous = signal.signal(signal.SIGALRM, expired)
    signal.alarm(seconds)
    try:
        yield
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, previous)


def execute(transport: str, cwd: Path, prompt: str, thread_id: str | None, model: str | None,
            timeout: int | None = None):
    start = time.monotonic()
    with _deadline(timeout):
        output = (sdk_turn if transport == "sdk" else cli_turn)(cwd, prompt, thread_id, model)
    output["elapsed_ms"] = round((time.monotonic() - start) * 1000)
    return output


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("transport", choices=["sdk", "cli"])
    parser.add_argument("phase", choices=["start", "resume"])
    parser.add_argument("--cwd", type=Path, required=True)
    parser.add_argument("--prompt-file", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True, help="separate state file for each transport")
    parser.add_argument("--timeout", type=int, default=900, help="seconds allowed per turn, 0 disables (default 900)")
    parser.add_argument("--model", help="omit to use the signed-in account's configured default")
    args = parser.parse_args(argv)
    cwd = args.cwd.resolve()
    if not cwd.is_dir():
        parser.error("--cwd must be a directory")
    if not args.prompt_file.is_file():
        parser.error("--prompt-file must exist")
    old = {}
    if args.phase == "resume":
        if not args.out.is_file():
            parser.error("resume needs a previous state file")
        old = json.loads(args.out.read_text())
        if old.get("transport") != args.transport or old.get("cwd") != str(cwd):
            parser.error("transport or cwd changed since the first phase")
        if not old.get("session_id"):
            parser.error("previous run has no session_id")
        if old.get("model") != args.model:
            parser.error("model changed since the first phase")
        if len(old.get("turns", [])) != 1:
            parser.error("resume expects exactly one earlier turn")
    elif args.out.exists():
        parser.error("start refuses to overwrite an existing experiment state")
    prompt = args.prompt_file.read_text()
    try:
        result = execute(args.transport, cwd, prompt, old.get("session_id"), args.model, args.timeout)
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}), file=sys.stderr)
        return 1
    ok = bool(result.get("session_id")) and not result.get("error") and result.get("status") in ("completed", "TurnStatus.completed")
    record = {
        "transport": args.transport, "cwd": str(cwd), "model": args.model,
        "session_id": result.get("session_id") or old.get("session_id"),
        "turns": old.get("turns", []) + [{
            "phase": args.phase, "prompt_file": str(args.prompt_file.resolve()),
            "elapsed_ms": result["elapsed_ms"], "usage": result.get("usage"),
            "status": result.get("status"), "error": result.get("error"),
            "response": result.get("response"),
        }],
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(record, indent=2) + "\n")
    print(json.dumps({"ok": ok, "transport": args.transport, "phase": args.phase,
                      "session_id": record["session_id"], "elapsed_ms": result["elapsed_ms"],
                      "usage": result.get("usage"), "error": result.get("error"),
                      "state_file": str(args.out)}))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
