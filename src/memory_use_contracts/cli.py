from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from memory_use_contracts.actions import FileOperation, build_command_action, build_file_action
from memory_use_contracts.adapters import (
    find_claude_code_files,
    find_codex_files,
    ingest_file as ingest_memory_file,
    ingest_files,
    workspace_name,
)
from memory_use_contracts.config import load_settings
from memory_use_contracts.extractor import ContractExtractionError, ContractExtractor
from memory_use_contracts.layer import MemoryContractLayer
from memory_use_contracts.models import (
    ActionClass,
    ActionSignature,
    Contract,
    ContractType,
    Modality,
    Scope,
    ScopeLevel,
    Source,
    SourceKind,
    Strength,
)
from memory_use_contracts.source_refresh import refresh_instruction_sources

app = typer.Typer(help="Memory Use Contracts v0 CLI")
console = Console()


@app.command()
def init() -> None:
    """Initialize local contract storage."""
    layer = MemoryContractLayer.from_env()
    layer.init()
    console.print(f"Initialized contract store at {layer.settings.db_path}")


@app.command()
def ingest(
    text: str = typer.Option(..., help="Raw memory or instruction text."),
    source_kind: SourceKind = typer.Option(SourceKind.USER_EXPLICIT),
    workspace: str = typer.Option("default"),
) -> None:
    """Extract and store contracts from text using the configured small model."""
    layer = MemoryContractLayer.from_env()
    try:
        contracts = layer.ingest_text(text, source_kind=source_kind, workspace=workspace)
    except ContractExtractionError as exc:
        _fail(str(exc))
    _print_contracts(contracts)


@app.command("ingest-file")
def ingest_file_command(
    path: Path = typer.Argument(..., exists=True, file_okay=True, dir_okay=False, readable=True),
    source_kind: SourceKind = typer.Option(SourceKind.PROJECT_DOC),
    workspace: str = typer.Option("default"),
) -> None:
    """Extract and store contracts from a single memory or instruction file."""
    layer = MemoryContractLayer.from_env()
    try:
        contracts = ingest_memory_file(layer, path, source_kind=source_kind, workspace=workspace)
    except ContractExtractionError as exc:
        _fail(str(exc))
    _print_contracts(contracts)


@app.command("ingest-codex")
def ingest_codex(
    root: Path = typer.Option(Path("."), exists=True, file_okay=False, dir_okay=True, readable=True),
    workspace: str | None = typer.Option(None),
) -> None:
    """Scan a Codex project root for AGENTS.md and ingest it as project docs."""
    layer = MemoryContractLayer.from_env()
    paths = find_codex_files(root)
    if not paths:
        _fail(f"No AGENTS.md files found under {root}")
    try:
        results = ingest_files(
            layer,
            paths,
            source_kind=SourceKind.PROJECT_DOC,
            workspace=workspace_name(root, workspace),
        )
    except ContractExtractionError as exc:
        _fail(str(exc))
    _print_ingest_results(results)


@app.command("ingest-cc")
def ingest_claude_code(
    root: Path = typer.Option(Path("."), exists=True, file_okay=False, dir_okay=True, readable=True),
    workspace: str | None = typer.Option(None),
) -> None:
    """Scan a Claude Code project root for CLAUDE.md and ingest it as project docs."""
    layer = MemoryContractLayer.from_env()
    paths = find_claude_code_files(root)
    if not paths:
        _fail(f"No CLAUDE.md files found under {root}")
    try:
        results = ingest_files(
            layer,
            paths,
            source_kind=SourceKind.PROJECT_DOC,
            workspace=workspace_name(root, workspace),
        )
    except ContractExtractionError as exc:
        _fail(str(exc))
    _print_ingest_results(results)


@app.command("refresh-instructions")
def refresh_instructions(
    root: Path = typer.Option(Path("."), exists=True, file_okay=False, dir_okay=True, readable=True),
    adapter: str = typer.Option("all", help="codex, cc, claude, or all."),
    workspace: str | None = typer.Option(None),
    background: bool = typer.Option(False, help="Run refresh in a background subprocess."),
) -> None:
    """Diff tracked instruction files and ingest changed AGENTS.md / CLAUDE.md contracts."""
    if background:
        cmd = [
            sys.executable,
            "-m",
            "memory_use_contracts.background",
            "refresh-instructions",
            "--root",
            str(root),
            "--adapter",
            adapter,
        ]
        if workspace:
            cmd.extend(["--workspace", workspace])
        process = subprocess.Popen(
            cmd,
            cwd=Path.cwd(),
            env=os.environ.copy(),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        console.print({"started": True, "pid": process.pid})
        return

    layer = MemoryContractLayer.from_env()
    try:
        results = refresh_instruction_sources(
            layer=layer,
            root=root,
            adapter=adapter,
            workspace=workspace,
        )
    except ContractExtractionError as exc:
        _fail(str(exc))
    console.print_json(
        json.dumps(
            [
                {
                    "path": str(result.path),
                    "adapter": result.adapter,
                    "status": result.status,
                    "fingerprint": result.fingerprint,
                    "contract_count": len(result.contracts),
                }
                for result in results
            ]
        )
    )


@app.command("add-contract")
def add_contract(
    text: str = typer.Option(...),
    contract_type: ContractType = typer.Option(..., "--type"),
    modality: Modality = typer.Option(...),
    strength: Strength = typer.Option(Strength.HARD),
    confirmation: str = typer.Option("not_required"),
    source_kind: SourceKind = typer.Option(SourceKind.USER_EXPLICIT),
    workspace: str = typer.Option("default"),
    scope: ScopeLevel = typer.Option(ScopeLevel.SESSION),
    path: list[str] = typer.Option([], "--path", help="Path glob for file/folder scoped contracts."),
    action_class: list[ActionClass] = typer.Option([], "--action-class"),
) -> None:
    """Directly write an explicit user/project contract without LLM extraction."""
    layer = MemoryContractLayer.from_env()
    contract = Contract(
        text=text,
        type=contract_type,
        modality=modality,
        source=Source(kind=source_kind, span=text),
        scope=Scope(
            workspace=workspace,
            path_globs=path,
            level=scope,
        ),
        action_classes=action_class,
        strength=strength,
        confirmation=confirmation,  # type: ignore[arg-type]
    )
    stored = layer.add_contract(contract)
    _print_contracts([stored])


@app.command("llm-check")
def llm_check() -> None:
    """Run a live write-time extraction check without storing contracts."""
    settings = load_settings()
    sample = (
        "In this repo, do not edit vendor/**. "
        "Always run uv run pytest before finishing."
    )
    try:
        contracts = ContractExtractor(settings).extract(
            sample,
            source_kind=SourceKind.PROJECT_DOC,
            workspace="llm-check",
        )
    except ContractExtractionError as exc:
        _fail(str(exc))
    console.print(
        {
            "ok": True,
            "model": settings.llm_model,
            "contract_count": len(contracts),
            "contract_types": [contract.type.value for contract in contracts],
            "action_classes": [
                [action_class.value for action_class in contract.action_classes]
                for contract in contracts
            ],
        }
    )


@app.command()
def gate(
    action_class: ActionClass = typer.Option(...),
    target: str | None = typer.Option(None),
    cwd: str | None = typer.Option(None),
    risk: str = typer.Option("medium"),
    intent: str = typer.Option(""),
    record: bool = typer.Option(False, help="Write a pending influence receipt."),
) -> None:
    """Evaluate an action against applicable contracts."""
    layer = MemoryContractLayer.from_env()
    action = ActionSignature(
        action_class=action_class,
        target=target,
        cwd=cwd,
        risk=risk,  # type: ignore[arg-type]
        intent=intent,
    )
    decision = layer.gate(action)
    console.print_json(decision.model_dump_json())
    if record:
        receipt = layer.record_result(action, decision, result="pending")
        console.print_json(receipt.model_dump_json())


@app.command("gate-file")
def gate_file(
    op: FileOperation = typer.Option(...),
    path: Path = typer.Option(...),
    cwd: str | None = typer.Option(None),
    risk: str = typer.Option("medium"),
    intent: str = typer.Option(""),
    record: bool = typer.Option(False, help="Write a pending influence receipt."),
) -> None:
    """Evaluate a simulated file action against applicable contracts."""
    layer = MemoryContractLayer.from_env()
    action = build_file_action(op=op, path=path, cwd=cwd, risk=risk, intent=intent)
    _print_gate_decision(layer, action, record=record)


@app.command("gate-command")
def gate_command(
    command: str = typer.Option(...),
    cwd: str | None = typer.Option(None),
    risk: str = typer.Option("medium"),
    intent: str = typer.Option(""),
    record: bool = typer.Option(False, help="Write a pending influence receipt."),
) -> None:
    """Evaluate a simulated shell/git/dependency command against applicable contracts."""
    layer = MemoryContractLayer.from_env()
    action = build_command_action(command=command, cwd=cwd, risk=risk, intent=intent)
    _print_gate_decision(layer, action, record=record)


@app.command()
def contracts() -> None:
    """List stored contracts."""
    store = MemoryContractLayer.from_env().store
    table = Table("id", "status", "type", "strength", "text")
    for contract in store.list_contracts():
        table.add_row(
            contract.id,
            contract.status.value,
            contract.type.value,
            contract.strength.value,
            contract.text,
        )
    console.print(table)


@app.command()
def receipts() -> None:
    """List influence receipts."""
    store = MemoryContractLayer.from_env().store
    table = Table("id", "action_id", "decision", "target", "result")
    for receipt in store.list_receipts():
        table.add_row(
            receipt.id,
            receipt.action_id,
            receipt.decision.value,
            receipt.target or "",
            receipt.result,
        )
    console.print(table)


@app.command()
def conflicts() -> None:
    """List conflict/supersession graph edges."""
    store = MemoryContractLayer.from_env().store
    table = Table("id", "source", "relation", "target", "reason")
    for edge in store.list_edges():
        table.add_row(
            edge.id,
            edge.source_contract_id,
            edge.relation.value,
            edge.target_contract_id,
            edge.reason,
        )
    console.print(table)


@app.command()
def snapshots() -> None:
    """List tracked instruction file snapshots."""
    store = MemoryContractLayer.from_env().store
    table = Table("adapter", "workspace", "path", "fingerprint")
    for snapshot in store.list_snapshots():
        table.add_row(
            snapshot.adapter,
            snapshot.workspace,
            snapshot.path,
            snapshot.fingerprint,
        )
    console.print(table)


@app.command()
def env() -> None:
    """Show resolved non-secret configuration."""
    settings = load_settings()
    console.print(
        {
            "OPENAI_BASE_URL": settings.openai_base_url,
            "MUC_LLM_MODEL": settings.llm_model,
            "MUC_DB_PATH": str(Path(settings.db_path)),
            "OPENAI_API_KEY_SET": bool(settings.openai_api_key),
        }
    )


def _print_gate_decision(
    layer: MemoryContractLayer,
    action: ActionSignature,
    record: bool,
) -> None:
    decision = layer.gate(action)
    console.print_json(decision.model_dump_json())
    if record:
        receipt = layer.record_result(action, decision, result="pending")
        console.print_json(receipt.model_dump_json())


def _print_contracts(contracts: list) -> None:
    console.print_json(json.dumps([contract.model_dump(mode="json") for contract in contracts]))


def _print_ingest_results(results: dict[Path, list]) -> None:
    console.print_json(
        json.dumps(
            {
                str(path): [contract.model_dump(mode="json") for contract in contracts]
                for path, contracts in results.items()
            }
        )
    )


def _fail(message: str) -> None:
    console.print(f"[red]{message}[/red]")
    raise typer.Exit(1)
