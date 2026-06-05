from __future__ import annotations

import shlex
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from memory_as_contracts.models import (
    ActionSignature,
    AvailableAction,
    RiskLevel,
    SessionContext,
    SideEffect,
    TimeContext,
    ToolCall,
    WorkspaceContext,
)


def coding_available_actions() -> list[AvailableAction]:
    return [
        AvailableAction(name="exec", canonical_tags=["shell"], side_effect=SideEffect.WRITE),
        AvailableAction(name="file.read", canonical_tags=["file_read"], side_effect=SideEffect.READ),
        AvailableAction(
            name="file.write",
            canonical_tags=["file_write", "workspace_write"],
            side_effect=SideEffect.WRITE,
        ),
        AvailableAction(
            name="file.delete",
            canonical_tags=["file_delete", "destructive"],
            side_effect=SideEffect.WRITE,
        ),
        AvailableAction(
            name="git.commit",
            canonical_tags=["version_control", "source_modification"],
            side_effect=SideEffect.WRITE,
        ),
        AvailableAction(
            name="git.push",
            canonical_tags=["external_write", "publish_code"],
            side_effect=SideEffect.EXTERNAL_WRITE,
        ),
        AvailableAction(
            name="dependency.install",
            canonical_tags=["dependency_change"],
            side_effect=SideEffect.WRITE,
        ),
        AvailableAction(name="web.search", canonical_tags=["network_read"], side_effect=SideEffect.READ),
        AvailableAction(
            name="email.send",
            canonical_tags=["external_write", "notify_human"],
            side_effect=SideEffect.EXTERNAL_WRITE,
        ),
        AvailableAction(
            name="message.send",
            canonical_tags=["external_write", "notify_human"],
            side_effect=SideEffect.EXTERNAL_WRITE,
        ),
        AvailableAction(
            name="memory.write",
            canonical_tags=["memory_write"],
            side_effect=SideEffect.WRITE,
        ),
    ]


@dataclass(frozen=True)
class SignatureContext:
    host: str = "codex"
    agent_family: str = "codex"
    session_id: str = "session"
    conversation_id: str | None = None
    turn_id: str | None = None
    task_id: str | None = None
    user_id: str | None = None
    cwd: str = "."
    repo: str | None = None
    branch: str | None = None
    timezone: str = "UTC"
    now: datetime | None = None
    available_actions: list[AvailableAction] = field(default_factory=coding_available_actions)


class ActionSignatureBuilder:
    """Construct MAC action signatures from adapter tool calls."""

    def build(
        self,
        *,
        tool_name: str,
        raw_arguments: dict,
        intent: str = "",
        context: SignatureContext,
    ) -> ActionSignature:
        host_action, tags, targets, risk, side_effect = self._classify(tool_name, raw_arguments, context)
        zone = ZoneInfo(context.timezone)
        now = context.now.astimezone(zone) if context.now and context.now.tzinfo else context.now
        return ActionSignature(
            host=context.host,
            agent_family=context.agent_family,
            session=SessionContext(
                session_id=context.session_id,
                conversation_id=context.conversation_id,
                turn_id=context.turn_id,
                task_id=context.task_id,
                user_id=context.user_id,
            ),
            time=TimeContext(now=now or datetime.now(zone), timezone=context.timezone),
            workspace=WorkspaceContext(
                cwd=str(Path(context.cwd)),
                repo=context.repo,
                branch=context.branch,
            ),
            available_actions=context.available_actions,
            tool=ToolCall(name=tool_name, raw_arguments=raw_arguments),
            host_action=host_action,
            canonical_tags=sorted(tags),
            targets=targets,
            intent=intent,
            risk=risk,
            side_effect=side_effect,
        )

    def _classify(
        self,
        tool_name: str,
        raw_arguments: dict,
        context: SignatureContext,
    ) -> tuple[str, set[str], list[str], RiskLevel, SideEffect]:
        normalized = _normalized_tool_name(tool_name)
        if normalized in {"bash", "shell", "exec", "exec_command", "terminal", "run_command", "run", "command"}:
            return self._classify_exec(raw_arguments, context)
        if normalized in {"read", "read_file", "fileread", "file.read", "ls", "glob", "grep"}:
            return self._classify_direct_tool("file.read", raw_arguments)
        if normalized in {
            "write",
            "edit",
            "multiedit",
            "apply_patch",
            "patch",
            "filewrite",
            "file.write",
        }:
            return self._classify_direct_tool("file.write", raw_arguments)
        if normalized in {"delete", "remove", "filedelete", "file.delete"}:
            return self._classify_direct_tool("file.delete", raw_arguments)
        if normalized in {"websearch", "web_search", "web.search", "search", "webfetch", "web_fetch"}:
            return self._classify_direct_tool("web.search", raw_arguments)
        if normalized in {"send_message", "message_send", "message.send", "message", "notify", "slack", "sessions_send"}:
            return self._classify_direct_tool("message.send", raw_arguments)
        if normalized in {"send_email", "email_send", "email.send"}:
            return self._classify_direct_tool("email.send", raw_arguments)
        if normalized in {"memory_record", "memory_write", "memory.write"}:
            return self._classify_direct_tool("memory.write", raw_arguments)
        if raw_arguments.get("cmd") or raw_arguments.get("command"):
            return self._classify_exec(raw_arguments, context)
        available = {action.name for action in context.available_actions}
        host_action = tool_name if tool_name in available else "exec"
        return host_action, set(), [], RiskLevel.MEDIUM, SideEffect.WRITE

    def _classify_direct_tool(
        self, tool_name: str, raw_arguments: dict
    ) -> tuple[str, set[str], list[str], RiskLevel, SideEffect]:
        targets = _path_targets(raw_arguments)
        if tool_name == "file.read":
            return "file.read", {"file_read"}, targets, RiskLevel.LOW, SideEffect.READ
        if tool_name == "file.delete":
            return (
                "file.delete",
                {"file_delete", "destructive", "workspace_write"},
                targets,
                RiskLevel.HIGH,
                SideEffect.WRITE,
            )
        if tool_name == "web.search":
            return "web.search", {"network_read"}, [], RiskLevel.LOW, SideEffect.READ
        if tool_name in {"email.send", "message.send"}:
            return (
                tool_name,
                {"external_write", "notify_human"},
                [],
                RiskLevel.HIGH,
                SideEffect.EXTERNAL_WRITE,
            )
        if tool_name == "memory.write":
            return "memory.write", {"memory_write"}, [], RiskLevel.MEDIUM, SideEffect.WRITE
        return (
            "file.write",
            {"file_write", "source_modification", "workspace_write"},
            targets or _patch_targets(raw_arguments),
            RiskLevel.MEDIUM,
            SideEffect.WRITE,
        )

    def _classify_exec(
        self, raw_arguments: dict, context: SignatureContext
    ) -> tuple[str, set[str], list[str], RiskLevel, SideEffect]:
        command = raw_arguments.get("cmd") or raw_arguments.get("command") or ""
        tokens = _tokens(command)
        if not tokens:
            return "exec", {"shell"}, [], RiskLevel.MEDIUM, SideEffect.WRITE
        available = {action.name for action in context.available_actions}
        program = tokens[0]
        subcommand = tokens[1] if len(tokens) > 1 else ""
        if program == "git" and subcommand == "push":
            return _prefer("git.push", available), {"external_write", "publish_code"}, ["origin"], RiskLevel.HIGH, SideEffect.EXTERNAL_WRITE
        if program == "git" and subcommand == "commit":
            return _prefer("git.commit", available), {"version_control", "source_modification"}, [], RiskLevel.MEDIUM, SideEffect.WRITE
        if _looks_like_dependency_install(tokens):
            return _prefer("dependency.install", available), {"dependency_change", "shell"}, [], RiskLevel.HIGH, SideEffect.WRITE
        tags = {"shell"}
        side_effect = SideEffect.WRITE if _looks_effectful(tokens) else SideEffect.READ
        risk = RiskLevel.MEDIUM if side_effect == SideEffect.WRITE else RiskLevel.LOW
        return "exec", tags, [], risk, side_effect


def _prefer(action: str, available: set[str]) -> str:
    return action if action in available else "exec"


def _tokens(command: str) -> list[str]:
    try:
        return shlex.split(command)
    except ValueError:
        return command.split()


def _looks_like_dependency_install(tokens: list[str]) -> bool:
    return (
        len(tokens) >= 2
        and tokens[0] in {"npm", "pnpm", "yarn", "uv", "pip", "pipx"}
        and tokens[1] in {"install", "add", "sync"}
    )


def _looks_effectful(tokens: list[str]) -> bool:
    return any(token in tokens for token in {">", ">>", "rm", "mv", "cp", "touch", "apply_patch"})


def _normalized_tool_name(tool_name: str) -> str:
    return tool_name.strip().lower().replace("-", "_")


def _path_targets(raw_arguments: dict) -> list[str]:
    targets: list[str] = []
    for key in ("path", "file_path", "filepath", "filename"):
        value = raw_arguments.get(key)
        if value:
            targets.append(str(value))
    for key in ("paths", "file_paths"):
        value = raw_arguments.get(key)
        if isinstance(value, list):
            targets.extend(str(item) for item in value if item)
    return sorted({target for target in targets if target})


def _patch_targets(raw_arguments: dict) -> list[str]:
    patch = raw_arguments.get("patch") or raw_arguments.get("value") or raw_arguments.get("input") or ""
    if not isinstance(patch, str):
        return []
    targets: list[str] = []
    prefixes = (
        "*** Add File: ",
        "*** Update File: ",
        "*** Delete File: ",
        "*** Move to: ",
    )
    for line in patch.splitlines():
        for prefix in prefixes:
            if line.startswith(prefix):
                targets.append(line.removeprefix(prefix).strip())
        if line.startswith("+++ b/") or line.startswith("--- a/"):
            targets.append(line[6:].strip())
    return sorted({target for target in targets if target and target != "/dev/null"})
