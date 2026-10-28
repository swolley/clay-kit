import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import session_usage  # noqa: E402


def write_jsonl(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r) + "\n" for r in records))


def assistant(ts, mid, model, inp, out, cread=0, cwrite=0, tool=None):
    content = [{"type": "tool_use", "id": tool[0], "name": tool[1], "input": {}}] if tool else [{"type": "text", "text": "x"}]
    usage = {"input_tokens": inp, "output_tokens": out, "cache_read_input_tokens": cread, "cache_creation_input_tokens": cwrite}
    return {"type": "assistant", "timestamp": ts, "cwd": "/w/run", "message": {"id": mid, "model": model, "usage": usage, "content": content}}


def user(ts, text=None, result_for=None):
    content = [{"type": "tool_result", "tool_use_id": result_for, "content": "ok"}] if result_for else text
    return {"type": "user", "timestamp": ts, "cwd": "/w/run", "message": {"role": "user", "content": content}}


def test_tokens_are_summed_once_per_message_and_per_model(tmp_path):
    main = tmp_path / "proj" / "S1.jsonl"
    write_jsonl(main, [
        user("2026-10-29T10:00:00Z", "go"),
        assistant("2026-10-29T10:00:05Z", "m1", "claude-opus-5-5", 10, 5, cread=100, cwrite=50),
        assistant("2026-10-29T10:00:05Z", "m1", "claude-opus-5-5", 10, 5, cread=100, cwrite=50),  # same message, second block
        assistant("2026-10-29T10:00:20Z", "m2", "claude-opus-5-5", 1, 2),
    ])
    write_jsonl(tmp_path / "proj" / "S1" / "subagents" / "agent-a.jsonl", [
        assistant("2026-10-29T10:00:10Z", "s1", "claude-sonnet-5-5", 3, 4, cread=7),
    ])
    out = session_usage.summarize(main, codex_home=tmp_path / "nocodex")
    assert out["main"]["claude-opus-5-5"] == {"input": 11, "output": 7, "cache_read": 100, "cache_write": 50, "messages": 2}
    assert out["subagents"]["claude-sonnet-5-5"] == {"input": 3, "output": 4, "cache_read": 7, "cache_write": 0, "messages": 1}
    assert out["wall_seconds"] == 20


def test_time_spent_waiting_for_the_person_is_not_active_time(tmp_path):
    main = tmp_path / "S2.jsonl"
    write_jsonl(main, [
        user("2026-10-29T10:00:00Z", "go"),
        assistant("2026-10-29T10:00:10Z", "m1", "claude-opus-5-5", 1, 1, tool=("t1", "AskUserQuestion")),
        user("2026-10-29T10:05:10Z", result_for="t1"),  # five minutes for the person to answer
        assistant("2026-10-29T10:05:20Z", "m2", "claude-opus-5-5", 1, 1),
        user("2026-10-29T10:10:20Z", "and now the next one"),  # a typed message after another wait
        assistant("2026-10-29T10:10:30Z", "m3", "claude-opus-5-5", 1, 1),
    ])
    out = session_usage.summarize(main, codex_home=tmp_path / "nocodex")
    assert out["wall_seconds"] == 630 and out["waiting_seconds"] == 600 and out["active_seconds"] == 30


def test_codex_sessions_of_the_run_are_added(tmp_path):
    main = tmp_path / "S3.jsonl"
    write_jsonl(main, [user("2026-10-29T10:00:00Z", "go"), assistant("2026-10-29T11:00:00Z", "m1", "claude-opus-5-5", 1, 1)])
    sessions = tmp_path / "codex" / "sessions" / "2026" / "10" / "29"

    def rollout(name, ts, cwd, totals):
        recs = [{"timestamp": ts, "type": "session_meta", "payload": {"timestamp": ts, "cwd": cwd}}]
        recs += [{"timestamp": ts, "type": "event_msg", "payload": {"type": "token_count", "info": {"total_token_usage": t}}} for t in totals]
        write_jsonl(sessions / name, recs)

    usage = {"input_tokens": 1000, "cached_input_tokens": 800, "output_tokens": 50, "reasoning_output_tokens": 10}
    rollout("rollout-a.jsonl", "2026-10-29T10:10:00Z", "/w/run-factory/001-x", [{**usage, "output_tokens": 20}, usage])
    rollout("rollout-b.jsonl", "2026-10-29T10:20:00Z", "/w/run", [usage])
    rollout("rollout-c.jsonl", "2026-10-29T12:00:00Z", "/w/run", [usage])  # after the run
    rollout("rollout-d.jsonl", "2026-10-29T10:30:00Z", "/elsewhere", [usage])  # another project
    (sessions / "rollout-e.jsonl").write_text('{"timestamp": "2026-10-29T10:40:00Z", "type": "session_meta", "payl')  # truncated
    out = session_usage.summarize(main, codex_home=tmp_path / "codex")
    assert out["codex"] == {"sessions": 2, "input": 2000, "cached_input": 1600, "output": 100, "reasoning_output": 20}


def test_the_cli_finds_a_session_by_id_and_prints_json(tmp_path, capsys):
    write_jsonl(tmp_path / "proj" / "S4.jsonl", [user("2026-10-29T10:00:00Z", "go"), assistant("2026-10-29T10:00:01Z", "m", "claude-opus-5-5", 1, 1)])
    assert session_usage.main(["S4", "--projects-dir", str(tmp_path), "--codex-home", str(tmp_path / "none"), "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["main"]["claude-opus-5-5"]["messages"] == 1
    assert session_usage.main(["missing", "--projects-dir", str(tmp_path)]) == 2


def test_notifications_and_system_messages_are_not_waiting(tmp_path):
    main = tmp_path / "S5.jsonl"
    meta = user("2026-10-29T10:02:00Z", "reminder")
    meta["isMeta"] = True
    write_jsonl(main, [
        user("2026-10-29T10:00:00Z", "go"),
        assistant("2026-10-29T10:00:10Z", "m1", "claude-opus-5-5", 1, 1),
        user("2026-10-29T10:01:10Z", "<task-notification>\n<task-id>a1</task-id>"),  # a subagent finished: not the person
        meta,
        assistant("2026-10-29T10:02:10Z", "m2", "claude-opus-5-5", 1, 1),
    ])
    out = session_usage.summarize(main, codex_home=tmp_path / "nocodex")
    assert out["waiting_seconds"] == 0 and out["active_seconds"] == 130


def test_a_typed_slash_command_ends_a_wait(tmp_path):
    main = tmp_path / "S6.jsonl"
    write_jsonl(main, [
        user("2026-10-29T10:00:00Z", "go"),
        assistant("2026-10-29T10:00:10Z", "m1", "claude-opus-5-5", 1, 1),
        user("2026-10-29T10:03:10Z", "<command-name>/clay:factory-run</command-name>\n<command-args>plan.md</command-args>"),
        assistant("2026-10-29T10:03:20Z", "m2", "claude-opus-5-5", 1, 1),
    ])
    out = session_usage.summarize(main, codex_home=tmp_path / "nocodex")
    assert out["waiting_seconds"] == 180 and out["active_seconds"] == 20


def test_a_wait_runs_from_the_last_assistant_message(tmp_path):
    main = tmp_path / "S7.jsonl"
    write_jsonl(main, [
        user("2026-10-29T10:00:00Z", "<system-reminder>\nLinked sessions now</system-reminder>"),
        user("2026-10-29T10:00:01Z", "go"),
        assistant("2026-10-29T10:00:10Z", "m1", "claude-opus-5-5", 1, 1),
        {"type": "system", "timestamp": "2026-10-29T10:05:09Z"},  # bookkeeping written just before the person's message
        user("2026-10-29T10:05:10Z", "<command-message>clay:factory-run</command-message>\n<command-name>/clay:factory-run</command-name>"),
        assistant("2026-10-29T10:05:20Z", "m2", "claude-opus-5-5", 1, 1),
    ])
    out = session_usage.summarize(main, codex_home=tmp_path / "nocodex")
    assert out["waiting_seconds"] == 300 and out["active_seconds"] == 20
