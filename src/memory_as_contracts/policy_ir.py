from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from memory_as_contracts.models import (
    ActionLogEntryV1,
    ActionSignature,
    Contract,
    GateDecisionType,
    RuleEffect,
)
from memory_as_contracts.store import ContractStore


class IRModel(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class PredicateExpr(IRModel):
    field: str | None = None
    op: str
    value: Any = None
    all: list["PredicateExpr"] = Field(default_factory=list)
    any: list["PredicateExpr"] = Field(default_factory=list)
    not_: "PredicateExpr | None" = Field(default=None, alias="not")

    @field_validator("op")
    @classmethod
    def validate_op(cls, value: str) -> str:
        allowed = {
            "all",
            "any",
            "not",
            "eq",
            "ne",
            "in",
            "contains",
            "not_contains",
            "regex",
            "not_regex",
            "glob",
            "path_under",
            "lt",
            "lte",
            "gt",
            "gte",
            "exists",
            "missing",
            "json_object",
            "word_count_lte",
            "word_count_gte",
            "word_count_between",
            "char_count_lte",
            "char_count_gte",
            "char_count_between",
            "endswith",
            "startswith",
        }
        if value not in allowed:
            raise ValueError(f"unsupported predicate op: {value}")
        return value


class RuntimeTarget(IRModel):
    phase: str = "pre"
    tool: str | None = None
    tools: list[str] = Field(default_factory=list)
    action_family: str | None = None
    action_families: list[str] = Field(default_factory=list)
    args: PredicateExpr | None = None
    paths: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def normalize_aliases(self):
        if self.tool and self.tool not in self.tools:
            self.tools.insert(0, self.tool)
        if self.action_family and self.action_family not in self.action_families:
            self.action_families.insert(0, self.action_family)
        return self


class MonitorExpr(IRModel):
    source: str = "action_log"
    where: PredicateExpr | None = None
    aggregate: str = "exists"
    field: str | None = None
    distinct_by: str | None = None
    group_by: str | None = None
    window: str = "session"

    @field_validator("source")
    @classmethod
    def validate_source(cls, value: str) -> str:
        if value not in {"pending_action", "action_log", "response"}:
            raise ValueError(f"unsupported monitor source: {value}")
        return value


class ObligationExpr(IRModel):
    kind: str
    predicate: PredicateExpr | None = None
    monitor: MonitorExpr | None = None
    op: str | None = None
    value: Any = None


class PolicyIR(IRModel):
    text: str
    effect: str
    scope: dict[str, Any] = Field(default_factory=dict)
    valid_until: str | None = None
    target: RuntimeTarget = Field(default_factory=RuntimeTarget)
    obligation: ObligationExpr
    monitor: MonitorExpr | None = None
    unsupported_reason: str | None = None

    @field_validator("effect")
    @classmethod
    def validate_effect(cls, value: str) -> str:
        if value not in {"deny", "allow", "require"}:
            raise ValueError(f"unsupported effect: {value}")
        return value


PolicyIRSafetyDecision = Literal["allow_pre_hook", "demote_to_response", "disable_enforcement"]
PolicyIREffectivePhase = Literal["pre", "response", "disabled"]


@dataclass(frozen=True)
class PolicyIRSafetyResult:
    decision: PolicyIRSafetyDecision
    reason: str
    effective_phase: PolicyIREffectivePhase


class PolicyIRSafetyChecker:
    """Conservative safety pass for deciding whether a PolicyIR may block pre-tool.

    The checker is deliberately structural and host-independent. It prevents
    future-dependent requirements from self-locking the agent before the action
    log can contain the events needed to satisfy the requirement.
    """

    FUTURE_DEPENDENT_KINDS = {
        "prior_action",
        "required_tool_usage",
        "required_tool_evidence",
        "sequence",
        "same_step",
    }
    RESPONSE_KINDS = {
        "response",
        "response_format",
        "response_content",
        "response_length",
    }
    COUNT_KINDS = {
        "action_count",
        "specific_tool_count",
        "tool_count",
        "interaction_turn_count",
    }
    CURRENT_ACTION_KINDS = {"current_action", "path_access"}

    def check(self, contract: Contract) -> PolicyIRSafetyResult:
        policy = _policy(contract)
        if policy is None:
            return PolicyIRSafetyResult(
                decision="disable_enforcement",
                reason="invalid_policy_ir",
                effective_phase="disabled",
            )
        return self.check_policy(policy)

    def check_policy(self, policy: PolicyIR) -> PolicyIRSafetyResult:
        if policy.unsupported_reason:
            return PolicyIRSafetyResult(
                decision="disable_enforcement",
                reason="unsupported_policy",
                effective_phase="disabled",
            )

        target = policy.target
        obligation = policy.obligation
        kind = obligation.kind
        if target.phase == "response" or kind in self.RESPONSE_KINDS:
            return PolicyIRSafetyResult(
                decision="allow_pre_hook",
                reason="response_stage_requirement",
                effective_phase="response",
            )
        if target.phase == "post":
            return PolicyIRSafetyResult(
                decision="demote_to_response",
                reason="post_tool_not_blocking",
                effective_phase="response",
            )
        if policy.effect == "allow":
            return PolicyIRSafetyResult(
                decision="allow_pre_hook",
                reason="allow_policy",
                effective_phase="pre",
            )
        if policy.effect == "deny":
            if kind in self.CURRENT_ACTION_KINDS:
                return PolicyIRSafetyResult(
                    decision="allow_pre_hook",
                    reason="current_action_deny",
                    effective_phase="pre",
                )
            if kind in self.COUNT_KINDS and _is_upper_bound_obligation(obligation):
                return PolicyIRSafetyResult(
                    decision="allow_pre_hook",
                    reason="upper_bound_deny",
                    effective_phase="pre",
                )
            return PolicyIRSafetyResult(
                decision="demote_to_response",
                reason="future_dependent_deny",
                effective_phase="response",
            )

        if kind in self.COUNT_KINDS:
            if _is_upper_bound_obligation(obligation):
                return PolicyIRSafetyResult(
                    decision="allow_pre_hook",
                    reason="upper_bound_count",
                    effective_phase="pre",
                )
            return PolicyIRSafetyResult(
                decision="demote_to_response",
                reason="lower_bound_count_requires_future",
                effective_phase="response",
            )

        if kind in self.FUTURE_DEPENDENT_KINDS:
            monitor = obligation.monitor or policy.monitor or _count_monitor_for_policy(policy)
            if _target_is_generic_tool_call(target):
                return PolicyIRSafetyResult(
                    decision="demote_to_response",
                    reason="generic_tool_call_prior_action",
                    effective_phase="response",
                )
            if _monitor_overlaps_target(monitor, target):
                return PolicyIRSafetyResult(
                    decision="demote_to_response",
                    reason="self_lock_same_tool",
                    effective_phase="response",
                )
            if not _monitor_has_specific_action(monitor):
                return PolicyIRSafetyResult(
                    decision="demote_to_response",
                    reason="future_dependent_requirement",
                    effective_phase="response",
                )
            return PolicyIRSafetyResult(
                decision="allow_pre_hook",
                reason="safe_prior_action_gate",
                effective_phase="pre",
            )

        if kind in self.CURRENT_ACTION_KINDS and policy.effect == "require":
            return PolicyIRSafetyResult(
                decision="demote_to_response",
                reason="current_action_require_not_safe_pre",
                effective_phase="response",
            )

        return PolicyIRSafetyResult(
            decision="demote_to_response",
            reason="unknown_requirement_timing",
            effective_phase="response",
        )


@dataclass(frozen=True)
class PolicyEvaluation:
    matched: bool
    decision: GateDecisionType | None = None
    reason: str = ""
    evidence: dict[str, Any] | None = None


class PolicyIREvaluator:
    """Evaluate structured MAC PolicyIR without generated code or API calls."""

    def __init__(self, store: ContractStore) -> None:
        self.store = store

    def evaluate(self, contract: Contract, signature: ActionSignature) -> PolicyEvaluation:
        policy = _policy(contract)
        if policy is None:
            return PolicyEvaluation(matched=False)
        safety = PolicyIRSafetyChecker().check_policy(policy)
        if safety.effective_phase == "disabled":
            return PolicyEvaluation(matched=False, reason=safety.reason)
        if not _effective_target_matches(policy, safety, signature):
            return PolicyEvaluation(matched=False)

        kind = policy.obligation.kind
        ok, evidence = self._obligation_holds(policy, signature)
        evidence = _policy_evidence(policy, safety, evidence, ok=ok)
        if contract.effect == RuleEffect.ALLOW or policy.effect == "allow":
            return PolicyEvaluation(matched=True, evidence=evidence)
        if contract.effect == RuleEffect.DENY or policy.effect == "deny":
            should_reject = ok if _deny_rejects_when_obligation_holds(kind) else not ok
            if not should_reject:
                return PolicyEvaluation(matched=True, evidence=evidence)
            if _response_violation_is_diagnostic_only(safety, evidence):
                return PolicyEvaluation(
                    matched=True,
                    reason=f"Policy {contract.id} response-stage violation was recorded as diagnostic.",
                    evidence=evidence,
                )
            return PolicyEvaluation(
                matched=True,
                decision=GateDecisionType.REJECT,
                reason=f"Policy {contract.id} denied this action.",
                evidence=evidence,
            )
        if ok:
            return PolicyEvaluation(matched=True, evidence=evidence)
        if _response_violation_is_diagnostic_only(safety, evidence):
            return PolicyEvaluation(
                matched=True,
                reason=f"Policy {contract.id} response-stage requirement could not be safely enforced.",
                evidence=evidence,
            )
        return PolicyEvaluation(
            matched=True,
            decision=GateDecisionType.REJECT,
            reason=f"Policy {contract.id} requirement was not satisfied.",
            evidence=evidence,
        )

    def _obligation_holds(
        self,
        policy: PolicyIR,
        signature: ActionSignature,
    ) -> tuple[bool, dict[str, Any]]:
        obligation = policy.obligation
        kind = obligation.kind
        if kind in {"current_action", "path_access"}:
            predicate = obligation.predicate
            if predicate is None:
                return (policy.effect != "deny"), {"kind": kind}
            return _predicate_matches(predicate, _signature_event(signature)), {"kind": kind}

        if kind in {"response", "response_format", "response_content", "response_length"}:
            text = _response_text(signature)
            predicate = obligation.predicate or _predicate_from_response_value(obligation)
            return _predicate_matches(predicate, {"response": text}), {
                "kind": kind,
                "response_length": len(text),
            }

        if kind in {"action_count", "specific_tool_count", "tool_count", "interaction_turn_count"}:
            monitor = obligation.monitor or policy.monitor
            if monitor is None and policy.target.phase == "response":
                return False, {"kind": kind, "unsupported": True, "ambiguous": True, "reason": "missing_monitor"}
            monitor = monitor or _count_monitor_for_policy(policy)
            count = self._aggregate_count(signature, monitor)
            if _pending_action_matches_monitor(signature, monitor):
                count += 1
            op = obligation.op or _op_from_predicate(obligation.predicate) or "lte"
            value = obligation.value
            if value is None and obligation.predicate is not None:
                value = obligation.predicate.value
            return _compare_value(count, op, value), {"kind": kind, "count": count, "op": op, "value": value}

        if kind in {"prior_action", "required_tool_usage", "required_tool_evidence"}:
            monitor = obligation.monitor or policy.monitor
            if monitor is None:
                if policy.target.phase == "response":
                    return False, {
                        "kind": kind,
                        "unsupported": True,
                        "ambiguous": True,
                        "reason": "missing_monitor",
                    }
                monitor = _count_monitor_for_policy(policy)
            entries = self._matching_log_entries(signature, monitor)
            required = obligation.value
            if required is None:
                required = 1
            count = self._aggregate_entries(entries, monitor)
            return count >= int(required), {"kind": kind, "count": count, "required": int(required)}

        if kind in {"sequence", "same_step"}:
            monitor = obligation.monitor or policy.monitor
            if monitor is None:
                return False, {
                    "kind": kind,
                    "unsupported": True,
                    "ambiguous": True,
                    "reason": "missing_monitor",
                }
            entries = self._matching_log_entries(signature, monitor) if monitor is not None else []
            if kind == "same_step":
                lower, upper = _same_step_bounds(obligation.value)
                ok, group_key, count = _has_group_with_distinct_entries(entries, monitor, lower, upper)
                return ok, {"kind": kind, "group": group_key, "count": count, "min": lower, "max": upper}
            return bool(entries), {"kind": kind, "count": len(entries)}

        return False, {"kind": kind, "unsupported": True}

    def _matching_log_entries(
        self,
        signature: ActionSignature,
        monitor: MonitorExpr | None,
    ) -> list[ActionLogEntryV1]:
        entries = [
            entry
            for entry in self.store.list_action_log_entries()
            if entry.session_id == signature.session.session_id
        ]
        if monitor is None or monitor.where is None:
            return entries
        return [
            entry
            for entry in entries
            if _predicate_matches(monitor.where, _entry_event(entry))
        ]

    def _aggregate_count(self, signature: ActionSignature, monitor: MonitorExpr | None) -> int:
        entries = self._matching_log_entries(signature, monitor)
        return self._aggregate_entries(entries, monitor)

    def _aggregate_entries(
        self,
        entries: list[ActionLogEntryV1],
        monitor: MonitorExpr | None,
    ) -> int:
        if monitor is None:
            return len(entries)
        if monitor.group_by:
            return len({_entry_field_value(entry, monitor.group_by) for entry in entries})
        if monitor.aggregate == "distinct_count":
            field = monitor.distinct_by or monitor.field or "tool_name"
            return len({_entry_field_value(entry, field) for entry in entries})
        return len(entries)


def _policy(contract: Contract) -> PolicyIR | None:
    if contract.policy_ir is None:
        return None
    try:
        return PolicyIR.model_validate(contract.policy_ir)
    except ValueError:
        return None


def _policy_evidence(
    policy: PolicyIR,
    safety: PolicyIRSafetyResult,
    evidence: dict[str, Any],
    *,
    ok: bool,
) -> dict[str, Any]:
    enriched = dict(evidence)
    enriched.update(
        {
            "policy_text": policy.text,
            "policy_effect": policy.effect,
            "safety_decision": safety.decision,
            "safety_reason": safety.reason,
            "effective_phase": safety.effective_phase,
            "satisfied": ok,
        }
    )
    if not ok:
        hint, repairable = _repair_hint(policy, enriched)
        enriched["repair_hint"] = hint
        enriched["repairable"] = repairable
        if enriched.get("ambiguous") or enriched.get("unsupported"):
            enriched["confidence"] = 0.0
        else:
            enriched["confidence"] = 1.0
    return enriched


def _response_violation_is_diagnostic_only(
    safety: PolicyIRSafetyResult,
    evidence: dict[str, Any],
) -> bool:
    if safety.effective_phase != "response":
        return False
    return bool(evidence.get("ambiguous") or evidence.get("unsupported"))


def _repair_hint(policy: PolicyIR, evidence: dict[str, Any]) -> tuple[str, bool]:
    kind = policy.obligation.kind
    if evidence.get("ambiguous") or evidence.get("unsupported"):
        return (
            "This constraint could not be deterministically checked from the runtime action log; revise only if you can verify it from prior tool results.",
            False,
        )
    if kind in {"response", "response_format", "response_content", "response_length"}:
        return "Revise the final response to satisfy this constraint, then retry send_message.", True
    if kind in {"prior_action", "required_tool_usage", "required_tool_evidence", "sequence", "same_step"}:
        action = _monitor_action_label(policy.obligation.monitor or policy.monitor)
        if action:
            return f"Call {action} before retrying send_message.", True
        return "Complete the required prior action before retrying send_message.", True
    if kind in {"action_count", "specific_tool_count", "tool_count", "interaction_turn_count"}:
        op = (policy.obligation.op or _op_from_predicate(policy.obligation.predicate) or "").lower()
        action = _monitor_action_label(policy.obligation.monitor or policy.monitor)
        target = f" for {action}" if action else ""
        if op in {"lt", "lte", "<", "<=", "eq", "=="}:
            return f"This action-count constraint{target} is already violated in the action log; avoid more matching calls.", False
        return f"Make additional matching calls{target} before retrying send_message.", True
    if kind in {"current_action", "path_access"}:
        return "Revise the tool call so the current action satisfies this constraint, then retry.", True
    return "Revise the action or final response to satisfy this constraint, then retry.", True


def _monitor_action_label(monitor: MonitorExpr | None) -> str:
    if monitor is None or monitor.where is None:
        return ""
    tools = sorted(_predicate_values_for_field(monitor.where, "tool_name"))
    if tools:
        return ", ".join(tools[:3])
    families = sorted(_predicate_values_for_field(monitor.where, "action_family"))
    if families:
        return "action family " + ", ".join(families[:3])
    return ""


def policy_target_matches(contract: Contract, signature: ActionSignature) -> bool:
    """Return whether a structured PolicyIR target applies to this action."""
    policy = _policy(contract)
    if policy is None:
        return False
    safety = PolicyIRSafetyChecker().check_policy(policy)
    if safety.effective_phase == "disabled":
        return False
    return _effective_target_matches(policy, safety, signature)


def policy_ir_safety(contract: Contract) -> PolicyIRSafetyResult:
    return PolicyIRSafetyChecker().check(contract)


def _effective_target_matches(
    policy: PolicyIR,
    safety: PolicyIRSafetyResult,
    signature: ActionSignature,
) -> bool:
    if safety.effective_phase == "response":
        return signature.tool.name == "send_message"
    return _target_matches(policy.target, signature)


def _target_matches(target: RuntimeTarget, signature: ActionSignature) -> bool:
    if target.phase == "response" and signature.tool.name != "send_message":
        return False
    tools = set(target.tools)
    if tools and signature.tool.name not in tools:
        return False
    families = {_normalize_family(item) for item in target.action_families}
    if families:
        actual = _signature_action_families(signature)
        if not families.intersection(actual):
            return False
    if target.args is not None and not _predicate_matches(target.args, _signature_event(signature)):
        return False
    if target.paths:
        targets = [path.replace("\\", "/") for path in signature.targets]
        if not any(_path_matches(path, pattern) for path in targets for pattern in target.paths):
            return False
    return True


def _signature_event(signature: ActionSignature) -> dict[str, Any]:
    return {
        "tool": signature.tool.name,
        "tool_name": signature.tool.name,
        "host_action": signature.host_action,
        "action_family": _generic_action_family(signature.tool.name, signature.host_action),
        "action_families": sorted(_signature_action_families(signature)),
        "turn_id": signature.session.turn_id,
        "tags": signature.canonical_tags,
        "args": signature.tool.raw_arguments,
        "response": _response_text(signature),
        "targets": signature.targets,
    }


def _entry_event(entry: ActionLogEntryV1) -> dict[str, Any]:
    return {
        "tool": entry.tool_name,
        "tool_name": entry.tool_name,
        "host_action": entry.host_action,
        "action_family": _generic_action_family(entry.tool_name, entry.host_action),
        "action_families": sorted(_entry_action_families(entry)),
        "seq": entry.seq,
        "turn_id": entry.turn_id,
        "args": entry.arguments,
        "result_text": entry.result_text,
        "response": _arg_text(entry.arguments, "response"),
        "targets": entry.targets,
        "outcome": entry.outcome.value,
    }


def _predicate_matches(predicate: PredicateExpr, data: dict[str, Any]) -> bool:
    op = predicate.op
    if op == "all":
        return all(_predicate_matches(child, data) for child in predicate.all)
    if op == "any":
        return any(_predicate_matches(child, data) for child in predicate.any)
    if op == "not":
        return not (predicate.not_ is not None and _predicate_matches(predicate.not_, data))

    value = _field_value(data, predicate.field or "response")
    expected = predicate.value
    if op == "eq":
        if isinstance(value, list):
            return expected in value
        return value == expected
    if op == "ne":
        if isinstance(value, list):
            return expected not in value
        return value != expected
    if op == "in":
        if isinstance(value, list):
            return any(item in (expected or []) for item in value)
        return value in (expected or [])
    if op == "contains":
        return str(expected) in str(value or "")
    if op == "not_contains":
        return str(expected) not in str(value or "")
    if op == "regex":
        try:
            return re.search(str(expected), str(value or ""), flags=re.I | re.S) is not None
        except re.error:
            return False
    if op == "not_regex":
        try:
            return re.search(str(expected), str(value or ""), flags=re.I | re.S) is None
        except re.error:
            return True
    if op == "glob":
        return _path_matches(str(value or ""), str(expected or ""))
    if op == "path_under":
        return _path_matches(str(value or ""), str(expected or ""))
    if op == "lt":
        return value is not None and value < expected
    if op == "lte":
        return value is not None and value <= expected
    if op == "gt":
        return value is not None and value > expected
    if op == "gte":
        return value is not None and value >= expected
    if op == "exists":
        return value is not None and value != ""
    if op == "missing":
        return value is None or value == ""
    if op == "json_object":
        try:
            parsed = json.loads(str(value or ""))
        except json.JSONDecodeError:
            return False
        if not isinstance(parsed, dict):
            return False
        if isinstance(expected, dict):
            keys = expected.get("required_keys", [])
        elif isinstance(expected, str):
            try:
                expected_payload = json.loads(expected)
            except json.JSONDecodeError:
                expected_payload = {}
            keys = list(expected_payload) if isinstance(expected_payload, dict) else []
        else:
            keys = []
        return all(key in parsed for key in keys)
    if op == "word_count_lte":
        return len(str(value or "").split()) <= int(expected)
    if op == "word_count_gte":
        return len(str(value or "").split()) >= int(expected)
    if op == "word_count_between":
        lower, upper = _range_bounds(expected)
        count = len(str(value or "").split())
        return (lower is None or count >= lower) and (upper is None or count <= upper)
    if op == "char_count_lte":
        return len(str(value or "")) <= int(expected)
    if op == "char_count_gte":
        return len(str(value or "")) >= int(expected)
    if op == "char_count_between":
        lower, upper = _range_bounds(expected)
        count = len(str(value or ""))
        return (lower is None or count >= lower) and (upper is None or count <= upper)
    if op == "endswith":
        return str(value or "").strip().endswith(str(expected))
    if op == "startswith":
        return str(value or "").strip().startswith(str(expected))
    return False


def _field_value(value: Any, field: str) -> Any:
    current = value
    for part in field.split("."):
        if isinstance(current, dict):
            current = current.get(part)
        else:
            return None
    return current


def _entry_field_value(entry: ActionLogEntryV1, field: str) -> Any:
    return _field_value(_entry_event(entry), field)


def _range_bounds(value: Any) -> tuple[int | None, int | None]:
    if isinstance(value, dict):
        lower = value.get("min", value.get("gte", value.get("lower")))
        upper = value.get("max", value.get("lte", value.get("upper")))
    elif isinstance(value, (list, tuple)):
        lower = value[0] if len(value) > 0 else None
        upper = value[1] if len(value) > 1 else None
    else:
        lower = None
        upper = value
    return (
        int(lower) if lower is not None else None,
        int(upper) if upper is not None else None,
    )


def _arg_text(arguments: Any, key: str) -> str:
    if isinstance(arguments, dict):
        value = arguments.get(key)
        return value if isinstance(value, str) else ""
    return ""


def _response_text(signature: ActionSignature) -> str:
    return _arg_text(signature.tool.raw_arguments, "response")


def _predicate_from_response_value(obligation: ObligationExpr) -> PredicateExpr:
    if obligation.op:
        return PredicateExpr(field="response", op=obligation.op, value=obligation.value)
    return PredicateExpr(field="response", op="exists")


def _count_monitor_for_policy(policy: PolicyIR) -> MonitorExpr:
    tools = policy.target.tools
    if tools:
        where = PredicateExpr(field="tool_name", op="in", value=tools)
    else:
        where = PredicateExpr(field="action_family", op="eq", value=policy.target.action_family or "")
    return MonitorExpr(where=where, aggregate="count")


def _pending_action_matches_monitor(
    signature: ActionSignature,
    monitor: MonitorExpr | None,
) -> bool:
    if monitor is None or monitor.source != "action_log" or monitor.where is None:
        return False
    return _predicate_matches(monitor.where, _signature_event(signature))


def _is_upper_bound_obligation(obligation: ObligationExpr) -> bool:
    op = (obligation.op or _op_from_predicate(obligation.predicate) or "").lower()
    return op in {"lt", "lte", "<", "<="}


def _deny_rejects_when_obligation_holds(kind: str) -> bool:
    return kind in {
        "current_action",
        "path_access",
        "response",
        "response_format",
        "response_content",
        "response_length",
    }


def _target_is_generic_tool_call(target: RuntimeTarget) -> bool:
    tools = set(target.tools)
    families = {_normalize_family(item) for item in target.action_families}
    return (
        not tools
        and not target.args
        and not target.paths
        and (not families or families == {"tool.call"})
    )


def _monitor_overlaps_target(monitor: MonitorExpr | None, target: RuntimeTarget) -> bool:
    if monitor is None or monitor.where is None:
        return False
    target_tools = set(target.tools)
    target_families = {_normalize_family(item) for item in target.action_families}
    monitor_tools = _predicate_values_for_field(monitor.where, "tool_name")
    monitor_families = {
        _normalize_family(value)
        for value in _predicate_values_for_field(monitor.where, "action_family")
    }
    if target_tools and target_tools.intersection(monitor_tools):
        return True
    if target_families and target_families.intersection(monitor_families):
        return True
    if "tool.call" in target_families and (monitor_tools or "tool.call" in monitor_families):
        return True
    if not target_tools and not target_families and (monitor_tools or monitor_families):
        return True
    return False


def _monitor_has_specific_action(monitor: MonitorExpr | None) -> bool:
    if monitor is None or monitor.where is None:
        return False
    tools = _predicate_values_for_field(monitor.where, "tool_name")
    families = {
        _normalize_family(value)
        for value in _predicate_values_for_field(monitor.where, "action_family")
    }
    return bool(tools or (families and families != {"tool.call"}))


def _predicate_values_for_field(predicate: PredicateExpr, field: str) -> set[str]:
    values: set[str] = set()
    if predicate.op in {"all", "any"}:
        for child in [*predicate.all, *predicate.any]:
            values.update(_predicate_values_for_field(child, field))
        return values
    if predicate.op == "not" and predicate.not_ is not None:
        return _predicate_values_for_field(predicate.not_, field)
    if predicate.field != field:
        return values
    if predicate.op == "eq":
        if predicate.value is not None:
            values.add(str(predicate.value))
    elif predicate.op == "in" and isinstance(predicate.value, list):
        values.update(str(value) for value in predicate.value if value is not None)
    return values


def _op_from_predicate(predicate: PredicateExpr | None) -> str | None:
    if predicate is None:
        return None
    return predicate.op if predicate.op in {"lt", "lte", "gt", "gte", "eq", "ne"} else None


def _compare(left: int, op: str, right: int) -> bool:
    if op in {"lt", "<"}:
        return left < right
    if op in {"lte", "<="}:
        return left <= right
    if op in {"gt", ">"}:
        return left > right
    if op in {"gte", ">="}:
        return left >= right
    if op in {"eq", "=="}:
        return left == right
    if op in {"ne", "!="}:
        return left != right
    return False


def _compare_value(left: int, op: str, value: Any) -> bool:
    normalized = (op or "").lower()
    if normalized in {"between", "range"}:
        lower, upper = _range_bounds(value)
        return (lower is None or left >= lower) and (upper is None or left <= upper)
    right = 0 if value is None else int(value)
    return _compare(left, normalized, right)


def _has_group_with_distinct_entries(
    entries: list[ActionLogEntryV1],
    monitor: MonitorExpr | None,
    minimum: int,
    maximum: int | None = None,
) -> tuple[bool, Any, int]:
    group_field = (monitor.group_by if monitor is not None else None) or "turn_id"
    distinct_field = (monitor.distinct_by if monitor is not None else None) or "tool_name"
    aggregate = monitor.aggregate if monitor is not None else "distinct_count"
    groups: dict[Any, set[Any] | int] = {}
    for entry in entries:
        group_key = _entry_field_value(entry, group_field)
        if group_key is None:
            group_key = entry.seq
        if aggregate == "count":
            groups[group_key] = int(groups.get(group_key, 0)) + 1
        else:
            bucket = groups.setdefault(group_key, set())
            if isinstance(bucket, set):
                bucket.add(_entry_field_value(entry, distinct_field))
    for group_key, values in groups.items():
        count = values if isinstance(values, int) else len(values)
        if count >= minimum and (maximum is None or count <= maximum):
            return True, group_key, count
    return False, None, 0


def _same_step_bounds(value: Any) -> tuple[int, int | None]:
    lower, upper = _range_bounds(value)
    if lower is None and upper is None:
        return 1, None
    if lower is None and upper is not None:
        return upper, upper
    return int(lower or 1), upper


def _normalize_family(value: str) -> str:
    normalized = value.lower().replace("_", ".").replace("-", ".")
    if normalized in {"agent.response", "final.respond", "send.message"}:
        return "message.send"
    if normalized == "response":
        return "message.send"
    if normalized in {"tool", "tool.call", "tool.execute", "external.tool"}:
        return "tool.call"
    return normalized


def _signature_action_families(signature: ActionSignature) -> set[str]:
    families = {
        _normalize_family(signature.host_action),
        *(_normalize_family(tag) for tag in signature.canonical_tags),
        _generic_action_family(signature.tool.name, signature.host_action),
    }
    return {family for family in families if family}


def _entry_action_families(entry: ActionLogEntryV1) -> set[str]:
    families = {
        _normalize_family(entry.host_action),
        _generic_action_family(entry.tool_name, entry.host_action),
    }
    return {family for family in families if family}


def _generic_action_family(tool_name: str, host_action: str) -> str:
    normalized_host = _normalize_family(host_action)
    normalized_tool = _normalize_family(tool_name)
    if normalized_host == "message.send" or normalized_tool == "message.send":
        return "message.send"
    if normalized_host in {
        "file.read",
        "file.write",
        "file.delete",
        "web.search",
        "email.send",
        "memory.write",
        "git.commit",
        "git.push",
        "dependency.install",
        "exec",
    }:
        return normalized_host
    return "tool.call"


def _path_matches(value: str, pattern: str) -> bool:
    value = value.replace("\\", "/").removeprefix("./")
    pattern = pattern.replace("\\", "/").removeprefix("./").rstrip("/")
    return (
        value == pattern
        or value.startswith(f"{pattern}/")
        or re.fullmatch(pattern.replace("**", ".*").replace("*", "[^/]*"), value) is not None
    )
