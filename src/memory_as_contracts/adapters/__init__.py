"""Host-agent adapters for Memory-as-Contracts integration."""

from memory_as_contracts.adapters.base import (
    AdapterContext,
    AdapterResult,
    ChangedSource,
    MemorySourceSpec,
)
from memory_as_contracts.adapters.claude_code import ClaudeCodeAdapter
from memory_as_contracts.adapters.codex import CodexAdapter
from memory_as_contracts.adapters.nanobot import NanobotAdapter, gate_nanobot_tool_call
from memory_as_contracts.adapters.openclaw import OpenClawAdapter
from memory_as_contracts.tool_capsules import ToolCapabilityCapsule

__all__ = [
    "AdapterContext",
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
