"""Build MAC runtime data files for SOPBench temporal memory evaluation."""

from __future__ import annotations

import argparse
import copy
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from bench.MAC.shared.terminal_tools import append_send_message, send_message_tool

DEFAULT_OUTPUT_DIR = REPO_ROOT / "bench" / "MAC" / "sopbench" / "data"
DEFAULT_STEP2 = REPO_ROOT / "bench" / "MAC" / "sopbench" / "mid_data" / "eval_step2_anchors.json"
DEFAULT_STEP4 = REPO_ROOT / "bench" / "MAC" / "sopbench" / "mid_data" / "eval_step4_temporal_sequence_v3.json"
DEFAULT_STEP5_HISTORIES = REPO_ROOT / "bench" / "MAC" / "sopbench" / "mid_data" / "eval_step5_task_histories.json"
DEFAULT_NOISE_MANIFEST = REPO_ROOT / "bench" / "MAC" / "sopbench" / "mid_data" / "eval_step5_noise_eval_specs.json"

MAC_SOPBENCH_TASKS_FILE = "mac-sopbench-tasks.json"
MAC_SOPBENCH_USER_TURN_FILE = "mac-sopbench-user_turn.json"
MAC_SOPBENCH_TOOL_REGISTRY_FILE = "mac-sopbench-tool_registry.json"
MAC_SOPBENCH_NOISE_MANIFEST_FILE = "mac-sopbench-noise_eval_specs.json"
MAC_SOPBENCH_TEMPORAL_SEQUENCES_FILE = "mac-sopbench-temporal_sequences.json"

# Runtime contract-follow grading only replays action deps + fallback graphs.
RUNTIME_TEMPORAL_STEP_FIELDS = (
    "sequence_order",
    "action",
    "dependency",
    "user_goal_action_graph",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--step2", type=Path, default=DEFAULT_STEP2)
    parser.add_argument("--step4", type=Path, default=DEFAULT_STEP4)
    parser.add_argument("--step5-histories", type=Path, default=DEFAULT_STEP5_HISTORIES)
    parser.add_argument("--noise-manifest", type=Path, default=DEFAULT_NOISE_MANIFEST)
    parser.add_argument("--limit", type=int, default=0, help="Maximum tasks to export; 0 means all.")
    parser.add_argument("--offset", type=int, default=0)
    return parser.parse_args()


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=4, ensure_ascii=False) + "\n", encoding="utf-8")


def write_json_compact(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")


def slim_temporal_step(step: dict[str, Any]) -> dict[str, Any]:
    return {
        key: copy.deepcopy(step[key])
        for key in RUNTIME_TEMPORAL_STEP_FIELDS
        if key in step
    }


def slim_temporal_sequence(sequence: list[Any]) -> list[dict[str, Any]]:
    return [
        slim_temporal_step(step)
        for step in sequence
        if isinstance(step, dict)
    ]


def index_by_uid(payload: Any, *, uid_key: str = "mac_task_uid") -> dict[str, dict[str, Any]]:
    if isinstance(payload, dict):
        rows = payload.get("tasks") or payload.get("task_histories") or []
    elif isinstance(payload, list):
        rows = payload
    else:
        raise TypeError("payload must be a list or object with tasks/task_histories")
    return {
        str(row.get(uid_key) or row.get("task_uid") or ""): row
        for row in rows
        if isinstance(row, dict) and (row.get(uid_key) or row.get("task_uid"))
    }


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


def user_turns_from_history(history: dict[str, Any]) -> list[dict[str, Any]]:
    turns: list[dict[str, Any]] = []
    for turn in history.get("turns") or []:
        if not isinstance(turn, dict) or turn.get("role") != "user":
            continue
        content = turn.get("content")
        if not isinstance(content, str) or not content.strip():
            continue
        turns.append(
            {
                "role": "user",
                "content": content,
                "phase": turn.get("phase"),
                "kind": turn.get("kind"),
                "turn_index": turn.get("turn_index"),
                "constraint_uids": copy.deepcopy(turn.get("constraint_uids") or []),
            }
        )
    return turns


def build_task_record(
    step2_task: dict[str, Any],
    *,
    task_spec: dict[str, Any] | None,
) -> dict[str, Any]:
    task_uid = str(step2_task.get("mac_task_uid") or "")
    patched = copy.deepcopy((task_spec or {}).get("patched_sopbench_task") or {})
    return {
        "mac_task_uid": task_uid,
        "task_uid": task_uid,
        "agent_name": step2_task.get("agent_name"),
        "domain": step2_task.get("domain"),
        "user_goal": step2_task.get("user_goal"),
        "task_index": step2_task.get("task_index"),
        "source_file": step2_task.get("source_file"),
        "mac_task_summary": step2_task.get("mac_task_summary"),
        "system_prompt_domain_id": step2_task.get("system_prompt_domain_id"),
        "system_prompt": step2_task.get("system_prompt"),
        "sop_text": step2_task.get("sop_text"),
        "input": copy.deepcopy(step2_task.get("input") or []),
        "original_sopbench": copy.deepcopy(step2_task.get("original_sopbench") or {}),
        "patched_sopbench_task": patched,
        "constraints": copy.deepcopy(step2_task.get("constraints") or []),
        "tools": copy.deepcopy(step2_task.get("tools") or []),
        "sequence_turn_count": (task_spec or {}).get("sequence_turn_count"),
    }


def build_history_record(history: dict[str, Any]) -> dict[str, Any]:
    task_uid = str(history.get("mac_task_uid") or history.get("task_uid") or "")
    turns = user_turns_from_history(history)
    return {
        "task_uid": task_uid,
        "agent_name": history.get("agent_name"),
        "domain": history.get("domain"),
        "user_goal": history.get("user_goal"),
        "warmup_turn_count": history.get("warmup_turn_count"),
        "normal_turn_count": history.get("normal_turn_count"),
        "delta_turn_count": history.get("delta_turn_count"),
        "expected_normal_turn_count": history.get("expected_normal_turn_count"),
        "evaluation_user_turn_count": history.get("evaluation_user_turn_count"),
        "history_user_turn_count": max(len(turns) - 1, 0),
        "actual_user_turn_count": len(turns),
        "turns": turns,
        "generation": copy.deepcopy(history.get("generation") or {}),
    }


def main() -> None:
    args = parse_args()
    step2_by_uid = index_by_uid(load_json(args.step2))
    step4_payload = load_json(args.step4)
    step4_rows = step4_payload.get("tasks") if isinstance(step4_payload, dict) else step4_payload
    step4_by_uid = index_by_uid(step4_rows if isinstance(step4_rows, list) else [])
    histories_by_uid = index_by_uid(load_json(args.step5_histories))
    manifest = load_json(args.noise_manifest)
    task_specs = manifest.get("task_specs") if isinstance(manifest, dict) else {}
    if not isinstance(task_specs, dict):
        raise TypeError("noise manifest must contain task_specs object")

    selected_uids = sorted(step2_by_uid)
    start = max(0, args.offset)
    if args.limit and args.limit > 0:
        selected_uids = selected_uids[start : start + args.limit]
    else:
        selected_uids = selected_uids[start:]

    tasks: list[dict[str, Any]] = []
    histories: list[dict[str, Any]] = []
    registry_tasks: list[dict[str, Any]] = []
    temporal_sequences: list[dict[str, Any]] = []
    missing_histories: list[str] = []
    missing_specs: list[str] = []

    for uid in selected_uids:
        step2_task = step2_by_uid[uid]
        history = histories_by_uid.get(uid)
        task_spec = task_specs.get(uid)
        if history is None:
            missing_histories.append(uid)
            continue
        if task_spec is None:
            missing_specs.append(uid)

        task = build_task_record(step2_task, task_spec=task_spec if isinstance(task_spec, dict) else None)
        tasks.append(task)

        history_record = build_history_record(history)
        histories.append(history_record)

        mac_tools = append_send_message(mac_tools_from_openai_schemas(task.get("tools") or []))
        registry_tasks.append(
            {
                "task_uid": uid,
                "agent_name": task.get("agent_name"),
                "domain": task.get("domain"),
                "user_goal": task.get("user_goal"),
                "tools": mac_tools,
            }
        )
        step4_task = step4_by_uid.get(uid)
        if step4_task is not None:
            temporal_sequences.append(
                {
                    "mac_task_uid": uid,
                    "task_uid": uid,
                    "temporal_sequence": slim_temporal_sequence(step4_task.get("temporal_sequence") or []),
                }
            )

    now = datetime.now(timezone.utc).isoformat()
    output_dir = args.output_dir
    write_json(
        output_dir / MAC_SOPBENCH_TASKS_FILE,
        {
            "schema_version": "MACSOPBenchTasksV1",
            "generated_at": now,
            "sources": {
                "step2": str(args.step2),
                "noise_manifest": str(args.noise_manifest),
            },
            "summary": {
                "task_count": len(tasks),
                "missing_histories": len(missing_histories),
                "missing_task_specs": len(missing_specs),
            },
            "tasks": tasks,
        },
    )
    write_json(
        output_dir / MAC_SOPBENCH_USER_TURN_FILE,
        {
            "schema_version": "MACSOPBenchUserTurnV1",
            "generated_at": now,
            "sources": {
                "step5_histories": str(args.step5_histories),
            },
            "summary": {
                "task_count": len(histories),
                "total_turns": sum(len(item.get("turns") or []) for item in histories),
            },
            "task_histories": histories,
        },
    )
    write_json(
        output_dir / MAC_SOPBENCH_TOOL_REGISTRY_FILE,
        {
            "schema_version": "MACSOPBenchToolRegistryV1",
            "generated_at": now,
            "sources": {
                "step2": str(args.step2),
            },
            "summary": {
                "task_count": len(registry_tasks),
            },
            "send_message_tool": send_message_tool(),
            "tasks": registry_tasks,
        },
    )
    manifest_copy = copy.deepcopy(manifest)
    manifest_copy["runtime_data_dir"] = str(output_dir)
    manifest_copy["generated_at"] = now
    manifest_copy["runtime_sources"] = {
        "tasks": str(output_dir / MAC_SOPBENCH_TASKS_FILE),
        "user_turns": str(output_dir / MAC_SOPBENCH_USER_TURN_FILE),
        "tool_registry": str(output_dir / MAC_SOPBENCH_TOOL_REGISTRY_FILE),
        "temporal_sequences": str(output_dir / MAC_SOPBENCH_TEMPORAL_SEQUENCES_FILE),
    }
    write_json(output_dir / MAC_SOPBENCH_NOISE_MANIFEST_FILE, manifest_copy)
    write_json_compact(
        output_dir / MAC_SOPBENCH_TEMPORAL_SEQUENCES_FILE,
        {
            "schema_version": "MACSOPBenchTemporalSequencesV1",
            "generated_at": now,
            "sources": {
                "step4": str(args.step4),
            },
            "runtime_step_fields": list(RUNTIME_TEMPORAL_STEP_FIELDS),
            "summary": {
                "task_count": len(temporal_sequences),
            },
            "tasks": temporal_sequences,
        },
    )

    print(
        f"Wrote {len(tasks)} task(s), {len(histories)} histor(ies), "
        f"{len(registry_tasks)} tool registry entries, "
        f"{len(temporal_sequences)} temporal sequence(s) -> {output_dir}"
    )
    if missing_histories:
        print(f"Missing histories for {len(missing_histories)} task(s).")
    if missing_specs:
        print(f"Missing noise task_specs for {len(missing_specs)} task(s).")


if __name__ == "__main__":
    main()
