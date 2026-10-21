"""Run MAC memory-system evaluation for a benchmark."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import traceback
from datetime import datetime, timezone

try:
    from datetime import UTC
except ImportError:  # Python < 3.11
    UTC = timezone.utc
from pathlib import Path
from typing import Any

from bench.MAC.agent.data import build_agent_loop_input
from bench.MAC.cctu.bridge import (
    MAC_CCTU_DATA_DIR,
    build_cctu_eval_task,
    build_cctu_system_config,
    list_cctu_task_uids,
    load_cctu_eval_tasks,
)
from bench.MAC.sopbench.bridge import (
    MAC_SOPBENCH_DATA_DIR,
    build_sopbench_eval_task,
    build_sopbench_system_config,
    list_sopbench_task_uids,
    load_sopbench_eval_tasks,
)
from bench.MAC.sopbench.clarification_reply import SOPClarificationContext
from bench.MAC.agent.llm import LLMConfig, model_client_from_config
from bench.MAC.agent.loop.cctu_tools import CCTUToolExecutor
from bench.MAC.agent.loop.sopbench_tools import SOPBenchToolExecutor
from bench.MAC.agent.loop.llm_tools import (
    DryRunToolReturnModelClient,
    LLMToolExecutor,
    LLMToolReturnConfig,
)
from bench.MAC.agent.loop.runner import ClarificationPolicy, run_agent_loop
from bench.MAC.agent.loop.tools import HeuristicToolExecutor
from bench.MAC.agent.memory import MemoryRequest, available_memory_systems, get_memory_provider
from bench.MAC.agent.memory.bm25 import BM25Config, BM25MemoryProvider
from bench.MAC.agent.memory.embedding import (
    DEFAULT_EMBEDDING_CACHE_DIR,
    DEFAULT_EMBEDDING_MODEL,
    EmbeddingConfig,
    EmbeddingMemoryProvider,
)
from bench.MAC.agent.memory.mac import (
    DEFAULT_MAC_STORE_DIR,
    MACHookedToolExecutor,
    MACMemoryConfig,
    MACMemoryProvider,
    export_mac_constraint_graph,
    write_mac_constraint_graph,
)
from bench.MAC.agent.memory.mem0 import (
    DEFAULT_MEM0_FAISS_DIR,
    DEFAULT_MEM0_INGEST_CACHE_DIR,
    Mem0Config,
    Mem0MemoryProvider,
)
from bench.MAC.agent.memory.rrf import RRFConfig, RRFMemoryProvider
from bench.MAC.scripts.run_paths import (
    bench_output_path,
    mac_graph_path,
    make_run_unique_index,
    memory_output_error_path,
)

BENCH_CHOICES = ["cctu", "sopbench"]
BENCH_ENV_PATH = Path(__file__).resolve().parents[2] / ".env"


def load_bench_env(env_path: Path = BENCH_ENV_PATH) -> None:
    """Load shared benchmark env vars before CLI defaults are resolved."""
    if not env_path.exists():
        return
    try:
        from dotenv import load_dotenv
    except ImportError:
        for line in env_path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            key, value = stripped.split("=", 1)
            key = key.strip().removeprefix("export ").strip()
            os.environ.setdefault(key, value.strip().strip('"').strip("'"))
        return
    load_dotenv(env_path, override=False)


def parse_args() -> argparse.Namespace:
    load_bench_env()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--memory-system", choices=available_memory_systems(), required=True)
    parser.add_argument(
        "--bench",
        choices=BENCH_CHOICES,
        default="cctu",
        help="Benchmark to run.",
    )
    parser.add_argument("--cctu-data-dir", type=Path, default=MAC_CCTU_DATA_DIR, help="MAC CCTU runtime data dir.")
    parser.add_argument(
        "--sopbench-data-dir",
        type=Path,
        default=MAC_SOPBENCH_DATA_DIR,
        help="MAC SOPBench runtime data dir.",
    )
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--run-id",
        help="Run identifier suffix; default is `{unix_seconds}-{dd}-{mm}-{yy}`.",
    )
    parser.add_argument("--limit", type=int, default=0, help="Maximum tasks to run; 0 means all.")
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--turn-index", type=int, default=-1)
    parser.add_argument("--max-iterations", type=int, default=25)
    parser.add_argument(
        "--replay-reasoning-content",
        action=argparse.BooleanOptionalAction,
        default=False,
        help=(
            "Replay model reasoning fields into subsequent agent calls. Disabled by default: "
            "raw traces retain reasoning for audit, while model context keeps visible "
            "content, tool calls, and tool results."
        ),
    )
    parser.add_argument(
        "--sop-clarification-reply",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="For sopbench, reply heuristically when send_message asks the user a question.",
    )
    parser.add_argument(
        "--sop-max-clarification-rounds",
        type=int,
        default=3,
        help="Maximum clarification reply rounds per SOP task.",
    )
    parser.add_argument(
        "--max-worker",
        "--max-workers",
        dest="max_worker",
        type=int,
        default=1,
        help="Maximum task-level concurrency. 1 keeps the original sequential behavior.",
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--save-messages", action="store_true")
    parser.add_argument("--skip-missing-system-prompt", action=argparse.BooleanOptionalAction, default=False)
    parser.add_argument(
        "--checkpoint-interval",
        type=int,
        default=10,
        help="Write partial memory_output every N completed tasks; 0 disables checkpoints.",
    )
    parser.add_argument(
        "--merge-into",
        type=Path,
        help="Merge new results into an existing memory_output JSON (in place).",
    )
    parser.add_argument(
        "--retry-errors",
        action="store_true",
        help="With --merge-into, rerun only rows whose record_type is task_error.",
    )
    parser.add_argument(
        "--only-indices",
        help="Comma-separated global task indices to run. Requires --merge-into.",
    )

    parser.add_argument("--agent-llm-model", default=os.getenv("LLM_MODEL") or "gpt-4o-mini")
    parser.add_argument("--agent-llm-base-url", default=os.getenv("LLM_BASE_URL"))
    parser.add_argument("--agent-llm-api-key-env", default="LLM_API_KEY")
    parser.add_argument("--agent-llm-temperature", type=float, default=0.3)
    parser.add_argument("--agent-llm-max-tokens", type=int, default=4096)

    parser.add_argument("--memory-llm-model", default=os.getenv("LLM_MODEL") or "")
    parser.add_argument("--memory-llm-base-url", default=os.getenv("LLM_BASE_URL"))
    parser.add_argument("--memory-llm-api-key-env", default="LLM_API_KEY")
    parser.add_argument("--memory-llm-temperature", type=float, default=0.3)
    parser.add_argument("--memory-llm-max-tokens", type=int, default=4096)
    parser.add_argument("--memory-top-k", type=int, default=int(os.getenv("MAC_MEMORY_TOP_K", "10")))
    parser.add_argument(
        "--memory-max-chars",
        type=int,
        default=int(os.getenv("MAC_MEMORY_MAX_CHARS", "0")),
        help="Maximum characters for retrieved memory; 0 means unlimited.",
    )
    parser.add_argument(
        "--embedding-model",
        default=os.getenv("MAC_EMBEDDING_MODEL") or os.getenv("EMBEDDING_MODEL") or DEFAULT_EMBEDDING_MODEL,
        help="Embedding model for embedding and rrf memory systems.",
    )
    parser.add_argument(
        "--embedding-cache-dir",
        type=Path,
        default=Path(os.getenv("MAC_EMBEDDING_CACHE_DIR", str(DEFAULT_EMBEDDING_CACHE_DIR))),
        help="Persistent embedding index cache directory.",
    )
    parser.add_argument(
        "--embedding-api-key-env",
        default=os.getenv("MAC_EMBEDDING_API_KEY_ENV", "EMBEDDING_API"),
    )
    parser.add_argument("--embedding-base-url", default=os.getenv("MAC_EMBEDDING_BASE_URL") or os.getenv("EMBEDDING_BASE"))
    parser.add_argument("--rrf-k", type=int, default=int(os.getenv("MAC_RRF_K", "60")))
    parser.add_argument(
        "--mac-token-budget",
        type=int,
        default=int(os.getenv("MAC_PROMPT_TOKEN_BUDGET", "1500")),
        help="Approximate token budget for rendered MAC reminders.",
    )
    parser.add_argument(
        "--mac-store-dir",
        type=Path,
        default=Path(os.getenv("MAC_BENCH_STORE_DIR", str(DEFAULT_MAC_STORE_DIR))),
        help="Directory for persisted per-task MAC runtime stores when enabled.",
    )
    parser.add_argument(
        "--mac-persist-store",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Persist per-task MAC stores instead of using in-memory stores.",
    )
    parser.add_argument(
        "--mac-load-store-dir",
        type=Path,
        default=None,
        help="Reuse persisted per-task MAC SQLite stores from this directory (skip history extraction).",
    )
    parser.add_argument(
        "--mac-ask-pass",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Bench test mode: treat MAC gate ask decisions as allow.",
    )
    parser.add_argument(
        "--mac-unified-ops-extraction",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Use per-turn BM25 candidate retrieval plus LLM add/update/remove ops for MAC extraction.",
    )
    parser.add_argument(
        "--mac-unified-ops-top-k",
        type=int,
        default=int(os.getenv("MAC_UNIFIED_OPS_TOP_K", "5")),
        help="Candidate active constraints passed to unified ops extraction.",
    )
    parser.add_argument("--mem0-user-id-prefix", default=os.getenv("MAC_MEM0_USER_ID_PREFIX", "mac-bench"))
    parser.add_argument(
        "--mem0-ingest-cache-dir",
        type=Path,
        default=Path(os.getenv("MAC_MEM0_INGEST_CACHE_DIR", str(DEFAULT_MEM0_INGEST_CACHE_DIR))),
        help="Local manifest directory used to avoid duplicate Mem0 ingest.",
    )
    parser.add_argument(
        "--mem0-faiss-dir",
        type=Path,
        default=Path(os.getenv("MAC_MEM0_FAISS_DIR", str(DEFAULT_MEM0_FAISS_DIR))),
        help="Local FAISS index directory for Mem0 OSS.",
    )
    parser.add_argument("--mem-llm-model", default=os.getenv("MEM_LLM_MODEL") or os.getenv("LLM_MODEL", ""))
    parser.add_argument("--mem-api-key-env", default=os.getenv("MAC_MEM_API_KEY_ENV") or "LLM_API_KEY")
    parser.add_argument("--mem-base-url", default=os.getenv("MEM_BASE_URL") or os.getenv("LLM_BASE_URL"))
    parser.add_argument("--mem-llm-max-tokens", type=int, default=int(os.getenv("MEM_LLM_MAX_TOKENS", "4096")))
    parser.add_argument(
        "--mac-extract-batch-size",
        type=int,
        default=int(os.getenv("MAC_EXTRACT_BATCH_SIZE", "1")),
        help="User-turn batch size for MAC IR extraction. Clamped to 10.",
    )
    parser.add_argument(
        "--mac-extract-max-worker",
        type=int,
        default=int(os.getenv("MAC_EXTRACT_MAX_WORKER", "8")),
        help="Maximum parallel MAC IR extraction batches. Clamped to 8.",
    )
    parser.add_argument(
        "--mem-llm-timeout-seconds",
        type=float,
        default=float(os.getenv("MEM_LLM_TIMEOUT_SECONDS", "120")),
    )
    parser.add_argument("--mem0-infer", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--mem0-rerank", action=argparse.BooleanOptionalAction, default=False)
    parser.add_argument("--mem0-threshold", type=float)
    parser.add_argument("--mem0-force-reingest", action=argparse.BooleanOptionalAction, default=False)

    parser.add_argument(
        "--tool-executor",
        choices=["heuristic", "hybrid", "llm", "cctu", "sopbench"],
        default="heuristic",
        help="Tool-return executor mode. `heuristic` preserves the original stub behavior.",
    )
    parser.add_argument("--tool-return-llm-model", default="")
    parser.add_argument("--tool-return-llm-base-url")
    parser.add_argument("--tool-return-llm-api-key-env", default="")
    parser.add_argument("--tool-return-llm-temperature", type=float, default=0.0)
    parser.add_argument("--tool-return-llm-max-tokens", type=int, default=8192)
    parser.add_argument("--tool-return-max-attempts", type=int, default=3)
    parser.add_argument("--tool-return-max-payload-chars", type=int, default=12000)

    return parser.parse_args()


def llm_config_from_args(args: argparse.Namespace, prefix: str) -> LLMConfig:
    return LLMConfig(
        model=getattr(args, f"{prefix}_model"),
        base_url=getattr(args, f"{prefix}_base_url"),
        api_key_env=getattr(args, f"{prefix}_api_key_env"),
        temperature=getattr(args, f"{prefix}_temperature"),
        max_tokens=getattr(args, f"{prefix}_max_tokens"),
    )


def tool_return_llm_config_from_args(args: argparse.Namespace, agent_llm: LLMConfig) -> LLMConfig:
    return LLMConfig(
        model=args.tool_return_llm_model or agent_llm.model,
        base_url=args.tool_return_llm_base_url or agent_llm.base_url,
        api_key_env=args.tool_return_llm_api_key_env or agent_llm.api_key_env,
        temperature=args.tool_return_llm_temperature,
        max_tokens=args.tool_return_llm_max_tokens,
    )


def memory_provider_from_args(args: argparse.Namespace):
    top_k = max(1, args.memory_top_k)
    max_chars = args.memory_max_chars if args.memory_max_chars > 0 else None
    normalized = args.memory_system.strip().lower().replace("-", "_")
    if normalized == "bm25":
        return BM25MemoryProvider(BM25Config(top_k=top_k, max_chars=max_chars))
    if normalized == "embedding":
        return EmbeddingMemoryProvider(
            EmbeddingConfig(
                top_k=top_k,
                max_chars=max_chars,
                model=args.embedding_model,
                cache_dir=args.embedding_cache_dir,
                api_key_env=args.embedding_api_key_env,
                base_url=args.embedding_base_url,
            )
        )
    if normalized == "rrf":
        embedding_config = EmbeddingConfig(
            top_k=top_k,
            max_chars=max_chars,
            model=args.embedding_model,
            cache_dir=args.embedding_cache_dir,
            api_key_env=args.embedding_api_key_env,
            base_url=args.embedding_base_url,
        )
        return RRFMemoryProvider(
            RRFConfig(
                top_k=top_k,
                max_chars=max_chars,
                rrf_k=max(1, args.rrf_k),
                embedding=embedding_config,
            )
        )
    if normalized == "mac":
        return MACMemoryProvider(
            MACMemoryConfig(
                top_k=top_k,
                token_budget=max(1, args.mac_token_budget),
                store_dir=args.mac_store_dir,
                persist_store=args.mac_persist_store,
                load_store_dir=args.mac_load_store_dir,
                ask_pass=args.mac_ask_pass,
                mem_llm_model=args.mem_llm_model,
                mem_api_key_env=args.mem_api_key_env,
                mem_base_url=args.mem_base_url,
                mem_llm_max_tokens=max(1, args.mem_llm_max_tokens),
                mem_llm_timeout_seconds=max(1.0, args.mem_llm_timeout_seconds),
                extract_batch_size=max(1, min(10, args.mac_extract_batch_size)),
                extract_max_worker=max(1, min(8, args.mac_extract_max_worker)),
                unified_ops_extraction=bool(args.mac_unified_ops_extraction),
                unified_ops_top_k=max(1, args.mac_unified_ops_top_k),
            )
        )
    if normalized == "mem0":
        return Mem0MemoryProvider(
            Mem0Config(
                top_k=top_k,
                max_chars=max_chars,
                user_id_prefix=args.mem0_user_id_prefix,
                ingest_cache_dir=args.mem0_ingest_cache_dir,
                faiss_dir=args.mem0_faiss_dir,
                rerank=args.mem0_rerank,
                threshold=args.mem0_threshold,
                force_reingest=args.mem0_force_reingest,
                infer=args.mem0_infer,
                mem_llm_model=args.mem_llm_model,
                mem_api_key_env=args.mem_api_key_env,
                mem_base_url=args.mem_base_url,
                embedding_model=args.embedding_model,
                embedding_api_key_env=args.embedding_api_key_env,
                embedding_base_url=args.embedding_base_url,
            )
        )
    return get_memory_provider(args.memory_system)


def resolve_run_id(args: argparse.Namespace) -> str:
    return args.run_id or make_run_unique_index()


def default_output_path(args: argparse.Namespace) -> Path:
    return bench_output_path(args.memory_system, args.bench, resolve_run_id(args))


def validate_args(args: argparse.Namespace) -> None:
    if args.bench == "cctu" and args.tool_executor not in {"cctu", "heuristic"}:
        raise ValueError("--bench cctu requires --tool-executor cctu (or heuristic for dry runs)")
    if args.bench == "sopbench" and args.tool_executor not in {"sopbench", "heuristic"}:
        raise ValueError("--bench sopbench requires --tool-executor sopbench (or heuristic for dry runs)")
    if args.merge_into and not args.retry_errors and not args.only_indices:
        raise ValueError("--merge-into requires --retry-errors or --only-indices")
    if args.retry_errors and not args.merge_into:
        raise ValueError("--retry-errors requires --merge-into")
    if args.only_indices and not args.merge_into:
        raise ValueError("--only-indices requires --merge-into")


def read_memory_output(path: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise TypeError(f"{path} must contain a JSON object")
    header = payload.get("header")
    records = payload.get("records")
    if not isinstance(header, dict) or not isinstance(records, list):
        raise ValueError(f"{path} is not a MACMemoryOutputV1 file")
    return header, [row for row in records if isinstance(row, dict)]


def parse_index_list(raw: str) -> list[int]:
    indices: list[int] = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        indices.append(int(part))
    return indices


def retry_indices_from_args(args: argparse.Namespace) -> list[int]:
    if args.retry_errors:
        _, records = read_memory_output(args.merge_into)
        indices = [
            int(row.get("index"))
            for row in records
            if row.get("record_type") == "task_error" and row.get("index") is not None
        ]
        return sorted(set(indices))
    if args.only_indices:
        return sorted(set(parse_index_list(args.only_indices)))
    return []


def load_merge_run_context(
    args: argparse.Namespace,
    *,
    retry_indices: list[int],
) -> tuple[list[tuple[int, dict[str, Any]]], dict[str, Any], dict[str, Any], int]:
    if args.bench not in {"cctu", "sopbench"}:
        raise NotImplementedError("--merge-into is only supported for --bench cctu or sopbench")
    if not retry_indices:
        raise ValueError("No task indices selected for retry")

    if args.bench == "cctu":
        all_uids = list_cctu_task_uids(data_dir=args.cctu_data_dir)
        build_task = lambda uid: build_cctu_eval_task(uid, data_dir=args.cctu_data_dir)
        _, task_set_summary = load_cctu_eval_tasks(data_dir=args.cctu_data_dir)
        system_config = build_cctu_system_config(data_dir=args.cctu_data_dir)
    else:
        all_uids = list_sopbench_task_uids(data_dir=args.sopbench_data_dir)
        build_task = lambda uid: build_sopbench_eval_task(uid, data_dir=args.sopbench_data_dir)
        _, task_set_summary = load_sopbench_eval_tasks(data_dir=args.sopbench_data_dir)
        system_config = build_sopbench_system_config(data_dir=args.sopbench_data_dir)

    selected: list[tuple[int, dict[str, Any]]] = []
    for index in retry_indices:
        if index < 0 or index >= len(all_uids):
            raise IndexError(f"Task index out of range for merge retry: {index}")
        selected.append((index, build_task(all_uids[index])))
    return selected, task_set_summary, system_config, len(all_uids)


def merge_records_by_index(
    *,
    base_records: list[dict[str, Any]],
    updates: list[dict[str, Any]],
    total_count: int,
) -> list[dict[str, Any]]:
    by_index: dict[int, dict[str, Any]] = {
        int(row.get("index")): row
        for row in base_records
        if row.get("index") is not None
    }
    for row in updates:
        by_index[int(row.get("index"))] = row
    return [by_index[index] for index in range(total_count)]


def load_run_context(
    args: argparse.Namespace,
    *,
    offset: int = 0,
    limit: int = 0,
) -> tuple[list[dict[str, Any]], dict[str, Any], dict[str, Any]]:
    if args.bench == "cctu":
        uids = task_slice(list_cctu_task_uids(data_dir=args.cctu_data_dir), offset=offset, limit=limit)
        tasks, task_set_summary = load_cctu_eval_tasks(data_dir=args.cctu_data_dir, uids=uids)
        system_config = build_cctu_system_config(data_dir=args.cctu_data_dir)
        return tasks, task_set_summary, system_config
    if args.bench == "sopbench":
        uids = task_slice(list_sopbench_task_uids(data_dir=args.sopbench_data_dir), offset=offset, limit=limit)
        tasks, task_set_summary = load_sopbench_eval_tasks(data_dir=args.sopbench_data_dir, uids=uids)
        system_config = build_sopbench_system_config(data_dir=args.sopbench_data_dir)
        return tasks, task_set_summary, system_config
    raise ValueError(f"Unsupported bench: {args.bench}")


def task_slice(tasks: list[dict[str, Any]], *, offset: int, limit: int) -> list[dict[str, Any]]:
    start = max(0, offset)
    if limit and limit > 0:
        return tasks[start : start + limit]
    return tasks[start:]


def write_output(
    path: Path,
    header: dict[str, Any],
    records: list[dict[str, Any]],
    *,
    checkpoint: bool = False,
    completed_count: int | None = None,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload_header = dict(header)
    if checkpoint:
        payload_header["checkpoint"] = True
        payload_header["completed_count"] = completed_count
        payload_header["checkpoint_at"] = datetime.now(UTC).isoformat()
    payload = {
        "schema_version": "MACMemoryOutputV1",
        "header": payload_header,
        "records": records,
    }
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def append_error_record(path: Path, header: dict[str, Any], record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "written_at": datetime.now(UTC).isoformat(),
        "run_id": header.get("run_id"),
        "bench": header.get("bench"),
        "memory_system": header.get("memory_system"),
        "record": record,
    }
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")


def is_error_record(record: dict[str, Any]) -> bool:
    if record.get("record_type") == "task_error":
        return True
    error = record.get("error")
    return isinstance(error, str) and bool(error.strip())


def memory_request_from_loop_input(loop_input, memory_llm: LLMConfig) -> MemoryRequest:
    return MemoryRequest(
        task_uid=loop_input.task_uid,
        agent=loop_input.agent,
        user_prompt=loop_input.user_prompt,
        past_user_turns=loop_input.past_user_turns,
        task=loop_input.task,
        agent_tools=list(loop_input.tools),
        memory_llm=memory_llm.to_metadata(),
    )


def task_difficulty(task: dict[str, Any], bench: str) -> str:
    value = task.get("task_level")
    return str(value).strip().lower() if isinstance(value, str) and value.strip() else bench


async def run_one_task(
    *,
    index: int,
    total: int,
    task: dict[str, Any],
    args: argparse.Namespace,
    system_config: dict[str, Any],
    memory_llm: LLMConfig,
    memory_provider,
    model_client,
    tool_return_model_client,
    progress_lock: asyncio.Lock,
) -> dict[str, Any]:
    task_uid = str(task.get("task_uid") or "")
    mac_state = None
    try:
        loop_input = build_agent_loop_input(
            task,
            system_config,
            turn_index=args.turn_index,
        )
        if args.skip_missing_system_prompt and not loop_input.system_prompt:
            raise ValueError(f"missing system prompt for agent {loop_input.agent}")
        memory_result = memory_provider.build_memory(
            memory_request_from_loop_input(loop_input, memory_llm)
        )
        executor = None
        if args.tool_executor == "cctu":
            executor = CCTUToolExecutor(task=task)
        elif args.tool_executor == "sopbench":
            executor = SOPBenchToolExecutor(task=task)
        elif args.tool_executor != "heuristic":
            executor = LLMToolExecutor(
                agent=loop_input.agent,
                tools=loop_input.tools,
                task_uid=loop_input.task_uid,
                user_prompt=loop_input.user_prompt,
                memory=memory_result.memory,
                model_client=tool_return_model_client,
                config=LLMToolReturnConfig(
                    mode=args.tool_executor,
                    max_attempts=args.tool_return_max_attempts,
                    max_payload_chars=args.tool_return_max_payload_chars,
                ),
            )
        if memory_result.system_name == "mac" and hasattr(memory_provider, "runtime_for_task"):
            mac_state = memory_provider.runtime_for_task(loop_input.task_uid)
            if mac_state is not None:
                ask_pass = getattr(getattr(memory_provider, "config", None), "ask_pass", False)
                executor = MACHookedToolExecutor(
                    state=mac_state,
                    inner=executor or HeuristicToolExecutor(agent=loop_input.agent),
                    ask_pass=ask_pass,
                )
        clarification = None
        if args.bench == "sopbench" and args.sop_clarification_reply:
            sop_context = SOPClarificationContext.from_task(
                task,
                user_prompt=loop_input.user_prompt,
                past_user_turns=loop_input.past_user_turns,
            )
            clarification = ClarificationPolicy(
                reply_for=sop_context.reply_for,
                max_rounds=max(0, args.sop_max_clarification_rounds),
            )
        result = await run_agent_loop(
            agent=loop_input.agent,
            system_prompt=loop_input.system_prompt,
            tools=loop_input.tools,
            memory=memory_result.memory,
            user_prompt=loop_input.user_prompt,
            model_client=model_client,
            executor=executor,
            max_iterations=args.max_iterations,
            clarification=clarification,
            replay_reasoning_content=args.replay_reasoning_content,
        )
        mac_graph_output = None
        if mac_state is not None:
            run_id = args.run_id or resolve_run_id(args)
            graph_payload = export_mac_constraint_graph(
                mac_state,
                metadata={
                    **(memory_result.metadata or {}),
                    "mac_events": list(getattr(executor, "mac_events", [])),
                },
            )
            mac_graph_output = write_mac_constraint_graph(
                mac_graph_path(args.memory_system, args.bench, run_id, task_uid),
                graph_payload,
            )
        if hasattr(executor, "close"):
            executor.close()
        row = {
            "record_type": "task_result",
            "index": index,
            "task_uid": task_uid,
            "agent": loop_input.agent,
            "difficulty": task_difficulty(task, args.bench),
            "memory_system": memory_result.system_name,
            "memory_metadata": memory_result.metadata,
            "user_prompt": loop_input.user_prompt,
            "memory": memory_result.memory,
            "final_answer": result.final_answer,
            "stop_reason": result.stop_reason,
            "error": result.error,
            "iterations": result.iterations,
            "prompt_hash": result.prompt_hash,
            "events": result.events,
            "clarification_rounds": result.clarification_rounds,
        }
        if args.save_messages:
            row["messages"] = result.messages
        if "executor" in locals() and hasattr(executor, "mac_events"):
            row["mac_events"] = list(executor.mac_events)
        if mac_graph_output is not None:
            row["mac_constraint_graph_path"] = str(mac_graph_output)
            if args.mac_persist_store:
                safe_task = "".join(
                    char if char.isalnum() or char in {"-", "_"} else "_" for char in task_uid
                )
                row["mac_store_sqlite_path"] = str(Path(args.mac_store_dir) / f"{safe_task}.sqlite")
    except Exception as exc:  # noqa: BLE001 - keep benchmark row-level failures isolated.
        if "executor" in locals() and hasattr(executor, "close"):
            executor.close()
        row = {
            "record_type": "task_error",
            "index": index,
            "task_uid": task_uid,
            "difficulty": task_difficulty(task, args.bench),
            "memory_system": args.memory_system,
            "error": f"{type(exc).__name__}: {exc}",
            "traceback": traceback.format_exc(limit=12),
        }
        cause = exc.__cause__
        if cause is not None:
            row["error_cause"] = f"{type(cause).__name__}: {cause}"

    async with progress_lock:
        print(f"[{index + 1}/{total}] {task_uid} -> {row['record_type']}", flush=True)
    return row


async def run(args: argparse.Namespace) -> None:
    validate_args(args)
    merge_into = args.merge_into
    base_header: dict[str, Any] | None = None
    base_records: list[dict[str, Any]] = []
    total_task_count = 0
    indexed_tasks: list[tuple[int, dict[str, Any]]] = []

    if merge_into:
        base_header, base_records = read_memory_output(merge_into)
        retry_indices = retry_indices_from_args(args)
        indexed_tasks, task_set_summary, system_config, total_task_count = load_merge_run_context(
            args,
            retry_indices=retry_indices,
        )
    else:
        tasks, task_set_summary, system_config = load_run_context(
            args,
            offset=args.offset,
            limit=args.limit,
        )
        indexed_tasks = [(index, task) for index, task in enumerate(tasks, start=max(0, args.offset))]
        total_task_count = len(indexed_tasks)

    agent_llm = llm_config_from_args(args, "agent_llm")
    memory_llm = llm_config_from_args(args, "memory_llm")
    tool_return_llm = tool_return_llm_config_from_args(args, agent_llm)
    run_id = resolve_run_id(args)
    args.run_id = run_id
    if args.memory_system == "mac" and args.mac_persist_store:
        args.mac_store_dir = Path(args.mac_store_dir) / run_id
    memory_provider = memory_provider_from_args(args)
    model_client = model_client_from_config(agent_llm, dry_run=args.dry_run)
    if args.tool_executor in {"heuristic", "cctu", "sopbench"}:
        tool_return_model_client = None
    elif args.dry_run:
        tool_return_model_client = DryRunToolReturnModelClient()
    else:
        tool_return_model_client = model_client_from_config(tool_return_llm, dry_run=False)
    output = merge_into or args.output or default_output_path(args)
    error_output = memory_output_error_path(output, bench=args.bench)
    header = {
        **(base_header or {}),
        "record_type": "run_header",
        "generated_at": datetime.now(UTC).isoformat(),
        "run_id": (base_header or {}).get("run_id") or run_id,
        "bench": args.bench,
        "memory_system": args.memory_system,
        "dry_run": args.dry_run,
        "turn_index": args.turn_index,
        "task_count": total_task_count if not merge_into else (base_header or {}).get("task_count", total_task_count),
        "max_worker": max(1, args.max_worker),
        "replay_reasoning_content": args.replay_reasoning_content,
        "checkpoint_interval": args.checkpoint_interval,
        "agent_llm": agent_llm.to_metadata(),
        "memory_llm": memory_llm.to_metadata(),
        "memory_top_k": max(1, args.memory_top_k),
        "memory_max_chars": args.memory_max_chars if args.memory_max_chars > 0 else None,
        "embedding_model": args.embedding_model if args.memory_system in {"embedding", "rrf"} else None,
        "embedding_cache_dir": str(args.embedding_cache_dir) if args.memory_system in {"embedding", "rrf"} else None,
        "rrf_k": max(1, args.rrf_k) if args.memory_system == "rrf" else None,
        "mac_token_budget": max(1, args.mac_token_budget) if args.memory_system == "mac" else None,
        "mac_store_dir": str(args.mac_store_dir) if args.memory_system == "mac" else None,
        "mac_persist_store": args.mac_persist_store if args.memory_system == "mac" else None,
        "mac_load_store_dir": str(args.mac_load_store_dir) if args.mac_load_store_dir else None,
        "mac_ask_pass": args.mac_ask_pass if args.memory_system == "mac" else None,
        "mac_mem_llm_model": args.mem_llm_model if args.memory_system == "mac" else None,
        "mac_mem_api_key_env": args.mem_api_key_env if args.memory_system == "mac" else None,
        "mac_mem_base_url": args.mem_base_url if args.memory_system == "mac" else None,
        "mac_mem_llm_max_tokens": max(1, args.mem_llm_max_tokens) if args.memory_system == "mac" else None,
        "mac_extract_batch_size": max(1, min(10, args.mac_extract_batch_size)) if args.memory_system == "mac" else None,
        "mac_extract_max_worker": max(1, min(8, args.mac_extract_max_worker)) if args.memory_system == "mac" else None,
        "mac_unified_ops_extraction": args.mac_unified_ops_extraction if args.memory_system == "mac" else None,
        "mac_unified_ops_top_k": max(1, args.mac_unified_ops_top_k) if args.memory_system == "mac" else None,
        "mac_mem_llm_timeout_seconds": max(1.0, args.mem_llm_timeout_seconds) if args.memory_system == "mac" else None,
        "mem0_user_id_prefix": args.mem0_user_id_prefix if args.memory_system == "mem0" else None,
        "mem0_ingest_cache_dir": str(args.mem0_ingest_cache_dir) if args.memory_system == "mem0" else None,
        "mem0_faiss_dir": str(args.mem0_faiss_dir) if args.memory_system == "mem0" else None,
        "mem0_infer": args.mem0_infer if args.memory_system == "mem0" else None,
        "mem_llm_model": args.mem_llm_model if args.memory_system == "mem0" else None,
        "mem0_rerank": args.mem0_rerank if args.memory_system == "mem0" else None,
        "mem0_threshold": args.mem0_threshold if args.memory_system == "mem0" else None,
        "mem0_force_reingest": args.mem0_force_reingest if args.memory_system == "mem0" else None,
        "tool_executor": args.tool_executor,
        "tool_return_llm": tool_return_llm.to_metadata() if args.tool_executor != "heuristic" else None,
        "tool_return_max_attempts": args.tool_return_max_attempts,
        "tool_return_max_payload_chars": args.tool_return_max_payload_chars,
        "task_set_summary": task_set_summary,
        "output_path": str(output),
        "error_output_path": str(error_output),
    }
    if merge_into:
        header["merged_at"] = datetime.now(UTC).isoformat()
        header["retry_indices"] = [index for index, _task in indexed_tasks]
        header["retry_count"] = len(indexed_tasks)
    max_worker = max(1, args.max_worker)
    progress_lock = asyncio.Lock()
    write_lock = asyncio.Lock()
    semaphore = asyncio.Semaphore(max_worker)
    records_by_index: list[dict[str, Any] | None] = [None] * len(indexed_tasks)
    completed_count = 0
    checkpoint_interval = max(0, args.checkpoint_interval)

    async def persist_progress(*, force: bool = False) -> None:
        nonlocal completed_count
        async with write_lock:
            updated_records = [
                record
                for record in sorted(
                    (row for row in records_by_index if row is not None),
                    key=lambda row: int(row.get("index", 0)),
                )
            ]
            if merge_into:
                sorted_records = merge_records_by_index(
                    base_records=base_records,
                    updates=updated_records,
                    total_count=total_task_count,
                )
            else:
                sorted_records = updated_records
            is_final = completed_count == len(indexed_tasks)
            should_checkpoint = force or (
                checkpoint_interval > 0
                and (
                    is_final
                    or (completed_count > 0 and completed_count % checkpoint_interval == 0)
                )
            )
            if not should_checkpoint:
                return
            write_output(
                output,
                header,
                sorted_records,
                checkpoint=not is_final,
                completed_count=completed_count if not merge_into else total_task_count,
            )
            label = "Final" if is_final else "Checkpoint"
            scope = f"{completed_count}/{len(indexed_tasks)}"
            if merge_into:
                scope = f"{completed_count}/{len(indexed_tasks)} retry tasks -> {total_task_count} total"
            print(f"{label} wrote {output} ({scope})", flush=True)

    async def handle_task_result(row: dict[str, Any]) -> None:
        nonlocal completed_count
        slot = next(
            (slot_index for slot_index, (global_index, _task) in enumerate(indexed_tasks) if global_index == int(row.get("index", -1))),
            None,
        )
        if slot is None:
            raise ValueError(f"Unexpected task index in retry result: {row.get('index')}")
        async with write_lock:
            records_by_index[slot] = row
            completed_count += 1
            if is_error_record(row):
                append_error_record(error_output, header, row)
                print(f"Error record appended to {error_output} ({row.get('task_uid')})", flush=True)
        await persist_progress()

    async def guarded_run(slot: int, global_index: int, task: dict[str, Any]) -> dict[str, Any]:
        async with semaphore:
            row = await run_one_task(
                index=global_index,
                total=total_task_count if merge_into else len(indexed_tasks),
                task=task,
                args=args,
                system_config=system_config,
                memory_llm=memory_llm,
                memory_provider=memory_provider,
                model_client=model_client,
                tool_return_model_client=tool_return_model_client,
                progress_lock=progress_lock,
            )
            await handle_task_result(row)
            return row

    await asyncio.gather(
        *(guarded_run(slot, global_index, task) for slot, (global_index, task) in enumerate(indexed_tasks))
    )
    await persist_progress(force=True)


def main() -> None:
    asyncio.run(run(parse_args()))


if __name__ == "__main__":
    main()
