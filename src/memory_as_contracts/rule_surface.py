from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from fnmatch import fnmatch
from typing import Any

from memory_as_contracts.models import (
    ActionLogEntryV1,
    ActionSignature,
    ArgPattern,
    Contract,
    MatchOutcome,
    RuleEffect,
    RulePatternVersion,
    ScopeLevel,
    ToolPattern,
    ValidatorVersion,
)


_STOP_WORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "be",
    "before",
    "do",
    "for",
    "from",
    "i",
    "in",
    "is",
    "it",
    "me",
    "my",
    "of",
    "on",
    "or",
    "the",
    "this",
    "to",
    "until",
    "with",
    "you",
}


@dataclass(frozen=True)
class RuleBinding:
    outcome: MatchOutcome
    scope_key: str | None = None

    @property
    def matched(self) -> bool:
        return self.outcome == MatchOutcome.MATCHED


def contract_operational_surface(contract: Contract) -> dict[str, Any]:
    return {
        "effect": contract.effect.value,
        "modality": contract.modality.value,
        "scope": contract.scope.model_dump(mode="json"),
        "lifecycle": {
            "type": contract.lifecycle.type.value,
            "expires_at": (
                contract.lifecycle.expires_at.isoformat()
                if contract.lifecycle.expires_at is not None
                else None
            ),
            "until_revoked": contract.lifecycle.until_revoked,
            "trigger_event": contract.lifecycle.trigger_event,
            "review_after": (
                contract.lifecycle.review_after.isoformat()
                if contract.lifecycle.review_after is not None
                else None
            ),
            "validity_until": (
                contract.validity.until.isoformat()
                if contract.validity.until is not None
                else None
            ),
        },
        "semantics_actions": sorted(contract.semantics.actions),
        "validator_enforcement_shape": contract.validator_enforcement_shape.value,
        "check_patterns": canonical_pattern_payloads(contract.check_patterns),
        "update_patterns": canonical_pattern_payloads(contract.update_patterns),
        "state_fields": sorted(contract.state_fields),
    }


def contract_dedup_fingerprint(contract: Contract) -> str:
    """Exact-ish duplicate key for same rule surface plus normalized text."""

    return _hash(
        {
            **contract_operational_surface(contract),
            "normalized_text_tokens": _normalized_text_tokens(contract.text),
        }
    )


def contract_pattern_surface_hash(contract: Contract) -> str:
    """Operational duplicate key for differently worded rules on the same surface."""

    return _hash(contract_operational_surface(contract))


def has_same_operational_surface(left: Contract, right: Contract) -> bool:
    if left.effect not in {RuleEffect.DENY, RuleEffect.ALLOW}:
        return False
    if _text_similarity(left.text, right.text) >= 0.2:
        return False
    if _is_generic_broader_clause(left.text, right.text) or _is_generic_broader_clause(
        right.text, left.text
    ):
        return False
    return (
        left.effect == right.effect
        and left.modality == right.modality
        and left.scope == right.scope
        and set(left.semantics.actions) == set(right.semantics.actions)
        and canonical_tool_patterns(left.check_patterns)
        == canonical_tool_patterns(right.check_patterns)
        and enforcement_equivalent(left, right)
        and lifecycle_equivalent(left, right)
    )


def enforcement_equivalent(left: Contract, right: Contract) -> bool:
    return (
        left.validator_enforcement_shape == right.validator_enforcement_shape
        and canonical_tool_patterns(left.check_patterns)
        == canonical_tool_patterns(right.check_patterns)
        and canonical_tool_patterns(left.update_patterns)
        == canonical_tool_patterns(right.update_patterns)
        and set(left.state_fields) == set(right.state_fields)
    )


def lifecycle_equivalent(left: Contract, right: Contract) -> bool:
    return (
        left.lifecycle.type == right.lifecycle.type
        and left.lifecycle.expires_at == right.lifecycle.expires_at
        and left.lifecycle.until_revoked == right.lifecycle.until_revoked
        and left.lifecycle.trigger_event == right.lifecycle.trigger_event
        and left.lifecycle.review_after == right.lifecycle.review_after
        and left.validity.until == right.validity.until
    )


def canonical_tool_patterns(patterns: list[ToolPattern]) -> tuple[str, ...]:
    return tuple(
        sorted(
            json.dumps(pattern.model_dump(mode="json"), sort_keys=True)
            for pattern in patterns
        )
    )


def canonical_pattern_payloads(patterns: list[Any]) -> list[dict[str, Any]]:
    payloads = [
        pattern.model_dump(mode="json", exclude_none=True)
        if hasattr(pattern, "model_dump")
        else pattern
        for pattern in patterns
    ]
    return sorted(payloads, key=lambda item: json.dumps(item, sort_keys=True))


def evaluate_patterns(
    patterns: list[ToolPattern],
    signature: ActionSignature,
) -> MatchOutcome:
    if not patterns:
        return MatchOutcome.NOT_MATCHED
    return (
        MatchOutcome.MATCHED
        if any(tool_pattern_matches(pattern, signature) for pattern in patterns)
        else MatchOutcome.NOT_MATCHED
    )


def evaluate_rule_pattern_version(
    predicate: RulePatternVersion,
    signature: ActionSignature,
) -> MatchOutcome:
    return evaluate_patterns(predicate.check_patterns, signature)


def bind_check_patterns(
    contract: Contract,
    signature: ActionSignature,
    patterns: list[ToolPattern],
) -> RuleBinding:
    del contract
    return RuleBinding(outcome=evaluate_patterns(patterns, signature))


def bind_validator_check(
    contract: Contract,
    version: ValidatorVersion,
    signature: ActionSignature,
) -> RuleBinding:
    outcome = evaluate_patterns(version.check_patterns, signature)
    return RuleBinding(
        outcome=outcome,
        scope_key=validator_scope_key_for_signature(contract, signature)
        if outcome == MatchOutcome.MATCHED
        else None,
    )


def bind_contract_check_patterns(
    contract: Contract,
    signature: ActionSignature,
) -> RuleBinding:
    outcome = evaluate_patterns(contract.check_patterns, signature)
    return RuleBinding(
        outcome=outcome,
        scope_key=validator_scope_key_for_signature(contract, signature)
        if outcome == MatchOutcome.MATCHED
        else None,
    )


def bind_validator_update(
    contract: Contract,
    version: ValidatorVersion,
    entry: ActionLogEntryV1,
    signature: ActionSignature,
) -> RuleBinding:
    outcome = evaluate_patterns(version.update_patterns, signature)
    return RuleBinding(
        outcome=outcome,
        scope_key=validator_scope_key_for_entry(contract, entry)
        if outcome == MatchOutcome.MATCHED
        else None,
    )


def tool_pattern_matches(pattern: ToolPattern, signature: ActionSignature) -> bool:
    if pattern.tool != "*" and pattern.tool != signature.tool.name:
        return False
    return all(
        arg_pattern_matches(signature.tool.raw_arguments.get(key), matcher)
        for key, matcher in pattern.args.items()
    )


def arg_pattern_matches(value: Any, matcher: ArgPattern) -> bool:
    if matcher.is_empty():
        return True
    if value is None:
        return False
    text = str(value)
    if matcher.equals is not None and value != matcher.equals:
        return False
    if matcher.contains is not None and matcher.contains not in text:
        return False
    if matcher.regex is not None:
        try:
            if re.search(matcher.regex, text) is None:
                return False
        except re.error:
            return False
    if matcher.path_glob is not None and not path_value_matches(text, matcher.path_glob):
        return False
    if matcher.mentions_path_glob is not None and not text_mentions_path_glob(
        text, matcher.mentions_path_glob
    ):
        return False
    return True


def path_value_matches(value: str, glob: str) -> bool:
    if fnmatch(value, glob):
        return True
    if glob.startswith("**/") and fnmatch(value, glob.removeprefix("**/")):
        return True
    if "/" not in glob and (value == glob or value.endswith(f"/{glob}")):
        return True
    return False


def text_mentions_path_glob(text: str, glob: str) -> bool:
    prefix = glob.split("*", 1)[0].rstrip("/")
    if prefix and prefix in text:
        return True
    candidates = re.findall(r"[A-Za-z0-9_./-]+", text)
    return any(path_value_matches(candidate, glob) for candidate in candidates)


def validator_scope_key_for_signature(
    contract: Contract,
    signature: ActionSignature,
) -> str:
    return validator_scope_key(
        contract,
        session_id=signature.session.session_id,
        workspace=signature.workspace.cwd,
        repo=signature.workspace.repo,
        branch=signature.workspace.branch,
        user_id=signature.session.user_id,
        turn_id=signature.session.turn_id,
    )


def validator_scope_key_for_entry(
    contract: Contract,
    entry: ActionLogEntryV1,
) -> str:
    return validator_scope_key(
        contract,
        session_id=entry.session_id,
        workspace=entry.workspace,
        repo=entry.repo,
        branch=entry.branch,
        user_id=entry.user_id,
        turn_id=entry.turn_id,
    )


def validator_scope_key(
    contract: Contract,
    *,
    session_id: str,
    workspace: str | None,
    repo: str | None,
    branch: str | None = None,
    user_id: str | None = None,
    turn_id: str | None = None,
) -> str:
    """Scope keys must only use inputs available at install, check, and update time."""

    payload = {
        "contract_id": contract.id,
        "scope_level": contract.scope.level.value,
    }
    level = contract.scope.level
    if level == ScopeLevel.SESSION:
        payload["session_id"] = session_id
    elif level == ScopeLevel.PATH:
        payload.update(
            workspace=contract.scope.workspace or workspace,
            path=contract.scope.path,
        )
    elif level == ScopeLevel.MODULE:
        payload.update(
            workspace=contract.scope.workspace or workspace,
            project=contract.scope.project or repo or workspace,
            module=contract.scope.module,
        )
    elif level == ScopeLevel.PROJECT:
        payload.update(
            workspace=contract.scope.workspace or workspace,
            project=contract.scope.project or repo or workspace,
        )
    elif level == ScopeLevel.WORKSPACE:
        payload["workspace"] = contract.scope.workspace or workspace
    elif level == ScopeLevel.GLOBAL:
        payload["user_id"] = contract.scope.user_id or user_id
    else:
        payload.update(
            session_id=session_id,
            workspace=workspace,
            repo=repo,
            branch=branch,
            user_id=user_id,
        )
    return _hash(payload)


def _normalized_text_tokens(text: str) -> list[str]:
    tokens: list[str] = []
    seen: set[str] = set()
    for token in re.findall(r"[a-z0-9_]+", text.lower()):
        if len(token) < 2 or token in _STOP_WORDS or token in seen:
            continue
        tokens.append(token)
        seen.add(token)
    return tokens


def _text_similarity(left: str, right: str) -> float:
    left_words = set(_normalized_text_tokens(left))
    right_words = set(_normalized_text_tokens(right))
    if not left_words or not right_words:
        return 0.0
    return len(left_words.intersection(right_words)) / len(left_words.union(right_words))


def _is_generic_broader_clause(candidate_text: str, existing_text: str) -> bool:
    candidate_lower = candidate_text.lower()
    existing_lower = existing_text.lower()
    generic_markers = ("anything", "do not publish", "do not browse")
    specific_markers = (
        "without asking",
        "asking",
        "approve",
        "approval",
        "git push",
        "web search",
    )
    return any(marker in candidate_lower for marker in generic_markers) and any(
        marker in existing_lower for marker in specific_markers
    )


def _hash(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
