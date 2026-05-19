from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path

from memory_use_contracts.models import (
    Contract,
    ContractEdge,
    ContractStatus,
    InfluenceReceipt,
    SourceSnapshot,
)


class ContractStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    def init(self) -> None:
        with self.connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS contracts (
                    id TEXT PRIMARY KEY,
                    text TEXT NOT NULL,
                    status TEXT NOT NULL,
                    type TEXT NOT NULL,
                    strength TEXT NOT NULL,
                    source_kind TEXT NOT NULL,
                    workspace TEXT NOT NULL,
                    source_path TEXT,
                    source_fingerprint TEXT,
                    payload TEXT NOT NULL
                );
                CREATE VIRTUAL TABLE IF NOT EXISTS contracts_fts
                USING fts5(id UNINDEXED, text);
                CREATE TABLE IF NOT EXISTS receipts (
                    id TEXT PRIMARY KEY,
                    action_id TEXT NOT NULL,
                    payload TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS contract_edges (
                    id TEXT PRIMARY KEY,
                    source_contract_id TEXT NOT NULL,
                    target_contract_id TEXT NOT NULL,
                    relation TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    payload TEXT NOT NULL
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
                    payload TEXT NOT NULL
                );
                """
            )
            _ensure_column(conn, "contracts", "source_path", "TEXT")
            _ensure_column(conn, "contracts", "source_fingerprint", "TEXT")

    def upsert_contract(self, contract: Contract) -> None:
        self.init()
        payload = contract.model_dump_json()
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO contracts
                    (
                        id, text, status, type, strength, source_kind, workspace,
                        source_path, source_fingerprint, payload
                    )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    text=excluded.text,
                    status=excluded.status,
                    type=excluded.type,
                    strength=excluded.strength,
                    source_kind=excluded.source_kind,
                    workspace=excluded.workspace,
                    source_path=excluded.source_path,
                    source_fingerprint=excluded.source_fingerprint,
                    payload=excluded.payload
                """,
                (
                    contract.id,
                    contract.text,
                    contract.status.value,
                    contract.type.value,
                    contract.strength.value,
                    contract.source.kind.value,
                    contract.scope.workspace,
                    contract.source.path,
                    contract.source.fingerprint,
                    payload,
                ),
            )
            conn.execute("DELETE FROM contracts_fts WHERE id = ?", (contract.id,))
            conn.execute(
                "INSERT INTO contracts_fts (id, text) VALUES (?, ?)",
                (contract.id, contract.text),
            )

    def list_contracts(self, status: ContractStatus | None = None) -> list[Contract]:
        self.init()
        with self.connect() as conn:
            if status:
                rows = conn.execute(
                    "SELECT payload FROM contracts WHERE status = ? ORDER BY id",
                    (status.value,),
                ).fetchall()
            else:
                rows = conn.execute("SELECT payload FROM contracts ORDER BY id").fetchall()
        return [Contract.model_validate_json(row["payload"]) for row in rows]

    def list_contracts_by_source(
        self,
        source_path: str,
        workspace: str,
        status: ContractStatus | None = None,
    ) -> list[Contract]:
        self.init()
        with self.connect() as conn:
            if status:
                rows = conn.execute(
                    """
                    SELECT payload FROM contracts
                    WHERE source_path = ? AND workspace = ? AND status = ?
                    ORDER BY id
                    """,
                    (source_path, workspace, status.value),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT payload FROM contracts
                    WHERE source_path = ? AND workspace = ?
                    ORDER BY id
                    """,
                    (source_path, workspace),
                ).fetchall()
        return [Contract.model_validate_json(row["payload"]) for row in rows]

    def update_contract_status(self, contract_id: str, status: ContractStatus) -> Contract | None:
        contract = self.get_contract(contract_id)
        if contract is None:
            return None
        contract.status = status
        self.upsert_contract(contract)
        return contract

    def get_contract(self, contract_id: str) -> Contract | None:
        self.init()
        with self.connect() as conn:
            row = conn.execute(
                "SELECT payload FROM contracts WHERE id = ?",
                (contract_id,),
            ).fetchone()
        return Contract.model_validate_json(row["payload"]) if row else None

    def search_contracts(self, query: str, limit: int = 20) -> list[Contract]:
        self.init()
        safe_query = _fts_query(query)
        if not safe_query:
            return self.list_contracts(ContractStatus.ACTIVE)[:limit]
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT c.payload
                FROM contracts_fts f
                JOIN contracts c ON c.id = f.id
                WHERE contracts_fts MATCH ?
                ORDER BY bm25(contracts_fts)
                LIMIT ?
                """,
                (safe_query, limit),
            ).fetchall()
        return [Contract.model_validate_json(row["payload"]) for row in rows]

    def add_receipt(self, receipt: InfluenceReceipt) -> None:
        self.init()
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO receipts (id, action_id, payload) VALUES (?, ?, ?)",
                (receipt.id, receipt.action_id, receipt.model_dump_json()),
            )

    def list_receipts(self) -> list[InfluenceReceipt]:
        self.init()
        with self.connect() as conn:
            rows = conn.execute("SELECT payload FROM receipts ORDER BY id").fetchall()
        return [InfluenceReceipt.model_validate(json.loads(row["payload"])) for row in rows]

    def add_edge(self, edge: ContractEdge) -> None:
        self.init()
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO contract_edges
                    (id, source_contract_id, target_contract_id, relation, reason, created_at, payload)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    source_contract_id=excluded.source_contract_id,
                    target_contract_id=excluded.target_contract_id,
                    relation=excluded.relation,
                    reason=excluded.reason,
                    created_at=excluded.created_at,
                    payload=excluded.payload
                """,
                (
                    edge.id,
                    edge.source_contract_id,
                    edge.target_contract_id,
                    edge.relation.value,
                    edge.reason,
                    edge.created_at.isoformat(),
                    edge.model_dump_json(),
                ),
            )

    def list_edges(self) -> list[ContractEdge]:
        self.init()
        with self.connect() as conn:
            rows = conn.execute("SELECT payload FROM contract_edges ORDER BY created_at, id").fetchall()
        return [ContractEdge.model_validate_json(row["payload"]) for row in rows]

    def get_snapshot(self, source_key: str) -> SourceSnapshot | None:
        self.init()
        with self.connect() as conn:
            row = conn.execute(
                "SELECT payload FROM source_snapshots WHERE source_key = ?",
                (source_key,),
            ).fetchone()
        return SourceSnapshot.model_validate_json(row["payload"]) if row else None

    def upsert_snapshot(self, snapshot: SourceSnapshot) -> None:
        self.init()
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO source_snapshots
                    (
                        source_key, adapter, path, workspace, source_kind, fingerprint,
                        content, observed_at, payload
                    )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(source_key) DO UPDATE SET
                    adapter=excluded.adapter,
                    path=excluded.path,
                    workspace=excluded.workspace,
                    source_kind=excluded.source_kind,
                    fingerprint=excluded.fingerprint,
                    content=excluded.content,
                    observed_at=excluded.observed_at,
                    payload=excluded.payload
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
                    snapshot.model_dump_json(),
                ),
            )

    def list_snapshots(self) -> list[SourceSnapshot]:
        self.init()
        with self.connect() as conn:
            rows = conn.execute("SELECT payload FROM source_snapshots ORDER BY path").fetchall()
        return [SourceSnapshot.model_validate_json(row["payload"]) for row in rows]


def _fts_query(query: str) -> str:
    tokens = re.findall(r"[A-Za-z0-9_]+", query)
    return " ".join(tokens)


def _ensure_column(conn: sqlite3.Connection, table: str, column: str, column_type: str) -> None:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    if column not in {row["name"] for row in rows}:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {column_type}")
