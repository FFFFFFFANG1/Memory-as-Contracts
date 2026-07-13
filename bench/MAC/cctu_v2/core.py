"""Core directive lifecycle and trajectory validation for CCTU v2.

The v2 benchmark deliberately keeps its oracle small and deterministic.  Natural
language is a rendering of canonical events; it never decides the gold state.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any


ACTIVE_EVENTS = {"introduce", "amend", "reactivate", "override"}
INACTIVE_EVENTS = {"revoke", "expire", "supersede"}


def context_matches(scope: dict[str, Any], context: dict[str, Any]) -> bool:
    """Return whether every non-null scope dimension matches current context."""
    return all(value is None or context.get(key) == value for key, value in scope.items())


def resolve_active_directives(
    events: list[dict[str, Any]], current_context: dict[str, Any]
) -> list[dict[str, Any]]:
    """Resolve the latest version/status of every directive at a checkpoint."""
    states: dict[str, dict[str, Any]] = {}
    for event in sorted(events, key=lambda item: int(item["event_index"])):
        directive_id = str(event["directive_id"])
        event_type = str(event["event_type"])
        if event_type in ACTIVE_EVENTS:
            prior = states.get(directive_id, {})
            payload = deepcopy(prior)
            payload.update(deepcopy(event.get("directive") or {}))
            payload["directive_id"] = directive_id
            payload["version"] = int(event.get("version", prior.get("version", 0) + 1))
            payload["status"] = "active"
            payload["last_event_index"] = int(event["event_index"])
            states[directive_id] = payload
        elif event_type in INACTIVE_EVENTS:
            if directive_id in states:
                states[directive_id]["status"] = "inactive"
                states[directive_id]["last_event_index"] = int(event["event_index"])
        elif event_type == "consume_exception":
            if directive_id in states:
                states[directive_id]["status"] = "consumed"
                states[directive_id]["last_event_index"] = int(event["event_index"])
        else:
            raise ValueError(f"unsupported directive event: {event_type}")

    return sorted(
        [
            state
            for state in states.values()
            if state.get("status") == "active"
            and context_matches(state.get("scope") or {}, current_context)
        ],
        key=lambda item: str(item["directive_id"]),
    )


def candidate_allowed(
    active_directives: list[dict[str, Any]],
    trace_prefix: list[dict[str, Any]],
    candidate_action: dict[str, Any],
) -> bool:
    """Evaluate the bounded predicate types used in the pilot."""
    for directive in active_directives:
        predicate = directive.get("predicate") or {}
        kind = predicate.get("kind")
        if kind == "response_requirement":
            if candidate_action.get("kind") == "final_response" and not candidate_action.get(
                "complies", False
            ):
                return False
        elif kind in {"max_tool_calls", "max_rounds"}:
            if candidate_action.get("kind") != "tool_call":
                continue
            tool = predicate.get("tool")
            observed = sum(
                1
                for action in trace_prefix
                if action.get("kind") == "tool_call"
                and (tool is None or action.get("tool") == tool)
            )
            if observed >= int(predicate["limit"]):
                return False
        elif kind in {"min_tool_calls", "min_rounds"}:
            if candidate_action.get("kind") != "final_response":
                continue
            tool = predicate.get("tool")
            observed = sum(
                1
                for action in trace_prefix
                if action.get("kind") == "tool_call"
                and (tool is None or action.get("tool") == tool)
            )
            if observed < int(predicate["limit"]):
                return False
        elif kind == "require_before":
            if candidate_action.get("tool") != predicate.get("after_tool"):
                continue
            if not any(
                action.get("kind") == "tool_call"
                and action.get("tool") == predicate.get("before_tool")
                for action in trace_prefix
            ):
                return False
        elif kind == "deny_tool":
            if candidate_action.get("tool") == predicate.get("tool"):
                return False
        else:
            raise ValueError(f"unsupported predicate kind: {kind}")
    return True


def validate_episode(episode: dict[str, Any]) -> list[str]:
    """Return structural/oracle errors; an empty list means the episode is valid."""
    errors: list[str] = []
    events = episode.get("directive_events") or []
    context = episode.get("current_context") or {}
    prefixes = episode.get("trace_prefixes") or []
    worlds = episode.get("worlds") or []
    if not events and not worlds:
        errors.append("missing directive events/worlds")
    if not context.get("project"):
        errors.append("current context must name project")
    if not prefixes:
        errors.append("missing trace prefixes")
    seen_conditions: set[str] = set()
    for world in worlds or [{"world_id": "default", "directive_events": events}]:
        active = resolve_active_directives(world.get("directive_events") or events, context)
        for prefix in prefixes:
            condition_id = f"{world['world_id']}::{prefix['prefix_id']}"
            if condition_id in seen_conditions:
                errors.append(f"duplicate condition: {condition_id}")
            seen_conditions.add(condition_id)
            allowed = candidate_allowed(active, prefix.get("actions") or [], episode["candidate_action"])
            expected = (episode.get("gold_labels") or {}).get(condition_id)
            if expected is None:
                errors.append(f"missing gold label: {condition_id}")
            elif bool(expected) != allowed:
                errors.append(f"oracle mismatch: {condition_id}")
    return errors
