from __future__ import annotations

from pathlib import Path

from memory_use_contracts.adapters import find_claude_code_files, find_codex_files, read_memory_file


def test_codex_adapter_finds_only_agents_md(tmp_path: Path) -> None:
    (tmp_path / "AGENTS.md").write_text("Codex rules", encoding="utf-8")
    (tmp_path / "CLAUDE.md").write_text("Claude rules", encoding="utf-8")
    nested = tmp_path / "nested"
    nested.mkdir()
    (nested / "AGENTS.md").write_text("Nested Codex rules", encoding="utf-8")

    found = [path.name for path in find_codex_files(tmp_path)]

    assert found == ["AGENTS.md", "AGENTS.md"]
    assert all(path.name == "AGENTS.md" for path in find_codex_files(tmp_path))


def test_claude_code_adapter_finds_only_claude_md(tmp_path: Path) -> None:
    (tmp_path / "AGENTS.md").write_text("Codex rules", encoding="utf-8")
    (tmp_path / "CLAUDE.md").write_text("Claude rules", encoding="utf-8")

    found = find_claude_code_files(tmp_path)

    assert [path.name for path in found] == ["CLAUDE.md"]


def test_read_memory_file(tmp_path: Path) -> None:
    path = tmp_path / "AGENTS.md"
    path.write_text("Use uv.", encoding="utf-8")

    assert read_memory_file(path) == "Use uv."
