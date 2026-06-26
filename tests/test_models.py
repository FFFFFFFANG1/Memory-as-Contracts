from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from memory_as_contracts.models import (
    ActionSignature,
    ArgPattern,
    AvailableAction,
    Contract,
    ContractEdge,
    ContractKind,
    ContractSource,
    EdgeRelation,
    GateDecisionType,
    IgnoredContract,
    Lifecycle,
    LifecycleType,
    MatchOutcome,
    Modality,
    Receipt,
    RulePatternVersion,
    RuleSemantics,
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
    return Scope(level=ScopeLevel.PROJECT, workspace="/workspace/project", project="/workspace/project")


def user_source() -> ContractSource:
    return ContractSource(
        kind=SourceKind.USER_TURN,
        conversation_id="conv-123",
        turn_id="u-017",
        created_at=datetime(2026, 5, 23, 9, 30, tzinfo=timezone.utc),
    )


def test_contract_and_pattern_version_serialize_canonical_schema() -> None:
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
        semantics=RuleSemantics(
            actions=["git.push"],
            tags=["external_write", "publish_code"],
        ),
        check_patterns=[
            ToolPattern(
                tool="exec",
                args={"cmd": ArgPattern(regex=r"^\s*git\s+push(?:\s|$)")},
            )
        ],
        confidence=0.94,
    )
    pattern_version = RulePatternVersion(
        id="PV-001",
        contract_id=contract.id,
        version="PV-001",
        check_patterns=contract.check_patterns,
        canonical_tags=["external_write", "publish_code"],
    )

    payload = contract.model_dump(mode="json")
    pattern_payload = pattern_version.model_dump(mode="json")

    assert payload["id"] == "MAC-001"
    assert payload["kind"] == "prohibition"
    assert payload["scope"]["level"] == "project"
    assert "action_constraints" not in payload
    assert "compiled_predicates" not in payload
    assert "host_action_patterns" not in pattern_payload
    assert "tool_patterns" not in payload
    assert pattern_payload["check_patterns"][0]["args"]["cmd"]["regex"].startswith("^")


def test_rule_schema_round_trips_linked_repo_check_patterns() -> None:
    payload = {
        "id": "rule_01",
        "text": "不要修改 linked repo，除非用户本轮显式要求。",
        "effect": "deny",
        "status": "active",
        "authority": "user_explicit",
        "scope": {"project": "current"},
        "semantics": {
            "actions": ["file.write"],
            "tags": ["workspace_write", "source_modification"],
        },
        "check_patterns": [
            {
                "tool": "Edit",
                "args": {"file_path": {"path_glob": "../linked_repo/**"}},
            },
            {
                "tool": "apply_patch",
                "args": {"patch": {"mentions_path_glob": "../linked_repo/**"}},
            },
        ],
        "override": {"type": "explicit_user_current_turn"},
        "validity": {"from": "2026-06-03T10:00:00Z", "until": None},
    }

    rule = Contract.model_validate(payload)
    dumped = rule.model_dump(mode="json")

    assert rule.effect == "deny"
    assert rule.scope.project == "current"
    assert rule.semantics.actions == ["file.write"]
    assert rule.check_patterns[0] == ToolPattern(
        tool="Edit",
        args={"file_path": ArgPattern(path_glob="../linked_repo/**")},
    )
    assert dumped["semantics"]["tags"] == ["workspace_write", "source_modification"]


def test_fact_cannot_bind_rule_semantics() -> None:
    with pytest.raises(ValidationError, match="fact contracts cannot bind rule semantics"):
        Contract(
            text="This repo uses uv.",
            kind=ContractKind.FACT,
            modality=Modality.MAY,
            source=ContractSource(kind=SourceKind.PROJECT_DOC),
            scope=project_scope(),
            semantics=RuleSemantics(actions=["exec"]),
        )


def test_fact_cannot_bind_check_patterns() -> None:
    with pytest.raises(ValidationError, match="fact contracts cannot bind operational patterns"):
        Contract(
            text="This repo uses uv.",
            kind=ContractKind.FACT,
            modality=Modality.MAY,
            source=ContractSource(kind=SourceKind.PROJECT_DOC),
            scope=project_scope(),
            check_patterns=[
                ToolPattern(tool="exec", args={"cmd": ArgPattern(regex=r"^uv(?:\s|$)")})
            ],
        )


def test_legacy_rule_payload_is_rejected_by_canonical_schema() -> None:
    legacy_payload = {
        "text": "Do not push code.",
        "kind": "prohibition",
        "modality": "MUST_NOT",
        "source": {"kind": "user_turn", "span": "Do not push code."},
        "scope": {"level": "project", "workspace": "/workspace/project"},
        "action_constraints": {
            "host_actions": ["git.push"],
            "canonical_tags": ["publish_code"],
        },
        "compiled_predicates": {
            "host_action_patterns": [
                {
                    "action": "exec",
                    "tool_name": "exec",
                    "parameter_regex": {"cmd": r"^git\s+push(?:\s|$)"},
                }
            ]
        },
    }

    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        Contract.model_validate(legacy_payload)

    assert "action_constraints" not in Contract.model_fields
    assert "compiled_predicates" not in Contract.model_fields


def test_project_scope_requires_project_or_workspace() -> None:
    with pytest.raises(ValidationError, match="project scope requires"):
        Scope(level=ScopeLevel.PROJECT)


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
        decision=GateDecisionType.ASK,
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

    assert payload["decision"] == "ask"
    assert payload["contracts_ignored"][0]["reason"] == "expired"
