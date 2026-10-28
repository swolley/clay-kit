#!/usr/bin/env python3
"""Runs one agent through the peer vendor's CLI (`codex exec` or `claude -p`) as a detached process, so a long build never hits the
host's command timeout.

Each command prints JSON. `start` returns at once; `wait` returns when the run ends, or at its timeout with state "running".
Either prints {"error": ...} and exits 2 for a run it cannot act on: `start` for one still running, `wait` for one never started.

  peer.py start --root DIR --job ID --role R --round N --vendor claude|codex --cwd DIR --write DIR --prompt-file F
                [--model M] [--effort E] [--resume SESSION] [--limit-seconds S]
  peer.py wait --root DIR --job ID --run R-rN [--timeout S]

A run's files are `<root>/factory/jobs/<job>/peer/<role>-r<N>.{log,status.json}`. `_run` is the runner `start` spawns: it runs
the CLI in its own process group with the prompt on stdin, records that group in the running status, kills the whole group at
the limit, and writes the final status. `wait` kills the group of a runner that died without one (`lost`).
"""
import argparse
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
VENDORS = ("claude", "codex")
LIMIT_PATTERNS = ("usage limit", "rate limit", "limit reached", "quota")
AUTH_PATTERNS = ("not logged in", "please log in", "unauthorized", "authentication")
SANDBOX_PATTERNS = ("sandbox is required", "failed to initialize", "sandbox can't", "sandbox cannot", "sandbox failed")
# The Claude peer's Bash runs in Claude Code's sandbox, as close as it gets to Codex's workspace-write: writes only in its working
# directory, the --add-dir folder and a temp dir, no network, no retry outside the sandbox, and no start at all without the sandbox.
CLAUDE_SANDBOX = {"sandbox": {"enabled": True, "failIfUnavailable": True, "allowUnsandboxedCommands": False,
                              "autoAllowBashIfSandboxed": True, "network": {"allowedDomains": []}}}
TIMEOUTS = {"builder": 3600}
CLAUDE_TOKENS = ("input_tokens", "output_tokens", "cache_read_input_tokens", "cache_creation_input_tokens")
DEFAULT_TIMEOUT = 1200
POLL_SECONDS = 1
GRACE_SECONDS = 2  # between SIGTERM and SIGKILL to the CLI's process group
NAME_RE = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_.-]*")
SESSION_MODEL = "inherit"  # the session's model: a CLI started on its own has no session to take it from, so it gets no model


class RunActive(ValueError):
    """A run name whose runner is still alive."""


def agent_tools(role: str) -> list[str]:
    """The `tools:` of an agent file's frontmatter, [] when the file or the line is missing."""
    try:
        text = (PLUGIN_ROOT / "agents" / f"{role}.md").read_text()
    except OSError:
        return []
    m = re.match(r"---\n(.*?)\n---\n", text, re.S)
    for line in (m.group(1).splitlines() if m else []):
        key, _, value = line.partition(":")
        if key.strip() == "tools":
            return [t.strip() for t in value.split(",") if t.strip()]
    return []


def build_command(vendor: str, cwd: str, write: str, model: str | None, effort: str | None, resume: str | None, tools: list[str],
                  last_message: str) -> list[str]:
    """The CLI's argument list; the prompt goes on stdin. Never a flag that bypasses the sandbox or the permission checks."""
    model = None if model == SESSION_MODEL else model
    if vendor == "codex":
        # `exec resume` takes no -C, -s or --add-dir of its own: the options go before the subcommand, the same for both.
        cmd = ["codex", "exec", "-C", cwd, "--add-dir", write, "-s", "workspace-write"]
        cmd += ["-m", model] if model else []
        cmd += ["-c", f"model_reasoning_effort={effort}"] if effort else []
        cmd += ["--json", "-o", last_message]
        cmd += ["resume", resume] if resume else []
        return cmd + ["-"]
    if vendor == "claude":
        cmd = ["claude", "-p"]
        cmd += ["--model", model] if model else []
        cmd += ["--effort", effort] if effort else []
        cmd += ["--output-format", "json", "--add-dir", write]
        cmd += ["--allowedTools", ",".join(tools)] if tools else []
        cmd += ["--permission-mode", "acceptEdits", "--settings", json.dumps(CLAUDE_SANDBOX)]
        return cmd + (["--resume", resume] if resume else [])
    raise ValueError(f"unknown vendor {vendor!r}")


def _events(output: str):
    for line in output.splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if isinstance(event, dict):
            yield event


def _find_limits(node):
    """The `rate_limits` object nearest the root of a parsed event, or None."""
    if isinstance(node, dict):
        if isinstance(node.get("rate_limits"), dict):
            return node["rate_limits"]
        children = node.values()
    elif isinstance(node, list):
        children = node
    else:
        return None
    return next((found for found in map(_find_limits, children) if found), None)


def _flat(limits: dict) -> dict | None:
    """{used_percent, resets_at} of the fullest window of a rate_limits object (flat, or Codex's primary/secondary)."""
    windows = [limits] if "used_percent" in limits else [limits.get("primary"), limits.get("secondary")]
    best = None
    for w in windows:
        used = w.get("used_percent") if isinstance(w, dict) else None
        if isinstance(used, bool) or not isinstance(used, (int, float)):
            continue
        if best is None or used > best["used_percent"]:
            best = {"used_percent": float(used), "resets_at": w.get("resets_at")}
    return best


def _usage_tokens(usage, keys=("input_tokens", "output_tokens")) -> int:
    if not isinstance(usage, dict):
        return 0
    values = (usage.get(k) for k in keys)
    return sum(int(v) for v in values if isinstance(v, (int, float)) and not isinstance(v, bool))


def parse_output(vendor: str, output: str) -> dict:
    """{session_id, tokens, rate_limits} from the CLI's output. tokens is input plus output as reported (Claude's cache reads and
    writes added, which it counts apart from its input; Codex's cached input is part of its input), 0 when nothing is."""
    session_id, tokens, rate_limits = None, 0, None
    for event in _events(output):
        if vendor == "codex":
            if event.get("type") == "thread.started" and event.get("thread_id"):
                session_id = event["thread_id"]
            elif event.get("type") == "turn.completed":
                tokens += _usage_tokens(event.get("usage"))
            limits = _find_limits(event)
            rate_limits = (limits and _flat(limits)) or rate_limits
        elif "session_id" in event or "usage" in event:  # claude prints one object; the last one wins
            session_id, tokens = event.get("session_id"), _usage_tokens(event.get("usage"), CLAUDE_TOKENS)
    return {"session_id": session_id, "tokens": tokens, "rate_limits": rate_limits}


def _error_text(output: str) -> str:
    """The parts of the output that report an error: plain lines (stderr) and error events, not the agent's own messages."""
    parts = []
    for line in output.splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            parts.append(line)
            continue
        if isinstance(event, dict) and ("error" in str(event.get("type", "")) or event.get("type") == "turn.failed" or event.get("is_error") is True):
            parts.append(line)
    return "\n".join(parts).lower()


def classify(vendor: str, returncode: int, output: str, rate_limits: dict | None) -> str | None:
    """None for a run that succeeded, else sandbox (Claude only), limit, auth or exit. `missing` and `timeout` are decided by the runner."""
    is_error = vendor == "claude" and any(e.get("is_error") is True for e in _events(output))
    if returncode == 0 and not is_error:
        return None
    if vendor == "codex" and rate_limits and (_flat(rate_limits) or {}).get("used_percent", 0) >= 100:
        return "limit"
    text = _error_text(output)
    if vendor == "claude" and any(p in text for p in SANDBOX_PATTERNS):
        return "sandbox"
    if any(p in text for p in LIMIT_PATTERNS):
        return "limit"
    if any(p in text for p in AUTH_PATTERNS):
        return "auth"
    return "exit"


def _paths(root, job: str, run: str) -> dict:
    folder = Path(root) / "factory" / "jobs" / job / "peer"
    return {"dir": folder, "log": folder / f"{run}.log", "status": folder / f"{run}.status.json", "last": folder / f"{run}.last.md"}


def _write_status(path: Path, status: dict) -> None:
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(status, indent=2) + "\n")
    os.replace(tmp, path)


def _read_status(path: Path) -> dict | None:
    try:
        status = json.loads(path.read_text())
    except (OSError, ValueError):
        return None
    return status if isinstance(status, dict) else None


def _alive(pid) -> bool:
    """True while a process exists and is not a zombie."""
    if isinstance(pid, bool) or not isinstance(pid, int) or pid <= 0:
        return False
    try:
        with open(f"/proc/{pid}/stat") as f:
            return f.read().rsplit(")", 1)[1].split()[0] != "Z"
    except FileNotFoundError:
        return False
    except OSError:  # no /proc: ask the kernel
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
        return True


def start(root, job: str, role: str, round_no: int, vendor: str, cwd: str, write: str, prompt_file: str, model=None, effort=None,
          resume=None, limit_seconds: int | None = None) -> dict:
    """Spawns the detached runner and returns {ok, run} at once; the status file says `running` with the runner's pid."""
    if vendor not in VENDORS:
        raise ValueError(f"unknown vendor {vendor!r}")
    for label, name in (("job", job), ("role", role)):
        if not NAME_RE.fullmatch(name) or ".." in name:
            raise ValueError(f"bad {label} {name!r}")
    if not Path(prompt_file).is_file():
        raise ValueError(f"no prompt file at {prompt_file}")
    run = f"{role}-r{int(round_no)}"
    paths = _paths(root, job, run)
    status = _read_status(paths["status"])
    if status and status.get("state") == "running":
        if _alive(status.get("pid")):
            raise RunActive(f"{run} is still running (runner pid {status['pid']}): wait for it")
        _kill_group(status.get("pgid"))  # the runner died and left its CLI behind: two agents must never share a worktree
    paths["dir"].mkdir(parents=True, exist_ok=True)
    limit = limit_seconds or TIMEOUTS.get(role, DEFAULT_TIMEOUT)
    args = [sys.executable, str(Path(__file__).resolve()), "_run", "--root", str(root), "--job", job, "--role", role, "--run", run,
            "--vendor", vendor, "--cwd", str(cwd), "--write", str(write), "--prompt-file", str(Path(prompt_file).resolve()),
            "--limit-seconds", str(limit)]
    for flag, value in (("--model", model), ("--effort", effort), ("--resume", resume)):
        args += [flag, value] if value else []
    paths["log"].write_bytes(b"")
    with paths["log"].open("ab") as log:  # a crash of the runner itself lands in the log too
        runner = subprocess.Popen(args, stdin=subprocess.PIPE, stdout=log, stderr=log, start_new_session=True)
    # The runner waits for its stdin to close, so this status is never written over the final one.
    _write_status(paths["status"], {"state": "running", "pid": runner.pid})
    runner.stdin.close()
    return {"ok": True, "run": run}


def _end_group(proc: subprocess.Popen) -> None:
    """SIGTERM to the CLI's whole process group, SIGKILL to what is left after the grace. Also ends what outlived a clean exit."""
    try:
        os.killpg(proc.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    deadline = time.monotonic() + GRACE_SECONDS
    while time.monotonic() < deadline:
        proc.poll()  # reap the leader, or the group never looks empty
        try:
            os.killpg(proc.pid, 0)
        except ProcessLookupError:
            return
        time.sleep(0.05)
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    proc.wait()


def _run(a) -> int:
    sys.stdin.read()  # start closes it once the running status is written
    began = time.monotonic()
    paths = _paths(a.root, a.job, a.run)

    def finish(error: str | None, parsed: dict) -> int:
        _write_status(paths["status"], {"state": "failed" if error else "done", "error": error, **parsed,
                                        "ms": max(1, int((time.monotonic() - began) * 1000))})
        return 0

    nothing = {"session_id": None, "tokens": 0, "rate_limits": None}
    exe = shutil.which(a.vendor)
    if not exe:
        return finish("missing", nothing)
    cmd = build_command(a.vendor, a.cwd, a.write, a.model, a.effort, a.resume, agent_tools(a.role) if a.vendor == "claude" else [],
                        str(paths["last"]))
    cmd[0] = exe
    prompt = Path(a.prompt_file).read_bytes()
    try:
        with paths["log"].open("ab") as log:
            proc = subprocess.Popen(cmd, cwd=a.cwd, stdin=subprocess.PIPE, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
    except FileNotFoundError:
        return finish("missing", nothing)
    except OSError:
        return finish("exit", nothing)
    _write_status(paths["status"], {"state": "running", "pid": os.getpid(), "pgid": proc.pid})
    timed_out = False
    try:
        proc.communicate(prompt, timeout=a.limit_seconds)
    except subprocess.TimeoutExpired:
        timed_out = True
    _end_group(proc)
    proc.wait()
    output = paths["log"].read_text(errors="replace")
    parsed = parse_output(a.vendor, output)
    return finish("timeout" if timed_out else classify(a.vendor, proc.returncode, output, parsed["rate_limits"]), parsed)


def _kill_group(pgid) -> None:
    if isinstance(pgid, int) and not isinstance(pgid, bool) and pgid > 0:
        try:
            os.killpg(pgid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass


def wait(root, job: str, run: str, timeout: int = 300) -> dict:
    """The final status once the run ends, {state: running} at the timeout. A runner gone without a final status is `lost`, and
    the CLI's group it leaves behind is killed first. A run that was never started is a ValueError."""
    path = _paths(root, job, run)["status"]
    if not path.exists():
        raise ValueError(f"no run {run} for job {job}: start it first")
    deadline = time.monotonic() + timeout
    keys = ("state", "error", "session_id", "tokens", "ms", "rate_limits")
    while True:
        status = _read_status(path)
        if status and status.get("state") in ("done", "failed"):
            return {k: status.get(k) for k in keys}
        if not status or not _alive(status.get("pid")):
            status = _read_status(path)  # the runner may have written its status just before it ended
            if status and status.get("state") in ("done", "failed"):
                return {k: status.get(k) for k in keys}
            _kill_group((status or {}).get("pgid"))
            return {"state": "failed", "error": "lost", "session_id": None, "tokens": 0, "ms": 0, "rate_limits": None}
        left = deadline - time.monotonic()
        if left <= 0:
            return {"state": "running"}
        time.sleep(min(POLL_SECONDS, left))


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="peer.py")
    sub = ap.add_subparsers(dest="cmd", required=True)
    st = sub.add_parser("start")
    ru = sub.add_parser("_run")
    for p in (st, ru):
        for opt in ("--root", "--job", "--role", "--vendor", "--cwd", "--write", "--prompt-file"):
            p.add_argument(opt, required=True)
        for opt in ("--model", "--effort", "--resume"):
            p.add_argument(opt)
    st.add_argument("--round", type=int, required=True)
    st.add_argument("--limit-seconds", type=int)
    ru.add_argument("--run", required=True)
    ru.add_argument("--limit-seconds", type=int, required=True)
    wt = sub.add_parser("wait")
    wt.add_argument("--root", required=True)
    wt.add_argument("--job", required=True)
    wt.add_argument("--run", required=True)
    wt.add_argument("--timeout", type=int, default=300)
    a = ap.parse_args(argv)
    if a.cmd == "_run":
        return _run(a)
    try:
        if a.cmd == "wait":
            out = wait(a.root, a.job, a.run, a.timeout)
        else:
            out = start(a.root, a.job, a.role, a.round, a.vendor, a.cwd, a.write, a.prompt_file, a.model, a.effort, a.resume, a.limit_seconds)
    except (ValueError, OSError) as e:
        print(json.dumps({"ok": False, "error": str(e)}))
        return 2 if a.cmd == "wait" or isinstance(e, RunActive) else 1
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
