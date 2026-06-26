from __future__ import annotations

from bench.MAC.agent.data import build_agent_loop_input
from bench.MAC.agent.loop.prompt import TERMINAL_TOOL_RUNTIME_RULE, build_prompt_messages
from bench.MAC.agent.memory.base import MemoryRequest
from bench.MAC.agent.memory.mac import BenchMACAdapter
from bench.MAC.agent.memory.long_context import LongContextMemoryProvider
from bench.MAC.cctu.bridge import (
    build_cctu_eval_task,
    build_cctu_system_config,
    list_cctu_task_uids,
)
from bench.MAC.shared.terminal_tools import ensure_terminal_tool_instruction


def test_bench_mac_adapter_capsules_are_host_tool_passthrough() -> None:
    host_tools = [
        {
            "name": "file.write",
            "description": "Writes files in the current agent workspace.",
            "input_schema": {
                "type": "object",
                "properties": {"path": {"type": "string"}, "content": {"type": "string"}},
            },
        },
        {
            "name": "web.search",
            "description": "Searches the current benchmark environment.",
            "input_schema": {"type": "object", "properties": {"query": {"type": "string"}}},
        },
        {
            "name": "send_message",
            "description": "Sends the final answer.",
            "input_schema": {"type": "object", "properties": {"response": {"type": "string"}}},
        },
    ]
    adapter = BenchMACAdapter(agent="example_agent", tools=host_tools, token_budget=1500)

    capsules = adapter.tool_capsules()

    assert [capsule.name for capsule in capsules] == ["file.write", "web.search", "send_message"]
    assert capsules[0].input_schema == host_tools[0]["input_schema"]


def test_bench_mac_adapter_uses_only_agent_loop_tools() -> None:
    task = build_cctu_eval_task("mac-cctu-t-00000")
    system_config = build_cctu_system_config()
    loop_input = build_agent_loop_input(task, system_config)
    adapter = BenchMACAdapter(
        agent=loop_input.agent,
        tools=list(loop_input.tools),
        token_budget=1500,
    )

    capsule_names = {capsule.name for capsule in adapter.tool_capsules()}
    loop_tool_names = {tool["name"] for tool in loop_input.tools}
    generic_tools = {"file.write", "file.delete", "web.search", "exec", "Bash"}

    assert capsule_names == loop_tool_names
    assert "send_message" in capsule_names
    assert capsule_names.isdisjoint(generic_tools)


def test_cctu_exports_are_loadable() -> None:
    uids = list_cctu_task_uids()
    assert len(uids) == 200
    assert uids[0] == "mac-cctu-t-00000"


def test_cctu_system_prompt_includes_send_message_rule() -> None:
    system_config = build_cctu_system_config()
    agent_config = system_config["agents"]["cctu_task_000"]
    prompt = agent_config["system_prompt"]
    assert "send_message" in prompt.lower()
    assert "plain assistant text" in prompt.lower()
    assert "Please call given tools to answer the question" in prompt
    assert any(tool["name"] == "send_message" for tool in agent_config["tools"])


def test_cctu_eval_task_strips_tool_use_boilerplate_from_user_prompt() -> None:
    task = build_cctu_eval_task("mac-cctu-t-00000")
    system_config = build_cctu_system_config()
    loop_input = build_agent_loop_input(task, system_config)

    assert loop_input.task_uid == "mac-cctu-t-00000"
    assert loop_input.past_user_turns
    assert "Please call given tools" not in loop_input.user_prompt
    assert loop_input.user_prompt.startswith("When did WikiLeaks")
    assert task["uses_cctu_eval_tool_instruction"] is True
    assert task["codes"]
    assert "Please call given tools to answer the question" in loop_input.system_prompt

    memory = LongContextMemoryProvider().build_memory(
        MemoryRequest(
            task_uid=loop_input.task_uid,
            agent=loop_input.agent,
            user_prompt=loop_input.user_prompt,
            past_user_turns=loop_input.past_user_turns,
            task=loop_input.task,
            memory_llm={"model": "unused"},
        )
    )
    messages = build_prompt_messages(
        agent=loop_input.agent,
        system_prompt=loop_input.system_prompt,
        tools=loop_input.tools,
        memory=memory.memory,
        user_prompt=loop_input.user_prompt,
    )

    assert [message["role"] for message in messages] == ["system", "system", "user"]
    assert TERMINAL_TOOL_RUNTIME_RULE in messages[1]["content"]
    assert "Below is previous messages from user" in messages[0]["content"]
    assert "[past_user_turn" in messages[0]["content"]
    assert "Please call given tools to answer the question" in messages[0]["content"]
    assert "Please call given tools" not in messages[2]["content"]


def test_ensure_terminal_tool_instruction_is_idempotent() -> None:
    base = "You are a helpful agent."
    once = ensure_terminal_tool_instruction(base)
    twice = ensure_terminal_tool_instruction(once)
    assert once == twice
    assert "send_message" in once
