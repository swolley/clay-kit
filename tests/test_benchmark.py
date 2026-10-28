import importlib.util
import json
from pathlib import Path

import pytest

MODULE = Path(__file__).resolve().parents[1] / "scripts/benchmark.py"
spec = importlib.util.spec_from_file_location("clay_benchmark", MODULE)
benchmark = importlib.util.module_from_spec(spec)
spec.loader.exec_module(benchmark)


def args(action, root, **kw):
    from argparse import Namespace
    return Namespace(action=action, root=root, name="sample", host="claude",
                     mode="full", session_cost_before=None,
                     session_cost_after=None, **kw)


def test_capture_before_cleanup_and_cost_delta(tmp_path, capsys):
    job_dir = tmp_path / "factory/jobs/001-example"
    job_dir.mkdir(parents=True)
    (job_dir / "job.json").write_text(json.dumps({
        "id": "001-example", "plan": "plan", "tier": "medium",
        "agents": [{"role": "builder", "tokens": 120}],
        "stage": "review", "phases": []
    }))
    benchmark.run(args("start", tmp_path))
    finish = args("finish", tmp_path)
    finish.session_cost_before = 0.2
    finish.session_cost_after = 0.6
    benchmark.run(finish)
    record = json.loads(benchmark.destination(tmp_path, "sample").read_text())
    assert record["session_cost_usd"]["delta"] == pytest.approx(0.4)
    assert record["jobs_at_finish"][0]["agents"][0]["tokens"] == 120
    assert record["status"] == "finished"
    assert (job_dir / "job.json").exists()


def test_refuses_overwrite_and_invalid_costs(tmp_path):
    benchmark.run(args("start", tmp_path))
    with pytest.raises(ValueError, match="already exists"):
        benchmark.run(args("start", tmp_path))
    finish = args("finish", tmp_path)
    finish.session_cost_before = 2
    finish.session_cost_after = 1
    with pytest.raises(ValueError, match="increasing"):
        benchmark.run(finish)
    assert json.loads(benchmark.destination(tmp_path, "sample").read_text())["status"] == "running"


def test_rejects_path_traversal(tmp_path):
    with pytest.raises(ValueError):
        benchmark.destination(tmp_path, "../bad")
