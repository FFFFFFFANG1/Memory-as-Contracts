#!/usr/bin/env python3
"""Assemble per-task temporal noise turns into shuffled sequences with graph deltas.

Reads ``bench/MAC/sopbench/mid_data/eval_step3_temporal_noise.json`` and
``bench/MAC/sopbench/mid_data/eval_step2_anchors.json``, then writes
``bench/MAC/sopbench/mid_data/eval_step4_temporal_sequence.json``:

- dedupe action-level noise fan-out across anchors on the same action
- merge action turn groups into one shuffled sequence per task (CCTU-style insert)
- compile ``user_goal_action_graph`` for each turn (patched dep_full)
- record machine + human-readable ``graph_delta`` / ``dependency_delta`` between turns
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import random
import statistics
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[4]
CONSTRUCT_ROOT = Path(__file__).resolve().parents[1]
SOP_ROOT = Path(__file__).resolve().parent
DEFAULT_STEP2 = Path("bench/MAC/sopbench/mid_data/eval_step2_anchors.json")
DEFAULT_STEP3 = Path("bench/MAC/sopbench/mid_data/eval_step3_temporal_noise.json")
DEFAULT_STEP4 = Path("bench/MAC/sopbench/mid_data/eval_step4_temporal_sequence.json")
DEFAULT_STEP4_V2 = Path("bench/MAC/sopbench/mid_data/eval_step4_temporal_sequence_v2.json")
DEFAULT_STEP4_V3 = Path("bench/MAC/sopbench/mid_data/eval_step4_temporal_sequence_v3.json")
DEFAULT_STEP4_DELTA = Path("bench/MAC/sopbench/mid_data/eval_step4_temporal_delta.json")
DEFAULT_COMPARE_OUTPUT = Path("bench/MAC/sopbench/mid_data/eval_step4_v1_v2_comparison.json")

sys.path.insert(0, str(CONSTRUCT_ROOT))
sys.path.insert(0, str(SOP_ROOT))
from cctu.constraint_merge import merge_constraint_sequence  # noqa: E402
from temporal_graph_sim import summarize_text_line_diff, verbalize_single_dep  # noqa: E402
from temporal_noise import (  # noqa: E402
    ActionJob,
    compile_user_goal_graph_under_noise,
    canonical_dependency_signature,
    dependency_singles,
    get_action_dependency,
    graph_to_process,
    is_small_subtree,
    load_step2_tasks,
    rulebase_action_temporal_sequence_sequential,
    DEFAULT_RULEBASE_MAX_ATTEMPTS,
)


def resolve_path(path: Path) -> Path:
    return path if path.is_absolute() else REPO_ROOT / path


def load_json(path: Path) -> Any:
    return json.loads(resolve_path(path).read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    target = resolve_path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, indent=4, ensure_ascii=False) + "\n", encoding="utf-8")


def graph_signature(graph: Any) -> str:
    if not graph:
        return ""
    return json.dumps(graph, sort_keys=True, ensure_ascii=False)


def dependency_signature(dep: Any) -> str:
    if dep is None:
        return ""
    return json.dumps(dep, sort_keys=True, ensure_ascii=False)


def task_dep_params(task: dict[str, Any]) -> dict[str, Any]:
    original = task.get("original_sopbench") or {}
    params = copy.deepcopy(task.get("constraint_parameters") or {})
    params.update(copy.deepcopy(original.get("constraint_parameters") or {}))
    return params


def anchor_user_goal_graph(step2_task: dict[str, Any]) -> dict[str, Any]:
    original = step2_task.get("original_sopbench") or {}
    graph = original.get("directed_action_graph")
    return copy.deepcopy(graph) if isinstance(graph, dict) else {}


def verbalize_action_graph(
    domain: str,
    graph: Any,
    target_action: str,
    dep_params: dict[str, Any],
) -> str:
    if not isinstance(graph, dict) or not graph.get("nodes"):
        return ""
    process = graph_to_process(graph, target_action)
    if process is None:
        return ""
    from temporal_graph_sim import verbalize_process_tree  # noqa: WPS433

    return verbalize_process_tree(domain, process, dep_params)


def single_constraint_key(constraint_id: str, params: dict[str, Any]) -> str:
    return json.dumps(
        {"constraint_id": constraint_id, "params": params},
        sort_keys=True,
        ensure_ascii=False,
    )


def singles_counter(dep: Any) -> Counter[str]:
    counter: Counter[str] = Counter()
    for constraint_id, params in dependency_singles(dep) if dep is not None else []:
        counter[single_constraint_key(constraint_id, params)] += 1
    return counter


def singles_lookup(dep: Any) -> dict[str, tuple[str, dict[str, Any]]]:
    lookup: dict[str, tuple[str, dict[str, Any]]] = {}
    for constraint_id, params in dependency_singles(dep) if dep is not None else []:
        lookup[single_constraint_key(constraint_id, params)] = (constraint_id, params)
    return lookup


def verbalize_single_constraint(
    domain: str,
    constraint_id: str,
    params: dict[str, Any],
    dep_params: dict[str, Any],
) -> str:
    single = ("single", constraint_id, copy.deepcopy(params))
    return verbalize_single_dep(domain, single, dep_params).strip()


def unique_strings_preserve_order(items: list[str]) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        unique.append(item)
    return unique


def diff_dependency_constraints(
    before: Any,
    after: Any,
    *,
    domain: str,
    dep_params: dict[str, Any],
) -> dict[str, Any]:
    before_counter = singles_counter(before)
    after_counter = singles_counter(after)
    lookup = singles_lookup(before)
    lookup.update(singles_lookup(after))

    removed: list[str] = []
    added: list[str] = []
    for key in sorted(set(before_counter) | set(after_counter)):
        before_count = before_counter.get(key, 0)
        after_count = after_counter.get(key, 0)
        if before_count == after_count:
            continue
        constraint_id, params = lookup[key]
        text = verbalize_single_constraint(domain, constraint_id, params, dep_params)
        if after_count > before_count:
            added.append(text)
        else:
            removed.append(text)

    return {
        "unchanged": not removed and not added,
        "removed": unique_strings_preserve_order(removed),
        "added": unique_strings_preserve_order(added),
    }


def diff_action_graphs(
    before: Any,
    after: Any,
    *,
    domain: str,
    target_action: str,
    dep_params: dict[str, Any],
) -> dict[str, Any]:
    before_graph = before if isinstance(before, dict) else {}
    after_graph = after if isinstance(after, dict) else {}
    before_text = verbalize_action_graph(domain, before_graph, target_action, dep_params)
    after_text = verbalize_action_graph(domain, after_graph, target_action, dep_params)
    if not before_text and not after_text:
        unchanged = graph_signature(before_graph) == graph_signature(after_graph)
        return {"unchanged": unchanged, "removed": [], "added": []}
    return summarize_text_line_diff(before_text, after_text)


def format_diff_summary(*, subject: str, diff: dict[str, Any], intro: str | None = None) -> str:
    if diff.get("unchanged"):
        return f"{subject}: no change."
    removed = [str(item).strip() for item in (diff.get("removed") or []) if str(item).strip()]
    added = [str(item).strip() for item in (diff.get("added") or []) if str(item).strip()]
    if not removed and not added:
        return f"{subject}: structure changed (no diff lines captured)."

    lines = [intro or subject]
    if removed:
        lines.append("Removed:")
        lines.extend(f"• {item}" for item in removed)
    if added:
        lines.append("Added:")
        lines.extend(f"• {item}" for item in added)
    return "\n".join(lines)


def build_graph_delta(
    before: Any,
    after: Any,
    *,
    domain: str,
    target_action: str,
    dep_params: dict[str, Any],
    subject: str,
    intro: str | None = None,
) -> dict[str, Any]:
    before_graph = before if isinstance(before, dict) else {}
    after_graph = after if isinstance(after, dict) else {}
    before_sig = graph_signature(before_graph)
    after_sig = graph_signature(after_graph)
    changed = before_sig != after_sig
    diff = diff_action_graphs(
        before_graph,
        after_graph,
        domain=domain,
        target_action=target_action,
        dep_params=dep_params,
    )
    if not changed:
        diff = {"unchanged": True, "removed": [], "added": []}
    return {
        "graph_changed": changed,
        "before_signature": before_sig,
        "after_signature": after_sig,
        "nodes_before": len(before_graph.get("nodes") or []),
        "nodes_after": len(after_graph.get("nodes") or []),
        "connections_before": len(before_graph.get("connections") or []),
        "connections_after": len(after_graph.get("connections") or []),
        "diff": diff,
        "summary": format_diff_summary(subject=subject, diff=diff, intro=intro),
    }


def build_dependency_delta(
    before: Any,
    after: Any,
    *,
    domain: str,
    dep_params: dict[str, Any],
    subject: str,
    intro: str | None = None,
) -> dict[str, Any]:
    before_sig = dependency_signature(before)
    after_sig = dependency_signature(after)
    changed = before_sig != after_sig
    diff = diff_dependency_constraints(
        before,
        after,
        domain=domain,
        dep_params=dep_params,
    )
    if not changed:
        diff = {"unchanged": True, "removed": [], "added": []}
    return {
        "dependency_changed": changed,
        "before_signature": before_sig,
        "after_signature": after_sig,
        "before": copy.deepcopy(before),
        "after": copy.deepcopy(after),
        "diff": diff,
        "summary": format_diff_summary(subject=subject, diff=diff, intro=intro),
    }


def constraint_action(constraint: dict[str, Any]) -> str:
    return str(
        constraint.get("action")
        or constraint.get("anchor_action")
        or ""
    ).strip()


def ordered_actions(task: dict[str, Any]) -> list[str]:
    actions: list[str] = []
    seen: set[str] = set()
    for row in task.get("action_noise") or []:
        if not isinstance(row, dict):
            continue
        action = str(row.get("action") or "").strip()
        if action and action not in seen:
            actions.append(action)
            seen.add(action)
    for constraint in task.get("constraints") or []:
        if not isinstance(constraint, dict):
            continue
        action = constraint_action(constraint)
        if action and action not in seen:
            actions.append(action)
            seen.add(action)
    return actions


def compile_turn_user_goal_graph(
    step2_task: dict[str, Any],
    *,
    mutated_action: str,
    noisy_dependency: Any,
) -> tuple[dict[str, Any] | None, str | None]:
    try:
        compiled = compile_user_goal_graph_under_noise(
            task=step2_task,
            mutated_action=mutated_action,
            noisy_dependency=noisy_dependency,
        )
    except Exception as exc:  # noqa: BLE001
        return None, f"{type(exc).__name__}: {exc}"
    graph = compiled.get("graph")
    return (copy.deepcopy(graph) if isinstance(graph, dict) else None), None


def turn_from_noise_item(
    *,
    action: str,
    turn_index: int,
    noise: dict[str, Any],
    source_mac_constraint_uid: str,
) -> dict[str, Any]:
    return {
        "local_id": f"{action}::t{turn_index}",
        "action": action,
        "source_mac_constraint_uid": source_mac_constraint_uid,
        "text": str(noise.get("text") or "").strip(),
        "dependency": copy.deepcopy(noise.get("dependency")),
        "compiled_graph": copy.deepcopy(noise.get("compiled_graph")),
        "mutation": noise.get("mutation"),
        "scope": noise.get("scope"),
        "dependency_diff": copy.deepcopy(noise.get("dependency_diff")),
        "dependency_diff_from_anchor": copy.deepcopy(noise.get("dependency_diff_from_anchor")),
        "graph_changed": noise.get("graph_changed"),
        "validation": noise.get("validation"),
        "sequential_step": noise.get("sequential_step"),
        "generation_mode": noise.get("generation_mode"),
    }


def collect_action_turn_groups(task: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    seen_graphs: dict[str, set[str]] = defaultdict(set)

    for constraint in task.get("constraints") or []:
        if not isinstance(constraint, dict):
            continue
        action = constraint_action(constraint)
        if not action:
            continue
        anchor_uid = str(constraint.get("mac_constraint_uid") or "")
        for noise in constraint.get("temporal_noise") or []:
            if not isinstance(noise, dict):
                continue
            graph_sig = graph_signature(noise.get("compiled_graph"))
            if not graph_sig or graph_sig in seen_graphs[action]:
                continue
            seen_graphs[action].add(graph_sig)
            groups[action].append(
                turn_from_noise_item(
                    action=action,
                    turn_index=len(groups[action]) + 1,
                    noise={**noise, "generation_mode": "anchor_rewrite"},
                    source_mac_constraint_uid=anchor_uid,
                )
            )
    return dict(groups)


def action_seed(*, seed: int, task_uid: str, action: str) -> int:
    digest = hashlib.sha256(f"{seed}:{task_uid}:{action}".encode("utf-8")).digest()
    return int.from_bytes(digest[:4], "big")


def source_anchor_uid(step3_task: dict[str, Any], action: str) -> str:
    for constraint in step3_task.get("constraints") or []:
        if not isinstance(constraint, dict):
            continue
        if constraint_action(constraint) == action:
            return str(constraint.get("mac_constraint_uid") or "")
    return f"action:{action}"


def sequential_v2_noise_target(
    step2_task: dict[str, Any],
    action: str,
    *,
    seed: int,
) -> int:
    """Reduced chain depth for v3: large subtree 3-4, small subtree 0-1."""
    action_dep = get_action_dependency(step2_task, action)
    rng = random.Random(action_seed(seed=seed, task_uid=str(step2_task.get("mac_task_uid") or ""), action=action) + 17)
    if action_dep is not None and is_small_subtree(action_dep):
        return rng.choice([0, 1])
    return rng.choice([3, 4])


def collect_sequential_action_turn_groups(
    step2_task: dict[str, Any],
    step3_task: dict[str, Any],
    *,
    seed: int,
    max_attempts: int = DEFAULT_RULEBASE_MAX_ATTEMPTS,
) -> tuple[dict[str, list[dict[str, Any]]], list[str], dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    warnings: list[str] = []
    generation_stats: dict[str, Any] = {
        "actions": {},
        "total_target": 0,
        "total_step3_target": 0,
        "total_generated": 0,
        "chain_stopped_early": 0,
        "skipped_actions": 0,
        "noise_target_policy": "v3_reduced: large=3-4, small=0-1",
    }
    task_uid = str(step2_task.get("mac_task_uid") or "")
    task_existing_noisy: list[dict[str, Any]] = []
    action_order = ordered_actions(step3_task)

    for action in action_order:
        row = next(
            (
                item
                for item in (step3_task.get("action_noise") or [])
                if isinstance(item, dict) and str(item.get("action") or "") == action
            ),
            None,
        )
        if row is None:
            continue
        step3_noise_target = int(row.get("noise_target") or 0)
        noise_target = sequential_v2_noise_target(step2_task, action, seed=seed)
        generation_stats["total_target"] += noise_target
        generation_stats["total_step3_target"] = generation_stats.get("total_step3_target", 0) + step3_noise_target
        if noise_target <= 0:
            generation_stats["skipped_actions"] += 1
            generation_stats["actions"][action] = {
                "noise_target": noise_target,
                "step3_noise_target": step3_noise_target,
                "noise_generated": 0,
                "skipped": True,
            }
            continue

        job = ActionJob(
            ordinal=0,
            total=1,
            task=step2_task,
            task_index=int(step2_task.get("task_index") or 0),
            action=action,
            anchors=tuple(),
            noise_target=noise_target,
            task_seed=action_seed(seed=seed, task_uid=task_uid, action=action),
        )
        try:
            sequence, seq_warnings, validation = rulebase_action_temporal_sequence_sequential(
                job,
                task_existing_noisy=task_existing_noisy,
                max_attempts=max_attempts,
            )
        except Exception as exc:  # noqa: BLE001
            warnings.append(f"{task_uid}/{action}: sequential generation failed: {exc}")
            continue

        warnings.extend(seq_warnings)
        generated = [item for item in sequence if not item.get("is_anchor")]
        generation_stats["actions"][action] = {
            "noise_target": noise_target,
            "step3_noise_target": step3_noise_target,
            "noise_generated": len(generated),
            "validation": validation,
        }
        generation_stats["total_generated"] += len(generated)
        if len(generated) < noise_target:
            generation_stats["chain_stopped_early"] += 1

        anchor_uid = source_anchor_uid(step3_task, action)
        for index, noise in enumerate(generated, start=1):
            noise_payload = copy.deepcopy(noise)
            noise_payload["generation_mode"] = "sequential_chain"
            groups[action].append(
                turn_from_noise_item(
                    action=action,
                    turn_index=index,
                    noise=noise_payload,
                    source_mac_constraint_uid=anchor_uid,
                )
            )
            dep_sig = canonical_dependency_signature(noise.get("dependency"))
            if dep_sig:
                task_existing_noisy.append(
                    {
                        "dependency_signature": dep_sig,
                        "mac_constraint_uid": f"action:{action}",
                    }
                )

    return dict(groups), warnings, generation_stats


def action_anchor_baselines(task: dict[str, Any]) -> dict[str, dict[str, Any]]:
    baselines: dict[str, dict[str, Any]] = {}
    for constraint in task.get("constraints") or []:
        if not isinstance(constraint, dict):
            continue
        action = constraint_action(constraint)
        if not action or action in baselines:
            continue
        baselines[action] = {
            "dependency": copy.deepcopy(constraint.get("anchor_dependency")),
            "compiled_graph": copy.deepcopy(constraint.get("anchor_compiled_graph")),
        }
    return baselines


def attach_sequence_deltas(
    sequence: list[dict[str, Any]],
    *,
    step2_task: dict[str, Any],
    step3_task: dict[str, Any],
) -> list[dict[str, Any]]:
    domain = str(step2_task.get("domain") or "")
    user_goal = str(step2_task.get("user_goal") or "")
    dep_params = task_dep_params(step2_task)
    anchor_graph = anchor_user_goal_graph(step2_task)
    anchor_sig = graph_signature(anchor_graph)
    action_baselines = action_anchor_baselines(step3_task)

    enriched: list[dict[str, Any]] = []
    prev_graph: Any = None
    prev_dep: Any = None
    prev_user_goal_graph: Any = None
    prev_local_id: str | None = None

    for order, item in enumerate(sequence, start=1):
        entry = copy.deepcopy(item)
        entry["sequence_order"] = order
        action = str(entry.get("action") or "")
        mutation = str(entry.get("mutation") or "").strip()
        current_graph = entry.get("compiled_graph")
        current_dep = entry.get("dependency")

        action_subject = f"Executable graph for action `{action}`"
        if mutation:
            action_subject = f"Executable graph for action `{action}` ({mutation})"
        dep_subject = f"SOP dependency tree for action `{action}`"
        if mutation:
            dep_subject = f"SOP dependency tree for action `{action}` ({mutation})"

        action_baseline = action_baselines.get(action) or {}
        graph_before = (
            prev_graph
            if prev_graph is not None
            else action_baseline.get("compiled_graph")
        )
        dep_before = (
            prev_dep
            if prev_dep is not None
            else action_baseline.get("dependency")
        )

        graph_delta = build_graph_delta(
            graph_before,
            current_graph,
            domain=domain,
            target_action=action,
            dep_params=dep_params,
            subject=action_subject,
            intro=(
                None
                if prev_graph is not None
                else f"Changes to executable graph for `{action}` ({mutation}):"
                if mutation
                else f"Changes to executable graph for `{action}`:"
            ),
        )
        graph_delta["from_local_id"] = prev_local_id
        graph_delta["to_local_id"] = entry.get("local_id")
        entry["graph_delta"] = graph_delta

        dep_delta = build_dependency_delta(
            dep_before,
            current_dep,
            domain=domain,
            dep_params=dep_params,
            subject=dep_subject,
            intro=(
                None
                if prev_dep is not None
                else f"Changes to SOP dependency for `{action}` ({mutation}):"
                if mutation
                else f"Changes to SOP dependency for `{action}`:"
            ),
        )
        dep_delta["from_local_id"] = prev_local_id
        dep_delta["to_local_id"] = entry.get("local_id")
        entry["dependency_delta"] = dep_delta

        user_goal_graph, compile_error = compile_turn_user_goal_graph(
            step2_task,
            mutated_action=action,
            noisy_dependency=current_dep,
        )
        entry["user_goal_action_graph"] = user_goal_graph
        if compile_error:
            entry["user_goal_compile_error"] = compile_error

        user_goal_subject = f"User-goal executable graph (`{user_goal}`) under this SOP revision"
        if mutation:
            user_goal_subject = (
                f"User-goal executable graph (`{user_goal}`) after `{action}` revision ({mutation})"
            )
        user_goal_delta = build_graph_delta(
            prev_user_goal_graph if prev_user_goal_graph is not None else anchor_graph,
            user_goal_graph,
            domain=domain,
            target_action=user_goal,
            dep_params=dep_params,
            subject=user_goal_subject,
            intro=(
                None
                if prev_user_goal_graph is not None
                else f"Changes to `{user_goal}` vs task anchor after `{action}` revision ({mutation}):"
                if mutation
                else f"Changes to `{user_goal}` vs task anchor after `{action}` revision:"
            ),
        )
        user_goal_delta["from_local_id"] = prev_local_id
        user_goal_delta["to_local_id"] = entry.get("local_id")
        entry["user_goal_graph_delta"] = user_goal_delta

        user_goal_anchor_delta = build_graph_delta(
            anchor_graph,
            user_goal_graph,
            domain=domain,
            target_action=user_goal,
            dep_params=dep_params,
            subject=f"User-goal graph vs task anchor (`{user_goal}`)",
        )
        entry["user_goal_graph_changed_from_anchor"] = graph_signature(user_goal_graph) != anchor_sig
        entry["user_goal_graph_anchor_delta"] = user_goal_anchor_delta

        enriched.append(entry)
        prev_graph = current_graph
        prev_dep = current_dep
        prev_user_goal_graph = user_goal_graph
        prev_local_id = str(entry.get("local_id") or "")

    return enriched


def build_task_sequence(
    task: dict[str, Any],
    step2_task: dict[str, Any],
    *,
    rng: random.Random,
    generation_mode: str = "anchor_rewrite",
    seed: int = 13,
    sequential_warnings: list[str] | None = None,
    sequential_stats: dict[str, Any] | None = None,
) -> dict[str, Any]:
    task_uid = str(task.get("mac_task_uid") or "")
    user_goal = str(step2_task.get("user_goal") or "")

    if generation_mode == "sequential_chain":
        action_groups, seq_warnings, seq_stats = collect_sequential_action_turn_groups(
            step2_task,
            task,
            seed=seed,
        )
        if sequential_warnings is not None:
            sequential_warnings.extend(seq_warnings)
        if sequential_stats is not None:
            sequential_stats[task_uid] = seq_stats
    else:
        action_groups = collect_action_turn_groups(task)
    action_order = ordered_actions(task)
    extra_actions = sorted(set(action_groups) - set(action_order))
    ordered = action_order + extra_actions

    source_graphs: list[list[dict[str, Any]]] = []
    source_actions: list[str] = []
    raw_turn_count = 0
    for action in ordered:
        turns = action_groups.get(action) or []
        if not turns:
            continue
        raw_turn_count += len(turns)
        source_actions.append(action)
        source_graphs.append(turns)

    merged = merge_constraint_sequence(source_graphs, rng=rng)
    sequence = attach_sequence_deltas(merged, step2_task=step2_task, step3_task=task)

    user_goal_changed_from_anchor = sum(
        1 for step in sequence if step.get("user_goal_graph_changed_from_anchor")
    )

    return {
        "mac_task_uid": task_uid,
        "domain": task.get("domain"),
        "user_goal": user_goal,
        "task_description": task.get("task_description"),
        "anchor_user_goal_action_graph": anchor_user_goal_graph(step2_task),
        "source_action_count": len(source_actions),
        "source_actions": source_actions,
        "raw_turn_count": raw_turn_count,
        "sequence_turn_count": len(sequence),
        "user_goal_graph_changed_turn_count": user_goal_changed_from_anchor,
        "action_noise": copy.deepcopy(task.get("action_noise") or []),
        "generation_mode": generation_mode,
        "temporal_sequence": sequence,
    }


def index_step2_tasks(tasks: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    indexed: dict[str, dict[str, Any]] = {}
    for task in tasks:
        if not isinstance(task, dict):
            continue
        uid = str(task.get("mac_task_uid") or "").strip()
        if uid:
            indexed[uid] = task
    return indexed


def build_all_task_sequences(
    tasks: list[dict[str, Any]],
    step2_by_uid: dict[str, dict[str, Any]],
    *,
    seed: int,
    generation_mode: str = "anchor_rewrite",
) -> tuple[list[dict[str, Any]], dict[str, Any], list[str]]:
    assembled: list[dict[str, Any]] = []
    warnings: list[str] = []
    sequential_stats_by_task: dict[str, Any] = {}
    sequence_lengths: list[int] = []
    source_action_counts: list[int] = []
    raw_turn_counts: list[int] = []
    graph_changed_steps = 0
    user_goal_changed_steps = 0
    user_goal_compile_errors = 0
    total_steps = 0
    dependency_diff_lines: list[int] = []
    anchor_diff_lines: list[int] = []

    for task in tasks:
        if not isinstance(task, dict):
            continue
        task_uid = str(task.get("mac_task_uid") or "")
        step2_task = step2_by_uid.get(task_uid)
        if step2_task is None:
            warnings.append(f"missing step2 task for {task_uid}; skipped")
            continue
        rng = random.Random(f"{seed}:{task_uid}")
        row = build_task_sequence(
            task,
            step2_task,
            rng=rng,
            generation_mode=generation_mode,
            seed=seed,
            sequential_warnings=warnings,
            sequential_stats=sequential_stats_by_task,
        )
        assembled.append(row)
        sequence_lengths.append(int(row.get("sequence_turn_count") or 0))
        source_action_counts.append(int(row.get("source_action_count") or 0))
        raw_turn_counts.append(int(row.get("raw_turn_count") or 0))
        for step in row.get("temporal_sequence") or []:
            total_steps += 1
            if (step.get("graph_delta") or {}).get("graph_changed"):
                graph_changed_steps += 1
            if step.get("user_goal_graph_changed_from_anchor"):
                user_goal_changed_steps += 1
            if step.get("user_goal_compile_error"):
                user_goal_compile_errors += 1
            dep_diff = step.get("dependency_diff") or {}
            dependency_diff_lines.append(
                len(dependency_singles(dep_diff.get("before")))
                + len(dependency_singles(dep_diff.get("after")))
            )
            anchor_diff = step.get("dependency_diff_from_anchor") or dep_diff
            anchor_diff_lines.append(
                len(dependency_singles(anchor_diff.get("before")))
                + len(dependency_singles(anchor_diff.get("after")))
            )

    def _mean(values: list[int | float]) -> float:
        return float(statistics.mean(values)) if values else 0.0

    noise_target_total = 0
    noise_generated_total = 0
    if generation_mode == "sequential_chain":
        noise_target_total = sum(
            stats.get("total_target", 0) for stats in sequential_stats_by_task.values()
        )
        noise_generated_total = sum(
            stats.get("total_generated", 0) for stats in sequential_stats_by_task.values()
        )
    else:
        for task in tasks:
            for row in task.get("action_noise") or []:
                if not isinstance(row, dict):
                    continue
                noise_target_total += int(row.get("noise_target") or 0)
                noise_generated_total += int(row.get("noise_generated") or 0)

    summary = {
        "task_count": len(assembled),
        "generation_mode": generation_mode,
        "total_turns_in_sequences": sum(sequence_lengths),
        "total_raw_turns_before_merge": sum(raw_turn_counts),
        "avg_turns_per_task": _mean(sequence_lengths),
        "avg_source_actions_per_task": _mean(source_action_counts),
        "sequence_turn_count_distribution": dict(Counter(sequence_lengths)),
        "source_action_count_distribution": dict(Counter(source_action_counts)),
        "graph_changed_step_ratio": (graph_changed_steps / total_steps) if total_steps else 0.0,
        "user_goal_graph_changed_from_anchor_ratio": (
            user_goal_changed_steps / total_steps
        ) if total_steps else 0.0,
        "user_goal_compile_error_count": user_goal_compile_errors,
        "noise_fill_rate": (
            noise_generated_total / noise_target_total if noise_target_total else None
        ),
        "avg_dependency_diff_single_count": _mean(dependency_diff_lines),
        "avg_anchor_diff_single_count": _mean(anchor_diff_lines),
        "sequential_chain_stopped_early": (
            sum(
                stats.get("chain_stopped_early", 0)
                for stats in sequential_stats_by_task.values()
            )
            if generation_mode == "sequential_chain"
            else None
        ),
        "sequential_skipped_actions": (
            sum(
                stats.get("skipped_actions", 0)
                for stats in sequential_stats_by_task.values()
            )
            if generation_mode == "sequential_chain"
            else None
        ),
        "sequential_step3_target_total": (
            sum(
                stats.get("total_step3_target", 0)
                for stats in sequential_stats_by_task.values()
            )
            if generation_mode == "sequential_chain"
            else None
        ),
        "sequential_adjusted_target_total": (
            noise_target_total if generation_mode == "sequential_chain" else None
        ),
        "sequential_generated_total": (
            noise_generated_total if generation_mode == "sequential_chain" else None
        ),
        "noise_target_policy": (
            sequential_stats_by_task.get(
                next(iter(sequential_stats_by_task), ""),
                {},
            ).get("noise_target_policy")
            if generation_mode == "sequential_chain" and sequential_stats_by_task
            else None
        ),
        "seed": seed,
    }
    if generation_mode == "sequential_chain":
        summary["sequential_generation"] = sequential_stats_by_task
    return assembled, summary, warnings


def dependency_state_keys(tasks: list[dict[str, Any]]) -> set[str]:
    keys: set[str] = set()
    for task in tasks:
        for step in task.get("temporal_sequence") or []:
            action = str(step.get("action") or "")
            dep_sig = dependency_signature(step.get("dependency"))
            if action and dep_sig:
                keys.add(f"{action}::{dep_sig}")
    return keys


def compare_generation_modes(
    v1_tasks: list[dict[str, Any]],
    v1_summary: dict[str, Any],
    v2_tasks: list[dict[str, Any]],
    v2_summary: dict[str, Any],
) -> dict[str, Any]:
    v1_keys = dependency_state_keys(v1_tasks)
    v2_keys = dependency_state_keys(v2_tasks)
    overlap = len(v1_keys & v2_keys)
    union = len(v1_keys | v2_keys)
    v1_fill = v1_summary.get("noise_fill_rate")
    v2_fill = v2_summary.get("noise_fill_rate")
    recommendation = "sequential_chain"
    reasons: list[str] = []

    if v2_fill is not None and v1_fill is not None and v2_fill + 0.02 < v1_fill:
        recommendation = "anchor_rewrite"
        reasons.append(f"sequential fill rate lower ({v2_fill:.3f} vs {v1_fill:.3f})")
    else:
        reasons.append(f"sequential fill comparable or better ({v2_fill} vs {v1_fill})")

    v1_step_diff = v1_summary.get("avg_dependency_diff_single_count") or 0
    v2_step_diff = v2_summary.get("avg_dependency_diff_single_count") or 0
    if v2_step_diff < v1_step_diff:
        reasons.append("sequential step diffs are smaller (better for user-turn clarifications)")
    else:
        reasons.append("sequential step diffs are not smaller than anchor-rewrite diffs")

    v1_ug = v1_summary.get("user_goal_graph_changed_from_anchor_ratio") or 0
    v2_ug = v2_summary.get("user_goal_graph_changed_from_anchor_ratio") or 0
    if v2_ug <= v1_ug + 0.05:
        reasons.append("sequential user_goal impact is not worse")
    else:
        recommendation = "anchor_rewrite"
        reasons.append("sequential changes user_goal graph more often")

    return {
        "v1": {"generation_mode": v1_summary.get("generation_mode"), "summary": v1_summary},
        "v2": {"generation_mode": v2_summary.get("generation_mode"), "summary": v2_summary},
        "dependency_state_overlap": {
            "shared": overlap,
            "union": union,
            "jaccard": (overlap / union) if union else None,
        },
        "turn_delta": {
            "v1_total_turns": v1_summary.get("total_turns_in_sequences"),
            "v2_total_turns": v2_summary.get("total_turns_in_sequences"),
        },
        "recommendation": recommendation,
        "reasons": reasons,
        "interpretation": {
            "anchor_rewrite": (
                "Each noise variant mutates from the action anchor; dependency_diff is anchor→noise."
            ),
            "sequential_chain": (
                "Each action builds g1=mut(g0), g2=mut(g1), ...; dependency_diff is step-wise."
            ),
        },
    }


def dependency_delta_summary(
    *,
    action: str,
    mutation: str,
    from_local_id: Any,
    diff: dict[str, Any],
) -> str:
    dep_subject = f"SOP dependency tree for action `{action}`"
    if mutation:
        dep_subject += f" ({mutation})"
    if from_local_id:
        return format_diff_summary(subject=dep_subject, diff=diff, intro=None)
    intro = (
        f"Changes to SOP dependency for `{action}` ({mutation}):"
        if mutation
        else f"Changes to SOP dependency for `{action}`:"
    )
    return format_diff_summary(subject=dep_subject, diff=diff, intro=intro)


def turn_delta_record(
    step: dict[str, Any],
    *,
    domain: str,
    dep_params: dict[str, Any],
) -> dict[str, Any] | None:
    """Extract semantic dependency change between this turn and its sequence predecessor."""
    dep_delta = step.get("dependency_delta")
    if not isinstance(dep_delta, dict):
        return None
    diff = diff_dependency_constraints(
        dep_delta.get("before"),
        dep_delta.get("after"),
        domain=domain,
        dep_params=dep_params,
    )
    action = str(step.get("action") or "")
    mutation = str(step.get("mutation") or "").strip()
    return {
        "sequence_order": step.get("sequence_order"),
        "local_id": step.get("local_id"),
        "action": action,
        "mutation": mutation or None,
        "scope": step.get("scope"),
        "generation_mode": step.get("generation_mode"),
        "source_mac_constraint_uid": step.get("source_mac_constraint_uid"),
        "from_local_id": dep_delta.get("from_local_id"),
        "to_local_id": dep_delta.get("to_local_id"),
        "dependency_changed": dep_delta.get("dependency_changed"),
        "before_signature": dep_delta.get("before_signature"),
        "after_signature": dep_delta.get("after_signature"),
        "diff": diff,
        "summary": dependency_delta_summary(
            action=action,
            mutation=mutation,
            from_local_id=dep_delta.get("from_local_id"),
            diff=diff,
        ),
    }


def slim_step4_summary(summary: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(summary, dict):
        return None
    slim = copy.deepcopy(summary)
    slim.pop("sequential_generation", None)
    return slim


def build_temporal_delta_payload(
    *,
    tasks: list[dict[str, Any]],
    generation_mode: str,
    source_step4: str,
    step2_by_uid: dict[str, dict[str, Any]],
    source_step2: str | None = None,
    source_step3: str | None = None,
    summary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    delta_tasks: list[dict[str, Any]] = []
    turn_count = 0
    for task in tasks:
        if not isinstance(task, dict):
            continue
        task_uid = str(task.get("mac_task_uid") or "")
        step2_task = step2_by_uid.get(task_uid) or {}
        domain = str(task.get("domain") or step2_task.get("domain") or "")
        dep_params = task_dep_params(step2_task) if step2_task else {}
        turns: list[dict[str, Any]] = []
        for step in task.get("temporal_sequence") or []:
            if not isinstance(step, dict):
                continue
            record = turn_delta_record(step, domain=domain, dep_params=dep_params)
            if record is None:
                continue
            turns.append(record)
        if not turns:
            continue
        turn_count += len(turns)
        delta_tasks.append(
            {
                "mac_task_uid": task.get("mac_task_uid"),
                "domain": task.get("domain"),
                "user_goal": task.get("user_goal"),
                "generation_mode": task.get("generation_mode") or generation_mode,
                "sequence_turn_count": task.get("sequence_turn_count"),
                "turns": turns,
            }
        )
    return {
        "schema_version": "MACConstructStep4TemporalSemanticDeltaV2",
        "generation_mode": generation_mode,
        "source_step4": source_step4,
        "source_step2": source_step2,
        "source_step3": source_step3,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "summary": {
            "task_count": len(delta_tasks),
            "turn_count": turn_count,
            "source_summary": slim_step4_summary(summary),
        },
        "tasks": delta_tasks,
    }


def write_step4_delta_payload(
    *,
    path: Path,
    tasks: list[dict[str, Any]],
    generation_mode: str,
    source_step4: Path,
    step2_by_uid: dict[str, dict[str, Any]],
    source_step2: Path | None = None,
    source_step3: Path | None = None,
    summary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = build_temporal_delta_payload(
        tasks=tasks,
        generation_mode=generation_mode,
        source_step4=str(source_step4),
        step2_by_uid=step2_by_uid,
        source_step2=str(source_step2) if source_step2 is not None else None,
        source_step3=str(source_step3) if source_step3 is not None else None,
        summary=summary,
    )
    write_json(path, payload)
    meta_path = path.with_suffix(path.suffix + ".meta.json")
    write_json(meta_path, {"summary": payload["summary"], "tasks_output": str(path)})
    return payload


def export_delta_from_step4(
    step4_path: Path,
    *,
    delta_output: Path,
    step2_by_uid: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    step4 = load_json(step4_path)
    if not isinstance(step4, dict) or not isinstance(step4.get("tasks"), list):
        raise ValueError(f"Expected step4 object with tasks[] in {step4_path}")
    return write_step4_delta_payload(
        path=resolve_path(delta_output),
        tasks=step4["tasks"],
        generation_mode=str(step4.get("generation_mode") or "unknown"),
        source_step4=step4_path,
        step2_by_uid=step2_by_uid,
        source_step2=Path(step4.get("source_step2") or DEFAULT_STEP2),
        source_step3=Path(step4.get("source_step3") or DEFAULT_STEP3),
        summary=step4.get("summary"),
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--step2-input", type=Path, default=DEFAULT_STEP2)
    parser.add_argument("--step3-input", type=Path, default=DEFAULT_STEP3)
    parser.add_argument("--step4-output", type=Path, default=DEFAULT_STEP4)
    parser.add_argument(
        "--generation-mode",
        choices=("anchor_rewrite", "sequential_chain", "both"),
        default="anchor_rewrite",
        help="anchor_rewrite=v1 from step3; sequential_chain=v2; both writes v1+v2+comparison.",
    )
    parser.add_argument("--step4-output-v2", type=Path, default=DEFAULT_STEP4_V2)
    parser.add_argument(
        "--step4-output-v3",
        type=Path,
        default=DEFAULT_STEP4_V3,
        help="Output for sequential_chain with fixed validator (v3).",
    )
    parser.add_argument("--compare-output", type=Path, default=DEFAULT_COMPARE_OUTPUT)
    parser.add_argument(
        "--delta-output",
        type=Path,
        default=DEFAULT_STEP4_DELTA,
        help="Write adjacent-turn semantic dependency_delta sidecar JSON.",
    )
    parser.add_argument(
        "--export-delta-only",
        type=Path,
        default=None,
        metavar="STEP4_JSON",
        help="Export semantic dependency_delta from an existing step4 file and exit.",
    )
    parser.add_argument("--seed", type=int, default=13, help="Seed for per-task shuffle/merge.")
    parser.add_argument("--limit", type=int, default=None, help="Process at most N tasks.")
    return parser.parse_args()


def write_step4_payload(
    *,
    path: Path,
    generation_mode: str,
    source_step2: Path,
    source_step3: Path,
    summary: dict[str, Any],
    tasks: list[dict[str, Any]],
) -> None:
    schema = (
        "MACConstructStep4TemporalSequenceV3Sequential"
        if generation_mode == "sequential_chain"
        else "MACConstructStep4TemporalSequenceV2"
    )
    payload = {
        "schema_version": schema,
        "generation_mode": generation_mode,
        "source_step2": str(source_step2),
        "source_step3": str(source_step3),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "summary": summary,
        "tasks": tasks,
    }
    write_json(path, payload)
    meta_path = path.with_suffix(path.suffix + ".meta.json")
    write_json(meta_path, {"summary": summary, "tasks_output": str(path)})


def main() -> int:
    args = parse_args()
    if args.export_delta_only is not None:
        step2_by_uid = index_step2_tasks(load_step2_tasks(resolve_path(args.step2_input)))
        payload = export_delta_from_step4(
            resolve_path(args.export_delta_only),
            delta_output=args.delta_output,
            step2_by_uid=step2_by_uid,
        )
        out_path = resolve_path(args.delta_output)
        print(
            f"exported semantic dependency_delta for {payload['summary']['turn_count']} turn(s) "
            f"across {payload['summary']['task_count']} task(s) to {out_path}"
        )
        return 0

    step3_path = resolve_path(args.step3_input)
    step2_tasks = load_step2_tasks(resolve_path(args.step2_input))
    step2_by_uid = index_step2_tasks(step2_tasks)

    tasks = load_json(step3_path)
    if not isinstance(tasks, list):
        raise ValueError(f"Expected top-level JSON array in {step3_path}")
    if args.limit is not None:
        tasks = tasks[: max(0, int(args.limit))]

    modes = ["anchor_rewrite", "sequential_chain"] if args.generation_mode == "both" else [args.generation_mode]

    v1_tasks: list[dict[str, Any]] | None = None
    v1_summary: dict[str, Any] | None = None
    v2_tasks: list[dict[str, Any]] | None = None
    v2_summary: dict[str, Any] | None = None

    for mode in modes:
        assembled, summary, warnings = build_all_task_sequences(
            tasks,
            step2_by_uid,
            seed=args.seed,
            generation_mode=mode,
        )
        if mode == "anchor_rewrite":
            v1_tasks, v1_summary = assembled, summary
            out_path = resolve_path(args.step4_output)
        else:
            v2_tasks, v2_summary = assembled, summary
            out_path = resolve_path(args.step4_output_v3)

        write_step4_payload(
            path=out_path,
            generation_mode=mode,
            source_step2=args.step2_input,
            source_step3=args.step3_input,
            summary=summary,
            tasks=assembled,
        )
        delta_path = resolve_path(args.delta_output)
        delta_payload = write_step4_delta_payload(
            path=delta_path,
            tasks=assembled,
            generation_mode=mode,
            source_step4=out_path,
            step2_by_uid=step2_by_uid,
            source_step2=resolve_path(args.step2_input),
            source_step3=step3_path,
            summary=summary,
        )
        meta_path = out_path.with_suffix(out_path.suffix + ".meta.json")
        write_json(meta_path, {"summary": summary, "tasks_output": str(out_path), "warnings": warnings})
        if warnings:
            warning_path = out_path.with_suffix(out_path.suffix + ".warning")
            write_json(warning_path, {"warnings": warnings})

        print(
            f"[{mode}] wrote {summary['task_count']} task sequence(s) to {out_path}; "
            f"total_turns={summary['total_turns_in_sequences']}, "
            f"fill={summary.get('noise_fill_rate')}, "
            f"avg_step_diff={summary.get('avg_dependency_diff_single_count'):.2f}, "
            f"user_goal_changed={summary.get('user_goal_graph_changed_from_anchor_ratio'):.3f}"
        )
        print(
            f"[{mode}] wrote semantic dependency_delta sidecar ({delta_payload['summary']['turn_count']} turns) "
            f"to {delta_path}"
        )

    if args.generation_mode == "both" and v1_tasks and v2_tasks and v1_summary and v2_summary:
        comparison = compare_generation_modes(v1_tasks, v1_summary, v2_tasks, v2_summary)
        compare_path = resolve_path(args.compare_output)
        write_json(
            compare_path,
            {
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "comparison": comparison,
            },
        )
        print(f"comparison written to {compare_path}")
        print(f"recommendation: {comparison['recommendation']}")
        for reason in comparison.get("reasons") or []:
            print(f"  - {reason}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
