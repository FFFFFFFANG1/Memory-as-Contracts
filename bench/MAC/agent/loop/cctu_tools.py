"""CCTU tool execution adapter for the MAC agent loop."""

from __future__ import annotations

import json
from typing import Any

from bench.MAC.agent.loop.tools import ToolExecution, default_heuristic_result, parse_tool_arguments
from bench.MAC.cctu.bridge import cctu_call_function
from bench.MAC.cctu.tool_match import cctu_tool_match_mode, format_cctu_call_error


def _tool_schema_map(task: dict[str, Any]) -> dict[str, dict[str, Any]]:
    schemas: dict[str, dict[str, Any]] = {}
    tools = task.get("tools")
    if not isinstance(tools, list):
        return schemas
    for tool in tools:
        if not isinstance(tool, dict):
            continue
        if tool.get("type") == "function" and isinstance(tool.get("function"), dict):
            fn = tool["function"]
            name = fn.get("name")
            schema = fn.get("parameters")
        else:
            name = tool.get("name")
            schema = tool.get("input_schema") or tool.get("parameters")
        if isinstance(name, str) and name and isinstance(schema, dict):
            schemas[name] = schema
    return schemas


class CCTUToolExecutor:
    """Execute CCTU task-local Python tool simulators.

    CCTU stores simulator source code in each task's ``codes`` JSON string. The
    MAC loop still owns message replay and terminal handling; this executor only
    replaces the generic heuristic tool output for CCTU domain tools.
    """

    def __init__(self, *, task: dict[str, Any]) -> None:
        raw_codes = task.get("codes", {})
        if isinstance(raw_codes, str):
            try:
                raw_codes = json.loads(raw_codes)
            except json.JSONDecodeError:
                raw_codes = {}
        self.codes = raw_codes if isinstance(raw_codes, dict) else {}
        self.schemas = _tool_schema_map(task)

    def execute(self, *, call_id: str, name: str, arguments: Any) -> ToolExecution:
        parsed = parse_tool_arguments(arguments)
        if name == "send_message":
            return ToolExecution(
                name=name,
                call_id=call_id,
                arguments=parsed,
                result=default_heuristic_result(name, parsed),
            )

        code = self.codes.get(name)
        if not isinstance(code, str):
            result = f"an error occured when call {name}: tool code not found"
            return ToolExecution(name=name, call_id=call_id, arguments=parsed, result=result)

        try:
            result = cctu_call_function(
                name,
                parsed,
                code,
                match_mode=cctu_tool_match_mode(),
                schema=self.schemas.get(name),
            )
        except Exception as exc:  # noqa: BLE001 - preserve CCTU's error-as-observation behavior.
            result = format_cctu_call_error(
                tool_name=name,
                arguments=parsed,
                code=code,
                exc=exc,
                schema=self.schemas.get(name),
            )
        return ToolExecution(name=name, call_id=call_id, arguments=parsed, result=result)
