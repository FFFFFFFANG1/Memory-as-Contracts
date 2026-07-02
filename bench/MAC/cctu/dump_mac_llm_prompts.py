"""Dump the exact MAC extractor OpenAI messages for one CCTU history turn.

Usage:
  uv run python -m bench.MAC.cctu.dump_mac_llm_prompts \\
    --task-uid mac-cctu-t-00000 --extract-turn-index 0 \\
    --output bench/MAC/cctu/results/mac_llm_prompts_cctu_task0_example.txt
"""

from __future__ import annotations

import argparse
import json
from dataclasses import replace
from pathlib import Path

from bench.MAC.agent.data import build_agent_loop_input
from bench.MAC.agent.memory.base import MemoryRequest
from bench.MAC.agent.memory.mac import BenchMACAdapter, _context_for_request
from bench.MAC.cctu.bridge import MAC_CCTU_DATA_DIR, build_cctu_eval_task, build_cctu_system_config
from memory_as_contracts.extractor import (
    _system_prompt_for_context,
    _user_turn_candidate_prompt,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task-uid", default="mac-cctu-t-00000")
    parser.add_argument(
        "--extract-turn-index",
        type=int,
        default=0,
        help="Index into loop_input.past_user_turns for the exact extractor call to dump.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("bench/MAC/cctu/results/mac_llm_prompts_cctu_task0_example.txt"),
    )
    return parser.parse_args()


def count_extractor_prompt_tokens(messages: list[dict[str, str]]) -> dict[str, int]:
    import tiktoken

    encoding = tiktoken.get_encoding("cl100k_base")
    per_message = {
        message["role"]: len(encoding.encode(message["content"]))
        for message in messages
    }
    total = 3
    for message in messages:
        total += 4
        total += len(encoding.encode(message["role"]))
        total += len(encoding.encode(message["content"]))
    return {
        "system_content_tokens": per_message.get("system", 0),
        "user_content_tokens": per_message.get("user", 0),
        "total_prompt_tokens": total,
    }


def main() -> None:
    args = parse_args()
    task = build_cctu_eval_task(args.task_uid, data_dir=MAC_CCTU_DATA_DIR)
    agent_name = str(task["agent_name"])
    system_config = build_cctu_system_config()
    loop_input = build_agent_loop_input(task=task, system_config=system_config)
    host_tools = list(loop_input.tools)
    adapter = BenchMACAdapter(agent=agent_name, tools=host_tools, token_budget=1500)

    past_turns = loop_input.past_user_turns
    if not past_turns:
        raise ValueError(f"Task has no past user turns: {args.task_uid}")
    turn_index = args.extract_turn_index
    if turn_index < 0:
        turn_index = len(past_turns) + turn_index
    if turn_index < 0 or turn_index >= len(past_turns):
        raise IndexError(f"--extract-turn-index out of range: {args.extract_turn_index}")
    turn = past_turns[turn_index]
    content = str(turn.get("content") or "")

    request = MemoryRequest(
        task_uid=loop_input.task_uid,
        agent=loop_input.agent,
        user_prompt=loop_input.user_prompt,
        past_user_turns=past_turns,
        task=loop_input.task,
        agent_tools=host_tools,
        memory_llm={},
    )
    base_ctx = _context_for_request(request)
    real_turn_id = str(turn.get("turn_index", turn_index))
    extraction_ctx = adapter._extraction_context(replace(base_ctx, turn_id=real_turn_id))
    messages = [
        {"role": "system", "content": _system_prompt_for_context(extraction_ctx)},
        {"role": "user", "content": _user_turn_candidate_prompt(content, extraction_ctx)},
    ]

    token_stats = count_extractor_prompt_tokens(messages)

    output = args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(messages, ensure_ascii=False, indent=2)
    output.write_text(text + "\n", encoding="utf-8")
    print(f"Wrote {output} ({len(text)} chars, {text.count(chr(10))} lines)")
    print(
        "Prompt tokens (cl100k_base): "
        f"system={token_stats['system_content_tokens']} "
        f"user={token_stats['user_content_tokens']} "
        f"total={token_stats['total_prompt_tokens']}"
    )


if __name__ == "__main__":
    main()
