from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from benchmarks.generation.manifest import GenerationManifest
from benchmarks.schemas.models import CanonicalAction

VariantType = Literal[
    "original_reference",
    "minimal_violation",
    "legal_near_miss",
    "scope_counterfactual",
    "temporal_counterfactual",
    "ask_case",
]


@dataclass(frozen=True)
class ActionVariant:
    action: CanonicalAction
    changed_fields: list[str]
    variant_type: VariantType
    manifest: GenerationManifest


def accept_action_variant(
    *,
    candidate: dict,
    changed_fields: list[str],
    variant_type: VariantType,
    manifest: GenerationManifest,
) -> ActionVariant:
    if variant_type != "original_reference" and not changed_fields:
        raise ValueError("counterfactual variants must record changed fields")
    return ActionVariant(
        action=CanonicalAction.model_validate(candidate),
        changed_fields=changed_fields,
        variant_type=variant_type,
        manifest=manifest,
    )
