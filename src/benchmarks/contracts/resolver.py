from __future__ import annotations

from dataclasses import dataclass

from benchmarks.contracts.lifecycle import lifecycle_active
from benchmarks.contracts.predicates import predicate_matches
from benchmarks.contracts.scope import merged_scope, scope_matches
from benchmarks.schemas.models import CanonicalAction, ContractEdge, ContractGraph, ContractNode, Decision


@dataclass(frozen=True)
class GraphDecision:
    decision: Decision
    active_contract_ids: list[str]
    decisive_relation_ids: list[str]
    decisive_contract_ids: list[str]
    reason: str


def _matching_nodes(
    graph: ContractGraph,
    *,
    prefix_end_event: int,
    current_scope: dict[str, object],
    action: CanonicalAction,
) -> list[ContractNode]:
    scope = merged_scope(current_scope, action.scope)
    return [
        node
        for node in graph.nodes
        if lifecycle_active(node.lifecycle, prefix_end_event)
        and scope_matches(node.scope, scope)
        and predicate_matches(node.action_predicate, action)
    ]


def _active_edges(edges: list[ContractEdge], active_ids: set[str]) -> list[ContractEdge]:
    return [edge for edge in edges if edge.source in active_ids and edge.target in active_ids]


def _defeated_ids(active_edges: list[ContractEdge]) -> tuple[set[str], list[str]]:
    defeated: set[str] = set()
    decisive_edges: list[str] = []
    for edge in active_edges:
        if edge.type in {"exception_to", "overrides", "supersedes"}:
            defeated.add(edge.target)
            decisive_edges.append(edge.id)
    return defeated, decisive_edges


def _has_unresolved_conflict(active_edges: list[ContractEdge], remaining_ids: set[str]) -> list[str]:
    return [
        edge.id
        for edge in active_edges
        if edge.type == "conflicts_with" and edge.source in remaining_ids and edge.target in remaining_ids
    ]


def resolve(
    graph: ContractGraph | dict,
    *,
    prefix_end_event: int,
    current_scope: dict[str, object],
    proposed_action: CanonicalAction | dict,
) -> GraphDecision:
    """Resolve a hidden contract graph for one proposed action.

    The resolver is deliberately conservative: recency and specificity do not
    decide conflicts unless the graph encodes an explicit edge.
    """
    graph_model = graph if isinstance(graph, ContractGraph) else ContractGraph.model_validate(graph)
    action_model = (
        proposed_action
        if isinstance(proposed_action, CanonicalAction)
        else CanonicalAction.model_validate(proposed_action)
    )

    active_nodes = _matching_nodes(
        graph_model,
        prefix_end_event=prefix_end_event,
        current_scope=current_scope,
        action=action_model,
    )
    active_ids = {node.id for node in active_nodes}
    active_edges = _active_edges(graph_model.edges, active_ids)
    defeated, decisive_edges = _defeated_ids(active_edges)
    remaining = [node for node in active_nodes if node.id not in defeated]
    remaining_ids = {node.id for node in remaining}

    conflict_edges = _has_unresolved_conflict(active_edges, remaining_ids)
    if conflict_edges:
        return GraphDecision(
            decision="ask",
            active_contract_ids=sorted(active_ids),
            decisive_relation_ids=sorted(set(decisive_edges + conflict_edges)),
            decisive_contract_ids=sorted(remaining_ids),
            reason="unresolved active contract conflict",
        )

    ask_nodes = [node for node in remaining if node.modality == "ask_before"]
    if ask_nodes:
        return GraphDecision(
            decision="ask",
            active_contract_ids=sorted(active_ids),
            decisive_relation_ids=sorted(set(decisive_edges)),
            decisive_contract_ids=sorted(node.id for node in ask_nodes),
            reason="active contract requires asking before action",
        )

    reject_nodes = [node for node in remaining if node.modality == "must_not"]
    if reject_nodes:
        return GraphDecision(
            decision="reject",
            active_contract_ids=sorted(active_ids),
            decisive_relation_ids=sorted(set(decisive_edges)),
            decisive_contract_ids=sorted(node.id for node in reject_nodes),
            reason="active contract prohibits action",
        )

    allow_nodes = [node for node in remaining if node.modality in {"must", "may", "prefer"}]
    if allow_nodes:
        return GraphDecision(
            decision="allow",
            active_contract_ids=sorted(active_ids),
            decisive_relation_ids=sorted(set(decisive_edges)),
            decisive_contract_ids=sorted(node.id for node in allow_nodes),
            reason="active contracts permit or require action",
        )

    return GraphDecision(
        decision="allow",
        active_contract_ids=sorted(active_ids),
        decisive_relation_ids=sorted(set(decisive_edges)),
        decisive_contract_ids=[],
        reason="no active contract blocks action",
    )
