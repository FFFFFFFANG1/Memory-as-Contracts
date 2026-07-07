from __future__ import annotations

import json
from pathlib import Path

import pytest

from bench.MAC.construct.sop.noise_eval import evaluate_task, task_answer_pass
from bench.construct.sop.noise_eval_grade import (
    apply_branch_aware_process_scores,
    score_branch_aware_active_process,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
MANIFEST = REPO_ROOT / "bench" / "MAC" / "sopbench" / "data" / "mac-sopbench-noise_eval_specs.json"


pytestmark = pytest.mark.skipif(
    __import__("sys").version_info < (3, 10),
    reason="SOPBench evaluation requires Python 3.10+",
)


def graph_action_nodes(graph: dict) -> set[str]:
    nodes: set[str] = set()
    for node in graph.get("nodes") or []:
        if isinstance(node, (list, tuple)) and node:
            nodes.add(str(node[0]))
    return nodes


def _task_spec(task_uid: str) -> dict:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    return manifest["task_specs"][task_uid]


def test_or_branch_task_passes_without_internal_get_database() -> None:
    spec = _task_spec("sopbench:bank:open_account:2")
    task_uid = "sopbench:bank:open_account:2"
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
    replay = evaluation.pop("_replay")
    task_scores = {task_uid: {"answer pass": task_answer_pass(evaluation)}}

    graph = spec["patched_sopbench_task"]["directed_action_graph"]
    apply_branch_aware_process_scores(
        task_scores,
        task_specs={task_uid: spec},
        replay_by_task={task_uid: replay},
        task_evals={task_uid: evaluation},
    )

    assert task_scores[task_uid]["constraint pass"] is True
    assert task_scores[task_uid]["constraint violation rate"] == 0.0
    assert "internal_get_database" in graph_action_nodes(graph)
    assert "internal_get_database" not in {
        str(action) for action in replay["order_respecting_actions"]
    }


def test_and_branch_miss_fails_process_scoring() -> None:
    graph = {
        "nodes": [
            ["user_goal_action", {"username": "username"}],
            "and",
            ["login_user", {"username": "username", "identification": "identification"}],
            ["get_policy_details", {"username": "username"}],
        ],
        "connections": [[0, 1], [1, 2], [1, 3]],
    }
    process = score_branch_aware_active_process(
        graph=graph,
        order_respecting_actions={"login_user"},
        user_goal="user_goal_action",
    )

    assert process["constraint pass"] is False
    assert process["constraint_satisfied"] == 1
    assert process["constraint_total"] == 2
    assert process["constraint violation rate"] == 0.5


def test_or_branch_cvr_uses_best_path_not_all_nodes() -> None:
    graph = {
        "nodes": [
            ["goal", {}],
            "or",
            ["path_a", {}],
            ["path_b", {}],
        ],
        "connections": [[0, 1], [1, 2], [1, 3]],
    }
    process = score_branch_aware_active_process(
        graph=graph,
        order_respecting_actions={"path_a"},
        user_goal="goal",
    )

    assert process["constraint pass"] is True
    assert process["constraint_satisfied"] == 1
    assert process["constraint_total"] == 1
    assert process["constraint violation rate"] == 0.0


def test_apply_branch_aware_process_scores_sets_joint_pass() -> None:
    task_uid = "sopbench:bank:open_account:2"
    spec = _task_spec(task_uid)
    trace = {
        "tool_calls": [
            {
                "name": "internal_check_username_exist",
                "arguments": {"username": "alex_smith"},
                "result": [True, False],
            }
        ],
        "final_response": "",
        "trajectory": [],
    }
    evaluation = evaluate_task(task_spec=spec, trace=trace)
    replay = evaluation.pop("_replay")
    task_scores = {task_uid: {"answer pass": task_answer_pass(evaluation)}}

    apply_branch_aware_process_scores(
        task_scores,
        task_specs={task_uid: spec},
        replay_by_task={task_uid: replay},
        task_evals={task_uid: evaluation},
    )

    assert task_scores[task_uid]["constraint pass"] is True
    assert task_scores[task_uid]["joint pass"] is True
