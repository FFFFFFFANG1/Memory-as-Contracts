from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone

from memory_as_contracts.models import (
    ArgPattern,
    Contract,
    ContractEdge,
    ContractKind,
    ContractSource,
    EdgeRelation,
    Lifecycle,
    LifecycleType,
    MatchOutcome,
    Modality,
    PredicateStatus,
    Receipt,
    RulePatternVersion,
    RuleSemantics,
    Scope,
    ScopeLevel,
    SourceKind,
    SourceSnapshot,
    Strength,
    ToolPattern,
)
from memory_as_contracts.rule_surface import (
    contract_dedup_fingerprint,
    contract_pattern_surface_hash,
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
        semantics=RuleSemantics(
            actions=["git.push"],
            tags=["external_write", "publish_code"],
        ),
        tool_patterns=[
            ToolPattern(
                tool="exec",
                args={"cmd": ArgPattern(regex=r"^\s*git\s+push(?:\s|$)")},
            )
        ],
    )


def test_store_round_trips_contract_edge_receipt_and_snapshot() -> None:
    store = make_store()
    contract = store.add_contract(make_contract())
    store.install_rule_pattern_version(
        RulePatternVersion(
            id="PV-test",
            contract_id=contract.id,
            tool_patterns=contract.tool_patterns,
        )
    )
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
            decision="ask",
            host_action="git.push",
            match_outcome=MatchOutcome.MATCHED,
            result="ask",
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
    stored_contract = store.get_contract(contract.id)
    assert stored_contract is not None
    assert stored_contract.text == contract.text
    assert store.get_active_rule_pattern_version(contract.id) is not None
    assert store.list_edges()[0].id == edge.id
    assert store.list_receipts()[0].id == receipt.id
    assert store.list_source_snapshots()[0].source_key == snapshot.source_key


def test_fts_search_uses_contract_text() -> None:
    store = make_store()
    store.add_contract(make_contract())

    results = store.search_contracts("push")

    assert [contract.id for contract in results] == ["MAC-test"]


def test_store_uses_schema_v11_with_dedup_keys_without_legacy_tables() -> None:
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

    action_log_table = store.conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'action_log'"
    ).fetchone()

    assert schema_version == 11
    assert action_log_table is not None
    assert {
        "effect",
        "authority",
        "semantics_json",
        "tool_patterns_json",
        "validity_json",
        "dedup_fingerprint",
        "pattern_surface_hash",
    } <= columns
    assert "targets_json" not in columns
    assert "action_constraints" not in payload
    assert "compiled_predicates" not in payload
    assert "pattern_version" not in payload
    assert "from" in payload["validity"]
    assert "start" not in payload["validity"]
    assert "target_patterns" not in pattern_payload
    assert "targets" not in pattern_payload
    assert "host_action_patterns" not in pattern_payload
    assert store.list_rule_pattern_versions(contract.id)[-1].id == "RPV-next"
    predicate_versions_table = store.conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'predicate_versions'"
    ).fetchone()
    assert predicate_versions_table is None
    for table in ("predicate_evaluations", "ambiguity_events", "refinement_jobs"):
        assert (
            store.conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
                (table,),
            ).fetchone()
            is None
        )


def test_store_queries_contracts_by_kernel_surface_keys() -> None:
    store = make_store()
    contract = store.add_contract(make_contract())

    matches = store.find_contracts_by_surface_keys(
        dedup_fingerprint=contract_dedup_fingerprint(contract),
        pattern_surface_hash=contract_pattern_surface_hash(contract),
    )

    assert [match.id for match in matches] == [contract.id]


def test_schema_v6_validator_state_migrates_to_scoped_v10_state(tmp_path) -> None:
    path = tmp_path / "mac-v6.sqlite3"
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE schema_version (version INTEGER NOT NULL);
        INSERT INTO schema_version(version) VALUES (6);
        CREATE TABLE validator_states (
            validator_version_id TEXT PRIMARY KEY,
            contract_id TEXT NOT NULL,
            state_json TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        """
    )
    conn.execute(
        """
        INSERT INTO validator_states (
            validator_version_id, contract_id, state_json, payload_json, updated_at
        ) VALUES (?, ?, ?, ?, ?)
        """,
        (
            "VV-old",
            "MAC-old",
            '{"count":1}',
            (
                '{"validator_version_id":"VV-old","contract_id":"MAC-old",'
                '"state":{"count":1},"updated_at":"2026-06-06T00:00:00Z"}'
            ),
            "2026-06-06T00:00:00Z",
        ),
    )
    conn.commit()
    conn.close()

    store = ContractStore(path)
    store.init_db()

    state = store.get_validator_state("VV-old", "legacy")
    assert state is not None
    assert state.scope_key == "legacy"
    assert state.state == {"count": 1}
    assert state.revision == 0
    assert store.conn.execute("SELECT version FROM schema_version").fetchone()["version"] == 11
