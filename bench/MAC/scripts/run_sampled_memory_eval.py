#!/usr/bin/env python3
"""Run memory eval on an explicit sampled task UID list."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from bench.MAC.cctu.bridge import build_cctu_system_config, load_cctu_eval_tasks
from bench.MAC.scripts import run_memory_eval as rme
from bench.MAC.sopbench.bridge import build_sopbench_system_config, load_sopbench_eval_tasks


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sample-file", type=Path, required=True, help="JSON list of task_uids.")
    parser.add_argument("run_args", nargs=argparse.REMAINDER, help="Args forwarded to run_memory_eval.")
    return parser.parse_args()


def load_sample_uids(path: Path) -> list[str]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        uids = payload
    elif isinstance(payload, dict):
        uids = payload.get("task_uids")
    else:
        uids = None
    if not isinstance(uids, list) or not uids:
        raise ValueError(f"{path} must contain a non-empty task_uids list")
    return [str(item) for item in uids]


def patch_load_run_context(*, bench: str, sample_uids: list[str]) -> None:
    original = rme.load_run_context

    def patched(args: argparse.Namespace, *, offset: int = 0, limit: int = 0):
        if args.bench != bench:
            return original(args, offset=offset, limit=limit)
        if bench == "cctu":
            tasks, task_set_summary = load_cctu_eval_tasks(uids=sample_uids)
            system_config = build_cctu_system_config()
        elif bench == "sopbench":
            tasks, task_set_summary = load_sopbench_eval_tasks(uids=sample_uids)
            system_config = build_sopbench_system_config()
        else:
            raise ValueError(f"Unsupported bench for sampled eval: {bench}")
        task_set_summary = {
            **task_set_summary,
            "sampled": True,
            "sample_count": len(sample_uids),
            "sample_uids": sample_uids,
        }
        return tasks, task_set_summary, system_config

    rme.load_run_context = patched


def main() -> None:
    args = parse_args()
    sample_uids = load_sample_uids(args.sample_file)
    forwarded = [item for item in args.run_args if item != "--"]
    if not forwarded:
        raise SystemExit("Missing forwarded run_memory_eval args")

    argv_backup = sys.argv
    sys.argv = [argv_backup[0], *forwarded]
    try:
        run_args = rme.parse_args()
    finally:
        sys.argv = argv_backup

    patch_load_run_context(bench=str(run_args.bench), sample_uids=sample_uids)
    asyncio.run(rme.run(run_args))


if __name__ == "__main__":
    main()
