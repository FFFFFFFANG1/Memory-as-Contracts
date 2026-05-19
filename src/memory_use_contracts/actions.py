from __future__ import annotations

import shlex
from pathlib import Path
from enum import StrEnum

from memory_use_contracts.models import ActionClass, ActionSignature


class FileOperation(StrEnum):
    EDIT = "edit"
    DELETE = "delete"
    FORMAT = "format"


FILE_OP_ACTIONS = {
    FileOperation.EDIT: ActionClass.EDIT_FILE,
    FileOperation.DELETE: ActionClass.DELETE_FILE,
    FileOperation.FORMAT: ActionClass.FORMAT_FILE,
}


def build_file_action(
    op: FileOperation | str,
    path: str | Path,
    intent: str = "",
    cwd: str | None = None,
    risk: str = "medium",
) -> ActionSignature:
    action_class = FILE_OP_ACTIONS[FileOperation(op)]
    return ActionSignature(
        action_class=action_class,
        target=str(path),
        cwd=cwd,
        risk=risk,  # type: ignore[arg-type]
        intent=intent,
    )


def build_command_action(
    command: str,
    intent: str = "",
    cwd: str | None = None,
    risk: str = "medium",
) -> ActionSignature:
    return ActionSignature(
        action_class=infer_command_action_class(command),
        target=command,
        cwd=cwd,
        risk=risk,  # type: ignore[arg-type]
        intent=intent,
    )


def infer_command_action_class(command: str) -> ActionClass:
    try:
        parts = shlex.split(command)
    except ValueError:
        parts = command.split()
    lowered = [part.lower() for part in parts]
    if not lowered:
        return ActionClass.RUN_COMMAND

    if lowered[:2] == ["git", "commit"]:
        return ActionClass.COMMIT
    if lowered[:2] == ["git", "push"]:
        return ActionClass.PUSH

    install_markers = {
        ("npm", "install"),
        ("npm", "i"),
        ("pnpm", "install"),
        ("pnpm", "add"),
        ("yarn", "add"),
        ("pip", "install"),
        ("uv", "add"),
        ("uv", "pip"),
        ("poetry", "add"),
    }
    first_two = tuple(lowered[:2])
    first_three = tuple(lowered[:3])
    if first_two in install_markers or first_three == ("uv", "pip", "install"):
        return ActionClass.INSTALL_DEPENDENCY

    return ActionClass.RUN_COMMAND
