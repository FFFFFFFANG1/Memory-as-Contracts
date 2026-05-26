from __future__ import annotations

import json
import math
import re
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from fnmatch import fnmatch

from memory_as_contracts.matching import scope_specificity
from memory_as_contracts.models import (
    Contract,
    ContractEdge,
    ContractKind,
    ContractStatus,
    EdgeRelation,
    Modality,
    SourceKind,
    Strength,
)
from memory_as_contracts.store import ContractStore


RELATION_CLASSIFICATION_SYSTEM_PROMPT = """
You classify relations between a new Memory-as-Contracts contract and existing
contracts. Return only valid JSON.

Allowed relations:
- duplicate: same behavioral rule or paraphrase in overlapping scope.
- refinement: compatible rule that narrows, clarifies, or adds detail.
- supersedes: new rule explicitly replaces old rule.
- conflicts_with: rules cannot both govern the same action/scope safely.
- exception_to: new rule is a concrete narrower allowance to an existing rule.
- independent: no update relation is needed.

Use the provided similarity scores only as retrieval evidence, not as the final
label. Prefer independent when uncertain.
""".strip()


DEFAULT_RELATION_SIMILARITY_THRESHOLD = 0.35
DEFAULT_RELATION_TOP_K = 3
TEXT_SIMILARITY_WEIGHT = 0.70
PATTERN_SIMILARITY_WEIGHT = 0.30


SOURCE_AUTHORITY = {
    SourceKind.USER_TURN: 100,
    SourceKind.PROJECT_DOC: 70,
    SourceKind.MEMORY_FILE: 60,
    SourceKind.USER_PROFILE: 60,
    SourceKind.TOOL_OBSERVATION: 30,
    SourceKind.AGENT_INFERRED: 10,
}


@dataclass
class ResolutionResult:
    contract: Contract
    edges: list[ContractEdge] = field(default_factory=list)
    relation: EdgeRelation = EdgeRelation.INDEPENDENT


@dataclass(frozen=True)
class DedupCandidate:
    existing: Contract
    relation: EdgeRelation
    similarity: float
    text_score: float = 0.0
    pattern_score: float = 0.0


@dataclass(frozen=True)
class RelationCandidate:
    existing: Contract
    similarity: float
    text_score: float
    pattern_score: float


@dataclass(frozen=True)
class RelationDecision:
    candidate: Contract
    existing: Contract
    relation: EdgeRelation
    similarity: float
    text_score: float
    pattern_score: float


class ConflictResolver:
    """Contract relation resolver with LLM classification and deterministic fallback."""

    def __init__(
        self,
        store: ContractStore,
        *,
        relation_response_provider: Callable[[str], str] | None = None,
        similarity_threshold: float = DEFAULT_RELATION_SIMILARITY_THRESHOLD,
        top_k: int = DEFAULT_RELATION_TOP_K,
        max_relation_workers: int = 4,
    ) -> None:
        self.store = store
        self.relation_response_provider = relation_response_provider
        self.similarity_threshold = similarity_threshold
        self.top_k = top_k
        self.max_relation_workers = max_relation_workers

    def insert(self, candidate: Contract) -> ResolutionResult:
        existing_contracts = self.store.list_contracts(
            [ContractStatus.ACTIVE, ContractStatus.PENDING_CONFLICT],
            include_expired_status=False,
        )
        result = ResolutionResult(contract=candidate)

        relation_decisions = self.classify_update_relations(candidate, existing_contracts)
        for decision in relation_decisions:
            if decision.relation == EdgeRelation.INDEPENDENT:
                continue
            result.relation = decision.relation
            candidate, edge = self._apply_relation(candidate, decision.existing, decision.relation)
            result.contract = candidate
            result.edges.append(edge)
            if candidate.status == ContractStatus.REJECTED:
                self.store.add_contract(candidate)
                for stored_edge in result.edges:
                    self.store.add_edge(stored_edge)
                return result

        self.store.add_contract(candidate)
        for edge in result.edges:
            self.store.add_edge(edge)
        return result

    def insert_batch(self, candidates: list[Contract]) -> list[ResolutionResult]:
        if not candidates:
            return []
        existing_contracts = self.store.list_contracts(
            [ContractStatus.ACTIVE, ContractStatus.PENDING_CONFLICT],
            include_expired_status=False,
        )
        relation_candidates_by_new = {
            candidate.id: self.find_relation_candidates(candidate, existing_contracts)
            for candidate in candidates
        }
        components = _relation_components(candidates, relation_candidates_by_new)
        relation_decisions: list[RelationDecision] = []
        if len(components) == 1:
            relation_decisions = self._classify_component(
                components[0],
                relation_candidates_by_new,
            )
        else:
            workers = max(1, min(self.max_relation_workers, len(components)))
            with ThreadPoolExecutor(max_workers=workers) as executor:
                futures = [
                    executor.submit(
                        self._classify_component,
                        component,
                        relation_candidates_by_new,
                    )
                    for component in components
                ]
                for future in futures:
                    relation_decisions.extend(future.result())
        return self._apply_batch(candidates, relation_decisions)

    def classify_update_relations(
        self,
        candidate: Contract,
        existing_contracts: list[Contract] | None = None,
    ) -> list[RelationDecision]:
        relation_candidates = self.find_relation_candidates(candidate, existing_contracts)
        if not relation_candidates:
            return []
        if self.relation_response_provider is not None:
            decisions = self._classify_with_llm(candidate, relation_candidates)
            if decisions is not None:
                return decisions
        return [
            RelationDecision(
                candidate=candidate,
                existing=item.existing,
                relation=self.classify_relation(candidate, item.existing),
                similarity=item.similarity,
                text_score=item.text_score,
                pattern_score=item.pattern_score,
            )
            for item in relation_candidates
        ]

    def find_dedup_candidates(
        self,
        candidate: Contract,
        existing_contracts: list[Contract] | None = None,
        *,
        min_similarity: float = DEFAULT_RELATION_SIMILARITY_THRESHOLD,
    ) -> list[DedupCandidate]:
        candidates = self.find_relation_candidates(
            candidate,
            existing_contracts,
            min_similarity=min_similarity,
            top_k=None,
        )
        result: list[DedupCandidate] = []
        for item in candidates:
            if not _same_direction(candidate, item.existing):
                continue
            relation = (
                EdgeRelation.DUPLICATE
                if _is_duplicate(candidate, item.existing, item.similarity)
                else EdgeRelation.REFINEMENT
            )
            result.append(
                DedupCandidate(
                    existing=item.existing,
                    relation=relation,
                    similarity=item.similarity,
                    text_score=item.text_score,
                    pattern_score=item.pattern_score,
                )
            )
        return result

    def find_relation_candidates(
        self,
        candidate: Contract,
        existing_contracts: list[Contract] | None = None,
        *,
        min_similarity: float | None = None,
        top_k: int | None = DEFAULT_RELATION_TOP_K,
    ) -> list[RelationCandidate]:
        pool = existing_contracts
        if pool is None:
            pool = self.store.list_contracts(
                [ContractStatus.ACTIVE, ContractStatus.PENDING_CONFLICT],
                include_expired_status=False,
            )
        scoped_pool = [
            existing
            for existing in pool
            if existing.id != candidate.id and _scope_lifecycle_overlaps(candidate, existing)
        ]
        if not scoped_pool:
            return []
        threshold = self.similarity_threshold if min_similarity is None else min_similarity
        text_corpus = [candidate.text, *[contract.text for contract in scoped_pool]]
        matches: list[RelationCandidate] = []
        candidate_pattern_text = _predicate_pattern_text(candidate)
        for existing in scoped_pool:
            if existing.id == candidate.id:
                continue
            text_score = _bm25_similarity(candidate.text, existing.text, text_corpus)
            pattern_score = _word_overlap_score(
                candidate_pattern_text,
                _predicate_pattern_text(existing),
            )
            similarity = (
                TEXT_SIMILARITY_WEIGHT * text_score
                + PATTERN_SIMILARITY_WEIGHT * pattern_score
            )
            if similarity < threshold:
                continue
            matches.append(
                RelationCandidate(
                    existing=existing,
                    similarity=similarity,
                    text_score=text_score,
                    pattern_score=pattern_score,
                )
            )
        ranked = sorted(matches, key=lambda item: item.similarity, reverse=True)
        limit = self.top_k if top_k == DEFAULT_RELATION_TOP_K else top_k
        if limit is None:
            return ranked
        return ranked[:limit]

    def classify_relation(self, candidate: Contract, existing: Contract) -> EdgeRelation:
        if _normalize(candidate.text) == _normalize(existing.text) and candidate.scope == existing.scope:
            return EdgeRelation.DUPLICATE
        if candidate.kind == ContractKind.EXCEPTION:
            return EdgeRelation.EXCEPTION_TO if _overlaps(candidate, existing) else EdgeRelation.INDEPENDENT
        if _says_supersedes(candidate.text) and _overlaps(candidate, existing):
            return EdgeRelation.SUPERSEDES
        if _overlaps(candidate, existing) and _same_direction(candidate, existing):
            if _contract_similarity(candidate, existing) >= 0.62:
                return EdgeRelation.DUPLICATE
        if _contradicts(candidate, existing):
            return EdgeRelation.CONFLICTS_WITH
        if _overlaps(candidate, existing) and _same_direction(candidate, existing):
            if _is_refinement(candidate, existing):
                return EdgeRelation.REFINEMENT
        return EdgeRelation.INDEPENDENT

    def _classify_with_llm(
        self,
        candidate: Contract,
        relation_candidates: list[RelationCandidate],
    ) -> list[RelationDecision] | None:
        if self.relation_response_provider is None:
            return None
        prompt = _relation_prompt(candidate, relation_candidates)
        try:
            raw = self.relation_response_provider(prompt)
            payload = _load_relation_payload(raw)
        except Exception:
            return None
        if not isinstance(payload, dict):
            return None
        rows = payload.get("relations")
        if not isinstance(rows, list):
            return None
        by_id = {item.existing.id: item for item in relation_candidates}
        decisions: list[RelationDecision] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            existing_id = str(row.get("existing_id") or "")
            relation = _relation_from_value(row.get("relation"))
            item = by_id.get(existing_id)
            if item is None or relation is None:
                continue
            decisions.append(
                RelationDecision(
                    candidate=candidate,
                    existing=item.existing,
                    relation=relation,
                    similarity=item.similarity,
                    text_score=item.text_score,
                    pattern_score=item.pattern_score,
                )
            )
        if not decisions:
            return None
        seen = {decision.existing.id for decision in decisions}
        for item in relation_candidates:
            if item.existing.id not in seen:
                decisions.append(
                    RelationDecision(
                        candidate=candidate,
                        existing=item.existing,
                        relation=EdgeRelation.INDEPENDENT,
                        similarity=item.similarity,
                        text_score=item.text_score,
                        pattern_score=item.pattern_score,
                    )
                )
        return sorted(decisions, key=lambda item: item.similarity, reverse=True)

    def _classify_component(
        self,
        candidates: list[Contract],
        relation_candidates_by_new: dict[str, list[RelationCandidate]],
    ) -> list[RelationDecision]:
        if len(candidates) == 1:
            candidate = candidates[0]
            relation_candidates = relation_candidates_by_new[candidate.id]
            if not relation_candidates:
                return []
            if self.relation_response_provider is not None:
                decisions = self._classify_with_llm(candidate, relation_candidates)
                if decisions is not None:
                    return decisions
            return self._fallback_component_decisions(candidates, relation_candidates_by_new)
        if self.relation_response_provider is not None:
            decisions = self._classify_batch_with_llm(candidates, relation_candidates_by_new)
            if decisions is not None:
                return decisions
        return self._fallback_component_decisions(candidates, relation_candidates_by_new)

    def _classify_batch_with_llm(
        self,
        candidates: list[Contract],
        relation_candidates_by_new: dict[str, list[RelationCandidate]],
    ) -> list[RelationDecision] | None:
        if self.relation_response_provider is None:
            return None
        prompt = _batch_relation_prompt(candidates, relation_candidates_by_new)
        try:
            raw = self.relation_response_provider(prompt)
            payload = _load_relation_payload(raw)
        except Exception:
            return None
        if not isinstance(payload, dict):
            return None
        rows = payload.get("relations")
        if not isinstance(rows, list):
            return None
        candidates_by_id = {candidate.id: candidate for candidate in candidates}
        by_pair = {
            (candidate.id, item.existing.id): item
            for candidate in candidates
            for item in relation_candidates_by_new.get(candidate.id, [])
        }
        decisions: list[RelationDecision] = []
        seen_pairs: set[tuple[str, str]] = set()
        for row in rows:
            if not isinstance(row, dict):
                continue
            candidate_id = str(row.get("new_id") or row.get("candidate_id") or "")
            existing_id = str(row.get("existing_id") or "")
            relation = _relation_from_value(row.get("relation"))
            candidate = candidates_by_id.get(candidate_id)
            item = by_pair.get((candidate_id, existing_id))
            if candidate is None or item is None or relation is None:
                continue
            seen_pairs.add((candidate_id, existing_id))
            decisions.append(
                RelationDecision(
                    candidate=candidate,
                    existing=item.existing,
                    relation=relation,
                    similarity=item.similarity,
                    text_score=item.text_score,
                    pattern_score=item.pattern_score,
                )
            )
        if not decisions:
            return None
        for (candidate_id, existing_id), item in by_pair.items():
            if (candidate_id, existing_id) in seen_pairs:
                continue
            candidate = candidates_by_id[candidate_id]
            decisions.append(
                RelationDecision(
                    candidate=candidate,
                    existing=item.existing,
                    relation=EdgeRelation.INDEPENDENT,
                    similarity=item.similarity,
                    text_score=item.text_score,
                    pattern_score=item.pattern_score,
                )
            )
        return sorted(decisions, key=lambda item: item.similarity, reverse=True)

    def _fallback_component_decisions(
        self,
        candidates: list[Contract],
        relation_candidates_by_new: dict[str, list[RelationCandidate]],
    ) -> list[RelationDecision]:
        return [
            RelationDecision(
                candidate=candidate,
                existing=item.existing,
                relation=self.classify_relation(candidate, item.existing),
                similarity=item.similarity,
                text_score=item.text_score,
                pattern_score=item.pattern_score,
            )
            for candidate in candidates
            for item in relation_candidates_by_new.get(candidate.id, [])
        ]

    def _apply_batch(
        self,
        candidates: list[Contract],
        relation_decisions: list[RelationDecision],
    ) -> list[ResolutionResult]:
        results = {candidate.id: ResolutionResult(contract=candidate) for candidate in candidates}
        current_contracts = {candidate.id: candidate for candidate in candidates}
        candidate_order = {candidate.id: index for index, candidate in enumerate(candidates)}
        ordered_decisions = sorted(
            relation_decisions,
            key=lambda item: (candidate_order[item.candidate.id], -item.similarity),
        )
        for decision in ordered_decisions:
            if decision.relation == EdgeRelation.INDEPENDENT:
                continue
            candidate = current_contracts[decision.candidate.id]
            if candidate.status == ContractStatus.REJECTED:
                continue
            updated, edge = self._apply_relation(candidate, decision.existing, decision.relation)
            current_contracts[decision.candidate.id] = updated
            result = results[decision.candidate.id]
            result.contract = updated
            result.relation = decision.relation
            result.edges.append(edge)

        ordered_results = [results[candidate.id] for candidate in candidates]
        for result in ordered_results:
            self.store.add_contract(current_contracts[result.contract.id])
            result.contract = current_contracts[result.contract.id]
        for result in ordered_results:
            for edge in result.edges:
                self.store.add_edge(edge)
        return ordered_results

    def _apply_relation(
        self,
        candidate: Contract,
        existing: Contract,
        relation: EdgeRelation,
    ) -> tuple[Contract, ContractEdge]:
        if relation == EdgeRelation.DUPLICATE:
            if _compare_precedence(candidate, existing) > 0:
                self.store.update_contract_status(existing.id, ContractStatus.SUPERSEDED)
            else:
                candidate = candidate.model_copy(update={"status": ContractStatus.REJECTED})
            return candidate, _edge(candidate, existing, relation)

        if relation in {EdgeRelation.SUPERSEDES, EdgeRelation.EXCEPTION_TO}:
            if relation == EdgeRelation.SUPERSEDES:
                self.store.update_contract_status(existing.id, ContractStatus.SUPERSEDED)
                candidate = candidate.model_copy(
                    update={"supersedes": sorted({*candidate.supersedes, existing.id})}
                )
            return candidate, _edge(candidate, existing, relation)

        if relation == EdgeRelation.CONFLICTS_WITH:
            precedence = _compare_precedence(candidate, existing)
            if precedence > 0:
                self.store.update_contract_status(existing.id, ContractStatus.SUPERSEDED)
                candidate = candidate.model_copy(
                    update={"supersedes": sorted({*candidate.supersedes, existing.id})}
                )
            elif precedence == 0:
                candidate = candidate.model_copy(
                    update={
                        "status": ContractStatus.PENDING_CONFLICT,
                        "conflicts_with": sorted({*candidate.conflicts_with, existing.id}),
                    }
                )
            else:
                candidate = candidate.model_copy(
                    update={
                        "status": ContractStatus.REJECTED,
                        "conflicts_with": sorted({*candidate.conflicts_with, existing.id}),
                    }
                )
            return candidate, _edge(candidate, existing, relation)

        return candidate, _edge(candidate, existing, relation)


def _edge(candidate: Contract, existing: Contract, relation: EdgeRelation) -> ContractEdge:
    return ContractEdge(
        from_contract=candidate.id,
        to_contract=existing.id,
        relation=relation,
        scope=candidate.scope,
        lifecycle=candidate.lifecycle,
        source=candidate.source,
        confidence=min(candidate.confidence, existing.confidence),
    )


def _relation_components(
    candidates: list[Contract],
    relation_candidates_by_new: dict[str, list[RelationCandidate]],
) -> list[list[Contract]]:
    ids = [candidate.id for candidate in candidates]
    parent = {candidate_id: candidate_id for candidate_id in ids}

    def find(candidate_id: str) -> str:
        while parent[candidate_id] != candidate_id:
            parent[candidate_id] = parent[parent[candidate_id]]
            candidate_id = parent[candidate_id]
        return candidate_id

    def union(left: str, right: str) -> None:
        left_root = find(left)
        right_root = find(right)
        if left_root != right_root:
            parent[right_root] = left_root

    seen_by_existing: dict[str, str] = {}
    for candidate in candidates:
        for item in relation_candidates_by_new.get(candidate.id, []):
            previous = seen_by_existing.get(item.existing.id)
            if previous is None:
                seen_by_existing[item.existing.id] = candidate.id
            else:
                union(previous, candidate.id)

    components_by_root: dict[str, list[Contract]] = {}
    for candidate in candidates:
        components_by_root.setdefault(find(candidate.id), []).append(candidate)
    return list(components_by_root.values())


def _relation_prompt(candidate: Contract, relation_candidates: list[RelationCandidate]) -> str:
    candidates_json = [
        _relation_candidate_payload(item)
        for item in relation_candidates
    ]
    candidate_json = _contract_payload(candidate)
    return (
        f"{RELATION_CLASSIFICATION_SYSTEM_PROMPT}\n\n"
        "Similarity is 0.7 * text_score + 0.3 * pattern_score. text_score is "
        "BM25 over contract text; pattern_score is word overlap over "
        "host_action/tool_name/parameter_regex predicate text.\n"
        "Classify every candidate pair. Return exactly this JSON shape:\n"
        '{"relations":[{"existing_id":"MAC-...",'
        '"relation":"duplicate|refinement|supersedes|conflicts_with|exception_to|independent",'
        '"reason":"short reason"}]}\n\n'
        f"New contract:\n{json.dumps(candidate_json, sort_keys=True)}\n\n"
        f"Retrieved candidates:\n{json.dumps(candidates_json, sort_keys=True)}"
    )


def _batch_relation_prompt(
    candidates: list[Contract],
    relation_candidates_by_new: dict[str, list[RelationCandidate]],
) -> str:
    existing_to_new_ids: dict[str, set[str]] = {}
    for candidate in candidates:
        for item in relation_candidates_by_new.get(candidate.id, []):
            existing_to_new_ids.setdefault(item.existing.id, set()).add(candidate.id)

    unique_retrieved_rules: dict[str, list[dict]] = {}
    overlapped_by_existing: dict[str, dict] = {}
    for candidate in candidates:
        unique_retrieved_rules[candidate.id] = []
        for item in relation_candidates_by_new.get(candidate.id, []):
            new_ids = existing_to_new_ids[item.existing.id]
            payload = _relation_candidate_payload(item)
            if len(new_ids) == 1:
                unique_retrieved_rules[candidate.id].append(payload)
            else:
                entry = overlapped_by_existing.setdefault(
                    item.existing.id,
                    {
                        "existing_rule": _contract_payload(item.existing),
                        "matched_new_ids": sorted(new_ids),
                        "scores_by_new_id": {},
                    },
                )
                entry["scores_by_new_id"][candidate.id] = {
                    "similarity": round(item.similarity, 4),
                    "text_score": round(item.text_score, 4),
                    "pattern_score": round(item.pattern_score, 4),
                }

    payload = {
        "new_rules": [_contract_payload(candidate) for candidate in candidates],
        "unique_retrieved_rules": unique_retrieved_rules,
        "overlapped_retrieved_rules": list(overlapped_by_existing.values()),
    }
    return (
        f"{RELATION_CLASSIFICATION_SYSTEM_PROMPT}\n\n"
        "This is a batch relation-classification component. Multiple new rules "
        "share at least one retrieved existing rule, so classify the component as "
        "one graph rather than as independent pairwise updates.\n"
        "Return relation edges only; do not decide final active/rejected/superseded "
        "status. The deterministic apply phase handles status updates.\n"
        "Return exactly this JSON shape:\n"
        '{"relations":[{"new_id":"MAC-new", "existing_id":"MAC-existing", '
        '"relation":"duplicate|refinement|supersedes|conflicts_with|exception_to|independent", '
        '"reason":"short reason"}]}\n\n'
        f"Batch input:\n{json.dumps(payload, sort_keys=True)}"
    )


def _contract_payload(contract: Contract) -> dict:
    return {
        "id": contract.id,
        "text": contract.text,
        "kind": contract.kind.value,
        "modality": contract.modality.value,
        "source": contract.source.kind.value,
        "scope": contract.scope.model_dump(mode="json"),
        "lifecycle": contract.lifecycle.model_dump(mode="json"),
        "action_constraints": contract.action_constraints.model_dump(mode="json"),
        "predicate_pattern": _predicate_pattern_text(contract),
    }


def _relation_candidate_payload(item: RelationCandidate) -> dict:
    return {
        "existing_id": item.existing.id,
        "existing_rule": _contract_payload(item.existing),
        "similarity": round(item.similarity, 4),
        "text_score": round(item.text_score, 4),
        "pattern_score": round(item.pattern_score, 4),
    }


def _load_relation_payload(raw: str) -> dict:
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        start = raw.find("{")
        end = raw.rfind("}")
        if start == -1 or end <= start:
            raise
        return json.loads(raw[start : end + 1])


def _relation_from_value(value) -> EdgeRelation | None:
    try:
        return EdgeRelation(value)
    except (TypeError, ValueError):
        return None


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower().rstrip(".。!！"))


def _says_supersedes(text: str) -> bool:
    lower = text.lower()
    return "instead of" in lower or "replace" in lower or "supersede" in lower


def _overlaps(left: Contract, right: Contract) -> bool:
    if left.scope.workspace and right.scope.workspace and left.scope.workspace != right.scope.workspace:
        return False
    if left.scope.repo and right.scope.repo and left.scope.repo != right.scope.repo:
        return False
    if left.action_constraints.host_actions and right.action_constraints.host_actions:
        if not set(left.action_constraints.host_actions).intersection(right.action_constraints.host_actions):
            return False
    if left.action_constraints.canonical_tags and right.action_constraints.canonical_tags:
        if not set(left.action_constraints.canonical_tags).intersection(right.action_constraints.canonical_tags):
            return False
    if left.scope.path_globs and right.scope.path_globs:
        return _path_globs_overlap(left.scope.path_globs, right.scope.path_globs)
    return True


def _scope_lifecycle_overlaps(left: Contract, right: Contract) -> bool:
    if left.is_expired() or right.is_expired():
        return False
    if left.scope.workspace and right.scope.workspace and left.scope.workspace != right.scope.workspace:
        return False
    if left.scope.repo and right.scope.repo and left.scope.repo != right.scope.repo:
        return False
    if left.scope.task and right.scope.task and left.scope.task != right.scope.task:
        return False
    if left.scope.component and right.scope.component and left.scope.component != right.scope.component:
        return False
    if left.scope.path_globs and right.scope.path_globs:
        return _path_globs_overlap(left.scope.path_globs, right.scope.path_globs)
    left_start = left.lifecycle.effective_from
    right_start = right.lifecycle.effective_from
    left_end = left.lifecycle.expires_at
    right_end = right.lifecycle.expires_at
    if left_end is not None and left_end < right_start:
        return False
    if right_end is not None and right_end < left_start:
        return False
    return True


def _contradicts(left: Contract, right: Contract) -> bool:
    if not _overlaps(left, right):
        return False
    left_bans = left.kind == ContractKind.PROHIBITION or left.modality == Modality.MUST_NOT
    right_bans = right.kind == ContractKind.PROHIBITION or right.modality == Modality.MUST_NOT
    left_requires = left.modality == Modality.MUST or left.kind in {
        ContractKind.REQUIREMENT,
        ContractKind.PROCEDURE,
    }
    right_requires = right.modality == Modality.MUST or right.kind in {
        ContractKind.REQUIREMENT,
        ContractKind.PROCEDURE,
    }
    return (left_bans and right_requires) or (right_bans and left_requires)


def _same_direction(left: Contract, right: Contract) -> bool:
    return left.kind == right.kind or left.modality == right.modality


def _contract_similarity(left: Contract, right: Contract) -> float:
    text_score = _text_similarity(left.text, right.text)
    action_score = _set_overlap(
        set(left.action_constraints.host_actions),
        set(right.action_constraints.host_actions),
    )
    tag_score = _set_overlap(
        set(left.action_constraints.canonical_tags),
        set(right.action_constraints.canonical_tags),
    )
    scope_score = 1.0 if left.scope.level == right.scope.level else 0.5
    return (text_score * 0.55) + (action_score * 0.2) + (tag_score * 0.15) + (scope_score * 0.1)


def _is_refinement(candidate: Contract, existing: Contract) -> bool:
    if scope_specificity(candidate.scope) <= scope_specificity(existing.scope):
        if not _has_narrower_action_binding(candidate, existing):
            return False
    if _is_generic_broader_clause(candidate.text, existing.text):
        return False
    candidate_words = _content_words(candidate.text)
    existing_words = _content_words(existing.text)
    if not candidate_words or not existing_words:
        return False
    return bool(candidate_words.intersection(existing_words)) and (
        candidate_words != existing_words
        or _has_narrower_action_binding(candidate, existing)
        or scope_specificity(candidate.scope) > scope_specificity(existing.scope)
    )


def _has_narrower_action_binding(candidate: Contract, existing: Contract) -> bool:
    candidate_actions = set(candidate.action_constraints.host_actions)
    existing_actions = set(existing.action_constraints.host_actions)
    candidate_tags = set(candidate.action_constraints.canonical_tags)
    existing_tags = set(existing.action_constraints.canonical_tags)
    return bool(
        existing_actions
        and candidate_actions
        and candidate_actions < existing_actions
        or existing_tags
        and candidate_tags
        and candidate_tags < existing_tags
    )


def _is_generic_broader_clause(candidate_text: str, existing_text: str) -> bool:
    candidate_lower = candidate_text.lower()
    existing_lower = existing_text.lower()
    generic_markers = ("anything", "any ", "do not publish", "do not browse")
    specific_markers = ("without asking", "approve", "approval", "git push", "web search")
    return any(marker in candidate_lower for marker in generic_markers) and any(
        marker in existing_lower for marker in specific_markers
    )


def _is_duplicate(left: Contract, right: Contract, similarity: float) -> bool:
    return (
        similarity >= DEFAULT_RELATION_SIMILARITY_THRESHOLD
        and left.kind == right.kind
        and left.modality == right.modality
        and left.scope.level == right.scope.level
    )


def _text_similarity(left: str, right: str) -> float:
    left_words = _content_words(left)
    right_words = _content_words(right)
    if not left_words or not right_words:
        return 0.0
    return len(left_words.intersection(right_words)) / len(left_words.union(right_words))


def _set_overlap(left: set[str], right: set[str]) -> float:
    if not left and not right:
        return 1.0
    if not left or not right:
        return 0.0
    return len(left.intersection(right)) / len(left.union(right))


def _content_words(text: str) -> set[str]:
    stop = {
        "a",
        "an",
        "any",
        "before",
        "for",
        "if",
        "in",
        "me",
        "of",
        "the",
        "to",
        "with",
        "without",
    }
    return {word for word in re.findall(r"[a-z0-9_]+", text.lower()) if word not in stop}


def _tokens(text: str) -> list[str]:
    return re.findall(r"[a-z0-9_]+", text.lower())


def _bm25_similarity(query: str, document: str, corpus: list[str]) -> float:
    query_tokens = _tokens(query)
    document_tokens = _tokens(document)
    if not query_tokens or not document_tokens:
        return 0.0
    tokenized_corpus = [_tokens(item) for item in corpus if _tokens(item)]
    if not tokenized_corpus:
        return 0.0
    score = _bm25_score(query_tokens, document_tokens, tokenized_corpus)
    self_score = _bm25_score(query_tokens, query_tokens, tokenized_corpus)
    if self_score <= 0:
        return 0.0
    return min(score / self_score, 1.0)


def _word_overlap_score(left: str, right: str) -> float:
    left_tokens = set(_tokens(left))
    right_tokens = set(_tokens(right))
    if not left_tokens or not right_tokens:
        return 0.0
    return len(left_tokens.intersection(right_tokens)) / min(len(left_tokens), len(right_tokens))


def _bm25_score(query_tokens: list[str], document_tokens: list[str], corpus: list[list[str]]) -> float:
    k1 = 1.5
    b = 0.75
    doc_len = len(document_tokens)
    avg_doc_len = sum(len(item) for item in corpus) / len(corpus)
    frequencies = {token: document_tokens.count(token) for token in set(document_tokens)}
    score = 0.0
    for token in set(query_tokens):
        frequency = frequencies.get(token, 0)
        if frequency == 0:
            continue
        doc_frequency = sum(1 for item in corpus if token in item)
        idf = math.log(1 + (len(corpus) - doc_frequency + 0.5) / (doc_frequency + 0.5))
        denominator = frequency + k1 * (1 - b + b * doc_len / avg_doc_len)
        score += idf * frequency * (k1 + 1) / denominator
    return score


def _predicate_pattern_text(contract: Contract) -> str:
    parts: list[str] = []
    predicates = contract.compiled_predicates
    if predicates is not None:
        for pattern in predicates.host_action_patterns:
            parts.append(pattern.action)
            if pattern.tool_name:
                parts.append(pattern.tool_name)
            if pattern.program:
                parts.append(pattern.program)
            if pattern.subcommand:
                parts.append(pattern.subcommand)
            parts.extend(f"{key} {value}" for key, value in sorted(pattern.parameter_regex.items()))
    parts.extend(contract.action_constraints.host_actions)
    parts.extend(contract.action_constraints.canonical_tags)
    return " ".join(parts)


def _path_globs_overlap(left_globs: list[str], right_globs: list[str]) -> bool:
    for left in left_globs:
        for right in right_globs:
            if left == right:
                return True
            left_prefix = _glob_prefix(left)
            right_prefix = _glob_prefix(right)
            if left_prefix and right_prefix:
                if left_prefix.startswith(right_prefix) or right_prefix.startswith(left_prefix):
                    return True
            sample_left = left.replace("**", "sample").replace("*", "sample")
            sample_right = right.replace("**", "sample").replace("*", "sample")
            if fnmatch(sample_left, right) or fnmatch(sample_right, left):
                return True
    return False


def _glob_prefix(glob: str) -> str:
    wildcard = min([index for index in (glob.find("*"), glob.find("?")) if index != -1] or [len(glob)])
    return glob[:wildcard].rstrip("/")


def _compare_precedence(candidate: Contract, existing: Contract) -> int:
    candidate_score = _precedence_score(candidate)
    existing_score = _precedence_score(existing)
    return (candidate_score > existing_score) - (candidate_score < existing_score)


def _precedence_score(contract: Contract) -> tuple[int, int, int, int]:
    source = SOURCE_AUTHORITY[contract.source.kind]
    scope = scope_specificity(contract.scope)
    lifecycle = 1 if not contract.is_expired() else 0
    strength = {
        Strength.HARD: 3,
        Strength.SOFT: 2,
        Strength.SUGGESTIVE: 1,
    }[contract.strength]
    return source, scope, lifecycle, strength
