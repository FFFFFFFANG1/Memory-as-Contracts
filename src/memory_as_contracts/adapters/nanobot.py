from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from memory_as_contracts.adapters.base import (
    AdapterContext,
    BaseAdapter,
    ColdStartExtractor,
    MemorySourceSpec,
    canonical_raw_arguments,
    dedupe_specs,
    source_spec,
)
from memory_as_contracts.gate import ActionGate
from memory_as_contracts.models import ActionSignature, GateDecisionType, SourceKind
from memory_as_contracts.store import ContractStore
from memory_as_contracts.tool_capsules import ToolCapabilityCapsule, object_schema


class NanobotAdapter(BaseAdapter):
    agent_name = "nanobot"
    host = "nanobot"
    always_on_tool_capsules = (
        ToolCapabilityCapsule(
            name="shell",
            description="Runs a shell command in the workspace.",
            input_schema=object_schema(
                required=("command",),
                properties={
                    "command": {"type": "string"},
                    "cwd": {"type": "string"},
                },
            ),
        ),
        ToolCapabilityCapsule(
            name="read",
            description="Reads file content from the workspace.",
            input_schema=object_schema(
                required=("path",),
                properties={
                    "path": {"type": "string"},
                    "limit": {"type": "integer"},
                },
            ),
        ),
        ToolCapabilityCapsule(
            name="write",
            description="Writes content to a workspace file.",
            input_schema=object_schema(
                required=("path", "content"),
                properties={
                    "path": {"type": "string"},
                    "content": {"type": "string"},
                },
            ),
        ),
        ToolCapabilityCapsule(
            name="edit",
            description="Edits a workspace file by replacing text.",
            input_schema=object_schema(
                required=("path", "old_text", "new_text"),
                properties={
                    "path": {"type": "string"},
                    "old_text": {"type": "string"},
                    "new_text": {"type": "string"},
                },
            ),
        ),
        ToolCapabilityCapsule(
            name="web_search",
            description="Searches the web for current information.",
            input_schema=object_schema(
                required=("query",),
                properties={
                    "query": {"type": "string"},
                    "limit": {"type": "integer"},
                },
            ),
        ),
        ToolCapabilityCapsule(
            name="memory_record",
            description="Stores or updates durable agent memory.",
            input_schema=object_schema(
                required=("text",),
                properties={
                    "text": {"type": "string"},
                    "category": {"type": "string"},
                    "source": {"type": "string"},
                },
            ),
        ),
    )

    def discover_sources(self, context: AdapterContext) -> list[MemorySourceSpec]:
        workspace = context.workspace_path()
        specs = [
            source_spec(
                agent_name=self.agent_name,
                path=workspace / "SOUL.md",
                source_kind=SourceKind.USER_PROFILE,
                scope_label="nanobot soul profile",
            ),
            source_spec(
                agent_name=self.agent_name,
                path=workspace / "USER.md",
                source_kind=SourceKind.USER_PROFILE,
                scope_label="nanobot user profile",
            ),
            source_spec(
                agent_name=self.agent_name,
                path=workspace / "memory" / "MEMORY.md",
                source_kind=SourceKind.MEMORY_FILE,
                scope_label="nanobot durable memory",
            ),
            source_spec(
                agent_name=self.agent_name,
                path=workspace / "memory" / "history.jsonl",
                source_kind=SourceKind.MEMORY_FILE,
                scope_label="nanobot lower-authority memory history",
            ),
        ]
        return dedupe_specs(specs)

    def build_action_signature(
        self,
        event: Mapping[str, Any] | Any,
        context: AdapterContext,
    ) -> ActionSignature:
        return super().build_action_signature(event, context)

    def gate_event(
        self,
        store: ContractStore,
        event: Mapping[str, Any] | Any,
        context: AdapterContext,
    ) -> dict[str, Any]:
        signature = self.build_action_signature(event, context)
        result = ActionGate(store, exclude_actions=self.exclude_actions).gate(signature)
        mac_payload = {
            "receipt_id": result.receipt.id,
            "signature_id": result.receipt.signature_id,
            "decision": result.decision.decision.value,
            "reason": result.decision.reason,
            "contracts_used": result.decision.contracts_used,
            "edges_applied": result.decision.edges_applied,
        }
        if result.decision.decision == GateDecisionType.BLOCK:
            return {"decision": "block", "reason": result.decision.reason, "mac": mac_payload}
        return {"decision": "allow", "mac": mac_payload}

    def build_observability_prompt_context(
        self,
        store: ContractStore,
        user_turn: str,
        context: AdapterContext,
    ) -> dict[str, Any]:
        prompt_text = self.render_prompt_context(store, user_turn, context)
        return {"additionalContext": prompt_text} if prompt_text else {}

    def hook_config_snippet(self) -> dict[str, Any]:
        return {
            "function_interface": "memory_as_contracts.adapters.nanobot:gate_nanobot_tool_call",
            "observability_hook": "memory_as_contracts.adapters.nanobot:build_observability_prompt_context",
            "note": (
                "Blocking is a function interface for manual runner insertion. "
                "Step 11 does not claim native automatic Nanobot blocking."
            ),
        }

    def _extract_tool_call(self, event: Mapping[str, Any] | Any) -> tuple[str, dict[str, Any], str]:
        tool_name = _value(event, "tool_name", _value(event, "name", "exec"))
        raw = _value(event, "arguments", _value(event, "args", _value(event, "tool_input", {})))
        if not isinstance(raw, dict):
            raw = {"value": raw}
        canonical = _nanobot_tool_name(str(tool_name), raw)
        return canonical, canonical_raw_arguments(canonical, raw), str(_value(event, "intent", ""))


def gate_nanobot_tool_call(
    store: ContractStore,
    tool_call: Mapping[str, Any] | Any,
    context: AdapterContext,
) -> dict[str, Any]:
    return _ADAPTER.gate_event(store, tool_call, context)


def _nanobot_tool_name(tool_name: str, raw: dict[str, Any]) -> str:
    lower = tool_name.lower()
    if lower in {"bash", "shell", "exec", "run", "command"}:
        return "exec"
    if lower in {"read", "file_read", "file.read"}:
        return "file.read"
    if lower in {"write", "edit", "patch", "file_write", "file.write"}:
        return "file.write"
    if lower in {"delete", "remove", "file_delete", "file.delete"}:
        return "file.delete"
    if lower in {"search", "web_search", "web.search"}:
        return "web.search"
    if lower in {"send_message", "message_send", "message.send", "notify", "slack"}:
        return "message.send"
    if lower in {"send_email", "email_send", "email.send"}:
        return "email.send"
    if raw.get("cmd") or raw.get("command"):
        return "exec"
    return tool_name


def _value(event: Mapping[str, Any] | Any, key: str, default: Any = None) -> Any:
    if isinstance(event, Mapping):
        return event.get(key, default)
    return getattr(event, key, default)


_ADAPTER = NanobotAdapter()


def discover_sources(context: AdapterContext) -> list[MemorySourceSpec]:
    return _ADAPTER.discover_sources(context)


def cold_start_import(
    store: ContractStore,
    extractor: ColdStartExtractor,
    context: AdapterContext,
):
    return _ADAPTER.cold_start_import(store, extractor, context)


def refresh_changed_sources(
    store: ContractStore,
    extractor: ColdStartExtractor,
    context: AdapterContext,
):
    return _ADAPTER.refresh_changed_sources(store, extractor, context)


def build_prompt_context(user_turn: str, context: AdapterContext):
    return _ADAPTER.build_prompt_context(user_turn, context)


def build_action_signature(event: Mapping[str, Any] | Any, context: AdapterContext):
    return _ADAPTER.build_action_signature(event, context)


def gate_event(store: ContractStore, event: Mapping[str, Any] | Any, context: AdapterContext):
    return _ADAPTER.gate_event(store, event, context)


def hook_config_snippet():
    return _ADAPTER.hook_config_snippet()


def build_observability_prompt_context(
    store: ContractStore,
    user_turn: str,
    context: AdapterContext,
):
    return _ADAPTER.build_observability_prompt_context(store, user_turn, context)
