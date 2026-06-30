"""Trajectory helpers for MAC benchmark grading."""

from __future__ import annotations

from typing import Any


def _compact_tool_output(value: Any) -> Any:
    if isinstance(value, dict):
        payload = value
        while (
            isinstance(payload, dict)
            and "result" in payload
            and isinstance(payload.get("result"), (dict, list, str, int, float, bool, type(None)))
            and any(key in payload for key in ("source", "route", "attempt", "cached", "simulated", "ok"))
        ):
            payload = payload["result"]
        if isinstance(payload, dict):
            return {
                key: _compact_tool_output(item)
                for key, item in payload.items()
                if key not in {"source", "route", "attempt", "cached", "simulated", "ok"}
            }
        return payload
    if isinstance(value, list):
        return [_compact_tool_output(item) for item in value]
    return value


def _event_tool_calls(event: dict[str, Any]) -> list[dict[str, Any]]:
    calls = event.get("tool_calls")
    if not isinstance(calls, list):
        return []
    out: list[dict[str, Any]] = []
    for call in calls:
        if not isinstance(call, dict):
            continue
        call_id = call.get("id")
        name = call.get("name")
        arguments = call.get("arguments")
        if not isinstance(name, str) or not name:
            continue
        item: dict[str, Any] = {"name": name, "arguments": arguments if isinstance(arguments, dict) else {}}
        if isinstance(call_id, str) and call_id:
            item["id"] = call_id
        out.append(item)
    return out


def _tool_result_payload(event: dict[str, Any]) -> Any:
    """Prefer the actual tool result when runtime metadata is empty."""
    runtime = event.get("runtime")
    result = event.get("result")
    if runtime is None:
        return result
    if isinstance(runtime, dict) and not runtime:
        return result
    return runtime


def build_raw_history(row: dict[str, Any]) -> dict[str, Any]:
    """Build the compact evaluator-facing trajectory from a MAC task result row."""
    final_response = row.get("final_answer")
    events = row.get("events")
    trajectory: list[dict[str, Any]] = []
    calls_by_id: dict[str, dict[str, Any]] = {}
    reasoning_by_iteration: dict[int, str] = {}

    if not isinstance(events, list):
        return {
            "final_response": final_response if isinstance(final_response, str) else "",
            "trajectory": trajectory,
        }

    for event in events:
        if not isinstance(event, dict):
            continue
        if event.get("event") == "reasoning":
            iteration = event.get("iteration")
            text = event.get("text")
            if isinstance(iteration, int) and isinstance(text, str) and text:
                reasoning_by_iteration[iteration] = text
            continue
        if event.get("event") != "model_response":
            continue

        iteration = event.get("iteration")
        content = event.get("content")
        step: dict[str, Any] = {
            "kind": "assistant",
            "iteration": iteration if isinstance(iteration, int) else None,
            "content": content if isinstance(content, str) and content else reasoning_by_iteration.get(iteration, ""),
            "tool_calls": [],
        }
        for call in _event_tool_calls(event):
            step["tool_calls"].append(call)
            call_id = call.get("id")
            if isinstance(call_id, str) and call_id:
                calls_by_id[call_id] = call
        trajectory.append(step)

    for event in events:
        if not isinstance(event, dict) or event.get("event") != "tool_result":
            continue
        call_id = event.get("tool_call_id")
        target = calls_by_id.get(call_id) if isinstance(call_id, str) else None
        if target is None:
            continue
        source = _tool_result_payload(event)
        target["result"] = _compact_tool_output(source)

    return {
        "final_response": final_response if isinstance(final_response, str) else "",
        "trajectory": trajectory,
    }
