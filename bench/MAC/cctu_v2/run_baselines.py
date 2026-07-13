"""Run information-sufficiency baselines over the 40-task CCTU v2 pilot.

The symbolic reader is deliberately an upper bound: it applies the benchmark
oracle to only the canonical events whose rendered user turns survived the
memory provider. It measures retained evidence, not LLM reasoning ability.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from bench.MAC.agent.memory.base import MemoryRequest
from bench.MAC.agent.memory.bm25 import BM25Config, BM25MemoryProvider
from bench.MAC.agent.memory.long_context import LongContextMemoryProvider
from bench.MAC.cctu_v2.core import candidate_allowed, resolve_active_directives

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_INPUT = ROOT / "bench/MAC/cctu_v2/data/pilot_40.json"
DEFAULT_OUTPUT = ROOT / "bench/MAC/cctu_v2/data/baseline_probe_report.json"


def _past_user_turns(world: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, int]]:
    turns: list[dict[str, Any]] = []
    event_turn_to_index: dict[str, int] = {}
    event_index = 0
    for message in world["rendered_history"]:
        if message["role"] != "user" or message["kind"] == "current_task":
            continue
        turn_index = str(len(turns))
        turns.append({"turn_index": turn_index, "content": message["content"]})
        if message["kind"] == "directive_event":
            event_turn_to_index[turn_index] = event_index
            event_index += 1
    if event_index != len(world["directive_events"]):
        raise ValueError("Rendered directive turns do not align with canonical events")
    return turns, event_turn_to_index


def _query(episode: dict[str, Any], prefix: dict[str, Any]) -> str:
    context = episode["current_context"]
    return "\n".join(
        [
            f"Current task: {episode['task_summary']}",
            f"Current project: {context.get('project')}",
            f"Current phase: {context.get('phase')}",
            f"Trajectory so far: {json.dumps(prefix['actions'], sort_keys=True)}",
            f"Candidate action: {json.dumps(episode['candidate_action'], sort_keys=True)}",
            "Decide whether the candidate action is allowed under effective prior user requirements.",
        ]
    )


def _memory_evidence(
    system: str,
    episode: dict[str, Any],
    world: dict[str, Any],
    prefix: dict[str, Any],
    *,
    bm25_top_k: int,
) -> tuple[list[dict[str, Any]], dict[str, Any], str]:
    turns, event_turn_to_index = _past_user_turns(world)
    request = MemoryRequest(
        task_uid=episode["episode_id"],
        agent="cctu_v2_probe",
        user_prompt=_query(episode, prefix),
        past_user_turns=turns,
        task=episode,
    )
    if system == "oracle":
        events = world["directive_events"]
        return events, {"included_event_count": len(events)}, ""
    if system == "long_context":
        result = LongContextMemoryProvider().build_memory(request)
        return world["directive_events"], result.metadata, result.memory
    if system == "bm25":
        result = BM25MemoryProvider(BM25Config(top_k=bm25_top_k)).build_memory(request)
        retrieved_turns = {str(match["turn_index"]) for match in result.metadata["matches"]}
        retained_indices = {
            event_turn_to_index[turn_index]
            for turn_index in retrieved_turns
            if turn_index in event_turn_to_index
        }
        events = [
            event
            for index, event in enumerate(world["directive_events"])
            if index in retained_indices
        ]
        metadata = dict(result.metadata)
        metadata["included_event_count"] = len(events)
        return events, metadata, result.memory
    raise ValueError(f"Unknown system: {system}")


def run_probe(payload: dict[str, Any], *, bm25_top_ks: tuple[int, ...] = (1, 3, 10)) -> dict[str, Any]:
    configurations = [("oracle", 0), ("long_context", 0)]
    configurations.extend(("bm25", top_k) for top_k in bm25_top_ks)
    rows: list[dict[str, Any]] = []

    for system, top_k in configurations:
        config_name = f"bm25@{top_k}" if system == "bm25" else system
        for episode in payload["episodes"]:
            for world in episode["worlds"]:
                for prefix in episode["trace_prefixes"]:
                    key = f"{world['world_id']}::{prefix['prefix_id']}"
                    events, metadata, memory = _memory_evidence(
                        system, episode, world, prefix, bm25_top_k=top_k
                    )
                    active = resolve_active_directives(events, episode["current_context"])
                    prediction = candidate_allowed(active, prefix["actions"], episode["candidate_action"])
                    gold = episode["gold_labels"][key]
                    rows.append(
                        {
                            "configuration": config_name,
                            "episode_id": episode["episode_id"],
                            "taxonomy_cell": episode["taxonomy_cell"],
                            "world_id": world["world_id"],
                            "prefix_id": prefix["prefix_id"],
                            "gold": gold,
                            "prediction": prediction,
                            "correct": prediction == gold,
                            "memory_chars": len(memory),
                            "metadata": metadata,
                        }
                    )

    summaries: dict[str, Any] = {}
    for config_name in dict.fromkeys(row["configuration"] for row in rows):
        subset = [row for row in rows if row["configuration"] == config_name]
        by_cell: dict[str, list[bool]] = defaultdict(list)
        episode_groups: dict[str, list[bool]] = defaultdict(list)
        for row in subset:
            by_cell[row["taxonomy_cell"]].append(row["correct"])
            episode_groups[row["episode_id"]].append(row["correct"])
        summaries[config_name] = {
            "condition_count": len(subset),
            "accuracy": sum(row["correct"] for row in subset) / len(subset),
            "all_conditions_correct_episode_rate": sum(all(values) for values in episode_groups.values())
            / len(episode_groups),
            "accuracy_by_taxonomy": {
                cell: sum(values) / len(values) for cell, values in sorted(by_cell.items())
            },
            "prediction_distribution": dict(Counter(str(row["prediction"]) for row in subset)),
            "mean_memory_chars": sum(row["memory_chars"] for row in subset) / len(subset),
        }

    return {
        "schema_version": "CCTUV2BaselineProbeV1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "method": "retrieval_plus_perfect_symbolic_reader_upper_bound",
        "caveat": "This is an information-sufficiency probe, not downstream LLM agent accuracy.",
        "summaries": summaries,
        "rows": rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    payload = json.loads(args.input.read_text(encoding="utf-8"))
    report = run_probe(payload)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(report["summaries"], indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
