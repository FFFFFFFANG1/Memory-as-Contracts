"""Build MAC runtime data files directly from the vendored CCTU benchmark."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from bench.MAC.cctu.bridge import (
    append_send_message,
    cctu_agent_name,
    cctu_difficulty,
    cctu_root,
    cctu_task_uid,
    first_message,
    load_cctu_samples,
    parse_cctu_tools,
    send_message_tool,
)

DEFAULT_OUTPUT_DIR = REPO_ROOT / "bench" / "MAC" / "cctu" / "data"
DIFFICULTIES = ("easy", "normal", "hard")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--limit", type=int, default=0, help="Maximum CCTU tasks to convert; 0 means all.")
    parser.add_argument("--offset", type=int, default=0)
    return parser.parse_args()


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=4, ensure_ascii=False) + "\n", encoding="utf-8")


def slice_samples(samples: list[dict[str, Any]], *, offset: int, limit: int) -> list[dict[str, Any]]:
    start = max(0, offset)
    if limit and limit > 0:
        return samples[start : start + limit]
    return samples[start:]


def constraint_records(sample: dict[str, Any], task_uid: str) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for index, raw in enumerate(sample.get("constraints_list") or []):
        if not isinstance(raw, list) or len(raw) < 3:
            continue
        primary, secondary, desc = raw[:3]
        records.append(
            {
                "id": index,
                "mac_constraint_uid": f"{task_uid}-c{index + 1:04d}",
                "desc": str(desc),
                "type": [str(primary), str(secondary)],
                "cctu_primary": str(primary),
                "cctu_secondary": str(secondary),
                "cctu_index": index,
                "check_code_stem": f"check_constraint_{index}",
            }
        )
    return records


def task_record(sample: dict[str, Any]) -> dict[str, Any]:
    sample_id = str(sample.get("id"))
    task_uid = cctu_task_uid(sample_id)
    user_prompt = first_message(sample, "user")
    difficulty = cctu_difficulty(sample)
    return {
        "task_uid": task_uid,
        "agent_name": cctu_agent_name(sample_id),
        "task_level": difficulty,
        "source_task_level": sample.get("data_source"),
        "task_summary": user_prompt,
        "original_input": copy.deepcopy(sample.get("messages") or []),
        "input": copy.deepcopy(sample.get("messages") or []),
        "constraints": constraint_records(sample, task_uid),
        "constraints_list": copy.deepcopy(sample.get("constraints_list") or []),
        "tools": sample.get("tools"),
        "codes": sample.get("codes"),
        "unsolved_set": sample.get("unsolved_set"),
        "answer": sample.get("answer"),
        "data_source": sample.get("data_source"),
        "cctu_id": sample_id,
        "task_chain": {
            "turns": [{"role": "user", "content": user_prompt}],
            "turn_count": 1,
            "target_user_turn_count": 1,
            "actual_user_turn_count": 1,
        },
        "evaluation": {
            "default_turn_policy": "last_user_turn",
            "current_user_turn": {"role": "user", "content": user_prompt},
            "past_user_turns": [],
        },
    }


def task_sets(samples: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {difficulty: [] for difficulty in DIFFICULTIES}
    for sample in samples:
        task = task_record(sample)
        grouped[str(task["task_level"])].append(task)

    now = datetime.now(timezone.utc).isoformat()
    return {
        difficulty: {
            "schema_version": "MACTaskSetV1",
            "generated_at": now,
            "difficulty": difficulty,
            "sources": {
                "cctu": str(cctu_root() / "data" / "input_data.jsonl"),
            },
            "summary": {
                "task_count": len(tasks),
                "total_turns": sum(task["task_chain"]["turn_count"] for task in tasks),
            },
            "tasks": sorted(tasks, key=lambda task: str(task.get("task_uid") or "")),
        }
        for difficulty, tasks in grouped.items()
    }


def system_config(samples: list[dict[str, Any]]) -> dict[str, Any]:
    terminal = send_message_tool()
    agents: dict[str, dict[str, Any]] = {}
    for sample in samples:
        sample_id = str(sample.get("id"))
        agent = cctu_agent_name(sample_id)
        task_uid = cctu_task_uid(sample_id)
        system_prompt = first_message(sample, "system")
        tools = append_send_message(parse_cctu_tools(sample))
        agents[agent] = {
            "agent": agent,
            "task_count": 1,
            "task_uids": [task_uid],
            "system_prompt": system_prompt,
            "system_prompt_sha256": sha256_text(system_prompt),
            "system_prompt_length": len(system_prompt),
            "system_prompt_is_default": False,
            "runtime_family": "cctu_tool_use",
            "needs_react_loop": True,
            "tools": tools,
            "aliases": {},
            "tool_rationale": "CCTU task-local tool schemas plus MAC send_message terminal tool.",
            "tool_extraction_cache": "cctu_input_data",
            "tool_extraction_skipped": False,
            "skip_reason": None,
            "cctu_id": sample_id,
            "data_source": sample.get("data_source"),
        }

    return {
        "schema_version": "MACSystemConfigV1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "sources": {
            "cctu": str(cctu_root() / "data" / "input_data.jsonl"),
        },
        "summary": {
            "total_agents": len(agents),
            "agents_with_system_prompt": len(agents),
            "agents_with_tools": len(agents),
            "agents_skipped_for_tool_extraction": 0,
            "agents_with_fallback_send_message": 0,
        },
        "send_message_tool": terminal,
        "agents": agents,
    }


def main() -> None:
    args = parse_args()
    samples = slice_samples(load_cctu_samples(), offset=args.offset, limit=args.limit)
    sets = task_sets(samples)
    for difficulty, payload in sets.items():
        write_json(args.output_dir / f"mac_{difficulty}.json", payload)
    write_json(args.output_dir / "mac_system_config.json", system_config(samples))
    print(
        "Wrote "
        + ", ".join(str(args.output_dir / f"mac_{difficulty}.json") for difficulty in DIFFICULTIES)
        + f", {args.output_dir / 'mac_system_config.json'}"
    )


if __name__ == "__main__":
    main()
