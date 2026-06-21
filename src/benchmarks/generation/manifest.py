from __future__ import annotations

import hashlib
from dataclasses import dataclass, field


def stable_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class GenerationManifest:
    artifact_id: str
    generator: str
    source: str
    source_revision: str
    model_id: str
    system_prompt_hash: str
    task_prompt_hash: str
    adapter_version: str
    metadata: dict[str, object] = field(default_factory=dict)

    @classmethod
    def from_prompts(
        cls,
        *,
        artifact_id: str,
        generator: str,
        source: str,
        source_revision: str,
        model_id: str,
        system_prompt: str,
        task_prompt: str,
        adapter_version: str,
        metadata: dict[str, object] | None = None,
    ) -> "GenerationManifest":
        return cls(
            artifact_id=artifact_id,
            generator=generator,
            source=source,
            source_revision=source_revision,
            model_id=model_id,
            system_prompt_hash=stable_hash(system_prompt),
            task_prompt_hash=stable_hash(task_prompt),
            adapter_version=adapter_version,
            metadata=metadata or {},
        )
