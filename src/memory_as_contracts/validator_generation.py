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
You generate validator code snippets.
Return strict JSON only. Do not wrap the answer in Markdown.
The snippet must define check(action, state, log, context).
For check_update validators, it must also define update(state, entry, log, context).
The snippet must be deterministic and must not perform file IO, network access,
environment access, subprocess execution, or raw SQL. Use only the supplied
log.search(spec) API and verdict helpers.
At runtime, action, entry, state, and context are plain JSON-like Python dicts.
Use mapping access such as action.get("arguments"); never use getattr or field
attribute access on those values. Only log is an object with a method API.
""".strip()

ValidatorPackageStatus = Literal["ready", "needs_refinement", "manual_review", "no_validator"]


class ValidatorSnippetPackage(BaseModel):
    status: ValidatorPackageStatus
    snippet: str | None = None
    initial_state: dict[str, Any] = Field(default_factory=dict)
    notes: list[str] = Field(default_factory=list)

    def is_ready(self) -> bool:
        return self.status == "ready" and bool(self.snippet)


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
        pending_examples: Sequence[dict[str, Any]] | None = None,
        tool_capsules: Sequence[Any] | None = None,
    ) -> ValidatorSnippetPackage:
        pending = list(pending_examples or [])
        capsules = list(tool_capsules or [])
        examples = matched_action_examples(
            store.list_action_log_entries(),
            patterns=[*contract.check_patterns, *contract.update_patterns],
            session_id=session_id,
            task_id=task_id,
            limit_per_tool=2,
        )
        preflight = _preflight(contract, examples, pending, capsules)
        if preflight is not None:
            return preflight

        prompt = build_validator_generator_prompt(
            contract,
            committed_examples=examples,
            pending_examples=pending,
            tool_capsules=capsules,
        )
        return _with_default_initial_state(contract, _parse_package(self.response_provider(prompt)))

    def generate_verified(
        self,
        contract: Contract,
        *,
        store: ContractStore,
        session_id: str,
        task_id: str | None = None,
        pending_examples: Sequence[dict[str, Any]] | None = None,
        tool_capsules: Sequence[Any] | None = None,
        max_attempts: int = 3,
    ) -> ValidatorSnippetPackage:
        from memory_as_contracts.validator_installation import ValidatorSnippetVerifier

        pending = list(pending_examples or [])
        capsules = list(tool_capsules or [])
        examples = matched_action_examples(
            store.list_action_log_entries(),
            patterns=[*contract.check_patterns, *contract.update_patterns],
            session_id=session_id,
            task_id=task_id,
            limit_per_tool=2,
        )
        preflight = _preflight(contract, examples, pending, capsules)
        if preflight is not None:
            return preflight
        base_prompt = build_validator_generator_prompt(
            contract,
            committed_examples=examples,
            pending_examples=pending,
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
            package = _with_default_initial_state(
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
                pending_examples=pending,
                committed_examples=examples,
            )
            if verification.accepted:
                return package
            errors = verification.errors
            if attempt + 1 >= max_attempts:
                break
        return ValidatorSnippetPackage(
            status="manual_review",
            notes=["validator verification failed after retries", *errors],
        )


def build_validator_generator_prompt(
    contract: Contract,
    *,
    committed_examples: Sequence[ActionLogEntryV1],
    pending_examples: Sequence[dict[str, Any]],
    tool_capsules: Sequence[Any],
) -> str:
    rule_payload = {
        "id": contract.id,
        "text": contract.text,
        "effect": contract.effect.value,
        "authority": contract.authority.value,
        "scope": contract.scope.model_dump(mode="json"),
        "semantics": contract.semantics.model_dump(mode="json"),
        "validity": contract.validity.model_dump(mode="json", by_alias=True),
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
        "You are generating a validator for Memory-as-Contracts v4.",
        "",
        "IMMUTABLE RULE",
        _json(rule_payload),
        "",
        "ENFORCEMENT PLAN",
        _enforcement_summary(enforcement_payload),
        _json(enforcement_payload),
        "",
        "ACTION LOG ENTRY SCHEMA",
        _action_log_schema_doc(),
        "",
        "ACTION LOG SEARCH API",
        _search_api_doc(),
        "",
        "VERDICT API",
        _verdict_api_doc(),
        "",
        "RUNTIME VALUE SHAPES",
        _runtime_value_shapes_doc(),
        "",
        "SANDBOX CAPABILITIES",
        _sandbox_capabilities_doc(),
        "",
        "TOOL CAPSULES",
        _json([_dump_capsule(capsule) for capsule in relevant_tool_capsules]),
        "",
        "MATCHED COMMITTED ACTION EXAMPLES",
        _json([_compact_action_signature_example(entry) for entry in committed_examples]),
        "",
        "PENDING ACTION EXAMPLES",
        _pending_examples_doc(pending_examples),
        "",
            "TASK",
        (
            "Return one JSON object with status, snippet, initial_state, and notes. "
            "For check_update validators, initial_state must contain every state_fields key "
            "with zero, null, false, or empty-list defaults as appropriate. "
            "Do not hard-code literal values from examples; use them only to infer "
            "where relevant fields appear in action arguments or results. "
            "Before returning allow, verify that every Pending Action field needed "
            "to evaluate the relevant check_patterns is present and usable. If a "
            "required argument or target is missing, null, or unparsable, return ask. "
            "The snippet may define helper functions plus check(action, state, log, context) "
            "and update(state, entry, log, context). It must only use the provided "
            "log.search(spec) API and verdict helper functions. If evidence is insufficient, "
            "return status needs_refinement or manual_review instead of unsafe code."
        ),
    ]
    return "\n".join(sections)


def _preflight(
    contract: Contract,
    committed_examples: Sequence[ActionLogEntryV1],
    pending_examples: Sequence[dict[str, Any]],
    tool_capsules: Sequence[Any],
) -> ValidatorSnippetPackage | None:
    shape = contract.validator_enforcement_shape
    if shape == ValidatorEnforcementShape.NO_VALIDATOR:
        return ValidatorSnippetPackage(
            status="no_validator",
            notes=["contract does not request validator enforcement"],
        )
    if not tool_capsules:
        return ValidatorSnippetPackage(status="needs_refinement", notes=["missing tool capsules"])
    if not contract.check_patterns:
        return ValidatorSnippetPackage(status="needs_refinement", notes=["missing check patterns"])
    if shape == ValidatorEnforcementShape.CHECK_UPDATE and not contract.update_patterns:
        return ValidatorSnippetPackage(status="needs_refinement", notes=["missing update patterns"])
    if shape == ValidatorEnforcementShape.CHECK_UPDATE and not committed_examples:
        return ValidatorSnippetPackage(
            status="needs_refinement",
            notes=["missing committed action examples"],
        )
    return None


def _pending_examples_doc(pending_examples: Sequence[dict[str, Any]]) -> str:
    if pending_examples:
        return _json(list(pending_examples))
    return (
        "[]\n"
        "No pending action examples were available. Generate the validator from the "
        "immutable rule, enforcement plan, runtime value shapes, and tool capsules. "
        "Infer possible action argument locations from the tool capsule schemas, and "
        "write defensive checks that return ask when a required runtime field is "
        "missing, null, or unparsable."
    )


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


def _with_default_initial_state(
    contract: Contract,
    package: ValidatorSnippetPackage,
) -> ValidatorSnippetPackage:
    if package.status != "ready":
        return package
    if contract.validator_enforcement_shape != ValidatorEnforcementShape.CHECK_UPDATE:
        return package
    initial_state = dict(package.initial_state)
    for field in contract.state_fields:
        initial_state.setdefault(field, _default_state_value(field))
    return package.model_copy(update={"initial_state": initial_state})


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


def pending_action_examples(contract: Contract) -> list[dict[str, Any]]:
    """Build shape-only Pending Action examples from extractor-proposed bindings."""

    examples: list[dict[str, Any]] = []
    host_action = contract.semantics.actions[0] if contract.semantics.actions else ""
    for pattern in contract.check_patterns:
        arguments = {
            name: _representative_argument(name, matcher)
            for name, matcher in pattern.args.items()
        }
        examples.append(
            {
                "tool_name": pattern.tool,
                "host_action": host_action or pattern.tool,
                "arguments": arguments,
            }
        )
    return examples


def _representative_argument(name: str, matcher: Any) -> Any:
    if matcher.equals is not None:
        return matcher.equals
    if matcher.contains is not None:
        return matcher.contains
    if matcher.path_glob is not None:
        return matcher.path_glob.replace("**", "example").replace("*", "example")
    if matcher.mentions_path_glob is not None:
        return matcher.mentions_path_glob.replace("**", "example").replace("*", "example")
    if matcher.regex is not None:
        lowered = matcher.regex.lower()
        if "git" in lowered and "push" in lowered:
            return "git push origin main"
        if "pytest" in lowered or "test" in lowered:
            return "uv run pytest -q"
        return f"<value matching {matcher.regex}>"
    return f"<{name}>"


def _parse_package(raw: str) -> ValidatorSnippetPackage:
    try:
        payload = _normalize_package_payload(json.loads(_json_object_text(raw)))
        package = ValidatorSnippetPackage.model_validate(payload)
    except (json.JSONDecodeError, ValidationError, ValueError) as exc:
        return ValidatorSnippetPackage(status="manual_review", notes=[f"invalid generator response: {exc}"])
    if package.status == "ready" and not package.snippet:
        return ValidatorSnippetPackage(status="manual_review", notes=["ready response omitted snippet"])
    return package


def _normalize_package_payload(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("generator response must be an object")
    normalized = dict(payload)
    nested = normalized.get("validator") or normalized.get("package")
    if isinstance(nested, dict):
        normalized = {**normalized, **nested}

    snippet = (
        normalized.get("snippet")
        or normalized.get("code")
        or normalized.get("validator_code")
        or normalized.get("python")
    )
    if snippet is not None:
        normalized["snippet"] = _clean_snippet(str(snippet))

    status = str(normalized.get("status", "")).strip().lower()
    status_aliases = {
        "ok": "ready",
        "success": "ready",
        "valid": "ready",
        "complete": "ready",
        "completed": "ready",
        "needs refinement": "needs_refinement",
        "need_refinement": "needs_refinement",
        "manual review": "manual_review",
    }
    if status in status_aliases:
        normalized["status"] = status_aliases[status]
    elif status not in {"ready", "needs_refinement", "manual_review", "no_validator"}:
        normalized["status"] = "ready" if snippet else "manual_review"

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


def _action_log_schema_doc() -> str:
    return "\n".join(
        [
            "ActionLogEntryV1 fields:",
            "- seq: committed action order, integer",
            "- timestamp: ISO datetime",
            "- session_id, agent_id, adapter_id",
            "- tool_call_id, tool_name, host_action",
            "- arguments: raw assistant tool-call arguments",
            "- result: structured tool result when available",
            "- result_text: textual tool result",
            "- outcome: success | failure | unknown",
            "- reasoning_text: optional assistant reasoning metadata",
        ]
    )


def _runtime_value_shapes_doc() -> str:
    return "\n".join(
        [
            "- action is a dict with tool_name, host_action, arguments, targets, and context fields.",
            "- entry is a dict matching ActionLogEntryV1.",
            "- state is a dict owned by this validator.",
            "- context is a dict with runtime metadata.",
            "- log is the only object; call log.search(spec).",
            "Use action.get(...) and entry.get(...) for field access.",
            "Do not use getattr, hasattr, action.field, or entry.field.",
        ]
    )


def _sandbox_capabilities_doc() -> str:
    return "\n".join(
        [
            "Only import math or re.",
            (
                "Available builtins: abs, all, any, bool, dict, enumerate, float, "
                "format, int, isinstance, len, list, max, min, range, round, set, "
                "sorted, str, sum, and tuple."
            ),
            "Do not assume any other builtin, module, filesystem, environment, or network API.",
            (
                "For check_update, check must be read-only: inspect the Pending Action "
                "and current state without mutating state or calling a helper that mutates it."
            ),
            (
                "For check_update, update must copy state, inspect entry.seq, and if that "
                "sequence is already recorded, return unchanged before applying any state transition."
            ),
            "For check_update, update must return a state dict on every path.",
            (
                "Do not reconcile or repair accumulated state inside check; replay and post-action "
                "update own state maintenance."
            ),
        ]
    )


def _search_api_doc() -> str:
    return "\n".join(
        [
            "Use log.search(spec) for bounded committed-action lookup.",
            'Required: {"from": "actions", "limit": N}.',
            "The where value MUST be an object mapping field names to operator objects.",
            "Do not use SQL strings, tuples, lambdas, or a list of clauses.",
            "Supported select/where fields include seq, timestamp, tool_name, host_action,",
            "outcome, arguments, result, result_text, reasoning_text, and any_text.",
            "Nested JSON fields are addressed with dot paths such as arguments.total.",
            "Supported operators: eq, ne, in, gt, gte, lt, lte, exists, missing, contains, regex.",
            "Always include limit as an integer from 1 through 100. Never use 0 or an unbounded limit.",
            "The runtime scopes search to the current session/task.",
            "Valid example:",
            _json(
                {
                    "from": "actions",
                    "select": ["seq", "tool_name", "arguments", "result_text"],
                    "where": {
                        "tool_name": {"eq": "Bash"},
                        "outcome": {"eq": "success"},
                        "any_text": {"regex": "pytest|uv run pytest"},
                    },
                    "order_by": [{"field": "seq", "direction": "desc"}],
                    "limit": 20,
                }
            ),
        ]
    )


def _verdict_api_doc() -> str:
    return "\n".join(
        [
            "Return allow(reason, evidence_refs=None, confidence=1.0) only when evidence is sufficient.",
            "Return reject(reason, evidence_refs=None, confidence=1.0) for definite violations.",
            "Return ask(reason, evidence_refs=None, confidence=1.0) when user input is required or evidence is insufficient.",
        ]
    )


def _dump_capsule(capsule: Any) -> Any:
    if hasattr(capsule, "as_dict"):
        return capsule.as_dict()
    if hasattr(capsule, "model_dump"):
        return capsule.model_dump(mode="json")
    if isinstance(capsule, dict):
        return capsule
    return str(capsule)
