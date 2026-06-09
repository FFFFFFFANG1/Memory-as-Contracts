from __future__ import annotations

import re
from typing import Any


SOURCE_KIND_TO_AUTHORITY = {
    "user_turn": "user_explicit",
    "project_doc": "project_instruction",
    "memory_file": "memory_import",
    "user_profile": "user_profile",
    "tool_observation": "tool_observation",
    "agent_inferred": "agent_inferred",
}

AUTHORITY_TO_SOURCE_KIND = {value: key for key, value in SOURCE_KIND_TO_AUTHORITY.items()}


def normalize_rule_payload(data: Any) -> Any:
    """Translate legacy contract-shaped input into the canonical Rule shape.

    This is the compatibility seam for v1/v2 payloads and tests that still pass
    legacy fields. Runtime modules should consume the canonical fields produced
    here: semantics, tool_patterns, validity, effect, and authority.
    """

    if not isinstance(data, dict):
        return data
    normalized = dict(data)
    if "text" not in normalized and "rule_text" in normalized:
        normalized["text"] = normalized["rule_text"]

    if "effect" not in normalized:
        normalized["effect"] = _effect_from_kind_modality(
            _value(normalized.get("kind")), _value(normalized.get("modality"))
        )
    if "kind" not in normalized or "modality" not in normalized:
        kind, modality, strength = _legacy_shape_from_effect(_value(normalized.get("effect")))
        normalized.setdefault("kind", kind)
        normalized.setdefault("modality", modality)
        normalized.setdefault("strength", strength)

    source = _model_to_dict(normalized.get("source"))
    if "authority" not in normalized and isinstance(source, dict) and source.get("kind"):
        normalized["authority"] = SOURCE_KIND_TO_AUTHORITY.get(
            _value(source["kind"]), "agent_inferred"
        )
    if "authority" in normalized and "source" not in normalized:
        normalized["source"] = {
            "kind": AUTHORITY_TO_SOURCE_KIND.get(_value(normalized["authority"]), "agent_inferred"),
            "span": normalized.get("text", ""),
        }

    semantics = _model_to_dict(normalized.get("semantics"))
    constraints = _model_to_dict(normalized.get("action_constraints"))
    if semantics is not None:
        normalized["semantics"] = semantics
    if "semantics" not in normalized and isinstance(constraints, dict):
        normalized["semantics"] = semantics_from_action_constraints(constraints)
    normalized.pop("action_constraints", None)

    lifecycle = _model_to_dict(normalized.get("lifecycle"))
    validity = _model_to_dict(normalized.get("validity"))
    if lifecycle is not None:
        normalized["lifecycle"] = lifecycle
    if validity is not None:
        normalized["validity"] = validity
    if "validity" not in normalized:
        derived = validity_from_lifecycle(lifecycle)
        if derived is not None:
            normalized["validity"] = derived
    if "lifecycle" not in normalized:
        derived = lifecycle_from_validity(validity)
        if derived is not None:
            normalized["lifecycle"] = derived

    pattern_version = normalized.get("compiled_predicates")
    if "pattern_version" in normalized and pattern_version is None:
        pattern_version = normalized.pop("pattern_version")
    else:
        normalized.pop("pattern_version", None)
    pattern_payload = _model_to_dict(pattern_version)
    if isinstance(pattern_payload, dict):
        canonical_pattern = canonical_pattern_version_payload(pattern_payload)
        normalized.setdefault("tool_patterns", canonical_pattern.get("tool_patterns", []))
    normalized.pop("compiled_predicates", None)
    normalized.pop("targets", None)
    normalized.pop("target_patterns", None)
    return normalized


def canonical_contract_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Return the public canonical Rule payload stored in contracts.payload_json."""

    canonical = dict(payload)
    canonical.pop("action_constraints", None)
    canonical.pop("compiled_predicates", None)
    canonical.pop("pattern_version", None)
    validity = canonical.get("validity")
    if isinstance(validity, dict) and "start" in validity and "from" not in validity:
        validity = dict(validity)
        validity["from"] = validity.pop("start")
        canonical["validity"] = validity
    return canonical


def canonical_pattern_version_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Return canonical RulePatternVersion JSON.

    Legacy host_action_patterns are converted into native tool_patterns at this
    seam. The legacy key is not emitted in the canonical payload.
    """

    canonical = dict(payload)
    canonical.pop("target_patterns", None)
    canonical.pop("targets", None)
    if not canonical.get("tool_patterns"):
        canonical["tool_patterns"] = tool_patterns_from_host_patterns(
            canonical.get("host_action_patterns", [])
        )
    canonical.pop("host_action_patterns", None)
    return canonical


def semantics_from_action_constraints(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "actions": payload.get("host_actions", []),
        "tags": payload.get("canonical_tags", []),
    }


def action_constraints_from_semantics(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "host_actions": payload.get("actions", []),
        "canonical_tags": payload.get("tags", []),
    }


def validity_from_lifecycle(lifecycle: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(lifecycle, dict):
        return None
    return {
        "from": lifecycle.get("effective_from"),
        "until": lifecycle.get("expires_at"),
    }


def lifecycle_from_validity(validity: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(validity, dict):
        return None
    until = validity.get("until")
    return {
        "type": "bounded_time" if until else "until_revoked",
        "effective_from": validity.get("from") or validity.get("start"),
        "expires_at": until,
        "until_revoked": until is None,
    }


def tool_patterns_from_host_patterns(patterns: list[Any]) -> list[dict[str, Any]]:
    converted: list[dict[str, Any]] = []
    for pattern in patterns:
        pattern = _model_to_dict(pattern)
        if not isinstance(pattern, dict):
            continue
        tool_name = pattern.get("tool_name") or pattern.get("tool") or pattern.get("action")
        if not tool_name:
            continue
        args: dict[str, dict[str, Any]] = {}
        parameter_regex = pattern.get("parameter_regex") or {}
        if isinstance(parameter_regex, dict):
            for key, regex in parameter_regex.items():
                args[str(key)] = {"regex": str(regex)}
        if pattern.get("program"):
            pieces = [re.escape(str(pattern["program"]))]
            if pattern.get("subcommand"):
                pieces.append(re.escape(str(pattern["subcommand"])))
            regex = r"^\s*" + r"\s+".join(pieces) + r"(?:\s|$)"
            for key in _command_arg_names(str(tool_name)):
                args.setdefault(key, {"regex": regex})
        converted.append({"tool": str(tool_name), "args": args})
    return converted


def _command_arg_names(tool_name: str) -> tuple[str, ...]:
    if tool_name == "Bash":
        return ("command",)
    if tool_name in {"exec", "exec_command"}:
        return ("cmd", "command")
    return ("command", "cmd")


def _effect_from_kind_modality(kind: str | None, modality: str | None) -> str:
    if kind == "prohibition" or modality == "MUST_NOT":
        return "deny"
    if kind == "exception" or modality == "MAY":
        return "allow"
    if kind in {"requirement", "procedure"} or modality == "MUST":
        return "require"
    return "prefer"


def _legacy_shape_from_effect(effect: str | None) -> tuple[str, str, str]:
    if effect == "deny":
        return "prohibition", "MUST_NOT", "hard"
    if effect == "require":
        return "requirement", "MUST", "hard"
    if effect == "allow":
        return "exception", "MAY", "soft"
    return "preference", "SHOULD", "soft"


def _model_to_dict(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    return value


def _value(value: Any) -> str | None:
    if value is None:
        return None
    return str(getattr(value, "value", value))
