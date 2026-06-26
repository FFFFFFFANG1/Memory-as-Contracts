from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ToolCapabilityCapsule:
    """Compact model-visible tool definition for extraction-time grounding."""

    name: str
    description: str
    input_schema: Mapping[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": dict(self.input_schema),
        }


def render_tool_capsule_system_prompt(
    capsules: Sequence[ToolCapabilityCapsule],
) -> str | None:
    if not capsules:
        return None
    payload = {
        "tools": [capsule.as_dict() for capsule in capsules],
    }
    return (
        "Tool definitions available to the acting agent are provided below as read-only "
        "environment context. Do not extract contracts from these tool definitions. Use "
        "them only to ground check_patterns with exact native tool names and "
        "raw parameter names when the source text states a user or source contract.\n\n"
        f"{json.dumps(payload, indent=2, sort_keys=True)}"
    )


def object_schema(
    *,
    properties: Mapping[str, Mapping[str, Any]],
    required: Sequence[str] = (),
) -> dict[str, Any]:
    schema: dict[str, Any] = {
        "type": "object",
        "properties": {key: dict(value) for key, value in properties.items()},
    }
    if required:
        schema["required"] = list(required)
    return schema
