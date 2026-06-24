"""Common memory provider interface for MAC evaluation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(slots=True)
class MemoryRequest:
    task_uid: str
    agent: str
    user_prompt: str
    past_user_turns: list[dict[str, Any]]
    task: dict[str, Any]
    memory_llm: dict[str, Any] | None = None


@dataclass(slots=True)
class MemoryResult:
    system_name: str
    memory: str
    metadata: dict[str, Any]


class MemoryProvider(Protocol):
    name: str

    def build_memory(self, request: MemoryRequest) -> MemoryResult:
        """Build the `<memory>` payload for one agent loop call."""

