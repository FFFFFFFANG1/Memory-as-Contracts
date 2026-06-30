#!/usr/bin/env python3
"""Grade SOP temporal noise eval specs against a memory-eval run output."""

from __future__ import annotations

import argparse
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
    contract_metrics,
    evaluate_sopbench_unit,
    evaluate_task,
    func_calls_from_trace,
    load_json,
    outcome_bucket,
    resolve_path,
    task_acc,
    task_responded,
    write_json,
)

DEFAULT_MANIFEST = Path("bench/MAC/sopbench/data/mac-sopbench-noise_eval_specs.json")
DEFAULT_OUTPUT = Path("bench/MAC/sopbench/results/eval_step6_noise_eval_grade.json")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "answers_file",
        type=Path,
        nargs="?",
        help="JSON output from bench/MAC/scripts/run_memory_eval.py",
    )
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--detail", action="store_true")
    parser.add_argument(
        "--dry-run-empty",
        action="store_true",
        help="Grade manifest structure only using empty trajectories (smoke test).",
    )
    return parser.parse_args()


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


def grouped_contract_metrics(
    details: list[dict[str, Any]],
    key: str,
) -> dict[str, Any]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in details:
        grouped[str(row.get(key) or "unknown")].append(row)
    return {name: contract_metrics(rows) for name, rows in sorted(grouped.items())}


def main() -> int:
    args = parse_args()
    manifest = load_json(args.manifest)
    units = manifest.get("units") if isinstance(manifest, dict) else None
    task_specs = manifest.get("task_specs") if isinstance(manifest, dict) else None
    if not isinstance(units, list) or not isinstance(task_specs, dict):
        raise ValueError("manifest must contain units list and task_specs object")

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
        task_eval: dict[str, Any] | None = None
        replay_cache: dict[str, Any] | None = None
        if func_calls_from_trace(trace):
            task_eval = evaluate_task(task_spec=task_spec, trace=trace)
            replay_cache = task_eval.pop("_replay", None)
        task_scores[task_uid] = {
            "ACC": task_acc(task_eval) if task_eval else False,
            "RSP": task_responded(trace),
            "dirgraph_satisfied": task_eval.get("dirgraph_satisfied") if task_eval else None,
            "success": task_eval.get("success") if task_eval else None,
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

    contract = contract_metrics(details)
    task_acc_values = [row.get("ACC") for row in task_scores.values() if row.get("ACC") is not None]
    task_rsp_values = [row.get("RSP") for row in task_scores.values() if row.get("RSP") is not None]
    payload = {
        "schema_version": "MACSOPNoiseEvalGradeV2",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_answers": str(args.answers_file) if args.answers_file else None,
        "source_manifest": str(args.manifest),
        "dry_run_empty": args.dry_run_empty,
        "run_header": {
            "run_id": header.get("run_id"),
            "bench": header.get("bench"),
            "memory_system": header.get("memory_system"),
        },
        "graded_unit_count": len(details),
        "missing_task_unit_count": missing_tasks,
        "task_scores": task_scores,
        "scores": {
            "ACC": (sum(1 for value in task_acc_values if value) / len(task_acc_values))
            if task_acc_values
            else None,
            "RSP": (sum(1 for value in task_rsp_values if value) / len(task_rsp_values))
            if task_rsp_values
            else None,
            **contract,
        },
        "scores_by_domain": grouped_contract_metrics(details, "domain"),
        "scores_by_unit_source": grouped_contract_metrics(details, "unit_source"),
        "details": details if args.detail else [],
    }
    write_json(args.output, payload)
    print(json.dumps(payload["scores"], indent=2, ensure_ascii=False))
    print(f"Wrote {resolve_path(args.output)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
