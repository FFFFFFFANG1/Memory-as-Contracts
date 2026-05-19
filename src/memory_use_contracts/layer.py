from __future__ import annotations

from memory_use_contracts.config import Settings, load_settings
from memory_use_contracts.extractor import ContractExtractor
from memory_use_contracts.gate import ContractGate
from memory_use_contracts.models import (
    ActionSignature,
    Contract,
    ContractEdge,
    ContractEdgeType,
    ContractStatus,
    GateDecision,
    InfluenceReceipt,
    SourceKind,
)
from memory_use_contracts.receipts import build_receipt
from memory_use_contracts.resolver import ConflictResolver
from memory_use_contracts.retriever import ContractRetriever
from memory_use_contracts.store import ContractStore


class MemoryContractLayer:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.store = ContractStore(settings.db_path)
        self.extractor = ContractExtractor(settings)
        self.resolver = ConflictResolver()
        self.retriever = ContractRetriever(self.store)
        self.gate_engine = ContractGate()

    @classmethod
    def from_env(cls) -> "MemoryContractLayer":
        return cls(load_settings())

    def init(self) -> None:
        self.store.init()

    def ingest_text(
        self,
        text: str,
        source_kind: SourceKind,
        workspace: str = "default",
        source_path: str | None = None,
        source_fingerprint: str | None = None,
        supersede_source: bool = False,
    ) -> list[Contract]:
        superseded_source_ids: list[str] = []
        if supersede_source and source_path:
            superseded_source_ids = self._mark_source_contracts_superseded(source_path, workspace)
        existing = self.store.list_contracts()
        candidates = self.extractor.extract(text, source_kind=source_kind, workspace=workspace)
        activated: list[Contract] = []
        for candidate in candidates:
            candidate.source.path = source_path
            candidate.source.fingerprint = source_fingerprint
            candidate.supersedes = sorted(set(candidate.supersedes + superseded_source_ids))
            resolved = self._resolve_and_store(candidate, existing + activated)
            for old_id in superseded_source_ids:
                self.store.add_edge(
                    ContractEdge(
                        source_contract_id=resolved.id,
                        target_contract_id=old_id,
                        relation=ContractEdgeType.SUPERSEDES,
                        reason="source_file_refresh",
                    )
                )
            activated.append(resolved)
        return activated

    def add_contract(self, contract: Contract) -> Contract:
        existing = self.store.list_contracts()
        return self._resolve_and_store(contract, existing)

    def gate(self, action: ActionSignature) -> GateDecision:
        contracts = self.retriever.retrieve(action)
        return self.gate_engine.decide(action, contracts)

    def record_result(
        self,
        action: ActionSignature,
        decision: GateDecision,
        result: str,
    ) -> InfluenceReceipt:
        receipt = build_receipt(action, decision, result=result)
        self.store.add_receipt(receipt)
        return receipt

    def _resolve_and_store(self, contract: Contract, existing: list[Contract]) -> Contract:
        resolution = self.resolver.resolve(contract, existing)
        self.store.upsert_contract(resolution.contract)
        for superseded_id in resolution.superseded_ids:
            self.store.update_contract_status(superseded_id, ContractStatus.SUPERSEDED)
            self.store.add_edge(
                ContractEdge(
                    source_contract_id=resolution.contract.id,
                    target_contract_id=superseded_id,
                    relation=ContractEdgeType.SUPERSEDES,
                    reason="higher_precedence_contract",
                )
            )
        for conflict_id in resolution.conflict_ids:
            self.store.add_edge(
                ContractEdge(
                    source_contract_id=resolution.contract.id,
                    target_contract_id=conflict_id,
                    relation=ContractEdgeType.CONFLICTS_WITH,
                    reason="equal_precedence_conflict",
                )
            )
        if resolution.rejected_by_id:
            self.store.add_edge(
                ContractEdge(
                    source_contract_id=resolution.contract.id,
                    target_contract_id=resolution.rejected_by_id,
                    relation=ContractEdgeType.REJECTED_BY,
                    reason="lower_precedence_contract",
                )
            )
        return resolution.contract

    def _mark_source_contracts_superseded(self, source_path: str, workspace: str) -> list[str]:
        old_contracts = self.store.list_contracts_by_source(
            source_path=source_path,
            workspace=workspace,
            status=ContractStatus.ACTIVE,
        )
        for old_contract in old_contracts:
            self.store.update_contract_status(old_contract.id, ContractStatus.SUPERSEDED)
        return [contract.id for contract in old_contracts]
