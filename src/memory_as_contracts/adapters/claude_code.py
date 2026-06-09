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
    dedupe_specs,
    source_spec,
)
from memory_as_contracts.hook_runtime import default_pattern_refiner_factory
from memory_as_contracts.models import ActionSignature, GateDecisionType, SourceKind
from memory_as_contracts.store import ContractStore
from memory_as_contracts.tool_capsules import ToolCapabilityCapsule, object_schema


class ClaudeCodeAdapter(BaseAdapter):
    agent_name = "claude_code"
    host = "claude_code"
    always_on_tool_capsules = (
        ToolCapabilityCapsule(
            name="Bash",
            description="Runs a shell command in the workspace.",
            input_schema=object_schema(
                required=("command",),
                properties={
                    "command": {"type": "string"},
                    "description": {"type": "string"},
                    "timeout": {"type": "integer"},
                    "run_in_background": {"type": "boolean"},
                },
            ),
        ),
        ToolCapabilityCapsule(
            name="Read",
            description="Reads a file from the workspace.",
            input_schema=object_schema(
                required=("file_path",),
                properties={
                    "file_path": {"type": "string"},
                    "offset": {"type": "integer"},
                    "limit": {"type": "integer"},
                },
            ),
        ),
        ToolCapabilityCapsule(
            name="Write",
            description="Writes content to a file.",
            input_schema=object_schema(
                required=("file_path", "content"),
                properties={
                    "file_path": {"type": "string"},
                    "content": {"type": "string"},
                },
            ),
        ),
        ToolCapabilityCapsule(
            name="Edit",
            description="Replaces text within a file.",
            input_schema=object_schema(
                required=("file_path", "old_string", "new_string"),
                properties={
                    "file_path": {"type": "string"},
                    "old_string": {"type": "string"},
                    "new_string": {"type": "string"},
                    "replace_all": {"type": "boolean"},
                },
            ),
        ),
        ToolCapabilityCapsule(
            name="MultiEdit",
            description="Applies multiple text replacements to one file.",
            input_schema=object_schema(
                required=("file_path", "edits"),
                properties={
                    "file_path": {"type": "string"},
                    "edits": {"type": "array", "items": {"type": "object"}},
                },
            ),
        ),
        ToolCapabilityCapsule(
            name="Glob",
            description="Finds files by glob pattern.",
            input_schema=object_schema(
                required=("pattern",),
                properties={
                    "pattern": {"type": "string"},
                    "path": {"type": "string"},
                },
            ),
        ),
        ToolCapabilityCapsule(
            name="Grep",
            description="Searches file contents with a pattern.",
            input_schema=object_schema(
                required=("pattern",),
                properties={
                    "pattern": {"type": "string"},
                    "path": {"type": "string"},
                    "glob": {"type": "string"},
                    "output_mode": {"type": "string"},
                    "head_limit": {"type": "integer"},
                },
            ),
        ),
        ToolCapabilityCapsule(
            name="LS",
            description="Lists files and directories at a path.",
            input_schema=object_schema(
                required=("path",),
                properties={"path": {"type": "string"}},
            ),
        ),
        ToolCapabilityCapsule(
            name="TodoWrite",
            description="Updates the agent's visible task list.",
            input_schema=object_schema(
                required=("todos",),
                properties={"todos": {"type": "array", "items": {"type": "object"}}},
            ),
        ),
        ToolCapabilityCapsule(
            name="WebSearch",
            description="Searches the web for current information.",
            input_schema=object_schema(
                required=("query",),
                properties={
                    "query": {"type": "string"},
                    "allowed_domains": {"type": "array", "items": {"type": "string"}},
                    "blocked_domains": {"type": "array", "items": {"type": "string"}},
                },
            ),
        ),
        ToolCapabilityCapsule(
            name="WebFetch",
            description="Fetches a URL and processes it with a prompt.",
            input_schema=object_schema(
                required=("url", "prompt"),
                properties={
                    "url": {"type": "string"},
                    "prompt": {"type": "string"},
                },
            ),
        ),
    )

    def discover_sources(self, context: AdapterContext) -> list[MemorySourceSpec]:
        workspace = context.workspace_path()
        cwd = context.cwd_path()
        specs: list[MemorySourceSpec | None] = []

        claude_dir = Path(os.environ.get("CLAUDE_CONFIG_DIR", Path.home() / ".claude"))
        for filename in ("CLAUDE.md", "CLAUDE.local.md"):
            specs.append(
                source_spec(
                    agent_name=self.agent_name,
                    path=claude_dir / filename,
                    source_kind=SourceKind.USER_PROFILE,
                    scope_label="global/user claude instructions",
                )
            )

        for directory in ancestor_dirs(workspace, cwd):
            for filename in ("CLAUDE.md", "CLAUDE.local.md"):
                specs.append(
                    source_spec(
                        agent_name=self.agent_name,
                        path=directory / filename,
                        source_kind=SourceKind.PROJECT_DOC,
                        scope_label=f"project claude instructions:{directory}",
                    )
                )

        rules_dir = workspace / ".claude" / "rules"
        if rules_dir.exists():
            for path in sorted(rules_dir.glob("*.md")):
                specs.append(
                    source_spec(
                        agent_name=self.agent_name,
                        path=path,
                        source_kind=SourceKind.PROJECT_DOC,
                        scope_label="project claude rule",
                    )
                )

        for memory_root in _claude_memory_roots(workspace):
            if memory_root.exists():
                for path in sorted(memory_root.glob("**/*.md")):
                    specs.append(
                        source_spec(
                            agent_name=self.agent_name,
                            path=path,
                            source_kind=SourceKind.MEMORY_FILE,
                            scope_label="claude auto memory",
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
                                "command": "uv run python -m memory_as_contracts.adapters.claude_code user_prompt_submit",
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
                                "command": "uv run python -m memory_as_contracts.adapters.claude_code pre_tool_use",
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
                                "command": "uv run python -m memory_as_contracts.adapters.claude_code post_tool_use",
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
            raw = {"value": raw}
        return str(tool_name), dict(raw), str(_value(event, "intent", ""))


def _claude_memory_roots(workspace: Path) -> list[Path]:
    override = os.environ.get("CLAUDE_PROJECT_MEMORY_DIR")
    if override:
        return [Path(override).expanduser()]
    project_slug = "-" + str(workspace).strip("/").replace("/", "-")
    return [
        Path.home() / ".claude" / "projects" / project_slug / "memory",
        Path.home() / ".claude" / "projects" / workspace.name / "memory",
    ]


def _value(event: Mapping[str, Any] | Any, key: str, default: Any = None) -> Any:
    if isinstance(event, Mapping):
        return event.get(key, default)
    return getattr(event, key, default)


_ADAPTER = ClaudeCodeAdapter(pattern_refiner_factory=default_pattern_refiner_factory)


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
