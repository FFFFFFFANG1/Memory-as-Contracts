from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from memory_as_contracts.models import (
    ActionConstraints,
    ActionSignature,
    ArgPattern,
    AvailableAction,
    CompiledPredicateVersion,
    Contract,
    ContractEdge,
    ContractKind,
    ContractSource,
    EdgeRelation,
    GateDecisionType,
    HostActionPattern,
    IgnoredContract,
    Lifecycle,
    LifecycleType,
    MatchOutcome,
    Modality,
    Receipt,
    Scope,
    ScopeLevel,
    SessionContext,
    SideEffect,
    SourceKind,
    Strength,
    ToolPattern,
    ToolCall,
    WorkspaceContext,
)


def project_scope() -> Scope:
    return Scope(level=ScopeLevel.PROJECT, workspace="/workspace/project")


def user_source() -> ContractSource:
    return ContractSource(
        kind=SourceKind.USER_TURN,
        conversation_id="conv-123",
        turn_id="u-017",
        span="this week do not push before asking",
        created_at=datetime(2026, 5, 23, 9, 30, tzinfo=timezone.utc),
    )


def test_contract_serializes_proposal_style_example() -> None:
    contract = Contract(
        id="MAC-001",
        text="This week, do not push any code changes to Git before asking me.",
        kind=ContractKind.PROHIBITION,
        modality=Modality.MUST_NOT,
        strength=Strength.HARD,
        source=user_source(),
        scope=project_scope(),
        lifecycle=Lifecycle(
            type=LifecycleType.BOUNDED_TIME,
            effective_from=datetime(2026, 5, 23, 9, 30, tzinfo=timezone.utc),
            expires_at=datetime(2026, 5, 30, 23, 59, 59, tzinfo=timezone.utc),
            original_text="this week",
        ),
        action_constraints=ActionConstraints(
            host_actions=["exec"],
            canonical_tags=["external_write", "publish_code"],
        ),
        compiled_predicates=CompiledPredicateVersion(
            id="PV-001",
            version="PV-001",
            host_action_patterns=[HostActionPattern(action="exec", program="git", subcommand="push")],
            canonical_tags=["external_write", "publish_code"],
        ),
        confidence=0.94,
    )

    payload = contract.model_dump(mode="json")

    assert payload["id"] == "MAC-001"
    assert payload["kind"] == "prohibition"
    assert payload["scope"]["level"] == "project"
    assert payload["compiled_predicates"]["host_action_patterns"][0]["subcommand"] == "push"


def test_rule_schema_round_trips_linked_repo_tool_patterns() -> None:
    payload = {
        "id": "rule_01",
        "text": "不要修改 linked repo，除非用户本轮显式要求。",
        "effect": "deny",
        "status": "active",
        "authority": "user_explicit",
        "scope": {"repo": "current", "paths": ["../linked_repo/**"]},
        "semantics": {
            "actions": ["file.write"],
            "tags": ["workspace_write", "source_modification"],
        },
        "tool_patterns": [
            {
                "tool": "Edit",
                "args": {"file_path": {"path_glob": "../linked_repo/**"}},
            },
            {
                "tool": "apply_patch",
                "args": {"patch": {"mentions_path_glob": "../linked_repo/**"}},
            },
        ],
        "targets": [{"kind": "path_glob", "value": "../linked_repo/**"}],
        "override": {"type": "explicit_user_current_turn"},
        "validity": {"from": "2026-06-03T10:00:00Z", "until": None},
    }

    rule = Contract.model_validate(payload)
    dumped = rule.model_dump(mode="json")

    assert rule.effect == "deny"
    assert rule.scope.path_globs == ["../linked_repo/**"]
    assert rule.action_constraints.host_actions == ["file.write"]
    assert rule.compiled_predicates is None
    assert rule.tool_patterns[0] == ToolPattern(
        tool="Edit",
        args={"file_path": ArgPattern(path_glob="../linked_repo/**")},
    )
    assert dumped["semantics"]["tags"] == ["workspace_write", "source_modification"]


def test_fact_cannot_bind_action_constraints() -> None:
    with pytest.raises(ValidationError, match="fact contracts cannot bind action constraints"):
        Contract(
            text="This repo uses uv.",
            kind=ContractKind.FACT,
            modality=Modality.MAY,
            source=ContractSource(kind=SourceKind.PROJECT_DOC, span="uses uv"),
            scope=project_scope(),
            action_constraints=ActionConstraints(host_actions=["exec"]),
        )


def test_fact_cannot_bind_compiled_predicates() -> None:
    with pytest.raises(ValidationError, match="fact contracts cannot bind compiled predicates"):
        Contract(
            text="This repo uses uv.",
            kind=ContractKind.FACT,
            modality=Modality.MAY,
            source=ContractSource(kind=SourceKind.PROJECT_DOC, span="uses uv"),
            scope=project_scope(),
            compiled_predicates=CompiledPredicateVersion(
                host_action_patterns=[HostActionPattern(action="exec", program="uv")]
            ),
        )


def test_path_scope_requires_path_globs() -> None:
    with pytest.raises(ValidationError, match="path scope requires"):
        Scope(level=ScopeLevel.PATH, workspace="/workspace/project")


def test_bounded_time_lifecycle_requires_expiry_after_effective_time() -> None:
    now = datetime(2026, 5, 23, 9, 30, tzinfo=timezone.utc)

    with pytest.raises(ValidationError, match="expires_at must be after effective_from"):
        Lifecycle(type=LifecycleType.BOUNDED_TIME, effective_from=now, expires_at=now)


def test_until_revoked_lifecycle_cannot_have_expiry() -> None:
    now = datetime(2026, 5, 23, 9, 30, tzinfo=timezone.utc)

    with pytest.raises(ValidationError, match="cannot also have expires_at"):
        Lifecycle(
            type=LifecycleType.UNTIL_REVOKED,
            effective_from=now,
            until_revoked=True,
            expires_at=now + timedelta(days=1),
        )


def test_contract_edge_has_own_scope_and_lifecycle() -> None:
    edge = ContractEdge(
        id="E-014",
        from_contract="MAC-014",
        to_contract="MAC-003",
        relation=EdgeRelation.SUPERSEDES,
        scope=project_scope(),
        lifecycle=Lifecycle(type=LifecycleType.UNTIL_REVOKED, until_revoked=True),
        source=user_source(),
        confidence=0.91,
    )

    assert edge.scope.workspace == "/workspace/project"
    assert edge.lifecycle.until_revoked is True


def test_contract_edge_must_connect_distinct_contracts() -> None:
    with pytest.raises(ValidationError, match="distinct contracts"):
        ContractEdge(
            from_contract="MAC-001",
            to_contract="MAC-001",
            relation=EdgeRelation.CONFLICTS_WITH,
            scope=project_scope(),
        )


def test_action_signature_requires_host_action_from_available_registry() -> None:
    with pytest.raises(ValidationError, match="host_action must be present"):
        ActionSignature(
            host="codex",
            agent_family="codex",
            session=SessionContext(session_id="sess-1"),
            workspace=WorkspaceContext(cwd="/workspace/project", repo="project"),
            available_actions=[AvailableAction(name="file.write")],
            tool=ToolCall(name="exec", raw_arguments={"cmd": "git push"}),
            host_action="exec",
        )


def test_action_signature_serializes_coding_tool_call() -> None:
    signature = ActionSignature(
        signature_id="AS-102",
        host="codex",
        agent_family="codex",
        session=SessionContext(session_id="sess-1", conversation_id="conv-123", turn_id="u-018"),
        workspace=WorkspaceContext(cwd="/workspace/project", repo="project", branch="fix-auth"),
        available_actions=[
            AvailableAction(
                name="file.write",
                canonical_tags=["file_write", "workspace_write"],
                side_effect=SideEffect.WRITE,
            )
        ],
        tool=ToolCall(name="file.write", raw_arguments={"path": "vendor/auth.js"}),
        host_action="file.write",
        canonical_tags=["file_write", "source_modification", "workspace_write"],
        targets=["vendor/auth.js"],
        intent="fix failing auth test",
        side_effect=SideEffect.WRITE,
    )

    payload = signature.model_dump(mode="json")

    assert payload["host_action"] == "file.write"
    assert payload["targets"] == ["vendor/auth.js"]


def test_receipt_serializes_gate_decision_evidence() -> None:
    receipt = Receipt(
        action_id="A-102",
        signature_id="AS-102",
        session_id="sess-1",
        decision=GateDecisionType.CONFIRM,
        host_action="git.push",
        canonical_tags=["external_write", "publish_code"],
        match_outcome=MatchOutcome.MATCHED,
        targets=["origin/main"],
        contracts_used=["MAC-001"],
        edges_applied=["E-014"],
        contracts_ignored=[IgnoredContract(id="MAC-005", reason="expired")],
        result="awaiting_user_confirmation",
    )

    payload = receipt.model_dump(mode="json")

    assert payload["decision"] == "confirm"
    assert payload["contracts_ignored"][0]["reason"] == "expired"
