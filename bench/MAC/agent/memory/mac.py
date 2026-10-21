"""Memory-as-Contracts runtime integration for the benchmark agent loop."""

from __future__ import annotations

import inspect
import json
import os
import re
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from pathlib import Path
from threading import Lock
from typing import Any, Protocol

from bench.MAC.agent.memory.base import MemoryRequest, MemoryResult
from memory_as_contracts.adapters.base import (
    PERIODIC_USER_TURN_BATCH_SIZE,
    AdapterCapabilities,
    AdapterContext,
    BaseAdapter,
)
from memory_as_contracts.config import MacConfig
from memory_as_contracts.extractor import (
    OpenAIChatResponseProvider,
    PolicyIRContractExtractor,
    _parse_policy_ir_contracts_with_diagnostics,
)
from memory_as_contracts.hook_plan import signature_with_active_paths
from memory_as_contracts.hook_runtime import _render_user_turn_batch
from memory_as_contracts.extraction_dedup import build_similar_rule_context
from memory_as_contracts.policy_ir import policy_ir_safety
from memory_as_contracts.models import (
    ActionOutcome,
    AvailableAction,
    Contract,
    ContractEdge,
    ContractKind,
    ContractStatus,
    EdgeRelation,
    Lifecycle,
    LifecycleType,
    RuleEffect,
    SideEffect,
    Scope,
    ScopeLevel,
)
from memory_as_contracts.retrieval import DEFAULT_PROMPT_TOKEN_BUDGET
from memory_as_contracts.store import ContractStore
from memory_as_contracts.tool_capsules import ToolCapabilityCapsule
from bench.MAC.agent.memory.bm25 import BM25Index
from bench.MAC.agent.memory.retrieval import MemoryDocument


DEFAULT_MAC_STORE_DIR = Path(__file__).resolve().parents[2] / ".cache" / "mac_runtime"


class OnlineExtractor(Protocol):
    def extract_online_turn(
        self,
        *,
        role: str,
        text: str,
        context: Any,
    ) -> list[Contract]:
        ...


@dataclass(frozen=True, slots=True)
class MACMemoryConfig:
    top_k: int = 10
    token_budget: int = DEFAULT_PROMPT_TOKEN_BUDGET
    store_dir: Path = DEFAULT_MAC_STORE_DIR
    persist_store: bool = False
    load_store_dir: Path | None = None
    ask_pass: bool = False
    mem_llm_model: str = ""
    mem_api_key_env: str = "MEM_API_KEY"
    mem_base_url: str | None = None
    mem_llm_timeout_seconds: float = 60.0
    mem_llm_max_tokens: int = 4096
    extract_batch_size: int = 1
    extract_max_worker: int = 8
    unified_ops_extraction: bool = False
    unified_ops_top_k: int = 5


@dataclass(slots=True)
class MACRuntimeState:
    task_uid: str
    adapter: "BenchMACAdapter"
    store: ContractStore
    context: AdapterContext
    memory: str
    metadata: dict[str, Any]

    def close(self) -> None:
        self.store.close()


class BenchMACAdapter(BaseAdapter):
    """Bench adapter that injects host-visible tools without MAC-core schema assumptions."""

    host = "mac-bench"
    capabilities = AdapterCapabilities(
        pre_action=True,
        post_action=True,
        user_input_event=True,
        native_auto_install=False,
    )

    def __init__(
        self,
        *,
        agent: str,
        tools: list[dict[str, Any]],
        token_budget: int,
        active_paths: list[str] | None = None,
    ) -> None:
        host_tools = _host_tools(tools)
        super().__init__(
            available_actions=_available_actions_from_host_tools(host_tools),
        )
        self.agent_name = agent
        self.prompt_token_budget = token_budget
        self._tool_capsules = _tool_capsules_from_host_tools(host_tools)
        self._active_paths = tuple(_dedupe_texts(active_paths or []))

    def discover_sources(self, context: AdapterContext):
        del context
        return []

    def tool_capsules(self) -> list[ToolCapabilityCapsule]:
        return list(self._tool_capsules)

    def build_prompt_context(self, user_turn: str, context: AdapterContext):
        prompt_context = super().build_prompt_context(user_turn, context)
        return replace(prompt_context, target_paths=[*prompt_context.target_paths, *self._active_paths])

    def build_action_signature(self, event: Mapping[str, Any] | Any, context: AdapterContext):
        signature = super().build_action_signature(event, context)
        if not self._active_paths:
            return signature
        return signature_with_active_paths(signature, self._active_paths)


class MACMemoryProvider:
    """Replay historical user turns through MAC and render current prompt reminders."""

    name = "mac"

    def __init__(
        self,
        config: MACMemoryConfig | None = None,
        *,
        extractor: OnlineExtractor | None = None,
    ) -> None:
        self.config = config or MACMemoryConfig()
        self.extractor = extractor
        self._states: dict[str, MACRuntimeState] = {}

    def build_memory(self, request: MemoryRequest) -> MemoryResult:
        self.close_runtime(request.task_uid)
        llm_call_stats = {"extractor_calls": 0, "validator_calls": 0}
        active_paths = _macbench_active_paths_for_request(request)
        adapter = BenchMACAdapter(
            agent=request.agent,
            tools=_agent_tools(request),
            token_budget=self.config.token_budget,
            active_paths=active_paths,
        )
        store_path = _store_path(self.config, request.task_uid)
        if self.config.load_store_dir is not None and not Path(store_path).exists():
            raise FileNotFoundError(f"MAC store not found for reuse: {store_path}")
        store = ContractStore(store_path)
        store.init_db()
        context = _context_for_request(request)

        if self.config.load_store_dir is not None:
            try:
                prompt_text = adapter.render_prompt_context(store, request.user_prompt, context)
                contracts = store.list_contracts()
                safety_stats = _policy_safety_stats(contracts)
                metadata = {
                    "retrieval_unit": "mac_contract",
                    "runtime": "policy_ir",
                    "contract_source": "loaded_store",
                    "loaded_store_path": str(store_path),
                    "past_turn_count": len(request.past_user_turns),
                    "extracted_contract_count": len(contracts),
                    "active_contract_count": len(contracts),
                    "policy_ir_count": sum(1 for contract in contracts if contract.policy_ir is not None),
                    "unsupported_policy_count": _unsupported_policy_count(contracts),
                    **safety_stats,
                    "included_contract_count": _rendered_contract_line_count(prompt_text),
                    "top_k": self.config.top_k,
                    "token_budget": self.config.token_budget,
                    "contract_ids": [contract.id for contract in contracts],
                    "macbench_active_paths": active_paths,
                    "ask_pass": self.config.ask_pass,
                    "error": None,
                }
                state = MACRuntimeState(
                    task_uid=request.task_uid,
                    adapter=adapter,
                    store=store,
                    context=context,
                    memory=prompt_text,
                    metadata=metadata,
                )
                self._states[request.task_uid] = state
                return MemoryResult(
                    system_name=self.name,
                    memory=prompt_text,
                    metadata=metadata,
                )
            except Exception:
                store.close()
                raise

        extractor = _counting_extractor(self.extractor or _live_extractor(self.config), llm_call_stats)
        extracted: list[Contract] = []

        try:
            skipped_history_turns = 0
            for index, turn in enumerate(request.past_user_turns):
                content = turn.get("content") if isinstance(turn, dict) else None
                if not isinstance(content, str) or not content.strip():
                    continue
                should_extract = (
                    _should_extract_history_turn_unified(turn)
                    if self.config.unified_ops_extraction
                    else _should_extract_history_turn(turn)
                )
                if isinstance(turn, dict) and not should_extract:
                    skipped_history_turns += 1
                    continue
                turn_context = replace(
                    context,
                    turn_id=str(turn.get("turn_index", index)) if isinstance(turn, dict) else str(index),
                )
                scope_path = _macbench_scope_path_for_turn(turn, request.task) if isinstance(turn, dict) else None
                store.append_user_turn(
                    adapter_id=adapter.host,
                    session_id=turn_context.session_id,
                    task_id=turn_context.task_id,
                    conversation_id=turn_context.conversation_id,
                    turn_id=turn_context.turn_id,
                    text=_with_macbench_scope_header(content, scope_path),
                    observed_at=turn_context.current_time(),
                )

            if self.config.unified_ops_extraction:
                unified_provider = _CountingResponseProvider(
                    OpenAIChatResponseProvider(
                        _memory_llm_config(self.config, purpose="MAC unified ops extraction"),
                        system_prompt=UNIFIED_OPS_EXTRACTION_SYSTEM_PROMPT,
                    ),
                    llm_call_stats,
                    counter_key="extractor_calls",
                )
                extracted.extend(
                    _process_pending_user_turns_unified_ops(
                        adapter=adapter,
                        store=store,
                        response_provider=unified_provider,
                        context=context,
                        top_k=self.config.unified_ops_top_k,
                        stats=llm_call_stats,
                    )
                )
            else:
                extracted.extend(
                    _flush_pending_extractor_batches(
                        adapter=adapter,
                        store=store,
                        extractor=extractor,
                        context=context,
                        batch_size=self.config.extract_batch_size,
                        max_worker=self.config.extract_max_worker,
                        force=True,
                    )
                )

            result = adapter.process_user_prompt_submit(
                store,
                request.user_prompt,
                context,
                extractor_factory=lambda: extractor,
            )
            extracted.extend(result.extracted_contracts)
            activated_contract_ids = _activate_prompt_contracts(store, result.prompt_text)
            active_contracts = store.list_contracts([ContractStatus.ACTIVE, ContractStatus.PENDING_CONFLICT])
            safety_stats = _policy_safety_stats(active_contracts)
            metadata = {
                "retrieval_unit": "mac_contract",
                "runtime": "policy_ir",
                "contract_source": "history_user_turns",
                "past_turn_count": len(request.past_user_turns),
                "skipped_history_turn_count": skipped_history_turns,
                "extracted_contract_count": len(extracted),
                "active_contract_count": len(active_contracts),
                "policy_ir_count": sum(1 for contract in active_contracts if contract.policy_ir is not None),
                "unsupported_policy_count": _unsupported_policy_count(active_contracts),
                **safety_stats,
                "included_contract_count": _rendered_contract_line_count(result.prompt_text),
                "activated_contract_ids": sorted(activated_contract_ids),
                "top_k": self.config.top_k,
                "token_budget": self.config.token_budget,
                "contract_ids": [contract.id for contract in extracted],
                "macbench_active_paths": active_paths,
                "error": result.error,
                "extract_batch_size": PERIODIC_USER_TURN_BATCH_SIZE,
                "ir_extract_batch_size": self.config.extract_batch_size,
                "ir_extract_max_worker": self.config.extract_max_worker,
                "unified_ops_extraction": self.config.unified_ops_extraction,
                "unified_ops_top_k": self.config.unified_ops_top_k,
                "llm_call_stats": dict(llm_call_stats),
            }
            state = MACRuntimeState(
                task_uid=request.task_uid,
                adapter=adapter,
                store=store,
                context=context,
                memory=result.prompt_text,
                metadata=metadata,
            )
            self._states[request.task_uid] = state
            return MemoryResult(
                system_name=self.name,
                memory=result.prompt_text,
                metadata=metadata,
            )
        except Exception:
            store.close()
            raise

    def runtime_for_task(self, task_uid: str) -> MACRuntimeState | None:
        return self._states.get(task_uid)

    def close_runtime(self, task_uid: str) -> None:
        state = self._states.pop(task_uid, None)
        if state is not None:
            state.close()


def export_mac_constraint_graph(
    state: MACRuntimeState,
    *,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Serialize the MAC store contracts and resolver edges for offline inspection."""
    contracts = state.store.list_contracts()
    edges = state.store.list_edges()
    return {
        "schema_version": "MACBenchConstraintGraphV1",
        "task_uid": state.task_uid,
        "metadata": metadata or state.metadata,
        "contract_graph": {
            "nodes": [
                {
                    "id": contract.id,
                    "text": contract.text,
                    "source": contract.source.model_dump(mode="json"),
                    "kind": contract.kind.value,
                    "effect": contract.effect.value,
                    "status": contract.status.value,
                    "modality": contract.modality.value,
                    "strength": contract.strength.value,
                    "scope": {
                        "level": contract.scope.level.value,
                        "workspace": contract.scope.workspace,
                        "project": contract.scope.project,
                        "module": contract.scope.module,
                        "path": contract.scope.path,
                        "user_id": contract.scope.user_id,
                    },
                    "lifecycle": {
                        "type": contract.lifecycle.type.value,
                        "until_revoked": contract.lifecycle.until_revoked,
                    },
                    "semantics": {
                        "actions": list(contract.semantics.actions),
                        "tags": list(contract.semantics.tags),
                    },
                    "check_patterns": [
                        pattern.model_dump(mode="json") for pattern in contract.check_patterns
                    ],
                    "update_patterns": [
                        pattern.model_dump(mode="json") for pattern in contract.update_patterns
                    ],
                    "validator_enforcement_shape": contract.validator_enforcement_shape.value,
                    "policy_ir": contract.policy_ir,
                }
                for contract in contracts
            ],
            "edges": [
                {
                    "from": edge.from_contract,
                    "to": edge.to_contract,
                    "relation": edge.relation.value,
                    "status": edge.status.value,
                }
                for edge in edges
            ],
        },
    }


def write_mac_constraint_graph(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


class MACHookedToolExecutor:
    """ToolExecutor wrapper that runs MAC pre/post tool hooks around execution."""

    def __init__(self, *, state: MACRuntimeState, inner: Any, ask_pass: bool = False) -> None:
        self.state = state
        self.inner = inner
        self.ask_pass = ask_pass
        self.mac_events: list[dict[str, Any]] = []

    async def execute(self, *, call_id: str, name: str, arguments: Any) -> Any:
        event = {
            "tool_call_id": call_id,
            "tool_name": name,
            "tool_input": arguments if isinstance(arguments, dict) else {"value": arguments},
        }
        gate = self.state.adapter.evaluate_action(self.state.store, event, self.state.context)
        gate_payload = self.state.adapter.decision_metadata(gate)
        self.mac_events.append(
            {
                "event": "mac_pre_tool_use",
                "tool_call_id": call_id,
                "tool_name": name,
                "decision": gate.decision.decision.value,
                "reason": gate.decision.reason,
                "mac": gate_payload,
            }
        )
        decision = gate.decision.decision.value
        if decision == "reject" or (decision == "ask" and not self.ask_pass):
            blocked_items = _blocked_constraint_items(self.state.store, gate_payload)
            return _blocked_execution(call_id, name, event["tool_input"], blocked_items)

        execution = self.inner.execute(call_id=call_id, name=name, arguments=arguments)
        if inspect.isawaitable(execution):
            execution = await execution
        post_event = {
            **event,
            "tool_result": execution.result,
            "result_text": execution.content,
            "outcome": ActionOutcome.SUCCESS.value,
        }
        post = self.state.adapter.record_committed_action(self.state.store, post_event, self.state.context)
        self.mac_events.append(
            {
                "event": "mac_post_tool_use",
                "tool_call_id": call_id,
                "tool_name": name,
                **post,
            }
        )
        return execution

    def close(self) -> None:
        if hasattr(self.inner, "close"):
            self.inner.close()
        self.state.close()


class _CountingResponseProvider:
    def __init__(
        self,
        inner: Callable[[str], str],
        stats: dict[str, int],
        *,
        counter_key: str,
    ) -> None:
        self._inner = inner
        self._stats = stats
        self._counter_key = counter_key

    def __call__(self, prompt: str, *, system_prompt: str | None = None) -> str:
        self._stats[self._counter_key] = self._stats.get(self._counter_key, 0) + 1
        if system_prompt is None:
            return self._inner(prompt)
        return self._inner(prompt, system_prompt=system_prompt)


class _CountingExtractor:
    def __init__(self, inner: OnlineExtractor, stats: dict[str, int]) -> None:
        self._inner = inner
        self._stats = stats
        self._lock = Lock()

    def extract_online_turn(
        self,
        *,
        role: str,
        text: str,
        context: Any,
    ) -> list[Contract]:
        with self._lock:
            self._stats["extractor_calls"] = self._stats.get("extractor_calls", 0) + 1
        contracts = self._inner.extract_online_turn(role=role, text=text, context=context)
        self._record_result(contracts)
        return contracts

    def _record_result(self, contracts: list[Contract]) -> None:
        diagnostics = []
        drain = getattr(self._inner, "drain_diagnostics", None)
        if callable(drain):
            diagnostics = drain()
        with self._lock:
            if not contracts:
                self._stats["extractor_zero_policy_calls"] = self._stats.get("extractor_zero_policy_calls", 0) + 1
            for diagnostic in diagnostics:
                self._stats["extractor_json_errors"] = self._stats.get("extractor_json_errors", 0) + int(
                    bool(diagnostic.get("json_error"))
                )
                self._stats["extractor_policy_items"] = self._stats.get("extractor_policy_items", 0) + int(
                    diagnostic.get("policy_items") or 0
                )
                self._stats["extractor_validation_errors"] = self._stats.get("extractor_validation_errors", 0) + int(
                    diagnostic.get("validation_error_count") or 0
                )
                self._stats["extractor_unsupported"] = self._stats.get("extractor_unsupported", 0) + int(
                    diagnostic.get("unsupported_count") or 0
                )
                self._stats["extractor_missing_text"] = self._stats.get("extractor_missing_text", 0) + int(
                    diagnostic.get("missing_text_count") or 0
                )


def _counting_extractor(inner: OnlineExtractor, stats: dict[str, int]) -> _CountingExtractor:
    return _CountingExtractor(inner, stats)


def _activate_prompt_contracts(store: ContractStore, prompt_text: str) -> set[str]:
    del store
    included = set(re.findall(r"- (MAC-[A-Za-z0-9_-]+)(?: \[|:)", prompt_text))
    return included


def _should_extract_history_turn(turn: dict[str, Any]) -> bool:
    if turn.get("mentions_constraint") is True:
        return True
    if turn.get("kind") == "introduce":
        return True
    if turn.get("introduce_mode"):
        return True
    if "mentions_constraint" in turn or "kind" in turn or "introduce_mode" in turn:
        return False
    content = turn.get("content")
    return isinstance(content, str) and _looks_like_durable_constraint(content)


def _should_extract_history_turn_unified(turn: dict[str, Any]) -> bool:
    kind = str(turn.get("kind") or "").strip().lower()
    if kind in {"actual_evaluation", "carryover"}:
        return False
    if kind in {"introduce", "warmup", "update", "remove", "modify"}:
        return True
    return _should_extract_history_turn(turn)


UNIFIED_OPS_EXTRACTION_SYSTEM_PROMPT = """You extract durable runtime constraints as policy operations.

Return JSON only:
{"ops":[{"op":"noop|add|remove|replace|refine|exception","match_ids":[],"new_policy":null,"reason":""}]}

Definitions:
- A runtime constraint is a hard behavior rule that can gate future agent actions.
- add: the user introduces a new durable constraint.
- remove: the user explicitly revokes an existing candidate constraint.
- replace: the user explicitly changes an existing candidate into a new rule.
- refine: the user narrows or strengthens an existing candidate while preserving its intent.
- exception: the user grants a narrower bounded allowance against an existing candidate.
- noop: no durable runtime constraint is introduced or changed.

Rules:
- Use match_ids only from Candidate constraints.
- Only update/remove a candidate when the current turn explicitly edits that exact prior rule.
- If the current turn applies to a different path, target, or subject, use add instead of update.
- For add/replace/refine/exception, new_policy must be a complete PolicyIR object.
- For remove/noop, new_policy must be null.
- Do not extract ordinary task objectives, background facts, or one-off answer requests.
- Prefer compact observable obligations over vague semantic labels.
- Separate gated_action from satisfying_action: target is the action that may be
  blocked; monitor is the earlier action that satisfies the rule.
- For "before X, do Y", never set target to Y. If X is vague or generic, target
  response/message.send instead of pre-blocking all tools.

PolicyIR fields:
- text, effect(deny|allow|require), valid_until(null or timestamp).
- scope: {"level":"global|workspace|session|path","path":"optional/path"}.
- target: {"phase":"pre|post|response","tool":"optional exact tool","tools":[],
  "action_family":"optional family such as message.send or tool.call",
  "action_families":[]}.
- obligation: {"kind":"current_action|response|action_count|specific_tool_count|tool_count|prior_action|required_tool_usage|interaction_turn_count|sequence|same_step",
  "predicate":{"field":"response|tool_name|action_family","op":"contains|not_contains|regex|json_object|word_count_lte|char_count_lte|endswith|eq|in|lte|gte","value":...},
  "monitor":{"source":"action_log","where":{"field":"tool_name|action_family","op":"eq|in|regex","value":...},"aggregate":"count|exists|distinct_count","distinct_by":"tool_name","group_by":"turn_id"},
  "op":"lte|gte|eq|between","value":1}.
"""


def _process_pending_user_turns_unified_ops(
    *,
    adapter: BenchMACAdapter,
    store: ContractStore,
    response_provider: Callable[[str], str],
    context: AdapterContext,
    top_k: int,
    stats: dict[str, int],
) -> list[Contract]:
    extracted: list[Contract] = []
    pending = store.pending_user_turns(
        adapter_id=adapter.host,
        session_id=context.session_id,
        limit=10000,
    )
    progress = os.getenv("MAC_UNIFIED_OPS_PROGRESS", "").lower() in {"1", "true", "yes", "on"}
    total = len(pending)
    for ordinal, row in enumerate(pending, start=1):
        raw_text = str(row.get("text") or "")
        scope_path, clean_text = _split_macbench_scope_header(raw_text)
        if not clean_text.strip():
            store.mark_user_turns_extracted([int(row["seq"])])
            continue
        turn_context = adapter._extraction_context(
            replace(context, turn_id=str(row.get("turn_id") or row.get("seq") or context.turn_id))
        )
        candidates = _candidate_contracts_for_unified_ops(
            store,
            clean_text,
            context=context,
            scope_path=scope_path,
            top_k=top_k,
        )
        if progress:
            print(
                "MAC unified extraction "
                f"task={context.task_id} turn={ordinal}/{total} "
                f"seq={row.get('seq')} candidates={len(candidates)}",
                flush=True,
            )
        prompt = _render_unified_ops_prompt(
            text=clean_text,
            context=turn_context,
            scope_path=scope_path,
            candidates=candidates,
        )
        raw = response_provider(prompt)
        ops = _parse_unified_ops(raw, stats=stats)
        if progress:
            op_counts = Counter(str(op.get("op") or "unknown") for op in ops)
            print(
                "MAC unified extraction done "
                f"task={context.task_id} turn={ordinal}/{total} "
                f"ops={dict(op_counts)}",
                flush=True,
            )
        extracted.extend(
            _apply_unified_ops(
                store=store,
                ops=ops,
                context=turn_context,
                scope_path=scope_path,
                workspace=context.workspace,
                stats=stats,
            )
        )
        store.mark_user_turns_extracted([int(row["seq"])])
    return extracted


def _candidate_contracts_for_unified_ops(
    store: ContractStore,
    text: str,
    *,
    context: AdapterContext,
    scope_path: str | None,
    top_k: int,
) -> list[Contract]:
    contracts = [
        contract
        for contract in store.list_contracts([ContractStatus.ACTIVE, ContractStatus.PENDING_CONFLICT])
        if _scope_compatible_for_unified_ops(contract, context=context, scope_path=scope_path)
    ]
    if not contracts:
        return []
    if len(contracts) <= top_k:
        return contracts
    documents = [
        MemoryDocument(
            doc_id=contract.id,
            label=contract.id,
            content=_contract_candidate_text(contract),
            ordinal=index,
            turn_index=contract.id,
        )
        for index, contract in enumerate(contracts)
    ]
    scored = BM25Index(documents).search(text, top_k=top_k)
    if not scored:
        return contracts[-top_k:]
    by_id = {contract.id: contract for contract in contracts}
    return [by_id[item.document.doc_id] for item in scored if item.document.doc_id in by_id]


def _scope_compatible_for_unified_ops(
    contract: Contract,
    *,
    context: AdapterContext,
    scope_path: str | None,
) -> bool:
    level = contract.scope.level
    if level == ScopeLevel.GLOBAL:
        return True
    if level == ScopeLevel.SESSION:
        return True
    if level == ScopeLevel.WORKSPACE:
        return not contract.scope.workspace or contract.scope.workspace == context.workspace
    if level == ScopeLevel.PATH:
        if not contract.scope.path or not scope_path:
            return False
        left = contract.scope.path.rstrip("/")
        right = scope_path.rstrip("/")
        return left == right or left.startswith(right + "/") or right.startswith(left + "/")
    return False


def _render_unified_ops_prompt(
    *,
    text: str,
    context: Any,
    scope_path: str | None,
    candidates: list[Contract],
) -> str:
    candidate_payload = [
        {
            "id": contract.id,
            "text": contract.text,
            "scope": _contract_scope_summary(contract),
            "target": _policy_summary(contract, "target"),
            "obligation": _policy_summary(contract, "obligation"),
        }
        for contract in candidates
    ]
    payload = {
        "workspace": getattr(context, "workspace", None),
        "current_path_scope": scope_path,
        "current_user_turn": text,
        "candidate_constraints": candidate_payload,
    }
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)


def _parse_unified_ops(raw: str, *, stats: dict[str, int]) -> list[dict[str, Any]]:
    payload, error = _load_unified_json(raw)
    if error:
        stats["unified_ops_json_errors"] = stats.get("unified_ops_json_errors", 0) + 1
        return []
    ops = payload.get("ops") if isinstance(payload, dict) else None
    if not isinstance(ops, list):
        stats["unified_ops_json_errors"] = stats.get("unified_ops_json_errors", 0) + 1
        return []
    result: list[dict[str, Any]] = []
    allowed = {"noop", "add", "remove", "replace", "refine", "exception"}
    for item in ops:
        if not isinstance(item, dict):
            continue
        op = str(item.get("op") or "").strip().lower()
        if op not in allowed:
            continue
        match_ids = item.get("match_ids")
        result.append(
            {
                "op": op,
                "match_ids": [str(value) for value in match_ids if isinstance(value, str)]
                if isinstance(match_ids, list)
                else [],
                "new_policy": item.get("new_policy") if isinstance(item.get("new_policy"), dict) else None,
                "reason": str(item.get("reason") or ""),
            }
        )
    stats["unified_ops_items"] = stats.get("unified_ops_items", 0) + len(result)
    for op in result:
        key = f"unified_ops_{op['op']}"
        stats[key] = stats.get(key, 0) + 1
    return result


def _load_unified_json(raw: str) -> tuple[dict[str, Any], str | None]:
    try:
        return json.loads(raw), None
    except json.JSONDecodeError:
        pass
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, flags=re.DOTALL)
    if fence:
        try:
            return json.loads(fence.group(1)), None
        except json.JSONDecodeError as exc:
            return {}, str(exc)
    start = raw.find("{")
    end = raw.rfind("}")
    if start >= 0 and end > start:
        try:
            return json.loads(raw[start : end + 1]), None
        except json.JSONDecodeError as exc:
            return {}, str(exc)
    return {}, "no_json_object"


def _apply_unified_ops(
    *,
    store: ContractStore,
    ops: list[dict[str, Any]],
    context: Any,
    scope_path: str | None,
    workspace: str | None,
    stats: dict[str, int],
) -> list[Contract]:
    extracted: list[Contract] = []
    for op in ops:
        op_kind = str(op.get("op") or "")
        match_ids = [
            contract_id
            for contract_id in op.get("match_ids", [])
            if isinstance(contract_id, str) and store.get_contract(contract_id) is not None
        ]
        if op_kind == "noop":
            continue
        if op_kind == "remove":
            for contract_id in match_ids:
                store.update_contract_status(contract_id, ContractStatus.INACTIVE)
            continue
        policy = op.get("new_policy")
        if not isinstance(policy, dict):
            stats["unified_ops_missing_policy"] = stats.get("unified_ops_missing_policy", 0) + 1
            continue
        raw_policy = json.dumps({"policies": [policy]}, ensure_ascii=False)
        contracts, diagnostic = _parse_policy_ir_contracts_with_diagnostics(raw_policy, context=context)
        _record_unified_policy_diagnostic(diagnostic, stats)
        contracts = [
            _normalize_history_contract(contract, scope_path=scope_path, workspace=workspace)
            for contract in contracts
        ]
        for contract in contracts:
            store.add_contract(contract)
            extracted.append(contract)
            relation = _relation_for_unified_op(op_kind)
            if relation is not None:
                for old_id in match_ids:
                    store.add_edge(
                        ContractEdge(
                            from_contract=contract.id,
                            to_contract=old_id,
                            relation=relation,
                            scope=contract.scope,
                            lifecycle=contract.lifecycle,
                            confidence=0.85,
                        )
                    )
            if op_kind in {"replace", "refine"}:
                for old_id in match_ids:
                    store.update_contract_status(old_id, ContractStatus.SUPERSEDED)
    return extracted


def _record_unified_policy_diagnostic(diagnostic: dict[str, Any], stats: dict[str, int]) -> None:
    stats["unified_policy_items"] = stats.get("unified_policy_items", 0) + int(
        diagnostic.get("policy_items") or 0
    )
    stats["unified_policy_validation_errors"] = stats.get(
        "unified_policy_validation_errors", 0
    ) + int(diagnostic.get("validation_error_count") or 0)
    stats["unified_policy_unsupported"] = stats.get("unified_policy_unsupported", 0) + int(
        diagnostic.get("unsupported_count") or 0
    )
    if diagnostic.get("json_error"):
        stats["unified_policy_json_errors"] = stats.get("unified_policy_json_errors", 0) + 1
    errors = diagnostic.get("validation_errors")
    if isinstance(errors, list) and errors:
        stats.setdefault("unified_policy_validation_error_samples", [])
        samples = stats["unified_policy_validation_error_samples"]
        if isinstance(samples, list):
            samples.extend(errors[: max(0, 3 - len(samples))])


def _relation_for_unified_op(op_kind: str) -> EdgeRelation | None:
    if op_kind == "exception":
        return EdgeRelation.EXCEPTION_TO
    if op_kind == "refine":
        return EdgeRelation.REFINEMENT
    if op_kind == "replace":
        return EdgeRelation.SUPERSEDES
    return None


def _contract_candidate_text(contract: Contract) -> str:
    parts = [
        contract.text,
        json.dumps(_contract_scope_summary(contract), ensure_ascii=False, sort_keys=True),
        json.dumps(_policy_summary(contract, "target"), ensure_ascii=False, sort_keys=True),
        json.dumps(_policy_summary(contract, "obligation"), ensure_ascii=False, sort_keys=True),
    ]
    return "\n".join(parts)


def _contract_scope_summary(contract: Contract) -> dict[str, Any]:
    return {
        "level": contract.scope.level.value,
        "workspace": contract.scope.workspace,
        "path": contract.scope.path,
    }


def _policy_summary(contract: Contract, key: str) -> Any:
    if not isinstance(contract.policy_ir, dict):
        return None
    value = contract.policy_ir.get(key)
    if value is None:
        return None
    if isinstance(value, dict):
        return value
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    return value


def _looks_like_durable_constraint(text: str) -> bool:
    lower = text.lower()
    durable_markers = (
        "always",
        "whenever",
        "every time",
        "from now on",
        "for this project",
        "for this workspace",
        "for this session",
        "for this phase",
        "for all",
        "all future",
        "any future",
        "going forward",
        "remember to",
        "standing rule",
        "process note",
        "formatting note",
        "procedural note",
        "methodology",
    )
    constraint_markers = (
        "must",
        "must not",
        "do not",
        "don't",
        "never",
        "require",
        "at most",
        "no more than",
        "before answering",
        "format",
    )
    return any(marker in lower for marker in durable_markers) and any(
        marker in lower for marker in constraint_markers
    )


_MACBENCH_SCOPE_PREFIX = "MACBench path scope: "
_MACBENCH_PATH_ROOT = "macbench"
_TOKEN_STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "by",
    "for",
    "from",
    "in",
    "into",
    "is",
    "of",
    "on",
    "or",
    "phase",
    "project",
    "the",
    "this",
    "to",
    "with",
}


def _with_macbench_scope_header(text: str, scope_path: str | None) -> str:
    if not scope_path:
        return text
    return f"{_MACBENCH_SCOPE_PREFIX}{scope_path}\n{text}"


def _split_macbench_scope_header(text: str) -> tuple[str | None, str]:
    first, sep, rest = text.partition("\n")
    if sep and first.startswith(_MACBENCH_SCOPE_PREFIX):
        return first.removeprefix(_MACBENCH_SCOPE_PREFIX).strip() or None, rest
    return None, text


def _scope_path_from_rows(rows: list[dict[str, Any]]) -> str | None:
    paths: set[str] = set()
    for row in rows:
        text = str(row.get("text") or "")
        path, _ = _split_macbench_scope_header(text)
        if path:
            paths.add(path)
    if len(paths) == 1:
        return next(iter(paths))
    return None


def _strip_scope_headers_from_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    stripped: list[dict[str, Any]] = []
    for row in rows:
        text = str(row.get("text") or "")
        _, clean = _split_macbench_scope_header(text)
        stripped.append({**row, "text": clean})
    return stripped


def _chunk_pending_rows(rows: list[dict[str, Any]], batch_size: int) -> list[list[dict[str, Any]]]:
    chunks: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    current_path: str | None = None
    for row in rows:
        path, _ = _split_macbench_scope_header(str(row.get("text") or ""))
        if current and (len(current) >= batch_size or path != current_path):
            chunks.append(current)
            current = []
        current.append(row)
        current_path = path
    if current:
        chunks.append(current)
    return chunks


def _macbench_scope_path_for_turn(turn: dict[str, Any], task: dict[str, Any]) -> str | None:
    scope = str(turn.get("scope") or "").strip().lower()
    if scope not in {"project", "phase"}:
        return None
    text = "\n".join(
        str(value)
        for value in (turn.get("content"), turn.get("scope_expression"))
        if isinstance(value, str) and value.strip()
    )
    match = _best_grounding_match(text, _project_phase_grounding(task), require_exact=scope == "phase")
    project = match.get("project")
    phase = match.get("phase")
    if scope == "phase" and project and phase:
        return _macbench_phase_path(project, phase)
    if scope == "project" and project:
        return _macbench_project_path(project)
    return None


def _macbench_active_paths_for_request(request: MemoryRequest) -> list[str]:
    task = request.task if isinstance(request.task, dict) else {}
    grounding = _project_phase_grounding(task)
    current_turn = {}
    evaluation = task.get("evaluation") if isinstance(task.get("evaluation"), dict) else {}
    if isinstance(evaluation.get("current_user_turn"), dict):
        current_turn = evaluation["current_user_turn"]
    query_text = "\n".join(
        value
        for value in (
            request.user_prompt,
            str(current_turn.get("scope_expression") or ""),
            str(task.get("task_summary") or ""),
        )
        if value
    )
    paths: list[str] = []
    match = _best_grounding_match(query_text, grounding, require_exact=False)
    project = match.get("project")
    phase = match.get("phase")
    if project:
        paths.append(_macbench_project_path(project))
        if phase:
            paths.append(_macbench_phase_path(project, phase))
    current_scope_path = _macbench_scope_path_for_turn(current_turn, task) if current_turn else None
    if current_scope_path:
        paths.append(current_scope_path)
        parent = _macbench_parent_project_path(current_scope_path)
        if parent:
            paths.append(parent)
    elif project:
        recent_scope_path = _recent_macbench_scope_path_for_project(request.past_user_turns, task, project)
        if recent_scope_path:
            paths.append(recent_scope_path)
            parent = _macbench_parent_project_path(recent_scope_path)
            if parent:
                paths.append(parent)
    return _dedupe_texts(paths)


def _project_phase_grounding(task: dict[str, Any]) -> list[dict[str, Any]]:
    raw_task_chain = task.get("task_chain") if isinstance(task.get("task_chain"), dict) else {}
    raw_grounding = raw_task_chain.get("project_phase_grounding") or task.get("project_phase_grounding")
    projects = raw_grounding.get("projects") if isinstance(raw_grounding, dict) else None
    if not isinstance(projects, list):
        return []
    result: list[dict[str, Any]] = []
    for project in projects:
        if not isinstance(project, dict) or not isinstance(project.get("name"), str):
            continue
        phases = [
            phase
            for phase in project.get("phases", [])
            if isinstance(phase, dict) and isinstance(phase.get("name"), str)
        ]
        result.append({**project, "phases": phases})
    return result


def _best_grounding_match(
    text: str,
    grounding: list[dict[str, Any]],
    *,
    require_exact: bool,
) -> dict[str, str | None]:
    if not text or not grounding:
        return {"project": None, "phase": None}
    text_lower = text.lower()
    text_tokens = _tokens(text)
    best_project: tuple[float, dict[str, Any] | None] = (0.0, None)
    best_phase: tuple[float, dict[str, Any] | None, dict[str, Any] | None] = (0.0, None, None)
    for project in grounding:
        project_score = _grounding_score(text_lower, text_tokens, project)
        if project_score > best_project[0]:
            best_project = (project_score, project)
        for phase in project.get("phases", []):
            phase_score = _grounding_score(text_lower, text_tokens, phase)
            if phase_score > best_phase[0]:
                best_phase = (phase_score, project, phase)
    exact_threshold = 1.0
    fuzzy_threshold = 0.16
    project: dict[str, Any] | None = best_project[1]
    if require_exact and best_project[0] < exact_threshold:
        project = None
    elif not require_exact and best_project[0] < fuzzy_threshold:
        project = None
    phase_project: dict[str, Any] | None = best_phase[1]
    phase: dict[str, Any] | None = best_phase[2]
    if require_exact and best_phase[0] < exact_threshold:
        phase = None
    elif not require_exact and best_phase[0] < fuzzy_threshold:
        phase = None
    if phase and phase_project and (project is None or phase_project.get("name") == project.get("name")):
        project = phase_project
    return {
        "project": str(project.get("name")) if project else None,
        "phase": str(phase.get("name")) if phase else None,
    }


def _grounding_score(text_lower: str, text_tokens: set[str], item: dict[str, Any]) -> float:
    name = str(item.get("name") or "")
    if name and name.lower() in text_lower:
        return 1.0
    return max(
        _token_overlap_score(text_tokens, _tokens(str(item.get("name") or ""))),
        _token_overlap_score(text_tokens, _tokens(str(item.get("summary") or ""))),
    )


def _token_overlap_score(text_tokens: set[str], candidate_tokens: set[str]) -> float:
    if not text_tokens or not candidate_tokens:
        return 0.0
    overlap = text_tokens.intersection(candidate_tokens)
    return len(overlap) / max(1, min(len(candidate_tokens), len(text_tokens)))


def _project_phases(project_name: str, grounding: list[dict[str, Any]]) -> list[dict[str, Any]]:
    for project in grounding:
        if project.get("name") == project_name:
            return [phase for phase in project.get("phases", []) if isinstance(phase, dict)]
    return []


def _recent_macbench_scope_path_for_project(
    turns: list[dict[str, Any]],
    task: dict[str, Any],
    project: str,
) -> str | None:
    project_path = _macbench_project_path(project)
    for turn in reversed(turns):
        if not isinstance(turn, dict):
            continue
        path = _macbench_scope_path_for_turn(turn, task)
        if path and (path == project_path or path.startswith(project_path + "/")):
            return path
    return None


def _macbench_project_path(project: str) -> str:
    return f"{_MACBENCH_PATH_ROOT}/projects/{_slug(project)}"


def _macbench_phase_path(project: str, phase: str) -> str:
    return f"{_macbench_project_path(project)}/phases/{_slug(phase)}"


def _macbench_parent_project_path(path: str) -> str | None:
    marker = "/phases/"
    if marker not in path:
        return None
    return path.split(marker, 1)[0]


def _slug(value: str) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return cleaned or "unknown"


def _tokens(value: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z0-9]+", value.lower())
        if token not in _TOKEN_STOPWORDS and len(token) > 1
    }


def _dedupe_texts(values: list[str] | tuple[str, ...]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        normalized = str(value).replace("\\", "/").removeprefix("./").rstrip("/")
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        result.append(normalized)
    return result


def _flush_pending_extractor_batches(
    *,
    adapter: BenchMACAdapter,
    store: ContractStore,
    extractor: OnlineExtractor,
    context: AdapterContext,
    batch_size: int = PERIODIC_USER_TURN_BATCH_SIZE,
    max_worker: int = 1,
    force: bool = False,
) -> list[Contract]:
    extracted: list[Contract] = []
    if force:
        pending = store.pending_user_turns(
            adapter_id=adapter.host,
            session_id=context.session_id,
            limit=10000,
        )
        if not pending:
            return []
        chunks = _chunk_pending_rows(pending, batch_size)
        workers = max(1, min(8, max_worker, len(chunks)))

        def extract_chunk(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[Contract]]:
            scope_path = _scope_path_from_rows(rows)
            batch_text = _render_user_turn_batch(_strip_scope_headers_from_rows(rows))
            if scope_path:
                batch_text = f"{_MACBENCH_SCOPE_PREFIX}{scope_path}\n\n{batch_text}"
            extraction_context = adapter._extraction_context(context)
            candidates = extractor.extract_online_turn(
                role="user",
                text=batch_text,
                context=extraction_context,
            )
            return rows, [
                _normalize_history_contract(contract, scope_path=scope_path, workspace=context.workspace)
                for contract in candidates
            ]

        if workers == 1:
            results = [extract_chunk(chunk) for chunk in chunks]
        else:
            with ThreadPoolExecutor(max_workers=workers) as executor:
                results = list(executor.map(extract_chunk, chunks))
        for rows, candidates in results:
            resolved = adapter._resolve_and_store(store, candidates, context)
            store.mark_user_turns_extracted(row["seq"] for row in rows)
            extracted.extend(resolved)
        return extracted

    while True:
        pending = store.pending_user_turns(
            adapter_id=adapter.host,
            session_id=context.session_id,
            limit=batch_size,
        )
        if not pending or (len(pending) < batch_size and not force):
            break
        pending = _chunk_pending_rows(pending, batch_size)[0]
        scope_path = _scope_path_from_rows(pending)
        batch_text = _render_user_turn_batch(_strip_scope_headers_from_rows(pending))
        if scope_path:
            batch_text = f"{_MACBENCH_SCOPE_PREFIX}{scope_path}\n\n{batch_text}"
        extraction_context = adapter._extraction_context(context)
        similar_rule_context = build_similar_rule_context(
            store,
            batch_text,
            extraction_context,
            limit=5,
        )
        if similar_rule_context:
            extraction_context = replace(
                extraction_context,
                similar_rules_system_prompt=similar_rule_context,
            )
        candidates = extractor.extract_online_turn(
            role="user",
            text=batch_text,
            context=extraction_context,
        )
        candidates = [
            _normalize_history_contract(contract, scope_path=scope_path, workspace=context.workspace)
            for contract in candidates
        ]
        resolved = adapter._resolve_and_store(store, candidates, context)
        store.mark_user_turns_extracted(row["seq"] for row in pending)
        extracted.extend(resolved)
    return extracted


def _live_extractor(config: MACMemoryConfig) -> PolicyIRContractExtractor:
    provider = OpenAIChatResponseProvider(_memory_llm_config(config, purpose="MAC memory extraction"))
    return PolicyIRContractExtractor(provider)


def _memory_llm_config(config: MACMemoryConfig, *, purpose: str) -> MacConfig:
    if not config.mem_llm_model:
        raise RuntimeError(f"Missing MEM_LLM_MODEL for {purpose}")
    api_key = os.getenv(config.mem_api_key_env)
    if not api_key:
        raise RuntimeError(f"Missing {config.mem_api_key_env} for {purpose}")
    return MacConfig(
        openai_api_key=api_key,
        openai_base_url=config.mem_base_url,
        llm_model=config.mem_llm_model,
        llm_max_tokens=config.mem_llm_max_tokens,
        db_path=Path(":memory:"),
        llm_timeout_seconds=config.mem_llm_timeout_seconds,
        log_path=Path(".mac/mac.log"),
        log_level="INFO",
    )


def _normalize_history_contract(
    contract: Contract,
    *,
    scope_path: str | None = None,
    workspace: str | None = None,
) -> Contract:
    effect = contract.effect
    if effect == RuleEffect.PREFER:
        effect = _effect_for_kind(contract.kind)
    lifecycle = contract.lifecycle
    if lifecycle.type == LifecycleType.IMMEDIATE:
        lifecycle = Lifecycle(
            type=LifecycleType.UNTIL_REVOKED,
            effective_from=lifecycle.effective_from,
            until_revoked=True,
            original_text=lifecycle.original_text or "history user turn",
        )
    updates: dict[str, Any] = {"effect": effect, "lifecycle": lifecycle}
    if scope_path:
        scope = Scope(
            level=ScopeLevel.PATH,
            workspace=workspace or contract.scope.workspace,
            path=scope_path,
            user_id=contract.scope.user_id,
        )
        updates["scope"] = scope
        if isinstance(contract.policy_ir, dict):
            policy_ir = dict(contract.policy_ir)
            policy_ir["scope"] = {"level": "path", "path": scope_path}
            updates["policy_ir"] = policy_ir
    return contract.model_copy(update=updates)


def _effect_for_kind(kind: ContractKind) -> RuleEffect:
    if kind == ContractKind.PROHIBITION:
        return RuleEffect.DENY
    if kind == ContractKind.EXCEPTION:
        return RuleEffect.ALLOW
    if kind in {ContractKind.REQUIREMENT, ContractKind.PROCEDURE}:
        return RuleEffect.REQUIRE
    return RuleEffect.PREFER


def _context_for_request(request: MemoryRequest) -> AdapterContext:
    task = request.task if isinstance(request.task, dict) else {}
    workspace = str(task.get("workspace") or Path.cwd())
    return AdapterContext(
        workspace=workspace,
        cwd=workspace,
        repo=str(task.get("repo")) if task.get("repo") else None,
        branch=str(task.get("branch")) if task.get("branch") else None,
        session_id=request.task_uid,
        conversation_id=request.task_uid,
        task_id=request.task_uid,
        turn_id="current",
    )


def _task_tools(task: dict[str, Any]) -> list[dict[str, Any]]:
    tools = task.get("tools") if isinstance(task, dict) else None
    return [tool for tool in tools if isinstance(tool, dict)] if isinstance(tools, list) else []


def _agent_tools(request: MemoryRequest) -> list[dict[str, Any]]:
    if request.agent_tools:
        return [tool for tool in request.agent_tools if isinstance(tool, dict)]
    return _task_tools(request.task)


def _host_tools(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [tool for tool in tools if isinstance(tool, dict) and isinstance(tool.get("name"), str)]


def _available_actions_from_host_tools(tools: list[dict[str, Any]]) -> list[AvailableAction]:
    actions: list[AvailableAction] = []
    seen: set[str] = set()
    for tool in tools:
        name = tool.get("name")
        if not isinstance(name, str) or not name:
            continue
        schema = tool.get("input_schema") if isinstance(tool.get("input_schema"), dict) else {}
        tags = [str(tag) for tag in tool.get("canonical_tags", []) if isinstance(tag, str)]
        side_effect = _side_effect(tool)
        description = str(tool.get("description") or "")
        for action_name in _host_action_names(name):
            if action_name in seen:
                continue
            seen.add(action_name)
            actions.append(
                AvailableAction(
                    name=action_name,
                    argument_schema=schema,
                    canonical_tags=tags,
                    side_effect=side_effect,
                    description=description,
                )
            )
    return actions


def _host_action_names(tool_name: str) -> list[str]:
    normalized = tool_name.lower().replace("-", "_").replace(".", "_")
    aliases = {
        "send_message": "message.send",
        "message_send": "message.send",
        "message": "message.send",
        "notify": "message.send",
        "slack": "message.send",
        "sessions_send": "message.send",
        "send_email": "email.send",
        "email_send": "email.send",
        "memory_record": "memory.write",
        "memory_write": "memory.write",
        "websearch": "web.search",
        "web_search": "web.search",
        "webfetch": "web.search",
        "web_fetch": "web.search",
        "filewrite": "file.write",
        "file_write": "file.write",
        "filedelete": "file.delete",
        "file_delete": "file.delete",
    }
    canonical = aliases.get(normalized)
    if canonical is None or canonical == tool_name:
        return [tool_name]
    return [tool_name, canonical]


def _tool_capsules_from_host_tools(tools: list[dict[str, Any]]) -> list[ToolCapabilityCapsule]:
    capsules: list[ToolCapabilityCapsule] = []
    seen: set[str] = set()
    for tool in tools:
        name = tool.get("name")
        if not isinstance(name, str) or not name or name in seen:
            continue
        seen.add(name)
        schema = tool.get("input_schema") if isinstance(tool.get("input_schema"), dict) else {}
        capsules.append(
            ToolCapabilityCapsule(
                name=name,
                description=str(tool.get("description") or ""),
                input_schema=schema,
            )
        )
    return capsules


def _side_effect(tool: Mapping[str, Any]) -> SideEffect:
    raw = str(tool.get("side_effect") or "").lower()
    if raw in {item.value for item in SideEffect}:
        return SideEffect(raw)
    name = str(tool.get("name") or "").lower()
    if any(token in name for token in ("search", "read", "find", "lookup", "get")):
        return SideEffect.READ
    if any(token in name for token in ("send", "write", "create", "delete", "update", "book")):
        return SideEffect.WRITE
    return SideEffect.READ


def _store_path(config: MACMemoryConfig, task_uid: str) -> str | Path:
    if config.load_store_dir is not None:
        base = config.load_store_dir
    elif config.persist_store:
        base = config.store_dir
    else:
        return ":memory:"
    safe_task = "".join(char if char.isalnum() or char in {"-", "_"} else "_" for char in task_uid)
    return base / f"{safe_task}.sqlite"


def _rendered_contract_line_count(memory: str) -> int:
    return sum(1 for line in memory.splitlines() if line.startswith("- "))


def _unsupported_policy_count(contracts: list[Contract]) -> int:
    count = 0
    for contract in contracts:
        policy = contract.policy_ir
        if isinstance(policy, dict) and policy.get("unsupported_reason"):
            count += 1
    return count


def _policy_safety_stats(contracts: list[Contract]) -> dict[str, int]:
    demoted = 0
    disabled = 0
    self_lock = 0
    for contract in contracts:
        if not isinstance(contract.policy_ir, dict):
            continue
        result = policy_ir_safety(contract)
        if result.decision == "demote_to_response":
            demoted += 1
        elif result.decision == "disable_enforcement":
            disabled += 1
        if result.reason in {"self_lock_same_tool", "generic_tool_call_prior_action"}:
            self_lock += 1
    return {
        "policy_safety_demoted_count": demoted,
        "policy_safety_disabled_count": disabled,
        "self_lock_prevented_count": self_lock,
    }


def _blocked_constraint_items(store: ContractStore, mac: dict[str, Any]) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    verdicts = mac.get("validator_verdicts") if isinstance(mac.get("validator_verdicts"), list) else []
    verdict_by_contract: dict[str, dict[str, Any]] = {}
    for verdict in verdicts:
        if not isinstance(verdict, dict):
            continue
        if verdict.get("decision") != "reject":
            continue
        contract_id = verdict.get("contract_id")
        if isinstance(contract_id, str):
            verdict_by_contract[contract_id] = verdict
    for contract_id in mac.get("contracts_used", []):
        if not isinstance(contract_id, str):
            continue
        contract = store.get_contract(contract_id)
        if contract is None:
            continue
        if verdict_by_contract and contract_id not in verdict_by_contract:
            continue
        verdict = verdict_by_contract.get(contract_id, {})
        evidence = verdict.get("evidence") if isinstance(verdict.get("evidence"), dict) else {}
        hint = evidence.get("repair_hint") if isinstance(evidence.get("repair_hint"), str) else ""
        items.append({"text": contract.text, "repair": hint})
    return items


def _blocked_execution(call_id: str, name: str, arguments: dict[str, Any], constraints: list[str | dict[str, str]]):
    from bench.MAC.agent.loop.tools import ToolExecution

    normalized = _normalize_blocked_constraints(constraints)
    quoted_constraints = (
        "; ".join(f'"{item["text"]}"' for item in normalized)
        if normalized
        else "the active memory constraint"
    )
    lines = [f"[memory] This tool call is not allowed due to {quoted_constraints}. Please retry after revise."]
    if normalized:
        lines.append("Violations:")
        for item in normalized:
            lines.append(f"- {item['text']}")
            if item.get("repair"):
                lines.append(f"  repair: {item['repair']}")
    message = "\n".join(lines)
    return ToolExecution(
        name=name,
        call_id=call_id,
        arguments=arguments,
        result={
            "ok": False,
            "error": message,
            "message": message,
            "constraints": [item["text"] for item in normalized],
            "constraint_repairs": normalized,
            "memory_rejected": True,
        },
    )


def _normalize_blocked_constraints(constraints: list[str | dict[str, str]]) -> list[dict[str, str]]:
    normalized: list[dict[str, str]] = []
    for item in constraints:
        if isinstance(item, str):
            text = item.strip()
            repair = ""
        elif isinstance(item, dict):
            text = str(item.get("text") or "").strip()
            repair = str(item.get("repair") or "").strip()
        else:
            continue
        if text:
            normalized.append({"text": text, "repair": repair})
    return normalized
