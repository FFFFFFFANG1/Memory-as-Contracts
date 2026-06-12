from __future__ import annotations

import hashlib
import logging
from collections.abc import Callable, Mapping
from dataclasses import replace
from typing import Any

from memory_as_contracts.extraction_dedup import build_similar_rule_context
from memory_as_contracts.extractor import LLMCallError
from memory_as_contracts.gate import ActionGate, GateResult
from memory_as_contracts.logging_config import log_event
from memory_as_contracts.models import (
    ActionLogEntryV1,
    ActionOutcome,
    Contract,
    ContractStatus,
    ValidatorEnforcementShape,
    ValidatorInstallationRecord,
    ValidatorInstallationStatus,
)
from memory_as_contracts.pattern_validation import PatternInstaller, PatternVerifier
from memory_as_contracts.resolver import ConflictResolver
from memory_as_contracts.retrieval import PromptIntakeRetriever
from memory_as_contracts.store import ContractStore
from memory_as_contracts.validator_installation import ValidatorProvisioner
from memory_as_contracts.validators import ValidatorRuntime


PERIODIC_USER_TURN_BATCH_SIZE = 10
LOGGER = logging.getLogger(__name__)


class MacHookRuntime:
    """Own host-independent MAC hook ordering and persistence."""

    def __init__(self, adapter: Any) -> None:
        self.adapter = adapter

    def cold_start_import(
        self,
        store: ContractStore,
        extractor: Any,
        context: Any,
    ) -> list[Contract]:
        contracts: list[Contract] = []
        for spec in self.adapter.discover_sources(context):
            content = spec.path.read_text(encoding="utf-8", errors="replace")
            fingerprint = _fingerprint(content)
            extracted = extractor.extract_cold_start_source(
                text=self.adapter._cold_start_source_text(spec, content),
                source_kind=spec.source_kind,
                context=self.adapter._extraction_context(context),
                path=str(spec.path),
                fingerprint=fingerprint,
            )
            resolved = self.resolve_and_store(store, extracted, context)
            store.add_source_snapshot(
                self.adapter._snapshot(spec, content, fingerprint, context)
            )
            contracts.extend(resolved)
        return contracts

    def render_prompt_context(
        self,
        store: ContractStore,
        user_turn: str,
        context: Any,
    ) -> str:
        retriever = PromptIntakeRetriever(store)
        prompt_context = self.adapter.build_prompt_context(user_turn, context)
        packets = retriever.retrieve(prompt_context)
        return retriever.render_prompt_text(
            packets,
            token_budget=self.adapter.prompt_token_budget,
        )

    def gate(
        self,
        store: ContractStore,
        event: Mapping[str, Any] | Any,
        context: Any,
    ) -> GateResult:
        signature = self.adapter.build_action_signature(event, context)
        return ActionGate(
            store,
            exclude_actions=self.adapter.exclude_actions,
        ).gate(
            signature,
            tool_family=self.adapter.tool_family(signature.tool.name),
        )

    def observe_user_input(
        self,
        store: ContractStore,
        context: Any,
    ):
        return store.mark_user_input_observed(
            session_id=context.session_id,
            task_id=context.task_id,
            adapter_id=self.adapter.host,
            turn_id=context.turn_id,
            observed_at=context.current_time(),
        )

    def process_user_prompt_submit(
        self,
        store: ContractStore,
        user_turn: str,
        context: Any,
        *,
        extractor_factory: Callable[[], Any] | None = None,
    ):
        from memory_as_contracts.adapters.base import AdapterResult

        self.observe_user_input(store, context)
        log_event(
            LOGGER,
            "user_turn.observed",
            adapter=self.adapter.host,
            session_id=context.session_id,
            task_id=context.task_id,
            turn_id=context.turn_id,
        )
        store.append_user_turn(
            adapter_id=self.adapter.host,
            session_id=context.session_id,
            task_id=context.task_id,
            conversation_id=context.conversation_id,
            turn_id=context.turn_id,
            text=user_turn,
            observed_at=context.current_time(),
        )
        pending = store.pending_user_turns(
            adapter_id=self.adapter.host,
            session_id=context.session_id,
            limit=PERIODIC_USER_TURN_BATCH_SIZE,
        )
        factory = (
            extractor_factory
            or self.adapter._online_extractor_factory
            or _default_online_extractor_factory
        )
        error: dict[str, Any] | None = None
        cold_start_extracted: list[Contract] = []
        extracted: list[Contract] = []
        if self.should_cold_start_once(store, context):
            log_event(
                LOGGER,
                "cold_start.started",
                adapter=self.adapter.host,
                session_id=context.session_id,
            )
            try:
                cold_start_extracted = self.cold_start_import(
                    store,
                    factory(),
                    context,
                )
            except LLMCallError as exc:
                error = exc.as_dict()
                log_event(
                    LOGGER,
                    "cold_start.failed",
                    level=logging.ERROR,
                    adapter=self.adapter.host,
                    session_id=context.session_id,
                    error_code=exc.code,
                    attempts=exc.attempts,
                )
            else:
                log_event(
                    LOGGER,
                    "cold_start.completed",
                    adapter=self.adapter.host,
                    session_id=context.session_id,
                    contract_count=len(cold_start_extracted),
                )
        if len(pending) == PERIODIC_USER_TURN_BATCH_SIZE:
            log_event(
                LOGGER,
                "extraction.started",
                adapter=self.adapter.host,
                session_id=context.session_id,
                turn_count=len(pending),
            )
            try:
                batch_text = _render_user_turn_batch(pending)
                extraction_context = self.adapter._extraction_context(context)
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
                candidates = factory().extract_online_turn(
                    role="user",
                    text=batch_text,
                    context=extraction_context,
                )
            except LLMCallError as exc:
                error = exc.as_dict()
                log_event(
                    LOGGER,
                    "extraction.failed",
                    level=logging.ERROR,
                    adapter=self.adapter.host,
                    session_id=context.session_id,
                    error_code=exc.code,
                    attempts=exc.attempts,
                )
            else:
                extracted = self.resolve_and_store(store, candidates, context)
                store.mark_user_turns_extracted(row["seq"] for row in pending)
                log_event(
                    LOGGER,
                    "extraction.completed",
                    adapter=self.adapter.host,
                    session_id=context.session_id,
                    contract_count=len(extracted),
                )
        prompt_text = self.render_prompt_context(store, user_turn, context)
        return AdapterResult(
            prompt_text=prompt_text,
            extracted_contracts=[*cold_start_extracted, *extracted],
            error=error,
        )

    def record_committed_action(
        self,
        store: ContractStore,
        event: Mapping[str, Any] | Any,
        context: Any,
    ) -> dict[str, Any]:
        signature = self.adapter.build_action_signature(event, context)
        result = _event_value(
            event,
            "tool_result",
            _event_value(event, "result", None),
        )
        result_text = _event_value(
            event,
            "result_text",
            _event_value(event, "content", ""),
        )
        if not result_text and result is not None:
            result_text = str(result)
        tool_call_id = _event_value(
            event,
            "tool_call_id",
            _event_value(event, "id", None),
        )
        if tool_call_id is None:
            tool_call_id = _fingerprint(
                f"{signature.session.session_id}:{signature.tool.name}:"
                f"{signature.tool.raw_arguments}:{result_text}"
            )
        entry = ActionLogEntryV1(
            adapter_id=self.adapter.host,
            session_id=signature.session.session_id,
            agent_id=self.adapter.agent_name,
            tool_call_id=str(tool_call_id),
            tool_name=signature.tool.name,
            host_action=signature.host_action,
            arguments=signature.tool.raw_arguments,
            result=result,
            result_text=str(result_text or ""),
            outcome=_event_outcome(event),
            timestamp=context.current_time(),
            reasoning_text=_event_value(event, "reasoning_content", None),
            conversation_id=context.conversation_id,
            turn_id=context.turn_id,
            user_id=context.user_id,
            workspace=str(context.workspace_path()),
            repo=context.repo,
            branch=context.branch,
            targets=signature.targets,
            risk=signature.risk,
            side_effect=signature.side_effect,
        )
        stored = ValidatorRuntime(store).record_committed_action(entry)
        log_event(
            LOGGER,
            "action.committed",
            adapter=self.adapter.host,
            session_id=stored.session_id,
            tool_name=stored.tool_name,
            action_log_seq=stored.seq,
            outcome=stored.outcome.value,
        )
        return {
            "mac": {
                "action_log_seq": stored.seq,
                "tool_call_id": stored.tool_call_id,
                "outcome": stored.outcome.value,
            }
        }

    def resolve_and_store(
        self,
        store: ContractStore,
        contracts: list[Contract],
        context: Any,
    ) -> list[Contract]:
        if not contracts:
            return []
        resolver = (
            self.adapter._conflict_resolver_factory(store)
            if self.adapter._conflict_resolver_factory is not None
            else ConflictResolver(store)
        )
        resolved: list[Contract] = []
        for result in resolver.insert_batch(contracts):
            contract = result.contract
            if contract.status in {
                ContractStatus.ACTIVE,
                ContractStatus.CANDIDATE,
                ContractStatus.PENDING_CONFLICT,
            }:
                installed = PatternInstaller(
                    store=store,
                    verifier=PatternVerifier(self.adapter.tool_capsules()),
                    response_provider=_build_pattern_refiner(
                        self.adapter._pattern_refiner_factory
                    ),
                ).install(contract)
                contract = installed.contract
                log_event(
                    LOGGER,
                    "pattern.verification",
                    level=(
                        logging.INFO
                        if installed.verification.accepted
                        else logging.WARNING
                    ),
                    contract_id=contract.id,
                    accepted=installed.verification.accepted,
                    refined=installed.refined,
                    errors=[
                        issue.code for issue in installed.verification.issues
                    ],
                )
            resolved.append(contract)

        for contract in resolved:
            if (
                contract.status != ContractStatus.ACTIVE
                or contract.validator_enforcement_shape
                == ValidatorEnforcementShape.NO_VALIDATOR
            ):
                continue
            factory = (
                self.adapter._validator_generator_factory
                or _default_validator_generator_factory
            )
            try:
                installation = ValidatorProvisioner(factory()).provision(
                    contract,
                    store=store,
                    session_id=context.session_id,
                    task_id=context.task_id,
                    tool_capsules=self.adapter.tool_capsules(),
                    user_id=context.user_id,
                    workspace=str(context.workspace_path()),
                    repo=context.repo,
                    branch=context.branch,
                    organization=context.organization,
                    supports_post_action=self.adapter.capabilities.post_action,
                )
            except (LLMCallError, ValueError) as exc:
                store.add_validator_installation(
                    ValidatorInstallationRecord(
                        contract_id=contract.id,
                        status=ValidatorInstallationStatus.MANUAL_REVIEW,
                        errors=[str(exc)],
                    )
                )
                log_event(
                    LOGGER,
                    "validator.installation",
                    level=logging.ERROR,
                    contract_id=contract.id,
                    status=ValidatorInstallationStatus.MANUAL_REVIEW.value,
                    error_type=exc.__class__.__name__,
                )
                continue
            log_event(
                LOGGER,
                "validator.installation",
                contract_id=contract.id,
                status=installation.status,
                error_count=len(installation.errors),
            )
        return resolved

    def should_cold_start_once(self, store: ContractStore, context: Any) -> bool:
        specs = self.adapter.discover_sources(context)
        if not specs:
            return False
        workspace = str(context.workspace_path())
        return not any(
            snapshot.adapter == self.adapter.agent_name
            and snapshot.workspace == workspace
            for snapshot in store.list_source_snapshots()
        )


def _render_user_turn_batch(rows: list[Mapping[str, Any]]) -> str:
    return "\n\n".join(
        f"User turn {index} [{row.get('turn_id') or row['seq']}]:\n{row['text']}"
        for index, row in enumerate(rows, start=1)
    )


def _default_online_extractor_factory():
    from memory_as_contracts.extractor import (
        CandidateJsonContractExtractor,
        OpenAIChatResponseProvider,
    )

    return CandidateJsonContractExtractor(OpenAIChatResponseProvider.from_env())


def _default_validator_generator_factory():
    from memory_as_contracts.extractor import OpenAIChatResponseProvider
    from memory_as_contracts.validator_generation import (
        VALIDATOR_GENERATION_SYSTEM_PROMPT,
        ValidatorSnippetGenerator,
    )

    return ValidatorSnippetGenerator(
        OpenAIChatResponseProvider.from_env(
            system_prompt=VALIDATOR_GENERATION_SYSTEM_PROMPT,
        )
    )


def default_pattern_refiner_factory() -> Callable[[str], str]:
    from memory_as_contracts.extractor import OpenAIChatResponseProvider
    from memory_as_contracts.pattern_validation import (
        PATTERN_REFINEMENT_SYSTEM_PROMPT,
    )

    return OpenAIChatResponseProvider.from_env(
        system_prompt=PATTERN_REFINEMENT_SYSTEM_PROMPT,
    )


def _build_pattern_refiner(
    factory: Callable[[], Callable[[str], str]] | None,
) -> Callable[[str], str] | None:
    if factory is None:
        return None
    try:
        return factory()
    except (LLMCallError, ValueError) as exc:
        log_event(
            LOGGER,
            "pattern.refinement.unavailable",
            level=logging.ERROR,
            error_type=exc.__class__.__name__,
        )
        return None


def _event_value(event: Mapping[str, Any] | Any, key: str, default: Any = None) -> Any:
    if isinstance(event, Mapping):
        return event.get(key, default)
    return getattr(event, key, default)


def _event_outcome(event: Mapping[str, Any] | Any) -> ActionOutcome:
    raw = _event_value(event, "outcome", _event_value(event, "status", None))
    if raw is not None:
        normalized = str(raw).strip().lower()
        if normalized in {"success", "succeeded", "ok", "passed"}:
            return ActionOutcome.SUCCESS
        if normalized in {"failure", "failed", "error"}:
            return ActionOutcome.FAILURE
    if _event_value(event, "error", None):
        return ActionOutcome.FAILURE
    return ActionOutcome.UNKNOWN


def _fingerprint(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()
