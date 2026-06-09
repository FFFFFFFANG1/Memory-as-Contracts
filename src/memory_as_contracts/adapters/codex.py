from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from memory_as_contracts.adapters.base import (
    AdapterContext,
    BaseAdapter,
    ColdStartExtractor,
    MemorySourceSpec,
    ancestor_dirs,
    configured_filenames,
    dedupe_specs,
    source_spec,
)
from memory_as_contracts.hook_runtime import default_pattern_refiner_factory
from memory_as_contracts.models import ActionSignature, GateDecisionType, SourceKind
from memory_as_contracts.store import ContractStore
from memory_as_contracts.tool_capsules import ToolCapabilityCapsule, object_schema


class CodexAdapter(BaseAdapter):
    agent_name = "codex"
    host = "codex"
    always_on_tool_capsules = (
        ToolCapabilityCapsule(
            name="exec_command",
            description="Runs a shell command in the workspace.",
            input_schema=object_schema(
                required=("cmd",),
                properties={
                    "cmd": {"type": "string"},
                    "workdir": {"type": "string"},
                    "shell": {"type": "string"},
                    "tty": {"type": "boolean"},
                    "yield_time_ms": {"type": "integer"},
                    "max_output_tokens": {"type": "integer"},
                },
            ),
        ),
        ToolCapabilityCapsule(
            name="write_stdin",
            description="Writes input to a running command session.",
            input_schema=object_schema(
                required=("session_id",),
                properties={
                    "session_id": {"type": "integer"},
                    "chars": {"type": "string"},
                    "yield_time_ms": {"type": "integer"},
                    "max_output_tokens": {"type": "integer"},
                },
            ),
        ),
        ToolCapabilityCapsule(
            name="apply_patch",
            description="Applies a patch that creates, updates, moves, or deletes files.",
            input_schema=object_schema(
                required=("patch",),
                properties={"patch": {"type": "string"}},
            ),
        ),
        ToolCapabilityCapsule(
            name="view_image",
            description="Reads a local image file for visual inspection.",
            input_schema=object_schema(
                required=("path",),
                properties={
                    "path": {"type": "string"},
                    "detail": {"type": "string"},
                },
            ),
        ),
    )

    def discover_sources(self, context: AdapterContext) -> list[MemorySourceSpec]:
        workspace = context.workspace_path()
        cwd = context.cwd_path()
        specs: list[MemorySourceSpec | None] = []

        codex_home = Path(os.environ.get("CODEX_HOME", Path.home() / ".codex"))
        global_override = codex_home / "AGENTS.override.md"
        global_agents = codex_home / "AGENTS.md"
        specs.append(
            source_spec(
                agent_name=self.agent_name,
                path=global_override if global_override.exists() else global_agents,
                source_kind=SourceKind.USER_PROFILE,
                scope_label="global/user codex instructions",
            )
        )

        filenames = (
            "AGENTS.override.md",
            "AGENTS.md",
            *configured_filenames("MAC_CODEX_FALLBACK_FILENAMES"),
        )
        for directory in ancestor_dirs(workspace, cwd):
            for filename in filenames:
                specs.append(
                    source_spec(
                        agent_name=self.agent_name,
                        path=directory / filename,
                        source_kind=SourceKind.PROJECT_DOC,
                        scope_label=f"project instructions:{directory}",
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
        result = self.evaluate_action(store, event, context)
        mac_payload = self.decision_metadata(result)
        output: dict[str, Any] = {
            "hookSpecificOutput": {"hookEventName": "PreToolUse"},
            "mac": mac_payload,
        }
        if result.decision.decision in {GateDecisionType.REJECT, GateDecisionType.ASK}:
            output["hookSpecificOutput"].update(
                {
                    "permissionDecision": "deny",
                    "permissionDecisionReason": result.decision.reason,
                }
            )
        if result.decision.decision == GateDecisionType.ASK:
            output["mac"]["requires_user_input"] = True
        return output

    def handle_user_prompt_submit(
        self,
        store: ContractStore,
        user_turn: str,
        context: AdapterContext,
        *,
        extractor_factory=None,
    ) -> dict[str, Any]:
        result = self.process_user_prompt_submit(
            store,
            user_turn,
            context,
            extractor_factory=extractor_factory,
        )
        output: dict[str, Any] = {}
        if result.prompt_text:
            output["hookSpecificOutput"] = {
                "hookEventName": "UserPromptSubmit",
                "additionalContext": result.prompt_text,
            }
        if result.error is not None:
            output["mac"] = {"error": result.error}
        return output

    def handle_pre_tool_use(
        self,
        store: ContractStore,
        event: Mapping[str, Any] | Any,
        context: AdapterContext,
    ) -> dict[str, Any]:
        return self.gate_event(store, event, context)

    def hook_config_snippet(self) -> dict[str, Any]:
        return {
            "hooks": {
                "UserPromptSubmit": [
                    {
                        "matcher": "*",
                        "hooks": [
                            {
                                "type": "command",
                                "command": "uv run python -m memory_as_contracts.adapters.codex user_prompt_submit",
                            }
                        ],
                    }
                ],
                "PreToolUse": [
                    {
                        "matcher": "*",
                        "hooks": [
                            {
                                "type": "command",
                                "command": "uv run python -m memory_as_contracts.adapters.codex pre_tool_use",
                            }
                        ],
                    }
                ],
                "PostToolUse": [
                    {
                        "matcher": "*",
                        "hooks": [
                            {
                                "type": "command",
                                "command": "uv run python -m memory_as_contracts.adapters.codex post_tool_use",
                            }
                        ],
                    }
                ],
            }
        }

    def _extract_tool_call(self, event: Mapping[str, Any] | Any) -> tuple[str, dict[str, Any], str]:
        tool_name = _value(event, "tool_name", _value(event, "name", "exec"))
        raw = _value(event, "tool_input", _value(event, "arguments", {}))
        if not isinstance(raw, dict):
            raw = {"patch": raw} if tool_name == "apply_patch" else {"value": raw}
        return str(tool_name), dict(raw), str(_value(event, "intent", ""))


def _value(event: Mapping[str, Any] | Any, key: str, default: Any = None) -> Any:
    if isinstance(event, Mapping):
        return event.get(key, default)
    return getattr(event, key, default)


_ADAPTER = CodexAdapter(pattern_refiner_factory=default_pattern_refiner_factory)


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


if __name__ == "__main__":
    from memory_as_contracts.adapters.command import run_adapter_command

    raise SystemExit(run_adapter_command(_ADAPTER))
