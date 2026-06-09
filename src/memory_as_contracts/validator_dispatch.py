from __future__ import annotations

from dataclasses import dataclass

from memory_as_contracts.compiler import PolicyCompiler
from memory_as_contracts.matching import contract_applies_to_signature
from memory_as_contracts.models import (
    ActionLogEntryV1,
    ActionSignature,
    Contract,
    ContractStatus,
    MatchOutcome,
    PredicateStatus,
    RulePatternVersion,
    SessionContext,
    TimeContext,
    ToolCall,
    ValidatorVersion,
    WorkspaceContext,
)
from memory_as_contracts.runtime_scope import validator_scope_key
from memory_as_contracts.store import ContractStore


@dataclass(frozen=True)
class ValidatorDispatchPlan:
    version: ValidatorVersion
    contract: Contract
    entry: ActionLogEntryV1
    signature: ActionSignature
    scope_key: str


class ValidatorDispatchPlanner:
    """Plan validator updates with one applicability and scope implementation."""

    def __init__(
        self,
        store: ContractStore,
        *,
        compiler: PolicyCompiler | None = None,
    ) -> None:
        self.store = store
        self.compiler = compiler or PolicyCompiler()

    def for_committed_entry(
        self,
        entry: ActionLogEntryV1,
    ) -> list[ValidatorDispatchPlan]:
        plans: list[ValidatorDispatchPlan] = []
        for version in self.store.list_validator_versions(
            status=PredicateStatus.ACTIVE
        ):
            plan = self.for_version_entry(version, entry)
            if plan is not None:
                plans.append(plan)
        return plans

    def for_replay(
        self,
        version: ValidatorVersion,
        *,
        scope_key: str,
    ) -> list[ValidatorDispatchPlan]:
        plans: list[ValidatorDispatchPlan] = []
        for entry in self.store.list_action_log_entries():
            plan = self.for_version_entry(version, entry)
            if plan is not None and plan.scope_key == scope_key:
                plans.append(plan)
        return plans

    def for_version_entry(
        self,
        version: ValidatorVersion,
        entry: ActionLogEntryV1,
    ) -> ValidatorDispatchPlan | None:
        contract = self.store.get_contract(version.contract_id)
        if contract is None:
            return None
        signature = action_signature_from_log_entry(entry)
        if (
            contract.status != ContractStatus.ACTIVE
            or contract.is_expired(signature.time.now)
            or not contract_applies_to_signature(contract, signature)
        ):
            return None
        if not version.update_patterns:
            return None
        update_pattern = RulePatternVersion(
            contract_id=version.contract_id,
            tool_patterns=version.update_patterns,
        )
        if self.compiler.evaluate(update_pattern, signature) != MatchOutcome.MATCHED:
            return None
        return ValidatorDispatchPlan(
            version=version,
            contract=contract,
            entry=entry,
            signature=signature,
            scope_key=validator_scope_key_for_entry(contract, entry),
        )


def action_signature_from_log_entry(entry: ActionLogEntryV1) -> ActionSignature:
    return ActionSignature(
        host=entry.adapter_id,
        agent_family=entry.agent_id,
        session=SessionContext(
            session_id=entry.session_id,
            conversation_id=entry.conversation_id,
            turn_id=entry.turn_id,
            task_id=entry.task_id,
            user_id=entry.user_id,
        ),
        time=TimeContext(now=entry.timestamp),
        workspace=WorkspaceContext(
            cwd=entry.workspace or ".",
            root=entry.workspace,
            repo=entry.repo,
            branch=entry.branch,
        ),
        tool=ToolCall(
            name=entry.tool_name,
            raw_arguments=(
                entry.arguments
                if isinstance(entry.arguments, dict)
                else {"value": entry.arguments}
            ),
        ),
        host_action=entry.host_action,
        targets=entry.targets,
        risk=entry.risk,
        side_effect=entry.side_effect,
    )


def validator_scope_key_for_signature(
    contract: Contract,
    signature: ActionSignature,
) -> str:
    return validator_scope_key(
        contract,
        session_id=signature.session.session_id,
        task_id=signature.session.task_id,
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
        task_id=entry.task_id,
        workspace=entry.workspace,
        repo=entry.repo,
        branch=entry.branch,
        user_id=entry.user_id,
        organization=entry.organization,
        turn_id=entry.turn_id,
    )
