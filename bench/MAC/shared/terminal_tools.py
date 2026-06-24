"""Terminal tool helpers shared across MAC benchmark bridges."""

from __future__ import annotations

from typing import Any


def send_message_tool() -> dict[str, Any]:
    return {
        "name": "send_message",
        "description": "Submit the final user-visible response for this task. This is a terminal tool.",
        "input_schema": {
            "type": "object",
            "required": ["response"],
            "properties": {
                "response": {
                    "type": "string",
                    "description": "The complete final answer that should be evaluated as the assistant response.",
                }
            },
            "additionalProperties": False,
        },
        "host_action": "final.respond",
        "canonical_tags": ["final_response", "user_visible_output"],
        "side_effect": "external_write",
        "terminal": True,
        "stub_result": {
            "ok": True,
            "simulated": True,
            "terminal": True,
            "message": "Final response accepted by the benchmark runtime.",
        },
    }


def append_send_message(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    filtered = [tool for tool in tools if tool.get("name") != "send_message"]
    return [*filtered, send_message_tool()]


def ensure_terminal_tool_instruction(system_prompt: str) -> str:
    """Append terminal tool rules when missing from a domain prompt."""
    from bench.MAC.agent.loop.prompt import TERMINAL_TOOL_RUNTIME_RULE, TERMINAL_TOOL_SYSTEM_SUFFIX

    text = system_prompt.rstrip()
    lowered = text.lower()
    if "send_message" in lowered and "plain assistant text" in lowered:
        return text
    if TERMINAL_TOOL_RUNTIME_RULE.lower() in lowered:
        return text
    return text + TERMINAL_TOOL_SYSTEM_SUFFIX
