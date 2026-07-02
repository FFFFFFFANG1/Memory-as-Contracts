from __future__ import annotations

import json
from pathlib import Path

import pytest

from bench.MAC.construct.sop.noise_eval import evaluate_task

REPO_ROOT = Path(__file__).resolve().parents[1]
MANIFEST = REPO_ROOT / "bench" / "MAC" / "sopbench" / "data" / "mac-sopbench-noise_eval_specs.json"


pytestmark = pytest.mark.skipif(
    __import__("sys").version_info < (3, 10),
    reason="SOPBench evaluation requires Python 3.10+",
)


def _task_spec(task_uid: str) -> dict:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    spec = manifest["task_specs"][task_uid]
    assert isinstance(spec, dict)
    return spec


def test_evaluate_task_empty_trace_matches_native_for_should_not_succeed() -> None:
    spec = _task_spec("sopbench:hotel:modify_reservation:70")
    evaluation = evaluate_task(task_spec=spec, trace={"tool_calls": []})

    assert evaluation["action_should_succeed"] is False
    assert evaluation["action_called_correctly"] is True
    assert evaluation["dirgraph_satisfied"] is True
    assert evaluation["success"] is True


def test_evaluate_task_empty_trace_fails_when_goal_should_succeed() -> None:
    spec = _task_spec("sopbench:hotel:book_room:8")
    evaluation = evaluate_task(task_spec=spec, trace={"tool_calls": []})

    assert evaluation["action_should_succeed"] is True
    assert evaluation["action_called_correctly"] is False
    assert evaluation["success"] is False
