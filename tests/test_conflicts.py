from __future__ import annotations

from pathlib import Path

from memory_use_contracts.config import Settings
from memory_use_contracts.layer import MemoryContractLayer
from memory_use_contracts.models import (
    ActionClass,
    ActionSignature,
    Contract,
    ContractEdgeType,
    ContractStatus,
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


def test_stronger_contract_supersedes_old_contract_and_writes_edge(tmp_path: Path) -> None:
    layer = make_layer(tmp_path)
    old = layer.add_contract(
        Contract(
            text="Do not edit files under src/**.",
            type=ContractType.PROHIBITION,
            modality=Modality.MUST_NOT,
            source=Source(kind=SourceKind.PROJECT_DOC, span="Do not edit"),
            scope=Scope(workspace="demo", path_globs=["src/**"]),
            action_classes=[ActionClass.EDIT_FILE],
            strength=Strength.HARD,
        )
    )

    new = layer.add_contract(
        Contract(
            text="For this project, edit files under src/** when fixing bugs.",
            type=ContractType.REQUIREMENT,
            modality=Modality.MUST,
            source=Source(kind=SourceKind.USER_EXPLICIT, span="edit files under src/**"),
            scope=Scope(workspace="demo", path_globs=["src/**"]),
            action_classes=[ActionClass.EDIT_FILE],
            strength=Strength.HARD,
        )
    )

    assert new.status == ContractStatus.ACTIVE
    assert layer.store.get_contract(old.id).status == ContractStatus.SUPERSEDED  # type: ignore[union-attr]
    edges = layer.store.list_edges()
    assert [(edge.relation, edge.source_contract_id, edge.target_contract_id) for edge in edges] == [
        (ContractEdgeType.SUPERSEDES, new.id, old.id)
    ]


def test_equal_precedence_conflict_defers_gate(tmp_path: Path) -> None:
    layer = make_layer(tmp_path)
    layer.add_contract(
        Contract(
            text="Do not edit vendor/**.",
            type=ContractType.PROHIBITION,
            modality=Modality.MUST_NOT,
            source=Source(kind=SourceKind.PROJECT_DOC, span="Do not edit vendor/**"),
            scope=Scope(workspace="demo", path_globs=["vendor/**"]),
            action_classes=[ActionClass.EDIT_FILE],
            strength=Strength.HARD,
        )
    )
    pending = layer.add_contract(
        Contract(
            text="Edit vendor/** to apply the emergency patch.",
            type=ContractType.REQUIREMENT,
            modality=Modality.MUST,
            source=Source(kind=SourceKind.PROJECT_DOC, span="Edit vendor/**"),
            scope=Scope(workspace="demo", path_globs=["vendor/**"]),
            action_classes=[ActionClass.EDIT_FILE],
            strength=Strength.HARD,
        )
    )

    assert pending.status == ContractStatus.PENDING_CONFLICT
    assert layer.store.list_edges()[0].relation == ContractEdgeType.CONFLICTS_WITH

    decision = layer.gate(
        ActionSignature(
            action_class=ActionClass.EDIT_FILE,
            target="vendor/a.py",
            intent="apply emergency patch",
        )
    )

    assert decision.decision == GateDecisionType.DEFER


def test_compatible_uv_requirements_do_not_create_conflict(tmp_path: Path) -> None:
    layer = make_layer(tmp_path)
    first = layer.add_contract(
        Contract(
            text="Use uv for dependency and test commands.",
            type=ContractType.REQUIREMENT,
            modality=Modality.MUST,
            source=Source(kind=SourceKind.PROJECT_DOC, span="Use uv"),
            scope=Scope(workspace="demo"),
            action_classes=[ActionClass.RUN_COMMAND],
            strength=Strength.HARD,
        )
    )
    second = layer.add_contract(
        Contract(
            text="Always run uv run pytest before finishing.",
            type=ContractType.PROCEDURE,
            modality=Modality.MUST,
            source=Source(kind=SourceKind.PROJECT_DOC, span="uv run pytest"),
            scope=Scope(workspace="demo"),
            action_classes=[ActionClass.RUN_COMMAND],
            strength=Strength.HARD,
        )
    )

    assert first.status == ContractStatus.ACTIVE
    assert second.status == ContractStatus.ACTIVE
    assert layer.store.list_edges() == []


def test_known_package_manager_conflict_enters_pending_conflict(tmp_path: Path) -> None:
    layer = make_layer(tmp_path)
    layer.add_contract(
        Contract(
            text="Use npm for test commands.",
            type=ContractType.PROCEDURE,
            modality=Modality.MUST,
            source=Source(kind=SourceKind.PROJECT_DOC, span="Use npm"),
            scope=Scope(workspace="demo"),
            action_classes=[ActionClass.RUN_COMMAND],
            strength=Strength.HARD,
        )
    )
    pending = layer.add_contract(
        Contract(
            text="Use uv for test commands.",
            type=ContractType.PROCEDURE,
            modality=Modality.MUST,
            source=Source(kind=SourceKind.PROJECT_DOC, span="Use uv"),
            scope=Scope(workspace="demo"),
            action_classes=[ActionClass.RUN_COMMAND],
            strength=Strength.HARD,
        )
    )

    assert pending.status == ContractStatus.PENDING_CONFLICT
    assert layer.store.list_edges()[0].relation == ContractEdgeType.CONFLICTS_WITH
