from __future__ import annotations

from bench.MAC.construct.sop.noise_eval import contract_metrics, follow_taxonomy_metrics
from bench.construct.sop.noise_eval_grade import (
    apply_active_constraint_scores,
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


def test_sop_main_cvr_ignores_noise_followed() -> None:
    details = [
        {"outcome": "anchor_followed"},
        {"outcome": "anchor_missed"},
        {"outcome": "noise_followed"},
        {"outcome": "noise_ignored"},
    ]
    metrics = with_task_scores(contract_metrics(details), {})

    assert metrics["constraint violation rate"] == 0.5


def test_sop_task_constraint_pass_uses_active_constraints_only() -> None:
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
