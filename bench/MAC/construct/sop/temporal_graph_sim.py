#!/usr/bin/env python3
"""Dry-run simulator for SOPBench native graph changes behind MAC noise constraints.

Mutates native action dependency structures (flip and/or, delete node, add OR
branch), projects per-seed local process snapshots, and prints whether each seed
executable changed.

Final native graph must match SOPBench; intermediate noise graphs may differ
widely (including flip of root AND), since user turns can walk back to the
anchor constraint state.
"""

from __future__ import annotations

import argparse
import copy
import importlib
import json
import os
import random
import re
import string
import time
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from filter_sop import ensure_sopbench_imports, list_to_tuple

REPO_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_STEP2 = Path("bench/MAC/sopbench/mid_data/eval_step2_anchors.json")
DEFAULT_ACTION_ADD_SETS = Path("bench/MAC/sopbench/mid_data/action_add_sets.json")
DEFAULT_ENV_FILE = Path("bench/.env")

LogicKind = str  # "and" | "or"


@dataclass
class DirectedActionGraph:
    nodes: list[Any]
    connections: list[list[int]]

    def copy(self) -> DirectedActionGraph:
        return DirectedActionGraph(copy.deepcopy(self.nodes), copy.deepcopy(self.connections))

    def children_of(self, index: int) -> list[int]:
        return sorted({b for a, b in self.connections if a == index})

    def parents_of(self, index: int) -> list[int]:
        return sorted({a for a, b in self.connections if b == index})

    def logic_node_indices(self) -> list[int]:
        return [
            index
            for index, node in enumerate(self.nodes)
            if isinstance(node, str) and node in ("and", "or")
        ]

    def tool_node_indices(self) -> list[int]:
        indices: list[int] = []
        for index, node in enumerate(self.nodes):
            if isinstance(node, list) and node:
                indices.append(index)
        return indices

    def flip_logic(self, index: int) -> str | None:
        node = self.nodes[index]
        if not isinstance(node, str) or node not in ("and", "or"):
            return None
        new_kind: LogicKind = "or" if node == "and" else "and"
        self.nodes[index] = new_kind
        return f"flip [{index}] {node} -> {new_kind}"

    def _drop_node_once(self, index: int) -> dict[int, int | None]:
        if index < 0 or index >= len(self.nodes):
            return {}
        old_to_new: dict[int, int | None] = {}
        new_nodes: list[Any] = []
        for old_index, node in enumerate(self.nodes):
            if old_index == index:
                old_to_new[old_index] = None
                continue
            old_to_new[old_index] = len(new_nodes)
            new_nodes.append(node)

        new_connections: list[list[int]] = []
        for parent, child in self.connections:
            if parent == index or child == index:
                continue
            new_parent = old_to_new.get(parent)
            new_child = old_to_new.get(child)
            if new_parent is None or new_child is None:
                continue
            new_connections.append([new_parent, new_child])

        self.nodes = new_nodes
        self.connections = new_connections
        return old_to_new

    def _compose_remaps(
        self, left: dict[int, int | None], right: dict[int, int | None]
    ) -> dict[int, int | None]:
        composed: dict[int, int | None] = {}
        for old_index, mapped in left.items():
            if mapped is None:
                composed[old_index] = None
            else:
                composed[old_index] = right.get(mapped, mapped)
        return composed

    def delete_node(self, index: int) -> tuple[str | None, dict[int, int | None]]:
        if index < 0 or index >= len(self.nodes):
            return None, {}
        if index == 0:
            return None, {}
        label = node_label(self.nodes[index], index)
        total_remap = self._drop_node_once(index)

        changed = True
        while changed:
            changed = False
            for node_index, node in list(enumerate(self.nodes)):
                if not isinstance(node, str) or node not in ("and", "or"):
                    continue
                if self.children_of(node_index):
                    continue
                total_remap = self._compose_remaps(total_remap, self._drop_node_once(node_index))
                changed = True
                break

        changed = True
        while changed:
            changed = False
            for node_index, node in list(enumerate(self.nodes)):
                if not isinstance(node, str) or node not in ("and", "or"):
                    continue
                kids = self.children_of(node_index)
                if len(kids) != 1:
                    continue
                child = kids[0]
                parents = self.parents_of(node_index)
                self.connections = [
                    edge
                    for edge in self.connections
                    if edge[0] != node_index and edge[1] != node_index
                ]
                for parent in parents:
                    self.connections.append([parent, child])
                total_remap = self._compose_remaps(total_remap, self._drop_node_once(node_index))
                changed = True
                break

        return f"delete [{index}] {label}", total_remap

    def add_or_branch(self, or_index: int, tool: str, params: dict[str, Any]) -> str | None:
        if or_index < 0 or or_index >= len(self.nodes):
            return None
        if self.nodes[or_index] != "or":
            return None
        for child in self.children_of(or_index):
            node = self.nodes[child]
            if isinstance(node, list) and node and str(node[0]) == tool:
                return None
        new_index = len(self.nodes)
        self.nodes.append([tool, copy.deepcopy(params)])
        self.connections.append([or_index, new_index])
        return f"add [or:{or_index}] {node_label(self.nodes[new_index], new_index)}"

    def to_process(self, index: int, *, _stack: set[int] | None = None) -> Any:
        stack = _stack or set()
        if index in stack:
            return None
        stack.add(index)
        node = self.nodes[index]
        if isinstance(node, list) and node:
            tool = str(node[0])
            params = node[1] if len(node) > 1 else {}
            if not isinstance(params, dict):
                params = {}
            return ["single", tool, copy.deepcopy(params)]
        if isinstance(node, str) and node in ("and", "or"):
            parts = [
                proc
                for child in self.children_of(index)
                if (proc := self.to_process(child, _stack=set(stack))) is not None
            ]
            if not parts:
                return None
            if len(parts) == 1:
                return parts[0]
            return [node, parts]
        return None

    def global_merge_process(self) -> Any:
        """Process tree required before the target action (root node 0)."""
        kids = self.children_of(0)
        if not kids:
            return None
        if len(kids) == 1:
            return self.to_process(kids[0])
        return ["and", [self.to_process(k) for k in kids if self.to_process(k) is not None]]


def node_label(node: Any, index: int) -> str:
    if isinstance(node, str):
        return f"{node}"
    if isinstance(node, list) and node:
        tool = node[0]
        params = node[1] if len(node) > 1 else {}
        if isinstance(params, dict) and params:
            arg_str = ", ".join(f"{key}={value}" for key, value in params.items())
            return f"{tool}({arg_str})"
        return f"{tool}()"
    return repr(node)


def normalize_process_tree(process: Any) -> Any:
    if process is None:
        return None
    if not isinstance(process, list) or not process:
        return None
    kind = str(process[0])
    if kind == "single":
        name = str(process[1]) if len(process) > 1 else ""
        params = process[2] if len(process) > 2 else {}
        if not isinstance(params, dict):
            params = {}
        normalized = tuple(sorted((str(k), json.dumps(v, sort_keys=True)) for k, v in params.items()))
        return ("single", name, normalized)
    if kind in ("and", "or", "chain", "gate"):
        children = process[1] if len(process) > 1 else []
        normalized = tuple(
            normalize_process_tree(part)
            for part in (children if isinstance(children, list) else [])
            if normalize_process_tree(part) is not None
        )
        if kind in ("and", "or"):
            normalized = tuple(sorted(normalized, key=lambda part: json.dumps(part, sort_keys=True)))
        return (kind, normalized)
    return None


def process_signature(process: Any) -> str:
    return json.dumps(normalize_process_tree(process), sort_keys=True)


def anchor_target_process(anchor: dict[str, Any]) -> Any:
    metadata = anchor.get("metadata") or {}
    proc = metadata.get("constraint_process")
    if proc:
        return copy.deepcopy(proc)
    link = metadata.get("constraint_link")
    if isinstance(link, list) and link:
        tool = str(link[0])
        params = link[1] if len(link) > 1 else {}
        if not isinstance(params, dict):
            params = {}
        return ["single", tool, copy.deepcopy(params)]
    return None


def process_tools(process: Any) -> set[str]:
    tools: set[str] = set()
    if not process or not isinstance(process, list):
        return tools
    kind = str(process[0])
    if kind == "single" and len(process) > 1:
        tools.add(str(process[1]))
    elif kind in ("and", "or", "chain") and len(process) > 1:
        for part in process[1]:
            tools |= process_tools(part)
    return tools


def remap_node_indices(
    node_index_by_uid: dict[str, int | None],
    remap: dict[int, int | None],
) -> None:
    for uid, node_index in list(node_index_by_uid.items()):
        if node_index is None:
            continue
        node_index_by_uid[uid] = remap.get(node_index, node_index)


def resolve_node_index(
    graph: DirectedActionGraph,
    anchor: dict[str, Any],
    cached: int | None,
    *,
    target_process: Any | None = None,
) -> int | None:
    target = (
        copy.deepcopy(target_process)
        if target_process is not None
        else anchor_target_process(anchor)
    )
    if cached is not None and 0 <= cached < len(graph.nodes):
        proc = graph.to_process(cached)
        if target is not None and proc is not None:
            if process_signature(proc) == process_signature(target):
                return cached
            if (
                isinstance(target, list)
                and target
                and str(target[0]) == "single"
                and isinstance(proc, list)
                and proc
                and str(proc[0]) == "single"
                and str(proc[1]) == str(target[1])
            ):
                target_params = target[2] if len(target) > 2 else {}
                proc_params = proc[2] if len(proc) > 2 else {}
                if isinstance(target_params, dict) and isinstance(proc_params, dict):
                    if all(proc_params.get(key) == value for key, value in target_params.items()):
                        return cached
    return find_anchor_node_index(graph, anchor, target_process=target)


def find_anchor_node_index(
    graph: DirectedActionGraph,
    anchor: dict[str, Any],
    *,
    target_process: Any | None = None,
) -> int | None:
    target = (
        copy.deepcopy(target_process)
        if target_process is not None
        else anchor_target_process(anchor)
    )
    if target is None:
        return None

    target_sig = process_signature(target)
    for index in range(len(graph.nodes)):
        proc = graph.to_process(index)
        if proc is not None and process_signature(proc) == target_sig:
            return index

    if isinstance(target, list) and target and str(target[0]) == "single":
        tool = str(target[1]) if len(target) > 1 else ""
        params = target[2] if len(target) > 2 else {}
        if not isinstance(params, dict):
            params = {}
        for index in graph.tool_node_indices():
            node = graph.nodes[index]
            if not isinstance(node, list) or str(node[0]) != tool:
                continue
            node_params = node[1] if len(node) > 1 else {}
            if not isinstance(node_params, dict):
                node_params = {}
            if all(node_params.get(key) == value for key, value in params.items()):
                return index

    target_tools = process_tools(target)
    for index in graph.logic_node_indices():
        proc = graph.to_process(index)
        if proc is None:
            continue
        if process_signature(proc) == target_sig:
            return index
        if process_tools(proc) == target_tools:
            return index

    return None


def build_anchor_graph_baseline(
    anchor_graph: DirectedActionGraph,
    anchors: list[dict[str, Any]],
    *,
    action: str,
) -> tuple[dict[str, Any], dict[str, int | None]]:
    """Snapshot anchor executable state from the SOPBench directed_action_graph."""
    anchor_process_by_uid: dict[str, Any] = {}
    node_index_by_uid: dict[str, int | None] = {}
    for anchor in anchors:
        if str(anchor.get("action") or "") != action:
            continue
        uid = str(anchor.get("mac_constraint_uid") or "")
        node_index = find_anchor_node_index(anchor_graph, anchor)
        proc = anchor_graph.to_process(node_index) if node_index is not None else None
        if proc is None:
            proc = anchor_target_process(anchor)
        anchor_process_by_uid[uid] = copy.deepcopy(proc)
        node_index_by_uid[uid] = find_anchor_node_index(
            anchor_graph,
            anchor,
            target_process=anchor_process_by_uid[uid],
        )
    return anchor_process_by_uid, node_index_by_uid


@dataclass
class AnchorProjection:
    mac_constraint_uid: str
    constraint_id: str
    action: str
    anchor_text: str
    node_index: int | None
    anchor_process: Any
    current_process: Any

    @property
    def changed(self) -> bool:
        return process_signature(self.anchor_process) != process_signature(self.current_process)


@dataclass
class MutationStep:
    step: int
    mutation: str
    changed_anchors: list[str]
    global_changed: bool
    projections: list[AnchorProjection]


def build_projections(
    graph: DirectedActionGraph,
    anchors: list[dict[str, Any]],
    *,
    action: str,
    anchor_process_by_uid: dict[str, Any],
    node_index_by_uid: dict[str, int | None],
) -> list[AnchorProjection]:
    projections: list[AnchorProjection] = []
    for anchor in anchors:
        if str(anchor.get("action") or "") != action:
            continue
        uid = str(anchor.get("mac_constraint_uid") or "")
        metadata = anchor.get("metadata") or {}
        anchor_process = anchor_process_by_uid.get(uid)
        if anchor_process is None:
            anchor_process = anchor_target_process(anchor)
        node_index = resolve_node_index(
            graph,
            anchor,
            node_index_by_uid.get(uid),
            target_process=anchor_process,
        )
        node_index_by_uid[uid] = node_index
        current_process = graph.to_process(node_index) if node_index is not None else None
        projections.append(
            AnchorProjection(
                mac_constraint_uid=uid,
                constraint_id=str(metadata.get("constraint_id") or ""),
                action=str(anchor.get("action") or ""),
                anchor_text=str(anchor.get("text") or ""),
                node_index=node_index,
                anchor_process=copy.deepcopy(anchor_process),
                current_process=copy.deepcopy(current_process),
            )
        )
    return projections


def tool_node_name(node: Any) -> str | None:
    if isinstance(node, list) and node:
        return str(node[0])
    return None


def tool_node_params(node: Any) -> dict[str, Any]:
    if isinstance(node, list) and len(node) > 1 and isinstance(node[1], dict):
        return copy.deepcopy(node[1])
    return {}


def or_sibling_tool_names(graph: DirectedActionGraph, or_index: int) -> list[str]:
    names: list[str] = []
    for child in graph.children_of(or_index):
        name = tool_node_name(graph.nodes[child])
        if name:
            names.append(name)
    return names


@dataclass
class ActionAddSet:
    domain: str
    action: str
    domain_tools: frozenset[str]
    or_pairs: frozenset[frozenset[str]]
    tool_param_templates: dict[str, dict[str, Any]]

    def candidate_tools(self, sibling_tool_names: list[str]) -> list[tuple[str, dict[str, Any]]]:
        siblings = [name for name in sibling_tool_names if name]
        if not siblings:
            return []
        present = set(siblings)
        results: list[tuple[str, dict[str, Any]]] = []
        for tool in sorted(self.domain_tools):
            if tool == self.action or tool in present:
                continue
            if not any(frozenset({sibling, tool}) in self.or_pairs for sibling in siblings):
                continue
            params = copy.deepcopy(self.tool_param_templates.get(tool, {}))
            results.append((tool, params))
        return results


@dataclass
class ActionAddSetRegistry:
    sets: dict[str, ActionAddSet]
    domain_tool_params: dict[tuple[str, str], dict[str, Any]]

    @classmethod
    def from_tasks(cls, tasks: list[dict[str, Any]]) -> ActionAddSetRegistry:
        domain_tools: dict[str, set[str]] = {}
        or_pairs: dict[tuple[str, str], set[frozenset[str]]] = {}
        param_counts: dict[tuple[str, str, str], Counter[str]] = {}

        for task in tasks:
            domain = task_domain(task)
            if not domain:
                continue
            action = str(task.get("user_goal") or (task.get("original_sopbench") or {}).get("user_goal") or "")
            dag_raw = (task.get("original_sopbench") or {}).get("directed_action_graph")
            if not isinstance(dag_raw, dict):
                continue
            graph = DirectedActionGraph(copy.deepcopy(dag_raw["nodes"]), copy.deepcopy(dag_raw["connections"]))
            domain_tools.setdefault(domain, set())
            for index in graph.tool_node_indices():
                name = tool_node_name(graph.nodes[index])
                if not name:
                    continue
                domain_tools[domain].add(name)
                params = tool_node_params(graph.nodes[index])
                if action:
                    param_counts.setdefault((domain, action, name), Counter())[json.dumps(params, sort_keys=True)] += 1
                param_counts.setdefault((domain, "*", name), Counter())[json.dumps(params, sort_keys=True)] += 1

            if not action:
                continue
            for or_index in graph.logic_node_indices():
                if graph.nodes[or_index] != "or":
                    continue
                sibling_names = or_sibling_tool_names(graph, or_index)
                pair_bucket = or_pairs.setdefault((domain, action), set())
                for left in range(len(sibling_names)):
                    for right in range(left + 1, len(sibling_names)):
                        pair_bucket.add(frozenset({sibling_names[left], sibling_names[right]}))

        domain_tool_params: dict[tuple[str, str], dict[str, Any]] = {}
        for (domain, _scope, tool), counter in param_counts.items():
            if not counter:
                continue
            best = counter.most_common(1)[0][0]
            domain_tool_params[(domain, tool)] = json.loads(best)

        sets: dict[str, ActionAddSet] = {}
        action_keys = {key for key in or_pairs} | {
            (domain, str(task.get("user_goal") or ""))
            for task in tasks
            if task_domain(task)
        }
        for domain, action in sorted(action_keys):
            if not action:
                continue
            templates: dict[str, dict[str, Any]] = {}
            for tool in domain_tools.get(domain, set()):
                for key in ((domain, action, tool), (domain, "*", tool)):
                    counter = param_counts.get(key)
                    if counter:
                        templates[tool] = json.loads(counter.most_common(1)[0][0])
                        break
                if tool not in templates:
                    templates[tool] = copy.deepcopy(domain_tool_params.get((domain, tool), {}))
            sets[f"{domain}:{action}"] = ActionAddSet(
                domain=domain,
                action=action,
                domain_tools=frozenset(domain_tools.get(domain, set())),
                or_pairs=frozenset(or_pairs.get((domain, action), set())),
                tool_param_templates=templates,
            )
        return cls(sets=sets, domain_tool_params=domain_tool_params)

    @classmethod
    def from_json(cls, payload: dict[str, Any]) -> ActionAddSetRegistry:
        sets: dict[str, ActionAddSet] = {}
        domain_tool_params: dict[tuple[str, str], dict[str, Any]] = {}
        for key, item in payload.items():
            if not isinstance(item, dict):
                continue
            domain = str(item.get("domain") or "")
            action = str(item.get("action") or "")
            templates = copy.deepcopy(item.get("tool_param_templates") or {})
            for tool, params in templates.items():
                if isinstance(params, dict):
                    domain_tool_params[(domain, str(tool))] = copy.deepcopy(params)
            pair_items = item.get("or_pairs") or []
            or_pair_set = frozenset(
                frozenset(str(part) for part in pair)
                for pair in pair_items
                if isinstance(pair, list) and len(pair) == 2
            )
            sets[str(key)] = ActionAddSet(
                domain=domain,
                action=action,
                domain_tools=frozenset(str(tool) for tool in (item.get("domain_tools") or [])),
                or_pairs=or_pair_set,
                tool_param_templates=templates if isinstance(templates, dict) else {},
            )
        return cls(sets=sets, domain_tool_params=domain_tool_params)

    def get(self, domain: str, action: str) -> ActionAddSet | None:
        return self.sets.get(f"{domain}:{action}")


def write_json(path: Path, payload: Any) -> None:
    target = resolve_path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def load_add_set_registry(
    *,
    path: Path,
    tasks: list[dict[str, Any]] | None = None,
    rebuild: bool = False,
) -> ActionAddSetRegistry:
    target = resolve_path(path)
    if rebuild or not target.exists():
        if tasks is None:
            raise ValueError("tasks are required to build action add sets")
        registry = ActionAddSetRegistry.from_tasks(tasks)
        write_json(target, add_set_registry_to_json(registry))
        return registry
    payload = load_json(target)
    if not isinstance(payload, dict):
        raise ValueError(f"expected object at root of {target}")
    return ActionAddSetRegistry.from_json(payload)

def list_add_candidates(
    graph: DirectedActionGraph,
    registry: ActionAddSetRegistry | None,
    *,
    domain: str,
    action: str,
) -> list[tuple[int, str, dict[str, Any]]]:
    if registry is None:
        return []
    add_set = registry.get(domain, action)
    if add_set is None:
        return []
    candidates: list[tuple[int, str, dict[str, Any]]] = []
    for or_index in graph.logic_node_indices():
        if graph.nodes[or_index] != "or":
            continue
        siblings = or_sibling_tool_names(graph, or_index)
        present = set(siblings)
        for tool, params in add_set.candidate_tools(siblings):
            if tool in present:
                continue
            candidates.append((or_index, tool, params))
    return candidates


def enumerate_mutation_candidates(
    graph: DirectedActionGraph,
    *,
    add_set_registry: ActionAddSetRegistry | None = None,
    domain: str = "",
    action: str = "",
) -> list[tuple[Any, ...]]:
    logic_nodes = graph.logic_node_indices()
    tool_nodes = [index for index in graph.tool_node_indices() if index != 0]
    candidates: list[tuple[Any, ...]] = []
    candidates.extend(("flip", index) for index in logic_nodes)
    candidates.extend(("delete", index) for index in tool_nodes)
    for or_index, tool, params in list_add_candidates(
        graph, add_set_registry, domain=domain, action=action
    ):
        candidates.append(("add", or_index, tool, params))
    return candidates


def apply_mutation_candidate(
    graph: DirectedActionGraph,
    item: tuple[Any, ...],
) -> tuple[str | None, dict[int, int | None]]:
    kind = item[0]
    if kind == "flip":
        label = graph.flip_logic(int(item[1]))
        return (label, {}) if label else (None, {})
    if kind == "delete":
        index = int(item[1])
        before_nodes = copy.deepcopy(graph.nodes)
        before_connections = copy.deepcopy(graph.connections)
        label, remap = graph.delete_node(index)
        if label and graph.nodes:
            return label, remap
        graph.nodes = before_nodes
        graph.connections = before_connections
        return None, {}
    if kind == "add":
        _, or_index, tool, params = item
        before_nodes = copy.deepcopy(graph.nodes)
        before_connections = copy.deepcopy(graph.connections)
        label = graph.add_or_branch(
            int(or_index),
            str(tool),
            params if isinstance(params, dict) else {},
        )
        if label:
            return label, {}
        graph.nodes = before_nodes
        graph.connections = before_connections
        return None, {}
    return None, {}


def pick_random_mutation(
    graph: DirectedActionGraph,
    rng: random.Random,
    *,
    add_set_registry: ActionAddSetRegistry | None = None,
    domain: str = "",
    action: str = "",
) -> tuple[str | None, dict[int, int | None]]:
    candidates = enumerate_mutation_candidates(
        graph,
        add_set_registry=add_set_registry,
        domain=domain,
        action=action,
    )
    if not candidates:
        return None, {}
    return apply_mutation_candidate(graph, rng.choice(candidates))


def sample_mutation(
    graph: DirectedActionGraph,
    rng: random.Random,
    *,
    add_set_registry: ActionAddSetRegistry | None = None,
    domain: str = "",
    action: str = "",
) -> tuple[str | None, dict[int, int | None]]:
    candidates = enumerate_mutation_candidates(
        graph,
        add_set_registry=add_set_registry,
        domain=domain,
        action=action,
    )
    rng.shuffle(candidates)
    for item in candidates:
        label, remap = apply_mutation_candidate(graph, item)
        if label:
            return label, remap
    return None, {}


def simulate_graph_noise(
    task: dict[str, Any],
    *,
    action: str,
    noise_target: int,
    seed: int,
    max_attempts: int,
    add_set_registry: ActionAddSetRegistry | None = None,
) -> dict[str, Any]:
    original = task.get("original_sopbench") or {}
    dag_raw = original.get("directed_action_graph")
    if not isinstance(dag_raw, dict):
        raise ValueError(f"task {task.get('mac_task_uid')} has no directed_action_graph")

    anchor_graph = DirectedActionGraph(copy.deepcopy(dag_raw["nodes"]), copy.deepcopy(dag_raw["connections"]))
    working = anchor_graph.copy()
    rng = random.Random(seed)

    anchors = [a for a in (task.get("anchors") or []) if str(a.get("action") or "") == action]
    anchor_process_by_uid, node_index_by_uid = build_anchor_graph_baseline(
        anchor_graph,
        anchors,
        action=action,
    )

    steps: list[MutationStep] = []
    accepted_mutations: list[str] = []

    baseline = build_projections(
        anchor_graph,
        anchors,
        action=action,
        anchor_process_by_uid=anchor_process_by_uid,
        node_index_by_uid=copy.deepcopy(node_index_by_uid),
    )
    baseline_node_map = copy.deepcopy(node_index_by_uid)
    anchor_global_sig = process_signature(anchor_graph.global_merge_process())
    working_nodes = copy.deepcopy(node_index_by_uid)
    domain = task_domain(task)

    attempt = 0
    while len(steps) < noise_target and attempt < max_attempts:
        attempt += 1
        snapshot = working.copy()
        mutation, remap = sample_mutation(
            snapshot,
            rng,
            add_set_registry=add_set_registry,
            domain=domain,
            action=action,
        )
        if not mutation:
            continue

        trial_nodes = copy.deepcopy(working_nodes)
        if remap:
            remap_node_indices(trial_nodes, remap)

        projections = build_projections(
            snapshot,
            anchors,
            action=action,
            anchor_process_by_uid=anchor_process_by_uid,
            node_index_by_uid=trial_nodes,
        )
        changed = [p.constraint_id for p in projections if p.changed]
        global_changed = process_signature(snapshot.global_merge_process()) != anchor_global_sig
        if not changed and not global_changed:
            continue

        working = snapshot
        working_nodes = trial_nodes
        accepted_mutations.append(mutation)
        steps.append(
            MutationStep(
                step=len(steps) + 1,
                mutation=mutation,
                changed_anchors=changed,
                global_changed=global_changed,
                projections=projections,
            )
        )

    final_anchor_match = process_signature(working.global_merge_process()) == anchor_global_sig
    restore_to_anchor = (
        "N/A (sim stops at last noisy graph; anchor is separate final state in full pipeline)"
    )

    return {
        "mac_task_uid": task.get("mac_task_uid"),
        "action": action,
        "seed": seed,
        "noise_target": noise_target,
        "noise_accepted": len(steps),
        "attempts": attempt,
        "anchor_node_map": baseline_node_map,
        "final_node_map": {
            uid: working_nodes.get(uid) for uid in anchor_process_by_uid
        },
        "baseline_projections": baseline,
        "steps": steps,
        "final_graph": {"nodes": working.nodes, "connections": working.connections},
        "anchor_graph_matches_final_noisy": final_anchor_match,
        "restore_note": restore_to_anchor,
    }


def format_process(process: Any, *, limit: int = 120) -> str:
    text = json.dumps(process, ensure_ascii=False)
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


def print_simulation_report(result: dict[str, Any]) -> None:
    print(f"task={result['mac_task_uid']} action={result['action']} seed={result['seed']}")
    print(
        f"noise_target={result['noise_target']} accepted={result['noise_accepted']} "
        f"attempts={result['attempts']}"
    )
    print("\nAnchor -> graph node index (anchor graph):")
    for uid, node_index in (result.get("anchor_node_map") or {}).items():
        short_uid = uid.split(":")[-1]
        print(f"  {short_uid}: node {node_index}")

    print("\nBaseline anchor local processes:")
    for projection in result["baseline_projections"]:
        short_uid = projection.mac_constraint_uid.split(":")[-1]
        print(
            f"  [{projection.constraint_id}] {short_uid} node={projection.node_index} "
            f"process={format_process(projection.anchor_process)}"
        )

    if not result["steps"]:
        print("\n(no mutations accepted)")
        return

    print("\n=== Mutation timeline ===")
    for step in result["steps"]:
        print(f"\n--- noisy step {step.step}: {step.mutation} ---")
        print(f"  global merge changed: {step.global_changed}")
        print(f"  changed anchors: {step.changed_anchors or '(none locally)'}")

        for projection in step.projections:
            marker = "*" if projection.changed else " "
            short_uid = projection.mac_constraint_uid.split(":")[-1]
            print(
                f"  {marker} [{projection.constraint_id}] {short_uid} "
                f"node={projection.node_index}"
            )
            if projection.changed:
                print(f"      anchor:  {format_process(projection.anchor_process, limit=100)}")
                print(f"      noisy:   {format_process(projection.current_process, limit=100)}")
            else:
                print(f"      process: {format_process(projection.current_process, limit=100)}")

    print("\n=== Final noisy graph ===")
    graph = DirectedActionGraph(result["final_graph"]["nodes"], result["final_graph"]["connections"])
    print(f"  global merge: {format_process(graph.global_merge_process(), limit=200)}")
    print(f"  (anchor global merge preserved as final SOP state in full pipeline)")


def sample_random_noisy_graph(
    task: dict[str, Any],
    *,
    action: str,
    num_steps: int,
    rng: random.Random,
    add_set_registry: ActionAddSetRegistry | None = None,
) -> dict[str, Any]:
    original = task.get("original_sopbench") or {}
    dag_raw = original.get("directed_action_graph")
    if not isinstance(dag_raw, dict):
        raise ValueError(f"task {task.get('mac_task_uid')} has no directed_action_graph")

    anchor_graph = DirectedActionGraph(copy.deepcopy(dag_raw["nodes"]), copy.deepcopy(dag_raw["connections"]))
    anchors = [a for a in (task.get("anchors") or []) if str(a.get("action") or "") == action]
    anchor_process_by_uid, node_index_by_uid = build_anchor_graph_baseline(
        anchor_graph,
        anchors,
        action=action,
    )
    anchor_global_sig = process_signature(anchor_graph.global_merge_process())
    domain = task_domain(task)

    working = anchor_graph.copy()
    working_nodes = copy.deepcopy(node_index_by_uid)
    applied_steps: list[str] = []

    for _ in range(max(0, num_steps)):
        snapshot = working.copy()
        mutation, remap = pick_random_mutation(
            snapshot,
            rng,
            add_set_registry=add_set_registry,
            domain=domain,
            action=action,
        )
        if not mutation:
            break
        trial_nodes = copy.deepcopy(working_nodes)
        if remap:
            remap_node_indices(trial_nodes, remap)
        working = snapshot
        working_nodes = trial_nodes
        applied_steps.append(mutation)

    projections = build_projections(
        working,
        anchors,
        action=action,
        anchor_process_by_uid=anchor_process_by_uid,
        node_index_by_uid=working_nodes,
    )
    changed = [p.constraint_id for p in projections if p.changed]
    global_changed = process_signature(working.global_merge_process()) != anchor_global_sig

    return {
        "planned_steps": num_steps,
        "applied_steps": applied_steps,
        "step_count": len(applied_steps),
        "changed_constraints": changed,
        "global_changed": global_changed,
        "projections": projections,
        "final_graph": {"nodes": working.nodes, "connections": working.connections},
    }


def sample_noisy_graph_batch(
    task: dict[str, Any],
    *,
    action: str,
    count: int = 10,
    max_steps: int = 3,
    seed: int = 0,
    add_set_registry: ActionAddSetRegistry | None = None,
) -> dict[str, Any]:
    rng = random.Random(seed)
    samples: list[dict[str, Any]] = []
    for index in range(max(0, count)):
        planned_steps = rng.randint(1, max(1, max_steps))
        sample_rng = random.Random(rng.randint(0, 2**31 - 1))
        sample = sample_random_noisy_graph(
            task,
            action=action,
            num_steps=planned_steps,
            rng=sample_rng,
            add_set_registry=add_set_registry,
        )
        sample["sample_index"] = index + 1
        samples.append(sample)

    changed_counts = [len(s.get("changed_constraints") or []) for s in samples]
    step_counts = [int(s.get("step_count") or 0) for s in samples]
    return {
        "mac_task_uid": task.get("mac_task_uid"),
        "action": action,
        "seed": seed,
        "count": len(samples),
        "max_steps": max_steps,
        "summary": {
            "step_count_min": min(step_counts) if step_counts else 0,
            "step_count_max": max(step_counts) if step_counts else 0,
            "changed_constraints_min": min(changed_counts) if changed_counts else 0,
            "changed_constraints_max": max(changed_counts) if changed_counts else 0,
            "global_changed_count": sum(1 for s in samples if s.get("global_changed")),
            "any_local_change_count": sum(1 for s in samples if s.get("changed_constraints")),
        },
        "samples": samples,
    }


def print_noisy_graph_batch_report(batch: dict[str, Any]) -> None:
    print(
        f"task={batch['mac_task_uid']} action={batch['action']} seed={batch['seed']} "
        f"samples={batch['count']} max_steps={batch['max_steps']}"
    )
    summary = batch.get("summary") or {}
    print(
        "summary: "
        f"steps=[{summary.get('step_count_min')},{summary.get('step_count_max')}] "
        f"changed_constraints=[{summary.get('changed_constraints_min')},{summary.get('changed_constraints_max')}] "
        f"global_changed={summary.get('global_changed_count')}/{batch['count']} "
        f"any_local_change={summary.get('any_local_change_count')}/{batch['count']}"
    )

    for sample in batch.get("samples") or []:
        print(f"\n=== noisy graph #{sample.get('sample_index')} ===")
        print(
            f"planned_steps={sample.get('planned_steps')} applied={sample.get('step_count')} "
            f"global_changed={sample.get('global_changed')}"
        )
        steps = sample.get("applied_steps") or []
        if steps:
            for step_index, mutation in enumerate(steps, start=1):
                print(f"  step {step_index}: {mutation}")
        else:
            print("  (no mutation applied)")

        changed = sample.get("changed_constraints") or []
        print(f"  changed constraints ({len(changed)}): {changed or '(none)'}")

        for projection in sample.get("projections") or []:
            if not projection.changed:
                continue
            short_uid = projection.mac_constraint_uid.split(":")[-1]
            print(f"  * [{projection.constraint_id}] {short_uid} node={projection.node_index}")
            print(f"      anchor: {format_process(projection.anchor_process, limit=100)}")
            print(f"      noisy:  {format_process(projection.current_process, limit=100)}")

        graph = DirectedActionGraph(
            copy.deepcopy((sample.get("final_graph") or {}).get("nodes") or []),
            copy.deepcopy((sample.get("final_graph") or {}).get("connections") or []),
        )
        if graph.nodes:
            print(f"  final global merge: {format_process(graph.global_merge_process(), limit=160)}")


def noisy_graph_batch_to_json(batch: dict[str, Any]) -> dict[str, Any]:
    payload = {
        "mac_task_uid": batch.get("mac_task_uid"),
        "action": batch.get("action"),
        "seed": batch.get("seed"),
        "count": batch.get("count"),
        "max_steps": batch.get("max_steps"),
        "summary": batch.get("summary"),
        "samples": [],
    }
    for sample in batch.get("samples") or []:
        payload["samples"].append(
            {
                "sample_index": sample.get("sample_index"),
                "planned_steps": sample.get("planned_steps"),
                "step_count": sample.get("step_count"),
                "applied_steps": sample.get("applied_steps"),
                "changed_constraints": sample.get("changed_constraints"),
                "global_changed": sample.get("global_changed"),
                "final_graph": sample.get("final_graph"),
                "projections": [
                    {
                        "mac_constraint_uid": p.mac_constraint_uid,
                        "constraint_id": p.constraint_id,
                        "node_index": p.node_index,
                        "anchor_process": p.anchor_process,
                        "current_process": p.current_process,
                        "changed": p.changed,
                    }
                    for p in sample.get("projections") or []
                ],
            }
        )
    return payload


JUDGE_SYSTEM_PROMPT = """
You judge whether a graph mutation produces plausible temporal SOP noise.

Context:
- The anchor state is the current SOP rule for one target action.
- A noisy step is an older superseded revision on the way to that anchor.
- Executable summaries appear as executable_diff removed/added lines (rule-base). You do NOT invent process trees.
- One graph edit may change multiple constraints at once.

Accept ONLY if ALL hold for every changed constraint delta:
1. Same policy thread: same domain, target action, and business topic as the anchor.
2. Prose matches executable: text must not claim tools/steps listed only on the removed side of a diff.
3. Superseded draft: reads like an older version the team later replaced, not an unrelated rule.
4. Standalone SOP bullet: direct rule statement; avoid if/when/only-if scaffolding.
5. Faithful to the delta: reflect the mutation (flip and/or, deleted tool, added OR branch, stricter/looser merge).

Reject if ANY holds:
- Prose contradicts the executable "after" side of a diff (e.g. requires login when process is removed).
- Logical inversion vs anchor intent without matching executable change.
- Unrelated new tools/topics not implied by the mutation diff.
- Duplicate of anchor_text with no meaningful revision story.
- Global-only change that no changed bullet can honestly describe (say so explicitly).

Output valid JSON only. Do not wrap in markdown fences.
""".strip()


def summarize_text_line_diff(
    before_text: str,
    after_text: str,
    *,
    max_items: int = 8,
) -> dict[str, Any]:
    before_lines = [line.strip() for line in before_text.splitlines() if line.strip()]
    after_lines = [line.strip() for line in after_text.splitlines() if line.strip()]
    if before_lines == after_lines:
        return {"unchanged": True, "removed": [], "added": []}
    before_set = set(before_lines)
    after_set = set(after_lines)
    removed = sorted(before_set - after_set)[:max_items]
    added = sorted(after_set - before_set)[:max_items]
    payload: dict[str, Any] = {"unchanged": False, "removed": removed, "added": added}
    overflow = max(0, len(before_set - after_set) - len(removed)) + max(0, len(after_set - before_set) - len(added))
    if overflow:
        payload["truncated_line_count"] = overflow
    return payload


def build_changed_constraint_diff_entry(item: dict[str, Any]) -> dict[str, Any]:
    anchor_proc = str(item.get("anchor_process_text") or "")
    noisy_proc = str(item.get("noisy_process_text") or "")
    entry: dict[str, Any] = {
        "mac_constraint_uid": item.get("mac_constraint_uid"),
        "constraint_id": item.get("constraint_id"),
        "anchor_text": item.get("anchor_text"),
        "executable_diff": summarize_text_line_diff(anchor_proc, noisy_proc),
    }
    if anchor_proc == noisy_proc:
        entry["executable_diff"]["unchanged"] = True
    return entry


def build_diff_summary(delta: GraphMutationDelta) -> dict[str, Any]:
    changed_items = [item for item in delta.constraint_deltas if item.get("changed")]
    summary: dict[str, Any] = {
        "mutation": delta.mutation,
        "global_changed": delta.global_changed,
        "global_executable_diff": summarize_text_line_diff(
            delta.global_merge_before_text,
            delta.global_merge_after_text,
        ),
        "changed_constraint_count": len(changed_items),
        "changed_constraints": [build_changed_constraint_diff_entry(item) for item in changed_items],
    }
    if changed_items:
        summary["changed_constraint_ids"] = [item.get("constraint_id") for item in changed_items]
    return summary


def task_domain(task: dict[str, Any]) -> str:
    original = task.get("original_sopbench") or {}
    return str(task.get("domain") or original.get("domain") or "").strip()


def task_dep_params(task: dict[str, Any]) -> dict[str, Any]:
    original = task.get("original_sopbench") or {}
    params = copy.deepcopy(task.get("constraint_parameters") or {})
    params.update(copy.deepcopy(original.get("constraint_parameters") or {}))
    return params


def normalize_dep_tree(value: Any) -> Any:
    if isinstance(value, list):
        return tuple(normalize_dep_tree(item) for item in value)
    if isinstance(value, tuple):
        return tuple(normalize_dep_tree(item) for item in value)
    return value


def process_to_dep_tuple(process: Any) -> tuple[Any, ...] | None:
    if process is None:
        return None
    normalized = normalize_dep_tree(process)
    return normalized if isinstance(normalized, tuple) else None


def _domain_assistant(domain: str) -> Any:
    ensure_sopbench_imports()
    from env.variables import domain_assistant_keys  # noqa: WPS433

    return domain_assistant_keys[domain]


def extended_dep_params(
    domain: str,
    single: tuple[Any, ...],
    dep_params: dict[str, Any],
) -> dict[str, Any]:
    merged = copy.deepcopy(dep_params)
    params = single[2] if len(single) > 2 and isinstance(single[2], dict) else {}
    for value in params.values():
        if isinstance(value, str):
            merged.setdefault(value, value)
    name = str(single[1]).replace("not ", "")
    assistant = _domain_assistant(domain)
    for template in (
        assistant.positive_constraint_descriptions.get(name),
        assistant.negative_constraint_descriptions.get(name),
    ):
        if not template:
            continue
        for _, field, _, _ in string.Formatter().parse(template):
            if field:
                merged.setdefault(field, field)
    return merged


def verbalize_single_dep(domain: str, single: tuple[Any, ...], dep_params: dict[str, Any]) -> str:
    ensure_sopbench_imports()
    from env.task import get_single_dep_verb  # noqa: WPS433

    name = str(single[1])
    assistant = _domain_assistant(domain)
    if name.startswith("not "):
        name = name[4:]
    if name in assistant.positive_constraint_descriptions or name in assistant.negative_constraint_descriptions:
        return get_single_dep_verb(domain, single, extended_dep_params(domain, single, dep_params))

    builtin_tool_text = {
        "internal_get_database": "Read the full system database (broad fallback verification path).",
        "internal_get_interaction_time": "Get the current interaction timestamp from the environment.",
    }
    if name in builtin_tool_text:
        return builtin_tool_text[name]

    action_descriptions = getattr(assistant, "action_descriptions", {}) or {}
    if name in action_descriptions:
        params = single[2] if len(single) > 2 and isinstance(single[2], dict) else {}
        param_bits: list[str] = []
        for key, value in sorted(params.items()):
            display = dep_params.get(str(value), value) if isinstance(value, str) else value
            param_bits.append(f'{key}="{display}"')
        param_clause = f" ({', '.join(param_bits)})" if param_bits else ""
        return f"Run {name}{param_clause}: {str(action_descriptions[name]).strip()}"

    params = single[2] if len(single) > 2 and isinstance(single[2], dict) else {}
    if params:
        return f"Run tool {name} with parameters {params}."
    return f"Run tool {name}."


def verbalize_process_tree(domain: str, process: Any, dep_params: dict[str, Any]) -> str:
    dep = process_to_dep_tuple(process)
    if dep is None:
        return "No executable check (process removed or unavailable)."

    def dfs(dep_part: tuple[Any, ...], indent_level: int = 0) -> str:
        if not dep_part:
            return "No executable check."
        if dep_part[0] == "single":
            return verbalize_single_dep(domain, dep_part, dep_params)
        logic = str(dep_part[0])
        children = dep_part[1] if len(dep_part) > 1 else ()
        if logic == "and":
            header = "ALL of these conditions must be met:"
        elif logic == "or":
            header = "ANY ONE of these conditions must be met:"
        elif logic == "chain":
            header = "These steps must be completed in order:"
        else:
            header = f"{logic.upper()} composition:"
        parts: list[str] = [header]
        child_items = children if isinstance(children, tuple) else ()
        for index, child in enumerate(child_items, 1):
            if not isinstance(child, tuple):
                continue
            part_str = dfs(child, indent_level + 1)
            indent = "  " * indent_level
            first_line = (
                f"{indent}{index}. {part_str.splitlines()[0]}"
                if logic == "chain"
                else f"{indent}• {part_str.splitlines()[0]}"
            )
            rest_lines = part_str.splitlines()[1:]
            if rest_lines:
                wrapped = [first_line]
                for line in rest_lines:
                    wrapped.append(f"{indent}  {line.strip()}")
                parts.append("\n".join(wrapped))
            else:
                parts.append(first_line)
        return "\n".join(parts)

    return dfs(dep)


def constraint_prerequisite_text(
    domain: str,
    constraint_id: str,
    dep_params: dict[str, Any],
) -> str | None:
    assistant = _domain_assistant(domain)
    dependencies = getattr(assistant, "constraint_dependencies", {}) or {}
    dep = dependencies.get(constraint_id)
    if not dep:
        return None
    return verbalize_process_tree(domain, dep, dep_params)


def enrich_constraint_delta(
    delta: dict[str, Any],
    *,
    domain: str,
    dep_params: dict[str, Any],
) -> dict[str, Any]:
    enriched = copy.deepcopy(delta)
    enriched["anchor_process_text"] = verbalize_process_tree(
        domain,
        enriched.get("anchor_process"),
        dep_params,
    )
    enriched["noisy_process_text"] = verbalize_process_tree(
        domain,
        enriched.get("noisy_process"),
        dep_params,
    )
    prerequisite = constraint_prerequisite_text(domain, str(enriched.get("constraint_id") or ""), dep_params)
    if prerequisite:
        enriched["prerequisite_text"] = prerequisite
    return enriched


def graph_snapshot(graph: DirectedActionGraph) -> dict[str, Any]:
    nodes = []
    for index, node in enumerate(graph.nodes):
        nodes.append({"index": index, "label": node_label(node, index), "raw": copy.deepcopy(node)})
    return {
        "nodes": nodes,
        "connections": copy.deepcopy(graph.connections),
        "global_merge_process": graph.global_merge_process(),
    }


def task_description(task: dict[str, Any]) -> str:
    original = task.get("original_sopbench") or {}
    return str(
        task.get("mac_task_summary")
        or original.get("user_prompt")
        or original.get("user_instruction")
        or ""
    ).strip()


@dataclass
class GraphMutationDelta:
    mac_task_uid: str
    domain: str
    target_action: str
    task_description: str
    mutation: str
    global_merge_before: Any
    global_merge_after: Any
    global_merge_before_text: str
    global_merge_after_text: str
    global_changed: bool
    anchor_graph: dict[str, Any]
    noisy_graph: dict[str, Any]
    constraint_deltas: list[dict[str, Any]]

    def to_judge_payload(self, *, include_raw_graph: bool = False) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "mac_task_uid": self.mac_task_uid,
            "domain": self.domain,
            "target_action": self.target_action,
            "task_description": self.task_description,
            "diff_summary": build_diff_summary(self),
            "output_schema": {
                "accept": True,
                "reason": "short justification",
                "failed_checks": [],
                "constraints": [
                    {
                        "mac_constraint_uid": "uid",
                        "constraint_id": "logged_in_user",
                        "text": "superseded SOP bullet faithful to executable diff 'after' side",
                        "executable": {"process": "copy noisy_process exactly (machine field, not prose)"},
                    }
                ],
            },
        }
        if include_raw_graph:
            constraint_deltas = []
            for item in self.constraint_deltas:
                entry = {
                    "mac_constraint_uid": item.get("mac_constraint_uid"),
                    "constraint_id": item.get("constraint_id"),
                    "changed": item.get("changed"),
                    "anchor_text": item.get("anchor_text"),
                    "anchor_process_text": item.get("anchor_process_text"),
                    "noisy_process_text": item.get("noisy_process_text"),
                    "anchor_process": item.get("anchor_process"),
                    "noisy_process": item.get("noisy_process"),
                    "graph_node_index": item.get("graph_node_index"),
                }
                if item.get("prerequisite_text"):
                    entry["prerequisite_text"] = item.get("prerequisite_text")
                constraint_deltas.append(entry)
            payload["global_merge_before_text"] = self.global_merge_before_text
            payload["global_merge_after_text"] = self.global_merge_after_text
            payload["global_merge_before"] = self.global_merge_before
            payload["global_merge_after"] = self.global_merge_after
            payload["constraint_deltas"] = constraint_deltas
            payload["anchor_graph"] = self.anchor_graph
            payload["noisy_graph"] = self.noisy_graph
        return payload


def build_constraint_delta(projection: AnchorProjection) -> dict[str, Any]:
    metadata_hint = {
        "anchor_text": projection.anchor_text,
        "anchor_process": copy.deepcopy(projection.anchor_process),
        "noisy_process": copy.deepcopy(projection.current_process),
        "changed": projection.changed,
    }
    return {
        "mac_constraint_uid": projection.mac_constraint_uid,
        "constraint_id": projection.constraint_id,
        "graph_node_index": projection.node_index,
        **metadata_hint,
    }


def build_mutation_delta(
    *,
    task: dict[str, Any],
    action: str,
    mutation: str,
    anchor_graph: DirectedActionGraph,
    noisy_graph: DirectedActionGraph,
    projections: list[AnchorProjection],
) -> GraphMutationDelta:
    domain = task_domain(task)
    dep_params = task_dep_params(task)
    global_before = anchor_graph.global_merge_process()
    global_after = noisy_graph.global_merge_process()
    raw_deltas = [build_constraint_delta(projection) for projection in projections]
    constraint_deltas = [
        enrich_constraint_delta(item, domain=domain, dep_params=dep_params) for item in raw_deltas
    ]
    return GraphMutationDelta(
        mac_task_uid=str(task.get("mac_task_uid") or ""),
        domain=domain,
        target_action=action,
        task_description=task_description(task),
        mutation=mutation,
        global_merge_before=global_before,
        global_merge_after=global_after,
        global_merge_before_text=verbalize_process_tree(domain, global_before, dep_params),
        global_merge_after_text=verbalize_process_tree(domain, global_after, dep_params),
        global_changed=process_signature(global_before) != process_signature(global_after),
        anchor_graph=graph_snapshot(anchor_graph),
        noisy_graph=graph_snapshot(noisy_graph),
        constraint_deltas=constraint_deltas,
    )


def deterministic_preflight(delta: GraphMutationDelta) -> tuple[bool, list[str]]:
    issues: list[str] = []
    if not delta.mutation.strip():
        issues.append("empty mutation label")
    if not delta.noisy_graph.get("nodes"):
        issues.append("noisy graph is empty")
    changed = [item for item in delta.constraint_deltas if item.get("changed")]
    if not changed and not delta.global_changed:
        issues.append("no local or global executable change")
    for item in changed:
        if process_signature(item.get("anchor_process")) == process_signature(item.get("noisy_process")):
            issues.append(
                f"{item.get('constraint_id')}: anchor and noisy process signatures are identical"
            )
    return not issues, issues


def build_judge_user_prompt(delta: GraphMutationDelta, *, include_raw_graph: bool = False) -> str:
    payload = delta.to_judge_payload(include_raw_graph=include_raw_graph)
    instructions = [
        "Review diff_summary and decide accept or reject.",
        "executable_diff removed/added lines are rule-base summaries of executable structure.",
        "If accept=true, return one entry in constraints for EACH item in diff_summary.changed_constraints.",
        "Prose must align with the 'after' side of each constraint executable_diff (and global diff if relevant).",
        "Each accepted constraint.executable.process MUST equal that delta's noisy_process exactly (machine field).",
        "If accept=false, constraints must be [] and failed_checks must name the violated criteria.",
        "If global_changed is true but changed_constraints is empty, accept ONLY if reason honestly describes",
        "the global_executable_diff; otherwise reject.",
    ]
    payload["instructions"] = instructions
    return json.dumps(payload, indent=2, ensure_ascii=False)


def judge_output_schema() -> dict[str, Any]:
    return {
        "accept": True,
        "reason": "string",
        "failed_checks": ["prose_executable_mismatch"],
        "constraints": [
            {
                "mac_constraint_uid": "sopbench:healthcare:schedule_appointment:20-c0026",
                "constraint_id": "logged_in_user",
                "text": "superseded SOP bullet",
                "executable": {"process": None},
            }
        ],
    }


def parse_judge_json(text: str) -> dict[str, Any]:
    stripped = text.strip()
    if stripped.startswith("```"):
        match = re.search(r"```(?:json)?\s*(.*?)\s*```", stripped, flags=re.DOTALL)
        if match:
            stripped = match.group(1).strip()
    payload = json.loads(stripped)
    if not isinstance(payload, dict):
        raise ValueError("judge JSON root must be an object")
    return payload


def validate_judge_response(
    payload: dict[str, Any],
    delta: GraphMutationDelta,
) -> tuple[bool, list[str]]:
    issues: list[str] = []
    accept = bool(payload.get("accept"))
    constraints = payload.get("constraints")
    if not isinstance(constraints, list):
        return False, ["constraints must be a list"]
    changed = [item for item in delta.constraint_deltas if item.get("changed")]
    changed_uids = {str(item.get("mac_constraint_uid") or "") for item in changed}
    if accept:
        if not delta.global_changed and not changed:
            issues.append("accept=true but delta has no changes")
        if changed and not constraints:
            issues.append("accept=true but constraints is empty")
        seen: set[str] = set()
        for entry in constraints:
            if not isinstance(entry, dict):
                issues.append("constraint entry must be an object")
                continue
            uid = str(entry.get("mac_constraint_uid") or "")
            text = str(entry.get("text") or "").strip()
            executable = entry.get("executable")
            if not uid:
                issues.append("constraint missing mac_constraint_uid")
            if uid not in changed_uids:
                issues.append(f"constraint {uid} is not in changed deltas")
            if not text:
                issues.append(f"constraint {uid} missing text")
            if not isinstance(executable, dict):
                issues.append(f"constraint {uid} missing executable object")
                continue
            expected = next(
                (item.get("noisy_process") for item in changed if item.get("mac_constraint_uid") == uid),
                None,
            )
            if process_signature(executable.get("process")) != process_signature(expected):
                issues.append(f"constraint {uid} executable.process must match noisy_process")
            if uid:
                seen.add(uid)
        missing = changed_uids - seen
        if missing:
            issues.append(f"missing accepted constraints for: {sorted(missing)}")
    else:
        if constraints:
            issues.append("accept=false but constraints is non-empty")
        if not str(payload.get("reason") or "").strip():
            issues.append("accept=false requires reason")
    return not issues, issues


def call_judge_llm(
    *,
    user_prompt: str,
    model: str,
    base_url: str | None,
    api_key: str | None,
    max_tokens: int,
    timeout: float,
    retries: int,
    sleep: float,
) -> str:
    try:
        openai_module = importlib.import_module("openai")
    except ImportError as exc:
        raise RuntimeError("openai package is required for llm_judge") from exc
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
                temperature=0.2,
                max_tokens=max_tokens,
                messages=[
                    {"role": "system", "content": JUDGE_SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
            )
            return response.choices[0].message.content or ""
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            if attempt == retries:
                break
            time.sleep(sleep * (2 ** (attempt - 1)))
    raise RuntimeError(f"LLM judge request failed after {retries} attempts: {last_error}") from last_error


def llm_judge(
    delta: GraphMutationDelta,
    *,
    model: str,
    base_url: str | None = None,
    api_key: str | None = None,
    max_tokens: int = 2048,
    timeout: float = 120.0,
    retries: int = 3,
    sleep: float = 0.5,
    skip_llm: bool = False,
    include_raw_graph: bool = False,
) -> dict[str, Any]:
    preflight_ok, preflight_issues = deterministic_preflight(delta)
    user_prompt = build_judge_user_prompt(delta, include_raw_graph=include_raw_graph)
    result: dict[str, Any] = {
        "preflight_ok": preflight_ok,
        "preflight_issues": preflight_issues,
        "user_prompt": user_prompt,
        "delta": delta.to_judge_payload(include_raw_graph=include_raw_graph),
    }
    if not preflight_ok:
        result.update(
            {
                "accept": False,
                "reason": "deterministic preflight failed",
                "failed_checks": preflight_issues,
                "constraints": [],
                "llm_called": False,
            }
        )
        return result

    if skip_llm:
        result.update(
            {
                "accept": None,
                "reason": "llm skipped (--print-judge-prompt or skip_llm=True)",
                "failed_checks": [],
                "constraints": [],
                "llm_called": False,
            }
        )
        return result

    response_text = call_judge_llm(
        user_prompt=user_prompt,
        model=model,
        base_url=base_url,
        api_key=api_key,
        max_tokens=max_tokens,
        timeout=timeout,
        retries=retries,
        sleep=sleep,
    )
    parsed = parse_judge_json(response_text)
    schema_ok, schema_issues = validate_judge_response(parsed, delta)
    result.update(
        {
            "accept": bool(parsed.get("accept")) and schema_ok,
            "reason": str(parsed.get("reason") or "").strip(),
            "failed_checks": list(parsed.get("failed_checks") or []) + schema_issues,
            "constraints": parsed.get("constraints") or [],
            "llm_called": True,
            "llm_raw": response_text,
            "schema_ok": schema_ok,
            "schema_issues": schema_issues,
        }
    )
    if parsed.get("accept") and not schema_ok:
        result["reason"] = (
            str(parsed.get("reason") or "").strip()
            or "LLM accept overridden by response schema validation"
        )
    return result


def sample_one_mutation(
    task: dict[str, Any],
    *,
    action: str,
    seed: int,
    max_attempts: int = 40,
    add_set_registry: ActionAddSetRegistry | None = None,
) -> tuple[GraphMutationDelta, DirectedActionGraph, DirectedActionGraph]:
    original = task.get("original_sopbench") or {}
    dag_raw = original.get("directed_action_graph")
    if not isinstance(dag_raw, dict):
        raise ValueError(f"task {task.get('mac_task_uid')} has no directed_action_graph")

    anchor_graph = DirectedActionGraph(copy.deepcopy(dag_raw["nodes"]), copy.deepcopy(dag_raw["connections"]))
    anchors = [a for a in (task.get("anchors") or []) if str(a.get("action") or "") == action]
    anchor_process_by_uid, node_index_by_uid = build_anchor_graph_baseline(
        anchor_graph,
        anchors,
        action=action,
    )
    anchor_global_sig = process_signature(anchor_graph.global_merge_process())
    rng = random.Random(seed)
    domain = task_domain(task)

    for _ in range(max_attempts):
        snapshot = anchor_graph.copy()
        mutation, remap = sample_mutation(
            snapshot,
            rng,
            add_set_registry=add_set_registry,
            domain=domain,
            action=action,
        )
        if not mutation:
            continue
        trial_nodes = copy.deepcopy(node_index_by_uid)
        if remap:
            remap_node_indices(trial_nodes, remap)
        projections = build_projections(
            snapshot,
            anchors,
            action=action,
            anchor_process_by_uid=anchor_process_by_uid,
            node_index_by_uid=trial_nodes,
        )
        changed = [p.constraint_id for p in projections if p.changed]
        global_changed = process_signature(snapshot.global_merge_process()) != anchor_global_sig
        if not changed and not global_changed:
            continue
        delta = build_mutation_delta(
            task=task,
            action=action,
            mutation=mutation,
            anchor_graph=anchor_graph,
            noisy_graph=snapshot,
            projections=projections,
        )
        return delta, anchor_graph, snapshot
    raise RuntimeError(f"could not sample a nontrivial mutation in {max_attempts} attempts")


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
    if not getattr(args, "model", None):
        args.model = os.getenv("MAC_LLM_MODEL") or os.getenv("LLM_MODEL")
    if not getattr(args, "base_url", None):
        args.base_url = (
            os.getenv("OPENAI_BASE_URL")
            or os.getenv("MAC_LLM_BASE_URL")
            or os.getenv("LLM_BASE_URL")
        )
    if not getattr(args, "api_key", None):
        args.api_key = os.getenv("OPENAI_API_KEY") or os.getenv("LLM_API_KEY")


def print_judge_report(judge_result: dict[str, Any]) -> None:
    print(f"preflight_ok={judge_result.get('preflight_ok')}")
    if judge_result.get("preflight_issues"):
        print(f"preflight_issues={judge_result.get('preflight_issues')}")
    print(f"accept={judge_result.get('accept')}")
    print(f"reason={judge_result.get('reason')}")
    if judge_result.get("failed_checks"):
        print(f"failed_checks={judge_result.get('failed_checks')}")
    if judge_result.get("schema_issues"):
        print(f"schema_issues={judge_result.get('schema_issues')}")
    constraints = judge_result.get("constraints") or []
    if constraints:
        print("\nAccepted delta constraints:")
        for entry in constraints:
            print(f"  [{entry.get('constraint_id')}] {entry.get('mac_constraint_uid')}")
            print(f"    text: {entry.get('text')}")
            print(f"    process: {format_process((entry.get('executable') or {}).get('process'), limit=160)}")


def resolve_path(path: Path) -> Path:
    return path if path.is_absolute() else REPO_ROOT / path


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def add_set_registry_to_json(registry: ActionAddSetRegistry) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    for key, add_set in sorted(registry.sets.items()):
        payload[key] = {
            "domain": add_set.domain,
            "action": add_set.action,
            "domain_tools": sorted(add_set.domain_tools),
            "or_pairs": [sorted(pair) for pair in add_set.or_pairs],
            "tool_param_templates": add_set.tool_param_templates,
        }
    return payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--step2-input", type=Path, default=DEFAULT_STEP2)
    parser.add_argument(
        "--task-uid",
        default="sopbench:healthcare:schedule_appointment:20",
        help="mac_task_uid to simulate",
    )
    parser.add_argument(
        "--action",
        default=None,
        help="Target action (default: user_goal from task)",
    )
    parser.add_argument("--seed", type=int, default=13)
    parser.add_argument("--noise-target", type=int, default=3, help="Target noisy graph steps")
    parser.add_argument("--max-steps", type=int, default=3, help="Max mutations per sampled noisy graph")
    parser.add_argument(
        "--sample-noisy-graphs",
        type=int,
        default=0,
        help="Sample N independent noisy graphs (each 1..max-steps random mutations) and print report.",
    )
    parser.add_argument("--max-attempts", type=int, default=40)
    parser.add_argument(
        "--json-out",
        type=Path,
        default=None,
        help="Optional path to write machine-readable simulation output",
    )
    parser.add_argument(
        "--llm-judge",
        action="store_true",
        help="Sample one graph mutation and run llm_judge on the delta.",
    )
    parser.add_argument(
        "--print-judge-prompt",
        action="store_true",
        help="With --llm-judge, print the judge payload/prompt without calling the LLM.",
    )
    parser.add_argument(
        "--include-raw-graph",
        action="store_true",
        help="Include raw graph nodes/process trees in the LLM judge payload.",
    )
    parser.add_argument("--model", default=None)
    parser.add_argument("--base-url", default=None)
    parser.add_argument("--api-key", default=None)
    parser.add_argument("--max-tokens", type=int, default=2048)
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument("--retries", type=int, default=3)
    parser.add_argument("--sleep", type=float, default=0.5)
    parser.add_argument(
        "--add-sets-input",
        type=Path,
        default=DEFAULT_ACTION_ADD_SETS,
        help="Path to action_add_sets.json for add_or_branch candidates.",
    )
    parser.add_argument(
        "--rebuild-add-sets",
        action="store_true",
        help="Rebuild action_add_sets.json from step2 before running.",
    )
    parser.add_argument(
        "--dump-add-sets",
        action="store_true",
        help="Rebuild action_add_sets.json from step2 and exit.",
    )
    parser.add_argument("--env-file", type=Path, default=DEFAULT_ENV_FILE)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    step2 = load_json(resolve_path(args.step2_input))
    if not isinstance(step2, list):
        raise SystemExit("expected step2 task list")

    add_set_registry = load_add_set_registry(
        path=args.add_sets_input,
        tasks=step2,
        rebuild=bool(args.rebuild_add_sets or args.dump_add_sets),
    )

    if args.dump_add_sets:
        print(
            f"wrote add sets for {len(add_set_registry.sets)} actions to "
            f"{resolve_path(args.add_sets_input)}"
        )
        return 0

    task = next((item for item in step2 if item.get("mac_task_uid") == args.task_uid), None)
    if task is None:
        raise SystemExit(f"task not found: {args.task_uid}")

    action = args.action or str(task.get("user_goal") or (task.get("original_sopbench") or {}).get("user_goal") or "")
    if not action:
        raise SystemExit("could not determine target action")

    if args.llm_judge:
        load_env(args.env_file)
        resolve_llm_config(args)
        delta, _, _ = sample_one_mutation(
            task,
            action=action,
            seed=int(args.seed),
            max_attempts=int(args.max_attempts),
            add_set_registry=add_set_registry,
        )
        print(f"sampled mutation: {delta.mutation}")
        print(f"global_changed={delta.global_changed}")
        changed = [item for item in delta.constraint_deltas if item.get("changed")]
        print(f"changed constraints: {[item.get('constraint_id') for item in changed]}")
        judge_result = llm_judge(
            delta,
            model=str(args.model or ""),
            base_url=args.base_url,
            api_key=args.api_key,
            max_tokens=int(args.max_tokens),
            timeout=float(args.timeout),
            retries=int(args.retries),
            sleep=float(args.sleep),
            skip_llm=bool(args.print_judge_prompt),
            include_raw_graph=bool(args.include_raw_graph),
        )
        if args.print_judge_prompt:
            print("\n=== JUDGE USER PROMPT ===\n")
            print(judge_result.get("user_prompt") or "")
        print_judge_report(judge_result)
        if args.json_out:
            out_path = resolve_path(args.json_out)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(json.dumps(judge_result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            print(f"\nwrote {out_path}")
        return 0

    if int(args.sample_noisy_graphs) > 0:
        batch = sample_noisy_graph_batch(
            task,
            action=action,
            count=int(args.sample_noisy_graphs),
            max_steps=max(1, int(args.max_steps)),
            seed=int(args.seed),
            add_set_registry=add_set_registry,
        )
        print_noisy_graph_batch_report(batch)
        if args.json_out:
            out_path = resolve_path(args.json_out)
            write_json(out_path, noisy_graph_batch_to_json(batch))
            print(f"\nwrote {out_path}")
        return 0

    result = simulate_graph_noise(
        task,
        action=action,
        noise_target=max(0, int(args.noise_target)),
        seed=int(args.seed),
        max_attempts=max(1, int(args.max_attempts)),
        add_set_registry=add_set_registry,
    )
    print_simulation_report(result)

    if args.json_out:
        serializable = {
            **result,
            "baseline_projections": [
                {
                    "mac_constraint_uid": p.mac_constraint_uid,
                    "constraint_id": p.constraint_id,
                    "node_index": p.node_index,
                    "anchor_process": p.anchor_process,
                    "current_process": p.current_process,
                    "changed": p.changed,
                }
                for p in result["baseline_projections"]
            ],
            "steps": [
                {
                    "step": s.step,
                    "mutation": s.mutation,
                    "changed_anchors": s.changed_anchors,
                    "global_changed": s.global_changed,
                    "projections": [
                        {
                            "mac_constraint_uid": p.mac_constraint_uid,
                            "constraint_id": p.constraint_id,
                            "node_index": p.node_index,
                            "anchor_process": p.anchor_process,
                            "current_process": p.current_process,
                            "changed": p.changed,
                        }
                        for p in s.projections
                    ],
                }
                for s in result["steps"]
            ],
        }
        out_path = resolve_path(args.json_out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(serializable, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"\nwrote {out_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
