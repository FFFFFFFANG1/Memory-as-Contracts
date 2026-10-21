from __future__ import annotations

import json
from pathlib import Path

import pytest

from bench.MAC.sopbench.delta_noise_follow import (
    DeltaItem,
    aggregate_delta_noise_follow,
    collect_unique_delta_set,
    dependency_delta_items,
    evaluate_task_delta_noise_follow,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
RUNTIME_DATA = REPO_ROOT / "bench" / "MAC" / "sopbench" / "data"
TASKS = RUNTIME_DATA / "mac-sopbench-tasks.json"
SEQUENCES = RUNTIME_DATA / "mac-sopbench-temporal_sequences.json"
MANIFEST = REPO_ROOT / "bench" / "MAC" / "sopbench" / "data" / "mac-sopbench-noise_eval_specs.json"

pytestmark = pytest.mark.skipif(
    __import__("sys").version_info < (3, 10),
    reason="SOPBench evaluation requires Python 3.10+",
)


def _step2(task_uid: str) -> dict:
    payload = json.loads(TASKS.read_text(encoding="utf-8"))
    for row in payload["tasks"]:
        if row.get("mac_task_uid") == task_uid:
            return row
    raise KeyError(task_uid)


def _step4(task_uid: str) -> dict:
    payload = json.loads(SEQUENCES.read_text(encoding="utf-8"))
    tasks = payload.get("tasks") if isinstance(payload, dict) else payload
    for row in tasks:
        if row.get("mac_task_uid") == task_uid:
            return row
    raise KeyError(task_uid)


def _task_spec(task_uid: str) -> dict:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    return manifest["task_specs"][task_uid]


def test_dependency_delta_items_detect_added_and_removed() -> None:
    anchor = ["single", "A", {}]
    noise = ["and", [["single", "A", {}], ["single", "B", {}]]]
    items = dependency_delta_items(anchor_dep=anchor, noise_dep=noise)
    assert any(item.direction == "added" for item in items)


def test_unique_delta_set_is_nonempty_for_real_task() -> None:
    task_uid = "sopbench:hotel:modify_reservation:70"
    step2 = _step2(task_uid)
    step4 = _step4(task_uid)
    sequence = [item for item in (step4.get("temporal_sequence") or []) if isinstance(item, dict)]
    unique = collect_unique_delta_set(step2_task=step2, sequence=sequence)
    assert unique
    assert all(isinstance(item, DeltaItem) for item in unique)


def test_empty_trace_has_zero_delta_hits() -> None:
    task_uid = "sopbench:hotel:modify_reservation:70"
    spec = _task_spec(task_uid)
    trace = {"tool_calls": [], "final_response": "Done.", "trajectory": []}
    result = evaluate_task_delta_noise_follow(
        step2_task=_step2(task_uid),
        task_spec=spec,
        sequence=[item for item in (_step4(task_uid).get("temporal_sequence") or []) if isinstance(item, dict)],
        trace=trace,
    )
    assert result["delta_hit_count"] == 0
    assert result["has_tool_calls"] is False


def test_anchor_satisfied_trajectory_has_zero_delta_hits() -> None:
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
        "final_response": "Cannot open account.",
        "trajectory": [],
    }
    result = evaluate_task_delta_noise_follow(
        step2_task=_step2(task_uid),
        task_spec=spec,
        sequence=[item for item in (_step4(task_uid).get("temporal_sequence") or []) if isinstance(item, dict)],
        trace=trace,
    )
    assert result["anchor_graph_satisfied"] is True
    assert result["delta_hit_count"] == 0


def test_aggregate_delta_noise_follow_micro_average() -> None:
    summary = aggregate_delta_noise_follow(
        [
            {"unique_delta_count": 4, "delta_hit_count": 1, "anchor_graph_satisfied": False},
            {"unique_delta_count": 2, "delta_hit_count": 0, "anchor_graph_satisfied": True},
        ]
    )
    assert summary["unique_delta_count"] == 6
    assert summary["delta_hit_count"] == 1
    assert summary["delta_noise_follow_rate"] == pytest.approx(1 / 6)
    assert summary["anchor_missed_delta_noise_follow_rate"] == pytest.approx(0.25)


def test_delta_item_identity_is_direction_sensitive() -> None:
    key = json.dumps({"constraint_id": "X", "params": {}}, sort_keys=True)
    assert DeltaItem(key, "added").delta_id != DeltaItem(key, "removed").delta_id
