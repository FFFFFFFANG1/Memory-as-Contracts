"""MemoryArena adapter for the MAC agent loop.

Upstream env/runtime code lives under ``bench/MemoryArena/``.
MAC-owned eval task inputs live under ``bench/MAC/memoryarena/tasks/``.
"""

from __future__ import annotations

import copy
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from bench.MAC.shared.terminal_tools import append_send_message, ensure_terminal_tool_instruction
from bench.MemoryArena.env.env_systems.web_shopping_env.webshop_plus_client import (
    WEBSHOP_FUNCTION_DESCRIPTION,
)
from bench.MemoryArena.env.env_systems.web_shopping_env.runtime.runner.task_files import (
    _reconstruct_task_def_from_hf_row,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
MEMORYARENA_ROOT = REPO_ROOT / "bench" / "MemoryArena"
MAC_MEMORYARENA_DIR = REPO_ROOT / "bench" / "MAC" / "memoryarena"
MAC_MEMORYARENA_TASKS_DIR = MAC_MEMORYARENA_DIR / "tasks"
MAC_MEMORYARENA_DATA_DIR = MAC_MEMORYARENA_DIR / "data"
MAC_MEMORYARENA_RESULTS_DIR = MAC_MEMORYARENA_DIR / "results"
DEFAULT_BUNDLED_SHOPPING_PATH = MAC_MEMORYARENA_TASKS_DIR / "bundled_shopping" / "test.jsonl"
MEMORYARENA_AGENT_NAME = "memoryarena_bundled_shopping"
MEMORYARENA_CURRENT_USER_PROMPT = (
    "Use the remembered WebShop shopping task instructions to complete the live shopping task. "
    "Call the WebShop search and click tools one action at a time. "
    "When the WebShop task is complete, call send_message with a concise summary of the purchased products."
)

MEMORYARENA_SYSTEM_PROMPT = """You are a WebShop shopping agent operating through tools.

Use the available WebShop tools to interact with the live environment:
- `search` searches for products.
- `click` clicks one of the currently available page controls or product IDs.

Choose exactly one WebShop action per turn. Use product IDs when clicking product search results. Do not invent page controls; rely on the latest tool observation."""


def memoryarena_task_uid(row_id: int | str) -> str:
    return f"mac-memoryarena-bundled_shopping-{int(row_id):05d}"


def _load_jsonl_rows(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def _mac_tool_from_webshop_function(tool: dict[str, Any]) -> dict[str, Any]:
    schema = tool.get("parameters")
    if not isinstance(schema, dict):
        schema = {"type": "object", "properties": {}, "additionalProperties": True}
    return {
        "name": str(tool.get("name") or ""),
        "description": str(tool.get("description") or ""),
        "input_schema": schema,
        "runtime_family": "memoryarena_webshop",
        "host_action": "memoryarena.webshop.step",
    }


def memoryarena_webshop_tools() -> list[dict[str, Any]]:
    tools = [
        _mac_tool_from_webshop_function(tool)
        for tool in WEBSHOP_FUNCTION_DESCRIPTION
        if isinstance(tool, dict) and tool.get("name") in {"search", "click"}
    ]
    return append_send_message(tools)


def _constraint_turn_content(row: dict[str, Any]) -> str:
    task_def = _reconstruct_task_def_from_hf_row(row)
    instruction = task_def.get("agent_instruction")
    return instruction.strip() if isinstance(instruction, str) else ""


def _constraint_free_task_def(row: dict[str, Any]) -> dict[str, Any]:
    task_def = _reconstruct_task_def_from_hf_row(row)
    task_def = copy.deepcopy(task_def)
    task_def["agent_instruction"] = (
        "Use the task constraints stored in memory to choose compatible products and complete the purchase sequence."
    )
    return task_def


def build_memoryarena_eval_task(row: dict[str, Any]) -> dict[str, Any]:
    row_id = row.get("id")
    if row_id is None:
        raise ValueError("MemoryArena row is missing id")
    task_uid = memoryarena_task_uid(row_id)
    turns = [
        {
            "turn_index": 0,
            "role": "user",
            "kind": "constraint_seed",
            "content": _constraint_turn_content(row),
            "mentions_constraint": True,
        },
        {
            "turn_index": 1,
            "role": "user",
            "kind": "evaluation",
            "content": MEMORYARENA_CURRENT_USER_PROMPT,
            "mentions_constraint": False,
        },
    ]
    answers = row.get("answers") if isinstance(row.get("answers"), list) else []
    target_asins = [
        str(answer.get("target_asin"))
        for answer in answers
        if isinstance(answer, dict) and answer.get("target_asin")
    ]
    return {
        "task_uid": task_uid,
        "agent_name": MEMORYARENA_AGENT_NAME,
        "task_level": "memoryarena",
        "memoryarena_id": row_id,
        "memoryarena_category": row.get("category"),
        "memoryarena_config": "bundled_shopping",
        "task_summary": f"MemoryArena bundled shopping task {row.get('category') or row_id}",
        "constraints": [{"type": "raw_prompt", "content": turns[0]["content"]}],
        "answers": copy.deepcopy(answers),
        "target_products": target_asins,
        "raw_questions": copy.deepcopy(row.get("questions", [])),
        "memoryarena_task_def": _constraint_free_task_def(row),
        "task_chain": {
            "turns": turns,
            "turn_count": len(turns),
            "history_user_turn_count": 1,
            "actual_user_turn_count": len(turns),
        },
        "evaluation": {
            "default_turn_policy": "last_user_turn",
            "current_user_turn": turns[-1],
            "past_user_turns": turns[:-1],
            "target_products": target_asins,
        },
    }


def list_memoryarena_task_uids(
    *,
    data_path: Path | None = None,
    category: str | None = None,
) -> list[str]:
    rows = _filtered_rows(data_path=data_path, category=category)
    return [memoryarena_task_uid(row["id"]) for row in rows]


def _filtered_rows(
    *,
    data_path: Path | None = None,
    category: str | None = None,
) -> list[dict[str, Any]]:
    rows = _load_jsonl_rows(data_path or DEFAULT_BUNDLED_SHOPPING_PATH)
    if category and category != "all":
        prefix = f"{category}_item_"
        rows = [row for row in rows if str(row.get("category") or "").startswith(prefix)]
    return rows


def load_memoryarena_eval_tasks(
    *,
    data_path: Path | None = None,
    uids: list[str] | None = None,
    category: str | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rows = _filtered_rows(data_path=data_path, category=category)
    uid_filter = set(uids or [])
    tasks = [
        build_memoryarena_eval_task(row)
        for row in rows
        if not uid_filter or memoryarena_task_uid(row["id"]) in uid_filter
    ]
    return tasks, {
        "bench": "memoryarena",
        "config": "bundled_shopping",
        "task_count": len(tasks),
        "data_path": str(data_path or DEFAULT_BUNDLED_SHOPPING_PATH),
        "category": category or "all",
        "task_uids": [task["task_uid"] for task in tasks],
    }


def build_memoryarena_system_config() -> dict[str, Any]:
    system_prompt = ensure_terminal_tool_instruction(MEMORYARENA_SYSTEM_PROMPT)
    tools = memoryarena_webshop_tools()
    return {
        "schema_version": "MACSystemConfigV1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "sources": {"tasks": str(DEFAULT_BUNDLED_SHOPPING_PATH)},
        "summary": {
            "total_agents": 1,
            "agents_with_system_prompt": 1,
            "agents_with_tools": 1,
        },
        "agents": {
            MEMORYARENA_AGENT_NAME: {
                "agent": MEMORYARENA_AGENT_NAME,
                "task_count": None,
                "system_prompt": system_prompt,
                "system_prompt_length": len(system_prompt),
                "runtime_family": "memoryarena_webshop",
                "needs_react_loop": True,
                "tools": tools,
            }
        },
    }
