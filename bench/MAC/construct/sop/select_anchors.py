#!/usr/bin/env python3
"""Select per-task SOP anchor_seeds for MAC construct step 2.

Reads ``bench/MAC/sopbench/mid_data/eval_step1_sop.json`` and writes
``bench/MAC/sopbench/mid_data/eval_step2_anchors.json``.

For each task:
- **core anchor_seeds** = task-level ``•`` (``eval_scope=user_goal``)
  plus ``•`` on actions in ``directed_action_graph``
- sample ``K`` additional anchor_seeds from the remaining domain-default pool,
  where ``K`` is drawn from a truncated normal on ``[k_min, k_max]`` (default 5–12)

The output keeps the historical JSON field name ``anchors`` for compatibility,
but conceptually those records are construction seeds. MAC constraints are
counted later by unique action/tool roots, not by raw seed count.
"""

from __future__ import annotations

import argparse
import copy
import json
import random
import statistics
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_STEP1 = Path("bench/MAC/sopbench/mid_data/eval_step1_sop.json")
DEFAULT_STEP2 = Path("bench/MAC/sopbench/mid_data/eval_step2_anchors.json")

DEFAULT_K_MIN = 5
DEFAULT_K_MAX = 12
DEFAULT_K_MEAN = 8.5
DEFAULT_K_STD = 1.5

WEIGHT_PATH_CHECK = 3.0
WEIGHT_PATH = 2.0
WEIGHT_DISTRACTOR = 1.0


def resolve_path(path: Path) -> Path:
    return path if path.is_absolute() else REPO_ROOT / path


def load_json(path: Path) -> Any:
    return json.loads(resolve_path(path).read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    target = resolve_path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, indent=4, ensure_ascii=False) + "\n", encoding="utf-8")


def load_step1_tasks(path: Path) -> list[dict[str, Any]]:
    payload = load_json(path)
    if isinstance(payload, list):
        return copy.deepcopy(payload)
    if isinstance(payload, dict) and isinstance(payload.get("tasks"), list):
        return copy.deepcopy(payload["tasks"])
    raise ValueError(f"Expected step-1 task list in {path}")


def sample_truncated_normal_k(
    rng: random.Random,
    *,
    k_min: int,
    k_max: int,
    mean: float,
    std: float,
) -> int:
    if k_min > k_max:
        raise ValueError(f"k_min ({k_min}) must be <= k_max ({k_max})")
    if k_min == k_max:
        return k_min
    for _ in range(256):
        value = int(round(rng.gauss(mean, std)))
        if k_min <= value <= k_max:
            return value
    fallback = int(round(mean))
    return max(k_min, min(k_max, fallback))


def node_action_name(node: Any) -> str | None:
    if isinstance(node, list) and node:
        return str(node[0])
    return None


def collect_user_goal_path_actions(task: dict[str, Any]) -> set[str]:
    dag = (task.get("original_sopbench") or {}).get("directed_action_graph") or {}
    nodes = dag.get("nodes") or []
    connections = dag.get("connections") or []
    if not nodes:
        return set()

    user_goal = str(task.get("user_goal") or "")
    root_indices = [
        index
        for index, node in enumerate(nodes)
        if isinstance(node, list) and str(node[0]) == user_goal
    ]
    if not root_indices:
        root_indices = [0]

    dependents: dict[int, set[int]] = {index: set() for index in range(len(nodes))}
    for connection in connections:
        if not isinstance(connection, (list, tuple)) or len(connection) < 2:
            continue
        source, destination = int(connection[0]), int(connection[1])
        dependents.setdefault(source, set()).add(destination)

    visited: set[int] = set()
    stack = list(root_indices)
    path_actions: set[str] = set()
    while stack:
        index = stack.pop()
        if index in visited:
            continue
        visited.add(index)
        action = node_action_name(nodes[index])
        if action:
            path_actions.add(action)
        stack.extend(dependents.get(index, ()))
    return path_actions


def constraint_uid(constraint: dict[str, Any]) -> str:
    uid = constraint.get("mac_constraint_uid")
    if uid:
        return str(uid)
    metadata = constraint.get("metadata") or {}
    return f"{constraint.get('id')}:{constraint.get('action')}:{metadata.get('constraint_id')}"


def constraint_signature(constraint: dict[str, Any]) -> tuple[str, str, bool]:
    metadata = constraint.get("metadata") or {}
    return (
        str(constraint.get("action") or ""),
        str(metadata.get("constraint_id") or ""),
        bool(metadata.get("negated", False)),
    )


def is_path_check_action(action: str) -> bool:
    return action == "login_user" or action.startswith("internal_check_")


def is_path_check_constraint(constraint: dict[str, Any]) -> bool:
    action = str(constraint.get("action") or "")
    constraint_id = str((constraint.get("metadata") or {}).get("constraint_id") or "")
    if is_path_check_action(action):
        return True
    if constraint_id.startswith("internal_check"):
        return True
    if constraint_id == "logged_in_user" or "login" in constraint_id:
        return True
    return False


def selection_tier(constraint: dict[str, Any], path_actions: set[str]) -> str:
    action = str(constraint.get("action") or "")
    if is_path_check_constraint(constraint):
        return "path_check"
    if action in path_actions:
        return "path"
    return "distractor"


def selection_weight(tier: str) -> float:
    if tier == "path_check":
        return WEIGHT_PATH_CHECK
    if tier == "path":
        return WEIGHT_PATH
    return WEIGHT_DISTRACTOR


def weighted_sample_without_replacement(
    rng: random.Random,
    items: list[dict[str, Any]],
    *,
    k: int,
) -> list[dict[str, Any]]:
    if k <= 0 or not items:
        return []
    if k >= len(items):
        return list(items)

    pool = list(items)
    selected: list[dict[str, Any]] = []
    for _ in range(k):
        weights = [float(entry["_selection_weight"]) for entry in pool]
        total = sum(weights)
        pick = rng.random() * total
        cumulative = 0.0
        chosen_index = len(pool) - 1
        for index, weight in enumerate(weights):
            cumulative += weight
            if pick <= cumulative:
                chosen_index = index
                break
        selected.append(pool.pop(chosen_index))
    return selected


def build_core_identity(
    task_anchors: list[dict[str, Any]],
    dag_path_anchors: list[dict[str, Any]],
) -> tuple[set[str], set[tuple[str, str, bool]]]:
    core_uids: set[str] = set()
    core_signatures: set[tuple[str, str, bool]] = set()
    for constraint in task_anchors + dag_path_anchors:
        core_uids.add(constraint_uid(constraint))
        core_signatures.add(constraint_signature(constraint))
    return core_uids, core_signatures


def is_core_constraint(
    constraint: dict[str, Any],
    *,
    core_uids: set[str],
    core_signatures: set[tuple[str, str, bool]],
    path_actions: set[str],
) -> bool:
    metadata = constraint.get("metadata") or {}
    action = str(constraint.get("action") or "")
    if metadata.get("eval_scope") == "user_goal":
        return True
    if action in path_actions:
        return True
    if constraint_uid(constraint) in core_uids:
        return True
    if constraint_signature(constraint) in core_signatures:
        return True
    return False


def partition_constraints(
    task: dict[str, Any],
    path_actions: set[str],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], set[str]]:
    task_anchors: list[dict[str, Any]] = []
    dag_path_anchors: list[dict[str, Any]] = []
    random_pool: list[dict[str, Any]] = []
    seen_task_uids: set[str] = set()
    seen_dag_uids: set[str] = set()

    for constraint in task.get("constraints") or []:
        if not isinstance(constraint, dict):
            continue
        entry = copy.deepcopy(constraint)
        uid = constraint_uid(entry)
        metadata = entry.get("metadata") or {}
        action = str(entry.get("action") or "")
        is_task = metadata.get("eval_scope") == "user_goal"
        is_on_dag = action in path_actions

        if is_task:
            if uid not in seen_task_uids:
                seen_task_uids.add(uid)
                task_anchors.append(entry)
        elif is_on_dag:
            if uid not in seen_dag_uids:
                seen_dag_uids.add(uid)
                dag_path_anchors.append(entry)

    core_uids, core_signatures = build_core_identity(task_anchors, dag_path_anchors)
    seen_random_uids: set[str] = set()
    for constraint in task.get("constraints") or []:
        if not isinstance(constraint, dict):
            continue
        entry = copy.deepcopy(constraint)
        uid = constraint_uid(entry)
        if is_core_constraint(
            entry,
            core_uids=core_uids,
            core_signatures=core_signatures,
            path_actions=path_actions,
        ):
            continue
        if uid in seen_random_uids:
            continue
        seen_random_uids.add(uid)
        random_pool.append(entry)

    return task_anchors, dag_path_anchors, random_pool, core_uids


def annotate_random_candidates(
    candidates: list[dict[str, Any]],
    path_actions: set[str],
) -> list[dict[str, Any]]:
    annotated: list[dict[str, Any]] = []
    for constraint in candidates:
        tier = selection_tier(constraint, path_actions)
        entry = copy.deepcopy(constraint)
        entry["_selection_tier"] = tier
        entry["_selection_weight"] = selection_weight(tier)
        annotated.append(entry)
    return annotated


def build_anchor_record(
    constraint: dict[str, Any],
    *,
    anchor_kind: str,
    anchor_order: int,
    selection_tier_name: str | None,
) -> dict[str, Any]:
    record = copy.deepcopy(constraint)
    record.pop("_selection_tier", None)
    record.pop("_selection_weight", None)
    record["anchor_kind"] = anchor_kind
    record["anchor_order"] = anchor_order
    if selection_tier_name is not None:
        record["selection_tier"] = selection_tier_name
    return record


def select_task_anchors(
    task: dict[str, Any],
    rng: random.Random,
    *,
    k_min: int,
    k_max: int,
    k_mean: float,
    k_std: float,
) -> dict[str, Any]:
    path_actions = collect_user_goal_path_actions(task)
    path_actions_sorted = sorted(path_actions)
    task_anchors, dag_path_anchors, random_pool, core_uids = partition_constraints(task, path_actions)
    core_signatures = {constraint_signature(c) for c in task_anchors + dag_path_anchors}

    k_target = sample_truncated_normal_k(
        rng,
        k_min=k_min,
        k_max=k_max,
        mean=k_mean,
        std=k_std,
    )
    k_effective = min(k_target, len(random_pool))
    annotated_candidates = annotate_random_candidates(random_pool, path_actions)
    sampled_random = weighted_sample_without_replacement(rng, annotated_candidates, k=k_effective)

    anchors: list[dict[str, Any]] = []
    for constraint in task_anchors:
        anchors.append(
            build_anchor_record(
                constraint,
                anchor_kind="task",
                anchor_order=len(anchors),
                selection_tier_name="task",
            )
        )
    for constraint in dag_path_anchors:
        anchors.append(
            build_anchor_record(
                constraint,
                anchor_kind="dag_path",
                anchor_order=len(anchors),
                selection_tier_name="dag_path",
            )
        )

    sampled_tier_counts = {"path_check": 0, "path": 0, "distractor": 0}
    sampled_uids: set[str] = set()
    for constraint in sampled_random:
        uid = constraint_uid(constraint)
        if uid in core_uids or uid in sampled_uids:
            raise ValueError(
                f"sampled anchor overlaps core or prior sample: {uid} task={task.get('mac_task_uid')}"
            )
        if constraint_signature(constraint) in core_signatures:
            raise ValueError(
                f"sampled anchor signature overlaps core: {constraint_signature(constraint)} "
                f"task={task.get('mac_task_uid')}"
            )
        sampled_uids.add(uid)
        tier = str(constraint.get("_selection_tier") or "distractor")
        sampled_tier_counts[tier] = sampled_tier_counts.get(tier, 0) + 1
        anchors.append(
            build_anchor_record(
                constraint,
                anchor_kind="sampled",
                anchor_order=len(anchors),
                selection_tier_name=tier,
            )
        )

    anchor_uids = [constraint_uid(a) for a in anchors]
    if len(anchor_uids) != len(set(anchor_uids)):
        raise ValueError(f"duplicate anchor uids in final list for task={task.get('mac_task_uid')}")

    core_count = len(task_anchors) + len(dag_path_anchors)
    step2_task = copy.deepcopy(task)
    step2_task["anchor_selection"] = {
        "k_target": k_target,
        "k_effective": k_effective,
        "k_bounds": [k_min, k_max],
        "k_distribution": {
            "type": "truncated_normal",
            "mean": k_mean,
            "std": k_std,
        },
        "task_anchor_count": len(task_anchors),
        "dag_path_anchor_count": len(dag_path_anchors),
        "core_anchor_count": core_count,
        "sampled_anchor_count": len(sampled_random),
        "total_anchor_count": len(anchors),
        "random_pool_count": len(random_pool),
        "core_uid_count": len(core_uids),
        "path_actions": path_actions_sorted,
        "sampled_tier_counts": sampled_tier_counts,
        "sampled_disjoint_from_core": True,
    }
    step2_task["anchors"] = anchors
    return step2_task


def summarize_step2_tasks(tasks: list[dict[str, Any]]) -> dict[str, Any]:
    def _sel(key: str) -> list[int]:
        return [int(task["anchor_selection"][key]) for task in tasks]

    def _mean(values: list[int | float]) -> float:
        return float(statistics.mean(values)) if values else 0.0

    k_targets = _sel("k_target")
    k_effective = _sel("k_effective")
    total_anchors = _sel("total_anchor_count")
    task_counts = _sel("task_anchor_count")
    dag_counts = _sel("dag_path_anchor_count")
    core_counts = _sel("core_anchor_count")
    sampled_counts = _sel("sampled_anchor_count")
    distractors = [
        int((task["anchor_selection"].get("sampled_tier_counts") or {}).get("distractor", 0))
        for task in tasks
    ]

    return {
        "task_count": len(tasks),
        "k_target_min": min(k_targets) if k_targets else 0,
        "k_target_max": max(k_targets) if k_targets else 0,
        "k_target_mean": _mean(k_targets),
        "k_effective_mean": _mean(k_effective),
        "total_anchor_count": sum(total_anchors),
        "avg_total_anchors_per_task": _mean(total_anchors),
        "avg_task_anchors_per_task": _mean(task_counts),
        "avg_dag_path_anchors_per_task": _mean(dag_counts),
        "avg_core_anchors_per_task": _mean(core_counts),
        "avg_sampled_anchors_per_task": _mean(sampled_counts),
        "avg_sampled_distractors_per_task": _mean(distractors),
        "k_target_histogram": {str(k): k_targets.count(k) for k in sorted(set(k_targets))},
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--step1-input", type=Path, default=DEFAULT_STEP1)
    parser.add_argument("--step2-output", type=Path, default=DEFAULT_STEP2)
    parser.add_argument("--seed", type=int, default=13, help="Global seed for reproducible sampling.")
    parser.add_argument("--k-min", type=int, default=DEFAULT_K_MIN)
    parser.add_argument("--k-max", type=int, default=DEFAULT_K_MAX)
    parser.add_argument("--k-mean", type=float, default=DEFAULT_K_MEAN)
    parser.add_argument("--k-std", type=float, default=DEFAULT_K_STD)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.k_min > args.k_max:
        raise SystemExit("--k-min must be <= --k-max")
    if args.k_std <= 0:
        raise SystemExit("--k-std must be > 0")

    step1_path = resolve_path(args.step1_input)
    step1_tasks = load_step1_tasks(step1_path)
    master_rng = random.Random(args.seed)

    step2_tasks: list[dict[str, Any]] = []
    for task in step1_tasks:
        task_seed = master_rng.randint(0, 2**31 - 1)
        task_rng = random.Random(task_seed)
        step2_task = select_task_anchors(
            task,
            task_rng,
            k_min=args.k_min,
            k_max=args.k_max,
            k_mean=args.k_mean,
            k_std=args.k_std,
        )
        step2_task["anchor_selection"]["seed"] = task_seed
        step2_tasks.append(step2_task)

    summary = summarize_step2_tasks(step2_tasks)
    step2_output_path = resolve_path(args.step2_output)
    step2_meta = {
        "schema_version": "MACConstructStep2AnchorsV2",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "tasks_output": str(step2_output_path.relative_to(REPO_ROOT))
        if step2_output_path.is_relative_to(REPO_ROOT)
        else str(step2_output_path),
        "source_step1": str(step1_path.relative_to(REPO_ROOT))
        if step1_path.is_relative_to(REPO_ROOT)
        else str(step1_path),
        "seed": args.seed,
        "k_bounds": [args.k_min, args.k_max],
        "k_distribution": {
            "type": "truncated_normal",
            "mean": args.k_mean,
            "std": args.k_std,
        },
        "anchor_policy": {
            "core": "task-level (eval_scope=user_goal) ∪ bullets on directed_action_graph actions",
            "sampled": "K additional bullets from remaining domain-default pool",
        },
        "terminology": {
            "anchors_field": "compatibility name for SOP anchor_seed records",
            "constraint_counting": "count unique root actions among selected seeds, not raw seed records",
        },
        "selection_weights": {
            "path_check": WEIGHT_PATH_CHECK,
            "path": WEIGHT_PATH,
            "distractor": WEIGHT_DISTRACTOR,
        },
        "summary": summary,
    }

    write_json(args.step2_output, step2_tasks)
    meta_path = resolve_path(args.step2_output).with_suffix(
        resolve_path(args.step2_output).suffix + ".meta.json"
    )
    write_json(meta_path, step2_meta)

    print(
        f"wrote {len(step2_tasks)} step-2 task(s) to {resolve_path(args.step2_output)}; "
        f"avg_anchors={summary['avg_total_anchors_per_task']:.2f} "
        f"(core={summary['avg_core_anchors_per_task']:.2f}, "
        f"sampled={summary['avg_sampled_anchors_per_task']:.2f}), "
        f"k_target_mean={summary['k_target_mean']:.2f}, "
        f"meta={meta_path}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
