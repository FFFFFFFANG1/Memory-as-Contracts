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
)
from memory_as_contracts.policy_ir import PolicyIREvaluator, policy_target_matches
from memory_as_contracts.store import ContractStore


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
    ) -> None:
        del compiler
        self.store = store
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

        if contract.policy_ir is not None:
            policy_result = PolicyIREvaluator(self.store).evaluate(contract, signature)
            if not policy_result.matched:
                return self._ignored(contract, "policy_ir_not_matched")
            verdict = {
                "contract_id": contract.id,
                "policy_ir": True,
                "decision": (
                    policy_result.decision.value
                    if policy_result.decision is not None
                    else GateDecisionType.ALLOW.value
                ),
                "reason": policy_result.reason or "policy ir satisfied",
                "evidence": policy_result.evidence or {},
                "confidence": float((policy_result.evidence or {}).get("confidence", 1.0)),
            }
            return RuleEvaluation(
                contract_id=contract.id,
                decision=policy_result.decision,
                reason=policy_result.reason,
                match_outcome=MatchOutcome.MATCHED,
                used=True,
                validator_verdicts=(verdict,),
            )

        return RuleEvaluation(
            contract_id=contract.id,
            decision=GateDecisionType.ASK,
            reason=f"Rule {contract.id} has no PolicyIR; re-extract or migrate it before execution.",
            match_outcome=MatchOutcome.MATCHED,
            used=True,
            validator_verdicts=({
                "contract_id": contract.id,
                "decision": GateDecisionType.ASK.value,
                "reason": "policy_ir_migration_required",
            },),
            ask_rule_ids=(contract.id,),
        )

    @staticmethod
    def _ignored(contract: Contract, reason: str) -> RuleEvaluation:
        return RuleEvaluation(contract_id=contract.id, ignored_reason=reason)


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
            if exception_contract.policy_ir is not None:
                if not policy_target_matches(exception_contract, signature):
                    continue
            else:
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
