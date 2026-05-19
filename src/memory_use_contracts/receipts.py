from __future__ import annotations

from memory_use_contracts.models import ActionSignature, GateDecision, InfluenceReceipt


def build_receipt(
    action: ActionSignature,
    decision: GateDecision,
    result: str = "pending",
) -> InfluenceReceipt:
    return InfluenceReceipt(
        action_class=action.action_class,
        target=action.target,
        decision=decision.decision,
        contracts_used=decision.applicable_contracts,
        result=result,
    )
