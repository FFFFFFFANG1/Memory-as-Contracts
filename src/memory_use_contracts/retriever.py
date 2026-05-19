from __future__ import annotations

from fnmatch import fnmatch

from memory_use_contracts.models import ActionSignature, Contract, ContractStatus
from memory_use_contracts.resolver import authority_score, scope_specificity
from memory_use_contracts.store import ContractStore


class ContractRetriever:
    def __init__(self, store: ContractStore):
        self.store = store

    def retrieve(self, action: ActionSignature, limit: int = 10) -> list[Contract]:
        query = " ".join(part for part in [action.intent, action.target or ""] if part)
        candidates_by_id = {
            contract.id: contract
            for contract in self.store.list_contracts()
            if contract.status in {ContractStatus.ACTIVE, ContractStatus.PENDING_CONFLICT}
        }
        candidates_by_id.update(
            {contract.id: contract for contract in self.store.search_contracts(query, limit=50)}
        )
        candidates = list(candidates_by_id.values())
        filtered = [
            contract
            for contract in candidates
            if self._matches_action(contract, action)
            and contract.status in {ContractStatus.ACTIVE, ContractStatus.PENDING_CONFLICT}
        ]
        return sorted(filtered, key=self._rank_key, reverse=True)[:limit]

    def _matches_action(self, contract: Contract, action: ActionSignature) -> bool:
        if contract.is_expired():
            return False
        if contract.action_classes and action.action_class not in contract.action_classes:
            return False
        if contract.scope.path_globs and action.target:
            return any(fnmatch(action.target, pattern) for pattern in contract.scope.path_globs)
        if contract.scope.path_globs and not action.target:
            return False
        return True

    def _rank_key(self, contract: Contract) -> tuple[int, int, float]:
        return (authority_score(contract), scope_specificity(contract), contract.confidence)
