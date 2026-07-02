from __future__ import annotations

from fnmatch import fnmatch
import json

from memory_as_contracts.models import (
    ActionSignature,
    Contract,
    ContractEdge,
    ContractStatus,
    Lifecycle,
    Scope,
    ScopeLevel,
)


def lifecycle_is_active(lifecycle: Lifecycle, signature: ActionSignature | None = None) -> bool:
    now = signature.time.now if signature is not None else None
    return not lifecycle.is_expired(now)


def scope_matches(scope: Scope, signature: ActionSignature) -> bool:
    workspace_root = signature.workspace.root or signature.workspace.cwd
    if scope.user_id and signature.session.user_id and scope.user_id != signature.session.user_id:
        return False
    if scope.workspace and scope.workspace != workspace_root:
        return False

    if scope.level == ScopeLevel.GLOBAL:
        return True
    if scope.level == ScopeLevel.SESSION:
        return True
    if scope.level == ScopeLevel.WORKSPACE:
        return bool(scope.workspace and scope.workspace == workspace_root)
    if scope.level == ScopeLevel.PATH:
        if scope.workspace and scope.workspace != workspace_root:
            return False
        if not scope.path:
            return False
        haystack = [
            *signature.targets,
            _raw_arguments_text(signature),
        ]
        return any(_path_scope_matches(value, scope.path) for value in haystack)
    if scope.level == ScopeLevel.PROJECT:
        return _project_matches(scope, signature)
    if scope.level == ScopeLevel.MODULE:
        if not _project_matches(scope, signature) or not scope.module:
            return False
        module = scope.module.lower()
        haystack = " ".join(
            [
                signature.intent,
                *signature.targets,
                _raw_arguments_text(signature),
            ]
        ).lower()
        return module in haystack
    return False


def _raw_arguments_text(signature: ActionSignature) -> str:
    return json.dumps(signature.tool.raw_arguments, sort_keys=True)


def _project_matches(scope: Scope, signature: ActionSignature) -> bool:
    workspace_root = signature.workspace.root or signature.workspace.cwd
    project = scope.project or scope.workspace
    if scope.workspace and scope.workspace != workspace_root:
        return False
    if project is None:
        return False
    return project in {workspace_root, signature.workspace.repo}


def path_scope_matches(value: str, path_scope: str) -> bool:
    normalized = value.replace("\\", "/")
    scope = path_scope.replace("\\", "/").rstrip("/")
    if not scope:
        return False
    if fnmatch(normalized, scope) or fnmatch(normalized, f"{scope}/**"):
        return True
    return normalized == scope or normalized.startswith(f"{scope}/") or scope in normalized


def _path_scope_matches(value: str, path_scope: str) -> bool:
    return path_scope_matches(value, path_scope)


def contract_applies_to_signature(contract: Contract, signature: ActionSignature) -> bool:
    if contract.status not in {ContractStatus.ACTIVE, ContractStatus.PENDING_CONFLICT}:
        return False
    return lifecycle_is_active(contract.lifecycle, signature) and scope_matches(contract.scope, signature)


def edge_applies_to_signature(edge: ContractEdge, signature: ActionSignature) -> bool:
    if edge.status != ContractStatus.ACTIVE:
        return False
    return lifecycle_is_active(edge.lifecycle, signature) and scope_matches(edge.scope, signature)


def scope_specificity(scope: Scope) -> int:
    order = {
        ScopeLevel.MODULE: 80,
        ScopeLevel.PATH: 75,
        ScopeLevel.SESSION: 70,
        ScopeLevel.PROJECT: 50,
        ScopeLevel.WORKSPACE: 40,
        ScopeLevel.GLOBAL: 10,
    }
    return order[scope.level]
