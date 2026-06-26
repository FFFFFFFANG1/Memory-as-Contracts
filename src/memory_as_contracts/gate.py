from __future__ import annotations

import json
import logging
import re
from collections.abc import Iterable
from dataclasses import dataclass

from memory_as_contracts.compiler import PolicyCompiler
from memory_as_contracts.logging_config import log_event
from memory_as_contracts.models import (
    ActionSignature,
    AskRequest,
    Contract,
    ContractStatus,
    GateDecision,
    GateDecisionType,
    IgnoredContract,
    MatchOutcome,
    Receipt,
)
from memory_as_contracts.rule_evaluation import RuleEvaluator
from memory_as_contracts.store import ContractStore


LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class GateResult:
    decision: GateDecision
    receipt: Receipt


@dataclass(frozen=True)
class ExcludedActionPattern:
    tool_name: str | None = None
    host_action: str | None = None
    parameter_regex: dict[str, str] | None = None


class ActionGate:
    """Deterministic action-time contract gate."""

    def __init__(
        self,
        store: ContractStore,
        *,
        compiler: PolicyCompiler | None = None,
        exclude_actions: Iterable[str | ExcludedActionPattern | dict] | None = None,
    ) -> None:
        self.store = store
        self.compiler = compiler or PolicyCompiler()
        self.exclude_actions = _normalize_exclusions(exclude_actions or [])

    def gate(
        self,
        signature: ActionSignature,
        *,
        tool_family: Iterable[str] | None = None,
    ) -> GateResult:
        if _is_excluded(signature, self.exclude_actions):
            return self._finish(
                signature,
                decision=GateDecisionType.ALLOW,
                reason="excluded action",
                match_outcome=MatchOutcome.NOT_MATCHED,
                result="excluded_action",
            )

        contracts = self.store.list_contracts(
            [ContractStatus.ACTIVE, ContractStatus.PENDING_CONFLICT],
            include_expired_status=True,
        )
        ask_response = self.store.matching_ask_response(
            session_id=signature.session.session_id,
            task_id=signature.session.task_id,
            adapter_id=signature.host,
            tool_names=tool_family or (signature.tool.name,),
            turn_id=signature.session.turn_id,
            now=signature.time.now,
        )
        ask_response_used = False
        ignored: list[IgnoredContract] = []
        used: list[str] = []
        edges_applied: list[str] = []
        validator_verdicts: list[dict] = []
        ask_rule_ids: list[str] = []
        final_decision = GateDecisionType.ALLOW
        final_reason = "no applicable contract required intervention"
        final_outcome = MatchOutcome.NOT_MATCHED
        evaluator = RuleEvaluator(
            self.store,
            compiler=self.compiler,
        )

        for contract in sorted(contracts, key=_gate_contract_rank, reverse=True):
            evaluation = evaluator.evaluate(
                contract,
                signature,
                ask_response=ask_response,
            )
            if evaluation.ignored_reason is not None:
                ignored.append(
                    IgnoredContract(
                        id=evaluation.contract_id,
                        reason=evaluation.ignored_reason,
                    )
                )
            if evaluation.used:
                used.append(evaluation.contract_id)
                final_outcome = evaluation.match_outcome
            edges_applied.extend(evaluation.edges_applied)
            validator_verdicts.extend(evaluation.validator_verdicts)
            ask_rule_ids.extend(evaluation.ask_rule_ids)
            ask_response_used = (
                ask_response_used or evaluation.ask_response_used
            )
            if evaluation.decision is not None:
                final_decision, final_reason = _merge_decision(
                    final_decision,
                    final_reason,
                    evaluation.decision,
                    evaluation.reason,
                )

        if ask_response is not None and ask_response_used:
            self.store.consume_ask_response(ask_response.id)
        return self._finish(
            signature,
            decision=final_decision,
            reason=final_reason,
            match_outcome=final_outcome,
            result=final_decision.value,
            contracts_used=used,
            edges_applied=sorted(set(edges_applied)),
            contracts_ignored=ignored,
            validator_verdicts=validator_verdicts,
            ask_rule_ids=ask_rule_ids,
        )

    def _finish(
        self,
        signature: ActionSignature,
        *,
        decision: GateDecisionType,
        reason: str,
        match_outcome: MatchOutcome,
        result: str,
        contracts_used: list[str] | None = None,
        edges_applied: list[str] | None = None,
        contracts_ignored: list[IgnoredContract] | None = None,
        validator_verdicts: list[dict] | None = None,
        ask_rule_ids: list[str] | None = None,
    ) -> GateResult:
        ask_request = None
        if decision == GateDecisionType.ASK:
            ask_request = self.store.add_ask_request(
                AskRequest(
                    session_id=signature.session.session_id,
                    task_id=signature.session.task_id,
                    adapter_id=signature.host,
                    tool_name=signature.tool.name,
                    rule_ids=sorted(set(ask_rule_ids or [])),
                    created_at=signature.time.now,
                )
            )
        gate_decision = GateDecision(
            decision=decision,
            reason=reason,
            contracts_used=contracts_used or [],
            edges_applied=edges_applied or [],
            match_outcome=match_outcome,
        )
        receipt = Receipt(
            signature_id=signature.signature_id,
            session_id=signature.session.session_id,
            decision=decision,
            host_action=signature.host_action,
            tool_name=signature.tool.name,
            raw_arguments=signature.tool.raw_arguments,
            available_actions=signature.available_actions,
            canonical_tags=signature.canonical_tags,
            match_outcome=match_outcome,
            targets=signature.targets,
            intent=signature.intent,
            contracts_used=contracts_used or [],
            edges_applied=edges_applied or [],
            contracts_ignored=contracts_ignored or [],
            validator_verdicts=validator_verdicts or [],
            ask_request_id=ask_request.id if ask_request is not None else None,
            result=result,
        )
        self.store.add_receipt(receipt)
        log_event(
            LOGGER,
            "gate.decision",
            session_id=signature.session.session_id,
            task_id=signature.session.task_id,
            adapter=signature.host,
            tool_name=signature.tool.name,
            decision=decision.value,
            receipt_id=receipt.id,
            contract_count=len(receipt.contracts_used),
            ask_request_id=receipt.ask_request_id,
        )
        return GateResult(decision=gate_decision, receipt=receipt)


def _merge_decision(
    current: GateDecisionType,
    current_reason: str,
    candidate: GateDecisionType,
    candidate_reason: str,
) -> tuple[GateDecisionType, str]:
    rank = {
        GateDecisionType.ALLOW: 0,
        GateDecisionType.ASK: 1,
        GateDecisionType.REJECT: 2,
    }
    if rank[candidate] > rank[current]:
        return candidate, candidate_reason
    return current, current_reason


def _gate_contract_rank(contract: Contract) -> tuple[int, int, int]:
    return (
        _binding_specificity(contract),
        _scope_specificity_value(contract),
        len(contract.text),
    )


def _binding_specificity(contract: Contract) -> int:
    score = 0
    actions = set(contract.semantics.actions)
    tags = set(contract.semantics.tags)
    if actions:
        score += 10
    if tags:
        score += 3
    if actions.difference({"exec"}):
        score += 10
    if contract.check_patterns:
        score += len(contract.check_patterns) * 4
    return score


def _scope_specificity_value(contract: Contract) -> int:
    return {
        "global": 0,
        "project": 3,
        "session": 5,
        "module": 7,
    }.get(contract.scope.level.value, 0)


def _normalize_exclusions(
    items: Iterable[str | ExcludedActionPattern | dict],
) -> list[ExcludedActionPattern]:
    exclusions: list[ExcludedActionPattern] = []
    for item in items:
        exclusions.extend(_normalize_exclusion(item))
    return exclusions


def _normalize_exclusion(item: str | ExcludedActionPattern | dict) -> list[ExcludedActionPattern]:
    if isinstance(item, str):
        return [ExcludedActionPattern(tool_name=item), ExcludedActionPattern(host_action=item)]
    if isinstance(item, ExcludedActionPattern):
        return [item]
    return [
        ExcludedActionPattern(
            tool_name=item.get("tool_name"),
            host_action=item.get("host_action"),
            parameter_regex=item.get("parameter_regex") or None,
        )
    ]


def _is_excluded(
    signature: ActionSignature,
    exclusions: list[ExcludedActionPattern],
) -> bool:
    return any(_matches_exclusion(signature, exclusion) for exclusion in exclusions)


def _matches_exclusion(signature: ActionSignature, exclusion: ExcludedActionPattern) -> bool:
    if exclusion.tool_name is not None and signature.tool.name != exclusion.tool_name:
        return False
    if exclusion.host_action is not None and signature.host_action != exclusion.host_action:
        return False
    for key, pattern in (exclusion.parameter_regex or {}).items():
        if key not in signature.tool.raw_arguments:
            return False
        if re.search(pattern, _argument_text(signature.tool.raw_arguments[key])) is None:
            return False
    return exclusion.tool_name is not None or exclusion.host_action is not None


def _argument_text(value) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value, sort_keys=True)
