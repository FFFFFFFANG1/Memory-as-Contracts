from __future__ import annotations

from bench.MAC.scripts.grade_cctu_answer import compute_ssr


def test_compute_ssr_all_satisfied() -> None:
    assert compute_ssr(constraint_total=5, violated_indices=set()) == 1.0


def test_compute_ssr_partial() -> None:
    assert compute_ssr(constraint_total=4, violated_indices={1, 3}) == 0.5


def test_compute_ssr_empty_total() -> None:
    assert compute_ssr(constraint_total=0, violated_indices={0}) == 1.0
