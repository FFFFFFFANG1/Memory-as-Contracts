from __future__ import annotations

from dataclasses import dataclass, field

from benchmarks.schemas.models import CanonicalEvent, QAItem


@dataclass(frozen=True)
class QAValidityReport:
    action_observable: bool
    evidence_recoverable: bool
    decision_unique: bool
    query_leaks_rule: bool
    assistant_echo_leakage: bool
    solvable_without_history: bool
    base_task_plausible: bool
    reject_reasons: list[str] = field(default_factory=list)

    @property
    def accepted(self) -> bool:
        return (
            self.action_observable
            and self.evidence_recoverable
            and self.decision_unique
            and not self.query_leaks_rule
            and not self.assistant_echo_leakage
            and not self.solvable_without_history
            and self.base_task_plausible
            and not self.reject_reasons
        )


def run_static_qa_checks(
    *,
    qa_item: QAItem,
    history_prefix: list[CanonicalEvent],
    rendered_question: str,
    oracle_decision_unique: bool = True,
    query_only_answered: bool = False,
) -> QAValidityReport:
    reasons: list[str] = []
    prefix_turns = {event.turn_id for event in history_prefix}
    evidence_recoverable = all(turn_id in prefix_turns for turn_id in qa_item.evidence_turn_ids)
    if not evidence_recoverable:
        reasons.append("gold evidence is not present in history prefix")

    action_observable = bool(qa_item.proposed_action.family and qa_item.proposed_action.effect_summary)
    if not action_observable:
        reasons.append("proposed action is not observable")

    lowered = rendered_question.lower()
    leak_tokens = ("contract id", "hidden graph", "active_contract_ids", "decisive_relation")
    query_leaks_rule = any(token in lowered for token in leak_tokens)
    if query_leaks_rule:
        reasons.append("query leaks hidden rule metadata")

    assistant_echo_leakage = any(
        event.role == "assistant" and any(turn_id in event.content for turn_id in qa_item.evidence_turn_ids)
        for event in history_prefix
    )
    if assistant_echo_leakage:
        reasons.append("assistant echo appears to expose evidence ids")

    if not oracle_decision_unique:
        reasons.append("oracle decision is not unique")

    if query_only_answered:
        reasons.append("query-only check makes item trivial")

    return QAValidityReport(
        action_observable=action_observable,
        evidence_recoverable=evidence_recoverable,
        decision_unique=oracle_decision_unique,
        query_leaks_rule=query_leaks_rule,
        assistant_echo_leakage=assistant_echo_leakage,
        solvable_without_history=query_only_answered,
        base_task_plausible=True,
        reject_reasons=reasons,
    )
