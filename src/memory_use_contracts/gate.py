from __future__ import annotations

from memory_use_contracts.models import (
    ActionSignature,
    Contract,
    ContractType,
    GateDecision,
    GateDecisionType,
    Modality,
    Strength,
)


class ContractGate:
    def decide(self, action: ActionSignature, contracts: list[Contract]) -> GateDecision:
        pending = [contract for contract in contracts if contract.status.value == "pending_conflict"]
        if pending:
            return GateDecision(
                decision=GateDecisionType.DEFER,
                reason="Unresolved contract conflict applies to this action",
                applicable_contracts=[contract.id for contract in pending],
                allowed_override="resolve_conflict",
            )

        hard_blocks = [
            contract
            for contract in contracts
            if contract.type == ContractType.PROHIBITION
            and contract.modality == Modality.MUST_NOT
            and contract.strength == Strength.HARD
            and contract.confirmation != "required"
        ]
        if hard_blocks:
            return GateDecision(
                decision=GateDecisionType.BLOCK,
                reason=f"Matches hard prohibition {hard_blocks[0].id}",
                applicable_contracts=[contract.id for contract in hard_blocks],
                allowed_override="explicit_user_confirmation",
            )

        confirmations = [
            contract for contract in contracts if contract.confirmation != "not_required"
        ]
        if confirmations and action.risk in {"medium", "high"}:
            return GateDecision(
                decision=GateDecisionType.CONFIRM,
                reason="Applicable contract requires confirmation",
                applicable_contracts=[contract.id for contract in confirmations],
                allowed_override="explicit_user_confirmation",
            )

        requirements = [contract for contract in contracts if contract.type == ContractType.REQUIREMENT]
        unsatisfied = [
            contract
            for contract in requirements
            if not _action_text_satisfies_contract(action, contract)
        ]
        if unsatisfied:
            return GateDecision(
                decision=GateDecisionType.REVISE,
                reason="Applicable requirement should be reflected in the action plan",
                applicable_contracts=[contract.id for contract in unsatisfied],
            )

        return GateDecision(decision=GateDecisionType.ALLOW, reason="No applicable contract changes action")


def _action_text_satisfies_contract(action: ActionSignature, contract: Contract) -> bool:
    haystack = " ".join(part for part in [action.target or "", action.intent] if part).lower()
    contract_text = contract.text.lower()
    command_markers = [
        "uv run pytest",
        "uv",
        "pnpm",
        "npm",
        "pip",
        "git",
    ]
    for marker in command_markers:
        if f"not {marker}" in contract_text and marker in haystack:
            return False
    matched_markers = [
        marker
        for marker in command_markers
        if marker in contract_text and f"not {marker}" not in contract_text
    ]
    if not matched_markers:
        return False
    return any(marker in haystack for marker in matched_markers)
