from __future__ import annotations

from pathlib import Path

from memory_use_contracts.config import Settings
from memory_use_contracts.layer import MemoryContractLayer
from memory_use_contracts.models import (
    ActionClass,
    ActionSignature,
    Contract,
    ContractType,
    GateDecisionType,
    Modality,
    Scope,
    Source,
    SourceKind,
    Strength,
)


def make_layer(tmp_path: Path) -> MemoryContractLayer:
    return MemoryContractLayer(
        Settings(
            openai_api_key="",
            openai_base_url=None,
            llm_model="test-model",
            db_path=tmp_path / "contracts.sqlite",
        )
    )


def test_hard_prohibition_blocks_matching_action(tmp_path: Path) -> None:
    layer = make_layer(tmp_path)
    layer.add_contract(
        Contract(
            text="Do not edit files under linked_repos unless explicitly asked.",
            type=ContractType.PROHIBITION,
            modality=Modality.MUST_NOT,
            source=Source(kind=SourceKind.USER_EXPLICIT, span="Do not edit files"),
            scope=Scope(path_globs=["linked_repos/**"]),
            action_classes=[ActionClass.EDIT_FILE],
            strength=Strength.HARD,
            confirmation="required_to_override",
        )
    )

    decision = layer.gate(
        ActionSignature(
            action_class=ActionClass.EDIT_FILE,
            target="linked_repos/foo.py",
            intent="fix bug",
        )
    )

    assert decision.decision == GateDecisionType.BLOCK
    assert decision.applicable_contracts


def test_satisfied_requirement_allows(tmp_path: Path) -> None:
    layer = make_layer(tmp_path)
    layer.add_contract(
        Contract(
            text="Use uv run pytest for tests in this repo.",
            type=ContractType.REQUIREMENT,
            modality=Modality.MUST,
            source=Source(kind=SourceKind.PROJECT_DOC, span="uv run pytest"),
            action_classes=[ActionClass.RUN_COMMAND],
            strength=Strength.HARD,
        )
    )

    decision = layer.gate(
        ActionSignature(
            action_class=ActionClass.RUN_COMMAND,
            target="uv run pytest",
            intent="run tests",
        )
    )

    assert decision.decision == GateDecisionType.ALLOW


def test_unsatisfied_requirement_revises(tmp_path: Path) -> None:
    layer = make_layer(tmp_path)
    layer.add_contract(
        Contract(
            text="Use uv, not pip, for project dependency management.",
            type=ContractType.REQUIREMENT,
            modality=Modality.MUST,
            source=Source(kind=SourceKind.PROJECT_DOC, span="Use uv, not pip"),
            action_classes=[ActionClass.INSTALL_DEPENDENCY],
            strength=Strength.HARD,
        )
    )

    decision = layer.gate(
        ActionSignature(
            action_class=ActionClass.INSTALL_DEPENDENCY,
            target="pip install pytest",
            intent="install pytest",
        )
    )

    assert decision.decision == GateDecisionType.REVISE


def test_hard_prohibition_with_required_confirmation_confirms(tmp_path: Path) -> None:
    layer = make_layer(tmp_path)
    layer.add_contract(
        Contract(
            text="Do not push commits without explicit user confirmation.",
            type=ContractType.PROHIBITION,
            modality=Modality.MUST_NOT,
            source=Source(kind=SourceKind.PROJECT_DOC, span="Do not push"),
            action_classes=[ActionClass.PUSH],
            strength=Strength.HARD,
            confirmation="required",
        )
    )

    decision = layer.gate(
        ActionSignature(
            action_class=ActionClass.PUSH,
            target="git push origin main",
            intent="publish changes",
        )
    )

    assert decision.decision == GateDecisionType.CONFIRM


def test_receipt_is_recorded(tmp_path: Path) -> None:
    layer = make_layer(tmp_path)
    action = ActionSignature(action_class=ActionClass.UPDATE_DOCS, target="README.md")
    decision = layer.gate(action)
    receipt = layer.record_result(action, decision, result="tool_executed")

    receipts = layer.store.list_receipts()

    assert receipts == [receipt]
    assert receipts[0].result == "tool_executed"
