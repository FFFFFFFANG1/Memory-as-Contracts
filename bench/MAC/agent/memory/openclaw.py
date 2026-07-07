"""OpenClaw-style memory provider for MAC evaluation.

Faithfully reproduces the key mechanisms of OpenClaw's memory-core extension:

1. Session-start prompt injection:
   A "## Memory Recall" system-prompt section tells the agent to call
   memory_search / memory_get before answering questions about prior work.
   (mirrors extensions/memory-core/src/prompt-section.ts)

2. memory_search tool – hybrid retrieval:
   - Chunks past user turns into ~400-token overlapping segments
     (DEFAULT_CHUNK_TOKENS=400, DEFAULT_CHUNK_OVERLAP=80 from memory-search.ts)
   - Scores each chunk with BM25 (weight 0.3) + cosine similarity (weight 0.7)
     (DEFAULT_HYBRID_VECTOR_WEIGHT=0.7, DEFAULT_HYBRID_TEXT_WEIGHT=0.3)
   - Returns at most DEFAULT_MAX_RESULTS=6 chunks above DEFAULT_MIN_SCORE=0.35
   - Result shape mirrors MemorySearchResult from host/types.ts

3. memory_get tool – exact excerpt read:
   - Accepts a path of the form "past_user_turn_<index>" and optional from/lines
   - Returns the raw turn content, mimicking readFile() from MemorySearchManager

The BM25 portion reuses the existing BM25Index implementation.
The embedding portion reuses EmbeddingMemoryProvider's persistent cache.
"""

from __future__ import annotations

import os
import threading
from dataclasses import dataclass, field
from typing import Any

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
    clamp_top_k,
    stable_hash,
)

# ── OpenClaw defaults (from extensions/memory-core/src/memory-search.ts) ───
DEFAULT_CHUNK_TOKENS = 400
DEFAULT_CHUNK_OVERLAP = 80
DEFAULT_MAX_RESULTS = 6
DEFAULT_MIN_SCORE = 0.35
DEFAULT_HYBRID_VECTOR_WEIGHT = 0.7
DEFAULT_HYBRID_TEXT_WEIGHT = 0.3
# Rough chars-per-token approximation (avoids a tokenizer dependency)
_CHARS_PER_TOKEN = 4

OPENCLAW_MEMORY_SYSTEM_PROMPT_SECTION = (
    "## Memory Recall\n"
    "Before answering anything about prior work, decisions, dates, people, "
    "preferences, or todos: run memory_search on indexed memory (past user turns); "
    "then use memory_get to pull only the needed lines. "
    "If low confidence after search, say you checked.\n"
    "Citations: include Source: <path#line> when it helps the user verify memory snippets."
)


@dataclass(frozen=True, slots=True)
class OpenClawConfig:
    top_k: int = DEFAULT_MAX_RESULTS
    min_score: float = DEFAULT_MIN_SCORE
    vector_weight: float = DEFAULT_HYBRID_VECTOR_WEIGHT
    text_weight: float = DEFAULT_HYBRID_TEXT_WEIGHT
    chunk_tokens: int = DEFAULT_CHUNK_TOKENS
    chunk_overlap: int = DEFAULT_CHUNK_OVERLAP
    max_chars: int | None = None
    embedding: EmbeddingConfig | None = None


def openclaw_config_from_env() -> OpenClawConfig:
    max_chars_raw = os.getenv("MAC_MEMORY_MAX_CHARS")
    max_chars = int(max_chars_raw) if max_chars_raw and max_chars_raw.isdigit() else None
    return OpenClawConfig(
        top_k=clamp_top_k(os.getenv("MAC_MEMORY_TOP_K"), default=DEFAULT_MAX_RESULTS),
        max_chars=max_chars,
        embedding=embedding_config_from_env(),
    )


# ── Chunking ────────────────────────────────────────────────────────────────

def _chunk_text(text: str, *, chunk_tokens: int, overlap_tokens: int) -> list[tuple[int, int, str]]:
    """Split text into overlapping character windows.

    Returns list of (start_line, end_line, chunk_text) tuples where line
    numbers are 0-based offsets within `text`.
    """
    chunk_chars = max(1, chunk_tokens * _CHARS_PER_TOKEN)
    overlap_chars = min(chunk_chars - 1, max(0, overlap_tokens * _CHARS_PER_TOKEN))
    step = max(1, chunk_chars - overlap_chars)

    lines = text.splitlines(keepends=True)
    char_offsets: list[int] = []
    offset = 0
    for line in lines:
        char_offsets.append(offset)
        offset += len(line)
    total_chars = offset

    chunks: list[tuple[int, int, str]] = []
    pos = 0
    while pos < total_chars:
        end = min(total_chars, pos + chunk_chars)
        chunk = text[pos:end]
        # Convert char positions to line numbers
        start_line = _char_to_line(pos, char_offsets)
        end_line = _char_to_line(end - 1, char_offsets) if end > pos else start_line
        chunks.append((start_line, end_line, chunk))
        if end >= total_chars:
            break
        pos += step
    return chunks


def _char_to_line(char_pos: int, char_offsets: list[int]) -> int:
    lo, hi = 0, len(char_offsets) - 1
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if char_offsets[mid] <= char_pos:
            lo = mid
        else:
            hi = mid - 1
    return lo


# ── Per-task runtime state ───────────────────────────────────────────────────

@dataclass
class _Chunk:
    doc_id: str
    turn_path: str          # e.g. "past_user_turn_42"
    turn_index: str
    start_line: int
    end_line: int
    content: str
    ordinal: int


@dataclass
class OpenClawMemoryState:
    """Per-task runtime memory index shared between provider and tool executor."""

    task_uid: str
    chunks: list[_Chunk] = field(default_factory=list)
    # raw turns for memory_get lookups
    turns: list[dict[str, Any]] = field(default_factory=list)
    # per-turn full text for memory_get
    turn_texts: dict[str, str] = field(default_factory=dict)
    # lazy BM25 index over chunks
    _bm25: BM25Index | None = field(default=None, init=False, repr=False)
    # embedding vectors parallel to chunks
    _embeddings: list[list[float]] = field(default_factory=list)

    def bm25(self) -> BM25Index:
        if self._bm25 is None:
            docs = [
                MemoryDocument(
                    doc_id=chunk.doc_id,
                    label=chunk.turn_path,
                    content=chunk.content,
                    ordinal=chunk.ordinal,
                    turn_index=chunk.turn_index,
                )
                for chunk in self.chunks
            ]
            self._bm25 = BM25Index(docs)
        return self._bm25

    def has_embeddings(self) -> bool:
        return len(self._embeddings) == len(self.chunks)


# ── Main MemoryProvider ──────────────────────────────────────────────────────

class OpenClawMemoryProvider:
    """OpenClaw-style hybrid memory provider.

    Provides:
    - A "## Memory Recall" system prompt section (injected as <memory> block)
    - Per-task runtime state (chunks + embeddings) accessed by the tool executor
    """

    name = "openclaw"

    def __init__(
        self,
        config: OpenClawConfig | None = None,
        *,
        embed: EmbeddingFunction | None = None,
    ) -> None:
        self.config = config or openclaw_config_from_env()
        embedding_config = self.config.embedding or embedding_config_from_env()
        self._embedding_provider = EmbeddingMemoryProvider(config=embedding_config, embed=embed)
        self._states: dict[str, OpenClawMemoryState] = {}
        self._lock = threading.RLock()

    def build_memory(self, request: MemoryRequest) -> MemoryResult:
        self._close_state(request.task_uid)
        state = self._build_state(request)
        with self._lock:
            self._states[request.task_uid] = state

        return MemoryResult(
            system_name=self.name,
            memory=OPENCLAW_MEMORY_SYSTEM_PROMPT_SECTION,
            metadata={
                "past_turn_count": len(request.past_user_turns),
                "chunk_count": len(state.chunks),
                "chunk_tokens": self.config.chunk_tokens,
                "chunk_overlap": self.config.chunk_overlap,
                "vector_weight": self.config.vector_weight,
                "text_weight": self.config.text_weight,
                "top_k": self.config.top_k,
                "min_score": self.config.min_score,
            },
        )

    def runtime_for_task(self, task_uid: str) -> OpenClawMemoryState | None:
        return self._states.get(task_uid)

    def _close_state(self, task_uid: str) -> None:
        with self._lock:
            self._states.pop(task_uid, None)

    def _build_state(self, request: MemoryRequest) -> OpenClawMemoryState:
        state = OpenClawMemoryState(task_uid=request.task_uid)
        state.turns = list(request.past_user_turns)

        ordinal = 0
        for idx, turn in enumerate(request.past_user_turns):
            content = turn.get("content") if isinstance(turn, dict) else None
            if not isinstance(content, str) or not content.strip():
                continue
            turn_index = str(turn.get("turn_index", idx)) if isinstance(turn, dict) else str(idx)
            turn_path = f"past_user_turn_{turn_index}"
            state.turn_texts[turn_path] = content.strip()

            for start_line, end_line, chunk_text in _chunk_text(
                content.strip(),
                chunk_tokens=self.config.chunk_tokens,
                overlap_tokens=self.config.chunk_overlap,
            ):
                doc_id = stable_hash(f"{turn_path}:{start_line}:{end_line}\n{chunk_text}")
                state.chunks.append(
                    _Chunk(
                        doc_id=doc_id,
                        turn_path=turn_path,
                        turn_index=turn_index,
                        start_line=start_line,
                        end_line=end_line,
                        content=chunk_text,
                        ordinal=ordinal,
                    )
                )
                ordinal += 1

        # Pre-build embeddings (cached to disk via EmbeddingMemoryProvider)
        if state.chunks:
            self._build_embeddings(request, state)

        return state

    def _build_embeddings(self, request: MemoryRequest, state: OpenClawMemoryState) -> None:
        documents = [
            MemoryDocument(
                doc_id=chunk.doc_id,
                label=chunk.turn_path,
                content=chunk.content,
                ordinal=chunk.ordinal,
                turn_index=chunk.turn_index,
            )
            for chunk in state.chunks
        ]
        try:
            embedding_index = self._embedding_provider.build_index(
                request, documents
            )
            state._embeddings = list(embedding_index.embeddings)
        except Exception:  # noqa: BLE001
            state._embeddings = []

    def hybrid_search(
        self,
        state: OpenClawMemoryState,
        query: str,
        request: MemoryRequest,
        *,
        max_results: int | None = None,
        min_score: float | None = None,
    ) -> list[dict[str, Any]]:
        if not state.chunks:
            return []

        k = max_results if max_results is not None else self.config.top_k
        threshold = min_score if min_score is not None else self.config.min_score

        # BM25 scores (normalize to [0, 1] via max)
        bm25_index = state.bm25()
        bm25_results = bm25_index.search(query, top_k=len(state.chunks))
        bm25_by_id: dict[str, float] = {r.document.doc_id: r.score for r in bm25_results}
        max_bm25 = max(bm25_by_id.values(), default=1.0) or 1.0

        # Embedding scores
        embed_by_id: dict[str, float] = {}
        if state.has_embeddings():
            try:
                query_vec = self._embedding_provider._embedder(request)(
                    [query], self._embedding_provider.config.model
                )[0]
                from bench.MAC.agent.memory.retrieval import cosine_similarity
                for chunk, emb in zip(state.chunks, state._embeddings):
                    embed_by_id[chunk.doc_id] = cosine_similarity(query_vec, emb)
            except Exception:  # noqa: BLE001
                pass

        vw = self.config.vector_weight
        tw = self.config.text_weight
        # normalise weights
        total = vw + tw if (vw + tw) > 0 else 1.0
        vw, tw = vw / total, tw / total

        scored: list[tuple[_Chunk, float]] = []
        for chunk in state.chunks:
            vec = embed_by_id.get(chunk.doc_id, 0.0)
            bm25_raw = bm25_by_id.get(chunk.doc_id, 0.0)
            bm25_norm = bm25_raw / max_bm25
            if embed_by_id:
                combined = vw * vec + tw * bm25_norm
            else:
                # fallback to BM25-only when embeddings unavailable
                combined = bm25_norm
            if combined >= threshold:
                scored.append((chunk, combined))

        scored.sort(key=lambda x: (-x[1], x[0].ordinal))
        top = scored[:k]

        results = []
        for chunk, score in top:
            results.append({
                "path": chunk.turn_path,
                "startLine": chunk.start_line,
                "endLine": chunk.end_line,
                "score": round(score, 4),
                "snippet": chunk.content[:500].strip(),
                "source": "memory",
            })
        return results

    def memory_get(
        self,
        state: OpenClawMemoryState,
        rel_path: str,
        *,
        from_line: int | None = None,
        lines: int | None = None,
    ) -> dict[str, Any]:
        content = state.turn_texts.get(rel_path)
        if content is None:
            return {
                "path": rel_path,
                "text": "",
                "disabled": True,
                "error": f"Memory path not found: {rel_path}",
            }

        content_lines = content.splitlines()
        total_lines = len(content_lines)
        start = max(0, (from_line or 1) - 1)  # OpenClaw uses 1-based from
        count = lines or min(200, total_lines - start)
        end = min(total_lines, start + count)
        slice_lines = content_lines[start:end]
        text = "\n".join(slice_lines)
        truncated = end < total_lines

        result: dict[str, Any] = {
            "path": rel_path,
            "text": text,
            "from": start + 1,
            "lines": len(slice_lines),
            "truncated": truncated,
        }
        if truncated:
            result["nextFrom"] = end + 1
        return result


# ── Tool schemas ─────────────────────────────────────────────────────────────

def memory_search_tool() -> dict[str, Any]:
    return {
        "name": "memory_search",
        "description": (
            "Mandatory recall step: semantically search indexed past user turns "
            "(memory) before answering questions about prior work, decisions, dates, "
            "people, preferences, or todos. Returns ranked snippets with source paths "
            "and line numbers. Use memory_get to read the full content of a result."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Natural language query to search memory for.",
                },
                "maxResults": {
                    "type": "integer",
                    "minimum": 1,
                    "description": f"Maximum results to return (default {DEFAULT_MAX_RESULTS}).",
                },
                "minScore": {
                    "type": "number",
                    "description": f"Minimum relevance score threshold (default {DEFAULT_MIN_SCORE}).",
                },
            },
            "required": ["query"],
        },
        "host_action": "memory.search",
        "runtime_family": "openclaw_memory",
    }


def memory_get_tool() -> dict[str, Any]:
    return {
        "name": "memory_get",
        "description": (
            "Read a specific excerpt from a memory file by path. "
            "Use paths returned by memory_search (e.g. 'past_user_turn_42'). "
            "Optional from/lines parameters select a line range within the turn."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Memory path, e.g. 'past_user_turn_42'.",
                },
                "from": {
                    "type": "integer",
                    "description": "1-based start line (default: beginning of file).",
                },
                "lines": {
                    "type": "integer",
                    "description": "Number of lines to read (default: up to 200).",
                },
            },
            "required": ["path"],
        },
        "host_action": "memory.get",
        "runtime_family": "openclaw_memory",
    }


def openclaw_memory_tools() -> list[dict[str, Any]]:
    """Return tool schemas to inject into the agent loop for OpenClaw memory."""
    return [memory_search_tool(), memory_get_tool()]
