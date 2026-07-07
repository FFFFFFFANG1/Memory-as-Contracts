#!/usr/bin/env python3
"""Grade SOP temporal noise eval specs against a memory-eval run output."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

if sys.version_info < (3, 10):
    raise SystemExit("SOP noise eval requires Python 3.10+ (SOPBench dependency).")

from bench.MAC.agent.trajectory import build_raw_history  # noqa: E402
from bench.MAC.construct.sop.noise_eval import (  # noqa: E402
    _replay_trajectory,
    anchor_directed_action_graph,
    contract_metrics,
    cumulative_user_goal_graph,
    evaluate_sopbench_unit,
    evaluate_task,
    follow_outcome,
    follow_taxonomy_metrics,
    func_calls_from_trace,
    graph_action_nodes,
    load_json,
    outcome_bucket,
    resolve_path,
    task_acc,
    task_answer_pass,
    task_joint_pass,
    task_process_constraint_pass,
    task_responded,
    write_json,
)
from bench.MAC.grading.score_format import build_grade_document, format_main_scores  # noqa: E402
from bench.MAC.scripts.run_paths import bench_grade_path, make_run_unique_index  # noqa: E402

DEFAULT_MANIFEST = Path("bench/MAC/sopbench/data/mac-sopbench-noise_eval_specs.json")
DEFAULT_OUTPUT = Path("bench/MAC/sopbench/results/eval_step6_noise_eval_grade.json")
DEFAULT_STEP2 = Path("bench/MAC/sopbench/mid_data/eval_step2_anchors.json")
DEFAULT_STEP4 = Path("bench/MAC/sopbench/mid_data/eval_step4_temporal_sequence_v3.json")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "answers_file",
        type=Path,
        nargs="?",
        help="JSON output from bench/MAC/scripts/run_memory_eval.py",
    )
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--step2", type=Path, default=DEFAULT_STEP2)
    parser.add_argument("--step4", type=Path, default=DEFAULT_STEP4)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--bench", choices=["sopbench"], default="sopbench")
    parser.add_argument("--memory-system")
    parser.add_argument("--run-id")
    parser.add_argument("--detail", action="store_true")
    parser.add_argument(
        "--dry-run-empty",
        action="store_true",
        help="Grade manifest structure only using empty trajectories (smoke test).",
    )
    return parser.parse_args()


def infer_memory_system(args: argparse.Namespace, header: dict[str, Any]) -> str:
    return str(args.memory_system or header.get("memory_system") or "unknown")


def output_path(
    args: argparse.Namespace,
    *,
    header: dict[str, Any],
    memory_system: str,
) -> Path:
    if args.output:
        return args.output
    run_id = args.run_id or header.get("run_id") or make_run_unique_index()
    if args.output_dir:
        return args.output_dir / f"{memory_system}_{args.bench}_{run_id}.json"
    return bench_grade_path(memory_system, args.bench, str(run_id))


def read_memory_output(path: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    payload = load_json(path)
    if not isinstance(payload, dict):
        raise TypeError(f"{path} must contain a JSON object")
    header = payload.get("header")
    records = payload.get("records")
    if isinstance(header, dict) and isinstance(records, list):
        return header, [row for row in records if isinstance(row, dict)]
    raise ValueError(f"{path} is not a MACMemoryOutputV1 file")


def flatten_tool_calls(raw_history: dict[str, Any]) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []
    for step in raw_history.get("trajectory") or []:
        if not isinstance(step, dict):
            continue
        iteration = step.get("iteration")
        for call in step.get("tool_calls") or []:
            if not isinstance(call, dict):
                continue
            calls.append(
                {
                    "index": len(calls),
                    "iteration": iteration,
                    "name": call.get("name"),
                    "arguments": call.get("arguments") if isinstance(call.get("arguments"), dict) else {},
                    "result": call.get("result"),
                }
            )
    return calls


def trace_from_row(row: dict[str, Any]) -> dict[str, Any]:
    raw = build_raw_history(row)
    return {
        "final_response": raw.get("final_response", ""),
        "trajectory": raw.get("trajectory", []),
        "tool_calls": flatten_tool_calls(raw),
    }


def grouped_main_scores(
    details: list[dict[str, Any]],
    key: str,
    task_scores: dict[str, Any],
) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in details:
        grouped[str(row.get(key) or "unknown")].append(row)
    score_groups: dict[str, list[dict[str, Any]]] = {}
    for name, rows in sorted(grouped.items()):
        task_uids = {str(row.get("task_uid") or "") for row in rows}
        group_task_scores = {
            task_uid: task_scores[task_uid] for task_uid in task_uids if task_uid in task_scores
        }
        score_groups[name] = format_main_scores(with_task_scores(group_task_scores))
    return score_groups


def graph_key(graph: dict[str, Any]) -> str:
    payload = json.dumps(graph, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def index_by_uid(items: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {str(item["mac_task_uid"]): item for item in items if item.get("mac_task_uid")}


def collect_history_graphs(step2: dict[str, Any], sequence: list[dict[str, Any]]) -> list[dict[str, Any]]:
    anchor = anchor_directed_action_graph(step2)
    anchor_key = graph_key(anchor)
    action_deps: dict[str, Any] = {}
    seen: set[str] = set()
    graphs: list[dict[str, Any]] = []
    for step in sequence:
        if not isinstance(step, dict):
            continue
        mutated_action = str(step.get("action") or "").strip()
        dependency = step.get("dependency")
        order = int(step.get("sequence_order") or 0)
        if mutated_action and dependency is not None:
            action_deps[mutated_action] = copy.deepcopy(dependency)
        try:
            graph = cumulative_user_goal_graph(
                step2,
                action_deps,
                fallback_graph=step.get("user_goal_action_graph"),
            )
        except Exception:
            continue
        key = graph_key(graph)
        if key == anchor_key or key in seen:
            continue
        seen.add(key)
        graphs.append({"sequence_order": order, "graph": graph, "graph_key": key})
    return graphs


def dirgraph_satisfied_for_graph(
    *,
    domain: str,
    patched_task: dict[str, Any],
    graph: dict[str, Any],
    trace: dict[str, Any],
) -> bool:
    task = copy.deepcopy(patched_task)
    task["directed_action_graph"] = copy.deepcopy(graph)
    func_calls = func_calls_from_trace(trace)
    if not func_calls:
        return False
    try:
        replay = _replay_trajectory(domain, task, func_calls)
    except Exception:
        return False
    return bool(replay["evaluation"].get("dirgraph_satisfied"))


def obsolete_only_nodes(*, anchor_graph: dict[str, Any], history_graph: dict[str, Any], user_goal: str) -> set[str]:
    anchor_nodes = graph_action_nodes(anchor_graph)
    history_nodes = graph_action_nodes(history_graph)
    return history_nodes - anchor_nodes - {user_goal}


def strict_history_graph_hit(
    *,
    domain: str,
    patched_task: dict[str, Any],
    anchor_graph: dict[str, Any],
    history_graph: dict[str, Any],
    user_goal: str,
    trace: dict[str, Any],
    successful_actions: set[str],
) -> bool:
    if not func_calls_from_trace(trace):
        return False
    obsolete_only = obsolete_only_nodes(
        anchor_graph=anchor_graph,
        history_graph=history_graph,
        user_goal=user_goal,
    )
    if not obsolete_only or not (obsolete_only & successful_actions):
        return False
    return dirgraph_satisfied_for_graph(
        domain=domain,
        patched_task=patched_task,
        graph=history_graph,
        trace=trace,
    )


def dependency_map(graph: dict[str, Any]) -> dict[int, list[int]]:
    """Map each node index to its prerequisite child indices (from -> dep)."""
    deps: dict[int, list[int]] = defaultdict(list)
    for edge in graph.get("connections") or []:
        if not isinstance(edge, (list, tuple)) or len(edge) < 2:
            continue
        deps[int(edge[0])].append(int(edge[1]))
    return deps


def user_goal_node_index(graph: dict[str, Any], user_goal: str) -> int:
    for index, node in enumerate(graph.get("nodes") or []):
        if isinstance(node, (list, tuple)) and node and str(node[0]) == user_goal:
            return index
    return 0


def _score_process_node(
    *,
    nodes: list[Any],
    deps: dict[int, list[int]],
    node_index: int,
    order_respecting_actions: set[str],
) -> tuple[int, int]:
    node = nodes[node_index]
    if isinstance(node, (list, tuple)) and node:
        action = str(node[0])
        matched = 1 if action in order_respecting_actions else 0
        return matched, 1

    logic = str(node).lower()
    child_indices = deps.get(node_index, [])
    if not child_indices:
        return 0, 0

    child_scores = [
        _score_process_node(
            nodes=nodes,
            deps=deps,
            node_index=child_index,
            order_respecting_actions=order_respecting_actions,
        )
        for child_index in child_indices
    ]
    if logic in {"or", "gate"}:
        return max(
            child_scores,
            key=lambda pair: (pair[0] / pair[1] if pair[1] else 0.0, pair[0]),
        )
    matched = sum(pair[0] for pair in child_scores)
    total = sum(pair[1] for pair in child_scores)
    return matched, total


def score_branch_aware_active_process(
    *,
    graph: dict[str, Any],
    order_respecting_actions: set[str],
    user_goal: str,
) -> dict[str, Any]:
    """Branch-aware active user-goal process support for one task."""
    nodes = graph.get("nodes") or []
    if not nodes:
        return {
            "constraint pass": True,
            "constraint_satisfied": 0,
            "constraint_total": 0,
            "constraint violation rate": 0.0,
        }

    deps = dependency_map(graph)
    root_index = user_goal_node_index(graph, user_goal)
    root_children = deps.get(root_index, [])
    if not root_children:
        return {
            "constraint pass": True,
            "constraint_satisfied": 0,
            "constraint_total": 0,
            "constraint violation rate": 0.0,
        }

    matched = 0
    total = 0
    for child_index in root_children:
        child_matched, child_total = _score_process_node(
            nodes=nodes,
            deps=deps,
            node_index=child_index,
            order_respecting_actions=order_respecting_actions,
        )
        matched += child_matched
        total += child_total

    constraint_pass = matched == total
    violation_rate = (1.0 - matched / total) if total else 0.0
    return {
        "constraint pass": constraint_pass,
        "constraint_satisfied": matched,
        "constraint_total": total,
        "constraint violation rate": violation_rate,
    }


def build_contract_diagnostics(details: list[dict[str, Any]]) -> dict[str, Any]:
    contract = follow_taxonomy_metrics(details)
    return {
        "constraint_follow_scores": {
            "noise_follow_rate": contract["noise_follow_rate"],
        },
        "support": {
            "comparison_count": contract["comparison_count"],
            "constraint_count": contract["constraint_count"],
            "active_constraint_count": contract["active_constraint_count"],
            "history_constraint_count": contract["history_constraint_count"],
            "noise_followed": contract["noise_followed"],
        },
    }


def apply_native_process_constraint_scores(
    task_scores: dict[str, Any],
    *,
    task_evals: dict[str, dict[str, Any]],
) -> None:
    """Set per-task process metrics from SOPBench-native replay fields."""
    for task_uid, score in task_scores.items():
        task_eval = task_evals.get(task_uid) or {}
        process_pass = task_process_constraint_pass(task_eval)
        if process_pass is None:
            process_pass = True
        joint_pass = task_joint_pass(task_eval)
        if joint_pass is None:
            joint_pass = bool(score.get("answer pass") and process_pass)
        score["constraint pass"] = process_pass
        score["constraint_satisfied"] = 1 if process_pass else 0
        score["constraint_total"] = 1
        score["joint pass"] = joint_pass


def apply_branch_aware_process_scores(
    task_scores: dict[str, Any],
    *,
    task_specs: dict[str, dict[str, Any]],
    replay_by_task: dict[str, dict[str, Any] | None],
    task_evals: dict[str, dict[str, Any]] | None = None,
) -> None:
    """Set main process metrics from branch-aware active user-goal directed graphs."""
    task_evals = task_evals or {}
    for task_uid, score in task_scores.items():
        task_spec = task_specs.get(task_uid) or {}
        patched = task_spec.get("patched_sopbench_task") if isinstance(task_spec.get("patched_sopbench_task"), dict) else {}
        graph = patched.get("directed_action_graph") if isinstance(patched.get("directed_action_graph"), dict) else {}
        replay = replay_by_task.get(task_uid) or {}
        order_respecting_actions = {
            str(action)
            for action in (replay.get("order_respecting_actions") or set())
        }
        user_goal = str(task_spec.get("user_goal") or patched.get("user_goal") or "")
        process = score_branch_aware_active_process(
            graph=graph,
            order_respecting_actions=order_respecting_actions,
            user_goal=user_goal,
        )
        native_process_pass = task_process_constraint_pass(task_evals.get(task_uid) or {})
        constraint_pass = (
            native_process_pass
            if native_process_pass is not None
            else process["constraint pass"]
        )
        if constraint_pass:
            process["constraint_satisfied"] = process["constraint_total"]
            process["constraint violation rate"] = 0.0
        answer_pass = score.get("answer pass")
        score["constraint pass"] = constraint_pass
        score["constraint_satisfied"] = process["constraint_satisfied"]
        score["constraint_total"] = process["constraint_total"]
        score["constraint violation rate"] = process["constraint violation rate"]
        score["joint pass"] = (
            bool(answer_pass and constraint_pass)
            if answer_pass is not None
            else None
        )


def apply_active_constraint_scores(
    task_scores: dict[str, Any],
    *,
    details_by_task: dict[str, list[dict[str, Any]]],
) -> None:
    """Set flat graph_action diagnostic process metrics (not main headline scoring)."""
    for task_uid, score in task_scores.items():
        rows = details_by_task.get(task_uid, [])
        row_contract = contract_metrics(rows)
        row_outcome = row_contract["outcome_counts"]
        active_total = row_contract["active_constraint_count"]
        active_missed = row_outcome["active_missed"]
        active_followed = row_outcome["active_followed"]
        constraint_pass = active_missed == 0
        answer_pass = score.get("answer pass")
        score["constraint pass"] = constraint_pass
        score["constraint_satisfied"] = active_followed
        score["constraint_total"] = active_total
        score["constraint violation rate"] = active_missed / active_total if active_total else 0.0
        score["joint pass"] = (
            bool(answer_pass and constraint_pass)
            if answer_pass is not None
            else None
        )


def with_task_scores(task_scores: dict[str, Any]) -> dict[str, Any]:
    answer_values = [
        row.get("answer pass") for row in task_scores.values() if row.get("answer pass") is not None
    ]
    constraint_values = [
        row.get("constraint pass")
        for row in task_scores.values()
        if row.get("constraint pass") is not None
    ]
    joint_values = [row.get("joint pass") for row in task_scores.values() if row.get("joint pass") is not None]
    matched_steps = sum(int(row.get("constraint_satisfied") or 0) for row in task_scores.values())
    total_steps = sum(int(row.get("constraint_total") or 0) for row in task_scores.values())
    return {
        "joint pass": (sum(1 for value in joint_values if value) / len(joint_values)) if joint_values else None,
        "answer pass": (
            sum(1 for value in answer_values if value) / len(answer_values) if answer_values else None
        ),
        "constraint pass": (
            sum(1 for value in constraint_values if value) / len(constraint_values)
            if constraint_values
            else None
        ),
        "constraint violation rate": (
            (1.0 - matched_steps / total_steps) if total_steps else 0.0
        ),
    }


def with_flat_unit_diagnostic_scores(
    contract: dict[str, Any],
    task_scores: dict[str, Any],
) -> dict[str, Any]:
    """Diagnostic headline row mixing task answer/constraint pass with flat unit CVR."""
    scores = with_task_scores(task_scores)
    scores["constraint violation rate"] = (
        contract["outcome_counts"]["active_missed"] / contract["active_constraint_count"]
        if contract["active_constraint_count"]
        else 0.0
    )
    return scores


def tool_unit_breakdown(tool_call_details: list[dict[str, Any]]) -> dict[str, Any]:
    counts = contract_metrics(tool_call_details)
    outcome = counts["outcome_counts"]
    active_total = counts["active_constraint_count"]
    history_total = counts["history_constraint_count"]
    unit_total = counts["constraint_count"]
    return {
        "active_followed_constraints": outcome["active_followed"],
        "active_missed_constraints": outcome["active_missed"],
        "history_followed_constraints": outcome["history_followed"],
        "history_ignored_constraints": outcome["history_ignored"],
        "active_constraint_count": active_total,
        "history_constraint_count": history_total,
        "constraint_count": unit_total,
        "rates": {
            "active_followed_rate": outcome["active_followed"] / active_total if active_total else None,
            "active_missed_rate": outcome["active_missed"] / active_total if active_total else None,
            "history_followed_rate": outcome["history_followed"] / history_total if history_total else None,
            "history_ignored_rate": outcome["history_ignored"] / history_total if history_total else None,
            "active_followed_share": outcome["active_followed"] / unit_total if unit_total else None,
            "active_missed_share": outcome["active_missed"] / unit_total if unit_total else None,
            "history_followed_share": outcome["history_followed"] / unit_total if unit_total else None,
            "history_ignored_share": outcome["history_ignored"] / unit_total if unit_total else None,
        },
    }


def main() -> int:
    args = parse_args()
    manifest = load_json(args.manifest)
    units = manifest.get("units") if isinstance(manifest, dict) else None
    task_specs = manifest.get("task_specs") if isinstance(manifest, dict) else None
    if not isinstance(units, list) or not isinstance(task_specs, dict):
        raise ValueError("manifest must contain units list and task_specs object")
    step2_by_uid = index_by_uid(load_json(args.step2))
    step4_payload = load_json(args.step4)
    step4_tasks = step4_payload.get("tasks") if isinstance(step4_payload, dict) else step4_payload
    step4_by_uid = index_by_uid(step4_tasks) if isinstance(step4_tasks, list) else {}

    header: dict[str, Any] = {}
    traces: dict[str, dict[str, Any]] = {}
    if args.dry_run_empty:
        for task_uid in task_specs:
            traces[task_uid] = {"final_response": "", "trajectory": [], "tool_calls": []}
    else:
        if args.answers_file is None:
            raise ValueError("answers_file is required unless --dry-run-empty is set")
        header, records = read_memory_output(args.answers_file)
        rows_by_task = {
            str(row.get("task_uid")): row
            for row in records
            if row.get("record_type") == "task_result" and row.get("task_uid")
        }
        traces = {task_uid: trace_from_row(row) for task_uid, row in rows_by_task.items()}

    details: list[dict[str, Any]] = []
    task_scores: dict[str, Any] = {}
    task_evals: dict[str, dict[str, Any]] = {}
    replay_by_task: dict[str, dict[str, Any] | None] = {}
    tool_behavior_by_task: dict[str, Any] = {}
    contract_follow_details: list[dict[str, Any]] = []
    missing_tasks = 0
    units_by_task: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for unit in units:
        if isinstance(unit, dict):
            units_by_task[str(unit.get("task_uid") or "")].append(unit)

    for task_uid, task_units in sorted(units_by_task.items()):
        trace = traces.get(task_uid)
        task_spec = task_specs.get(task_uid)
        if trace is None or not isinstance(task_spec, dict):
            missing_tasks += len(task_units)
            continue
        task_eval = evaluate_task(task_spec=task_spec, trace=trace)
        replay_cache = task_eval.pop("_replay", None)
        task_evals[task_uid] = task_eval
        replay_by_task[task_uid] = replay_cache
        answer_pass = task_answer_pass(task_eval)
        success = task_acc(task_eval)
        task_scores[task_uid] = {
            "answer pass": answer_pass,
            "RSP": task_responded(trace),
            "dirgraph_satisfied": task_eval.get("dirgraph_satisfied") if task_eval else None,
            "action_called_correctly": task_eval.get("action_called_correctly") if task_eval else None,
            "success": success,
            "legacy_ACC": success,
        }
        graph_action_units = [unit for unit in task_units if unit.get("unit_source") == "graph_action"]
        anchor_tool_ids = {
            str(unit.get("normalized_constraint_id") or unit.get("constraint_id") or "")
            for unit in graph_action_units
            if unit.get("expected_should_apply")
        }
        history_tool_ids = {
            str(unit.get("normalized_constraint_id") or unit.get("constraint_id") or "")
            for unit in graph_action_units
            if not unit.get("expected_should_apply")
        }
        successful_actions = set()
        order_respecting_actions = set()
        if replay_cache:
            order_respecting_actions = {
                str(action) for action in replay_cache.get("order_respecting_actions") or set()
            }
        user_goal = str(task_spec.get("user_goal") or "")
        step2 = step2_by_uid.get(task_uid)
        step4 = step4_by_uid.get(task_uid)
        history_graphs: list[dict[str, Any]] = []
        history_hits: list[dict[str, Any]] = []
        if step2 and step4:
            sequence = [item for item in (step4.get("temporal_sequence") or []) if isinstance(item, dict)]
            patched_task = copy.deepcopy(task_spec.get("patched_sopbench_task") or {})
            domain = str(task_spec.get("domain") or "")
            try:
                anchor_graph = anchor_directed_action_graph(step2)
                history_graphs = collect_history_graphs(step2, sequence)
                successful_actions = {
                    str(action) for action in (replay_cache or {}).get("successful_actions", set())
                }
                history_hits = [
                    entry
                    for entry in history_graphs
                    if strict_history_graph_hit(
                        domain=domain,
                        patched_task=patched_task,
                        anchor_graph=anchor_graph,
                        history_graph=entry["graph"],
                        user_goal=user_goal,
                        trace=trace,
                        successful_actions=successful_actions,
                    )
                ]
            except Exception:
                history_graphs = []
                history_hits = []
        anchor_matched = bool(task_eval.get("dirgraph_satisfied") and task_eval.get("action_called_correctly"))
        history_matched = bool(history_hits)
        contract_follow_details.append(
            {
                "task_uid": task_uid,
                "domain": task_spec.get("domain"),
                "follow_outcome": follow_outcome(anchor_matched, history_matched),
                "anchor_matched": anchor_matched,
                "history_matched": history_matched,
                "history_hit_count": len(history_hits),
                "history_graph_count": len(history_graphs),
                "active_constraint_count": 1,
                "history_constraint_count": len(history_graphs),
                "history_hit_graph_keys": [str(entry.get("graph_key")) for entry in history_hits],
            }
        )
        tool_behavior_by_task[task_uid] = {
            "anchor_supported_successful_actions": sorted(order_respecting_actions & anchor_tool_ids),
            "history_only_successful_actions": sorted(order_respecting_actions & history_tool_ids),
            "off_policy_successful_actions": sorted(
                order_respecting_actions - anchor_tool_ids - history_tool_ids - {user_goal}
            ),
            "successful_action_count": len(order_respecting_actions),
            "anchor_tool_unit_count": len(anchor_tool_ids),
            "history_tool_unit_count": len(history_tool_ids),
        }
        for unit in task_units:
            result = evaluate_sopbench_unit(
                unit=unit,
                task_spec=task_spec,
                trace=trace,
                replay=replay_cache,
            )
            expected = bool(unit.get("expected_should_apply"))
            observed = result.get("observed_followed")
            outcome = outcome_bucket(expected, observed if observed in {True, False, None} else None)
            details.append(
                {
                    "task_uid": task_uid,
                    "domain": task_spec.get("domain"),
                    "unit_id": unit.get("unit_id"),
                    "unit_source": unit.get("unit_source"),
                    "is_anchor": unit.get("is_anchor"),
                    "constraint_id": unit.get("constraint_id"),
                    "normalized_constraint_id": unit.get("normalized_constraint_id"),
                    "text": unit.get("text"),
                    "evaluator_type": unit.get("evaluator_type"),
                    "expected_should_apply": expected,
                    "observed_followed": observed,
                    "confidence": result.get("confidence"),
                    "reason": result.get("reason"),
                    "outcome": outcome,
                    "evidence_refs": result.get("evidence_refs", []),
                }
            )

    tool_call_details = [row for row in details if row.get("unit_source") == "graph_action"]
    all_unit_contract = contract_metrics(details)
    tool_behavior_summary = {
        "unit_breakdown": tool_unit_breakdown(tool_call_details),
        "successful_action_breakdown": {
            "anchor_supported_successful_actions": sum(
                len(row["anchor_supported_successful_actions"]) for row in tool_behavior_by_task.values()
            ),
            "history_only_successful_actions": sum(
                len(row["history_only_successful_actions"]) for row in tool_behavior_by_task.values()
            ),
            "off_policy_successful_actions": sum(
                len(row["off_policy_successful_actions"]) for row in tool_behavior_by_task.values()
            ),
            "successful_actions_total": sum(row["successful_action_count"] for row in tool_behavior_by_task.values()),
        },
        "task_breakdown": {
            "tasks_with_anchor_supported_action": sum(
                1 for row in tool_behavior_by_task.values() if row["anchor_supported_successful_actions"]
            ),
            "tasks_with_history_only_action": sum(
                1 for row in tool_behavior_by_task.values() if row["history_only_successful_actions"]
            ),
            "tasks_with_off_policy_action": sum(
                1 for row in tool_behavior_by_task.values() if row["off_policy_successful_actions"]
            ),
            "tasks_with_no_successful_actions": sum(
                1 for row in tool_behavior_by_task.values() if row["successful_action_count"] == 0
            ),
        },
    }
    successful_total = tool_behavior_summary["successful_action_breakdown"]["successful_actions_total"]
    successful_action_breakdown = tool_behavior_summary["successful_action_breakdown"]
    successful_action_breakdown["rates"] = {
        "anchor_supported_successful_action_rate": (
            successful_action_breakdown["anchor_supported_successful_actions"] / successful_total
            if successful_total
            else None
        ),
        "history_only_successful_action_rate": (
            successful_action_breakdown["history_only_successful_actions"] / successful_total
            if successful_total
            else None
        ),
        "off_policy_successful_action_rate": (
            successful_action_breakdown["off_policy_successful_actions"] / successful_total
            if successful_total
            else None
        ),
    }
    task_total = len(tool_behavior_by_task)
    task_breakdown = tool_behavior_summary["task_breakdown"]
    task_breakdown["task_count"] = task_total
    task_breakdown["rates"] = {
        "tasks_with_anchor_supported_action_rate": (
            task_breakdown["tasks_with_anchor_supported_action"] / task_total if task_total else None
        ),
        "tasks_with_history_only_action_rate": (
            task_breakdown["tasks_with_history_only_action"] / task_total if task_total else None
        ),
        "tasks_with_off_policy_action_rate": (
            task_breakdown["tasks_with_off_policy_action"] / task_total if task_total else None
        ),
        "tasks_with_no_successful_actions_rate": (
            task_breakdown["tasks_with_no_successful_actions"] / task_total if task_total else None
        ),
    }

    apply_branch_aware_process_scores(
        task_scores,
        task_specs=task_specs,
        replay_by_task=replay_by_task,
        task_evals=task_evals,
    )
    main_scores = with_task_scores(task_scores)
    payload = build_grade_document(
        scores=format_main_scores(main_scores),
        schema_version="MACSOPNoiseEvalGradeV5",
        generated_at=datetime.now(timezone.utc).isoformat(),
        source_answers=str(args.answers_file) if args.answers_file else None,
        source_manifest=str(args.manifest),
        bench=args.bench,
        memory_system=infer_memory_system(args, header),
        dry_run_empty=args.dry_run_empty,
        contract_metric_scope="branch_aware_active_process",
        contract_metric_scope_note=(
            "SOP main process metrics use branch-aware active user-goal directed "
            "action graph scoring from order_respecting_actions. Flat graph_action "
            "units remain in tool_behavior_breakdown for diagnostics and "
            "noise_follow_rate."
        ),
        run_header={
            "run_id": header.get("run_id"),
            "bench": header.get("bench"),
            "memory_system": header.get("memory_system"),
        },
        graded_unit_count=len(details),
        graded_tool_call_unit_count=len(tool_call_details),
        missing_task_unit_count=missing_tasks,
        diagnostic_scores={
            "all_units": format_main_scores(
                with_flat_unit_diagnostic_scores(all_unit_contract, task_scores)
            ),
        },
        constraint_follow_analysis=build_contract_diagnostics(contract_follow_details),
        contract_diagnostics=build_contract_diagnostics(contract_follow_details),
        task_scores=task_scores,
        tool_behavior_breakdown=tool_behavior_summary,
        score_groups=grouped_main_scores(tool_call_details, "domain", task_scores),
        score_groups_all_units=grouped_main_scores(details, "domain", task_scores),
        score_groups_by_unit_source=grouped_main_scores(details, "unit_source", task_scores),
        tool_behavior_by_task=tool_behavior_by_task if args.detail else {},
        details=details if args.detail else [],
        contract_follow_details=contract_follow_details if args.detail else [],
    )
    target = output_path(args, header=header, memory_system=infer_memory_system(args, header))
    write_json(target, payload)
    print(json.dumps(payload["scores"], indent=2, ensure_ascii=False))
    print(f"Wrote {resolve_path(target)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
