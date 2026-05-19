from __future__ import annotations

from dataclasses import dataclass, field

from memory_use_contracts.models import Contract, ContractStatus, ContractType, Modality, SourceKind


SOURCE_AUTHORITY = {
    SourceKind.USER_EXPLICIT: 4,
    SourceKind.PROJECT_DOC: 3,
    SourceKind.TOOL_OBSERVATION: 2,
    SourceKind.AGENT_INFERRED: 1,
}


def scope_specificity(contract: Contract) -> int:
    score = 0
    if contract.scope.workspace and contract.scope.workspace != "default":
        score += 1
    if contract.scope.task:
        score += 2
    score += min(len(contract.scope.path_globs), 3) * 3
    return score


def authority_score(contract: Contract) -> int:
    return SOURCE_AUTHORITY.get(contract.source.kind, 0)


class ConflictResolver:
    def resolve(self, candidate: Contract, existing: list[Contract]) -> "Resolution":
        if candidate.is_expired():
            candidate.status = ContractStatus.EXPIRED
            return Resolution(contract=candidate)

        conflicts = [contract for contract in existing if self._conflicts(candidate, contract)]
        if not conflicts:
            candidate.status = ContractStatus.ACTIVE
            return Resolution(contract=candidate)

        candidate_score = self._precedence(candidate)
        strongest_existing = max(conflicts, key=self._precedence)
        strongest_score = self._precedence(strongest_existing)
        if candidate_score > strongest_score:
            candidate.status = ContractStatus.ACTIVE
            candidate.supersedes = [contract.id for contract in conflicts]
            return Resolution(
                contract=candidate,
                superseded_ids=[contract.id for contract in conflicts],
            )
        if candidate_score == strongest_score:
            candidate.status = ContractStatus.PENDING_CONFLICT
            return Resolution(
                contract=candidate,
                conflict_ids=[contract.id for contract in conflicts],
            )
        candidate.status = ContractStatus.REJECTED
        return Resolution(contract=candidate, rejected_by_id=strongest_existing.id)

    def activate(self, candidate: Contract, existing: list[Contract]) -> Contract:
        return self.resolve(candidate, existing).contract

    def _precedence(self, contract: Contract) -> tuple[int, int, int]:
        hard = 1 if contract.strength.value == "hard" else 0
        return (authority_score(contract), scope_specificity(contract), hard)

    def _conflicts(self, left: Contract, right: Contract) -> bool:
        if right.status != ContractStatus.ACTIVE:
            return False
        if left.scope.workspace != right.scope.workspace:
            return False
        if not set(left.action_classes).intersection(right.action_classes):
            return False
        if not _path_scopes_can_overlap(left, right):
            return False
        if left.type == ContractType.EXCEPTION or right.type == ContractType.EXCEPTION:
            return _is_exception_override(left, right) or _is_exception_override(right, left)
        if _has_opposing_force(left, right):
            return _same_policy_target(left, right)
        if _known_choice_conflict(left, right):
            return True
        return False


@dataclass
class Resolution:
    contract: Contract
    superseded_ids: list[str] = field(default_factory=list)
    conflict_ids: list[str] = field(default_factory=list)
    rejected_by_id: str | None = None


COMMAND_MARKERS = ("uv", "pip", "npm", "pnpm", "yarn", "pytest", "git")
PACKAGE_MANAGER_MARKERS = ("uv", "pip", "npm", "pnpm", "yarn")


def _path_scopes_can_overlap(left: Contract, right: Contract) -> bool:
    if left.scope.path_globs and right.scope.path_globs:
        return bool(set(left.scope.path_globs).intersection(right.scope.path_globs))
    return True


def _is_exception_override(exception: Contract, other: Contract) -> bool:
    if exception.type != ContractType.EXCEPTION:
        return False
    has_boundary = bool(exception.scope.path_globs or exception.validity.expires_at)
    return has_boundary and _same_policy_target(exception, other)


def _has_opposing_force(left: Contract, right: Contract) -> bool:
    return (left.modality == Modality.MUST_NOT) != (right.modality == Modality.MUST_NOT)


def _same_policy_target(left: Contract, right: Contract) -> bool:
    if left.scope.path_globs and right.scope.path_globs:
        return bool(set(left.scope.path_globs).intersection(right.scope.path_globs))

    left_mentions = _marker_mentions(left.text)
    right_mentions = _marker_mentions(right.text)
    if left_mentions["all"] and right_mentions["all"]:
        return bool(left_mentions["all"].intersection(right_mentions["all"]))

    return False


def _known_choice_conflict(left: Contract, right: Contract) -> bool:
    left_mentions = _marker_mentions(left.text)
    right_mentions = _marker_mentions(right.text)
    if left_mentions["negative"].intersection(right_mentions["positive"]):
        return True
    if right_mentions["negative"].intersection(left_mentions["positive"]):
        return True

    left_choices = left_mentions["positive"].intersection(PACKAGE_MANAGER_MARKERS)
    right_choices = right_mentions["positive"].intersection(PACKAGE_MANAGER_MARKERS)
    if not left_choices or not right_choices:
        return False
    return left_choices.isdisjoint(right_choices)


def _marker_mentions(text: str) -> dict[str, set[str]]:
    lowered = text.lower()
    positive: set[str] = set()
    negative: set[str] = set()
    for marker in COMMAND_MARKERS:
        if marker not in lowered:
            continue
        if f"not {marker}" in lowered or f"no {marker}" in lowered:
            negative.add(marker)
        else:
            positive.add(marker)
    return {
        "positive": positive,
        "negative": negative,
        "all": positive | negative,
    }
