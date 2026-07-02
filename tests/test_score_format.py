from __future__ import annotations

from bench.MAC.grading.score_format import (
    MAIN_METRIC_ORDER,
    build_grade_document,
    format_main_scores,
    format_score_entries,
)


def test_format_main_scores_order_and_descriptions() -> None:
    entries = format_main_scores(
        {
            "joint pass": 0.4,
            "answer pass": 0.5,
            "constraint pass": 0.45,
            "constraint violation rate": 0.28,
        }
    )
    assert [entry["score_name"] for entry in entries] == list(MAIN_METRIC_ORDER)
    assert all(entry["description"] for entry in entries)
    assert entries[0]["value"] == 0.4


def test_build_grade_document_puts_scores_first() -> None:
    payload = build_grade_document(
        scores=format_score_entries({"joint pass": 1.0}, {"joint pass": "Task correct."}),
        schema_version="test",
    )
    assert list(payload.keys())[0] == "scores"
    assert payload["schema_version"] == "test"
