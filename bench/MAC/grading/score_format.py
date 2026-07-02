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
    "joint pass": "Task-level full success: SOPBench native success, or CCTU answer plus process constraints.",
    "answer pass": (
        "SOPBench user-goal correctness (action_called_correctly), or CCTU final answer text match."
    ),
    "constraint pass": (
        "Process only: CCTU satisfies every constraints_list rule over the full trajectory, "
        "or all SOPBench process fields pass (no_tool_call_error, constraint_not_violated, "
        "database_match, dirgraph_satisfied)."
    ),
    "constraint violation rate": "Lower is better: violated constraints divided by total constraints.",
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
