from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from memory_as_contracts.models import (
    AmbiguityEvent,
    CompiledPredicateVersion,
    Contract,
    ContractEdge,
    ContractStatus,
    MatchOutcome,
    PredicateEvaluation,
    PredicateStatus,
    Receipt,
    RefinementJob,
    RulePatternVersion,
    SourceSnapshot,
    utc_now,
)
from memory_as_contracts.schema_compat import (
    canonical_contract_payload,
    canonical_pattern_version_payload,
)


SCHEMA_VERSION = 3


def _dump_model(model: Any) -> str:
    return model.model_dump_json(by_alias=True)


def _dump_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _dump_contract_payload(contract: Contract) -> str:
    payload = contract.model_dump(mode="json", by_alias=True)
    return _dump_json(canonical_contract_payload(payload))


def _dump_pattern_version_payload(pattern_version: RulePatternVersion) -> str:
    return _dump_json(canonical_pattern_version_payload(pattern_version.model_dump(mode="json")))


def _load_json(value: str | None) -> Any:
    if not value:
        return None
    return json.loads(value)


class ContractStore:
    """SQLite-backed durable store for MAC kernel state."""

    def __init__(self, path: str | Path = ":memory:") -> None:
        self.path = Path(path) if path != ":memory:" else Path(":memory:")
        if self.path != Path(":memory:"):
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(path))
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")

    def close(self) -> None:
        self.conn.close()

    def init_db(self) -> None:
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS schema_version (
                version INTEGER NOT NULL
            );

            CREATE TABLE IF NOT EXISTS contracts (
                id TEXT PRIMARY KEY,
                text TEXT NOT NULL,
                kind TEXT NOT NULL,
                modality TEXT NOT NULL,
                strength TEXT NOT NULL,
                status TEXT NOT NULL,
                confidence REAL NOT NULL,
                effect TEXT,
                authority TEXT,
                source_json TEXT NOT NULL,
                scope_json TEXT NOT NULL,
                lifecycle_json TEXT NOT NULL,
                action_constraints_json TEXT NOT NULL,
                semantics_json TEXT,
                tool_patterns_json TEXT,
                targets_json TEXT,
                validity_json TEXT,
                compiled_predicates_json TEXT,
                override_json TEXT NOT NULL,
                supersedes_json TEXT NOT NULL,
                conflicts_with_json TEXT NOT NULL,
                payload_json TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE VIRTUAL TABLE IF NOT EXISTS contracts_fts
            USING fts5(contract_id UNINDEXED, text, source_span);

            CREATE TABLE IF NOT EXISTS contract_edges (
                id TEXT PRIMARY KEY,
                from_contract TEXT NOT NULL,
                to_contract TEXT NOT NULL,
                relation TEXT NOT NULL,
                status TEXT NOT NULL,
                scope_json TEXT NOT NULL,
                lifecycle_json TEXT NOT NULL,
                source_json TEXT,
                confidence REAL NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS rule_pattern_versions (
                id TEXT PRIMARY KEY,
                contract_id TEXT NOT NULL,
                version TEXT NOT NULL,
                status TEXT NOT NULL,
                refines TEXT,
                payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS receipts (
                id TEXT PRIMARY KEY,
                action_id TEXT NOT NULL,
                signature_id TEXT NOT NULL,
                session_id TEXT NOT NULL,
                decision TEXT NOT NULL,
                host_action TEXT NOT NULL,
                match_outcome TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS source_snapshots (
                source_key TEXT PRIMARY KEY,
                adapter TEXT NOT NULL,
                path TEXT NOT NULL,
                workspace TEXT NOT NULL,
                source_kind TEXT NOT NULL,
                fingerprint TEXT NOT NULL,
                content TEXT NOT NULL,
                observed_at TEXT NOT NULL,
                payload_json TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS predicate_evaluations (
                id TEXT PRIMARY KEY,
                contract_id TEXT NOT NULL,
                predicate_version_id TEXT NOT NULL,
                signature_id TEXT NOT NULL,
                match_outcome TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                evaluated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS ambiguity_events (
                id TEXT PRIMARY KEY,
                contract_id TEXT NOT NULL,
                predicate_version_id TEXT NOT NULL,
                signature_id TEXT NOT NULL,
                match_outcome TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                evaluated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS refinement_jobs (
                id TEXT PRIMARY KEY,
                contract_id TEXT NOT NULL,
                predicate_version_id TEXT NOT NULL,
                status TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            """
        )
        row = self.conn.execute("SELECT version FROM schema_version LIMIT 1").fetchone()
        if row is None:
            self.conn.execute("INSERT INTO schema_version(version) VALUES (?)", (SCHEMA_VERSION,))
        elif int(row["version"]) < SCHEMA_VERSION:
            self._migrate_schema(int(row["version"]))
        elif int(row["version"]) != SCHEMA_VERSION:
            raise RuntimeError(f"unsupported MAC schema version: {row['version']}")
        self.conn.commit()

    def _migrate_schema(self, version: int) -> None:
        if version in {1, 2}:
            self._ensure_contract_columns()
            self.conn.execute(
                """
                CREATE TABLE IF NOT EXISTS rule_pattern_versions (
                    id TEXT PRIMARY KEY,
                    contract_id TEXT NOT NULL,
                    version TEXT NOT NULL,
                    status TEXT NOT NULL,
                    refines TEXT,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            if self._table_exists("predicate_versions"):
                self.conn.execute(
                    """
                    INSERT OR IGNORE INTO rule_pattern_versions (
                        id, contract_id, version, status, refines, payload_json, created_at
                    )
                    SELECT id, contract_id, version, status, refines, payload_json, created_at
                    FROM predicate_versions
                    """
                )
            self.conn.execute("UPDATE schema_version SET version = ?", (SCHEMA_VERSION,))
            return
        raise RuntimeError(f"unsupported MAC schema version: {version}")

    def _table_exists(self, table: str) -> bool:
        row = self.conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
            (table,),
        ).fetchone()
        return row is not None

    def _ensure_contract_columns(self) -> None:
        columns = {
            row["name"]
            for row in self.conn.execute("PRAGMA table_info(contracts)").fetchall()
        }
        additions = {
            "payload_json": "TEXT",
            "effect": "TEXT",
            "authority": "TEXT",
            "semantics_json": "TEXT",
            "tool_patterns_json": "TEXT",
            "targets_json": "TEXT",
            "validity_json": "TEXT",
        }
        for name, column_type in additions.items():
            if name not in columns:
                self.conn.execute(f"ALTER TABLE contracts ADD COLUMN {name} {column_type}")

    def add_contract(self, contract: Contract) -> Contract:
        now = utc_now().isoformat()
        with self.conn:
            self.conn.execute(
                """
                INSERT OR REPLACE INTO contracts (
                    id, text, kind, modality, strength, status, confidence,
                    effect, authority, source_json, scope_json, lifecycle_json, action_constraints_json,
                    semantics_json, tool_patterns_json, targets_json, validity_json,
                    compiled_predicates_json, override_json, supersedes_json,
                    conflicts_with_json, payload_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    contract.id,
                    contract.text,
                    contract.kind.value,
                    contract.modality.value,
                    contract.strength.value,
                    contract.status.value,
                    contract.confidence,
                    contract.effect.value,
                    contract.authority.value,
                    _dump_model(contract.source),
                    _dump_model(contract.scope),
                    _dump_model(contract.lifecycle),
                    _dump_model(contract.action_constraints),
                    _dump_model(contract.semantics),
                    _dump_json([pattern.model_dump(mode="json") for pattern in contract.tool_patterns]),
                    _dump_json([target.model_dump(mode="json") for target in contract.targets]),
                    _dump_model(contract.validity),
                    _dump_model(contract.compiled_predicates)
                    if contract.compiled_predicates
                    else None,
                    _dump_model(contract.override),
                    _dump_json(contract.supersedes),
                    _dump_json(contract.conflicts_with),
                    _dump_contract_payload(contract),
                    contract.source.created_at.isoformat(),
                    now,
                ),
            )
            self.conn.execute("DELETE FROM contracts_fts WHERE contract_id = ?", (contract.id,))
            self.conn.execute(
                "INSERT INTO contracts_fts(contract_id, text, source_span) VALUES (?, ?, ?)",
                (contract.id, contract.text, contract.source.span),
            )
            if contract.compiled_predicates is not None:
                predicate = contract.compiled_predicates.model_copy(update={"contract_id": contract.id})
                self.add_rule_pattern_version(predicate)
        return contract

    def get_contract(self, contract_id: str) -> Contract | None:
        row = self.conn.execute("SELECT * FROM contracts WHERE id = ?", (contract_id,)).fetchone()
        return self._row_to_contract(row) if row else None

    def list_contracts(
        self,
        statuses: Iterable[ContractStatus] | None = None,
        *,
        include_expired_status: bool = True,
    ) -> list[Contract]:
        params: list[Any] = []
        where = ""
        if statuses is not None:
            values = [status.value for status in statuses]
            placeholders = ",".join("?" for _ in values)
            where = f"WHERE status IN ({placeholders})"
            params.extend(values)
        rows = self.conn.execute(f"SELECT * FROM contracts {where} ORDER BY created_at, id", params)
        contracts = [self._row_to_contract(row) for row in rows]
        if include_expired_status:
            return contracts
        return [contract for contract in contracts if not contract.is_expired()]

    def update_contract_status(self, contract_id: str, status: ContractStatus) -> None:
        with self.conn:
            self.conn.execute(
                "UPDATE contracts SET status = ?, updated_at = ? WHERE id = ?",
                (status.value, utc_now().isoformat(), contract_id),
            )

    def search_contracts(
        self,
        query: str,
        *,
        statuses: Iterable[ContractStatus] | None = None,
        limit: int = 10,
    ) -> list[Contract]:
        values: list[Any] = [query, limit]
        status_clause = ""
        if statuses is not None:
            status_values = [status.value for status in statuses]
            placeholders = ",".join("?" for _ in status_values)
            status_clause = f"AND c.status IN ({placeholders})"
            values = [query, *status_values, limit]
        rows = self.conn.execute(
            f"""
            SELECT c.*
            FROM contracts_fts f
            JOIN contracts c ON c.id = f.contract_id
            WHERE contracts_fts MATCH ?
            {status_clause}
            ORDER BY bm25(contracts_fts), c.created_at DESC
            LIMIT ?
            """,
            values,
        ).fetchall()
        return [self._row_to_contract(row) for row in rows]

    def add_edge(self, edge: ContractEdge) -> ContractEdge:
        with self.conn:
            self.conn.execute(
                """
                INSERT OR REPLACE INTO contract_edges (
                    id, from_contract, to_contract, relation, status, scope_json,
                    lifecycle_json, source_json, confidence, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    edge.id,
                    edge.from_contract,
                    edge.to_contract,
                    edge.relation.value,
                    edge.status.value,
                    _dump_model(edge.scope),
                    _dump_model(edge.lifecycle),
                    _dump_model(edge.source) if edge.source else None,
                    edge.confidence,
                    edge.created_at.isoformat(),
                ),
            )
        return edge

    def list_edges(self, statuses: Iterable[ContractStatus] | None = None) -> list[ContractEdge]:
        params: list[Any] = []
        where = ""
        if statuses is not None:
            values = [status.value for status in statuses]
            where = f"WHERE status IN ({','.join('?' for _ in values)})"
            params.extend(values)
        rows = self.conn.execute(f"SELECT * FROM contract_edges {where} ORDER BY created_at, id", params)
        return [self._row_to_edge(row) for row in rows]

    def add_rule_pattern_version(
        self, pattern_version: RulePatternVersion
    ) -> RulePatternVersion:
        if pattern_version.contract_id is None:
            raise ValueError("predicate version requires contract_id before storage")
        with self.conn:
            self.conn.execute(
                """
                INSERT OR REPLACE INTO rule_pattern_versions (
                    id, contract_id, version, status, refines, payload_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    pattern_version.id,
                    pattern_version.contract_id,
                    pattern_version.version,
                    pattern_version.status.value,
                    pattern_version.refines,
                    _dump_pattern_version_payload(pattern_version),
                    pattern_version.created_at.isoformat(),
                ),
            )
        return pattern_version

    def add_predicate_version(
        self, predicate: CompiledPredicateVersion
    ) -> CompiledPredicateVersion:
        return self.add_rule_pattern_version(predicate)

    def list_rule_pattern_versions(
        self,
        contract_id: str | None = None,
        status: PredicateStatus | None = None,
    ) -> list[RulePatternVersion]:
        clauses: list[str] = []
        params: list[Any] = []
        if contract_id is not None:
            clauses.append("contract_id = ?")
            params.append(contract_id)
        if status is not None:
            clauses.append("status = ?")
            params.append(status.value)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = self.conn.execute(
            f"SELECT payload_json FROM rule_pattern_versions {where} ORDER BY created_at, id",
            params,
        )
        return [RulePatternVersion.model_validate_json(row["payload_json"]) for row in rows]

    def get_active_rule_pattern_version(self, contract_id: str) -> RulePatternVersion | None:
        rows = self.list_rule_pattern_versions(contract_id, PredicateStatus.ACTIVE)
        return rows[-1] if rows else None

    def list_predicate_versions(
        self,
        contract_id: str | None = None,
        status: PredicateStatus | None = None,
    ) -> list[CompiledPredicateVersion]:
        return self.list_rule_pattern_versions(contract_id=contract_id, status=status)

    def add_receipt(self, receipt: Receipt) -> Receipt:
        with self.conn:
            self.conn.execute(
                """
                INSERT OR REPLACE INTO receipts (
                    id, action_id, signature_id, session_id, decision, host_action,
                    match_outcome, payload_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    receipt.id,
                    receipt.action_id,
                    receipt.signature_id,
                    receipt.session_id,
                    receipt.decision.value,
                    receipt.host_action,
                    receipt.match_outcome.value,
                    _dump_model(receipt),
                    receipt.created_at.isoformat(),
                ),
            )
        return receipt

    def list_receipts(self) -> list[Receipt]:
        rows = self.conn.execute("SELECT payload_json FROM receipts ORDER BY created_at, id")
        return [Receipt.model_validate_json(row["payload_json"]) for row in rows]

    def receipts_by_signature_ids(self, signature_ids: Iterable[str]) -> dict[str, Receipt]:
        ordered_ids = list(signature_ids)
        if not ordered_ids:
            return {}
        placeholders = ",".join("?" for _ in ordered_ids)
        rows = self.conn.execute(
            f"""
            SELECT payload_json FROM receipts
            WHERE signature_id IN ({placeholders})
            ORDER BY created_at, id
            """,
            ordered_ids,
        ).fetchall()
        return {
            receipt.signature_id: receipt
            for receipt in (Receipt.model_validate_json(row["payload_json"]) for row in rows)
        }

    def add_source_snapshot(self, snapshot: SourceSnapshot) -> SourceSnapshot:
        with self.conn:
            self.conn.execute(
                """
                INSERT OR REPLACE INTO source_snapshots (
                    source_key, adapter, path, workspace, source_kind, fingerprint,
                    content, observed_at, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    snapshot.source_key,
                    snapshot.adapter,
                    snapshot.path,
                    snapshot.workspace,
                    snapshot.source_kind.value,
                    snapshot.fingerprint,
                    snapshot.content,
                    snapshot.observed_at.isoformat(),
                    _dump_model(snapshot),
                ),
            )
        return snapshot

    def list_source_snapshots(self) -> list[SourceSnapshot]:
        rows = self.conn.execute("SELECT payload_json FROM source_snapshots ORDER BY observed_at")
        return [SourceSnapshot.model_validate_json(row["payload_json"]) for row in rows]

    def add_pattern_evaluation(self, evaluation: PredicateEvaluation) -> PredicateEvaluation:
        with self.conn:
            self.conn.execute(
                """
                INSERT OR REPLACE INTO predicate_evaluations (
                    id, contract_id, predicate_version_id, signature_id,
                    match_outcome, payload_json, evaluated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    evaluation.id,
                    evaluation.contract_id,
                    evaluation.pattern_version_id,
                    evaluation.signature_id,
                    evaluation.match_outcome.value,
                    _dump_model(evaluation),
                    evaluation.evaluated_at.isoformat(),
                ),
            )
        if evaluation.match_outcome == MatchOutcome.AMBIGUOUS:
            self.add_ambiguity_event(
                AmbiguityEvent(
                    contract_id=evaluation.contract_id,
                    pattern_version_id=evaluation.pattern_version_id,
                    signature_id=evaluation.signature_id,
                    reason=evaluation.reason,
                )
            )
        return evaluation

    def add_predicate_evaluation(
        self, evaluation: PredicateEvaluation
    ) -> PredicateEvaluation:
        return self.add_pattern_evaluation(evaluation)

    def recent_pattern_evaluations(
        self,
        contract_id: str,
        pattern_version_id: str,
        *,
        limit: int = 10,
    ) -> list[PredicateEvaluation]:
        rows = self.conn.execute(
            """
            SELECT payload_json FROM predicate_evaluations
            WHERE contract_id = ? AND predicate_version_id = ?
            ORDER BY evaluated_at DESC, id DESC
            LIMIT ?
            """,
            (contract_id, pattern_version_id, limit),
        ).fetchall()
        return [PredicateEvaluation.model_validate_json(row["payload_json"]) for row in rows]

    def recent_predicate_evaluations(
        self,
        contract_id: str,
        predicate_version_id: str,
        *,
        limit: int = 10,
    ) -> list[PredicateEvaluation]:
        return self.recent_pattern_evaluations(contract_id, predicate_version_id, limit=limit)

    def pattern_evaluations_by_signature_ids(
        self,
        contract_id: str,
        pattern_version_id: str,
        signature_ids: Iterable[str],
    ) -> list[PredicateEvaluation]:
        ordered_ids = list(signature_ids)
        if not ordered_ids:
            return []
        placeholders = ",".join("?" for _ in ordered_ids)
        rows = self.conn.execute(
            f"""
            SELECT payload_json FROM predicate_evaluations
            WHERE contract_id = ?
            AND predicate_version_id = ?
            AND signature_id IN ({placeholders})
            """,
            [contract_id, pattern_version_id, *ordered_ids],
        ).fetchall()
        by_id = {
            evaluation.signature_id: evaluation
            for evaluation in (
                PredicateEvaluation.model_validate_json(row["payload_json"]) for row in rows
            )
        }
        return [by_id[signature_id] for signature_id in ordered_ids if signature_id in by_id]

    def predicate_evaluations_by_signature_ids(
        self,
        contract_id: str,
        predicate_version_id: str,
        signature_ids: Iterable[str],
    ) -> list[PredicateEvaluation]:
        return self.pattern_evaluations_by_signature_ids(
            contract_id, predicate_version_id, signature_ids
        )

    def add_ambiguity_event(self, event: AmbiguityEvent) -> AmbiguityEvent:
        with self.conn:
            self.conn.execute(
                """
                INSERT OR REPLACE INTO ambiguity_events (
                    id, contract_id, predicate_version_id, signature_id,
                    match_outcome, payload_json, evaluated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event.id,
                    event.contract_id,
                    event.pattern_version_id,
                    event.signature_id,
                    event.match_outcome.value,
                    _dump_model(event),
                    event.evaluated_at.isoformat(),
                ),
            )
        return event

    def recent_ambiguity_events(
        self, contract_id: str, pattern_version_id: str, *, limit: int = 10
    ) -> list[AmbiguityEvent]:
        rows = self.conn.execute(
            """
            SELECT payload_json FROM ambiguity_events
            WHERE contract_id = ? AND predicate_version_id = ?
            ORDER BY evaluated_at DESC, id DESC
            LIMIT ?
            """,
            (contract_id, pattern_version_id, limit),
        )
        return [AmbiguityEvent.model_validate_json(row["payload_json"]) for row in rows]

    def add_refinement_job(self, job: RefinementJob) -> RefinementJob:
        with self.conn:
            self.conn.execute(
                """
                INSERT OR REPLACE INTO refinement_jobs (
                    id, contract_id, predicate_version_id, status,
                    payload_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    job.id,
                    job.contract_id,
                    job.pattern_version_id,
                    job.status.value,
                    _dump_model(job),
                    job.created_at.isoformat(),
                    job.updated_at.isoformat(),
                ),
            )
        return job

    def list_refinement_jobs(self, status: str | None = None) -> list[RefinementJob]:
        params: list[Any] = []
        where = ""
        if status is not None:
            where = "WHERE status = ?"
            params.append(status)
        rows = self.conn.execute(
            f"SELECT payload_json FROM refinement_jobs {where} ORDER BY created_at, id",
            params,
        )
        return [RefinementJob.model_validate_json(row["payload_json"]) for row in rows]

    def _row_to_contract(self, row: sqlite3.Row) -> Contract:
        if "payload_json" in row.keys() and row["payload_json"]:
            payload = _load_json(row["payload_json"])
            if isinstance(payload, dict):
                payload["status"] = row["status"]
                return Contract.model_validate(payload)
        payload = {
            "id": row["id"],
            "text": row["text"],
            "kind": row["kind"],
            "modality": row["modality"],
            "strength": row["strength"],
            "source": _load_json(row["source_json"]),
            "scope": _load_json(row["scope_json"]),
            "lifecycle": _load_json(row["lifecycle_json"]),
            "action_constraints": _load_json(row["action_constraints_json"]),
            "compiled_predicates": _load_json(row["compiled_predicates_json"]),
            "override": _load_json(row["override_json"]),
            "status": row["status"],
            "confidence": row["confidence"],
            "supersedes": _load_json(row["supersedes_json"]) or [],
            "conflicts_with": _load_json(row["conflicts_with_json"]) or [],
        }
        row_keys = set(row.keys())
        if "effect" in row_keys and row["effect"]:
            payload["effect"] = row["effect"]
        if "authority" in row_keys and row["authority"]:
            payload["authority"] = row["authority"]
        if "semantics_json" in row_keys and row["semantics_json"]:
            payload["semantics"] = _load_json(row["semantics_json"])
        if "tool_patterns_json" in row_keys and row["tool_patterns_json"]:
            payload["tool_patterns"] = _load_json(row["tool_patterns_json"]) or []
        if "targets_json" in row_keys and row["targets_json"]:
            payload["targets"] = _load_json(row["targets_json"]) or []
        if "validity_json" in row_keys and row["validity_json"]:
            payload["validity"] = _load_json(row["validity_json"])
        return Contract.model_validate(payload)

    def _row_to_edge(self, row: sqlite3.Row) -> ContractEdge:
        payload = {
            "id": row["id"],
            "from_contract": row["from_contract"],
            "to_contract": row["to_contract"],
            "relation": row["relation"],
            "scope": _load_json(row["scope_json"]),
            "lifecycle": _load_json(row["lifecycle_json"]),
            "source": _load_json(row["source_json"]),
            "status": row["status"],
            "confidence": row["confidence"],
            "created_at": row["created_at"],
        }
        return ContractEdge.model_validate(payload)
