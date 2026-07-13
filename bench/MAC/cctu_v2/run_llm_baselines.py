"""Evaluate CCTU v2 decisions with an OpenAI-compatible judge model."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from openai import AsyncOpenAI

from bench.MAC.agent.memory.base import MemoryRequest
from bench.MAC.agent.memory.bm25 import BM25Config, BM25MemoryProvider
from bench.MAC.agent.memory.long_context import LongContextMemoryProvider
from bench.MAC.cctu_v2.core import resolve_active_directives
from bench.MAC.cctu_v2.run_baselines import _past_user_turns, _query

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_INPUT = ROOT / "bench/MAC/cctu_v2/data/pilot_40.json"
DEFAULT_OUTPUT = ROOT / "bench/MAC/cctu_v2/data/llm_baseline_results.json"
SYSTEM_PROMPT = """You evaluate memory-governed agent execution.
For every condition, decide whether the proposed NEXT action is allowed.
Use only the supplied memory, current context, and trajectory. Prior user
requirements can be introduced, amended, revoked, scoped, or superseded.
For count/order constraints, include the proposed next action when deciding.
Return only a JSON array with objects {"condition_id": string, "allowed": boolean}.
Do not solve the underlying user task."""


def _oracle_memory(episode: dict[str, Any], world: dict[str, Any]) -> str:
    active = resolve_active_directives(world["directive_events"], episode["current_context"])
    if not active:
        return "No active prior user requirements apply in the current context."
    lines = ["Oracle-active prior user requirements:"]
    for directive in active:
        lines.append(f"- {directive['text']}")
    return "\n".join(lines)


def _memory(system: str, episode: dict[str, Any], world: dict[str, Any], prefix: dict[str, Any], top_k: int) -> str:
    if system == "oracle":
        return _oracle_memory(episode, world)
    turns, _ = _past_user_turns(world)
    request = MemoryRequest(
        task_uid=episode["episode_id"],
        agent="cctu_v2_llm",
        user_prompt=_query(episode, prefix),
        past_user_turns=turns,
        task=episode,
    )
    if system == "long_context":
        return LongContextMemoryProvider().build_memory(request).memory
    if system == "bm25":
        return BM25MemoryProvider(BM25Config(top_k=top_k)).build_memory(request).memory
    raise ValueError(system)


def _conditions(system: str, episodes: list[dict[str, Any]], top_k: int) -> list[dict[str, Any]]:
    conditions: list[dict[str, Any]] = []
    for episode in episodes:
        for world in episode["worlds"]:
            for prefix in episode["trace_prefixes"]:
                condition_id = f"{episode['episode_id']}::{world['world_id']}::{prefix['prefix_id']}"
                gold_key = f"{world['world_id']}::{prefix['prefix_id']}"
                conditions.append(
                    {
                        "condition_id": condition_id,
                        "taxonomy_cell": episode["taxonomy_cell"],
                        "memory": _memory(system, episode, world, prefix, top_k),
                        "current_context": episode["current_context"],
                        "trajectory_so_far": prefix["actions"],
                        "candidate_next_action": episode["candidate_action"],
                        "gold": episode["gold_labels"][gold_key],
                    }
                )
    return conditions


def _parse_json_array(text: str) -> list[dict[str, Any]]:
    stripped = text.strip()
    fenced = re.search(r"```(?:json)?\s*(\[.*?\])\s*```", stripped, re.DOTALL)
    if fenced:
        stripped = fenced.group(1)
    else:
        start, end = stripped.find("["), stripped.rfind("]")
        if start >= 0 and end > start:
            stripped = stripped[start : end + 1]
    value = json.loads(stripped)
    if not isinstance(value, list):
        raise ValueError("Model response is not a JSON array")
    return value


async def _judge_batch(
    client: AsyncOpenAI,
    *,
    model: str,
    system: str,
    batch: list[dict[str, Any]],
    semaphore: asyncio.Semaphore,
    max_tokens: int,
) -> list[dict[str, Any]]:
    public_batch = [{key: value for key, value in row.items() if key not in {"gold", "taxonomy_cell"}} for row in batch]
    prompt = f"Memory system: {system}\n\nConditions:\n{json.dumps(public_batch, ensure_ascii=False)}"
    last_error: Exception | None = None
    async with semaphore:
        for attempt in range(3):
            try:
                response = await client.chat.completions.create(
                    model=model,
                    messages=[
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": prompt},
                    ],
                    temperature=0,
                    max_tokens=max_tokens,
                )
                message = response.choices[0].message
                content = message.content or getattr(message, "reasoning_content", None) or ""
                try:
                    parsed = _parse_json_array(content)
                except Exception as exc:
                    raise ValueError(f"Could not parse model output prefix: {content[:300]!r}") from exc
                predictions = {str(item["condition_id"]): item["allowed"] for item in parsed}
                if set(predictions) != {row["condition_id"] for row in batch}:
                    raise ValueError("Model returned missing or unexpected condition ids")
                if not all(isinstance(value, bool) for value in predictions.values()):
                    raise ValueError("All allowed predictions must be booleans")
                usage = response.usage.model_dump() if response.usage else {}
                return [
                    {
                        **row,
                        "memory": None,
                        "prediction": predictions[row["condition_id"]],
                        "correct": predictions[row["condition_id"]] == row["gold"],
                        "usage": usage if index == 0 else None,
                    }
                    for index, row in enumerate(batch)
                ]
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                await asyncio.sleep(2**attempt)
    raise RuntimeError(f"Batch failed after retries: {last_error}")


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    by_cell: dict[str, list[bool]] = defaultdict(list)
    by_episode: dict[str, list[bool]] = defaultdict(list)
    for row in rows:
        by_cell[row["taxonomy_cell"]].append(row["correct"])
        by_episode[row["condition_id"].split("::", 1)[0]].append(row["correct"])
    return {
        "condition_count": len(rows),
        "accuracy": sum(row["correct"] for row in rows) / len(rows),
        "accuracy_by_taxonomy": {cell: sum(values) / len(values) for cell, values in sorted(by_cell.items())},
        "all_conditions_correct_episode_rate": sum(all(values) for values in by_episode.values()) / len(by_episode),
    }


async def run(args: argparse.Namespace) -> dict[str, Any]:
    api_key = os.getenv(args.api_key_env)
    if not api_key:
        raise RuntimeError(f"Missing API key environment variable: {args.api_key_env}")
    payload = json.loads(args.input.read_text(encoding="utf-8"))
    if args.offset_episodes:
        payload["episodes"] = payload["episodes"][args.offset_episodes :]
    if args.limit_episodes:
        payload["episodes"] = payload["episodes"][: args.limit_episodes]
    client = AsyncOpenAI(api_key=api_key, base_url=args.base_url)
    semaphore = asyncio.Semaphore(args.max_concurrency)
    all_results: dict[str, Any] = {}
    for system in args.systems:
        conditions = _conditions(system, payload["episodes"], args.bm25_top_k)
        batches = [conditions[index : index + args.batch_size] for index in range(0, len(conditions), args.batch_size)]
        nested = await asyncio.gather(
            *[
                _judge_batch(
                    client,
                    model=args.model,
                    system=system,
                    batch=batch,
                    semaphore=semaphore,
                    max_tokens=args.max_tokens,
                )
                for batch in batches
            ]
        )
        rows = [row for batch in nested for row in batch]
        all_results[system] = {"summary": _summary(rows), "rows": rows}
    report = {
        "schema_version": "CCTUV2LLMBaselinesV1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "model": args.model,
        "base_url": args.base_url,
        "bm25_top_k": args.bm25_top_k,
        "systems": all_results,
    }
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--systems", nargs="+", choices=["oracle", "bm25", "long_context"], default=["oracle", "bm25", "long_context"])
    parser.add_argument("--bm25-top-k", type=int, default=10)
    parser.add_argument("--model", default=os.getenv("LLM_MODEL", ""))
    parser.add_argument("--base-url", default=os.getenv("LLM_BASE_URL"))
    parser.add_argument("--api-key-env", default="LLM_API_KEY")
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--max-concurrency", type=int, default=3)
    parser.add_argument("--max-tokens", type=int, default=8192)
    parser.add_argument("--limit-episodes", type=int, default=0)
    parser.add_argument("--offset-episodes", type=int, default=0)
    args = parser.parse_args()
    if not args.model:
        parser.error("Pass --model or set LLM_MODEL")
    return args


def main() -> None:
    args = parse_args()
    report = asyncio.run(run(args))
    print(json.dumps({name: value["summary"] for name, value in report["systems"].items()}, indent=2))


if __name__ == "__main__":
    main()
