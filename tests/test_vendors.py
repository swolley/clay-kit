import json
import os
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugins/clay/scripts"))
import vendors  # noqa: E402
from vendors import decide, quota  # noqa: E402

NOW = "2026-10-25T12:00:00Z"
FUTURE = "2026-10-25T18:00:00Z"
PAST = "2026-10-25T06:00:00Z"


def on(**extra):
    return {"cross": {"on": True, "peer": "codex", "threshold": 80, "builder_tiers": [], **extra}}


def run_with(vendor_state=None, **extra):
    return {**on(**extra), "vendors": vendor_state or {}}


def d(job, run, agent, host="claude", usage=None):
    return decide(job, run, agent, host, usage or {}, NOW)


def built_by(vendor):
    return {"tier": "medium", "vendors": {"builder": {"vendor": vendor, "reason": "session"}}}


AGENTS = ["builder", "reviewer-code", "reviewer-interface", "reviewer-security", "reviewer-spec", "approver"]


@pytest.mark.parametrize("agent", AGENTS)
def test_peer_off_keeps_every_agent_on_the_host(agent):
    for run in ({}, {"cross": {"on": False, "peer": "codex"}}):
        assert d({"tier": "light"}, run, agent) == {"vendor": "claude", "peer": False, "reason": "session", "crossed": False}


def test_a_host_without_a_peer_stays_on_itself_even_when_on():
    assert decide({"tier": "light"}, on(), "builder", "cursor", {}, NOW)["vendor"] == "cursor"


def test_builder_on_a_listed_tier_goes_to_the_peer():
    out = d({"tier": "light"}, on(builder_tiers=["light"]), "builder")
    assert out == {"vendor": "codex", "peer": True, "reason": "builder_tiers", "crossed": False}
    assert d({"tier": "light"}, on(builder_tiers=["light"]), "builder", host="codex")["vendor"] == "claude"
    assert d({"tier": "heavy"}, on(builder_tiers=["light"]), "builder") == {"vendor": "claude", "peer": False, "reason": "session", "crossed": False}


def test_builder_moves_off_a_vendor_over_the_threshold():
    out = d({"tier": "light"}, on(builder_tiers=["light"]), "builder", usage={"codex": 85.0, "claude": None})
    assert (out["vendor"], out["reason"], out["peer"]) == ("claude", "threshold", False)
    out = d({"tier": "light"}, on(builder_tiers=["light"]), "builder", usage={"codex": 80.0})
    assert out["vendor"] == "claude"
    out = d({"tier": "light"}, on(builder_tiers=["light"]), "builder", usage={"codex": 79.9})
    assert (out["vendor"], out["reason"]) == ("codex", "builder_tiers")


def test_builder_stays_when_the_other_vendor_is_over_too():
    out = d({"tier": "light"}, on(builder_tiers=["light"]), "builder", usage={"codex": 90.0, "claude": 95.0})
    assert out["vendor"] == "codex"


def test_unknown_margin_is_never_over():
    assert d({"tier": "light"}, on(builder_tiers=["light"]), "builder", usage={"codex": None})["vendor"] == "codex"


def test_builder_moves_off_an_exhausted_vendor_and_a_past_exhaustion_does_not_count():
    run = run_with({"codex": {"exhausted_until": FUTURE}}, builder_tiers=["light"])
    out = d({"tier": "light"}, run, "builder")
    assert (out["vendor"], out["reason"]) == ("claude", "exhausted")
    run = run_with({"codex": {"exhausted_until": PAST}}, builder_tiers=["light"])
    assert d({"tier": "light"}, run, "builder")["vendor"] == "codex"


def test_builder_on_an_exhausted_host_goes_to_the_peer():
    out = d({"tier": "medium"}, run_with({"claude": {"exhausted_until": FUTURE}}), "builder")
    assert (out["vendor"], out["reason"], out["peer"]) == ("codex", "exhausted", True)


@pytest.mark.parametrize("agent", AGENTS[1:])
def test_reviewer_is_opposite_to_the_builder(agent):
    out = d(built_by("codex"), on(), agent)
    assert out == {"vendor": "claude", "peer": False, "reason": "opposite", "crossed": True}
    out = d(built_by("claude"), on(), agent)
    assert out == {"vendor": "codex", "peer": True, "reason": "opposite", "crossed": True}


def test_review_stays_on_the_builder_when_the_opposite_is_exhausted():
    run = run_with({"claude": {"exhausted_until": FUTURE}})
    out = d(built_by("codex"), run, "reviewer-code")
    assert out == {"vendor": "codex", "peer": True, "reason": "not crossed", "crossed": False}


def test_review_stays_on_the_builder_when_the_opposite_is_over_the_threshold():
    out = d(built_by("claude"), on(), "approver", usage={"codex": 99.0})
    assert (out["vendor"], out["reason"], out["crossed"]) == ("claude", "not crossed", False)


def test_a_lean_job_counts_the_host_as_its_builder():
    out = d({"tier": "light", "lean": True, "vendors": {}}, on(), "reviewer-code")
    assert (out["vendor"], out["reason"]) == ("codex", "opposite")
    assert d({"tier": "light"}, on(), "reviewer-code", host="codex")["vendor"] == "claude"


def test_final_review_is_opposite_to_the_host():
    out = d(None, on(), "reviewer-final")
    assert out == {"vendor": "codex", "peer": True, "reason": "opposite", "crossed": True}
    assert d(None, on(), "reviewer-final", host="codex")["vendor"] == "claude"
    out = d(None, run_with({"codex": {"exhausted_until": FUTURE}}), "reviewer-final")
    assert (out["vendor"], out["reason"], out["crossed"]) == ("claude", "not crossed", False)


def test_both_exhausted_gives_no_vendor():
    run = run_with({"claude": {"exhausted_until": FUTURE}, "codex": {"exhausted_until": FUTURE}})
    for agent in ("builder", "reviewer-code", "reviewer-final"):
        out = d(built_by("claude") if agent != "reviewer-final" else None, run, agent)
        assert (out["vendor"], out["reason"], out["peer"]) == (None, "exhausted", False)


def test_a_peer_turned_off_is_never_chosen():
    run = run_with({"codex": {"off": True}}, builder_tiers=["light"])
    assert d({"tier": "light"}, run, "builder")["vendor"] == "claude"
    out = d(built_by("claude"), run, "reviewer-code")
    assert (out["vendor"], out["reason"]) == ("claude", "not crossed")
    assert d(None, run, "reviewer-final")["vendor"] == "claude"


def test_the_builders_vendor_out_sends_the_review_to_the_opposite_even_over_the_threshold():
    run = run_with({"claude": {"exhausted_until": FUTURE}})
    out = d(built_by("claude"), run, "reviewer-code", usage={"codex": 95.0})
    assert (out["vendor"], out["crossed"]) == ("codex", True)


def test_risky_agent_names_are_refused():
    with pytest.raises(ValueError):
        d(None, on(), "approver-risky")
    with pytest.raises(ValueError):
        d(None, on(), "nobody")


# quota

FUTURE_EPOCH = time.time() + 3600
PAST_EPOCH = time.time() - 3600


def rollout(home, name="rollout-x.jsonl", used=42.0, resets=FUTURE_EPOCH, tail=""):
    folder = Path(home) / "sessions/2026/10/25"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / name
    event = {"type": "event_msg", "payload": {"type": "token_count", "rate_limits": {"primary": {"used_percent": used, "resets_at": resets}, "secondary": None}}}
    path.write_text(json.dumps({"type": "session_meta"}) + "\n" + json.dumps(event) + "\n" + tail)
    return path


def test_quota_reads_the_last_rate_limits_of_a_rollout(tmp_path):
    rollout(tmp_path / "codex", used=42.0)
    out = quota(tmp_path / "root", "codex", codex_home=tmp_path / "codex")
    assert out["used_percent"] == 42.0 and out["source"] == "sessions"
    assert out["resets_at"] == vendors.iso(FUTURE_EPOCH)


def test_quota_counts_a_window_that_has_reset_as_zero(tmp_path):
    rollout(tmp_path / "codex", used=97.0, resets=PAST_EPOCH)
    out = quota(tmp_path / "root", "codex", codex_home=tmp_path / "codex")
    assert out["used_percent"] == 0.0 and out["source"] == "sessions"


def test_quota_skips_a_truncated_last_line(tmp_path):
    rollout(tmp_path / "codex", used=42.0, tail='{"type": "event_msg", "payload": {"rate_limits": {"prim')
    assert quota(tmp_path / "root", "codex", codex_home=tmp_path / "codex")["used_percent"] == 42.0


def test_quota_without_data_is_none(tmp_path):
    out = quota(tmp_path / "root", "codex", codex_home=tmp_path / "codex")
    assert out == {"used_percent": None, "resets_at": None, "source": "none"}
    (tmp_path / "codex/sessions").mkdir(parents=True)
    (tmp_path / "codex/sessions/rollout-empty.jsonl").write_text("not json\n{}\n")
    assert quota(tmp_path / "root", "codex", codex_home=tmp_path / "codex")["source"] == "none"


def test_quota_for_claude_is_always_none(tmp_path):
    rollout(tmp_path / "codex")
    assert quota(tmp_path / "root", "claude", codex_home=tmp_path / "codex")["used_percent"] is None


def test_quota_prefers_a_newer_peer_status_file(tmp_path):
    old = rollout(tmp_path / "codex", used=10.0)
    os.utime(old, (time.time() - 100, time.time() - 100))
    peer = tmp_path / "root/factory/jobs/some-job/peer"
    peer.mkdir(parents=True)
    (peer / "builder-r1.status.json").write_text(json.dumps({"state": "done", "rate_limits": {"used_percent": 77.0, "resets_at": FUTURE_EPOCH}}))
    out = quota(tmp_path / "root", "codex", codex_home=tmp_path / "codex")
    assert out["used_percent"] == 77.0 and out["source"] == "peer"


def test_quota_prefers_a_rollout_newer_than_the_status_file(tmp_path):
    peer = tmp_path / "root/factory/jobs/some-job/peer"
    peer.mkdir(parents=True)
    status = peer / "builder-r1.status.json"
    status.write_text(json.dumps({"state": "done", "rate_limits": {"used_percent": 77.0, "resets_at": FUTURE_EPOCH}}))
    os.utime(status, (time.time() - 100, time.time() - 100))
    rollout(tmp_path / "codex", used=10.0)
    out = quota(tmp_path / "root", "codex", codex_home=tmp_path / "codex")
    assert out["used_percent"] == 10.0 and out["source"] == "sessions"


def test_quota_ignores_a_status_file_without_limits(tmp_path):
    peer = tmp_path / "root/factory/jobs/some-job/peer"
    peer.mkdir(parents=True)
    (peer / "builder-r1.status.json").write_text(json.dumps({"state": "running", "pid": 1, "rate_limits": None}))
    rollout(tmp_path / "codex", used=10.0)
    assert quota(tmp_path / "root", "codex", codex_home=tmp_path / "codex")["source"] == "sessions"
