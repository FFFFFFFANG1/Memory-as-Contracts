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
    matched_action_examples,
    pending_action_examples,
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
        pending_examples: Sequence[dict[str, Any]],
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
        snippet = parsed.snippet or ""
        tree = self._parse_structure(snippet, contract, errors)
        if tree is None:
            return ValidatorVerificationResult(accepted=False, errors=errors)
        missing_state = sorted(set(contract.state_fields) - set(parsed.initial_state))
        if missing_state:
            errors.append(f"initial state is missing fields: {', '.join(missing_state)}")
        if not pending_examples:
            errors.append("at least one pending action example is required")
        if errors:
            return ValidatorVerificationResult(accepted=False, errors=errors)

        version = ValidatorVersion(
            contract_id=contract.id,
            enforcement_shape=contract.validator_enforcement_shape,
            snippet=snippet,
            check_patterns=contract.check_patterns,
            update_patterns=contract.update_patterns,
            state_fields=contract.state_fields,
            status=PredicateStatus.REJECTED,
        )
        del task_id
        log = ActionLogView(store, session_id=session_id)
        initial_state = json.loads(json.dumps(parsed.initial_state))
        for pending in pending_examples:
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
                        "check must not modify input state; keep check read-only and do not "
                        "call helpers that mutate state"
                    )
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
            self._verify_updates(version, initial_state, committed_examples, log, errors)

        digest_payload = {
            "snippet": snippet,
            "shape": contract.validator_enforcement_shape.value,
            "check_patterns": [
                pattern.model_dump(mode="json") for pattern in contract.check_patterns
            ],
            "update_patterns": [
                pattern.model_dump(mode="json") for pattern in contract.update_patterns
            ],
            "state_fields": contract.state_fields,
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
        snippet: str,
        contract: Contract,
        errors: list[str],
    ) -> ast.Module | None:
        try:
            tree = ast.parse(snippet)
        except SyntaxError as exc:
            errors.append(f"syntax error: {exc}")
            return None
        functions = {
            node.name: node for node in tree.body if isinstance(node, ast.FunctionDef)
        }
        self._check_signature(functions.get("check"), "check", errors)
        if contract.validator_enforcement_shape == ValidatorEnforcementShape.CHECK_UPDATE:
            self._check_signature(functions.get("update"), "update", errors)
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
    def _check_signature(
        function: ast.FunctionDef | None,
        name: str,
        errors: list[str],
    ) -> None:
        expected = ["action", "state", "log", "context"] if name == "check" else [
            "state",
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
        if not entries:
            errors.append("check_update verification requires a committed action example")
            return
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


class ValidatorInstaller:
    """Install only snippets accepted by ValidatorSnippetVerifier."""

    def __init__(self, verifier: ValidatorSnippetVerifier | None = None) -> None:
        self.verifier = verifier or ValidatorSnippetVerifier()

    def install(
        self,
        contract: Contract,
        package: ValidatorSnippetPackage | dict[str, Any],
        *,
        store: ContractStore,
        session_id: str,
        task_id: str | None,
        pending_examples: Sequence[dict[str, Any]],
        committed_examples: Sequence[ActionLogEntryV1] = (),
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
            status = (
                ValidatorInstallationStatus.NEEDS_REFINEMENT
                if parsed.status == "needs_refinement"
                else ValidatorInstallationStatus.MANUAL_REVIEW
            )
            store.add_validator_installation(
                ValidatorInstallationRecord(
                    contract_id=contract.id,
                    status=status,
                    errors=list(parsed.notes),
                )
            )
            return ValidatorInstallationResult(status=status.value, validator_version=None, errors=list(parsed.notes))
        if (
            contract.validator_enforcement_shape == ValidatorEnforcementShape.CHECK_UPDATE
            and contract.scope.level.value == "global"
            and user_id is None
        ):
            errors = ["stateful global validators require user identity"]
            store.add_validator_installation(
                ValidatorInstallationRecord(
                    contract_id=contract.id,
                    status=ValidatorInstallationStatus.MANUAL_REVIEW,
                    errors=errors,
                )
            )
            return ValidatorInstallationResult(
                status=ValidatorInstallationStatus.MANUAL_REVIEW.value,
                validator_version=None,
                errors=errors,
            )
        if (
            contract.validator_enforcement_shape == ValidatorEnforcementShape.CHECK_UPDATE
            and not supports_post_action
        ):
            errors = ["check_update validators require reliable post-action capability"]
            store.add_validator_installation(
                ValidatorInstallationRecord(
                    contract_id=contract.id,
                    status=ValidatorInstallationStatus.MANUAL_REVIEW,
                    errors=errors,
                )
            )
            return ValidatorInstallationResult(
                status=ValidatorInstallationStatus.MANUAL_REVIEW.value,
                validator_version=None,
                errors=errors,
            )

        verification = self.verifier.verify(
            contract,
            parsed,
            store=store,
            session_id=session_id,
            task_id=task_id,
            pending_examples=pending_examples,
            committed_examples=committed_examples,
        )
        if not verification.accepted:
            store.add_validator_installation(
                ValidatorInstallationRecord(
                    contract_id=contract.id,
                    status=ValidatorInstallationStatus.MANUAL_REVIEW,
                    errors=verification.errors,
                )
            )
            return ValidatorInstallationResult(
                status=ValidatorInstallationStatus.MANUAL_REVIEW.value,
                validator_version=None,
                errors=verification.errors,
            )

        snippet = parsed.snippet or ""
        version = ValidatorVersion(
            contract_id=contract.id,
            enforcement_shape=contract.validator_enforcement_shape,
            snippet=snippet,
            check_patterns=contract.check_patterns,
            update_patterns=contract.update_patterns,
            state_fields=contract.state_fields,
            initial_state=parsed.initial_state,
            snippet_hash=hashlib.sha256(snippet.encode("utf-8")).hexdigest(),
            verification_hash=verification.verification_hash,
            verified_at=utc_now(),
            sandbox_policy_version="subprocess-v1",
            action_log_search_spec_version="ActionLogSearchSpecV1",
        )
        scope_key = validator_scope_key(
            contract,
            session_id=session_id,
            workspace=workspace or contract.scope.workspace,
            repo=repo or contract.scope.repo,
            branch=branch,
            user_id=user_id or contract.scope.user_id,
        )
        store.install_verified_validator_version(
            version,
            initial_state=parsed.initial_state,
            scope_key=scope_key,
        )
        store.add_validator_installation(
            ValidatorInstallationRecord(
                contract_id=contract.id,
                status=ValidatorInstallationStatus.INSTALLED,
                validator_version_id=version.id,
            )
        )
        return ValidatorInstallationResult(
            status=ValidatorInstallationStatus.INSTALLED.value,
            validator_version=version,
            errors=[],
        )


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
        pending = pending_action_examples(contract)
        committed = matched_action_examples(
            store.list_action_log_entries(),
            patterns=[*contract.check_patterns, *contract.update_patterns],
            session_id=session_id,
            task_id=task_id,
            limit_per_tool=2,
        )
        try:
            package = self.generator.generate_verified(
                contract,
                store=store,
                session_id=session_id,
                task_id=task_id,
                pending_examples=pending,
                tool_capsules=tool_capsules,
            )
        except LLMCallError as exc:
            package = ValidatorSnippetPackage(
                status="manual_review",
                notes=[str(exc)],
            )
        return self.installer.install(
            contract,
            package,
            store=store,
            session_id=session_id,
            task_id=task_id,
            pending_examples=pending,
            committed_examples=committed,
            user_id=user_id,
            workspace=workspace,
            repo=repo,
            branch=branch,
            organization=organization,
            supports_post_action=supports_post_action,
        )
