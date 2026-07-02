"""Graph-level SOP grading probe with loose and strict directed-action-graph oracles.

Loose oracle (diagnostic):
  - Anchor TP when replay dirgraph_satisfied is True on the anchor graph.
  - History FP when replay dirgraph_satisfied is True on a history graph.

Strict oracle (recommended alternate):
  - Anchor TP when dirgraph_satisfied AND action_called_correctly on the anchor task.
  - History FP when an obsolete-only precall action was successfully called AND replay
    dirgraph_satisfied is True on that history graph.
  - Traces with no tool calls are anchor FN / history TN.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from bench.construct.sop.noise_eval_grade import read_memory_output, trace_from_row
from bench.MAC.construct.sop.noise_eval import (
    _replay_trajectory,
    anchor_directed_action_graph,
    contract_metrics,
    cumulative_user_goal_graph,
    evaluate_task,
    func_calls_from_trace,
    graph_action_nodes,
    load_json,
    task_responded,
    write_json,
)

DEFAULT_STEP2 = REPO_ROOT / "bench/MAC/sopbench/mid_data/eval_step2_anchors.json"
DEFAULT_STEP3 = REPO_ROOT / "bench/MAC/sopbench/mid_data/eval_step3_temporal_noise.json"
DEFAULT_STEP4 = REPO_ROOT / "bench/MAC/sopbench/mid_data/eval_step4_temporal_sequence_v3.json"
DEFAULT_MANIFEST = REPO_ROOT / "bench/MAC/sopbench/data/mac-sopbench-noise_eval_specs.json"

OracleMode = Literal["loose", "strict"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("answers_file", type=Path, help="memory_eval output JSON")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--step2", type=Path, default=DEFAULT_STEP2)
    parser.add_argument("--step3", type=Path, default=DEFAULT_STEP3)
    parser.add_argument("--step4", type=Path, default=DEFAULT_STEP4)
    parser.add_argument(
        "--output",
        type=Path,
        help="Optional JSON output path. Always prints both loose and strict summaries.",
    )
    parser.add_argument(
        "--oracle",
        choices=["both", "loose", "strict"],
        default="both",
        help="Which oracle summary to print (both are always computed when output is set).",
    )
    return parser.parse_args()


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
        return bool(replay["evaluation"].get("dirgraph_satisfied"))
    except Exception:
        return False


def strict_anchor_tp(*, task_spec: dict[str, Any], trace: dict[str, Any]) -> bool:
    task_eval = evaluate_task(task_spec=task_spec, trace=trace)
    return bool(task_eval.get("dirgraph_satisfied") and task_eval.get("action_called_correctly"))


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
) -> bool:
    func_calls = func_calls_from_trace(trace)
    if not func_calls:
        return False
    obsolete_only = obsolete_only_nodes(
        anchor_graph=anchor_graph,
        history_graph=history_graph,
        user_goal=user_goal,
    )
    if not obsolete_only:
        return False
    try:
        anchor_replay = _replay_trajectory(domain, patched_task, func_calls)
    except Exception:
        return False
    if not obsolete_only & anchor_replay["successful_actions"]:
        return False
    return dirgraph_satisfied_for_graph(
        domain=domain,
        patched_task=patched_task,
        graph=history_graph,
        trace=trace,
    )


def evaluate_oracle(
    *,
    mode: OracleMode,
    task_uid: str,
    task_spec: dict[str, Any],
    step2: dict[str, Any],
    sequence: list[dict[str, Any]],
    trace: dict[str, Any],
) -> dict[str, Any]:
    patched_task = copy.deepcopy(task_spec.get("patched_sopbench_task") or {})
    domain = str(task_spec.get("domain") or "")
    user_goal = str(task_spec.get("user_goal") or "")
    anchor_graph = anchor_directed_action_graph(step2)
    history_graphs = collect_history_graphs(step2, sequence)

    if mode == "loose":
        anchor_hit = dirgraph_satisfied_for_graph(
            domain=domain,
            patched_task=patched_task,
            graph=anchor_graph,
            trace=trace,
        )
        history_hits = [
            entry
            for entry in history_graphs
            if dirgraph_satisfied_for_graph(
                domain=domain,
                patched_task=patched_task,
                graph=entry["graph"],
                trace=trace,
            )
        ]
    else:
        anchor_hit = strict_anchor_tp(task_spec=task_spec, trace=trace)
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
            )
        ]

    details: list[dict[str, Any]] = [
        {
            "task_uid": task_uid,
            "graph_role": "anchor",
            "expected_should_apply": True,
            "outcome": "anchor_followed" if anchor_hit else "anchor_missed",
        }
    ]
    for entry in history_graphs:
        hit = entry in history_hits
        details.append(
            {
                "task_uid": task_uid,
                "graph_role": "history",
                "graph_key": entry["graph_key"],
                "sequence_order": entry["sequence_order"],
                "expected_should_apply": False,
                "outcome": "noise_followed" if hit else "noise_ignored",
            }
        )

    has_tool_calls = bool(func_calls_from_trace(trace))
    if not has_tool_calls:
        trace_bucket = "no_tool_calls"
    elif anchor_hit and history_hits:
        trace_bucket = "anchor_tp_and_history_fp"
    elif anchor_hit:
        trace_bucket = "anchor_tp_only"
    elif history_hits:
        trace_bucket = "history_fp_only"
    else:
        trace_bucket = "neither"

    task_eval = evaluate_task(task_spec=task_spec, trace=trace)
    return {
        "task_uid": task_uid,
        "details": details,
        "trace_bucket": trace_bucket,
        "has_tool_calls": has_tool_calls,
        "anchor_hit": anchor_hit,
        "history_hit_count": len(history_hits),
        "history_graph_count": len(history_graphs),
        "ACC": bool(task_eval.get("success")),
        "RSP": task_responded(trace),
    }


def summarize_oracle(*, mode: OracleMode, per_task: list[dict[str, Any]], details: list[dict[str, Any]]) -> dict[str, Any]:
    graph_scores = contract_metrics(details)
    task_acc = sum(1 for row in per_task if row["ACC"]) / len(per_task) if per_task else None
    task_rsp = sum(1 for row in per_task if row["RSP"]) / len(per_task) if per_task else None
    trace_buckets = Counter(row["trace_bucket"] for row in per_task)
    return {
        "oracle": mode,
        "description": (
            "anchor dirgraph satisfied=TP; history dirgraph satisfied=FP"
            if mode == "loose"
            else (
                "anchor dirgraph satisfied AND action_called_correctly=TP; "
                "obsolete-only precall successfully called AND history dirgraph satisfied=FP"
            )
        ),
        "task_count": len(per_task),
        "anchor_graph_units": len(per_task),
        "history_graph_units": sum(1 for row in details if row.get("graph_role") == "history"),
        "avg_history_graphs_per_task": (
            sum(row["history_graph_count"] for row in per_task) / len(per_task) if per_task else None
        ),
        "scores": {
            "ACC": task_acc,
            "RSP": task_rsp,
            "correct_follow_rate": graph_scores["correct_follow_rate"],
            "wrong_follow_rate": graph_scores["wrong_follow_rate"],
            "support": {
                "constraint_count": graph_scores["constraint_count"],
                "active_constraint_count": graph_scores["active_constraint_count"],
                "history_constraint_count": graph_scores["history_constraint_count"],
                "correctly_followed": graph_scores["correctly_followed"],
                "wrongly_followed": graph_scores["wrongly_followed"],
            },
        },
        "trace_buckets": dict(sorted(trace_buckets.items())),
        "trace_outcomes": {
            "anchor_hit": sum(1 for row in per_task if row["anchor_hit"]),
            "any_history_hit": sum(1 for row in per_task if row["history_hit_count"] > 0),
            "neither_hit": sum(
                1 for row in per_task if not row["anchor_hit"] and row["history_hit_count"] == 0
            ),
            "both_hit": sum(
                1 for row in per_task if row["anchor_hit"] and row["history_hit_count"] > 0
            ),
            "no_tool_calls": sum(1 for row in per_task if not row["has_tool_calls"]),
        },
    }


def grade_graph_oracles(
    *,
    answers_file: Path,
    manifest_path: Path,
    step2_path: Path,
    step3_path: Path,
    step4_path: Path,
) -> dict[str, Any]:
    step2_by_uid = index_by_uid(load_json(step2_path))
    step3_by_uid = index_by_uid(load_json(step3_path))
    step4_payload = load_json(step4_path)
    step4_tasks = step4_payload.get("tasks") if isinstance(step4_payload, dict) else step4_payload
    step4_by_uid = index_by_uid(step4_tasks)
    manifest = load_json(manifest_path)
    task_specs = manifest.get("task_specs") or {}

    header, records = read_memory_output(answers_file)
    rows_by_task = {
        str(row.get("task_uid")): row
        for row in records
        if row.get("record_type") == "task_result" and row.get("task_uid")
    }

    loose_details: list[dict[str, Any]] = []
    strict_details: list[dict[str, Any]] = []
    loose_tasks: list[dict[str, Any]] = []
    strict_tasks: list[dict[str, Any]] = []

    for task_uid, task_spec in sorted(task_specs.items()):
        step2 = step2_by_uid.get(task_uid)
        step3 = step3_by_uid.get(task_uid)
        step4 = step4_by_uid.get(task_uid)
        row = rows_by_task.get(task_uid)
        if not step2 or not step3 or not step4 or not row:
            continue
        sequence = [item for item in (step4.get("temporal_sequence") or []) if isinstance(item, dict)]
        trace = trace_from_row(row)

        loose = evaluate_oracle(
            mode="loose",
            task_uid=task_uid,
            task_spec=task_spec,
            step2=step2,
            sequence=sequence,
            trace=trace,
        )
        strict = evaluate_oracle(
            mode="strict",
            task_uid=task_uid,
            task_spec=task_spec,
            step2=step2,
            sequence=sequence,
            trace=trace,
        )
        loose_details.extend(loose["details"])
        strict_details.extend(strict["details"])
        loose_tasks.append(loose)
        strict_tasks.append(strict)

    return {
        "schema_version": "MACSOPGraphLevelGradeV1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_answers": str(answers_file),
        "source_manifest": str(manifest_path),
        "run_header": {
            "run_id": header.get("run_id"),
            "bench": header.get("bench"),
            "memory_system": header.get("memory_system"),
        },
        "oracles": {
            "loose": summarize_oracle(mode="loose", per_task=loose_tasks, details=loose_details),
            "strict": summarize_oracle(mode="strict", per_task=strict_tasks, details=strict_details),
        },
    }


def main() -> int:
    args = parse_args()
    payload = grade_graph_oracles(
        answers_file=args.answers_file,
        manifest_path=args.manifest,
        step2_path=args.step2,
        step3_path=args.step3,
        step4_path=args.step4,
    )

    to_print: dict[str, Any]
    if args.oracle == "both":
        to_print = payload
    else:
        to_print = payload["oracles"][args.oracle]

    print(json.dumps(to_print, indent=2, ensure_ascii=False))
    if args.output:
        write_json(args.output, payload)
        print(f"Wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
