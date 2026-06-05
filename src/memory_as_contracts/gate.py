from __future__ import annotations

import json
import re
from collections.abc import Iterable
from dataclasses import dataclass

from memory_as_contracts.ambiguity import AmbiguityMonitor
from memory_as_contracts.compiler import PolicyCompiler
from memory_as_contracts.matching import contract_applies_to_signature, edge_applies_to_signature
from memory_as_contracts.models import (
    ActionSignature,
    Contract,
    ContractKind,
    ContractStatus,
    EdgeRelation,
    GateDecision,
    GateDecisionType,
    IgnoredContract,
    MatchOutcome,
    PredicateEvaluation,
    Receipt,
    RuleEffect,
    RulePatternVersion,
)
from memory_as_contracts.store import ContractStore


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
        ambiguity_monitor: AmbiguityMonitor | None = None,
        auto_enqueue_refinement: bool = True,
    ) -> None:
        self.store = store
        self.compiler = compiler or PolicyCompiler()
        self.exclude_actions = _normalize_exclusions(exclude_actions or [])
        self.ambiguity_monitor = (
            ambiguity_monitor
            if ambiguity_monitor is not None
            else AmbiguityMonitor(store)
            if auto_enqueue_refinement
            else None
        )

    def gate(self, signature: ActionSignature) -> GateResult:
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
        ignored: list[IgnoredContract] = []
        used: list[str] = []
        edges_applied: list[str] = []
        final_decision = GateDecisionType.ALLOW
        final_reason = "no applicable contract required intervention"
        final_outcome = MatchOutcome.NOT_MATCHED

        for contract in sorted(contracts, key=_gate_contract_rank, reverse=True):
            if contract.effect == RuleEffect.PREFER or contract.kind == ContractKind.PREFERENCE:
                ignored.append(IgnoredContract(id=contract.id, reason="preference_not_gated"))
                continue
            if contract.is_expired(signature.time.now):
                ignored.append(IgnoredContract(id=contract.id, reason="expired"))
                continue
            if not contract_applies_to_signature(contract, signature):
                ignored.append(IgnoredContract(id=contract.id, reason="out_of_scope"))
                continue
            override_edge_id = self._active_override_edge_id(signature, contract)
            if override_edge_id is not None:
                ignored.append(IgnoredContract(id=contract.id, reason="override_applied"))
                edges_applied.append(override_edge_id)
                continue
            if self._has_active_exception(signature, contract):
                ignored.append(IgnoredContract(id=contract.id, reason="exception_applied"))
                continue
            pattern_version = self._active_pattern_version(contract, signature)
            if pattern_version is None:
                ignored.append(IgnoredContract(id=contract.id, reason="missing_tool_pattern"))
                continue
            outcome = self.compiler.evaluate(pattern_version, signature)
            evaluation = self.store.add_pattern_evaluation(
                PredicateEvaluation(
                    contract_id=contract.id,
                    pattern_version_id=pattern_version.id,
                    signature_id=signature.signature_id,
                    match_outcome=outcome,
                )
            )
            self._enqueue_refinement_if_needed(evaluation)
            if outcome == MatchOutcome.NOT_MATCHED:
                ignored.append(IgnoredContract(id=contract.id, reason="predicate_not_matched"))
                continue
            used.append(contract.id)
            final_outcome = outcome
            edges_applied.extend(self._active_edge_ids(signature, contract))

            if contract.status == ContractStatus.PENDING_CONFLICT:
                final_decision = GateDecisionType.BLOCK
                final_reason = _block_hint(contract)
                break
            if outcome == MatchOutcome.AMBIGUOUS:
                decision = self._decision_for_matched_contract(contract)
                if decision == GateDecisionType.BLOCK:
                    final_decision = GateDecisionType.BLOCK
                    final_reason = _block_hint(contract)
                    break
                final_reason = f"matched ambiguous non-blocking contract {contract.id}"
                continue

            decision = self._decision_for_matched_contract(contract)
            if decision != GateDecisionType.ALLOW:
                final_decision = decision
                final_reason = _block_hint(contract)
                break
            final_reason = f"matched non-blocking contract {contract.id}"

        return self._finish(
            signature,
            decision=final_decision,
            reason=final_reason,
            match_outcome=final_outcome,
            result=final_decision.value,
            contracts_used=used,
            edges_applied=sorted(set(edges_applied)),
            contracts_ignored=ignored,
        )

    def _active_pattern_version(
        self, contract: Contract, signature: ActionSignature
    ) -> RulePatternVersion | None:
        current = self.store.get_active_rule_pattern_version(contract.id)
        if current is not None:
            return current if current.tool_patterns else None
        if not contract.tool_patterns:
            return None
        pattern_version = self.compiler.compile(contract, signature.available_actions)
        if not pattern_version.has_binding_predicates():
            return None
        return self.store.add_rule_pattern_version(
            pattern_version.model_copy(update={"contract_id": contract.id})
        )

    def _decision_for_matched_contract(self, contract: Contract) -> GateDecisionType:
        if contract.effect == RuleEffect.DENY or contract.kind == ContractKind.PROHIBITION:
            return GateDecisionType.BLOCK
        return GateDecisionType.ALLOW

    def _enqueue_refinement_if_needed(self, evaluation: PredicateEvaluation) -> None:
        if self.ambiguity_monitor is None:
            return
        self.ambiguity_monitor.enqueue_if_needed(
            evaluation.contract_id,
            evaluation.pattern_version_id,
        )

    def _active_override_edge_id(self, signature: ActionSignature, contract: Contract) -> str | None:
        edges = self.store.list_edges([ContractStatus.ACTIVE])
        for edge in edges:
            if edge.relation != EdgeRelation.OVERRIDE:
                continue
            if edge.to_contract != contract.id:
                continue
            if edge_applies_to_signature(edge, signature):
                return edge.id
        return None

    def _active_edge_ids(self, signature: ActionSignature, contract: Contract) -> list[str]:
        edges = self.store.list_edges([ContractStatus.ACTIVE])
        return [
            edge.id
            for edge in edges
            if edge_applies_to_signature(edge, signature)
            and (edge.from_contract == contract.id or edge.to_contract == contract.id)
        ]

    def _has_active_exception(self, signature: ActionSignature, contract: Contract) -> bool:
        edges = self.store.list_edges([ContractStatus.ACTIVE])
        for edge in edges:
            if edge.relation != EdgeRelation.EXCEPTION_TO:
                continue
            if not edge_applies_to_signature(edge, signature):
                continue
            exception_contract = self.store.get_contract(edge.from_contract)
            if exception_contract is None:
                continue
            if not contract_applies_to_signature(exception_contract, signature):
                continue
            exception_pattern_version = self._active_pattern_version(exception_contract, signature)
            if exception_pattern_version is None:
                continue
            if self.compiler.evaluate(exception_pattern_version, signature) != MatchOutcome.MATCHED:
                continue
            if _exception_can_cover_contract(exception_contract, contract):
                return True
        return False

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
    ) -> GateResult:
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
            result=result,
        )
        self.store.add_receipt(receipt)
        return GateResult(decision=gate_decision, receipt=receipt)


def _exception_can_cover_contract(exception_contract: Contract, contract: Contract) -> bool:
    if exception_contract.effect != RuleEffect.ALLOW and exception_contract.kind != ContractKind.EXCEPTION:
        return False
    if contract.effect != RuleEffect.DENY and contract.kind != ContractKind.PROHIBITION:
        return False
    if (
        exception_contract.scope.workspace
        and contract.scope.workspace
        and exception_contract.scope.workspace != contract.scope.workspace
    ):
        return False
    if (
        exception_contract.scope.repo
        and contract.scope.repo
        and exception_contract.scope.repo != contract.scope.repo
    ):
        return False
    exception_actions = set(exception_contract.semantics.actions)
    contract_actions = set(contract.semantics.actions)
    if exception_actions and contract_actions and not exception_actions.intersection(contract_actions):
        return False
    exception_tags = set(exception_contract.semantics.tags)
    contract_tags = set(contract.semantics.tags)
    if exception_tags and contract_tags and not exception_tags.intersection(contract_tags):
        return False
    exception_globs = exception_contract.scope.path_globs
    contract_globs = contract.scope.path_globs
    if exception_globs and contract_globs:
        if not any(
            _glob_is_narrower(exception_glob, contract_glob)
            for exception_glob in exception_globs
            for contract_glob in contract_globs
        ):
            return False
    return True


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
    if contract.tool_patterns:
        score += len(contract.tool_patterns) * 4
    if contract.targets:
        score += len(contract.targets) * 3
    return score


def _scope_specificity_value(contract: Contract) -> int:
    return {
        "global": 0,
        "organization": 1,
        "agent_family": 2,
        "project": 3,
        "repo": 4,
        "session": 5,
        "task": 6,
        "component": 7,
        "path": 8,
        "per_turn": 9,
    }.get(contract.scope.level.value, 0)


def _glob_is_narrower(candidate: str, broader: str) -> bool:
    if candidate == broader:
        return False
    candidate_prefix = candidate.split("*", 1)[0].rstrip("/")
    broader_prefix = broader.split("*", 1)[0].rstrip("/")
    return bool(candidate_prefix and broader_prefix and candidate_prefix.startswith(broader_prefix))


def _block_hint(contract: Contract) -> str:
    return (
        f"Action violates rule {contract.id}: {contract.text}. "
        "Consider another way or ask user for clarification."
    )


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
