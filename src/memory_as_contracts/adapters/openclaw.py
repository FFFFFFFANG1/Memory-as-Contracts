from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from memory_as_contracts.adapters.base import (
    AdapterContext,
    BaseAdapter,
    ColdStartExtractor,
    MemorySourceSpec,
    dedupe_specs,
    source_spec,
)
from memory_as_contracts.hook_runtime import default_pattern_refiner_factory
from memory_as_contracts.models import ActionSignature, GateDecisionType, SourceKind
from memory_as_contracts.store import ContractStore
from memory_as_contracts.tool_capsules import ToolCapabilityCapsule, object_schema


class OpenClawAdapter(BaseAdapter):
    agent_name = "openclaw"
    host = "openclaw"
    always_on_tool_capsules = (
        ToolCapabilityCapsule(
            name="exec",
            description="Runs a shell command or local process.",
            input_schema=object_schema(
                required=("command",),
                properties={
                    "command": {"type": "string"},
                    "cwd": {"type": "string"},
                    "timeoutMs": {"type": "integer"},
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
                    "offset": {"type": "integer"},
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
                required=("path", "oldString", "newString"),
                properties={
                    "path": {"type": "string"},
                    "oldString": {"type": "string"},
                    "newString": {"type": "string"},
                    "replaceAll": {"type": "boolean"},
                },
            ),
        ),
        ToolCapabilityCapsule(
            name="apply_patch",
            description="Applies a patch to workspace files.",
            input_schema=object_schema(
                required=("patch",),
                properties={"patch": {"type": "string"}},
            ),
        ),
        ToolCapabilityCapsule(
            name="web_search",
            description="Searches the web for current information.",
            input_schema=object_schema(
                required=("query",),
                properties={
                    "query": {"type": "string"},
                    "count": {"type": "integer"},
                },
            ),
        ),
        ToolCapabilityCapsule(
            name="web_fetch",
            description="Fetches readable content from a URL.",
            input_schema=object_schema(
                required=("url",),
                properties={
                    "url": {"type": "string"},
                    "maxChars": {"type": "integer"},
                },
            ),
        ),
        ToolCapabilityCapsule(
            name="message",
            description="Sends or manages messages in an external chat channel.",
            input_schema=object_schema(
                required=("text",),
                properties={
                    "action": {"type": "string"},
                    "to": {"type": "string"},
                    "channel": {"type": "string"},
                    "text": {"type": "string"},
                },
            ),
        ),
        ToolCapabilityCapsule(
            name="memory_search",
            description="Searches stored agent memory.",
            input_schema=object_schema(
                required=("query",),
                properties={
                    "query": {"type": "string"},
                    "limit": {"type": "integer"},
                },
            ),
        ),
        ToolCapabilityCapsule(
            name="memory_get",
            description="Retrieves a stored memory item.",
            input_schema=object_schema(
                required=("key",),
                properties={"key": {"type": "string"}},
            ),
        ),
        ToolCapabilityCapsule(
            name="sessions_list",
            description="Lists visible agent sessions.",
            input_schema=object_schema(
                properties={
                    "agentId": {"type": "string"},
                    "search": {"type": "string"},
                    "limit": {"type": "integer"},
                },
            ),
        ),
        ToolCapabilityCapsule(
            name="sessions_send",
            description="Sends a prompt or message to another visible session.",
            input_schema=object_schema(
                required=("target", "message"),
                properties={
                    "target": {"type": "string"},
                    "message": {"type": "string"},
                    "wait": {"type": "boolean"},
                },
            ),
        ),
    )

    def discover_sources(self, context: AdapterContext) -> list[MemorySourceSpec]:
        workspace = context.workspace_path()
        specs: list[MemorySourceSpec | None] = []
        for filename in ("MEMORY.md", "DREAMS.md"):
            specs.append(
                source_spec(
                    agent_name=self.agent_name,
                    path=workspace / filename,
                    source_kind=SourceKind.MEMORY_FILE,
                    scope_label="openclaw workspace memory",
                )
            )
        memory_dir = workspace / "memory"
        if memory_dir.exists():
            for path in sorted(memory_dir.glob("**/*.md")):
                specs.append(
                    source_spec(
                        agent_name=self.agent_name,
                        path=path,
                        source_kind=SourceKind.MEMORY_FILE,
                        scope_label="openclaw memory file",
                    )
                )
        for filename in ("AGENTS.md", "CLAUDE.md", "README.md", "CONTRIBUTING.md"):
            specs.append(
                source_spec(
                    agent_name=self.agent_name,
                    path=workspace / filename,
                    source_kind=SourceKind.PROJECT_DOC,
                    scope_label="project instruction document",
                )
            )
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
        self.configure_runtime(context)
        result = self.evaluate_action(store, event, context)
        mac_payload = self.decision_metadata(result)
        if result.decision.decision != GateDecisionType.ALLOW:
            return {
                "block": True,
                "decision": result.decision.decision.value,
                "reason": result.decision.reason,
                "requires_user_input": result.decision.decision == GateDecisionType.ASK,
                "mac": mac_payload,
            }
        return {"block": False, "mac": mac_payload}

    def bridge_before_prompt_build(
        self,
        store: ContractStore,
        payload: Mapping[str, Any],
        context: AdapterContext,
        *,
        extractor_factory=None,
    ) -> dict[str, Any]:
        user_turn = str(payload.get("prompt") or payload.get("user_turn") or "")
        result = self.process_user_prompt_submit(
            store,
            user_turn,
            context,
            extractor_factory=extractor_factory,
        )
        output: dict[str, Any] = {}
        if result.prompt_text:
            output["additionalContext"] = result.prompt_text
        if result.error is not None:
            output["mac"] = {"error": result.error}
        return output

    def bridge_before_tool_call(
        self,
        store: ContractStore,
        payload: Mapping[str, Any],
        context: AdapterContext,
    ) -> dict[str, Any]:
        return self.gate_event(store, payload, context)

    def hook_config_snippet(self) -> dict[str, Any]:
        return {
            "plugin": {
                "hooks": {
                    "before_prompt_build": "memory_as_contracts.adapters.openclaw:bridge_before_prompt_build",
                    "before_tool_call": "memory_as_contracts.adapters.openclaw:bridge_before_tool_call",
                    "after_tool_call": "memory_as_contracts.adapters.openclaw:bridge_after_tool_call",
                }
            },
            "note": "Function bridge only; Step 11 does not auto-install OpenClaw plugins.",
        }

    def _extract_tool_call(self, event: Mapping[str, Any] | Any) -> tuple[str, dict[str, Any], str]:
        tool_name = _value(event, "toolName", _value(event, "tool_name", _value(event, "name", "exec")))
        raw = _value(event, "params", _value(event, "tool_input", _value(event, "arguments", {})))
        if not isinstance(raw, dict):
            raw = {"value": raw}
        return str(tool_name), dict(raw), str(_value(event, "intent", ""))


def _value(event: Mapping[str, Any] | Any, key: str, default: Any = None) -> Any:
    if isinstance(event, Mapping):
        return event.get(key, default)
    return getattr(event, key, default)


_ADAPTER = OpenClawAdapter(pattern_refiner_factory=default_pattern_refiner_factory)


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


def bridge_before_prompt_build(store: ContractStore, payload: Mapping[str, Any], context: AdapterContext):
    _ADAPTER.configure_runtime(context)
    return _ADAPTER.bridge_before_prompt_build(store, payload, context)


def bridge_before_tool_call(store: ContractStore, payload: Mapping[str, Any], context: AdapterContext):
    _ADAPTER.configure_runtime(context)
    return _ADAPTER.bridge_before_tool_call(store, payload, context)


def bridge_after_tool_call(store: ContractStore, payload: Mapping[str, Any], context: AdapterContext):
    _ADAPTER.configure_runtime(context)
    return _ADAPTER.handle_post_tool_use(store, payload, context)
