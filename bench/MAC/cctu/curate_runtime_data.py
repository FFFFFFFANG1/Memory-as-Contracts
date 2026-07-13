#!/usr/bin/env python3
"""Apply the audited 184-task MAC-CCTU curation manifest in place."""

from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from bench.MAC.cctu.runtime_repairs import (
    EXCLUDED_TASK_UIDS,
    repaired_answer,
    repair_tool_schemas,
)

DATA_DIR = Path(__file__).resolve().parent / "data"


def load(name: str) -> Any:
    return json.loads((DATA_DIR / name).read_text(encoding="utf-8"))


def write(name: str, payload: Any) -> None:
    (DATA_DIR / name).write_text(
        json.dumps(payload, ensure_ascii=False, indent=4) + "\n",
        encoding="utf-8",
    )


def included(task_uid: str) -> bool:
    return task_uid not in EXCLUDED_TASK_UIDS


def curate_tasks() -> None:
    payload = load("mac-cctu-tasks.json")
    tasks = []
    for task in payload.get("tasks", []):
        uid = str(task.get("mac_task_uid") or task.get("task_uid") or "")
        if not included(uid):
            continue
        task["answer"] = repaired_answer(uid, task.get("answer"))
        tools = task.get("tools")
        if isinstance(tools, list):
            task["tools"] = repair_tool_schemas(uid, tools)
        tasks.append(task)
    payload["tasks"] = tasks
    payload.setdefault("summary", {})["task_count"] = len(tasks)
    payload["generated_at"] = datetime.now(timezone.utc).isoformat()
    write("mac-cctu-tasks.json", payload)


def curate_user_turns() -> None:
    payload = load("mac-cctu-user_turn.json")
    histories = [
        history
        for history in payload.get("task_histories", [])
        if included(str(history.get("task_uid") or ""))
    ]
    payload["task_histories"] = histories

    modes: Counter[str] = Counter()
    grounding_cache: Counter[str] = Counter()
    turn_cache: Counter[str] = Counter()
    for history in histories:
        generation = history.get("generation") or {}
        cache = generation.get("grounding_cache")
        if cache:
            grounding_cache[str(cache)] += 1
        for item in generation.get("constraint_generations") or []:
            mode = item.get("introduce_mode")
            cache = item.get("cache")
            if mode:
                modes[str(mode)] += 1
            if cache:
                turn_cache[str(cache)] += 1

    failed_uids = [
        uid
        for uid in payload.get("summary", {}).get("failed_task_uids", [])
        if included(str(uid))
    ]
    payload["summary"] = {
        "total_tasks": len(histories),
        "introduce_mode_distribution": dict(modes),
        "total_user_turns": sum(len(history.get("turns") or []) for history in histories),
        "failed_tasks": len(failed_uids),
        "failed_task_uids": failed_uids,
        "cache_distribution": {
            **dict(grounding_cache),
            **{f"turns_{key}": value for key, value in turn_cache.items()},
        },
    }
    payload["generated_at"] = datetime.now(timezone.utc).isoformat()
    write("mac-cctu-user_turn.json", payload)


def curate_tool_registry() -> None:
    payload = load("mac-cctu-tool_registry.json")
    tasks = []
    for task in payload.get("tasks", []):
        uid = str(task.get("task_uid") or "")
        if not included(uid):
            continue
        tools = task.get("tools")
        if isinstance(tools, list):
            task["tools"] = repair_tool_schemas(uid, tools)
        tasks.append(task)
    payload["tasks"] = tasks
    payload["summary"] = {
        "task_count": len(tasks),
        "total_tool_defs": sum(len(task.get("tools") or []) for task in tasks),
    }
    payload["generated_at"] = datetime.now(timezone.utc).isoformat()
    write("mac-cctu-tool_registry.json", payload)


def curate_system_prompts() -> None:
    payload = load("mac-cctu-system_prompt_constraint_free.json")
    payload = [
        item
        for item in payload
        if included(f"mac-cctu-t-{int(item['id']):05d}")
    ]
    write("mac-cctu-system_prompt_constraint_free.json", payload)


def curate_contract_graphs() -> None:
    payload = load("mac-cctu-contract_graphs.json")
    graphs = [
        graph
        for graph in payload.get("graphs", [])
        if included(str(graph.get("task_uid") or ""))
    ]
    roles = Counter(str(graph.get("anchor_role") or "unknown") for graph in graphs)
    edges = Counter(
        str(edge.get("type") or "unknown")
        for graph in graphs
        for edge in (graph.get("contract_graph") or {}).get("edges", [])
    )
    accepted = sum(bool((graph.get("validation") or {}).get("accepted")) for graph in graphs)
    payload["graphs"] = graphs
    payload["summary"] = {
        "total_graphs": len(graphs),
        "accepted_graphs": accepted,
        "rejected_graphs": len(graphs) - accepted,
        "role_distribution": dict(roles),
        "edge_distribution": dict(edges),
    }
    payload["generated_at"] = datetime.now(timezone.utc).isoformat()
    write("mac-cctu-contract_graphs.json", payload)


def curate_noise_specs() -> None:
    payload = load("mac-cctu-noise_eval_specs.json")
    units = [
        unit
        for unit in payload.get("units", [])
        if included(str(unit.get("task_uid") or ""))
    ]
    payload["units"] = units
    payload.setdefault("summary", {})["unit_count"] = len(units)
    payload["generated_at"] = datetime.now(timezone.utc).isoformat()
    write("mac-cctu-noise_eval_specs.json", payload)


def main() -> None:
    curate_tasks()
    curate_user_turns()
    curate_tool_registry()
    curate_system_prompts()
    curate_contract_graphs()
    curate_noise_specs()


if __name__ == "__main__":
    main()
