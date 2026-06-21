from __future__ import annotations

from typing import Any, TypeAlias

from pydantic import ValidationError

from benchmarks.schemas.models import (
    CanonicalAction,
    CanonicalEvent,
    ContractGraph,
    HistoryPack,
    QAItem,
)

Artifact: TypeAlias = ContractGraph | CanonicalAction | CanonicalEvent | HistoryPack | QAItem

_MODELS = {
    "contract_graph": ContractGraph,
    "canonical_action": CanonicalAction,
    "canonical_event": CanonicalEvent,
    "history_pack": HistoryPack,
    "qa_item": QAItem,
}


def validate_artifact(kind: str, payload: dict[str, Any]) -> Artifact:
    """Validate one benchmark artifact and return its typed model."""
    try:
        model = _MODELS[kind]
    except KeyError as exc:
        valid = ", ".join(sorted(_MODELS))
        raise ValueError(f"unknown artifact kind {kind!r}; expected one of: {valid}") from exc
    try:
        return model.model_validate(payload)
    except ValidationError:
        raise
