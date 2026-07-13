"""SOPBench delta-based noise-follow metric (experimental).

For each distinct obsolete user-goal graph state, compute the user-goal dependency
delta against the final anchor dependency, deduplicate changed singles, then count
how many delta items the eval trajectory matches when the anchor graph is not
satisfied under strict replay.
"""

from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass
from typing import Any, Literal

from bench.MAC.construct.sop.noise_eval import (
    anchor_directed_action_graph,
    anchor_user_goal_dependency,
    cumulative_user_goal_graph,
    evaluate_sopbench_unit,
    evaluate_task,
    func_calls_from_trace,
    parse_single_identity,
    user_goal_dependency,
)
from bench.MAC.construct.sop.temporal_assemble import singles_counter, singles_lookup

DeltaDirection = Literal["added", "removed"]


@dataclass(frozen=True, slots=True)
class DeltaItem:
    """One user-goal dependency single that differs between anchor and a noise state."""

    constraint_key: str
    direction: DeltaDirection

    @property
    def delta_id(self) -> str:
        return f"{self.direction}:{self.constraint_key}"


def graph_key(graph: dict[str, Any]) -> str:
    payload = json.dumps(graph, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def dependency_delta_items(
    *,
    anchor_dep: Any,
    noise_dep: Any,
) -> list[DeltaItem]:
    """Return changed user-goal dependency singles (anchor -> noise)."""
    before_counter = singles_counter(anchor_dep)
    after_counter = singles_counter(noise_dep)
    items: list[DeltaItem] = []
    for key in sorted(set(before_counter) | set(after_counter)):
        before_count = before_counter.get(key, 0)
        after_count = after_counter.get(key, 0)
        if after_count > before_count:
            items.append(DeltaItem(constraint_key=key, direction="added"))
        elif before_count > after_count:
            items.append(DeltaItem(constraint_key=key, direction="removed"))
    return items


def collect_unique_delta_set(
    *,
    step2_task: dict[str, Any],
    sequence: list[dict[str, Any]],
) -> set[DeltaItem]:
    """Deduplicated dependency deltas for all distinct noise user-goal graph states."""
    anchor_graph = anchor_directed_action_graph(step2_task)
    anchor_key = graph_key(anchor_graph)
    anchor_dep = anchor_user_goal_dependency(step2_task)
    action_deps: dict[str, Any] = {}
    seen_graphs: set[str] = set()
    unique: set[DeltaItem] = set()

    for step in sequence:
        if not isinstance(step, dict):
            continue
        mutated_action = str(step.get("action") or "").strip()
        dependency = step.get("dependency")
        if mutated_action and dependency is not None:
            action_deps[mutated_action] = copy.deepcopy(dependency)
        try:
            graph = cumulative_user_goal_graph(
                step2_task,
                action_deps,
                fallback_graph=step.get("user_goal_action_graph"),
            )
            noise_dep = user_goal_dependency(step2_task, action_deps)
        except Exception:
            continue
        key = graph_key(graph)
        if key == anchor_key or key in seen_graphs:
            continue
        seen_graphs.add(key)
        for item in dependency_delta_items(anchor_dep=anchor_dep, noise_dep=noise_dep):
            unique.add(item)
    return unique


def anchor_graph_satisfied(*, task_spec: dict[str, Any], trace: dict[str, Any]) -> bool:
    if not func_calls_from_trace(trace):
        return False
    task_eval = evaluate_task(task_spec=task_spec, trace=trace)
    return bool(task_eval.get("dirgraph_satisfied"))


def evaluate_single_observed(
    *,
    constraint_key: str,
    task_spec: dict[str, Any],
    trace: dict[str, Any],
    replay: dict[str, Any],
) -> bool | None:
    try:
        payload = json.loads(constraint_key)
        constraint_id = str(payload["constraint_id"])
        params = payload.get("params") if isinstance(payload.get("params"), dict) else {}
    except (json.JSONDecodeError, KeyError, TypeError):
        return None

    unit = {
        "evaluator_type": "sopbench_single",
        "constraint_id": constraint_id,
        "normalized_constraint_id": parse_single_identity(constraint_id)[0],
        "params": copy.deepcopy(params),
    }
    result = evaluate_sopbench_unit(
        unit=unit,
        task_spec=task_spec,
        trace=trace,
        replay=replay,
    )
    observed = result.get("observed_followed")
    if observed not in {True, False}:
        return None
    return bool(observed)


def delta_item_hit(
    *,
    item: DeltaItem,
    task_spec: dict[str, Any],
    trace: dict[str, Any],
    replay: dict[str, Any],
) -> bool:
    observed = evaluate_single_observed(
        constraint_key=item.constraint_key,
        task_spec=task_spec,
        trace=trace,
        replay=replay,
    )
    if observed is None:
        return False
    if item.direction == "added":
        return observed
    return not observed


def evaluate_task_delta_noise_follow(
    *,
    step2_task: dict[str, Any],
    task_spec: dict[str, Any],
    sequence: list[dict[str, Any]],
    trace: dict[str, Any],
) -> dict[str, Any]:
    unique_deltas = collect_unique_delta_set(step2_task=step2_task, sequence=sequence)
    has_tool_calls = bool(func_calls_from_trace(trace))
    anchor_ok = anchor_graph_satisfied(task_spec=task_spec, trace=trace) if has_tool_calls else False
    task_eval = evaluate_task(task_spec=task_spec, trace=trace)
    replay = task_eval.pop("_replay", None) or {}

    if not has_tool_calls or anchor_ok or not unique_deltas:
        return {
            "anchor_graph_satisfied": anchor_ok,
            "has_tool_calls": has_tool_calls,
            "unique_delta_count": len(unique_deltas),
            "delta_hit_count": 0,
            "delta_hit_ids": [],
            "delta_noise_follow_rate": 0.0 if unique_deltas else None,
        }

    hit_ids: list[str] = []
    for item in sorted(unique_deltas, key=lambda row: row.delta_id):
        if delta_item_hit(item=item, task_spec=task_spec, trace=trace, replay=replay):
            hit_ids.append(item.delta_id)

    count = len(unique_deltas)
    return {
        "anchor_graph_satisfied": anchor_ok,
        "has_tool_calls": has_tool_calls,
        "unique_delta_count": count,
        "delta_hit_count": len(hit_ids),
        "delta_hit_ids": hit_ids,
        "delta_noise_follow_rate": len(hit_ids) / count if count else None,
    }


def aggregate_delta_noise_follow(per_task: list[dict[str, Any]]) -> dict[str, Any]:
    total_deltas = sum(int(row.get("unique_delta_count") or 0) for row in per_task)
    total_hits = sum(int(row.get("delta_hit_count") or 0) for row in per_task)
    anchor_missed = [row for row in per_task if not row.get("anchor_graph_satisfied")]
    missed_deltas = sum(int(row.get("unique_delta_count") or 0) for row in anchor_missed)
    missed_hits = sum(int(row.get("delta_hit_count") or 0) for row in anchor_missed)
    return {
        "task_count": len(per_task),
        "unique_delta_count": total_deltas,
        "delta_hit_count": total_hits,
        "delta_noise_follow_rate": (total_hits / total_deltas) if total_deltas else None,
        "anchor_missed_task_count": len(anchor_missed),
        "anchor_missed_unique_delta_count": missed_deltas,
        "anchor_missed_delta_hit_count": missed_hits,
        "anchor_missed_delta_noise_follow_rate": (
            missed_hits / missed_deltas if missed_deltas else None
        ),
    }
