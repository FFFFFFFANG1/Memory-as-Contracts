#!/usr/bin/env python3
"""Assign stable MAC unique IDs to AgentIF tasks and constraints.

Task IDs (`mac_task_uid`) are assigned from the source dataset order.
Constraint IDs (`mac_constraint_uid`) use the constraint's array index within
its source task so the same rule keeps the same ID across pipeline stages.

Run on the pre-filter source first, then on derived datasets that subset it.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=4, ensure_ascii=False) + "\n", encoding="utf-8")


def task_fingerprint(task: dict[str, Any]) -> tuple[Any, ...]:
    return (
        task.get("id"),
        task.get("agent_name"),
        json.dumps(task.get("input", []), sort_keys=True, ensure_ascii=False),
    )


def constraint_fingerprint(constraint: dict[str, Any]) -> tuple[Any, ...]:
    return (constraint.get("id"), constraint.get("desc"))


def assign_uids_to_tasks(tasks: list[dict[str, Any]], *, start: int = 1) -> dict[tuple[Any, ...], str]:
    fingerprint_to_uid: dict[tuple[Any, ...], str] = {}
    for offset, task in enumerate(tasks):
        task_uid = f"mac-t-{start + offset:05d}"
        task["mac_task_uid"] = task_uid
        fingerprint_to_uid[task_fingerprint(task)] = task_uid

        constraints = task.get("constraints", [])
        if not isinstance(constraints, list):
            continue
        for index, constraint in enumerate(constraints):
            if not isinstance(constraint, dict):
                continue
            constraint["mac_constraint_uid"] = f"{task_uid}-c{index:04d}"

    return fingerprint_to_uid


def build_constraint_uid_map(tasks: list[dict[str, Any]]) -> dict[tuple[Any, ...], str]:
    mapping: dict[tuple[Any, ...], str] = {}
    for task in tasks:
        task_uid = task.get("mac_task_uid")
        if not task_uid:
            continue
        for index, constraint in enumerate(task.get("constraints", [])):
            if not isinstance(constraint, dict):
                continue
            key = (task_uid, constraint_fingerprint(constraint))
            mapping[key] = constraint.get("mac_constraint_uid", f"{task_uid}-c{index:04d}")
    return mapping


def propagate_uids(
    tasks: list[dict[str, Any]],
    *,
    task_uid_by_fingerprint: dict[tuple[Any, ...], str],
    source_tasks: list[dict[str, Any]],
) -> tuple[int, int]:
    constraint_uid_map = build_constraint_uid_map(source_tasks)
    missing_tasks = 0
    missing_constraints = 0

    for task in tasks:
        fingerprint = task_fingerprint(task)
        task_uid = task_uid_by_fingerprint.get(fingerprint)
        if task_uid is None:
            missing_tasks += 1
            continue
        task["mac_task_uid"] = task_uid

        constraints = task.get("constraints", [])
        if not isinstance(constraints, list):
            continue
        for index, constraint in enumerate(constraints):
            if not isinstance(constraint, dict):
                continue
            key = (task_uid, constraint_fingerprint(constraint))
            constraint_uid = constraint_uid_map.get(key)
            if constraint_uid is None:
                missing_constraints += 1
                constraint_uid = f"{task_uid}-c{index:04d}"
            constraint["mac_constraint_uid"] = constraint_uid

    return missing_tasks, missing_constraints


def validate_unique_ids(tasks: list[dict[str, Any]], *, label: str) -> None:
    task_uids = [task.get("mac_task_uid") for task in tasks if isinstance(task, dict)]
    constraint_uids: list[str] = []
    for task in tasks:
        if not isinstance(task, dict):
            continue
        for constraint in task.get("constraints", []):
            if isinstance(constraint, dict) and constraint.get("mac_constraint_uid"):
                constraint_uids.append(constraint["mac_constraint_uid"])

    if len(task_uids) != len(set(task_uids)):
        raise ValueError(f"{label}: duplicate mac_task_uid values found")
    if len(constraint_uids) != len(set(constraint_uids)):
        raise ValueError(f"{label}: duplicate mac_constraint_uid values found")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source",
        type=Path,
        default=Path("bench/MAC/mid_data/eval_nonzh_single_turn_tmp.json"),
        help="Source dataset that defines canonical task/constraint IDs.",
    )
    parser.add_argument(
        "--derived",
        type=Path,
        nargs="*",
        default=[Path("bench/MAC/mid_data/eval_step1_tmp.json")],
        help="Derived datasets that inherit IDs from the source.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = Path(__file__).resolve().parents[3]
    source_path = args.source if args.source.is_absolute() else repo_root / args.source
    derived_paths = [path if path.is_absolute() else repo_root / path for path in args.derived]

    source_tasks = load_json(source_path)
    if not isinstance(source_tasks, list):
        raise ValueError(f"Expected top-level JSON array in {source_path}")

    task_uid_by_fingerprint = assign_uids_to_tasks(source_tasks)
    validate_unique_ids(source_tasks, label=str(source_path))
    write_json(source_path, source_tasks)
    print(
        f"assigned IDs in {source_path}: "
        f"{len(source_tasks)} tasks, "
        f"{sum(len(t.get('constraints', [])) for t in source_tasks)} constraints"
    )

    for derived_path in derived_paths:
        derived_tasks = load_json(derived_path)
        if not isinstance(derived_tasks, list):
            raise ValueError(f"Expected top-level JSON array in {derived_path}")

        missing_tasks, missing_constraints = propagate_uids(
            derived_tasks,
            task_uid_by_fingerprint=task_uid_by_fingerprint,
            source_tasks=source_tasks,
        )
        validate_unique_ids(derived_tasks, label=str(derived_path))
        write_json(derived_path, derived_tasks)
        print(
            f"propagated IDs in {derived_path}: "
            f"{len(derived_tasks)} tasks, "
            f"{sum(len(t.get('constraints', [])) for t in derived_tasks)} constraints, "
            f"missing_tasks={missing_tasks}, missing_constraints={missing_constraints}"
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
