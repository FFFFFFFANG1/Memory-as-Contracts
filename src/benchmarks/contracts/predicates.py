from __future__ import annotations

from typing import Any

from benchmarks.schemas.models import ActionPredicate, CanonicalAction


def _action_value(action: CanonicalAction, key: str) -> Any:
    if key == "effect":
        return action.effect_summary
    if hasattr(action, key):
        return getattr(action, key)
    if key in action.arguments:
        return action.arguments[key]
    if key in action.scope:
        return action.scope[key]
    return None


def predicate_matches(predicate: ActionPredicate, action: CanonicalAction) -> bool:
    """Return true when the action falls under the contract predicate."""
    if predicate.family != action.family:
        return False
    for key in ("object", "target", "effect"):
        expected = getattr(predicate, key)
        if expected is None:
            continue
        actual = _action_value(action, key)
        if actual != expected:
            return False
    for key, expected in predicate.attributes.items():
        if expected is None:
            continue
        if _action_value(action, key) != expected:
            return False
    return True
