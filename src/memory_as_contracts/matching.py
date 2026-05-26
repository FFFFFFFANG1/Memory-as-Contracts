from __future__ import annotations

from fnmatch import fnmatch

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
    if scope.agent_family and signature.agent_family not in scope.agent_family:
        return False
    if scope.user_id and signature.session.user_id and scope.user_id != signature.session.user_id:
        return False
    if scope.workspace and scope.workspace != signature.workspace.cwd:
        return False
    if scope.repo and signature.workspace.repo and scope.repo != signature.workspace.repo:
        return False
    if scope.task and signature.session.task_id and scope.task != signature.session.task_id:
        return False

    if scope.level == ScopeLevel.GLOBAL:
        return True
    if scope.level == ScopeLevel.ORGANIZATION:
        return bool(scope.organization)
    if scope.level == ScopeLevel.AGENT_FAMILY:
        return signature.agent_family in scope.agent_family
    if scope.level == ScopeLevel.PROJECT:
        return bool(scope.workspace and scope.workspace == signature.workspace.cwd)
    if scope.level == ScopeLevel.REPO:
        if scope.repo and signature.workspace.repo:
            return scope.repo == signature.workspace.repo
        return bool(scope.workspace and scope.workspace == signature.workspace.cwd)
    if scope.level == ScopeLevel.COMPONENT:
        if not scope.component:
            return False
        component = scope.component.lower()
        return component in signature.intent.lower() or any(
            component in target.lower() for target in signature.targets
        )
    if scope.level == ScopeLevel.PATH:
        return any(
            fnmatch(target, glob)
            for target in signature.targets
            for glob in scope.path_globs
        )
    if scope.level == ScopeLevel.TASK:
        return bool(scope.task and scope.task == signature.session.task_id)
    if scope.level == ScopeLevel.SESSION:
        return True
    if scope.level == ScopeLevel.PER_TURN:
        return True
    return False


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
        ScopeLevel.PATH: 90,
        ScopeLevel.TASK: 80,
        ScopeLevel.SESSION: 70,
        ScopeLevel.COMPONENT: 65,
        ScopeLevel.REPO: 60,
        ScopeLevel.PROJECT: 50,
        ScopeLevel.AGENT_FAMILY: 40,
        ScopeLevel.ORGANIZATION: 30,
        ScopeLevel.GLOBAL: 10,
        ScopeLevel.PER_TURN: 100,
    }
    return order[scope.level]
