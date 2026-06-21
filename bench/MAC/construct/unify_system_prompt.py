#!/usr/bin/env python3
"""Unify cleaned system prompts at the agent level.

This script builds one canonical cleaned system prompt per agent:
1. Read each agent's original unique system prompt from AgentIF raw data.
2. Collect the union of selected constraints for that agent from the step-1
   filtered task file.
3. Reuse prompt_filter's cleaning logic to remove those constraints from the
   original system prompt.
4. Replace every task for that agent with the same canonical cleaned system
   prompt.

By default the unified dataset is written to a new file so existing artifacts are
not overwritten accidentally.
"""

from __future__ import annotations

import argparse
import copy
import os
import threading
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from prompt_filter import (
    clean_message,
    constraint_descs,
    load_cache,
    load_env,
    load_json,
    resolve_path,
    sha256_text,
    write_json,
)


DEFAULT_INPUT = Path("bench/MAC/mid_data/eval_step1_constraint_filtered.json")
DEFAULT_OUTPUT = Path("bench/MAC/mid_data/eval_step1_constraint_filtered.unified_system.json")
DEFAULT_RAW_INPUT = Path("bench/MAC/data/agentif_raw_data.json")
DEFAULT_PROMPT_LIB = Path("bench/MAC/mid_data/prompt_filter_lib.json")


def first_system_index(task: dict[str, Any]) -> int | None:
    messages = task.get("input", [])
    if not isinstance(messages, list):
        return None
    for index, message in enumerate(messages):
        if not isinstance(message, dict):
            continue
        if message.get("role") == "system" and isinstance(message.get("content"), str):
            return index
    return None


def first_system_prompt(task: dict[str, Any]) -> str:
    index = first_system_index(task)
    if index is None:
        return ""
    messages = task.get("input", [])
    content = messages[index].get("content")
    return content.strip() if isinstance(content, str) else ""


def agent_name(task: dict[str, Any]) -> str:
    value = task.get("agent_name")
    return value.strip() if isinstance(value, str) else ""


def dedupe_constraints(items: list[dict[str, str]]) -> list[dict[str, str]]:
    by_desc: dict[str, dict[str, str]] = {}
    for item in items:
        desc = item.get("desc", "").strip()
        if not desc or desc in by_desc:
            continue
        by_desc[desc] = {
            "constraint_uid": item.get("constraint_uid", f"agent-constraint-{len(by_desc) + 1}"),
            "desc": desc,
        }
    return sorted(by_desc.values(), key=lambda item: item["desc"])


def raw_system_prompts_by_agent(raw_tasks: list[Any]) -> dict[str, set[str]]:
    prompts: dict[str, set[str]] = defaultdict(set)
    for task in raw_tasks:
        if not isinstance(task, dict):
            continue
        agent = agent_name(task)
        if not agent:
            continue
        prompt = first_system_prompt(task)
        if prompt:
            prompts[agent].add(prompt)
        else:
            prompts.setdefault(agent, set())
    return prompts


def selected_constraints_by_agent(tasks: list[Any]) -> dict[str, list[dict[str, str]]]:
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for task in tasks:
        if not isinstance(task, dict):
            continue
        agent = agent_name(task)
        if not agent:
            continue
        grouped[agent].extend(constraint_descs(task))
    return {agent: dedupe_constraints(items) for agent, items in grouped.items()}


def current_prompt_versions_by_agent(tasks: list[Any]) -> dict[str, Counter[str]]:
    versions: dict[str, Counter[str]] = defaultdict(Counter)
    for task in tasks:
        if not isinstance(task, dict):
            continue
        agent = agent_name(task)
        if not agent:
            continue
        versions[agent][first_system_prompt(task)] += 1
    return versions


def clean_agent_prompt(
    *,
    agent: str,
    raw_prompt: str,
    constraints: list[dict[str, str]],
    cache: dict[str, Any],
    cache_lock: threading.Lock,
    key_locks: dict[str, threading.Lock],
    key_locks_lock: threading.Lock,
    args: argparse.Namespace,
) -> tuple[str, str]:
    cleaned_message, status = clean_message(
        message={"role": "system", "content": raw_prompt},
        task_uid=f"agent:{agent}",
        message_index=0,
        constraints=constraints,
        cache=cache,
        cache_lock=cache_lock,
        key_locks=key_locks,
        key_locks_lock=key_locks_lock,
        model=args.model,
        base_url=args.base_url,
        api_key=args.api_key,
        max_tokens=args.max_tokens,
        timeout=args.timeout,
        retries=args.retries,
        sleep=args.sleep,
    )
    content = cleaned_message.get("content", "")
    if not isinstance(content, str):
        raise ValueError(f"prompt_filter returned non-string system content for agent={agent!r}")
    return content.strip(), status


def apply_canonical_prompts(
    tasks: list[Any],
    canonical_by_agent: dict[str, str],
    *,
    insert_missing: bool,
) -> tuple[list[Any], Counter[str]]:
    output: list[Any] = []
    stats: Counter[str] = Counter()

    for task in tasks:
        if not isinstance(task, dict):
            output.append(copy.deepcopy(task))
            stats["non_object"] += 1
            continue

        agent = agent_name(task)
        canonical = canonical_by_agent.get(agent)
        if not canonical:
            output.append(copy.deepcopy(task))
            stats["no_canonical"] += 1
            continue

        updated = copy.deepcopy(task)
        messages = updated.get("input", [])
        if not isinstance(messages, list):
            output.append(updated)
            stats["no_input_list"] += 1
            continue

        index = first_system_index(updated)
        if index is None:
            if insert_missing:
                messages.insert(0, {"role": "system", "content": canonical})
                stats["inserted_missing"] += 1
            else:
                stats["missing_system_skipped"] += 1
            output.append(updated)
            continue

        old_prompt = first_system_prompt(updated)
        messages[index]["content"] = canonical
        stats["updated" if old_prompt != canonical else "unchanged"] += 1
        output.append(updated)

    return output, stats


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT, help="Step-1 filtered task dataset.")
    parser.add_argument("--raw-input", type=Path, default=DEFAULT_RAW_INPUT, help="AgentIF raw task dataset.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="Unified output dataset.")
    parser.add_argument("--prompt-lib", type=Path, default=DEFAULT_PROMPT_LIB, help="Prompt filter cache/library.")
    parser.add_argument("--env-file", type=Path, default=None, help="Optional .env file.")
    parser.add_argument(
        "--model",
        default=os.getenv("MAC_LLM_MODEL"),
        help="OpenAI-compatible model name. Defaults to MAC_LLM_MODEL.",
    )
    parser.add_argument(
        "--base-url",
        default=os.getenv("OPENAI_BASE_URL") or os.getenv("MAC_LLM_BASE_URL"),
        help="OpenAI-compatible base URL. Defaults to OPENAI_BASE_URL or MAC_LLM_BASE_URL.",
    )
    parser.add_argument("--api-key", default=os.getenv("OPENAI_API_KEY"), help="Defaults to OPENAI_API_KEY.")
    parser.add_argument("--max-tokens", type=int, default=4096)
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument("--retries", type=int, default=3)
    parser.add_argument("--sleep", type=float, default=2.0)
    parser.add_argument(
        "--only-agent",
        action="append",
        default=[],
        help="Unify only this agent_name. Can be repeated.",
    )
    parser.add_argument(
        "--raw-multiple",
        choices=("error", "skip"),
        default="error",
        help="What to do if an input agent has multiple non-empty raw system prompts.",
    )
    parser.add_argument(
        "--insert-missing",
        action="store_true",
        help="Insert the canonical system prompt when an input task has no system message.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report which agents would be unified without calling the LLM or writing output.",
    )
    return parser.parse_args()


def preparse_env_file() -> Path | None:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--env-file", type=Path, default=None)
    args, _ = parser.parse_known_args()
    return args.env_file


def main() -> int:
    load_env(preparse_env_file())
    args = parse_args()

    input_path = resolve_path(args.input)
    raw_input_path = resolve_path(args.raw_input)
    output_path = resolve_path(args.output)
    prompt_lib_path = resolve_path(args.prompt_lib)

    tasks = load_json(input_path)
    raw_tasks = load_json(raw_input_path)
    if not isinstance(tasks, list):
        raise ValueError(f"Expected top-level JSON array in {input_path}")
    if not isinstance(raw_tasks, list):
        raise ValueError(f"Expected top-level JSON array in {raw_input_path}")

    only_agents = set(args.only_agent)
    constraints_by_agent = selected_constraints_by_agent(tasks)
    raw_prompts = raw_system_prompts_by_agent(raw_tasks)
    current_versions = current_prompt_versions_by_agent(tasks)
    input_agents = sorted(agent for agent in constraints_by_agent if not only_agents or agent in only_agents)

    skipped: Counter[str] = Counter()
    candidate_agents: list[str] = []
    for agent in input_agents:
        non_empty_raw = sorted(raw_prompts.get(agent, set()))
        if not non_empty_raw:
            skipped["no_raw_system_prompt"] += 1
            continue
        if len(non_empty_raw) > 1:
            if args.raw_multiple == "error":
                raise ValueError(f"Agent {agent!r} has {len(non_empty_raw)} raw system prompts")
            skipped["multiple_raw_system_prompts"] += 1
            continue
        if not constraints_by_agent.get(agent):
            skipped["no_constraints"] += 1
            continue
        candidate_agents.append(agent)

    print(
        f"input_tasks={len(tasks)} agents={len(current_versions)} candidates={len(candidate_agents)} "
        f"skipped={dict(skipped)}"
    )
    for agent in candidate_agents:
        task_count = sum(current_versions[agent].values())
        non_empty_current = [prompt for prompt in current_versions[agent] if prompt]
        print(
            f"agent={agent!r} tasks={task_count} current_versions={len(non_empty_current)} "
            f"constraints={len(constraints_by_agent[agent])}"
        )

    if args.dry_run:
        return 0

    cache = load_cache(prompt_lib_path)
    cache_lock = threading.Lock()
    key_locks: dict[str, threading.Lock] = {}
    key_locks_lock = threading.Lock()

    canonical_by_agent: dict[str, str] = {}
    clean_statuses: Counter[str] = Counter()
    for index, agent in enumerate(candidate_agents, start=1):
        raw_prompt = next(iter(raw_prompts[agent]))
        canonical, status = clean_agent_prompt(
            agent=agent,
            raw_prompt=raw_prompt,
            constraints=constraints_by_agent[agent],
            cache=cache,
            cache_lock=cache_lock,
            key_locks=key_locks,
            key_locks_lock=key_locks_lock,
            args=args,
        )
        canonical_by_agent[agent] = canonical
        clean_statuses[status] += 1
        print(
            f"[{index}/{len(candidate_agents)}] agent={agent!r} clean={status} "
            f"raw_len={len(raw_prompt)} canonical_len={len(canonical)} "
            f"canonical_hash={sha256_text(canonical)[:12]}"
        )

    with cache_lock:
        write_json(prompt_lib_path, cache)

    output_tasks, apply_stats = apply_canonical_prompts(
        tasks,
        canonical_by_agent,
        insert_missing=args.insert_missing,
    )
    write_json(output_path, output_tasks)
    print(
        f"wrote {len(output_tasks)} tasks to {output_path}; "
        f"clean_statuses={dict(clean_statuses)} apply_stats={dict(apply_stats)} "
        f"prompt_lib={prompt_lib_path}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
