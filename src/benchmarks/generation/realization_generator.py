from __future__ import annotations

from dataclasses import dataclass

from benchmarks.generation.manifest import GenerationManifest


@dataclass(frozen=True)
class ContractRealization:
    contract_id: str
    inserted_text: str
    insertion_point: str
    source_form: str
    manifest: GenerationManifest


def accept_realization_candidate(
    *,
    contract_id: str,
    inserted_text: str,
    insertion_point: str,
    source_form: str,
    manifest: GenerationManifest,
) -> ContractRealization:
    if not inserted_text.strip():
        raise ValueError("inserted_text must not be empty")
    if "contract id" in inserted_text.lower():
        raise ValueError("realized text must not mention contract ids")
    return ContractRealization(
        contract_id=contract_id,
        inserted_text=inserted_text,
        insertion_point=insertion_point,
        source_form=source_form,
        manifest=manifest,
    )
