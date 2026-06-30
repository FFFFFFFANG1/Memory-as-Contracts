#!/usr/bin/env python3
"""Generate per-anchor temporal SOP revision histories for MAC SOPBench construct step 3.

Reads ``bench/MAC/sopbench/mid_data/eval_step2_anchors.json`` and writes
``bench/MAC/sopbench/mid_data/eval_step3_temporal_noise.json``:

- per task: ``domain``, ``task_description``
- per constraint: anchor ``text``, ``anchor_dependency``,
  ``anchor_compiled_graph``, and ``temporal_noise`` entries with ``dependency``,
  ``compiled_graph``, ``mutation``, and ``dependency_diff``

Default generator: rule-based dependency mutations (add/delete/flip/swap) on
action-level dependency trees. For each action/subtree the sampler tries up to
10 shuffled mutation candidates and keeps the first validated graph-changing
variants: 4-5 for composite subtrees, 1-2 for small single-constraint subtrees.
Use ``--llm`` for the legacy LLM prose+dependency path.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import importlib
import json
import os
import random
import re
import statistics
import sys
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[4]
CONSTRUCT_SOP_ROOT = REPO_ROOT / "bench" / "MAC" / "construct" / "sop"
DEFAULT_ENV_FILE = Path("bench/.env")
DEFAULT_STEP2 = Path("bench/MAC/sopbench/mid_data/eval_step2_anchors.json")
DEFAULT_STEP3 = Path("bench/MAC/sopbench/mid_data/eval_step3_temporal_noise.json")

DEFAULT_NOISE_MIN = 0
DEFAULT_NOISE_MAX = 5
DEFAULT_NOISE_MEAN = 1.5
DEFAULT_NOISE_STD = 0.8
DEFAULT_VALIDATION_RETRIES = 2
DEFAULT_NOISE_DEDUP_SIMILARITY = 0.92
DEFAULT_RULEBASE_SAMPLE_ATTEMPTS = 10
DEFAULT_RULEBASE_MAX_ATTEMPTS = DEFAULT_RULEBASE_SAMPLE_ATTEMPTS
RULEBASE_PLACEHOLDER_TEXT_PREFIX = "[structural-only]"

_NOISE_DEDUP_ARG_PLACEHOLDERS = (
    "username",
    "provider_id",
    "order_id",
    "check_in_date",
    "check_out_date",
    "appointment_date",
    "claim_id",
    "coverage_amount",
    "annual_income",
    "old_check_in_date",
)

EXECUTABLE_GUIDE = """
### Executable model

This data is for SOPBench tool evaluation. Do not write tool-call processes or
graphs directly. SOPBench derives those from dependency trees.

`anchor_dependency` is the current SOP dependency subtree:
- `["single", constraint_id, params]`: one known SOP constraint.
- `["and", [a, b]]`: all child constraints are required.
- `["or", [a, b]]`: any one child constraint is enough.

For each noisy draft, write a changed `noisy_dependency`. The program will call
SOPBench's graph builder on that dependency and accept the draft only if the
compiled graph differs from the anchor graph.
""".strip()

PROMPT_REQUIREMENTS: list[str] = [
    "Return exactly `noise_count` noisy items, then the anchor item last.",
    "Each item: `text` plus `noisy_dependency`.",
    "Do not output `process`, `compiled_graph`, or tool-call plans; those are derived by SOPBench.",
    "Every `single` constraint_id must come from `allowed_constraints`.",
    "Every params object must use only the provided placeholder values for that constraint.",
    "Noisy dependencies must compile with SOPBench and must compile to a graph different from the anchor graph.",
    "Do not copy or lightly paraphrase `other_anchor_constraints`.",
    "Use `other_constraints_on_action` for context, but do not duplicate one of them as the noisy dependency unless the revision explicitly adds an AND/OR combination.",
    "Write direct standalone rules; avoid if/when/only-if scaffolding.",
    "Anchor item: exact `anchor_constraint.text` and exact `anchor_dependency`.",
    "Output valid JSON only; no markdown or extra metadata.",
]

# --- LLM prompts (edit below) ---

SYSTEM_PROMPT_BODY = """
Generate temporal noise for one SOP constraint.

The anchor is the current rule. Noisy items are plausible earlier revisions of
the same rule thread, and must be obsolete in an executable way. Keep the same
domain, target action, and business topic. Write standalone SOP rules in the
same tone as the anchor.
""".strip()

NOISE_REVISION_GUIDE = """
### Writing superseded drafts

Each noisy item should read like an older version the team later replaced—not a
different rule, a new user goal, or an unrelated policy.

Revision axes (change one main axis when possible):
- **Composition**: add/remove a known sibling requirement with AND.
- **Alternative**: broaden/narrow a known OR branch.
- **Requirement swap**: replace the anchor with a nearby known constraint on the
  same action.
- **Prerequisite shape**: make an older draft require a different known
  checkable condition that SOPBench can compile.

Prose and dependency must agree. Do not invent new policy names or verifier
functions. If you need a stricter or looser predicate, express it using known
constraints and AND/OR structure rather than free-form process edits.

Avoid: unrelated tools or topics; copying `other_anchor_constraints`; conditional
scaffolding ("if/when/only if")—write direct SOP statements; flipping the rule
into its logical opposite unless the executable predicate moves in the same
direction (same intent, stricter or looser—not inverted policy).

Illustrative patterns (pick what fits; do not copy blindly):
- `["single", "policy_active", ...]` → older draft requires
  `["and", [policy_active, logged_in_user]]`.
- `["or", [provider_covers_policy, provider_authorized]]` → older draft only
  accepts one branch.
- `provider_available` → older draft also requires `appointment_date_valid`.
""".strip()


def build_system_prompt() -> str:
    requirements = "\n".join(f"- {item}" for item in PROMPT_REQUIREMENTS)
    return "\n\n".join(
        [
            SYSTEM_PROMPT_BODY,
            NOISE_REVISION_GUIDE,
            EXECUTABLE_GUIDE,
            f"### Output requirements\n{requirements}",
        ]
    )


def prompt_output_schema(*, noise_count: int) -> dict[str, Any]:
    noisy_examples = [
        {
            "text": f"superseded SOP draft {index}",
            "noisy_dependency": ["single", "known_constraint_id", {"param": "param"}],
        }
        for index in range(1, max(1, noise_count) + 1)
    ]
    anchor_item = {
        "text": "anchor constraint text (same as anchor_constraint.text)",
        "noisy_dependency": "same as anchor_dependency",
    }
    if noise_count == 0:
        sequence = [anchor_item]
    else:
        sequence = noisy_examples[:noise_count] + [anchor_item]
    return {
        "noise_count": noise_count,
        "temporal_sequence": sequence,
    }


def resolve_path(path: Path) -> Path:
    return path if path.is_absolute() else REPO_ROOT / path


def ensure_construct_imports() -> None:
    root = str(CONSTRUCT_SOP_ROOT)
    if root not in sys.path:
        sys.path.insert(0, root)


_domain_runtime_cache: dict[str, Any] = {}


def domain_runtime(domain: str) -> Any:
    domain_key = str(domain or "").strip()
    if not domain_key:
        raise ValueError("task domain is required for tool schema lookup")
    if domain_key not in _domain_runtime_cache:
        ensure_construct_imports()
        from filter_sop import DomainRuntime  # noqa: WPS433

        _domain_runtime_cache[domain_key] = DomainRuntime(domain_key)
    return _domain_runtime_cache[domain_key]


def tool_schema_for_name(domain: str, tool_name: str) -> dict[str, Any] | None:
    runtime = domain_runtime(domain)
    for tool in runtime.neat_tools:
        function = tool.get("function") or {}
        if str(function.get("name") or "") == tool_name:
            return copy.deepcopy(tool)
    return None


def involved_tools_schemas(domain: str, tool_names: list[str]) -> list[dict[str, Any]]:
    schemas: list[dict[str, Any]] = []
    for tool_name in tool_names:
        schema = tool_schema_for_name(domain, tool_name)
        if schema is not None:
            schemas.append(schema)
            continue
        schemas.append(
            {
                "type": "function",
                "function": {
                    "name": tool_name,
                    "description": f"SOPBench tool `{tool_name}` (schema unavailable).",
                    "parameters": {"type": "object", "properties": {}, "required": []},
                },
            }
        )
    return schemas


def load_env(env_file: Path | None = None) -> None:
    if env_file:
        load_dotenv(resolve_path(env_file), override=False)
        return
    for candidate in (DEFAULT_ENV_FILE, Path(".env")):
        path = resolve_path(candidate)
        if path.exists():
            load_dotenv(path, override=False)
            return
    load_dotenv(override=False)


def resolve_llm_config(args: argparse.Namespace) -> None:
    if not args.model:
        args.model = os.getenv("MAC_LLM_MODEL") or os.getenv("LLM_MODEL")
    if not args.base_url:
        args.base_url = (
            os.getenv("OPENAI_BASE_URL")
            or os.getenv("MAC_LLM_BASE_URL")
            or os.getenv("LLM_BASE_URL")
        )
    if not args.api_key:
        args.api_key = os.getenv("OPENAI_API_KEY") or os.getenv("LLM_API_KEY")


def load_json(path: Path) -> Any:
    return json.loads(resolve_path(path).read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    target = resolve_path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, indent=4, ensure_ascii=False) + "\n", encoding="utf-8")


def load_step2_tasks(path: Path) -> list[dict[str, Any]]:
    payload = load_json(path)
    if isinstance(payload, list):
        return copy.deepcopy(payload)
    if isinstance(payload, dict) and isinstance(payload.get("tasks"), list):
        return copy.deepcopy(payload["tasks"])
    raise ValueError(f"Expected step-2 task list in {path}")


def sample_truncated_normal_int(
    rng: random.Random,
    *,
    value_min: int,
    value_max: int,
    mean: float,
    std: float,
) -> int:
    if value_min > value_max:
        raise ValueError(f"value_min ({value_min}) must be <= value_max ({value_max})")
    if value_min == value_max:
        return value_min
    for _ in range(256):
        value = int(round(rng.gauss(mean, std)))
        if value_min <= value <= value_max:
            return value
    fallback = int(round(mean))
    return max(value_min, min(value_max, fallback))


def selected_items(data: list[dict[str, Any]], offset: int, limit: int | None) -> list[dict[str, Any]]:
    if offset < 0:
        raise ValueError("--offset must be non-negative")
    if limit is not None and limit < 0:
        raise ValueError("--limit must be non-negative")
    end = None if limit is None else offset + limit
    return data[offset:end]


def truncate_text(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 20].rstrip() + "\n...[truncated]"


def metadata_process(metadata: dict[str, Any]) -> Any:
    proc = metadata.get("constraint_process")
    if proc:
        return copy.deepcopy(proc)
    link = metadata.get("constraint_link")
    if isinstance(link, list) and link:
        tool = str(link[0])
        params = link[1] if len(link) > 1 else {}
        if not isinstance(params, dict):
            params = {}
        return ["single", tool, params]
    return None


def dependency_parameters(metadata: dict[str, Any]) -> dict[str, Any]:
    dep = metadata.get("dependency")
    if isinstance(dep, list) and len(dep) >= 3 and str(dep[0]) == "single":
        params = dep[2]
        if isinstance(params, dict):
            return copy.deepcopy(params)
    return {}


def build_check_from_anchor(anchor: dict[str, Any]) -> dict[str, Any]:
    metadata = anchor.get("metadata") or {}
    constraint_parameters = metadata.get("constraint_parameters")
    if not isinstance(constraint_parameters, dict):
        constraint_parameters = {}
    return {
        "constraint_id": str(metadata.get("constraint_id") or ""),
        "negated": bool(metadata.get("negated", False)),
        "parameters": dependency_parameters(metadata),
        "constraint_parameters": copy.deepcopy(constraint_parameters),
        "semantics": str(anchor.get("text") or "").strip(),
    }


def build_anchor_executable(anchor: dict[str, Any]) -> dict[str, Any]:
    metadata = anchor.get("metadata") or {}
    return {
        "target_action": str(anchor.get("action") or ""),
        "process": metadata_process(metadata),
        "check": build_check_from_anchor(anchor),
    }


def walk_process_tools(process: Any, tools: set[str]) -> None:
    if not process or not isinstance(process, list):
        return
    kind = str(process[0])
    if kind == "single":
        if len(process) > 1:
            name = str(process[1])
            if name.startswith("not "):
                name = name[len("not ") :]
            if name:
                tools.add(name)
        return
    if kind in ("and", "or", "chain", "gate") and len(process) > 1:
        for part in process[1]:
            walk_process_tools(part, tools)


def normalize_param_mapping(params: Any) -> tuple[tuple[str, str], ...]:
    if not isinstance(params, dict):
        return ()
    items: list[tuple[str, str]] = []
    for key in sorted(params.keys()):
        value = params[key]
        items.append((str(key), json.dumps(value, sort_keys=True, ensure_ascii=False)))
    return tuple(items)


def normalize_process_tree(process: Any) -> Any:
    if process is None:
        return None
    if not isinstance(process, list) or not process:
        return None
    kind = str(process[0])
    if kind == "single":
        name = str(process[1]) if len(process) > 1 else ""
        params = normalize_param_mapping(process[2] if len(process) > 2 else {})
        return ("single", name, params)
    if kind in ("and", "or", "chain", "gate"):
        children = process[1] if len(process) > 1 else []
        normalized = tuple(normalize_process_tree(part) for part in children)
        if kind in ("and", "or"):
            normalized = tuple(
                sorted(
                    normalized,
                    key=lambda part: json.dumps(part, sort_keys=True, ensure_ascii=False),
                )
            )
        return (kind, normalized)
    return None


def involved_tools_for_anchor(anchor: dict[str, Any]) -> list[str]:
    executable = build_anchor_executable(anchor)
    tools: set[str] = set()
    action = executable.get("target_action")
    if action:
        tools.add(str(action))
    walk_process_tools(executable.get("process"), tools)
    return sorted(tools)


def normalize_semantics(text: Any) -> str:
    return re.sub(r"\s+", " ", str(text or "").strip().lower())


def check_signature(check: dict[str, Any]) -> tuple[Any, ...]:
    return (
        str(check.get("constraint_id") or ""),
        bool(check.get("negated", False)),
        normalize_semantics(check.get("semantics")),
        json.dumps(check.get("constraint_parameters") or {}, sort_keys=True, ensure_ascii=False),
    )


def executable_signature(executable: dict[str, Any]) -> tuple[Any, ...]:
    check = executable.get("check") if isinstance(executable.get("check"), dict) else {}
    return (
        normalize_process_tree(executable.get("process")),
        check_signature(check),
    )


def executables_equivalent(left: dict[str, Any], right: dict[str, Any]) -> bool:
    return executable_signature(left) == executable_signature(right)


def validate_noisy_executable(
    anchor_executable: dict[str, Any],
    noisy_executable: dict[str, Any],
    *,
    allowed_tools: set[str],
) -> tuple[bool, str]:
    anchor_check = anchor_executable.get("check") if isinstance(anchor_executable.get("check"), dict) else {}
    noisy_check = noisy_executable.get("check") if isinstance(noisy_executable.get("check"), dict) else {}
    anchor_id = str(anchor_check.get("constraint_id") or "")
    noisy_id = str(noisy_check.get("constraint_id") or "")
    if anchor_id and noisy_id and noisy_id != anchor_id:
        return False, f"constraint_id mismatch: {noisy_id} != {anchor_id}"
    if executables_equivalent(anchor_executable, noisy_executable):
        return False, "noisy_executable equivalent to anchor_executable"
    noisy_tools: set[str] = set()
    walk_process_tools(noisy_executable.get("process"), noisy_tools)
    unknown = sorted(noisy_tools - allowed_tools)
    if unknown:
        return False, f"unknown tools in noisy_executable: {unknown}"
    return True, "accepted"


def anchor_dependency(anchor: dict[str, Any]) -> Any:
    metadata = anchor.get("metadata") or {}
    dep = metadata.get("dependency")
    return normalize_dep_tree(dep) if dep is not None else None


def normalize_dep_tree(dep: Any) -> Any:
    if isinstance(dep, tuple):
        return normalize_dep_tree(list(dep))
    if isinstance(dep, list):
        return [
            normalize_dep_tree(item) if isinstance(item, (list, tuple)) else copy.deepcopy(item)
            for item in dep
        ]
    return dep


def task_source_for_dep_full(task: dict[str, Any]) -> dict[str, Any]:
    original = task.get("original_sopbench") or {}
    return {
        "user_goal": str(task.get("user_goal") or ""),
        "constraints_original": original.get("constraints_original")
        or original.get("constraints")
        or [],
        "constraint_parameters": copy.deepcopy(
            original.get("constraint_parameters") or task.get("constraint_parameters") or {}
        ),
    }


def get_action_dependency(task: dict[str, Any], action: str) -> Any | None:
    if not action:
        return None
    runtime = domain_runtime(str(task.get("domain") or ""))
    dep_full = runtime.build_task_dep_full(task_source_for_dep_full(task))
    dep = dep_full.get(action)
    if dep is None:
        return None
    normalized = normalize_dep_tree(dep)
    return normalized if normalized else None


def dependency_kind(dep: Any) -> str:
    if isinstance(dep, (list, tuple)) and dep:
        return str(dep[0])
    return ""


def walk_dependency_singles(dep: Any, singles: list[tuple[str, dict[str, Any]]]) -> None:
    if not isinstance(dep, (list, tuple)) or not dep:
        return
    kind = str(dep[0])
    if kind == "single":
        constraint_id = str(dep[1]) if len(dep) > 1 else ""
        params = dep[2] if len(dep) > 2 and isinstance(dep[2], dict) else {}
        singles.append((constraint_id, copy.deepcopy(params)))
        return
    if kind in ("and", "or", "chain", "gate") and len(dep) > 1 and isinstance(dep[1], (list, tuple)):
        for child in dep[1]:
            walk_dependency_singles(child, singles)


def dependency_singles(dep: Any) -> list[tuple[str, dict[str, Any]]]:
    singles: list[tuple[str, dict[str, Any]]] = []
    walk_dependency_singles(normalize_dep_tree(dep), singles)
    return singles


def dependency_node_count(dep: Any) -> int:
    dep = normalize_dep_tree(dep)
    if not isinstance(dep, list) or not dep:
        return 0
    kind = str(dep[0])
    if kind == "single":
        return 1
    if kind in ("and", "or", "chain", "gate") and len(dep) > 1 and isinstance(dep[1], list):
        return 1 + sum(dependency_node_count(child) for child in dep[1])
    return 0


def process_node_count(process: Any) -> int:
    if not isinstance(process, list) or not process:
        return 0
    kind = str(process[0])
    if kind == "single":
        return 1
    if kind in ("and", "or", "chain", "gate") and len(process) > 1 and isinstance(process[1], list):
        return 1 + sum(process_node_count(child) for child in process[1])
    return 0


def constraint_complexity(anchor: dict[str, Any]) -> int:
    dep = anchor_dependency(anchor)
    proc = metadata_process(anchor.get("metadata") or {})
    score = dependency_node_count(dep) + process_node_count(proc)
    if dependency_kind(dep) in ("and", "or"):
        score += 2
    if dependency_kind(proc) in ("and", "or", "chain", "gate"):
        score += 2
    return score


def action_dependency_complexity(action_dep: Any) -> int:
    dep = normalize_dep_tree(action_dep)
    score = dependency_node_count(dep)
    if dependency_kind(dep) in ("and", "or"):
        score += 2
    nested_logic = sum(
        1
        for node, _ in dependency_singles(dep)
        for _ in [0]
    )
    if nested_logic > 1:
        score += min(3, nested_logic - 1)
    return score


def is_small_subtree(dep: Any) -> bool:
    """True for single-bullet or very shallow dependency subtrees."""
    dep = normalize_dep_tree(dep)
    if dependency_kind(dep) == "single":
        return True
    singles = len(dependency_singles(dep))
    nodes = dependency_node_count(dep)
    return singles <= 2 and nodes <= 3


def complexity_aware_action_noise_target(
    action_dep: Any,
    rng: random.Random,
    *,
    noise_min: int,
    noise_max: int,
) -> int:
    if noise_max <= 0:
        return 0
    if is_small_subtree(action_dep):
        target = rng.choice([1, 2])
    else:
        target = rng.choice([4, 5])
    return max(noise_min, min(noise_max, target))


def complexity_aware_noise_target(
    anchor: dict[str, Any],
    rng: random.Random,
    *,
    noise_min: int,
    noise_max: int,
) -> int:
    if noise_max <= 0:
        return 0
    anchor_dep = anchor_dependency(anchor)
    if anchor_dep is not None and is_small_subtree(anchor_dep):
        target = rng.choice([1, 2])
    else:
        target = rng.choice([4, 5])
    return max(noise_min, min(noise_max, target))


def normalize_single_constraint_id(raw_id: str) -> str:
    constraint_id = str(raw_id)
    if constraint_id.startswith("not "):
        constraint_id = constraint_id[len("not ") :]
    return constraint_id


def normalize_single_params(params: Any) -> dict[str, Any]:
    if params is None:
        return {}
    if isinstance(params, dict):
        return params
    return {}


def known_constraint_params(task: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    known: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for constraint in task.get("constraints") or []:
        if not isinstance(constraint, dict):
            continue
        dep = (constraint.get("metadata") or {}).get("dependency")
        for raw_id, params in dependency_singles(dep):
            constraint_id = normalize_single_constraint_id(raw_id)
            if not constraint_id:
                continue
            normalized_params = normalize_single_params(params)
            if normalized_params not in known[constraint_id]:
                known[constraint_id].append(normalized_params)
    return dict(known)


def allowed_constraint_records(task: dict[str, Any], action: str) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for constraint in task.get("constraints") or []:
        if not isinstance(constraint, dict):
            continue
        if action and str(constraint.get("action") or "") != action:
            continue
        metadata = constraint.get("metadata") or {}
        dep = metadata.get("dependency")
        singles = dependency_singles(dep)
        if not singles:
            continue
        constraint_id, params = singles[0]
        key = (constraint_id, json.dumps(params, sort_keys=True, ensure_ascii=False))
        if key in seen:
            continue
        seen.add(key)
        records.append(
            {
                "constraint_id": constraint_id,
                "params": copy.deepcopy(params),
            }
        )
    return records


def other_constraints_on_action(
    task: dict[str, Any],
    *,
    current_uid: str,
    target_action: str,
) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for constraint in task.get("constraints") or []:
        if not isinstance(constraint, dict):
            continue
        uid = str(constraint.get("mac_constraint_uid") or "")
        if uid == current_uid:
            continue
        if target_action and str(constraint.get("action") or "") != target_action:
            continue
        metadata = constraint.get("metadata") or {}
        entries.append(
            {
                "mac_constraint_uid": uid,
                "constraint_id": str(metadata.get("constraint_id") or ""),
                "dependency": copy.deepcopy(metadata.get("dependency")),
                "text": truncate_text(str(constraint.get("text") or ""), 400),
            }
        )
    return entries


@dataclass(frozen=True)
class DependencyMutation:
    kind: str
    label: str
    sibling_dep: Any | None = None
    child_index: int | None = None


def canonical_dependency_signature(dep: Any) -> str:
    return json.dumps(dep, sort_keys=True, ensure_ascii=False)


def same_action_dependency_pool(
    task: dict[str, Any],
    *,
    target_action: str,
    current_uid: str,
) -> list[dict[str, Any]]:
    return copy.deepcopy(
        other_constraints_on_action(
            task,
            current_uid=current_uid,
            target_action=target_action,
        )
    )


def cross_action_single_pool(task: dict[str, Any], target_action: str) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    seen: set[str] = set()
    for constraint in task.get("constraints") or []:
        if not isinstance(constraint, dict):
            continue
        action = str(constraint.get("action") or "")
        if not action or action == target_action:
            continue
        metadata = constraint.get("metadata") or {}
        dep = normalize_dep_tree(metadata.get("dependency"))
        if dep is None:
            continue
        sig = canonical_dependency_signature(dep)
        if sig in seen:
            continue
        seen.add(sig)
        entries.append(
            {
                "constraint_id": str(metadata.get("constraint_id") or ""),
                "dependency": copy.deepcopy(dep),
                "source_action": action,
            }
        )
    return entries


def apply_dependency_mutation(anchor_dep: Any, mutation: DependencyMutation) -> Any | None:
    dep = copy.deepcopy(normalize_dep_tree(anchor_dep))
    kind = mutation.kind
    if kind == "add_and":
        if mutation.sibling_dep is None:
            return None
        return ["and", [dep, copy.deepcopy(mutation.sibling_dep)]]
    if kind == "add_or":
        if mutation.sibling_dep is None:
            return None
        return ["or", [dep, copy.deepcopy(mutation.sibling_dep)]]
    if kind == "swap":
        if mutation.sibling_dep is None:
            return None
        return copy.deepcopy(mutation.sibling_dep)
    if kind == "flip_logic":
        logic = dependency_kind(dep)
        if logic not in ("and", "or") or len(dep) < 2 or not isinstance(dep[1], list):
            return None
        flipped = "or" if logic == "and" else "and"
        return [flipped, copy.deepcopy(dep[1])]
    if kind == "delete_child":
        logic = dependency_kind(dep)
        if logic not in ("and", "or") or len(dep) < 2 or not isinstance(dep[1], list):
            return None
        child_index = mutation.child_index
        if child_index is None or child_index < 0 or child_index >= len(dep[1]):
            return None
        remaining = [
            copy.deepcopy(child)
            for index, child in enumerate(dep[1])
            if index != child_index
        ]
        if not remaining:
            return None
        if len(remaining) == 1:
            return remaining[0]
        return [logic, remaining]
    if kind == "unwrap":
        if mutation.sibling_dep is None:
            return None
        return copy.deepcopy(mutation.sibling_dep)
    return None


def enumerate_dependency_mutations(
    anchor_dep: Any,
    pool: list[dict[str, Any]],
) -> list[DependencyMutation]:
    anchor_dep = normalize_dep_tree(anchor_dep)
    anchor_sig = canonical_dependency_signature(anchor_dep)
    seen: set[str] = set()
    candidates: list[DependencyMutation] = []

    def add_candidate(mutation: DependencyMutation) -> None:
        mutated = apply_dependency_mutation(anchor_dep, mutation)
        if mutated is None:
            return
        sig = canonical_dependency_signature(mutated)
        if sig == anchor_sig or sig in seen:
            return
        seen.add(sig)
        candidates.append(mutation)

    for entry in pool:
        sibling_dep = entry.get("dependency")
        if sibling_dep is None:
            continue
        constraint_id = str(entry.get("constraint_id") or "sibling")
        add_candidate(
            DependencyMutation("add_and", f"add_and:{constraint_id}", sibling_dep=sibling_dep)
        )
        add_candidate(
            DependencyMutation("add_or", f"add_or:{constraint_id}", sibling_dep=sibling_dep)
        )
        add_candidate(
            DependencyMutation("swap", f"swap:{constraint_id}", sibling_dep=sibling_dep)
        )

    logic = dependency_kind(anchor_dep)
    if logic in ("and", "or") and len(anchor_dep) > 1 and isinstance(anchor_dep[1], list):
        flipped = "or" if logic == "and" else "and"
        add_candidate(
            DependencyMutation("flip_logic", f"flip_logic:{logic}_to_{flipped}")
        )
        children = anchor_dep[1]
        if len(children) > 1:
            for index in range(len(children)):
                add_candidate(
                    DependencyMutation(
                        "delete_child",
                        f"delete_child:{index}",
                        child_index=index,
                    )
                )
        elif len(children) == 1:
            add_candidate(
                DependencyMutation("unwrap", "unwrap", sibling_dep=children[0])
            )

    return candidates


def build_dependency_diff(
    *,
    before: Any,
    after: Any,
    mutation: str,
) -> dict[str, Any]:
    return {
        "mutation": mutation,
        "before": copy.deepcopy(before),
        "after": copy.deepcopy(after),
        "before_signature": canonical_dependency_signature(before),
        "after_signature": canonical_dependency_signature(after),
    }


def structural_placeholder_text(mutation_label: str, *, anchor_uid: str = "") -> str:
    if anchor_uid.startswith("action:"):
        suffix = anchor_uid.replace("action:", "action-")
    else:
        suffix = anchor_uid.split(":")[-1] if anchor_uid else "unknown"
    return f"{RULEBASE_PLACEHOLDER_TEXT_PREFIX} {suffix} mutation={mutation_label}"


def dependency_dedup_is_duplicate(
    dep: Any,
    existing: list[dict[str, Any]],
) -> tuple[bool, str]:
    signature = canonical_dependency_signature(dep)
    for item in existing:
        other_sig = str(item.get("dependency_signature") or "")
        if other_sig and other_sig == signature:
            other_uid = str(item.get("mac_constraint_uid") or "")
            suffix = f" (anchor {other_uid.split(':')[-1]})" if other_uid else ""
            return True, f"duplicate dependency signature{suffix}"
    return False, ""


def graph_children(graph: dict[str, Any]) -> dict[int, list[int]]:
    children: dict[int, list[int]] = defaultdict(list)
    for edge in graph.get("connections") or []:
        if isinstance(edge, (list, tuple)) and len(edge) >= 2:
            children[int(edge[0])].append(int(edge[1]))
    return {key: sorted(value) for key, value in children.items()}


def graph_node_action(node: Any) -> str | None:
    if isinstance(node, list) and node:
        return str(node[0])
    if isinstance(node, tuple) and node:
        return str(node[0])
    return None


def graph_to_process(graph: dict[str, Any], target_action: str) -> Any:
    nodes = graph.get("nodes") or []
    if not isinstance(nodes, list):
        return None
    children = graph_children(graph)

    def to_process(index: int, stack: set[int] | None = None) -> Any:
        stack = stack or set()
        if index in stack or index < 0 or index >= len(nodes):
            return None
        stack.add(index)
        node = nodes[index]
        if isinstance(node, (list, tuple)) and node:
            params = node[1] if len(node) > 1 and isinstance(node[1], dict) else {}
            return ["single", str(node[0]), copy.deepcopy(params)]
        if isinstance(node, str) and node in ("and", "or"):
            parts = [
                child_proc
                for child in children.get(index, [])
                if (child_proc := to_process(child, set(stack))) is not None
            ]
            if not parts:
                return None
            if len(parts) == 1:
                return parts[0]
            return [node, parts]
        return None

    root_indices = [
        index
        for index, node in enumerate(nodes)
        if graph_node_action(node) == target_action
    ] or [0]
    root = root_indices[0]
    root_children = children.get(root, [])
    parts = [
        child_proc
        for child in root_children
        if (child_proc := to_process(child, set())) is not None
    ]
    if not parts:
        return None
    if len(parts) == 1:
        return parts[0]
    return ["and", parts]


def build_patched_dep_full(
    task: dict[str, Any],
    *,
    mutated_action: str,
    noisy_dependency: Any,
) -> dict[str, Any]:
    ensure_construct_imports()
    from filter_sop import list_to_tuple  # noqa: WPS433

    runtime = domain_runtime(str(task.get("domain") or ""))
    dep_full = runtime.build_task_dep_full(task_source_for_dep_full(task))
    if mutated_action and noisy_dependency is not None:
        dep_full[str(mutated_action)] = list_to_tuple(normalize_dep_tree(noisy_dependency))
    return dep_full


def compile_action_graph(
    *,
    task: dict[str, Any],
    target_action: str,
    dependency: Any,
    dep_full: dict[str, Any] | None = None,
) -> dict[str, Any]:
    ensure_construct_imports()
    from filter_sop import ensure_sopbench_imports  # noqa: WPS433

    ensure_sopbench_imports()
    from env.helpers import dfsgather_invfunccalldirgraph, get_action_parameters  # type: ignore[import-not-found]  # noqa: WPS433
    from env.variables import domain_keys  # type: ignore[import-not-found]  # noqa: WPS433

    domain = str(task.get("domain") or "")
    runtime = domain_runtime(domain)
    domain_assistant = runtime._domain_assistant
    domain_system = domain_keys[domain]()
    action_parameters = get_action_parameters(domain_system, domain_assistant)
    params = {
        key: key
        for key in sorted(action_parameters.get(target_action, set()))
    }
    user_goal_node = (target_action, params)
    resolved_dep_full = dep_full if dep_full is not None else runtime.default_dep_full
    graph = dfsgather_invfunccalldirgraph(
        copy.deepcopy(normalize_dep_tree(dependency)),
        domain_assistant.constraint_links,
        domain_assistant.constraint_processes,
        resolved_dep_full,
        action_parameters,
        user_goal_node,
    )
    return {
        "graph": copy.deepcopy(graph),
        "process": graph_to_process(graph, target_action),
    }


def compile_dependency_graph(
    *,
    task: dict[str, Any],
    target_action: str,
    dependency: Any,
) -> dict[str, Any]:
    return compile_action_graph(
        task=task,
        target_action=target_action,
        dependency=dependency,
    )


def compile_user_goal_graph_under_noise(
    *,
    task: dict[str, Any],
    mutated_action: str,
    noisy_dependency: Any,
) -> dict[str, Any]:
    user_goal = str(task.get("user_goal") or "").strip()
    if not user_goal:
        raise ValueError("task missing user_goal")
    dep_full = build_patched_dep_full(
        task,
        mutated_action=mutated_action,
        noisy_dependency=noisy_dependency,
    )
    user_goal_dep = dep_full.get(user_goal)
    if not user_goal_dep:
        raise ValueError(f"user_goal action {user_goal} has no dependency in dep_full")
    return compile_action_graph(
        task=task,
        target_action=user_goal,
        dependency=user_goal_dep,
        dep_full=dep_full,
    )


def graph_signature(graph: Any) -> str:
    return json.dumps(graph, sort_keys=True, ensure_ascii=False)


def validate_dependency_tree(
    dep: Any,
    *,
    known_params: dict[str, list[dict[str, Any]]],
) -> tuple[bool, str]:
    dep = normalize_dep_tree(dep)
    if not isinstance(dep, list) or not dep:
        return False, "dependency must be a non-empty list"
    kind = str(dep[0])
    if kind == "single":
        if len(dep) < 2:
            return False, "single dependency must be [single, constraint_id, params?]"
        constraint_id = normalize_single_constraint_id(str(dep[1]))
        params = normalize_single_params(dep[2] if len(dep) > 2 else None)
        if constraint_id not in known_params:
            return False, f"unknown constraint_id: {constraint_id}"
        if len(dep) > 2 and dep[2] is not None and not isinstance(dep[2], dict):
            return False, f"params for {constraint_id} must be an object"
        allowed_param_sets = known_params[constraint_id]
        if params not in allowed_param_sets:
            return False, f"params for {constraint_id} are not one of the allowed mappings"
        return True, "ok"
    if kind in ("and", "or", "chain", "gate"):
        if len(dep) < 2 or not isinstance(dep[1], list) or len(dep[1]) < 1:
            return False, f"{kind} dependency must contain a non-empty child list"
        for index, child in enumerate(dep[1]):
            ok, reason = validate_dependency_tree(child, known_params=known_params)
            if not ok:
                return False, f"{kind} child {index}: {reason}"
        return True, "ok"
    return False, f"unsupported dependency kind: {kind}"


def executable_from_compiled(
    *,
    target_action: str,
    compiled: dict[str, Any],
    anchor_executable: dict[str, Any],
    text: str,
) -> dict[str, Any]:
    check = copy.deepcopy(anchor_executable.get("check") or {})
    check["semantics"] = text
    return {
        "target_action": target_action,
        "process": copy.deepcopy(compiled.get("process")),
        "check": check,
    }


def normalize_noisy_dependency(raw: dict[str, Any]) -> Any:
    for key in ("noisy_dependency", "dependency"):
        if key in raw:
            return copy.deepcopy(raw.get(key))
    return None


def normalize_noise_text(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "").strip().lower())


def noise_text_fingerprint(text: str) -> str:
    normalized = normalize_noise_text(text)
    for placeholder in _NOISE_DEDUP_ARG_PLACEHOLDERS:
        normalized = re.sub(rf'"{re.escape(placeholder)}"', "<arg>", normalized)
        normalized = re.sub(rf"\b{re.escape(placeholder)}\b", "<arg>", normalized)
    normalized = re.sub(r"\b\d{1,2}:\d{2}\b", "<time>", normalized)
    normalized = re.sub(r"\b\d+\b", "<num>", normalized)
    return normalized


def noise_text_jaccard(left: str, right: str) -> float:
    left_tokens = set(normalize_noise_text(left).split())
    right_tokens = set(normalize_noise_text(right).split())
    if not left_tokens or not right_tokens:
        return 0.0
    return len(left_tokens & right_tokens) / len(left_tokens | right_tokens)


def noise_dedup_is_duplicate(
    text: str,
    existing: list[dict[str, Any]],
    *,
    similarity_threshold: float = DEFAULT_NOISE_DEDUP_SIMILARITY,
) -> tuple[bool, str]:
    candidate = str(text or "").strip()
    if not candidate:
        return True, "empty text"
    normalized = normalize_noise_text(candidate)
    fingerprint = noise_text_fingerprint(candidate)
    for item in existing:
        other_text = str(item.get("text") or "").strip()
        if not other_text:
            continue
        if normalized == normalize_noise_text(other_text):
            other_uid = str(item.get("mac_constraint_uid") or "")
            suffix = f" (anchor {other_uid.split(':')[-1]})" if other_uid else ""
            return True, f"exact duplicate text{suffix}"
        if fingerprint == noise_text_fingerprint(other_text):
            other_uid = str(item.get("mac_constraint_uid") or "")
            suffix = f" (anchor {other_uid.split(':')[-1]})" if other_uid else ""
            return True, f"duplicate template fingerprint{suffix}"
        similarity = noise_text_jaccard(candidate, other_text)
        if similarity >= similarity_threshold:
            other_uid = str(item.get("mac_constraint_uid") or "")
            suffix = f" (anchor {other_uid.split(':')[-1]}, j={similarity:.2f})" if other_uid else f" (j={similarity:.2f})"
            return True, f"similar text{suffix}"
    return False, ""


def noise_dedup_items(
    items: list[dict[str, Any]],
    task_existing_noisy: list[dict[str, Any]],
    *,
    mac_constraint_uid: str = "",
    similarity_threshold: float = DEFAULT_NOISE_DEDUP_SIMILARITY,
) -> tuple[list[dict[str, Any]], list[str], dict[str, Any]]:
    kept: list[dict[str, Any]] = []
    rejected_reasons: list[str] = []
    registry = [copy.deepcopy(item) for item in task_existing_noisy]
    for index, item in enumerate(items, start=1):
        text = str(item.get("text") or "").strip()
        is_duplicate, reason = noise_dedup_is_duplicate(
            text,
            registry,
            similarity_threshold=similarity_threshold,
        )
        if is_duplicate:
            rejected_reasons.append(f"noisy item {index}: task dedup: {reason}")
            continue
        kept.append(item)
        registry.append(
            {
                "text": text,
                "mac_constraint_uid": mac_constraint_uid,
            }
        )
    return kept, rejected_reasons, {"kept": len(kept), "rejected": len(rejected_reasons)}


def task_noisy_registry_from_artifact(
    artifact: dict[str, Any],
    *,
    exclude_constraint_uid: str | None = None,
) -> list[dict[str, Any]]:
    constraint_uid = str(artifact.get("mac_constraint_uid") or "")
    if exclude_constraint_uid and constraint_uid == exclude_constraint_uid:
        return []
    entries: list[dict[str, Any]] = []
    for item in artifact.get("temporal_sequence") or []:
        if item.get("is_anchor"):
            continue
        text = str(item.get("text") or "").strip()
        dependency = item.get("dependency")
        if not text and dependency is None:
            continue
        registry_item: dict[str, Any] = {"mac_constraint_uid": constraint_uid}
        if text:
            registry_item["text"] = text
        if dependency is not None:
            registry_item["dependency_signature"] = canonical_dependency_signature(dependency)
        entries.append(registry_item)
    return entries


def dedup_slim_step3_tasks(
    tasks: list[dict[str, Any]],
    *,
    similarity_threshold: float = DEFAULT_NOISE_DEDUP_SIMILARITY,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    deduped_tasks = copy.deepcopy(tasks)
    report: dict[str, Any] = {
        "similarity_threshold": similarity_threshold,
        "tasks": [],
        "total_before": 0,
        "total_after": 0,
        "total_removed": 0,
    }
    for task in deduped_tasks:
        task_uid = str(task.get("mac_task_uid") or "")
        registry: list[dict[str, Any]] = []
        removed: list[dict[str, Any]] = []
        before_count = 0
        after_count = 0
        for constraint in task.get("constraints") or []:
            if not isinstance(constraint, dict):
                continue
            constraint_uid = str(constraint.get("mac_constraint_uid") or "")
            kept_noise: list[dict[str, Any]] = []
            for noisy in constraint.get("temporal_noise") or []:
                if not isinstance(noisy, dict):
                    continue
                before_count += 1
                text = str(noisy.get("text") or "").strip()
                is_duplicate, reason = noise_dedup_is_duplicate(
                    text,
                    registry,
                    similarity_threshold=similarity_threshold,
                )
                if is_duplicate:
                    removed.append(
                        {
                            "mac_constraint_uid": constraint_uid,
                            "text": text,
                            "reason": reason,
                        }
                    )
                    continue
                kept_noise.append(noisy)
                registry.append({"text": text, "mac_constraint_uid": constraint_uid})
                after_count += 1
            constraint["temporal_noise"] = kept_noise
        task_report = {
            "mac_task_uid": task_uid,
            "noisy_before": before_count,
            "noisy_after": after_count,
            "removed": len(removed),
            "removed_items": removed,
        }
        report["tasks"].append(task_report)
        report["total_before"] += before_count
        report["total_after"] += after_count
        report["total_removed"] += len(removed)
    return deduped_tasks, report


def apply_noise_dedup_to_artifacts(
    artifacts_by_uid: dict[str, dict[str, Any]],
    tasks: list[dict[str, Any]],
    *,
    similarity_threshold: float = DEFAULT_NOISE_DEDUP_SIMILARITY,
) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    updated = copy.deepcopy(artifacts_by_uid)
    report: dict[str, Any] = {
        "similarity_threshold": similarity_threshold,
        "tasks": [],
        "total_before": 0,
        "total_after": 0,
        "total_removed": 0,
    }
    for task in tasks:
        task_uid = str(task.get("mac_task_uid") or "")
        anchor_entries = task.get("constraints") or task.get("anchors") or []
        registry: list[dict[str, Any]] = []
        removed: list[dict[str, Any]] = []
        before_count = 0
        after_count = 0
        for entry in anchor_entries:
            if not isinstance(entry, dict):
                continue
            constraint_uid = str(entry.get("mac_constraint_uid") or "").strip()
            artifact = updated.get(constraint_uid)
            if not artifact:
                continue
            sequence = artifact.get("temporal_sequence")
            if not isinstance(sequence, list):
                continue
            anchor_items = [item for item in sequence if item.get("is_anchor")]
            noisy_items = [item for item in sequence if not item.get("is_anchor")]
            kept_noisy: list[dict[str, Any]] = []
            for item in noisy_items:
                before_count += 1
                text = str(item.get("text") or "").strip()
                is_duplicate, reason = noise_dedup_is_duplicate(
                    text,
                    registry,
                    similarity_threshold=similarity_threshold,
                )
                if is_duplicate:
                    removed.append(
                        {
                            "mac_constraint_uid": constraint_uid,
                            "text": text,
                            "reason": reason,
                        }
                    )
                    continue
                kept_noisy.append(item)
                registry.append({"text": text, "mac_constraint_uid": constraint_uid})
                after_count += 1
            for index, item in enumerate(kept_noisy, start=1):
                item["local_id"] = f"t{index}"
                item["temporal_order"] = index
            anchor_item = anchor_items[0] if anchor_items else None
            if anchor_item is not None:
                anchor_item["temporal_order"] = len(kept_noisy) + 1
                anchor_item["local_id"] = "anchor"
            artifact["temporal_sequence"] = kept_noisy + ([anchor_item] if anchor_item else [])
            artifact["noise_effective"] = len(kept_noisy)
            artifact["sequence_length"] = len(artifact["temporal_sequence"])
        task_report = {
            "mac_task_uid": task_uid,
            "noisy_before": before_count,
            "noisy_after": after_count,
            "removed": len(removed),
            "removed_items": removed,
        }
        report["tasks"].append(task_report)
        report["total_before"] += before_count
        report["total_after"] += after_count
        report["total_removed"] += len(removed)
    return updated, report


def task_context(task: dict[str, Any]) -> dict[str, Any]:
    original = task.get("original_sopbench") or {}
    return {
        "task_description": task.get("mac_task_summary") or original.get("user_instruction") or "",
    }


def other_anchor_summaries(
    task: dict[str, Any],
    *,
    current_uid: str,
    target_action: str,
) -> list[dict[str, Any]]:
    summaries: list[dict[str, Any]] = []
    target_action = str(target_action or "").strip()
    for anchor in task.get("anchors") or []:
        if not isinstance(anchor, dict):
            continue
        uid = str(anchor.get("mac_constraint_uid") or "")
        if not uid or uid == current_uid:
            continue
        if target_action and str(anchor.get("action") or "") != target_action:
            continue
        summaries.append(
            {
                "action": anchor.get("action"),
                "text": truncate_text(str(anchor.get("text") or ""), 400),
            }
        )
    return summaries


def anchor_summary(anchor: dict[str, Any]) -> dict[str, Any]:
    return {
        "action": anchor.get("action"),
        "text": anchor.get("text"),
    }


@dataclass(frozen=True)
class AnchorJob:
    ordinal: int
    total: int
    task: dict[str, Any]
    task_index: int
    anchor: dict[str, Any]
    anchor_index: int
    noise_target: int
    task_seed: int = 0


@dataclass(frozen=True)
class ActionJob:
    ordinal: int
    total: int
    task: dict[str, Any]
    task_index: int
    action: str
    anchors: tuple[dict[str, Any], ...]
    noise_target: int
    task_seed: int = 0


def allowed_tools_for_job(job: AnchorJob) -> set[str]:
    tools = set(involved_tools_for_anchor(job.anchor))
    target_action = str(job.anchor.get("action") or "")
    for constraint in job.task.get("constraints") or []:
        if not isinstance(constraint, dict):
            continue
        if target_action and str(constraint.get("action") or "") != target_action:
            continue
        tools.update(involved_tools_for_anchor(constraint))
    return tools


def build_user_prompt(job: AnchorJob) -> str:
    anchor_uid = str(job.anchor.get("mac_constraint_uid") or "")
    anchor_executable = build_anchor_executable(job.anchor)
    dep = anchor_dependency(job.anchor)
    tool_names = involved_tools_for_anchor(job.anchor)
    domain = str(job.task.get("domain") or "")
    target_action = str(job.anchor.get("action") or "")
    payload = {
        "task_context": task_context(job.task),
        "target_action": target_action,
        "anchor_constraint": anchor_summary(job.anchor),
        "anchor_dependency": dep,
        "anchor_compiled_graph": compile_dependency_graph(
            task=job.task,
            target_action=target_action,
            dependency=dep,
        ).get("graph") if dep is not None else None,
        "involved_tools": involved_tools_schemas(domain, tool_names),
        "allowed_constraints": allowed_constraint_records(job.task, target_action),
        "other_constraints_on_action": other_constraints_on_action(
            job.task,
            current_uid=anchor_uid,
            target_action=target_action,
        ),
        "other_anchor_constraints": other_anchor_summaries(
            job.task,
            current_uid=anchor_uid,
            target_action=target_action,
        ),
        "noise_count": job.noise_target,
        "output_schema": prompt_output_schema(noise_count=job.noise_target),
    }
    return json.dumps(payload, indent=2, ensure_ascii=False)


def call_llm(
    *,
    model: str,
    base_url: str | None,
    api_key: str | None,
    user_prompt: str,
    max_tokens: int,
    timeout: float,
    retries: int,
    sleep: float,
) -> str:
    try:
        openai_module = importlib.import_module("openai")
    except ImportError as exc:
        raise RuntimeError("openai package is required for live temporal noise generation") from exc

    if not model:
        raise ValueError("Missing model. Pass --model or set MAC_LLM_MODEL / LLM_MODEL.")
    if not api_key:
        raise ValueError("Missing API key. Pass --api-key or set OPENAI_API_KEY / LLM_API_KEY.")

    client = openai_module.OpenAI(
        api_key=api_key,
        base_url=base_url or None,
        timeout=timeout,
        max_retries=0,
    )
    last_error: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            response = client.chat.completions.create(
                model=model,
                temperature=0.4,
                max_tokens=max_tokens,
                messages=[
                    {"role": "system", "content": build_system_prompt()},
                    {"role": "user", "content": user_prompt},
                ],
            )
            return response.choices[0].message.content or ""
        except Exception as exc:  # noqa: BLE001 - CLI should retry transport/provider errors.
            last_error = exc
            if attempt == retries:
                break
            time.sleep(sleep * (2 ** (attempt - 1)))
    raise RuntimeError(f"LLM request failed after {retries} attempts: {last_error}") from last_error


def parse_llm_json(text: str) -> dict[str, Any]:
    stripped = text.strip()
    if stripped.startswith("```"):
        match = re.search(r"```(?:json)?\s*(.*?)\s*```", stripped, flags=re.DOTALL)
        if match:
            stripped = match.group(1).strip()
    payload = json.loads(stripped)
    if isinstance(payload, list):
        return {"temporal_sequence": payload}
    if not isinstance(payload, dict):
        raise ValueError("LLM JSON root must be an object")
    return payload


def normalize_temporal_sequence(
    payload: dict[str, Any],
    *,
    job: AnchorJob,
    anchor_executable: dict[str, Any],
    allowed_tools: set[str],
    task_existing_noisy: list[dict[str, Any]] | None = None,
    noise_dedup_similarity: float = DEFAULT_NOISE_DEDUP_SIMILARITY,
) -> tuple[list[dict[str, Any]], list[str], dict[str, Any]]:
    warnings: list[str] = []
    validation: dict[str, Any] = {
        "accepted": 0,
        "rejected": 0,
        "reject_reasons": [],
        "task_dedup_rejected": 0,
    }
    raw_items = payload.get("temporal_sequence")
    if raw_items is None:
        raw_items = payload.get("generated_constraints")
    if not isinstance(raw_items, list):
        raise ValueError("LLM payload must contain temporal_sequence array")
    if not raw_items:
        raise ValueError("temporal_sequence is empty")

    anchor_text = str(job.anchor.get("text") or "").strip()
    target_action = str(job.anchor.get("action") or "")
    anchor_dep = anchor_dependency(job.anchor)
    if anchor_dep is None:
        raise ValueError("anchor has no metadata.dependency; cannot run graph-builder validation")
    known_params = known_constraint_params(job.task)
    try:
        anchor_compiled = compile_dependency_graph(
            task=job.task,
            target_action=target_action,
            dependency=anchor_dep,
        )
    except Exception as exc:  # noqa: BLE001
        raise ValueError(f"anchor dependency failed graph-builder compilation: {exc}") from exc
    anchor_graph_sig = graph_signature(anchor_compiled.get("graph"))
    parsed_items: list[dict[str, Any]] = []
    for index, raw in enumerate(raw_items):
        if not isinstance(raw, dict):
            warnings.append(f"skipped non-object temporal item at index {index}")
            continue
        text = str(raw.get("text") or "").strip()
        if not text:
            warnings.append(f"skipped empty temporal item at index {index}")
            continue
        dep = normalize_noisy_dependency(raw)
        parsed_items.append({"text": text, "dependency": dep})

    if not parsed_items:
        raise ValueError("temporal_sequence is empty after normalization")

    anchor_raw = parsed_items[-1]
    noisy_raws = parsed_items[:-1]
    if job.noise_target == 0 and noisy_raws:
        warnings.append("noise_target=0 but LLM returned noisy items; dropped extras")
        noisy_raws = []

    non_anchor: list[dict[str, Any]] = []
    constraint_uid = str(job.anchor.get("mac_constraint_uid") or "")
    dedup_registry = [copy.deepcopy(item) for item in (task_existing_noisy or [])]
    for index, item in enumerate(noisy_raws, start=1):
        dep = item.get("dependency")
        accepted, reason = validate_dependency_tree(dep, known_params=known_params)
        if not accepted:
            validation["rejected"] += 1
            validation["reject_reasons"].append(f"noisy item {index}: {reason}")
            continue
        try:
            compiled = compile_dependency_graph(
                task=job.task,
                target_action=target_action,
                dependency=dep,
            )
        except Exception as exc:  # noqa: BLE001
            validation["rejected"] += 1
            validation["reject_reasons"].append(
                f"noisy item {index}: graph-builder compilation failed: {exc}"
            )
            continue
        compiled_graph_sig = graph_signature(compiled.get("graph"))
        if compiled_graph_sig == anchor_graph_sig:
            validation["rejected"] += 1
            validation["reject_reasons"].append(
                f"noisy item {index}: compiled graph equivalent to anchor graph"
            )
            continue
        executable = executable_from_compiled(
            target_action=target_action,
            compiled=compiled,
            anchor_executable=anchor_executable,
            text=item["text"],
        )
        accepted, reason = validate_noisy_executable(
            anchor_executable,
            executable,
            allowed_tools=allowed_tools,
        )
        if not accepted:
            validation["rejected"] += 1
            validation["reject_reasons"].append(f"noisy item {index}: {reason}")
            continue
        is_duplicate, dedup_reason = noise_dedup_is_duplicate(
            item["text"],
            dedup_registry,
            similarity_threshold=noise_dedup_similarity,
        )
        if is_duplicate:
            validation["rejected"] += 1
            validation["task_dedup_rejected"] += 1
            validation["reject_reasons"].append(f"noisy item {index}: task dedup: {dedup_reason}")
            continue
        validation["accepted"] += 1
        dedup_registry.append({"text": item["text"], "mac_constraint_uid": constraint_uid})
        non_anchor.append(
            {
                "local_id": f"t{index}",
                "text": item["text"],
                "is_anchor": False,
                "dependency": copy.deepcopy(dep),
                "compiled_graph": copy.deepcopy(compiled.get("graph")),
                "executable": executable,
                "validation": "accepted_builder_graph_changed",
            }
        )

    anchor_item = {
        "local_id": "anchor",
        "text": anchor_raw["text"] or anchor_text,
        "is_anchor": True,
        "dependency": copy.deepcopy(anchor_dep),
        "compiled_graph": copy.deepcopy(anchor_compiled.get("graph")),
        "executable": copy.deepcopy(anchor_executable),
        "validation": "anchor",
    }

    if job.noise_target == 0:
        ordered = [anchor_item]
    elif len(non_anchor) > job.noise_target:
        warnings.append(
            f"truncated noisy items from {len(non_anchor)} to noise_target={job.noise_target}"
        )
        ordered = non_anchor[: job.noise_target] + [anchor_item]
    else:
        if len(non_anchor) < job.noise_target:
            warnings.append(
                f"only {len(non_anchor)} noisy item(s) accepted; target was {job.noise_target}"
            )
        ordered = non_anchor + [anchor_item]

    for index, item in enumerate(ordered, start=1):
        item["temporal_order"] = index
        item["is_anchor"] = index == len(ordered)
        if item["is_anchor"]:
            item["local_id"] = "anchor"

    return ordered, warnings, validation


def dry_run_temporal_sequence(
    job: AnchorJob,
    *,
    anchor_executable: dict[str, Any] | None = None,
) -> dict[str, Any]:
    anchor_text = str(job.anchor.get("text") or "Follow the selected SOP constraint.")
    action = str(job.anchor.get("action") or "the action")
    constraint_id = str((job.anchor.get("metadata") or {}).get("constraint_id") or "constraint")
    anchor_executable = anchor_executable or build_anchor_executable(job.anchor)
    anchor_dep = anchor_dependency(job.anchor)
    target_action = str(job.anchor.get("action") or "")
    anchor_compiled = (
        compile_dependency_graph(task=job.task, target_action=target_action, dependency=anchor_dep)
        if anchor_dep is not None
        else {"graph": None, "process": anchor_executable.get("process")}
    )
    anchor_graph_sig = graph_signature(anchor_compiled.get("graph"))

    noisy_templates = [
        (
            "t1",
            f"Earlier SOP draft for {action}: use a longer verification procedure before enforcing "
            f"the same {constraint_id} requirement.",
        ),
        (
            "t2",
            f"Earlier SOP draft for {action}: require an explicit pre-check step that is now folded "
            f"into the final wording of the same requirement.",
        ),
        (
            "t3",
            f"Earlier SOP draft for {action}: collect user inputs in a different order while still "
            f"aiming to satisfy the same {constraint_id} policy.",
        ),
    ]

    sequence: list[dict[str, Any]] = []
    other_deps = [
        entry.get("dependency")
        for entry in other_constraints_on_action(
            job.task,
            current_uid=str(job.anchor.get("mac_constraint_uid") or ""),
            target_action=target_action,
        )
        if entry.get("dependency") is not None
    ]
    candidate_deps: list[Any] = []
    if anchor_dep is not None:
        for other_dep in other_deps:
            candidate_deps.append(["and", [copy.deepcopy(anchor_dep), copy.deepcopy(other_dep)]])
            candidate_deps.append(["or", [copy.deepcopy(anchor_dep), copy.deepcopy(other_dep)]])
        if dependency_kind(anchor_dep) in ("and", "or") and isinstance(anchor_dep[1], list):
            candidate_deps.extend(copy.deepcopy(child) for child in anchor_dep[1])
    variant = 0
    for local_id, text in noisy_templates:
        if len(sequence) >= job.noise_target:
            break
        if not candidate_deps:
            break
        dep = candidate_deps[variant % len(candidate_deps)]
        variant += 1
        try:
            compiled = compile_dependency_graph(
                task=job.task,
                target_action=target_action,
                dependency=dep,
            )
        except Exception:
            continue
        if graph_signature(compiled.get("graph")) == anchor_graph_sig:
            continue
        executable = executable_from_compiled(
            target_action=target_action,
            compiled=compiled,
            anchor_executable=anchor_executable,
            text=text,
        )
        sequence.append(
            {
                "local_id": local_id,
                "text": text,
                "is_anchor": False,
                "dependency": copy.deepcopy(dep),
                "compiled_graph": copy.deepcopy(compiled.get("graph")),
                "executable": executable,
                "validation": "accepted_dry_run_builder",
                "temporal_order": len(sequence) + 1,
            }
        )
    sequence.append(
        {
            "local_id": "anchor",
            "text": anchor_text,
            "is_anchor": True,
            "dependency": copy.deepcopy(anchor_dep),
            "compiled_graph": copy.deepcopy(anchor_compiled.get("graph")),
            "executable": copy.deepcopy(anchor_executable),
            "validation": "anchor",
            "temporal_order": len(sequence) + 1,
        }
    )
    return {"noise_count": job.noise_target, "temporal_sequence": sequence}


def rulebase_temporal_sequence(
    job: AnchorJob,
    *,
    anchor_executable: dict[str, Any],
    allowed_tools: set[str],
    task_existing_noisy: list[dict[str, Any]] | None = None,
    max_attempts: int = DEFAULT_RULEBASE_MAX_ATTEMPTS,
) -> tuple[list[dict[str, Any]], list[str], dict[str, Any]]:
    warnings: list[str] = []
    validation: dict[str, Any] = {
        "accepted": 0,
        "rejected": 0,
        "reject_reasons": [],
        "attempts": 0,
        "sample_attempts": max_attempts,
        "keep_target": job.noise_target,
        "dependency_dedup_rejected": 0,
        "generator": "rulebase",
    }
    anchor_text = str(job.anchor.get("text") or "").strip()
    target_action = str(job.anchor.get("action") or "")
    anchor_uid = str(job.anchor.get("mac_constraint_uid") or "")
    anchor_dep = anchor_dependency(job.anchor)
    if anchor_dep is None:
        raise ValueError("anchor has no metadata.dependency; cannot run rulebase generation")

    known_params = known_constraint_params(job.task)
    try:
        anchor_compiled = compile_dependency_graph(
            task=job.task,
            target_action=target_action,
            dependency=anchor_dep,
        )
    except Exception as exc:  # noqa: BLE001
        raise ValueError(f"anchor dependency failed graph-builder compilation: {exc}") from exc
    anchor_graph_sig = graph_signature(anchor_compiled.get("graph"))

    anchor_item = {
        "local_id": "anchor",
        "text": anchor_text,
        "is_anchor": True,
        "dependency": copy.deepcopy(anchor_dep),
        "compiled_graph": copy.deepcopy(anchor_compiled.get("graph")),
        "executable": copy.deepcopy(anchor_executable),
        "validation": "anchor",
    }

    if job.noise_target == 0:
        anchor_item["temporal_order"] = 1
        return [anchor_item], warnings, validation

    pool = same_action_dependency_pool(
        job.task,
        target_action=target_action,
        current_uid=anchor_uid,
    )
    mutations = enumerate_dependency_mutations(anchor_dep, pool)
    if not mutations:
        warnings.append("no legal dependency mutations available for this anchor")
        anchor_item["temporal_order"] = 1
        return [anchor_item], warnings, validation

    rng = random.Random(job.task_seed)
    rng.shuffle(mutations)

    dedup_registry = [copy.deepcopy(item) for item in (task_existing_noisy or [])]
    accepted: list[dict[str, Any]] = []
    seen_local_signatures: set[str] = set()
    attempts = 0

    for mutation in mutations:
        if len(accepted) >= job.noise_target:
            break
        if attempts >= max_attempts:
            break
        attempts += 1
        validation["attempts"] = attempts

        dep = apply_dependency_mutation(anchor_dep, mutation)
        if dep is None:
            validation["rejected"] += 1
            validation["reject_reasons"].append(
                f"attempt {attempts}: {mutation.label}: mutation produced no dependency"
            )
            continue

        dep_sig = canonical_dependency_signature(dep)
        if dep_sig in seen_local_signatures:
            validation["rejected"] += 1
            validation["dependency_dedup_rejected"] += 1
            validation["reject_reasons"].append(
                f"attempt {attempts}: {mutation.label}: duplicate dependency within anchor"
            )
            continue

        accepted_tree, reason = validate_dependency_tree(dep, known_params=known_params)
        if not accepted_tree:
            validation["rejected"] += 1
            validation["reject_reasons"].append(
                f"attempt {attempts}: {mutation.label}: {reason}"
            )
            continue

        is_duplicate, dedup_reason = dependency_dedup_is_duplicate(dep, dedup_registry)
        if is_duplicate:
            validation["rejected"] += 1
            validation["dependency_dedup_rejected"] += 1
            validation["reject_reasons"].append(
                f"attempt {attempts}: {mutation.label}: task dedup: {dedup_reason}"
            )
            continue

        try:
            compiled = compile_dependency_graph(
                task=job.task,
                target_action=target_action,
                dependency=dep,
            )
        except Exception as exc:  # noqa: BLE001
            validation["rejected"] += 1
            validation["reject_reasons"].append(
                f"attempt {attempts}: {mutation.label}: graph-builder compilation failed: {exc}"
            )
            continue

        compiled_graph_sig = graph_signature(compiled.get("graph"))
        graph_changed = compiled_graph_sig != anchor_graph_sig
        if not graph_changed:
            validation["rejected"] += 1
            validation["reject_reasons"].append(
                f"attempt {attempts}: {mutation.label}: compiled graph equivalent to anchor graph"
            )
            continue

        executable = executable_from_compiled(
            target_action=target_action,
            compiled=compiled,
            anchor_executable=anchor_executable,
            text=structural_placeholder_text(mutation.label, anchor_uid=anchor_uid),
        )
        accepted_exec, exec_reason = validate_noisy_executable(
            anchor_executable,
            executable,
            allowed_tools=allowed_tools,
        )
        if not accepted_exec:
            validation["rejected"] += 1
            validation["reject_reasons"].append(
                f"attempt {attempts}: {mutation.label}: {exec_reason}"
            )
            continue

        validation["accepted"] += 1
        seen_local_signatures.add(dep_sig)
        dedup_registry.append(
            {
                "dependency_signature": dep_sig,
                "mac_constraint_uid": anchor_uid,
            }
        )
        accepted.append(
            {
                "local_id": f"t{len(accepted) + 1}",
                "text": structural_placeholder_text(mutation.label, anchor_uid=anchor_uid),
                "is_anchor": False,
                "dependency": copy.deepcopy(dep),
                "compiled_graph": copy.deepcopy(compiled.get("graph")),
                "executable": executable,
                "mutation": mutation.label,
                "dependency_diff": build_dependency_diff(
                    before=anchor_dep,
                    after=dep,
                    mutation=mutation.label,
                ),
                "graph_changed": True,
                "validation": "accepted_rulebase_builder_graph_changed",
            }
        )

    if len(accepted) < job.noise_target:
        warnings.append(
            f"only {len(accepted)} noisy item(s) accepted for anchor; target was {job.noise_target}"
        )

    ordered = accepted + [anchor_item]
    for index, item in enumerate(ordered, start=1):
        item["temporal_order"] = index
        item["is_anchor"] = index == len(ordered)
        if item["is_anchor"]:
            item["local_id"] = "anchor"

    return ordered, warnings, validation


def rulebase_action_temporal_sequence(
    job: ActionJob,
    *,
    allowed_tools: set[str],
    task_existing_noisy: list[dict[str, Any]] | None = None,
    max_attempts: int = DEFAULT_RULEBASE_MAX_ATTEMPTS,
) -> tuple[list[dict[str, Any]], list[str], dict[str, Any]]:
    warnings: list[str] = []
    validation: dict[str, Any] = {
        "accepted": 0,
        "rejected": 0,
        "reject_reasons": [],
        "attempts": 0,
        "sample_attempts": max_attempts,
        "keep_target": job.noise_target,
        "dependency_dedup_rejected": 0,
        "generator": "rulebase_action",
    }
    target_action = str(job.action or "")
    action_dep = get_action_dependency(job.task, target_action)
    if action_dep is None:
        raise ValueError(f"action {target_action} has no dependency tree; cannot run action-level rulebase")

    known_params = known_constraint_params(job.task)
    try:
        anchor_compiled = compile_dependency_graph(
            task=job.task,
            target_action=target_action,
            dependency=action_dep,
        )
    except Exception as exc:  # noqa: BLE001
        raise ValueError(f"action dependency failed graph-builder compilation: {exc}") from exc
    anchor_graph_sig = graph_signature(anchor_compiled.get("graph"))

    anchor_item = {
        "local_id": "anchor",
        "text": structural_placeholder_text("anchor", anchor_uid=f"action:{target_action}"),
        "is_anchor": True,
        "dependency": copy.deepcopy(action_dep),
        "compiled_graph": copy.deepcopy(anchor_compiled.get("graph")),
        "validation": "anchor",
        "scope": "action",
    }

    if job.noise_target == 0:
        anchor_item["temporal_order"] = 1
        return [anchor_item], warnings, validation

    pool = cross_action_single_pool(job.task, target_action)
    mutations = enumerate_dependency_mutations(action_dep, pool)
    if not mutations:
        warnings.append(
            f"no legal action-level dependency mutations available for action={target_action}"
        )
        anchor_item["temporal_order"] = 1
        return [anchor_item], warnings, validation

    rng = random.Random(job.task_seed)
    rng.shuffle(mutations)

    dedup_registry = [copy.deepcopy(item) for item in (task_existing_noisy or [])]
    accepted: list[dict[str, Any]] = []
    seen_local_signatures: set[str] = set()
    attempts = 0

    for mutation in mutations:
        if len(accepted) >= job.noise_target:
            break
        if attempts >= max_attempts:
            break
        attempts += 1
        validation["attempts"] = attempts

        dep = apply_dependency_mutation(action_dep, mutation)
        if dep is None:
            validation["rejected"] += 1
            validation["reject_reasons"].append(
                f"attempt {attempts}: {mutation.label}: mutation produced no dependency"
            )
            continue

        dep_sig = canonical_dependency_signature(dep)
        if dep_sig in seen_local_signatures:
            validation["rejected"] += 1
            validation["dependency_dedup_rejected"] += 1
            validation["reject_reasons"].append(
                f"attempt {attempts}: {mutation.label}: duplicate dependency within action"
            )
            continue

        accepted_tree, reason = validate_dependency_tree(dep, known_params=known_params)
        if not accepted_tree:
            validation["rejected"] += 1
            validation["reject_reasons"].append(
                f"attempt {attempts}: {mutation.label}: {reason}"
            )
            continue

        is_duplicate, dedup_reason = dependency_dedup_is_duplicate(dep, dedup_registry)
        if is_duplicate:
            validation["rejected"] += 1
            validation["dependency_dedup_rejected"] += 1
            validation["reject_reasons"].append(
                f"attempt {attempts}: {mutation.label}: task dedup: {dedup_reason}"
            )
            continue

        try:
            compiled = compile_dependency_graph(
                task=job.task,
                target_action=target_action,
                dependency=dep,
            )
        except Exception as exc:  # noqa: BLE001
            validation["rejected"] += 1
            validation["reject_reasons"].append(
                f"attempt {attempts}: {mutation.label}: graph-builder compilation failed: {exc}"
            )
            continue

        compiled_graph_sig = graph_signature(compiled.get("graph"))
        if compiled_graph_sig == anchor_graph_sig:
            validation["rejected"] += 1
            validation["reject_reasons"].append(
                f"attempt {attempts}: {mutation.label}: compiled graph equivalent to anchor graph"
            )
            continue

        validation["accepted"] += 1
        seen_local_signatures.add(dep_sig)
        dedup_registry.append(
            {
                "dependency_signature": dep_sig,
                "mac_constraint_uid": f"action:{target_action}",
            }
        )
        accepted.append(
            {
                "local_id": f"t{len(accepted) + 1}",
                "text": structural_placeholder_text(
                    mutation.label,
                    anchor_uid=f"action:{target_action}",
                ),
                "is_anchor": False,
                "dependency": copy.deepcopy(dep),
                "compiled_graph": copy.deepcopy(compiled.get("graph")),
                "mutation": mutation.label,
                "dependency_diff": build_dependency_diff(
                    before=action_dep,
                    after=dep,
                    mutation=mutation.label,
                ),
                "graph_changed": True,
                "validation": "accepted_rulebase_action_graph_changed",
                "scope": "action",
            }
        )

    if len(accepted) < job.noise_target:
        warnings.append(
            f"only {len(accepted)} noisy item(s) accepted for action={target_action}; "
            f"target was {job.noise_target}"
        )

    ordered = accepted + [anchor_item]
    for index, item in enumerate(ordered, start=1):
        item["temporal_order"] = index
        item["is_anchor"] = index == len(ordered)
        if item["is_anchor"]:
            item["local_id"] = "anchor"

    return ordered, warnings, validation


def rulebase_action_temporal_sequence_sequential(
    job: ActionJob,
    *,
    task_existing_noisy: list[dict[str, Any]] | None = None,
    max_attempts: int = DEFAULT_RULEBASE_MAX_ATTEMPTS,
) -> tuple[list[dict[str, Any]], list[str], dict[str, Any]]:
    """Build a sequential noise chain g0=anchor, g1=mut(g0), g2=mut(g1), ..."""
    warnings: list[str] = []
    validation: dict[str, Any] = {
        "accepted": 0,
        "rejected": 0,
        "reject_reasons": [],
        "attempts": 0,
        "sample_attempts": max_attempts,
        "keep_target": job.noise_target,
        "dependency_dedup_rejected": 0,
        "generator": "rulebase_action_sequential",
    }
    target_action = str(job.action or "")
    action_dep = get_action_dependency(job.task, target_action)
    if action_dep is None:
        raise ValueError(f"action {target_action} has no dependency tree; cannot run sequential rulebase")

    known_params = known_constraint_params(job.task)
    try:
        anchor_compiled = compile_dependency_graph(
            task=job.task,
            target_action=target_action,
            dependency=action_dep,
        )
    except Exception as exc:  # noqa: BLE001
        raise ValueError(f"action dependency failed graph-builder compilation: {exc}") from exc
    anchor_graph_sig = graph_signature(anchor_compiled.get("graph"))

    anchor_item = {
        "local_id": "anchor",
        "text": structural_placeholder_text("anchor", anchor_uid=f"action:{target_action}"),
        "is_anchor": True,
        "dependency": copy.deepcopy(action_dep),
        "compiled_graph": copy.deepcopy(anchor_compiled.get("graph")),
        "validation": "anchor",
        "scope": "action",
    }

    if job.noise_target == 0:
        anchor_item["temporal_order"] = 1
        return [anchor_item], warnings, validation

    pool = cross_action_single_pool(job.task, target_action)
    dedup_registry = [copy.deepcopy(item) for item in (task_existing_noisy or [])]
    accepted: list[dict[str, Any]] = []
    seen_local_signatures: set[str] = set()
    attempts = 0

    current_dep = copy.deepcopy(action_dep)
    previous_graph_sig = anchor_graph_sig

    for _step in range(job.noise_target):
        if attempts >= max_attempts:
            break
        mutations = enumerate_dependency_mutations(current_dep, pool)
        if not mutations:
            warnings.append(
                f"no legal sequential mutations at step {len(accepted) + 1} "
                f"for action={target_action}"
            )
            break
        rng = random.Random(job.task_seed + len(accepted) * 9973)
        rng.shuffle(mutations)
        step_accepted = False

        for mutation in mutations:
            if attempts >= max_attempts:
                break
            attempts += 1
            validation["attempts"] = attempts

            before_dep = copy.deepcopy(current_dep)
            dep = apply_dependency_mutation(current_dep, mutation)
            if dep is None:
                validation["rejected"] += 1
                validation["reject_reasons"].append(
                    f"attempt {attempts}: {mutation.label}: mutation produced no dependency"
                )
                continue

            dep_sig = canonical_dependency_signature(dep)
            if dep_sig in seen_local_signatures:
                validation["rejected"] += 1
                validation["dependency_dedup_rejected"] += 1
                validation["reject_reasons"].append(
                    f"attempt {attempts}: {mutation.label}: duplicate dependency within action chain"
                )
                continue

            accepted_tree, reason = validate_dependency_tree(dep, known_params=known_params)
            if not accepted_tree:
                validation["rejected"] += 1
                validation["reject_reasons"].append(
                    f"attempt {attempts}: {mutation.label}: {reason}"
                )
                continue

            is_duplicate, dedup_reason = dependency_dedup_is_duplicate(dep, dedup_registry)
            if is_duplicate:
                validation["rejected"] += 1
                validation["dependency_dedup_rejected"] += 1
                validation["reject_reasons"].append(
                    f"attempt {attempts}: {mutation.label}: task dedup: {dedup_reason}"
                )
                continue

            try:
                compiled = compile_dependency_graph(
                    task=job.task,
                    target_action=target_action,
                    dependency=dep,
                )
            except Exception as exc:  # noqa: BLE001
                validation["rejected"] += 1
                validation["reject_reasons"].append(
                    f"attempt {attempts}: {mutation.label}: graph-builder compilation failed: {exc}"
                )
                continue

            compiled_graph_sig = graph_signature(compiled.get("graph"))
            if compiled_graph_sig == previous_graph_sig:
                validation["rejected"] += 1
                validation["reject_reasons"].append(
                    f"attempt {attempts}: {mutation.label}: compiled graph unchanged from previous step"
                )
                continue

            validation["accepted"] += 1
            seen_local_signatures.add(dep_sig)
            dedup_registry.append(
                {
                    "dependency_signature": dep_sig,
                    "mac_constraint_uid": f"action:{target_action}",
                }
            )
            accepted.append(
                {
                    "local_id": f"t{len(accepted) + 1}",
                    "text": structural_placeholder_text(
                        mutation.label,
                        anchor_uid=f"action:{target_action}",
                    ),
                    "is_anchor": False,
                    "dependency": copy.deepcopy(dep),
                    "compiled_graph": copy.deepcopy(compiled.get("graph")),
                    "mutation": mutation.label,
                    "dependency_diff": build_dependency_diff(
                        before=before_dep,
                        after=dep,
                        mutation=mutation.label,
                    ),
                    "dependency_diff_from_anchor": build_dependency_diff(
                        before=action_dep,
                        after=dep,
                        mutation=mutation.label,
                    ),
                    "graph_changed": True,
                    "validation": "accepted_rulebase_action_sequential",
                    "scope": "action",
                    "sequential_step": len(accepted),
                }
            )
            current_dep = copy.deepcopy(dep)
            previous_graph_sig = compiled_graph_sig
            step_accepted = True
            break

        if not step_accepted:
            warnings.append(
                f"sequential chain stopped at step {len(accepted) + 1}/{job.noise_target} "
                f"for action={target_action}"
            )
            break

    if len(accepted) < job.noise_target:
        warnings.append(
            f"only {len(accepted)} sequential noisy item(s) accepted for action={target_action}; "
            f"target was {job.noise_target}"
        )

    ordered = accepted + [anchor_item]
    for index, item in enumerate(ordered, start=1):
        item["temporal_order"] = index
        item["is_anchor"] = index == len(ordered)
        if item["is_anchor"]:
            item["local_id"] = "anchor"

    return ordered, warnings, validation


def sequence_for_anchor_from_action(
    sequence: list[dict[str, Any]],
    *,
    anchor: dict[str, Any],
    action_compiled_graph: Any,
) -> list[dict[str, Any]]:
    anchor_text = str(anchor.get("text") or "").strip()
    anchor_dep = anchor_dependency(anchor)
    adapted: list[dict[str, Any]] = []
    for item in sequence:
        entry = copy.deepcopy(item)
        if entry.get("is_anchor"):
            entry["text"] = anchor_text
            entry["dependency"] = copy.deepcopy(anchor_dep)
            entry["compiled_graph"] = copy.deepcopy(action_compiled_graph)
            entry["scope"] = "anchor"
        adapted.append(entry)
    return adapted


def generation_artifact(
    *,
    job: AnchorJob,
    sequence: list[dict[str, Any]],
    warnings: list[str],
    prompt: str | None,
    model: str | None,
    dry_run: bool,
    anchor_executable: dict[str, Any],
    involved_tools: list[str],
    validation: dict[str, Any] | None = None,
    rulebase: bool = False,
    action_level: bool = False,
    action: str | None = None,
    action_dependency: Any | None = None,
    action_noise_generated: int | None = None,
    action_noise_target: int | None = None,
) -> dict[str, Any]:
    anchor_uid = str(job.anchor.get("mac_constraint_uid") or "")
    task_uid = str(job.task.get("mac_task_uid") or "")
    public_sequence: list[dict[str, Any]] = []
    for item in sequence:
        public_item = {
            key: copy.deepcopy(value)
            for key, value in item.items()
            if key != "executable"
        }
        public_sequence.append(public_item)
    artifact = {
        "mac_task_uid": task_uid,
        "mac_constraint_uid": anchor_uid,
        "anchor_kind": job.anchor.get("anchor_kind"),
        "anchor_action": job.anchor.get("action"),
        "anchor_text": job.anchor.get("text"),
        "anchor_dependency": anchor_dependency(job.anchor),
        "anchor_compiled_graph": next(
            (
                copy.deepcopy(item.get("compiled_graph"))
                for item in sequence
                if item.get("is_anchor") and "compiled_graph" in item
            ),
            None,
        ),
        "involved_tools": involved_tools,
        "noise_target": job.noise_target,
        "noise_effective": sum(1 for item in public_sequence if not item.get("is_anchor")),
        "sequence_length": len(public_sequence),
        "temporal_sequence": public_sequence,
        "generation": {
            "model": model,
            "dry_run": dry_run,
            "rulebase": rulebase,
            "prompt_hash": hashlib.sha256((prompt or "").encode("utf-8")).hexdigest()
            if prompt is not None
            else None,
            "warnings": warnings,
            "validation": validation or {},
        },
    }
    if action_level:
        artifact["action_level"] = True
        artifact["action"] = action or job.anchor.get("action")
        artifact["action_dependency"] = copy.deepcopy(action_dependency)
        artifact["action_noise_target"] = (
            job.noise_target if action_noise_target is None else action_noise_target
        )
        artifact["action_noise_generated"] = (
            action_noise_generated
            if action_noise_generated is not None
            else sum(1 for item in public_sequence if not item.get("is_anchor"))
        )
        artifact["generation"]["action_level"] = True
    return artifact


def accepted_noisy_count(sequence: list[dict[str, Any]]) -> int:
    return sum(
        1
        for item in sequence
        if not item.get("is_anchor")
        and str(item.get("validation") or "").startswith("accepted")
    )


def process_anchor_job(
    job: AnchorJob,
    args: argparse.Namespace,
    *,
    task_existing_noisy: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    anchor_executable = build_anchor_executable(job.anchor)
    involved_tools = sorted(allowed_tools_for_job(job))
    allowed_tools = allowed_tools_for_job(job)

    print(
        f"processing anchor {job.ordinal}/{job.total} "
        f"task={job.task.get('mac_task_uid')} "
        f"constraint={job.anchor.get('mac_constraint_uid')} "
        f"noise_target={job.noise_target}",
        flush=True,
    )

    if job.noise_target == 0:
        sequence, warnings, validation = rulebase_temporal_sequence(
            job,
            anchor_executable=anchor_executable,
            allowed_tools=allowed_tools,
            task_existing_noisy=task_existing_noisy,
            max_attempts=int(getattr(args, "mutation_max_attempts", DEFAULT_RULEBASE_MAX_ATTEMPTS)),
        )
        return generation_artifact(
            job=job,
            sequence=sequence,
            warnings=warnings + ["noise_target=0; anchor-only sequence"],
            prompt=None,
            model=None,
            dry_run=False,
            anchor_executable=anchor_executable,
            involved_tools=involved_tools,
            validation=validation,
            rulebase=True,
        )

    if args.dry_run:
        sequence = dry_run_temporal_sequence(job, anchor_executable=anchor_executable)["temporal_sequence"]
        return generation_artifact(
            job=job,
            sequence=sequence,
            warnings=["dry-run: legacy template sequence, no LLM call"],
            prompt=None,
            model=None,
            dry_run=True,
            anchor_executable=anchor_executable,
            involved_tools=involved_tools,
        )

    if getattr(args, "llm", False):
        user_prompt = build_user_prompt(job)
        warnings: list[str] = []
        validation_total: dict[str, Any] = {
            "accepted": 0,
            "rejected": 0,
            "reject_reasons": [],
            "attempts": 0,
            "task_dedup_rejected": 0,
            "generator": "llm",
        }
        sequence: list[dict[str, Any]] = []
        max_attempts = max(1, int(args.validation_retries) + 1)

        for attempt in range(1, max_attempts + 1):
            validation_total["attempts"] = attempt
            try:
                response_text = call_llm(
                    model=args.model,
                    base_url=args.base_url,
                    api_key=args.api_key,
                    user_prompt=user_prompt,
                    max_tokens=args.max_tokens,
                    timeout=args.timeout,
                    retries=args.retries,
                    sleep=args.sleep,
                )
                payload = parse_llm_json(response_text)
                sequence, normalization_warnings, validation = normalize_temporal_sequence(
                    payload,
                    job=job,
                    anchor_executable=anchor_executable,
                    allowed_tools=allowed_tools,
                    task_existing_noisy=task_existing_noisy,
                    noise_dedup_similarity=float(
                        getattr(args, "noise_dedup_similarity", DEFAULT_NOISE_DEDUP_SIMILARITY)
                    ),
                )
                warnings.extend(normalization_warnings)
                validation_total["accepted"] += int(validation.get("accepted", 0))
                validation_total["rejected"] += int(validation.get("rejected", 0))
                validation_total["task_dedup_rejected"] += int(validation.get("task_dedup_rejected", 0))
                validation_total["reject_reasons"].extend(validation.get("reject_reasons") or [])
            except Exception as exc:  # noqa: BLE001 - preserve placeholder artifact.
                warnings.append(f"attempt {attempt}: LLM/normalize failed: {exc}")
                sequence = []
                continue

            if accepted_noisy_count(sequence) >= job.noise_target:
                break
            if attempt < max_attempts:
                warnings.append(
                    f"attempt {attempt}: only {accepted_noisy_count(sequence)} noisy item(s) accepted; retrying"
                )

        if not sequence:
            warnings.append("validation retries exhausted; no noisy items accepted")
        elif accepted_noisy_count(sequence) < job.noise_target:
            warnings.append(
                f"validation retries exhausted; only {accepted_noisy_count(sequence)} "
                f"noisy item(s) accepted; target was {job.noise_target}"
            )

        return generation_artifact(
            job=job,
            sequence=sequence,
            warnings=warnings,
            prompt=user_prompt,
            model=args.model,
            dry_run=False,
            anchor_executable=anchor_executable,
            involved_tools=involved_tools,
            validation=validation_total,
            rulebase=False,
        )

    sequence, warnings, validation = rulebase_temporal_sequence(
        job,
        anchor_executable=anchor_executable,
        allowed_tools=allowed_tools,
        task_existing_noisy=task_existing_noisy,
        max_attempts=int(getattr(args, "mutation_max_attempts", DEFAULT_RULEBASE_MAX_ATTEMPTS)),
    )
    return generation_artifact(
        job=job,
        sequence=sequence,
        warnings=warnings,
        prompt=None,
        model=None,
        dry_run=False,
        anchor_executable=anchor_executable,
        involved_tools=involved_tools,
        validation=validation,
        rulebase=True,
    )


def build_action_skip_artifacts(
    job: ActionJob,
    *,
    reason: str,
    action_dep: Any | None = None,
    involved_tools: list[str] | None = None,
) -> list[dict[str, Any]]:
    target_action = str(job.action or "")
    warnings = [f"skipped action-level noise for action={target_action}: {reason}"]
    validation: dict[str, Any] = {
        "accepted": 0,
        "rejected": 0,
        "reject_reasons": [reason],
        "attempts": 0,
        "sample_attempts": 0,
        "keep_target": job.noise_target,
        "dependency_dedup_rejected": 0,
        "generator": "rulebase_action",
        "skipped": True,
    }
    tools = involved_tools or []
    artifacts: list[dict[str, Any]] = []
    for anchor in job.anchors:
        anchor_job = AnchorJob(
            ordinal=job.ordinal,
            total=job.total,
            task=job.task,
            task_index=job.task_index,
            anchor=anchor,
            anchor_index=0,
            noise_target=job.noise_target,
            task_seed=job.task_seed,
        )
        anchor_executable = build_anchor_executable(anchor)
        anchor_dep = anchor_dependency(anchor)
        anchor_text = str(anchor.get("text") or "").strip()
        anchor_compiled_graph = None
        if anchor_dep is not None:
            try:
                anchor_compiled_graph = compile_dependency_graph(
                    task=job.task,
                    target_action=target_action,
                    dependency=anchor_dep,
                ).get("graph")
            except Exception:  # noqa: BLE001
                anchor_compiled_graph = None
        sequence = [
            {
                "local_id": "anchor",
                "text": anchor_text,
                "is_anchor": True,
                "dependency": copy.deepcopy(anchor_dep),
                "compiled_graph": copy.deepcopy(anchor_compiled_graph),
                "executable": copy.deepcopy(anchor_executable),
                "validation": "anchor",
                "scope": "anchor",
                "temporal_order": 1,
            }
        ]
        artifacts.append(
            generation_artifact(
                job=anchor_job,
                sequence=sequence,
                warnings=warnings,
                prompt=None,
                model=None,
                dry_run=False,
                anchor_executable=anchor_executable,
                involved_tools=tools,
                validation=validation,
                rulebase=True,
                action_level=True,
                action=target_action,
                action_dependency=action_dep,
                action_noise_generated=0,
                action_noise_target=job.noise_target,
            )
        )
    return artifacts


def process_action_job(
    job: ActionJob,
    args: argparse.Namespace,
    *,
    task_existing_noisy: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    target_action = str(job.action or "")
    allowed_tools: set[str] = set()
    involved_tools: set[str] = set()
    for anchor in job.anchors:
        allowed_tools |= allowed_tools_for_job(
            AnchorJob(
                ordinal=job.ordinal,
                total=job.total,
                task=job.task,
                task_index=job.task_index,
                anchor=anchor,
                anchor_index=0,
                noise_target=job.noise_target,
                task_seed=job.task_seed,
            )
        )
        involved_tools |= allowed_tools

    print(
        f"processing action {job.ordinal}/{job.total} "
        f"task={job.task.get('mac_task_uid')} "
        f"action={target_action} "
        f"anchors={len(job.anchors)} "
        f"noise_target={job.noise_target}",
        flush=True,
    )

    action_dep = get_action_dependency(job.task, target_action)
    action_compiled_graph = None
    if action_dep is not None:
        try:
            action_compiled_graph = compile_dependency_graph(
                task=job.task,
                target_action=target_action,
                dependency=action_dep,
            ).get("graph")
        except Exception:  # noqa: BLE001
            action_compiled_graph = None

    if job.noise_target == 0 or args.dry_run or getattr(args, "llm", False):
        artifacts: list[dict[str, Any]] = []
        for anchor in job.anchors:
            anchor_job = AnchorJob(
                ordinal=job.ordinal,
                total=job.total,
                task=job.task,
                task_index=job.task_index,
                anchor=anchor,
                anchor_index=0,
                noise_target=job.noise_target,
                task_seed=job.task_seed,
            )
            artifacts.append(process_anchor_job(anchor_job, args, task_existing_noisy=task_existing_noisy))
        return artifacts

    try:
        sequence, warnings, validation = rulebase_action_temporal_sequence(
            job,
            allowed_tools=allowed_tools,
            task_existing_noisy=task_existing_noisy,
            max_attempts=int(getattr(args, "mutation_max_attempts", DEFAULT_RULEBASE_MAX_ATTEMPTS)),
        )
    except Exception as exc:  # noqa: BLE001
        return build_action_skip_artifacts(
            job,
            reason=str(exc),
            action_dep=action_dep,
            involved_tools=sorted(involved_tools),
        )

    action_noise_generated = sum(1 for item in sequence if not item.get("is_anchor"))

    artifacts = []
    for anchor in job.anchors:
        anchor_job = AnchorJob(
            ordinal=job.ordinal,
            total=job.total,
            task=job.task,
            task_index=job.task_index,
            anchor=anchor,
            anchor_index=0,
            noise_target=job.noise_target,
            task_seed=job.task_seed,
        )
        anchor_executable = build_anchor_executable(anchor)
        anchor_sequence = sequence_for_anchor_from_action(
            sequence,
            anchor=anchor,
            action_compiled_graph=action_compiled_graph,
        )
        artifacts.append(
            generation_artifact(
                job=anchor_job,
                sequence=anchor_sequence,
                warnings=warnings,
                prompt=None,
                model=None,
                dry_run=False,
                anchor_executable=anchor_executable,
                involved_tools=sorted(involved_tools),
                validation=validation,
                rulebase=True,
                action_level=True,
                action=target_action,
                action_dependency=action_dep,
                action_noise_generated=action_noise_generated,
                action_noise_target=job.noise_target,
            )
        )
    return artifacts


def iter_action_jobs(
    tasks: list[dict[str, Any]],
    *,
    seed: int,
    noise_min: int,
    noise_max: int,
    max_anchors: int | None,
    only_uids: set[str],
) -> list[ActionJob]:
    master_rng = random.Random(seed)
    grouped: dict[tuple[int, str], list[dict[str, Any]]] = defaultdict(list)
    task_by_index: dict[int, dict[str, Any]] = {}

    for task_index, task in enumerate(tasks):
        task_by_index[task_index] = task
        for anchor in task.get("anchors") or []:
            if not isinstance(anchor, dict):
                continue
            anchor_uid = str(anchor.get("mac_constraint_uid") or "").strip()
            if only_uids and anchor_uid not in only_uids:
                continue
            action = str(anchor.get("action") or "")
            if not action:
                continue
            grouped[(task_index, action)].append(anchor)

    raw_jobs: list[ActionJob] = []
    for (task_index, action), anchors in sorted(grouped.items(), key=lambda item: (item[0][0], item[0][1])):
        task = task_by_index[task_index]
        action_dep = get_action_dependency(task, action)
        if action_dep is None:
            continue
        task_seed = master_rng.randint(0, 2**31 - 1)
        task_rng = random.Random(task_seed)
        noise_target = complexity_aware_action_noise_target(
            action_dep,
            task_rng,
            noise_min=max(noise_min, 1) if noise_max > 0 else 0,
            noise_max=noise_max,
        )
        raw_jobs.append(
            ActionJob(
                ordinal=0,
                total=0,
                task=task,
                task_index=task_index,
                action=action,
                anchors=tuple(anchors),
                noise_target=noise_target,
                task_seed=task_seed,
            )
        )
        if max_anchors is not None and sum(len(job.anchors) for job in raw_jobs) >= max_anchors:
            break

    if max_anchors is not None:
        trimmed: list[ActionJob] = []
        anchor_count = 0
        for job in raw_jobs:
            if anchor_count >= max_anchors:
                break
            remaining = max_anchors - anchor_count
            if len(job.anchors) <= remaining:
                trimmed.append(job)
                anchor_count += len(job.anchors)
            else:
                trimmed.append(
                    ActionJob(
                        ordinal=0,
                        total=0,
                        task=job.task,
                        task_index=job.task_index,
                        action=job.action,
                        anchors=job.anchors[:remaining],
                        noise_target=job.noise_target,
                        task_seed=job.task_seed,
                    )
                )
                anchor_count += remaining
        raw_jobs = trimmed

    total = len(raw_jobs)
    return [
        ActionJob(
            ordinal=index,
            total=total,
            task=job.task,
            task_index=job.task_index,
            action=job.action,
            anchors=job.anchors,
            noise_target=job.noise_target,
            task_seed=job.task_seed,
        )
        for index, job in enumerate(raw_jobs, start=1)
    ]


def iter_anchor_jobs(
    tasks: list[dict[str, Any]],
    *,
    seed: int,
    noise_min: int,
    noise_max: int,
    noise_mean: float,
    noise_std: float,
    max_anchors: int | None,
    only_uids: set[str],
) -> list[AnchorJob]:
    master_rng = random.Random(seed)
    jobs: list[AnchorJob] = []
    for task_index, task in enumerate(tasks):
        anchors = task.get("anchors") or []
        if not isinstance(anchors, list):
            continue
        for anchor_index, anchor in enumerate(anchors):
            if not isinstance(anchor, dict):
                continue
            anchor_uid = str(anchor.get("mac_constraint_uid") or "").strip()
            if only_uids and anchor_uid not in only_uids:
                continue
            task_seed = master_rng.randint(0, 2**31 - 1)
            task_rng = random.Random(task_seed)
            noise_target = complexity_aware_noise_target(
                anchor,
                task_rng,
                noise_min=max(noise_min, 1) if noise_max > 0 else 0,
                noise_max=noise_max,
            )
            jobs.append(
                AnchorJob(
                    ordinal=0,
                    total=0,
                    task=task,
                    task_index=task_index,
                    anchor=anchor,
                    anchor_index=anchor_index,
                    noise_target=noise_target,
                    task_seed=task_seed,
                )
            )
            if max_anchors is not None and len(jobs) >= max_anchors:
                break
        if max_anchors is not None and len(jobs) >= max_anchors:
            break

    total = len(jobs)
    return [
        AnchorJob(
            ordinal=index,
            total=total,
            task=job.task,
            task_index=job.task_index,
            anchor=job.anchor,
            anchor_index=job.anchor_index,
            noise_target=job.noise_target,
            task_seed=job.task_seed,
        )
        for index, job in enumerate(jobs, start=1)
    ]


def artifacts_by_constraint_uid(artifacts: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    by_uid: dict[str, dict[str, Any]] = {}
    for artifact in artifacts:
        uid = str(artifact.get("mac_constraint_uid") or "").strip()
        if uid:
            by_uid[uid] = artifact
    return by_uid


def task_description(task: dict[str, Any]) -> str:
    original = task.get("original_sopbench") or {}
    return str(task.get("mac_task_summary") or original.get("user_instruction") or "").strip()


def temporal_noise_entries(sequence: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ordered = sorted(sequence, key=lambda item: int(item.get("temporal_order") or 0))
    entries: list[dict[str, Any]] = []
    for item in ordered:
        if item.get("is_anchor"):
            continue
        text = str(item.get("text") or "").strip()
        dependency = item.get("dependency")
        if not text and dependency is None:
            continue
        entry: dict[str, Any] = {}
        if text:
            entry["text"] = text
        if dependency is not None:
            entry["dependency"] = copy.deepcopy(dependency)
        if "compiled_graph" in item:
            entry["compiled_graph"] = copy.deepcopy(item.get("compiled_graph"))
        if item.get("mutation"):
            entry["mutation"] = item.get("mutation")
        if item.get("scope"):
            entry["scope"] = item.get("scope")
        if item.get("dependency_diff"):
            entry["dependency_diff"] = copy.deepcopy(item.get("dependency_diff"))
        if "graph_changed" in item:
            entry["graph_changed"] = bool(item.get("graph_changed"))
        validation = item.get("validation")
        if validation:
            entry["validation"] = validation
        entries.append(entry)
    return entries


def slim_constraint_from_artifact(artifact: dict[str, Any]) -> dict[str, Any]:
    sequence = artifact.get("temporal_sequence") or []
    involved_tools = artifact.get("involved_tools")
    if not isinstance(involved_tools, list):
        involved_tools = involved_tools_for_anchor(
            {
                "action": artifact.get("anchor_action"),
                "metadata": {"constraint_id": ""},
            }
        )
    slim: dict[str, Any] = {
        "mac_constraint_uid": artifact.get("mac_constraint_uid"),
        "text": artifact.get("anchor_text") or next(
            (item.get("text") for item in sequence if item.get("is_anchor")),
            "",
        ),
        "anchor_dependency": copy.deepcopy(artifact.get("anchor_dependency")),
        "anchor_compiled_graph": copy.deepcopy(artifact.get("anchor_compiled_graph")),
        "involved_tools": list(involved_tools),
        "temporal_noise": temporal_noise_entries(
            sequence if isinstance(sequence, list) else []
        ),
    }
    if artifact.get("action_level"):
        slim["action_level"] = True
        slim["action"] = artifact.get("action") or artifact.get("anchor_action")
        slim["action_dependency"] = copy.deepcopy(artifact.get("action_dependency"))
        if "action_noise_target" in artifact:
            slim["action_noise_target"] = artifact.get("action_noise_target")
        if "action_noise_generated" in artifact:
            slim["action_noise_generated"] = artifact.get("action_noise_generated")
    return slim


def normalize_temporal_noise_entry(entry: Any) -> dict[str, Any] | None:
    if isinstance(entry, str):
        text = entry.strip()
        if not text:
            return None
        return {"text": text}
    if isinstance(entry, dict):
        text = str(entry.get("text") or "").strip()
        dependency = entry.get("dependency")
        if not text and dependency is None:
            return None
        normalized: dict[str, Any] = {}
        if text:
            normalized["text"] = text
        if dependency is not None:
            normalized["dependency"] = copy.deepcopy(dependency)
        if "compiled_graph" in entry:
            normalized["compiled_graph"] = copy.deepcopy(entry.get("compiled_graph"))
        if entry.get("mutation"):
            normalized["mutation"] = entry.get("mutation")
        if entry.get("dependency_diff"):
            normalized["dependency_diff"] = copy.deepcopy(entry.get("dependency_diff"))
        if "graph_changed" in entry:
            normalized["graph_changed"] = bool(entry.get("graph_changed"))
        validation = entry.get("validation")
        if validation:
            normalized["validation"] = validation
        return normalized
    return None


def slim_constraint_from_entry(entry: dict[str, Any]) -> dict[str, Any]:
    if "temporal_noise" in entry or "anchor_dependency" in entry or "anchor_compiled_graph" in entry:
        temporal_noise: list[dict[str, Any]] = []
        for raw in entry.get("temporal_noise") or []:
            normalized = normalize_temporal_noise_entry(raw)
            if normalized:
                temporal_noise.append(normalized)
        slim: dict[str, Any] = {
            "mac_constraint_uid": entry.get("mac_constraint_uid"),
            "text": entry.get("text"),
            "temporal_noise": temporal_noise,
        }
        if "anchor_dependency" in entry:
            slim["anchor_dependency"] = copy.deepcopy(entry.get("anchor_dependency"))
        if "anchor_compiled_graph" in entry:
            slim["anchor_compiled_graph"] = copy.deepcopy(entry.get("anchor_compiled_graph"))
        if "action_dependency" in entry:
            slim["action_dependency"] = copy.deepcopy(entry.get("action_dependency"))
        if entry.get("action_level"):
            slim["action_level"] = True
        if entry.get("action"):
            slim["action"] = entry.get("action")
        if "action_noise_target" in entry:
            slim["action_noise_target"] = entry.get("action_noise_target")
        if "action_noise_generated" in entry:
            slim["action_noise_generated"] = entry.get("action_noise_generated")
        involved_tools = entry.get("involved_tools")
        if isinstance(involved_tools, list):
            slim["involved_tools"] = list(involved_tools)
        return slim
    return {
        "mac_constraint_uid": entry.get("mac_constraint_uid"),
        "text": entry.get("text"),
        "temporal_noise": [],
    }


def artifact_from_slim_constraint(entry: dict[str, Any], *, task_uid: str) -> dict[str, Any]:
    slim = slim_constraint_from_entry(entry)
    uid = str(slim.get("mac_constraint_uid") or "")
    anchor_text = str(slim.get("text") or "")
    noisy_entries = [
        item
        for item in (
            normalize_temporal_noise_entry(raw)
            for raw in (slim.get("temporal_noise") or [])
        )
        if item
    ]
    sequence: list[dict[str, Any]] = []
    for index, noisy in enumerate(noisy_entries, start=1):
        sequence.append(
            {
                "local_id": f"t{index}",
                "text": noisy.get("text") or "",
                "is_anchor": False,
                "dependency": copy.deepcopy(noisy.get("dependency")),
                "compiled_graph": copy.deepcopy(noisy.get("compiled_graph")),
                "mutation": noisy.get("mutation"),
                "dependency_diff": copy.deepcopy(noisy.get("dependency_diff")),
                "graph_changed": noisy.get("graph_changed"),
                "validation": noisy.get("validation") or "accepted",
                "temporal_order": index,
            }
        )
    sequence.append(
        {
            "local_id": "anchor",
            "text": anchor_text,
            "is_anchor": True,
            "dependency": copy.deepcopy(slim.get("anchor_dependency")),
            "compiled_graph": copy.deepcopy(slim.get("anchor_compiled_graph")),
            "validation": "anchor",
            "temporal_order": len(sequence) + 1,
        }
    )
    return {
        "mac_task_uid": task_uid,
        "mac_constraint_uid": uid,
        "anchor_text": anchor_text,
        "anchor_dependency": copy.deepcopy(slim.get("anchor_dependency")),
        "anchor_compiled_graph": copy.deepcopy(slim.get("anchor_compiled_graph")),
        "involved_tools": list(slim.get("involved_tools") or []),
        "noise_target": len(noisy_entries),
        "noise_effective": len(noisy_entries),
        "sequence_length": len(sequence),
        "temporal_sequence": sequence,
    }


def load_step3_tasks(path: Path) -> list[dict[str, Any]]:
    payload = load_json(path)
    if isinstance(payload, list):
        return copy.deepcopy(payload)
    if isinstance(payload, dict) and isinstance(payload.get("tasks"), list):
        return copy.deepcopy(payload["tasks"])
    raise ValueError(f"Expected step-3 task list in {path}")


def existing_artifacts_from_step3_tasks(tasks: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    by_uid: dict[str, dict[str, Any]] = {}
    for task in tasks:
        task_uid = str(task.get("mac_task_uid") or "")
        for entry in task.get("constraints") or []:
            if not isinstance(entry, dict):
                continue
            uid = str(entry.get("mac_constraint_uid") or "").strip()
            if uid:
                by_uid[uid] = artifact_from_slim_constraint(entry, task_uid=task_uid)
    return by_uid


def build_slim_step3_tasks(
    source_tasks: list[dict[str, Any]],
    artifacts_by_uid: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    slim_tasks: list[dict[str, Any]] = []
    for task in source_tasks:
        constraints: list[dict[str, Any]] = []
        action_noise_index: dict[str, dict[str, Any]] = {}
        if isinstance(task.get("constraints"), list) and task.get("domain") and "anchors" not in task:
            anchor_entries = task.get("constraints") or []
        else:
            anchor_entries = task.get("anchors") or []

        for entry in anchor_entries:
            if not isinstance(entry, dict):
                continue
            uid = str(entry.get("mac_constraint_uid") or "").strip()
            if not uid:
                continue
            if uid in artifacts_by_uid:
                slim = slim_constraint_from_artifact(artifacts_by_uid[uid])
            else:
                slim = slim_constraint_from_entry(entry)
            constraints.append(slim)
            if slim.get("action_level") and slim.get("action"):
                action_name = str(slim.get("action") or "")
                if action_name and action_name not in action_noise_index:
                    action_noise_index[action_name] = {
                        "action": action_name,
                        "noise_target": slim.get("action_noise_target"),
                        "noise_generated": slim.get("action_noise_generated"),
                    }

        task_payload: dict[str, Any] = {
            "mac_task_uid": task.get("mac_task_uid"),
            "domain": task.get("domain"),
            "task_description": task_description(task) if "anchors" in task or task.get("mac_task_summary") else task.get("task_description", ""),
            "constraints": constraints,
        }
        if action_noise_index:
            task_payload["action_noise"] = [
                action_noise_index[action_name]
                for action_name in sorted(action_noise_index.keys())
            ]
        slim_tasks.append(task_payload)
    return slim_tasks


def estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)


def print_sample_prompt(
    jobs: list[AnchorJob],
    *,
    constraint_uid: str | None = None,
) -> None:
    if not jobs:
        raise SystemExit("no anchor jobs available for --print-prompt")

    job = jobs[0]
    if constraint_uid:
        matched = next(
            (
                candidate
                for candidate in jobs
                if str(candidate.anchor.get("mac_constraint_uid") or "") == constraint_uid
            ),
            None,
        )
        if matched is None:
            raise SystemExit(f"constraint uid not found in selected jobs: {constraint_uid}")
        job = matched

    system_prompt = build_system_prompt()
    user_prompt = build_user_prompt(job)
    total = system_prompt + user_prompt
    print(
        f"constraint={job.anchor.get('mac_constraint_uid')} "
        f"action={job.anchor.get('action')} "
        f"noise_count={job.noise_target}"
    )
    print(
        f"system_chars={len(system_prompt)} "
        f"user_chars={len(user_prompt)} "
        f"total_chars={len(total)}"
    )
    print(
        f"system_tokens~={estimate_tokens(system_prompt)} "
        f"user_tokens~={estimate_tokens(user_prompt)} "
        f"total_tokens~={estimate_tokens(total)}"
    )
    print("\n=== SYSTEM PROMPT ===\n")
    print(system_prompt)
    print("\n=== USER PROMPT ===\n")
    print(user_prompt)


def warnings_report_from_artifacts(
    artifacts_by_uid: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    entries: list[dict[str, Any]] = []
    for uid in sorted(artifacts_by_uid.keys()):
        artifact = artifacts_by_uid[uid]
        generation = artifact.get("generation")
        if not isinstance(generation, dict):
            continue
        warnings = [str(item) for item in (generation.get("warnings") or []) if str(item).strip()]
        validation = generation.get("validation") if isinstance(generation.get("validation"), dict) else {}
        reject_reasons = [
            str(item) for item in (validation.get("reject_reasons") or []) if str(item).strip()
        ]
        has_validation_issue = bool(reject_reasons) or (
            int(artifact.get("noise_target") or 0) > 0
            and int(artifact.get("noise_effective") or 0) < int(artifact.get("noise_target") or 0)
        )
        if not warnings and not has_validation_issue:
            continue
        entry: dict[str, Any] = {
            "mac_task_uid": artifact.get("mac_task_uid"),
            "mac_constraint_uid": uid,
            "anchor_action": artifact.get("anchor_action"),
            "noise_target": artifact.get("noise_target"),
            "noise_effective": artifact.get("noise_effective"),
            "warnings": warnings,
        }
        if validation:
            entry["validation"] = copy.deepcopy(validation)
        model = generation.get("model")
        if model:
            entry["model"] = model
        if generation.get("dry_run"):
            entry["dry_run"] = True
        entries.append(entry)
    return {"anchors": entries}


def summarize_artifacts(artifacts: list[dict[str, Any]]) -> dict[str, Any]:
    noise_targets = [int(a.get("noise_target", 0)) for a in artifacts]
    noise_effective = [int(a.get("noise_effective", 0)) for a in artifacts]
    sequence_lengths = [int(a.get("sequence_length", 0)) for a in artifacts]
    warning_count = sum(
        1
        for artifact in artifacts
        if (artifact.get("generation") or {}).get("warnings")
    )
    rejected_total = sum(
        int((artifact.get("generation") or {}).get("validation", {}).get("rejected", 0))
        for artifact in artifacts
    )

    def _mean(values: list[int | float]) -> float:
        return float(statistics.mean(values)) if values else 0.0

    return {
        "anchor_count": len(artifacts),
        "noise_target_min": min(noise_targets) if noise_targets else 0,
        "noise_target_max": max(noise_targets) if noise_targets else 0,
        "noise_target_mean": _mean(noise_targets),
        "noise_effective_mean": _mean(noise_effective),
        "avg_sequence_length": _mean(sequence_lengths),
        "artifacts_with_warnings": warning_count,
        "validation_rejected_total": rejected_total,
        "noise_target_histogram": {
            str(k): noise_targets.count(k) for k in sorted(set(noise_targets))
        },
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--step2-input", type=Path, default=DEFAULT_STEP2)
    parser.add_argument("--step3-output", type=Path, default=DEFAULT_STEP3)
    parser.add_argument("--limit", type=int, default=None, help="Process at most N tasks.")
    parser.add_argument("--offset", type=int, default=0, help="Start from this task offset.")
    parser.add_argument("--max-anchors", type=int, default=None, help="Process at most N anchors.")
    parser.add_argument("--seed", type=int, default=13, help="Seed for reproducible noise-count sampling.")
    parser.add_argument("--workers", type=int, default=1, help="Number of anchors to process in parallel.")
    parser.add_argument("--dry-run", action="store_true", help="Use legacy template dry-run sequence.")
    parser.add_argument(
        "--anchor-level",
        action="store_true",
        help="Generate rulebase noise per anchor bullet instead of per action (legacy).",
    )
    parser.add_argument(
        "--llm",
        action="store_true",
        help="Use legacy LLM dependency+text generation instead of rule-based mutations.",
    )
    parser.add_argument(
        "--mutation-max-attempts",
        type=int,
        default=DEFAULT_RULEBASE_SAMPLE_ATTEMPTS,
        help="Max mutation candidates to sample per anchor/action before stopping (default 10).",
    )
    parser.add_argument("--noise-min", type=int, default=DEFAULT_NOISE_MIN)
    parser.add_argument("--noise-max", type=int, default=DEFAULT_NOISE_MAX)
    parser.add_argument("--noise-mean", type=float, default=DEFAULT_NOISE_MEAN)
    parser.add_argument("--noise-std", type=float, default=DEFAULT_NOISE_STD)
    parser.add_argument("--model", default=None)
    parser.add_argument("--base-url", default=None)
    parser.add_argument("--api-key", default=None)
    parser.add_argument("--max-tokens", type=int, default=4096)
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument("--retries", type=int, default=3)
    parser.add_argument("--sleep", type=float, default=0.5)
    parser.add_argument(
        "--validation-retries",
        type=int,
        default=DEFAULT_VALIDATION_RETRIES,
        help="Extra LLM attempts when noisy executable validation rejects equivalent items.",
    )
    parser.add_argument(
        "--print-prompt",
        action="store_true",
        help="Print one sample system+user prompt with length stats and exit.",
    )
    parser.add_argument(
        "--print-prompt-constraint",
        default=None,
        help="mac_constraint_uid to use with --print-prompt (default: first selected anchor).",
    )
    parser.add_argument(
        "--merge-into",
        type=Path,
        default=None,
        help="Incremental mode: read existing step-3 output and replace entries by mac_constraint_uid.",
    )
    parser.add_argument(
        "--only-constraint",
        action="append",
        default=[],
        help="Process only these mac_constraint_uid values; requires --merge-into.",
    )
    parser.add_argument(
        "--noise-dedup-similarity",
        type=float,
        default=DEFAULT_NOISE_DEDUP_SIMILARITY,
        help="Reject noisy text when task-level Jaccard similarity exceeds this threshold (0-1).",
    )
    parser.add_argument(
        "--report-dedup",
        action="store_true",
        help="Print task-level noisy dedup before/after report for --step3-output or --merge-into and exit.",
    )
    return parser.parse_args()


def seed_task_noisy_registries(
    tasks: list[dict[str, Any]],
    *,
    skip_constraint_uids: set[str] | None = None,
) -> dict[str, list[dict[str, Any]]]:
    registries: dict[str, list[dict[str, Any]]] = defaultdict(list)
    skip = skip_constraint_uids or set()
    for task in tasks:
        task_uid = str(task.get("mac_task_uid") or "")
        for entry in task.get("constraints") or []:
            if not isinstance(entry, dict):
                continue
            constraint_uid = str(entry.get("mac_constraint_uid") or "")
            if constraint_uid in skip:
                continue
            for noisy in entry.get("temporal_noise") or []:
                if not isinstance(noisy, dict):
                    continue
                text = str(noisy.get("text") or "").strip()
                dependency = noisy.get("dependency")
                if not text and dependency is None:
                    continue
                registry_item: dict[str, Any] = {
                    "mac_constraint_uid": constraint_uid,
                }
                if text:
                    registry_item["text"] = text
                if dependency is not None:
                    registry_item["dependency_signature"] = canonical_dependency_signature(dependency)
                registries[task_uid].append(registry_item)
    return registries


def print_dedup_report(report: dict[str, Any]) -> None:
    print(
        f"noise dedup threshold={report.get('similarity_threshold')} "
        f"total {report.get('total_before')} -> {report.get('total_after')} "
        f"(removed {report.get('total_removed')})"
    )
    for task_report in report.get("tasks") or []:
        task_uid = str(task_report.get("mac_task_uid") or "")
        short_name = task_uid.split(":", 2)[-1] if task_uid.count(":") >= 2 else task_uid
        print(
            f"  {short_name}: {task_report.get('noisy_before')} -> {task_report.get('noisy_after')} "
            f"(removed {task_report.get('removed')})"
        )
        for removed in task_report.get("removed_items") or []:
            text = str(removed.get("text") or "")
            preview = text if len(text) <= 100 else text[:97] + "..."
            anchor = str(removed.get("mac_constraint_uid") or "").split(":")[-1]
            print(f"    - [{anchor}] {preview}")
            print(f"      reason: {removed.get('reason')}")


def main() -> int:
    load_env()
    args = parse_args()
    if args.llm or args.print_prompt:
        resolve_llm_config(args)

    if args.noise_min > args.noise_max:
        raise SystemExit("--noise-min must be <= --noise-max")
    if args.noise_std <= 0:
        raise SystemExit("--noise-std must be > 0")

    if args.noise_dedup_similarity < 0 or args.noise_dedup_similarity > 1:
        raise SystemExit("--noise-dedup-similarity must be between 0 and 1")

    only_uids = {str(uid).strip() for uid in (args.only_constraint or []) if str(uid).strip()}
    if only_uids and not args.merge_into:
        raise SystemExit("--only-constraint requires --merge-into")

    step2_path = resolve_path(args.step2_input)
    step2_tasks = load_step2_tasks(step2_path)
    selected_tasks = selected_items(step2_tasks, args.offset, args.limit)

    existing_by_uid: dict[str, dict[str, Any]] = {}
    merge_base: list[dict[str, Any]] | None = None
    if args.merge_into:
        merge_base = load_step3_tasks(resolve_path(args.merge_into))
        existing_by_uid = existing_artifacts_from_step3_tasks(merge_base)

    if args.report_dedup:
        report_path = resolve_path(args.merge_into or args.step3_output)
        tasks = load_step3_tasks(report_path)
        _, report = dedup_slim_step3_tasks(
            tasks,
            similarity_threshold=float(args.noise_dedup_similarity),
        )
        print_dedup_report(report)
        return 0

    task_registries = seed_task_noisy_registries(
        merge_base or [],
        skip_constraint_uids=only_uids,
    )

    jobs = iter_anchor_jobs(
        selected_tasks,
        seed=args.seed,
        noise_min=args.noise_min,
        noise_max=args.noise_max,
        noise_mean=args.noise_mean,
        noise_std=args.noise_std,
        max_anchors=args.max_anchors,
        only_uids=only_uids,
    )
    action_jobs = iter_action_jobs(
        selected_tasks,
        seed=args.seed,
        noise_min=args.noise_min,
        noise_max=args.noise_max,
        max_anchors=args.max_anchors,
        only_uids=only_uids,
    )
    use_action_level = not args.anchor_level and not args.llm

    if args.print_prompt:
        print_sample_prompt(jobs, constraint_uid=args.print_prompt_constraint)
        return 0

    artifacts: list[dict[str, Any]] = []
    workers = max(1, int(args.workers))

    def register_artifact(task_uid: str, constraint_uid: str, artifact: dict[str, Any]) -> None:
        task_registries[task_uid] = [
            item
            for item in task_registries[task_uid]
            if str(item.get("mac_constraint_uid") or "") != constraint_uid
        ]
        task_registries[task_uid].extend(task_noisy_registry_from_artifact(artifact))

    if use_action_level:
        for action_job in action_jobs:
            skip = False
            if only_uids:
                skip = all(
                    str(anchor.get("mac_constraint_uid") or "").strip() not in only_uids
                    for anchor in action_job.anchors
                )
            if skip:
                for anchor in action_job.anchors:
                    uid = str(anchor.get("mac_constraint_uid") or "").strip()
                    reused = existing_by_uid.get(uid)
                    if reused:
                        artifacts.append(reused)
                continue
            task_uid = str(action_job.task.get("mac_task_uid") or "")
            job_artifacts = process_action_job(
                action_job,
                args,
                task_existing_noisy=task_registries[task_uid],
            )
            anchor_uids = {
                str(anchor.get("mac_constraint_uid") or "").strip()
                for anchor in action_job.anchors
            }
            task_registries[task_uid] = [
                item
                for item in task_registries[task_uid]
                if str(item.get("mac_constraint_uid") or "") not in anchor_uids
            ]
            if job_artifacts:
                task_registries[task_uid].extend(
                    task_noisy_registry_from_artifact(job_artifacts[0])
                )
            for artifact in job_artifacts:
                uid = str(artifact.get("mac_constraint_uid") or "").strip()
                if only_uids and uid not in only_uids:
                    reused = existing_by_uid.get(uid)
                    if reused:
                        artifacts.append(reused)
                    continue
                artifacts.append(artifact)
    elif workers == 1:
        def handle_completed_job(job: AnchorJob, artifact: dict[str, Any]) -> None:
            task_uid = str(job.task.get("mac_task_uid") or "")
            constraint_uid = str(job.anchor.get("mac_constraint_uid") or "")
            register_artifact(task_uid, constraint_uid, artifact)
            artifacts.append(artifact)

        for job in jobs:
            uid = str(job.anchor.get("mac_constraint_uid") or "").strip()
            if only_uids and uid not in only_uids:
                reused = existing_by_uid.get(uid)
                if reused:
                    artifacts.append(reused)
                continue
            task_uid = str(job.task.get("mac_task_uid") or "")
            artifact = process_anchor_job(
                job,
                args,
                task_existing_noisy=task_registries[task_uid],
            )
            handle_completed_job(job, artifact)
    else:
        def handle_completed_job(job: AnchorJob, artifact: dict[str, Any]) -> None:
            task_uid = str(job.task.get("mac_task_uid") or "")
            constraint_uid = str(job.anchor.get("mac_constraint_uid") or "")
            register_artifact(task_uid, constraint_uid, artifact)
            artifacts.append(artifact)

        futures = {}
        with ThreadPoolExecutor(max_workers=workers) as executor:
            for job in jobs:
                uid = str(job.anchor.get("mac_constraint_uid") or "").strip()
                if only_uids and uid not in only_uids:
                    reused = existing_by_uid.get(uid)
                    if reused:
                        artifacts.append(reused)
                    continue
                task_uid = str(job.task.get("mac_task_uid") or "")
                futures[
                    executor.submit(
                        process_anchor_job,
                        job,
                        args,
                        task_existing_noisy=list(task_registries[task_uid]),
                    )
                ] = job
            for future in as_completed(futures):
                job = futures[future]
                handle_completed_job(job, future.result())

    new_by_uid = artifacts_by_constraint_uid(artifacts)
    if args.merge_into and merge_base is not None:
        merged_by_uid = dict(existing_by_uid)
        merged_by_uid.update(new_by_uid)
        output_scope = copy.deepcopy(merge_base)
        existing_task_uids = {
            str(task.get("mac_task_uid") or "").strip()
            for task in output_scope
            if str(task.get("mac_task_uid") or "").strip()
        }
        for task in selected_tasks:
            task_uid = str(task.get("mac_task_uid") or "").strip()
            if task_uid and task_uid not in existing_task_uids:
                output_scope.append(copy.deepcopy(task))
                existing_task_uids.add(task_uid)
    else:
        merged_by_uid = new_by_uid
        output_scope = selected_tasks if (args.limit is not None or args.offset > 0) else step2_tasks

    merged_by_uid, dedup_report = apply_noise_dedup_to_artifacts(
        merged_by_uid,
        output_scope,
        similarity_threshold=float(args.noise_dedup_similarity),
    )
    if dedup_report.get("total_removed"):
        print_dedup_report(dedup_report)

    step3_tasks = build_slim_step3_tasks(copy.deepcopy(output_scope), merged_by_uid)

    summary = summarize_artifacts(list(merged_by_uid.values()))
    step3_output_path = resolve_path(args.step3_output)
    step3_meta = {
        "schema_version": "MACConstructStep3TemporalNoiseV5",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "generator": "llm" if args.llm else ("rulebase_action" if not args.anchor_level else "rulebase_anchor"),
        "tasks_output": str(step3_output_path.relative_to(REPO_ROOT))
        if step3_output_path.is_relative_to(REPO_ROOT)
        else str(step3_output_path),
        "source_step2": str(step2_path.relative_to(REPO_ROOT))
        if step2_path.is_relative_to(REPO_ROOT)
        else str(step2_path),
        "seed": args.seed,
        "noise_bounds": [args.noise_min, args.noise_max],
        "noise_distribution": {
            "type": "complexity_aware",
            "small_subtree_keep": "1-2 validated variants",
            "composite_subtree_keep": "4-5 validated variants",
            "sample_attempts_per_unit": int(
                getattr(args, "mutation_max_attempts", DEFAULT_RULEBASE_SAMPLE_ATTEMPTS)
            ),
        },
        "mutation_max_attempts": int(
            getattr(args, "mutation_max_attempts", DEFAULT_RULEBASE_SAMPLE_ATTEMPTS)
        ),
        "summary": summary,
    }

    write_json(args.step3_output, step3_tasks)
    meta_path = step3_output_path.with_suffix(step3_output_path.suffix + ".meta.json")
    warnings_path = step3_output_path.with_suffix(step3_output_path.suffix + ".warning")
    warnings_report = {
        "schema_version": "MACConstructStep3TemporalNoiseWarningsV1",
        "generated_at": step3_meta["generated_at"],
        "step3_output": step3_meta["tasks_output"],
        **warnings_report_from_artifacts(merged_by_uid),
    }
    write_json(warnings_path, warnings_report)
    step3_meta["warnings_output"] = (
        str(warnings_path.relative_to(REPO_ROOT))
        if warnings_path.is_relative_to(REPO_ROOT)
        else str(warnings_path)
    )
    write_json(meta_path, step3_meta)

    print(
        f"wrote {len(step3_tasks)} step-3 task(s) to {step3_output_path}; "
        f"anchors={summary['anchor_count']}, "
        f"avg_sequence={summary['avg_sequence_length']:.2f}, "
        f"meta={meta_path}, warnings={warnings_path}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
