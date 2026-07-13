from __future__ import annotations

import asyncio

from bench.MAC.agent.trajectory import build_raw_history
from bench.MAC.agent.loop.prompt import build_prompt_messages, openai_tool_definitions
from bench.MAC.agent.loop.llm_tools import LLMToolExecutor, LLMToolReturnConfig
from bench.MAC.agent.loop.runner import model_context_from_trace, run_agent_loop
from bench.MAC.agent.loop.tools import HeuristicToolExecutor, default_heuristic_result, route_tool


TOOL_SCHEMAS = [
    {
        "name": "read_file",
        "description": "Read a file.",
        "input_schema": {
            "type": "object",
            "required": ["path"],
            "properties": {"path": {"type": "string"}},
            "additionalProperties": False,
        },
    },
    {
        "name": "send_message",
        "description": "Submit final response.",
        "input_schema": {
            "type": "object",
            "required": ["response"],
            "properties": {"response": {"type": "string"}},
            "additionalProperties": False,
        },
    },
]


def test_prompt_builder_emits_compact_tool_protocol_and_memory_user_order() -> None:
    messages = build_prompt_messages(
        agent="TestAgent",
        system_prompt="system text",
        tools=TOOL_SCHEMAS,
        memory="remember this",
        user_prompt="answer me",
    )

    assert [message["role"] for message in messages] == ["system", "system", "user"]
    assert messages[0]["content"] == "system text\n\n<memory>\nremember this\n</memory>"
    assert "<tool_protocol>" in messages[1]["content"]
    assert "send_message" in messages[1]["content"]
    assert "read_file" not in messages[1]["content"]
    assert messages[2]["content"] == "answer me"


def test_openai_tool_definitions_preserve_input_schema() -> None:
    definitions = openai_tool_definitions(TOOL_SCHEMAS)

    assert definitions[0]["type"] == "function"
    assert definitions[0]["function"]["name"] == "read_file"
    assert definitions[0]["function"]["parameters"]["required"] == ["path"]


def test_stub_executor_uses_agent_specific_template() -> None:
    executor = HeuristicToolExecutor(
        agent="TestAgent",
        tool_returns={
            "read_file": {
                "result": {
                    "ok": True,
                    "path": "{path}",
                    "content_preview": "Loaded {path}",
                }
            }
        },
    )

    result = executor.execute(call_id="call_1", name="read_file", arguments={"path": "README.md"})

    assert result.result["path"] == "README.md"
    assert result.result["content_preview"] == "Loaded README.md"


def test_default_stub_returns_realistic_search_shape() -> None:
    result = default_heuristic_result("web_search", {"query": "latest docs"})

    assert result["ok"] is True
    assert result["simulated"] is True
    assert result["query"] == "latest docs"
    assert result["results"][0]["source"] == "benchmark_workspace_index"


class FakeModel:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    async def __call__(self, *, messages, tools):
        self.calls.append({"messages": list(messages), "tools": list(tools)})
        return self.responses.pop(0)


class FakeToolReturnModel:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    async def __call__(self, *, messages, tools):
        self.calls.append({"messages": list(messages), "tools": list(tools)})
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


class FakeMemoryRejectingExecutor:
    def __init__(self) -> None:
        self.calls = 0

    def execute(self, *, call_id, name, arguments):
        from bench.MAC.agent.loop.tools import ToolExecution

        self.calls += 1
        if self.calls == 1:
            return ToolExecution(
                name=name,
                call_id=call_id,
                arguments=arguments,
                result={
                    "ok": False,
                    "memory_rejected": True,
                    "message": "[memory] This tool call is not allowed due to \"final format\". Please retry after revise.",
                },
            )
        return ToolExecution(name=name, call_id=call_id, arguments=arguments, result={"ok": True})


def test_runner_appends_tool_result_and_continues_to_send_message() -> None:
    model = FakeModel(
        [
            {
                "content": "",
                "reasoning_content": "Need to inspect a file.",
                "tool_calls": [
                    {
                        "id": "call_read",
                        "type": "function",
                        "function": {
                            "name": "read_file",
                            "arguments": "{\"path\": \"README.md\"}",
                        },
                    }
                ],
            },
            {
                "content": "",
                "tool_calls": [
                    {
                        "id": "call_final",
                        "type": "function",
                        "function": {
                            "name": "send_message",
                            "arguments": "{\"response\": \"done\"}",
                        },
                    }
                ],
            },
        ]
    )

    result = asyncio.run(
        run_agent_loop(
            agent="TestAgent",
            system_prompt="system",
            tools=TOOL_SCHEMAS,
            memory="contract memory",
            user_prompt="task",
            model_client=model,
        )
    )

    assert result.final_answer == "done"
    assert result.stop_reason == "send_message"
    assert result.prompt_hash
    assert any(event["event"] == "reasoning" for event in result.events)
    assert any(message.get("role") == "tool" and message.get("name") == "read_file" for message in result.messages)
    assert any(message.get("role") == "tool" and message.get("name") == "send_message" for message in result.messages)
    assert any(message.get("role") == "tool" and message.get("name") == "read_file" for message in model.calls[1]["messages"])
    raw_assistant = next(message for message in result.messages if message.get("tool_calls"))
    model_assistant = next(message for message in model.calls[1]["messages"] if message.get("tool_calls"))
    assert raw_assistant["reasoning_content"] == "Need to inspect a file."
    assert "reasoning_content" not in model_assistant
    assert model.calls[1]["messages"] is not result.messages


def test_model_context_can_explicitly_replay_reasoning_for_ablation() -> None:
    raw_trace = [
        {"role": "system", "content": "system"},
        {
            "role": "assistant",
            "content": "",
            "reasoning_content": "private chain of thought",
            "tool_calls": [{"id": "call_1", "type": "function", "function": {"name": "read_file"}}],
        },
        {"role": "tool", "tool_call_id": "call_1", "name": "read_file", "content": "file content"},
    ]

    compact_context = model_context_from_trace(raw_trace, replay_reasoning_content=False)
    replay_context = model_context_from_trace(raw_trace, replay_reasoning_content=True)

    assert raw_trace[1]["reasoning_content"] == "private chain of thought"
    assert "reasoning_content" not in compact_context[1]
    assert replay_context[1]["reasoning_content"] == "private chain of thought"
    assert compact_context[1]["tool_calls"] == raw_trace[1]["tool_calls"]
    assert compact_context[2] == raw_trace[2]


def test_runner_does_not_treat_memory_rejected_send_message_as_terminal() -> None:
    model = FakeModel(
        [
            {
                "content": "",
                "tool_calls": [
                    {
                        "id": "call_bad_final",
                        "type": "function",
                        "function": {
                            "name": "send_message",
                            "arguments": "{\"response\": \"bad\"}",
                        },
                    }
                ],
            },
            {
                "content": "",
                "tool_calls": [
                    {
                        "id": "call_good_final",
                        "type": "function",
                        "function": {
                            "name": "send_message",
                            "arguments": "{\"response\": \"good\"}",
                        },
                    }
                ],
            },
        ]
    )
    executor = FakeMemoryRejectingExecutor()

    result = asyncio.run(
        run_agent_loop(
            agent="TestAgent",
            system_prompt="system",
            tools=TOOL_SCHEMAS,
            memory="contract memory",
            user_prompt="task",
            model_client=model,
            executor=executor,
        )
    )

    assert result.final_answer == "good"
    assert result.stop_reason == "send_message"
    assert executor.calls == 2
    tool_events = [event for event in result.events if event["event"] == "tool_result"]
    assert tool_events[0]["terminal"] is False
    assert tool_events[1]["terminal"] is True


def test_runner_repairs_plain_final_text_with_send_message() -> None:
    model = FakeModel(
        [
            {"content": "plain final", "tool_calls": []},
            {
                "content": "",
                "tool_calls": [
                    {
                        "id": "call_final",
                        "type": "function",
                        "function": {
                            "name": "send_message",
                            "arguments": "{\"response\": \"plain final\"}",
                        },
                    }
                ],
            },
        ]
    )

    result = asyncio.run(
        run_agent_loop(
            agent="TestAgent",
            system_prompt="system",
            tools=TOOL_SCHEMAS,
            memory="contract memory",
            user_prompt="task",
            model_client=model,
        )
    )

    assert result.final_answer == "plain final"
    assert result.stop_reason == "send_message"
    assert any(event["event"] == "terminal_repair_prompt" for event in result.events)
    second_call_messages = model.calls[1]["messages"]
    assert second_call_messages[-2] == {"role": "assistant", "content": "plain final"}
    assert second_call_messages[-1]["role"] == "user"
    assert "call the `send_message` tool" in second_call_messages[-1]["content"]


def test_runner_reports_plain_final_text_after_terminal_repair_fails() -> None:
    model = FakeModel(
        [
            {"content": "plain final", "tool_calls": []},
            {"content": "still plain", "tool_calls": []},
        ]
    )

    result = asyncio.run(
        run_agent_loop(
            agent="TestAgent",
            system_prompt="system",
            tools=TOOL_SCHEMAS,
            memory="contract memory",
            user_prompt="task",
            model_client=model,
        )
    )

    assert result.final_answer is None
    assert result.stop_reason == "missing_terminal_tool"
    assert result.error == "Model produced final text without calling send_message after terminal repair."


def test_tool_route_table_marks_content_tools_for_llm() -> None:
    assert route_tool(agent="Codex CLI_Prompt", tool_name="run_shell_command") == "llm"
    assert route_tool(agent="Codex CLI_Prompt", tool_name="apply_patch") == "heuristic"
    assert route_tool(agent="Codex CLI_Prompt", tool_name="insert_patch") == "heuristic"
    assert route_tool(agent="atomr", tool_name="send_message") == "heuristic"


def test_build_raw_history_merges_tool_results_into_tool_calls() -> None:
    row = {
        "final_answer": "done",
        "events": [
            {
                "event": "reasoning",
                "iteration": 0,
                "text": "Need to inspect.",
            },
            {
                "event": "model_response",
                "iteration": 0,
                "content": "",
                "tool_calls": [
                    {
                        "id": "call_shell",
                        "name": "run_shell_command",
                        "arguments": {"cmd": ["bash", "-lc", "pytest -q"]},
                    }
                ],
            },
            {
                "event": "tool_result",
                "iteration": 0,
                "tool_call_id": "call_shell",
                "name": "run_shell_command",
                "runtime": {
                    "ok": True,
                    "simulated": True,
                    "source": "llm_tool_return",
                    "route": "llm",
                    "attempt": 1,
                    "cached": False,
                    "result": {"exit_code": 0, "stdout": "passed", "stderr": ""},
                },
            },
        ],
    }

    raw_history = build_raw_history(row)

    assert raw_history == {
        "final_response": "done",
        "trajectory": [
            {
                "kind": "assistant",
                "iteration": 0,
                "content": "Need to inspect.",
                "tool_calls": [
                    {
                        "id": "call_shell",
                        "name": "run_shell_command",
                        "arguments": {"cmd": ["bash", "-lc", "pytest -q"]},
                        "result": {"exit_code": 0, "stdout": "passed", "stderr": ""},
                    }
                ],
            }
        ],
    }


def test_llm_tool_executor_retries_and_wraps_runtime_metadata() -> None:
    model = FakeToolReturnModel(
        [
            {"content": "not json", "tool_calls": []},
            {
                "content": '{"exit_code": 0, "stdout": "tests passed", "stderr": ""}',
                "tool_calls": [],
            },
        ]
    )
    executor = LLMToolExecutor(
        agent="Codex CLI_Prompt",
        tools=[
            {
                "name": "run_shell_command",
                "canonical_tags": ["shell"],
                "host_action": "computer.shell",
            }
        ],
        task_uid="mac-t-test",
        user_prompt="run tests",
        memory="project phase: test run",
        model_client=model,
        config=LLMToolReturnConfig(mode="hybrid", max_attempts=3),
    )

    execution = asyncio.run(
        executor.execute(
            call_id="call_shell",
            name="run_shell_command",
            arguments={"cmd": ["bash", "-lc", "pytest -q"]},
        )
    )

    assert len(model.calls) == 2
    assert execution.result["ok"] is True
    assert execution.result["simulated"] is True
    assert execution.result["source"] == "llm_tool_return"
    assert execution.result["attempt"] == 2
    assert execution.result["cached"] is False
    assert execution.result["result"]["stdout"] == "tests passed"
    prompt = model.calls[-1]["messages"][-1]["content"]
    assert prompt.rfind('"current_tool_call"') > prompt.find('"prior_tool_calls_and_outcomes"')


def test_llm_tool_executor_cache_reuses_identical_call_in_same_state() -> None:
    model = FakeToolReturnModel(
        [
            {
                "content": '{"path": "README.md", "content": "# Demo", "truncated": false}',
                "tool_calls": [],
            }
        ]
    )
    executor = LLMToolExecutor(
        agent="Cline_Prompt",
        tools=[{"name": "read_file", "canonical_tags": ["read", "file"]}],
        task_uid="mac-t-test",
        user_prompt="read file",
        memory="",
        model_client=model,
        config=LLMToolReturnConfig(mode="hybrid", max_attempts=1),
    )

    first = asyncio.run(
        executor.execute(call_id="call_1", name="read_file", arguments={"path": "README.md"})
    )
    second = asyncio.run(
        executor.execute(call_id="call_2", name="read_file", arguments={"path": "README.md"})
    )

    assert len(model.calls) == 1
    assert first.result["cached"] is False
    assert second.result["cached"] is True
    assert second.result["result"]["content"] == "# Demo"


def test_llm_tool_executor_reports_runtime_failure_after_retries() -> None:
    model = FakeToolReturnModel(
        [
            {"content": "not json", "tool_calls": []},
            {"content": "still not json", "tool_calls": []},
        ]
    )
    executor = LLMToolExecutor(
        agent="Cline_Prompt",
        tools=[{"name": "read_file", "canonical_tags": ["read", "file"]}],
        task_uid="mac-t-test",
        user_prompt="read file",
        memory="",
        model_client=model,
        config=LLMToolReturnConfig(mode="hybrid", max_attempts=2),
    )

    execution = asyncio.run(
        executor.execute(call_id="call_1", name="read_file", arguments={"path": "README.md"})
    )

    assert len(model.calls) == 2
    assert execution.result["ok"] is False
    assert execution.result["error"] == "tool_return_generation_failed"
    assert execution.result["result"]["tool_name"] == "read_file"
