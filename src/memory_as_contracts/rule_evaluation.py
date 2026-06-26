from __future__ import annotations

from dataclasses import dataclass

from memory_as_contracts.matching import (
    contract_applies_to_signature,
    edge_applies_to_signature,
)
from memory_as_contracts.models import (
    ActionSignature,
    AskRequest,
    Contract,
    ContractKind,
    ContractStatus,
    EdgeRelation,
    GateDecisionType,
    MatchOutcome,
    RuleEffect,
    ValidatorEnforcementShape,
)
from memory_as_contracts.rule_surface import (
    bind_contract_check_patterns,
    bind_check_patterns,
    bind_validator_check,
)
from memory_as_contracts.store import ContractStore
from memory_as_contracts.validators import ValidatorRuntime, ValidatorSandboxError


@dataclass(frozen=True)
class RuleEvaluation:
    contract_id: str
    decision: GateDecisionType | None = None
    reason: str = ""
    match_outcome: MatchOutcome = MatchOutcome.NOT_MATCHED
    used: bool = False
    ignored_reason: str | None = None
    edges_applied: tuple[str, ...] = ()
    validator_verdicts: tuple[dict, ...] = ()
    ask_response_used: bool = False
    ask_rule_ids: tuple[str, ...] = ()


class RuleEvaluator:
    """Evaluate one applicable Rule without aggregating or writing receipts."""

    def __init__(
        self,
        store: ContractStore,
        *,
        compiler: object | None = None,
        validator_runtime: ValidatorRuntime | None = None,
    ) -> None:
        del compiler
        self.store = store
        self.validator_runtime = validator_runtime or ValidatorRuntime(store)
        self.active_edges = store.list_edges([ContractStatus.ACTIVE])
        self._contract_cache: dict[str, Contract | None] = {}

    def evaluate(
        self,
        contract: Contract,
        signature: ActionSignature,
        *,
        ask_response: AskRequest | None,
    ) -> RuleEvaluation:
        if contract.effect == RuleEffect.PREFER or contract.kind == ContractKind.PREFERENCE:
            return self._ignored(contract, "preference_not_gated")
        if contract.is_expired(signature.time.now):
            return self._ignored(contract, "expired")
        if not contract_applies_to_signature(contract, signature):
            return self._ignored(contract, "out_of_scope")
        override_edge_id = self._active_override_edge_id(signature, contract)
        if override_edge_id is not None:
            return RuleEvaluation(
                contract_id=contract.id,
                ignored_reason="override_applied",
                edges_applied=(override_edge_id,),
            )
        if self._has_active_exception(signature, contract):
            return self._ignored(contract, "exception_applied")

        validator_version = self.store.get_active_validator_version(contract.id)
        if validator_version is not None:
            if not validator_version.check_patterns:
                return self._ignored(contract, "missing_validator_check_pattern")
            binding = bind_validator_check(contract, validator_version, signature)
            if not binding.matched:
                return self._ignored(contract, "validator_not_matched")
            response = self._ask_response_evaluation(
                contract,
                validator_version.id,
                binding.outcome,
                ask_response,
            )
            if response is not None:
                return response
            try:
                verdict = self.validator_runtime.check(
                    validator_version,
                    signature,
                    ask_response_flag=False,
                    ask_request_id=None,
                )
            except (ValidatorSandboxError, ValueError) as exc:
                return RuleEvaluation(
                    contract_id=contract.id,
                    decision=GateDecisionType.ASK,
                    reason=f"Validator for rule {contract.id} could not be evaluated.",
                    match_outcome=binding.outcome,
                    used=True,
                    validator_verdicts=(
                        {
                            "contract_id": contract.id,
                            "validator_version_id": validator_version.id,
                            "decision": GateDecisionType.ASK.value,
                            "reason": f"validator unavailable: {exc}",
                            "evidence_refs": [],
                            "confidence": 0.0,
                            "runtime_error": exc.__class__.__name__,
                        },
                    ),
                    ask_rule_ids=(contract.id,),
                )
            return RuleEvaluation(
                contract_id=contract.id,
                decision=verdict.decision,
                reason=verdict.reason,
                match_outcome=binding.outcome,
                used=True,
                validator_verdicts=(
                    {
                        "contract_id": contract.id,
                        "validator_version_id": validator_version.id,
                        "decision": verdict.decision.value,
                        "reason": verdict.reason,
                        "evidence_refs": verdict.evidence_refs,
                        "confidence": verdict.confidence,
                    },
                ),
                ask_rule_ids=(
                    (contract.id,)
                    if verdict.decision == GateDecisionType.ASK
                    else ()
                ),
            )

        if contract.validator_enforcement_shape != ValidatorEnforcementShape.NO_VALIDATOR:
            if not contract.check_patterns:
                return self._ignored(contract, "validator_unavailable")
            binding = bind_contract_check_patterns(contract, signature)
            if not binding.matched:
                return self._ignored(contract, "validator_not_matched")
            response = self._ask_response_evaluation(
                contract,
                None,
                binding.outcome,
                ask_response,
            )
            if response is not None:
                return response
            return RuleEvaluation(
                contract_id=contract.id,
                decision=GateDecisionType.ASK,
                reason=f"Rule {contract.id} requires a validator that is not available.",
                match_outcome=binding.outcome,
                used=True,
                validator_verdicts=(
                    {
                        "contract_id": contract.id,
                        "validator_version_id": None,
                        "decision": GateDecisionType.ASK.value,
                        "reason": "validator is not installed",
                        "evidence_refs": [],
                        "confidence": 0.0,
                    },
                ),
                ask_rule_ids=(contract.id,),
            )

        pattern_version = self._active_pattern_version(contract)
        if pattern_version is None:
            return self._ignored(contract, "missing_check_pattern")
        binding = bind_check_patterns(contract, signature, pattern_version.check_patterns)
        if not binding.matched:
            return self._ignored(contract, "predicate_not_matched")
        response = self._ask_response_evaluation(
            contract,
            None,
            binding.outcome,
            ask_response,
        )
        if response is not None:
            return response
        edges_applied = tuple(self._active_edge_ids(signature, contract))
        if contract.status == ContractStatus.PENDING_CONFLICT:
            return RuleEvaluation(
                contract_id=contract.id,
                decision=GateDecisionType.ASK,
                reason=_intervention_hint(contract),
                match_outcome=binding.outcome,
                used=True,
                edges_applied=edges_applied,
                ask_rule_ids=(contract.id,),
            )
        decision = (
            GateDecisionType.REJECT
            if contract.effect == RuleEffect.DENY
            or contract.kind == ContractKind.PROHIBITION
            else GateDecisionType.ALLOW
        )
        return RuleEvaluation(
            contract_id=contract.id,
            decision=decision,
            reason=(
                _intervention_hint(contract)
                if decision != GateDecisionType.ALLOW
                else f"matched non-blocking contract {contract.id}"
            ),
            match_outcome=binding.outcome,
            used=True,
            edges_applied=edges_applied,
        )

    @staticmethod
    def _ignored(contract: Contract, reason: str) -> RuleEvaluation:
        return RuleEvaluation(contract_id=contract.id, ignored_reason=reason)

    @staticmethod
    def _ask_response_evaluation(
        contract: Contract,
        validator_version_id: str | None,
        outcome: MatchOutcome,
        ask_response: AskRequest | None,
    ) -> RuleEvaluation | None:
        if ask_response is None or contract.id not in ask_response.rule_ids:
            return None
        return RuleEvaluation(
            contract_id=contract.id,
            decision=GateDecisionType.ALLOW,
            reason="single-use Ask Response Flag applied",
            match_outcome=outcome,
            used=True,
            validator_verdicts=(
                {
                    "contract_id": contract.id,
                    "validator_version_id": validator_version_id,
                    "decision": GateDecisionType.ALLOW.value,
                    "reason": "single-use Ask Response Flag applied",
                    "evidence_refs": [{"ask_request_id": ask_response.id}],
                    "confidence": 1.0,
                },
            ),
            ask_response_used=True,
        )

    def _active_pattern_version(
        self,
        contract: Contract,
    ) -> RulePatternVersion | None:
        current = self.store.get_active_rule_pattern_version(contract.id)
        return current if current is not None and current.check_patterns else None

    def _active_override_edge_id(
        self,
        signature: ActionSignature,
        contract: Contract,
    ) -> str | None:
        for edge in self.active_edges:
            if edge.relation != EdgeRelation.OVERRIDE:
                continue
            if edge.to_contract != contract.id:
                continue
            if edge_applies_to_signature(edge, signature):
                return edge.id
        return None

    def _active_edge_ids(
        self,
        signature: ActionSignature,
        contract: Contract,
    ) -> list[str]:
        return [
            edge.id
            for edge in self.active_edges
            if edge_applies_to_signature(edge, signature)
            and (
                edge.from_contract == contract.id
                or edge.to_contract == contract.id
            )
        ]

    def _has_active_exception(
        self,
        signature: ActionSignature,
        contract: Contract,
    ) -> bool:
        for edge in self.active_edges:
            if edge.relation != EdgeRelation.EXCEPTION_TO:
                continue
            if not edge_applies_to_signature(edge, signature):
                continue
            exception_contract = self._contract(edge.from_contract)
            if exception_contract is None:
                continue
            if not contract_applies_to_signature(exception_contract, signature):
                continue
            exception_pattern_version = self._active_pattern_version(
                exception_contract
            )
            if exception_pattern_version is None:
                continue
            if not bind_check_patterns(
                exception_contract,
                signature,
                exception_pattern_version.check_patterns,
            ).matched:
                continue
            if _exception_can_cover_contract(exception_contract, contract):
                return True
        return False

    def _contract(self, contract_id: str) -> Contract | None:
        if contract_id not in self._contract_cache:
            self._contract_cache[contract_id] = self.store.get_contract(contract_id)
        return self._contract_cache[contract_id]


def _exception_can_cover_contract(
    exception_contract: Contract,
    contract: Contract,
) -> bool:
    if (
        exception_contract.effect != RuleEffect.ALLOW
        and exception_contract.kind != ContractKind.EXCEPTION
    ):
        return False
    if (
        contract.effect != RuleEffect.DENY
        and contract.kind != ContractKind.PROHIBITION
    ):
        return False
    if (
        exception_contract.scope.workspace
        and contract.scope.workspace
        and exception_contract.scope.workspace != contract.scope.workspace
    ):
        return False
    if (
        exception_contract.scope.project
        and contract.scope.project
        and exception_contract.scope.project != contract.scope.project
    ):
        return False
    exception_actions = set(exception_contract.semantics.actions)
    contract_actions = set(contract.semantics.actions)
    if (
        exception_actions
        and contract_actions
        and not exception_actions.intersection(contract_actions)
    ):
        return False
    exception_tags = set(exception_contract.semantics.tags)
    contract_tags = set(contract.semantics.tags)
    if (
        exception_tags
        and contract_tags
        and not exception_tags.intersection(contract_tags)
    ):
        return False
    if (
        exception_contract.scope.module
        and contract.scope.module
        and exception_contract.scope.module != contract.scope.module
    ):
        return False
    return True


def _glob_is_narrower(candidate: str, broader: str) -> bool:
    if candidate == broader:
        return False
    candidate_prefix = candidate.split("*", 1)[0].rstrip("/")
    broader_prefix = broader.split("*", 1)[0].rstrip("/")
    return bool(
        candidate_prefix
        and broader_prefix
        and candidate_prefix.startswith(broader_prefix)
    )


def _intervention_hint(contract: Contract) -> str:
    return (
        f"Action violates rule {contract.id}: {contract.text}. "
        "Consider another way or ask user for clarification."
    )
