"""Memory provider registry."""

from __future__ import annotations

from bench.MAC.agent.memory.base import MemoryProvider
from bench.MAC.agent.memory.bm25 import BM25MemoryProvider
from bench.MAC.agent.memory.embedding import EmbeddingMemoryProvider
from bench.MAC.agent.memory.long_context import LongContextMemoryProvider
from bench.MAC.agent.memory.mac import MACMemoryProvider
from bench.MAC.agent.memory.mem0 import Mem0MemoryProvider
from bench.MAC.agent.memory.no_memory import NoMemoryProvider
from bench.MAC.agent.memory.oracle import OracleMemoryProvider
from bench.MAC.agent.memory.rrf import RRFMemoryProvider


def get_memory_provider(name: str) -> MemoryProvider:
    normalized = name.strip().lower().replace("-", "_")
    if normalized == "no_memory":
        return NoMemoryProvider()
    if normalized == "long_context":
        return LongContextMemoryProvider()
    if normalized == "bm25":
        return BM25MemoryProvider()
    if normalized == "embedding":
        return EmbeddingMemoryProvider()
    if normalized == "rrf":
        return RRFMemoryProvider()
    if normalized == "mac":
        return MACMemoryProvider()
    if normalized == "mem0":
        return Mem0MemoryProvider()
    if normalized == "oracle":
        return OracleMemoryProvider()
    raise ValueError(f"Unknown memory system: {name}")


def available_memory_systems() -> list[str]:
    return ["no_memory", "long_context", "bm25", "embedding", "rrf", "mac", "mem0", "oracle"]

