from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from memory_as_contracts.models import (
    Lifecycle,
    LifecycleType,
    Scope,
    ScopeLevel,
)


@dataclass(frozen=True)
class NormalizationContext:
    workspace: str | None = None
    repo: str | None = None
    task: str | None = None
    agent_family: list[str] = field(default_factory=list)
    organization: str | None = None
    user_id: str | None = None
    timezone: str = "UTC"
    now: datetime | None = None

    def current_time(self) -> datetime:
        zone = ZoneInfo(self.timezone)
        if self.now is None:
            return datetime.now(zone)
        if self.now.tzinfo is None:
            return self.now.replace(tzinfo=zone)
        return self.now.astimezone(zone)


class ScopeNormalizer:
    path_pattern = re.compile(
        r"(?:under|inside|path|folder)\s+`?([A-Za-z0-9_./*?-]+)`?|in\s+`([A-Za-z0-9_./*?-]+)`",
        re.I,
    )
    glob_pattern = re.compile(r"`?([A-Za-z0-9_.-]+/(?:[A-Za-z0-9_.-]+/)*\*\*?)`?")
    relative_path_pattern = re.compile(
        r"\b(?:[A-Za-z0-9_.-]+/)+(?:[A-Za-z0-9_.-]+)\."
        r"(?:py|js|jsx|ts|tsx|md|json|toml|yaml|yml|txt|lock|rs|go|java|c|cc|cpp|h|css|html|sh)\b"
    )
    component_pattern = re.compile(r"(?:component|module|package)\s+`?([A-Za-z0-9_.-]+)`?", re.I)
    bare_file_pattern = re.compile(
        r"\b[A-Za-z0-9_.-]+\.(?:py|js|jsx|ts|tsx|md|json|toml|yaml|yml|txt|lock|rs|go|java|c|cc|cpp|h|css|html|sh)\b"
    )

    def normalize(self, text: str, context: NormalizationContext) -> Scope:
        lower = text.lower()
        if _is_per_turn_text(lower):
            return Scope(
                level=ScopeLevel.PER_TURN,
                workspace=context.workspace,
                repo=context.repo,
                agent_family=context.agent_family,
                user_id=context.user_id,
            )
        component_match = self.component_pattern.search(text)
        if component_match:
            return Scope(
                level=ScopeLevel.COMPONENT,
                workspace=context.workspace,
                repo=context.repo,
                task=context.task,
                component=component_match.group(1).rstrip(".,;:"),
                agent_family=context.agent_family,
                user_id=context.user_id,
            )
        path_match = self.path_pattern.search(text)
        glob_match = self.glob_pattern.search(text)
        relative_path_match = self.relative_path_pattern.search(text)
        if relative_path_match or path_match or glob_match:
            if relative_path_match:
                path_glob = relative_path_match.group(0)
            elif path_match:
                path_glob = path_match.group(1) or path_match.group(2)
            else:
                path_glob = glob_match.group(1)
            path_glob = path_glob.rstrip(".,;:")
            return Scope(
                level=ScopeLevel.PATH,
                workspace=context.workspace,
                repo=context.repo,
                path_globs=[path_glob],
                task=context.task,
                agent_family=context.agent_family,
                user_id=context.user_id,
            )
        bare_file = _selected_bare_file_target(text, self.bare_file_pattern)
        if bare_file and any(token in lower for token in ("edit", "write", "delete", "touch", "read")):
            return Scope(
                level=ScopeLevel.PATH,
                workspace=context.workspace,
                repo=context.repo,
                path_globs=[bare_file],
                task=context.task,
                agent_family=context.agent_family,
                user_id=context.user_id,
            )
        if "generated" in lower and any(token in lower for token in ("edit", "write", "touch")):
            return Scope(
                level=ScopeLevel.PATH,
                workspace=context.workspace,
                repo=context.repo,
                path_globs=["generated/**"],
                task=context.task,
                agent_family=context.agent_family,
                user_id=context.user_id,
            )
        if "this task" in lower or "current task" in lower:
            return Scope(
                level=ScopeLevel.TASK,
                workspace=context.workspace,
                repo=context.repo,
                task=context.task or "current",
                agent_family=context.agent_family,
                user_id=context.user_id,
            )
        if "this session" in lower or "current session" in lower:
            return Scope(
                level=ScopeLevel.SESSION,
                workspace=context.workspace,
                repo=context.repo,
                agent_family=context.agent_family,
                user_id=context.user_id,
            )
        if "globally" in lower or "always" in lower or "from now on" in lower:
            return Scope(
                level=ScopeLevel.GLOBAL,
                agent_family=context.agent_family,
                organization=context.organization,
                user_id=context.user_id,
            )
        if "this repo" in lower and (context.repo or context.workspace):
            return Scope(
                level=ScopeLevel.REPO,
                workspace=context.workspace,
                repo=context.repo,
                agent_family=context.agent_family,
                user_id=context.user_id,
            )
        return Scope(
            level=ScopeLevel.PROJECT if context.workspace else ScopeLevel.GLOBAL,
            workspace=context.workspace,
            repo=context.repo,
            agent_family=context.agent_family,
            organization=context.organization,
            user_id=context.user_id,
        )


class LifecycleNormalizer:
    def normalize(self, text: str, context: NormalizationContext) -> Lifecycle:
        lower = text.lower()
        now = context.current_time()
        if _is_per_turn_text(lower):
            return Lifecycle(
                type=LifecycleType.IMMEDIATE,
                effective_from=now,
                original_text="per-turn",
            )
        if "this week" in lower:
            days_until_sunday = 6 - now.weekday()
            expires_date = now.date() + timedelta(days=days_until_sunday)
            expires_at = datetime.combine(expires_date, time(23, 59, 59), tzinfo=now.tzinfo)
            return Lifecycle(
                type=LifecycleType.BOUNDED_TIME,
                effective_from=now,
                expires_at=expires_at,
                original_text="this week",
            )
        if "today" in lower:
            expires_at = datetime.combine(now.date(), time(23, 59, 59), tzinfo=now.tzinfo)
            return Lifecycle(
                type=LifecycleType.BOUNDED_TIME,
                effective_from=now,
                expires_at=expires_at,
                original_text="today",
            )
        if "this session" in lower or "current session" in lower:
            return Lifecycle(
                type=LifecycleType.BOUNDED_SESSION,
                effective_from=now,
                trigger_event="session_end",
                original_text="this session",
            )
        if "this task" in lower or "current task" in lower:
            return Lifecycle(
                type=LifecycleType.BOUNDED_TASK,
                effective_from=now,
                trigger_event="task_complete",
                original_text="this task",
            )
        if "until revoked" in lower or "from now on" in lower or "always" in lower:
            return Lifecycle(
                type=LifecycleType.UNTIL_REVOKED,
                effective_from=now,
                until_revoked=True,
                original_text="until revoked",
            )
        until_match = re.search(r"until\s+([A-Za-z0-9 ,:-]+)", text, re.I)
        if until_match:
            return Lifecycle(
                type=LifecycleType.CONDITIONAL,
                effective_from=now,
                trigger_event=until_match.group(1).strip(),
                original_text=until_match.group(0),
            )
        return Lifecycle(type=LifecycleType.IMMEDIATE, effective_from=now)


def _is_per_turn_text(lower: str) -> bool:
    markers = (
        "this answer",
        "this reply",
        "this response",
        "this message",
        "this turn",
        "current answer",
        "current reply",
        "current response",
        "current message",
        "current turn",
        "in your answer",
        "in this answer",
        "in your reply",
        "in this reply",
    )
    return any(marker in lower for marker in markers)


def _selected_bare_file_target(text: str, pattern: re.Pattern[str]) -> str | None:
    matches = list(pattern.finditer(text))
    if not matches:
        return None
    trigger = re.search(r"\b(?:do not|don't|never|must not)\b", text, flags=re.I)
    if trigger is None:
        return matches[0].group(0).rstrip(".,;:")
    after_trigger = [match for match in matches if match.start() >= trigger.start()]
    return (after_trigger[0] if after_trigger else matches[0]).group(0).rstrip(".,;:")
