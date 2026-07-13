"""Shared MAC-Bench grade score formatting."""

from __future__ import annotations

from typing import Any

MAIN_METRIC_ORDER = (
    "joint pass",
    "answer pass",
    "constraint pass",
    "constraint violation rate",
)

MAIN_METRIC_DESCRIPTIONS: dict[str, str] = {
    "joint pass": "Task-level full success: answer pass and task-level active constraint pass.",
    "answer pass": (
        "SOPBench user-goal correctness (action_called_correctly), or CCTU final answer text match."
    ),
    "constraint pass": (
        "Task-level all-or-nothing active constraint success: CCTU constraints_list, "
        "or SOPBench branch-aware active user-goal process scoring."
    ),
    "constraint violation rate": (
        "Lower is better: violated active constraints divided by total active constraints."
    ),
}

CCTU_LEGACY_METRIC_DESCRIPTIONS: dict[str, str] = {
    "SR": "Task succeeded with a valid final response (legacy CCTU).",
    "PSR": "Task succeeded and passed all per-task constraints (legacy CCTU).",
    "SSR": "Average constraints_list rule satisfaction rate retained for CCTU appendix reporting.",
    "step pass rate": "CCTU step success: satisfied unsolved_set tool-output slots divided by all required slots.",
}


def format_score_entries(
    values: dict[str, Any],
    descriptions: dict[str, str],
    *,
    metric_order: tuple[str, ...] | list[str] | None = None,
) -> list[dict[str, Any]]:
    order = list(metric_order or descriptions.keys())
    entries: list[dict[str, Any]] = []
    for name in order:
        if name not in descriptions:
            continue
        entries.append(
            {
                "score_name": name,
                "description": descriptions[name],
                "value": values.get(name),
            }
        )
    return entries


def format_main_scores(values: dict[str, Any]) -> list[dict[str, Any]]:
    return format_score_entries(values, MAIN_METRIC_DESCRIPTIONS, metric_order=MAIN_METRIC_ORDER)


def format_cctu_legacy_scores(values: dict[str, Any]) -> list[dict[str, Any]]:
    return format_score_entries(
        values,
        CCTU_LEGACY_METRIC_DESCRIPTIONS,
        metric_order=tuple(CCTU_LEGACY_METRIC_DESCRIPTIONS),
    )


def build_grade_document(*, scores: list[dict[str, Any]], **metadata: Any) -> dict[str, Any]:
    """Return a grade JSON object with ``scores`` first."""
    return {"scores": scores, **metadata}
