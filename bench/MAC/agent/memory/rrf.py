"""Reciprocal rank fusion over BM25 and embedding user-turn retrieval."""

from __future__ import annotations

import os
from dataclasses import dataclass

from bench.MAC.agent.memory.base import MemoryRequest, MemoryResult
from bench.MAC.agent.memory.bm25 import BM25Index
from bench.MAC.agent.memory.embedding import (
    EmbeddingConfig,
    EmbeddingFunction,
    EmbeddingMemoryProvider,
    embedding_config_from_env,
)
from bench.MAC.agent.memory.retrieval import (
    MemoryDocument,
    ScoredDocument,
    clamp_top_k,
    documents_from_turns,
    format_retrieved_memory,
)


@dataclass(frozen=True, slots=True)
class RRFConfig:
    top_k: int = 10
    max_chars: int | None = None
    rrf_k: int = 60
    embedding: EmbeddingConfig | None = None


def rrf_config_from_env() -> RRFConfig:
    max_chars_raw = os.getenv("MAC_MEMORY_MAX_CHARS")
    max_chars = int(max_chars_raw) if max_chars_raw and max_chars_raw.isdigit() else None
    rrf_k_raw = os.getenv("MAC_RRF_K")
    rrf_k = int(rrf_k_raw) if rrf_k_raw and rrf_k_raw.isdigit() else 60
    return RRFConfig(
        top_k=clamp_top_k(os.getenv("MAC_MEMORY_TOP_K"), default=10),
        max_chars=max_chars,
        rrf_k=max(1, rrf_k),
    )


def _rank_map(results: list[ScoredDocument]) -> dict[str, int]:
    return {result.document.doc_id: result.rank for result in results}


def reciprocal_rank_fusion(
    *,
    documents: list[MemoryDocument],
    ranked_lists: list[list[ScoredDocument]],
    rrf_k: int = 60,
    top_k: int = 10,
) -> list[ScoredDocument]:
    by_id = {document.doc_id: document for document in documents}
    scores = {document.doc_id: 0.0 for document in documents}
    for ranked in ranked_lists:
        for scored in ranked:
            scores[scored.document.doc_id] += 1.0 / (rrf_k + scored.rank)

    ranked = [(by_id[doc_id], score) for doc_id, score in scores.items() if score > 0.0]
    ranked = sorted(ranked, key=lambda item: (-item[1], item[0].ordinal))[:top_k]
    return [
        ScoredDocument(document=document, score=score, rank=rank)
        for rank, (document, score) in enumerate(ranked, start=1)
    ]


class RRFMemoryProvider:
    name = "rrf"

    def __init__(
        self,
        config: RRFConfig | None = None,
        *,
        embed: EmbeddingFunction | None = None,
    ) -> None:
        self.config = config or rrf_config_from_env()
        embedding_config = self.config.embedding or embedding_config_from_env()
        self.embedding_provider = EmbeddingMemoryProvider(config=embedding_config, embed=embed)

    def build_memory(self, request: MemoryRequest) -> MemoryResult:
        documents = documents_from_turns(request.past_user_turns)
        if not documents:
            return MemoryResult(
                system_name=self.name,
                memory="",
                metadata={
                    "past_turn_count": len(request.past_user_turns),
                    "indexed_turn_count": 0,
                    "included_turn_count": 0,
                    "retrieval_unit": "user_turn",
                    "top_k": self.config.top_k,
                    "ranker": "rrf",
                    "components": ["bm25", "embedding"],
                },
            )

        bm25_results = BM25Index(documents).search(request.user_prompt, top_k=len(documents))
        embedding_index = self.embedding_provider.build_index(request, documents)
        embedding_results = self.embedding_provider.search_index(
            request,
            embedding_index,
            top_k=len(documents),
        )
        fused_documents = reciprocal_rank_fusion(
            documents=documents,
            ranked_lists=[bm25_results, embedding_results],
            rrf_k=self.config.rrf_k,
            top_k=self.config.top_k,
        )
        bm25_ranks = _rank_map(bm25_results)
        embedding_ranks = _rank_map(embedding_results)
        return MemoryResult(
            system_name=self.name,
            memory=format_retrieved_memory(
                fused_documents,
                past_turn_count=len(request.past_user_turns),
                max_chars=self.config.max_chars,
            ),
            metadata={
                "past_turn_count": len(request.past_user_turns),
                "indexed_turn_count": len(documents),
                "included_turn_count": len(fused_documents),
                "retrieval_unit": "user_turn",
                "top_k": self.config.top_k,
                "ranker": "rrf",
                "rrf_k": self.config.rrf_k,
                "components": ["bm25", "embedding"],
                "embedding_model": self.embedding_provider.config.model,
                "embedding_cache_hit": embedding_index.cache_hit,
                "embedding_cache_path": str(embedding_index.path) if embedding_index.path else None,
                "matches": [
                    {
                        "turn_index": scored.document.turn_index,
                        "score": scored.score,
                        "rank": scored.rank,
                        "bm25_rank": bm25_ranks.get(scored.document.doc_id),
                        "embedding_rank": embedding_ranks.get(scored.document.doc_id),
                    }
                    for scored in fused_documents
                ],
            },
        )
