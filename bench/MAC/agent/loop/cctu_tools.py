"""CCTU tool execution adapter for the MAC agent loop."""

from __future__ import annotations

import json
from typing import Any

from bench.MAC.agent.loop.tools import ToolExecution, default_heuristic_result, parse_tool_arguments
from bench.MAC.cctu.bridge import cctu_call_function
from bench.MAC.cctu.tool_match import cctu_tool_match_mode


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
            result = cctu_call_function(name, parsed, code, match_mode=cctu_tool_match_mode())
        except Exception as exc:  # noqa: BLE001 - preserve CCTU's error-as-observation behavior.
            result = f"an error occured when call {name}: {exc}"
        return ToolExecution(name=name, call_id=call_id, arguments=parsed, result=result)
