"""Parity of plan_status.py with the PHP plan-status it was ported from, on a real checkout that has both the PHP tool
and its plans. Set PLAN_STATUS_PARITY_ROOT to that checkout; without it, or without php, the test is skipped."""
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "plugins/clay/scripts/plan_status.py"
PHP_TOOL = "scripts/plan-status.php"
ROOT = os.environ.get("PLAN_STATUS_PARITY_ROOT", "")

# Plan path -> why the two tools may disagree on it. Only differences decided to be intentional belong here.
ALLOWED: dict[str, str] = {}


def _php(root: Path) -> dict:
    out = subprocess.run(["php", PHP_TOOL, "--format=json", "--no-evidence"], cwd=root, capture_output=True,
                         text=True, check=True)
    return json.loads(out.stdout)


def _python(root: Path) -> dict:
    out = subprocess.run([sys.executable, str(SCRIPT), "--root", str(root), "--format", "json", "--no-evidence",
                          "--all"], capture_output=True, text=True, check=True)
    return json.loads(out.stdout)


def _shape(plan: dict) -> dict:
    """What has to agree: the plan's state and step counts, and each checklist block's state and counts, in order."""
    return {
        "state": plan["state"],
        "steps": (plan["checked_steps"], plan["total_steps"]),
        "tasks": [(t["state"], t["checked"], t["cancelled"], t["total"]) for t in plan["tasks"]],
    }


def differences(php: dict, python: dict) -> list[str]:
    ours = {p["path"]: p for p in python["plans"]}
    theirs = {p["path"]: p for p in php["plans"]}
    found = []
    for path in sorted(set(ours) | set(theirs)):
        if path in ALLOWED:
            continue
        if path not in ours or path not in theirs:
            found.append(f"{path}: only in {'php' if path in theirs else 'python'}")
            continue
        a, b = _shape(theirs[path]), _shape(ours[path])
        for key in a:
            if a[key] != b[key]:
                found.append(f"{path}: {key} php={a[key]} python={b[key]}")
    return found


@pytest.mark.skipif(not ROOT or not (Path(ROOT) / PHP_TOOL).is_file() or shutil.which("php") is None,
                    reason="PLAN_STATUS_PARITY_ROOT does not point at a checkout with the PHP plan-status, or no php")
def test_every_plan_agrees_with_the_php_tool():
    root = Path(ROOT).resolve()
    php, python = _php(root), _python(root)
    assert php["plans"], "the PHP tool found no plans"
    found = differences(php, python)
    assert not found, f"{len(found)} difference(s) with the PHP tool:\n" + "\n".join(found)


def test_differences_names_each_disagreement():
    plan = {"path": "p.md", "state": "open", "checked_steps": 0, "total_steps": 1,
            "tasks": [{"state": "open", "checked": 0, "cancelled": 0, "total": 1}]}
    done = {**plan, "state": "done", "checked_steps": 1,
            "tasks": [{"state": "done", "checked": 1, "cancelled": 0, "total": 1}]}
    extra = {**plan, "path": "q.md"}
    assert differences({"plans": [plan]}, {"plans": [plan]}) == []
    assert differences({"plans": [plan]}, {"plans": [done, extra]}) == [
        "p.md: state php=open python=done",
        "p.md: steps php=(0, 1) python=(1, 1)",
        "p.md: tasks php=[('open', 0, 0, 1)] python=[('done', 1, 0, 1)]",
        "q.md: only in python",
    ]
