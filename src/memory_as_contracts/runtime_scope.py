from __future__ import annotations

import hashlib
import json

from memory_as_contracts.models import Contract, ScopeLevel


def validator_scope_key(
    contract: Contract,
    *,
    session_id: str,
    task_id: str | None,
    workspace: str | None,
    repo: str | None,
    branch: str | None = None,
    user_id: str | None = None,
    organization: str | None = None,
    turn_id: str | None = None,
) -> str:
    payload = {
        "contract_id": contract.id,
        "scope_level": contract.scope.level.value,
    }
    level = contract.scope.level
    if level == ScopeLevel.PER_TURN:
        payload.update(session_id=session_id, task_id=task_id, turn_id=turn_id)
    elif level == ScopeLevel.TASK:
        payload.update(session_id=session_id, task_id=contract.scope.task or task_id)
    elif level == ScopeLevel.SESSION:
        payload["session_id"] = session_id
    elif level == ScopeLevel.COMPONENT:
        payload.update(
            workspace=contract.scope.workspace or workspace,
            repo=contract.scope.repo or repo,
            component=contract.scope.component,
        )
    elif level == ScopeLevel.PROJECT:
        payload["workspace"] = contract.scope.workspace or workspace
    elif level in {ScopeLevel.REPO, ScopeLevel.PATH}:
        payload.update(
            workspace=contract.scope.workspace or workspace,
            repo=contract.scope.repo or repo,
        )
        if level == ScopeLevel.PATH:
            payload["path_globs"] = sorted(contract.scope.path_globs)
    elif level == ScopeLevel.AGENT_FAMILY:
        payload["agent_family"] = sorted(contract.scope.agent_family)
    elif level == ScopeLevel.ORGANIZATION:
        payload["organization"] = contract.scope.organization or organization
    elif level == ScopeLevel.GLOBAL:
        payload["user_id"] = contract.scope.user_id or user_id
    else:
        payload.update(
            session_id=session_id,
            task_id=task_id,
            workspace=workspace,
            repo=repo,
            branch=branch,
            user_id=user_id,
            organization=organization,
        )
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
