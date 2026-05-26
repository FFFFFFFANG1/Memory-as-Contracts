from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from memory_as_contracts.models import (
    CompiledPredicateVersion,
    HostActionPattern,
    JobStatus,
    MatchOutcome,
    PredicateStatus,
    Receipt,
    RefinementJob,
    TargetPattern,
    prefixed_id,
    utc_now,
)
from memory_as_contracts.store import ContractStore


PREDICATE_REFINEMENT_SYSTEM_PROMPT = """
You refine Memory-as-Contracts action-signature predicates. Return only valid JSON.

The rule text is authoritative and must not be changed. Treat ambiguity as a
predicate matching problem, not as a rule problem. You may only revise action
signature patterns: host_action_patterns, target_patterns, and canonical_tags.
Do not change rule text, source, scope, lifecycle, modality, or strength.
""".strip()


@dataclass(frozen=True)
class PredicateInvocationResult:
    signature_id: str
    match_outcome: MatchOutcome
    evaluated_at: str
    receipt: Receipt | None = None


class PredicateRefiner(Protocol):
    def refine(
        self,
        *,
        contract_text: str,
        current: CompiledPredicateVersion,
        invocation_results: list[PredicateInvocationResult],
    ) -> CompiledPredicateVersion:
        ...


class CopyingPredicateRefiner:
    """Default local refiner used when no LLM-backed refiner is configured."""

    def refine(
        self,
        *,
        contract_text: str,
        current: CompiledPredicateVersion,
        invocation_results: list[PredicateInvocationResult],
    ) -> CompiledPredicateVersion:
        next_number = _next_version_number(current.version)
        return current.model_copy(
            update={
                "id": prefixed_id("PV"),
                "version": f"PV-{next_number:03d}",
                "refines": current.id,
                "status": PredicateStatus.ACTIVE,
                "created_at": utc_now(),
            }
        )


class LLMPredicateRefiner:
    """LLM-backed refiner that only changes action-signature predicates."""

    def __init__(self, response_provider: Callable[[str], str]) -> None:
        self.response_provider = response_provider

    def refine(
        self,
        *,
        contract_text: str,
        current: CompiledPredicateVersion,
        invocation_results: list[PredicateInvocationResult],
    ) -> CompiledPredicateVersion:
        prompt = _predicate_refinement_prompt(
            contract_text=contract_text,
            current=current,
            invocation_results=invocation_results,
        )
        payload = _load_refinement_payload(self.response_provider(prompt))
        next_number = _next_version_number(current.version)
        return current.model_copy(
            update={
                "id": prefixed_id("PV"),
                "version": f"PV-{next_number:03d}",
                "refines": current.id,
                "status": PredicateStatus.ACTIVE,
                "host_action_patterns": [
                    HostActionPattern.model_validate(item)
                    for item in payload.get("host_action_patterns", [])
                ],
                "target_patterns": [
                    TargetPattern.model_validate(item)
                    for item in payload.get("target_patterns", [])
                ],
                "canonical_tags": sorted(
                    {str(item) for item in payload.get("canonical_tags", [])}
                ),
                "created_at": utc_now(),
            }
        )


class AmbiguityMonitor:
    def __init__(
        self,
        store: ContractStore,
        *,
        window: int = 10,
        threshold: float = 0.60,
    ) -> None:
        self.store = store
        self.window = window
        self.threshold = threshold

    def should_enqueue(self, contract_id: str, predicate_version_id: str) -> bool:
        evaluations = self.store.recent_predicate_evaluations(
            contract_id, predicate_version_id, limit=self.window
        )
        if len(evaluations) < self.window:
            return False
        ambiguous = sum(1 for item in evaluations if item.match_outcome == MatchOutcome.AMBIGUOUS)
        return ambiguous / len(evaluations) >= self.threshold

    def enqueue_if_needed(
        self, contract_id: str, predicate_version_id: str
    ) -> RefinementJob | None:
        if not self.should_enqueue(contract_id, predicate_version_id):
            return None
        for status in (JobStatus.PENDING, JobStatus.RUNNING):
            for job in self.store.list_refinement_jobs(status.value):
                if job.contract_id == contract_id and job.predicate_version_id == predicate_version_id:
                    return job
        evaluations = self.store.recent_predicate_evaluations(
            contract_id, predicate_version_id, limit=self.window
        )
        job = RefinementJob(
            contract_id=contract_id,
            predicate_version_id=predicate_version_id,
            recent_signature_ids=[item.signature_id for item in evaluations],
        )
        return self.store.add_refinement_job(job)

    def run_next_pending(self, refiner: PredicateRefiner | None = None) -> RefinementJob | None:
        jobs = self.store.list_refinement_jobs(JobStatus.PENDING.value)
        if not jobs:
            return None
        job = jobs[0].model_copy(update={"status": JobStatus.RUNNING, "updated_at": utc_now()})
        self.store.add_refinement_job(job)
        refiner = refiner or CopyingPredicateRefiner()
        contract = self.store.get_contract(job.contract_id)
        predicates = self.store.list_predicate_versions(job.contract_id)
        current = next((item for item in predicates if item.id == job.predicate_version_id), None)
        if contract is None or current is None:
            failed = job.model_copy(
                update={
                    "status": JobStatus.FAILED,
                    "error": "missing contract or predicate version",
                    "updated_at": utc_now(),
                }
            )
            return self.store.add_refinement_job(failed)
        try:
            invocation_results = self._invocation_results(job)
            refined = refiner.refine(
                contract_text=contract.text,
                current=current,
                invocation_results=invocation_results,
            )
            refined = refined.model_copy(update={"contract_id": contract.id})
            self.store.add_predicate_version(
                current.model_copy(update={"status": PredicateStatus.SUPERSEDED})
            )
            self.store.add_predicate_version(refined)
            self.store.add_contract(contract.model_copy(update={"compiled_predicates": refined}))
            completed = job.model_copy(
                update={
                    "status": JobStatus.COMPLETED,
                    "result_predicate_version_id": refined.id,
                    "updated_at": utc_now(),
                }
            )
            return self.store.add_refinement_job(completed)
        except Exception as exc:  # pragma: no cover - defensive job boundary
            failed = job.model_copy(
                update={"status": JobStatus.FAILED, "error": str(exc), "updated_at": utc_now()}
            )
            return self.store.add_refinement_job(failed)

    def _invocation_results(self, job: RefinementJob) -> list[PredicateInvocationResult]:
        evaluations = self.store.predicate_evaluations_by_signature_ids(
            job.contract_id,
            job.predicate_version_id,
            job.recent_signature_ids,
        )
        receipts = self.store.receipts_by_signature_ids(job.recent_signature_ids)
        return [
            PredicateInvocationResult(
                signature_id=evaluation.signature_id,
                match_outcome=evaluation.match_outcome,
                evaluated_at=evaluation.evaluated_at.isoformat(),
                receipt=receipts.get(evaluation.signature_id),
            )
            for evaluation in evaluations
        ]


def _next_version_number(version: str) -> int:
    try:
        return int(version.split("-", 1)[1]) + 1
    except (IndexError, ValueError):
        return 2


def _predicate_refinement_prompt(
    *,
    contract_text: str,
    current: CompiledPredicateVersion,
    invocation_results: list[PredicateInvocationResult],
) -> str:
    payload = {
        "rule_text": contract_text,
        "current_predicate": current.model_dump(mode="json"),
        "ambiguous_invocation_results": [
            _invocation_payload(item) for item in invocation_results
        ],
        "output_contract": {
            "host_action_patterns": [
                {
                    "action": "git.push",
                    "tool_name": "exec",
                    "parameter_regex": {"cmd": r"^git\s+push(\s|$)"},
                }
            ],
            "target_patterns": [{"kind": "path_glob", "value": "generated/**"}],
            "canonical_tags": ["external_write"],
        },
    }
    return (
        f"{PREDICATE_REFINEMENT_SYSTEM_PROMPT}\n\n"
        "Use all ambiguous invocation results below. Produce a stricter or more "
        "complete predicate that would make future matching deterministic. "
        "Return exactly this JSON shape, with no extra text:\n"
        '{"host_action_patterns":[],"target_patterns":[],"canonical_tags":[]}\n\n'
        f"Input:\n{json.dumps(payload, sort_keys=True)}"
    )


def _invocation_payload(item: PredicateInvocationResult) -> dict:
    receipt = item.receipt
    return {
        "signature_id": item.signature_id,
        "match_outcome": item.match_outcome.value,
        "evaluated_at": item.evaluated_at,
        "receipt": None
        if receipt is None
        else {
            "decision": receipt.decision.value,
            "host_action": receipt.host_action,
            "tool_name": receipt.tool_name,
            "raw_arguments": receipt.raw_arguments,
            "canonical_tags": receipt.canonical_tags,
            "targets": receipt.targets,
            "intent": receipt.intent,
            "result": receipt.result,
            "contracts_used": receipt.contracts_used,
            "contracts_ignored": [
                item.model_dump(mode="json") for item in receipt.contracts_ignored
            ],
        },
    }


def _load_refinement_payload(raw: str) -> dict:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        start = raw.find("{")
        end = raw.rfind("}")
        if start == -1 or end <= start:
            raise
        payload = json.loads(raw[start : end + 1])
    if "compiled_predicate" in payload and isinstance(payload["compiled_predicate"], dict):
        payload = payload["compiled_predicate"]
    for key in ("host_action_patterns", "target_patterns", "canonical_tags"):
        if key not in payload:
            payload[key] = []
        if not isinstance(payload[key], list):
            raise ValueError(f"{key} must be a list")
    return payload
