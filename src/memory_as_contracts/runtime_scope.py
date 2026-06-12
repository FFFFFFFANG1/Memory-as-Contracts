from __future__ import annotations

from memory_as_contracts.models import Contract
from memory_as_contracts.rule_surface import validator_scope_key as _validator_scope_key


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
    return _validator_scope_key(
        contract,
        session_id=session_id,
        workspace=workspace,
        repo=repo,
        branch=branch,
        user_id=user_id,
        turn_id=turn_id,
    )
