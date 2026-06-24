"""Minimal Nanobot-style benchmark agent loop."""

from __future__ import annotations

import hashlib
import inspect
import json
from dataclasses import dataclass, field
from typing import Any, Protocol

from bench.MAC.agent.loop.prompt import build_prompt_messages, openai_tool_definitions
from bench.MAC.agent.loop.tools import HeuristicToolExecutor, ToolExecution, parse_tool_arguments

TERMINAL_REPAIR_PROMPT = """Your previous response was plain assistant text, but this runtime cannot deliver plain assistant text as the final answer.

You must now call the `send_message` tool exactly once. Put the complete final answer you intended to give in `send_message.response`.

Do not revise the answer unless needed to preserve the original user request. Do not add any extra plain assistant text."""


class ModelClient(Protocol):
    async def __call__(
        self,
        *,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> Any:
        """Return a model response with optional tool calls."""


class ToolExecutor(Protocol):
    def execute(self, *, call_id: str, name: str, arguments: Any) -> Any:
        """Return a ToolExecution, either synchronously or as an awaitable."""


@dataclass(slots=True)
class ParsedToolCall:
    id: str
    name: str
    arguments: dict[str, Any]

    def to_openai_tool_call(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "type": "function",
            "function": {
                "name": self.name,
                "arguments": json.dumps(self.arguments, ensure_ascii=False),
            },
        }


@dataclass(slots=True)
class LoopResult:
    final_answer: str | None
    messages: list[dict[str, Any]]
    prompt_hash: str
    events: list[dict[str, Any]] = field(default_factory=list)
    iterations: int = 0
    stop_reason: str = "completed"
    error: str | None = None


def _response_value(response: Any, key: str, default: Any = None) -> Any:
    if isinstance(response, dict):
        return response.get(key, default)
    return getattr(response, key, default)


def _parse_tool_call(raw: Any, index: int) -> ParsedToolCall | None:
    if not isinstance(raw, dict):
        raw = {
            "id": getattr(raw, "id", f"call_{index}"),
            "name": getattr(raw, "name", ""),
            "arguments": getattr(raw, "arguments", {}),
        }

    call_id = str(raw.get("id") or f"call_{index}")
    function = raw.get("function")
    if isinstance(function, dict):
        name = function.get("name")
        arguments = function.get("arguments", {})
    else:
        name = raw.get("name")
        arguments = raw.get("arguments", raw.get("args", {}))

    if not isinstance(name, str) or not name:
        return None
    return ParsedToolCall(call_id, name, parse_tool_arguments(arguments))


def parse_tool_calls(response: Any) -> list[ParsedToolCall]:
    raw_calls = _response_value(response, "tool_calls", [])
    if not isinstance(raw_calls, list):
        return []
    calls: list[ParsedToolCall] = []
    for index, raw in enumerate(raw_calls):
        call = _parse_tool_call(raw, index)
        if call is not None:
            calls.append(call)
    return calls


def parse_response_content(response: Any) -> str:
    value = _response_value(response, "content", "")
    return value if isinstance(value, str) else ""


def parse_reasoning_content(response: Any) -> str:
    for key in ("reasoning_content", "reasoning"):
        value = _response_value(response, key, "")
        if isinstance(value, str) and value:
            return value
    return ""


def prompt_hash(messages: list[dict[str, Any]]) -> str:
    payload = json.dumps(messages, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


async def _call_model(
    model_client: ModelClient,
    *,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]],
) -> Any:
    result = model_client(messages=messages, tools=tools)
    if inspect.isawaitable(result):
        return await result
    return result


async def _execute_tool(
    executor: ToolExecutor,
    *,
    call_id: str,
    name: str,
    arguments: Any,
) -> ToolExecution:
    result = executor.execute(call_id=call_id, name=name, arguments=arguments)
    if inspect.isawaitable(result):
        result = await result
    if not isinstance(result, ToolExecution):
        raise TypeError(f"Tool executor returned invalid result for {name}: {type(result).__name__}")
    return result


async def run_agent_loop(
    *,
    agent: str,
    system_prompt: str,
    tools: list[dict[str, Any]],
    memory: str,
    user_prompt: str,
    model_client: ModelClient,
    executor: ToolExecutor | None = None,
    max_iterations: int = 15,
    strict_terminal: bool = True,
    max_terminal_repairs: int = 1,
) -> LoopResult:
    """Run prompt -> model -> tool result replay until terminal `send_message`."""
    messages = build_prompt_messages(
        agent=agent,
        system_prompt=system_prompt,
        tools=tools,
        memory=memory,
        user_prompt=user_prompt,
    )
    tool_definitions = openai_tool_definitions(tools)
    tool_executor = executor or HeuristicToolExecutor(agent=agent)
    initial_prompt_hash = prompt_hash(messages)
    events: list[dict[str, Any]] = [
        {"event": "prompt_built", "agent": agent, "prompt_hash": initial_prompt_hash}
    ]
    terminal_repairs_used = 0

    for iteration in range(max_iterations):
        response = await _call_model(model_client, messages=messages, tools=tool_definitions)
        content = parse_response_content(response)
        reasoning = parse_reasoning_content(response)
        tool_calls = parse_tool_calls(response)

        if reasoning:
            events.append({"event": "reasoning", "iteration": iteration, "text": reasoning})

        assistant_message: dict[str, Any] = {"role": "assistant", "content": content}
        if reasoning:
            assistant_message["reasoning_content"] = reasoning
        if tool_calls:
            assistant_message["tool_calls"] = [call.to_openai_tool_call() for call in tool_calls]
        messages.append(assistant_message)

        events.append(
            {
                "event": "model_response",
                "iteration": iteration,
                "content": content,
                "tool_calls": [
                    {"id": call.id, "name": call.name, "arguments": call.arguments}
                    for call in tool_calls
                ],
            }
        )

        if not tool_calls:
            if strict_terminal:
                if terminal_repairs_used < max_terminal_repairs:
                    terminal_repairs_used += 1
                    messages.append({"role": "user", "content": TERMINAL_REPAIR_PROMPT})
                    events.append(
                        {
                            "event": "terminal_repair_prompt",
                            "iteration": iteration,
                            "repair_index": terminal_repairs_used,
                            "original_content_length": len(content),
                        }
                    )
                    continue
                return LoopResult(
                    final_answer=None,
                    messages=messages,
                    prompt_hash=initial_prompt_hash,
                    events=events,
                    iterations=iteration + 1,
                    stop_reason="missing_terminal_tool",
                    error="Model produced final text without calling send_message after terminal repair.",
                )
            return LoopResult(
                final_answer=content,
                messages=messages,
                prompt_hash=initial_prompt_hash,
                events=events,
                iterations=iteration + 1,
            )

        for call in tool_calls:
            execution = await _execute_tool(
                tool_executor,
                call_id=call.id,
                name=call.name,
                arguments=call.arguments,
            )
            tool_message = {
                "role": "tool",
                "tool_call_id": call.id,
                "name": call.name,
                "content": execution.content,
            }
            messages.append(tool_message)
            events.append(
                {
                    "event": "tool_result",
                    "iteration": iteration,
                    "tool_call_id": call.id,
                    "name": call.name,
                    "arguments": execution.arguments,
                    "result": execution.result,
                    "runtime": execution.result if isinstance(execution.result, dict) else {},
                    "terminal": call.name == "send_message",
                }
            )

            if call.name == "send_message":
                response_text = call.arguments.get("response")
                final_answer = response_text if isinstance(response_text, str) else ""
                return LoopResult(
                    final_answer=final_answer,
                    messages=messages,
                    prompt_hash=initial_prompt_hash,
                    events=events,
                    iterations=iteration + 1,
                    stop_reason="send_message",
                )

    return LoopResult(
        final_answer=None,
        messages=messages,
        prompt_hash=initial_prompt_hash,
        events=events,
        iterations=max_iterations,
        stop_reason="max_iterations",
        error="Loop reached max_iterations before send_message.",
    )

