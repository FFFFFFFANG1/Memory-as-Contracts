"""Run CCTU baseline memory systems sequentially with error/rate-limit guards."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from bench.MAC.scripts.run_paths import bench_output_path, make_run_unique_index, memory_output_error_path

SYSTEMS = ("bm25", "embedding", "rrf", "mem0")
BENCH = "cctu"
MAX_WORKER = 6
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
LOG_DIR = REPO_ROOT / "bench" / "MAC" / "cctu" / "results" / "logs"
SUMMARY_PATH = REPO_ROOT / "bench" / "MAC" / "cctu" / "results" / "baseline_batch_summary.json"


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def collect_error_text(output_path: Path, error_path: Path) -> str:
    chunks: list[str] = []
    if output_path.exists():
        _, records = _read_memory_output(output_path)
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
    return "\n".join(chunks).lower()


def _read_memory_output(path: Path) -> tuple[dict, list[dict]]:
    payload = load_json(path)
    header = payload.get("header")
    records = payload.get("records")
    if not isinstance(header, dict) or not isinstance(records, list):
        raise ValueError(f"{path} is not a MACMemoryOutputV1 file")
    return header, [row for row in records if isinstance(row, dict)]


def detect_rate_limit(output_path: Path, error_path: Path) -> str | None:
    blob = collect_error_text(output_path, error_path)
    for pattern in RATE_LIMIT_PATTERNS:
        if pattern in blob:
            return pattern
    return None


def summarize_errors(output_path: Path, error_path: Path) -> dict:
    header, records = _read_memory_output(output_path)
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


def wait_for_first_output(log_path: Path, process: subprocess.Popen[str], *, timeout_s: int = 3600) -> None:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        if log_path.exists():
            text = log_path.read_text(encoding="utf-8", errors="replace")
            if FIRST_OUTPUT_RE.search(text):
                print(f"FIRST_OUTPUT {log_path.name}", flush=True)
                return
        if process.poll() is not None:
            text = log_path.read_text(encoding="utf-8", errors="replace") if log_path.exists() else ""
            if FIRST_OUTPUT_RE.search(text):
                print(f"FIRST_OUTPUT {log_path.name}", flush=True)
                return
            raise RuntimeError(
                f"Process exited before first output (code={process.returncode}). "
                f"See log: {log_path}"
            )
        time.sleep(2)
    raise TimeoutError(f"Timed out waiting for first output in {log_path}")


def run_eval(system: str, run_id: str, output_path: Path, log_path: Path) -> int:
    cmd = [
        "uv",
        "run",
        "python",
        "-m",
        "bench.MAC.scripts.run_memory_eval",
        "--memory-system",
        system,
        "--bench",
        BENCH,
        "--tool-executor",
        "cctu",
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
    print(f"START {system} run_id={run_id}", flush=True)
    with log_path.open("w", encoding="utf-8") as handle:
        process = subprocess.Popen(
            cmd,
            cwd=REPO_ROOT,
            stdout=handle,
            stderr=subprocess.STDOUT,
            text=True,
        )
        wait_for_first_output(log_path, process)
        print(f"BACKGROUND {system} pid={process.pid} log={log_path}", flush=True)
        return process.wait()


def grade_run(output_path: Path, grade_path: Path) -> dict:
    cmd = [
        "uv",
        "run",
        "python",
        "-m",
        "bench.MAC.cctu.grade_answer",
        str(output_path),
        "--output",
        str(grade_path),
    ]
    completed = subprocess.run(cmd, cwd=REPO_ROOT, check=True, capture_output=True, text=True)
    payload = load_json(grade_path)
    print(completed.stdout, end="", flush=True)
    return payload["scores"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch-id", help="Reuse an existing batch id for remaining systems.")
    parser.add_argument(
        "--start-from",
        choices=SYSTEMS,
        help="Skip systems before this one (for resume).",
    )
    parser.add_argument(
        "--summary-path",
        type=Path,
        default=SUMMARY_PATH,
        help="Where to write batch summary JSON.",
    )
    return parser.parse_args()


def systems_to_run(args: argparse.Namespace) -> tuple[str, ...]:
    if not args.start_from:
        return SYSTEMS
    start_index = SYSTEMS.index(args.start_from)
    return SYSTEMS[start_index:]


def load_summary(path: Path, *, batch_id: str | None = None) -> dict:
    if path.exists():
        payload = load_json(path)
        if isinstance(payload, dict):
            if batch_id:
                payload["batch_id"] = batch_id
            payload["stopped_reason"] = None
            return payload
    return {
        "batch_id": batch_id or make_run_unique_index(),
        "started_at": now_iso(),
        "systems": {},
        "stopped_reason": None,
    }


def main() -> int:
    args = parse_args()
    summary_path = args.summary_path
    batch_id = args.batch_id or make_run_unique_index()
    summary = load_summary(summary_path, batch_id=batch_id if args.batch_id else None)
    if not args.batch_id:
        batch_id = summary["batch_id"]
    write_json(summary_path, summary)

    for system in systems_to_run(args):
        run_id = f"baseline-{system}-{batch_id}"
        output_path = bench_output_path(system, BENCH, run_id)
        error_path = memory_output_error_path(output_path, bench=BENCH)
        log_path = LOG_DIR / f"{system}_cctu_{run_id}.log"
        grade_path = REPO_ROOT / "bench" / "MAC" / "cctu" / "results" / "memory_grade" / f"{system}_cctu_{run_id}.json"

        exit_code = run_eval(system, run_id, output_path, log_path)
        error_summary = summarize_errors(output_path, error_path)
        rate_limit = detect_rate_limit(output_path, error_path)

        system_summary: dict = {
            "run_id": run_id,
            "output_path": str(output_path),
            "log_path": str(log_path),
            "exit_code": exit_code,
            "finished_at": now_iso(),
            **error_summary,
            "rate_limit_hit": rate_limit,
        }

        if exit_code != 0:
            summary["systems"][system] = system_summary
            summary["stopped_reason"] = f"{system} eval exited with code {exit_code}"
            summary["finished_at"] = now_iso()
            write_json(summary_path, summary)
            print(summary["stopped_reason"], flush=True)
            return exit_code

        if rate_limit:
            summary["systems"][system] = system_summary
            summary["stopped_reason"] = f"rate limit detected during {system}: matched {rate_limit!r}"
            summary["finished_at"] = now_iso()
            write_json(summary_path, summary)
            print(summary["stopped_reason"], flush=True)
            return 2

        scores = grade_run(output_path, grade_path)
        system_summary["grade_path"] = str(grade_path)
        system_summary["scores"] = scores
        summary["systems"][system] = system_summary
        write_json(summary_path, summary)
        print(f"DONE {system} scores={json.dumps(scores.get('Overall'), ensure_ascii=False)}", flush=True)

    summary["finished_at"] = now_iso()
    write_json(summary_path, summary)
    print(f"BATCH_COMPLETE {summary_path}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
