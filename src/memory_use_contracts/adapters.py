from __future__ import annotations

from pathlib import Path

from memory_use_contracts.layer import MemoryContractLayer
from memory_use_contracts.models import Contract, SourceKind

IGNORED_DIRS = {".git", ".hg", ".muc", ".ruff_cache", ".pytest_cache", ".uv-cache", ".venv", "build"}


def read_memory_file(path: str | Path) -> str:
    file_path = Path(path)
    return file_path.read_text(encoding="utf-8")


def workspace_name(root: str | Path, workspace: str | None = None) -> str:
    if workspace:
        return workspace
    resolved = Path(root).resolve()
    return resolved.name or "default"


def find_codex_files(root: str | Path) -> list[Path]:
    return _find_named_files(root, "AGENTS.md")


def find_claude_code_files(root: str | Path) -> list[Path]:
    return _find_named_files(root, "CLAUDE.md")


def ingest_file(
    layer: MemoryContractLayer,
    path: str | Path,
    source_kind: SourceKind,
    workspace: str,
) -> list[Contract]:
    return layer.ingest_text(read_memory_file(path), source_kind=source_kind, workspace=workspace)


def ingest_files(
    layer: MemoryContractLayer,
    paths: list[Path],
    source_kind: SourceKind,
    workspace: str,
) -> dict[Path, list[Contract]]:
    results: dict[Path, list[Contract]] = {}
    for path in paths:
        results[path] = ingest_file(layer, path, source_kind=source_kind, workspace=workspace)
    return results


def _find_named_files(root: str | Path, filename: str) -> list[Path]:
    root_path = Path(root)
    if root_path.is_file():
        return [root_path] if root_path.name == filename else []
    found: list[Path] = []
    for path in root_path.rglob(filename):
        if any(part in IGNORED_DIRS for part in path.parts):
            continue
        if path.is_file():
            found.append(path)
    return sorted(found)
