#!/usr/bin/env python3
"""Run bm25 and embedding baselines on CCTU + SOPBench until rate limit or completion."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from bench.MAC.scripts.run_paths import bench_grade_path, bench_output_path, make_run_unique_index, memory_output_error_path

SYSTEMS = ("bm25", "embedding")
BENCHES = ("cctu", "sopbench")
MAX_WORKER = 8
CHECKPOINT_INTERVAL = 10

RATE_LIMIT_PATTERNS = (
    "rate limit",
    "rate_limit",
    "ratelimit",
    "too many requests",
    "quota exceeded",
    "insufficient_quota",
    "429",
    "resource_exhausted",
)

FIRST_OUTPUT_RE = re.compile(r"\[\d+/\d+\]|Checkpoint wrote|Final wrote")
SUMMARY_PATH = REPO_ROOT / "bench" / "MAC" / "results" / "bm25_embedding_batch_summary.json"


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def read_memory_output(path: Path) -> tuple[dict, list[dict]]:
    payload = load_json(path)
    header = payload.get("header")
    records = payload.get("records")
    if not isinstance(header, dict) or not isinstance(records, list):
        raise ValueError(f"{path} is not a MACMemoryOutputV1 file")
    return header, [row for row in records if isinstance(row, dict)]


def collect_error_text(output_path: Path, error_path: Path, log_path: Path) -> str:
    chunks: list[str] = []
    if output_path.exists():
        _, records = read_memory_output(output_path)
        for row in records:
            if row.get("record_type") == "task_error":
                chunks.append(str(row.get("error") or ""))
                chunks.append(str(row.get("error_cause") or ""))
    if error_path.exists():
        for line in error_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            record = payload.get("record")
            if not isinstance(record, dict) or record.get("record_type") != "task_error":
                continue
            chunks.append(str(record.get("error") or ""))
            chunks.append(str(record.get("error_cause") or ""))
    if log_path.exists():
        chunks.append(log_path.read_text(encoding="utf-8", errors="replace"))
    return "\n".join(chunks).lower()


def detect_rate_limit(output_path: Path, error_path: Path, log_path: Path) -> str | None:
    blob = collect_error_text(output_path, error_path, log_path)
    for pattern in RATE_LIMIT_PATTERNS:
        if pattern in blob:
            return pattern
    return None


def summarize_run(output_path: Path, error_path: Path) -> dict:
    header, records = read_memory_output(output_path)
    task_errors = [row for row in records if row.get("record_type") == "task_error"]
    task_results = [row for row in records if row.get("record_type") == "task_result"]
    return {
        "task_count": header.get("task_count"),
        "task_result_count": len(task_results),
        "task_error_count": len(task_errors),
        "sample_errors": [
            {
                "index": row.get("index"),
                "task_uid": row.get("task_uid"),
                "error": row.get("error"),
            }
            for row in task_errors[:5]
        ],
        "error_jsonl": str(error_path),
    }


def grade_module(bench: str) -> str:
    if bench == "cctu":
        return "bench.MAC.construct.cctu.noise_eval_grade"
    return "bench.construct.sop.noise_eval_grade"


def run_eval(*, system: str, bench: str, run_id: str, output_path: Path, log_path: Path) -> int:
    cmd = [
        "uv",
        "run",
        "python",
        "-m",
        "bench.MAC.scripts.run_memory_eval",
        "--memory-system",
        system,
        "--bench",
        bench,
        "--tool-executor",
        bench if bench in {"cctu", "sopbench"} else "heuristic",
        "--max-worker",
        str(MAX_WORKER),
        "--run-id",
        run_id,
        "--checkpoint-interval",
        str(CHECKPOINT_INTERVAL),
        "--output",
        str(output_path),
    ]
    log_path.parent.mkdir(parents=True, exist_ok=True)
    print(f"START {system}/{bench} run_id={run_id}", flush=True)
    completed = subprocess.run(
        cmd,
        cwd=REPO_ROOT,
        stdout=log_path.open("w", encoding="utf-8"),
        stderr=subprocess.STDOUT,
        text=True,
    )
    return completed.returncode


def grade_run(*, bench: str, output_path: Path, grade_path: Path) -> list[dict]:
    cmd = [
        "uv",
        "run",
        "python",
        "-m",
        grade_module(bench),
        str(output_path),
        "--output",
        str(grade_path),
    ]
    completed = subprocess.run(cmd, cwd=REPO_ROOT, check=True, capture_output=True, text=True)
    print(completed.stdout, end="", flush=True)
    return load_json(grade_path)["scores"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch-id", help="Reuse batch id prefix for run ids.")
    parser.add_argument(
        "--systems",
        nargs="+",
        choices=SYSTEMS,
        default=list(SYSTEMS),
        help="Memory systems to run (default: bm25 embedding).",
    )
    parser.add_argument(
        "--benches",
        nargs="+",
        choices=BENCHES,
        default=list(BENCHES),
        help="Benchmarks to run (default: cctu sopbench).",
    )
    parser.add_argument(
        "--start-from",
        help="Resume from '<system>:<bench>' e.g. embedding:cctu",
    )
    parser.add_argument("--summary-path", type=Path, default=SUMMARY_PATH)
    return parser.parse_args()


def job_order(systems: tuple[str, ...], benches: tuple[str, ...]) -> list[tuple[str, str]]:
    return [(system, bench) for system in systems for bench in benches]


def main() -> int:
    args = parse_args()
    batch_id = args.batch_id or make_run_unique_index()
    jobs = job_order(tuple(args.systems), tuple(args.benches))
    if args.start_from:
        start = tuple(args.start_from.split(":", 1))
        if len(start) != 2 or start not in jobs:
            raise SystemExit(f"Invalid --start-from {args.start_from!r}; expected one of {jobs}")
        jobs = jobs[jobs.index(start) :]

    summary = {
        "batch_id": batch_id,
        "started_at": now_iso(),
        "max_worker": MAX_WORKER,
        "runs": {},
        "stopped_reason": None,
    }
    write_json(args.summary_path, summary)

    for system, bench in jobs:
        key = f"{system}:{bench}"
        run_id = batch_id
        output_path = bench_output_path(system, bench, run_id)
        error_path = memory_output_error_path(output_path, bench=bench)
        log_dir = REPO_ROOT / "bench" / "MAC" / bench / "results" / "logs"
        log_path = log_dir / f"{system}_{bench}_{run_id}.log"
        grade_path = bench_grade_path(system, bench, run_id)

        exit_code = run_eval(system=system, bench=bench, run_id=run_id, output_path=output_path, log_path=log_path)
        run_summary = {
            "run_id": run_id,
            "output_path": str(output_path),
            "log_path": str(log_path),
            "exit_code": exit_code,
            "finished_at": now_iso(),
        }
        if output_path.exists():
            run_summary.update(summarize_run(output_path, error_path))
        rate_limit = detect_rate_limit(output_path, error_path, log_path)
        run_summary["rate_limit_hit"] = rate_limit

        if exit_code != 0:
            summary["runs"][key] = run_summary
            summary["stopped_reason"] = f"{key} eval exited with code {exit_code}"
            summary["finished_at"] = now_iso()
            write_json(args.summary_path, summary)
            print(summary["stopped_reason"], flush=True)
            return exit_code

        if rate_limit:
            summary["runs"][key] = run_summary
            summary["stopped_reason"] = f"rate limit detected during {key}: matched {rate_limit!r}"
            summary["finished_at"] = now_iso()
            write_json(args.summary_path, summary)
            print(summary["stopped_reason"], flush=True)
            return 2

        scores = grade_run(bench=bench, output_path=output_path, grade_path=grade_path)
        run_summary["grade_path"] = str(grade_path)
        run_summary["scores"] = scores
        summary["runs"][key] = run_summary
        write_json(args.summary_path, summary)
        print(f"DONE {key} grade={grade_path}", flush=True)

    summary["finished_at"] = now_iso()
    summary["stopped_reason"] = "completed"
    write_json(args.summary_path, summary)
    print("All requested baselines completed.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
