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

_REQUEST_TURN_KINDS = frozenset({"carryover", "actual_evaluation"})


def is_agent_clarification_request(text: str) -> bool:
    """Return True when send_message text looks like the agent is asking the user."""
    cleaned = text.strip()
    if not cleaned:
        return False
    return bool(_CLARIFICATION_PATTERNS.search(cleaned))


def _dedupe_preserve_order(items: list[str]) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        unique.append(item)
    return unique


def collect_known_user_information(
    *,
    user_prompt: str,
    past_user_turns: list[dict[str, Any]] | None = None,
    user_known: dict[str, Any] | None = None,
    max_request_snippets: int = 5,
) -> str:
    """Summarize information already present in user turns and user_known."""
    parts: list[str] = []

    if user_known:
        parts.append(json.dumps(user_known, ensure_ascii=False, sort_keys=True))

    request_snippets: list[str] = []
    for turn in past_user_turns or []:
        if not isinstance(turn, dict):
            continue
        kind = str(turn.get("kind") or "")
        phase = str(turn.get("phase") or "")
        if kind not in _REQUEST_TURN_KINDS and phase != "evaluation":
            continue
        content = turn.get("content")
        if isinstance(content, str) and content.strip():
            request_snippets.append(content.strip())

    if user_prompt.strip():
        request_snippets.append(user_prompt.strip())

    request_snippets = _dedupe_preserve_order(request_snippets)
    if request_snippets:
        tail = request_snippets[-max_request_snippets:]
        parts.append("From our conversation: " + " | ".join(tail))

    if parts:
        return ". ".join(parts)
    if user_prompt.strip():
        return user_prompt.strip()
    return "nothing further beyond what I already shared."


def build_clarification_reply(
    *,
    user_prompt: str,
    past_user_turns: list[dict[str, Any]] | None = None,
    user_known: dict[str, Any] | None = None,
) -> str:
    known = collect_known_user_information(
        user_prompt=user_prompt,
        past_user_turns=past_user_turns,
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
            past_user_turns=self.past_user_turns,
            user_known=self.user_known,
        )
