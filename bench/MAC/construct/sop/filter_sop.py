#!/usr/bin/env python3
"""Extract SOPBench SOP blocks and emit MAC construct step-1 artifacts.

Reads ``bench/MAC/sopbench/mid_data/sampled_tasks_200.json`` (or any compatible
sample manifest), builds domain-level constraint-free system prompts, and writes:

- ``bench/MAC/sopbench/data/mac-sop_system_prompt.json``
- ``bench/MAC/sopbench/mid_data/eval_step1_sop.json``

Each task's ``constraints`` array expands every SOP ``•`` (single dependency node)
across all actions, with ``text``, ``action``, and SOPBench rule ``metadata``.
"""

from __future__ import annotations

import argparse
import copy
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_INPUT = Path("bench/MAC/sopbench/mid_data/sampled_tasks_200.json")
DEFAULT_SYSTEM_PROMPTS = Path("bench/MAC/sopbench/data/mac-sop_system_prompt.json")
DEFAULT_STEP1 = Path("bench/MAC/sopbench/mid_data/eval_step1_sop.json")

SOPBENCH_ROOT = REPO_ROOT / "bench" / "SOPBench"
DOMAINS = (
    "bank",
    "dmv",
    "healthcare",
    "hotel",
    "library",
    "online_market",
    "university",
)


def resolve_path(path: Path) -> Path:
    return path if path.is_absolute() else REPO_ROOT / path


def load_json(path: Path) -> Any:
    return json.loads(resolve_path(path).read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    target = resolve_path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, indent=4, ensure_ascii=False) + "\n", encoding="utf-8")


def ensure_sopbench_imports() -> None:
    root = str(SOPBENCH_ROOT)
    if root not in sys.path:
        sys.path.insert(0, root)


def list_to_tuple(value: Any) -> Any:
    if isinstance(value, list):
        return tuple(list_to_tuple(item) for item in value)
    if isinstance(value, dict):
        return {key: list_to_tuple(item) for key, item in value.items()}
    return value


def to_json_safe(value: Any) -> Any:
    if isinstance(value, tuple):
        return [to_json_safe(item) for item in value]
    if isinstance(value, list):
        return [to_json_safe(item) for item in value]
    if isinstance(value, dict):
        return {str(key): to_json_safe(item) for key, item in value.items()}
    return value


def walk_single_constraints(
    dep: Any,
    composition_path: list[dict[str, Any]] | None = None,
) -> list[tuple[tuple, list[dict[str, Any]]]]:
    if not dep:
        return []
    composition_path = composition_path or []
    if dep[0] == "single":
        return [(tuple(dep), composition_path)]
    if dep[0] in ("and", "or", "chain", "gate"):
        found: list[tuple[tuple, list[dict[str, Any]]]] = []
        for index, child in enumerate(dep[1]):
            child_path = composition_path + [{"logic": dep[0], "child_index": index}]
            found.extend(walk_single_constraints(child, child_path))
        return found
    return []


def parse_single_metadata(single: tuple) -> tuple[str, bool, dict[str, Any]]:
    raw_id = str(single[1])
    negated = raw_id.startswith("not ")
    constraint_id = raw_id[4:] if negated else raw_id
    param_mapping = dict(single[2]) if len(single) > 2 and isinstance(single[2], dict) else {}
    return constraint_id, negated, param_mapping


def agent_name(domain: str, user_goal: str, task_index: int) -> str:
    return f"sopbench_{domain}_{user_goal}_{task_index}"


class DomainRuntime:
    def __init__(self, domain: str) -> None:
        ensure_sopbench_imports()
        from env.task import (  # noqa: WPS433
            create_assistant,
            get_single_dep_verb,
            gather_dependency_instructions,
            task_default_dep_full,
        )

        self.domain = domain
        self._create_assistant = create_assistant
        self._get_single_dep_verb = get_single_dep_verb
        self._gather_dependency_instructions = gather_dependency_instructions
        from env.variables import domain_assistant_keys  # noqa: WPS433

        self._domain_assistant = domain_assistant_keys[domain]
        self._dep_innate_full, self.default_dep_full, self.default_dep_full_descr = task_default_dep_full(
            domain,
            "full",
            "structured",
            dependency_verb_dep_orig=True,
        )
        assistant = self._create_assistant(
            domain,
            shuffle_func=False,
            mode="prompt",
            included_functions=None,
            assistant_dependency_instructions=None,
        )
        self.neat_system_prompt = assistant["instructions"].rstrip()
        self.neat_tools = copy.deepcopy(assistant["tools"])

    def build_task_dep_full(self, task: dict[str, Any]) -> dict[str, Any]:
        dep_full = copy.deepcopy(self.default_dep_full)
        dep_full[task["user_goal"]] = list_to_tuple(task.get("constraints_original") or ())
        return dep_full

    def build_sop_text(self, task: dict[str, Any]) -> str:
        dep_full_descr = copy.deepcopy(self.default_dep_full_descr)
        dep_orig = list_to_tuple(task.get("constraints_original") or ())
        dep_params = copy.deepcopy(task.get("constraint_parameters") or {})
        user_goal = task["user_goal"]
        return self._gather_dependency_instructions(
            self.domain,
            dep_full_descr,
            user_goal,
            dep_orig,
            dep_params,
            included_functions=None,
            shuffle_func=False,
            constraint_descr_format="structured",
        )

    def _domain_rule_metadata(self, constraint_id: str) -> dict[str, Any]:
        da = self._domain_assistant
        metadata: dict[str, Any] = {}
        if hasattr(da, "constraint_processes") and constraint_id in da.constraint_processes:
            metadata["constraint_process"] = to_json_safe(da.constraint_processes[constraint_id])
        if hasattr(da, "constraint_links") and constraint_id in da.constraint_links:
            metadata["constraint_link"] = to_json_safe(da.constraint_links[constraint_id])
        if hasattr(da, "constraint_dependencies") and constraint_id in da.constraint_dependencies:
            metadata["constraint_dependency"] = to_json_safe(da.constraint_dependencies[constraint_id])
        if hasattr(da, "positive_constraint_descriptions") and constraint_id in da.positive_constraint_descriptions:
            metadata["positive_template"] = da.positive_constraint_descriptions[constraint_id]
        if hasattr(da, "negative_constraint_descriptions") and constraint_id in da.negative_constraint_descriptions:
            metadata["negative_template"] = da.negative_constraint_descriptions[constraint_id]
        return metadata

    def expand_sop_constraints(self, task: dict[str, Any], task_uid: str) -> list[dict[str, Any]]:
        dep_full = self.build_task_dep_full(task)
        dep_params = copy.deepcopy(task.get("constraint_parameters") or {})
        user_goal = task["user_goal"]
        task_constraints_expanded = list_to_tuple(task.get("constraints") or ())
        task_constraints_original = list_to_tuple(task.get("constraints_original") or ())

        records: list[dict[str, Any]] = []
        constraint_index = 0
        for action in sorted(dep_full.keys()):
            dep = dep_full[action]
            if not dep:
                continue
            is_user_goal_action = action == user_goal
            for single, composition_path in walk_single_constraints(dep):
                constraint_id, negated, param_mapping = parse_single_metadata(single)
                text = self._get_single_dep_verb(self.domain, single, dep_params)
                rule_metadata = self._domain_rule_metadata(constraint_id)
                metadata: dict[str, Any] = {
                    "constraint_id": constraint_id,
                    "negated": negated,
                    "dependency": to_json_safe(single),
                    "param_mapping": param_mapping,
                    "composition_path": composition_path,
                    "constraint_parameters": dep_params,
                    "eval_scope": "user_goal" if is_user_goal_action else "domain_default",
                    **rule_metadata,
                }
                if is_user_goal_action:
                    metadata["task_constraints_original"] = to_json_safe(task_constraints_original)
                    metadata["task_constraints_expanded"] = to_json_safe(task_constraints_expanded)
                records.append(
                    {
                        "id": constraint_index,
                        "mac_constraint_uid": f"{task_uid}-c{constraint_index + 1:04d}",
                        "action": action,
                        "text": text,
                        "metadata": metadata,
                    }
                )
                constraint_index += 1
        return records


def load_sample_tasks(path: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    payload = load_json(path)
    if isinstance(payload, dict) and isinstance(payload.get("tasks"), list):
        return copy.deepcopy(payload["tasks"]), copy.deepcopy(payload)
    if isinstance(payload, list):
        return copy.deepcopy(payload), {"tasks": payload}
    raise ValueError(f"Expected sample manifest object or task list in {path}")


def adapt_task(task: dict[str, Any], runtime: DomainRuntime, neat_prompt: str) -> dict[str, Any]:
    domain = task["domain"]
    user_goal = task["user_goal"]
    task_index = int(task["task_index"])
    task_uid = str(task.get("mac_task_uid") or f"sopbench:{domain}:{user_goal}:{task_index}")

    sop_text = runtime.build_sop_text(task)
    user_prompt = str(task.get("user_prompt") or "").strip()
    constraints = runtime.expand_sop_constraints(task, task_uid)

    return {
        "mac_task_uid": task_uid,
        "domain": domain,
        "user_goal": user_goal,
        "task_index": task_index,
        "source_file": task.get("source_file"),
        "agent_name": agent_name(domain, user_goal, task_index),
        "mac_task_summary": user_prompt or str(task.get("user_instruction") or ""),
        "system_prompt_domain_id": domain,
        "system_prompt": neat_prompt,
        "sop_text": sop_text,
        "input": [
            {"role": "system", "content": neat_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "original_sopbench": {
            "user_instruction": task.get("user_instruction"),
            "user_prompt": task.get("user_prompt"),
            "user_known": copy.deepcopy(task.get("user_known") or {}),
            "constraint_parameters": copy.deepcopy(task.get("constraint_parameters") or {}),
            "constraints": copy.deepcopy(task.get("constraints") or []),
            "constraints_original": copy.deepcopy(task.get("constraints_original") or []),
            "directed_action_graph": copy.deepcopy(task.get("directed_action_graph") or {}),
            "action_should_succeed": task.get("action_should_succeed"),
            "initial_database": copy.deepcopy(task.get("initial_database") or {}),
        },
        "constraints": constraints,
        "tools": copy.deepcopy(runtime.neat_tools),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--system-prompts-output", type=Path, default=DEFAULT_SYSTEM_PROMPTS)
    parser.add_argument("--step1-output", type=Path, default=DEFAULT_STEP1)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    input_path = resolve_path(args.input)
    tasks, source_manifest = load_sample_tasks(input_path)

    domain_runtimes = {domain: DomainRuntime(domain) for domain in DOMAINS}
    system_prompt_rows = [
        {
            "id": domain,
            "domain": domain,
            "system_prompt": domain_runtimes[domain].neat_system_prompt,
        }
        for domain in DOMAINS
    ]
    system_prompt_payload = {
        "schema_version": "MACSOPBenchSystemPromptV1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": "SOPBench create_assistant(..., assistant_dependency_instructions=None)",
        "constraint_descr_format": "structured",
        "tool_list": "full",
        "prompts": system_prompt_rows,
    }
    write_json(args.system_prompts_output, system_prompt_payload)

    step1_tasks: list[dict[str, Any]] = []
    for task in tasks:
        domain = str(task["domain"])
        if domain not in domain_runtimes:
            raise ValueError(f"Unknown domain {domain!r} in sample input")
        neat_prompt = domain_runtimes[domain].neat_system_prompt
        step1_tasks.append(adapt_task(task, domain_runtimes[domain], neat_prompt))

    step1_output_path = resolve_path(args.step1_output)
    step1_meta = {
        "schema_version": "MACConstructStep1SOPV2",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "tasks_output": str(step1_output_path.relative_to(REPO_ROOT))
        if step1_output_path.is_relative_to(REPO_ROOT)
        else str(step1_output_path),
        "source_input": str(input_path.relative_to(REPO_ROOT)) if input_path.is_relative_to(REPO_ROOT) else str(input_path),
        "system_prompts": str(resolve_path(args.system_prompts_output).relative_to(REPO_ROOT))
        if resolve_path(args.system_prompts_output).is_relative_to(REPO_ROOT)
        else str(resolve_path(args.system_prompts_output)),
        "source_summary": source_manifest.get("summary"),
        "summary": {
            "task_count": len(step1_tasks),
            "domain_counts": {
                domain: sum(1 for task in step1_tasks if task["domain"] == domain) for domain in DOMAINS
            },
            "constraint_count": sum(len(task.get("constraints") or []) for task in step1_tasks),
            "avg_constraints_per_task": (
                sum(len(task.get("constraints") or []) for task in step1_tasks) / len(step1_tasks)
                if step1_tasks
                else 0.0
            ),
            "avg_sop_chars": (
                sum(len(task.get("sop_text") or "") for task in step1_tasks) / len(step1_tasks)
                if step1_tasks
                else 0.0
            ),
            "user_goal_constraint_count": sum(
                1
                for task in step1_tasks
                for constraint in task.get("constraints") or []
                if constraint.get("metadata", {}).get("eval_scope") == "user_goal"
            ),
        },
    }
    write_json(args.step1_output, step1_tasks)
    write_json(args.step1_output.with_suffix(args.step1_output.suffix + ".meta.json"), step1_meta)

    print(
        f"wrote {len(system_prompt_rows)} domain system prompt(s) to {resolve_path(args.system_prompts_output)}"
    )
    print(
        f"wrote {len(step1_tasks)} step-1 task(s) to {resolve_path(args.step1_output)}; "
        f"constraints={step1_meta['summary']['constraint_count']}, "
        f"meta={resolve_path(args.step1_output.with_suffix(args.step1_output.suffix + '.meta.json'))}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
