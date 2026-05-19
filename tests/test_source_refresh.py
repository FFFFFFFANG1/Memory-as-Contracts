from __future__ import annotations

from pathlib import Path

from memory_use_contracts.config import Settings
from memory_use_contracts.layer import MemoryContractLayer
from memory_use_contracts.models import (
    ActionClass,
    Contract,
    ContractEdgeType,
    ContractStatus,
    ContractType,
    Modality,
    Scope,
    Source,
    SourceKind,
    Strength,
)
from memory_use_contracts.source_refresh import refresh_instruction_sources


class FakeExtractor:
    def extract(self, text: str, source_kind: SourceKind, workspace: str = "default") -> list[Contract]:
        path_glob = "generated/**" if "generated/**" in text else "vendor/**"
        return [
            Contract(
                text=f"Do not edit {path_glob}.",
                type=ContractType.PROHIBITION,
                modality=Modality.MUST_NOT,
                source=Source(kind=source_kind, span=f"Do not edit {path_glob}."),
                scope=Scope(workspace=workspace, path_globs=[path_glob]),
                action_classes=[ActionClass.EDIT_FILE],
                strength=Strength.HARD,
            )
        ]


def make_layer(tmp_path: Path) -> MemoryContractLayer:
    layer = MemoryContractLayer(
        Settings(
            openai_api_key="",
            openai_base_url=None,
            llm_model="test-model",
            db_path=tmp_path / "contracts.sqlite",
        )
    )
    layer.extractor = FakeExtractor()  # type: ignore[assignment]
    return layer


def test_refresh_sources_snapshots_and_diff_supersedes_old_contract(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    agents = root / "AGENTS.md"
    agents.write_text("Do not edit vendor/**.", encoding="utf-8")
    layer = make_layer(tmp_path)

    first = refresh_instruction_sources(layer, root=root, adapter="codex", workspace="demo")

    assert first[0].status == "new"
    old_contract = first[0].contracts[0]
    assert old_contract.source.path == str(agents.resolve())
    assert layer.store.list_snapshots()[0].content == "Do not edit vendor/**."

    agents.write_text("Do not edit generated/**.", encoding="utf-8")
    second = refresh_instruction_sources(layer, root=root, adapter="codex", workspace="demo")

    assert second[0].status == "changed"
    assert "vendor/**" in (second[0].diff or "")
    assert "generated/**" in (second[0].diff or "")
    assert layer.store.get_contract(old_contract.id).status == ContractStatus.SUPERSEDED  # type: ignore[union-attr]
    assert layer.store.list_edges()[0].relation == ContractEdgeType.SUPERSEDES
    active = layer.store.list_contracts(ContractStatus.ACTIVE)
    assert active[0].scope.path_globs == ["generated/**"]
