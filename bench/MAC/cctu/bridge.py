"""CCTU adapter for the MAC agent loop.

Upstream CCTU validators and raw tasks live under ``bench/CCTU/``.
MAC-generated runtime exports live under ``bench/MAC/cctu/data/``.
"""

from __future__ import annotations

import copy
import importlib
import json
import re
import sys
import types
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from bench.MAC.shared.terminal_tools import send_message_tool
from bench.MAC.cctu.runtime_repairs import repaired_answer, repair_tool_codes, repair_tool_schemas

REPO_ROOT = Path(__file__).resolve().parents[3]
MAC_CCTU_DIR = REPO_ROOT / "bench" / "MAC" / "cctu"
MAC_CCTU_DATA_DIR = MAC_CCTU_DIR / "data"
MAC_CCTU_MID_DATA_DIR = MAC_CCTU_DIR / "mid_data"
MAC_CCTU_RESULTS_DIR = MAC_CCTU_DIR / "results"

MAC_CCTU_TASKS_FILE = "mac-cctu-tasks.json"
MAC_CCTU_USER_TURN_FILE = "mac-cctu-user_turn.json"
MAC_CCTU_TOOL_REGISTRY_FILE = "mac-cctu-tool_registry.json"

CCTU_EVAL_TOOL_USE_INSTRUCTION = (
    "Please call given tools to answer the question. Please note that all your information "
    "must be obtained by calling tools and not by answering the question directly.\n"
)

CCTU_EVIDENCE_STOPPING_POLICY = """# Evidence and Stopping Policy
Use tools only when they can obtain missing evidence.
After each tool result, decide whether the current evidence is sufficient to answer the user.

If a tool result contains a successful suggested result, treat that suggestion as usable evidence.
Do not retry solely because the original query was a miss.
Retry only when a required fact is still missing or results conflict.

Do not repeat a tool call with materially equivalent arguments after it has failed twice.

If the required answer can be derived from collected evidence, immediately call send_message. You do not need to exhaust every possible tool.

If evidence remains incomplete after a bounded number of attempts, call send_message with the best answer supported by collected tool evidence. Unless a task-specific instruction explicitly requires otherwise, do not keep searching after evidence stops improving."""

CCTU_EVAL_USER_PREFIX_RE = re.compile(
    r"^(?:Please call given tools to answer the question\. Please note that all your information must be obtained by calling tools(?: and not by answering the question directly)?\.(?:\s*If the call fails, you need to try to correct it and continue until you arrive at an answer\.?)?\s*)+",
    re.IGNORECASE,
)

CCTU_LEGACY_STAGE_LABELS = (
    "[THOUGHT]",
    "[ACTION]",
    "[REFLECTION]",
    "[FINAL ANSWER]",
)


def cctu_root() -> Path:
    """Return the upstream CCTU checkout used for validators and raw input."""
    candidates = [
        REPO_ROOT / "bench" / "CCTU",
        REPO_ROOT / "CCTU",
    ]
    for candidate in candidates:
        if (candidate / "evaluation.py").exists() and (candidate / "check_code").exists():
            return candidate
    searched = ", ".join(str(path) for path in candidates)
    raise FileNotFoundError(f"Could not locate CCTU source tree; searched: {searched}")


def ensure_cctu_on_path() -> Path:
    root = cctu_root()
    root_text = str(root)
    if root_text not in sys.path:
        sys.path.insert(0, root_text)
    utils_dir = root / "utils"
    if utils_dir.exists():
        loaded_utils = sys.modules.get("utils")
        loaded_path = str(getattr(loaded_utils, "__file__", "") or "") if loaded_utils is not None else ""
        loaded_paths = [str(path) for path in getattr(loaded_utils, "__path__", [])] if loaded_utils is not None else []
        if loaded_utils is None or not (
            loaded_path.startswith(root_text) or any(path.startswith(root_text) for path in loaded_paths)
        ):
            utils_pkg = types.ModuleType("utils")
            utils_pkg.__path__ = [str(utils_dir)]  # type: ignore[attr-defined]
            sys.modules["utils"] = utils_pkg
    return root


def cctu_upstream_data_dir() -> Path:
    return cctu_root() / "data"


def mac_cctu_data_dir() -> Path:
    return MAC_CCTU_DATA_DIR


def cctu_validators_dir() -> Path:
    root = cctu_root()
    if not (root / "check_code").exists():
        raise FileNotFoundError(f"CCTU check_code directory is missing: {root / 'check_code'}")
    return root


def load_cctu_samples(input_file: Path | None = None) -> list[dict[str, Any]]:
    path = input_file or (cctu_upstream_data_dir() / "input_data.jsonl")
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def cctu_samples_by_id(input_file: Path | None = None) -> dict[str, dict[str, Any]]:
    return {str(sample.get("id")): sample for sample in load_cctu_samples(input_file)}


def cctu_task_uid(sample_id: str | int) -> str:
    return f"mac-cctu-t-{int(sample_id):05d}"


def cctu_agent_name(sample_id: str | int) -> str:
    return f"cctu_task_{int(sample_id):03d}"


def cctu_id_from_task_uid(task_uid: str) -> str:
    prefix = "mac-cctu-t-"
    if task_uid.startswith(prefix):
        return str(int(task_uid[len(prefix) :]))
    if task_uid.startswith("cctu-"):
        return task_uid.split("-", 1)[1]
    return task_uid


def import_cctu_attr(module_name: str, attr_name: str) -> Any:
    ensure_cctu_on_path()
    module = importlib.import_module(module_name)
    return getattr(module, attr_name)


def cctu_call_function(
    name: str,
    arguments: dict[str, Any],
    code: str,
    *,
    match_mode: str | None = None,
    schema: dict[str, Any] | None = None,
) -> str:
    from bench.MAC.cctu.tool_match import cctu_call_function_with_match_mode

    call_function = import_cctu_attr("utils.utils", "call_function")
    return cctu_call_function_with_match_mode(
        name,
        arguments,
        code,
        match_mode=match_mode,
        call_function=call_function,
        schema=schema,
    )


def parse_cctu_tools(sample: dict[str, Any]) -> list[dict[str, Any]]:
    tools_raw = sample.get("tools", "[]")
    tools = json.loads(tools_raw) if isinstance(tools_raw, str) else tools_raw
    if not isinstance(tools, list):
        return []

    out: list[dict[str, Any]] = []
    for item in tools:
        if not isinstance(item, dict):
            continue
        fn = item.get("function") if item.get("type") == "function" else item
        if not isinstance(fn, dict):
            continue
        name = fn.get("name")
        if not isinstance(name, str) or not name:
            continue
        schema = fn.get("parameters")
        if not isinstance(schema, dict):
            schema = {"type": "object", "properties": {}, "additionalProperties": True}
        out.append(
            {
                "name": name,
                "description": str(fn.get("description") or ""),
                "input_schema": schema,
                "runtime_family": "cctu_code",
                "host_action": "cctu.tool.execute",
            }
        )
    return out


def cctu_difficulty(sample: dict[str, Any]) -> str:
    source = str(sample.get("data_source") or "")
    constraint_count = len(sample.get("constraints_list") or [])
    if "Multi-Hop" in source or constraint_count >= 6:
        return "hard"
    if "Parallel" in source or constraint_count >= 4:
        return "normal"
    return "easy"


def first_message(sample: dict[str, Any], role: str) -> str:
    messages = sample.get("messages", [])
    if not isinstance(messages, list):
        return ""
    for message in messages:
        if isinstance(message, dict) and message.get("role") == role:
            content = message.get("content")
            return content if isinstance(content, str) else ""
    return ""


def load_json_file(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def mac_cctu_tasks_path(data_dir: Path | None = None) -> Path:
    return (data_dir or mac_cctu_data_dir()) / MAC_CCTU_TASKS_FILE


def mac_cctu_user_turn_path(data_dir: Path | None = None) -> Path:
    return (data_dir or mac_cctu_data_dir()) / MAC_CCTU_USER_TURN_FILE


def mac_cctu_tool_registry_path(data_dir: Path | None = None) -> Path:
    return (data_dir or mac_cctu_data_dir()) / MAC_CCTU_TOOL_REGISTRY_FILE


def load_cctu_mac_tasks(data_dir: Path | None = None) -> dict[str, Any]:
    payload = load_json_file(mac_cctu_tasks_path(data_dir))
    if not isinstance(payload, dict):
        raise TypeError("mac-cctu-tasks.json must contain a JSON object")
    return payload


def load_cctu_user_turns(data_dir: Path | None = None) -> dict[str, Any]:
    payload = load_json_file(mac_cctu_user_turn_path(data_dir))
    if not isinstance(payload, dict):
        raise TypeError("mac-cctu-user_turn.json must contain a JSON object")
    return payload


def load_cctu_tool_registry(data_dir: Path | None = None) -> dict[str, Any]:
    payload = load_json_file(mac_cctu_tool_registry_path(data_dir))
    if not isinstance(payload, dict):
        raise TypeError("mac-cctu-tool_registry.json must contain a JSON object")
    return payload


def normalize_cctu_user_turn_content(content: str) -> tuple[str, bool]:
    """Strip repeated CCTU eval boilerplate and optional ``Question:`` wrapper."""
    text = content.strip()
    if not text:
        return text, False
    stripped = CCTU_EVAL_USER_PREFIX_RE.sub("", text).strip()
    if stripped == text:
        return text, False
    if stripped.lower().startswith("question:"):
        stripped = stripped.split(":", 1)[1].strip()
    return stripped or text, True


def ensure_cctu_eval_tool_use_instruction(system_prompt: str) -> str:
    if CCTU_EVAL_TOOL_USE_INSTRUCTION.split(".", 1)[0] in system_prompt:
        return system_prompt
    prompt = system_prompt.rstrip()
    if not prompt:
        return CCTU_EVAL_TOOL_USE_INSTRUCTION
    return f"{prompt}\n\n{CCTU_EVAL_TOOL_USE_INSTRUCTION}"


def ensure_cctu_evidence_stopping_policy(system_prompt: str) -> str:
    """Append the CCTU runtime stopping policy exactly once."""
    if "Use tools only when they can obtain missing evidence." in system_prompt:
        return system_prompt
    prompt = system_prompt.rstrip()
    if not prompt:
        return CCTU_EVIDENCE_STOPPING_POLICY
    return f"{prompt}\n\n{CCTU_EVIDENCE_STOPPING_POLICY}"


def strip_cctu_legacy_stage_labels(system_prompt: str) -> str:
    """Remove CCTU's legacy textual stage labels from the MAC runtime prompt."""
    prompt = system_prompt
    for label in CCTU_LEGACY_STAGE_LABELS:
        prompt = prompt.replace(label, "")
    return prompt


def _iter_task_user_messages(task: dict[str, Any]) -> list[str]:
    messages: list[str] = []
    for key in ("input", "original_input", "messages"):
        raw = task.get(key)
        if not isinstance(raw, list):
            continue
        for message in raw:
            if isinstance(message, dict) and message.get("role") == "user":
                content = message.get("content")
                if isinstance(content, str) and content.strip():
                    messages.append(content)
    return messages


def task_uses_cctu_eval_tool_instruction(task: dict[str, Any]) -> bool:
    return any(normalize_cctu_user_turn_content(content)[1] for content in _iter_task_user_messages(task))


def normalize_cctu_user_turn(turn: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    if turn.get("role") != "user":
        return turn, False
    content = turn.get("content")
    if not isinstance(content, str):
        return turn, False
    normalized, had_boilerplate = normalize_cctu_user_turn_content(content)
    if not had_boilerplate or normalized == content:
        return turn, False
    updated = copy.deepcopy(turn)
    updated["content"] = normalized
    return updated, True


def system_prompt_from_task_record(task: dict[str, Any], *, ensure_terminal_instruction: bool = True) -> str:
    from bench.MAC.shared.terminal_tools import ensure_terminal_tool_instruction

    prompt = ""
    messages = task.get("input", task.get("messages", []))
    if isinstance(messages, list):
        for message in messages:
            if isinstance(message, dict) and message.get("role") == "system":
                content = message.get("content")
                if isinstance(content, str) and content.strip():
                    prompt = content.strip()
                    break
    if not prompt:
        domain = task.get("domain_context")
        prompt = domain.strip() if isinstance(domain, str) else ""
    prompt = strip_cctu_legacy_stage_labels(prompt)
    if task_uses_cctu_eval_tool_instruction(task):
        prompt = ensure_cctu_eval_tool_use_instruction(prompt)
        prompt = ensure_cctu_evidence_stopping_policy(prompt)
    if ensure_terminal_instruction:
        prompt = ensure_terminal_tool_instruction(prompt)
    return prompt


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
    runtime_family = "terminal" if name == "send_message" else "cctu_code"
    host_action = "final.respond" if name == "send_message" else "cctu.tool.execute"
    return {
        "name": name,
        "description": str(fn.get("description") or ""),
        "input_schema": schema,
        "runtime_family": runtime_family,
        "host_action": host_action,
    }


def mac_tools_from_openai_schemas(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [openai_tool_schema_to_mac(tool) for tool in tools if isinstance(tool, dict)]


def index_mac_cctu_tasks(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    indexed: dict[str, dict[str, Any]] = {}
    for task in payload.get("tasks", []):
        if not isinstance(task, dict):
            continue
        uid = str(task.get("mac_task_uid") or task.get("task_uid") or "")
        if uid:
            indexed[uid] = task
    return indexed


def index_cctu_user_histories(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    indexed: dict[str, dict[str, Any]] = {}
    for history in payload.get("task_histories", []):
        if not isinstance(history, dict):
            continue
        uid = str(history.get("task_uid") or "")
        if uid:
            indexed[uid] = history
    return indexed


def index_cctu_tool_registry(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    indexed: dict[str, dict[str, Any]] = {}
    for entry in payload.get("tasks", []):
        if not isinstance(entry, dict):
            continue
        uid = str(entry.get("task_uid") or "")
        if uid:
            indexed[uid] = entry
    return indexed


def parse_cctu_codes(raw: Any) -> dict[str, str]:
    if isinstance(raw, dict):
        return {str(key): str(value) for key, value in raw.items() if isinstance(value, str)}
    if isinstance(raw, str) and raw.strip():
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return {}
        if isinstance(parsed, dict):
            return {str(key): str(value) for key, value in parsed.items() if isinstance(value, str)}
    return {}


def build_cctu_system_config(
    *,
    data_dir: Path | None = None,
    ensure_terminal_instruction: bool = True,
) -> dict[str, Any]:
    tasks_payload = load_cctu_mac_tasks(data_dir)
    registry_payload = load_cctu_tool_registry(data_dir)
    tasks_by_uid = index_mac_cctu_tasks(tasks_payload)
    registry_by_uid = index_cctu_tool_registry(registry_payload)

    agents: dict[str, dict[str, Any]] = {}
    for task_uid, task in sorted(tasks_by_uid.items()):
        agent = str(task.get("agent_name") or cctu_agent_name(task.get("cctu_id") or cctu_id_from_task_uid(task_uid)))
        registry_entry = registry_by_uid.get(task_uid, {})
        tools_raw = registry_entry.get("tools", [])
        if isinstance(tools_raw, list):
            tools_raw = repair_tool_schemas(task_uid, tools_raw)
        tools = mac_tools_from_openai_schemas(tools_raw) if isinstance(tools_raw, list) else []
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
            "runtime_family": "cctu_tool_use",
            "needs_react_loop": True,
            "tools": tools,
            "cctu_id": str(task.get("cctu_id") or cctu_id_from_task_uid(task_uid)),
        }

    return {
        "schema_version": "MACSystemConfigV1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "sources": {
            "tasks": str(mac_cctu_tasks_path(data_dir)),
            "tool_registry": str(mac_cctu_tool_registry_path(data_dir)),
        },
        "summary": {
            "total_agents": len(agents),
            "agents_with_system_prompt": len(agents),
            "agents_with_tools": len(agents),
        },
        "send_message_tool": send_message_tool(),
        "agents": agents,
    }


def build_cctu_eval_task(
    task_uid: str,
    *,
    data_dir: Path | None = None,
    samples_by_id: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build one agent-loop task record from exported CCTU MAC artifacts."""
    tasks_by_uid = index_mac_cctu_tasks(load_cctu_mac_tasks(data_dir))
    histories_by_uid = index_cctu_user_histories(load_cctu_user_turns(data_dir))
    if task_uid not in tasks_by_uid:
        raise KeyError(f"Unknown CCTU task uid: {task_uid}")
    if task_uid not in histories_by_uid:
        raise KeyError(f"Missing user-turn history for task uid: {task_uid}")

    task_meta = tasks_by_uid[task_uid]
    history = histories_by_uid[task_uid]
    turns: list[dict[str, Any]] = []
    uses_eval_tool_instruction = task_uses_cctu_eval_tool_instruction(task_meta)
    for turn in history.get("turns", []):
        if not isinstance(turn, dict):
            continue
        normalized_turn, had_boilerplate = normalize_cctu_user_turn(turn)
        turns.append(normalized_turn)
        uses_eval_tool_instruction = uses_eval_tool_instruction or had_boilerplate
    cctu_id = str(task_meta.get("cctu_id") or cctu_id_from_task_uid(task_uid))
    sample_lookup = samples_by_id if samples_by_id is not None else cctu_samples_by_id()
    sample = sample_lookup.get(cctu_id, {})
    tools = copy.deepcopy(task_meta.get("tools", []))
    if not isinstance(tools, list):
        tools = []
    tools = repair_tool_schemas(task_uid, tools)
    codes = repair_tool_codes(task_uid, parse_cctu_codes(sample.get("codes")))

    return {
        "task_uid": task_uid,
        "agent_name": task_meta.get("agent_name") or cctu_agent_name(cctu_id),
        "cctu_id": cctu_id,
        "task_summary": task_meta.get("mac_task_summary"),
        "input": copy.deepcopy(task_meta.get("input", [])),
        "original_input": copy.deepcopy(task_meta.get("original_input", [])),
        "constraints": copy.deepcopy(task_meta.get("constraints", [])),
        "constraints_list": copy.deepcopy(task_meta.get("constraints_list", [])),
        "answer": repaired_answer(task_uid, task_meta.get("answer") or sample.get("answer")),
        "data_source": task_meta.get("data_source") or sample.get("data_source"),
        "codes": codes,
        "tools": tools,
        "task_chain": {
            "turns": turns,
            "turn_count": len(turns),
            "history_user_turn_count": history.get("history_user_turn_count", max(len(turns) - 1, 0)),
            "actual_user_turn_count": history.get("actual_user_turn_count", len(turns)),
            "project_phase_grounding": copy.deepcopy(history.get("project_phase_grounding")),
            "style_example": copy.deepcopy(history.get("style_example")),
        },
        "evaluation": {
            "default_turn_policy": "last_user_turn",
            "current_user_turn": turns[-1] if turns else None,
            "past_user_turns": turns[:-1] if turns else [],
        },
        "uses_cctu_eval_tool_instruction": uses_eval_tool_instruction,
    }


def list_cctu_task_uids(*, data_dir: Path | None = None) -> list[str]:
    return sorted(index_mac_cctu_tasks(load_cctu_mac_tasks(data_dir)).keys())


def load_cctu_eval_tasks(
    *,
    data_dir: Path | None = None,
    uids: list[str] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Load exported CCTU tasks in agent-loop shape."""
    selected_uids = uids or list_cctu_task_uids(data_dir=data_dir)
    samples = cctu_samples_by_id()
    tasks = [
        build_cctu_eval_task(uid, data_dir=data_dir, samples_by_id=samples) for uid in selected_uids
    ]
    return tasks, {
        "bench": "cctu",
        "task_count": len(tasks),
        "task_uids": selected_uids,
        "data_dir": str(data_dir or mac_cctu_data_dir()),
    }
