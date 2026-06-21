from __future__ import annotations

from collections.abc import Mapping
from typing import Any

FORBIDDEN_STATE_KEYS = {
    "contract_ids",
    "active_contract_ids",
    "hidden_graph",
    "gold",
    "decisive_relation_ids",
}


def summarize_state(state: Mapping[str, Any], *, allowed_keys: set[str] | None = None) -> dict[str, Any]:
    summary: dict[str, Any] = {}
    for key, value in state.items():
        if key in FORBIDDEN_STATE_KEYS:
            continue
        if allowed_keys is not None and key not in allowed_keys:
            continue
        summary[key] = value
    return summary
