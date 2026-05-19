from __future__ import annotations

from memory_use_contracts.actions import build_command_action, build_file_action
from memory_use_contracts.models import ActionClass


def test_build_file_action_maps_operations() -> None:
    assert build_file_action("edit", "src/a.py").action_class == ActionClass.EDIT_FILE
    assert build_file_action("delete", "src/a.py").action_class == ActionClass.DELETE_FILE
    assert build_file_action("format", "src/a.py").action_class == ActionClass.FORMAT_FILE


def test_build_command_action_detects_install_commit_push_and_run() -> None:
    assert build_command_action("uv add rich").action_class == ActionClass.INSTALL_DEPENDENCY
    assert build_command_action("uv pip install pytest").action_class == ActionClass.INSTALL_DEPENDENCY
    assert build_command_action("git commit -m test").action_class == ActionClass.COMMIT
    assert build_command_action("git push origin main").action_class == ActionClass.PUSH
    assert build_command_action("uv run pytest").action_class == ActionClass.RUN_COMMAND
