"""CLI probe for delta-based SOPBench noise-follow."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from bench.construct.sop.noise_eval_grade import read_memory_output, trace_from_row
from bench.MAC.construct.sop.noise_eval import load_json, write_json
from bench.MAC.sopbench.delta_noise_follow import (
    aggregate_delta_noise_follow,
    evaluate_task_delta_noise_follow,
)
from bench.MAC.sopbench.graph_level_grade_probe import index_by_uid

DEFAULT_STEP2 = REPO_ROOT / "bench/MAC/sopbench/mid_data/eval_step2_anchors.json"
DEFAULT_STEP4 = REPO_ROOT / "bench/MAC/sopbench/mid_data/eval_step4_temporal_sequence_v3.json"
DEFAULT_MANIFEST = REPO_ROOT / "bench/MAC/sopbench/data/mac-sopbench-noise_eval_specs.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("answers_file", type=Path, help="memory_eval output JSON")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--step2", type=Path, default=DEFAULT_STEP2)
    parser.add_argument("--step4", type=Path, default=DEFAULT_STEP4)
    parser.add_argument("--output", type=Path, help="Optional JSON output path")
    return parser.parse_args()


def grade_delta_noise_follow(
    *,
    answers_file: Path,
    manifest_path: Path,
    step2_path: Path,
    step4_path: Path,
) -> dict[str, Any]:
    step2_by_uid = index_by_uid(load_json(step2_path))
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

    per_task: list[dict[str, Any]] = []
    for task_uid, task_spec in sorted(task_specs.items()):
        step2 = step2_by_uid.get(task_uid)
        step4 = step4_by_uid.get(task_uid)
        row = rows_by_task.get(task_uid)
        if not step2 or not step4 or not row:
            continue
        sequence = [item for item in (step4.get("temporal_sequence") or []) if isinstance(item, dict)]
        trace = trace_from_row(row)
        result = evaluate_task_delta_noise_follow(
            step2_task=step2,
            task_spec=task_spec,
            sequence=sequence,
            trace=trace,
        )
        per_task.append({"task_uid": task_uid, **result})

    return {
        "schema_version": "MACSOPDeltaNoiseFollowV1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_answers": str(answers_file),
        "run_header": {
            "run_id": header.get("run_id"),
            "bench": header.get("bench"),
            "memory_system": header.get("memory_system"),
        },
        "summary": aggregate_delta_noise_follow(per_task),
        "per_task": per_task,
    }


def main() -> int:
    args = parse_args()
    payload = grade_delta_noise_follow(
        answers_file=args.answers_file,
        manifest_path=args.manifest,
        step2_path=args.step2,
        step4_path=args.step4,
    )
    print(json.dumps(payload["summary"], indent=2, ensure_ascii=False))
    if args.output:
        write_json(args.output, payload)
        print(f"Wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
