from __future__ import annotations

import hashlib
import json
import sqlite3
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from memory_as_contracts.rule_surface import (
    contract_dedup_fingerprint,
    contract_pattern_surface_hash,
)
from memory_as_contracts.models import (
    ActionLogEntryV1,
    ActionOutcome,
    AskRequest,
    AskRequestStatus,
    Contract,
    ContractEdge,
    ContractStatus,
    PredicateStatus,
    Receipt,
    RulePatternVersion,
    SourceSnapshot,
    ValidatorInstallationRecord,
    ValidatorRuntimeErrorRecord,
    ValidatorState,
    ValidatorStateTransition,
    ValidatorVersion,
    utc_now,
)
from memory_as_contracts.schema_compat import (
    action_constraints_from_semantics,
    canonical_contract_payload,
    canonical_pattern_version_payload,
    normalize_rule_payload,
)


SCHEMA_VERSION = 12
ASK_RESPONSE_TTL = timedelta(minutes=30)
ACTION_LOG_SQL_COLUMNS = {
    "seq": "seq",
    "timestamp": "timestamp",
    "session_id": "session_id",
    "agent_id": "agent_id",
    "adapter_id": "adapter_id",
    "tool_call_id": "tool_call_id",
    "tool_name": "tool_name",
    "host_action": "host_action",
    "outcome": "outcome",
    "result_text": "result_text",
    "reasoning_text": "reasoning_text",
    "conversation_id": "conversation_id",
    "turn_id": "turn_id",
    "user_id": "user_id",
    "workspace": "workspace",
    "repo": "repo",
    "branch": "branch",
    "risk": "risk",
    "side_effect": "side_effect",
}


@dataclass(frozen=True)
class RankedContractSearchResult:
    contract: Contract
    rank: float


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


def _compile_action_log_sql_predicate(
    column: str,
    predicate: dict[str, Any],
) -> tuple[str, list[Any]] | None:
    clauses: list[str] = []
    params: list[Any] = []
    for operator, expected in predicate.items():
        if operator == "eq":
            clauses.append(f"{column} = ?")
            params.append(expected)
        elif operator == "ne":
            clauses.append(f"{column} != ?")
            params.append(expected)
        elif operator == "in":
            if not isinstance(expected, list) or not expected:
                return None
            placeholders = ", ".join("?" for _ in expected)
            clauses.append(f"{column} IN ({placeholders})")
            params.extend(expected)
        elif operator == "gt":
            clauses.append(f"{column} > ?")
            params.append(expected)
        elif operator == "gte":
            clauses.append(f"{column} >= ?")
            params.append(expected)
        elif operator == "lt":
            clauses.append(f"{column} < ?")
            params.append(expected)
        elif operator == "lte":
            clauses.append(f"{column} <= ?")
            params.append(expected)
        elif operator == "exists" and bool(expected):
            clauses.append(f"{column} IS NOT NULL")
        elif operator == "missing" and bool(expected):
            clauses.append(f"{column} IS NULL")
        elif operator == "contains":
            clauses.append(f"{column} LIKE ?")
            params.append(f"%{expected}%")
        else:
            return None
    return " AND ".join(clauses), params


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
                validity_json TEXT,
                dedup_fingerprint TEXT,
                pattern_surface_hash TEXT,
                compiled_predicates_json TEXT,
                override_json TEXT NOT NULL,
                supersedes_json TEXT NOT NULL,
                conflicts_with_json TEXT NOT NULL,
                payload_json TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE VIRTUAL TABLE IF NOT EXISTS contracts_fts
            USING fts5(contract_id UNINDEXED, text);

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

            CREATE TABLE IF NOT EXISTS action_log (
                seq INTEGER PRIMARY KEY AUTOINCREMENT,
                adapter_id TEXT NOT NULL,
                session_id TEXT NOT NULL,
                agent_id TEXT NOT NULL,
                tool_call_id TEXT NOT NULL,
                tool_name TEXT NOT NULL,
                host_action TEXT NOT NULL,
                arguments_json TEXT NOT NULL,
                result_json TEXT,
                result_text TEXT NOT NULL,
                outcome TEXT NOT NULL,
                reasoning_text TEXT,
                conversation_id TEXT,
                turn_id TEXT,
                user_id TEXT,
                workspace TEXT,
                repo TEXT,
                branch TEXT,
                targets_json TEXT NOT NULL DEFAULT '[]',
                risk TEXT NOT NULL DEFAULT 'medium',
                side_effect TEXT NOT NULL DEFAULT 'none',
                timestamp TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                UNIQUE(adapter_id, session_id, tool_call_id)
            );

            CREATE TABLE IF NOT EXISTS validator_versions (
                id TEXT PRIMARY KEY,
                contract_id TEXT NOT NULL,
                enforcement_shape TEXT NOT NULL,
                status TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS validator_states (
                validator_version_id TEXT NOT NULL,
                scope_key TEXT NOT NULL,
                contract_id TEXT NOT NULL,
                state_json TEXT NOT NULL,
                revision INTEGER NOT NULL,
                last_applied_seq INTEGER,
                degraded INTEGER NOT NULL,
                payload_json TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (validator_version_id, scope_key)
            );

            CREATE TABLE IF NOT EXISTS ask_requests (
                id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                task_id TEXT,
                adapter_id TEXT NOT NULL,
                tool_name TEXT NOT NULL,
                status TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS validator_installations (
                id TEXT PRIMARY KEY,
                contract_id TEXT NOT NULL,
                status TEXT NOT NULL,
                validator_version_id TEXT,
                payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS validator_state_transitions (
                id TEXT PRIMARY KEY,
                validator_version_id TEXT NOT NULL,
                scope_key TEXT NOT NULL,
                action_log_seq INTEGER NOT NULL,
                payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS validator_runtime_errors (
                id TEXT PRIMARY KEY,
                validator_version_id TEXT NOT NULL,
                contract_id TEXT NOT NULL,
                scope_key TEXT NOT NULL,
                phase TEXT NOT NULL,
                replay_required INTEGER NOT NULL,
                payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS user_turns (
                seq INTEGER PRIMARY KEY AUTOINCREMENT,
                adapter_id TEXT NOT NULL,
                session_id TEXT NOT NULL,
                task_id TEXT,
                conversation_id TEXT,
                turn_id TEXT,
                text TEXT NOT NULL,
                observed_at TEXT NOT NULL,
                extracted_at TEXT
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
        self._ensure_contract_dedup_indexes()
        self.conn.commit()

    def _migrate_schema(self, version: int) -> None:
        if version in {1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11}:
            self._ensure_contract_columns()
            self._ensure_action_log_columns()
            self._rebuild_action_log_without_task_or_org()
            self._ensure_validator_state_schema()
            self._backfill_contract_dedup_keys()
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
            for table in ("predicate_evaluations", "ambiguity_events", "refinement_jobs"):
                self.conn.execute(f"DROP TABLE IF EXISTS {table}")
            columns = {
                row["name"]
                for row in self.conn.execute("PRAGMA table_info(contracts)").fetchall()
            }
            if "targets_json" in columns:
                self.conn.execute("ALTER TABLE contracts DROP COLUMN targets_json")
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
            "validity_json": "TEXT",
            "dedup_fingerprint": "TEXT",
            "pattern_surface_hash": "TEXT",
        }
        for name, column_type in additions.items():
            if name not in columns:
                self.conn.execute(f"ALTER TABLE contracts ADD COLUMN {name} {column_type}")

    def _ensure_contract_dedup_indexes(self) -> None:
        columns = {
            row["name"]
            for row in self.conn.execute("PRAGMA table_info(contracts)").fetchall()
        }
        if "dedup_fingerprint" not in columns or "pattern_surface_hash" not in columns:
            return
        self.conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_contracts_dedup_fingerprint
            ON contracts(dedup_fingerprint)
            """
        )
        self.conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_contracts_pattern_surface_hash
            ON contracts(pattern_surface_hash)
            """
        )

    def _backfill_contract_dedup_keys(self) -> None:
        if not self._table_exists("contracts"):
            return
        columns = {
            row["name"]
            for row in self.conn.execute("PRAGMA table_info(contracts)").fetchall()
        }
        if "dedup_fingerprint" not in columns or "pattern_surface_hash" not in columns:
            return
        rows = self.conn.execute(
            """
            SELECT id, payload_json FROM contracts
            WHERE payload_json IS NOT NULL
              AND (dedup_fingerprint IS NULL OR pattern_surface_hash IS NULL)
            """
        ).fetchall()
        for row in rows:
            try:
                contract = Contract.model_validate_json(row["payload_json"])
            except (TypeError, ValueError):
                continue
            self.conn.execute(
                """
                UPDATE contracts
                SET dedup_fingerprint = ?, pattern_surface_hash = ?
                WHERE id = ?
                """,
                (
                    contract_dedup_fingerprint(contract),
                    contract_pattern_surface_hash(contract),
                    row["id"],
                ),
            )

    def _ensure_action_log_columns(self) -> None:
        if not self._table_exists("action_log"):
            return
        columns = {
            row["name"]
            for row in self.conn.execute("PRAGMA table_info(action_log)").fetchall()
        }
        additions = {
            "conversation_id": "TEXT",
            "turn_id": "TEXT",
            "user_id": "TEXT",
            "workspace": "TEXT",
            "repo": "TEXT",
            "branch": "TEXT",
            "targets_json": "TEXT NOT NULL DEFAULT '[]'",
            "risk": "TEXT NOT NULL DEFAULT 'medium'",
            "side_effect": "TEXT NOT NULL DEFAULT 'none'",
        }
        for name, column_type in additions.items():
            if name not in columns:
                self.conn.execute(f"ALTER TABLE action_log ADD COLUMN {name} {column_type}")

    def _rebuild_action_log_without_task_or_org(self) -> None:
        if not self._table_exists("action_log"):
            return
        columns = {
            row["name"]
            for row in self.conn.execute("PRAGMA table_info(action_log)").fetchall()
        }
        if "task_id" not in columns and "organization" not in columns:
            return
        self.conn.executescript(
            """
            CREATE TABLE action_log_new (
                seq INTEGER PRIMARY KEY AUTOINCREMENT,
                adapter_id TEXT NOT NULL,
                session_id TEXT NOT NULL,
                agent_id TEXT NOT NULL,
                tool_call_id TEXT NOT NULL,
                tool_name TEXT NOT NULL,
                host_action TEXT NOT NULL,
                arguments_json TEXT NOT NULL,
                result_json TEXT,
                result_text TEXT NOT NULL,
                outcome TEXT NOT NULL,
                reasoning_text TEXT,
                conversation_id TEXT,
                turn_id TEXT,
                user_id TEXT,
                workspace TEXT,
                repo TEXT,
                branch TEXT,
                targets_json TEXT NOT NULL DEFAULT '[]',
                risk TEXT NOT NULL DEFAULT 'medium',
                side_effect TEXT NOT NULL DEFAULT 'none',
                timestamp TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                UNIQUE(adapter_id, session_id, tool_call_id)
            );

            INSERT INTO action_log_new (
                seq, adapter_id, session_id, agent_id, tool_call_id,
                tool_name, host_action, arguments_json, result_json, result_text,
                outcome, reasoning_text, conversation_id, turn_id, user_id,
                workspace, repo, branch, targets_json, risk, side_effect,
                timestamp, payload_json
            )
            SELECT
                seq, adapter_id, session_id, agent_id, tool_call_id,
                tool_name, host_action, arguments_json, result_json, result_text,
                outcome, reasoning_text, conversation_id, turn_id, user_id,
                workspace, repo, branch, targets_json, risk, side_effect,
                timestamp, payload_json
            FROM action_log;

            DROP TABLE action_log;
            ALTER TABLE action_log_new RENAME TO action_log;
            """
        )
        rows = self.conn.execute("SELECT seq, payload_json FROM action_log").fetchall()
        for row in rows:
            payload = _load_json(row["payload_json"]) or {}
            if not isinstance(payload, dict):
                continue
            payload.pop("task_id", None)
            payload.pop("organization", None)
            self.conn.execute(
                "UPDATE action_log SET payload_json = ? WHERE seq = ?",
                (_dump_json(payload), row["seq"]),
            )

    def _ensure_validator_state_schema(self) -> None:
        if not self._table_exists("validator_states"):
            return
        columns = {
            row["name"]
            for row in self.conn.execute("PRAGMA table_info(validator_states)").fetchall()
        }
        if "scope_key" in columns:
            return
        self.conn.execute("ALTER TABLE validator_states RENAME TO validator_states_legacy")
        self.conn.execute(
            """
            CREATE TABLE validator_states (
                validator_version_id TEXT NOT NULL,
                scope_key TEXT NOT NULL,
                contract_id TEXT NOT NULL,
                state_json TEXT NOT NULL,
                revision INTEGER NOT NULL,
                last_applied_seq INTEGER,
                degraded INTEGER NOT NULL,
                payload_json TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (validator_version_id, scope_key)
            )
            """
        )
        rows = self.conn.execute(
            "SELECT * FROM validator_states_legacy"
        ).fetchall()
        for row in rows:
            payload = _load_json(row["payload_json"]) or {}
            payload.update(
                {
                    "scope_key": "legacy",
                    "revision": 0,
                    "last_applied_seq": None,
                    "degraded": False,
                }
            )
            self.conn.execute(
                """
                INSERT INTO validator_states (
                    validator_version_id, scope_key, contract_id, state_json,
                    revision, last_applied_seq, degraded, payload_json, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    row["validator_version_id"],
                    "legacy",
                    row["contract_id"],
                    row["state_json"],
                    0,
                    None,
                    0,
                    _dump_json(payload),
                    row["updated_at"],
                ),
            )
        self.conn.execute("DROP TABLE validator_states_legacy")

    def add_contract(self, contract: Contract) -> Contract:
        now = utc_now().isoformat()
        with self.conn:
            self.conn.execute(
                """
                INSERT OR REPLACE INTO contracts (
                    id, text, kind, modality, strength, status, confidence,
                    effect, authority, source_json, scope_json, lifecycle_json, action_constraints_json,
                    semantics_json, validity_json,
                    dedup_fingerprint, pattern_surface_hash,
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
                    _dump_json(
                        action_constraints_from_semantics(
                            contract.semantics.model_dump(mode="json")
                        )
                    ),
                    _dump_model(contract.semantics),
                    _dump_model(contract.validity),
                    contract_dedup_fingerprint(contract),
                    contract_pattern_surface_hash(contract),
                    None,
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
                "INSERT INTO contracts_fts(contract_id, text) VALUES (?, ?)",
                (contract.id, contract.text),
            )
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

    def find_contracts_by_dedup_keys(
        self,
        contract: Contract,
        statuses: Iterable[ContractStatus] | None = None,
    ) -> list[Contract]:
        return self.find_contracts_by_surface_keys(
            dedup_fingerprint=contract_dedup_fingerprint(contract),
            pattern_surface_hash=contract_pattern_surface_hash(contract),
            statuses=statuses,
        )

    def find_contracts_by_surface_keys(
        self,
        *,
        dedup_fingerprint: str,
        pattern_surface_hash: str,
        statuses: Iterable[ContractStatus] | None = None,
    ) -> list[Contract]:
        values: list[Any] = [
            dedup_fingerprint,
            pattern_surface_hash,
        ]
        status_clause = ""
        if statuses is not None:
            status_values = [status.value for status in statuses]
            placeholders = ",".join("?" for _ in status_values)
            status_clause = f"AND status IN ({placeholders})"
            values.extend(status_values)
        rows = self.conn.execute(
            f"""
            SELECT *
            FROM contracts
            WHERE (dedup_fingerprint = ? OR pattern_surface_hash = ?)
              {status_clause}
            ORDER BY created_at, id
            """,
            values,
        ).fetchall()
        return [self._row_to_contract(row) for row in rows]

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

    def search_contracts_ranked_text(
        self,
        query: str,
        *,
        statuses: Iterable[ContractStatus] | None = None,
        limit: int = 10,
    ) -> list[RankedContractSearchResult]:
        values: list[Any] = [query, limit]
        status_clause = ""
        if statuses is not None:
            status_values = [status.value for status in statuses]
            placeholders = ",".join("?" for _ in status_values)
            status_clause = f"AND c.status IN ({placeholders})"
            values = [query, *status_values, limit]
        rows = self.conn.execute(
            f"""
            SELECT c.*, bm25(contracts_fts) AS fts_rank
            FROM contracts_fts f
            JOIN contracts c ON c.id = f.contract_id
            WHERE contracts_fts MATCH ?
            {status_clause}
            ORDER BY fts_rank, c.created_at DESC
            LIMIT ?
            """,
            values,
        ).fetchall()
        return [
            RankedContractSearchResult(
                contract=self._row_to_contract(row),
                rank=float(row["fts_rank"]),
            )
            for row in rows
        ]

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

    def install_rule_pattern_version(
        self,
        pattern_version: RulePatternVersion,
    ) -> RulePatternVersion:
        if pattern_version.contract_id is None:
            raise ValueError("pattern version requires contract_id before installation")
        if pattern_version.status != PredicateStatus.ACTIVE:
            raise ValueError("installed pattern version must be active")
        with self.conn:
            active = self.list_rule_pattern_versions(
                contract_id=pattern_version.contract_id,
                status=PredicateStatus.ACTIVE,
            )
            for current in active:
                superseded = current.model_copy(
                    update={"status": PredicateStatus.SUPERSEDED}
                )
                self.conn.execute(
                    """
                    UPDATE rule_pattern_versions
                    SET status = ?, payload_json = ?
                    WHERE id = ?
                    """,
                    (
                        PredicateStatus.SUPERSEDED.value,
                        _dump_pattern_version_payload(superseded),
                        current.id,
                    ),
                )
            self.conn.execute(
                """
                INSERT INTO rule_pattern_versions (
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
        return [
            RulePatternVersion.model_validate(
                canonical_pattern_version_payload(_load_json(row["payload_json"]))
            )
            for row in rows
        ]

    def get_active_rule_pattern_version(self, contract_id: str) -> RulePatternVersion | None:
        rows = self.list_rule_pattern_versions(contract_id, PredicateStatus.ACTIVE)
        return rows[-1] if rows else None

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

    def add_action_log_entry(self, entry: ActionLogEntryV1) -> ActionLogEntryV1:
        stored, _ = self.append_action_log_entry(entry)
        return stored

    def append_user_turn(
        self,
        *,
        adapter_id: str,
        session_id: str,
        task_id: str | None,
        conversation_id: str | None,
        turn_id: str | None,
        text: str,
        observed_at,
    ) -> int:
        with self.conn:
            cursor = self.conn.execute(
                """
                INSERT INTO user_turns (
                    adapter_id, session_id, task_id, conversation_id,
                    turn_id, text, observed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    adapter_id,
                    session_id,
                    task_id,
                    conversation_id,
                    turn_id,
                    text,
                    observed_at.isoformat(),
                ),
            )
        return int(cursor.lastrowid)

    def pending_user_turns(
        self,
        *,
        adapter_id: str,
        session_id: str,
        limit: int,
    ) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT seq, task_id, conversation_id, turn_id, text, observed_at
            FROM user_turns
            WHERE adapter_id = ? AND session_id = ? AND extracted_at IS NULL
            ORDER BY seq
            LIMIT ?
            """,
            (adapter_id, session_id, limit),
        ).fetchall()
        return [dict(row) for row in rows]

    def mark_user_turns_extracted(self, sequences: Iterable[int]) -> None:
        seqs = list(sequences)
        if not seqs:
            return
        placeholders = ", ".join("?" for _ in seqs)
        with self.conn:
            self.conn.execute(
                f"""
                UPDATE user_turns
                SET extracted_at = ?
                WHERE seq IN ({placeholders})
                """,
                (utc_now().isoformat(), *seqs),
            )

    def append_action_log_entry(
        self,
        entry: ActionLogEntryV1,
    ) -> tuple[ActionLogEntryV1, bool]:
        existing_row = self.conn.execute(
            """
            SELECT * FROM action_log
            WHERE adapter_id = ? AND session_id = ? AND tool_call_id = ?
            """,
            (entry.adapter_id, entry.session_id, entry.tool_call_id),
        ).fetchone()
        if existing_row is not None:
            existing = self._row_to_action_log_entry(existing_row)
            if _action_log_identity_payload(existing) != _action_log_identity_payload(entry):
                raise ValueError("action log idempotency key reused with different payload")
            return existing, False
        with self.conn:
            self.conn.execute(
                """
                INSERT INTO action_log (
                    adapter_id, session_id, agent_id, tool_call_id,
                    tool_name, host_action, arguments_json, result_json, result_text,
                    outcome, reasoning_text, conversation_id, turn_id, user_id,
                    workspace, repo, branch, targets_json, risk,
                    side_effect, timestamp, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    entry.adapter_id,
                    entry.session_id,
                    entry.agent_id,
                    entry.tool_call_id,
                    entry.tool_name,
                    entry.host_action,
                    _dump_json(entry.arguments),
                    _dump_json(entry.result) if entry.result is not None else None,
                    entry.result_text,
                    entry.outcome.value,
                    entry.reasoning_text,
                    entry.conversation_id,
                    entry.turn_id,
                    entry.user_id,
                    entry.workspace,
                    entry.repo,
                    entry.branch,
                    _dump_json(entry.targets),
                    entry.risk.value,
                    entry.side_effect.value,
                    entry.timestamp.isoformat(),
                    entry.model_dump_json(),
                ),
            )
        row = self.conn.execute(
            """
            SELECT * FROM action_log
            WHERE adapter_id = ? AND session_id = ? AND tool_call_id = ?
            """,
            (entry.adapter_id, entry.session_id, entry.tool_call_id),
        ).fetchone()
        if row is None:
            raise RuntimeError("failed to append action log entry")
        return self._row_to_action_log_entry(row), True

    def list_action_log_entries(self) -> list[ActionLogEntryV1]:
        rows = self.conn.execute("SELECT * FROM action_log ORDER BY seq").fetchall()
        return [self._row_to_action_log_entry(row) for row in rows]

    def search_action_log_candidates(
        self,
        *,
        session_id: str,
        where: dict[str, dict[str, Any]],
        limit: int,
    ) -> list[ActionLogEntryV1]:
        clauses = ["session_id = ?"]
        params: list[Any] = [session_id]
        for field, predicate in where.items():
            column = ACTION_LOG_SQL_COLUMNS.get(field)
            if column is None or "regex" in predicate:
                continue
            compiled = _compile_action_log_sql_predicate(column, predicate)
            if compiled is None:
                continue
            clause, values = compiled
            clauses.append(clause)
            params.extend(values)
        params.append(limit)
        rows = self.conn.execute(
            f"""
            SELECT *
            FROM action_log
            WHERE {' AND '.join(clauses)}
            ORDER BY timestamp DESC, seq DESC
            LIMIT ?
            """,
            params,
        ).fetchall()
        return [self._row_to_action_log_entry(row) for row in rows]

    def add_validator_version(self, version: ValidatorVersion) -> ValidatorVersion:
        if version.status == PredicateStatus.ACTIVE and not version.verification_hash:
            raise ValueError("active validator versions must be installed from verified output")
        with self.conn:
            self.conn.execute(
                """
                INSERT OR REPLACE INTO validator_versions (
                    id, contract_id, enforcement_shape, status, payload_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    version.id,
                    version.contract_id,
                    version.enforcement_shape.value,
                    version.status.value,
                    version.model_dump_json(),
                    version.created_at.isoformat(),
                ),
            )
        return version

    def install_verified_validator_version(
        self,
        version: ValidatorVersion,
        *,
        scope_key: str,
    ) -> ValidatorVersion:
        expected_hash = hashlib.sha256(
            json.dumps(
                {
                    "check_code": version.check_code,
                    "update_code": version.update_code,
                },
                sort_keys=True,
            ).encode("utf-8")
        ).hexdigest()
        if not version.verification_hash or version.snippet_hash != expected_hash:
            raise ValueError("validator version is missing valid verification metadata")
        if version.status != PredicateStatus.ACTIVE:
            raise ValueError("installed validator version must be active")
        with self.conn:
            active = self.list_validator_versions(
                contract_id=version.contract_id,
                status=PredicateStatus.ACTIVE,
            )
            for current in active:
                superseded = current.model_copy(update={"status": PredicateStatus.SUPERSEDED})
                self.conn.execute(
                    """
                    UPDATE validator_versions
                    SET status = ?, payload_json = ?
                    WHERE id = ?
                    """,
                    (
                        PredicateStatus.SUPERSEDED.value,
                        superseded.model_dump_json(),
                        current.id,
                    ),
                )
            self.conn.execute(
                """
                INSERT INTO validator_versions (
                    id, contract_id, enforcement_shape, status, payload_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    version.id,
                    version.contract_id,
                    version.enforcement_shape.value,
                    version.status.value,
                    version.model_dump_json(),
                    version.created_at.isoformat(),
                ),
            )
            if version.enforcement_shape.value == "check_update":
                state = ValidatorState(
                    validator_version_id=version.id,
                    scope_key=scope_key,
                    contract_id=version.contract_id,
                    state=version.shared_states,
                )
                self.conn.execute(
                    """
                    INSERT INTO validator_states (
                        validator_version_id, scope_key, contract_id, state_json,
                        revision, last_applied_seq, degraded, payload_json, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    _validator_state_params(state),
                )
        return version

    def add_validator_installation(
        self,
        installation: ValidatorInstallationRecord,
    ) -> ValidatorInstallationRecord:
        with self.conn:
            self.conn.execute(
                """
                INSERT INTO validator_installations (
                    id, contract_id, status, validator_version_id, payload_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    installation.id,
                    installation.contract_id,
                    installation.status.value,
                    installation.validator_version_id,
                    installation.model_dump_json(),
                    installation.created_at.isoformat(),
                ),
            )
        return installation

    def list_validator_installations(
        self,
        contract_id: str | None = None,
    ) -> list[ValidatorInstallationRecord]:
        if contract_id is None:
            rows = self.conn.execute(
                "SELECT payload_json FROM validator_installations ORDER BY created_at, id"
            ).fetchall()
        else:
            rows = self.conn.execute(
                """
                SELECT payload_json FROM validator_installations
                WHERE contract_id = ?
                ORDER BY created_at, id
                """,
                (contract_id,),
            ).fetchall()
        return [
            ValidatorInstallationRecord.model_validate_json(row["payload_json"])
            for row in rows
        ]

    def list_validator_versions(
        self,
        contract_id: str | None = None,
        status: PredicateStatus | None = None,
    ) -> list[ValidatorVersion]:
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
            f"SELECT payload_json FROM validator_versions {where} ORDER BY created_at, id",
            params,
        ).fetchall()
        return [ValidatorVersion.model_validate_json(row["payload_json"]) for row in rows]

    def get_active_validator_version(self, contract_id: str) -> ValidatorVersion | None:
        rows = self.list_validator_versions(contract_id=contract_id, status=PredicateStatus.ACTIVE)
        return rows[-1] if rows else None

    def get_validator_version(self, validator_version_id: str) -> ValidatorVersion | None:
        row = self.conn.execute(
            "SELECT payload_json FROM validator_versions WHERE id = ?",
            (validator_version_id,),
        ).fetchone()
        return ValidatorVersion.model_validate_json(row["payload_json"]) if row else None

    def put_validator_state(
        self,
        state: ValidatorState,
        *,
        expected_revision: int | None = None,
    ) -> ValidatorState:
        with self.conn:
            if expected_revision is None:
                self.conn.execute(
                    """
                    INSERT INTO validator_states (
                        validator_version_id, scope_key, contract_id, state_json,
                        revision, last_applied_seq, degraded, payload_json, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(validator_version_id, scope_key) DO UPDATE SET
                        contract_id = excluded.contract_id,
                        state_json = excluded.state_json,
                        revision = excluded.revision,
                        last_applied_seq = excluded.last_applied_seq,
                        degraded = excluded.degraded,
                        payload_json = excluded.payload_json,
                        updated_at = excluded.updated_at
                    """,
                    _validator_state_params(state),
                )
            else:
                cursor = self.conn.execute(
                    """
                    UPDATE validator_states
                    SET state_json = ?, revision = ?, last_applied_seq = ?,
                        degraded = ?, payload_json = ?, updated_at = ?
                    WHERE validator_version_id = ? AND scope_key = ? AND revision = ?
                    """,
                    (
                        _dump_json(state.state),
                        state.revision,
                        state.last_applied_seq,
                        int(state.degraded),
                        state.model_dump_json(),
                        state.updated_at.isoformat(),
                        state.validator_version_id,
                        state.scope_key,
                        expected_revision,
                    ),
                )
                if cursor.rowcount != 1:
                    raise RuntimeError("validator state revision conflict")
        return state

    def get_validator_state(
        self,
        validator_version_id: str,
        scope_key: str | None = None,
    ) -> ValidatorState | None:
        if scope_key is None:
            rows = self.list_validator_states(validator_version_id)
            return rows[0] if len(rows) == 1 else None
        row = self.conn.execute(
            """
            SELECT payload_json FROM validator_states
            WHERE validator_version_id = ? AND scope_key = ?
            """,
            (validator_version_id, scope_key),
        ).fetchone()
        return ValidatorState.model_validate_json(row["payload_json"]) if row else None

    def list_validator_states(self, validator_version_id: str) -> list[ValidatorState]:
        rows = self.conn.execute(
            """
            SELECT payload_json FROM validator_states
            WHERE validator_version_id = ?
            ORDER BY scope_key
            """,
            (validator_version_id,),
        ).fetchall()
        return [ValidatorState.model_validate_json(row["payload_json"]) for row in rows]

    def delete_validator_state(
        self,
        validator_version_id: str,
        scope_key: str | None = None,
    ) -> None:
        with self.conn:
            if scope_key is None:
                self.conn.execute(
                    "DELETE FROM validator_states WHERE validator_version_id = ?",
                    (validator_version_id,),
                )
            else:
                self.conn.execute(
                    """
                    DELETE FROM validator_states
                    WHERE validator_version_id = ? AND scope_key = ?
                    """,
                    (validator_version_id, scope_key),
                )

    def add_validator_state_transition(
        self,
        transition: ValidatorStateTransition,
    ) -> ValidatorStateTransition:
        with self.conn:
            self.conn.execute(
                """
                INSERT INTO validator_state_transitions (
                    id, validator_version_id, scope_key, action_log_seq,
                    payload_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    transition.id,
                    transition.validator_version_id,
                    transition.scope_key,
                    transition.action_log_seq,
                    transition.model_dump_json(),
                    transition.created_at.isoformat(),
                ),
            )
        return transition

    def add_validator_runtime_error(
        self,
        error: ValidatorRuntimeErrorRecord,
    ) -> ValidatorRuntimeErrorRecord:
        with self.conn:
            self.conn.execute(
                """
                INSERT INTO validator_runtime_errors (
                    id, validator_version_id, contract_id, scope_key, phase,
                    replay_required, payload_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    error.id,
                    error.validator_version_id,
                    error.contract_id,
                    error.scope_key,
                    error.phase,
                    int(error.replay_required),
                    error.model_dump_json(),
                    error.created_at.isoformat(),
                ),
            )
        return error

    def list_validator_state_transitions(
        self,
        validator_version_id: str | None = None,
    ) -> list[ValidatorStateTransition]:
        if validator_version_id is None:
            rows = self.conn.execute(
                """
                SELECT payload_json FROM validator_state_transitions
                ORDER BY created_at, id
                """
            ).fetchall()
        else:
            rows = self.conn.execute(
                """
                SELECT payload_json FROM validator_state_transitions
                WHERE validator_version_id = ?
                ORDER BY created_at, id
                """,
                (validator_version_id,),
            ).fetchall()
        return [
            ValidatorStateTransition.model_validate_json(row["payload_json"])
            for row in rows
        ]

    def list_validator_runtime_errors(
        self,
        validator_version_id: str | None = None,
    ) -> list[ValidatorRuntimeErrorRecord]:
        if validator_version_id is None:
            rows = self.conn.execute(
                """
                SELECT payload_json FROM validator_runtime_errors
                ORDER BY created_at, id
                """
            ).fetchall()
        else:
            rows = self.conn.execute(
                """
                SELECT payload_json FROM validator_runtime_errors
                WHERE validator_version_id = ?
                ORDER BY created_at, id
                """,
                (validator_version_id,),
            ).fetchall()
        return [
            ValidatorRuntimeErrorRecord.model_validate_json(row["payload_json"])
            for row in rows
        ]

    def add_ask_request(self, request: AskRequest) -> AskRequest:
        existing = self.list_ask_requests(
            status=AskRequestStatus.REQUIRED,
            session_id=request.session_id,
            adapter_id=request.adapter_id,
        )
        for stale in existing:
            if stale.task_id != request.task_id:
                continue
            self._replace_ask_request(
                stale.model_copy(update={"status": AskRequestStatus.CANCELLED})
            )
        with self.conn:
            self.conn.execute(
                """
                INSERT INTO ask_requests (
                    id, session_id, task_id, adapter_id, tool_name,
                    status, payload_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    request.id,
                    request.session_id,
                    request.task_id,
                    request.adapter_id,
                    request.tool_name,
                    request.status.value,
                    request.model_dump_json(),
                    request.created_at.isoformat(),
                    request.created_at.isoformat(),
                ),
            )
        return request

    def get_ask_request(self, request_id: str) -> AskRequest | None:
        row = self.conn.execute(
            "SELECT payload_json FROM ask_requests WHERE id = ?",
            (request_id,),
        ).fetchone()
        return AskRequest.model_validate_json(row["payload_json"]) if row else None

    def list_ask_requests(
        self,
        *,
        status: AskRequestStatus | None = None,
        session_id: str | None = None,
        task_id: str | None = None,
        adapter_id: str | None = None,
    ) -> list[AskRequest]:
        clauses: list[str] = []
        params: list[Any] = []
        for column, value in (
            ("status", status.value if status is not None else None),
            ("session_id", session_id),
            ("task_id", task_id),
            ("adapter_id", adapter_id),
        ):
            if value is not None:
                clauses.append(f"{column} = ?")
                params.append(value)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = self.conn.execute(
            f"SELECT payload_json FROM ask_requests {where} ORDER BY created_at, id",
            params,
        ).fetchall()
        return [AskRequest.model_validate_json(row["payload_json"]) for row in rows]

    def mark_user_input_observed(
        self,
        *,
        session_id: str,
        task_id: str | None,
        adapter_id: str,
        turn_id: str | None,
        observed_at: datetime,
    ) -> AskRequest | None:
        task_clause = "task_id IS NULL" if task_id is None else "task_id = ?"
        params: list[Any] = [
            AskRequestStatus.REQUIRED.value,
            session_id,
            adapter_id,
        ]
        if task_id is not None:
            params.append(task_id)
        rows = self.conn.execute(
            f"""
            SELECT payload_json FROM ask_requests
            WHERE status = ? AND session_id = ? AND adapter_id = ? AND {task_clause}
            ORDER BY created_at, id
            """,
            params,
        ).fetchall()
        required = [AskRequest.model_validate_json(row["payload_json"]) for row in rows]
        if not required:
            return None
        selected = required[-1]
        for stale in required[:-1]:
            self._replace_ask_request(
                stale.model_copy(update={"status": AskRequestStatus.CANCELLED})
            )
        return self._replace_ask_request(
            selected.model_copy(
                update={
                    "status": AskRequestStatus.RESPONDED,
                    "responded_at": observed_at,
                    "responded_turn_id": turn_id,
                    "expires_at": observed_at + ASK_RESPONSE_TTL,
                }
            )
        )

    def matching_ask_response(
        self,
        *,
        session_id: str,
        task_id: str | None,
        adapter_id: str,
        tool_names: Iterable[str],
        turn_id: str | None,
        now: datetime,
    ) -> AskRequest | None:
        task_clause = "task_id IS NULL" if task_id is None else "task_id = ?"
        params: list[Any] = [
            AskRequestStatus.RESPONDED.value,
            session_id,
            adapter_id,
        ]
        if task_id is not None:
            params.append(task_id)
        rows = self.conn.execute(
            f"""
            SELECT payload_json FROM ask_requests
            WHERE status = ? AND session_id = ? AND adapter_id = ? AND {task_clause}
            ORDER BY created_at, id
            """,
            params,
        ).fetchall()
        responded = [AskRequest.model_validate_json(row["payload_json"]) for row in rows]
        allowed_tools = set(tool_names)
        eligible: list[AskRequest] = []
        for request in responded:
            expired = request.expires_at is not None and now > request.expires_at
            wrong_turn = (
                request.responded_turn_id is not None
                and turn_id is not None
                and request.responded_turn_id != turn_id
            )
            wrong_tool = request.tool_name not in allowed_tools
            if expired or wrong_turn or wrong_tool:
                self._replace_ask_request(
                    request.model_copy(update={"status": AskRequestStatus.CANCELLED})
                )
                continue
            eligible.append(request)
        selected = eligible[-1] if eligible else None
        for request in eligible:
            if selected is not None and request.id == selected.id:
                continue
            self._replace_ask_request(
                request.model_copy(update={"status": AskRequestStatus.CANCELLED})
            )
        return selected

    def consume_ask_response(self, request_id: str) -> AskRequest:
        request = self.get_ask_request(request_id)
        if request is None:
            raise ValueError(f"unknown ask request: {request_id}")
        if request.status != AskRequestStatus.RESPONDED:
            raise ValueError("only responded ask requests can be consumed")
        return self._replace_ask_request(
            request.model_copy(
                update={"status": AskRequestStatus.CONSUMED, "consumed_at": utc_now()}
            )
        )

    def _replace_ask_request(self, request: AskRequest) -> AskRequest:
        with self.conn:
            self.conn.execute(
                """
                UPDATE ask_requests
                SET status = ?, payload_json = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    request.status.value,
                    request.model_dump_json(),
                    utc_now().isoformat(),
                    request.id,
                ),
            )
        return request

    def _row_to_contract(self, row: sqlite3.Row) -> Contract:
        if "payload_json" in row.keys() and row["payload_json"]:
            payload = _load_json(row["payload_json"])
            if isinstance(payload, dict):
                payload["status"] = row["status"]
                return Contract.model_validate(normalize_rule_payload(payload))
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
        if "validity_json" in row_keys and row["validity_json"]:
            payload["validity"] = _load_json(row["validity_json"])
        return Contract.model_validate(normalize_rule_payload(payload))

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

    def _row_to_action_log_entry(self, row: sqlite3.Row) -> ActionLogEntryV1:
        return ActionLogEntryV1(
            seq=row["seq"],
            timestamp=row["timestamp"],
            session_id=row["session_id"],
            agent_id=row["agent_id"],
            adapter_id=row["adapter_id"],
            tool_call_id=row["tool_call_id"],
            tool_name=row["tool_name"],
            host_action=row["host_action"],
            arguments=_load_json(row["arguments_json"]),
            result=_load_json(row["result_json"]),
            result_text=row["result_text"],
            outcome=ActionOutcome(row["outcome"]),
            reasoning_text=row["reasoning_text"],
            conversation_id=row["conversation_id"],
            turn_id=row["turn_id"],
            user_id=row["user_id"],
            workspace=row["workspace"],
            repo=row["repo"],
            branch=row["branch"],
            targets=_load_json(row["targets_json"]) or [],
            risk=row["risk"],
            side_effect=row["side_effect"],
        )


def _action_log_identity_payload(entry: ActionLogEntryV1) -> dict[str, Any]:
    payload = entry.model_dump(mode="json")
    payload.pop("seq", None)
    payload.pop("timestamp", None)
    return payload


def _validator_state_params(state: ValidatorState) -> tuple[Any, ...]:
    return (
        state.validator_version_id,
        state.scope_key,
        state.contract_id,
        _dump_json(state.state),
        state.revision,
        state.last_applied_seq,
        int(state.degraded),
        state.model_dump_json(),
        state.updated_at.isoformat(),
    )
