"""Embedding retrieval over individual past user turns with persistent indexes."""

from __future__ import annotations

import json
import os
import re
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from bench.MAC.agent.memory.base import MemoryRequest, MemoryResult
from bench.MAC.agent.memory.retrieval import (
    MemoryDocument,
    ScoredDocument,
    clamp_top_k,
    corpus_fingerprint,
    cosine_similarity,
    documents_from_turns,
    format_retrieved_memory,
)


EmbeddingFunction = Callable[[list[str], str], list[list[float]]]

DEFAULT_EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_CACHE_SCHEMA_VERSION = "MACEmbeddingIndexV1"
DEFAULT_EMBEDDING_CACHE_DIR = Path(__file__).resolve().parents[2] / ".cache" / "memory_embeddings"
_SAFE_PATH_RE = re.compile(r"[^A-Za-z0-9_.-]+")


@dataclass(frozen=True, slots=True)
class EmbeddingConfig:
    top_k: int = 10
    max_chars: int | None = None
    model: str = DEFAULT_EMBEDDING_MODEL
    cache_dir: Path = DEFAULT_EMBEDDING_CACHE_DIR
    api_key_env: str = "LLM_API_KEY"
    base_url: str | None = None


@dataclass(frozen=True, slots=True)
class EmbeddingIndex:
    documents: list[MemoryDocument]
    embeddings: list[list[float]]
    fingerprint: str
    cache_hit: bool
    path: Path | None


def embedding_config_from_env() -> EmbeddingConfig:
    max_chars_raw = os.getenv("MAC_MEMORY_MAX_CHARS")
    max_chars = int(max_chars_raw) if max_chars_raw and max_chars_raw.isdigit() else None
    cache_dir = Path(os.getenv("MAC_EMBEDDING_CACHE_DIR", str(DEFAULT_EMBEDDING_CACHE_DIR)))
    return EmbeddingConfig(
        top_k=clamp_top_k(os.getenv("MAC_MEMORY_TOP_K"), default=10),
        max_chars=max_chars,
        model=os.getenv("MAC_EMBEDDING_MODEL") or os.getenv("EMBEDDING_MODEL") or DEFAULT_EMBEDDING_MODEL,
        cache_dir=cache_dir,
        api_key_env=os.getenv("MAC_EMBEDDING_API_KEY_ENV", "EMBEDDING_API"),
        base_url=os.getenv("MAC_EMBEDDING_BASE_URL") or os.getenv("EMBEDDING_BASE"),
    )


def _safe_path_part(value: str) -> str:
    cleaned = _SAFE_PATH_RE.sub("_", value.strip())
    return cleaned[:80] or "task"


class OpenAIEmbeddingClient:
    """Synchronous OpenAI-compatible embeddings client."""

    def __init__(self, *, api_key_env: str, base_url: str | None) -> None:
        self.api_key_env = api_key_env
        self.base_url = base_url
        self._client: Any | None = None

    def _client_or_raise(self) -> Any:
        if self._client is not None:
            return self._client
        from openai import OpenAI

        api_key = os.getenv(self.api_key_env)
        if not api_key:
            raise RuntimeError(f"Missing API key env var for embeddings: {self.api_key_env}")
        self._client = OpenAI(api_key=api_key, base_url=self.base_url)
        return self._client

    def __call__(self, texts: list[str], model: str) -> list[list[float]]:
        response = self._client_or_raise().embeddings.create(model=model, input=texts)
        return [list(item.embedding) for item in response.data]


class EmbeddingMemoryProvider:
    name = "embedding"

    def __init__(
        self,
        config: EmbeddingConfig | None = None,
        *,
        embed: EmbeddingFunction | None = None,
    ) -> None:
        self.config = config or embedding_config_from_env()
        self._embed = embed
        self._lock = threading.RLock()

    def _embedder(self, request: MemoryRequest) -> EmbeddingFunction:
        if self._embed is not None:
            return self._embed
        memory_llm = request.memory_llm or {}
        api_key_env = str(self.config.api_key_env or memory_llm.get("api_key_env") or "EMBEDDING_API")
        base_url = self.config.base_url or memory_llm.get("base_url")
        client = OpenAIEmbeddingClient(api_key_env=api_key_env, base_url=str(base_url) if base_url else None)
        return client

    def _cache_path(self, *, task_uid: str, fingerprint: str) -> Path:
        filename = f"{_safe_path_part(task_uid)}-{fingerprint[:16]}.json"
        return self.config.cache_dir / filename

    def _load_index(
        self,
        *,
        path: Path,
        fingerprint: str,
        documents: list[MemoryDocument],
    ) -> EmbeddingIndex | None:
        if not path.exists():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if not isinstance(payload, dict):
            return None
        if payload.get("schema_version") != EMBEDDING_CACHE_SCHEMA_VERSION:
            return None
        if payload.get("fingerprint") != fingerprint or payload.get("model") != self.config.model:
            return None
        raw_documents = payload.get("documents")
        if not isinstance(raw_documents, list) or len(raw_documents) != len(documents):
            return None

        embeddings: list[list[float]] = []
        for raw, document in zip(raw_documents, documents, strict=True):
            if not isinstance(raw, dict) or raw.get("doc_id") != document.doc_id:
                return None
            embedding = raw.get("embedding")
            if not isinstance(embedding, list) or not all(isinstance(value, int | float) for value in embedding):
                return None
            embeddings.append([float(value) for value in embedding])
        return EmbeddingIndex(
            documents=documents,
            embeddings=embeddings,
            fingerprint=fingerprint,
            cache_hit=True,
            path=path,
        )

    def _write_index(self, *, path: Path, index: EmbeddingIndex) -> None:
        payload = {
            "schema_version": EMBEDDING_CACHE_SCHEMA_VERSION,
            "fingerprint": index.fingerprint,
            "model": self.config.model,
            "retrieval_unit": "user_turn",
            "documents": [
                {
                    "doc_id": document.doc_id,
                    "label": document.label,
                    "ordinal": document.ordinal,
                    "turn_index": document.turn_index,
                    "content": document.content,
                    "embedding": embedding,
                }
                for document, embedding in zip(index.documents, index.embeddings, strict=True)
            ],
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = path.with_suffix(path.suffix + ".tmp")
        tmp_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        tmp_path.replace(path)

    def build_index(self, request: MemoryRequest, documents: list[MemoryDocument]) -> EmbeddingIndex:
        fingerprint = corpus_fingerprint(
            task_uid=request.task_uid,
            documents=documents,
            model=self.config.model,
        )
        path = self._cache_path(task_uid=request.task_uid, fingerprint=fingerprint)
        with self._lock:
            cached = self._load_index(path=path, fingerprint=fingerprint, documents=documents)
            if cached is not None:
                return cached

        embeddings = self._embedder(request)([document.content for document in documents], self.config.model)
        if len(embeddings) != len(documents):
            raise RuntimeError(
                f"Embedding provider returned {len(embeddings)} vectors for {len(documents)} user turns"
            )
        index = EmbeddingIndex(
            documents=documents,
            embeddings=embeddings,
            fingerprint=fingerprint,
            cache_hit=False,
            path=path,
        )
        with self._lock:
            self._write_index(path=path, index=index)
        return index

    def search_index(
        self,
        request: MemoryRequest,
        index: EmbeddingIndex,
        *,
        top_k: int | None = None,
    ) -> list[ScoredDocument]:
        query_embedding = self._embedder(request)([request.user_prompt], self.config.model)[0]
        scored = [
            (document, cosine_similarity(query_embedding, embedding))
            for document, embedding in zip(index.documents, index.embeddings, strict=True)
        ]
        ranked = sorted(scored, key=lambda item: (-item[1], item[0].ordinal))[: top_k or self.config.top_k]
        return [
            ScoredDocument(document=document, score=score, rank=rank)
            for rank, (document, score) in enumerate(ranked, start=1)
        ]

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
                    "ranker": "embedding",
                    "embedding_model": self.config.model,
                    "cache_hit": False,
                },
            )

        index = self.build_index(request, documents)
        scored_documents = self.search_index(request, index)
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
                "ranker": "embedding",
                "embedding_model": self.config.model,
                "cache_hit": index.cache_hit,
                "cache_path": str(index.path) if index.path else None,
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
