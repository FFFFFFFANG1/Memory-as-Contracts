from __future__ import annotations

import json

from pydantic import ValidationError

from benchmarks.generation.builder_client import JsonBuilder
from benchmarks.generation.manifest import stable_hash
from benchmarks.generation.templates import load_template
from benchmarks.sources.scbench.models import (
    GroundedRuleGraph,
    RuleBlueprintSet,
    ScbenchPreRunBuild,
    ScbenchTaskCandidate,
    TaskDecomposition,
)


def task_prompt_payload(task: ScbenchTaskCandidate) -> dict:
    return {
        "problem_id": task.problem_id,
        "description": task.description,
        "difficulty": task.difficulty,
        "category": task.category,
        "entry_file": task.entry_file,
        "tags": task.tags,
        "checkpoints": [
            {
                "checkpoint_id": checkpoint.checkpoint_id,
                "order": checkpoint.order,
                "spec_text": checkpoint.spec_text,
                "test_files": [
                    str(path.relative_to(task.root)) if path.is_relative_to(task.root) else str(path)
                    for path in checkpoint.test_files
                ],
            }
            for checkpoint in task.checkpoints
        ],
    }


def coarse_task_metadata_payload(task: ScbenchTaskCandidate) -> dict:
    return {
        "problem_id": task.problem_id,
        "description": task.description,
        "difficulty": task.difficulty,
        "category": task.category,
        "entry_file": task.entry_file,
        "tags": task.tags,
        "checkpoint_ids": [checkpoint.checkpoint_id for checkpoint in task.checkpoints],
        "available_scope_vocabulary": sorted(
            {
                "global",
                "project",
                "component",
                "path",
                "phase",
                "tool",
                *(task.tags or []),
                *(task.category.split("-") if task.category else []),
            }
        ),
    }


def _split_template(name: str, version: str) -> tuple[str, str]:
    template = load_template(name, version=version)
    system_prompt, user_template = template.split("\n\nUSER\n", 1)
    return system_prompt.removeprefix("SYSTEM\n").strip(), user_template


def _generate_model(
    *,
    builder: JsonBuilder,
    system_prompt: str,
    user_prompt: str,
    response_name: str,
    model_cls,
    max_attempts: int,
):
    last_error: ValidationError | None = None
    current_user_prompt = user_prompt
    for attempt in range(1, max_attempts + 1):
        payload = builder.generate_json(
            system_prompt=system_prompt,
            user_prompt=current_user_prompt,
            response_name=f"{response_name}:attempt{attempt}",
        )
        try:
            return model_cls.model_validate(payload)
        except ValidationError as exc:
            last_error = exc
            current_user_prompt = (
                f"{user_prompt}\n\n"
                "Your previous JSON did not match the required schema. Fix only the schema "
                "and return the full corrected JSON object.\n"
                f"Validation errors:\n{exc}\n"
            )
    assert last_error is not None
    raise last_error


def build_task_decomposition(
    *,
    task: ScbenchTaskCandidate,
    builder: JsonBuilder,
    template_version: str = "v1",
    max_attempts: int = 2,
    validation_feedback: str | None = None,
) -> tuple[TaskDecomposition, dict[str, str]]:
    system_prompt, user_template = _split_template("scbench_task_decomposition", template_version)
    user_prompt = user_template.replace(
        "{{task_json}}",
        json.dumps(task_prompt_payload(task), ensure_ascii=False, indent=2),
    )
    if validation_feedback:
        user_prompt = (
            f"{user_prompt}\n\n"
            "A previous candidate passed JSON schema but failed benchmark validation. "
            "Return a fully corrected JSON object that fixes these validation errors:\n"
            f"{validation_feedback}\n"
        )
    decomposition = _generate_model(
        builder=builder,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        response_name=f"scbench_decomposition:{task.problem_id}",
        model_cls=TaskDecomposition,
        max_attempts=max_attempts,
    )
    return decomposition, {
        "system_prompt_hash": stable_hash(system_prompt),
        "task_prompt_hash": stable_hash(user_prompt),
    }


def build_rule_blueprint(
    *,
    task: ScbenchTaskCandidate,
    builder: JsonBuilder,
    template_version: str = "v1",
    max_attempts: int = 2,
    validation_feedback: str | None = None,
) -> tuple[RuleBlueprintSet, dict[str, str]]:
    system_prompt, user_template = _split_template("scbench_rule_blueprint", template_version)
    user_prompt = user_template.replace(
        "{{task_metadata_json}}",
        json.dumps(coarse_task_metadata_payload(task), ensure_ascii=False, indent=2),
    )
    if validation_feedback:
        user_prompt = (
            f"{user_prompt}\n\n"
            "A previous candidate failed blueprint validation. Return a fully corrected "
            "blueprint set that fixes these errors:\n"
            f"{validation_feedback}\n"
        )
    blueprint = _generate_model(
        builder=builder,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        response_name=f"scbench_blueprint:{task.problem_id}",
        model_cls=RuleBlueprintSet,
        max_attempts=max_attempts,
    )
    return blueprint, {
        "system_prompt_hash": stable_hash(system_prompt),
        "task_prompt_hash": stable_hash(user_prompt),
    }


def instantiate_rule_graph(
    *,
    task: ScbenchTaskCandidate,
    decomposition: TaskDecomposition,
    blueprint: RuleBlueprintSet,
    builder: JsonBuilder,
    template_version: str = "v1",
    max_attempts: int = 2,
    validation_feedback: str | None = None,
) -> tuple[GroundedRuleGraph, dict[str, str]]:
    system_prompt, user_template = _split_template("scbench_rule_instantiation", template_version)
    user_prompt = (
        user_template.replace(
            "{{task_metadata_json}}",
            json.dumps(task_prompt_payload(task), ensure_ascii=False, indent=2),
        )
        .replace(
            "{{decomposition_json}}",
            decomposition.model_dump_json(indent=2),
        )
        .replace(
            "{{blueprint_json}}",
            blueprint.model_dump_json(indent=2),
        )
    )
    if validation_feedback:
        user_prompt = (
            f"{user_prompt}\n\n"
            "A previous candidate failed grounding validation. Return a fully corrected "
            "grounded graph that fixes these errors while preserving blueprint intent:\n"
            f"{validation_feedback}\n"
        )
    grounded = _generate_model(
        builder=builder,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        response_name=f"scbench_grounded_graph:{task.problem_id}",
        model_cls=GroundedRuleGraph,
        max_attempts=max_attempts,
    )
    return grounded, {
        "system_prompt_hash": stable_hash(system_prompt),
        "task_prompt_hash": stable_hash(user_prompt),
    }


def build_scbench_prerun(
    *,
    task: ScbenchTaskCandidate,
    builder: JsonBuilder,
    template_version: str = "v1",
    max_attempts: int = 2,
    validation_feedback: dict[str, str] | None = None,
) -> tuple[ScbenchPreRunBuild, dict[str, str]]:
    decomposition, decomp_hashes = build_task_decomposition(
        task=task,
        builder=builder,
        template_version=template_version,
        max_attempts=max_attempts,
        validation_feedback=(validation_feedback or {}).get("decomposition"),
    )
    blueprint, blueprint_hashes = build_rule_blueprint(
        task=task,
        builder=builder,
        template_version=template_version,
        max_attempts=max_attempts,
        validation_feedback=(validation_feedback or {}).get("blueprint"),
    )
    grounded, grounded_hashes = instantiate_rule_graph(
        task=task,
        decomposition=decomposition,
        blueprint=blueprint,
        builder=builder,
        template_version=template_version,
        max_attempts=max_attempts,
        validation_feedback=(validation_feedback or {}).get("grounding"),
    )
    return (
        ScbenchPreRunBuild(
            task_id=task.problem_id,
            decomposition=decomposition,
            rule_blueprint=blueprint,
            contract_graph=grounded.contract_graph,
            rule_task_links=grounded.rule_task_links,
        ),
        {
            "task_decomposition_system_prompt_hash": decomp_hashes["system_prompt_hash"],
            "task_decomposition_prompt_hash": decomp_hashes["task_prompt_hash"],
            "rule_blueprint_system_prompt_hash": blueprint_hashes["system_prompt_hash"],
            "rule_blueprint_prompt_hash": blueprint_hashes["task_prompt_hash"],
            "rule_instantiation_system_prompt_hash": grounded_hashes["system_prompt_hash"],
            "rule_instantiation_prompt_hash": grounded_hashes["task_prompt_hash"],
        },
    )
