from __future__ import annotations

import difflib
import hashlib
import os
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol
from zoneinfo import ZoneInfo

from memory_as_contracts.extractor import ExtractionContext
from memory_as_contracts.gate import ActionGate, ExcludedActionPattern, GateResult
from memory_as_contracts.models import (
    ActionSignature,
    AvailableAction,
    Contract,
    GateDecisionType,
    SourceKind,
    SourceSnapshot,
)
from memory_as_contracts.normalizers import NormalizationContext
from memory_as_contracts.resolver import ConflictResolver
from memory_as_contracts.retrieval import (
    DEFAULT_PROMPT_TOKEN_BUDGET,
    PromptIntakeRetriever,
    PromptRetrievalContext,
)
from memory_as_contracts.signatures import (
    ActionSignatureBuilder,
    SignatureContext,
    coding_available_actions,
)
from memory_as_contracts.store import ContractStore
from memory_as_contracts.tool_capsules import (
    ToolCapabilityCapsule,
    render_tool_capsule_system_prompt,
)


class ColdStartExtractor(Protocol):
    def extract_cold_start_source(
        self,
        *,
        text: str,
        source_kind: SourceKind,
        context: ExtractionContext,
        path: str | None = None,
        fingerprint: str | None = None,
    ) -> list[Contract]:
        ...


@dataclass(frozen=True)
class AdapterContext:
    workspace: str
    repo: str | None = None
    branch: str | None = None
    session_id: str = "session"
    turn_id: str | None = None
    task_id: str | None = None
    user_id: str | None = None
    timezone: str = "UTC"
    now: datetime | None = None
    cwd: str | None = None
    conversation_id: str | None = None
    organization: str | None = None

    def workspace_path(self) -> Path:
        return Path(self.workspace).expanduser().resolve(strict=False)

    def cwd_path(self) -> Path:
        return Path(self.cwd or self.workspace).expanduser().resolve(strict=False)

    def current_time(self) -> datetime:
        zone = ZoneInfo(self.timezone)
        if self.now is None:
            return datetime.now(zone)
        if self.now.tzinfo is None:
            return self.now.replace(tzinfo=zone)
        return self.now.astimezone(zone)


@dataclass(frozen=True)
class MemorySourceSpec:
    source_key: str
    path: Path
    source_kind: SourceKind
    scope_label: str
    agent_name: str


@dataclass(frozen=True)
class ChangedSource:
    spec: MemorySourceSpec
    old_fingerprint: str | None
    new_fingerprint: str
    unified_diff: str
    new_content: str


@dataclass(frozen=True)
class AdapterResult:
    extracted_contracts: list[Contract] = field(default_factory=list)
    snapshots_updated: list[SourceSnapshot] = field(default_factory=list)
    prompt_text: str = ""
    gate_result: GateResult | None = None


class BaseAdapter:
    agent_name = "base"
    host = "base"
    exclude_actions: tuple[ExcludedActionPattern, ...] = ()
    always_on_tool_capsules: tuple[ToolCapabilityCapsule, ...] = ()
    prompt_token_budget = DEFAULT_PROMPT_TOKEN_BUDGET

    def __init__(
        self,
        *,
        signature_builder: ActionSignatureBuilder | None = None,
        available_actions: Sequence[AvailableAction] | None = None,
        exclude_actions: Sequence[ExcludedActionPattern] | None = None,
        conflict_resolver_factory: Callable[[ContractStore], ConflictResolver] | None = None,
    ) -> None:
        self.signature_builder = signature_builder or ActionSignatureBuilder()
        self._available_actions = list(available_actions) if available_actions is not None else None
        self._conflict_resolver_factory = conflict_resolver_factory
        if exclude_actions is not None:
            self.exclude_actions = tuple(exclude_actions)

    def available_actions(self) -> list[AvailableAction]:
        if self._available_actions is not None:
            return list(self._available_actions)
        return coding_available_actions()

    def tool_capsules(self) -> list[ToolCapabilityCapsule]:
        return list(self.always_on_tool_capsules)

    def tool_capsule_system_prompt(self) -> str | None:
        return render_tool_capsule_system_prompt(
            agent_name=self.agent_name,
            capsules=self.tool_capsules(),
        )

    def discover_sources(self, context: AdapterContext) -> list[MemorySourceSpec]:
        raise NotImplementedError

    def cold_start_import(
        self,
        store: ContractStore,
        extractor: ColdStartExtractor,
        context: AdapterContext,
    ) -> list[Contract]:
        contracts: list[Contract] = []
        for spec in self.discover_sources(context):
            content = _read_text(spec.path)
            fingerprint = _fingerprint(content)
            extracted = extractor.extract_cold_start_source(
                text=self._cold_start_source_text(spec, content),
                source_kind=spec.source_kind,
                context=self._extraction_context(context),
                path=str(spec.path),
                fingerprint=fingerprint,
            )
            resolved = self._resolve_and_store(store, extracted)
            store.add_source_snapshot(self._snapshot(spec, content, fingerprint, context))
            contracts.extend(resolved)
        return contracts

    def refresh_changed_sources(
        self,
        store: ContractStore,
        extractor: ColdStartExtractor,
        context: AdapterContext,
    ) -> list[Contract]:
        contracts: list[Contract] = []
        snapshots = {snapshot.source_key: snapshot for snapshot in store.list_source_snapshots()}
        for spec in self.discover_sources(context):
            content = _read_text(spec.path)
            fingerprint = _fingerprint(content)
            previous = snapshots.get(spec.source_key)
            if previous is not None and previous.fingerprint == fingerprint:
                continue
            changed = ChangedSource(
                spec=spec,
                old_fingerprint=previous.fingerprint if previous else None,
                new_fingerprint=fingerprint,
                unified_diff=_unified_diff(previous.content if previous else "", content, spec.path),
                new_content=content,
            )
            extracted = extractor.extract_cold_start_source(
                text=self._changed_source_text(changed),
                source_kind=spec.source_kind,
                context=self._extraction_context(context),
                path=str(spec.path),
                fingerprint=fingerprint,
            )
            resolved = self._resolve_and_store(store, extracted)
            store.add_source_snapshot(self._snapshot(spec, content, fingerprint, context))
            contracts.extend(resolved)
        return contracts

    def build_prompt_context(
        self,
        user_turn: str,
        context: AdapterContext,
    ) -> PromptRetrievalContext:
        return PromptRetrievalContext(
            host=self.host,
            agent_family=self.agent_name,
            session_id=context.session_id,
            conversation_id=context.conversation_id,
            turn_id=context.turn_id,
            task_id=context.task_id,
            user_id=context.user_id,
            workspace=str(context.workspace_path()),
            repo=context.repo,
            branch=context.branch,
            organization=context.organization,
            timezone=context.timezone,
            now=context.current_time(),
            user_turn=user_turn,
        )

    def render_prompt_context(
        self,
        store: ContractStore,
        user_turn: str,
        context: AdapterContext,
    ) -> str:
        retriever = PromptIntakeRetriever(store)
        prompt_context = self.build_prompt_context(user_turn, context)
        packets = retriever.retrieve(prompt_context)
        return retriever.render_prompt_text(packets, token_budget=self.prompt_token_budget)

    def build_action_signature(self, event: Mapping[str, Any] | Any, context: AdapterContext) -> ActionSignature:
        tool_name, raw_arguments, intent = self._extract_tool_call(event)
        return self.signature_builder.build(
            tool_name=tool_name,
            raw_arguments=raw_arguments,
            intent=intent,
            context=SignatureContext(
                host=self.host,
                agent_family=self.agent_name,
                session_id=str(_event_value(event, "session_id", context.session_id)),
                conversation_id=context.conversation_id,
                turn_id=str(_event_value(event, "turn_id", context.turn_id))
                if _event_value(event, "turn_id", context.turn_id) is not None
                else None,
                task_id=context.task_id,
                user_id=context.user_id,
                cwd=str(context.cwd_path()),
                repo=context.repo,
                branch=context.branch,
                timezone=context.timezone,
                now=context.current_time(),
                available_actions=self.available_actions(),
            ),
        )

    def gate_event(
        self,
        store: ContractStore,
        event: Mapping[str, Any] | Any,
        context: AdapterContext,
    ) -> dict[str, Any]:
        signature = self.build_action_signature(event, context)
        result = ActionGate(store, exclude_actions=self.exclude_actions).gate(signature)
        return self._format_gate_payload(result)

    def hook_config_snippet(self) -> dict[str, Any] | str:
        raise NotImplementedError

    def _extract_tool_call(self, event: Mapping[str, Any] | Any) -> tuple[str, dict[str, Any], str]:
        tool_name = str(_event_value(event, "tool_name", _event_value(event, "name", "exec")))
        raw_arguments = _event_value(event, "tool_input", _event_value(event, "arguments", {}))
        if not isinstance(raw_arguments, dict):
            raw_arguments = {"value": raw_arguments}
        intent = str(_event_value(event, "intent", ""))
        return _canonical_tool_call(tool_name, raw_arguments), canonical_raw_arguments(tool_name, raw_arguments), intent

    def _format_gate_payload(self, result: GateResult) -> dict[str, Any]:
        payload = _receipt_summary(result)
        if result.decision.decision == GateDecisionType.BLOCK:
            return {"decision": "block", "reason": result.decision.reason, "mac": payload}
        return {"decision": "allow", "mac": payload}

    def _resolve_and_store(
        self,
        store: ContractStore,
        contracts: list[Contract],
    ) -> list[Contract]:
        if not contracts:
            return []
        resolver = (
            self._conflict_resolver_factory(store)
            if self._conflict_resolver_factory is not None
            else ConflictResolver(store)
        )
        return [result.contract for result in resolver.insert_batch(contracts)]

    def _cold_start_source_text(self, spec: MemorySourceSpec, content: str) -> str:
        return (
            f"Agent: {self.agent_name}\n"
            f"Source kind: {spec.source_kind.value}\n"
            f"Source path: {spec.path}\n"
            f"Scope label: {spec.scope_label}\n\n"
            f"{content}"
        )

    def _changed_source_text(self, changed: ChangedSource) -> str:
        return (
            f"Agent: {self.agent_name}\n"
            f"Source kind: {changed.spec.source_kind.value}\n"
            f"Source path: {changed.spec.path}\n"
            f"Scope label: {changed.spec.scope_label}\n"
            f"Old fingerprint: {changed.old_fingerprint or '<new source>'}\n"
            f"New fingerprint: {changed.new_fingerprint}\n\n"
            "Extract only durable contracts introduced or changed by this diff.\n"
            "Unified diff:\n"
            f"{changed.unified_diff}"
        )

    def _extraction_context(self, context: AdapterContext) -> ExtractionContext:
        return ExtractionContext(
            normalization=NormalizationContext(
                workspace=str(context.workspace_path()),
                repo=context.repo,
                task=context.task_id,
                agent_family=[self.agent_name],
                organization=context.organization,
                user_id=context.user_id,
                timezone=context.timezone,
                now=context.current_time(),
            ),
            conversation_id=context.conversation_id,
            turn_id=context.turn_id,
            tool_capsule_system_prompt=self.tool_capsule_system_prompt(),
        )

    def _snapshot(
        self,
        spec: MemorySourceSpec,
        content: str,
        fingerprint: str,
        context: AdapterContext,
    ) -> SourceSnapshot:
        return SourceSnapshot(
            source_key=spec.source_key,
            adapter=self.agent_name,
            path=str(spec.path),
            workspace=str(context.workspace_path()),
            source_kind=spec.source_kind,
            fingerprint=fingerprint,
            content=content,
            observed_at=context.current_time(),
        )


def source_spec(
    *,
    agent_name: str,
    path: Path | str,
    source_kind: SourceKind,
    scope_label: str,
) -> MemorySourceSpec | None:
    resolved = Path(path).expanduser().resolve(strict=False)
    if not resolved.exists() or not resolved.is_file():
        return None
    source_key = f"{agent_name}:{source_kind.value}:{resolved}"
    return MemorySourceSpec(
        source_key=source_key,
        path=resolved,
        source_kind=source_kind,
        scope_label=scope_label,
        agent_name=agent_name,
    )


def dedupe_specs(specs: Sequence[MemorySourceSpec | None]) -> list[MemorySourceSpec]:
    seen: set[str] = set()
    result: list[MemorySourceSpec] = []
    for spec in specs:
        if spec is None or spec.source_key in seen:
            continue
        seen.add(spec.source_key)
        result.append(spec)
    return result


def ancestor_dirs(root: Path, cwd: Path) -> list[Path]:
    root = root.resolve(strict=False)
    cwd = cwd.resolve(strict=False)
    try:
        relative = cwd.relative_to(root)
    except ValueError:
        return [root]
    dirs = [root]
    current = root
    for part in relative.parts:
        current = current / part
        dirs.append(current)
    return dirs


def configured_filenames(env_name: str) -> tuple[str, ...]:
    value = os.environ.get(env_name, "")
    return tuple(item.strip() for item in value.split(",") if item.strip())


def _canonical_tool_call(tool_name: str, raw_arguments: dict[str, Any]) -> str:
    lower = tool_name.lower()
    if lower in {"bash", "shell", "exec", "terminal", "run_command"}:
        return "exec"
    if lower in {"read", "read_file", "fileread", "file.read"}:
        return "file.read"
    if lower in {"write", "edit", "multiedit", "apply_patch", "filewrite", "file.write"}:
        return "file.write"
    if lower in {"delete", "remove", "file.delete"}:
        return "file.delete"
    if lower in {"websearch", "web_search", "web.search", "search"}:
        return "web.search"
    if lower in {"send_message", "message_send", "message.send", "notify", "slack"}:
        return "message.send"
    if lower in {"send_email", "email_send", "email.send"}:
        return "email.send"
    if raw_arguments.get("cmd") or raw_arguments.get("command"):
        return "exec"
    return tool_name


def canonical_raw_arguments(tool_name: str, raw_arguments: Mapping[str, Any]) -> dict[str, Any]:
    args = dict(raw_arguments)
    canonical_tool = _canonical_tool_call(tool_name, args)
    if canonical_tool == "exec":
        command = args.get("cmd") or args.get("command") or args.get("script") or ""
        return {
            "cmd": str(command),
            "host_tool_name": tool_name,
            "host_arguments": args,
        }
    if canonical_tool.startswith("file."):
        path = args.get("path") or args.get("file_path") or args.get("filename")
        if path is not None:
            args["path"] = str(path)
    if canonical_tool in {"message.send", "email.send"}:
        channel = args.get("channel") or args.get("to") or args.get("recipient")
        if channel is not None:
            args["target"] = str(channel)
    return args


def _event_value(event: Mapping[str, Any] | Any, key: str, default: Any = None) -> Any:
    if isinstance(event, Mapping):
        return event.get(key, default)
    return getattr(event, key, default)


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def _fingerprint(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _unified_diff(old: str, new: str, path: Path) -> str:
    diff = difflib.unified_diff(
        old.splitlines(keepends=True),
        new.splitlines(keepends=True),
        fromfile=f"{path}:snapshot",
        tofile=str(path),
        lineterm="",
    )
    return "".join(diff)


def _receipt_summary(result: GateResult) -> dict[str, Any]:
    return {
        "receipt_id": result.receipt.id,
        "signature_id": result.receipt.signature_id,
        "decision": result.decision.decision.value,
        "reason": result.decision.reason,
        "contracts_used": result.decision.contracts_used,
        "edges_applied": result.decision.edges_applied,
        "match_outcome": result.decision.match_outcome.value
        if result.decision.match_outcome is not None
        else None,
    }
