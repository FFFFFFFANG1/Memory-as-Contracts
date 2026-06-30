"""SOPBench strict-domain tool execution adapter for the MAC agent loop."""

from __future__ import annotations

import copy
import sys
from pathlib import Path
from typing import Any

from bench.MAC.agent.loop.tools import ToolExecution, default_heuristic_result, parse_tool_arguments

REPO_ROOT = Path(__file__).resolve().parents[4]
SOPBENCH_ROOT = REPO_ROOT / "bench" / "SOPBench"


def ensure_sopbench_imports() -> None:
    root = str(SOPBENCH_ROOT)
    if root not in sys.path:
        sys.path.insert(0, root)


def list_to_tuple(value: Any) -> Any:
    if isinstance(value, list):
        return tuple(list_to_tuple(item) for item in value)
    if isinstance(value, dict):
        return {key: list_to_tuple(item) for key, item in value.items()}
    return value


def to_json_safe(value: Any) -> Any:
    if isinstance(value, tuple):
        return [to_json_safe(item) for item in value]
    if isinstance(value, list):
        return [to_json_safe(item) for item in value]
    if isinstance(value, dict):
        return {str(key): to_json_safe(item) for key, item in value.items()}
    return value


def create_strict_runtime(task: dict[str, Any]) -> Any:
    """Instantiate the SOPBench strict domain runtime for one eval task."""
    ensure_sopbench_imports()
    from env.task import get_default_dep_full  # type: ignore[import-not-found]  # noqa: WPS433
    from env.variables import domain_assistant_keys, domain_keys  # type: ignore[import-not-found]  # noqa: WPS433

    domain = str(task.get("domain") or "")
    patched = copy.deepcopy(task.get("patched_sopbench_task") or {})
    if not patched:
        raise ValueError(f"missing patched_sopbench_task for {task.get('task_uid')}")

    user_goal = str(patched.get("user_goal") or task.get("user_goal") or "")
    dep_innate_full = domain_assistant_keys[domain].action_innate_dependencies
    default_dep_full = get_default_dep_full(domain, "default")
    default_dep_full[user_goal] = list_to_tuple(patched.get("constraints"))
    return domain_keys[f"{domain}_strict"](
        copy.deepcopy(patched.get("initial_database")),
        dep_innate_full,
        default_dep_full,
        patched.get("constraint_parameters") or {},
    )


class SOPBenchToolExecutor:
    """Execute SOPBench domain tools against a persistent strict runtime."""

    def __init__(self, *, task: dict[str, Any]) -> None:
        self.task = task
        self._runtime = create_strict_runtime(task)

    def execute(self, *, call_id: str, name: str, arguments: Any) -> ToolExecution:
        parsed = parse_tool_arguments(arguments)
        if name == "send_message":
            return ToolExecution(
                name=name,
                call_id=call_id,
                arguments=parsed,
                result=default_heuristic_result(name, parsed),
            )

        if not hasattr(self._runtime, name):
            result = f"an error occured when call {name}: tool not found in SOPBench strict runtime"
            return ToolExecution(name=name, call_id=call_id, arguments=parsed, result=result)

        try:
            response = getattr(self._runtime, name)(**parsed)
            result = to_json_safe(response)
        except Exception as exc:  # noqa: BLE001 - preserve SOPBench-style error-as-observation behavior.
            result = f"an error occured when call {name}: {exc}"
        return ToolExecution(name=name, call_id=call_id, arguments=parsed, result=result)
