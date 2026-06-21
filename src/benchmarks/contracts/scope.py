from __future__ import annotations

from typing import Any


def merged_scope(current_scope: dict[str, Any], action_scope: dict[str, Any] | None = None) -> dict[str, Any]:
    """Combine current context scope and action-local scope."""
    merged = dict(current_scope)
    if action_scope:
        merged.update(action_scope)
    return merged


def scope_matches(contract_scope: dict[str, Any], current_scope: dict[str, Any]) -> bool:
    """Return true when every non-null contract scope key matches current scope."""
    for key, expected in contract_scope.items():
        if expected is None:
            continue
        if current_scope.get(key) != expected:
            return False
    return True


def specificity(contract_scope: dict[str, Any]) -> int:
    """Count concrete scope keys; used only for explicit tie diagnostics."""
    return sum(1 for value in contract_scope.values() if value is not None)
