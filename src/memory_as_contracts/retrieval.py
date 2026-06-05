from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from fnmatch import fnmatch
from zoneinfo import ZoneInfo

from memory_as_contracts.matching import lifecycle_is_active
from memory_as_contracts.models import (
    ActionSignature,
    Contract,
    ContractKind,
    ContractStatus,
    RuleSemantics,
    Scope,
    ScopeLevel,
    Strength,
)
from memory_as_contracts.store import ContractStore


DEFAULT_PROMPT_TOKEN_BUDGET = 1500
DEFAULT_LOCAL_REMINDER_LIMIT = 3


@dataclass(frozen=True)
class PromptRetrievalContext:
    """Adapter-provided prompt-intake context before any concrete action exists."""

    host: str = "codex"
    agent_family: str = "codex"
    session_id: str = "session"
    conversation_id: str | None = None
    turn_id: str | None = None
    task_id: str | None = None
    user_id: str | None = None
    workspace: str | None = None
    repo: str | None = None
    branch: str | None = None
    organization: str | None = None
    timezone: str = "UTC"
    now: datetime | None = None
    user_turn: str = ""
    target_paths: list[str] = field(default_factory=list)
    target_components: list[str] = field(default_factory=list)

    def current_time(self) -> datetime:
        zone = ZoneInfo(self.timezone)
        if self.now is None:
            return datetime.now(zone)
        if self.now.tzinfo is None:
            return self.now.replace(tzinfo=zone)
        return self.now.astimezone(zone)

    @classmethod
    def from_signature(
        cls,
        signature: ActionSignature,
        *,
        user_turn: str = "",
    ) -> PromptRetrievalContext:
        return cls(
            host=signature.host,
            agent_family=signature.agent_family,
            session_id=signature.session.session_id,
            conversation_id=signature.session.conversation_id,
            turn_id=signature.session.turn_id,
            task_id=signature.session.task_id,
            user_id=signature.session.user_id,
            workspace=signature.workspace.cwd,
            repo=signature.workspace.repo,
            branch=signature.workspace.branch,
            timezone=signature.time.timezone,
            now=signature.time.now,
            user_turn=user_turn or signature.intent,
            target_paths=signature.targets,
        )


@dataclass(frozen=True)
class PromptContractPacket:
    id: str
    text: str
    status: str
    source_kind: str
    channel: str
    scope_label: str
    lifecycle_label: str
    inclusion_reason: str
    conflict_status: str | None = None


class PromptIntakeRetriever:
    """Compact contract retrieval for plan-time prompt shaping."""

    def __init__(self, store: ContractStore) -> None:
        self.store = store

    def retrieve(
        self,
        context: PromptRetrievalContext | ActionSignature,
        *,
        query: str | None = None,
        preference_limit: int = 5,
        global_limit: int = 5,
        local_reminder_limit: int = DEFAULT_LOCAL_REMINDER_LIMIT,
        include_soft_preferences: bool = True,
    ) -> list[PromptContractPacket]:
        prompt_context = _coerce_prompt_context(context, query=query)
        query_text = query if query is not None else prompt_context.user_turn
        target_paths = _target_paths(prompt_context, query_text)
        target_components = _target_components(prompt_context, query_text)
        action_hints = _action_hints(query_text)
        contracts = self.store.list_contracts(
            [ContractStatus.ACTIVE, ContractStatus.PENDING_CONFLICT],
            include_expired_status=False,
        )

        preferences: list[Contract] = []
        global_rules: list[Contract] = []
        local_rules: list[Contract] = []
        for contract in contracts:
            if not _lifecycle_matches(contract, prompt_context):
                continue
            if contract.kind == ContractKind.PREFERENCE:
                if include_soft_preferences and _prompt_scope_matches(
                    contract.scope,
                    prompt_context,
                    target_paths,
                    target_components,
                    allow_local_without_target=True,
                ):
                    preferences.append(contract)
                continue
            if _is_global_prompt_scope(contract.scope):
                if _prompt_scope_matches(
                    contract.scope,
                    prompt_context,
                    target_paths,
                    target_components,
                    allow_local_without_target=True,
                ):
                    global_rules.append(contract)
                continue
            if not target_paths and not target_components and not _action_relevant(
                contract.semantics,
                action_hints,
            ):
                continue
            if _prompt_scope_matches(
                contract.scope,
                prompt_context,
                target_paths,
                target_components,
                allow_local_without_target=bool(action_hints),
            ):
                local_rules.append(contract)

        preferences.sort(key=_default_rank, reverse=True)
        global_rules.sort(key=_default_rank, reverse=True)
        local_rules.sort(key=lambda item: (_text_score(item, query_text), _default_rank(item)), reverse=True)

        packets = [
            self._packet(contract, "preference", "ambient scope match")
            for contract in preferences[:preference_limit]
        ]
        packets.extend(
            self._packet(contract, "global-rule", "ambient scope match")
            for contract in global_rules[:global_limit]
        )
        packets.extend(
            self._packet(
                contract,
                "local-reminder",
                _target_reason(
                    contract.semantics,
                    target_paths,
                    target_components,
                    action_hints,
                ),
            )
            for contract in local_rules[:local_reminder_limit]
        )
        return packets

    def render_prompt_text(
        self,
        packets: list[PromptContractPacket],
        *,
        token_budget: int = DEFAULT_PROMPT_TOKEN_BUDGET,
    ) -> str:
        return render_prompt_packets(packets, token_budget=token_budget)

    def _packet(
        self,
        contract: Contract,
        channel: str,
        reason: str,
    ) -> PromptContractPacket:
        return PromptContractPacket(
            id=contract.id,
            text=contract.text,
            status=contract.status.value,
            source_kind=contract.source.kind.value,
            channel=channel,
            scope_label=_scope_label(contract.scope),
            lifecycle_label=_lifecycle_label(contract),
            inclusion_reason=reason,
            conflict_status="pending_conflict"
            if contract.status == ContractStatus.PENDING_CONFLICT
            else None,
        )


def render_prompt_packets(
    packets: list[PromptContractPacket],
    *,
    token_budget: int = DEFAULT_PROMPT_TOKEN_BUDGET,
) -> str:
    if not packets or token_budget <= 0:
        return ""
    lines = ["MAC reminders"]
    used = _estimate_tokens(lines[0])
    current_channel: str | None = None
    included = 0
    for packet in packets:
        if packet.channel != current_channel:
            header = _channel_header(packet.channel)
            header_tokens = _estimate_tokens(header)
            if used + header_tokens > token_budget:
                break
            lines.append(header)
            used += header_tokens
            current_channel = packet.channel
        line = _packet_line(packet)
        line_tokens = _estimate_tokens(line)
        if used + line_tokens > token_budget:
            break
        lines.append(line)
        used += line_tokens
        included += 1
    if included == 0:
        return ""
    return "\n".join(lines)


def _coerce_prompt_context(
    context: PromptRetrievalContext | ActionSignature,
    *,
    query: str | None,
) -> PromptRetrievalContext:
    if isinstance(context, PromptRetrievalContext):
        return context
    return PromptRetrievalContext.from_signature(context, user_turn=query or context.intent)


def _lifecycle_matches(contract: Contract, context: PromptRetrievalContext) -> bool:
    fake_signature = _minimal_signature(context)
    return lifecycle_is_active(contract.lifecycle, fake_signature)


def _minimal_signature(context: PromptRetrievalContext) -> ActionSignature:
    return ActionSignature(
        host=context.host,
        agent_family=context.agent_family,
        session={
            "session_id": context.session_id,
            "conversation_id": context.conversation_id,
            "turn_id": context.turn_id,
            "task_id": context.task_id,
            "user_id": context.user_id,
        },
        time={"now": context.current_time(), "timezone": context.timezone},
        workspace={
            "cwd": context.workspace or "",
            "repo": context.repo,
            "branch": context.branch,
        },
        tool={"name": "prompt-intake", "raw_arguments": {}},
        host_action="prompt.intake",
    )


def _prompt_scope_matches(
    scope: Scope,
    context: PromptRetrievalContext,
    target_paths: list[str],
    target_components: list[str],
    *,
    allow_local_without_target: bool,
) -> bool:
    if scope.agent_family and context.agent_family not in scope.agent_family:
        return False
    if scope.user_id and context.user_id and scope.user_id != context.user_id:
        return False
    if scope.organization and context.organization and scope.organization != context.organization:
        return False
    if scope.workspace and context.workspace and scope.workspace != context.workspace:
        return False
    if scope.workspace and not context.workspace:
        return False
    if scope.repo and context.repo and scope.repo != context.repo:
        return False
    if scope.repo and not context.repo:
        return False
    if scope.task and context.task_id and scope.task != context.task_id:
        return False
    if scope.task and not context.task_id:
        return False

    if scope.level == ScopeLevel.GLOBAL:
        return True
    if scope.level == ScopeLevel.ORGANIZATION:
        return bool(scope.organization)
    if scope.level == ScopeLevel.AGENT_FAMILY:
        return context.agent_family in scope.agent_family
    if scope.level == ScopeLevel.SESSION:
        return True
    if scope.level == ScopeLevel.TASK:
        return bool(scope.task and scope.task == context.task_id)
    if scope.level in {ScopeLevel.PROJECT, ScopeLevel.REPO}:
        if not allow_local_without_target and not (target_paths or target_components):
            return False
        if scope.level == ScopeLevel.REPO and scope.repo and context.repo:
            return scope.repo == context.repo
        return bool(scope.workspace and scope.workspace == context.workspace)
    if scope.level == ScopeLevel.COMPONENT:
        if not target_components:
            return False
        return bool(scope.component and scope.component.lower() in target_components)
    if scope.level == ScopeLevel.PATH:
        return any(_path_matches(target, glob) for target in target_paths for glob in scope.path_globs)
    if scope.level == ScopeLevel.PER_TURN:
        return True
    return False


def _is_global_prompt_scope(scope: Scope) -> bool:
    return scope.level in {
        ScopeLevel.GLOBAL,
        ScopeLevel.ORGANIZATION,
        ScopeLevel.AGENT_FAMILY,
        ScopeLevel.SESSION,
        ScopeLevel.TASK,
    }


BACKTICK_HINT_PATTERN = re.compile(r"`([^`]+)`")
BARE_PATH_HINT_PATTERN = re.compile(
    r"(?<!://)\b(?:[A-Za-z0-9_.-]+/)+(?:[A-Za-z0-9_.{}*?\[\]-]+/?)+"
)
FILE_HINT_PATTERN = re.compile(
    r"\b[A-Za-z0-9_.-]+\.(?:py|js|jsx|ts|tsx|md|json|toml|yaml|yml|txt|rs|go|java|c|cc|cpp|h|css|html|sh)\b"
)
COMPONENT_HINT_PATTERN = re.compile(
    r"(?:component|module|package)\s+`?([A-Za-z0-9_.-]+)`?",
    re.I,
)


def _target_paths(context: PromptRetrievalContext, query: str) -> list[str]:
    targets = [_clean_path_hint(path) for path in context.target_paths]
    consumed_spans: list[tuple[int, int]] = []
    for pattern in (BACKTICK_HINT_PATTERN, BARE_PATH_HINT_PATTERN):
        for match in pattern.finditer(query):
            raw = match.group(1) if match.groups() else match.group(0)
            cleaned = _clean_path_hint(raw)
            if _looks_like_path(cleaned):
                targets.append(cleaned)
                consumed_spans.append(match.span())
    for match in FILE_HINT_PATTERN.finditer(query):
        if any(start <= match.start() and match.end() <= end for start, end in consumed_spans):
            continue
        cleaned = _clean_path_hint(match.group(0))
        if _looks_like_path(cleaned):
            targets.append(cleaned)
    return sorted({target for target in targets if target})


def _target_components(context: PromptRetrievalContext, query: str) -> list[str]:
    components = [component.lower() for component in context.target_components]
    components.extend(match.group(1).lower().rstrip(".,;:") for match in COMPONENT_HINT_PATTERN.finditer(query))
    return sorted({component for component in components if component})


def _action_hints(query: str) -> set[str]:
    lower = query.lower()
    hints: set[str] = set()
    if "git push" in lower or "push" in lower or "publish" in lower:
        hints.update({"git.push", "external_write", "publish_code"})
    if "web search" in lower or "browse" in lower or "online" in lower or "web" in lower:
        hints.update({"web.search", "network_read"})
    if any(token in lower for token in ("send message", "send messages", "slack", "notify", "email")):
        hints.update({"message.send", "email.send", "external_write", "notify_human"})
    if any(token in lower for token in ("edit", "write", "patch", "delete", "touch")):
        hints.update({"file.write", "file.delete", "workspace_write", "source_modification"})
    return hints


def _action_relevant(semantics: RuleSemantics, action_hints: set[str]) -> bool:
    if not action_hints:
        return False
    return bool(
        action_hints.intersection(semantics.actions)
        or action_hints.intersection(semantics.tags)
    )


def _clean_path_hint(value: str) -> str:
    return value.strip().strip("`'\"").rstrip(".,;:")


def _looks_like_path(value: str) -> bool:
    return "/" in value or "*" in value or "." in value


def _path_matches(target: str, glob: str) -> bool:
    target_clean = target.rstrip("/")
    glob_clean = glob.rstrip("/")
    if fnmatch(target_clean, glob) or fnmatch(target_clean + "/sample", glob):
        return True
    glob_prefix = _glob_prefix(glob_clean)
    if glob_prefix and (
        target_clean == glob_prefix
        or target_clean.startswith(glob_prefix + "/")
        or glob_prefix.startswith(target_clean + "/")
    ):
        return True
    return False


def _glob_prefix(glob: str) -> str:
    wildcard = min([index for index in (glob.find("*"), glob.find("?")) if index != -1] or [len(glob)])
    return glob[:wildcard].rstrip("/")


def _target_reason(
    semantics: RuleSemantics,
    target_paths: list[str],
    target_components: list[str],
    action_hints: set[str] | None = None,
) -> str:
    parts: list[str] = []
    if target_paths:
        parts.append("target=" + ",".join(target_paths[:3]))
    if target_components:
        parts.append("component=" + ",".join(target_components[:3]))
    if semantics.actions:
        parts.append("actions=" + ",".join(semantics.actions))
    if semantics.tags:
        parts.append("tags=" + ",".join(semantics.tags))
    if action_hints:
        matching = sorted(
            action_hints.intersection(semantics.actions)
            | action_hints.intersection(semantics.tags)
        )
        if matching:
            parts.append("query-actions=" + ",".join(matching[:3]))
    return "; ".join(parts) if parts else "target hint match"


def _scope_label(scope: Scope) -> str:
    parts = [scope.level.value]
    if scope.workspace:
        parts.append(f"workspace={scope.workspace}")
    if scope.repo:
        parts.append(f"repo={scope.repo}")
    if scope.path_globs:
        parts.append("paths=" + ",".join(scope.path_globs))
    if scope.component:
        parts.append(f"component={scope.component}")
    if scope.task:
        parts.append(f"task={scope.task}")
    if scope.agent_family:
        parts.append("agents=" + ",".join(scope.agent_family))
    return ";".join(parts)


def _lifecycle_label(contract: Contract) -> str:
    lifecycle = contract.lifecycle
    if lifecycle.expires_at is not None:
        return f"{lifecycle.type.value};until={lifecycle.expires_at.isoformat()}"
    if lifecycle.until_revoked:
        return lifecycle.type.value
    return lifecycle.type.value


def _channel_header(channel: str) -> str:
    labels = {
        "preference": "Preferences:",
        "global-rule": "Global rules:",
        "local-reminder": "Local reminders:",
    }
    return labels.get(channel, f"{channel}:")


def _packet_line(packet: PromptContractPacket) -> str:
    conflict = ";conflict=pending" if packet.conflict_status else ""
    return (
        f"- {packet.id} [{packet.source_kind};{packet.status};"
        f"{packet.scope_label};{packet.lifecycle_label}{conflict}] "
        f"{packet.text} ({packet.inclusion_reason})"
    )


def _default_rank(contract: Contract) -> tuple[int, int]:
    strength = {Strength.HARD: 3, Strength.SOFT: 2, Strength.SUGGESTIVE: 1}[contract.strength]
    status = 2 if contract.status == ContractStatus.PENDING_CONFLICT else 1
    return status, strength


def _text_score(contract: Contract, query: str) -> int:
    query_terms = set(re.findall(r"[a-z0-9_./*-]+", query.lower()))
    contract_terms = set(re.findall(r"[a-z0-9_./*-]+", contract.text.lower()))
    return len(query_terms.intersection(contract_terms))


def _estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)
