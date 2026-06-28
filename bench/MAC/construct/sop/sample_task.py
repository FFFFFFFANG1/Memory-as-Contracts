#!/usr/bin/env python3
"""Sample SOPBench tasks while preserving the source domain distribution.

Reads ``bench/SOPBench/data/*_tasks.json``, draws *n* tasks without replacement
per domain using largest-remainder allocation, and writes a manifest JSON for
downstream construct steps.
"""

from __future__ import annotations

import argparse
import copy
import json
import math
import random
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_DATA_DIR = Path("bench/SOPBench/data")
DEFAULT_OUTPUT = Path("bench/MAC/sopbench/mid_data/sampled_tasks_200.json")

DOMAIN_FILES = (
    "bank_tasks.json",
    "dmv_tasks.json",
    "healthcare_tasks.json",
    "hotel_tasks.json",
    "library_tasks.json",
    "online_market_tasks.json",
    "university_tasks.json",
)


def resolve_path(path: Path) -> Path:
    return path if path.is_absolute() else REPO_ROOT / path


def load_json(path: Path) -> Any:
    return json.loads(resolve_path(path).read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    target = resolve_path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, indent=4, ensure_ascii=False) + "\n", encoding="utf-8")


def domain_from_filename(name: str) -> str:
    return name.removesuffix("_tasks.json")


def load_all_tasks(data_dir: Path) -> dict[str, list[dict[str, Any]]]:
    by_domain: dict[str, list[dict[str, Any]]] = {}
    for filename in DOMAIN_FILES:
        path = data_dir / filename
        if not path.is_file():
            raise FileNotFoundError(f"Missing SOPBench task file: {path}")
        domain = domain_from_filename(filename)
        raw = load_json(path)
        if not isinstance(raw, dict):
            raise ValueError(f"Expected top-level object in {path}")
        flat: list[dict[str, Any]] = []
        for user_goal, tasks in raw.items():
            if not isinstance(tasks, list):
                raise ValueError(f"Expected list for {domain}/{user_goal} in {path}")
            for task_index, task in enumerate(tasks):
                if not isinstance(task, dict):
                    raise ValueError(f"Expected task object at {domain}/{user_goal}[{task_index}]")
                record = copy.deepcopy(task)
                record.setdefault("user_goal", user_goal)
                record["domain"] = domain
                record["task_index"] = task_index
                record["source_file"] = filename
                flat.append(record)
        by_domain[domain] = flat
    return by_domain


def allocate_counts(domain_sizes: dict[str, int], sample_size: int) -> dict[str, int]:
    total = sum(domain_sizes.values())
    if sample_size > total:
        raise ValueError(f"sample_size {sample_size} exceeds available tasks {total}")

    quotas = {domain: sample_size * count / total for domain, count in domain_sizes.items()}
    floors = {domain: int(math.floor(q)) for domain, q in quotas.items()}
    assigned = sum(floors.values())
    remainder = sample_size - assigned

    ranked = sorted(
        domain_sizes,
        key=lambda domain: (quotas[domain] - floors[domain], domain_sizes[domain]),
        reverse=True,
    )
    counts = dict(floors)
    for domain in ranked[:remainder]:
        counts[domain] += 1
    return counts


def sop_task_uid(domain: str, user_goal: str, task_index: int) -> str:
    return f"sopbench:{domain}:{user_goal}:{task_index}"


def sample_tasks(
    by_domain: dict[str, list[dict[str, Any]]],
    sample_size: int,
    seed: int,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rng = random.Random(seed)
    domain_sizes = {domain: len(tasks) for domain, tasks in by_domain.items()}
    counts = allocate_counts(domain_sizes, sample_size)

    sampled: list[dict[str, Any]] = []
    for domain in sorted(by_domain):
        pool = list(by_domain[domain])
        take = counts[domain]
        if take > len(pool):
            raise ValueError(f"Cannot sample {take} tasks from {domain} (only {len(pool)} available)")
        chosen = rng.sample(pool, take)
        for task in chosen:
            entry = copy.deepcopy(task)
            entry["mac_task_uid"] = sop_task_uid(
                entry["domain"],
                entry["user_goal"],
                entry["task_index"],
            )
            sampled.append(entry)

    rng.shuffle(sampled)

    source_total = sum(domain_sizes.values())
    summary = {
        "sample_size": sample_size,
        "source_total": source_total,
        "seed": seed,
        "domain_counts_requested": counts,
        "domain_counts_source": domain_sizes,
        "domain_fractions_source": {
            domain: round(count / source_total, 6) for domain, count in domain_sizes.items()
        },
        "sampled_domain_counts": {
            domain: sum(1 for task in sampled if task["domain"] == domain)
            for domain in sorted(domain_sizes)
        },
    }
    return sampled, summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=DEFAULT_DATA_DIR,
        help="Directory containing SOPBench *_tasks.json files.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="Output manifest JSON path.",
    )
    parser.add_argument(
        "--sample-size",
        type=int,
        default=200,
        help="Number of tasks to sample (default: 200).",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random seed for reproducible sampling.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    data_dir = resolve_path(args.data_dir)
    by_domain = load_all_tasks(data_dir)
    tasks, summary = sample_tasks(by_domain, args.sample_size, args.seed)

    payload = {
        "schema_version": "MACSOPBenchSampleV1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_data_dir": str(data_dir.relative_to(REPO_ROOT)) if data_dir.is_relative_to(REPO_ROOT) else str(data_dir),
        "summary": summary,
        "tasks": tasks,
    }
    write_json(args.output, payload)

    print(f"Wrote {len(tasks)} tasks to {resolve_path(args.output)}")
    print("Sampled domain counts:")
    for domain, count in summary["sampled_domain_counts"].items():
        src = summary["domain_counts_source"][domain]
        print(f"  {domain}: {count} / {src}")


if __name__ == "__main__":
    main()
