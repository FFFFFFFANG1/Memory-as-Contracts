"""Mem0 OSS-backed memory provider for MAC evaluation."""

from __future__ import annotations

import json
import os
import sys
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from bench.MAC.agent.memory.base import MemoryRequest, MemoryResult
from bench.MAC.agent.memory.retrieval import (
    MemoryDocument,
    ScoredDocument,
    clamp_top_k,
    corpus_fingerprint,
    documents_from_turns,
    format_retrieved_memory,
    stable_hash,
)


MEM0_REPO_DIR = Path(__file__).resolve().parent / "repo" / "mem0"
DEFAULT_MEM0_INGEST_CACHE_DIR = Path(__file__).resolve().parents[2] / ".cache" / "mem0_ingest"
DEFAULT_MEM0_FAISS_DIR = Path(__file__).resolve().parents[2] / ".cache" / "mem0_faiss"
DEFAULT_MEM0_HISTORY_DB = Path(__file__).resolve().parents[2] / ".cache" / "mem0_history.db"
DEFAULT_MEM0_INGEST_BATCH_SIZE = 10
MEM0_INGEST_SCHEMA_VERSION = "MACMem0IngestV3"


class Mem0Client(Protocol):
    def add(self, messages: Any, **kwargs: Any) -> Any:
        """Add one memory payload to Mem0."""

    def search(self, query: str, **kwargs: Any) -> Any:
        """Search Mem0 memories."""

    def delete_all(self, **kwargs: Any) -> Any:
        """Delete scoped memories."""


@dataclass(frozen=True, slots=True)
class Mem0Config:
    top_k: int = 10
    max_chars: int | None = None
    user_id_prefix: str = "mac-bench"
    ingest_cache_dir: Path = DEFAULT_MEM0_INGEST_CACHE_DIR
    faiss_dir: Path = DEFAULT_MEM0_FAISS_DIR
    history_db_path: Path = DEFAULT_MEM0_HISTORY_DB
    rerank: bool = False
    threshold: float | None = None
    force_reingest: bool = False
    ingest_batch_size: int = DEFAULT_MEM0_INGEST_BATCH_SIZE
    infer: bool = True
    mem_llm_model: str = ""
    mem_api_key_env: str = "MEM_API_KEY"
    mem_base_url: str | None = None
    embedding_model: str = ""
    embedding_api_key_env: str = "EMBEDDING_API"
    embedding_base_url: str | None = None
    embedding_dims: int = 1024


def mem0_config_from_env() -> Mem0Config:
    max_chars_raw = os.getenv("MAC_MEMORY_MAX_CHARS")
    max_chars = int(max_chars_raw) if max_chars_raw and max_chars_raw.isdigit() else None
    threshold_raw = os.getenv("MAC_MEM0_THRESHOLD")
    threshold = float(threshold_raw) if threshold_raw else None
    embedding_dims_raw = os.getenv("MAC_MEM0_EMBEDDING_DIMS", "1024")
    embedding_dims = int(embedding_dims_raw) if embedding_dims_raw.isdigit() else 1024
    infer_raw = os.getenv("MAC_MEM0_INFER", "true").strip().lower()
    return Mem0Config(
        top_k=clamp_top_k(os.getenv("MAC_MEMORY_TOP_K"), default=10),
        max_chars=max_chars,
        user_id_prefix=os.getenv("MAC_MEM0_USER_ID_PREFIX", "mac-bench"),
        ingest_cache_dir=Path(
            os.getenv("MAC_MEM0_INGEST_CACHE_DIR", str(DEFAULT_MEM0_INGEST_CACHE_DIR))
        ),
        faiss_dir=Path(os.getenv("MAC_MEM0_FAISS_DIR", str(DEFAULT_MEM0_FAISS_DIR))),
        history_db_path=Path(os.getenv("MAC_MEM0_HISTORY_DB", str(DEFAULT_MEM0_HISTORY_DB))),
        rerank=os.getenv("MAC_MEM0_RERANK", "").strip().lower() in {"1", "true", "yes"},
        threshold=threshold,
        force_reingest=os.getenv("MAC_MEM0_FORCE_REINGEST", "").strip().lower()
        in {"1", "true", "yes"},
        infer=infer_raw not in {"0", "false", "no"},
        mem_llm_model=os.getenv("MEM_LLM_MODEL", ""),
        mem_api_key_env=os.getenv("MAC_MEM_API_KEY_ENV", "MEM_API_KEY"),
        mem_base_url=os.getenv("MEM_BASE_URL"),
        embedding_model=os.getenv("EMBEDDING_MODEL") or os.getenv("MAC_EMBEDDING_MODEL") or "",
        embedding_api_key_env=os.getenv("MAC_EMBEDDING_API_KEY_ENV", "EMBEDDING_API"),
        embedding_base_url=os.getenv("EMBEDDING_BASE") or os.getenv("MAC_EMBEDDING_BASE_URL"),
        embedding_dims=embedding_dims,
    )


def _ensure_mem0_repo_on_path() -> None:
    if MEM0_REPO_DIR.exists():
        repo_root = str(MEM0_REPO_DIR)
        if repo_root not in sys.path:
            sys.path.insert(0, repo_root)


def _require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


class MemoryOssAdapter:
    """Lazy adapter around the Mem0 OSS `Memory` class."""

    def __init__(self, config: Mem0Config) -> None:
        self.config = config
        self._memory: Any | None = None

    def _build_config(self) -> dict[str, Any]:
        mem_api_key = _require_env(self.config.mem_api_key_env)
        embed_api_key = _require_env(self.config.embedding_api_key_env)
        if not self.config.mem_llm_model:
            raise RuntimeError("Missing MEM_LLM_MODEL for Mem0 OSS infer mode")
        if not self.config.embedding_model:
            raise RuntimeError("Missing EMBEDDING_MODEL for Mem0 OSS")
        self.config.faiss_dir.mkdir(parents=True, exist_ok=True)
        self.config.history_db_path.parent.mkdir(parents=True, exist_ok=True)
        return {
            "llm": {
                "provider": "openai",
                "config": {
                    "model": self.config.mem_llm_model,
                    "api_key": mem_api_key,
                    "openai_base_url": self.config.mem_base_url,
                    "temperature": 0.0,
                },
            },
            "embedder": {
                "provider": "openai",
                "config": {
                    "model": self.config.embedding_model,
                    "api_key": embed_api_key,
                    "openai_base_url": self.config.embedding_base_url,
                    "embedding_dims": self.config.embedding_dims,
                },
            },
            "vector_store": {
                "provider": "faiss",
                "config": {
                    "path": str(self.config.faiss_dir),
                    "collection_name": "mac_mem0",
                    "embedding_model_dims": self.config.embedding_dims,
                    "distance_strategy": "cosine",
                },
            },
            "history_db_path": str(self.config.history_db_path),
        }

    def _memory_or_raise(self) -> Any:
        if self._memory is not None:
            return self._memory
        _ensure_mem0_repo_on_path()
        from mem0 import Memory

        self._memory = Memory.from_config(self._build_config())
        return self._memory

    def add(self, messages: Any, **kwargs: Any) -> Any:
        return self._memory_or_raise().add(messages, **kwargs)

    def search(self, query: str, **kwargs: Any) -> Any:
        return self._memory_or_raise().search(query, **kwargs)

    def delete_all(self, **kwargs: Any) -> Any:
        return self._memory_or_raise().delete_all(**kwargs)


def _mem0_user_id(config: Mem0Config, request: MemoryRequest) -> str:
    raw = f"{config.user_id_prefix}:{request.agent}:{request.task_uid}"
    return f"{config.user_id_prefix}-{stable_hash(raw)[:24]}"


def _manifest_path(config: Mem0Config, *, user_id: str, fingerprint: str) -> Path:
    return config.ingest_cache_dir / f"{user_id}-{fingerprint[:16]}.json"


def _result_items(response: Any) -> list[dict[str, Any]]:
    if isinstance(response, dict):
        raw_results = response.get("results", [])
    elif isinstance(response, list):
        raw_results = response
    else:
        raw_results = []
    return [item for item in raw_results if isinstance(item, dict)]


def _result_memory(item: dict[str, Any]) -> str:
    value = item.get("memory") or item.get("content") or item.get("text")
    return value.strip() if isinstance(value, str) else ""


def _chunk_documents(
    documents: list[MemoryDocument],
    batch_size: int,
) -> list[list[MemoryDocument]]:
    size = batch_size if batch_size > 0 else DEFAULT_MEM0_INGEST_BATCH_SIZE
    return [documents[index : index + size] for index in range(0, len(documents), size)]


def _batch_messages(documents: list[MemoryDocument]) -> list[dict[str, str]]:
    return [{"role": "user", "content": document.content} for document in documents]


class Mem0MemoryProvider:
    name = "mem0"

    def __init__(
        self,
        config: Mem0Config | None = None,
        *,
        client: Mem0Client | None = None,
    ) -> None:
        self.config = config or mem0_config_from_env()
        self._client = client
        self._lock = threading.RLock()

    def _client_or_raise(self) -> Mem0Client:
        if self._client is not None:
            return self._client
        self._client = MemoryOssAdapter(self.config)
        return self._client

    def _ingest_documents(
        self,
        *,
        request: MemoryRequest,
        documents: list[MemoryDocument],
        user_id: str,
        fingerprint: str,
    ) -> tuple[bool, Path]:
        path = _manifest_path(self.config, user_id=user_id, fingerprint=fingerprint)
        if not self.config.force_reingest and path.exists():
            return True, path

        client = self._client_or_raise()
        client.delete_all(user_id=user_id)
        batches = _chunk_documents(documents, self.config.ingest_batch_size)
        for batch_index, batch in enumerate(batches):
            client.add(
                _batch_messages(batch),
                user_id=user_id,
                infer=self.config.infer,
                metadata={
                    "task_uid": request.task_uid,
                    "agent": request.agent,
                    "batch_index": batch_index,
                    "batch_size": len(batch),
                    "doc_ids": [document.doc_id for document in batch],
                    "turn_indices": [document.turn_index for document in batch],
                    "retrieval_unit": "user_turn",
                    "ingest_unit": "user_turn_batch",
                },
            )

        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": MEM0_INGEST_SCHEMA_VERSION,
            "fingerprint": fingerprint,
            "user_id": user_id,
            "task_uid": request.task_uid,
            "agent": request.agent,
            "retrieval_unit": "user_turn",
            "ingest_unit": "user_turn_batch",
            "backend": "oss",
            "infer": self.config.infer,
            "ingest_batch_size": self.config.ingest_batch_size,
            "ingest_batch_count": len(batches),
            "ingested_turn_count": len(documents),
            "doc_ids": [document.doc_id for document in documents],
        }
        tmp_path = path.with_suffix(path.suffix + ".tmp")
        tmp_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        tmp_path.replace(path)
        return False, path

    def _search(self, *, request: MemoryRequest, user_id: str) -> list[ScoredDocument]:
        kwargs: dict[str, Any] = {
            "filters": {"user_id": user_id},
            "top_k": self.config.top_k,
            "rerank": self.config.rerank,
        }
        if self.config.threshold is not None:
            kwargs["threshold"] = self.config.threshold
        response = self._client_or_raise().search(request.user_prompt, **kwargs)

        scored: list[ScoredDocument] = []
        for rank, item in enumerate(_result_items(response), start=1):
            memory = _result_memory(item)
            if not memory:
                continue
            score = item.get("score")
            document = MemoryDocument(
                doc_id=str(item.get("id") or stable_hash(memory)),
                label=f"mem0_memory {rank}",
                content=memory,
                ordinal=rank,
                turn_index=str(item.get("turn_index") or rank),
            )
            scored.append(
                ScoredDocument(
                    document=document,
                    score=float(score) if isinstance(score, int | float) else 0.0,
                    rank=rank,
                )
            )
        return scored[: self.config.top_k]

    def build_memory(self, request: MemoryRequest) -> MemoryResult:
        documents = documents_from_turns(request.past_user_turns)
        user_id = _mem0_user_id(self.config, request)
        fingerprint = corpus_fingerprint(
            task_uid=request.task_uid,
            documents=documents,
            model=(
                f"mem0-oss-infer={self.config.infer}:"
                f"batch={self.config.ingest_batch_size}:"
                f"{self.config.mem_llm_model}:{self.config.embedding_model}"
            ),
        )
        if not documents:
            return MemoryResult(
                system_name=self.name,
                memory="",
                metadata={
                    "past_turn_count": len(request.past_user_turns),
                    "indexed_turn_count": 0,
                    "included_turn_count": 0,
                    "retrieval_unit": "mem0_memory",
                    "ingest_unit": "user_turn_batch",
                    "ingest_batch_size": self.config.ingest_batch_size,
                    "top_k": self.config.top_k,
                    "user_id": user_id,
                    "ranker": "mem0",
                    "backend": "oss",
                    "infer": self.config.infer,
                },
            )

        with self._lock:
            ingest_cache_hit, manifest_path = self._ingest_documents(
                request=request,
                documents=documents,
                user_id=user_id,
                fingerprint=fingerprint,
            )
        scored_documents = self._search(request=request, user_id=user_id)
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
                "retrieval_unit": "mem0_memory",
                "ingest_unit": "user_turn_batch",
                "ingest_batch_size": self.config.ingest_batch_size,
                "ingest_batch_count": len(
                    _chunk_documents(documents, self.config.ingest_batch_size)
                ),
                "top_k": self.config.top_k,
                "ranker": "mem0",
                "backend": "oss",
                "infer": self.config.infer,
                "mem_llm_model": self.config.mem_llm_model,
                "embedding_model": self.config.embedding_model,
                "faiss_dir": str(self.config.faiss_dir),
                "user_id": user_id,
                "rerank": self.config.rerank,
                "threshold": self.config.threshold,
                "ingest_cache_hit": ingest_cache_hit,
                "ingest_manifest_path": str(manifest_path),
                "matches": [
                    {
                        "memory_id": scored.document.doc_id,
                        "score": scored.score,
                        "rank": scored.rank,
                    }
                    for scored in scored_documents
                ],
            },
        )
