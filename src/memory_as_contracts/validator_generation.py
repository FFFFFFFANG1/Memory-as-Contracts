from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError

from memory_as_contracts.models import (
    ActionLogEntryV1,
    Contract,
    ToolPattern,
    ValidatorEnforcementShape,
)
from memory_as_contracts.store import ContractStore


VALIDATOR_GENERATION_SYSTEM_PROMPT = """
You translate one immutable contract into pre/post hook code that gates an agent at runtime.
Return strict JSON only. Do not wrap the answer in Markdown.

# Required output
Return one JSON object with:
- check_code: Python code defining check(action, log, context)
- update_code: Python code defining update(entry, log, context), or null
  when the enforcement shape is check_only
- shared_states: object declaring the only state keys this validator may read or
  write. For check_update include every requested state field with a safe
  default such as zero, null, false, or []

# Hook responsibilities
- check_code runs before a pending tool action. It decides whether that action
  satisfies the contract. It may read shared state but must not write it.
- update_code runs after a committed tool action. It updates shared state from
  that entry using log.state_write(...).
- check_code and update_code run as separate modules. Do not rely on shared
  helper functions, globals, or imports between them.

# Runtime API
- action is a dict with tool_name, host_action, arguments, targets, and context fields.
- entry is a committed action dict with seq, tool_name, host_action, arguments,
  result, result_text, outcome, and targets when available.
- context is a dict with runtime metadata such as contract_id and scope_key.
- log.read(spec) reads bounded committed action-log rows.
- log.state_read(key=None) reads shared state. With a key, it returns that value;
  without a key, it returns a shallow state snapshot.
- log.state_write(updates) writes existing shared state keys in update only.
  It does not add or delete keys, and it is forbidden in check.
Use action.get(...) and entry.get(...) for field access.
Do not use getattr, hasattr, action.field, or entry.field.

# log.read spec
Required: {"from": "actions", "limit": N}.
The where value MUST be an object mapping field names to operator objects.
Do not use SQL strings, tuples, lambdas, or a list of clauses.
Supported select/where fields include seq, timestamp, tool_name, host_action,
outcome, arguments, result, result_text, targets, and any_text.

Example:
{
  "from": "actions",
  "select": ["seq", "tool_name", "arguments", "result_text"],
  "where": {
    "tool_name": {"eq": "Bash"},
    "outcome": {"eq": "success"},
    "any_text": {"regex": "pytest|uv run pytest"}
  },
  "order_by": [{"field": "seq", "direction": "desc"}],
  "limit": 20
}

# Verdict API
check must return allow(reason, evidence_refs=None, confidence=1.0) only when evidence is sufficient.
Return reject(reason, evidence_refs=None, confidence=1.0) for definite violations.
Return ask(reason, evidence_refs=None, confidence=1.0) when user input is required or evidence is insufficient.

# Sandbox capabilities
Only import math or re.
Available builtins: abs, all, any, bool, dict, enumerate, float, format, int,
isinstance, len, list, max, min, range, round, set, sorted, str, sum, and tuple.
Do not assume any other builtin, module, filesystem, environment, subprocess,
network, or raw SQL API.

# Safety rules
Do not hard-code literal values from committed examples; use them only to infer
where relevant fields appear in action arguments or results.
Before returning allow, verify that every pending action field needed by the
check_patterns is present and usable. If a required field is missing, null, or
unparsable, return ask.
For check_update, update must use state_read/state_write, inspect entry.seq when
present, and be idempotent for repeated entries.
""".strip()

ValidatorPackageStatus = Literal["success", "fail"]


class ValidatorSnippetPackage(BaseModel):
    status: ValidatorPackageStatus
    check_code: str | None = None
    update_code: str | None = None
    shared_states: dict[str, Any] = Field(default_factory=dict)
    notes: list[str] = Field(default_factory=list)
    verification_hash: str = ""

    def is_ready(self) -> bool:
        return self.status == "success" and bool(self.check_code)


class ValidatorSnippetGenerator:
    """Build and parse the LLM-facing validator snippet generation request."""

    def __init__(self, response_provider: Callable[[str], str]) -> None:
        self.response_provider = response_provider

    def generate(
        self,
        contract: Contract,
        *,
        store: ContractStore,
        session_id: str,
        task_id: str | None = None,
        tool_capsules: Sequence[Any] | None = None,
    ) -> ValidatorSnippetPackage:
        capsules = list(tool_capsules or [])
        examples = matched_action_examples(
            store.list_action_log_entries(),
            patterns=[*contract.check_patterns, *contract.update_patterns],
            session_id=session_id,
            task_id=task_id,
            limit_per_tool=2,
        )
        preflight = _preflight(contract, capsules)
        if preflight is not None:
            return preflight

        prompt = build_validator_generator_prompt(
            contract,
            committed_examples=examples,
            tool_capsules=capsules,
        )
        return _with_default_shared_states(contract, _parse_package(self.response_provider(prompt)))

    def generate_verified(
        self,
        contract: Contract,
        *,
        store: ContractStore,
        session_id: str,
        task_id: str | None = None,
        tool_capsules: Sequence[Any] | None = None,
        max_attempts: int = 3,
    ) -> ValidatorSnippetPackage:
        from memory_as_contracts.validator_installation import ValidatorSnippetVerifier

        capsules = list(tool_capsules or [])
        examples = matched_action_examples(
            store.list_action_log_entries(),
            patterns=[*contract.check_patterns, *contract.update_patterns],
            session_id=session_id,
            task_id=task_id,
            limit_per_tool=2,
        )
        preflight = _preflight(contract, capsules)
        if preflight is not None:
            return preflight
        base_prompt = build_validator_generator_prompt(
            contract,
            committed_examples=examples,
            tool_capsules=capsules,
        )
        verifier = ValidatorSnippetVerifier()
        errors: list[str] = []
        for attempt in range(max_attempts):
            prompt = base_prompt
            if errors:
                prompt += (
                    "\n\nVERIFIER FEEDBACK\n"
                    + _json(errors)
                    + "\nReturn a corrected full package. Do not weaken uncertain cases to allow."
                )
            package = _with_default_shared_states(
                contract,
                _parse_package(self.response_provider(prompt)),
            )
            if not package.is_ready():
                return package
            verification = verifier.verify(
                contract,
                package,
                store=store,
                session_id=session_id,
                task_id=task_id,
                committed_examples=examples,
            )
            if verification.accepted:
                return package.model_copy(update={"verification_hash": verification.verification_hash})
            errors = verification.errors
            if attempt + 1 >= max_attempts:
                break
        return ValidatorSnippetPackage(
            status="fail",
            notes=["validator verification failed after retries", *errors],
        )


def build_validator_generator_prompt(
    contract: Contract,
    *,
    committed_examples: Sequence[ActionLogEntryV1],
    tool_capsules: Sequence[Any],
) -> str:
    rule_payload = {
        "text": contract.text,
    }
    enforcement_payload = {
        "enforcement_shape": contract.validator_enforcement_shape.value,
        "check_patterns": [pattern.model_dump(mode="json") for pattern in contract.check_patterns],
        "update_patterns": [pattern.model_dump(mode="json") for pattern in contract.update_patterns],
        "state_fields": list(contract.state_fields),
    }
    relevant_tool_capsules = _filter_tool_capsules_for_enforcement(
        tool_capsules,
        patterns=[*contract.check_patterns, *contract.update_patterns],
    )
    sections = [
        "IMMUTABLE RULE",
        _json(rule_payload),
        "",
        "ENFORCEMENT PLAN",
        _enforcement_summary(enforcement_payload),
        _json(enforcement_payload),
        "",
        "TOOL CAPSULES",
        _json([_dump_capsule(capsule) for capsule in relevant_tool_capsules]),
        "",
        "TASK",
        (
            "Translate the immutable rule into hook functions. Use the patterns to decide "
            "which actions should be gated and the tool capsules to locate runtime fields."
        ),
    ]
    if committed_examples:
        sections[10:10] = [
            "",
            "MATCHED COMMITTED ACTION EXAMPLES",
            _json([_compact_action_signature_example(entry) for entry in committed_examples]),
        ]
    return "\n".join(sections)


def _preflight(
    contract: Contract,
    tool_capsules: Sequence[Any],
) -> ValidatorSnippetPackage | None:
    shape = contract.validator_enforcement_shape
    if shape == ValidatorEnforcementShape.NO_VALIDATOR:
        return ValidatorSnippetPackage(
            status="fail",
            notes=["contract does not request validator enforcement"],
        )
    if not tool_capsules:
        return ValidatorSnippetPackage(status="fail", notes=["missing tool capsules"])
    if not contract.check_patterns:
        return ValidatorSnippetPackage(status="fail", notes=["missing check patterns"])
    if shape == ValidatorEnforcementShape.CHECK_UPDATE and not contract.update_patterns:
        return ValidatorSnippetPackage(status="fail", notes=["missing update patterns"])
    return None


def _filter_tool_capsules_for_enforcement(
    tool_capsules: Sequence[Any],
    *,
    patterns: Sequence[ToolPattern],
) -> list[Any]:
    requested_tools = {pattern.tool for pattern in patterns if pattern.tool and pattern.tool != "*"}
    if not requested_tools or any(pattern.tool == "*" for pattern in patterns):
        return list(tool_capsules)
    filtered = [
        capsule
        for capsule in tool_capsules
        if _capsule_name(capsule) in requested_tools
    ]
    # If pattern tool names do not match any capsule, an empty TOOL CAPSULES
    # section would leave the generator blind; fall back to the full set.
    return filtered or list(tool_capsules)


def _capsule_name(capsule: Any) -> str | None:
    if hasattr(capsule, "name"):
        return str(capsule.name)
    if isinstance(capsule, dict) and capsule.get("name") is not None:
        return str(capsule["name"])
    return None


def _compact_action_signature_example(entry: ActionLogEntryV1) -> dict[str, Any]:
    return {
        "seq": entry.seq,
        "tool_call_id": entry.tool_call_id,
        "tool_name": entry.tool_name,
        "host_action": entry.host_action,
        "arguments": _compact_arguments(entry.arguments),
        "targets": entry.targets,
        "risk": entry.risk.value,
        "side_effect": entry.side_effect.value,
    }


def _compact_arguments(arguments: Any) -> Any:
    if not isinstance(arguments, dict):
        return arguments
    blocked = {"prompt", "observation", "metadata", "turn_session_id"}
    compact: dict[str, Any] = {}
    for key, value in arguments.items():
        if key in blocked:
            continue
        if key == "normalized_action" and isinstance(value, dict):
            compact[key] = {
                nested_key: nested_value
                for nested_key, nested_value in value.items()
                if nested_key not in {"prompt", "observation", "metadata"}
            }
            continue
        compact[key] = value
    return compact


def _with_default_shared_states(
    contract: Contract,
    package: ValidatorSnippetPackage,
) -> ValidatorSnippetPackage:
    if package.status != "success":
        return package
    if contract.validator_enforcement_shape != ValidatorEnforcementShape.CHECK_UPDATE:
        return package
    shared_states = dict(package.shared_states)
    for field in contract.state_fields:
        shared_states.setdefault(field, _default_state_value(field))
    return package.model_copy(update={"shared_states": shared_states})


def _default_state_value(field: str) -> Any:
    lower = field.lower()
    if any(token in lower for token in ("seqs", "ids", "items", "events", "entries")):
        return []
    if any(token in lower for token in ("total", "count", "cents", "amount", "spent", "sum")):
        return 0
    if lower.startswith(("has_", "is_", "needs_")) or lower.endswith("_flag"):
        return False
    return None


def matched_action_examples(
    entries: Sequence[ActionLogEntryV1],
    *,
    patterns: Sequence[ToolPattern],
    session_id: str,
    limit_per_tool: int,
    task_id: str | None = None,
) -> list[ActionLogEntryV1]:
    del task_id
    tool_names = {pattern.tool for pattern in patterns if pattern.tool and pattern.tool != "*"}
    wildcard = any(pattern.tool == "*" for pattern in patterns)
    counts: dict[str, int] = {}
    examples: list[ActionLogEntryV1] = []
    ordered_entries = sorted(
        entries,
        key=lambda entry: (entry.timestamp, entry.seq or 0),
        reverse=True,
    )
    for entry in ordered_entries:
        if entry.session_id != session_id:
            continue
        if not wildcard and entry.tool_name not in tool_names:
            continue
        key = entry.tool_name
        if counts.get(key, 0) >= limit_per_tool:
            continue
        counts[key] = counts.get(key, 0) + 1
        examples.append(entry)
    return examples


def _parse_package(raw: str) -> ValidatorSnippetPackage:
    try:
        payload = _normalize_package_payload(json.loads(_json_object_text(raw)))
        package = ValidatorSnippetPackage.model_validate(payload)
    except (json.JSONDecodeError, ValidationError, ValueError) as exc:
        return ValidatorSnippetPackage(status="fail", notes=[f"invalid generator response: {exc}"])
    if package.status == "success" and not package.check_code:
        return ValidatorSnippetPackage(status="fail", notes=["success response omitted check_code"])
    return package


def _normalize_package_payload(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("generator response must be an object")
    normalized = dict(payload)
    nested = normalized.get("validator") or normalized.get("package")
    if isinstance(nested, dict):
        normalized = {**normalized, **nested}

    check_code = (
        normalized.get("check_code")
        or normalized.get("check")
        or normalized.get("pre_hook")
        or normalized.get("pre_hook_code")
    )
    if check_code is not None:
        normalized["check_code"] = _clean_snippet(str(check_code))
    update_code = (
        normalized.get("update_code")
        or normalized.get("update")
        or normalized.get("post_hook")
        or normalized.get("post_hook_code")
    )
    if update_code is not None:
        normalized["update_code"] = _clean_snippet(str(update_code))
    shared_states = normalized.get("shared_states", normalized.get("initial_state", {}))
    normalized["shared_states"] = shared_states if isinstance(shared_states, dict) else {}

    status = str(normalized.get("status", "")).strip().lower()
    status_aliases = {
        "ok": "success",
        "ready": "success",
        "valid": "success",
        "complete": "success",
        "completed": "success",
        "failed": "fail",
        "failure": "fail",
        "error": "fail",
        "needs_refinement": "fail",
        "needs refinement": "fail",
        "need_refinement": "fail",
        "manual_review": "fail",
        "manual review": "fail",
        "no_validator": "fail",
    }
    if status in status_aliases:
        normalized["status"] = status_aliases[status]
    elif status not in {"success", "fail"}:
        normalized["status"] = "success" if check_code else "fail"

    notes = normalized.get("notes", [])
    if isinstance(notes, str):
        normalized["notes"] = [notes]
    elif notes is None:
        normalized["notes"] = []
    return normalized


def _clean_snippet(snippet: str) -> str:
    stripped = snippet.strip()
    if not stripped.startswith("```"):
        return stripped
    lines = stripped.splitlines()
    if lines and lines[0].startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]
    return "\n".join(lines).strip()


def _json_object_text(raw: str) -> str:
    start = raw.find("{")
    end = raw.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("response did not contain a JSON object")
    return raw[start : end + 1]


def _json(payload: Any) -> str:
    return json.dumps(payload, indent=2, sort_keys=True)


def _enforcement_summary(payload: dict[str, Any]) -> str:
    lines = [
        f"enforcement_shape: {payload['enforcement_shape']}",
        f"state_fields: {', '.join(payload['state_fields']) or '<none>'}",
    ]
    return "\n".join(lines)


def _dump_capsule(capsule: Any) -> Any:
    if hasattr(capsule, "as_dict"):
        return capsule.as_dict()
    if hasattr(capsule, "model_dump"):
        return capsule.model_dump(mode="json")
    if isinstance(capsule, dict):
        return capsule
    return str(capsule)
