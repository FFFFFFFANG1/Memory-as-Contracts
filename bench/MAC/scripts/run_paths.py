"""Shared output paths and run identifiers for MAC benchmark runs."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from bench.MAC.agent.loop.prompt import REPO_ROOT

BENCH_NAMES = ("cctu", "sopbench")


def bench_results_dir(bench: str) -> Path:
    if bench not in BENCH_NAMES:
        raise ValueError(f"Unknown bench for results dir: {bench}")
    return REPO_ROOT / "bench" / "MAC" / bench / "results"


def memory_output_dir(bench: str) -> Path:
    return bench_results_dir(bench) / "memory_output"


def memory_output_error_dir(bench: str) -> Path:
    return bench_results_dir(bench) / "memory_output_error"


def memory_grade_dir(bench: str) -> Path:
    return bench_results_dir(bench) / "memory_grade"


def log_dir(bench: str) -> Path:
    return bench_results_dir(bench) / "logs"


def make_run_unique_index(when: datetime | None = None) -> str:
    """Return `{unix_seconds}-{dd}-{mm}-{yy}`."""
    moment = when or datetime.now(UTC)
    return f"{int(moment.timestamp())}-{moment.strftime('%d-%m-%y')}"


def bench_run_basename(memory_system: str, bench: str, run_id: str) -> str:
    return f"{memory_system}_{bench}_{run_id}"


def bench_output_path(memory_system: str, bench: str, run_id: str) -> Path:
    return memory_output_dir(bench) / f"{bench_run_basename(memory_system, bench, run_id)}.json"


def memory_output_error_path(output_path: Path, *, bench: str) -> Path:
    """Return the JSONL path for incremental error records for a run output file."""
    return memory_output_error_dir(bench) / f"{output_path.stem}.jsonl"


def bench_grade_path(memory_system: str, bench: str, run_id: str) -> Path:
    return memory_grade_dir(bench) / f"{bench_run_basename(memory_system, bench, run_id)}.json"


def mac_graph_dir(bench: str) -> Path:
    return bench_results_dir(bench) / "mac_graph"


def mac_graph_path(memory_system: str, bench: str, run_id: str, task_uid: str) -> Path:
    safe_task = "".join(char if char.isalnum() or char in {"-", "_"} else "_" for char in task_uid)
    return mac_graph_dir(bench) / f"{bench_run_basename(memory_system, bench, run_id)}__{safe_task}.json"


def bench_run_log_path(memory_system: str, bench: str, run_id: str) -> Path:
    return log_dir(bench) / f"{bench_run_basename(memory_system, bench, run_id)}.log"
