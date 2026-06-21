from __future__ import annotations

from benchmarks.qa.blinded_checks import QAValidityReport
from benchmarks.schemas.models import CanonicalEvent, QAItem


def build_human_review_record(
    *,
    qa_item: QAItem,
    history_prefix: list[CanonicalEvent],
    rendered_question: str,
    validity_report: QAValidityReport,
) -> dict[str, object]:
    return {
        "qa_id": qa_item.qa_id,
        "source": qa_item.source,
        "trajectory_id": qa_item.trajectory_id,
        "prefix_end_event": qa_item.prefix_end_event,
        "history_prefix": [event.model_dump(exclude_none=True) for event in history_prefix],
        "question": rendered_question,
        "proposed_action": qa_item.proposed_action.model_dump(exclude_none=True),
        "gold_decision": qa_item.gold.decision,
        "evidence_turn_ids": qa_item.evidence_turn_ids,
        "validator": {
            "accepted": validity_report.accepted,
            "reject_reasons": validity_report.reject_reasons,
        },
    }
