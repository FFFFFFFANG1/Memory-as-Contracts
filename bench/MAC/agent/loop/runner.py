"""Minimal Nanobot-style benchmark agent loop."""

from __future__ import annotations

import hashlib
import inspect
import json
from dataclasses import dataclass, field
from typing import Any, Callable, Protocol

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
class ClarificationPolicy:
    """When send_message looks like a question, inject a heuristic user reply and continue."""

    reply_for: Callable[[str], str | None]
    max_rounds: int = 3


@dataclass(slots=True)
class LoopResult:
    final_answer: str | None
    messages: list[dict[str, Any]]
    prompt_hash: str
    events: list[dict[str, Any]] = field(default_factory=list)
    iterations: int = 0
    stop_reason: str = "completed"
    error: str | None = None
    clarification_rounds: int = 0


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


CLARIFICATION_DEFERRED_TOOL_RESULT = {
    "ok": True,
    "simulated": True,
    "terminal": False,
    "clarification_deferred": True,
    "message": (
        "The response was treated as a clarification request rather than a final answer. "
        "The user's reply follows in the next message."
    ),
}


async def run_agent_loop(
    *,
    agent: str,
    system_prompt: str,
    tools: list[dict[str, Any]],
    memory: str,
    user_prompt: str,
    model_client: ModelClient,
    executor: ToolExecutor | None = None,
    max_iterations: int = 25,
    strict_terminal: bool = True,
    max_terminal_repairs: int = 1,
    clarification: ClarificationPolicy | None = None,
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
    clarification_rounds = 0

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
                    clarification_rounds=clarification_rounds,
                )
            return LoopResult(
                final_answer=content,
                messages=messages,
                prompt_hash=initial_prompt_hash,
                events=events,
                iterations=iteration + 1,
                clarification_rounds=clarification_rounds,
            )

        deferred_clarification = False
        for call in tool_calls:
            execution = await _execute_tool(
                tool_executor,
                call_id=call.id,
                name=call.name,
                arguments=call.arguments,
            )
            is_send_message = call.name == "send_message"
            response_text = call.arguments.get("response") if is_send_message else None
            response_text = response_text if isinstance(response_text, str) else ""
            user_clarification_reply = None
            if (
                is_send_message
                and clarification is not None
                and clarification_rounds < clarification.max_rounds
            ):
                user_clarification_reply = clarification.reply_for(response_text)

            if is_send_message and user_clarification_reply is not None:
                tool_content = json.dumps(CLARIFICATION_DEFERRED_TOOL_RESULT, ensure_ascii=False)
                tool_runtime: Any = CLARIFICATION_DEFERRED_TOOL_RESULT
                terminal = False
            else:
                tool_content = execution.content
                tool_runtime = execution.result if isinstance(execution.result, dict) else {}
                terminal = is_send_message

            tool_message = {
                "role": "tool",
                "tool_call_id": call.id,
                "name": call.name,
                "content": tool_content,
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
                    "runtime": tool_runtime,
                    "terminal": terminal,
                }
            )

            if is_send_message and user_clarification_reply is not None:
                clarification_rounds += 1
                messages.append({"role": "user", "content": user_clarification_reply})
                events.append(
                    {
                        "event": "clarification_reply",
                        "iteration": iteration,
                        "round": clarification_rounds,
                        "agent_response": response_text,
                        "user_reply": user_clarification_reply,
                    }
                )
                deferred_clarification = True
                continue

            if is_send_message:
                final_answer = response_text
                return LoopResult(
                    final_answer=final_answer,
                    messages=messages,
                    prompt_hash=initial_prompt_hash,
                    events=events,
                    iterations=iteration + 1,
                    stop_reason="send_message",
                    clarification_rounds=clarification_rounds,
                )

        if deferred_clarification:
            continue

    return LoopResult(
        final_answer=None,
        messages=messages,
        prompt_hash=initial_prompt_hash,
        events=events,
        iterations=max_iterations,
        stop_reason="max_iterations",
        error="Loop reached max_iterations before send_message.",
        clarification_rounds=clarification_rounds,
    )

