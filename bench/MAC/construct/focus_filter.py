#!/usr/bin/env python3
"""Build a focused step-1 dataset for MACBench.

Reads eval_step1_tmp.json, drops Cline_Prompt tasks, and labels each remaining
task with task_level=hard when it has more than 10 constraints, otherwise
task_level=normal.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Literal

TaskLevel = Literal["hard", "normal"]
EXCLUDED_AGENT_NAMES = {"Cline_Prompt"}
HARD_CONSTRAINT_THRESHOLD = 10
BOTTOM_TASK_KEYS = ("input", "constraints")
PREFERRED_METADATA_KEYS = (
    "id",
    "agent_name",
    "mac_task_uid",
    "task_level",
    "mac_task_summary",
    "mac_bench_filter_summary",
)

REPO_ROOT = Path(__file__).resolve().parents[3]


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=4, ensure_ascii=False) + "\n", encoding="utf-8")


def resolve_path(path: Path) -> Path:
    return path if path.is_absolute() else REPO_ROOT / path


def task_level(task: dict[str, Any]) -> TaskLevel:
    constraints = task.get("constraints", [])
    count = len(constraints) if isinstance(constraints, list) else 0
    return "hard" if count > HARD_CONSTRAINT_THRESHOLD else "normal"


def reorder_task_entry(task: dict[str, Any]) -> dict[str, Any]:
    """Put metadata first and heavy payload fields (input, constraints) last."""
    ordered: dict[str, Any] = {}
    seen: set[str] = set()

    for key in PREFERRED_METADATA_KEYS:
        if key in task:
            ordered[key] = task[key]
            seen.add(key)

    for key, value in task.items():
        if key in seen or key in BOTTOM_TASK_KEYS:
            continue
        ordered[key] = value
        seen.add(key)

    for key in BOTTOM_TASK_KEYS:
        if key in task:
            ordered[key] = task[key]

    return ordered


def focus_tasks(tasks: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    kept: list[dict[str, Any]] = []
    excluded_by_agent: dict[str, int] = {}
    hard_count = 0
    normal_count = 0

    for task in tasks:
        if not isinstance(task, dict):
            continue
        agent_name = str(task.get("agent_name", ""))
        if agent_name in EXCLUDED_AGENT_NAMES:
            excluded_by_agent[agent_name] = excluded_by_agent.get(agent_name, 0) + 1
            continue

        focused = reorder_task_entry(dict(task))
        level = task_level(focused)
        focused["task_level"] = level
        focused = reorder_task_entry(focused)
        kept.append(focused)
        if level == "hard":
            hard_count += 1
        else:
            normal_count += 1

    summary = {
        "source_task_count": len(tasks),
        "kept_task_count": len(kept),
        "excluded_task_count": sum(excluded_by_agent.values()),
        "excluded_by_agent": excluded_by_agent,
        "hard_task_count": hard_count,
        "normal_task_count": normal_count,
        "hard_constraint_threshold": HARD_CONSTRAINT_THRESHOLD,
    }
    return kept, summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input",
        type=Path,
        default=Path("bench/MAC/mid_data/eval_step1_tmp.json"),
        help="Filtered step-1 dataset.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("bench/MAC/mid_data/eval_step1_focus.json"),
        help="Focused step-1 dataset output path.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    input_path = resolve_path(args.input)
    output_path = resolve_path(args.output)
    raw = load_json(input_path)
    if not isinstance(raw, list):
        raise ValueError(f"Expected top-level JSON array in {input_path}")

    focused_tasks, summary = focus_tasks(raw)
    write_json(output_path, focused_tasks)
    print(
        f"wrote {summary['kept_task_count']} focused task(s) "
        f"(hard={summary['hard_task_count']}, normal={summary['normal_task_count']}, "
        f"excluded={summary['excluded_task_count']}) to {output_path}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
