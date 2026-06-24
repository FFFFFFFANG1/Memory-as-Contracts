import os

from bench.MAC.agent.data import build_agent_loop_input
from bench.MAC.agent.loop.memoryarena_tools import MemoryArenaWebShopToolExecutor
from bench.MAC.agent.memory.base import MemoryRequest
from bench.MAC.agent.memory.long_context import LongContextMemoryProvider
from bench.MAC.scripts.run_memory_eval import load_bench_env
from bench.MAC.memoryarena.bridge import (
    MEMORYARENA_AGENT_NAME,
    MEMORYARENA_CURRENT_USER_PROMPT,
    build_memoryarena_system_config,
    load_memoryarena_eval_tasks,
)


def test_memoryarena_tasks_are_loadable() -> None:
    tasks, summary = load_memoryarena_eval_tasks()

    assert summary["bench"] == "memoryarena"
    assert summary["config"] == "bundled_shopping"
    assert tasks
    assert tasks[0]["task_uid"] == "mac-memoryarena-bundled_shopping-00000"
    assert tasks[0]["agent_name"] == MEMORYARENA_AGENT_NAME


def test_memoryarena_constraints_move_to_first_user_turn() -> None:
    tasks, _summary = load_memoryarena_eval_tasks()
    system_config = build_memoryarena_system_config()
    loop_input = build_agent_loop_input(tasks[0], system_config)

    assert "GLOBAL RULES" not in loop_input.system_prompt
    assert "Product 1:" not in loop_input.system_prompt
    assert "GLOBAL RULES" in loop_input.past_user_turns[0]["content"]
    assert "Product 1:" in loop_input.past_user_turns[0]["content"]
    assert loop_input.user_prompt == MEMORYARENA_CURRENT_USER_PROMPT

    memory = LongContextMemoryProvider().build_memory(
        MemoryRequest(
            task_uid=loop_input.task_uid,
            agent=loop_input.agent,
            user_prompt=loop_input.user_prompt,
            past_user_turns=loop_input.past_user_turns,
            task=loop_input.task,
            memory_llm={},
        )
    )
    assert "GLOBAL RULES" in memory.memory
    assert "Product 1:" in memory.memory


def test_memoryarena_system_config_exposes_webshop_tools_and_send_message() -> None:
    system_config = build_memoryarena_system_config()
    agent_config = system_config["agents"][MEMORYARENA_AGENT_NAME]
    tools = {tool["name"]: tool for tool in agent_config["tools"]}

    assert "send_message" in agent_config["system_prompt"]
    assert "Plain assistant text is not delivered to the user" in agent_config["system_prompt"]
    assert set(tools) == {"search", "click", "send_message"}
    assert tools["search"]["runtime_family"] == "memoryarena_webshop"
    assert tools["click"]["runtime_family"] == "memoryarena_webshop"
    assert tools["send_message"]["terminal"] is True


def test_memoryarena_executor_maps_tools_to_native_actions() -> None:
    search_action = MemoryArenaWebShopToolExecutor._action_from_tool(
        "search",
        {"keywords": "vanilla cake mix"},
    )
    click_action = MemoryArenaWebShopToolExecutor._action_from_tool(
        "click",
        {"item": "B00TUDFEW2"},
    )

    assert search_action == "search[vanilla cake mix]"
    assert click_action == "click[B00TUDFEW2]"


def test_bench_env_loader_uses_llm_env_names(tmp_path, monkeypatch) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text(
        "LLM_API_KEY=test-key\nLLM_BASE_URL=https://example.test/v1\nLLM_MODEL=test-model\n",
        encoding="utf-8",
    )
    for key in ("LLM_API_KEY", "LLM_BASE_URL", "LLM_MODEL"):
        monkeypatch.delenv(key, raising=False)

    load_bench_env(env_path)

    assert os.environ["LLM_API_KEY"] == "test-key"
    assert os.environ["LLM_BASE_URL"] == "https://example.test/v1"
    assert os.environ["LLM_MODEL"] == "test-model"
