"""Host-agent adapters for Memory-as-Contracts integration."""

from memory_as_contracts.adapters.base import (
    AdapterContext,
    AdapterCapabilities,
    AdapterResult,
    ChangedSource,
    MemorySourceSpec,
)
from memory_as_contracts.tool_capsules import ToolCapabilityCapsule

__all__ = [
    "AdapterContext",
    "AdapterCapabilities",
    "AdapterResult",
    "ChangedSource",
    "ClaudeCodeAdapter",
    "CodexAdapter",
    "MemorySourceSpec",
    "NanobotAdapter",
    "OpenClawAdapter",
    "ToolCapabilityCapsule",
    "gate_nanobot_tool_call",
]


def __getattr__(name: str):
    if name == "ClaudeCodeAdapter":
        from memory_as_contracts.adapters.claude_code import ClaudeCodeAdapter

        return ClaudeCodeAdapter
    if name == "CodexAdapter":
        from memory_as_contracts.adapters.codex import CodexAdapter

        return CodexAdapter
    if name == "NanobotAdapter":
        from memory_as_contracts.adapters.nanobot import NanobotAdapter

        return NanobotAdapter
    if name == "OpenClawAdapter":
        from memory_as_contracts.adapters.openclaw import OpenClawAdapter

        return OpenClawAdapter
    if name == "gate_nanobot_tool_call":
        from memory_as_contracts.adapters.nanobot import gate_nanobot_tool_call

        return gate_nanobot_tool_call
    raise AttributeError(name)
