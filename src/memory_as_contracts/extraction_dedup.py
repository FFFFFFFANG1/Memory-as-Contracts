from __future__ import annotations

import sqlite3
import re

from memory_as_contracts.extractor import ExtractionContext
from memory_as_contracts.models import Contract, ContractStatus
from memory_as_contracts.store import ContractStore


MAX_SEGMENT_QUERY_TOKENS = 18
MIN_SEGMENT_TOKENS = 2

_STOP_WORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "be",
    "but",
    "can",
    "for",
    "from",
    "i",
    "if",
    "in",
    "is",
    "it",
    "me",
    "my",
    "of",
    "on",
    "or",
    "please",
    "the",
    "this",
    "to",
    "turn",
    "we",
    "with",
    "you",
}


def build_similar_rule_context(
    store: ContractStore,
    text: str,
    context: ExtractionContext,
    *,
    limit: int = 5,
) -> str | None:
    """Return rendered similar-rule context for extractor deduplication."""
    ranked: dict[str, tuple[Contract, float]] = {}
    for segment in _segments(text):
        query = _fts_query(segment)
        if query is None:
            continue
        try:
            matches = store.search_contracts_ranked_text(
                query,
                statuses=[ContractStatus.ACTIVE, ContractStatus.PENDING_CONFLICT],
                limit=limit,
            )
        except sqlite3.OperationalError:
            continue
        for match in matches:
            contract = match.contract
            if not _scope_can_apply_to_extraction_context(contract, context):
                continue
            previous = ranked.get(contract.id)
            if previous is None or match.rank < previous[1]:
                ranked[contract.id] = (contract, match.rank)
    contracts = [
        contract
        for contract, _rank in sorted(
            ranked.values(),
            key=lambda item: (item[1], item[0].source.created_at, item[0].id),
        )[:limit]
    ]
    if not contracts:
        return None
    return _render_similar_rules(contracts)


def _segments(text: str) -> list[str]:
    normalized = re.sub(r"\[SEP\]", "\n", text, flags=re.I)
    parts = re.split(r"(?:\n+|[;.!?。！？]+|\s+-\s+|\s+\*\s+)", normalized)
    return [part.strip(" \t\r\n-•*") for part in parts if part.strip(" \t\r\n-•*")]


def _fts_query(text: str) -> str | None:
    tokens: list[str] = []
    seen: set[str] = set()
    for token in re.findall(r"[a-z0-9_]+", text.lower()):
        if len(token) < 2 or token in _STOP_WORDS or token in seen:
            continue
        tokens.append(token)
        seen.add(token)
        if len(tokens) >= MAX_SEGMENT_QUERY_TOKENS:
            break
    if len(tokens) < MIN_SEGMENT_TOKENS:
        return None
    return " OR ".join(tokens)


def _scope_can_apply_to_extraction_context(
    contract: Contract,
    context: ExtractionContext,
) -> bool:
    user_id = context.normalization.user_id
    if user_id and contract.scope.user_id and contract.scope.user_id != user_id:
        return False
    project = context.normalization.repo or context.normalization.workspace
    if contract.scope.project and project and contract.scope.project != project:
        return False
    if (
        context.conversation_id
        and contract.source.conversation_id
        and contract.source.conversation_id != context.conversation_id
    ):
        return False
    source_session_id = contract.source.metadata.get("session_id")
    if context.session_id and source_session_id and source_session_id != context.session_id:
        return False
    return True


def _render_similar_rules(contracts: list[Contract]) -> str:
    lines = [
        "Existing similar rules; do not re-emit duplicates. "
        "Only extract genuinely new constraints."
    ]
    for index, contract in enumerate(contracts, start=1):
        scope = contract.scope.level.value
        lines.append(
            f"{index}. [{contract.id}] {contract.kind.value} "
            f"scope={scope}: {contract.text}"
        )
    return "\n".join(lines)
