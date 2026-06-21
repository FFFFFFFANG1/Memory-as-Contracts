from __future__ import annotations

from benchmarks.schemas.models import ContractGraph


def contract_event_positions(graph: ContractGraph) -> dict[str, list[int]]:
    positions: dict[str, set[int]] = {
        "effective": set(),
        "expiry": set(),
        "revocation": set(),
        "relation": set(),
    }
    for node in graph.nodes:
        positions["effective"].add(node.lifecycle.effective_from_event)
        if node.lifecycle.effective_until_event is not None:
            positions["expiry"].add(node.lifecycle.effective_until_event)
        if node.lifecycle.revoked_at_event is not None:
            positions["revocation"].add(node.lifecycle.revoked_at_event)
    if graph.edges:
        earliest = min(node.lifecycle.effective_from_event for node in graph.nodes)
        positions["relation"].add(earliest)
    return {key: sorted(value) for key, value in positions.items()}


def progress_bin(prefix_end_event: int, total_events: int) -> str:
    if total_events <= 0:
        raise ValueError("total_events must be positive")
    progress = prefix_end_event / total_events
    if progress < 0.2:
        return "0-20%"
    if progress < 0.4:
        return "20-40%"
    if progress < 0.6:
        return "40-60%"
    if progress < 0.8:
        return "60-80%"
    return "80-100%"
