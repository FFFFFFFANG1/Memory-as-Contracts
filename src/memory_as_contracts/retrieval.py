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
from memory_as_contracts.policy_ir import policy_ir_safety
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
    trigger_label: str
    requirement_label: str
    effect_label: str
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
        contracts = self.store.list_contracts(
            [ContractStatus.ACTIVE, ContractStatus.PENDING_CONFLICT],
            include_expired_status=False,
        )

        preferences: list[Contract] = []
        global_rules: list[Contract] = []
        local_rules: list[Contract] = []
        final_response_rules: list[Contract] = []
        for contract in contracts:
            if not _lifecycle_matches(contract, prompt_context):
                continue
            if contract.kind == ContractKind.PREFERENCE:
                if include_soft_preferences and _prompt_scope_matches(
                    contract.scope,
                    prompt_context,
                    query_text,
                ):
                    preferences.append(contract)
                continue
            if _is_response_stage_contract(contract):
                if _prompt_scope_matches(
                    contract.scope,
                    prompt_context,
                    query_text,
                ):
                    final_response_rules.append(contract)
                continue
            if contract.scope.level in {ScopeLevel.GLOBAL, ScopeLevel.SESSION, ScopeLevel.WORKSPACE}:
                if _prompt_scope_matches(
                    contract.scope,
                    prompt_context,
                    query_text,
                ):
                    global_rules.append(contract)
                continue
            if _prompt_scope_matches(
                contract.scope,
                prompt_context,
                query_text,
            ):
                local_rules.append(contract)

        preferences.sort(key=_default_rank, reverse=True)
        global_rules.sort(key=lambda item: (_text_score(item, query_text), _default_rank(item)), reverse=True)
        local_rules.sort(key=lambda item: (_text_score(item, query_text), _default_rank(item)), reverse=True)
        final_response_rules.sort(key=lambda item: (_text_score(item, query_text), _default_rank(item)), reverse=True)

        packets = [
            self._packet(contract, "preference", "ambient scope match")
            for contract in preferences[:preference_limit]
        ]
        packets.extend(
            self._packet(contract, "global-rule", "ambient scope match")
            for contract in global_rules[:global_limit]
        )
        packets.extend(
            self._packet(contract, "final-checklist", "response-stage active contract")
            for contract in final_response_rules[:global_limit]
        )
        packets.extend(
            self._packet(
                contract,
                "local-reminder",
                _target_reason(
                    contract.semantics,
                    [],
                    [],
                    set(),
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
            scope_label=_operational_scope_label(contract),
            lifecycle_label=_lifecycle_label(contract),
            inclusion_reason=reason,
            trigger_label=_trigger_label(contract),
            requirement_label=_requirement_label(contract),
            effect_label=_effect_label(contract),
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
    query_text: str,
) -> bool:
    if scope.user_id and context.user_id and scope.user_id != context.user_id:
        return False
    if scope.workspace and context.workspace and scope.workspace != context.workspace:
        return False
    if scope.workspace and not context.workspace:
        return False

    if scope.level == ScopeLevel.GLOBAL:
        return True
    if scope.level == ScopeLevel.SESSION:
        return True
    if scope.level == ScopeLevel.WORKSPACE:
        return bool(scope.workspace and context.workspace and scope.workspace == context.workspace)
    if scope.level == ScopeLevel.PATH:
        if scope.workspace and context.workspace and scope.workspace != context.workspace:
            return False
        targets = _target_paths(context, query_text)
        return bool(scope.path and any(_path_matches(target, scope.path) for target in targets))
    query_lower = query_text.lower()
    if scope.level == ScopeLevel.PROJECT:
        project = scope.project or scope.workspace
        if not project:
            return False
        return project.lower() in query_lower
    if scope.level == ScopeLevel.MODULE:
        project = scope.project or scope.workspace
        return bool(
            scope.module
            and scope.module.lower() in query_lower
            and (not project or project.lower() in query_lower)
        )
    return False


def _is_response_stage_contract(contract: Contract) -> bool:
    if not isinstance(contract.policy_ir, dict):
        return False
    return policy_ir_safety(contract).effective_phase == "response"


def _is_global_prompt_scope(scope: Scope) -> bool:
    return scope.level in {ScopeLevel.GLOBAL, ScopeLevel.SESSION}


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
    if scope.project:
        parts.append(f"project={scope.project}")
    if scope.module:
        parts.append(f"module={scope.module}")
    if scope.path:
        parts.append(f"path={scope.path}")
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
        "final-checklist": "Before final response:",
        "local-reminder": "Local reminders:",
    }
    return labels.get(channel, f"{channel}:")


def _packet_line(packet: PromptContractPacket) -> str:
    lines = [f"- {packet.id}: {packet.text}"]
    lines.append(f"  scope: {packet.scope_label}")
    lines.append(f"  trigger: {packet.trigger_label}")
    lines.append(f"  requirement: {packet.requirement_label}")
    effect = packet.effect_label
    if packet.conflict_status:
        effect = f"{effect}; conflict pending"
    lines.append(f"  effect: {effect}")
    return "\n".join(lines)


def _policy_dict(contract: Contract) -> dict | None:
    return contract.policy_ir if isinstance(contract.policy_ir, dict) else None


def _operational_scope_label(contract: Contract) -> str:
    policy = _policy_dict(contract) or {}
    policy_scope = policy.get("scope") if isinstance(policy.get("scope"), dict) else {}
    path = policy_scope.get("path") or contract.scope.path
    if path:
        return f"path={path}"
    level = str(policy_scope.get("level") or contract.scope.level.value)
    if level == ScopeLevel.WORKSPACE.value:
        return f"workspace={contract.scope.workspace}" if contract.scope.workspace else "workspace"
    if level == ScopeLevel.SESSION.value:
        return "session"
    if level == ScopeLevel.GLOBAL.value:
        return "global"
    if level == ScopeLevel.PATH.value:
        return "path"
    return _scope_label(contract.scope)


def _trigger_label(contract: Contract) -> str:
    policy = _policy_dict(contract) or {}
    target = policy.get("target") if isinstance(policy.get("target"), dict) else {}
    phase = str(target.get("phase") or "pre")
    tools = _as_text_list(target.get("tools"))
    if target.get("tool"):
        tools.insert(0, str(target["tool"]))
    action_families = _as_text_list(target.get("action_families"))
    if target.get("action_family"):
        action_families.insert(0, str(target["action_family"]))
    tools = _dedupe_preserve_order(tools)
    action_families = _dedupe_preserve_order(action_families)

    if phase == "response":
        return "before final response"
    if tools:
        prefix = "after" if phase == "post" else "before"
        return f"{prefix} tool {_join_limited(tools)}"
    if action_families:
        prefix = "after" if phase == "post" else "before"
        return f"{prefix} action {_join_limited(action_families)}"
    if contract.semantics.actions:
        return f"before action {_join_limited(list(contract.semantics.actions))}"
    if contract.semantics.tags:
        return f"before action tagged {_join_limited(list(contract.semantics.tags))}"
    return "before matching action"


def _requirement_label(contract: Contract) -> str:
    policy = _policy_dict(contract) or {}
    obligation = policy.get("obligation") if isinstance(policy.get("obligation"), dict) else {}
    kind = str(obligation.get("kind") or "").strip()
    monitor = obligation.get("monitor") if isinstance(obligation.get("monitor"), dict) else None
    predicate = obligation.get("predicate") if isinstance(obligation.get("predicate"), dict) else None
    if kind in {"prior_action", "required_tool_usage", "required_tool_evidence"}:
        return f"prior action matching {_monitor_label(monitor)}"
    if kind in {"action_count", "specific_tool_count", "tool_count", "interaction_turn_count"}:
        op = str(obligation.get("op") or _predicate_op(predicate) or "count")
        value = obligation.get("value")
        if value is None and isinstance(predicate, dict):
            value = predicate.get("value")
        return f"action count {op} {value} for {_monitor_label(monitor)}"
    if kind == "same_step":
        op = str(obligation.get("op") or "gte")
        value = obligation.get("value")
        return f"same-step actions {op} {value} matching {_monitor_label(monitor)}"
    if kind in {"response", "response_format", "response_content", "response_length"}:
        return _response_requirement_label(predicate)
    if kind in {"current_action", "path_access"}:
        return f"current action matches {_predicate_label(predicate)}"
    if kind == "sequence":
        return f"action sequence includes {_monitor_label(monitor)}"
    if kind:
        return f"{kind} obligation"
    if contract.semantics.actions or contract.semantics.tags:
        return _target_reason(contract.semantics, [], [], set())
    return "satisfy constraint text"


def _effect_label(contract: Contract) -> str:
    policy = _policy_dict(contract) or {}
    effect = str(policy.get("effect") or contract.effect.value)
    if effect == "deny":
        return "block matching action"
    if effect == "allow":
        return "allow when matched"
    return "block until satisfied"


def _monitor_label(monitor: dict | None) -> str:
    if not isinstance(monitor, dict):
        return "action log"
    where = monitor.get("where") if isinstance(monitor.get("where"), dict) else None
    aggregate = monitor.get("aggregate")
    base = _predicate_label(where) if where else str(monitor.get("source") or "action log")
    extras: list[str] = []
    if aggregate and aggregate != "exists":
        extras.append(f"aggregate={aggregate}")
    if monitor.get("distinct_by"):
        extras.append(f"distinct_by={monitor['distinct_by']}")
    if monitor.get("group_by"):
        extras.append(f"group_by={monitor['group_by']}")
    if extras:
        return f"{base}; " + "; ".join(extras)
    return base


def _response_requirement_label(predicate: dict | None) -> str:
    if not isinstance(predicate, dict):
        return "final response satisfies constraint text"
    op = str(predicate.get("op") or "")
    value = predicate.get("value")
    if op == "json_object":
        keys = value.get("required_keys") if isinstance(value, dict) else None
        if keys:
            return f"final response is JSON with keys {_join_limited(_as_text_list(keys))}"
        return "final response is a JSON object"
    if op in {"word_count_lte", "word_count_gte", "word_count_between", "char_count_lte", "char_count_gte", "char_count_between"}:
        return f"final response {op} {value}"
    if op in {"startswith", "endswith", "contains", "not_contains"}:
        return f"final response {op} {_short_value(value)}"
    if op == "regex":
        return "final response satisfies response-pattern constraint"
    if op == "not_regex":
        return "final response avoids forbidden response pattern"
    return f"final response matches {_predicate_label(predicate)}"


def _predicate_label(predicate: dict | None) -> str:
    if not isinstance(predicate, dict):
        return "predicate"
    op = str(predicate.get("op") or "")
    if op in {"all", "any"}:
        children = predicate.get(op)
        if isinstance(children, list) and children:
            return f"{op}(" + "; ".join(_predicate_label(item) for item in children[:3]) + ")"
        return op
    if op == "not":
        return "not(" + _predicate_label(predicate.get("not")) + ")"
    field = predicate.get("field")
    value = predicate.get("value")
    if field:
        value_text = _short_value(value)
        return f"{field} {op}" + (f" {value_text}" if value_text else "")
    value_text = _short_value(value)
    return f"{op}" + (f" {value_text}" if value_text else "")


def _predicate_op(predicate: dict | None) -> str | None:
    if not isinstance(predicate, dict):
        return None
    op = predicate.get("op")
    return str(op) if op else None


def _short_value(value: object, *, max_chars: int = 96) -> str:
    if isinstance(value, list):
        text = "[" + ", ".join(str(item) for item in value[:5])
        if len(value) > 5:
            text += ", ..."
        text += "]"
    elif isinstance(value, dict):
        text = ", ".join(f"{key}={value[key]}" for key in list(value)[:5])
        if len(value) > 5:
            text += ", ..."
        text = "{" + text + "}"
    else:
        text = "" if value is None else str(value)
    text = " ".join(text.split())
    if len(text) > max_chars:
        return text[: max_chars - 3] + "..."
    return text


def _as_text_list(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if str(item)]
    if value is None:
        return []
    return [str(value)]


def _dedupe_preserve_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def _join_limited(values: list[str], *, limit: int = 4) -> str:
    values = _dedupe_preserve_order(values)
    if len(values) <= limit:
        return ", ".join(values)
    return ", ".join(values[:limit]) + ", ..."


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
