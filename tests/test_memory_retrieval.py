from __future__ import annotations

import asyncio
from pathlib import Path

from bench.MAC.agent.loop.tools import ToolExecution
from bench.MAC.agent.memory.base import MemoryRequest
from bench.MAC.agent.memory.bm25 import BM25Config, BM25MemoryProvider
from bench.MAC.agent.memory.embedding import EmbeddingConfig, EmbeddingMemoryProvider
from bench.MAC.agent.memory.mac import MACHookedToolExecutor, MACMemoryConfig, MACMemoryProvider
from bench.MAC.agent.memory.mem0 import Mem0Config, Mem0MemoryProvider
from bench.MAC.agent.memory.registry import available_memory_systems, get_memory_provider
from bench.MAC.agent.memory.rrf import RRFConfig, RRFMemoryProvider
from memory_as_contracts.models import (
    Contract,
    ContractKind,
    ContractSource,
    Lifecycle,
    LifecycleType,
    Modality,
    RuleEffect,
    RuleSemantics,
    Scope,
    ScopeLevel,
    SourceKind,
    Strength,
    ToolPattern,
)


def memory_request(user_prompt: str = "python test style") -> MemoryRequest:
    return MemoryRequest(
        task_uid="task-1",
        agent="agent",
        user_prompt=user_prompt,
        past_user_turns=[
            {"role": "user", "turn_index": 0, "content": "Always write Python tests with pytest."},
            {"role": "user", "turn_index": 1, "content": "Billing answers must mention invoices."},
        ],
        task={},
        memory_llm={"api_key_env": "unused"},
    )


def fake_embed(texts: list[str], model: str) -> list[list[float]]:
    del model
    vectors: list[list[float]] = []
    for text in texts:
        lowered = text.lower()
        if "python" in lowered or "pytest" in lowered:
            vectors.append([1.0, 0.0])
        elif "billing" in lowered or "invoice" in lowered:
            vectors.append([0.0, 1.0])
        else:
            vectors.append([0.5, 0.5])
    return vectors


class FakeMACExtractor:
    def extract_online_turn(self, *, role: str, text: str, context) -> list[Contract]:
        if role != "user":
            return []
        if "Always write Python tests with pytest." in text:
            return [
                Contract(
                    text="Always write Python tests with pytest.",
                    kind=ContractKind.PREFERENCE,
                    modality=Modality.SHOULD,
                    strength=Strength.SOFT,
                    effect=RuleEffect.PREFER,
                    source=ContractSource(
                        kind=SourceKind.USER_TURN,
                        conversation_id=context.conversation_id,
                        turn_id=context.turn_id,
                    ),
                    scope=Scope(
                        level=ScopeLevel.GLOBAL,
                    ),
                    lifecycle=Lifecycle(type=LifecycleType.UNTIL_REVOKED, until_revoked=True),
                    semantics=RuleSemantics(actions=["agent.response"], tags=["response_style"]),
                    check_patterns=[ToolPattern(tool="agent.response")],
                )
            ]
        if "Do not send messages." in text:
            return [
                Contract(
                    text="Do not send messages.",
                    kind=ContractKind.PROHIBITION,
                    modality=Modality.MUST_NOT,
                    strength=Strength.HARD,
                    effect=RuleEffect.DENY,
                    source=ContractSource(
                        kind=SourceKind.USER_TURN,
                        conversation_id=context.conversation_id,
                        turn_id=context.turn_id,
                    ),
                    scope=Scope(
                        level=ScopeLevel.GLOBAL,
                    ),
                    lifecycle=Lifecycle(type=LifecycleType.UNTIL_REVOKED, until_revoked=True),
                    semantics=RuleSemantics(actions=["message.send"], tags=["external_write"]),
                    check_patterns=[ToolPattern(tool="send_message")],
                )
            ]
        return []


def test_bm25_retrieves_single_user_turns() -> None:
    provider = BM25MemoryProvider(BM25Config(top_k=1))

    result = provider.build_memory(memory_request())

    assert result.metadata["retrieval_unit"] == "user_turn"
    assert result.metadata["indexed_turn_count"] == 2
    assert result.metadata["included_turn_count"] == 1
    assert "Always write Python tests" in result.memory
    assert "Billing answers" not in result.memory


def test_embedding_persists_turn_level_index(tmp_path: Path) -> None:
    calls: list[list[str]] = []

    def counting_embed(texts: list[str], model: str) -> list[list[float]]:
        calls.append(list(texts))
        return fake_embed(texts, model)

    config = EmbeddingConfig(top_k=1, model="fake-embedding", cache_dir=tmp_path)
    first = EmbeddingMemoryProvider(config=config, embed=counting_embed).build_memory(memory_request())
    second = EmbeddingMemoryProvider(config=config, embed=counting_embed).build_memory(memory_request())

    assert first.metadata["retrieval_unit"] == "user_turn"
    assert first.metadata["cache_hit"] is False
    assert second.metadata["cache_hit"] is True
    assert "Always write Python tests" in second.memory
    assert len(calls[0]) == 2
    assert calls[-1] == ["python test style"]
    assert list(tmp_path.glob("*.json"))


def test_rrf_fuses_bm25_and_embedding_turn_rankings(tmp_path: Path) -> None:
    config = RRFConfig(
        top_k=1,
        embedding=EmbeddingConfig(top_k=1, model="fake-embedding", cache_dir=tmp_path),
    )
    provider = RRFMemoryProvider(config=config, embed=fake_embed)

    result = provider.build_memory(memory_request())

    assert result.metadata["retrieval_unit"] == "user_turn"
    assert result.metadata["components"] == ["bm25", "embedding"]
    assert result.metadata["included_turn_count"] == 1
    assert "Always write Python tests" in result.memory


def test_registry_exposes_retrieval_memory_systems() -> None:
    systems = available_memory_systems()

    assert {"bm25", "embedding", "rrf", "mac", "mem0"}.issubset(systems)
    assert get_memory_provider("bm25").name == "bm25"
    assert get_memory_provider("embedding").name == "embedding"
    assert get_memory_provider("rrf").name == "rrf"
    assert get_memory_provider("mac").name == "mac"
    assert get_memory_provider("mem0").name == "mem0"


def test_mac_memory_provider_extracts_contracts_from_history_user_turns() -> None:
    request = MemoryRequest(
        task_uid="task-1",
        agent="agent",
        user_prompt="Please write Python tests for the parser.",
        past_user_turns=[
            {
                "role": "user",
                "turn_index": 0,
                "content": "Always write Python tests with pytest.",
            },
            {
                "role": "user",
                "turn_index": 1,
                "content": "The billing task is ordinary context, not a future rule.",
            },
        ],
        task={"tools": []},
        memory_llm={"api_key_env": "unused"},
    )
    provider = MACMemoryProvider(MACMemoryConfig(), extractor=FakeMACExtractor())

    result = provider.build_memory(request)

    assert result.metadata["retrieval_unit"] == "mac_contract"
    assert result.metadata["contract_source"] == "history_user_turns"
    assert result.metadata["extracted_contract_count"] == 1
    assert "Always write Python tests with pytest." in result.memory
    assert "billing task" not in result.memory
    provider.close_runtime("task-1")


class FakeInnerExecutor:
    def __init__(self) -> None:
        self.called = False

    def execute(self, *, call_id: str, name: str, arguments):
        self.called = True
        return ToolExecution(name=name, call_id=call_id, arguments=arguments, result={"ok": True})


def test_mac_hook_wrapper_gates_tool_calls_from_extracted_history() -> None:
    request = MemoryRequest(
        task_uid="task-1",
        agent="agent",
        user_prompt="Please notify the user.",
        past_user_turns=[
            {
                "role": "user",
                "turn_index": 0,
                "content": "Do not send messages.",
            }
        ],
        task={"tools": [{"name": "send_message", "input_schema": {"type": "object"}}]},
        memory_llm={"api_key_env": "unused"},
    )
    provider = MACMemoryProvider(MACMemoryConfig(), extractor=FakeMACExtractor())
    provider.build_memory(request)
    state = provider.runtime_for_task("task-1")
    assert state is not None
    inner = FakeInnerExecutor()
    executor = MACHookedToolExecutor(state=state, inner=inner)

    result = asyncio.run(
        executor.execute(
            call_id="call-1",
            name="send_message",
            arguments={"response": "hello"},
        )
    )

    assert inner.called is False
    assert result.result["ok"] is False
    assert result.result["error"] == "MAC constraint blocked tool call"
    assert result.result["constraints"] == ["Do not send messages."]
    assert executor.mac_events[0]["event"] == "mac_pre_tool_use"
    assert executor.mac_events[0]["decision"] == "reject"


class FakeMem0Client:
    def __init__(self) -> None:
        self.add_calls: list[dict] = []
        self.search_calls: list[dict] = []
        self.delete_all_calls: list[dict] = []

    def add(self, messages, **kwargs):
        self.add_calls.append({"messages": messages, "kwargs": kwargs})
        return {"results": [{"id": f"mem-{len(self.add_calls)}", "event": "ADD"}]}

    def search(self, query: str, **kwargs):
        self.search_calls.append({"query": query, "kwargs": kwargs})
        return {
            "results": [
                {
                    "id": "mem-python",
                    "memory": "Always write Python tests with pytest.",
                    "score": 0.9,
                }
            ]
        }

    def delete_all(self, **kwargs):
        self.delete_all_calls.append(kwargs)
        return {"message": "deleted"}


def test_mem0_batches_user_turns_for_extraction(tmp_path: Path) -> None:
    client = FakeMem0Client()
    provider = Mem0MemoryProvider(
        Mem0Config(top_k=1, ingest_cache_dir=tmp_path, ingest_batch_size=10),
        client=client,
    )

    result = provider.build_memory(memory_request())
    cached = provider.build_memory(memory_request())

    assert result.metadata["ingest_unit"] == "user_turn_batch"
    assert result.metadata["ingest_batch_size"] == 10
    assert result.metadata["ingest_batch_count"] == 1
    assert result.metadata["retrieval_unit"] == "mem0_memory"
    assert result.metadata["backend"] == "oss"
    assert result.metadata["infer"] is True
    assert result.metadata["ingest_cache_hit"] is False
    assert cached.metadata["ingest_cache_hit"] is True
    assert len(client.add_calls) == 1
    assert len(client.delete_all_calls) == 1
    messages = client.add_calls[0]["messages"]
    assert isinstance(messages, list)
    assert len(messages) == 2
    assert messages[0]["role"] == "user"
    assert "pytest" in messages[0]["content"]
    assert client.add_calls[0]["kwargs"]["infer"] is True
    assert client.add_calls[0]["kwargs"]["metadata"]["ingest_unit"] == "user_turn_batch"
    assert client.search_calls[-1]["kwargs"]["filters"] == {"user_id": result.metadata["user_id"]}
    assert client.search_calls[-1]["kwargs"]["top_k"] == 1
    assert "Always write Python tests" in result.memory


def test_mem0_uses_multiple_batches_when_turn_count_exceeds_batch_size(tmp_path: Path) -> None:
    client = FakeMem0Client()
    turns = [
        {"role": "user", "turn_index": index, "content": f"Constraint rule number {index}."}
        for index in range(12)
    ]
    request = MemoryRequest(
        task_uid="task-batch",
        agent="agent",
        user_prompt="What is rule 11?",
        past_user_turns=turns,
        task={},
        memory_llm={"api_key_env": "unused"},
    )
    provider = Mem0MemoryProvider(
        Mem0Config(top_k=1, ingest_cache_dir=tmp_path, ingest_batch_size=10),
        client=client,
    )

    result = provider.build_memory(request)

    assert result.metadata["ingest_batch_count"] == 2
    assert len(client.add_calls) == 2
    assert len(client.add_calls[0]["messages"]) == 10
    assert len(client.add_calls[1]["messages"]) == 2
