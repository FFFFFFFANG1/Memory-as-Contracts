from __future__ import annotations

from benchmarks.contracts.resolver import resolve
from benchmarks.schemas.models import CanonicalAction, ContractGraph, QAItem


def build_qa_item(
    *,
    qa_id: str,
    track: str,
    source: str,
    trajectory_id: str,
    prefix_end_event: int,
    history_prefix_ref: str,
    current_context: dict[str, object],
    current_scope: dict[str, object],
    proposed_action: CanonicalAction,
    graph: ContractGraph,
    evidence_turn_ids: list[str],
    probe_metadata: dict[str, object],
    event_group_id: str | None = None,
) -> QAItem:
    decision = resolve(
        graph,
        prefix_end_event=prefix_end_event,
        current_scope=current_scope,
        proposed_action=proposed_action,
    )
    payload = {
        "qa_id": qa_id,
        "track": track,
        "source": source,
        "trajectory_id": trajectory_id,
        "prefix_end_event": prefix_end_event,
        "history_prefix_ref": history_prefix_ref,
        "current_context": current_context,
        "proposed_action": proposed_action.model_dump(),
        "gold": {
            "decision": decision.decision,
            "active_contract_ids": decision.active_contract_ids,
            "decisive_relation_ids": decision.decisive_relation_ids,
        },
        "evidence_turn_ids": evidence_turn_ids,
        "probe_metadata": probe_metadata,
        "event_group_id": event_group_id,
    }
    return QAItem.model_validate(payload)
