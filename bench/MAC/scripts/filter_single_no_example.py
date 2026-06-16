#!/usr/bin/env python3
"""Keep single-turn tasks with no example_driven constraints."""

import argparse
import json
from pathlib import Path


def is_multi_turn(item: dict) -> bool:
    return item.get("query_id") is not None


def has_example_driven(item: dict) -> bool:
    return any(c.get("dimension") == "example_driven" for c in item.get("constraints", []))


def filter_dataset(data: list[dict]) -> list[dict]:
    return [item for item in data if not is_multi_turn(item) and not has_example_driven(item)]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=Path("data/eval_full.json"))
    parser.add_argument("--output", type=Path, default=Path("data/eval.json"))
    args = parser.parse_args()

    data = json.loads(args.input.read_text(encoding="utf-8"))
    filtered = filter_dataset(data)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(filtered, indent=4, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"{len(filtered)} / {len(data)} samples -> {args.output}")


if __name__ == "__main__":
    main()
