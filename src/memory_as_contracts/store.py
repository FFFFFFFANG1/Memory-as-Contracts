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
    SourceSnapshot,
    utc_now,
)


SCHEMA_VERSION = 1


def _dump_model(model: Any) -> str:
    return model.model_dump_json()


def _dump_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


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
                source_json TEXT NOT NULL,
                scope_json TEXT NOT NULL,
                lifecycle_json TEXT NOT NULL,
                action_constraints_json TEXT NOT NULL,
                compiled_predicates_json TEXT,
                override_json TEXT NOT NULL,
                supersedes_json TEXT NOT NULL,
                conflicts_with_json TEXT NOT NULL,
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

            CREATE TABLE IF NOT EXISTS predicate_versions (
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
        elif int(row["version"]) != SCHEMA_VERSION:
            raise RuntimeError(f"unsupported MAC schema version: {row['version']}")
        self.conn.commit()

    def add_contract(self, contract: Contract) -> Contract:
        now = utc_now().isoformat()
        with self.conn:
            self.conn.execute(
                """
                INSERT OR REPLACE INTO contracts (
                    id, text, kind, modality, strength, status, confidence,
                    source_json, scope_json, lifecycle_json, action_constraints_json,
                    compiled_predicates_json, override_json, supersedes_json,
                    conflicts_with_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    contract.id,
                    contract.text,
                    contract.kind.value,
                    contract.modality.value,
                    contract.strength.value,
                    contract.status.value,
                    contract.confidence,
                    _dump_model(contract.source),
                    _dump_model(contract.scope),
                    _dump_model(contract.lifecycle),
                    _dump_model(contract.action_constraints),
                    _dump_model(contract.compiled_predicates)
                    if contract.compiled_predicates
                    else None,
                    _dump_model(contract.override),
                    _dump_json(contract.supersedes),
                    _dump_json(contract.conflicts_with),
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
                self.add_predicate_version(predicate)
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

    def add_predicate_version(
        self, predicate: CompiledPredicateVersion
    ) -> CompiledPredicateVersion:
        if predicate.contract_id is None:
            raise ValueError("predicate version requires contract_id before storage")
        with self.conn:
            self.conn.execute(
                """
                INSERT OR REPLACE INTO predicate_versions (
                    id, contract_id, version, status, refines, payload_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    predicate.id,
                    predicate.contract_id,
                    predicate.version,
                    predicate.status.value,
                    predicate.refines,
                    _dump_model(predicate),
                    predicate.created_at.isoformat(),
                ),
            )
        return predicate

    def list_predicate_versions(
        self,
        contract_id: str | None = None,
        status: PredicateStatus | None = None,
    ) -> list[CompiledPredicateVersion]:
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
            f"SELECT payload_json FROM predicate_versions {where} ORDER BY created_at, id",
            params,
        )
        return [CompiledPredicateVersion.model_validate_json(row["payload_json"]) for row in rows]

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

    def add_predicate_evaluation(
        self, evaluation: PredicateEvaluation
    ) -> PredicateEvaluation:
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
                    evaluation.predicate_version_id,
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
                    predicate_version_id=evaluation.predicate_version_id,
                    signature_id=evaluation.signature_id,
                    reason=evaluation.reason,
                )
            )
        return evaluation

    def recent_predicate_evaluations(
        self,
        contract_id: str,
        predicate_version_id: str,
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
            (contract_id, predicate_version_id, limit),
        ).fetchall()
        return [PredicateEvaluation.model_validate_json(row["payload_json"]) for row in rows]

    def predicate_evaluations_by_signature_ids(
        self,
        contract_id: str,
        predicate_version_id: str,
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
            [contract_id, predicate_version_id, *ordered_ids],
        ).fetchall()
        by_id = {
            evaluation.signature_id: evaluation
            for evaluation in (
                PredicateEvaluation.model_validate_json(row["payload_json"]) for row in rows
            )
        }
        return [by_id[signature_id] for signature_id in ordered_ids if signature_id in by_id]

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
                    event.predicate_version_id,
                    event.signature_id,
                    event.match_outcome.value,
                    _dump_model(event),
                    event.evaluated_at.isoformat(),
                ),
            )
        return event

    def recent_ambiguity_events(
        self, contract_id: str, predicate_version_id: str, *, limit: int = 10
    ) -> list[AmbiguityEvent]:
        rows = self.conn.execute(
            """
            SELECT payload_json FROM ambiguity_events
            WHERE contract_id = ? AND predicate_version_id = ?
            ORDER BY evaluated_at DESC, id DESC
            LIMIT ?
            """,
            (contract_id, predicate_version_id, limit),
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
                    job.predicate_version_id,
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
