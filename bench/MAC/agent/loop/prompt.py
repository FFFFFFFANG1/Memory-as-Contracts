"""Prompt assembly for the benchmark agent loop."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


def _repo_root() -> Path:
    for parent in Path(__file__).resolve().parents:
        if (parent / "pyproject.toml").exists():
            return parent
    return Path(__file__).resolve().parents[4]


REPO_ROOT = _repo_root()

TERMINAL_TOOL_RUNTIME_RULE = (
    "Do not provide the final answer as plain assistant text. "
    "When you are ready to answer, call send_message with the full final answer "
    "in its response field. Plain assistant text is not delivered to the user."
)

TERMINAL_TOOL_SYSTEM_SUFFIX = (
    "\n\n# Final Response Protocol\n"
    "Do not provide the final answer as plain assistant text. "
    "When you are ready to answer, you must call the `send_message` tool exactly once "
    "and put the complete final answer in its `response` field. "
    "Plain assistant text is not delivered to the user."
)


def slugify_agent(agent: str) -> str:
    """Return a deterministic filesystem slug for an agent name."""
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", agent.strip().lower()).strip("_")
    return slug or "agent"


def load_json(path: str | Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def openai_tool_definitions(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Convert extracted tool schemas to OpenAI-style function definitions."""
    definitions: list[dict[str, Any]] = []
    for tool in tools:
        name = tool.get("name")
        if not isinstance(name, str) or not name:
            continue
        schema = tool.get("input_schema")
        if not isinstance(schema, dict):
            schema = {"type": "object", "properties": {}, "additionalProperties": True}
        definitions.append(
            {
                "type": "function",
                "function": {
                    "name": name,
                    "description": str(tool.get("description") or ""),
                    "parameters": schema,
                },
            }
        )
    return definitions


def render_tool_schema_message(agent: str, tools: list[dict[str, Any]]) -> str:
    """Render tool schemas and terminal-output rules as a prompt block."""
    payload = {
        "agent": agent,
        "tool_calling_contract": {
            "all_useful_outputs_must_be_tool_bounded": True,
            "terminal_tool": "send_message",
            "plain_assistant_final_text_is_invalid": True,
            "tool_results_are_simulated_by_benchmark_runtime": True,
            "runtime_output_rule": TERMINAL_TOOL_RUNTIME_RULE,
        },
        "tools": tools,
    }
    return "<tool_schema>\n" + json.dumps(payload, indent=2, ensure_ascii=False) + "\n</tool_schema>"


def render_memory_message(memory: str) -> str:
    """Render the externally supplied MAC memory block."""
    return "<memory>\n" + memory.strip() + "\n</memory>"


def append_memory_to_system_prompt(system_prompt: str, memory: str) -> str:
    """Append the memory block to the end of the domain system prompt."""
    if not memory.strip():
        return system_prompt
    return system_prompt.rstrip() + "\n\n" + render_memory_message(memory)


def build_prompt_messages(
    *,
    agent: str,
    system_prompt: str,
    tools: list[dict[str, Any]],
    memory: str,
    user_prompt: str,
) -> list[dict[str, str]]:
    """Build messages in benchmark order: system (+ memory), tools, user."""
    return [
        {"role": "system", "content": append_memory_to_system_prompt(system_prompt, memory)},
        {"role": "system", "content": render_tool_schema_message(agent, tools)},
        {"role": "user", "content": user_prompt},
    ]
