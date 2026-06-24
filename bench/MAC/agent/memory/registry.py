"""Memory provider registry."""

from __future__ import annotations

from bench.MAC.agent.memory.base import MemoryProvider
from bench.MAC.agent.memory.long_context import LongContextMemoryProvider
from bench.MAC.agent.memory.no_memory import NoMemoryProvider


def get_memory_provider(name: str) -> MemoryProvider:
    normalized = name.strip().lower().replace("-", "_")
    if normalized == "no_memory":
        return NoMemoryProvider()
    if normalized == "long_context":
        return LongContextMemoryProvider()
    raise ValueError(f"Unknown memory system: {name}")


def available_memory_systems() -> list[str]:
    return ["no_memory", "long_context"]

