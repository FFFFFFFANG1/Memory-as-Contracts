"""Shared helpers for retrieval-style memory providers."""

from __future__ import annotations

import hashlib
import math
import re
from dataclasses import dataclass
from typing import Any


RETRIEVAL_MEMORY_PREAMBLE = (
    "Below are relevant previous user messages retrieved for the current task. "
    "Learn and follow any effective user requirements that still apply."
)

_TOKEN_RE = re.compile(r"[A-Za-z0-9_]+")


@dataclass(frozen=True, slots=True)
class MemoryDocument:
    doc_id: str
    label: str
    content: str
    ordinal: int
    turn_index: str


@dataclass(frozen=True, slots=True)
class ScoredDocument:
    document: MemoryDocument
    score: float
    rank: int


def tokenize(text: str) -> list[str]:
    return [match.group(0).lower() for match in _TOKEN_RE.finditer(text)]


def turn_label(turn: dict[str, Any], fallback_index: int) -> str:
    value = turn.get("turn_index", fallback_index)
    return str(value)


def documents_from_turns(turns: list[dict[str, Any]]) -> list[MemoryDocument]:
    documents: list[MemoryDocument] = []
    for ordinal, turn in enumerate(turns):
        content = turn.get("content")
        if not isinstance(content, str) or not content.strip():
            continue
        label = turn_label(turn, ordinal)
        normalized = content.strip()
        documents.append(
            MemoryDocument(
                doc_id=stable_hash(f"{label}\n{normalized}"),
                label=f"past_user_turn {label}",
                content=normalized,
                ordinal=ordinal,
                turn_index=label,
            )
        )
    return documents


def stable_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def corpus_fingerprint(*, task_uid: str, documents: list[MemoryDocument], model: str = "") -> str:
    parts = [task_uid, model]
    parts.extend(f"{document.turn_index}\0{document.doc_id}" for document in documents)
    return stable_hash("\n".join(parts))


def clamp_top_k(value: int | str | None, *, default: int = 10) -> int:
    if value is None:
        return default
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(1, parsed)


def format_retrieved_memory(
    scored_documents: list[ScoredDocument],
    *,
    past_turn_count: int,
    max_chars: int | None = None,
) -> str:
    if past_turn_count == 0 or not scored_documents:
        return ""

    remaining = max_chars if max_chars is not None and max_chars > 0 else None
    blocks = [RETRIEVAL_MEMORY_PREAMBLE]
    for scored in sorted(scored_documents, key=lambda item: item.document.ordinal):
        header = f"[{scored.document.label}]"
        content = scored.document.content
        block = f"{header}\n{content}"
        if remaining is not None:
            if remaining <= 0:
                break
            if len(block) > remaining:
                if remaining <= len(header) + 5:
                    break
                content_budget = remaining - len(header) - 5
                block = f"{header}\n{content[:content_budget].rstrip()}..."
            remaining -= len(block)
        blocks.append(block)

    return "\n\n".join(blocks) if len(blocks) > 1 else ""


def cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    dot = 0.0
    left_norm = 0.0
    right_norm = 0.0
    for left_value, right_value in zip(left, right, strict=True):
        dot += left_value * right_value
        left_norm += left_value * left_value
        right_norm += right_value * right_value
    if left_norm == 0.0 or right_norm == 0.0:
        return 0.0
    return dot / (math.sqrt(left_norm) * math.sqrt(right_norm))
