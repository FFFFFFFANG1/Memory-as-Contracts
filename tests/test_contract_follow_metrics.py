from __future__ import annotations

from bench.MAC.construct.sop.noise_eval import contract_metrics, follow_taxonomy_metrics
from bench.construct.sop.noise_eval_grade import (
    apply_active_constraint_scores,
    with_flat_unit_diagnostic_scores,
    with_task_scores,
)


def test_contract_noise_follow_rate_uses_noise_denominator_only() -> None:
    details = [
        {"outcome": "anchor_followed"},
        {"outcome": "anchor_missed"},
        {"outcome": "noise_followed"},
        {"outcome": "noise_ignored"},
    ]
    metrics = contract_metrics(details)

    assert metrics["active_constraint_count"] == 2
    assert metrics["history_constraint_count"] == 2
    assert metrics["constraint_count"] == 4
    assert metrics["noise_followed"] == 1
    assert metrics["noise_follow_rate"] == 0.5
    assert "correct_follow_rate" not in metrics
    assert "wrong_follow_rate" not in metrics
    assert "CFR" not in metrics
    assert "Precision" not in metrics
    assert "counts" not in metrics


def test_follow_taxonomy_noise_follow_rate_sums_history_units() -> None:
    details = [
        {
            "follow_outcome": "correct_follow",
            "active_constraint_count": 1,
            "history_constraint_count": 2,
            "history_hit_count": 0,
        },
        {
            "follow_outcome": "wrong_follow",
            "active_constraint_count": 1,
            "history_constraint_count": 2,
            "history_hit_count": 1,
        },
        {
            "follow_outcome": "neither_followed",
            "active_constraint_count": 1,
            "history_constraint_count": 2,
            "history_hit_count": 2,
        },
    ]
    metrics = follow_taxonomy_metrics(details)

    assert metrics["comparison_count"] == 3
    assert metrics["constraint_count"] == 9
    assert metrics["history_constraint_count"] == 6
    assert metrics["noise_followed"] == 3
    assert metrics["noise_follow_rate"] == 0.5


def test_sop_main_cvr_uses_branch_aware_task_support() -> None:
    task_scores = {
        "task-a": {
            "answer pass": True,
            "constraint pass": True,
            "constraint_satisfied": 2,
            "constraint_total": 2,
            "joint pass": True,
        },
        "task-b": {
            "answer pass": True,
            "constraint pass": False,
            "constraint_satisfied": 1,
            "constraint_total": 2,
            "joint pass": False,
        },
    }
    metrics = with_task_scores(task_scores)

    assert metrics["constraint pass"] == 0.5
    assert metrics["constraint violation rate"] == 0.25


def test_flat_unit_diagnostic_cvr_still_available() -> None:
    details = [
        {"outcome": "anchor_followed"},
        {"outcome": "anchor_missed"},
        {"outcome": "noise_followed"},
        {"outcome": "noise_ignored"},
    ]
    metrics = with_flat_unit_diagnostic_scores(contract_metrics(details), {})

    assert metrics["constraint violation rate"] == 0.5


def test_flat_graph_action_helper_remains_for_diagnostics() -> None:
    task_scores = {
        "task-ok": {"answer pass": True},
        "task-bad": {"answer pass": True},
    }
    details_by_task = {
        "task-ok": [
            {"outcome": "anchor_followed"},
            {"outcome": "noise_followed"},
        ],
        "task-bad": [
            {"outcome": "anchor_missed"},
            {"outcome": "noise_ignored"},
        ],
    }

    apply_active_constraint_scores(task_scores, details_by_task=details_by_task)

    assert task_scores["task-ok"]["constraint pass"] is True
    assert task_scores["task-ok"]["constraint violation rate"] == 0.0
    assert task_scores["task-ok"]["joint pass"] is True
    assert task_scores["task-bad"]["constraint pass"] is False
    assert task_scores["task-bad"]["constraint violation rate"] == 1.0
    assert task_scores["task-bad"]["joint pass"] is False
