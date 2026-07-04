"""Heuristic user replies when a SOPBench agent asks for clarification."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

_CLARIFICATION_PATTERNS = re.compile(
    r"\?"
    r"|\bplease provide\b"
    r"|\bcould you\b"
    r"|\bcan you tell\b"
    r"|\bneed (?:your|the|more)\b"
    r"|\bwhich (?:state|one)\b"
    r"|\bclarif\w*\b"
    r"|\blet me know\b"
    r"|\bwhat is your\b"
    r"|\bprovide (?:the|your)\b",
    re.IGNORECASE,
)

def is_agent_clarification_request(text: str) -> bool:
    """Return True when send_message text looks like the agent is asking the user."""
    cleaned = text.strip()
    if not cleaned:
        return False
    return bool(_CLARIFICATION_PATTERNS.search(cleaned))


def collect_known_user_information(
    *,
    user_prompt: str,
    user_known: dict[str, Any] | None = None,
) -> str:
    """Summarize task-bound user information for the current evaluation turn."""
    parts: list[str] = []

    if user_known:
        parts.append(json.dumps(user_known, ensure_ascii=False, sort_keys=True))

    if user_prompt.strip():
        parts.append(user_prompt.strip())

    if parts:
        return ". ".join(parts)
    return "nothing further beyond what I already shared."


def build_clarification_reply(
    *,
    user_prompt: str,
    user_known: dict[str, Any] | None = None,
) -> str:
    known = collect_known_user_information(
        user_prompt=user_prompt,
        user_known=user_known,
    )
    return f"All information I know is {known}"


@dataclass(slots=True)
class SOPClarificationContext:
    user_prompt: str
    past_user_turns: list[dict[str, Any]]
    user_known: dict[str, Any]

    @classmethod
    def from_task(cls, task: dict[str, Any], *, user_prompt: str, past_user_turns: list[dict[str, Any]]) -> SOPClarificationContext:
        patched = task.get("patched_sopbench_task") or {}
        user_known = patched.get("user_known") if isinstance(patched, dict) else {}
        if not isinstance(user_known, dict):
            user_known = {}
        return cls(
            user_prompt=user_prompt,
            past_user_turns=list(past_user_turns),
            user_known=user_known,
        )

    def reply_for(self, agent_response: str) -> str | None:
        if not is_agent_clarification_request(agent_response):
            return None
        return build_clarification_reply(
            user_prompt=self.user_prompt,
            user_known=self.user_known,
        )
