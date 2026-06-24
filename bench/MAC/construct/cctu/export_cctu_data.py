#!/usr/bin/env python3
"""Export finalized CCTU benchmark artifacts from MAC mid_data into bench/MAC/cctu/data/."""

from __future__ import annotations

import argparse
import copy
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[4]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from bench.MAC.cctu.bridge import cctu_samples_by_id, send_message_tool  # noqa: E402

DEFAULT_STEP1 = Path("bench/MAC/cctu/mid_data/eval_step1_cctu.json")
DEFAULT_STEP3 = Path("bench/MAC/cctu/mid_data/eval_step3_base.validated.json")
DEFAULT_STEP4 = Path("bench/MAC/cctu/mid_data/eval_step4_task_histories.json")
DEFAULT_OUTPUT_DIR = Path("bench/MAC/cctu/data")


def resolve_path(path: Path) -> Path:
    return path if path.is_absolute() else REPO_ROOT / path


def load_json(path: Path) -> Any:
    return json.loads(resolve_path(path).read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    target = resolve_path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, indent=4, ensure_ascii=False) + "\n", encoding="utf-8")


def drop_keys(value: dict[str, Any], *keys: str) -> dict[str, Any]:
    out = copy.deepcopy(value)
    for key in keys:
        out.pop(key, None)
    return out


def export_user_turns(step4: dict[str, Any]) -> dict[str, Any]:
    summary = drop_keys(
        copy.deepcopy(step4.get("summary") or {}),
        "task_level_distribution",
        "history_length_distribution",
    )
    task_histories: list[dict[str, Any]] = []
    for history in step4.get("task_histories") or []:
        if not isinstance(history, dict):
            continue
        task_histories.append(drop_keys(copy.deepcopy(history), "task_level", "preference_count"))

    return {
        "schema_version": "MACCCTUUserTurnV1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "sources": {
            "task_histories": str(DEFAULT_STEP4),
        },
        "source_input": step4.get("source_input"),
        "task_input": step4.get("task_input"),
        "summary": summary,
        "task_histories": task_histories,
    }


def export_tasks(step1: list[dict[str, Any]]) -> dict[str, Any]:
    tasks: list[dict[str, Any]] = []
    for item in step1:
        if not isinstance(item, dict):
            continue
        record = drop_keys(copy.deepcopy(item), "task_level")
        tasks.append(record)
    return {
        "schema_version": "MACCCTUTaskV1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": str(DEFAULT_STEP1),
        "summary": {"task_count": len(tasks)},
        "tasks": tasks,
    }


def export_contract_graphs(step3: dict[str, Any]) -> dict[str, Any]:
    graphs: list[dict[str, Any]] = []
    for graph in step3.get("graphs") or []:
        if not isinstance(graph, dict):
            continue
        graphs.append(drop_keys(copy.deepcopy(graph), "task_level"))

    summary = copy.deepcopy(step3.get("summary") or {})
    return {
        "schema_version": "MACCCTUContractGraphV1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": str(DEFAULT_STEP3),
        "summary": summary,
        "graphs": graphs,
    }


def send_message_tool_schema() -> dict[str, Any]:
    tool = send_message_tool()
    return {
        "type": "function",
        "function": {
            "name": tool["name"],
            "description": tool["description"],
            "parameters": copy.deepcopy(tool["input_schema"]),
        },
    }


def append_send_message_schema(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    filtered = [
        tool
        for tool in tools
        if not (
            isinstance(tool, dict)
            and isinstance(tool.get("function"), dict)
            and tool["function"].get("name") == "send_message"
        )
    ]
    return [*filtered, send_message_tool_schema()]


def load_agent_tool_schemas(sample: dict[str, Any]) -> list[dict[str, Any]]:
    """Return the OpenAI-style tool schemas originally provided to the agent."""
    tools_raw = sample.get("tools", "[]")
    tools = json.loads(tools_raw) if isinstance(tools_raw, str) else tools_raw
    if not isinstance(tools, list):
        return []
    return [copy.deepcopy(item) for item in tools if isinstance(item, dict)]


def export_tool_registry(
    step1: list[dict[str, Any]],
    *,
    cctu_samples: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    tasks: list[dict[str, Any]] = []
    for item in step1:
        if not isinstance(item, dict):
            continue
        task_uid = str(item.get("mac_task_uid") or item.get("task_uid") or "")
        cctu_id = str(item.get("cctu_id") or item.get("id") or "")
        sample = cctu_samples.get(cctu_id, {})
        tools = append_send_message_schema(load_agent_tool_schemas(sample))
        tasks.append(
            {
                "task_uid": task_uid,
                "agent_name": item.get("agent_name"),
                "tools": tools,
            }
        )

    return {
        "schema_version": "MACCCTUToolRegistryV1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": "bench/CCTU/data/input_data.jsonl",
        "summary": {
            "task_count": len(tasks),
            "total_tool_defs": sum(len(task.get("tools") or []) for task in tasks),
        },
        "tasks": tasks,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--step1", type=Path, default=DEFAULT_STEP1)
    parser.add_argument("--step3", type=Path, default=DEFAULT_STEP3)
    parser.add_argument("--step4", type=Path, default=DEFAULT_STEP4)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output_dir = resolve_path(args.output_dir)

    step1 = load_json(args.step1)
    step3 = load_json(args.step3)
    step4 = load_json(args.step4)
    cctu_samples = cctu_samples_by_id(resolve_path(Path("bench/CCTU/data/input_data.jsonl")))

    outputs = {
        "mac-cctu-user_turn.json": export_user_turns(step4),
        "mac-cctu-tasks.json": export_tasks(step1),
        "mac-cctu-contract_graphs.json": export_contract_graphs(step3),
        "tool_registry.json": export_tool_registry(step1, cctu_samples=cctu_samples),
    }

    for name, payload in outputs.items():
        path = output_dir / name
        write_json(path, payload)
        print(f"wrote {path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
