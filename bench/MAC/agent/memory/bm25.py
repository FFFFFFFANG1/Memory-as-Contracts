"""BM25 retrieval over individual past user turns."""

from __future__ import annotations

import math
import os
from collections import Counter
from dataclasses import dataclass

from bench.MAC.agent.memory.base import MemoryRequest, MemoryResult
from bench.MAC.agent.memory.retrieval import (
    MemoryDocument,
    ScoredDocument,
    clamp_top_k,
    documents_from_turns,
    format_retrieved_memory,
    tokenize,
)


@dataclass(frozen=True, slots=True)
class BM25Config:
    top_k: int = 10
    max_chars: int | None = None
    k1: float = 1.5
    b: float = 0.75


def bm25_config_from_env() -> BM25Config:
    max_chars_raw = os.getenv("MAC_MEMORY_MAX_CHARS")
    max_chars = int(max_chars_raw) if max_chars_raw and max_chars_raw.isdigit() else None
    return BM25Config(
        top_k=clamp_top_k(os.getenv("MAC_MEMORY_TOP_K"), default=10),
        max_chars=max_chars,
    )


class BM25Index:
    """Small in-process BM25 index where each document is one user turn."""

    def __init__(self, documents: list[MemoryDocument], *, k1: float = 1.5, b: float = 0.75) -> None:
        self.documents = documents
        self.k1 = k1
        self.b = b
        self.term_frequencies = [Counter(tokenize(document.content)) for document in documents]
        self.lengths = [sum(frequencies.values()) for frequencies in self.term_frequencies]
        self.average_length = sum(self.lengths) / len(self.lengths) if self.lengths else 0.0
        self.idf = self._build_idf()

    def _build_idf(self) -> dict[str, float]:
        document_frequency: Counter[str] = Counter()
        for frequencies in self.term_frequencies:
            document_frequency.update(frequencies.keys())
        document_count = len(self.documents)
        return {
            term: math.log(1.0 + (document_count - frequency + 0.5) / (frequency + 0.5))
            for term, frequency in document_frequency.items()
        }

    def search(self, query: str, *, top_k: int) -> list[ScoredDocument]:
        query_terms = tokenize(query)
        if not query_terms or not self.documents:
            return []

        scored: list[tuple[MemoryDocument, float]] = []
        for document, frequencies, length in zip(
            self.documents,
            self.term_frequencies,
            self.lengths,
            strict=True,
        ):
            score = 0.0
            for term in query_terms:
                frequency = frequencies.get(term, 0)
                if frequency == 0:
                    continue
                denominator = frequency + self.k1 * (
                    1.0 - self.b + self.b * length / (self.average_length or 1.0)
                )
                score += self.idf.get(term, 0.0) * (frequency * (self.k1 + 1.0) / denominator)
            if score > 0.0:
                scored.append((document, score))

        ranked = sorted(scored, key=lambda item: (-item[1], item[0].ordinal))[:top_k]
        return [
            ScoredDocument(document=document, score=score, rank=rank)
            for rank, (document, score) in enumerate(ranked, start=1)
        ]


class BM25MemoryProvider:
    name = "bm25"

    def __init__(self, config: BM25Config | None = None) -> None:
        self.config = config or bm25_config_from_env()

    def build_memory(self, request: MemoryRequest) -> MemoryResult:
        documents = documents_from_turns(request.past_user_turns)
        index = BM25Index(documents, k1=self.config.k1, b=self.config.b)
        scored_documents = index.search(request.user_prompt, top_k=self.config.top_k)
        return MemoryResult(
            system_name=self.name,
            memory=format_retrieved_memory(
                scored_documents,
                past_turn_count=len(request.past_user_turns),
                max_chars=self.config.max_chars,
            ),
            metadata={
                "past_turn_count": len(request.past_user_turns),
                "indexed_turn_count": len(documents),
                "included_turn_count": len(scored_documents),
                "retrieval_unit": "user_turn",
                "top_k": self.config.top_k,
                "ranker": "bm25",
                "matches": [
                    {
                        "turn_index": scored.document.turn_index,
                        "score": scored.score,
                        "rank": scored.rank,
                    }
                    for scored in scored_documents
                ],
            },
        )
