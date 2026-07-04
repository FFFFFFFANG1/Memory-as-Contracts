#!/usr/bin/env python3
"""Quality gates for SOP temporal graph evolution artifacts.

This script is intentionally read-only: it inspects step4 temporal sequence
JSON files and reports whether each task has enough graph evolution to behave
like SOP-temporal rather than simple stale-rule noise.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_STEP4 = Path("bench/MAC/sopbench/mid_data/eval_step4_temporal_sequence_v3.json")
DEFAULT_REPORT = Path("bench/MAC/sopbench/mid_data/eval_step4_temporal_quality.json")


@dataclass(frozen=True)
class QualityThresholds:
    min_events: int = 5
    min_final_edit_distance: int = 3
    min_stale_conflicts: int = 2


def resolve_path(path: Path) -> Path:
    return path if path.is_absolute() else REPO_ROOT / path


def load_json(path: Path) -> Any:
    return json.loads(resolve_path(path).read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    target = resolve_path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, indent=4, ensure_ascii=False) + "\n", encoding="utf-8")


def json_signature(value: Any) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False)


def graph_nodes(graph: Any) -> list[Any]:
    if not isinstance(graph, dict):
        return []
    nodes = graph.get("nodes")
    return nodes if isinstance(nodes, list) else []


def graph_edges(graph: Any) -> set[tuple[int, int]]:
    if not isinstance(graph, dict):
        return set()
    edges: set[tuple[int, int]] = set()
    for edge in graph.get("connections") or []:
        if (
            isinstance(edge, (list, tuple))
            and len(edge) == 2
            and isinstance(edge[0], int)
            and isinstance(edge[1], int)
        ):
            edges.add((edge[0], edge[1]))
    return edges


def graph_signature(graph: Any) -> str:
    if not isinstance(graph, dict):
        return ""
    return json_signature(
        {
            "nodes": graph_nodes(graph),
            "connections": sorted(graph_edges(graph)),
        }
    )


def multiset_distance(left: list[str], right: list[str]) -> int:
    left_counter = Counter(left)
    right_counter = Counter(right)
    keys = set(left_counter) | set(right_counter)
    return sum(abs(left_counter.get(key, 0) - right_counter.get(key, 0)) for key in keys)


def graph_edit_distance(left: Any, right: Any) -> int:
    left_nodes = [json_signature(node) for node in graph_nodes(left)]
    right_nodes = [json_signature(node) for node in graph_nodes(right)]
    left_edges = {json_signature(edge) for edge in sorted(graph_edges(left))}
    right_edges = {json_signature(edge) for edge in sorted(graph_edges(right))}
    return multiset_distance(left_nodes, right_nodes) + len(left_edges ^ right_edges)


def node_identity(node: Any) -> str:
    if isinstance(node, list) and node:
        return str(node[0])
    if isinstance(node, str):
        return node
    return type(node).__name__


def stale_conflict_count(active_graph: Any, historical_graphs: list[Any]) -> int:
    active_nodes = graph_nodes(active_graph)
    active_node_sigs = {json_signature(node) for node in active_nodes}
    active_identities = {node_identity(node) for node in active_nodes}

    conflicts: set[str] = set()
    stale_nodes: set[str] = set()
    for graph in historical_graphs:
        if graph_signature(graph) == graph_signature(active_graph):
            continue
        for node in graph_nodes(graph):
            node_sig = json_signature(node)
            if node_sig in active_node_sigs:
                continue
            stale_nodes.add(node_sig)
            if node_identity(node) in active_identities:
                conflicts.add(node_sig)

    # Same identity with changed params/operators is the strongest signal. If a
    # graph only adds/removes executable nodes, count those as stale conflicts too.
    return max(len(conflicts), min(len(stale_nodes), len(active_node_sigs) + 1))


def has_structural_change(sequence: list[dict[str, Any]]) -> bool:
    structural_prefixes = ("add_", "delete_", "flip_logic", "swap", "unwrap", "rewire", "rollback", "reinstate")
    for step in sequence:
        mutation = str(step.get("mutation") or "")
        if mutation.startswith(structural_prefixes):
            return True
        for key in ("graph_delta", "user_goal_graph_delta"):
            delta = step.get(key) or {}
            if not delta.get("graph_changed"):
                continue
            before_nodes = int(delta.get("nodes_before") or 0)
            after_nodes = int(delta.get("nodes_after") or 0)
            before_edges = int(delta.get("connections_before") or 0)
            after_edges = int(delta.get("connections_after") or 0)
            if before_nodes != after_nodes or before_edges != after_edges:
                return True
    return False


def first_graph(sequence: list[dict[str, Any]], anchor_graph: Any) -> Any:
    for step in sequence:
        graph = step.get("user_goal_action_graph")
        if isinstance(graph, dict) and graph.get("nodes"):
            return graph
    return anchor_graph


def last_graph(sequence: list[dict[str, Any]], anchor_graph: Any) -> Any:
    for step in reversed(sequence):
        graph = step.get("user_goal_action_graph")
        if isinstance(graph, dict) and graph.get("nodes"):
            return graph
    return anchor_graph


def initial_graph_from_task(task: dict[str, Any], sequence: list[dict[str, Any]], anchor_graph: Any) -> Any:
    g0_block = task.get("g0") or {}
    g0_graph = g0_block.get("user_goal_action_graph")
    if isinstance(g0_graph, dict) and graph_nodes(g0_graph):
        return g0_graph
    return first_graph(sequence, anchor_graph)


def noise_event_count(sequence: list[dict[str, Any]]) -> int:
    return sum(
        1
        for step in sequence
        if isinstance(step, dict) and str(step.get("kind") or "") != "anchor_alignment"
    )


def task_quality(
    task: dict[str, Any],
    *,
    active_mode: str,
    thresholds: QualityThresholds,
) -> dict[str, Any]:
    sequence = [step for step in task.get("temporal_sequence") or [] if isinstance(step, dict)]
    anchor_graph = task.get("anchor_user_goal_action_graph") or {}
    historical_graphs = [
        step.get("user_goal_action_graph")
        for step in sequence
        if isinstance(step.get("user_goal_action_graph"), dict)
    ]
    initial_graph = initial_graph_from_task(task, sequence, anchor_graph)
    active_graph = anchor_graph if active_mode == "anchor" else last_graph(sequence, anchor_graph)

    signatures = [graph_signature(graph) for graph in historical_graphs]
    active_sig = graph_signature(active_graph)
    stale_state_count = sum(1 for sig in signatures if sig and sig != active_sig)
    event_count = noise_event_count(sequence)
    edit_distance = graph_edit_distance(initial_graph, active_graph)
    stale_conflicts = stale_conflict_count(active_graph, historical_graphs)
    expired_or_revoked = stale_state_count > 0
    structural = has_structural_change(sequence)
    observable_failure = any(sig and sig != active_sig for sig in signatures)
    g0_graph = (task.get("g0") or {}).get("user_goal_action_graph") or initial_graph
    g0_ne_anchor = bool(graph_nodes(g0_graph)) and graph_signature(g0_graph) != graph_signature(anchor_graph)

    gates = {
        "min_5_temporal_events": event_count >= thresholds.min_events,
        "final_graph_edit_distance_ge_3": edit_distance >= thresholds.min_final_edit_distance,
        "stale_conflicts_ge_2": stale_conflicts >= thresholds.min_stale_conflicts,
        "has_expired_or_revoked_rule": expired_or_revoked,
        "has_structural_graph_change": structural,
        "old_version_causes_observable_failure": observable_failure,
        "g0_user_goal_graph_ne_anchor": g0_ne_anchor,
    }
    gates["all"] = all(gates.values())

    mutation_counts = Counter(
        str(step.get("mutation") or "unknown").split(":", 1)[0]
        for step in sequence
    )

    return {
        "mac_task_uid": task.get("mac_task_uid"),
        "domain": task.get("domain"),
        "user_goal": task.get("user_goal"),
        "active_graph_source": active_mode,
        "event_count": event_count,
        "noise_event_count": event_count,
        "history_event_count": max(event_count - 1, 0),
        "g0_user_goal_graph_ne_anchor": g0_ne_anchor,
        "g0_to_anchor_edit_distance": graph_edit_distance(g0_graph, anchor_graph),
        "source_action_count": task.get("source_action_count"),
        "final_graph_edit_distance": edit_distance,
        "stale_state_count": stale_state_count,
        "stale_conflict_count": stale_conflicts,
        "unique_historical_graph_states": len(set(sig for sig in signatures if sig)),
        "mutation_counts": dict(sorted(mutation_counts.items())),
        "gates": gates,
    }


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    task_count = len(rows)
    gate_names = [
        "min_5_temporal_events",
        "final_graph_edit_distance_ge_3",
        "stale_conflicts_ge_2",
        "has_expired_or_revoked_rule",
        "has_structural_graph_change",
        "old_version_causes_observable_failure",
        "g0_user_goal_graph_ne_anchor",
        "all",
    ]
    gate_pass_counts = {
        name: sum(1 for row in rows if (row.get("gates") or {}).get(name))
        for name in gate_names
    }

    def mean(field: str) -> float:
        values = [float(row.get(field) or 0) for row in rows]
        return sum(values) / len(values) if values else 0.0

    return {
        "task_count": task_count,
        "gate_pass_counts": gate_pass_counts,
        "gate_pass_rates": {
            name: (count / task_count if task_count else 0.0)
            for name, count in gate_pass_counts.items()
        },
        "avg_event_count": mean("event_count"),
        "avg_final_graph_edit_distance": mean("final_graph_edit_distance"),
        "avg_stale_state_count": mean("stale_state_count"),
        "avg_stale_conflict_count": mean("stale_conflict_count"),
    }


def payload_tasks(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, dict):
        tasks = payload.get("tasks")
    else:
        tasks = payload
    if not isinstance(tasks, list):
        raise TypeError("step4 payload must be a list or an object with tasks")
    return [task for task in tasks if isinstance(task, dict)]


def analyze_step4(path: Path, *, active_mode: str, thresholds: QualityThresholds) -> dict[str, Any]:
    payload = load_json(path)
    rows = [
        task_quality(task, active_mode=active_mode, thresholds=thresholds)
        for task in payload_tasks(payload)
    ]
    return {
        "source_step4": str(path),
        "generation_mode": payload.get("generation_mode") if isinstance(payload, dict) else None,
        "active_graph_source": active_mode,
        "summary": summarize(rows),
        "tasks": rows,
    }


def parse_input(raw: str) -> tuple[str, Path]:
    if "=" in raw:
        name, path = raw.split("=", 1)
        return name.strip() or Path(path).stem, Path(path)
    path = Path(raw)
    return path.stem, path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input",
        action="append",
        default=[],
        metavar="NAME=STEP4_JSON",
        help="Step4 file to analyze. Repeat to compare files.",
    )
    parser.add_argument(
        "--active-mode",
        choices=("anchor", "last"),
        default="anchor",
        help="Use anchor gold (current evaluator) or last replayed graph as active graph.",
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--min-events", type=int, default=5)
    parser.add_argument("--min-final-edit-distance", type=int, default=3)
    parser.add_argument("--min-stale-conflicts", type=int, default=2)
    return parser.parse_args()


def print_summary(report: dict[str, Any]) -> None:
    print(f"wrote {resolve_path(Path(report['output']))}")
    for name, result in report["results"].items():
        summary = result["summary"]
        rates = summary["gate_pass_rates"]
        counts = summary["gate_pass_counts"]
        task_count = summary["task_count"]
        print(
            f"{name}: tasks={task_count} active={result['active_graph_source']} "
            f"all_gates={counts['all']}/{task_count} ({rates['all']:.1%}) "
            f"avg_events={summary['avg_event_count']:.2f} "
            f"avg_edit={summary['avg_final_graph_edit_distance']:.2f} "
            f"avg_stale_conflicts={summary['avg_stale_conflict_count']:.2f}"
        )
        print(
            "  gates: "
            f"events={rates['min_5_temporal_events']:.1%}, "
            f"edit={rates['final_graph_edit_distance_ge_3']:.1%}, "
            f"stale={rates['stale_conflicts_ge_2']:.1%}, "
            f"expired={rates['has_expired_or_revoked_rule']:.1%}, "
            f"structural={rates['has_structural_graph_change']:.1%}, "
            f"g0_ne_anchor={rates.get('g0_user_goal_graph_ne_anchor', 0.0):.1%}, "
            f"observable={rates['old_version_causes_observable_failure']:.1%}"
        )


def main() -> int:
    args = parse_args()
    thresholds = QualityThresholds(
        min_events=args.min_events,
        min_final_edit_distance=args.min_final_edit_distance,
        min_stale_conflicts=args.min_stale_conflicts,
    )
    inputs = args.input or [f"v3={DEFAULT_STEP4}"]
    results = {
        name: analyze_step4(path, active_mode=args.active_mode, thresholds=thresholds)
        for name, path in (parse_input(raw) for raw in inputs)
    }
    report = {
        "schema_version": "MACSOPTemporalQualityV1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "active_graph_source": args.active_mode,
        "thresholds": {
            "min_events": thresholds.min_events,
            "min_final_edit_distance": thresholds.min_final_edit_distance,
            "min_stale_conflicts": thresholds.min_stale_conflicts,
        },
        "results": results,
        "output": str(args.output),
    }
    write_json(args.output, report)
    print_summary(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
