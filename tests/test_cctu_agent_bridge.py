from __future__ import annotations

from bench.MAC.agent.data import build_agent_loop_input
from bench.MAC.agent.loop.prompt import TERMINAL_TOOL_RUNTIME_RULE, build_prompt_messages
from bench.MAC.agent.memory.base import MemoryRequest
from bench.MAC.agent.memory.long_context import LongContextMemoryProvider
from bench.MAC.cctu.bridge import (
    build_cctu_eval_task,
    build_cctu_system_config,
    list_cctu_task_uids,
)
from bench.MAC.shared.terminal_tools import ensure_terminal_tool_instruction


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
    assert any(tool["name"] == "send_message" for tool in agent_config["tools"])


def test_cctu_eval_task_wires_long_context_inputs() -> None:
    task = build_cctu_eval_task("mac-cctu-t-00000")
    system_config = build_cctu_system_config()
    loop_input = build_agent_loop_input(task, system_config)

    assert loop_input.task_uid == "mac-cctu-t-00000"
    assert loop_input.past_user_turns
    assert loop_input.user_prompt == task["task_chain"]["turns"][-1]["content"]
    assert task["codes"]

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


def test_ensure_terminal_tool_instruction_is_idempotent() -> None:
    base = "You are a helpful agent."
    once = ensure_terminal_tool_instruction(base)
    twice = ensure_terminal_tool_instruction(once)
    assert once == twice
    assert "send_message" in once
