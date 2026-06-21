from __future__ import annotations

from dataclasses import dataclass

from benchmarks.schemas.models import CanonicalEvent, HistoryPack
from benchmarks.sources.base import AdapterRunResult, BenchmarkSourceAdapter, SourceTaskValidationResult


@dataclass(frozen=True)
class AdapterE2EResult:
    selected_task: dict[str, object]
    history_pack: HistoryPack
    run_result: AdapterRunResult
    normalized_events: list[CanonicalEvent]
    validation: SourceTaskValidationResult


def run_adapter_e2e(
    adapter: BenchmarkSourceAdapter,
    *,
    model_id: str,
    limit: int = 1,
    run_index: int = 1,
) -> list[AdapterE2EResult]:
    adapter.fetch()
    selected = adapter.select(limit=limit)
    results: list[AdapterE2EResult] = []
    for task in selected:
        plan = adapter.plan_history(task)
        history_pack = adapter.overlay_or_pack(task, plan)
        run_result = adapter.run(history_pack, model_id=model_id, run_index=run_index)
        normalized = adapter.normalize(run_result)
        validation = adapter.validate(run_result)
        results.append(
            AdapterE2EResult(
                selected_task=task,
                history_pack=history_pack,
                run_result=run_result,
                normalized_events=normalized,
                validation=validation,
            )
        )
    return results
