from __future__ import annotations

from bench.MAC.agent.memory.base import MemoryRequest
from bench.MAC.agent.memory.oracle import OracleMemoryProvider
from bench.MAC.agent.memory.registry import available_memory_systems, get_memory_provider
from bench.MAC.cctu.bridge import build_cctu_eval_task
from bench.MAC.sopbench.bridge import build_sopbench_eval_task


def test_registry_exposes_oracle_provider() -> None:
    assert "oracle" in available_memory_systems()
    provider = get_memory_provider("oracle")
    assert provider.name == "oracle"


def test_oracle_cctu_renders_active_constraints_without_history() -> None:
    task = build_cctu_eval_task("mac-cctu-t-00000")
    request = MemoryRequest(
        task_uid=task["task_uid"],
        agent=str(task["agent_name"]),
        user_prompt="Please answer the final question.",
        past_user_turns=list(task["evaluation"]["past_user_turns"]),
        task=task,
        memory_llm={"api_key_env": "unused"},
    )

    result = OracleMemoryProvider().build_memory(request)

    assert result.system_name == "oracle"
    assert "Oracle constraints active for the current evaluation task." in result.memory
    assert "Markdown syntax" in result.memory
    assert "At most 20 including final answer" in result.memory
    assert result.metadata["bench_family"] == "cctu"
    assert result.metadata["constraint_count"] >= 2
    assert result.metadata["included_turn_count"] == 0
    assert "past_user_turn" not in result.memory


def test_oracle_sopbench_renders_user_goal_constraints_only() -> None:
    task = build_sopbench_eval_task("sopbench:bank:apply_credit_card:3")
    request = MemoryRequest(
        task_uid=task["task_uid"],
        agent=str(task["agent_name"]),
        user_prompt="Apply for a credit card.",
        past_user_turns=list(task["evaluation"]["past_user_turns"]),
        task=task,
        memory_llm={"api_key_env": "unused"},
    )

    result = OracleMemoryProvider().build_memory(request)

    assert result.system_name == "oracle"
    assert result.metadata["bench_family"] == "sopbench"
    assert result.metadata["user_goal"] == "apply_credit_card"
    assert result.metadata["oracle_source"] == "patched_sopbench_task.constraints[checklist]"
    assert "Overall success condition:" in result.memory
    assert "[apply_credit_card]" in result.memory or "apply_credit_card" in result.memory
    assert "credit score higher than the 400 credit score" in result.memory
    assert "exchange_foreign_currency" not in result.memory
    assert result.metadata["included_turn_count"] == 0


def test_oracle_sopbench_renders_or_branches_for_book_room() -> None:
    task = build_sopbench_eval_task("sopbench:hotel:book_room:8")
    request = MemoryRequest(
        task_uid=task["task_uid"],
        agent=str(task["agent_name"]),
        user_prompt="Book a room.",
        past_user_turns=list(task["evaluation"]["past_user_turns"]),
        task=task,
        memory_llm={"api_key_env": "unused"},
    )

    result = OracleMemoryProvider().build_memory(request)

    assert result.metadata["oracle_source"] == "patched_sopbench_task.constraints[checklist]"
    assert "Section 1 MUST pass." in result.memory
    assert "AND Section 2 MUST pass." in result.memory
    assert "At least one Path below must pass" in result.memory
    assert "loyalty tier of either \"gold\" or \"platinum\"" in result.memory
    assert "10 nights **or fewer**" in result.memory
    assert "Expected outcome" not in result.memory


def test_oracle_sopbench_renders_should_not_succeed_for_impossible_modify() -> None:
    task = build_sopbench_eval_task("sopbench:hotel:modify_reservation:70")
    request = MemoryRequest(
        task_uid=task["task_uid"],
        agent=str(task["agent_name"]),
        user_prompt="Modify the reservation.",
        past_user_turns=list(task["evaluation"]["past_user_turns"]),
        task=task,
        memory_llm={"api_key_env": "unused"},
    )

    result = OracleMemoryProvider().build_memory(request)

    assert "Expected outcome" not in result.memory
    assert "3 nights **or fewer**" in result.memory
