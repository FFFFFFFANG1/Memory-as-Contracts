from __future__ import annotations

import difflib
import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from memory_use_contracts.adapters import find_claude_code_files, find_codex_files, workspace_name
from memory_use_contracts.layer import MemoryContractLayer
from memory_use_contracts.models import Contract, SourceKind, SourceSnapshot


@dataclass
class RefreshResult:
    path: Path
    adapter: str
    status: str
    fingerprint: str
    contracts: list[Contract]
    diff: str | None = None


def refresh_instruction_sources(
    layer: MemoryContractLayer,
    root: str | Path,
    adapter: str = "all",
    workspace: str | None = None,
) -> list[RefreshResult]:
    root_path = Path(root)
    resolved_workspace = workspace_name(root_path, workspace)
    files = _adapter_files(root_path, adapter)
    results: list[RefreshResult] = []
    for adapter_name, path in files:
        results.append(
            refresh_instruction_file(
                layer=layer,
                path=path,
                adapter=adapter_name,
                workspace=resolved_workspace,
            )
        )
    return results


def refresh_instruction_file(
    layer: MemoryContractLayer,
    path: str | Path,
    adapter: str,
    workspace: str,
) -> RefreshResult:
    file_path = Path(path)
    content = file_path.read_text(encoding="utf-8")
    fingerprint = content_fingerprint(content)
    source_key = snapshot_key(adapter, file_path, workspace)
    previous = layer.store.get_snapshot(source_key)
    snapshot = SourceSnapshot(
        source_key=source_key,
        adapter=adapter,
        path=str(file_path.resolve()),
        workspace=workspace,
        source_kind=SourceKind.PROJECT_DOC,
        fingerprint=fingerprint,
        content=content,
        observed_at=datetime.now(timezone.utc),
    )

    if previous and previous.fingerprint == fingerprint:
        layer.store.upsert_snapshot(snapshot)
        return RefreshResult(
            path=file_path,
            adapter=adapter,
            status="unchanged",
            fingerprint=fingerprint,
            contracts=[],
        )

    diff = None
    if previous:
        diff = unified_diff(previous.content, content, previous.path, str(file_path.resolve()))
        prompt = _changed_file_prompt(content=content, diff=diff)
        supersede_source = True
        status = "changed"
    else:
        prompt = content
        supersede_source = False
        status = "new"

    contracts = layer.ingest_text(
        prompt,
        source_kind=SourceKind.PROJECT_DOC,
        workspace=workspace,
        source_path=str(file_path.resolve()),
        source_fingerprint=fingerprint,
        supersede_source=supersede_source,
    )
    layer.store.upsert_snapshot(snapshot)
    return RefreshResult(
        path=file_path,
        adapter=adapter,
        status=status,
        fingerprint=fingerprint,
        contracts=contracts,
        diff=diff,
    )


def content_fingerprint(content: str) -> str:
    return "sha256:" + hashlib.sha256(content.encode("utf-8")).hexdigest()


def snapshot_key(adapter: str, path: str | Path, workspace: str) -> str:
    return f"{workspace}:{adapter}:{Path(path).resolve()}"


def unified_diff(old_content: str, new_content: str, old_path: str, new_path: str) -> str:
    return "".join(
        difflib.unified_diff(
            old_content.splitlines(keepends=True),
            new_content.splitlines(keepends=True),
            fromfile=old_path,
            tofile=new_path,
        )
    )


def _adapter_files(root: Path, adapter: str) -> list[tuple[str, Path]]:
    files: list[tuple[str, Path]] = []
    if adapter in {"codex", "all"}:
        files.extend(("codex", path) for path in find_codex_files(root))
    if adapter in {"cc", "claude", "all"}:
        files.extend(("cc", path) for path in find_claude_code_files(root))
    return files


def _changed_file_prompt(content: str, diff: str) -> str:
    return (
        "A project instruction file changed. Extract the currently valid Memory Use "
        "Contracts from the current full file content. Use the diff only to identify "
        "what changed; do not extract removed rules as active contracts.\n\n"
        "Unified diff:\n"
        f"{diff}\n\n"
        "Current full file content:\n"
        f"{content}"
    )
