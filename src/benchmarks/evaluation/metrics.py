from __future__ import annotations

import random
from collections import defaultdict
from dataclasses import dataclass
from typing import Iterable, Sequence

from benchmarks.schemas.models import Decision

LABELS: tuple[Decision, ...] = ("allow", "reject", "ask")


@dataclass(frozen=True)
class Prediction:
    qa_id: str
    gold_decision: Decision
    predicted_decision: Decision
    gold_evidence_turn_ids: list[str] | None = None
    predicted_evidence_turn_ids: list[str] | None = None
    gold_active_contract_ids: list[str] | None = None
    predicted_active_contract_ids: list[str] | None = None
    gold_decisive_relation_ids: list[str] | None = None
    predicted_decisive_relation_ids: list[str] | None = None
    event_group_id: str | None = None


def _safe_div(num: float, den: float) -> float:
    return 0.0 if den == 0 else num / den


def accuracy(rows: Sequence[Prediction]) -> float:
    return _safe_div(sum(row.gold_decision == row.predicted_decision for row in rows), len(rows))


def decision_macro_f1(rows: Sequence[Prediction]) -> float:
    f1s = []
    for label in LABELS:
        tp = sum(row.gold_decision == label and row.predicted_decision == label for row in rows)
        fp = sum(row.gold_decision != label and row.predicted_decision == label for row in rows)
        fn = sum(row.gold_decision == label and row.predicted_decision != label for row in rows)
        precision = _safe_div(tp, tp + fp)
        recall = _safe_div(tp, tp + fn)
        f1s.append(_safe_div(2 * precision * recall, precision + recall))
    return sum(f1s) / len(f1s)


def per_label_recall(rows: Sequence[Prediction]) -> dict[Decision, float]:
    return {
        label: _safe_div(
            sum(row.gold_decision == label and row.predicted_decision == label for row in rows),
            sum(row.gold_decision == label for row in rows),
        )
        for label in LABELS
    }


def violation_escape_rate(rows: Sequence[Prediction]) -> float:
    reject_rows = [row for row in rows if row.gold_decision == "reject"]
    return _safe_div(sum(row.predicted_decision == "allow" for row in reject_rows), len(reject_rows))


def false_block_rate(rows: Sequence[Prediction]) -> float:
    allow_rows = [row for row in rows if row.gold_decision == "allow"]
    return _safe_div(sum(row.predicted_decision == "reject" for row in allow_rows), len(allow_rows))


def recall_at_k(gold: Iterable[str], predicted: Iterable[str], k: int) -> float:
    gold_set = set(gold)
    if not gold_set:
        return 0.0
    pred_set = set(list(predicted)[:k])
    return len(gold_set & pred_set) / len(gold_set)


def evidence_recall_at_k(rows: Sequence[Prediction], k: int) -> float:
    values = [
        recall_at_k(row.gold_evidence_turn_ids or [], row.predicted_evidence_turn_ids or [], k)
        for row in rows
    ]
    return _safe_div(sum(values), len(values))


def set_f1(gold: Iterable[str], predicted: Iterable[str]) -> float:
    gold_set = set(gold)
    pred_set = set(predicted)
    if not gold_set and not pred_set:
        return 1.0
    precision = _safe_div(len(gold_set & pred_set), len(pred_set))
    recall = _safe_div(len(gold_set & pred_set), len(gold_set))
    return _safe_div(2 * precision * recall, precision + recall)


def average_set_f1(
    rows: Sequence[Prediction],
    *,
    gold_attr: str,
    predicted_attr: str,
) -> float:
    values = [
        set_f1(getattr(row, gold_attr) or [], getattr(row, predicted_attr) or []) for row in rows
    ]
    return _safe_div(sum(values), len(values))


def paired_counterfactual_accuracy(rows: Sequence[Prediction]) -> float:
    by_group: dict[str, list[Prediction]] = defaultdict(list)
    for row in rows:
        if row.event_group_id:
            by_group[row.event_group_id].append(row)
    groups = [group for group in by_group.values() if len(group) >= 2]
    return _safe_div(
        sum(all(row.gold_decision == row.predicted_decision for row in group) for group in groups),
        len(groups),
    )


def bootstrap_ci(
    rows: Sequence[Prediction],
    metric_fn,
    *,
    iterations: int = 500,
    confidence: float = 0.95,
    seed: int = 0,
) -> tuple[float, float]:
    if not rows:
        return (0.0, 0.0)
    rng = random.Random(seed)
    values = []
    for _ in range(iterations):
        sample = [rows[rng.randrange(len(rows))] for _ in rows]
        values.append(metric_fn(sample))
    values.sort()
    alpha = (1 - confidence) / 2
    lo = values[int(alpha * (len(values) - 1))]
    hi = values[int((1 - alpha) * (len(values) - 1))]
    return (lo, hi)


def compute_metrics(rows: Sequence[Prediction], *, evidence_k: int = 5) -> dict[str, object]:
    return {
        "contract_decision_accuracy": accuracy(rows),
        "decision_macro_f1": decision_macro_f1(rows),
        "per_label_recall": per_label_recall(rows),
        "violation_escape_rate": violation_escape_rate(rows),
        "false_block_rate": false_block_rate(rows),
        "evidence_recall_at_k": evidence_recall_at_k(rows, evidence_k),
        "active_contract_f1": average_set_f1(
            rows,
            gold_attr="gold_active_contract_ids",
            predicted_attr="predicted_active_contract_ids",
        ),
        "decisive_relation_f1": average_set_f1(
            rows,
            gold_attr="gold_decisive_relation_ids",
            predicted_attr="predicted_decisive_relation_ids",
        ),
        "paired_counterfactual_accuracy": paired_counterfactual_accuracy(rows),
        "decision_accuracy_ci95": bootstrap_ci(rows, accuracy),
    }
