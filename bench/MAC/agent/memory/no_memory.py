"""No-memory baseline."""

from __future__ import annotations

from bench.MAC.agent.memory.base import MemoryRequest, MemoryResult


class NoMemoryProvider:
    name = "no_memory"

    def build_memory(self, request: MemoryRequest) -> MemoryResult:
        return MemoryResult(
            system_name=self.name,
            memory="",
            metadata={
                "past_turn_count": len(request.past_user_turns),
                "included_turn_count": 0,
            },
        )

