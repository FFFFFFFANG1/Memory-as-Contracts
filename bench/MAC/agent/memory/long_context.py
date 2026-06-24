"""Long-context baseline that places all past user turns into memory."""

from __future__ import annotations

from typing import Any

from bench.MAC.agent.memory.base import MemoryRequest, MemoryResult


def _turn_label(turn: dict[str, Any], fallback_index: int) -> str:
    value = turn.get("turn_index", fallback_index)
    return str(value)


LONG_CONTEXT_MEMORY_PREAMBLE = (
    "Below is previous messages from user. You should learn all effective user "
    "requirements from these messages and follow them in the current task."
)


class LongContextMemoryProvider:
    name = "long_context"

    def build_memory(self, request: MemoryRequest) -> MemoryResult:
        lines: list[str] = [LONG_CONTEXT_MEMORY_PREAMBLE]
        for index, turn in enumerate(request.past_user_turns):
            content = turn.get("content")
            if not isinstance(content, str) or not content.strip():
                continue
            label = _turn_label(turn, index)
            lines.append(f"[past_user_turn {label}]")
            lines.append(content.strip())

        return MemoryResult(
            system_name=self.name,
            memory="\n\n".join(lines) if request.past_user_turns else "",
            metadata={
                "past_turn_count": len(request.past_user_turns),
                "included_turn_count": len(request.past_user_turns),
                "format": "chronological_user_turns",
            },
        )

