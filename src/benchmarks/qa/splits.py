from __future__ import annotations

from collections import defaultdict
from typing import Literal

from benchmarks.schemas.models import QAItem

Split = Literal["development", "public_test", "hidden_test"]


def validate_event_group_splits(items: list[QAItem]) -> None:
    by_group: dict[str, set[str]] = defaultdict(set)
    for item in items:
        if item.event_group_id and item.split:
            by_group[item.event_group_id].add(item.split)
    bad = {group: sorted(splits) for group, splits in by_group.items() if len(splits) > 1}
    if bad:
        raise ValueError(f"event groups assigned to multiple splits: {bad}")


def assign_split_by_event_group(items: list[QAItem], assignments: dict[str, Split]) -> list[QAItem]:
    assigned: list[QAItem] = []
    for item in items:
        key = item.event_group_id or item.qa_id
        split = assignments.get(key)
        if split is None:
            raise ValueError(f"missing split assignment for {key}")
        assigned.append(item.model_copy(update={"split": split}))
    validate_event_group_splits(assigned)
    return assigned
