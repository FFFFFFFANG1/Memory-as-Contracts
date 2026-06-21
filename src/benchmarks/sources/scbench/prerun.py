from __future__ import annotations

import argparse
import json
from pathlib import Path

from benchmarks.generation.builder_client import JsonBuilder, OpenAIJsonBuilder, load_builder_config
from benchmarks.sources.scbench.builder import (
    build_rule_blueprint,
    build_task_decomposition,
    instantiate_rule_graph,
)
from benchmarks.sources.scbench.models import ScbenchBuildArtifact, ScbenchPreRunBuild
from benchmarks.sources.scbench.select import discover_scbench_tasks, select_scbench_tasks
from benchmarks.sources.scbench.validate import validate_scbench_build


DEFAULT_PROBLEMS_ROOT = Path("bench/sources/scbench-problems")


def build_scbench_prerun_artifacts(
    *,
    problems_root: Path = DEFAULT_PROBLEMS_ROOT,
    limit: int = 2,
    difficulties: set[str] | None = frozenset({"Easy", "Medium"}),
    task_ids: set[str] | None = None,
    output_dir: Path | None = None,
    builder: JsonBuilder | None = None,
    builder_model: str | None = None,
    validation_attempts: int = 2,
) -> list[ScbenchBuildArtifact]:
    config = None
    if builder is None:
        config = load_builder_config()
        builder = OpenAIJsonBuilder(config)
        builder_model = config.model
    if builder_model is None:
        builder_model = config.model if config else "fake-builder"

    if task_ids:
        discovered = discover_scbench_tasks(problems_root)
        tasks = [task for task in discovered if task.problem_id in task_ids]
        tasks.sort(key=lambda task: task.problem_id)
    else:
        tasks = select_scbench_tasks(
            problems_root,
            limit=limit,
            difficulties=set(difficulties) if difficulties else None,
        )
    artifacts: list[ScbenchBuildArtifact] = []
    for task in tasks:
        print(f"building {task.problem_id} with {builder_model}", flush=True)
        feedback: dict[str, str] = {}
        validation = None
        build = None
        prompt_hashes = None
        for attempt in range(1, validation_attempts + 1):
            if attempt > 1:
                print(f"retrying {task.problem_id} after validator feedback", flush=True)
            print(f"Call A decomposition: {task.problem_id}", flush=True)
            decomposition, decomp_hashes = build_task_decomposition(
                task=task,
                builder=builder,
                validation_feedback=feedback.get("decomposition"),
            )
            print(f"Call B blueprint: {task.problem_id}", flush=True)
            blueprint, blueprint_hashes = build_rule_blueprint(
                task=task,
                builder=builder,
                validation_feedback=feedback.get("blueprint"),
            )
            print(f"Call C instantiation: {task.problem_id}", flush=True)
            grounded, grounded_hashes = instantiate_rule_graph(
                task=task,
                decomposition=decomposition,
                blueprint=blueprint,
                builder=builder,
                validation_feedback=feedback.get("grounding"),
            )
            build = ScbenchPreRunBuild(
                task_id=task.problem_id,
                decomposition=decomposition,
                rule_blueprint=blueprint,
                contract_graph=grounded.contract_graph,
                rule_task_links=grounded.rule_task_links,
            )
            prompt_hashes = {
                "task_decomposition_system_prompt_hash": decomp_hashes["system_prompt_hash"],
                "task_decomposition_prompt_hash": decomp_hashes["task_prompt_hash"],
                "rule_blueprint_system_prompt_hash": blueprint_hashes["system_prompt_hash"],
                "rule_blueprint_prompt_hash": blueprint_hashes["task_prompt_hash"],
                "rule_instantiation_system_prompt_hash": grounded_hashes["system_prompt_hash"],
                "rule_instantiation_prompt_hash": grounded_hashes["task_prompt_hash"],
            }
            print(f"validator result: {task.problem_id}", flush=True)
            validation = validate_scbench_build(task=task, build=build)
            if validation.accepted:
                break
            feedback = route_validation_feedback(validation.errors)
        assert build is not None and prompt_hashes is not None and validation is not None
        artifact = ScbenchBuildArtifact(
            task=task,
            build=build,
            validation=validation,
            builder_model=builder_model,
            prompt_hashes=prompt_hashes,
        )
        artifacts.append(artifact)
        if output_dir is not None:
            output_dir.mkdir(parents=True, exist_ok=True)
            out_path = output_dir / f"{task.problem_id}.prerun.json"
            out_path.write_text(
                json.dumps(artifact.model_dump(mode="json"), indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            print(
                f"wrote {out_path} accepted={validation.accepted} errors={len(validation.errors)}",
                flush=True,
            )
    return artifacts


def route_validation_feedback(errors: list[str]) -> dict[str, str]:
    routed: dict[str, list[str]] = {"decomposition": [], "blueprint": [], "grounding": []}
    for error in errors:
        lowered = error.lower()
        if "rule_task_link" in lowered or "contract " in lowered:
            routed["grounding"].append(error)
        elif any(token in lowered for token in ("checkpoint", "coverage", "subtask", "boundary")):
            routed["decomposition"].append(error)
        elif any(token in lowered for token in ("blueprint", "scope level", "style rule")):
            routed["blueprint"].append(error)
        else:
            routed["grounding"].append(error)
    return {key: "\n".join(f"- {item}" for item in values) for key, values in routed.items() if values}


def main() -> None:
    parser = argparse.ArgumentParser(description="Build SCBench pre-OpenCode artifacts.")
    parser.add_argument("--problems-root", type=Path, default=DEFAULT_PROBLEMS_ROOT)
    parser.add_argument("--limit", type=int, default=2)
    parser.add_argument("--task-id", action="append", default=None)
    parser.add_argument("--validation-attempts", type=int, default=2)
    parser.add_argument("--output-dir", type=Path, default=Path("benchmarks/work/scbench_prerun"))
    args = parser.parse_args()

    artifacts = build_scbench_prerun_artifacts(
        problems_root=args.problems_root,
        limit=args.limit,
        task_ids=set(args.task_id) if args.task_id else None,
        output_dir=args.output_dir,
        validation_attempts=args.validation_attempts,
    )
    accepted = sum(artifact.validation.accepted for artifact in artifacts)
    print(f"built {len(artifacts)} SCBench pre-run artifacts; accepted={accepted}")
    for artifact in artifacts:
        status = "accepted" if artifact.validation.accepted else "rejected"
        print(f"- {artifact.task.problem_id}: {status}")
        for error in artifact.validation.errors:
            print(f"  error: {error}")


if __name__ == "__main__":
    main()
