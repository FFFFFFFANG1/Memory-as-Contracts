from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

from benchmarks.schemas.models import CanonicalEvent, HistoryPack

HistoryShape = Literal["decomposition", "interaction_stages", "history_packs"]


@dataclass(frozen=True)
class DecompositionUnit:
    unit_id: str
    objective: str
    acceptance_tests: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class InteractionStage:
    stage_id: str
    description: str
    insertion_points: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class HistoryPackPlan:
    pack_id: str
    episodes: list[str]
    consistency_notes: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class SourceTaskValidationResult:
    success: bool
    evaluator_name: str
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ContractAuditResult:
    success: bool
    violations: list[str] = field(default_factory=list)
    checked_action_count: int = 0


@dataclass(frozen=True)
class AdapterFailure:
    message: str
    consumes_run_budget: bool
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AdapterRunResult:
    events: list[CanonicalEvent]
    validation: SourceTaskValidationResult
    contract_audit: ContractAuditResult
    run_index: int
    model_id: str
    failure: AdapterFailure | None = None

    @property
    def retained(self) -> bool:
        return self.failure is None and self.validation.success and self.contract_audit.success


class BenchmarkSourceAdapter(Protocol):
    source_id: str
    adapter_version: str
    history_shape: HistoryShape

    def fetch(self) -> None: ...

    def select(self, *, limit: int) -> list[dict[str, Any]]: ...

    def plan_history(self, selected_task: dict[str, Any]) -> (
        list[DecompositionUnit] | list[InteractionStage] | HistoryPackPlan
    ): ...

    def overlay_or_pack(
        self,
        selected_task: dict[str, Any],
        plan: list[DecompositionUnit] | list[InteractionStage] | HistoryPackPlan,
    ) -> HistoryPack: ...

    def run(self, history_pack: HistoryPack, *, model_id: str, run_index: int) -> AdapterRunResult: ...

    def normalize(self, run_result: AdapterRunResult) -> list[CanonicalEvent]: ...

    def validate(self, run_result: AdapterRunResult) -> SourceTaskValidationResult: ...
