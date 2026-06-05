from __future__ import annotations

import json
from datetime import datetime, timezone

from memory_as_contracts.models import (
    ActionConstraints,
    CompiledPredicateVersion,
    Contract,
    ContractEdge,
    ContractKind,
    ContractSource,
    EdgeRelation,
    HostActionPattern,
    Lifecycle,
    LifecycleType,
    MatchOutcome,
    Modality,
    PredicateEvaluation,
    PredicateStatus,
    Receipt,
    RulePatternVersion,
    Scope,
    ScopeLevel,
    SourceKind,
    SourceSnapshot,
    Strength,
)
from memory_as_contracts.store import ContractStore


def make_store() -> ContractStore:
    store = ContractStore(":memory:")
    store.init_db()
    return store


def make_contract(contract_id: str = "MAC-test") -> Contract:
    return Contract(
        id=contract_id,
        text="This week, do not push any code changes to Git before asking me.",
        kind=ContractKind.PROHIBITION,
        modality=Modality.MUST_NOT,
        strength=Strength.HARD,
        source=ContractSource(
            kind=SourceKind.USER_TURN,
            span="do not push",
            created_at=datetime(2026, 5, 23, tzinfo=timezone.utc),
        ),
        scope=Scope(level=ScopeLevel.PROJECT, workspace="/workspace/project"),
        lifecycle=Lifecycle(
            type=LifecycleType.BOUNDED_TIME,
            effective_from=datetime(2026, 5, 23, tzinfo=timezone.utc),
            expires_at=datetime(2026, 5, 30, tzinfo=timezone.utc),
        ),
        action_constraints=ActionConstraints(
            host_actions=["exec"],
            canonical_tags=["external_write", "publish_code"],
        ),
        compiled_predicates=CompiledPredicateVersion(
            id="PV-test",
            contract_id=contract_id,
            host_action_patterns=[HostActionPattern(action="exec", program="git", subcommand="push")],
        ),
    )


def test_store_round_trips_contract_edge_receipt_snapshot_and_events() -> None:
    store = make_store()
    contract = store.add_contract(make_contract())
    edge = store.add_edge(
        ContractEdge(
            from_contract="MAC-new",
            to_contract=contract.id,
            relation=EdgeRelation.SUPERSEDES,
            scope=contract.scope,
            lifecycle=contract.lifecycle,
        )
    )
    receipt = store.add_receipt(
        Receipt(
            signature_id="AS-1",
            session_id="sess-1",
            decision="confirm",
            host_action="git.push",
            match_outcome=MatchOutcome.MATCHED,
            result="confirm",
        )
    )
    snapshot = store.add_source_snapshot(
        SourceSnapshot(
            source_key="codex:/workspace/project/AGENTS.md",
            adapter="codex",
            path="AGENTS.md",
            workspace="/workspace/project",
            source_kind=SourceKind.PROJECT_DOC,
            fingerprint="abc",
            content="Do not push.",
        )
    )
    store.add_predicate_evaluation(
        PredicateEvaluation(
            contract_id=contract.id,
            predicate_version_id="PV-test",
            signature_id="AS-1",
            match_outcome=MatchOutcome.AMBIGUOUS,
        )
    )

    stored_contract = store.get_contract(contract.id)
    assert stored_contract is not None
    assert stored_contract.compiled_predicates is None
    assert stored_contract.text == contract.text
    assert store.get_active_rule_pattern_version(contract.id) is not None
    assert store.list_edges()[0].id == edge.id
    assert store.list_receipts()[0].id == receipt.id
    assert store.list_source_snapshots()[0].source_key == snapshot.source_key
    assert len(store.recent_ambiguity_events(contract.id, "PV-test")) == 1


def test_fts_search_uses_contract_text() -> None:
    store = make_store()
    store.add_contract(make_contract())

    results = store.search_contracts("push")

    assert [contract.id for contract in results] == ["MAC-test"]


def test_store_uses_schema_v3_rule_columns_and_rule_pattern_versions() -> None:
    store = make_store()
    contract = store.add_contract(make_contract())

    version = RulePatternVersion(
        id="RPV-next",
        contract_id=contract.id,
        version="PV-002",
        status=PredicateStatus.ACTIVE,
    )
    store.add_rule_pattern_version(version)

    schema_version = store.conn.execute("SELECT version FROM schema_version").fetchone()["version"]
    columns = {row["name"] for row in store.conn.execute("PRAGMA table_info(contracts)").fetchall()}
    payload = json.loads(
        store.conn.execute(
            "SELECT payload_json FROM contracts WHERE id = ?",
            (contract.id,),
        ).fetchone()["payload_json"]
    )
    pattern_payload = json.loads(
        store.conn.execute(
            "SELECT payload_json FROM rule_pattern_versions WHERE id = ?",
            ("RPV-next",),
        ).fetchone()["payload_json"]
    )

    assert schema_version == 3
    assert {
        "effect",
        "authority",
        "semantics_json",
        "tool_patterns_json",
        "targets_json",
        "validity_json",
    } <= columns
    assert "action_constraints" not in payload
    assert "compiled_predicates" not in payload
    assert "pattern_version" not in payload
    assert "from" in payload["validity"]
    assert "start" not in payload["validity"]
    assert "target_patterns" not in pattern_payload
    assert "targets" in pattern_payload
    assert "host_action_patterns" not in pattern_payload
    assert store.list_rule_pattern_versions(contract.id)[-1].id == "RPV-next"
    assert store.list_predicate_versions(contract.id)[-1].id == "RPV-next"
    predicate_versions_table = store.conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'predicate_versions'"
    ).fetchone()
    assert predicate_versions_table is None
