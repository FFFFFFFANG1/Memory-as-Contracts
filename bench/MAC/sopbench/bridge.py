"""SOPBench adapter for the MAC agent loop."""

from __future__ import annotations

import copy
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from bench.MAC.shared.terminal_tools import append_send_message, ensure_terminal_tool_instruction, send_message_tool

REPO_ROOT = Path(__file__).resolve().parents[3]
MAC_SOPBENCH_DIR = REPO_ROOT / "bench" / "MAC" / "sopbench"
MAC_SOPBENCH_DATA_DIR = MAC_SOPBENCH_DIR / "data"
MAC_SOPBENCH_MID_DATA_DIR = MAC_SOPBENCH_DIR / "mid_data"
MAC_SOPBENCH_RESULTS_DIR = MAC_SOPBENCH_DIR / "results"
SOPBENCH_ROOT = REPO_ROOT / "bench" / "SOPBench"

MAC_SOPBENCH_TASKS_FILE = "mac-sopbench-tasks.json"
MAC_SOPBENCH_USER_TURN_FILE = "mac-sopbench-user_turn.json"
MAC_SOPBENCH_TOOL_REGISTRY_FILE = "mac-sopbench-tool_registry.json"
MAC_SOPBENCH_NOISE_MANIFEST_FILE = "mac-sopbench-noise_eval_specs.json"
MAC_SOPBENCH_TEMPORAL_SEQUENCES_FILE = "mac-sopbench-temporal_sequences.json"


def sopbench_root() -> Path:
    if (SOPBENCH_ROOT / "run_simulation.py").exists():
        return SOPBENCH_ROOT
    raise FileNotFoundError(f"Could not locate SOPBench source tree: {SOPBENCH_ROOT}")


def mac_sopbench_data_dir() -> Path:
    return MAC_SOPBENCH_DATA_DIR


def mac_sopbench_tasks_path(data_dir: Path | None = None) -> Path:
    return (data_dir or mac_sopbench_data_dir()) / MAC_SOPBENCH_TASKS_FILE


def mac_sopbench_user_turn_path(data_dir: Path | None = None) -> Path:
    return (data_dir or mac_sopbench_data_dir()) / MAC_SOPBENCH_USER_TURN_FILE


def mac_sopbench_tool_registry_path(data_dir: Path | None = None) -> Path:
    return (data_dir or mac_sopbench_data_dir()) / MAC_SOPBENCH_TOOL_REGISTRY_FILE


def mac_sopbench_noise_manifest_path(data_dir: Path | None = None) -> Path:
    return (data_dir or mac_sopbench_data_dir()) / MAC_SOPBENCH_NOISE_MANIFEST_FILE


def mac_sopbench_temporal_sequences_path(data_dir: Path | None = None) -> Path:
    return (data_dir or mac_sopbench_data_dir()) / MAC_SOPBENCH_TEMPORAL_SEQUENCES_FILE


def load_json_file(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def load_sopbench_mac_tasks(data_dir: Path | None = None) -> dict[str, Any]:
    payload = load_json_file(mac_sopbench_tasks_path(data_dir))
    if not isinstance(payload, dict):
        raise TypeError("mac-sopbench-tasks.json must contain a JSON object")
    return payload


def load_sopbench_user_turns(data_dir: Path | None = None) -> dict[str, Any]:
    payload = load_json_file(mac_sopbench_user_turn_path(data_dir))
    if not isinstance(payload, dict):
        raise TypeError("mac-sopbench-user_turn.json must contain a JSON object")
    return payload


def load_sopbench_tool_registry(data_dir: Path | None = None) -> dict[str, Any]:
    payload = load_json_file(mac_sopbench_tool_registry_path(data_dir))
    if not isinstance(payload, dict):
        raise TypeError("mac-sopbench-tool_registry.json must contain a JSON object")
    return payload


def load_sopbench_noise_manifest(data_dir: Path | None = None) -> dict[str, Any]:
    payload = load_json_file(mac_sopbench_noise_manifest_path(data_dir))
    if not isinstance(payload, dict):
        raise TypeError("mac-sopbench-noise_eval_specs.json must contain a JSON object")
    return payload


def openai_tool_schema_to_mac(tool: dict[str, Any]) -> dict[str, Any]:
    fn = tool.get("function") if tool.get("type") == "function" else tool
    if not isinstance(fn, dict):
        raise TypeError("tool schema must contain a function object")
    name = fn.get("name")
    if not isinstance(name, str) or not name:
        raise ValueError("tool schema is missing function.name")
    schema = fn.get("parameters")
    if not isinstance(schema, dict):
        schema = {"type": "object", "properties": {}, "additionalProperties": True}
    runtime_family = "terminal" if name == "send_message" else "sopbench_strict"
    host_action = "final.respond" if name == "send_message" else "sopbench.tool.execute"
    return {
        "name": name,
        "description": str(fn.get("description") or ""),
        "input_schema": schema,
        "runtime_family": runtime_family,
        "host_action": host_action,
    }


def mac_tools_from_openai_schemas(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [openai_tool_schema_to_mac(tool) for tool in tools if isinstance(tool, dict)]


def index_sopbench_tasks(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    indexed: dict[str, dict[str, Any]] = {}
    for task in payload.get("tasks", []):
        if not isinstance(task, dict):
            continue
        uid = str(task.get("task_uid") or task.get("mac_task_uid") or "")
        if uid:
            indexed[uid] = task
    return indexed


def index_sopbench_user_histories(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    indexed: dict[str, dict[str, Any]] = {}
    for history in payload.get("task_histories", []):
        if not isinstance(history, dict):
            continue
        uid = str(history.get("task_uid") or "")
        if uid:
            indexed[uid] = history
    return indexed


def index_sopbench_tool_registry(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    indexed: dict[str, dict[str, Any]] = {}
    for entry in payload.get("tasks", []):
        if not isinstance(entry, dict):
            continue
        uid = str(entry.get("task_uid") or "")
        if uid:
            indexed[uid] = entry
    return indexed


def system_prompt_from_task_record(task: dict[str, Any], *, ensure_terminal_instruction: bool = True) -> str:
    prompt = ""
    messages = task.get("input", [])
    if isinstance(messages, list):
        for message in messages:
            if isinstance(message, dict) and message.get("role") == "system":
                content = message.get("content")
                if isinstance(content, str) and content.strip():
                    prompt = content.strip()
                    break
    if not prompt:
        prompt = str(task.get("system_prompt") or "").strip()
    if ensure_terminal_instruction:
        prompt = ensure_terminal_tool_instruction(prompt)
    return prompt


def build_sopbench_system_config(
    *,
    data_dir: Path | None = None,
    ensure_terminal_instruction: bool = True,
) -> dict[str, Any]:
    tasks_payload = load_sopbench_mac_tasks(data_dir)
    registry_payload = load_sopbench_tool_registry(data_dir)
    tasks_by_uid = index_sopbench_tasks(tasks_payload)
    registry_by_uid = index_sopbench_tool_registry(registry_payload)

    agents: dict[str, dict[str, Any]] = {}
    for task_uid, task in sorted(tasks_by_uid.items()):
        agent = str(task.get("agent_name") or "")
        registry_entry = registry_by_uid.get(task_uid, {})
        tools_raw = registry_entry.get("tools", [])
        if isinstance(tools_raw, list) and tools_raw:
            tools = tools_raw
        else:
            tools = append_send_message(mac_tools_from_openai_schemas(task.get("tools") or []))
        system_prompt = system_prompt_from_task_record(
            task,
            ensure_terminal_instruction=ensure_terminal_instruction,
        )
        agents[agent] = {
            "agent": agent,
            "task_count": 1,
            "task_uids": [task_uid],
            "system_prompt": system_prompt,
            "system_prompt_length": len(system_prompt),
            "runtime_family": "sopbench_tool_use",
            "needs_react_loop": True,
            "tools": tools,
            "domain": task.get("domain"),
            "user_goal": task.get("user_goal"),
        }

    return {
        "schema_version": "MACSystemConfigV1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "sources": {
            "tasks": str(mac_sopbench_tasks_path(data_dir)),
            "tool_registry": str(mac_sopbench_tool_registry_path(data_dir)),
        },
        "summary": {
            "total_agents": len(agents),
            "agents_with_system_prompt": len(agents),
            "agents_with_tools": len(agents),
        },
        "send_message_tool": send_message_tool(),
        "agents": agents,
    }


def build_sopbench_eval_task(
    task_uid: str,
    *,
    data_dir: Path | None = None,
) -> dict[str, Any]:
    """Build one agent-loop task record from exported SOPBench MAC artifacts."""
    tasks_by_uid = index_sopbench_tasks(load_sopbench_mac_tasks(data_dir))
    histories_by_uid = index_sopbench_user_histories(load_sopbench_user_turns(data_dir))
    if task_uid not in tasks_by_uid:
        raise KeyError(f"Unknown SOPBench task uid: {task_uid}")
    if task_uid not in histories_by_uid:
        raise KeyError(f"Missing user-turn history for task uid: {task_uid}")

    task_meta = tasks_by_uid[task_uid]
    history = histories_by_uid[task_uid]
    turns = [copy.deepcopy(turn) for turn in history.get("turns", []) if isinstance(turn, dict)]

    return {
        "task_uid": task_uid,
        "agent_name": task_meta.get("agent_name"),
        "domain": task_meta.get("domain"),
        "user_goal": task_meta.get("user_goal"),
        "task_summary": task_meta.get("mac_task_summary"),
        "input": copy.deepcopy(task_meta.get("input", [])),
        "original_sopbench": copy.deepcopy(task_meta.get("original_sopbench") or {}),
        "patched_sopbench_task": copy.deepcopy(task_meta.get("patched_sopbench_task") or {}),
        "constraints": copy.deepcopy(task_meta.get("constraints") or []),
        "tools": copy.deepcopy(task_meta.get("tools") or []),
        "sequence_turn_count": task_meta.get("sequence_turn_count"),
        "task_chain": {
            "turns": turns,
            "turn_count": len(turns),
            "history_user_turn_count": history.get("history_user_turn_count", max(len(turns) - 1, 0)),
            "actual_user_turn_count": history.get("actual_user_turn_count", len(turns)),
            "warmup_turn_count": history.get("warmup_turn_count"),
            "normal_turn_count": history.get("normal_turn_count"),
            "delta_turn_count": history.get("delta_turn_count"),
        },
        "evaluation": {
            "default_turn_policy": "last_user_turn",
            "current_user_turn": turns[-1] if turns else None,
            "past_user_turns": turns[:-1] if turns else [],
        },
    }


def list_sopbench_task_uids(*, data_dir: Path | None = None) -> list[str]:
    return sorted(index_sopbench_tasks(load_sopbench_mac_tasks(data_dir)).keys())


def load_sopbench_eval_tasks(
    *,
    data_dir: Path | None = None,
    uids: list[str] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Load exported SOPBench tasks in agent-loop shape."""
    selected_uids = uids or list_sopbench_task_uids(data_dir=data_dir)
    tasks = [build_sopbench_eval_task(uid, data_dir=data_dir) for uid in selected_uids]
    return tasks, {
        "bench": "sopbench",
        "task_count": len(tasks),
        "task_uids": selected_uids,
        "data_dir": str(data_dir or mac_sopbench_data_dir()),
        "noise_manifest": str(mac_sopbench_noise_manifest_path(data_dir)),
    }
