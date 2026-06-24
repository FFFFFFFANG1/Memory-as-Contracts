#!/usr/bin/env python3
"""Build one constraint sequence per task from per-constraint histories.

For every task, prepare an independent constraint sequence ``cs`` that contains
all anchor constraints and noisy constraints from that task's histories.

Merge algorithm (per task, not shared across tasks):

    cs = []
    for cg in task_constraint_graphs:
        if not cs:
            cs = cg.copy()
        else:
            for c in cg:
                insert c at a random index in cs -> id_current
                next c may only be inserted in [id_current + 1, len(cs)]
                if id_current is already at the end of cs, append the rest of cg
"""

from __future__ import annotations

import argparse
import copy
import json
import random
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[4]


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=4, ensure_ascii=False) + "\n", encoding="utf-8")


def resolve_path(path: Path) -> Path:
    return path if path.is_absolute() else REPO_ROOT / path


def extract_histories(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if not isinstance(payload, dict):
        raise ValueError("Expected input JSON object or list")
    raw = payload.get("constraint_histories", payload.get("graphs", []))
    if not isinstance(raw, list):
        raise ValueError("Input must contain constraint_histories or graphs list")
    return [item for item in raw if isinstance(item, dict)]


def task_metadata(tasks: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    metadata: dict[str, dict[str, Any]] = {}
    for task in tasks:
        if not isinstance(task, dict):
            continue
        task_uid = task.get("mac_task_uid")
        if not task_uid:
            continue
        constraint_order = [
            str(constraint.get("mac_constraint_uid"))
            for constraint in task.get("constraints", [])
            if isinstance(constraint, dict) and constraint.get("mac_constraint_uid")
        ]
        metadata[str(task_uid)] = {
            "task_uid": str(task_uid),
            "agent_name": task.get("agent_name"),
            "task_level": task.get("task_level"),
            "mac_task_summary": task.get("mac_task_summary"),
            "constraint_order": constraint_order,
        }
    return metadata


def namespaced_items(history: dict[str, Any]) -> list[dict[str, Any]]:
    constraint_uid = str(history.get("constraint_uid", ""))
    items = history.get("generated_constraints", [])
    if not isinstance(items, list):
        return []

    local_to_merged: dict[str, str] = {}
    copied: list[dict[str, Any]] = []
    for index, raw in enumerate(items):
        if not isinstance(raw, dict):
            continue
        source_local_id = str(raw.get("local_id", f"g{index + 1}"))
        merged_local_id = f"{constraint_uid}-{source_local_id}"
        local_to_merged[source_local_id] = merged_local_id
        item = copy.deepcopy(raw)
        item["local_id"] = merged_local_id
        item["source_local_id"] = source_local_id
        item["source_constraint_uid"] = constraint_uid
        item["source_anchor_role"] = history.get("anchor_role")
        copied.append(item)

    for item in copied:
        except_by = item.get("except_by")
        if except_by in {None, ""}:
            item["except_by"] = None
            continue
        except_by_text = str(except_by)
        item["except_by"] = local_to_merged.get(except_by_text, except_by_text)

    return copied


def merge_constraint_sequence(
    constraint_graphs: list[list[dict[str, Any]]],
    *,
    rng: random.Random,
) -> list[dict[str, Any]]:
    cs: list[dict[str, Any]] = []
    for cg in constraint_graphs:
        if not cg:
            continue
        if not cs:
            cs = list(cg)
            continue

        insert_from = rng.randint(0, len(cs))
        for index, item in enumerate(cg):
            insert_at = rng.randint(insert_from, len(cs))
            cs.insert(insert_at, item)
            if insert_at == len(cs) - 1:
                cs.extend(cg[index + 1 :])
                break
            insert_from = insert_at + 1
    return cs


def duplicate_key(item: dict[str, Any]) -> str:
    text = str(item.get("text", ""))
    text = re.sub(r"\s+", " ", text).strip()
    return text


def dedupe_constraint_sequence(
    sequence: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    groups: dict[str, list[int]] = defaultdict(list)
    for index, item in enumerate(sequence):
        key = duplicate_key(item)
        if key:
            groups[key].append(index)

    removed_ids: set[str] = set()
    remap_ids: dict[str, str] = {}
    duplicate_groups = 0
    for indices in groups.values():
        if len(indices) <= 1:
            continue
        duplicate_groups += 1
        keep_index = next(
            (index for index in indices if sequence[index].get("is_anchor")),
            indices[0],
        )
        keep_id = str(sequence[keep_index].get("local_id"))
        for index in indices:
            if index == keep_index:
                continue
            old_id = str(sequence[index].get("local_id"))
            removed_ids.add(old_id)
            remap_ids[old_id] = keep_id

    deduped: list[dict[str, Any]] = []
    for item in sequence:
        local_id = str(item.get("local_id"))
        if local_id in removed_ids:
            continue
        copied = copy.deepcopy(item)
        except_by = copied.get("except_by")
        if except_by not in {None, ""}:
            copied["except_by"] = remap_ids.get(str(except_by), except_by)
        deduped.append(copied)

    stats = {
        "duplicate_groups": duplicate_groups,
        "removed_constraints": len(removed_ids),
    }
    return deduped, stats


def ordered_histories_for_task(
    histories: list[dict[str, Any]],
    *,
    constraint_order: list[str] | None,
) -> list[dict[str, Any]]:
    if not constraint_order:
        return sorted(histories, key=lambda item: str(item.get("constraint_uid", "")))

    order_index = {uid: index for index, uid in enumerate(constraint_order)}
    return sorted(
        histories,
        key=lambda item: order_index.get(str(item.get("constraint_uid", "")), 10**9),
    )


def build_task_sequences(
    histories: list[dict[str, Any]],
    *,
    task_meta: dict[str, dict[str, Any]],
    seed: int,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    by_task: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for history in histories:
        task_uid = str(history.get("task_uid", ""))
        if task_uid:
            by_task[task_uid].append(history)

    task_sequences: list[dict[str, Any]] = []
    sequence_lengths: list[int] = []
    source_graph_counts: list[int] = []
    raw_sequence_lengths: list[int] = []
    total_duplicate_groups = 0
    total_removed_constraints = 0
    tasks_with_dedup = 0

    for task_uid in sorted(task_meta):
        meta = task_meta[task_uid]
        task_histories = ordered_histories_for_task(
            by_task.get(task_uid, []),
            constraint_order=meta.get("constraint_order"),
        )
        rng = random.Random(f"{seed}:{task_uid}")
        namespaced_graphs = [namespaced_items(history) for history in task_histories]
        constraint_sequence = merge_constraint_sequence(namespaced_graphs, rng=rng)
        raw_sequence_lengths.append(len(constraint_sequence))
        constraint_sequence, dedupe_stats = dedupe_constraint_sequence(constraint_sequence)
        total_duplicate_groups += int(dedupe_stats["duplicate_groups"])
        total_removed_constraints += int(dedupe_stats["removed_constraints"])
        if dedupe_stats["removed_constraints"]:
            tasks_with_dedup += 1
        sequence_lengths.append(len(constraint_sequence))
        source_graph_counts.append(len(task_histories))

        task_sequences.append(
            {
                "task_uid": task_uid,
                "agent_name": meta.get("agent_name"),
                "task_level": meta.get("task_level"),
                "mac_task_summary": meta.get("mac_task_summary"),
                "source_constraint_uids": [
                    str(history.get("constraint_uid"))
                    for history in task_histories
                    if history.get("constraint_uid")
                ],
                "source_graph_count": len(task_histories),
                "constraint_sequence_count": len(constraint_sequence),
                "raw_constraint_sequence_count": raw_sequence_lengths[-1],
                "dedup_removed_constraint_count": dedupe_stats["removed_constraints"],
                "dedup_duplicate_group_count": dedupe_stats["duplicate_groups"],
                "constraint_sequence": constraint_sequence,
            }
        )

    summary = {
        "task_count": len(task_sequences),
        "total_constraints_in_sequences": sum(sequence_lengths),
        "total_constraints_before_dedup": sum(raw_sequence_lengths),
        "total_dedup_removed_constraints": total_removed_constraints,
        "total_dedup_duplicate_groups": total_duplicate_groups,
        "tasks_with_dedup": tasks_with_dedup,
        "avg_constraints_per_sequence": (
            sum(sequence_lengths) / len(task_sequences) if task_sequences else 0.0
        ),
        "avg_constraints_before_dedup": (
            sum(raw_sequence_lengths) / len(task_sequences) if task_sequences else 0.0
        ),
        "avg_source_graphs_per_task": (
            sum(source_graph_counts) / len(task_sequences) if task_sequences else 0.0
        ),
        "constraint_sequence_count_distribution": dict(Counter(sequence_lengths)),
        "raw_constraint_sequence_count_distribution": dict(Counter(raw_sequence_lengths)),
        "source_graph_count_distribution": dict(Counter(source_graph_counts)),
        "seed": seed,
    }
    return task_sequences, summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input",
        type=Path,
        default=Path("bench/MAC/cctu/mid_data/eval_step2_rule_graphs.validated.json"),
        help="Validated per-constraint histories to merge.",
    )
    parser.add_argument(
        "--task-input",
        type=Path,
        default=Path("bench/MAC/cctu/mid_data/eval_step1_cctu.json"),
        help="CCTU step-1 task metadata and constraint ordering source.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("bench/MAC/cctu/mid_data/eval_step3_base.json"),
        help="Output JSON with one constraint sequence per task.",
    )
    parser.add_argument("--seed", type=int, default=13, help="Seed for merge randomness.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    input_path = resolve_path(args.input)
    task_input_path = resolve_path(args.task_input)
    output_path = resolve_path(args.output)

    histories = extract_histories(load_json(input_path))
    task_payload = load_json(task_input_path)
    if not isinstance(task_payload, list):
        raise ValueError(f"Expected top-level JSON array in {task_input_path}")

    task_sequences, summary = build_task_sequences(
        histories,
        task_meta=task_metadata(task_payload),
        seed=args.seed,
    )
    payload = {
        "source_input": str(args.input),
        "task_input": str(args.task_input),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "summary": summary,
        "task_sequences": task_sequences,
    }
    write_json(output_path, payload)
    print(
        f"wrote {summary['task_count']} task constraint sequence(s), "
        f"total_constraints={summary['total_constraints_in_sequences']}, "
        f"avg_per_task={summary['avg_constraints_per_sequence']:.2f}, "
        f"output={output_path}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
