from __future__ import annotations

from dataclasses import dataclass

from benchmarks.generation.manifest import GenerationManifest
from benchmarks.schemas.models import ContractGraph


@dataclass(frozen=True)
class GeneratedGraph:
    graph: ContractGraph
    manifest: GenerationManifest


def accept_graph_candidate(candidate: dict, manifest: GenerationManifest) -> GeneratedGraph:
    """Validate and wrap a generated hidden contract graph candidate."""
    return GeneratedGraph(graph=ContractGraph.model_validate(candidate), manifest=manifest)
