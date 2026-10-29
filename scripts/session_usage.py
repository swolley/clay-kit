#!/usr/bin/env python3
"""Tokens and time of one Claude Code session, for comparing runs of the same plan with and without clay.

Reads the session's transcript (`~/.claude/projects/<project>/<session>.jsonl`) and its subagents (`<session>/subagents/*.jsonl`),
counts each assistant message once (a message is written once per content block, with the same usage), and adds the Codex sessions
that ran for the same checkout during the same window (`~/.codex/sessions/**/rollout-*.jsonl`), which is how a Codex peer shows up.
Time spent waiting for the person (a question tool's answer, a typed message after the session went idle) is not active time.

    python3 scripts/session_usage.py <session id or .jsonl path> [--json]
"""
import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

ASK_TOOLS = ("AskUserQuestion", "request_user_input")
# User records the person did not type: a background task finishing, a local command's output, the summary after a compaction.
# A slash command the person typed (`<command-name>`) does end a wait.
NOT_TYPED = ("<task-notification>", "<system-reminder>", "<local-command-stdout>", "This session is being continued")
FIELDS = (("input", "input_tokens"), ("output", "output_tokens"), ("cache_read", "cache_read_input_tokens"),
          ("cache_write", "cache_creation_input_tokens"))
CODEX_FIELDS = (("input", "input_tokens"), ("cached_input", "cached_input_tokens"), ("output", "output_tokens"),
                ("reasoning_output", "reasoning_output_tokens"))


def _records(path: Path) -> list[dict]:
    out = []
    for line in path.read_text(errors="replace").splitlines():
        try:
            rec = json.loads(line)
        except ValueError:
            continue
        if isinstance(rec, dict):
            out.append(rec)
    return out


def _when(rec: dict) -> float | None:
    try:
        return datetime.fromisoformat(str(rec["timestamp"]).replace("Z", "+00:00")).timestamp()
    except (KeyError, ValueError):
        return None


def _tokens(records: list[dict]) -> dict:
    """Per model: the usage of each assistant message, counted once (the last record of a message wins)."""
    messages: dict[str, tuple[str, dict]] = {}
    for i, rec in enumerate(records):
        msg = rec.get("message") if rec.get("type") == "assistant" else None
        if isinstance(msg, dict) and isinstance(msg.get("usage"), dict):
            messages[msg.get("id") or f"#{i}"] = (msg.get("model") or "unknown", msg["usage"])
    out: dict[str, dict] = {}
    for model, usage in messages.values():
        row = out.setdefault(model, {name: 0 for name, _ in FIELDS} | {"messages": 0})
        for name, key in FIELDS:
            row[name] += int(usage.get(key) or 0)
        row["messages"] += 1
    return out


def _merge(a: dict, b: dict) -> dict:
    for model, row in b.items():
        into = a.setdefault(model, {k: 0 for k in row})
        for k, v in row.items():
            into[k] += v
    return a


def _human_input(rec: dict, asked: set[str]) -> bool:
    """A record that only a person could produce: a typed message, or the answer to a question tool."""
    if rec.get("type") != "user" or rec.get("isMeta"):
        return False
    content = (rec.get("message") or {}).get("content")
    if isinstance(content, str):
        return not content.lstrip().startswith(NOT_TYPED)
    if isinstance(content, list):
        if any(b.get("type") == "tool_result" and b.get("tool_use_id") in asked for b in content if isinstance(b, dict)):
            return True
        return any(b.get("type") == "text" for b in content if isinstance(b, dict)) and not any(
            b.get("type") == "tool_result" for b in content if isinstance(b, dict))
    return False


def _times(records: list[dict]) -> dict:
    timed = sorted(((t, i, rec) for i, rec in enumerate(records) if (t := _when(rec)) is not None))
    if not timed:
        return {"start": None, "end": None, "wall_seconds": 0, "waiting_seconds": 0, "active_seconds": 0}
    asked = {b.get("id") for _, _, rec in timed if rec.get("type") == "assistant"
             for b in ((rec.get("message") or {}).get("content") or []) if isinstance(b, dict) and b.get("name") in ASK_TOOLS}
    waiting, last_reply = 0.0, None  # a wait runs from the model's last message to the person's input, whatever sits between
    for t, _, rec in timed:
        if rec.get("type") == "assistant":
            last_reply = t
        elif last_reply is not None and _human_input(rec, asked):
            waiting += t - last_reply
            last_reply = None
    wall = timed[-1][0] - timed[0][0]
    return {"start": timed[0][0], "end": timed[-1][0], "wall_seconds": round(wall), "waiting_seconds": round(waiting),
            "active_seconds": round(wall - waiting)}


def _codex(codex_home: Path, cwd: str | None, start: float | None, end: float | None) -> dict:
    """The Codex sessions started in this run's window for this checkout or its clay worktrees (`<checkout>-factory/...`)."""
    out = {"sessions": 0} | {name: 0 for name, _ in CODEX_FIELDS}
    if not cwd or start is None or end is None:
        return out
    for path in sorted(Path(codex_home).glob("sessions/**/rollout-*.jsonl")):
        records = _records(path)
        meta = next((r.get("payload") or {} for r in records if r.get("type") == "session_meta"), None)
        if not meta:
            continue
        where, when = str(meta.get("cwd") or ""), _when(meta) or _when(records[0])
        if when is None or not start <= when <= end:
            continue
        if not (where == cwd or where.startswith(cwd + "/") or where.startswith(cwd + "-factory/")):
            continue
        totals = [((r.get("payload") or {}).get("info") or {}).get("total_token_usage") for r in records]
        last = next((t for t in reversed(totals) if isinstance(t, dict)), None)
        if last:
            out["sessions"] += 1
            for name, key in CODEX_FIELDS:
                out[name] += int(last.get(key) or 0)
    return out


def summarize(main: Path, codex_home: Path | None = None) -> dict:
    records = _records(main)
    sub = _tokens([])
    for agent in sorted((main.parent / main.stem / "subagents").glob("*.jsonl")):
        _merge(sub, _tokens(_records(agent)))
    times = _times(records)
    cwd = next((r["cwd"] for r in records if r.get("cwd")), None)
    codex = _codex(codex_home or Path.home() / ".codex", cwd, times["start"], times["end"])
    return {"session": main.stem, "cwd": cwd, **{k: v for k, v in times.items() if k not in ("start", "end")},
            "main": _tokens(records), "subagents": sub, "codex": codex}


def _find(target: str, projects: Path) -> Path | None:
    path = Path(target)
    if path.suffix == ".jsonl" and path.is_file():
        return path
    return next(iter(sorted(projects.glob(f"*/{target}.jsonl"))), None)


def _print(out: dict) -> None:
    print(f"session {out['session']}  cwd {out['cwd']}")
    print(f"time: wall {out['wall_seconds']}s, waiting for the person {out['waiting_seconds']}s, active {out['active_seconds']}s")
    for part in ("main", "subagents"):
        for model, row in sorted(out[part].items()):
            print(f"{part:9} {model:24} " + "  ".join(f"{k} {v}" for k, v in row.items()))
    c = out["codex"]
    print("codex     " + "  ".join(f"{k} {v}" for k, v in c.items()))


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="session_usage.py", description=__doc__.splitlines()[0])
    ap.add_argument("session", help="a session id, or the path of its .jsonl")
    ap.add_argument("--projects-dir", default=str(Path.home() / ".claude" / "projects"))
    ap.add_argument("--codex-home", default=str(Path.home() / ".codex"))
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    main_file = _find(a.session, Path(a.projects_dir))
    if main_file is None:
        print(json.dumps({"error": f"no session {a.session} under {a.projects_dir}"}))
        return 2
    out = summarize(main_file, Path(a.codex_home))
    print(json.dumps(out, indent=2)) if a.json else _print(out)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
