from __future__ import annotations

from pathlib import Path

from memory_use_contracts.actions import build_command_action, build_file_action
from memory_use_contracts.config import Settings
from memory_use_contracts.layer import MemoryContractLayer
from memory_use_contracts.models import (
    ActionClass,
    Contract,
    ContractStatus,
    ContractType,
    GateDecisionType,
    Modality,
    Scope,
    Source,
    SourceKind,
    Strength,
)
from memory_use_contracts.source_refresh import refresh_instruction_sources


class InstructionExtractor:
    def extract(self, text: str, source_kind: SourceKind, workspace: str = "default") -> list[Contract]:
        if "Current full file content:" in text:
            text = text.split("Current full file content:", maxsplit=1)[1]
        contracts: list[Contract] = []
        if "vendor/**" in text:
            contracts.append(_prohibition("Do not edit vendor/**.", "vendor/**", workspace, source_kind))
        if "generated/**" in text:
            contracts.append(
                _prohibition("Do not edit generated/**.", "generated/**", workspace, source_kind)
            )
        if "uv run pytest" in text:
            contracts.append(
                Contract(
                    text="Always run uv run pytest before finishing.",
                    type=ContractType.REQUIREMENT,
                    modality=Modality.MUST,
                    source=Source(kind=source_kind, span="uv run pytest"),
                    scope=Scope(workspace=workspace),
                    action_classes=[ActionClass.RUN_COMMAND],
                    strength=Strength.HARD,
                )
            )
        if "Do not push" in text:
            contracts.append(
                Contract(
                    text="Do not push commits unless explicitly asked.",
                    type=ContractType.PROHIBITION,
                    modality=Modality.MUST_NOT,
                    source=Source(kind=source_kind, span="Do not push"),
                    scope=Scope(workspace=workspace),
                    action_classes=[ActionClass.PUSH],
                    strength=Strength.HARD,
                    confirmation="required_to_override",
                )
            )
        return contracts


def test_instruction_refresh_gate_and_receipt_flow(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    agents = root / "AGENTS.md"
    agents.write_text(
        "Do not edit vendor/**. Always run uv run pytest before finishing.",
        encoding="utf-8",
    )
    (root / "CLAUDE.md").write_text("Do not push commits unless explicitly asked.", encoding="utf-8")
    layer = _layer(tmp_path)

    first = refresh_instruction_sources(layer, root=root, adapter="all", workspace="demo")
    assert [result.status for result in first] == ["new", "new"]

    vendor_decision = layer.gate(build_file_action("edit", "vendor/a.py", intent="fix bug"))
    assert vendor_decision.decision == GateDecisionType.BLOCK

    test_decision = layer.gate(build_command_action("pytest", intent="run tests"))
    assert test_decision.decision == GateDecisionType.REVISE

    push_decision = layer.gate(build_command_action("git push origin main", intent="publish"))
    receipt = layer.record_result(
        build_command_action("git push origin main", intent="publish"),
        push_decision,
        result="not_executed",
    )
    assert push_decision.decision == GateDecisionType.BLOCK
    assert receipt.contracts_used == push_decision.applicable_contracts

    agents.write_text(
        "Do not edit generated/**. Always run uv run pytest before finishing.",
        encoding="utf-8",
    )
    changed = refresh_instruction_sources(layer, root=root, adapter="codex", workspace="demo")
    assert changed[0].status == "changed"
    assert "vendor/**" in (changed[0].diff or "")
    assert "generated/**" in (changed[0].diff or "")

    active = layer.store.list_contracts(ContractStatus.ACTIVE)
    active_text = {contract.text for contract in active}
    assert "Do not edit generated/**." in active_text
    assert "Do not edit vendor/**." not in active_text
    assert layer.gate(build_file_action("edit", "vendor/a.py", intent="fix bug")).decision == (
        GateDecisionType.ALLOW
    )
    assert layer.gate(build_file_action("edit", "generated/a.py", intent="fix bug")).decision == (
        GateDecisionType.BLOCK
    )


def _layer(tmp_path: Path) -> MemoryContractLayer:
    layer = MemoryContractLayer(
        Settings(
            openai_api_key="",
            openai_base_url=None,
            llm_model="test-model",
            db_path=tmp_path / "contracts.sqlite",
        )
    )
    layer.extractor = InstructionExtractor()  # type: ignore[assignment]
    return layer


def _prohibition(
    text: str,
    path_glob: str,
    workspace: str,
    source_kind: SourceKind,
) -> Contract:
    return Contract(
        text=text,
        type=ContractType.PROHIBITION,
        modality=Modality.MUST_NOT,
        source=Source(kind=source_kind, span=text),
        scope=Scope(workspace=workspace, path_globs=[path_glob]),
        action_classes=[ActionClass.EDIT_FILE, ActionClass.DELETE_FILE, ActionClass.FORMAT_FILE],
        strength=Strength.HARD,
    )
