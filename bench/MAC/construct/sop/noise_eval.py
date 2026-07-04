"""Deterministic SOP temporal noise eval: segment export and trajectory grading.

Requires Python 3.10+ (SOPBench uses ``match`` statements).
"""

from __future__ import annotations

import copy
import hashlib
import json
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[4]
CONSTRUCT_SOP_ROOT = Path(__file__).resolve().parent
SOPBENCH_ROOT = REPO_ROOT / "bench" / "SOPBench"

if str(CONSTRUCT_SOP_ROOT) not in sys.path:
    sys.path.insert(0, str(CONSTRUCT_SOP_ROOT))
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


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


def to_json_safe(value: Any) -> Any:
    if isinstance(value, tuple):
        return [to_json_safe(item) for item in value]
    if isinstance(value, list):
        return [to_json_safe(item) for item in value]
    if isinstance(value, dict):
        return {str(key): to_json_safe(item) for key, item in value.items()}
    return value


def list_to_tuple(value: Any) -> Any:
    if isinstance(value, list):
        return tuple(list_to_tuple(item) for item in value)
    if isinstance(value, dict):
        return {key: list_to_tuple(item) for key, item in value.items()}
    return value


def single_constraint_key(constraint_id: str, params: dict[str, Any]) -> str:
    return json.dumps(
        {"constraint_id": constraint_id, "params": params},
        sort_keys=True,
        ensure_ascii=False,
    )


def parse_single_identity(raw_id: str) -> tuple[str, bool]:
    raw = str(raw_id or "")
    negated = raw.startswith("not ")
    normalized = raw[4:] if negated else raw
    return normalized, negated


def unit_id(task_uid: str, constraint_id: str, params: dict[str, Any], *, occurrence: int = 1) -> str:
    digest = hashlib.sha256(
        f"{task_uid}|{constraint_id}|{json.dumps(params, sort_keys=True)}|{occurrence}".encode("utf-8")
    ).hexdigest()[:12]
    normalized, _ = parse_single_identity(constraint_id)
    return f"{task_uid}-u-{normalized}-o{occurrence}-{digest}"


def graph_action_unit_id(task_uid: str, action: str) -> str:
    digest = hashlib.sha256(f"{task_uid}|graph_action|{action}".encode("utf-8")).hexdigest()[:12]
    return f"{task_uid}-g-{action}-{digest}"


def graph_action_nodes(graph: Any) -> set[str]:
    nodes: set[str] = set()
    if not isinstance(graph, dict):
        return nodes
    for node in graph.get("nodes") or []:
        if isinstance(node, (list, tuple)) and node:
            name = str(node[0]).strip()
            if name:
                nodes.add(name)
    return nodes


def anchor_user_goal_dependency(step2_task: dict[str, Any]) -> Any:
    """Return SOPBench's original user-goal dependency.

    Step3 stores per-seed action fragments, so using it as the baseline can
    accidentally replace the full SOPBench dependency with one sampled leaf.
    The grading oracle must stay attached to SOPBench's original task.
    """
    original = step2_task.get("original_sopbench") or {}
    dep = original.get("constraints")
    if dep is None:
        raise ValueError(f"missing original constraints for {step2_task.get('mac_task_uid')}")
    from temporal_noise import normalize_dep_tree  # noqa: WPS433

    return normalize_dep_tree(copy.deepcopy(dep))


def anchor_directed_action_graph(step2_task: dict[str, Any]) -> dict[str, Any]:
    original = step2_task.get("original_sopbench") or {}
    graph = original.get("directed_action_graph")
    if isinstance(graph, dict) and graph.get("nodes"):
        return copy.deepcopy(graph)
    raise ValueError(f"missing anchor directed_action_graph for {step2_task.get('mac_task_uid')}")


def anchor_sopbench_task(step2_task: dict[str, Any]) -> dict[str, Any]:
    original = copy.deepcopy(step2_task.get("original_sopbench") or {})
    user_goal = str(step2_task.get("user_goal") or "")
    return {
        **original,
        "user_goal": user_goal,
        "constraints": copy.deepcopy(original.get("constraints") or []),
        "directed_action_graph": anchor_directed_action_graph(step2_task),
    }


def patched_sopbench_task(
    step2_task: dict[str, Any],
    *,
    user_goal_dep: Any,
    directed_action_graph: dict[str, Any],
) -> dict[str, Any]:
    patched = anchor_sopbench_task(step2_task)
    patched["constraints"] = copy.deepcopy(user_goal_dep)
    patched["constraints_original"] = copy.deepcopy(user_goal_dep)
    patched["directed_action_graph"] = copy.deepcopy(directed_action_graph)
    return patched


def cumulative_user_goal_graph(
    step2_task: dict[str, Any],
    action_deps: dict[str, Any],
    *,
    fallback_graph: Any = None,
) -> dict[str, Any]:
    dep_full = build_patched_dep_full(step2_task, action_deps)
    user_goal = str(step2_task.get("user_goal") or "").strip()
    dep = dep_full.get(user_goal)
    if dep is None:
        raise ValueError(f"user_goal {user_goal} missing from dep_full")
    try:
        return compile_user_goal_graph(
            step2_task,
            user_goal_dep=dep,
            dep_full=dep_full,
        )
    except Exception:  # noqa: BLE001
        if isinstance(fallback_graph, dict) and fallback_graph.get("nodes"):
            return copy.deepcopy(fallback_graph)
        return anchor_directed_action_graph(step2_task)


def action_anchor_baselines(step3_task: dict[str, Any]) -> dict[str, dict[str, Any]]:
    baselines: dict[str, dict[str, Any]] = {}
    for constraint in step3_task.get("constraints") or []:
        if not isinstance(constraint, dict):
            continue
        action = str(
            constraint.get("action")
            or constraint.get("anchor_action")
            or ""
        ).strip()
        if not action or action in baselines:
            continue
        baselines[action] = {
            "dependency": copy.deepcopy(constraint.get("anchor_dependency")),
        }
    return baselines


def build_cumulative_action_deps(
    step3_task: dict[str, Any],
    sequence: list[dict[str, Any]],
) -> dict[str, Any]:
    baselines = action_anchor_baselines(step3_task)
    deps: dict[str, Any] = {
        action: copy.deepcopy(entry.get("dependency"))
        for action, entry in baselines.items()
    }
    for step in sequence:
        if not isinstance(step, dict):
            continue
        action = str(step.get("action") or "").strip()
        dependency = step.get("dependency")
        if action and dependency is not None:
            deps[action] = copy.deepcopy(dependency)
    return deps


def build_patched_dep_full(step2_task: dict[str, Any], action_deps: dict[str, Any]) -> dict[str, Any]:
    from temporal_noise import (  # noqa: WPS433
        domain_runtime,
        normalize_dep_tree,
        task_source_for_dep_full,
    )

    runtime = domain_runtime(str(step2_task.get("domain") or ""))
    dep_full = runtime.build_task_dep_full(task_source_for_dep_full(step2_task))
    for action, dependency in action_deps.items():
        if dependency is not None:
            dep_full[str(action)] = list_to_tuple(normalize_dep_tree(dependency))
    return dep_full


def user_goal_dependency(step2_task: dict[str, Any], action_deps: dict[str, Any]) -> Any:
    user_goal = str(step2_task.get("user_goal") or "").strip()
    dep_full = build_patched_dep_full(step2_task, action_deps)
    dep = dep_full.get(user_goal)
    if dep is None:
        raise ValueError(f"user_goal {user_goal} missing from dep_full")
    from temporal_noise import normalize_dep_tree  # noqa: WPS433

    return normalize_dep_tree(dep)


def compile_user_goal_graph(
    step2_task: dict[str, Any],
    *,
    user_goal_dep: Any,
    dep_full: dict[str, Any],
) -> dict[str, Any]:
    from temporal_noise import compile_action_graph  # noqa: WPS433

    user_goal = str(step2_task.get("user_goal") or "").strip()
    compiled = compile_action_graph(
        task=step2_task,
        target_action=user_goal,
        dependency=user_goal_dep,
        dep_full=dep_full,
    )
    graph = compiled.get("graph")
    if not isinstance(graph, dict):
        raise ValueError(f"failed to compile user_goal graph for {user_goal}")
    return copy.deepcopy(graph)


def final_user_goal_graph(
    step2_task: dict[str, Any],
    *,
    user_goal_dep: Any,
    dep_full: dict[str, Any],
    sequence: list[dict[str, Any]],
) -> dict[str, Any]:
    try:
        return compile_user_goal_graph(
            step2_task,
            user_goal_dep=user_goal_dep,
            dep_full=dep_full,
        )
    except Exception:  # noqa: BLE001
        for step in reversed(sequence):
            if not isinstance(step, dict):
                continue
            graph = step.get("user_goal_action_graph")
            if isinstance(graph, dict) and graph.get("nodes"):
                return copy.deepcopy(graph)
        original = step2_task.get("original_sopbench") or {}
        anchor_graph = original.get("directed_action_graph")
        if isinstance(anchor_graph, dict) and anchor_graph.get("nodes"):
            return copy.deepcopy(anchor_graph)
        raise


def replay_final_action_deps(sequence: list[dict[str, Any]]) -> dict[str, Any]:
    action_deps: dict[str, Any] = {}
    for step in sequence:
        if not isinstance(step, dict):
            continue
        if str(step.get("kind") or "") == "anchor_alignment":
            for action, dependency in (step.get("action_patches") or {}).items():
                action_key = str(action or "").strip()
                if action_key and dependency is not None:
                    action_deps[action_key] = copy.deepcopy(dependency)
            continue
        action = str(step.get("action") or "").strip()
        dependency = step.get("dependency")
        if action and dependency is not None:
            action_deps[action] = copy.deepcopy(dependency)
    return action_deps


def replay_final_state(
    step2_task: dict[str, Any],
    sequence: list[dict[str, Any]],
) -> tuple[dict[str, Any], Any, dict[str, Any]]:
    action_deps = replay_final_action_deps(sequence)
    dep_full = build_patched_dep_full(step2_task, action_deps)
    user_goal = str(step2_task.get("user_goal") or "").strip()
    user_goal_dep = dep_full.get(user_goal)
    if user_goal_dep is None:
        raise ValueError(f"user_goal {user_goal} missing from final dep_full")
    from temporal_noise import normalize_dep_tree  # noqa: WPS433

    normalized_dep = normalize_dep_tree(user_goal_dep)
    directed_graph = final_user_goal_graph(
        step2_task,
        user_goal_dep=normalized_dep,
        dep_full=dep_full,
        sequence=sequence,
    )
    return action_deps, normalized_dep, directed_graph


def task_dep_params(step2_task: dict[str, Any]) -> dict[str, Any]:
    original = step2_task.get("original_sopbench") or {}
    params = copy.deepcopy(step2_task.get("constraint_parameters") or {})
    params.update(copy.deepcopy(original.get("constraint_parameters") or {}))
    return params


def verbalize_single(
    domain: str,
    constraint_id: str,
    params: dict[str, Any],
    dep_params: dict[str, Any],
) -> str:
    from temporal_assemble import verbalize_single_constraint  # noqa: WPS433

    return verbalize_single_constraint(domain, constraint_id, params, dep_params)


@dataclass
class EvalRevision:
    task_uid: str
    domain: str
    user_goal: str
    sequence_turn_count: int
    action_deps: dict[str, Any]
    user_goal_dependency: Any
    directed_action_graph: dict[str, Any]
    patched_sopbench_task: dict[str, Any]
    units: list[dict[str, Any]]


def collect_eval_units(
    *,
    step2_task: dict[str, Any],
    step3_task: dict[str, Any],
    sequence: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Collect dependency-single and graph-action diagnostic segments.

    The exported JSON keeps the historical ``units`` field for compatibility,
    but these rows are MAC diagnostic segments, not top-level constraints.
    Ground truth (``expected_should_apply``) comes from active SOP constraints;
    historical temporal revisions contribute noise segments that should not
    apply at eval.
    """
    from temporal_noise import dependency_singles  # noqa: WPS433

    task_uid = str(step2_task.get("mac_task_uid") or "")
    domain = str(step2_task.get("domain") or "")
    user_goal = str(step2_task.get("user_goal") or "")
    dep_params = task_dep_params(step2_task)
    action_deps: dict[str, Any] = {}

    anchor_dep = anchor_user_goal_dependency(step2_task)
    anchor_single_counts = Counter(
        single_constraint_key(constraint_id, params)
        for constraint_id, params in dependency_singles(anchor_dep)
    )
    anchor_graph = anchor_directed_action_graph(step2_task)
    anchor_graph_actions = graph_action_nodes(anchor_graph) - {user_goal}

    historical_single_counts: Counter[str] = Counter()
    single_lookup: dict[str, tuple[str, dict[str, Any]]] = {}
    single_first_seen: dict[str, int] = {}
    single_last_seen: dict[str, int] = {}

    historical_graph_actions: set[str] = set()
    graph_first_seen: dict[str, int] = {}
    graph_last_seen: dict[str, int] = {}

    def record_dep_state(order: int, dep: Any) -> None:
        state_counts: Counter[str] = Counter()
        for constraint_id, params in dependency_singles(dep):
            key = single_constraint_key(constraint_id, params)
            state_counts[key] += 1
            single_lookup[key] = (constraint_id, copy.deepcopy(params))
            single_first_seen.setdefault(key, order)
            single_last_seen[key] = order
        for key, count in state_counts.items():
            historical_single_counts[key] = max(historical_single_counts[key], count)

    def record_graph_state(order: int, graph: Any) -> None:
        for action in graph_action_nodes(graph) - {user_goal}:
            historical_graph_actions.add(action)
            graph_first_seen.setdefault(action, order)
            graph_last_seen[action] = order

    record_dep_state(0, anchor_dep)
    record_graph_state(0, anchor_graph)
    for step in sequence:
        if not isinstance(step, dict):
            continue
        order = int(step.get("sequence_order") or 0)
        if str(step.get("kind") or "") == "anchor_alignment":
            for action, dependency in (step.get("action_patches") or {}).items():
                action_key = str(action or "").strip()
                if action_key and dependency is not None:
                    action_deps[action_key] = copy.deepcopy(dependency)
        else:
            mutated_action = str(step.get("action") or "").strip()
            dependency = step.get("dependency")
            if mutated_action and dependency is not None:
                action_deps[mutated_action] = copy.deepcopy(dependency)
        record_dep_state(order, user_goal_dependency(step2_task, action_deps))
        record_graph_state(
            order,
            cumulative_user_goal_graph(
                step2_task,
                action_deps,
                fallback_graph=step.get("user_goal_action_graph"),
            ),
        )

    units: list[dict[str, Any]] = []
    single_normalized_ids: set[str] = set()

    for key in sorted(historical_single_counts):
        constraint_id, params = single_lookup[key]
        normalized, negated = parse_single_identity(constraint_id)
        single_normalized_ids.add(normalized)
        for occurrence in range(1, historical_single_counts[key] + 1):
            expected = occurrence <= anchor_single_counts.get(key, 0)
            units.append(
                {
                    "unit_id": unit_id(task_uid, constraint_id, params, occurrence=occurrence),
                    "task_uid": task_uid,
                    "expected_should_apply": expected,
                    "is_anchor": expected,
                    "constraint_id": constraint_id,
                    "normalized_constraint_id": normalized,
                    "negated": negated,
                    "params": copy.deepcopy(params),
                    "occurrence": occurrence,
                    "text": verbalize_single(domain, constraint_id, params, dep_params),
                    "evaluator_type": "sopbench_single",
                    "unit_source": "dependency_single",
                    "first_seen_sequence_order": single_first_seen.get(key),
                    "last_seen_sequence_order": single_last_seen.get(key),
                }
            )

    for action in sorted(historical_graph_actions):
        if action in single_normalized_ids:
            continue
        expected = action in anchor_graph_actions
        units.append(
            {
                "unit_id": graph_action_unit_id(task_uid, action),
                "task_uid": task_uid,
                "expected_should_apply": expected,
                "is_anchor": expected,
                "constraint_id": action,
                "normalized_constraint_id": action,
                "negated": False,
                "params": {},
                "text": (
                    f"Precall action `{action}` appears in a historical user-goal "
                    f"directed action graph for `{user_goal}`."
                ),
                "evaluator_type": "sopbench_action_call",
                "unit_source": "graph_action",
                "first_seen_sequence_order": graph_first_seen.get(action),
                "last_seen_sequence_order": graph_last_seen.get(action),
            }
        )

    return units


def build_eval_revision(
    *,
    step2_task: dict[str, Any],
    step3_task: dict[str, Any],
    step4_task: dict[str, Any],
) -> EvalRevision:
    sequence = [
        step
        for step in (step4_task.get("temporal_sequence") or [])
        if isinstance(step, dict)
    ]
    units = collect_eval_units(
        step2_task=step2_task,
        step3_task=step3_task,
        sequence=sequence,
    )
    anchor_dep = anchor_user_goal_dependency(step2_task)
    anchor_graph = anchor_directed_action_graph(step2_task)
    patched = anchor_sopbench_task(step2_task)
    return EvalRevision(
        task_uid=str(step2_task.get("mac_task_uid") or ""),
        domain=str(step2_task.get("domain") or ""),
        user_goal=str(step2_task.get("user_goal") or ""),
        sequence_turn_count=len(sequence),
        action_deps={},
        user_goal_dependency=to_json_safe(anchor_dep),
        directed_action_graph=anchor_graph,
        patched_sopbench_task=patched,
        units=units,
    )


def build_manifest_payload(
    *,
    revisions: list[EvalRevision],
    source_step2: str,
    source_step3: str,
    source_step4: str,
) -> dict[str, Any]:
    units: list[dict[str, Any]] = []
    task_specs: dict[str, Any] = {}
    for revision in revisions:
        task_specs[revision.task_uid] = {
            "task_uid": revision.task_uid,
            "domain": revision.domain,
            "user_goal": revision.user_goal,
            "sequence_turn_count": revision.sequence_turn_count,
            "patched_sopbench_task": revision.patched_sopbench_task,
        }
        units.extend(revision.units)
    dependency_units = [unit for unit in units if unit.get("unit_source") == "dependency_single"]
    graph_units = [unit for unit in units if unit.get("unit_source") == "graph_action"]
    return {
        "schema_version": "MACSOPNoiseEvalSpecManifestV2",
        "oracle": "anchor",
        "source_step2": source_step2,
        "source_step3": source_step3,
        "source_step4": source_step4,
        "summary": {
            "task_count": len(revisions),
            "unit_count": len(units),
            "dependency_single_unit_count": len(dependency_units),
            "graph_action_unit_count": len(graph_units),
            "anchor_unit_count": sum(1 for unit in units if unit.get("expected_should_apply")),
            "noise_unit_count": sum(1 for unit in units if not unit.get("expected_should_apply")),
        },
        "terminology": {
            "units": "compatibility name for diagnostic segments",
            "anchor_unit_count": "anchor diagnostic segment count",
            "noise_unit_count": "noise diagnostic segment count",
            "constraint": "action-scoped evaluable SOP unit; segments are nested diagnostics",
        },
        "task_specs": task_specs,
        "units": units,
    }


MAC_TERMINAL_TOOL_NAMES = frozenset({"send_message"})


def func_calls_from_trace(trace: dict[str, Any]) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []
    for call in trace.get("tool_calls") or []:
        if not isinstance(call, dict):
            continue
        name = call.get("name")
        if not isinstance(name, str) or not name:
            continue
        if name in MAC_TERMINAL_TOOL_NAMES:
            continue
        calls.append(
            {
                "tool_name": name,
                "arguments": call.get("arguments") if isinstance(call.get("arguments"), dict) else {},
                "content": call.get("result"),
            }
        )
    return calls


def _call_success(response: Any) -> bool:
    if isinstance(response, bool):
        return response
    if isinstance(response, (tuple, list)) and response:
        head = response[0]
        return head if isinstance(head, bool) else bool(head)
    return bool(response)


def _strict_domain_context(domain_str: str, task: dict[str, Any]) -> tuple[Any, Any, set[str]]:
    ensure_sopbench_imports()
    from env.helpers import get_action_parameters  # type: ignore[import-not-found]  # noqa: WPS433
    from env.task import get_default_dep_full  # type: ignore[import-not-found]  # noqa: WPS433
    from env.variables import domain_assistant_keys, domain_keys  # type: ignore[import-not-found]  # noqa: WPS433

    dep_innate_full = domain_assistant_keys[domain_str].action_innate_dependencies
    default_dep_full = get_default_dep_full(domain_str, "default")
    default_dep_full[task["user_goal"]] = list_to_tuple(task["constraints"])
    domain_system_strict = domain_keys[f"{domain_str}_strict"](
        copy.deepcopy(task["initial_database"]),
        dep_innate_full,
        default_dep_full,
        task.get("constraint_parameters") or {},
    )
    domain_system = domain_system_strict.evaluation_get_domain_system()
    action_parameters = set(
        get_action_parameters(domain_system, domain_assistant_keys[domain_str]).keys()
    )
    return domain_system_strict, domain_system, action_parameters


def _replay_trajectory(
    domain_str: str,
    task: dict[str, Any],
    func_calls: list[dict[str, Any]],
) -> dict[str, Any]:
    ensure_sopbench_imports()
    from env.evaluator import evaluator_function_directed_graph  # type: ignore[import-not-found]  # noqa: WPS433

    domain_system_strict, domain_system, action_parameters = _strict_domain_context(domain_str, task)
    user_goal = str(task.get("user_goal") or "")
    successful_actions: set[str] = set()
    user_goal_called = False
    for func_call in func_calls:
        func_name = str(func_call.get("tool_name") or "")
        arguments = func_call.get("arguments") if isinstance(func_call.get("arguments"), dict) else {}
        if not func_name:
            continue
        if not hasattr(domain_system_strict, func_name):
            continue
        try:
            response = getattr(domain_system_strict, func_name)(**arguments)
        except Exception:  # noqa: BLE001
            continue
        if _call_success(response):
            successful_actions.add(func_name)
            if func_name == user_goal:
                user_goal_called = True

    final_database = domain_system_strict.evaluation_get_database()
    evaluation = evaluator_function_directed_graph(
        domain_str=domain_str,
        task=task,
        log_msg_fcall=[],
        func_calls=func_calls,
        results={"final_database": final_database},
        default_constraint_option="default",
    )
    order_respecting_actions = {
        str(name)
        for name in (evaluation.get("order_respecting_actions") or [])
    }
    return {
        "evaluation": evaluation,
        "final_database": final_database,
        "successful_actions": successful_actions,
        "order_respecting_actions": order_respecting_actions,
        "user_goal_called": user_goal_called,
        "action_parameters": action_parameters,
        "domain_system_strict": domain_system_strict,
        "domain_system": domain_system,
    }


def _dependency_evaluator_before_user_goal(
    domain_system_strict: Any,
    task: dict[str, Any],
    func_calls: list[dict[str, Any]],
    user_goal: str,
) -> tuple[Any, dict[str, Any]]:
    dependency_evaluator = domain_system_strict.evaluation_get_dependency_evaluator()
    user_known = copy.deepcopy(task.get("user_known") or {})
    for func_call in func_calls:
        func_name = func_call["tool_name"]
        if func_name == user_goal:
            break
        arguments = func_call.get("arguments") if isinstance(func_call.get("arguments"), dict) else {}
        if not hasattr(domain_system_strict, func_name):
            continue
        try:
            getattr(domain_system_strict, func_name)(**arguments)
        except Exception:  # noqa: BLE001
            break
    return dependency_evaluator, user_known


def evaluate_sopbench_unit(
    *,
    unit: dict[str, Any],
    task_spec: dict[str, Any],
    trace: dict[str, Any],
    replay: dict[str, Any] | None = None,
) -> dict[str, Any]:
    domain = str(task_spec.get("domain") or "")
    patched_task = copy.deepcopy(task_spec.get("patched_sopbench_task") or {})
    if not patched_task:
        return {
            "observed_followed": None,
            "confidence": "unknown",
            "reason": "missing patched_sopbench_task",
            "evidence_refs": [],
        }
    func_calls = func_calls_from_trace(trace)
    if not func_calls:
        return {
            "observed_followed": False,
            "confidence": "high",
            "reason": "no tool calls in trajectory",
            "evidence_refs": [],
        }
    if replay is None:
        replay = _replay_trajectory(domain, patched_task, func_calls)
    order_respecting_actions = replay.get("order_respecting_actions") or set()
    user_goal_called = bool(replay.get("user_goal_called"))
    domain_system_strict = replay.get("domain_system_strict")

    evaluator_type = str(unit.get("evaluator_type") or "sopbench_single")
    constraint_id = str(unit.get("constraint_id") or "")
    normalized = str(unit.get("normalized_constraint_id") or parse_single_identity(constraint_id)[0])
    params = unit.get("params") if isinstance(unit.get("params"), dict) else {}
    action_parameters = replay.get("action_parameters") or set()

    if evaluator_type == "sopbench_action_call" or normalized in action_parameters:
        observed = normalized in order_respecting_actions
        reason = (
            f"action `{normalized}` was successfully called in directed-graph order during strict replay"
            if observed
            else f"action `{normalized}` was not successfully called in directed-graph order during strict replay"
        )
        return {
            "observed_followed": observed,
            "confidence": "high",
            "reason": reason,
            "evidence_refs": [{"tool_calls": [call["tool_name"] for call in func_calls]}],
        }

    if domain_system_strict is None:
        domain_system_strict, _, _ = _strict_domain_context(domain, patched_task)
    dependency_evaluator, user_known = _dependency_evaluator_before_user_goal(
        domain_system_strict,
        patched_task,
        func_calls,
        str(patched_task.get("user_goal") or ""),
    )
    single_dep = list_to_tuple(["single", constraint_id, params])
    try:
        observed = bool(dependency_evaluator._process(single_dep, **user_known))  # noqa: SLF001
    except Exception as exc:  # noqa: BLE001
        return {
            "observed_followed": None,
            "confidence": "unknown",
            "reason": f"dependency evaluator failed: {type(exc).__name__}: {exc}",
            "evidence_refs": [],
        }
    return {
        "observed_followed": observed,
        "confidence": "medium" if user_goal_called else "low",
        "reason": (
            f"state constraint `{constraint_id}` evaluated on replayed domain state "
            f"before `{patched_task.get('user_goal')}`"
        ),
        "evidence_refs": [{"user_goal_called": user_goal_called}],
    }


def evaluate_task(
    *,
    task_spec: dict[str, Any],
    trace: dict[str, Any],
) -> dict[str, Any]:
    domain = str(task_spec.get("domain") or "")
    patched_task = copy.deepcopy(task_spec.get("patched_sopbench_task") or {})
    func_calls = func_calls_from_trace(trace)
    replay = _replay_trajectory(domain, patched_task, func_calls)
    evaluation = replay["evaluation"]
    return {
        **evaluation,
        "user_goal_called": replay["user_goal_called"],
        "_replay": {
            "successful_actions": replay["successful_actions"],
            "order_respecting_actions": replay["order_respecting_actions"],
            "user_goal_called": replay["user_goal_called"],
            "action_parameters": replay["action_parameters"],
            "domain_system_strict": replay["domain_system_strict"],
        },
    }


def outcome_bucket(expected: bool, observed: bool | None) -> str:
    if observed is None:
        return "anchor_missed" if expected else "noise_ignored"
    if expected and observed:
        return "anchor_followed"
    if expected and not observed:
        return "anchor_missed"
    if not expected and observed:
        return "noise_followed"
    return "noise_ignored"


def contract_metrics(details: list[dict[str, Any]]) -> dict[str, Any]:
    counts = Counter(str(row.get("outcome")) for row in details)
    active_followed = counts["anchor_followed"]
    active_missed = counts["anchor_missed"]
    history_followed = counts["noise_followed"]
    history_ignored = counts["noise_ignored"]
    active_constraint_count = active_followed + active_missed
    history_constraint_count = history_followed + history_ignored
    constraint_count = active_constraint_count + history_constraint_count
    noise_followed = history_followed
    return {
        "noise_follow_rate": noise_followed / history_constraint_count if history_constraint_count else None,
        "noise_followed": noise_followed,
        "active_constraint_count": active_constraint_count,
        "history_constraint_count": history_constraint_count,
        "constraint_count": constraint_count,
        "outcome_counts": {
            "active_followed": active_followed,
            "active_missed": active_missed,
            "history_followed": history_followed,
            "history_ignored": history_ignored,
        },
    }


def follow_outcome(anchor_matched: bool, history_matched: bool) -> str:
    if anchor_matched:
        return "correct_follow"
    if history_matched:
        return "wrong_follow"
    return "neither_followed"


def follow_taxonomy_metrics(details: list[dict[str, Any]]) -> dict[str, Any]:
    per_unit = any(
        str(row.get("outcome") or "")
        in {"anchor_followed", "anchor_missed", "noise_followed", "noise_ignored"}
        for row in details
    )
    if per_unit:
        unit_metrics = contract_metrics(details)
        noise_followed = unit_metrics["noise_followed"]
        history_count = unit_metrics["history_constraint_count"]
        active_count = unit_metrics["active_constraint_count"]
    else:
        noise_followed = sum(int(row.get("history_hit_count") or 0) for row in details)
        history_count = sum(int(row.get("history_constraint_count") or 0) for row in details)
        active_count = sum(int(row.get("active_constraint_count") or 0) for row in details)

    return {
        "noise_follow_rate": noise_followed / history_count if history_count else None,
        "noise_followed": noise_followed,
        "comparison_count": len(details),
        "active_constraint_count": active_count,
        "history_constraint_count": history_count,
        "constraint_count": active_count + history_count,
    }


def task_responded(trace: dict[str, Any]) -> bool:
    if str(trace.get("final_response") or "").strip():
        return True
    for call in trace.get("tool_calls") or []:
        if isinstance(call, dict) and call.get("name") == "send_message":
            return True
    return False


def task_acc(task_eval: dict[str, Any]) -> bool | None:
    """SOPBench native task success (outcome + process)."""
    if "success" not in task_eval:
        return None
    return bool(task_eval.get("success"))


def task_answer_pass(task_eval: dict[str, Any]) -> bool | None:
    """SOPBench user-goal outcome only: should vs did call user_goal."""
    if "action_called_correctly" not in task_eval:
        return None
    return bool(task_eval.get("action_called_correctly"))


def task_joint_pass(task_eval: dict[str, Any]) -> bool | None:
    """SOPBench native joint success; equivalent to answer pass AND process pass."""
    return task_acc(task_eval)


def task_process_constraint_pass(task_eval: dict[str, Any]) -> bool | None:
    """Return SOPBench-native process compliance, excluding user-goal outcome."""
    keys = (
        "no_tool_call_error",
        "constraint_not_violated",
        "database_match",
        "dirgraph_satisfied",
    )
    if any(key not in task_eval for key in keys):
        return None
    return all(bool(task_eval.get(key)) for key in keys)
