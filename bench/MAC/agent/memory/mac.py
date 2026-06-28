"""Memory-as-Contracts runtime integration for the benchmark agent loop."""

from __future__ import annotations

import inspect
import json
import os
from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from pathlib import Path
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
    CandidateJsonContractExtractor,
    OpenAIChatResponseProvider,
)
from memory_as_contracts.hook_runtime import _render_user_turn_batch
from memory_as_contracts.extraction_dedup import build_similar_rule_context
from memory_as_contracts.validator_generation import (
    VALIDATOR_GENERATION_SYSTEM_PROMPT,
    ValidatorSnippetGenerator,
)
from memory_as_contracts.models import (
    ActionOutcome,
    AvailableAction,
    Contract,
    ContractKind,
    Lifecycle,
    LifecycleType,
    RuleEffect,
    SideEffect,
)
from memory_as_contracts.retrieval import DEFAULT_PROMPT_TOKEN_BUDGET
from memory_as_contracts.store import ContractStore
from memory_as_contracts.tool_capsules import ToolCapabilityCapsule
from memory_as_contracts.validator_generation import ValidatorSnippetPackage


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
    live_validator: bool = False
    mem_llm_model: str = ""
    mem_api_key_env: str = "MEM_API_KEY"
    mem_base_url: str | None = None
    mem_llm_timeout_seconds: float = 60.0
    mem_llm_max_tokens: int = 4096


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
        memory_config: MACMemoryConfig | None = None,
        live_validator: bool = False,
        llm_call_stats: dict[str, int] | None = None,
    ) -> None:
        host_tools = _host_tools(tools)
        stats = llm_call_stats if llm_call_stats is not None else {}
        if live_validator:
            def validator_factory() -> ValidatorSnippetGenerator | _FailValidatorGenerator:
                return _live_validator_generator(memory_config or MACMemoryConfig(), stats)
        else:
            def validator_factory() -> _FailValidatorGenerator:
                return _FailValidatorGenerator()

        super().__init__(
            available_actions=_available_actions_from_host_tools(host_tools),
            validator_generator_factory=validator_factory,
        )
        self.agent_name = agent
        self.prompt_token_budget = token_budget
        self._tool_capsules = _tool_capsules_from_host_tools(host_tools)

    def discover_sources(self, context: AdapterContext):
        del context
        return []

    def tool_capsules(self) -> list[ToolCapabilityCapsule]:
        return list(self._tool_capsules)


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
        adapter = BenchMACAdapter(
            agent=request.agent,
            tools=_agent_tools(request),
            token_budget=self.config.token_budget,
            memory_config=self.config,
            live_validator=self.config.live_validator,
            llm_call_stats=llm_call_stats,
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
                metadata = {
                    "retrieval_unit": "mac_contract",
                    "contract_source": "loaded_store",
                    "loaded_store_path": str(store_path),
                    "past_turn_count": len(request.past_user_turns),
                    "extracted_contract_count": len(contracts),
                    "active_contract_count": len(contracts),
                    "included_contract_count": _rendered_contract_line_count(prompt_text),
                    "top_k": self.config.top_k,
                    "token_budget": self.config.token_budget,
                    "contract_ids": [contract.id for contract in contracts],
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
            for index, turn in enumerate(request.past_user_turns):
                content = turn.get("content") if isinstance(turn, dict) else None
                if not isinstance(content, str) or not content.strip():
                    continue
                turn_context = replace(
                    context,
                    turn_id=str(turn.get("turn_index", index)) if isinstance(turn, dict) else str(index),
                )
                store.append_user_turn(
                    adapter_id=adapter.host,
                    session_id=turn_context.session_id,
                    task_id=turn_context.task_id,
                    conversation_id=turn_context.conversation_id,
                    turn_id=turn_context.turn_id,
                    text=content,
                    observed_at=turn_context.current_time(),
                )
                extracted.extend(
                    _flush_pending_extractor_batches(
                        adapter=adapter,
                        store=store,
                        extractor=extractor,
                        context=turn_context,
                    )
                )

            result = adapter.process_user_prompt_submit(
                store,
                request.user_prompt,
                context,
                extractor_factory=lambda: extractor,
            )
            extracted.extend(result.extracted_contracts)
            metadata = {
                "retrieval_unit": "mac_contract",
                "contract_source": "history_user_turns",
                "past_turn_count": len(request.past_user_turns),
                "extracted_contract_count": len(extracted),
                "active_contract_count": len(store.list_contracts()),
                "included_contract_count": _rendered_contract_line_count(result.prompt_text),
                "top_k": self.config.top_k,
                "token_budget": self.config.token_budget,
                "contract_ids": [contract.id for contract in extracted],
                "error": result.error,
                "extract_batch_size": PERIODIC_USER_TURN_BATCH_SIZE,
                "live_validator": self.config.live_validator,
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
            constraint_texts = _constraint_texts(self.state.store, gate_payload)
            return _blocked_execution(call_id, name, event["tool_input"], constraint_texts)

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


class _FailValidatorGenerator:
    def generate_verified(self, *args: Any, **kwargs: Any) -> ValidatorSnippetPackage:
        del args, kwargs
        return ValidatorSnippetPackage(
            status="fail",
            notes=["bench MAC runtime does not call a live validator generator by default"],
        )


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

    def extract_online_turn(
        self,
        *,
        role: str,
        text: str,
        context: Any,
    ) -> list[Contract]:
        self._stats["extractor_calls"] = self._stats.get("extractor_calls", 0) + 1
        return self._inner.extract_online_turn(role=role, text=text, context=context)


def _counting_extractor(inner: OnlineExtractor, stats: dict[str, int]) -> _CountingExtractor:
    return _CountingExtractor(inner, stats)


def _flush_pending_extractor_batches(
    *,
    adapter: BenchMACAdapter,
    store: ContractStore,
    extractor: OnlineExtractor,
    context: AdapterContext,
) -> list[Contract]:
    extracted: list[Contract] = []
    while True:
        pending = store.pending_user_turns(
            adapter_id=adapter.host,
            session_id=context.session_id,
            limit=PERIODIC_USER_TURN_BATCH_SIZE,
        )
        if len(pending) < PERIODIC_USER_TURN_BATCH_SIZE:
            break
        batch_text = _render_user_turn_batch(pending)
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
        candidates = [_normalize_history_contract(contract) for contract in candidates]
        resolved = adapter._resolve_and_store(store, candidates, context)
        store.mark_user_turns_extracted(row["seq"] for row in pending)
        extracted.extend(resolved)
    return extracted


def _live_validator_generator(
    config: MACMemoryConfig,
    stats: dict[str, int],
) -> ValidatorSnippetGenerator:
    provider = OpenAIChatResponseProvider(
        _memory_llm_config(config, purpose="MAC validator generation"),
        system_prompt=VALIDATOR_GENERATION_SYSTEM_PROMPT,
    )
    counting_provider = _CountingResponseProvider(
        provider,
        stats,
        counter_key="validator_calls",
    )
    return ValidatorSnippetGenerator(counting_provider)


def _live_extractor(config: MACMemoryConfig) -> CandidateJsonContractExtractor:
    provider = OpenAIChatResponseProvider(_memory_llm_config(config, purpose="MAC memory extraction"))
    return CandidateJsonContractExtractor(provider)


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


def _normalize_history_contract(contract: Contract) -> Contract:
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
    return contract.model_copy(update={"effect": effect, "lifecycle": lifecycle})


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


def _constraint_texts(store: ContractStore, mac: dict[str, Any]) -> list[str]:
    texts: list[str] = []
    for contract_id in mac.get("contracts_used", []):
        if not isinstance(contract_id, str):
            continue
        contract = store.get_contract(contract_id)
        if contract is not None:
            texts.append(contract.text)
    return texts


def _blocked_execution(call_id: str, name: str, arguments: dict[str, Any], constraints: list[str]):
    from bench.MAC.agent.loop.tools import ToolExecution

    return ToolExecution(
        name=name,
        call_id=call_id,
        arguments=arguments,
        result={
            "ok": False,
            "error": "MAC constraint blocked tool call",
            "constraints": constraints,
        },
    )
