from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from benchmarks.evaluation.fixed_reader import ReaderInput, ReaderOutput, run_fixed_reader
from benchmarks.evaluation.metrics import Prediction
from benchmarks.schemas.models import CanonicalEvent, QAItem


class MemorySystem(Protocol):
    def add(self, event: CanonicalEvent) -> None: ...

    def retrieve(self, qa_item: QAItem, *, token_budget: int) -> str: ...


class ReaderBackend(Protocol):
    def complete(self, prompt: str, *, temperature: float) -> str: ...


@dataclass(frozen=True)
class QARunResult:
    qa_item: QAItem
    reader_output: ReaderOutput
    prediction: Prediction


def _assert_no_future_event(events: list[CanonicalEvent], qa_item: QAItem) -> None:
    seen_ids = {event.event_id for event in events if event.event_id <= qa_item.prefix_end_event}
    future_evidence = [turn_id for turn_id in qa_item.evidence_turn_ids if turn_id not in {e.turn_id for e in events if e.event_id <= qa_item.prefix_end_event}]
    if future_evidence:
        raise ValueError(f"QA {qa_item.qa_id} requires future evidence turns: {future_evidence}")
    if qa_item.prefix_end_event not in seen_ids and events:
        max_seen = max(event.event_id for event in events)
        if qa_item.prefix_end_event > max_seen:
            raise ValueError(f"QA {qa_item.qa_id} prefix_end_event is beyond available events")


def run_online_prefix(
    *,
    events: list[CanonicalEvent],
    qa_items: list[QAItem],
    memory: MemorySystem,
    reader_backend: ReaderBackend,
    token_budget: int = 2000,
) -> list[QARunResult]:
    """Evaluate QA positions while ingesting the reference trajectory once."""
    events = sorted(events, key=lambda event: event.event_id)
    qa_by_prefix: dict[int, list[QAItem]] = {}
    for qa_item in qa_items:
        qa_by_prefix.setdefault(qa_item.prefix_end_event, []).append(qa_item)
        _assert_no_future_event(events, qa_item)

    results: list[QARunResult] = []
    for event in events:
        memory.add(event)
        for qa_item in qa_by_prefix.get(event.event_id, []):
            context = memory.retrieve(qa_item, token_budget=token_budget)
            reader_input = ReaderInput(
                qa_id=qa_item.qa_id,
                current_state=qa_item.current_context,
                proposed_action=qa_item.proposed_action,
                retrieved_context=context,
                token_budget=token_budget,
            )
            reader_output = run_fixed_reader(reader_input, reader_backend)
            prediction = Prediction(
                qa_id=qa_item.qa_id,
                gold_decision=qa_item.gold.decision,
                predicted_decision=reader_output.decision,
                gold_evidence_turn_ids=qa_item.evidence_turn_ids,
                predicted_evidence_turn_ids=[],
                gold_active_contract_ids=qa_item.gold.active_contract_ids,
                predicted_active_contract_ids=reader_output.active_contract_ids,
                gold_decisive_relation_ids=qa_item.gold.decisive_relation_ids,
                predicted_decisive_relation_ids=[],
                event_group_id=qa_item.event_group_id,
            )
            results.append(
                QARunResult(
                    qa_item=qa_item,
                    reader_output=reader_output,
                    prediction=prediction,
                )
            )

    max_event_id = events[-1].event_id if events else -1
    missing_positions = sorted(prefix for prefix in qa_by_prefix if prefix > max_event_id)
    if missing_positions:
        raise ValueError(f"QA positions beyond trajectory: {missing_positions}")
    return results
