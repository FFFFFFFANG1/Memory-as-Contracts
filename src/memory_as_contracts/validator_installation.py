from __future__ import annotations

import ast
import hashlib
import json
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, Field

from memory_as_contracts.action_log import ActionLogView
from memory_as_contracts.extractor import LLMCallError
from memory_as_contracts.models import (
    ActionLogEntryV1,
    Contract,
    GateDecisionType,
    PredicateStatus,
    ToolPattern,
    ValidatorEnforcementShape,
    ValidatorInstallationRecord,
    ValidatorInstallationStatus,
    ValidatorVersion,
    utc_now,
)
from memory_as_contracts.runtime_scope import validator_scope_key
from memory_as_contracts.store import ContractStore
from memory_as_contracts.validator_generation import (
    ValidatorSnippetGenerator,
    ValidatorSnippetPackage,
)
from memory_as_contracts.validators import ValidatorSandboxError, ValidatorSandboxRunner


class ValidatorVerificationResult(BaseModel):
    accepted: bool
    errors: list[str] = Field(default_factory=list)
    verification_hash: str = ""


@dataclass(frozen=True)
class ValidatorInstallationResult:
    status: str
    validator_version: ValidatorVersion | None
    errors: list[str]


class ValidatorSnippetVerifier:
    """Validate snippet structure and behavior through the production sandbox."""

    def __init__(self, runner: ValidatorSandboxRunner | None = None) -> None:
        self.runner = runner or ValidatorSandboxRunner()

    def verify(
        self,
        contract: Contract,
        package: ValidatorSnippetPackage | dict[str, Any],
        *,
        store: ContractStore,
        session_id: str,
        task_id: str | None,
        committed_examples: Sequence[ActionLogEntryV1] = (),
    ) -> ValidatorVerificationResult:
        parsed = (
            package
            if isinstance(package, ValidatorSnippetPackage)
            else ValidatorSnippetPackage.model_validate(package)
        )
        errors: list[str] = []
        if not parsed.is_ready():
            return ValidatorVerificationResult(
                accepted=False,
                errors=[f"package status is {parsed.status}"],
            )
        check_code = parsed.check_code or ""
        check_tree = self._parse_structure(check_code, "check", errors)
        update_tree = None
        if contract.validator_enforcement_shape == ValidatorEnforcementShape.CHECK_UPDATE:
            if not parsed.update_code:
                errors.append("check_update validators must include update_code")
            else:
                update_tree = self._parse_structure(parsed.update_code, "update", errors)
        elif parsed.update_code:
            errors.append("check_only validators must not include update_code")
        if check_tree is None or (
            contract.validator_enforcement_shape == ValidatorEnforcementShape.CHECK_UPDATE
            and update_tree is None
        ):
            return ValidatorVerificationResult(accepted=False, errors=errors)
        missing_state = sorted(set(contract.state_fields) - set(parsed.shared_states))
        if missing_state:
            errors.append(f"shared_states is missing fields: {', '.join(missing_state)}")
        if errors:
            return ValidatorVerificationResult(accepted=False, errors=errors)

        version = ValidatorVersion(
            contract_id=contract.id,
            enforcement_shape=contract.validator_enforcement_shape,
            check_code=check_code,
            update_code=parsed.update_code,
            check_patterns=contract.check_patterns,
            update_patterns=contract.update_patterns,
            state_fields=contract.state_fields,
            shared_states=parsed.shared_states,
            status=PredicateStatus.REJECTED,
        )
        del task_id
        log = ActionLogView(store, session_id=session_id)
        initial_state = json.loads(json.dumps(parsed.shared_states))
        for pending in _verification_actions(contract):
            try:
                verdict, post_state = self.runner.inspect_check(
                    version,
                    action=dict(pending),
                    state=initial_state,
                    log=log,
                    context={"contract_id": contract.id, "verification": True},
                )
                if post_state != initial_state:
                    errors.append(
                        "check must not write shared state; use log.state_read only"
                    )
                if pending.get("arguments"):
                    incomplete = dict(pending)
                    incomplete["arguments"] = {}
                    incomplete_verdict, _ = self.runner.inspect_check(
                        version,
                        action=incomplete,
                        state=initial_state,
                        log=log,
                        context={"contract_id": contract.id, "verification": True},
                    )
                    if incomplete_verdict.decision == GateDecisionType.ALLOW:
                        errors.append("check unsafely allows an action with missing arguments")
                if verdict.decision not in set(GateDecisionType):
                    errors.append("check returned an invalid decision")
            except (ValidatorSandboxError, ValueError) as exc:
                errors.append(f"sandbox check failed: {exc}")

        if contract.validator_enforcement_shape == ValidatorEnforcementShape.CHECK_UPDATE:
            entries = list(committed_examples) or _verification_entries(
                contract,
                session_id=session_id,
            )
            self._verify_updates(version, initial_state, entries, log, errors)

        digest_payload = {
            "check_code": check_code,
            "update_code": parsed.update_code,
            "shape": contract.validator_enforcement_shape.value,
            "check_patterns": [
                pattern.model_dump(mode="json") for pattern in contract.check_patterns
            ],
            "update_patterns": [
                pattern.model_dump(mode="json") for pattern in contract.update_patterns
            ],
            "shared_states": parsed.shared_states,
        }
        verification_hash = hashlib.sha256(
            json.dumps(digest_payload, sort_keys=True).encode("utf-8")
        ).hexdigest()
        return ValidatorVerificationResult(
            accepted=not errors,
            errors=errors,
            verification_hash=verification_hash if not errors else "",
        )

    def _parse_structure(
        self,
        code: str,
        function_name: str,
        errors: list[str],
    ) -> ast.Module | None:
        try:
            tree = ast.parse(code)
        except SyntaxError as exc:
            errors.append(f"syntax error: {exc}")
            return None
        functions = {
            node.name: node for node in tree.body if isinstance(node, ast.FunctionDef)
        }
        self._check_signature(functions.get(function_name), function_name, errors)
        for node in tree.body:
            if isinstance(node, (ast.Assign, ast.AnnAssign)):
                value = node.value
                if isinstance(value, (ast.List, ast.Dict, ast.Set, ast.ListComp, ast.DictComp, ast.SetComp)):
                    errors.append("mutable global state is not allowed")
            elif isinstance(node, (ast.FunctionDef, ast.Import, ast.ImportFrom)):
                continue
            elif isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant):
                continue
            else:
                errors.append(f"unsupported top-level statement: {node.__class__.__name__}")
        self._check_mapping_access(tree, errors)
        self._check_log_access(tree, errors)
        return tree

    @staticmethod
    def _check_mapping_access(tree: ast.Module, errors: list[str]) -> None:
        mapping_names = {"action", "entry", "state", "context"}
        dict_methods = {
            "clear",
            "copy",
            "get",
            "items",
            "keys",
            "pop",
            "popitem",
            "setdefault",
            "update",
            "values",
        }
        seen: set[str] = set()
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id in {"getattr", "hasattr"}
                and node.args
                and isinstance(node.args[0], ast.Name)
                and node.args[0].id in mapping_names
            ):
                name = node.args[0].id
                seen.add(f"{name} is a dict; use {name}.get(...) or key access")
            if (
                isinstance(node, ast.Attribute)
                and isinstance(node.value, ast.Name)
                and node.value.id in mapping_names
                and node.attr not in dict_methods
            ):
                name = node.value.id
                seen.add(f"{name} is a dict; use {name}.get(...) or key access")
        errors.extend(sorted(seen))

    @staticmethod
    def _check_log_access(tree: ast.Module, errors: list[str]) -> None:
        allowed = {"read", "state_read", "state_write"}
        seen: set[str] = set()
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Attribute)
                and isinstance(node.value, ast.Name)
                and node.value.id == "log"
                and node.attr not in allowed
            ):
                seen.add(
                    "log only exposes read(...), state_read(...), and state_write(...)"
                )
        errors.extend(sorted(seen))

    @staticmethod
    def _check_signature(
        function: ast.FunctionDef | None,
        name: str,
        errors: list[str],
    ) -> None:
        expected = ["action", "log", "context"] if name == "check" else [
            "entry",
            "log",
            "context",
        ]
        if function is None:
            errors.append(f"missing {name} function")
            return
        actual = [argument.arg for argument in function.args.args]
        if actual != expected or function.args.vararg or function.args.kwarg:
            errors.append(f"{name} signature must be ({', '.join(expected)})")

    def _verify_updates(
        self,
        version: ValidatorVersion,
        initial_state: dict[str, Any],
        entries: Sequence[ActionLogEntryV1],
        log: ActionLogView,
        errors: list[str],
    ) -> None:
        state = json.loads(json.dumps(initial_state))
        try:
            for index, raw_entry in enumerate(entries, start=1):
                entry = raw_entry if raw_entry.seq is not None else raw_entry.model_copy(
                    update={"seq": index}
                )
                payload = entry.model_dump(mode="json")
                once = self.runner.update(
                    version,
                    state=state,
                    entry=payload,
                    log=log,
                    context={"contract_id": version.contract_id, "verification": True},
                )
                twice = self.runner.update(
                    version,
                    state=once,
                    entry=payload,
                    log=log,
                    context={"contract_id": version.contract_id, "verification": True},
                )
                if twice != once:
                    errors.append(
                        "update must be idempotent for a repeated entry: check entry.seq "
                        "against recorded sequence ids and return unchanged before adding "
                        "amounts, counters, or other state"
                    )
                    return
                state = once
            replay = json.loads(json.dumps(initial_state))
            for index, raw_entry in enumerate(entries, start=1):
                entry = raw_entry if raw_entry.seq is not None else raw_entry.model_copy(
                    update={"seq": index}
                )
                replay = self.runner.update(
                    version,
                    state=replay,
                    entry=entry.model_dump(mode="json"),
                    log=log,
                    context={"contract_id": version.contract_id, "verification": True, "replay": True},
                )
            if replay != state:
                errors.append("replay did not reproduce the same validator state")
        except (ValidatorSandboxError, ValueError) as exc:
            errors.append(f"sandbox update failed: {exc}")


def _verification_actions(contract: Contract) -> list[dict[str, Any]]:
    host_action = contract.semantics.actions[0] if contract.semantics.actions else ""
    return [
        {
            "tool_name": pattern.tool,
            "host_action": host_action or pattern.tool,
            "arguments": _representative_arguments(pattern),
        }
        for pattern in contract.check_patterns
    ]


def _verification_entries(
    contract: Contract,
    *,
    session_id: str,
) -> list[ActionLogEntryV1]:
    host_action = contract.semantics.actions[0] if contract.semantics.actions else ""
    return [
        ActionLogEntryV1(
            seq=index,
            session_id=session_id,
            agent_id="validator-verifier",
            adapter_id="validator-verifier",
            tool_call_id=f"verification-{contract.id}-{index}",
            tool_name=pattern.tool,
            host_action=host_action or pattern.tool,
            arguments=_representative_arguments(pattern),
        )
        for index, pattern in enumerate(contract.update_patterns, start=1)
    ]


def _representative_arguments(pattern: ToolPattern) -> dict[str, Any]:
    return {
        name: _representative_argument(name, matcher)
        for name, matcher in pattern.args.items()
    }


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


def _code_hash(check_code: str, update_code: str | None) -> str:
    payload = {
        "check_code": check_code,
        "update_code": update_code,
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()


class ValidatorInstaller:
    """Register validator hook packages already accepted by generate_verified."""

    def __init__(self, verifier: ValidatorSnippetVerifier | None = None) -> None:
        del verifier

    def register(
        self,
        contract: Contract,
        package: ValidatorSnippetPackage | dict[str, Any],
        *,
        store: ContractStore,
        session_id: str,
        task_id: str | None,
        user_id: str | None = None,
        workspace: str | None = None,
        repo: str | None = None,
        branch: str | None = None,
        organization: str | None = None,
        supports_post_action: bool = True,
    ) -> ValidatorInstallationResult:
        parsed = (
            package
            if isinstance(package, ValidatorSnippetPackage)
            else ValidatorSnippetPackage.model_validate(package)
        )
        if not parsed.is_ready():
            store.add_validator_installation(
                ValidatorInstallationRecord(
                    contract_id=contract.id,
                    status=ValidatorInstallationStatus.FAILED,
                    errors=list(parsed.notes),
                )
            )
            return ValidatorInstallationResult(
                status=ValidatorInstallationStatus.FAILED.value,
                validator_version=None,
                errors=list(parsed.notes),
            )
        if not parsed.verification_hash:
            errors = ["validator package is missing verification_hash"]
            store.add_validator_installation(
                ValidatorInstallationRecord(
                    contract_id=contract.id,
                    status=ValidatorInstallationStatus.FAILED,
                    errors=errors,
                )
            )
            return ValidatorInstallationResult(
                status=ValidatorInstallationStatus.FAILED.value,
                validator_version=None,
                errors=errors,
            )

        check_code = parsed.check_code or ""
        snippet_hash = _code_hash(check_code, parsed.update_code)
        version = ValidatorVersion(
            contract_id=contract.id,
            enforcement_shape=contract.validator_enforcement_shape,
            check_code=check_code,
            update_code=parsed.update_code,
            check_patterns=contract.check_patterns,
            update_patterns=contract.update_patterns,
            state_fields=sorted(parsed.shared_states),
            shared_states=parsed.shared_states,
            snippet_hash=snippet_hash,
            verification_hash=parsed.verification_hash,
            verified_at=utc_now(),
            sandbox_policy_version="subprocess-v1",
            action_log_search_spec_version="ActionLogSearchSpecV1",
        )
        scope_key = validator_scope_key(
            contract,
            session_id=session_id,
            workspace=workspace or contract.scope.workspace,
            repo=repo or contract.scope.project,
            branch=branch,
            user_id=user_id or contract.scope.user_id,
        )
        store.install_verified_validator_version(
            version,
            scope_key=scope_key,
        )
        store.add_validator_installation(
            ValidatorInstallationRecord(
                contract_id=contract.id,
                status=ValidatorInstallationStatus.SUCCESS,
                validator_version_id=version.id,
            )
        )
        return ValidatorInstallationResult(
            status=ValidatorInstallationStatus.SUCCESS.value,
            validator_version=version,
            errors=[],
        )

    def install(self, *args: Any, **kwargs: Any) -> ValidatorInstallationResult:
        return self.register(*args, **kwargs)


class ValidatorProvisioner:
    """Connect accepted contracts to generation, verification, and installation."""

    def __init__(
        self,
        generator: ValidatorSnippetGenerator,
        installer: ValidatorInstaller | None = None,
    ) -> None:
        self.generator = generator
        self.installer = installer or ValidatorInstaller()

    def provision(
        self,
        contract: Contract,
        *,
        store: ContractStore,
        session_id: str,
        task_id: str | None,
        tool_capsules: Sequence[Any],
        user_id: str | None = None,
        workspace: str | None = None,
        repo: str | None = None,
        branch: str | None = None,
        organization: str | None = None,
        supports_post_action: bool = True,
    ) -> ValidatorInstallationResult:
        if (
            contract.validator_enforcement_shape == ValidatorEnforcementShape.CHECK_UPDATE
            and contract.scope.level.value == "global"
            and user_id is None
        ):
            package = ValidatorSnippetPackage(
                status="fail",
                notes=["stateful global validators require user identity"],
            )
            return self.installer.register(
                contract,
                package,
                store=store,
                session_id=session_id,
                task_id=task_id,
                user_id=user_id,
                workspace=workspace,
                repo=repo,
                branch=branch,
                organization=organization,
                supports_post_action=supports_post_action,
            )
        if (
            contract.validator_enforcement_shape == ValidatorEnforcementShape.CHECK_UPDATE
            and not supports_post_action
        ):
            package = ValidatorSnippetPackage(
                status="fail",
                notes=["check_update validators require reliable post-action capability"],
            )
            return self.installer.register(
                contract,
                package,
                store=store,
                session_id=session_id,
                task_id=task_id,
                user_id=user_id,
                workspace=workspace,
                repo=repo,
                branch=branch,
                organization=organization,
                supports_post_action=supports_post_action,
            )
        try:
            package = self.generator.generate_verified(
                contract,
                store=store,
                session_id=session_id,
                task_id=task_id,
                tool_capsules=tool_capsules,
            )
        except LLMCallError as exc:
            package = ValidatorSnippetPackage(
                status="fail",
                notes=[str(exc)],
            )
        return self.installer.register(
            contract,
            package,
            store=store,
            session_id=session_id,
            task_id=task_id,
            user_id=user_id,
            workspace=workspace,
            repo=repo,
            branch=branch,
            organization=organization,
            supports_post_action=supports_post_action,
        )
