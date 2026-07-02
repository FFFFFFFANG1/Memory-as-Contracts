from __future__ import annotations

import json
from pathlib import Path

import pytest

from bench.MAC.construct.sop.noise_eval import (
    evaluate_sopbench_unit,
    evaluate_task,
    task_acc,
    task_answer_pass,
    task_joint_pass,
    task_process_constraint_pass,
)
from bench.construct.sop.noise_eval_grade import apply_native_process_constraint_scores

REPO_ROOT = Path(__file__).resolve().parents[1]
MANIFEST = REPO_ROOT / "bench" / "MAC" / "sopbench" / "data" / "mac-sopbench-noise_eval_specs.json"


pytestmark = pytest.mark.skipif(
    __import__("sys").version_info < (3, 10),
    reason="SOPBench evaluation requires Python 3.10+",
)


def _task_spec(task_uid: str) -> dict:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    return manifest["task_specs"][task_uid]


def _apply_scores(task_uid: str, evaluation: dict) -> dict:
    task_scores = {task_uid: {"answer pass": task_answer_pass(evaluation)}}
    apply_native_process_constraint_scores(task_scores, task_evals={task_uid: evaluation})
    return task_scores[task_uid]


def test_empty_trace_answer_pass_is_outcome_only_and_joint_is_success() -> None:
    spec = _task_spec("sopbench:hotel:modify_reservation:70")
    trace = {"tool_calls": [], "final_response": "Done.", "trajectory": []}
    evaluation = evaluate_task(task_spec=spec, trace=trace)

    assert evaluation["success"] is True
    assert task_answer_pass(evaluation) is True
    assert task_process_constraint_pass(evaluation) is True
    assert task_joint_pass(evaluation) is True

    score = _apply_scores("sopbench:hotel:modify_reservation:70", evaluation)

    assert score["answer pass"] is True
    assert score["constraint pass"] is True
    assert score["joint pass"] is True


def test_open_account_or_path_passes_native_process_constraint() -> None:
    spec = _task_spec("sopbench:bank:open_account:2")
    trace = {
        "tool_calls": [
            {
                "name": "internal_check_username_exist",
                "arguments": {"username": "alex_smith"},
                "result": [True, False],
            }
        ],
        "final_response": "Cannot open account.",
        "trajectory": [],
    }
    evaluation = evaluate_task(task_spec=spec, trace=trace)

    assert evaluation["success"] is True
    assert task_answer_pass(evaluation) is True
    assert evaluation["dirgraph_satisfied"] is True
    assert task_process_constraint_pass(evaluation) is True

    score = _apply_scores("sopbench:bank:open_account:2", evaluation)

    assert score["answer pass"] is True
    assert score["constraint pass"] is True
    assert score["joint pass"] is True


def test_joint_pass_matches_native_success_not_answer_pass_alone() -> None:
    evaluation = {
        "action_called_correctly": True,
        "no_tool_call_error": True,
        "constraint_not_violated": True,
        "database_match": True,
        "dirgraph_satisfied": False,
        "success": False,
    }

    assert task_answer_pass(evaluation) is True
    assert task_process_constraint_pass(evaluation) is False
    assert task_acc(evaluation) is False
    assert task_joint_pass(evaluation) is False

    score = _apply_scores("synthetic", evaluation)

    assert score["answer pass"] is True
    assert score["constraint pass"] is False
    assert score["joint pass"] is False


def test_graph_action_unit_uses_order_respecting_actions() -> None:
    spec = _task_spec("sopbench:hotel:book_room:8")
    trace = {
        "tool_calls": [
            {
                "name": "check_room_availability",
                "arguments": {"room_type": "single", "date": "2024-01-01"},
                "result": True,
            }
        ],
        "final_response": "",
        "trajectory": [],
    }
    evaluation = evaluate_task(task_spec=spec, trace=trace)
    replay = evaluation.pop("_replay")

    assert "order_respecting_actions" in replay
    assert replay["order_respecting_actions"].issubset(replay["successful_actions"])

    unit = {
        "evaluator_type": "sopbench_action_call",
        "constraint_id": "check_room_availability",
        "normalized_constraint_id": "check_room_availability",
        "params": {},
    }
    result = evaluate_sopbench_unit(
        unit=unit,
        task_spec=spec,
        trace=trace,
        replay=replay,
    )
    observed = result["observed_followed"]
    expected_in_order = "check_room_availability" in replay["order_respecting_actions"]
    assert observed is expected_in_order
