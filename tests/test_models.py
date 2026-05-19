from __future__ import annotations

import pytest

from memory_use_contracts.models import (
    ActionClass,
    Contract,
    ContractType,
    Modality,
    Source,
    SourceKind,
)


def test_fact_cannot_bind_action_class() -> None:
    with pytest.raises(ValueError, match="fact contracts cannot"):
        Contract(
            text="The repo uses uv.",
            type=ContractType.FACT,
            modality=Modality.MAY,
            source=Source(kind=SourceKind.TOOL_OBSERVATION, span="uses uv"),
            action_classes=[ActionClass.RUN_COMMAND],
        )


def test_prohibition_can_bind_action_class() -> None:
    contract = Contract(
        text="Do not edit linked repos.",
        type=ContractType.PROHIBITION,
        modality=Modality.MUST_NOT,
        source=Source(kind=SourceKind.USER_EXPLICIT, span="Do not edit linked repos."),
        action_classes=[ActionClass.EDIT_FILE],
    )

    assert contract.action_classes == [ActionClass.EDIT_FILE]
