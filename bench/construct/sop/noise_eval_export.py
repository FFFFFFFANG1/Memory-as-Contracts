#!/usr/bin/env python3
"""Export deterministic SOP temporal noise eval specs from step4 sequence artifacts."""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

if sys.version_info < (3, 10):
    raise SystemExit("SOP noise eval requires Python 3.10+ (SOPBench dependency).")

from bench.MAC.construct.sop.noise_eval import (  # noqa: E402
    build_eval_revision,
    build_manifest_payload,
    load_json,
    resolve_path,
    write_json,
)

DEFAULT_STEP2 = Path("bench/MAC/sopbench/mid_data/eval_step2_anchors.json")
DEFAULT_STEP3 = Path("bench/MAC/sopbench/mid_data/eval_step3_temporal_noise.json")
DEFAULT_STEP4 = Path("bench/MAC/sopbench/mid_data/eval_step4_temporal_sequence_v3.json")
DEFAULT_OUTPUT = Path("bench/MAC/sopbench/mid_data/eval_step5_noise_eval_specs.json")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--step2", type=Path, default=DEFAULT_STEP2)
    parser.add_argument("--step3", type=Path, default=DEFAULT_STEP3)
    parser.add_argument("--step4", type=Path, default=DEFAULT_STEP4)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--task", action="append", default=[], help="Limit to mac_task_uid (repeatable).")
    parser.add_argument("--limit", type=int, default=0, help="Export only the first N tasks after filtering.")
    return parser.parse_args()


def index_tasks(payload: Any) -> dict[str, dict[str, Any]]:
    if isinstance(payload, dict):
        rows = payload.get("tasks") or payload.get("task_histories") or []
    elif isinstance(payload, list):
        rows = payload
    else:
        raise TypeError("task payload must be a list or object with tasks")
    return {
        str(row.get("mac_task_uid") or ""): row
        for row in rows
        if isinstance(row, dict) and row.get("mac_task_uid")
    }


def main() -> int:
    args = parse_args()
    step2_by_uid = index_tasks(load_json(args.step2))
    step3_by_uid = index_tasks(load_json(args.step3))
    step4_payload = load_json(args.step4)
    step4_by_uid = index_tasks(step4_payload)

    selected_uids = sorted(step4_by_uid)
    if args.task:
        wanted = {str(item) for item in args.task}
        selected_uids = [uid for uid in selected_uids if uid in wanted]
    if args.limit and args.limit > 0:
        selected_uids = selected_uids[: args.limit]

    revisions = []
    skipped: list[str] = []
    for uid in selected_uids:
        step2_task = step2_by_uid.get(uid)
        step3_task = step3_by_uid.get(uid)
        step4_task = step4_by_uid.get(uid)
        if not step2_task or not step3_task or not step4_task:
            skipped.append(uid)
            continue
        try:
            revisions.append(
                build_eval_revision(
                    step2_task=step2_task,
                    step3_task=step3_task,
                    step4_task=step4_task,
                )
            )
        except Exception as exc:  # noqa: BLE001
            skipped.append(f"{uid}: {type(exc).__name__}: {exc}")

    payload = build_manifest_payload(
        revisions=revisions,
        source_step2=str(args.step2),
        source_step3=str(args.step3),
        source_step4=str(args.step4),
    )
    payload["generated_at"] = datetime.now(timezone.utc).isoformat()
    payload["summary"]["skipped"] = skipped
    write_json(args.output, payload)
    print(
        f"Exported {payload['summary']['task_count']} task(s), "
        f"{payload['summary']['unit_count']} unit(s) -> {resolve_path(args.output)}"
    )
    if skipped:
        print(f"Skipped {len(skipped)} task(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
