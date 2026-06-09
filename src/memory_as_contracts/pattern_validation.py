from __future__ import annotations

import json
import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

from memory_as_contracts.compiler import PolicyCompiler
from memory_as_contracts.models import (
    Contract,
    ContractKind,
    ContractStatus,
    RulePatternVersion,
    ToolPattern,
    ValidatorEnforcementShape,
)
from memory_as_contracts.store import ContractStore
from memory_as_contracts.tool_capsules import ToolCapabilityCapsule


PATTERN_REFINEMENT_SYSTEM_PROMPT = """
You repair operational tool patterns for a Memory-as-Contracts rule.
Return only valid JSON.

The rule text, effect, authority, scope, semantics, validity, source, lifecycle,
status, and validator enforcement shape are immutable. You may only rewrite
tool_patterns, check_patterns, and update_patterns. Tool names and argument
names must exist in the provided tool capsules. Every regex must compile.
""".strip()


@dataclass(frozen=True)
class PatternValidationIssue:
    code: str
    field: str
    message: str


@dataclass(frozen=True)
class PatternVerificationResult:
    accepted: bool
    issues: tuple[PatternValidationIssue, ...] = ()


@dataclass(frozen=True)
class PatternProvisioningResult:
    contract: Contract
    verification: PatternVerificationResult
    refined: bool = False


@dataclass(frozen=True)
class PatternInstallationResult:
    contract: Contract
    verification: PatternVerificationResult
    pattern_version: RulePatternVersion | None
    refined: bool = False


class PatternVerifier:
    """Validate LLM-proposed patterns against one adapter's native tool schemas."""

    def __init__(self, tool_capsules: Sequence[ToolCapabilityCapsule]) -> None:
        self.capsules = tuple(tool_capsules)
        self.tool_capsules = {capsule.name: capsule for capsule in self.capsules}

    def verify(self, contract: Contract) -> PatternVerificationResult:
        issues: list[PatternValidationIssue] = []
        if (
            contract.kind != ContractKind.FACT
            and contract.validator_enforcement_shape
            == ValidatorEnforcementShape.NO_VALIDATOR
            and not contract.tool_patterns
        ):
            issues.append(
                PatternValidationIssue(
                    code="missing_tool_patterns",
                    field="tool_patterns",
                    message="non-fact rules require at least one operational tool pattern",
                )
            )
        self._verify_group("tool_patterns", contract.tool_patterns, issues)

        shape = contract.validator_enforcement_shape
        if shape != ValidatorEnforcementShape.NO_VALIDATOR and not contract.check_patterns:
            issues.append(
                PatternValidationIssue(
                    code="missing_check_patterns",
                    field="check_patterns",
                    message="validator rules require at least one check pattern",
                )
            )
        self._verify_group("check_patterns", contract.check_patterns, issues)

        if shape == ValidatorEnforcementShape.CHECK_UPDATE and not contract.update_patterns:
            issues.append(
                PatternValidationIssue(
                    code="missing_update_patterns",
                    field="update_patterns",
                    message="check_update rules require at least one update pattern",
                )
            )
        self._verify_group("update_patterns", contract.update_patterns, issues)
        return PatternVerificationResult(accepted=not issues, issues=tuple(issues))

    def _verify_group(
        self,
        field: str,
        patterns: Sequence[ToolPattern],
        issues: list[PatternValidationIssue],
    ) -> None:
        for index, pattern in enumerate(patterns):
            pattern_field = f"{field}[{index}]"
            capsule = self.tool_capsules.get(pattern.tool)
            if pattern.tool == "agent.response":
                if pattern.args:
                    issues.append(
                        PatternValidationIssue(
                            code="unknown_argument",
                            field=f"{pattern_field}.args",
                            message="agent.response does not expose native arguments",
                        )
                    )
                continue
            if capsule is None:
                issues.append(
                    PatternValidationIssue(
                        code="unknown_tool",
                        field=f"{pattern_field}.tool",
                        message=f"tool {pattern.tool!r} is not present in adapter capsules",
                    )
                )
                self._verify_matchers(pattern_field, pattern, {}, issues)
                continue
            schema = dict(capsule.input_schema)
            properties = schema.get("properties", {}) if schema.get("type") == "object" else {}
            if not isinstance(properties, dict):
                properties = {}
            for argument in pattern.args:
                if argument not in properties:
                    issues.append(
                        PatternValidationIssue(
                            code="unknown_argument",
                            field=f"{pattern_field}.args.{argument}",
                            message=(
                                f"argument {argument!r} is not declared by "
                                f"tool {pattern.tool!r}"
                            ),
                        )
                    )
            self._verify_matchers(pattern_field, pattern, properties, issues)

    @staticmethod
    def _verify_matchers(
        pattern_field: str,
        pattern: ToolPattern,
        properties: dict[str, Any],
        issues: list[PatternValidationIssue],
    ) -> None:
        for argument, matcher in pattern.args.items():
            matcher_field = f"{pattern_field}.args.{argument}"
            if matcher.regex is not None:
                try:
                    re.compile(matcher.regex)
                except re.error as exc:
                    issues.append(
                        PatternValidationIssue(
                            code="invalid_regex",
                            field=f"{matcher_field}.regex",
                            message=str(exc),
                        )
                    )
            uses_text_matcher = any(
                value is not None
                for value in (
                    matcher.regex,
                    matcher.contains,
                    matcher.path_glob,
                    matcher.mentions_path_glob,
                )
            )
            property_schema = properties.get(argument)
            if (
                uses_text_matcher
                and isinstance(property_schema, dict)
                and property_schema.get("type") not in {None, "string"}
            ):
                issues.append(
                    PatternValidationIssue(
                        code="incompatible_argument_type",
                        field=matcher_field,
                        message=(
                            f"text matcher cannot be applied to "
                            f"{property_schema.get('type')!r}"
                        ),
                    )
                )


class PatternProvisioner:
    """Verify patterns and perform at most one synchronous LLM repair."""

    def __init__(
        self,
        *,
        verifier: PatternVerifier,
        response_provider: Callable[[str], str] | None = None,
    ) -> None:
        self.verifier = verifier
        self.response_provider = response_provider

    def provision(self, contract: Contract) -> PatternProvisioningResult:
        initial = self.verifier.verify(contract)
        if initial.accepted:
            return PatternProvisioningResult(contract=contract, verification=initial)
        if self.response_provider is None:
            return PatternProvisioningResult(
                contract=contract.model_copy(update={"status": ContractStatus.CANDIDATE}),
                verification=initial,
            )

        try:
            payload = _load_pattern_payload(
                self.response_provider(
                    _pattern_refinement_prompt(
                        contract,
                        initial,
                        self.verifier.capsules,
                    )
                )
            )
            refined = contract.model_copy(
                update={
                    "tool_patterns": [
                        ToolPattern.model_validate(item)
                        for item in payload["tool_patterns"]
                    ],
                    "check_patterns": [
                        ToolPattern.model_validate(item)
                        for item in payload["check_patterns"]
                    ],
                    "update_patterns": [
                        ToolPattern.model_validate(item)
                        for item in payload["update_patterns"]
                    ],
                }
            )
            verification = self.verifier.verify(refined)
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            verification = PatternVerificationResult(
                accepted=False,
                issues=(
                    *initial.issues,
                    PatternValidationIssue(
                        code="refinement_error",
                        field="pattern_refinement",
                        message=str(exc),
                    ),
                ),
            )
            refined = contract

        if verification.accepted:
            return PatternProvisioningResult(
                contract=refined.model_copy(
                    update={
                        "status": (
                            ContractStatus.ACTIVE
                            if contract.status == ContractStatus.CANDIDATE
                            else contract.status
                        )
                    }
                ),
                verification=verification,
                refined=True,
            )
        return PatternProvisioningResult(
            contract=refined.model_copy(update={"status": ContractStatus.CANDIDATE}),
            verification=verification,
            refined=True,
        )


class PatternInstaller:
    """Own the verify, compile, and active-version installation invariant."""

    def __init__(
        self,
        *,
        store: ContractStore,
        verifier: PatternVerifier,
        compiler: PolicyCompiler | None = None,
        response_provider: Callable[[str], str] | None = None,
    ) -> None:
        self.store = store
        self.provisioner = PatternProvisioner(
            verifier=verifier,
            response_provider=response_provider,
        )
        self.compiler = compiler or PolicyCompiler()

    def install(self, contract: Contract) -> PatternInstallationResult:
        provisioned = self.provisioner.provision(contract)
        installed_contract = self.store.add_contract(provisioned.contract)
        pattern_version = None
        if provisioned.verification.accepted and installed_contract.tool_patterns:
            compiled = self.compiler.compile(installed_contract)
            if compiled.has_binding_predicates():
                pattern_version = self.store.install_rule_pattern_version(compiled)
        return PatternInstallationResult(
            contract=installed_contract,
            verification=provisioned.verification,
            pattern_version=pattern_version,
            refined=provisioned.refined,
        )


def _pattern_refinement_prompt(
    contract: Contract,
    verification: PatternVerificationResult,
    tool_capsules: Sequence[ToolCapabilityCapsule],
) -> str:
    payload = {
        "immutable_rule": {
            "id": contract.id,
            "text": contract.text,
            "effect": contract.effect.value,
            "authority": contract.authority.value,
            "scope": contract.scope.model_dump(mode="json"),
            "semantics": contract.semantics.model_dump(mode="json"),
            "validity": contract.validity.model_dump(mode="json"),
            "validator_enforcement_shape": contract.validator_enforcement_shape.value,
            "state_fields": contract.state_fields,
        },
        "current_patterns": {
            "tool_patterns": [
                pattern.model_dump(mode="json") for pattern in contract.tool_patterns
            ],
            "check_patterns": [
                pattern.model_dump(mode="json") for pattern in contract.check_patterns
            ],
            "update_patterns": [
                pattern.model_dump(mode="json") for pattern in contract.update_patterns
            ],
        },
        "verification_errors": [
            {
                "code": issue.code,
                "field": issue.field,
                "message": issue.message,
            }
            for issue in verification.issues
        ],
        "tool_capsules": [capsule.as_dict() for capsule in tool_capsules],
    }
    return (
        f"{PATTERN_REFINEMENT_SYSTEM_PROMPT}\n\n"
        "Repair only the pattern fields listed in verification_errors. Return exactly:\n"
        '{"tool_patterns":[],"check_patterns":[],"update_patterns":[]}\n\n'
        f"Input:\n{json.dumps(payload, sort_keys=True)}"
    )


def _load_pattern_payload(raw: str) -> dict[str, list[dict[str, Any]]]:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        start = raw.find("{")
        end = raw.rfind("}")
        if start == -1 or end <= start:
            raise
        payload = json.loads(raw[start : end + 1])
    if not isinstance(payload, dict):
        raise ValueError("pattern refinement response must be a JSON object")
    result: dict[str, list[dict[str, Any]]] = {}
    for key in ("tool_patterns", "check_patterns", "update_patterns"):
        value = payload.get(key)
        if not isinstance(value, list):
            raise ValueError(f"{key} must be a list")
        result[key] = value
    return result
