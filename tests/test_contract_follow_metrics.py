from __future__ import annotations

from bench.MAC.construct.sop.noise_eval import contract_metrics, follow_taxonomy_metrics


def test_contract_follow_rates_use_active_plus_history_denominator() -> None:
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
    assert metrics["correctly_followed"] == 2
    assert metrics["wrongly_followed"] == 2
    assert metrics["correct_follow_rate"] == 0.5
    assert metrics["wrong_follow_rate"] == 0.5
    assert metrics["correct_follow_rate"] + metrics["wrong_follow_rate"] == 1.0
    assert "CFR" not in metrics
    assert "Precision" not in metrics
    assert "counts" not in metrics


def test_follow_taxonomy_reports_correct_wrong_and_neither() -> None:
    details = [
        {"follow_outcome": "correct_follow", "active_constraint_count": 1, "history_constraint_count": 2},
        {"follow_outcome": "wrong_follow", "active_constraint_count": 1, "history_constraint_count": 2},
        {"follow_outcome": "neither_followed", "active_constraint_count": 1, "history_constraint_count": 2},
    ]
    metrics = follow_taxonomy_metrics(details)

    assert metrics["comparison_count"] == 3
    assert metrics["constraint_count"] == 9
    assert metrics["correctly_followed"] == 1
    assert metrics["wrongly_followed"] == 1
    assert metrics["neither_followed"] == 1
    assert metrics["correct_follow_rate"] == 1 / 3
    assert metrics["wrong_follow_rate"] == 1 / 3
    assert metrics["neither_follow_rate"] == 1 / 3
